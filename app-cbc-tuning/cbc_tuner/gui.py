"""
cbc_tuner/gui.py — CBC balance PID tuning interface.

Telemetry received:
  VCP_TYPE_TELEMETRY_IMU (0x11) → pitch, drive output (angle PID), pitch rate
  VCP_TYPE_TELEMETRY_PID (0x10) → vel setpoint/measured, target_pitch, motor outputs

    VcpTelPid_t field mapping (cascade mode):
      sp_rpm      : velocity setpoint (RPM)
      pv_l_rpm    : left wheel velocity (RPM)
      pv_r_rpm    : right wheel velocity (RPM)
      err_l       : target_pitch_deg × 100  (outer loop output)
      err_r       : (reserved)
      pwm_l_x100  : left motor drive output × 100
      pwm_r_x100  : right motor drive output × 100

Commands sent:
  VCP_TYPE_CMD_SET_BALANCE_GAINS (0x24) → loop_id=0 angle / 1 velocity / 2 yaw
  VCP_TYPE_CMD_SET_SP            (0x21) → velocity setpoint in RPM
  VCP_TYPE_CMD_STREAM_CTRL       (0x22) → enable, rate_hz
"""
from __future__ import annotations

import struct
import time as _time
from collections import deque
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QThread, QTimer, Signal, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QRadialGradient
from PySide6.QtWidgets import (
    QAbstractSpinBox, QCheckBox, QComboBox, QDoubleSpinBox, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QMainWindow, QPushButton, QScrollArea,
    QSizePolicy, QSlider, QSpinBox, QSplitter, QStackedWidget, QTabWidget,
    QVBoxLayout, QWidget,
)

import numpy as np
import pyqtgraph as pg
import serial
import serial.tools.list_ports

from .mcp_server import StateServer, TunerState
from .sweep_panel import SweepPanel
from .sweep_planner import SweepPlannerPanel
from .sweep_runner import SweepRunnerPanel
from .ident_k_panel import IdentKPanel
from .ident_td_panel import IdentTdPanel
from .ident_a_panel import IdentAPanel
from .simulation_panel import SimPanel
from .motor_calib_panel import MotorCalibPanel

pg.setConfigOptions(antialias=True, background="#1e1e1e", foreground="#cccccc")

C_PITCH  = "#ef5350"
C_DRIVE  = "#66bb6a"
C_ZERO   = "#546e7a"
C_SAFETY = "#ff7043"
C_P_TERM = "#ef5350"   # rouge  — terme P
C_I_TERM = "#66bb6a"   # vert   — terme I
C_D_TERM = "#42a5f5"   # bleu   — terme D

_SOF1, _SOF2, _EOF, _VER = 0xAA, 0x55, 0x33, 0x01

_TYPE_TEL_PID      = 0x10
_TYPE_TEL_IMU      = 0x11
_TYPE_TEL_CALIB    = 0x12
_TYPE_TEL_POS      = 0x13
_TYPE_STREAM       = 0x22
_TYPE_BAL_GAINS    = 0x24
_TYPE_SET_SP       = 0x21
_TYPE_MOTOR_CALIB  = 0x25
_TYPE_SET_POS_SP   = 0x26
_TYPE_SET_POS_TRAJ = 0x27

_TRAJ_HOLD  = 0
_TRAJ_SINUS = 1
_TYPE_SPIN_CTRL    = 0x28
_CTRL_SPIN         = 3
_TYPE_SET_DRIVE    = 0x29
_TYPE_ANGLE_SP     = 0x2A
_TYPE_ANGLE_DIRECT = 0x2B   # direct angle mode (mode 4)
_TYPE_TEL_POWER    = 0x14

# VcpTelPid_t : uint32 + 7×int16 = 18 bytes
# ts, sp_rpm, pv_l, pv_r, err_l, err_r, pwm_l_x100, pwm_r_x100
_FMT_PID = "<Ihhhhhhh"
_SZ_PID  = struct.calcsize(_FMT_PID)   # 18

# VcpTelImu_t : uint32 + 8×int16 = 20 bytes
# ts, ax, ay, az, gx, gy, gz, pitch_x100, drive_x100
_FMT_IMU = "<Ihhhhhhhh"
_SZ_IMU  = struct.calcsize(_FMT_IMU)   # 20

# VcpTelCalib_t : uint32 + 3×int16 + 2×uint8 = 12 bytes
# ts_ms, drive_x1000, vel_l_rpm, vel_r_rpm, phase, calib_active
_FMT_CALIB = "<IhhhBB"
_SZ_CALIB  = struct.calcsize(_FMT_CALIB)  # 12

# VcpTelPos_t : uint32 + 3×int16 + 2×uint8 = 12 bytes
# ts_ms, pos_cm_x10, sp_cm_x10, vel_sp_rpm, ctrl_mode, traj_mode
_FMT_POS = "<IhhhBB"
_SZ_POS  = struct.calcsize(_FMT_POS)   # 12

# VcpTelPower_t : uint32 + 4×int16 = 12 bytes
# ts_ms, current_l_ma, current_r_ma, power_l_mw, power_r_mw
_FMT_POWER = "<Ihhhh"
_SZ_POWER  = struct.calcsize(_FMT_POWER)  # 12

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

def _sp_frame(rpm: int, seq: int) -> bytes:
    return _build_frame(_TYPE_SET_SP, struct.pack("<h", max(-85, min(85, rpm))), seq)

def _pos_sp_frame(sp_cm: float, seq: int) -> bytes:
    return _build_frame(_TYPE_SET_POS_SP, struct.pack("<f", sp_cm), seq)

def _pos_traj_frame(mode: int, amplitude_cm: float, period_s: float, seq: int) -> bytes:
    return _build_frame(_TYPE_SET_POS_TRAJ,
                        struct.pack("<Bff", mode, amplitude_cm, period_s), seq)

def _spin_frame(enable: bool, interval_s: float, yaw_force: float, seq: int) -> bytes:
    return _build_frame(_TYPE_SPIN_CTRL,
                        struct.pack("<Bff", int(enable), interval_s, yaw_force), seq)

def _angle_sp_frame(offset_deg: float, seq: int) -> bytes:
    return _build_frame(_TYPE_ANGLE_SP, struct.pack("<f", offset_deg), seq)

def _angle_direct_frame(target_deg: float, seq: int) -> bytes:
    target_deg = max(-8.0, min(8.0, target_deg))
    return _build_frame(_TYPE_ANGLE_DIRECT, struct.pack("<f", target_deg), seq)

