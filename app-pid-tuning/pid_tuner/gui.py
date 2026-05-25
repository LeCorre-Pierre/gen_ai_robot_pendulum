"""
PySide6 GUI for the robot PID tuner.

Left pane  : live pyqtgraph plots (RPM, error, PWM).
Right pane : connection toolbar + PID gains + motor control +
             stream control + Nelder-Mead optimiser + MCP server toggle.
"""
from __future__ import annotations

import json
import os
import pathlib
import queue
import struct
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable

# PySide6 must be imported before numpy/pyqtgraph to avoid Qt DLL conflicts
# (numpy loads OpenBLAS/MKL DLLs that can interfere with Qt6Core loading).
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox, QSplitter,
    QTextEdit, QVBoxLayout, QWidget,
)

import numpy as np
import pyqtgraph as pg
import serial.tools.list_ports

from . import protocol as P
from .optimizer import optimize_pid
from .robot_client import RobotClient

# ── plot config ───────────────────────────────────────────────────────────────
pg.setConfigOptions(antialias=True, background="#1e1e1e", foreground="#cccccc")
_PLOT_POINTS   = 3000   # max data points kept per signal
_POLL_MS       = 40     # telemetry poll interval (~25 Hz UI refresh)
_SETTINGS_FILE = pathlib.Path.home() / ".robot-pid-tuner.json"
_MAX_RPM       = 85     # motor max at 12 V

_TYPE_NAMES = {
    P.TYPE_TELEMETRY_PID:   "TELEMETRY",
    P.TYPE_CMD_SET_GAINS:   "SET_GAINS",
    P.TYPE_CMD_SET_SP:      "SET_SP",
    P.TYPE_CMD_STREAM_CTRL: "STREAM_CTRL",
    P.TYPE_CMD_MOTOR_CTRL:  "MOTOR_CTRL",
    P.TYPE_ACK:             "ACK",
}
_MOTOR_NAMES  = {0: "LEFT", 1: "RIGHT", 2: "BOTH"}
_ACTION_NAMES = {P.ACTION_COAST: "COAST", P.ACTION_BRAKE: "BRAKE",
                 P.ACTION_ENABLE: "ENABLE"}


def _load_last_port() -> str:
    try:
        return json.loads(_SETTINGS_FILE.read_text()).get("port", "COM4")
    except Exception:
        return "COM4"


def _save_last_port(port: str) -> None:
    try:
        _SETTINGS_FILE.write_text(json.dumps({"port": port}))
    except Exception:
        pass


def _fmt_pkt(direction: str, pkt: P.Packet) -> str:
    """Human-readable one-line description of a VCP packet."""
    arrow = "→" if direction == "TX" else "←"
    name  = _TYPE_NAMES.get(pkt.type, f"0x{pkt.type:02X}")

    try:
        if pkt.type == P.TYPE_TELEMETRY_PID:
            tel = P.parse_telemetry(pkt)
            if tel:
                detail = (f"sp={tel.sp_rpm:+d} "
                          f"pvL={tel.pv_l_rpm:+d} pvR={tel.pv_r_rpm:+d} "
                          f"errL={tel.err_l:+d} errR={tel.err_r:+d} "
                          f"pwmL={tel.pwm_l_pct*100:.0f}% pwmR={tel.pwm_r_pct*100:.0f}%")
            else:
                detail = pkt.payload.hex(" ")
        elif pkt.type == P.TYPE_ACK and len(pkt.payload) >= 2:
            cmd = _TYPE_NAMES.get(pkt.payload[0], f"0x{pkt.payload[0]:02X}")
            detail = f"{cmd} {'OK' if pkt.payload[1] == 0 else f'ERR={pkt.payload[1]}'}"
        elif pkt.type == P.TYPE_CMD_SET_GAINS and len(pkt.payload) >= 13:
            mid, kp, ki, kd = struct.unpack_from("<Bfff", pkt.payload)
            detail = (f"motor={_MOTOR_NAMES.get(mid,'?')} "
                      f"kp={kp:.5f} ki={ki:.5f} kd={kd:.5f}")
        elif pkt.type == P.TYPE_CMD_SET_SP and len(pkt.payload) >= 2:
            sp, = struct.unpack_from("<h", pkt.payload)
            detail = f"sp={sp:+d} rpm"
        elif pkt.type == P.TYPE_CMD_STREAM_CTRL and len(pkt.payload) >= 3:
            en, rate = struct.unpack_from("<BH", pkt.payload)
            detail = f"enable={en} rate={rate} Hz"
        elif pkt.type == P.TYPE_CMD_MOTOR_CTRL and len(pkt.payload) >= 1:
            detail = _ACTION_NAMES.get(pkt.payload[0], f"0x{pkt.payload[0]:02X}")
        else:
            detail = pkt.payload.hex(" ") if pkt.payload else ""
    except Exception:
        detail = pkt.payload.hex(" ") if pkt.payload else ""

    return f"{arrow} {name:<12} {detail}"


