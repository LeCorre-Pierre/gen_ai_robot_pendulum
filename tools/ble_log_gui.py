#!/usr/bin/env python3
"""
ble_log_gui.py — Moniteur GRAPHIQUE des traces serie du firmware emb-sw-ble.

Fenetre Tkinter : log colore qui defile + panneau de compteurs live
(connexions, deconnexions, notif on/off, commandes, erreurs).

    py -3.11 tools/ble_log_gui.py
    py -3.11 tools/ble_log_gui.py --port COM5

Dependances : tkinter (stdlib) + pyserial.
"""
import argparse
import queue
import re
import threading
import time
import tkinter as tk
from tkinter import ttk

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    raise SystemExit("pyserial manquant : pip install pyserial")

# (categorie, regex, couleur)
RULES = [
    ("error",   re.compile(r"\bFail\b|error|ERR_|HardFault|assert", re.I), "#ff5555"),
    ("command", re.compile(r"ROBOT APP : (DRIVE|EMERGENCY_STOP|RESUME|DEMO_|unknown)", re.I), "#ff79c6"),
    ("notify",  re.compile(r"notifications? (ENABLED|DISABLED)", re.I), "#f1fa8c"),
    ("conn",    re.compile(r"HCI_LE_CONNECTION_COMPLETE", re.I), "#8be9fd"),
    ("disc",    re.compile(r"HCI_DISCONNECTION_COMPLETE", re.I), "#ffb86c"),
    ("robot",   re.compile(r"ROBOT", re.I), "#bd93f9"),
    ("ble",     re.compile(r">>==|==>>|SHCI|GAP|GATT|Advertis|Success", re.I), "#50fa7b"),
]

# Compteurs : (cle, libelle, regex)
COUNTERS = [
    ("conn",  "Connexions",   re.compile(r"HCI_LE_CONNECTION_COMPLETE", re.I)),
    ("disc",  "Deconnexions", re.compile(r"HCI_DISCONNECTION_COMPLETE", re.I)),
    ("non",   "Notif ON",     re.compile(r"notifications? ENABLED", re.I)),
    ("noff",  "Notif OFF",    re.compile(r"notifications? DISABLED", re.I)),
    ("cmd",   "Commandes",    re.compile(r"ROBOT APP : (DRIVE|EMERGENCY|RESUME|DEMO_|unknown)", re.I)),
    ("err",   "Erreurs",      re.compile(r"\bFail\b|error|HardFault", re.I)),
]


def categorize(line: str) -> str:
    for name, rx, _ in RULES:
        if rx.search(line):
            return name
    return "info"


class SerialReader(threading.Thread):
    def __init__(self, port, baud, out_queue):
        super().__init__(daemon=True)
        self.port, self.baud, self.q = port, baud, out_queue
        self._stop = threading.Event()
        self.error = None

    def run(self):
        try:
            ser = serial.Serial(self.port, self.baud, timeout=0.2)
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
            self.q.put(("__error__", self.error))
            return
        buf = b""
        while not self._stop.is_set():
            try:
                data = ser.read(256)
            except Exception as exc:  # noqa: BLE001
                self.q.put(("__error__", str(exc)))
                break
            if data:
                buf += data
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    line = raw.decode("utf-8", "replace").rstrip("\r")
                    if line:
                        self.q.put(("line", line))
        ser.close()

    def stop(self):
        self._stop.set()


class App:
    def __init__(self, root, default_port):
        self.root = root
        self.q = queue.Queue()
        self.reader = None
        self.t0 = None
        self.counts = {k: 0 for k, _, _ in COUNTERS}
        root.title("emb-sw-ble — Moniteur de traces BLE")
        root.configure(bg="#282a36")

        # --- barre du haut ---
        top = tk.Frame(root, bg="#282a36")
        top.pack(fill=tk.X, padx=6, pady=4)
        tk.Label(top, text="Port:", fg="#f8f8f2", bg="#282a36").pack(side=tk.LEFT)
        self.port_var = tk.StringVar(value=default_port)
        ports = [p.device for p in list_ports.comports()] or [default_port]
        self.port_cb = ttk.Combobox(top, textvariable=self.port_var, values=ports, width=10)
        self.port_cb.pack(side=tk.LEFT, padx=4)
        self.btn = tk.Button(top, text="Connecter", command=self.toggle, width=12)
        self.btn.pack(side=tk.LEFT, padx=4)
        tk.Button(top, text="Effacer", command=self.clear).pack(side=tk.LEFT, padx=4)
        self.status = tk.Label(top, text="deconnecte", fg="#ffb86c", bg="#282a36")
        self.status.pack(side=tk.LEFT, padx=8)

        # --- corps : log + compteurs ---
        body = tk.Frame(root, bg="#282a36")
        body.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        self.text = tk.Text(body, bg="#1e1f29", fg="#f8f8f2", insertbackground="#f8f8f2",
                            font=("Consolas", 10), width=90, height=30, wrap=tk.NONE)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = tk.Scrollbar(body, command=self.text.yview)
        sb.pack(side=tk.LEFT, fill=tk.Y)
        self.text.config(yscrollcommand=sb.set)
        for name, _, color in RULES:
            self.text.tag_config(name, foreground=color)
        self.text.tag_config("info", foreground="#a0a0b0")

        panel = tk.Frame(body, bg="#282a36")
        panel.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0))
        tk.Label(panel, text="COMPTEURS", fg="#f8f8f2", bg="#282a36",
                 font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(0, 6))
        self.count_labels = {}
        for key, label, _ in COUNTERS:
            row = tk.Frame(panel, bg="#282a36")
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=label + ":", fg="#bbbbcc", bg="#282a36",
                     width=12, anchor=tk.W).pack(side=tk.LEFT)
            v = tk.Label(row, text="0", fg="#50fa7b", bg="#282a36",
                         font=("Consolas", 12, "bold"), width=6, anchor=tk.E)
            v.pack(side=tk.LEFT)
            self.count_labels[key] = v

        self.root.after(50, self.poll)

    def toggle(self):
        if self.reader is None:
            self.t0 = time.monotonic()
            self.reader = SerialReader(self.port_var.get(), 115200, self.q)
            self.reader.start()
            self.btn.config(text="Deconnecter")
            self.status.config(text="connecte a " + self.port_var.get(), fg="#50fa7b")
        else:
            self.reader.stop()
            self.reader = None
            self.btn.config(text="Connecter")
            self.status.config(text="deconnecte", fg="#ffb86c")

    def clear(self):
        self.text.delete("1.0", tk.END)
        for k in self.counts:
            self.counts[k] = 0
            self.count_labels[k].config(text="0")

    def add_line(self, line):
        cat = categorize(line)
        ts = (time.monotonic() - self.t0) if self.t0 else 0.0
        self.text.insert(tk.END, f"[{ts:8.2f}] {line}\n", cat)
        self.text.see(tk.END)
        for key, _, rx in COUNTERS:
            if rx.search(line):
                self.counts[key] += 1
                self.count_labels[key].config(text=str(self.counts[key]))

    def poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "__error__":
                    self.status.config(text="ERREUR: " + payload, fg="#ff5555")
                    if self.reader:
                        self.reader = None
                        self.btn.config(text="Connecter")
                else:
                    self.add_line(payload)
        except queue.Empty:
            pass
        self.root.after(50, self.poll)


def main():
    ap = argparse.ArgumentParser(description="Moniteur graphique des traces emb-sw-ble")
    ap.add_argument("--port", default="COM4")
    args = ap.parse_args()
    root = tk.Tk()
    App(root, args.port)
    root.mainloop()


if __name__ == "__main__":
    main()