def _drive_frame(drive_norm: float, seq: int) -> bytes:
    drive_x1000 = int(round(max(-1.0, min(1.0, drive_norm)) * 1000))
    return _build_frame(_TYPE_SET_DRIVE, struct.pack("<h", drive_x1000), seq)

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
    imu_sample   = Signal(float, float, float)
    # pv_l_rpm, pv_r_rpm, pwm_l_pct, pwm_r_pct, sp_rpm, target_pitch_deg
    pid_sample   = Signal(int, int, float, float, int, float)
    # ts_ms, drive, vel_l_rpm, vel_r_rpm, phase, calib_active
    calib_sample = Signal(int, float, float, float, int, int)
    # pos_cm, sp_cm, vel_sp_rpm, ctrl_mode, traj_mode
    pos_sample   = Signal(float, float, float, int, int)
    # current_l_a, current_r_a, power_l_w, power_r_w
    power_sample = Signal(float, float, float, float)
    rx_bytes     = Signal(int)
    error        = Signal(str)

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
                        -gx / 100.0,           # pitch_rate °/s (−Gx)
                    )

                elif pkt_type == _TYPE_TEL_PID and plen >= _SZ_PID:
                    _ts, sp, pv_l, pv_r, target_pitch_x100, _er, pwm_l, pwm_r = \
                        struct.unpack_from(_FMT_PID, payload)
                    self.pid_sample.emit(
                        int(pv_l),
                        int(pv_r),
                        pwm_l / 100.0,              # left motor output [-1..1]
                        pwm_r / 100.0,              # right motor output [-1..1]
                        int(sp),                    # velocity setpoint (RPM)
                        target_pitch_x100 / 100.0,  # outer loop output (°)
                    )

                elif pkt_type == _TYPE_TEL_CALIB and plen >= _SZ_CALIB:
                    ts_ms, drv_x1000, vl, vr, phase, active = \
                        struct.unpack_from(_FMT_CALIB, payload)
                    self.calib_sample.emit(
                        int(ts_ms),
                        drv_x1000 / 1000.0,
                        float(vl),
                        float(vr),
                        int(phase),
                        int(active),
                    )

                elif pkt_type == _TYPE_TEL_POS and plen >= _SZ_POS:
                    _ts, pos_x10, sp_x10, vel_sp, ctrl, traj = \
                        struct.unpack_from(_FMT_POS, payload)
                    self.pos_sample.emit(
                        pos_x10 / 10.0,
                        sp_x10  / 10.0,
                        float(vel_sp),
                        int(ctrl),
                        int(traj),
                    )

                elif pkt_type == _TYPE_TEL_POWER and plen >= _SZ_POWER:
                    _ts, cl_ma, cr_ma, pl_mw, pr_mw = \
                        struct.unpack_from(_FMT_POWER, payload)
                    self.power_sample.emit(
                        cl_ma / 1000.0,   # A
                        cr_ma / 1000.0,   # A
                        pl_mw / 1000.0,   # W
                        pr_mw / 1000.0,   # W
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
    _SCALE = 100_000  # résolution 0.00001

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
        self._spin.setDecimals(5)
        self._spin.setStepType(QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        self._spin.setValue(0.0)
        self._spin.setFixedWidth(96)
        self._spin.setStyleSheet("font-size:11px;font-family:Consolas;")
        lay.addWidget(self._spin)

        self._slider.valueChanged.connect(self._on_slider)
        # editingFinished : ne se déclenche qu'après validation (Enter ou perte focus)
        # → évite la reformation des zéros pendant la saisie
        self._spin.editingFinished.connect(self._on_spin_edit)

    def _on_slider(self, v: int):
        if self._syncing: return
        self._syncing = True
        fv = v / self._SCALE
        self._spin.setValue(fv)
        self._syncing = False
        self.value_changed.emit(fv)

    def _on_spin_edit(self):
        if self._syncing: return
        fv = self._spin.value()
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


# ── Robot logo ───────────────────────────────────────────────────────────────

class _RobotLogo(QWidget):
    """Fun two-wheeled inverted pendulum robot illustration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(110)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip("CBC Tuner — Robot pendule inversé")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx = w / 2

        # ── Fond ──────────────────────────────────────────────────────────────
        p.fillRect(self.rect(), QColor("#1a1a2e"))

        # couleurs
        body_c  = QColor("#37474f")
        body_hl = QColor("#546e7a")
        wheel_c = QColor("#263238")
        wheel_r = QColor("#ef5350")
        eye_c   = QColor("#42a5f5")
        ant_c   = QColor("#66bb6a")
        text_c  = QColor("#546e7a")

        # ── Corps ─────────────────────────────────────────────────────────────
        body_w, body_h = 36, 30
        body_x = cx - body_w / 2
        body_y = h * 0.20

        p.setBrush(QBrush(body_c))
        p.setPen(QPen(body_hl, 1.5))
        p.drawRoundedRect(QRectF(body_x, body_y, body_w, body_h), 5, 5)

        # ── Tête ──────────────────────────────────────────────────────────────
        head_w, head_h = 26, 20
        head_x = cx - head_w / 2
        head_y = body_y - head_h - 3

        p.setBrush(QBrush(body_c))
        p.setPen(QPen(body_hl, 1.5))
        p.drawRoundedRect(QRectF(head_x, head_y, head_w, head_h), 4, 4)

        # yeux
        for ex in (cx - 6, cx + 2):
            grad = QRadialGradient(QPointF(ex + 2, head_y + 7), 5)
            grad.setColorAt(0, QColor("#90caf9"))
            grad.setColorAt(1, eye_c)
            p.setBrush(QBrush(grad))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(ex, head_y + 4, 7, 7))

        # ── Antenne ───────────────────────────────────────────────────────────
        p.setPen(QPen(ant_c, 1.5))
        p.drawLine(QPointF(cx, head_y), QPointF(cx, head_y - 9))
        p.setBrush(QBrush(ant_c))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - 3, head_y - 12, 6, 6))

        # ── Roues ─────────────────────────────────────────────────────────────
        wr = 13   # rayon roue
        wy = body_y + body_h + wr - 4   # axe Y des roues
        for wx in (cx - body_w / 2 - wr + 6, cx + body_w / 2 + wr - 6):
            # pneu
            p.setBrush(QBrush(wheel_c))
            p.setPen(QPen(wheel_r, 2))
            p.drawEllipse(QRectF(wx - wr, wy - wr, 2 * wr, 2 * wr))
            # moyeu
            p.setBrush(QBrush(body_hl))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(wx - 4, wy - 4, 8, 8))

        # ── Légende ───────────────────────────────────────────────────────────
        font = QFont("Consolas", 7)
        p.setFont(font)
        p.setPen(QPen(text_c))
        p.drawText(QRectF(0, h - 13, w, 12),
                   Qt.AlignmentFlag.AlignHCenter, "CBC Tuner  v1.0  ·  pendule inversé")


# ── Display options panel ─────────────────────────────────────────────────────

class _CurveRow(QWidget):
    """Une ligne de contrôle par courbe : afficher, amplitude réelle, inverser."""

    changed = Signal()

    def __init__(
        self,
        name: str,
        color: str,
        default_max: float,
        unit: str = "",
        show: bool = True,
        invert: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._unit = unit
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 1, 0, 1)
        lay.setSpacing(4)

        # Pastille colorée
        dot = QLabel("●")
        dot.setFixedWidth(14)
        dot.setStyleSheet(f"color:{color};font-size:10px;")
        lay.addWidget(dot)

        # Nom de la courbe
        lbl = QLabel(name)
        lbl.setFixedWidth(52)
        lbl.setStyleSheet("font-size:10px;font-family:Consolas;color:#cccccc;")
        lay.addWidget(lbl)

        # Checkbox affichage
        self._show = QCheckBox()
        self._show.setChecked(show)
        self._show.setFixedWidth(18)
        self._show.setToolTip("Afficher cette courbe")
        self._show.stateChanged.connect(self.changed)
        lay.addWidget(self._show)

        # Label "max:"
        lay.addWidget(QLabel("max:"))

        # Spinbox amplitude réelle
        self._spin = QDoubleSpinBox()
        self._spin.setRange(0.0001, 100000.0)
        self._spin.setDecimals(2)
        self._spin.setValue(default_max)
        self._spin.setFixedWidth(68)
        self._spin.setStepType(QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        self._spin.setToolTip(f"Amplitude réelle correspondant à 1.0 sur le graphique")
        self._spin.valueChanged.connect(self.changed)
        lay.addWidget(self._spin)

        # Unité
        if unit:
            ulbl = QLabel(unit)
            ulbl.setStyleSheet("font-size:9px;color:#78909c;")
            ulbl.setFixedWidth(28)
            lay.addWidget(ulbl)

        # Checkbox inversion
        self._inv = QCheckBox("inv")
        self._inv.setChecked(invert)
        self._inv.setToolTip("Inverser le signe de la courbe")
        self._inv.stateChanged.connect(self.changed)
        lay.addWidget(self._inv)

    def visible(self) -> bool:
        return self._show.isChecked()

    def factor(self) -> float:
        """Multiplicateur à appliquer sur la donnée brute normalisée."""
        sign = -1.0 if self._inv.isChecked() else 1.0
        return sign / max(self._spin.value(), 1e-9)

    def real_amplitude(self) -> float:
        """Valeur réelle correspondant à 1.0 sur le graphique."""
        return self._spin.value()


class _DisplayOptionsPanel(QGroupBox):
    """Panneau de contrôle d'affichage — une ligne par courbe."""

    changed = Signal()

    _CURVES = [
        # (key,      name,     color,    max,   unit,  show,  inv)
        ("pitch",   "pitch",   C_PITCH,  10.0,  "°",   True,  True),
        ("pid_p",   "P",       C_P_TERM,  1.0,  "",    True,  False),
        ("pid_i",   "I",       C_I_TERM,  1.0,  "",    True,  False),
        ("pid_d",   "D",       "#42a5f5", 1.0,  "",    True,  False),
        ("drive",   "drive",   "#ffffff", 1.0,  "",    True,  False),
        ("sp_rpm",  "sp RPM",  "#b0bec5", 85.0, "RPM", True,  False),
        ("rpm_l",   "RPM G",   "#ffd54f", 85.0, "RPM", True,  False),
        ("rpm_r",   "RPM D",   "#4dd0e1", 85.0, "RPM", True,  False),
        ("pwm_l",   "PWM G",   "#ff8a65", 1.0,  "",    True,  False),
        ("pwm_r",   "PWM D",   "#a5d6a7", 1.0,  "",    True,  False),
    ]

    def __init__(self, parent=None):
        super().__init__("Affichage", parent)
        self.setStyleSheet("QGroupBox { font-weight:bold; font-size:10px; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 12, 6, 4)
        lay.setSpacing(1)

        # En-tête
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 2)
        for txt, w in (("courbe", 66), ("vis", 18), ("", 28), ("max réel", 68), ("", 28), ("", 36)):
            l = QLabel(txt)
            l.setFixedWidth(w)
            l.setStyleSheet("font-size:9px;color:#546e7a;")
            hdr.addWidget(l)
        hdr.addStretch()
        lay.addLayout(hdr)

        self._rows: dict[str, _CurveRow] = {}
        for key, name, color, mx, unit, show, inv in self._CURVES:
            row = _CurveRow(name, color, mx, unit, show, inv)
            row.changed.connect(self.changed)
            self._rows[key] = row
            lay.addWidget(row)

    def row(self, key: str) -> _CurveRow:
        return self._rows[key]


# ── Angle setpoint slider ─────────────────────────────────────────────────────

class _AngleSpPanel(QGroupBox):
    """Slider for manual angle equilibrium offset (-5° to +5°, step 0.1°)."""

    value_changed = Signal(float)   # offset in degrees

    _TICKS_PER_DEG = 10   # slider range [-50..+50] → [-5.0..+5.0] °

    def __init__(self, parent=None):
        super().__init__("Consigne angle  (offset équilibre)", parent)
        self.setStyleSheet("QGroupBox { font-weight:bold; font-size:11px; }")

        self._syncing = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 12, 8, 8)
        lay.setSpacing(4)

        # Value label + reset button
        top = QHBoxLayout(); top.setSpacing(6)
        self._lbl = QLabel("0.0 °")
        self._lbl.setStyleSheet(
            "font-size:16px;font-family:Consolas;font-weight:bold;color:#42a5f5;"
        )
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(self._lbl, stretch=1)
        self._reset_btn = QPushButton("Reset")
        self._reset_btn.setFixedWidth(56)
        self._reset_btn.setFixedHeight(24)
        self._reset_btn.clicked.connect(self._reset)
        top.addWidget(self._reset_btn)
        lay.addLayout(top)

        # Slider row with limit labels
        row = QHBoxLayout(); row.setSpacing(4)
        lo_lbl = QLabel("-5°"); lo_lbl.setStyleSheet("font-size:9px;color:#546e7a;")
        hi_lbl = QLabel("+5°"); hi_lbl.setStyleSheet("font-size:9px;color:#546e7a;")
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(-50, 50)
        self._slider.setValue(0)
        self._slider.setTickInterval(10)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._slider.valueChanged.connect(self._on_slider)
        row.addWidget(lo_lbl)
        row.addWidget(self._slider, stretch=1)
        row.addWidget(hi_lbl)
        lay.addLayout(row)

        # Fine spinbox
        spin_row = QHBoxLayout(); spin_row.setSpacing(4)
        spin_row.addWidget(QLabel("Valeur :"))
        self._spin = QDoubleSpinBox()
        self._spin.setRange(-5.0, 5.0)
        self._spin.setDecimals(1)
        self._spin.setSingleStep(0.1)
        self._spin.setSuffix(" °")
        self._spin.setFixedWidth(78)
        self._spin.setStyleSheet("font-size:11px;font-family:Consolas;")
        self._spin.editingFinished.connect(self._on_spin)
        spin_row.addWidget(self._spin)
        spin_row.addStretch()
        lay.addLayout(spin_row)

    def _on_slider(self, v: int):
        if self._syncing: return
        deg = v / self._TICKS_PER_DEG
        self._syncing = True
        self._spin.setValue(deg)
        self._syncing = False
        self._update_label(deg)
        self.value_changed.emit(deg)

    def _on_spin(self):
        if self._syncing: return
        deg = self._spin.value()
        self._syncing = True
        self._slider.setValue(int(round(deg * self._TICKS_PER_DEG)))
        self._syncing = False
        self._update_label(deg)
        self.value_changed.emit(deg)

    def _update_label(self, deg: float):
        sign = "+" if deg >= 0 else ""
        self._lbl.setText(f"{sign}{deg:.1f} °")
        color = "#42a5f5" if abs(deg) < 0.05 else "#ffd54f"
        self._lbl.setStyleSheet(
            f"font-size:16px;font-family:Consolas;font-weight:bold;color:{color};"
        )

    def _reset(self):
        self._syncing = True
        self._slider.setValue(0)
        self._spin.setValue(0.0)
        self._syncing = False
        self._update_label(0.0)
        self.value_changed.emit(0.0)

    def value(self) -> float:
        return self._spin.value()


# ── Motion mode panel ─────────────────────────────────────────────────────────

class _MotionModePanel(QGroupBox):
    """
    3 locomotion modes (switchable via firmware command):
      0 – Velocity   : outer loop = velocity setpoint (RPM)
      1 – Position   : outer loop = position PID  (configured in Position tab)
      4 – Angle direct : no outer loop, target pitch angle directly
    """

    vel_sp_cmd       = Signal(int)    # → SET_SP (rpm)
    angle_direct_cmd = Signal(float)  # → SET_ANGLE_DIRECT (deg)

    _BTN_STYLE_ON  = ("QPushButton { background:#1565c0; color:#e3f2fd; "
                      "font-weight:bold; border-radius:3px; padding:2px 6px; }")
    _BTN_STYLE_OFF = ("QPushButton { background:#263238; color:#78909c; "
                      "font-weight:normal; border-radius:3px; padding:2px 6px; }")

    def __init__(self, parent=None):
        super().__init__("Mode de déplacement", parent)
        self.setStyleSheet("QGroupBox { font-weight:bold; font-size:11px; }")

        self._syncing = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 12, 8, 8)
        lay.setSpacing(6)

        # ── Mode buttons ──────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self._btn_vel = QPushButton("Vitesse")
        self._btn_pos = QPushButton("Position")
        self._btn_ang = QPushButton("Angle direct")
        for btn in (self._btn_vel, self._btn_pos, self._btn_ang):
            btn.setCheckable(True)
            btn.setFixedHeight(26)
            btn.setStyleSheet(self._BTN_STYLE_OFF)
            btn_row.addWidget(btn)
        self._btn_vel.setChecked(True)
        self._btn_vel.setStyleSheet(self._BTN_STYLE_ON)
        lay.addLayout(btn_row)

        # ── Stacked content per mode ─────────────────────────────────────────
        self._stack = QStackedWidget()

        # Page 0 — Velocity
        vel_page = QWidget()
        vl = QVBoxLayout(vel_page)
        vl.setContentsMargins(0, 2, 0, 0)
        vl.setSpacing(4)
        sp_row = QHBoxLayout(); sp_row.setSpacing(6)
        sp_row.addWidget(QLabel("Consigne :"))
        self._vel_spin = QSpinBox()
        self._vel_spin.setRange(-85, 85)
        self._vel_spin.setValue(0)
        self._vel_spin.setSuffix(" RPM")
        self._vel_spin.setFixedWidth(88)
        self._vel_spin.setStyleSheet("font-family:Consolas;font-size:11px;")
        sp_row.addWidget(self._vel_spin)
        sp_row.addStretch()
        vl.addLayout(sp_row)
        vsl_row = QHBoxLayout(); vsl_row.setSpacing(4)
        vsl_lbl_l = QLabel("-85"); vsl_lbl_l.setStyleSheet("font-size:9px;color:#546e7a;")
        vsl_lbl_r = QLabel("+85"); vsl_lbl_r.setStyleSheet("font-size:9px;color:#546e7a;")
        self._vel_slider = QSlider(Qt.Orientation.Horizontal)
        self._vel_slider.setRange(-85, 85)
        self._vel_slider.setValue(0)
        vsl_row.addWidget(vsl_lbl_l)
        vsl_row.addWidget(self._vel_slider, stretch=1)
        vsl_row.addWidget(vsl_lbl_r)
        vl.addLayout(vsl_row)
        vel_btn = QPushButton("↑ Envoyer")
        vel_btn.setFixedHeight(24)
        vel_btn.clicked.connect(self._send_vel)
        vl.addWidget(vel_btn)
        self._stack.addWidget(vel_page)

        # Page 1 — Position
        pos_page = QWidget()
        pl = QVBoxLayout(pos_page)
        pl.setContentsMargins(0, 2, 0, 0)
        info = QLabel("→  Configurer depuis l'onglet Position\n"
                      "   (Hold / Sinusoïde / Tour auto)")
        info.setStyleSheet("color:#78909c;font-size:10px;font-family:Consolas;")
        info.setWordWrap(True)
        pl.addWidget(info)
        pl.addStretch()
        self._stack.addWidget(pos_page)

        # Page 2 — Angle direct
        ang_page = QWidget()
        al = QVBoxLayout(ang_page)
        al.setContentsMargins(0, 2, 0, 0)
        al.setSpacing(4)
        ang_row = QHBoxLayout(); ang_row.setSpacing(6)
        ang_row.addWidget(QLabel("Cible :"))
        self._ang_spin = QDoubleSpinBox()
        self._ang_spin.setRange(-8.0, 8.0)
        self._ang_spin.setDecimals(1)
        self._ang_spin.setSingleStep(0.5)
        self._ang_spin.setValue(0.0)
        self._ang_spin.setSuffix(" °")
        self._ang_spin.setFixedWidth(80)
        self._ang_spin.setStyleSheet("font-family:Consolas;font-size:11px;")
        ang_row.addWidget(self._ang_spin)
        ang_row.addStretch()
        al.addLayout(ang_row)
        asl_row = QHBoxLayout(); asl_row.setSpacing(4)
        asl_lbl_l = QLabel("-8°"); asl_lbl_l.setStyleSheet("font-size:9px;color:#546e7a;")
        asl_lbl_r = QLabel("+8°"); asl_lbl_r.setStyleSheet("font-size:9px;color:#546e7a;")
        self._ang_slider = QSlider(Qt.Orientation.Horizontal)
        self._ang_slider.setRange(-80, 80)   # ×0.1 → [-8..+8]°
        self._ang_slider.setValue(0)
        asl_row.addWidget(asl_lbl_l)
        asl_row.addWidget(self._ang_slider, stretch=1)
        asl_row.addWidget(asl_lbl_r)
        al.addLayout(asl_row)
        ang_btn = QPushButton("↑ Envoyer")
        ang_btn.setFixedHeight(24)
        ang_btn.clicked.connect(self._send_ang)
        al.addWidget(ang_btn)
        self._stack.addWidget(ang_page)

        lay.addWidget(self._stack)

        # ── Internal connections ───────────────────────────────────────────────
        self._btn_vel.clicked.connect(lambda: self._set_mode(0))
        self._btn_pos.clicked.connect(lambda: self._set_mode(1))
        self._btn_ang.clicked.connect(lambda: self._set_mode(2))

        self._vel_slider.valueChanged.connect(self._on_vel_slider)
        self._vel_spin.valueChanged.connect(self._on_vel_spin)
        self._ang_slider.valueChanged.connect(self._on_ang_slider)
        self._ang_spin.valueChanged.connect(self._on_ang_spin)

    # ── Private ───────────────────────────────────────────────────────────────

    def _set_mode(self, idx: int, send_cmd: bool = True):
        for i, btn in enumerate((self._btn_vel, self._btn_pos, self._btn_ang)):
            btn.setChecked(i == idx)
            btn.setStyleSheet(self._BTN_STYLE_ON if i == idx else self._BTN_STYLE_OFF)
        self._stack.setCurrentIndex(idx)
        if send_cmd:
            if idx == 0:
                self._send_vel()
            elif idx == 2:
                self._send_ang()

    def _on_vel_slider(self, v: int):
        if self._syncing: return
        self._syncing = True
        self._vel_spin.setValue(v)
        self._syncing = False

    def _on_vel_spin(self, v: int):
        if self._syncing: return
        self._syncing = True
        self._vel_slider.setValue(v)
        self._syncing = False

    def _on_ang_slider(self, v: int):
        if self._syncing: return
        self._syncing = True
        self._ang_spin.setValue(v / 10.0)
        self._syncing = False

    def _on_ang_spin(self, v: float):
        if self._syncing: return
        self._syncing = True
        self._ang_slider.setValue(int(round(v * 10)))
        self._syncing = False

    def _send_vel(self):
        self.vel_sp_cmd.emit(self._vel_spin.value())

    def _send_ang(self):
        self.angle_direct_cmd.emit(self._ang_spin.value())

    # ── Public ────────────────────────────────────────────────────────────────

    def sync_from_firmware(self, ctrl_mode: int):
        """Reflect firmware ctrl_mode in the button group (no command sent back)."""
        idx = {0: 0, 1: 1, 4: 2}.get(ctrl_mode, -1)
        if idx >= 0:
            self._set_mode(idx, send_cmd=False)


