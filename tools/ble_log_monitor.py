#!/usr/bin/env python3
"""
ble_log_monitor.py — Moniteur/analyseur des traces serie du firmware emb-sw-ble.

Lit les APP_DBG_MSG emis sur le VCP ST-Link (USART1), en direct depuis un port
COM ou depuis un fichier de log deja capture. Chaque ligne est horodatee et
coloree par categorie ; un resume est affiche a la sortie (Ctrl+C).

Exemples :
    py -3.11 tools/ble_log_monitor.py                  # live COM4 @115200
    py -3.11 tools/ble_log_monitor.py --port COM5
    py -3.11 tools/ble_log_monitor.py --file capture.log
    py -3.11 tools/ble_log_monitor.py --no-color | tee run.log
"""
import argparse
import re
import sys
import time
from collections import Counter

# ---- Categorisation des lignes -------------------------------------------------
# (nom, regex, couleur ANSI)
# Ordre important : les lignes commande/notif contiennent aussi "ROBOT APP",
# donc on les teste AVANT la regle generique "robot".
RULES = [
    ("error",   re.compile(r"\bFail\b|error|ERR_|HardFault|assert", re.I), "\033[91m"),  # rouge
    ("command", re.compile(r"DRIVE|EMERGENCY_STOP|RESUME|DEMO_|unknown CMD", re.I), "\033[95m"),  # magenta
    ("notify",  re.compile(r"notifications? (ENABLED|DISABLED)", re.I),    "\033[93m"),  # jaune
    ("robot",   re.compile(r"ROBOT APP", re.I),                            "\033[96m"),  # cyan
    ("ble",     re.compile(r">>==|==>>|SHCI|GAP|GATT|Advertis|Connection|WIRELESS", re.I), "\033[92m"),  # vert
    ("success", re.compile(r"\bSuccess\b", re.I),                          "\033[92m"),  # vert
]
RESET = "\033[0m"


def categorize(line: str):
    for name, rx, color in RULES:
        if rx.search(line):
            return name, color
    return "info", ""


def emit(line: str, t0: float, use_color: bool, stats: Counter, failures: list, commands: list):
    name, color = categorize(line)
    stats[name] += 1
    if name == "error":
        failures.append(line)
    if name == "command":
        commands.append(line)
    ts = time.monotonic() - t0
    prefix = f"[{ts:8.3f}] "
    if use_color and color:
        print(f"{prefix}{color}{line}{RESET}")
    else:
        print(f"{prefix}{line}")
    sys.stdout.flush()


def summary(stats: Counter, failures: list, commands: list, use_color: bool = True):
    warn = "\033[91m" if use_color else ""
    rst = RESET if use_color else ""
    print("\n" + "=" * 60)
    print("RESUME")
    print("=" * 60)
    total = sum(stats.values())
    print(f"  Lignes totales      : {total}")
    for cat in ("success", "ble", "robot", "notify", "command", "error", "info"):
        if stats[cat]:
            print(f"  {cat:18}: {stats[cat]}")
    if commands:
        print(f"\n  Commandes recues ({len(commands)}):")
        for c in commands[-10:]:
            print(f"    - {c.strip()}")
    if failures:
        print(f"\n  {warn}/!\\ {len(failures)} echec(s) detecte(s):{rst}")
        for f in failures[-10:]:
            print(f"    - {f.strip()}")
    else:
        print("\n  Aucun echec detecte.")
    print("=" * 60)


def run_file(path: str, use_color: bool):
    stats, failures, commands = Counter(), [], []
    t0 = time.monotonic()
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            if line:
                emit(line, t0, use_color, stats, failures, commands)
    summary(stats, failures, commands, use_color)


def run_serial(port: str, baud: int, use_color: bool):
    try:
        import serial  # pyserial
    except ImportError:
        sys.exit("pyserial manquant : pip install pyserial")

    stats, failures, commands = Counter(), [], []
    t0 = time.monotonic()
    print(f"# Lecture {port} @ {baud} bauds — Ctrl+C pour arreter et resumer\n")
    try:
        ser = serial.Serial(port, baud, timeout=0.2)
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"Impossible d'ouvrir {port} : {exc}")

    buf = b""
    try:
        while True:
            data = ser.read(256)
            if not data:
                continue
            buf += data
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                line = raw.decode("utf-8", "replace").rstrip("\r")
                if line:
                    emit(line, t0, use_color, stats, failures, commands)
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        summary(stats, failures, commands, use_color)


def main():
    ap = argparse.ArgumentParser(description="Moniteur/analyseur des traces serie emb-sw-ble")
    ap.add_argument("--port", default="COM4", help="port serie VCP ST-Link (defaut: COM4)")
    ap.add_argument("--baud", type=int, default=115200, help="debit (defaut: 115200)")
    ap.add_argument("--file", help="analyser un fichier de log au lieu du port serie")
    ap.add_argument("--no-color", action="store_true", help="desactiver la couleur ANSI")
    args = ap.parse_args()

    use_color = not args.no_color
    if args.file:
        run_file(args.file, use_color)
    else:
        run_serial(args.port, args.baud, use_color)


if __name__ == "__main__":
    main()
