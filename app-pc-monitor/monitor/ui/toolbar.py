"""
Persistent top toolbar: port selector, connect/disconnect, PING, status badges.
"""

from __future__ import annotations

from PySide6.QtCore import Signal, QTimer, Qt
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QComboBox, QLabel, QPushButton,
    QFrame,
)

from monitor.serial.port_scanner import list_ports
from monitor.model.session import ConnectionState, DeviceMode

_MODE_COLORS: dict[str, str] = {
    "BOOT":        "#78909c",
    "IDLE":        "#42a5f5",
    "ARMED":       "#ff7043",
    "BALANCING":   "#66bb6a",
    "FAULT":       "#ef5350",
    "CALIBRATION": "#ffd54f",
    "TEST":        "#ab47bc",
    "UNKNOWN":     "#546e7a",
}

_BAUDS = ["115200", "230400", "460800"]
_PING_TIMEOUT_MS  = 2000
_LED_FLASH_MS     = 120   # how long the RX LED stays lit after a byte burst


class _RxLed(QWidget):
    """A small coloured circle that flashes green when bytes arrive."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self._lit  = False
        self._off_timer = QTimer(self)
        self._off_timer.setSingleShot(True)
        self._off_timer.setInterval(_LED_FLASH_MS)
        self._off_timer.timeout.connect(self._turn_off)

    def flash(self) -> None:
        self._lit = True
        self.update()
        self._off_timer.start()

    def reset(self) -> None:
        self._lit = False
        self._off_timer.stop()
        self.update()

    def _turn_off(self) -> None:
        self._lit = False
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor("#66bb6a") if self._lit else QColor("#37474f")
        p.setBrush(color)
        p.setPen(QColor("#263238"))
        p.drawEllipse(1, 1, 12, 12)


def _badge(text: str, color: str) -> str:
    return (f'<span style="background:{color};color:#fff;'
            f'border-radius:3px;padding:2px 6px;font-weight:bold;">'
            f'{text}</span>')


class ConnectionToolbar(QWidget):
    connect_requested    = Signal(str, int)  # port, baud
    disconnect_requested = Signal()
    ping_requested       = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._uptime_ms    = 0
        self._uptime_timer = QTimer(self)
        self._uptime_timer.setInterval(1000)
        self._uptime_timer.timeout.connect(self._tick_uptime)

        # Ping timeout: mark as TIMEOUT if no PONG within _PING_TIMEOUT_MS
        self._ping_timeout_timer = QTimer(self)
        self._ping_timeout_timer.setSingleShot(True)
        self._ping_timeout_timer.setInterval(_PING_TIMEOUT_MS)
        self._ping_timeout_timer.timeout.connect(self._on_ping_timeout)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(6)

        # ── Port ─────────────────────────────────────────────────────────
        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(140)
        self._port_combo.setToolTip("Serial port (ST-Link VCP adapters shown first)")

        self._refresh_btn = QPushButton("⟳")
        self._refresh_btn.setFixedWidth(28)
        self._refresh_btn.setToolTip("Refresh port list")
        self._refresh_btn.clicked.connect(self.refresh_ports)

        # ── Baud ──────────────────────────────────────────────────────────
        self._baud_combo = QComboBox()
        for b in _BAUDS:
            self._baud_combo.addItem(b)
        self._baud_combo.setCurrentIndex(0)

        # ── Connect / Disconnect ──────────────────────────────────────────
        self._connect_btn    = QPushButton("Connect")
        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setEnabled(False)
        self._connect_btn.clicked.connect(self._on_connect)
        self._disconnect_btn.clicked.connect(self.disconnect_requested)

        # ── PING button ───────────────────────────────────────────────────
        self._ping_btn = QPushButton("Ping")
        self._ping_btn.setToolTip("Send PING and measure round-trip latency")
        self._ping_btn.setEnabled(False)
        self._ping_btn.clicked.connect(self._on_ping_clicked)

        self._ping_label = QLabel()
        self._ping_label.setTextFormat(Qt.RichText)
        self._ping_label.setMinimumWidth(110)
        self._set_ping_badge("—", "#546e7a")

        # ── Separator ─────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Sunken)

        # ── Mode / Fault badges ───────────────────────────────────────────
        self._mode_label = QLabel()
        self._mode_label.setTextFormat(Qt.RichText)
        self._set_mode_badge("UNKNOWN")

        self._fault_label = QLabel()
        self._fault_label.setTextFormat(Qt.RichText)
        self._set_fault_badge(0, "")

        # ── RX activity indicator ─────────────────────────────────────────
        self._rx_led     = _RxLed()
        self._rx_led.setToolTip("Flashes green when bytes are received")
        self._rx_label   = QLabel("RX: 0 B")
        self._rx_label.setToolTip("Total bytes received this session")
        self._pkt_label  = QLabel("PKT: 0")
        self._pkt_label.setToolTip("Total valid packets decoded this session")
        self._rx_packets = 0

        # ── Right-side info ───────────────────────────────────────────────
        self._uptime_label = QLabel("Uptime: --:--:--")
        self._crc_label    = QLabel("CRC err: 0")
        self._crc_label.setToolTip("Cumulative CRC errors on this session")

        # ── Layout ────────────────────────────────────────────────────────
        lay.addWidget(QLabel("Port:"))
        lay.addWidget(self._port_combo)
        lay.addWidget(self._refresh_btn)
        lay.addWidget(QLabel("Baud:"))
        lay.addWidget(self._baud_combo)
        lay.addWidget(self._connect_btn)
        lay.addWidget(self._disconnect_btn)
        lay.addWidget(self._ping_btn)
        lay.addWidget(self._ping_label)
        lay.addWidget(sep)
        lay.addWidget(self._mode_label)
        lay.addWidget(self._fault_label)
        lay.addStretch()
        lay.addWidget(self._rx_led)
        lay.addWidget(self._rx_label)
        lay.addWidget(self._pkt_label)
        lay.addWidget(self._uptime_label)
        lay.addWidget(self._crc_label)

        self.refresh_ports()

    # ── Public slots ─────────────────────────────────────────────────────────
    def refresh_ports(self) -> None:
        self._port_combo.clear()
        for p in list_ports():
            label = f"⭐ {p.device} — {p.description}" if p.is_stlink \
                    else f"{p.device} — {p.description}"
            self._port_combo.addItem(label, userData=p.device)
        if self._port_combo.count() == 0:
            self._port_combo.addItem("(no ports found)", userData="")

    def on_connection_state_changed(self, state: ConnectionState) -> None:
        connected  = state == ConnectionState.CONNECTED
        connecting = state == ConnectionState.CONNECTING
        self._connect_btn.setEnabled(not connected and not connecting)
        self._disconnect_btn.setEnabled(connected or connecting)
        self._port_combo.setEnabled(not connected and not connecting)
        self._baud_combo.setEnabled(not connected and not connecting)
        self._ping_btn.setEnabled(connected)
        if state == ConnectionState.DISCONNECTED:
            self._uptime_timer.stop()
            self._ping_timeout_timer.stop()
            self._uptime_label.setText("Uptime: --:--:--")
            self._set_mode_badge("UNKNOWN")
            self._set_fault_badge(0, "")
            self._set_ping_badge("—", "#546e7a")
            self._rx_led.reset()
            self._rx_label.setText("RX: 0 B")
            self._pkt_label.setText("PKT: 0")
            self._rx_packets = 0
        elif state == ConnectionState.CONNECTING:
            self._set_ping_badge("connecting…", "#ffd54f")

    def on_mode_changed(self, mode: DeviceMode) -> None:
        self._set_mode_badge(mode.name)

    def on_fault_changed(self, code: int, name: str) -> None:
        self._set_fault_badge(code, name)

    def on_uptime_changed(self, uptime_ms) -> None:
        self._uptime_ms = int(uptime_ms)
        self._uptime_timer.start()
        self._update_uptime()

    def on_pong_received(self, latency_ms: int) -> None:
        self._ping_timeout_timer.stop()
        self._ping_btn.setEnabled(True)
        self._ping_btn.setText("Ping")
        self._set_ping_badge(f"PONG  {latency_ms} ms", "#2e7d32")

    def on_rx_activity(self, total_bytes: int) -> None:
        self._rx_led.flash()
        self._rx_label.setText(f"RX: {_fmt_bytes(total_bytes)}")

    def on_packet_received(self) -> None:
        self._rx_packets += 1
        self._pkt_label.setText(f"PKT: {self._rx_packets}")

    def on_crc_errors(self, count: int) -> None:
        color = "#ef5350" if count > 0 else ""
        self._crc_label.setStyleSheet(f"color:{color};" if color else "")
        self._crc_label.setText(f"CRC err: {count}")

    # ── Internal ──────────────────────────────────────────────────────────────
    def _on_connect(self) -> None:
        port = self._port_combo.currentData()
        if not port:
            return
        baud = int(self._baud_combo.currentText())
        self.connect_requested.emit(port, baud)

    def _on_ping_clicked(self) -> None:
        self._ping_btn.setEnabled(False)
        self._ping_btn.setText("…")
        self._set_ping_badge("waiting…", "#ffd54f")
        self._ping_timeout_timer.start()
        self.ping_requested.emit()

    def _on_ping_timeout(self) -> None:
        self._ping_btn.setEnabled(True)
        self._ping_btn.setText("Ping")
        self._set_ping_badge("TIMEOUT", "#ef5350")

    def _tick_uptime(self) -> None:
        self._uptime_ms += 1000
        self._update_uptime()

    def _update_uptime(self) -> None:
        s = self._uptime_ms // 1000
        h, rem = divmod(s, 3600)
        m, sc  = divmod(rem, 60)
        self._uptime_label.setText(f"Uptime: {h:02d}:{m:02d}:{sc:02d}")

    def _set_mode_badge(self, mode_name: str) -> None:
        color = _MODE_COLORS.get(mode_name, _MODE_COLORS["UNKNOWN"])
        self._mode_label.setText(_badge(f"Mode: {mode_name}", color))

    def _set_fault_badge(self, code: int, name: str) -> None:
        if code == 0:
            self._fault_label.setText(_badge("Fault: OK", "#2e7d32"))
        else:
            label = name if name else f"0x{code:04X}"
            self._fault_label.setText(_badge(f"Fault: {label}", "#ef5350"))

    def _set_ping_badge(self, text: str, color: str) -> None:
        self._ping_label.setText(_badge(f"Ping: {text}", color))


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"
