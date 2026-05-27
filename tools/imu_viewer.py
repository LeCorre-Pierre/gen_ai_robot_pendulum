"""
tools/imu_viewer.py — Visualiseur IMU + guide d'identification des axes.

Reçoit VCP_TYPE_TELEMETRY_IMU (0x11) : 6 axes bruts + pitch estimé.
Aide à identifier quel axe physique correspond à chaque axe BSP.

Usage:
    py -3 tools/imu_viewer.py
    py -3 tools/imu_viewer.py --port COM4 --rate 20
"""

from __future__ import annotations

import struct
import sys
from collections import deque

# PySide6 must be imported before numpy/pyqtgraph to avoid Qt DLL conflicts
# (numpy loads OpenBLAS/MKL DLLs that can interfere with Qt6Core loading).
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGroupBox, QHBoxLayout,
    QLabel, QMainWindow, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

import numpy as np
import pyqtgraph as pg
import serial
import serial.tools.list_ports

# ── Thème sombre (identique à app-pid-tuning/pid_tuner/gui.py) ───────────────
pg.setConfigOptions(antialias=True, background="#1e1e1e", foreground="#cccccc")

# ── Palette ───────────────────────────────────────────────────────────────────
# Accéléromètre : teintes bleues
C_AX = "#42a5f5"   # bleu vif
C_AY = "#1565c0"   # bleu foncé
C_AZ = "#26c6da"   # cyan

# Gyroscope : teintes vertes/oranges
C_GX = "#ff7043"   # orange
C_GY = "#66bb6a"   # vert
C_GZ = "#ab47bc"   # violet

C_PITCH = "#ef5350"   # rouge — pitch estimé
C_ZERO  = "#546e7a"   # gris  — ligne zéro

# ── VCP protocole ─────────────────────────────────────────────────────────────
_SOF1, _SOF2, _EOF, _VER = 0xAA, 0x55, 0x33, 0x01
_TYPE_IMU         = 0x11
_TYPE_STREAM_CTRL = 0x22

# VcpTelImu_t : uint32 + 8×int16 = 20 bytes
# ts_ms, ax_mg, ay_mg, az_mg, gx_x10, gy_x10, gz_x10, pitch_x100, drive_x100
_FMT  = "<Ihhhhhhhh"
_SIZE = struct.calcsize(_FMT)   # 4 + 8×2 = 20

_RATES = [5, 10, 20, 50, 100]
_BAUDS = ["115200", "230400", "460800"]
_WIN_S = 10.0       # fenêtre scrollante
_NPTS  = 20_000     # profondeur ring buffer


# ── Protocole helpers ─────────────────────────────────────────────────────────

def _crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def _frame(pkt_type: int, payload: bytes, seq: int) -> bytes:
    hdr = bytes([_VER, pkt_type, 0, seq & 0xFF,
                 len(payload) & 0xFF, (len(payload) >> 8) & 0xFF])
    crc = _crc16(hdr + payload)
    return bytes([_SOF1, _SOF2]) + hdr + payload + struct.pack("<H", crc) + bytes([_EOF])


def _stream_frame(enable: bool, rate_hz: int, seq: int) -> bytes:
    return _frame(_TYPE_STREAM_CTRL, struct.pack("<BH", int(enable), rate_hz), seq)


def _list_ports():
    result = []
    for p in sorted(serial.tools.list_ports.comports(), key=lambda x: x.device):
        stlink = any(k in (p.description or "").upper()
                     for k in ("STM32", "STLINK", "ST-LINK", "STMICROELECTRONICS"))
        result.append((p.device, p.description or p.device, stlink))
    return result


# ── Thread série ──────────────────────────────────────────────────────────────

