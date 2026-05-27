"""
cbc_tuner/gui.py — Interface de tuning des PIDs balance (angle / vitesse / yaw).

Reçoit :
  VCP_TYPE_TELEMETRY_IMU (0x11) → pitch_deg
  VCP_TYPE_TELEMETRY_PID (0x10) → pwm_l_x100, pwm_r_x100 (≈ drive output)

Envoie :
  VCP_TYPE_CMD_SET_BALANCE_GAINS (0x24) → loop_id, kp, ki, kd
  VCP_TYPE_CMD_STREAM_CTRL (0x22)       → enable, rate_hz
"""
from __future__ import annotations

import struct
from collections import deque

# PySide6 avant numpy/pyqtgraph
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QMainWindow, QPushButton, QScrollArea,
    QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

import numpy as np
import pyqtgraph as pg
import serial
import serial.tools.list_ports

# ── Thème ─────────────────────────────────────────────────────────────────────
pg.setConfigOptions(antialias=True, background="#1e1e1e", foreground="#cccccc")

C_PITCH  = "#ef5350"   # rouge  — pitch_deg
C_DRIVE  = "#66bb6a"   # vert   — drive output
C_ZERO   = "#546e7a"   # gris   — zéro
C_SAFETY = "#ff7043"   # orange — ±45°

# ── Protocole VCP ─────────────────────────────────────────────────────────────
_SOF1, _SOF2, _EOF, _VER = 0xAA, 0x55, 0x33, 0x01

_TYPE_TEL_PID   = 0x10
_TYPE_TEL_IMU   = 0x11
_TYPE_STREAM    = 0x22
_TYPE_BAL_GAINS = 0x24

# VcpTelPid_t : uint32 + 7×int16 = 18 bytes (velocity PID — ignoré en mode balance)
_FMT_PID  = "<Ihhhhhhh"
_SZ_PID   = struct.calcsize(_FMT_PID)   # 18

# VcpTelImu_t : uint32 + 8×int16 = 20 bytes (inclut drive_x100)
_FMT_IMU  = "<Ihhhhhhhh"
_SZ_IMU   = struct.calcsize(_FMT_IMU)   # 20

_RATES = [5, 10, 20, 50, 100]
_BAUDS = ["115200", "230400"]
_WIN_S = 15.0
_NPTS  = 30_000


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


def _balance_gains_frame(loop_id: int, kp: float, ki: float, kd: float, seq: int) -> bytes:
    payload = struct.pack("<Bfff", loop_id, kp, ki, kd)
    return _build_frame(_TYPE_BAL_GAINS, payload, seq)


def _list_ports():
    result = []
    for p in sorted(serial.tools.list_ports.comports(), key=lambda x: x.device):
        stlink = any(k in (p.description or "").upper()
                     for k in ("STM32", "STLINK", "ST-LINK", "STMICROELECTRONICS"))
        result.append((p.device, p.description or p.device, stlink))
    return result


# ── Thread série ──────────────────────────────────────────────────────────────

class SerialReader(QThread):
    # pitch_deg (°), drive_pct (%)
    imu_sample = Signal(float, float)
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
                    _ts, ax, ay, az, gx, gy, gz, p, drv = struct.unpack_from(_FMT_IMU, payload)
                    pitch     = p   / 100.0
                    drive_pct = drv / 100.0 * 100.0   # [-1..1] → [-100..100] %
                    self.imu_sample.emit(pitch, drive_pct)
            i += total
        del buf[:i]


# ── Widget voyant RX ──────────────────────────────────────────────────────────

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
        from PySide6.QtGui import QPainter, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#66bb6a" if self._lit else "#37474f"))
        p.setPen(QColor("#263238"))
        p.drawEllipse(1, 1, 12, 12)


# ── Widget ligne PID (label + slider + spinbox) ───────────────────────────────

class _PidRow(QWidget):
    value_changed = Signal(float)

    # slider encodes float as int (×SCALE)
    _SCALE = 1000

    def __init__(self, label: str, v_min: float, v_max: float,
                 step: float = 0.01, parent=None):
        super().__init__(parent)
        self._v_min  = v_min
        self._v_max  = v_max
        self._step   = step
        self._syncing = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        lbl = QLabel(label)
        lbl.setFixedWidth(24)
        lbl.setStyleSheet("color:#cccccc;font-size:11px;font-family:Consolas;"
                          "font-weight:bold;")
        lay.addWidget(lbl)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(int(v_min * self._SCALE), int(v_max * self._SCALE))
        self._slider.setValue(0)
        self._slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay.addWidget(self._slider)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(v_min, v_max)
        self._spin.setSingleStep(step)
        self._spin.setDecimals(3)
        self._spin.setValue(0.0)
        self._spin.setFixedWidth(80)
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
        clamped = max(self._v_min, min(self._v_max, v))
        self._spin.setValue(clamped)
        self._slider.setValue(int(clamped * self._SCALE))
        self._syncing = False