# ── Angle PID panel ───────────────────────────────────────────────────────────

class _AnglePidPanel(QGroupBox):
    apply_requested = Signal(float, float, float)

    def __init__(self, parent=None):
        super().__init__("Angle PID  —  boucle interne", parent)
        self.setStyleSheet("QGroupBox { font-weight:bold; font-size:11px; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 12, 8, 8)
        lay.setSpacing(4)

        self._kp = _PidRow("Kp", 0.500)
        self._ki = _PidRow("Ki", 0.100)
        self._kd = _PidRow("Kd", 0.050)

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


# ── Velocity PID panel ───────────────────────────────────────────────────

class _VelocityPidPanel(QGroupBox):
    apply_requested = Signal(float, float, float)

    def __init__(self, parent=None):
        super().__init__("Velocity PID  —  boucle externe", parent)
        self.setStyleSheet("QGroupBox { font-weight:bold; font-size:11px; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 12, 8, 8)
        lay.setSpacing(4)

        self._kp = _PidRow("Kp", 0.500)
        self._ki = _PidRow("Ki", 0.200)
        self._kd = _PidRow("Kd", 0.100)

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
        self._status.setText(f"→  Kp={kp:.5f}  Ki={ki:.5f}  Kd={kd:.5f}")
        self.apply_requested.emit(kp, ki, kd)

    def gains(self) -> tuple[float, float, float]:
        return self._kp.value(), self._ki.value(), self._kd.value()

    def set_gains(self, kp: float, ki: float, kd: float):
        self._kp.set_value(kp)
        self._ki.set_value(ki)
        self._kd.set_value(kd)
        self._status.setText(f"→  Kp={kp:.5f}  Ki={ki:.5f}  Kd={kd:.5f}")


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

        _section("── Boucle Vitesse (externe) ────────")
        _row("sp_vel",        "Consigne vitesse", "rpm")
        _row("vel_l",         "RPM gauche",       "rpm")
        _row("vel_r",         "RPM droite",       "rpm")
        _row("target_pitch",  "→ Pitch cible",    "°")

        _section("── Boucle Angle (interne) ──────────")
        _row("pv_pitch",      "Pitch mesuré",     "°")
        _row("err_pitch",     "Erreur",            "°")
        _row("drive",         "Drive output",      "%")

        _section("── Sorties moteurs ──────────────────")
        _row("pwm_l",         "Gauche",            "%")
        _row("pwm_r",         "Droite",            "%")

    def update_angle(self, pitch: float, drive_pct: float, target_pitch: float = 0.0):
        error = target_pitch - pitch
        self._vals["pv_pitch"].setText(f"{pitch:+.1f}")
        c = "#ef5350" if abs(pitch) > 30 else "#e0e0e0"
        self._vals["pv_pitch"].setStyleSheet(self._VAL_STYLE + f"color:{c};")
        self._vals["err_pitch"].setText(f"{error:+.1f}")
        self._vals["drive"].setText(f"{drive_pct:+.1f}")
        c = "#ff7043" if abs(drive_pct) > 90 else "#e0e0e0"
        self._vals["drive"].setStyleSheet(self._VAL_STYLE + f"color:{c};")
        c = "#ffd54f" if abs(target_pitch) > 5 else "#e0e0e0"
        self._vals["target_pitch"].setText(f"{target_pitch:+.2f}")
        self._vals["target_pitch"].setStyleSheet(self._VAL_STYLE + f"color:{c};")

    def update_velocity(self, sp_rpm: int, pv_l: int, pv_r: int,
                        pwm_l: float, pwm_r: float):
        self._vals["sp_vel"].setText(f"{sp_rpm:+d}")
        self._vals["vel_l"].setText(f"{pv_l:+d}")
        self._vals["vel_r"].setText(f"{pv_r:+d}")
        self._vals["pwm_l"].setText(f"{pwm_l * 100:+.1f}")
        self._vals["pwm_r"].setText(f"{pwm_r * 100:+.1f}")


# ── K actuator-gain identification ───────────────────────────────────────────

class _KIdentPanel(QGroupBox):
    """
    Continuous real-time identification of K (actuator gain) from live telemetry.

    Regression model (no intercept, all data since Start):
        θ̈ − a²·θ = −K · u
        y           = K · X,   X = −u

    θ̈ is estimated by finite-differencing the telemetered pitch_rate.
    Changing PID gains during sampling does NOT bias K: u is measured
    directly from the drive signal, not reconstructed from gains.
    """

    _A2 = 7.38 ** 2   # a² = g/L,  L = 18 cm measured

    def __init__(self, parent=None):
        super().__init__("Identification de K  (gain actionneur)", parent)
        self.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")

        self._running = False
        # (pitch_deg, drive_norm, pitch_rate_dps, t_monotonic)
        self._buf: list[tuple[float, float, float, float]] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 14, 8, 8)
        lay.setSpacing(6)

        # Start / Stop
        self._btn = QPushButton("▶ Démarrer mesure K")
        self._btn.setCheckable(True)
        self._btn.setFixedHeight(28)
        self._btn.clicked.connect(self._on_toggle)
        lay.addWidget(self._btn)

        # Result display
        self._lbl = QLabel(
            "→ Cliquez ▶ puis connectez et streamez le robot."
        )
        self._lbl.setStyleSheet(
            "font-size:10px;font-family:Consolas;color:#78909c;"
            "padding:5px;border:1px solid #37474f;border-radius:3px;"
        )
        self._lbl.setWordWrap(True)
        self._lbl.setMinimumHeight(60)
        lay.addWidget(self._lbl)

        # Excitation bar
        self._exc_lbl = QLabel("Excitation drive : —")
        self._exc_lbl.setStyleSheet(
            "font-size:9px;font-family:Consolas;color:#546e7a;"
        )
        lay.addWidget(self._exc_lbl)

        # Static note
        note = QLabel(
            "ⓘ  Les gains PID ne biaisent pas K\n"
            "    (drive mesuré, pas recalculé)"
        )
        note.setStyleSheet("font-size:9px;color:#37474f;font-family:Consolas;")
        lay.addWidget(note)

        self._timer = QTimer(self, interval=400)
        self._timer.timeout.connect(self._update)

    # ── Public ────────────────────────────────────────────────────────────────

    def feed(self, pitch: float, drive: float, pitch_rate: float):
        """Append one telemetry sample (drive normalised to [-1,+1])."""
        if self._running:
            self._buf.append((pitch, drive, pitch_rate, _time.monotonic()))

    # ── Private ───────────────────────────────────────────────────────────────

    def _on_toggle(self, checked: bool):
        self._running = checked
        if checked:
            self._buf.clear()
            self._btn.setText("⏹ Stop mesure K")
            self._timer.start()
            self._set_msg(
                "→ Laissez le robot s'équilibrer (ou le perturber).\n"
                "  Accumulation en cours…",
                "#90a4ae",
            )
        else:
            self._timer.stop()
            self._btn.setText("▶ Démarrer mesure K")

    def _update(self):
        n_raw = len(self._buf)
        K, se_K, r2, n_used, exc = self._regress(self._buf)

        exc_pct = int(min(exc, 1.0) * 100)
        filled  = exc_pct // 5          # 20 chars wide bar
        bar     = "█" * filled + "░" * (20 - filled)
        self._exc_lbl.setText(f"Excitation : {bar} {exc_pct}%")

        # ── Diagnostic messages ──────────────────────────────────────────────
        if n_raw == 0:
            self._set_msg(
                "Aucune donnée reçue.\n"
                "→ 1. Connectez le robot (bouton Connecter)\n"
                "  2. Activez le stream (▶ Stream)\n"
                "  3. Le robot doit être sous tension.",
                "#78909c",
            )
            return

        if n_raw < 10:
            self._set_msg(
                f"Accumulation : {n_raw} échantillon(s)…\n"
                "→ Attendez quelques secondes, ou\n"
                "  augmentez la cadence stream (50–100 Hz).",
                "#78909c",
            )
            return

        if exc < 0.04:
            self._set_msg(
                f"Drive trop faible ({exc_pct}% d'excitation, {n_raw} pts).\n"
                "→ Perturbez doucement le robot pour\n"
                "  créer des variations de drive.",
                "#ffd54f",
            )
            return

        if n_used < 5:
            self._set_msg(
                f"Points utiles insuffisants ({n_used}/{n_raw}).\n"
                "→ Le robot est peut-être trop stable\n"
                "  (drive ≈ 0). Perturbez-le légèrement.",
                "#ffd54f",
            )
            return

        # ── Result ───────────────────────────────────────────────────────────
        rel_err = se_K / max(abs(K), 1e-3) * 100
        if r2 > 0.75 and rel_err < 25:
            col = "#66bb6a"
        elif r2 > 0.45:
            col = "#ffd54f"
        else:
            col = "#ef5350"

        self._set_msg(
            f"K = {K:.0f}  ±  {se_K:.0f}  °/s²\n"
            f"R² = {r2:.3f}   ±{rel_err:.0f}%   n = {n_used}/{n_raw} pts",
            col,
        )

    def _set_msg(self, text: str, color: str):
        self._lbl.setText(text)
        self._lbl.setStyleSheet(
            f"font-size:10px;font-family:Consolas;color:{color};"
            "padding:5px;border:1px solid #37474f;border-radius:3px;"
        )

    @staticmethod
    def _regress(
        buf: list[tuple[float, float, float, float]],
    ) -> tuple[float, float, float, int, float]:
        """Return (K, se_K, r2, n_used, mean_abs_drive)."""
        if len(buf) < 4:
            return 0.0, 0.0, 0.0, 0, 0.0

        arr   = np.array(buf, dtype=float)
        theta = arr[:, 0]
        u     = arr[:, 1]
        omega = arr[:, 2]
        t     = arr[:, 3]

        dt = np.diff(t)
        dt = np.where(dt < 5e-4, 5e-4, dt)

        # θ̈ from gyro differences (less noise than double-diff of pitch)
        ddot      = np.diff(omega) / dt
        theta_mid = (theta[:-1] + theta[1:]) / 2.0
        u_mid     = (u[:-1]     + u[1:])     / 2.0

        exc = float(np.mean(np.abs(u_mid)))

        y = ddot - _KIdentPanel._A2 * theta_mid  # LHS
        X = -u_mid                                 # regressor

        mask = np.abs(X) > 0.03   # ignore near-zero drive samples
        n    = int(mask.sum())
        if n < 4:
            return 0.0, 0.0, 0.0, n, exc

        yf, Xf = y[mask], X[mask]
        XtX    = float(np.dot(Xf, Xf))
        if XtX < 1e-6:
            return 0.0, 0.0, 0.0, n, exc

        K         = float(np.dot(Xf, yf) / XtX)
        residuals = yf - K * Xf
        RSS       = float(np.dot(residuals, residuals))
        se_K      = float(np.sqrt(RSS / max(n - 1, 1) / XtX))
        SS_tot    = float(np.var(yf) * n)
        r2        = max(0.0, min(1.0, 1.0 - RSS / max(SS_tot, 1e-10)))

        return K, se_K, r2, n, exc


# ── Position control panel (tab) ─────────────────────────────────────────────

class _PositionPanel(QWidget):
    """Full position control tab: PID gains, mode selector, live plot."""

    gains_changed = Signal(float, float, float)   # Kp, Ki, Kd → loop_id=3
    pos_sp_cmd    = Signal(float)                 # SET_POS_SP(sp_cm)
    pos_traj_cmd  = Signal(int, float, float)     # SET_POS_TRAJ(mode, ampl, period)
    spin_cmd      = Signal(bool, float, float)    # SPIN_CTRL(enable, interval_s, yaw_force)
    vel_mode_cmd  = Signal()                      # return to velocity mode

    _NPTS = 6000   # ~5 min at 20 Hz

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t_pos:  deque[float] = deque(maxlen=self._NPTS)
        self._pos_cm: deque[float] = deque(maxlen=self._NPTS)
        self._sp_cm:  deque[float] = deque(maxlen=self._NPTS)
        self._t0: float | None = None

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(6)
        splitter.addWidget(self._build_controls())
        splitter.addWidget(self._build_plot())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 700])

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter)

        self._plot_timer = QTimer(self, interval=100)
        self._plot_timer.timeout.connect(self._refresh_plot)
        self._plot_timer.start()

    # ── Controls ──────────────────────────────────────────────────────────────

    def _build_controls(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(290)
        scroll.setMaximumWidth(380)

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(8)

        # ── PID gains ─────────────────────────────────────────────────────────
        pid_box = QGroupBox("Gains — Position PID  (boucle n°3)")
        pid_box.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        pid_lay = QVBoxLayout(pid_box)
        pid_lay.setContentsMargins(8, 14, 8, 8)
        pid_lay.setSpacing(4)

        self._pos_kp = _PidRow("Kp", 2.000)
        self._pos_ki = _PidRow("Ki", 0.500)
        self._pos_kd = _PidRow("Kd", 0.500)
        self._pos_kp.set_value(0.5)

        self._gains_debounce = QTimer(singleShot=True, interval=400)
        self._gains_debounce.timeout.connect(self._emit_gains)
        for row in (self._pos_kp, self._pos_ki, self._pos_kd):
            pid_lay.addWidget(row)
            row.value_changed.connect(lambda _: self._gains_debounce.start())

        self._gains_status = QLabel("—")
        self._gains_status.setStyleSheet(
            "color:#90a4ae;font-size:10px;font-family:Consolas;"
        )
        pid_lay.addWidget(self._gains_status)

        pid_btns = QHBoxLayout()
        pid_btns.setSpacing(6)
        rst = QPushButton("Reset (0,0,0)")
        rst.setFixedHeight(24)
        rst.clicked.connect(self._reset_gains)
        pid_btns.addWidget(rst)
        apl = QPushButton("✓ Appliquer")
        apl.setFixedHeight(24)
        apl.setFixedWidth(95)
        apl.clicked.connect(self._emit_gains)
        pid_btns.addWidget(apl)
        pid_lay.addLayout(pid_btns)
        lay.addWidget(pid_box)

        # ── Mode & Consigne ────────────────────────────────────────────────────
        mode_box = QGroupBox("Mode & Consigne")
        mode_box.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        mode_lay = QVBoxLayout(mode_box)
        mode_lay.setContentsMargins(8, 14, 8, 8)
        mode_lay.setSpacing(6)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Mode :"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Hold",       userData=_TRAJ_HOLD)
        self._mode_combo.addItem("Sinusoïde",  userData=_TRAJ_SINUS)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self._mode_combo)
        mode_row.addStretch()
        mode_lay.addLayout(mode_row)

        # Hold section
        self._hold_widget = QWidget()
        hold_lay = QVBoxLayout(self._hold_widget)
        hold_lay.setContentsMargins(0, 0, 0, 0)
        hold_lay.setSpacing(4)

        h_row = QHBoxLayout()
        h_row.addWidget(QLabel("Cible :"))
        self._hold_spin = QDoubleSpinBox()
        self._hold_spin.setRange(-50.0, 50.0)
        self._hold_spin.setDecimals(1)
        self._hold_spin.setSingleStep(1.0)
        self._hold_spin.setValue(0.0)
        self._hold_spin.setSuffix(" cm")
        self._hold_spin.setFixedWidth(90)
        self._hold_spin.setStepType(QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        h_row.addWidget(self._hold_spin)
        h_row.addStretch()
        hold_lay.addLayout(h_row)

        self._hold_btn = QPushButton("▶ Activer Hold")
        self._hold_btn.setFixedHeight(28)
        self._hold_btn.clicked.connect(self._send_hold)
        hold_lay.addWidget(self._hold_btn)
        mode_lay.addWidget(self._hold_widget)

        # Sinus section
        self._sinus_widget = QWidget()
        sinus_lay = QVBoxLayout(self._sinus_widget)
        sinus_lay.setContentsMargins(0, 0, 0, 0)
        sinus_lay.setSpacing(4)

        a_row = QHBoxLayout()
        a_row.addWidget(QLabel("Amplitude :"))
        self._sinus_ampl = QDoubleSpinBox()
        self._sinus_ampl.setRange(1.0, 50.0)
        self._sinus_ampl.setDecimals(1)
        self._sinus_ampl.setSingleStep(1.0)
        self._sinus_ampl.setValue(10.0)
        self._sinus_ampl.setSuffix(" cm")
        self._sinus_ampl.setFixedWidth(90)
        a_row.addWidget(self._sinus_ampl)
        a_row.addStretch()
        sinus_lay.addLayout(a_row)

        t_row = QHBoxLayout()
        t_row.addWidget(QLabel("Période :"))
        self._sinus_period = QDoubleSpinBox()
        self._sinus_period.setRange(0.5, 30.0)
        self._sinus_period.setDecimals(1)
        self._sinus_period.setSingleStep(0.5)
        self._sinus_period.setValue(4.0)
        self._sinus_period.setSuffix(" s")
        self._sinus_period.setFixedWidth(90)
        t_row.addWidget(self._sinus_period)
        t_row.addStretch()
        sinus_lay.addLayout(t_row)

        self._sinus_btn = QPushButton("▶ Démarrer sinusoïde")
        self._sinus_btn.setFixedHeight(28)
        self._sinus_btn.setCheckable(True)
        self._sinus_btn.clicked.connect(self._on_sinus_toggle)
        sinus_lay.addWidget(self._sinus_btn)
        mode_lay.addWidget(self._sinus_widget)
        self._sinus_widget.setVisible(False)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        mode_lay.addWidget(sep)

        vel_btn = QPushButton("↩ Retour Mode Vitesse")
        vel_btn.setFixedHeight(28)
        vel_btn.clicked.connect(self._on_vel_mode)
        mode_lay.addWidget(vel_btn)
        lay.addWidget(mode_box)

        # ── État temps réel ────────────────────────────────────────────────────
        st_box = QGroupBox("État temps réel")
        st_box.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        st_lay = QVBoxLayout(st_box)
        st_lay.setContentsMargins(8, 14, 8, 8)
        st_lay.setSpacing(2)

        _V = "color:#e0e0e0;font-size:12px;font-family:Consolas;font-weight:bold;"
        _L = "color:#78909c;font-size:11px;font-family:Consolas;"
        _U = "color:#546e7a;font-size:11px;font-family:Consolas;"

        self._sv: dict[str, QLabel] = {}

        def _srow(key: str, label: str, unit: str):
            h = QHBoxLayout()
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(4)
            l = QLabel(label)
            l.setStyleSheet(_L)
            l.setFixedWidth(110)
            v = QLabel("—")
            v.setStyleSheet(_V)
            v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            u = QLabel(unit)
            u.setStyleSheet(_U)
            u.setFixedWidth(32)
            h.addWidget(l)
            h.addWidget(v, stretch=1)
            h.addWidget(u)
            st_lay.addLayout(h)
            self._sv[key] = v

        _srow("mode",   "Mode",       "")
        _srow("pos",    "Position",   "cm")
        _srow("sp",     "Consigne",   "cm")
        _srow("err",    "Erreur",     "cm")
        _srow("vel_sp", "Vel SP",     "rpm")
        lay.addWidget(st_box)

        # ── Cas 4 — Auto-spin ─────────────────────────────────────────────────
        spin_box = QGroupBox("Cas 4 — Tour automatique")
        spin_box.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        spin_lay = QVBoxLayout(spin_box)
        spin_lay.setContentsMargins(8, 14, 8, 8)
        spin_lay.setSpacing(6)

        iv_row = QHBoxLayout()
        iv_row.addWidget(QLabel("Intervalle :"))
        self._spin_interval = QDoubleSpinBox()
        self._spin_interval.setRange(5.0, 300.0)
        self._spin_interval.setDecimals(0)
        self._spin_interval.setSingleStep(5.0)
        self._spin_interval.setValue(60.0)
        self._spin_interval.setSuffix(" s")
        self._spin_interval.setFixedWidth(80)
        iv_row.addWidget(self._spin_interval)
        iv_row.addStretch()
        spin_lay.addLayout(iv_row)

        yf_row = QHBoxLayout()
        yf_row.addWidget(QLabel("Force lacet :"))
        self._spin_yaw = QDoubleSpinBox()
        self._spin_yaw.setRange(0.10, 0.50)
        self._spin_yaw.setDecimals(2)
        self._spin_yaw.setSingleStep(0.05)
        self._spin_yaw.setValue(0.40)
        self._spin_yaw.setFixedWidth(80)
        yf_row.addWidget(self._spin_yaw)
        yf_row.addStretch()
        spin_lay.addLayout(yf_row)

        self._spin_btn = QPushButton("▶ Activer tour auto")
        self._spin_btn.setFixedHeight(28)
        self._spin_btn.setCheckable(True)
        self._spin_btn.clicked.connect(self._on_spin_toggle)
        spin_lay.addWidget(self._spin_btn)

        self._spin_status = QLabel("—")
        self._spin_status.setStyleSheet(
            "color:#90a4ae;font-size:10px;font-family:Consolas;"
        )
        spin_lay.addWidget(self._spin_status)
        lay.addWidget(spin_box)

        lay.addStretch()

        scroll.setWidget(container)
        return scroll

    # ── Plot ──────────────────────────────────────────────────────────────────

    def _build_plot(self) -> pg.PlotWidget:
        pw = pg.PlotWidget(title="Position  (cm)")
        pw.showGrid(x=True, y=True, alpha=0.25)
        pw.setLabel("left", "position (cm)")
        pw.setLabel("bottom", "temps (s)")
        pw.addLegend(offset=(10, 10))
        pw.addLine(y=0, pen=pg.mkPen("#546e7a", width=1,
                                     style=Qt.PenStyle.DashLine))

        self._c_sp  = pw.plot(pen=pg.mkPen("#42a5f5", width=2,
                                           style=Qt.PenStyle.DashLine),
                              name="consigne")
        self._c_pos = pw.plot(pen=pg.mkPen("#ef5350", width=2),
                              name="position")

        for c in (self._c_sp, self._c_pos):
            c.setDownsampling(auto=True, method="subsample")
            c.setClipToView(True)

        self._pw_pos = pw
        return pw

    # ── Slots & helpers ───────────────────────────────────────────────────────

    def _on_mode_changed(self, _idx: int):
        mode = self._mode_combo.currentData()
        self._hold_widget.setVisible(mode == _TRAJ_HOLD)
        self._sinus_widget.setVisible(mode == _TRAJ_SINUS)
        if mode != _TRAJ_SINUS and self._sinus_btn.isChecked():
            self._sinus_btn.setChecked(False)
            self._sinus_btn.setText("▶ Démarrer sinusoïde")

    def _send_hold(self):
        self.pos_sp_cmd.emit(self._hold_spin.value())

    def _on_sinus_toggle(self, checked: bool):
        if checked:
            self.pos_traj_cmd.emit(
                _TRAJ_SINUS,
                self._sinus_ampl.value(),
                self._sinus_period.value(),
            )
            self._sinus_btn.setText("⏹ Stop sinusoïde")
        else:
            self.pos_sp_cmd.emit(0.0)   # hold at current origin
            self._sinus_btn.setText("▶ Démarrer sinusoïde")

    def _on_spin_toggle(self, checked: bool):
        if checked:
            self._spin_btn.setText("⏹ Stop tour auto")
            self._spin_status.setText("En attente du premier tour...")
            self.spin_cmd.emit(True, self._spin_interval.value(), self._spin_yaw.value())
        else:
            self._spin_btn.setText("▶ Activer tour auto")
            self._spin_status.setText("Désactivé")
            self.spin_cmd.emit(False, 60.0, 0.4)

    def _on_vel_mode(self):
        if self._sinus_btn.isChecked():
            self._sinus_btn.setChecked(False)
            self._sinus_btn.setText("▶ Démarrer sinusoïde")
        if self._spin_btn.isChecked():
            self._spin_btn.setChecked(False)
            self._spin_btn.setText("▶ Activer tour auto")
            self._spin_status.setText("Désactivé")
        self.vel_mode_cmd.emit()

    def _emit_gains(self):
        kp, ki, kd = self.gains()
        self._gains_status.setText(f"→  Kp={kp:.4f}  Ki={ki:.4f}  Kd={kd:.4f}")
        self.gains_changed.emit(kp, ki, kd)

    def _reset_gains(self):
        for row in (self._pos_kp, self._pos_ki, self._pos_kd):
            row.set_value(0.0)
        self._emit_gains()

    def gains(self) -> tuple[float, float, float]:
        return self._pos_kp.value(), self._pos_ki.value(), self._pos_kd.value()

    def set_gains(self, kp: float, ki: float, kd: float):
        self._pos_kp.set_value(kp)
        self._pos_ki.set_value(ki)
        self._pos_kd.set_value(kd)
        self._gains_status.setText(f"→  Kp={kp:.4f}  Ki={ki:.4f}  Kd={kd:.4f}")

    def on_pos_sample(self, pos_cm: float, sp_cm: float, vel_sp_rpm: float,
                      ctrl_mode: int, traj_mode: int):
        now = _time.monotonic()
        if self._t0 is None:
            self._t0 = now
        self._t_pos.append(now - self._t0)
        self._pos_cm.append(pos_cm)
        self._sp_cm.append(sp_cm)

        err = sp_cm - pos_cm
        mode_str = {
            (0, 0): "VELOCITY",
            (1, 0): "HOLD",
            (1, 1): "SINUS",
            (2, 0): "DRIVE DIRECT",
            (3, 0): "SPIN – attente",
            (3, 1): "SPIN – rotation",
            (4, 0): "ANGLE DIRECT",
        }.get((ctrl_mode, traj_mode), "—")
        c_mode = {
            "VELOCITY":       "#78909c",
            "HOLD":           "#42a5f5",
            "SINUS":          "#66bb6a",
            "DRIVE DIRECT":   "#ab47bc",
            "SPIN – attente": "#ffd54f",
            "SPIN – rotation":"#ff7043",
            "ANGLE DIRECT":   "#26c6da",
        }.get(mode_str, "#e0e0e0")

        # Update spin button and status label to reflect firmware state
        if ctrl_mode == _CTRL_SPIN and not self._spin_btn.isChecked():
            self._spin_btn.setChecked(True)
            self._spin_btn.setText("⏹ Stop tour auto")
        if ctrl_mode == _CTRL_SPIN:
            if traj_mode == 1:
                self._spin_status.setText("Rotation en cours...")
            else:
                self._spin_status.setText("En attente du prochain tour")
        _V = "font-size:12px;font-family:Consolas;font-weight:bold;"
        self._sv["mode"].setText(mode_str)
        self._sv["mode"].setStyleSheet(f"color:{c_mode};" + _V)
        self._sv["pos"].setText(f"{pos_cm:+.1f}")
        self._sv["sp"].setText(f"{sp_cm:+.1f}")
        self._sv["err"].setText(f"{err:+.1f}")
        c_err = ("#ef5350" if abs(err) > 10
                 else "#ffd54f" if abs(err) > 3 else "#e0e0e0")
        self._sv["err"].setStyleSheet(f"color:{c_err};" + _V)
        self._sv["vel_sp"].setText(f"{vel_sp_rpm:+.1f}")

    def _refresh_plot(self):
        n = len(self._t_pos)
        if n < 2:
            return
        t   = np.fromiter(self._t_pos, float, n)
        pos = np.fromiter(self._pos_cm, float, n)
        sp  = np.fromiter(self._sp_cm,  float, n)
        t_now = t[-1]
        mask  = t >= (t_now - 30.0)   # 30 s window
        self._c_pos.setData(x=t[mask], y=pos[mask])
        self._c_sp.setData(x=t[mask],  y=sp[mask])
        self._pw_pos.setXRange(t_now - 30.0, t_now, padding=0)

    def clear(self):
        self._t_pos.clear()
        self._pos_cm.clear()
        self._sp_cm.clear()
        self._t0 = None
        self._c_pos.setData([], [])
        self._c_sp.setData([], [])


# ── Power panel ──────────────────────────────────────────────────────────────

class _PowerPanel(QWidget):
    """Live current (A) and electrical power (W) per motor, left/right separated."""

    _NPTS    = 6000   # ~5 min at 20 Hz
    _WIN_S   = 30.0   # default scroll window

    _VAL_STYLE = "color:#e0e0e0;font-size:13px;font-family:Consolas;font-weight:bold;"
    _LBL_STYLE = "color:#78909c;font-size:11px;font-family:Consolas;"
    _UNI_STYLE = "color:#546e7a;font-size:11px;font-family:Consolas;"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t0: float | None = None
        self._t_buf  : deque[float] = deque(maxlen=self._NPTS)
        self._cl_buf : deque[float] = deque(maxlen=self._NPTS)
        self._cr_buf : deque[float] = deque(maxlen=self._NPTS)
        self._pl_buf : deque[float] = deque(maxlen=self._NPTS)
        self._pr_buf : deque[float] = deque(maxlen=self._NPTS)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(6)
        splitter.addWidget(self._build_readout())
        splitter.addWidget(self._build_plots())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([200, 700])

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter)

        self._plot_timer = QTimer(self, interval=100)
        self._plot_timer.timeout.connect(self._refresh_plots)
        self._plot_timer.start()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_readout(self) -> QWidget:
        box = QGroupBox("Valeurs temps réel")
        box.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        box.setMinimumWidth(190)
        box.setMaximumWidth(240)

        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 14, 8, 8)
        lay.setSpacing(4)

        self._rv: dict[str, QLabel] = {}

        def _sec(text: str):
            l = QLabel(text)
            l.setStyleSheet(
                "color:#42a5f5;font-size:10px;font-family:Consolas;"
                "font-weight:bold;margin-top:6px;"
            )
            lay.addWidget(l)

        def _row(key: str, label: str, unit: str):
            h = QHBoxLayout()
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(4)
            lbl = QLabel(label); lbl.setStyleSheet(self._LBL_STYLE); lbl.setFixedWidth(90)
            val = QLabel("—");   val.setStyleSheet(self._VAL_STYLE)
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            uni = QLabel(unit);  uni.setStyleSheet(self._UNI_STYLE); uni.setFixedWidth(28)
            h.addWidget(lbl); h.addWidget(val, stretch=1); h.addWidget(uni)
            lay.addLayout(h)
            self._rv[key] = val

        _sec("── Moteur Gauche ───────")
        _row("cl", "Courant",  "A")
        _row("pl", "Puissance","W")

        _sec("── Moteur Droite ───────")
        _row("cr", "Courant",  "A")
        _row("pr", "Puissance","W")

        _sec("── Total ────────────────")
        _row("pt", "Puissance","W")

        clear_btn = QPushButton("Effacer")
        clear_btn.setFixedHeight(26)
        clear_btn.clicked.connect(self.clear)
        lay.addStretch()
        lay.addWidget(clear_btn)

        return box

    def _build_plots(self) -> QWidget:
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setHandleWidth(5)

        # ── Current plot ──────────────────────────────────────────────────────
        self._pw_current = pg.PlotWidget(title="Courant moteurs (A)")
        self._pw_current.showGrid(x=True, y=True, alpha=0.25)
        self._pw_current.setLabel("left", "courant (A)")
        self._pw_current.setLabel("bottom", "temps (s)")
        self._pw_current.addLegend(offset=(10, 10))
        self._pw_current.addLine(y=0, pen=pg.mkPen("#37474f", width=1,
                                                    style=Qt.PenStyle.DashLine))
        self._c_cl = self._pw_current.plot(
            pen=pg.mkPen("#ef5350", width=2), name="I gauche")
        self._c_cr = self._pw_current.plot(
            pen=pg.mkPen("#ff8a65", width=2), name="I droite")
        for c in (self._c_cl, self._c_cr):
            c.setDownsampling(auto=True, method="subsample")
            c.setClipToView(True)

        # ── Power plot ────────────────────────────────────────────────────────
        self._pw_power = pg.PlotWidget(title="Puissance électrique (W)  —  V×I, Vnom=12V")
        self._pw_power.showGrid(x=True, y=True, alpha=0.25)
        self._pw_power.setLabel("left", "puissance (W)")
        self._pw_power.setLabel("bottom", "temps (s)")
        self._pw_power.addLegend(offset=(10, 10))
        self._pw_power.addLine(y=0, pen=pg.mkPen("#37474f", width=1,
                                                  style=Qt.PenStyle.DashLine))
        self._c_pl = self._pw_power.plot(
            pen=pg.mkPen("#ef5350", width=2), name="P gauche")
        self._c_pr = self._pw_power.plot(
            pen=pg.mkPen("#ff8a65", width=2), name="P droite")
        self._c_pt = self._pw_power.plot(
            pen=pg.mkPen("#ffd54f", width=2,
                         style=Qt.PenStyle.DashLine), name="P total")
        for c in (self._c_pl, self._c_pr, self._c_pt):
            c.setDownsampling(auto=True, method="subsample")
            c.setClipToView(True)

        vsplit.addWidget(self._pw_current)
        vsplit.addWidget(self._pw_power)
        vsplit.setSizes([300, 300])
        return vsplit

    # ── Public slots ─────────────────────────────────────────────────────────

    def on_power_sample(self, curr_l: float, curr_r: float,
                        pow_l: float, pow_r: float):
        now = _time.monotonic()
        if self._t0 is None:
            self._t0 = now
        self._t_buf.append(now - self._t0)
        self._cl_buf.append(curr_l)
        self._cr_buf.append(curr_r)
        self._pl_buf.append(pow_l)
        self._pr_buf.append(pow_r)

        def _fmt_a(v: float) -> str:
            c = "#ef5350" if v > 1.5 else "#ffd54f" if v > 0.8 else "#e0e0e0"
            return f'<span style="color:{c}">{v:.3f}</span>'

        def _fmt_w(v: float) -> str:
            c = "#ef5350" if v > 18.0 else "#ffd54f" if v > 9.0 else "#e0e0e0"
            return f'<span style="color:{c}">{v:.1f}</span>'

        self._rv["cl"].setText(_fmt_a(curr_l)); self._rv["cl"].setTextFormat(Qt.TextFormat.RichText)
        self._rv["cr"].setText(_fmt_a(curr_r)); self._rv["cr"].setTextFormat(Qt.TextFormat.RichText)
        self._rv["pl"].setText(_fmt_w(pow_l));  self._rv["pl"].setTextFormat(Qt.TextFormat.RichText)
        self._rv["pr"].setText(_fmt_w(pow_r));  self._rv["pr"].setTextFormat(Qt.TextFormat.RichText)
        self._rv["pt"].setText(_fmt_w(pow_l + pow_r)); self._rv["pt"].setTextFormat(Qt.TextFormat.RichText)

    def clear(self):
        for d in (self._t_buf, self._cl_buf, self._cr_buf, self._pl_buf, self._pr_buf):
            d.clear()
        self._t0 = None
        for c in (self._c_cl, self._c_cr, self._c_pl, self._c_pr, self._c_pt):
            c.setData([], [])
        for key in self._rv:
            self._rv[key].setText("—")

    # ── Internal ─────────────────────────────────────────────────────────────

    def _refresh_plots(self):
        n = len(self._t_buf)
        if n < 2:
            return
        t  = np.fromiter(self._t_buf, float, n)
        cl = np.fromiter(self._cl_buf, float, n)
        cr = np.fromiter(self._cr_buf, float, n)
        pl = np.fromiter(self._pl_buf, float, n)
        pr = np.fromiter(self._pr_buf, float, n)
        pt = pl + pr
        t_now = t[-1]
        mask  = t >= (t_now - self._WIN_S)
        tw    = t[mask]
        self._c_cl.setData(x=tw, y=cl[mask])
        self._c_cr.setData(x=tw, y=cr[mask])
        self._c_pl.setData(x=tw, y=pl[mask])
        self._c_pr.setData(x=tw, y=pr[mask])
        self._c_pt.setData(x=tw, y=pt[mask])
        for pw in (self._pw_current, self._pw_power):
            pw.setXRange(t_now - self._WIN_S, t_now, padding=0)


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

        self._planner_panel = SweepPlannerPanel()
        self._runner_panel  = SweepRunnerPanel()
        self._results_panel = SweepPanel()
        self._ident_k_panel  = IdentKPanel()
        self._ident_td_panel = IdentTdPanel()
        self._ident_a_panel  = IdentAPanel()
        self._sim_panel         = SimPanel()
        self._sim_panel.request_snapshot.connect(self._on_snapshot_request)
        self._sim_panel.apply_angle_gains.connect(self._on_sim_apply_angle_gains)
        self._sim_panel.apply_vel_gains.connect(self._on_sim_apply_vel_gains)
        self._motor_calib_panel = MotorCalibPanel()

        self._right_tabs.addTab(self._planner_panel,      "Plan")
        self._tab_run_idx = self._right_tabs.addTab(self._runner_panel, "Run")
        self._tab_res_idx = self._right_tabs.addTab(self._results_panel, "Résultats")
        self._right_tabs.addTab(self._ident_k_panel,      "Ident K")
        self._right_tabs.addTab(self._ident_td_panel,     "Ident td")
        self._right_tabs.addTab(self._ident_a_panel,      "Ident a")
        self._right_tabs.addTab(self._sim_panel,          "Simulation")
        self._right_tabs.addTab(self._motor_calib_panel,  "Calib moteurs")

        self._pos_panel = _PositionPanel()
        self._pos_panel.gains_changed.connect(
            lambda kp, ki, kd: self._send_gains(3, kp, ki, kd)
        )
        self._pos_panel.pos_sp_cmd.connect(self._send_pos_sp)
        self._pos_panel.pos_traj_cmd.connect(self._send_pos_traj)
        self._pos_panel.spin_cmd.connect(self._send_spin)
        self._pos_panel.vel_mode_cmd.connect(lambda: self._send_sp(0))
        self._right_tabs.addTab(self._pos_panel, "Position")

        self._power_panel = _PowerPanel()
        self._right_tabs.addTab(self._power_panel, "Courant")

        self._ident_k_panel.send_drive.connect(self._send_drive)
        self._ident_k_panel.send_sp.connect(self._send_sp)
        self._ident_td_panel.send_drive.connect(self._send_drive)
        self._ident_td_panel.send_sp.connect(self._send_sp)
        self._ident_a_panel.send_drive.connect(self._send_drive)
        self._ident_a_panel.send_sp.connect(self._send_sp)
        self._motor_calib_panel.start_calib.connect(self._send_motor_calib)

        self._planner_panel.plan_ready.connect(self._on_plan_ready)
        self._runner_panel.gains_to_apply.connect(
            lambda kp, ki, kd: self._send_gains(0, kp, ki, kd)
        )
        self._runner_panel.sweep_complete.connect(self._on_sweep_complete)

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

        self._motion_panel = _MotionModePanel()
        self._motion_panel.vel_sp_cmd.connect(self._send_sp)
        self._motion_panel.angle_direct_cmd.connect(self._send_angle_direct)
        lay.addWidget(self._motion_panel)

        self._angle_panel = _AnglePidPanel()
        self._angle_panel.apply_requested.connect(
            lambda kp, ki, kd: self._send_gains(0, kp, ki, kd)
        )
        lay.addWidget(self._angle_panel)

        self._angle_sp_panel = _AngleSpPanel()
        self._angle_sp_panel.value_changed.connect(self._send_angle_sp)
        lay.addWidget(self._angle_sp_panel)

        self._velocity_panel = _VelocityPidPanel()
        self._velocity_panel.apply_requested.connect(self._on_vel_gains_changed)
        lay.addWidget(self._velocity_panel)

        self._chain_panel = _SignalChainPanel()
        lay.addWidget(self._chain_panel)

        self._disp_panel = _DisplayOptionsPanel()
        self._disp_panel.changed.connect(lambda: None)  # refresh déclenché par timer
        lay.addWidget(self._disp_panel)

        self._kident_panel = _KIdentPanel()
        lay.addWidget(self._kident_panel)

        lay.addWidget(_RobotLogo())

        lay.addStretch()
        scroll.setWidget(container)
        return scroll

    def _build_plots_panel(self) -> pg.PlotWidget:
        self._pw_main = pg.PlotWidget(title="Pitch · PID · Moteurs  (tout normalisé)")
        self._pw_main.showGrid(x=True, y=True, alpha=0.25)
        self._pw_main.setLabel("left", "unités normalisées")
        self._pw_main.addLegend(offset=(10, 10))
        self._pw_main.addLine(y=0,  pen=pg.mkPen(C_ZERO,    width=1, style=Qt.PenStyle.DashLine))
        self._pw_main.addLine(y=1,  pen=pg.mkPen("#37474f", width=1, style=Qt.PenStyle.DashLine))
        self._pw_main.addLine(y=-1, pen=pg.mkPen("#37474f", width=1, style=Qt.PenStyle.DashLine))

        # Pitch + PID
        self._c_pitch  = self._pw_main.plot(pen=pg.mkPen(C_PITCH,  width=2), name="pitch")
        self._c_pid_p  = self._pw_main.plot(pen=pg.mkPen(C_P_TERM, width=2), name="P")
        self._c_pid_i  = self._pw_main.plot(pen=pg.mkPen(C_I_TERM, width=2), name="I")
        self._c_pid_d  = self._pw_main.plot(pen=pg.mkPen(C_D_TERM, width=2), name="D")
        self._c_drive  = self._pw_main.plot(pen=pg.mkPen("#ffffff", width=2,
                                             style=Qt.PenStyle.DashLine), name="drive")
        # Moteurs
        self._c_sp_rpm = self._pw_main.plot(pen=pg.mkPen("#b0bec5", width=1,
                                             style=Qt.PenStyle.DashLine), name="sp RPM")
        self._c_rpm_l  = self._pw_main.plot(pen=pg.mkPen("#ffd54f", width=2), name="RPM G")
        self._c_rpm_r  = self._pw_main.plot(pen=pg.mkPen("#4dd0e1", width=2), name="RPM D")
        self._c_pwm_l  = self._pw_main.plot(pen=pg.mkPen("#ff8a65", width=1,
                                             style=Qt.PenStyle.DotLine), name="PWM G")
        self._c_pwm_r  = self._pw_main.plot(pen=pg.mkPen("#a5d6a7", width=1,
                                             style=Qt.PenStyle.DotLine), name="PWM D")

        for c in (self._c_pitch, self._c_pid_p, self._c_pid_i, self._c_pid_d, self._c_drive,
                  self._c_sp_rpm, self._c_rpm_l, self._c_rpm_r, self._c_pwm_l, self._c_pwm_r):
            c.setDownsampling(auto=True, method="subsample")
            c.setClipToView(True)

        return self._pw_main

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

        # Restore saved angle PID gains (default = last known good values)
        kp = float(self._settings.value("gains/angle_kp", 0.241))
        ki = float(self._settings.value("gains/angle_ki", 0.0))
        kd = float(self._settings.value("gains/angle_kd", 0.00041))
        self._angle_panel.set_gains(kp, ki, kd)

        # Restore saved velocity PID gains
        vkp = float(self._settings.value("gains/vel_kp", 0.0))
        vki = float(self._settings.value("gains/vel_ki", 0.0))
        vkd = float(self._settings.value("gains/vel_kd", 0.0))
        if vkp or vki or vkd:
            self._velocity_panel.set_gains(vkp, vki, vkd)

        # Restore saved position PID gains
        pkp = float(self._settings.value("gains/pos_kp", 0.5))
        pki = float(self._settings.value("gains/pos_ki", 0.0))
        pkd = float(self._settings.value("gains/pos_kd", 0.0))
        self._pos_panel.set_gains(pkp, pki, pkd)

    def _save_layout(self):
        self._settings.setValue("geometry",       self.saveGeometry())
        self._settings.setValue("splitter_main",  self._main_splitter.saveState())
        self._settings.setValue("time_window_s",  self._win_spin.value())
        self._settings.setValue("last_port",      self._port_combo.currentData() or "")
        self._settings.setValue("last_baud",      self._baud_combo.currentText())
        kp, ki, kd = self._angle_panel.gains()
        self._settings.setValue("gains/angle_kp", kp)
        self._settings.setValue("gains/angle_ki", ki)
        self._settings.setValue("gains/angle_kd", kd)
        vkp, vki, vkd = self._velocity_panel.gains()
        self._settings.setValue("gains/vel_kp", vkp)
        self._settings.setValue("gains/vel_ki", vki)
        self._settings.setValue("gains/vel_kd", vkd)
        pkp, pki, pkd = self._pos_panel.gains()
        self._settings.setValue("gains/pos_kp", pkp)
        self._settings.setValue("gains/pos_ki", pki)
        self._settings.setValue("gains/pos_kd", pkd)

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
        self._reader.calib_sample.connect(self._motor_calib_panel.on_calib_packet)
        self._reader.pos_sample.connect(self._on_pos)
        self._reader.power_sample.connect(self._power_panel.on_power_sample)
        self._reader.rx_bytes.connect(self._on_rx)
        self._reader.error.connect(self._on_err)
        self._reader.start()
        self._state.connected      = True
        self._state.send_gains     = lambda kp, ki, kd: self._send_gains(0, kp, ki, kd)
        self._state.send_vel_gains = lambda kp, ki, kd: self._send_gains(1, kp, ki, kd)
        self._connect_btn.setText("Déconnecter")
        self._stream_btn.setEnabled(True)
        self._port_combo.setEnabled(False)
        self._baud_combo.setEnabled(False)
        self.statusBar().showMessage(f"Connecté sur {port}")
        self._stream_btn.setChecked(True)
        self._stream_btn.setText("⏹ Stop")
        self._send_stream(True)
        QTimer.singleShot(200, self._send_saved_gains)
        QTimer.singleShot(300, self._send_saved_vel_gains)

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
        self._state.connected      = False
        self._state.send_gains     = None
        self._state.send_vel_gains = None
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

    def _on_sim_apply_angle_gains(self, kp: float, ki: float, kd: float):
        """Apply gains selected in the angle simulation heatmap to the robot and the left panel."""
        self._angle_panel.set_gains(kp, ki, kd)
        self._send_gains(0, kp, ki, kd)

    def _on_sim_apply_vel_gains(self, kp: float, ki: float, kd: float):
        """Apply gains selected in the velocity simulation heatmap to the robot and the left panel."""
        self._velocity_panel.set_gains(kp, ki, kd)
        self._send_gains(1, kp, ki, kd)

    def _send_motor_calib(self, enable: bool):
        if not self._reader:
            return
        payload = struct.pack("<B", 1 if enable else 0)
        frame   = _build_frame(_TYPE_MOTOR_CALIB, payload, self._tx_seq)
        self._reader.write(frame)
        self._tx_seq = (self._tx_seq + 1) & 0xFF

    def _send_sp(self, rpm: int):
        if not self._reader:
            return
        self._reader.write(_sp_frame(rpm, self._tx_seq))
        self._tx_seq = (self._tx_seq + 1) & 0xFF

    def _send_drive(self, drive_norm: float):
        if not self._reader:
            return
        self._reader.write(_drive_frame(drive_norm, self._tx_seq))
        self._tx_seq = (self._tx_seq + 1) & 0xFF

    def _send_angle_sp(self, offset_deg: float):
        if not self._reader:
            return
        self._reader.write(_angle_sp_frame(offset_deg, self._tx_seq))
        self._tx_seq = (self._tx_seq + 1) & 0xFF

    def _send_angle_direct(self, target_deg: float):
        if not self._reader:
            return
        self._reader.write(_angle_direct_frame(target_deg, self._tx_seq))
        self._tx_seq = (self._tx_seq + 1) & 0xFF

    def _on_snapshot_request(self, duration_s: float):
        s = self._state
        n = len(s.t)
        if n < 2:
            return
        t_arr = np.fromiter(s.t,     float, n)
        p_arr = np.fromiter(s.pitch, float, n)
        t_now = t_arr[-1]
        mask  = t_arr >= (t_now - duration_s)
        t_win = t_arr[mask] - t_arr[mask][0]   # normalize to start at 0
        p_win = p_arr[mask]
        self._sim_panel.import_snapshot(t_win, p_win)

    def _send_saved_gains(self):
        kp, ki, kd = self._angle_panel.gains()
        self._send_gains(0, kp, ki, kd)

    def _send_saved_vel_gains(self):
        kp, ki, kd = self._velocity_panel.gains()
        self._send_gains(1, kp, ki, kd)

    def _on_vel_gains_changed(self, kp: float, ki: float, kd: float):
        self._state.vel_kp = kp
        self._state.vel_ki = ki
        self._state.vel_kd = kd
        self._send_gains(1, kp, ki, kd)

    def _on_pos(self, pos_cm: float, sp_cm: float, vel_sp_rpm: float,
                ctrl_mode: int, traj_mode: int):
        self._pos_panel.on_pos_sample(pos_cm, sp_cm, vel_sp_rpm, ctrl_mode, traj_mode)
        self._motion_panel.sync_from_firmware(ctrl_mode)

    def _send_pos_sp(self, sp_cm: float):
        if not self._reader:
            return
        self._reader.write(_pos_sp_frame(sp_cm, self._tx_seq))
        self._tx_seq = (self._tx_seq + 1) & 0xFF

    def _send_pos_traj(self, mode: int, amplitude_cm: float, period_s: float):
        if not self._reader:
            return
        self._reader.write(_pos_traj_frame(mode, amplitude_cm, period_s, self._tx_seq))
        self._tx_seq = (self._tx_seq + 1) & 0xFF

    def _send_spin(self, enable: bool, interval_s: float, yaw_force: float):
        if not self._reader:
            return
        self._reader.write(_spin_frame(enable, interval_s, yaw_force, self._tx_seq))
        self._tx_seq = (self._tx_seq + 1) & 0xFF

    # ── Data slots ────────────────────────────────────────────────────────────

    def _on_plan_ready(
        self, tests: list, out_dir: str, delay_s: float, hold_s: float
    ) -> None:
        self._runner_panel.load_plan(tests, out_dir, delay_s, hold_s)
        self._right_tabs.setCurrentIndex(self._tab_run_idx)

    def _on_sweep_complete(self, out_dir: str) -> None:
        if out_dir:
            self._results_panel._load_dir(out_dir)
        self._right_tabs.setCurrentIndex(self._tab_res_idx)

    def _on_imu(self, pitch: float, drive_pct: float, pitch_rate: float):
        now = _time.monotonic()
        self._runner_panel.feed_imu(pitch, drive_pct / 100.0, now)
        self._kident_panel.feed(pitch, drive_pct / 100.0, pitch_rate)
        self._ident_k_panel.feed_imu(pitch, drive_pct, pitch_rate)
        self._ident_td_panel.feed_imu(pitch, drive_pct, pitch_rate)
        self._ident_a_panel.feed_imu(pitch, drive_pct, pitch_rate)
        dt  = (now - self._t_prev) if self._t_prev is not None else 0.005
        self._t_prev = now

        s = self._state
        s.t.append(now)
        s.pitch.append(pitch)
        s.pitch_rate.append(pitch_rate)
        s.drive.append(drive_pct / 100.0)

        kp, ki, kd = self._state.kp, self._state.ki, self._state.kd
        target_pitch = self._state.target_pitch
        error = target_pitch - pitch

        # Integral avec anti-windup ±0.5 (cohérent avec CBC_Init integral limits)
        self._i_accum = max(-0.5, min(0.5, self._i_accum + error * dt))

        # d(error)/dt = -d(pitch)/dt ≈ -pitch_rate
        s.pid_p.append(kp * error)
        s.pid_i.append(ki * self._i_accum)
        s.pid_d.append(kd * (-pitch_rate))

        self._pkt_cnt += 1
        self._pkt_label.setText(f"PKT: {self._pkt_cnt}")
        self._chain_panel.update_angle(pitch, drive_pct, target_pitch)

    def _on_pid(self, pv_l: int, pv_r: int, pwm_l: float, pwm_r: float,
                sp_rpm: int, target_pitch_deg: float):
        self._ident_k_panel.feed_motor(pv_l, pv_r, pwm_l, pwm_r, sp_rpm)
        self._ident_td_panel.feed_motor(pv_l, pv_r, pwm_l, pwm_r, sp_rpm)
        now = _time.monotonic()
        s = self._state
        s.t_motor.append(now)
        s.sp_rpm_ts.append(sp_rpm / 85.0)    # normalisé [-1..1]  (max réel = 85 RPM)
        s.rpm_l_ts.append(pv_l   / 85.0)
        s.rpm_r_ts.append(pv_r   / 85.0)
        s.pwm_l_ts.append(pwm_l)
        s.pwm_r_ts.append(pwm_r)
        s.rpm_l = pv_l
        s.rpm_r = pv_r
        s.pwm_l = pwm_l
        s.pwm_r = pwm_r
        s.target_pitch = target_pitch_deg
        s.vel_avg = (pv_l + pv_r) / 2.0
        self._chain_panel.update_velocity(sp_rpm, pv_l, pv_r, pwm_l, pwm_r)

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
        drv   = np.fromiter(s.drive, float, min(n, len(s.drive)))
        t_now = t[-1]
        mask  = t >= (t_now - win_s)
        def _set(curve, data, row_key):
            r = self._disp_panel.row(row_key)
            if r.visible() and len(data) > 0:
                curve.setData(x=tw, y=data * r.factor())
            else:
                curve.setData([], [])

        tw = t[mask]
        _set(self._c_pitch, p[mask],                      "pitch")
        _set(self._c_pid_p, pp[mask],                     "pid_p")
        _set(self._c_pid_i, pi[mask],                     "pid_i")
        _set(self._c_pid_d, pd[mask],                     "pid_d")
        _set(self._c_drive, drv[mask] if len(drv)==n else np.array([]), "drive")
        self._pw_main.setXRange(t_now - win_s, t_now, padding=0)

        # ── Courbes moteur ────────────────────────────────────────────────────
        nm = len(s.t_motor)
        if nm > 0:
            tm  = np.fromiter(s.t_motor,   float, nm)
            sp  = np.fromiter(s.sp_rpm_ts, float, min(nm, len(s.sp_rpm_ts)))
            rl  = np.fromiter(s.rpm_l_ts,  float, min(nm, len(s.rpm_l_ts)))
            rr  = np.fromiter(s.rpm_r_ts,  float, min(nm, len(s.rpm_r_ts)))
            pl  = np.fromiter(s.pwm_l_ts,  float, min(nm, len(s.pwm_l_ts)))
            pr  = np.fromiter(s.pwm_r_ts,  float, min(nm, len(s.pwm_r_ts)))
            mk  = tm >= (tm[-1] - win_s)
            tmw = tm[mk]

            def _setm(curve, data, row_key):
                r = self._disp_panel.row(row_key)
                if r.visible() and len(data) == nm:
                    curve.setData(x=tmw, y=data[mk] * r.factor())
                else:
                    curve.setData([], [])

            _setm(self._c_sp_rpm, sp, "sp_rpm")
            _setm(self._c_rpm_l,  rl, "rpm_l")
            _setm(self._c_rpm_r,  rr, "rpm_r")
            _setm(self._c_pwm_l,  pl, "pwm_l")
            _setm(self._c_pwm_r,  pr, "pwm_r")

    def _clear(self):
        s = self._state
        for d in (s.t, s.pitch, s.pitch_rate, s.drive, s.pid_p, s.pid_i, s.pid_d,
                  s.t_motor, s.sp_rpm_ts, s.rpm_l_ts, s.rpm_r_ts, s.pwm_l_ts, s.pwm_r_ts):
            d.clear()
        for c in (self._c_pitch, self._c_pid_p, self._c_pid_i, self._c_pid_d, self._c_drive,
                  self._c_sp_rpm, self._c_rpm_l, self._c_rpm_r, self._c_pwm_l, self._c_pwm_r):
            c.setData([], [])
        self._power_panel.clear()
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