class SerialReader(QThread):
    # ts_s, ax, ay, az (g), gx, gy, gz (dps), pitch (deg)
    sample = Signal(float, float, float, float, float, float, float, float)
    rx_bytes  = Signal(int)
    crc_error = Signal()
    error     = Signal(str)

    def __init__(self, ser: serial.Serial, parent=None) -> None:
        super().__init__(parent)
        self._ser      = ser
        self._running  = False
        self._rx_total = 0

    def run(self) -> None:
        self._running  = True
        self._rx_total = 0
        buf = bytearray()
        while self._running:
            try:
                chunk = self._ser.read(256)
            except serial.SerialException as exc:
                self.error.emit(str(exc))
                break
            if chunk:
                self._rx_total += len(chunk)
                self.rx_bytes.emit(self._rx_total)
                buf.extend(chunk)
                self._parse(buf)

    def stop(self) -> None:
        self._running = False

    def write(self, data: bytes) -> None:
        try:
            if self._ser.is_open:
                self._ser.write(data)
        except serial.SerialException:
            pass

    def _parse(self, buf: bytearray) -> None:
        i = 0
        while i < len(buf):
            if buf[i] != _SOF1:
                i += 1; continue
            if i + 1 >= len(buf): break
            if buf[i + 1] != _SOF2:
                i += 1; continue
            if i + 8 > len(buf): break
            plen  = buf[i + 6] | (buf[i + 7] << 8)
            total = 11 + plen
            if i + total > len(buf): break
            frame    = bytes(buf[i:i + total])
            crc_calc = _crc16(frame[2:8 + plen])
            crc_got  = frame[8 + plen] | (frame[9 + plen] << 8)
            if crc_calc == crc_got and frame[10 + plen] == _EOF:
                if frame[3] == _TYPE_IMU and plen >= _SIZE:
                    ts, ax, ay, az, gx, gy, gz, p, _drv = struct.unpack_from(_FMT, frame, 8)
                    self.sample.emit(
                        ts / 1000.0,
                        ax / 1000.0, ay / 1000.0, az / 1000.0,
                        gx / 10.0,  gy / 10.0,  gz / 10.0,
                        p  / 100.0,
                    )
            else:
                self.crc_error.emit()
            i += total
        del buf[:i]


# ── Voyant RX ─────────────────────────────────────────────────────────────────