# ── logging client ────────────────────────────────────────────────────────────

class _LoggingClient(RobotClient):
    """RobotClient subclass that fires callbacks for every TX/RX packet."""

    def __init__(self, port: str, baud: int = 115200,
                 tx_cb=None, rx_cb=None) -> None:
        super().__init__(port, baud)
        self._tx_cb = tx_cb
        self._rx_cb = rx_cb

    def _send_ack(self, pkt: P.Packet) -> bool:
        if self._tx_cb:
            self._tx_cb(pkt)
        return super()._send_ack(pkt)

    def _dispatch(self, pkt: P.Packet) -> None:
        if self._rx_cb:
            self._rx_cb(pkt)
        super()._dispatch(pkt)


# ── background workers ────────────────────────────────────────────────────────

class _OptimizeWorker(QThread):
    """Runs optimize_pid() in a QThread; emits Qt signals for progress/result."""

    progress = Signal(int, float, float, float, object)  # iter, kp, ki, cost, metrics
    finished = Signal(float, float, object)               # kp_opt, ki_opt, metrics
    error    = Signal(str)

    def __init__(self, client: RobotClient, motor: str,
                 target_rpm: int, max_iter: int) -> None:
        super().__init__()
        self._client     = client
        self._motor      = motor
        self._target_rpm = target_rpm
        self._max_iter   = max_iter

    def run(self) -> None:
        try:
            kp, ki, _, m = optimize_pid(
                self._client, self._motor, self._target_rpm,
                max_iter=self._max_iter,
                progress_cb=lambda i, kp, ki, c, m:
                    self.progress.emit(i, kp, ki, c, m),
            )
            self.finished.emit(kp, ki, m)
        except Exception as exc:
            self.error.emit(str(exc))


