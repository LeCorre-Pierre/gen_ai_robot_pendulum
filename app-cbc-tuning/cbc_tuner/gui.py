"""
cbc_tuner/gui.py — CBC balance PID tuning interface.

Telemetry received:
  VCP_TYPE_TELEMETRY_IMU (0x11) → pitch, drive output, pitch rate
  VCP_TYPE_TELEMETRY_PID (0x10) → motor RPM measured, motor PWM output

Commands sent:
  VCP_TYPE_CMD_SET_BALANCE_GAINS (0x24) → loop_id=0, kp, ki, kd  (angle only)
  VCP_TYPE_CMD_STREAM_CTRL       (0x22) → enable, rate_hz
"""
from __future__ import annotations

import struct
import time as _time
from collections import deque
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QThread, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox,
    QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

import numpy as np
import pyqtgraph as pg
import serial
import serial.tools.list_ports

from .mcp_server import StateServer, TunerState
from .sweep_panel import SweepPanel

pg.setConfigOptions(antialias=True, background="#1e1e1e", foreground="#cccccc")

C_PITCH  = "#ef5350"
C_DRIVE  = "#66bb6a"
C_ZERO   = "#546e7a"
C_SAFETY = "#ff7043"
C_P_TERM = "#ef5350"   # rouge  — terme P
C_I_TERM = "#66bb6a"   # vert   — terme I
C_D_TERM = "#42a5f5"   # bleu   — terme D

_SOF1, _SOF2, _EOF, _VER = 0xAA, 0x55, 0x33, 0x01

_TYPE_TEL_PID   = 0x10
_TYPE_TEL_IMU   = 0x11
_TYPE_STREAM    = 0x22
_TYPE_BAL_GAINS = 0x24

# VcpTelPid_t : uint32 + 7×int16 = 18 bytes
# ts, sp_rpm, pv_l, pv_r, err_l, err_r, pwm_l_x100, pwm_r_x100
_FMT_PID = "<Ihhhhhhh"
_SZ_PID  = struct.calcsize(_FMT_PID)   # 18

# VcpTelImu_t : uint32 + 8×int16 = 20 bytes
# ts, ax, ay, az, gx, gy, gz, pitch_x100, drive_x100
_FMT_IMU = "<Ihhhhhhhh"
_SZ_IMU  = struct.calcsize(_FMT_IMU)   # 20

_RATES    = [5, 10, 20, 50, 100]
_BAUDS    = ["115200", "230400"]
_NPTS     = 12_000

_CFG_DIR  = Path.home() / ".config" / "cbc-tuner"
_CFG_FILE = str(_CFG_DIR / "settings.ini")


# ── Protocol helpers ──────────────────────────────────────────────────────────

def _crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc

def _build_frame(pkt_type: int, payload: bytes, seq: int) -> bytes:
    hdr = bytes([_VER, pkt_type, 0, seq & 0xFF,
                 len(payload) & 0xFF, (len(payload) >> 8) & 0xFF])
    crc = _crc16(hdr + payload)
    return bytes([_SOF1, _SOF2]) + hdr + payload + struct.pack("<H", crc) + bytes([_EOF])

def _stream_frame(enable: bool, rate_hz: int, seq: int) -> bytes:
    return _build_frame(_TYPE_STREAM, struct.pack("<BH", int(enable), rate_hz), seq)

def _gains_frame(loop_id: int, kp: float, ki: float, kd: float, seq: int) -> bytes:
    return _build_frame(_TYPE_BAL_GAINS, struct.pack("<Bfff", loop_id, kp, ki, kd), seq)

def _list_ports():
    result = []
    for p in sorted(serial.tools.list_ports.comports(), key=lambda x: x.device):
        stlink = any(k in (p.description or "").upper()
                     for k in ("STM32", "STLINK", "ST-LINK", "STMICROELECTRONICS"))
        result.append((p.device, p.description or p.device, stlink))
    return result


# ── Serial reader thread ──────────────────────────────────────────────────────

