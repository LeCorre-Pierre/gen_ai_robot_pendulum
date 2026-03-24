"""
Main application window.

Builds all dockable panels, creates the Session, and wires signals.
Persists layout to QSettings.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QByteArray
from PySide6.QtWidgets import (
    QMainWindow, QDockWidget, QWidget, QTabWidget,
    QMenuBar, QMenu, QStatusBar, QLabel, QFileDialog,
)
from PySide6.QtGui import QAction

from monitor.model.parameters import ParameterModel
from monitor.model.session import Session, ConnectionState, DeviceMode
from monitor.ui.toolbar import ConnectionToolbar
from monitor.ui.telemetry_panel import TelemetryPanel
from monitor.ui.parameters_panel import ParametersPanel
from monitor.ui.commands_panel import CommandsPanel
from monitor.ui.faults_panel import FaultsPanel
from monitor.ui.log_panel import LogPanel
from monitor.ui.capture_panel import CapturePanel


def _dock(title: str, widget: QWidget,
          area: Qt.DockWidgetArea) -> QDockWidget:
    d = QDockWidget(title)
    d.setWidget(widget)
    d.setAllowedAreas(Qt.AllDockWidgetAreas)
    d.setFeatures(
        QDockWidget.DockWidgetMovable |
        QDockWidget.DockWidgetFloatable |
        QDockWidget.DockWidgetClosable
    )
    return d


class MainWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Robot Monitor")
        self.resize(1400, 900)

        # ── Models ────────────────────────────────────────────────────────
        self._param_model = ParameterModel()
        self._session     = Session(self._param_model)

        # ── Panels ────────────────────────────────────────────────────────
        self._toolbar    = ConnectionToolbar()
        self._telemetry  = TelemetryPanel()
        self._parameters = ParametersPanel(self._param_model)
        self._commands   = CommandsPanel()
        self._faults     = FaultsPanel()
        self._log        = LogPanel()
        self._capture    = CapturePanel()

        # ── Central widget (tabbed: Telemetry + Capture) ──────────────────
        central_tabs = QTabWidget()
        central_tabs.addTab(self._telemetry, "Telemetry")
        central_tabs.addTab(self._capture,   "Capture")
        self.setCentralWidget(central_tabs)

        # ── Toolbar ───────────────────────────────────────────────────────
        toolbar_dock = self.addToolBar("Connection")
        toolbar_dock.setObjectName("toolbar_connection")
        toolbar_dock.setMovable(False)
        toolbar_dock.addWidget(self._toolbar)

        # ── Dock panels ───────────────────────────────────────────────────
        self._params_dock  = _dock("Parameters",    self._parameters, Qt.RightDockWidgetArea)
        self._cmd_dock     = _dock("Commands",      self._commands,   Qt.LeftDockWidgetArea)
        self._faults_dock  = _dock("Events & Faults", self._faults,  Qt.BottomDockWidgetArea)
        self._log_dock     = _dock("Log",           self._log,        Qt.BottomDockWidgetArea)

        self._params_dock.setObjectName("dock_parameters")
        self._cmd_dock.setObjectName("dock_commands")
        self._faults_dock.setObjectName("dock_faults")
        self._log_dock.setObjectName("dock_log")

        self.addDockWidget(Qt.RightDockWidgetArea,  self._params_dock)
        self.addDockWidget(Qt.LeftDockWidgetArea,   self._cmd_dock)
        self.addDockWidget(Qt.BottomDockWidgetArea, self._faults_dock)
        self.addDockWidget(Qt.BottomDockWidgetArea, self._log_dock)
        self.tabifyDockWidget(self._faults_dock, self._log_dock)

        # ── Menu bar ──────────────────────────────────────────────────────
        self._build_menu()

        # ── Status bar ────────────────────────────────────────────────────
        self._sb_link  = QLabel("Disconnected")
        self._sb_crc   = QLabel("CRC errors: 0")
        self.statusBar().addPermanentWidget(self._sb_link)
        self.statusBar().addPermanentWidget(QLabel("|"))
        self.statusBar().addPermanentWidget(self._sb_crc)

        # ── Wire signals ──────────────────────────────────────────────────
        self._wire_toolbar()
        self._wire_session()
        self._wire_panels()

        # ── Restore layout ────────────────────────────────────────────────
        self._restore_layout()

    # ── Menu ──────────────────────────────────────────────────────────────────
    def _build_menu(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        act_export_tel = QAction("Export telemetry CSV…", self)
        act_export_tel.triggered.connect(self._on_export_telemetry)
        act_quit = QAction("Quit", self)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_export_tel)
        file_menu.addSeparator()
        file_menu.addAction(act_quit)

        view_menu = mb.addMenu("&View")
        for dock, label in [
            (self._params_dock,  "Parameters"),
            (self._cmd_dock,     "Commands"),
            (self._faults_dock,  "Events & Faults"),
            (self._log_dock,     "Log"),
        ]:
            act = dock.toggleViewAction()
            act.setText(label)
            view_menu.addAction(act)

    # ── Signal wiring ─────────────────────────────────────────────────────────
    def _wire_toolbar(self) -> None:
        self._toolbar.connect_requested.connect(
            lambda port, baud: self._session.connect(port, baud)
        )
        self._toolbar.disconnect_requested.connect(self._session.disconnect)
        self._toolbar.ping_requested.connect(self._session.send_ping)

    def _wire_session(self) -> None:
        s = self._session
        s.connection_state_changed.connect(self._toolbar.on_connection_state_changed)
        s.connection_state_changed.connect(self._on_connection_state)
        s.device_mode_changed.connect(self._toolbar.on_mode_changed)
        s.device_mode_changed.connect(self._commands.on_mode_changed)
        s.fault_changed.connect(self._toolbar.on_fault_changed)
        s.uptime_ms_changed.connect(self._toolbar.on_uptime_changed)
        s.crc_errors_changed.connect(self._toolbar.on_crc_errors)
        s.pong_received.connect(self._toolbar.on_pong_received)
        s.rx_activity.connect(self._toolbar.on_rx_activity)
        s.telemetry_sample.connect(lambda *_: self._toolbar.on_packet_received())
        s.crc_errors_changed.connect(
            lambda n: self._sb_crc.setText(f"CRC errors: {n}")
        )
        s.telemetry_sample.connect(self._telemetry.on_telemetry_sample)
        s.event_received.connect(
            lambda code, name, ctx: self._faults.on_event(code, name, ctx)
        )
        s.fault_received.connect(
            lambda code, name, payload: self._faults.on_fault(code, name, payload)
        )
        s.log_received.connect(self._log.on_log)
        s.capture_status_changed.connect(self._capture.on_status_changed)
        s.capture_data_chunk.connect(self._capture.on_data_chunk)

        # Telemetry stream enable/disable
        self._telemetry.stream_enable_changed.connect(
            lambda sid, en, period: (
                self._session.enable_stream(sid, period) if en
                else self._session.disable_stream(sid)
            )
        )

    def _wire_panels(self) -> None:
        # Parameters panel
        self._parameters.save_to_flash_requested.connect(self._session.save_parameters)
        self._parameters.load_defaults_requested.connect(self._session.load_defaults)

        # Commands panel
        self._commands.emergency_stop_requested.connect(self._session.emergency_stop)
        self._commands.clear_fault_requested.connect(self._session.clear_fault)
        self._commands.set_control_mode_requested.connect(self._session.set_control_mode)
        self._commands.set_manual_command_requested.connect(self._session.set_manual_command)
        self._commands.start_test_requested.connect(self._session.start_test)
        self._commands.stop_test_requested.connect(self._session.stop_test)

        # Faults panel clear button
        self._faults.clear_fault_requested.connect(self._session.clear_fault)

        # Capture panel
        self._capture.configure_requested.connect(self._session.configure_capture)
        self._capture.arm_requested.connect(self._session.arm_capture)

    # ── Slots ─────────────────────────────────────────────────────────────────
    def _on_connection_state(self, state: ConnectionState) -> None:
        self._sb_link.setText(state.value)

    def _on_export_telemetry(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export telemetry", "", "CSV files (*.csv)"
        )
        if not path:
            return
        # Collect all ring buffers from all stream widgets
        from monitor.model.ring_buffer import RingBuffer
        from monitor.export.csv_export import export_streams
        bufs: dict[str, RingBuffer] = {}
        for sid, sw in self._telemetry._stream_widgets.items():
            for name, track in sw._tracks.items():
                bufs[f"s{sid:02x}_{name}"] = track.buffer
        rows = export_streams(bufs, path)
        self.statusBar().showMessage(f"Exported {rows} rows to {path}", 4000)

    # ── Layout persistence ────────────────────────────────────────────────────
    def _restore_layout(self) -> None:
        from PySide6.QtCore import QSettings
        settings = QSettings()
        geo = settings.value("mainwindow/geometry")
        if geo:
            self.restoreGeometry(geo)
        state = settings.value("mainwindow/state")
        if state:
            self.restoreState(state)

    def closeEvent(self, event) -> None:
        from PySide6.QtCore import QSettings
        settings = QSettings()
        settings.setValue("mainwindow/geometry", self.saveGeometry())
        settings.setValue("mainwindow/state", self.saveState())
        self._session.disconnect()
        super().closeEvent(event)