# ── main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self, port: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Robot PID Tuner")
        self.resize(1280, 800)

        self._client: RobotClient | None = None
        self._opt_worker: _OptimizeWorker | None = None
        self._mcp_proc: subprocess.Popen | None = None
        self._mcp_poll_timer: QTimer | None = None

        # Cross-thread UI update queue (background threads post callables here;
        # the poll timer drains it on the main thread).
        self._ui_q: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()

        # Ring buffers for plot data
        N = _PLOT_POINTS
        self._t     : deque[float] = deque(maxlen=N)
        self._sp    : deque[float] = deque(maxlen=N)
        self._pv_l  : deque[float] = deque(maxlen=N)
        self._pv_r  : deque[float] = deque(maxlen=N)
        self._err_l : deque[float] = deque(maxlen=N)
        self._err_r : deque[float] = deque(maxlen=N)
        self._pwm_l : deque[float] = deque(maxlen=N)
        self._pwm_r : deque[float] = deque(maxlen=N)
        self._t0             = 0.0
        self._pkt_count      = 0
        self._last_pkt_sec   = time.monotonic()

        self._build_ui()
        self._refresh_ports()
        if port:
            idx = self._port_combo.findText(port)
            if idx >= 0:
                self._port_combo.setCurrentIndex(idx)
        self._set_connected(False)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_MS)
        self._poll_timer.timeout.connect(self._on_poll)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        tb = self.addToolBar("Connection")
        tb.setMovable(False)

        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(110)

        self._refresh_btn = QPushButton("↺")
        self._refresh_btn.setFixedWidth(28)
        self._refresh_btn.setToolTip("Refresh port list")
        self._refresh_btn.clicked.connect(self._refresh_ports)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setFixedWidth(90)
        self._connect_btn.clicked.connect(self._on_connect_toggle)

        self._status_lbl = QLabel("Disconnected")
        self._status_lbl.setStyleSheet("color:#888;padding:0 10px;")

        self._rate_lbl = QLabel("")
        self._rate_lbl.setStyleSheet("color:#aaa;padding:0 6px;")

        for w in (QLabel("Port:"), self._port_combo, self._refresh_btn,
                  self._connect_btn, self._status_lbl, self._rate_lbl):
            tb.addWidget(w)

        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)
        splitter.addWidget(self._build_plots())
        splitter.addWidget(self._build_controls())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([880, 380])

    def _build_plots(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(4)

        def _pw(title: str) -> pg.PlotWidget:
            p = pg.PlotWidget(title=title)
            p.showGrid(x=True, y=True, alpha=0.3)
            p.addLegend(offset=(10, 10))
            return p

        self._rpm_plot = _pw("Velocity (RPM)")
        self._rpm_plot.setLabel("left", "RPM")
        self._c_sp  = self._rpm_plot.plot([], [], pen=pg.mkPen("#ffffff", width=1), name="SP")
        self._c_pvl = self._rpm_plot.plot([], [], pen=pg.mkPen("#4fc3f7", width=1), name="PV Left")
        self._c_pvr = self._rpm_plot.plot([], [], pen=pg.mkPen("#81c784", width=1), name="PV Right")

        self._err_plot = _pw("Error (RPM)")
        self._err_plot.setLabel("left", "Error RPM")
        self._c_errl = self._err_plot.plot([], [], pen=pg.mkPen("#ef5350", width=1), name="Err Left")
        self._c_errr = self._err_plot.plot([], [], pen=pg.mkPen("#ffa726", width=1), name="Err Right")

        self._pwm_plot = _pw("PWM (%)")
        self._pwm_plot.setLabel("left", "PWM %")
        self._pwm_plot.setYRange(-105, 105)
        self._c_pwml = self._pwm_plot.plot([], [], pen=pg.mkPen("#ce93d8", width=1), name="PWM Left")
        self._c_pwmr = self._pwm_plot.plot([], [], pen=pg.mkPen("#80cbc4", width=1), name="PWM Right")

        vbox.addWidget(self._rpm_plot, 2)
        vbox.addWidget(self._err_plot, 1)
        vbox.addWidget(self._pwm_plot, 1)
        return w

    def _build_controls(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(8)

        vbox.addWidget(self._build_gains_group())
        vbox.addWidget(self._build_motor_group())
        vbox.addWidget(self._build_stream_group())
        vbox.addWidget(self._build_optimize_group())
        vbox.addWidget(self._build_mcp_group())
        vbox.addWidget(self._build_frame_log_group())
        vbox.addStretch()

        scroll.setWidget(container)
        return scroll

    # ── control panels ────────────────────────────────────────────────────────

    def _build_gains_group(self) -> QGroupBox:
        g = QGroupBox("PID Gains")
        f = QFormLayout(g)
        f.setContentsMargins(8, 8, 8, 8)

        self._motor_combo = QComboBox()
        for label, val in (("Both", "both"), ("Left", "left"), ("Right", "right")):
            self._motor_combo.addItem(label, userData=val)
        f.addRow("Motor:", self._motor_combo)

        def _ds(v: float, step: float = 0.001) -> QDoubleSpinBox:
            s = QDoubleSpinBox()
            s.setDecimals(5); s.setRange(0, 1); s.setSingleStep(step); s.setValue(v)
            return s

        self._kp_spin = _ds(0.004)
        self._ki_spin = _ds(0.002)
        self._kd_spin = _ds(0.0, step=0.0001)
        f.addRow("Kp:", self._kp_spin)
        f.addRow("Ki:", self._ki_spin)
        f.addRow("Kd:", self._kd_spin)

        self._apply_btn = QPushButton("Apply Gains")
        self._apply_btn.clicked.connect(self._on_apply_gains)
        f.addRow(self._apply_btn)

        self._gains_lbl = QLabel("")
        self._gains_lbl.setStyleSheet("color:#888;font-size:10px;")
        f.addRow(self._gains_lbl)
        return g

    def _build_motor_group(self) -> QGroupBox:
        g = QGroupBox("Motor / Setpoint")
        vbox = QVBoxLayout(g)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(6)

        # Slider 0–100 %
        slider_row = QHBoxLayout()
        self._sp_slider = QSlider(Qt.Orientation.Horizontal)
        self._sp_slider.setRange(0, 100)
        self._sp_slider.setValue(0)
        self._sp_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._sp_slider.setTickInterval(25)
        self._sp_pct_lbl = QLabel("0 %")
        self._sp_pct_lbl.setFixedWidth(36)
        slider_row.addWidget(QLabel("0"))
        slider_row.addWidget(self._sp_slider)
        slider_row.addWidget(QLabel("100"))
        slider_row.addWidget(self._sp_pct_lbl)
        vbox.addLayout(slider_row)

        # RPM free-entry + Send
        rpm_row = QHBoxLayout()
        rpm_row.addWidget(QLabel("Setpoint:"))
        self._sp_line = QLineEdit("0")
        self._sp_line.setMaximumWidth(60)
        self._sp_line.setPlaceholderText("RPM")
        self._sp_btn = QPushButton("Send")
        rpm_row.addWidget(self._sp_line)
        rpm_row.addWidget(QLabel("RPM"))
        rpm_row.addStretch()
        rpm_row.addWidget(self._sp_btn)
        vbox.addLayout(rpm_row)

        self._sp_slider.valueChanged.connect(self._on_sp_slider_changed)
        self._sp_line.returnPressed.connect(self._on_send_sp)
        self._sp_btn.clicked.connect(self._on_send_sp)

        btn_row = QHBoxLayout()
        self._coast_btn  = QPushButton("COAST")
        self._brake_btn  = QPushButton("BRAKE")
        self._enable_btn = QPushButton("ENABLE")
        self._coast_btn.setStyleSheet("background:#37474f;color:white;font-weight:bold;")
        self._brake_btn.setStyleSheet("background:#b71c1c;color:white;font-weight:bold;")
        self._enable_btn.setStyleSheet("background:#1b5e20;color:white;font-weight:bold;")
        self._coast_btn.clicked.connect(self._on_coast)
        self._brake_btn.clicked.connect(self._on_brake)
        self._enable_btn.clicked.connect(self._on_enable)
        for b in (self._coast_btn, self._brake_btn, self._enable_btn):
            btn_row.addWidget(b)
        vbox.addLayout(btn_row)
        return g

    def _build_stream_group(self) -> QGroupBox:
        g = QGroupBox("Telemetry Stream")
        row = QHBoxLayout(g)
        row.setContentsMargins(8, 8, 8, 8)

        self._rate_combo = QComboBox()
        for r in (10, 20, 50, 100):
            self._rate_combo.addItem(f"{r} Hz", userData=r)
        self._rate_combo.setCurrentIndex(2)  # 50 Hz

        self._stream_btn = QPushButton("▶ Start")
        self._stream_btn.setCheckable(True)
        self._stream_btn.clicked.connect(self._on_stream_toggle)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self._clear_plots)

        row.addWidget(QLabel("Rate:")); row.addWidget(self._rate_combo)
        row.addWidget(self._stream_btn); row.addWidget(self._clear_btn)
        return g

    def _build_optimize_group(self) -> QGroupBox:
        g = QGroupBox("Optimize — Nelder-Mead")
        vbox = QVBoxLayout(g)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(4)

        f = QFormLayout()
        self._opt_motor_combo = QComboBox()
        for label, val in (("Both", "both"), ("Left", "left"), ("Right", "right")):
            self._opt_motor_combo.addItem(label, userData=val)
        self._opt_target_spin = QSpinBox()
        self._opt_target_spin.setRange(10, 300); self._opt_target_spin.setValue(50); self._opt_target_spin.setSuffix(" RPM")
        self._opt_iter_spin = QSpinBox()
        self._opt_iter_spin.setRange(5, 100); self._opt_iter_spin.setValue(30)
        f.addRow("Motor:", self._opt_motor_combo)
        f.addRow("Target:", self._opt_target_spin)
        f.addRow("Max iter:", self._opt_iter_spin)
        vbox.addLayout(f)

        self._opt_run_btn = QPushButton("▶ Run Optimization")
        self._opt_run_btn.setStyleSheet(
            "background:#1565c0;color:white;font-weight:bold;padding:4px;")
        self._opt_run_btn.clicked.connect(self._on_opt_run)
        vbox.addWidget(self._opt_run_btn)

        self._opt_bar = QProgressBar()
        self._opt_bar.setRange(0, 30); self._opt_bar.setValue(0)
        vbox.addWidget(self._opt_bar)

        self._opt_log = QTextEdit()
        self._opt_log.setReadOnly(True)
        self._opt_log.setMaximumHeight(100)
        self._opt_log.setFont(QFont("Consolas", 8))
        self._opt_log.setStyleSheet("background:#111;color:#ccc;")
        vbox.addWidget(self._opt_log)

        self._opt_result = QLabel("")
        self._opt_result.setWordWrap(True)
        self._opt_result.setFont(QFont("Consolas", 9))
        self._opt_result.setStyleSheet("color:#a5d6a7;")
        vbox.addWidget(self._opt_result)
        return g

    def _build_mcp_group(self) -> QGroupBox:
        g = QGroupBox("MCP Server — Claude integration")
        vbox = QVBoxLayout(g)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(4)

        info = QLabel(
            "Démarre un serveur MCP dans un nouveau terminal.\n"
            "La connexion série de la GUI est libérée pendant ce temps."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#888;font-size:10px;")
        vbox.addWidget(info)

        self._mcp_btn = QPushButton("● Start MCP Server")
        self._mcp_btn.setCheckable(True)
        self._mcp_btn.clicked.connect(self._on_mcp_toggle)
        vbox.addWidget(self._mcp_btn)

        self._mcp_config_box = QTextEdit()
        self._mcp_config_box.setReadOnly(True)
        self._mcp_config_box.setMaximumHeight(110)
        self._mcp_config_box.setFont(QFont("Consolas", 8))
        self._mcp_config_box.setStyleSheet("background:#111;color:#aaa;")
        self._mcp_config_box.hide()
        vbox.addWidget(self._mcp_config_box)

        self._mcp_copy_btn = QPushButton("Copy config to clipboard")
        self._mcp_copy_btn.clicked.connect(self._on_mcp_copy)
        self._mcp_copy_btn.hide()
        vbox.addWidget(self._mcp_copy_btn)

        return g

    # ── controls enable/disable ───────────────────────────────────────────────

    def _set_connected(self, connected: bool) -> None:
        self._connect_btn.setText("Disconnect" if connected else "Connect")
        if connected:
            self._status_lbl.setText("Connected")
            self._status_lbl.setStyleSheet("color:#4caf50;padding:0 10px;")
        else:
            self._status_lbl.setText("Disconnected")
            self._status_lbl.setStyleSheet("color:#888;padding:0 10px;")
            self._rate_lbl.setText("")

        for w in (self._apply_btn, self._sp_btn, self._coast_btn,
                  self._brake_btn, self._enable_btn,
                  self._stream_btn, self._opt_run_btn):
            w.setEnabled(connected)

        self._mcp_btn.setEnabled(bool(self._port_combo.currentText()))

    # ── connection ────────────────────────────────────────────────────────────

    def _refresh_ports(self) -> None:
        cur = self._port_combo.currentText() or _load_last_port()
        self._port_combo.clear()
        ports = [p.device for p in serial.tools.list_ports.comports()] or ["COM4"]
        for p in ports:
            self._port_combo.addItem(p)
        # Prefer: current selection → last saved port → COM4 → first available
        for candidate in (cur, _load_last_port(), "COM4"):
            idx = self._port_combo.findText(candidate)
            if idx >= 0:
                self._port_combo.setCurrentIndex(idx)
                break

    def _on_connect_toggle(self) -> None:
        if self._client and self._client.is_connected():
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        port = self._port_combo.currentText()
        if not port:
            return
        try:
            self._client = _LoggingClient(
                port,
                tx_cb=self._on_tx_frame,
                rx_cb=self._on_rx_frame,
            )
            self._client.connect()
            self._t0 = time.monotonic()
            self._poll_timer.start()
            self._set_connected(True)
            _save_last_port(port)
        except Exception as exc:
            self._status_lbl.setText(f"Error: {exc}")
            self._status_lbl.setStyleSheet("color:#ef5350;padding:0 10px;")

    def _disconnect(self) -> None:
        self._poll_timer.stop()
        if self._client:
            # Close the port immediately — no ACK waits so disconnect is instant
            self._client.disconnect()
            self._client = None
        self._set_connected(False)
        self._stream_btn.setChecked(False)
        self._stream_btn.setText("▶ Start")

    # ── poll timer (main thread) ──────────────────────────────────────────────

    def _on_poll(self) -> None:
        # 1) drain cross-thread UI updates
        while not self._ui_q.empty():
            try:
                fn = self._ui_q.get_nowait()
                fn()
            except Exception:
                pass

        # 2) drain telemetry queue → update plots
        if not self._client or not self._client.is_connected():
            return

        count = 0
        while True:
            tel = self._client.get_telemetry(timeout=0.0)
            if tel is None:
                break
            t = time.monotonic() - self._t0
            self._t.append(t)
            self._sp.append(float(tel.sp_rpm))
            self._pv_l.append(float(tel.pv_l_rpm))
            self._pv_r.append(float(tel.pv_r_rpm))
            self._err_l.append(float(tel.err_l))
            self._err_r.append(float(tel.err_r))
            self._pwm_l.append(tel.pwm_l_pct * 100.0)
            self._pwm_r.append(tel.pwm_r_pct * 100.0)
            count += 1

        if count:
            ta = np.array(self._t)
            self._c_sp.setData(ta, np.array(self._sp))
            self._c_pvl.setData(ta, np.array(self._pv_l))
            self._c_pvr.setData(ta, np.array(self._pv_r))
            self._c_errl.setData(ta, np.array(self._err_l))
            self._c_errr.setData(ta, np.array(self._err_r))
            self._c_pwml.setData(ta, np.array(self._pwm_l))
            self._c_pwmr.setData(ta, np.array(self._pwm_r))

            self._pkt_count += count
            now = time.monotonic()
            if now - self._last_pkt_sec >= 1.0:
                self._rate_lbl.setText(f"{self._pkt_count} pkt/s")
                self._pkt_count = 0
                self._last_pkt_sec = now

    def _clear_plots(self) -> None:
        for d in (self._t, self._sp, self._pv_l, self._pv_r,
                  self._err_l, self._err_r, self._pwm_l, self._pwm_r):
            d.clear()
        for c in (self._c_sp, self._c_pvl, self._c_pvr,
                  self._c_errl, self._c_errr, self._c_pwml, self._c_pwmr):
            c.setData([], [])

    # ── background helper (avoids blocking the Qt event loop for ACK waits) ──

    def _bg(self, fn) -> None:
        threading.Thread(target=fn, daemon=True).start()

    # ── gains ─────────────────────────────────────────────────────────────────

    def _on_apply_gains(self) -> None:
        if not self._client:
            return
        motor = self._motor_combo.currentData()
        kp, ki, kd = self._kp_spin.value(), self._ki_spin.value(), self._kd_spin.value()
        lbl = self._gains_lbl

        def _do() -> None:
            ok = self._client.set_gains(motor, kp, ki, kd)
            msg = "✓ Applied" if ok else "✗ No ACK"
            self._ui_q.put(lambda m=msg: lbl.setText(m))

        self._bg(_do)

    # ── motor / setpoint ──────────────────────────────────────────────────────

    def _on_sp_slider_changed(self, pct: int) -> None:
        rpm = round(pct / 100.0 * _MAX_RPM)
        self._sp_pct_lbl.setText(f"{pct} %")
        self._sp_line.setText(str(rpm))

    def _on_send_sp(self) -> None:
        if not self._client:
            return
        try:
            rpm = int(self._sp_line.text())
        except ValueError:
            return
        # Sync slider (clamp to its range)
        pct = round(rpm / _MAX_RPM * 100)
        self._sp_slider.blockSignals(True)
        self._sp_slider.setValue(max(0, min(100, pct)))
        self._sp_slider.blockSignals(False)
        client = self._client
        self._bg(lambda r=rpm, c=client: c.set_setpoint(r))

    def _on_coast(self)  -> None:
        if self._client: self._bg(self._client.motor_coast)

    def _on_brake(self)  -> None:
        if self._client: self._bg(self._client.motor_brake)

    def _on_enable(self) -> None:
        if self._client: self._bg(self._client.motor_enable)

    # ── stream ────────────────────────────────────────────────────────────────

    def _on_stream_toggle(self, checked: bool) -> None:
        if not self._client:
            return
        rate = self._rate_combo.currentData()
        if checked:
            self._stream_btn.setText("■ Stop")
            self._bg(lambda: self._client.start_stream(rate))
        else:
            self._stream_btn.setText("▶ Start")
            self._bg(self._client.stop_stream)

    # ── optimization ──────────────────────────────────────────────────────────

    def _on_opt_run(self) -> None:
        if self._opt_worker and self._opt_worker.isRunning():
            return
        if not self._client:
            return

        motor    = self._opt_motor_combo.currentData()
        target   = self._opt_target_spin.value()
        max_iter = self._opt_iter_spin.value()

        self._opt_bar.setRange(0, max_iter)
        self._opt_bar.setValue(0)
        self._opt_log.clear()
        self._opt_result.setText("")
        self._opt_run_btn.setEnabled(False)
        self._opt_run_btn.setText("Running…")

        self._opt_worker = _OptimizeWorker(self._client, motor, target, max_iter)
        self._opt_worker.progress.connect(self._on_opt_progress)
        self._opt_worker.finished.connect(self._on_opt_done)
        self._opt_worker.error.connect(self._on_opt_error)
        # Stop the GUI poll so it doesn't drain the telemetry queue while the
        # optimizer's record_telemetry() is collecting step-response samples.
        self._poll_timer.stop()
        self._opt_worker.start()

    def _on_opt_progress(self, i: int, kp: float, ki: float,
                         cost: float, m) -> None:
        self._opt_bar.setValue(i)
        self._opt_log.append(
            f"#{i:3d}  Kp={kp:.5f}  Ki={ki:.5f}  cost={cost:.2f}  "
            f"OS={m.overshoot_pct:.1f}%  Ts={m.settling_time_s:.2f}s  "
            f"Err={m.steady_error:.1f}rpm"
        )

    def _on_opt_done(self, kp: float, ki: float, m) -> None:
        self._poll_timer.start()
        self._opt_run_btn.setEnabled(True)
        self._opt_run_btn.setText("▶ Run Optimization")
        # Push optimal gains into the gains panel
        self._kp_spin.setValue(kp)
        self._ki_spin.setValue(ki)
        self._opt_result.setStyleSheet("color:#a5d6a7;font-family:Consolas;font-size:9px;")
        self._opt_result.setText(
            f"Kp={kp:.5f}  Ki={ki:.5f}\n"
            f"OS={m.overshoot_pct:.1f}%  Ts={m.settling_time_s:.2f}s  "
            f"Err={m.steady_error:.1f}rpm\n\n"
            f"#define MTR_VEL_KP_DEFAULT  {kp:.4f}f\n"
            f"#define MTR_VEL_KI_DEFAULT  {ki:.4f}f"
        )

    def _on_opt_error(self, msg: str) -> None:
        self._poll_timer.start()
        self._opt_run_btn.setEnabled(True)
        self._opt_run_btn.setText("▶ Run Optimization")
        self._opt_result.setStyleSheet("color:#ef5350;font-size:9px;")
        self._opt_result.setText(f"Error: {msg}")

    # ── MCP server ────────────────────────────────────────────────────────────

    def _on_mcp_toggle(self, checked: bool) -> None:
        if checked:
            self._start_mcp()
        else:
            self._stop_mcp()

    def _start_mcp(self) -> None:
        port = self._port_combo.currentText()
        if not port:
            self._mcp_btn.setChecked(False)
            return

        # Release the serial port so the MCP subprocess can open it
        self._disconnect()

        main_py = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "main.py",
        )
        cmd = [sys.executable, main_py, "mcp", "--port", port]

        if sys.platform == "win32":
            self._mcp_proc = subprocess.Popen(
                cmd, creationflags=subprocess.CREATE_NEW_CONSOLE
            )
        else:
            # xterm fallback; user may need to adjust for their desktop env
            self._mcp_proc = subprocess.Popen(
                ["xterm", "-title", "MCP Server", "-e"] + cmd
            )

        self._mcp_btn.setText("■ Stop MCP Server")
        self._connect_btn.setEnabled(False)
        self._port_combo.setEnabled(False)
        self._mcp_btn.setStyleSheet("color:#ef5350;font-weight:bold;")

        # Show config JSON
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config = {
            "mcpServers": {
                "robot-pid-tuner": {
                    "command": "python",
                    "args": ["main.py", "mcp", "--port", port],
                    "cwd": app_dir,
                }
            }
        }
        self._mcp_config_box.setPlainText(
            "Ajouter dans Claude Code settings :\n"
            + json.dumps(config, indent=2)
        )
        self._mcp_config_box.show()
        self._mcp_copy_btn.show()

        # Poll every second to detect if the subprocess exited unexpectedly
        self._mcp_poll_timer = QTimer(self)
        self._mcp_poll_timer.setInterval(1000)
        self._mcp_poll_timer.timeout.connect(self._check_mcp_alive)
        self._mcp_poll_timer.start()

    def _stop_mcp(self) -> None:
        if self._mcp_poll_timer:
            self._mcp_poll_timer.stop()
            self._mcp_poll_timer = None
        if self._mcp_proc:
            try:
                self._mcp_proc.terminate()
                self._mcp_proc.wait(timeout=3)
            except Exception:
                pass
            self._mcp_proc = None
        self._mcp_btn.setChecked(False)
        self._mcp_btn.setText("● Start MCP Server")
        self._mcp_btn.setStyleSheet("")
        self._connect_btn.setEnabled(True)
        self._port_combo.setEnabled(True)
        self._mcp_config_box.hide()
        self._mcp_copy_btn.hide()

    def _check_mcp_alive(self) -> None:
        if self._mcp_proc and self._mcp_proc.poll() is not None:
            self._stop_mcp()

    def _on_mcp_copy(self) -> None:
        QApplication.clipboard().setText(self._mcp_config_box.toPlainText())
        self._mcp_copy_btn.setText("✓ Copied!")
        QTimer.singleShot(2000, lambda: self._mcp_copy_btn.setText("Copy config to clipboard"))

    # ── frame log ─────────────────────────────────────────────────────────────

    def _build_frame_log_group(self) -> QGroupBox:
        g = QGroupBox("Frame Log")
        vbox = QVBoxLayout(g)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(4)

        top_row = QHBoxLayout()
        self._log_tel_chk = QCheckBox("Log telemetry")
        self._log_tel_chk.setChecked(False)
        top_row.addWidget(self._log_tel_chk)
        top_row.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(55)
        clear_btn.clicked.connect(self._clear_frame_log)
        top_row.addWidget(clear_btn)
        vbox.addLayout(top_row)

        self._frame_log = QTextEdit()
        self._frame_log.setReadOnly(True)
        self._frame_log.setFont(QFont("Consolas", 8))
        self._frame_log.setStyleSheet("background:#111;color:#bbb;")
        self._frame_log.document().setMaximumBlockCount(200)
        self._frame_log.setMinimumHeight(120)
        vbox.addWidget(self._frame_log)
        return g

    def _clear_frame_log(self) -> None:
        self._frame_log.clear()

    def _on_tx_frame(self, pkt: P.Packet) -> None:
        """Called from background thread when a packet is sent."""
        line = _fmt_pkt("TX", pkt)
        self._ui_q.put(lambda l=line: self._log_frame(l))

    def _on_rx_frame(self, pkt: P.Packet) -> None:
        """Called from reader thread when a packet is received."""
        if pkt.type == P.TYPE_TELEMETRY_PID and not self._log_tel_chk.isChecked():
            return  # skip 50 Hz telemetry flood unless explicitly opted in
        line = _fmt_pkt("RX", pkt)
        self._ui_q.put(lambda l=line: self._log_frame(l))

    def _log_frame(self, line: str) -> None:
        """Append a frame line; runs on main thread via _ui_q."""
        self._frame_log.append(line)
        sb = self._frame_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── close ─────────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        self._stop_mcp()
        self._disconnect()
        super().closeEvent(event)


# ── entry point ───────────────────────────────────────────────────────────────

def run_gui(port: str | None = None) -> None:
    import signal as _signal
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Robot PID Tuner")
    _signal.signal(_signal.SIGINT, lambda *_: app.quit())
    # Wake Python every 200 ms so SIGINT is delivered even while Qt blocks
    _timer = QTimer(); _timer.start(200); _timer.timeout.connect(lambda: None)
    win = MainWindow(port=port)
    win.show()
    sys.exit(app.exec())
