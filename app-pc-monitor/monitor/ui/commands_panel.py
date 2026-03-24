"""
Commands panel: safe commands, bring-up commands, closed-loop control, test sequences.
Buttons are greyed according to the current device mode.
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton,
    QLabel, QSlider, QComboBox, QDoubleSpinBox, QFormLayout, QSizePolicy,
)

from monitor.model.session import DeviceMode

# Test IDs (must match firmware)
TEST_MOTOR_LEFT_STEP   = 0x01
TEST_MOTOR_RIGHT_STEP  = 0x02
TEST_MOTOR_COAST       = 0x03
TEST_MOTOR_BRAKE       = 0x04
TEST_ENCODER_RESET     = 0x05
TEST_IMU_ZERO_PITCH    = 0x06
TEST_SINE_EXCITATION   = 0x10
TEST_STEP_RESPONSE     = 0x11
TEST_STATIC_IMU        = 0x12
TEST_ENCODER_SPIN      = 0x13
TEST_CURRENT_MONITOR   = 0x14


def _group(title: str) -> QGroupBox:
    g = QGroupBox(title)
    g.setLayout(QVBoxLayout())
    g.layout().setContentsMargins(6, 6, 6, 6)
    g.layout().setSpacing(4)
    return g


class CommandsPanel(QWidget):

    emergency_stop_requested     = Signal()
    clear_fault_requested        = Signal()
    set_control_mode_requested   = Signal(int)
    set_manual_command_requested = Signal(float, float)
    start_test_requested         = Signal(int, bytes)
    stop_test_requested          = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mode = DeviceMode.UNKNOWN
        self._build_ui()
        self._update_mode_guards()

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)

        # ── Emergency stop (always on top) ────────────────────────────────
        estop = QPushButton("⛔  EMERGENCY STOP")
        estop.setStyleSheet(
            "QPushButton { background:#c62828; color:white; font-weight:bold; "
            "font-size:14px; padding:8px; border-radius:4px; }"
            "QPushButton:hover { background:#b71c1c; }"
        )
        estop.clicked.connect(self.emergency_stop_requested)
        root.addWidget(estop)

        # ── Safe commands ─────────────────────────────────────────────────
        safe_grp = _group("Safe commands")
        self._clear_fault_btn = QPushButton("Clear fault")
        self._clear_fault_btn.clicked.connect(self.clear_fault_requested)
        safe_grp.layout().addWidget(self._clear_fault_btn)
        root.addWidget(safe_grp)

        # ── Mode selector ─────────────────────────────────────────────────
        mode_grp = _group("Control mode")
        mode_row = QHBoxLayout()
        self._mode_combo = QComboBox()
        for m in ["IDLE", "ARMED", "BALANCING"]:
            self._mode_combo.addItem(m, userData=DeviceMode[m].value)
        self._set_mode_btn = QPushButton("Apply")
        self._set_mode_btn.clicked.connect(self._on_set_mode)
        mode_row.addWidget(self._mode_combo)
        mode_row.addWidget(self._set_mode_btn)
        mode_grp.layout().addLayout(mode_row)

        # Velocity slider
        vel_row = QFormLayout()
        self._vel_slider = QSlider(Qt.Horizontal)
        self._vel_slider.setRange(-50, 50)
        self._vel_slider.setValue(0)
        self._vel_label = QLabel("0 rpm")
        self._vel_slider.valueChanged.connect(
            lambda v: (self._vel_label.setText(f"{v} rpm"), self._send_manual())
        )

        yaw_row = QFormLayout()
        self._yaw_slider = QSlider(Qt.Horizontal)
        self._yaw_slider.setRange(-100, 100)
        self._yaw_slider.setValue(0)
        self._yaw_label = QLabel("0.00")
        self._yaw_slider.valueChanged.connect(
            lambda v: (self._yaw_label.setText(f"{v/100:.2f}"), self._send_manual())
        )

        vel_row.addRow("Velocity (rpm):", self._vel_slider)
        vel_row.addRow("", self._vel_label)
        yaw_row.addRow("Yaw turn:", self._yaw_slider)
        yaw_row.addRow("", self._yaw_label)

        mode_grp.layout().addLayout(vel_row)
        mode_grp.layout().addLayout(yaw_row)
        root.addWidget(mode_grp)

        # ── Bring-up commands ─────────────────────────────────────────────
        bring_grp = _group("Bring-up (IDLE / TEST mode only)")
        grid = QHBoxLayout()
        self._bringup_buttons: list[QPushButton] = []

        def _bringup_btn(label: str, test_id: int) -> QPushButton:
            b = QPushButton(label)
            b.clicked.connect(lambda: self.start_test_requested.emit(test_id, b""))
            self._bringup_buttons.append(b)
            return b

        grid.addWidget(_bringup_btn("Motor A step", TEST_MOTOR_LEFT_STEP))
        grid.addWidget(_bringup_btn("Motor B step", TEST_MOTOR_RIGHT_STEP))
        grid.addWidget(_bringup_btn("Coast both",   TEST_MOTOR_COAST))
        grid.addWidget(_bringup_btn("Brake both",   TEST_MOTOR_BRAKE))
        bring_grp.layout().addLayout(grid)

        grid2 = QHBoxLayout()
        grid2.addWidget(_bringup_btn("Reset encoders", TEST_ENCODER_RESET))
        grid2.addWidget(_bringup_btn("Zero IMU pitch", TEST_IMU_ZERO_PITCH))
        bring_grp.layout().addLayout(grid2)
        root.addWidget(bring_grp)

        # ── Test sequences ─────────────────────────────────────────────────
        test_grp = _group("Test sequences (TEST mode only)")
        self._test_buttons: list[QPushButton] = []

        def _test_btn(label: str, test_id: int) -> QPushButton:
            b = QPushButton(label)
            b.clicked.connect(lambda: self.start_test_requested.emit(test_id, b""))
            self._test_buttons.append(b)
            return b

        t_row1 = QHBoxLayout()
        t_row1.addWidget(_test_btn("Sine excitation",    TEST_SINE_EXCITATION))
        t_row1.addWidget(_test_btn("Step response",      TEST_STEP_RESPONSE))
        t_row1.addWidget(_test_btn("Static IMU",         TEST_STATIC_IMU))
        t_row2 = QHBoxLayout()
        t_row2.addWidget(_test_btn("Encoder spin",       TEST_ENCODER_SPIN))
        t_row2.addWidget(_test_btn("Current monitor",    TEST_CURRENT_MONITOR))
        stop_btn = QPushButton("Stop test")
        stop_btn.setStyleSheet("color: #ef5350;")
        stop_btn.clicked.connect(self.stop_test_requested)
        t_row2.addWidget(stop_btn)

        test_grp.layout().addLayout(t_row1)
        test_grp.layout().addLayout(t_row2)
        root.addWidget(test_grp)

        root.addStretch()

    # ── Mode guard ────────────────────────────────────────────────────────────
    def on_mode_changed(self, mode: DeviceMode) -> None:
        self._mode = mode
        self._update_mode_guards()

    def _update_mode_guards(self) -> None:
        m = self._mode
        idle_or_test = m in (DeviceMode.IDLE, DeviceMode.TEST)
        test_only    = m == DeviceMode.TEST

        for b in self._bringup_buttons:
            b.setEnabled(idle_or_test)
            if not idle_or_test:
                b.setToolTip("Only available in IDLE or TEST mode")
            else:
                b.setToolTip("")

        for b in self._test_buttons:
            b.setEnabled(test_only)
            if not test_only:
                b.setToolTip("Only available in TEST mode")
            else:
                b.setToolTip("")

    # ── Internal ──────────────────────────────────────────────────────────────
    def _on_set_mode(self) -> None:
        mode_val = self._mode_combo.currentData()
        self.set_control_mode_requested.emit(mode_val)

    def _send_manual(self) -> None:
        vel  = float(self._vel_slider.value())
        yaw  = self._yaw_slider.value() / 100.0
        self.set_manual_command_requested.emit(vel, yaw)