class _RxLed(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self._lit   = False
        self._timer = QTimer(self, singleShot=True, interval=120)
        self._timer.timeout.connect(self._off)

    def flash(self):
        self._lit = True; self.update(); self._timer.start()

    def reset(self):
        self._lit = False; self._timer.stop(); self.update()

    def _off(self):
        self._lit = False; self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#66bb6a" if self._lit else "#37474f"))
        p.setPen(QColor("#263238"))
        p.drawEllipse(1, 1, 12, 12)


# ── Jauge horizontale ─────────────────────────────────────────────────────────

class BarGauge(QWidget):
    """Barre horizontale bipolaire avec label valeur. Hauteur fixe, largeur flexible."""

    def __init__(self, label: str, color: str, v_max: float, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._v_max = v_max
        self._value = 0.0
        self._dominant = False
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self._lbl = QLabel(label)
        self._lbl.setFixedWidth(32)
        self._lbl.setStyleSheet(f"color:{color};font-size:11px;font-family:Consolas;"
                                f"font-weight:bold;")

        self._canvas = QWidget()
        self._canvas.setMinimumWidth(80)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._canvas.setFixedHeight(16)
        self._canvas.paintEvent = self._paint_canvas  # type: ignore[method-assign]

        self._val_lbl = QLabel("  0.000")
        self._val_lbl.setFixedWidth(58)
        self._val_lbl.setStyleSheet(f"color:{color};font-size:11px;font-family:Consolas;")
        self._val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        lay.addWidget(self._lbl)
        lay.addWidget(self._canvas)
        lay.addWidget(self._val_lbl)

    def set_value(self, v: float) -> None:
        self._value = v
        self._val_lbl.setText(f"{v:+.3f}")
        self._canvas.update()

    def set_dominant(self, dominant: bool) -> None:
        if dominant != self._dominant:
            self._dominant = dominant
            self._lbl.setStyleSheet(
                f"color:{'#ffffff' if dominant else self._color.name()};"
                f"font-size:11px;font-family:Consolas;font-weight:bold;"
            )
            self._canvas.update()

    def _paint_canvas(self, _) -> None:
        p = QPainter(self._canvas)
        p.setRenderHint(QPainter.Antialiasing)
        w = self._canvas.width()
        h = self._canvas.height()
        cx = w // 2

        # Fond
        p.fillRect(0, 0, w, h, QColor("#2a2a2a"))

        # Ligne centrale
        p.setPen(QPen(QColor("#444"), 1))
        p.drawLine(cx, 0, cx, h)

        # Barre
        frac  = max(-1.0, min(1.0, self._value / self._v_max))
        bw    = int(abs(frac) * cx)
        color = self._color if not self._dominant else self._color.lighter(140)
        p.fillRect(cx if frac >= 0 else cx - bw, 2, bw, h - 4, color)


# ── Guide d'identification ────────────────────────────────────────────────────

_STEPS = [
    {
        "title": "① Robot debout, immobile",
        "desc":  "Posez le robot verticalement, sans le tenir.\nUn axe accel doit afficher ≈ +1 g (gravité).",
        "check": "Quel axe accel est proche de +1 g ?",
        "kind":  "accel_static",
    },
    {
        "title": "② Incliner lentement avant / arrière (tangage)",
        "desc":  "Penchez le robot vers l'avant et vers l'arrière.\nL'axe accel de tangage VARIE le plus.",
        "check": "Quel axe accel varie le plus ?",
        "kind":  "accel_dynamic",
    },
    {
        "title": "③ Incliner rapidement avant / arrière",
        "desc":  "Même mouvement, mais rapide.\nL'axe gyro de tangage (pitch rate) s'emballe.",
        "check": "Quel axe gyro varie le plus ?",
        "kind":  "gyro_dynamic",
    },
    {
        "title": "④ Faire tourner sur place (lacet / yaw)",
        "desc":  "Faites pivoter le robot sur lui-même (rotation verticale).\nL'axe gyro de lacet réagit.",
        "check": "Quel axe gyro varie le plus ?",
        "kind":  "gyro_dynamic",
    },
]

_AXIS_COLORS = {
    "Ax": C_AX, "Ay": C_AY, "Az": C_AZ,
    "Gx": C_GX, "Gy": C_GY, "Gz": C_GZ,
}


class GuidePanel(QWidget):
    """Guide d'identification avec détection automatique et boutons de confirmation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self._live_labels:  list[QLabel]       = []
        self._conf_labels:  list[QLabel]       = []
        self._conf_btns:    list[QPushButton]  = []
        self._confirmed:    list[str | None]   = [None] * 4

        # Current live values (for confirm snapshot)
        self._live_static_dom = ("Ax", 0.0, False)   # (axis, value, ok)
        self._live_dyn_accel  = ("Ax", 0.0)
        self._live_dyn_gyro   = ("Gx", 0.0)

        for i, step in enumerate(_STEPS):
            box = QGroupBox(step["title"])
            box.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11px; }")
            bl  = QVBoxLayout(box)
            bl.setContentsMargins(6, 4, 6, 6)
            bl.setSpacing(2)

            desc = QLabel(step["desc"])
            desc.setStyleSheet("color:#90a4ae;font-size:10px;")
            desc.setWordWrap(True)
            bl.addWidget(desc)

            q = QLabel(f"→ {step['check']}")
            q.setStyleSheet("color:#cccccc;font-size:10px;font-style:italic;")
            bl.addWidget(q)

            live = QLabel("  Dominant : —")
            live.setStyleSheet("color:#ffd54f;font-size:11px;font-family:Consolas;"
                               "font-weight:bold;")
            bl.addWidget(live)
            self._live_labels.append(live)

            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            btn = QPushButton("✓ Confirmer")
            btn.setFixedHeight(22)
            btn.setFixedWidth(100)
            btn.setStyleSheet("font-size:10px;")
            btn.clicked.connect(lambda _, idx=i: self._confirm(idx))
            self._conf_btns.append(btn)

            conf = QLabel("")
            conf.setStyleSheet("color:#66bb6a;font-size:11px;font-family:Consolas;"
                               "font-weight:bold;")
            self._conf_labels.append(conf)

            row.addWidget(btn)
            row.addWidget(conf)
            row.addStretch()
            bl.addLayout(row)

            lay.addWidget(box)

        # ── Conclusions ──────────────────────────────────────────────────────
        self._concl_box = QGroupBox("Conclusions")
        self._concl_box.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11px; }")
        cl = QVBoxLayout(self._concl_box)
        cl.setContentsMargins(6, 4, 6, 6)
        cl.setSpacing(2)

        self._concl_labels: list[QLabel] = []
        _names = ["Gravité (vertical)", "Tangage accel", "Tangage gyro", "Lacet gyro"]
        for name in _names:
            lbl = QLabel(f"  {name:<18}: —")
            lbl.setStyleSheet("color:#90a4ae;font-size:10px;font-family:Consolas;")
            cl.addWidget(lbl)
            self._concl_labels.append(lbl)

        copy_btn = QPushButton("Copier")
        copy_btn.setFixedWidth(70)
        copy_btn.setFixedHeight(20)
        copy_btn.setStyleSheet("font-size:10px;")
        copy_btn.clicked.connect(self._copy_conclusions)
        cl.addWidget(copy_btn, alignment=Qt.AlignRight)

        lay.addWidget(self._concl_box)
        lay.addStretch()

    def _confirm(self, idx: int) -> None:
        if idx == 0:
            axis, val, ok = self._live_static_dom
            text = f"✓ {axis} = {val:+.3f} g"
        elif idx == 1:
            axis, val = self._live_dyn_accel
            text = f"✓ {axis} = {val:+.3f} g (variance max)"
        else:
            axis, val = self._live_dyn_gyro
            text = f"✓ {axis} = {val:+.1f} °/s (variance max)"

        self._confirmed[idx] = axis
        lbl = self._conf_labels[idx]
        lbl.setText(text)
        color = _AXIS_COLORS.get(axis, "#66bb6a")
        lbl.setStyleSheet(f"color:{color};font-size:11px;font-family:Consolas;"
                          f"font-weight:bold;")
        self._update_conclusions()

    def _update_conclusions(self) -> None:
        for i, lbl in enumerate(self._concl_labels):
            axis = self._confirmed[i]
            _names = ["Gravité (vertical)", "Tangage accel", "Tangage gyro", "Lacet gyro"]
            if axis is None:
                lbl.setText(f"  {_names[i]:<18}: —")
                lbl.setStyleSheet("color:#90a4ae;font-size:10px;font-family:Consolas;")
            else:
                color = _AXIS_COLORS.get(axis, "#66bb6a")
                lbl.setText(f"  {_names[i]:<18}: {axis}")
                lbl.setStyleSheet(f"color:{color};font-size:10px;font-family:Consolas;"
                                  f"font-weight:bold;")

    def _copy_conclusions(self) -> None:
        _names = ["Gravite (vertical)", "Tangage accel", "Tangage gyro", "Lacet gyro"]
        lines  = [f"{_names[i]}: {self._confirmed[i] or '?'}" for i in range(4)]
        QApplication.clipboard().setText("\n".join(lines))

    def update_dominant(self,
                        ax: float, ay: float, az: float,
                        gx: float, gy: float, gz: float,
                        var_ax: float, var_ay: float, var_az: float,
                        var_gx: float, var_gy: float, var_gz: float) -> None:
        # ── Étape 1 : axe accel le plus proche de ±1 g (statique) ───────────
        gravity_vals  = {"Ax": ax, "Ay": ay, "Az": az}
        gravity_axis  = max(gravity_vals, key=lambda k: abs(gravity_vals[k]))
        gv = gravity_vals[gravity_axis]
        ok = abs(abs(gv) - 1.0) < 0.15
        self._live_static_dom = (gravity_axis, gv, ok)
        mark = "✓" if ok else "≈"
        self._live_labels[0].setText(f"  {mark} {gravity_axis} = {gv:+.3f} g")
        self._live_labels[0].setStyleSheet(
            f"color:{'#66bb6a' if ok else '#ffd54f'};"
            f"font-size:11px;font-family:Consolas;font-weight:bold;"
        )

        # ── Étape 2 : axe accel avec la plus grande variance (dynamique) ─────
        accel_var   = {"Ax": var_ax, "Ay": var_ay, "Az": var_az}
        accel_dyn   = max(accel_var, key=accel_var.get)
        accel_dyn_v = {"Ax": ax, "Ay": ay, "Az": az}[accel_dyn]
        self._live_dyn_accel = (accel_dyn, accel_dyn_v)
        self._live_labels[1].setText(
            f"  → {accel_dyn} = {accel_dyn_v:+.3f} g  (σ²={accel_var[accel_dyn]:.4f})"
        )

        # ── Étapes 3 & 4 : axe gyro avec la plus grande variance ─────────────
        gyro_var  = {"Gx": var_gx, "Gy": var_gy, "Gz": var_gz}
        gyro_dyn  = max(gyro_var, key=gyro_var.get)
        gyro_dyn_v = {"Gx": gx, "Gy": gy, "Gz": gz}[gyro_dyn]
        self._live_dyn_gyro = (gyro_dyn, gyro_dyn_v)
        gyro_txt = f"  → {gyro_dyn} = {gyro_dyn_v:+.1f} °/s  (σ²={gyro_var[gyro_dyn]:.1f})"
        self._live_labels[2].setText(gyro_txt)
        self._live_labels[3].setText(gyro_txt)


# ── Fenêtre principale ────────────────────────────────────────────────────────

class ImuViewer(QMainWindow):

    def __init__(self, args) -> None:
        super().__init__()
        self.setWindowTitle("IMU Viewer — Identification des axes")
        self.setMinimumSize(1200, 700)

        self._ser:    serial.Serial | None = None
        self._reader: SerialReader  | None = None
        self._tx_seq = 0
        self._pkt_cnt = 0
        self._crc_cnt = 0

        # Ring buffers (plots)
        self._t  = deque(maxlen=_NPTS)
        self._ax = deque(maxlen=_NPTS)
        self._ay = deque(maxlen=_NPTS)
        self._az = deque(maxlen=_NPTS)
        self._gx = deque(maxlen=_NPTS)
        self._gy = deque(maxlen=_NPTS)
        self._gz = deque(maxlen=_NPTS)
        self._pitch = deque(maxlen=_NPTS)

        # Short rolling window for variance (≈2 s at 20 Hz → 40 samples)
        _VAR_WIN = 40
        self._w_ax = deque(maxlen=_VAR_WIN)
        self._w_ay = deque(maxlen=_VAR_WIN)
        self._w_az = deque(maxlen=_VAR_WIN)
        self._w_gx = deque(maxlen=_VAR_WIN)
        self._w_gy = deque(maxlen=_VAR_WIN)
        self._w_gz = deque(maxlen=_VAR_WIN)

        self._build_ui()

        # 30 FPS
        self._plot_timer = QTimer(self, interval=33)
        self._plot_timer.timeout.connect(self._refresh)
        self._plot_timer.start()

        self._refresh_ports()
        if args.port:
            idx = self._port_combo.findData(args.port)
            if idx >= 0:
                self._port_combo.setCurrentIndex(idx)
        if args.rate in _RATES:
            self._rate_combo.setCurrentIndex(_RATES.index(args.rate))

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = self.addToolBar("Connexion")
        toolbar.setMovable(False)

        self._port_combo = QComboBox(); self._port_combo.setMinimumWidth(200)
        ref_btn = QPushButton("↺"); ref_btn.setFixedWidth(28)
        ref_btn.clicked.connect(self._refresh_ports)

        self._baud_combo = QComboBox()
        for b in _BAUDS: self._baud_combo.addItem(b)

        self._connect_btn = QPushButton("Connecter")
        self._connect_btn.setFixedWidth(100)
        self._connect_btn.clicked.connect(self._on_connect_toggle)

        self._rate_combo = QComboBox()
        for r in _RATES: self._rate_combo.addItem(f"{r} Hz", userData=r)
        self._rate_combo.setCurrentIndex(_RATES.index(20))
        self._rate_combo.currentIndexChanged.connect(self._on_rate_changed)

        self._stream_btn = QPushButton("▶ Stream")
        self._stream_btn.setCheckable(True)
        self._stream_btn.setEnabled(False)
        self._stream_btn.setFixedWidth(90)
        self._stream_btn.clicked.connect(self._on_stream_toggle)

        self._clear_btn = QPushButton("Effacer")
        self._clear_btn.clicked.connect(self._clear)

        self._rx_led    = _RxLed()
        self._rx_label  = QLabel("RX: 0 B")
        self._rx_label.setStyleSheet("color:#90a4ae;")
        self._pkt_label = QLabel("PKT: 0")
        self._pkt_label.setStyleSheet("color:#90a4ae;")
        self._crc_label = QLabel("CRC: 0")

        for w in (QLabel("Port:"), self._port_combo, ref_btn,
                  QLabel("Baud:"), self._baud_combo, self._connect_btn,
                  _vsep(),
                  QLabel("Cadence:"), self._rate_combo,
                  self._stream_btn, self._clear_btn,
                  _vsep(),
                  self._rx_led, self._rx_label,
                  self._pkt_label, self._crc_label):
            toolbar.addWidget(w)

        # ── Layout central : plots | jauges + guide ───────────────────────────
        central = QWidget()
        h_lay   = QHBoxLayout(central)
        h_lay.setContentsMargins(4, 4, 4, 4)
        h_lay.setSpacing(6)

        h_lay.addWidget(self._build_plots(), stretch=3)
        h_lay.addWidget(self._build_right(), stretch=0)

        self.setCentralWidget(central)

    def _build_plots(self) -> QWidget:
        w   = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        def _pw(title, ylabel, yunits) -> pg.PlotWidget:
            pw = pg.PlotWidget(title=title)
            pw.showGrid(x=True, y=True, alpha=0.3)
            pw.setLabel("left", ylabel, units=yunits)
            pw.addLegend(offset=(10, 10))
            pw.getPlotItem().getViewBox().disableAutoRange(pg.ViewBox.XAxis)
            return pw

        # ── Accéléromètre ─────────────────────────────────────────────────
        self._pw_a = _pw("Accéléromètre — 3 axes", "accel", "g")
        self._pw_a.addLine(y=0,   pen=pg.mkPen(C_ZERO,  width=1, style=Qt.DashLine))
        self._pw_a.addLine(y=1.0, pen=pg.mkPen("#37474f", width=1, style=Qt.DashLine))
        self._c_ax = self._pw_a.plot(pen=pg.mkPen(C_AX, width=2), name="Ax")
        self._c_ay = self._pw_a.plot(pen=pg.mkPen(C_AY, width=2), name="Ay")
        self._c_az = self._pw_a.plot(pen=pg.mkPen(C_AZ, width=2), name="Az")

        # ── Gyroscope ─────────────────────────────────────────────────────
        self._pw_g = _pw("Gyroscope — 3 axes", "gyro", "°/s")
        self._pw_g.setXLink(self._pw_a)
        self._pw_g.addLine(y=0, pen=pg.mkPen(C_ZERO, width=1, style=Qt.DashLine))
        self._c_gx = self._pw_g.plot(pen=pg.mkPen(C_GX, width=2), name="Gx")
        self._c_gy = self._pw_g.plot(pen=pg.mkPen(C_GY, width=2), name="Gy")
        self._c_gz = self._pw_g.plot(pen=pg.mkPen(C_GZ, width=2), name="Gz")

        # ── Pitch estimé ──────────────────────────────────────────────────
        self._pw_p = _pw("Pitch estimé (filtre complémentaire)", "pitch", "°")
        self._pw_p.setXLink(self._pw_a)
        self._pw_p.addLine(y=0,   pen=pg.mkPen(C_ZERO,  width=1, style=Qt.DashLine))
        self._pw_p.addLine(y=45,  pen=pg.mkPen("#ff7043", width=1, style=Qt.DotLine))
        self._pw_p.addLine(y=-45, pen=pg.mkPen("#ff7043", width=1, style=Qt.DotLine))
        self._c_pitch = self._pw_p.plot(pen=pg.mkPen(C_PITCH, width=2), name="pitch_deg")

        for c in (self._c_ax, self._c_ay, self._c_az,
                  self._c_gx, self._c_gy, self._c_gz, self._c_pitch):
            c.setDownsampling(auto=True, method="subsample")
            c.setClipToView(True)

        lay.addWidget(self._pw_a,  stretch=2)
        lay.addWidget(self._pw_g,  stretch=2)
        lay.addWidget(self._pw_p,  stretch=1)
        return w

    def _build_right(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedWidth(290)

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(8)

        # ── Jauges accéléromètre ──────────────────────────────────────────
        a_box = QGroupBox("Accéléromètre (g)  — plage ±2 g")
        a_lay = QVBoxLayout(a_box)
        a_lay.setSpacing(2)
        a_lay.setContentsMargins(6, 6, 6, 6)
        self._g_ax = BarGauge("Ax", C_AX, 2.0)
        self._g_ay = BarGauge("Ay", C_AY, 2.0)
        self._g_az = BarGauge("Az", C_AZ, 2.0)
        for g in (self._g_ax, self._g_ay, self._g_az):
            a_lay.addWidget(g)
        lay.addWidget(a_box)

        # ── Jauges gyroscope ──────────────────────────────────────────────
        g_box = QGroupBox("Gyroscope (°/s)  — plage ±250 °/s")
        g_lay = QVBoxLayout(g_box)
        g_lay.setSpacing(2)
        g_lay.setContentsMargins(6, 6, 6, 6)
        self._g_gx = BarGauge("Gx", C_GX, 250.0)
        self._g_gy = BarGauge("Gy", C_GY, 250.0)
        self._g_gz = BarGauge("Gz", C_GZ, 250.0)
        for g in (self._g_gx, self._g_gy, self._g_gz):
            g_lay.addWidget(g)
        lay.addWidget(g_box)

        # ── Guide d'identification ─────────────────────────────────────────
        lay.addWidget(QLabel("<b>Guide d'identification</b>"))
        self._guide = GuidePanel()
        lay.addWidget(self._guide)

        scroll.setWidget(container)
        return scroll

    # ── Connexion ─────────────────────────────────────────────────────────────

    def _on_connect_toggle(self) -> None:
        if self._reader:
            self._disconnect()
        else:
            port = self._port_combo.currentData()
            baud = int(self._baud_combo.currentText())
            if not port:
                return
            try:
                self._ser = serial.Serial(port, baud, timeout=0.05)
            except serial.SerialException as exc:
                self.statusBar().showMessage(f"Erreur : {exc}", 5000)
                return
            self._reader = SerialReader(self._ser)
            self._reader.sample.connect(self._on_sample)
            self._reader.rx_bytes.connect(self._on_rx)
            self._reader.crc_error.connect(self._on_crc)
            self._reader.error.connect(self._on_err)
            self._reader.start()
            self._connect_btn.setText("Déconnecter")
            self._stream_btn.setEnabled(True)
            self._port_combo.setEnabled(False)
            self._baud_combo.setEnabled(False)
            self.statusBar().showMessage(f"Connecté sur {port}")
            # Auto-démarrer le stream
            self._stream_btn.setChecked(True)
            self._send_stream(True)
            self._stream_btn.setText("⏹ Stop")

    def _disconnect(self) -> None:
        self._send_stream(False)
        if self._reader:
            self._reader.stop()
            self._reader.wait(800)
            self._reader = None
        if self._ser and self._ser.is_open:
            try: self._ser.close()
            except Exception: pass
            self._ser = None
        self._connect_btn.setText("Connecter")
        self._stream_btn.setChecked(False)
        self._stream_btn.setEnabled(False)
        self._stream_btn.setText("▶ Stream")
        self._port_combo.setEnabled(True)
        self._baud_combo.setEnabled(True)
        self._rx_led.reset()
        self.statusBar().showMessage("Déconnecté")

    def _on_stream_toggle(self, checked: bool) -> None:
        self._send_stream(checked)
        self._stream_btn.setText("⏹ Stop" if checked else "▶ Stream")

    def _on_rate_changed(self) -> None:
        if self._reader and self._stream_btn.isChecked():
            self._send_stream(True)

    def _send_stream(self, enable: bool) -> None:
        if not self._reader:
            return
        rate  = self._rate_combo.currentData()
        frame = _stream_frame(enable, rate, self._tx_seq)
        self._tx_seq = (self._tx_seq + 1) & 0xFF
        self._reader.write(frame)

    # ── Données ───────────────────────────────────────────────────────────────

    def _on_sample(self, ts: float,
                   ax: float, ay: float, az: float,
                   gx: float, gy: float, gz: float,
                   pitch: float) -> None:
        self._t.append(ts)
        self._ax.append(ax); self._ay.append(ay); self._az.append(az)
        self._gx.append(gx); self._gy.append(gy); self._gz.append(gz)
        self._pitch.append(pitch)

        # Rolling variance window
        self._w_ax.append(ax); self._w_ay.append(ay); self._w_az.append(az)
        self._w_gx.append(gx); self._w_gy.append(gy); self._w_gz.append(gz)

        def _var(d):
            if len(d) < 2: return 0.0
            a = np.fromiter(d, float, len(d))
            return float(np.var(a))

        var_ax = _var(self._w_ax); var_ay = _var(self._w_ay); var_az = _var(self._w_az)
        var_gx = _var(self._w_gx); var_gy = _var(self._w_gy); var_gz = _var(self._w_gz)

        self._pkt_cnt += 1
        self._pkt_label.setText(f"PKT: {self._pkt_cnt}")

        # Jauges
        self._g_ax.set_value(ax); self._g_ay.set_value(ay); self._g_az.set_value(az)
        self._g_gx.set_value(gx); self._g_gy.set_value(gy); self._g_gz.set_value(gz)

        # Dominant accel (max |valeur|)
        a_vals = [abs(ax), abs(ay), abs(az)]
        a_dom  = a_vals.index(max(a_vals))
        self._g_ax.set_dominant(a_dom == 0)
        self._g_ay.set_dominant(a_dom == 1)
        self._g_az.set_dominant(a_dom == 2)

        # Dominant gyro (max |valeur|)
        g_vals = [abs(gx), abs(gy), abs(gz)]
        g_dom  = g_vals.index(max(g_vals))
        self._g_gx.set_dominant(g_dom == 0)
        self._g_gy.set_dominant(g_dom == 1)
        self._g_gz.set_dominant(g_dom == 2)

        # Guide (variance-based detection for steps 2-4)
        self._guide.update_dominant(ax, ay, az, gx, gy, gz,
                                    var_ax, var_ay, var_az,
                                    var_gx, var_gy, var_gz)

    def _on_rx(self, total: int) -> None:
        self._rx_led.flash()
        self._rx_label.setText(
            f"RX: {total} B" if total < 1024 else f"RX: {total/1024:.1f} KB"
        )

    def _on_crc(self) -> None:
        self._crc_cnt += 1
        self._crc_label.setText(f"CRC: {self._crc_cnt}")
        self._crc_label.setStyleSheet("color:#ef5350;")

    def _on_err(self, msg: str) -> None:
        self._disconnect()
        self.statusBar().showMessage(f"Erreur série : {msg}", 6000)

    # ── Rafraîchissement plots ────────────────────────────────────────────────

    def _refresh(self) -> None:
        if not self._t:
            return
        t     = np.fromiter(self._t, float, len(self._t))
        t_now = t[-1]
        mask  = t >= (t_now - _WIN_S)
        t_w   = t[mask]

        def _s(curve, buf):
            curve.setData(x=t_w, y=np.fromiter(buf, float, len(buf))[mask])

        _s(self._c_ax, self._ax); _s(self._c_ay, self._ay); _s(self._c_az, self._az)
        _s(self._c_gx, self._gx); _s(self._c_gy, self._gy); _s(self._c_gz, self._gz)
        _s(self._c_pitch, self._pitch)

        xr = (t_now - _WIN_S, t_now)
        for pw in (self._pw_a, self._pw_g, self._pw_p):
            pw.setXRange(*xr, padding=0)

    def _clear(self) -> None:
        for d in (self._t, self._ax, self._ay, self._az,
                  self._gx, self._gy, self._gz, self._pitch):
            d.clear()
        for c in (self._c_ax, self._c_ay, self._c_az,
                  self._c_gx, self._c_gy, self._c_gz, self._c_pitch):
            c.setData([], [])
        self._pkt_cnt = 0
        self._pkt_label.setText("PKT: 0")

    def _refresh_ports(self) -> None:
        self._port_combo.clear()
        for dev, desc, stlink in _list_ports():
            self._port_combo.addItem(
                f"{'⭐ ' if stlink else ''}{dev} — {desc}", userData=dev
            )
        if not self._port_combo.count():
            self._port_combo.addItem("(aucun port)", userData="")

    def closeEvent(self, event) -> None:
        self._disconnect(); event.accept()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _vsep() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.VLine); f.setFrameShadow(QFrame.Sunken)
    return f


# ── Point d'entrée ───────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="")
    ap.add_argument("--rate", type=int, default=20)
    args = ap.parse_args()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    from PySide6.QtGui import QPalette
    pal = QPalette()
    pal.setColor(QPalette.Window,          QColor("#2b2b2b"))
    pal.setColor(QPalette.WindowText,      QColor("#cccccc"))
    pal.setColor(QPalette.Base,            QColor("#1e1e1e"))
    pal.setColor(QPalette.AlternateBase,   QColor("#252525"))
    pal.setColor(QPalette.Text,            QColor("#cccccc"))
    pal.setColor(QPalette.Button,          QColor("#3c3c3c"))
    pal.setColor(QPalette.ButtonText,      QColor("#cccccc"))
    pal.setColor(QPalette.Highlight,       QColor("#42a5f5"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)

    win = ImuViewer(args)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