class SerialReader(QThread):
    # pitch_deg, drive_pct (%), pitch_rate (°/s)
    imu_sample = Signal(float, float, float)
    # pv_l_rpm, pv_r_rpm, pwm_l_pct, pwm_r_pct
    pid_sample = Signal(int, int, float, float)
    rx_bytes   = Signal(int)
    error      = Signal(str)

    def __init__(self, ser: serial.Serial, parent=None):
        super().__init__(parent)
        self._ser     = ser
        self._running = False
        self._rx_tot  = 0

    def run(self):
        self._running = True
        buf = bytearray()
        while self._running:
            try:
                chunk = self._ser.read(256)
            except serial.SerialException as exc:
                self.error.emit(str(exc))
                break
            if chunk:
                self._rx_tot += len(chunk)
                self.rx_bytes.emit(self._rx_tot)
                buf.extend(chunk)
                self._parse(buf)

    def stop(self):
        self._running = False

    def write(self, data: bytes):
        try:
            if self._ser.is_open:
                self._ser.write(data)
        except serial.SerialException:
            pass

    def _parse(self, buf: bytearray):
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
                pkt_type = frame[3]
                payload  = frame[8:8 + plen]

                if pkt_type == _TYPE_TEL_IMU and plen >= _SZ_IMU:
                    _ts, _ax, _ay, _az, gx, _gy, _gz, p, drv = \
                        struct.unpack_from(_FMT_IMU, payload)
                    self.imu_sample.emit(
                        p   / 100.0,           # pitch_deg
                        drv / 100.0 * 100.0,   # drive_pct [-100..100]
                        -gx / 10.0,            # pitch_rate °/s (−Gx)
                    )

                elif pkt_type == _TYPE_TEL_PID and plen >= _SZ_PID:
                    _ts, _sp, pv_l, pv_r, _el, _er, pwm_l, pwm_r = \
                        struct.unpack_from(_FMT_PID, payload)
                    self.pid_sample.emit(
                        int(pv_l),
                        int(pv_r),
                        pwm_l / 100.0,   # PWM gauche  [-1..1] → float
                        pwm_r / 100.0,   # PWM droite
                    )

            i += total
        del buf[:i]


# ── RX activity LED ───────────────────────────────────────────────────────────

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
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#66bb6a" if self._lit else "#37474f"))
        p.setPen(QColor("#263238"))
        p.drawEllipse(1, 1, 12, 12)


# ── PID gain row ──────────────────────────────────────────────────────────────

class _PidRow(QWidget):
    value_changed = Signal(float)
    _SCALE = 10_000

    def __init__(self, label: str, v_max: float, parent=None):
        super().__init__(parent)
        self._v_max   = v_max
        self._syncing = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        lbl = QLabel(label)
        lbl.setFixedWidth(24)
        lbl.setStyleSheet(
            "color:#cccccc;font-size:11px;font-family:Consolas;font-weight:bold;"
        )
        lay.addWidget(lbl)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, int(v_max * self._SCALE))
        self._slider.setValue(0)
        self._slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay.addWidget(self._slider)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(0.0, v_max)
        self._spin.setSingleStep(v_max / 100.0)
        self._spin.setDecimals(4)
        self._spin.setValue(0.0)
        self._spin.setFixedWidth(86)
        self._spin.setStyleSheet("font-size:11px;font-family:Consolas;")
        lay.addWidget(self._spin)

        self._slider.valueChanged.connect(self._on_slider)
        self._spin.valueChanged.connect(self._on_spin)

    def _on_slider(self, v: int):
        if self._syncing: return
        self._syncing = True
        fv = v / self._SCALE
        self._spin.setValue(fv)
        self._syncing = False
        self.value_changed.emit(fv)

    def _on_spin(self, fv: float):
        if self._syncing: return
        self._syncing = True
        self._slider.setValue(int(fv * self._SCALE))
        self._syncing = False
        self.value_changed.emit(fv)

    def value(self) -> float:
        return self._spin.value()

    def set_value(self, v: float):
        self._syncing = True
        clamped = max(0.0, min(self._v_max, v))
        self._spin.setValue(clamped)
        self._slider.setValue(int(clamped * self._SCALE))
        self._syncing = False


# ── Angle PID panel ───────────────────────────────────────────────────────────