# ── Panneau PID (3 lignes + boutons) ─────────────────────────────────────────

class _PidPanel(QGroupBox):

    apply_requested = Signal(float, float, float)   # kp, ki, kd

    def __init__(self, title: str, enabled: bool = True,
                 kp_max: float = 30.0, ki_max: float = 10.0, kd_max: float = 5.0,
                 parent=None):
        super().__init__(title, parent)
        self.setStyleSheet("QGroupBox { font-weight:bold; font-size:11px; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        self._kp = _PidRow("Kp", 0.0, kp_max, step=kp_max / 100)
        self._ki = _PidRow("Ki", 0.0, ki_max, step=ki_max / 100)
        self._kd = _PidRow("Kd", 0.0, kd_max, step=kd_max / 100)

        # Debounce timer: envoie les gains 300 ms après le dernier changement
        self._debounce = QTimer(singleShot=True, interval=300)
        self._debounce.timeout.connect(self._send)

        for row in (self._kp, self._ki, self._kd):
            lay.addWidget(row)
            row.value_changed.connect(lambda _: self._debounce.start())

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._reset_btn = QPushButton("Réinitialiser (0, 0, 0)")
        self._reset_btn.setFixedHeight(26)
        self._reset_btn.clicked.connect(self._reset)
        btn_row.addWidget(self._reset_btn)

        self._apply_btn = QPushButton("✓ Appliquer")
        self._apply_btn.setFixedHeight(26)
        self._apply_btn.setFixedWidth(100)
        self._apply_btn.clicked.connect(self._send)
        btn_row.addWidget(self._apply_btn)

        lay.addLayout(btn_row)

        if not enabled:
            self._set_enabled(False)
            hint = QLabel("Activer après tuning de la boucle précédente.")
            hint.setStyleSheet("color:#546e7a;font-size:10px;font-style:italic;")
            lay.addWidget(hint)

    def _set_enabled(self, on: bool):
        for w in (self._kp, self._ki, self._kd,
                  self._reset_btn, self._apply_btn):
            w.setEnabled(on)

    def _reset(self):
        for row in (self._kp, self._ki, self._kd):
            row.set_value(0.0)
        self._send()

    def _send(self):
        self.apply_requested.emit(
            self._kp.value(), self._ki.value(), self._kd.value()
        )

    def gains(self) -> tuple[float, float, float]:
        return self._kp.value(), self._ki.value(), self._kd.value()

    def unlock(self):
        self._set_enabled(True)


# ── Fenêtre principale ────────────────────────────────────────────────────────

class CbcTuner(QMainWindow):

    def __init__(self, args):
        super().__init__()
        self.setWindowTitle("CBC Tuner — Équilibre PID")
        self.setMinimumSize(1100, 650)

        self._ser:    serial.Serial | None = None
        self._reader: SerialReader  | None = None
        self._tx_seq = 0
        self._pkt_cnt = 0

        # Ring buffers (un seul timestamp commun — IMU packet porte les deux)
        self._t       = deque(maxlen=_NPTS)
        self._pitch   = deque(maxlen=_NPTS)
        self._drive   = deque(maxlen=_NPTS)   # CBC drive output %

        self._build_ui()

        self._plot_timer = QTimer(self, interval=40)
        self._plot_timer.timeout.connect(self._refresh)
        self._plot_timer.start()

        self._refresh_ports()
        if args.port:
            idx = self._port_combo.findData(args.port)
            if idx >= 0:
                self._port_combo.setCurrentIndex(idx)

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self):
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

        self._rx_led   = _RxLed()
        self._rx_label = QLabel("RX: 0 B")
        self._rx_label.setStyleSheet("color:#90a4ae;")
        self._pkt_label = QLabel("PKT: 0")
        self._pkt_label.setStyleSheet("color:#90a4ae;")

        for w in (QLabel("Port:"), self._port_combo, ref_btn,
                  QLabel("Baud:"), self._baud_combo, self._connect_btn,
                  _vsep(),
                  QLabel("Cadence:"), self._rate_combo,
                  self._stream_btn, self._clear_btn,
                  _vsep(),
                  self._rx_led, self._rx_label, self._pkt_label):
            toolbar.addWidget(w)

        central = QWidget()
        h_lay = QHBoxLayout(central)
        h_lay.setContentsMargins(4, 4, 4, 4)
        h_lay.setSpacing(6)

        h_lay.addWidget(self._build_left(), stretch=0)
        h_lay.addWidget(self._build_plots(), stretch=1)
        self.setCentralWidget(central)

    def _build_left(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedWidth(310)

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(10)

        # ── Angle PID (boucle interne) ────────────────────────────────────
        self._angle_panel = _PidPanel(
            "① Boucle angle  (inner loop)",
            enabled=True, kp_max=0.05, ki_max=0.02, kd_max=0.02,
        )
        self._angle_panel.apply_requested.connect(
            lambda kp, ki, kd: self._send_balance_gains(0, kp, ki, kd)
        )
        lay.addWidget(self._angle_panel)

        # ── Velocity PID (boucle externe) ─────────────────────────────────
        self._vel_panel = _PidPanel(
            "② Boucle vitesse  (outer loop)",
            enabled=False, kp_max=1.0, ki_max=0.5, kd_max=0.2,
        )
        self._vel_panel.apply_requested.connect(
            lambda kp, ki, kd: self._send_balance_gains(1, kp, ki, kd)
        )
        lay.addWidget(self._vel_panel)

        # ── Yaw PID ───────────────────────────────────────────────────────
        self._yaw_panel = _PidPanel(
            "③ Boucle yaw",
            enabled=False, kp_max=2.0, ki_max=1.0, kd_max=0.5,
        )
        self._yaw_panel.apply_requested.connect(
            lambda kp, ki, kd: self._send_balance_gains(2, kp, ki, kd)
        )
        lay.addWidget(self._yaw_panel)

        # ── Boutons de déblocage ──────────────────────────────────────────
        unlock_vel = QPushButton("Déverrouiller boucle vitesse")
        unlock_vel.setFixedHeight(26)
        unlock_vel.setStyleSheet("font-size:10px;")
        unlock_vel.clicked.connect(self._vel_panel.unlock)
        lay.addWidget(unlock_vel)

        unlock_yaw = QPushButton("Déverrouiller boucle yaw")
        unlock_yaw.setFixedHeight(26)
        unlock_yaw.setStyleSheet("font-size:10px;")
        unlock_yaw.clicked.connect(self._yaw_panel.unlock)
        lay.addWidget(unlock_yaw)

        lay.addStretch()
        scroll.setWidget(container)
        return scroll

    def _build_plots(self) -> QWidget:
        w   = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        # ── Pitch ─────────────────────────────────────────────────────────
        self._pw_pitch = pg.PlotWidget(title="Pitch estimé  (consigne = 0°)")
        self._pw_pitch.showGrid(x=True, y=True, alpha=0.3)
        self._pw_pitch.setLabel("left", "angle", units="°")
        self._pw_pitch.addLegend(offset=(10, 10))
        self._pw_pitch.addLine(y=0,    pen=pg.mkPen(C_ZERO,   width=1, style=Qt.DashLine))
        self._pw_pitch.addLine(y=45,   pen=pg.mkPen(C_SAFETY, width=1, style=Qt.DotLine))
        self._pw_pitch.addLine(y=-45,  pen=pg.mkPen(C_SAFETY, width=1, style=Qt.DotLine))
        self._c_pitch = self._pw_pitch.plot(
            pen=pg.mkPen(C_PITCH, width=2), name="pitch_deg"
        )

        # ── Drive output ──────────────────────────────────────────────────
        self._pw_drive = pg.PlotWidget(title="Commande moteur  (sortie PID angle)")
        self._pw_drive.showGrid(x=True, y=True, alpha=0.3)
        self._pw_drive.setLabel("left", "drive", units="%")
        self._pw_drive.setXLink(self._pw_pitch)
        self._pw_drive.addLegend(offset=(10, 10))
        self._pw_drive.addLine(y=0,    pen=pg.mkPen(C_ZERO, width=1, style=Qt.DashLine))
        self._pw_drive.addLine(y=100,  pen=pg.mkPen("#37474f", width=1, style=Qt.DashLine))
        self._pw_drive.addLine(y=-100, pen=pg.mkPen("#37474f", width=1, style=Qt.DashLine))
        self._c_drive = self._pw_drive.plot(
            pen=pg.mkPen(C_DRIVE, width=2), name="drive_output %"
        )

        for c in (self._c_pitch, self._c_drive):
            c.setDownsampling(auto=True, method="subsample")
            c.setClipToView(True)

        lay.addWidget(self._pw_pitch, stretch=2)
        lay.addWidget(self._pw_drive, stretch=1)
        return w

    # ── Connexion ─────────────────────────────────────────────────────────────

    def _on_connect_toggle(self):
        if self._reader:
            self._disconnect()
        else:
            port = self._port_combo.currentData()
            baud = int(self._baud_combo.currentText())
            if not port: return
            try:
                self._ser = serial.Serial(port, baud, timeout=0.05)
            except serial.SerialException as exc:
                self.statusBar().showMessage(f"Erreur : {exc}", 5000)
                return
            self._reader = SerialReader(self._ser)
            self._reader.imu_sample.connect(self._on_imu)
            self._reader.rx_bytes.connect(self._on_rx)
            self._reader.error.connect(self._on_err)
            self._reader.start()
            self._connect_btn.setText("Déconnecter")
            self._stream_btn.setEnabled(True)
            self._port_combo.setEnabled(False)
            self._baud_combo.setEnabled(False)
            self.statusBar().showMessage(f"Connecté sur {port}")
            self._stream_btn.setChecked(True)
            self._send_stream(True)
            self._stream_btn.setText("⏹ Stop")

    def _disconnect(self):
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

    def _on_stream_toggle(self, checked: bool):
        self._send_stream(checked)
        self._stream_btn.setText("⏹ Stop" if checked else "▶ Stream")

    def _on_rate_changed(self):
        if self._reader and self._stream_btn.isChecked():
            self._send_stream(True)

    def _send_stream(self, enable: bool):
        if not self._reader: return
        rate = self._rate_combo.currentData()
        self._reader.write(_stream_frame(enable, rate, self._tx_seq))
        self._tx_seq = (self._tx_seq + 1) & 0xFF

    def _send_balance_gains(self, loop_id: int, kp: float, ki: float, kd: float):
        if not self._reader: return
        self._reader.write(_balance_gains_frame(loop_id, kp, ki, kd, self._tx_seq))
        self._tx_seq = (self._tx_seq + 1) & 0xFF
        names = {0: "Angle", 1: "Vitesse", 2: "Yaw"}
        self.statusBar().showMessage(
            f"[{names.get(loop_id,'?')} PID] Kp={kp:.3f}  Ki={ki:.3f}  Kd={kd:.3f}  → envoyé",
            3000,
        )

    # ── Données ───────────────────────────────────────────────────────────────

    def _on_imu(self, pitch: float, drive_pct: float):
        import time as _time
        self._t.append(_time.monotonic())
        self._pitch.append(pitch)
        self._drive.append(drive_pct)
        self._pkt_cnt += 1
        self._pkt_label.setText(f"PKT: {self._pkt_cnt}")

    def _on_rx(self, total: int):
        self._rx_led.flash()
        self._rx_label.setText(
            f"RX: {total} B" if total < 1024 else f"RX: {total/1024:.1f} KB"
        )

    def _on_err(self, msg: str):
        self._disconnect()
        self.statusBar().showMessage(f"Erreur série : {msg}", 6000)

    # ── Rafraîchissement ──────────────────────────────────────────────────────

    def _refresh(self):
        if not self._t:
            return
        t     = np.fromiter(self._t, float, len(self._t))
        t_now = t[-1]
        mask  = t >= (t_now - _WIN_S)
        t_w   = t[mask]
        self._c_pitch.setData(x=t_w, y=np.fromiter(self._pitch, float, len(self._pitch))[mask])
        self._c_drive.setData(x=t_w, y=np.fromiter(self._drive, float, len(self._drive))[mask])
        for pw in (self._pw_pitch, self._pw_drive):
            pw.setXRange(t_now - _WIN_S, t_now, padding=0)

    def _clear(self):
        for d in (self._t, self._pitch, self._drive):
            d.clear()
        for c in (self._c_pitch, self._c_drive):
            c.setData([], [])
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

    def closeEvent(self, event):
        self._disconnect(); event.accept()


# ── Helper ────────────────────────────────────────────────────────────────────

def _vsep() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.VLine); f.setFrameShadow(QFrame.Sunken)
    return f