class _AnglePidPanel(QGroupBox):
    apply_requested = Signal(float, float, float)

    def __init__(self, parent=None):
        super().__init__("Angle PID  —  boucle interne", parent)
        self.setStyleSheet("QGroupBox { font-weight:bold; font-size:11px; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 12, 8, 8)
        lay.setSpacing(4)

        self._kp = _PidRow("Kp", 10.0)
        self._ki = _PidRow("Ki", 1.0)
        self._kd = _PidRow("Kd", 0.5)

        self._debounce = QTimer(singleShot=True, interval=300)
        self._debounce.timeout.connect(self._send)

        for row in (self._kp, self._ki, self._kd):
            lay.addWidget(row)
            row.value_changed.connect(lambda _: self._debounce.start())

        self._status = QLabel("—")
        self._status.setStyleSheet(
            "color:#90a4ae;font-size:10px;font-family:Consolas;"
        )
        lay.addWidget(self._status)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self._reset_btn = QPushButton("Reset (0,0,0)")
        self._reset_btn.setFixedHeight(24)
        self._reset_btn.clicked.connect(self._reset)
        btn_row.addWidget(self._reset_btn)
        self._apply_btn = QPushButton("✓ Appliquer")
        self._apply_btn.setFixedHeight(24)
        self._apply_btn.setFixedWidth(95)
        self._apply_btn.clicked.connect(self._send)
        btn_row.addWidget(self._apply_btn)
        lay.addLayout(btn_row)

    def _reset(self):
        for row in (self._kp, self._ki, self._kd):
            row.set_value(0.0)
        self._send()

    def _send(self):
        kp, ki, kd = self.gains()
        self._status.setText(f"→  Kp={kp:.4f}  Ki={ki:.4f}  Kd={kd:.4f}")
        self.apply_requested.emit(kp, ki, kd)

    def gains(self) -> tuple[float, float, float]:
        return self._kp.value(), self._ki.value(), self._kd.value()

    def set_gains(self, kp: float, ki: float, kd: float):
        self._kp.set_value(kp)
        self._ki.set_value(ki)
        self._kd.set_value(kd)
        self._status.setText(f"→  Kp={kp:.4f}  Ki={ki:.4f}  Kd={kd:.4f}")


# ── Signal chain live display ─────────────────────────────────────────────────

class _SignalChainPanel(QGroupBox):
    """Real-time display of the full regulation chain: inputs → PID → outputs."""

    _VAL_STYLE  = "color:#e0e0e0;font-size:12px;font-family:Consolas;font-weight:bold;"
    _LBL_STYLE  = "color:#78909c;font-size:11px;font-family:Consolas;"
    _UNIT_STYLE = "color:#546e7a;font-size:11px;font-family:Consolas;"
    _SEC_STYLE  = ("color:#42a5f5;font-size:10px;font-family:Consolas;"
                   "font-weight:bold;margin-top:6px;")

    def __init__(self, parent=None):
        super().__init__("Chaîne de régulation  (temps réel)", parent)
        self.setStyleSheet("QGroupBox { font-weight:bold; font-size:11px; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 12, 8, 8)
        lay.setSpacing(1)

        self._vals: dict[str, QLabel] = {}

        def _section(text: str):
            lbl = QLabel(text)
            lbl.setStyleSheet(self._SEC_STYLE)
            lay.addWidget(lbl)

        def _row(key: str, label: str, unit: str):
            h = QHBoxLayout()
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(4)
            l = QLabel(label)
            l.setStyleSheet(self._LBL_STYLE)
            l.setFixedWidth(115)
            v = QLabel("—")
            v.setStyleSheet(self._VAL_STYLE)
            v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            u = QLabel(unit)
            u.setStyleSheet(self._UNIT_STYLE)
            u.setFixedWidth(32)
            h.addWidget(l)
            h.addWidget(v, stretch=1)
            h.addWidget(u)
            lay.addLayout(h)
            self._vals[key] = v

        _section("── Entrées  PID Angle ──────────────")
        _row("sp_pitch",  "Consigne pitch",  "°")
        _row("pv_pitch",  "Pitch mesuré",    "°")
        _row("err_pitch", "Erreur",          "°")

        _section("── Sortie  PID Angle ───────────────")
        _row("drive",     "Drive output",    "%")

        _section("── Entrées  PID Moteur ────────────")
        _row("rpm_l",     "RPM gauche",      "rpm")
        _row("rpm_r",     "RPM droite",      "rpm")

        _section("── Sortie  PID Moteur ─────────────")
        _row("pwm_l",     "PWM gauche",      "%")
        _row("pwm_r",     "PWM droite",      "%")

    def update_angle(self, pitch: float, drive_pct: float):
        error = -pitch   # setpoint = 0°
        self._vals["sp_pitch"].setText("0.0")
        self._vals["pv_pitch"].setText(f"{pitch:+.1f}")
        c = "#ef5350" if abs(pitch) > 30 else "#e0e0e0"
        self._vals["pv_pitch"].setStyleSheet(
            self._VAL_STYLE + f"color:{c};"
        )
        self._vals["err_pitch"].setText(f"{error:+.1f}")
        self._vals["drive"].setText(f"{drive_pct:+.1f}")
        c = "#ff7043" if abs(drive_pct) > 90 else "#e0e0e0"
        self._vals["drive"].setStyleSheet(self._VAL_STYLE + f"color:{c};")

    def update_motor(self, pv_l: int, pv_r: int, pwm_l: float, pwm_r: float):
        self._vals["rpm_l"].setText(f"{pv_l:+d}")
        self._vals["rpm_r"].setText(f"{pv_r:+d}")
        self._vals["pwm_l"].setText(f"{pwm_l * 100:+.1f}")
        self._vals["pwm_r"].setText(f"{pwm_r * 100:+.1f}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _vsep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine)
    f.setFrameShadow(QFrame.Shadow.Sunken)
    return f


# ── Main window ───────────────────────────────────────────────────────────────

class CbcTuner(QMainWindow):

    def __init__(self, args):
        super().__init__()
        self.setWindowTitle("CBC Tuner — Angle PID")
        self.setMinimumSize(900, 500)

        _CFG_DIR.mkdir(parents=True, exist_ok=True)
        self._settings = QSettings(_CFG_FILE, QSettings.Format.IniFormat)

        self._ser:    serial.Serial | None = None
        self._reader: SerialReader  | None = None
        self._tx_seq  = 0
        self._pkt_cnt = 0

        self._state = TunerState()
        self._i_accum: float       = 0.0
        self._t_prev:  float | None = None

        self._mcp = StateServer(self._state)
        self._mcp_ok = self._mcp.start()

        self._build_ui()
        self._restore_layout()

        self._refresh_ports()
        if args.port:
            idx = self._port_combo.findData(args.port)
            if idx >= 0:
                self._port_combo.setCurrentIndex(idx)
        else:
            last_port = self._settings.value("last_port", "")
            idx = self._port_combo.findData(last_port)
            if idx >= 0:
                self._port_combo.setCurrentIndex(idx)

        last_baud = self._settings.value("last_baud", "115200")
        idx = self._baud_combo.findText(last_baud)
        if idx >= 0:
            self._baud_combo.setCurrentIndex(idx)

        self._plot_timer = QTimer(self, interval=40)
        self._plot_timer.timeout.connect(self._refresh_plots)
        self._plot_timer.start()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        tb = self.addToolBar("Main")
        tb.setMovable(False)

        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(200)

        ref_btn = QPushButton("↺")
        ref_btn.setFixedWidth(28)
        ref_btn.clicked.connect(self._refresh_ports)

        self._baud_combo = QComboBox()
        for b in _BAUDS:
            self._baud_combo.addItem(b)

        self._connect_btn = QPushButton("Connecter")
        self._connect_btn.setFixedWidth(100)
        self._connect_btn.clicked.connect(self._on_connect_toggle)

        self._rate_combo = QComboBox()
        for r in _RATES:
            self._rate_combo.addItem(f"{r} Hz", userData=r)
        self._rate_combo.setCurrentIndex(_RATES.index(20))
        self._rate_combo.currentIndexChanged.connect(self._on_rate_changed)

        self._stream_btn = QPushButton("▶ Stream")
        self._stream_btn.setCheckable(True)
        self._stream_btn.setEnabled(False)
        self._stream_btn.setFixedWidth(90)
        self._stream_btn.clicked.connect(self._on_stream_toggle)

        self._win_spin = QSpinBox()
        self._win_spin.setRange(5, 120)
        self._win_spin.setValue(int(self._settings.value("time_window_s", 20)))
        self._win_spin.setSuffix(" s")
        self._win_spin.setFixedWidth(65)
        self._win_spin.setToolTip("Durée de la fenêtre temporelle")

        self._clear_btn = QPushButton("Effacer")
        self._clear_btn.clicked.connect(self._clear)

        self._rx_led    = _RxLed()
        self._rx_label  = QLabel("RX: 0 B")
        self._rx_label.setStyleSheet("color:#90a4ae;")
        self._pkt_label = QLabel("PKT: 0")
        self._pkt_label.setStyleSheet("color:#90a4ae;")

        mcp_color = "#66bb6a" if self._mcp_ok else "#ef5350"
        mcp_info  = f"IPC: {self._mcp.url()}" if self._mcp_ok else "IPC: port occupé"
        self._mcp_label = QLabel(mcp_info)
        self._mcp_label.setStyleSheet(f"color:{mcp_color};font-size:10px;font-family:Consolas;")
        self._mcp_label.setToolTip(
            ("Serveur HTTP IPC pour MCP stdio actif sur " + self._mcp.url())
            if self._mcp_ok else "Impossible de démarrer le serveur IPC (port 3334 occupé ?)"
        )

        for w in (
            QLabel("Port:"), self._port_combo, ref_btn,
            QLabel("Baud:"), self._baud_combo,
            self._connect_btn,
            _vsep(),
            QLabel("Cadence:"), self._rate_combo,
            self._stream_btn,
            QLabel("Fenêtre:"), self._win_spin,
            self._clear_btn,
            _vsep(),
            self._rx_led, self._rx_label, self._pkt_label,
            _vsep(),
            self._mcp_label,
        ):
            tb.addWidget(w)

        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.setHandleWidth(6)
        self._main_splitter.addWidget(self._build_left_panel())

        self._right_tabs = QTabWidget()
        self._right_tabs.addTab(self._build_plots_panel(), "Live")
        self._sweep_panel = SweepPanel()
        self._right_tabs.addTab(self._sweep_panel, "Sweep")
        self._main_splitter.addWidget(self._right_tabs)

        self.setCentralWidget(self._main_splitter)

    def _build_left_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(260)

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(10)

        self._angle_panel = _AnglePidPanel()
        self._angle_panel.apply_requested.connect(
            lambda kp, ki, kd: self._send_gains(0, kp, ki, kd)
        )
        lay.addWidget(self._angle_panel)

        self._chain_panel = _SignalChainPanel()
        lay.addWidget(self._chain_panel)

        lay.addStretch()
        scroll.setWidget(container)
        return scroll

    def _build_plots_panel(self) -> QSplitter:
        self._plots_splitter = QSplitter(Qt.Orientation.Vertical)
        self._plots_splitter.setHandleWidth(6)

        # Pitch
        self._pw_pitch = pg.PlotWidget(title="Pitch  (°)  —  consigne = 0°")
        self._pw_pitch.showGrid(x=True, y=True, alpha=0.25)
        self._pw_pitch.setLabel("left", "angle", units="°")
        self._pw_pitch.addLegend(offset=(10, 10))
        self._pw_pitch.addLine(y=0,   pen=pg.mkPen(C_ZERO,   width=1, style=Qt.PenStyle.DashLine))
        self._pw_pitch.addLine(y=45,  pen=pg.mkPen(C_SAFETY, width=1, style=Qt.PenStyle.DotLine))
        self._pw_pitch.addLine(y=-45, pen=pg.mkPen(C_SAFETY, width=1, style=Qt.PenStyle.DotLine))
        self._c_pitch = self._pw_pitch.plot(pen=pg.mkPen(C_PITCH, width=2), name="pitch (°)")

        # Contributions P / I / D (calculées côté PC à partir des gains et de l'erreur)
        self._pw_pid = pg.PlotWidget(title="Contributions PID  (normalisé)  —  P + I + D = drive")
        self._pw_pid.showGrid(x=True, y=True, alpha=0.25)
        self._pw_pid.setLabel("left", "terme", units="")
        self._pw_pid.setXLink(self._pw_pitch)
        self._pw_pid.addLegend(offset=(10, 10))
        self._pw_pid.addLine(y=0,    pen=pg.mkPen(C_ZERO,    width=1, style=Qt.PenStyle.DashLine))
        self._pw_pid.addLine(y=1,    pen=pg.mkPen("#37474f", width=1, style=Qt.PenStyle.DashLine))
        self._pw_pid.addLine(y=-1,   pen=pg.mkPen("#37474f", width=1, style=Qt.PenStyle.DashLine))
        self._c_pid_p = self._pw_pid.plot(pen=pg.mkPen(C_P_TERM, width=2), name="P")
        self._c_pid_i = self._pw_pid.plot(pen=pg.mkPen(C_I_TERM, width=2), name="I")
        self._c_pid_d = self._pw_pid.plot(pen=pg.mkPen(C_D_TERM, width=2), name="D")

        for c in (self._c_pitch, self._c_pid_p, self._c_pid_i, self._c_pid_d):
            c.setDownsampling(auto=True, method="subsample")
            c.setClipToView(True)

        self._plots_splitter.addWidget(self._pw_pitch)
        self._plots_splitter.addWidget(self._pw_pid)
        return self._plots_splitter

    # ── Layout persistence ────────────────────────────────────────────────────

    def _restore_layout(self):
        geom = self._settings.value("geometry")
        if geom is not None:
            self.restoreGeometry(geom)
        else:
            self.resize(1300, 750)

        ms = self._settings.value("splitter_main")
        if ms is not None:
            self._main_splitter.restoreState(ms)
        else:
            self._main_splitter.setSizes([300, 1000])

        ps = self._settings.value("splitter_plots")
        if ps is not None:
            self._plots_splitter.restoreState(ps)

        # Restore saved angle PID gains
        kp = float(self._settings.value("gains/angle_kp", 0.0))
        ki = float(self._settings.value("gains/angle_ki", 0.0))
        kd = float(self._settings.value("gains/angle_kd", 0.0))
        if kp or ki or kd:
            self._angle_panel.set_gains(kp, ki, kd)

    def _save_layout(self):
        self._settings.setValue("geometry",       self.saveGeometry())
        self._settings.setValue("splitter_main",  self._main_splitter.saveState())
        self._settings.setValue("splitter_plots", self._plots_splitter.saveState())
        self._settings.setValue("time_window_s",  self._win_spin.value())
        self._settings.setValue("last_port",      self._port_combo.currentData() or "")
        self._settings.setValue("last_baud",      self._baud_combo.currentText())

    def closeEvent(self, event):
        self._save_layout()
        self._disconnect()
        event.accept()

    # ── Connection ────────────────────────────────────────────────────────────

    def _on_connect_toggle(self):
        if self._reader:
            self._disconnect()
            return
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
        self._reader.imu_sample.connect(self._on_imu)
        self._reader.pid_sample.connect(self._on_pid)
        self._reader.rx_bytes.connect(self._on_rx)
        self._reader.error.connect(self._on_err)
        self._reader.start()
        self._state.connected  = True
        self._state.send_gains = lambda kp, ki, kd: self._send_gains(0, kp, ki, kd)
        self._connect_btn.setText("Déconnecter")
        self._stream_btn.setEnabled(True)
        self._port_combo.setEnabled(False)
        self._baud_combo.setEnabled(False)
        self.statusBar().showMessage(f"Connecté sur {port}")
        self._stream_btn.setChecked(True)
        self._stream_btn.setText("⏹ Stop")
        self._send_stream(True)
        QTimer.singleShot(200, self._send_saved_gains)

    def _disconnect(self):
        self._send_stream(False)
        if self._reader:
            self._reader.stop()
            self._reader.wait(800)
            self._reader = None
        if self._ser and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        self._state.connected  = False
        self._state.send_gains = None
        self._connect_btn.setText("Connecter")
        self._stream_btn.setChecked(False)
        self._stream_btn.setEnabled(False)
        self._stream_btn.setText("▶ Stream")
        self._port_combo.setEnabled(True)
        self._baud_combo.setEnabled(True)
        self._rx_led.reset()
        self.statusBar().showMessage("Déconnecté")

    def _on_stream_toggle(self, checked: bool):
        self._send_stream(checked)
        self._stream_btn.setText("⏹ Stop" if checked else "▶ Stream")

    def _on_rate_changed(self):
        if self._reader and self._stream_btn.isChecked():
            self._send_stream(True)

    def _send_stream(self, enable: bool):
        if not self._reader:
            return
        rate = self._rate_combo.currentData()
        self._reader.write(_stream_frame(enable, rate, self._tx_seq))
        self._tx_seq = (self._tx_seq + 1) & 0xFF

    def _send_gains(self, loop_id: int, kp: float, ki: float, kd: float):
        if not self._reader:
            return
        self._reader.write(_gains_frame(loop_id, kp, ki, kd, self._tx_seq))
        self._tx_seq = (self._tx_seq + 1) & 0xFF
        self._i_accum = 0.0  # reset intégrateur local à chaque changement de gains
        if loop_id == 0:
            self._state.kp = kp
            self._state.ki = ki
            self._state.kd = kd
            self._angle_panel.set_gains(kp, ki, kd)
        if loop_id == 0:
            self._settings.setValue("gains/angle_kp", kp)
            self._settings.setValue("gains/angle_ki", ki)
            self._settings.setValue("gains/angle_kd", kd)
        self.statusBar().showMessage(
            f"[Angle PID]  Kp={kp:.4f}  Ki={ki:.4f}  Kd={kd:.4f}  → envoyé", 3000
        )

    def _send_saved_gains(self):
        kp, ki, kd = self._angle_panel.gains()
        self._send_gains(0, kp, ki, kd)

    # ── Data slots ────────────────────────────────────────────────────────────

    def _on_imu(self, pitch: float, drive_pct: float, pitch_rate: float):
        now = _time.monotonic()
        dt  = (now - self._t_prev) if self._t_prev is not None else 0.005
        self._t_prev = now

        s = self._state
        s.t.append(now)
        s.pitch.append(pitch)
        s.pitch_rate.append(pitch_rate)
        s.drive.append(drive_pct / 100.0)

        kp, ki, kd = self._state.kp, self._state.ki, self._state.kd
        error = -pitch  # setpoint = 0°

        # Integral avec anti-windup ±0.5 (cohérent avec CBC_Init integral limits)
        self._i_accum = max(-0.5, min(0.5, self._i_accum + error * dt))

        # d(error)/dt = -d(pitch)/dt ≈ -pitch_rate  (pitch_rate = −Gx déjà négatif)
        s.pid_p.append(kp * error)
        s.pid_i.append(ki * self._i_accum)
        s.pid_d.append(kd * (-pitch_rate))

        self._pkt_cnt += 1
        self._pkt_label.setText(f"PKT: {self._pkt_cnt}")
        self._chain_panel.update_angle(pitch, drive_pct)

    def _on_pid(self, pv_l: int, pv_r: int, pwm_l: float, pwm_r: float):
        self._state.rpm_l = pv_l
        self._state.rpm_r = pv_r
        self._state.pwm_l = pwm_l
        self._state.pwm_r = pwm_r
        self._chain_panel.update_motor(pv_l, pv_r, pwm_l, pwm_r)

    def _on_rx(self, total: int):
        self._rx_led.flash()
        self._rx_label.setText(
            f"RX: {total} B" if total < 1024 else f"RX: {total / 1024:.1f} kB"
        )

    def _on_err(self, msg: str):
        self._disconnect()
        self.statusBar().showMessage(f"Erreur série : {msg}", 6000)

    # ── Plot refresh ──────────────────────────────────────────────────────────

    def _refresh_plots(self):
        s = self._state
        n = len(s.t)
        if n == 0:
            return
        win_s = float(self._win_spin.value())
        t     = np.fromiter(s.t,     float, n)
        p     = np.fromiter(s.pitch, float, n)
        pp    = np.fromiter(s.pid_p, float, n)
        pi    = np.fromiter(s.pid_i, float, n)
        pd    = np.fromiter(s.pid_d, float, n)
        t_now = t[-1]
        mask  = t >= (t_now - win_s)
        tw    = t[mask]
        self._c_pitch.setData(x=tw, y=p[mask])
        self._c_pid_p.setData(x=tw, y=pp[mask])
        self._c_pid_i.setData(x=tw, y=pi[mask])
        self._c_pid_d.setData(x=tw, y=pd[mask])
        for pw in (self._pw_pitch, self._pw_pid):
            pw.setXRange(t_now - win_s, t_now, padding=0)

    def _clear(self):
        s = self._state
        for d in (s.t, s.pitch, s.pitch_rate, s.drive, s.pid_p, s.pid_i, s.pid_d):
            d.clear()
        for c in (self._c_pitch, self._c_pid_p, self._c_pid_i, self._c_pid_d):
            c.setData([], [])
        self._i_accum = 0.0
        self._t_prev  = None
        self._pkt_cnt = 0
        self._pkt_label.setText("PKT: 0")

    def _refresh_ports(self):
        self._port_combo.clear()
        for dev, desc, stlink in _list_ports():
            self._port_combo.addItem(
                f"{'⭐ ' if stlink else ''}{dev} — {desc}", userData=dev
            )
        if not self._port_combo.count():
            self._port_combo.addItem("(aucun port)", userData="")
