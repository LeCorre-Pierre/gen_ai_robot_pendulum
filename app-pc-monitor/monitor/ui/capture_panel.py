"""
Capture panel: configure trigger, arm, retrieve chunked ring-buffer data.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QPushButton, QLabel, QComboBox,
    QSpinBox, QDoubleSpinBox, QFileDialog,
)

from monitor.model.telemetry import STREAM_DEFS

_STATUS_COLORS = {
    "IDLE":      "#546e7a",
    "ARMED":     "#ffd54f",
    "TRIGGERED": "#ff8a65",
    "DONE":      "#66bb6a",
    "UNKNOWN":   "#ef5350",
}

_TRIGGER_EDGES = ["Rising edge", "Falling edge", "Level above", "Level below"]


class CapturePanel(QWidget):

    configure_requested = Signal(int, int, int, int)  # trigger, signal_mask, pre, post
    arm_requested       = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._chunks:    list[bytes] = []
        self._status     = "IDLE"
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)

        # ── Configuration ─────────────────────────────────────────────────
        cfg_grp = QGroupBox("Capture configuration")
        cfg_lay = QFormLayout(cfg_grp)

        self._trigger_combo = QComboBox()
        for t in _TRIGGER_EDGES:
            self._trigger_combo.addItem(t)
        cfg_lay.addRow("Trigger:", self._trigger_combo)

        self._signal_combo = QComboBox()
        all_signals = []
        for sid, sdef in STREAM_DEFS.items():
            for sig in sdef.signals:
                all_signals.append((sid, sig.name))
                self._signal_combo.addItem(
                    f"[0x{sid:02X}] {sig.name}",
                    userData=(sid, sig.name)
                )
        cfg_lay.addRow("Trigger signal:", self._signal_combo)

        self._pre_spin = QSpinBox()
        self._pre_spin.setRange(0, 10000)
        self._pre_spin.setValue(200)
        cfg_lay.addRow("Pre-trigger samples:", self._pre_spin)

        self._post_spin = QSpinBox()
        self._post_spin.setRange(1, 10000)
        self._post_spin.setValue(800)
        cfg_lay.addRow("Post-trigger samples:", self._post_spin)

        self._cfg_btn = QPushButton("Configure")
        self._cfg_btn.clicked.connect(self._on_configure)
        cfg_lay.addRow("", self._cfg_btn)

        root.addWidget(cfg_grp)

        # ── Status and arm ────────────────────────────────────────────────
        status_row = QHBoxLayout()
        self._status_label = QLabel()
        self._set_status("IDLE")
        self._arm_btn = QPushButton("Arm capture")
        self._arm_btn.clicked.connect(self.arm_requested)
        status_row.addWidget(QLabel("Status:"))
        status_row.addWidget(self._status_label)
        status_row.addStretch()
        status_row.addWidget(self._arm_btn)
        root.addLayout(status_row)

        # ── Capture plot ──────────────────────────────────────────────────
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setMinimumHeight(200)
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._plot_widget.getPlotItem().addLegend()
        root.addWidget(self._plot_widget)

        # ── Export ────────────────────────────────────────────────────────
        exp_btn = QPushButton("Export capture CSV…")
        exp_btn.clicked.connect(self._on_export)
        root.addWidget(exp_btn)

    # ── Public slots ──────────────────────────────────────────────────────────
    def on_status_changed(self, status: str) -> None:
        self._set_status(status)
        if status == "DONE":
            self._render_capture()

    def on_data_chunk(self, chunk: bytes) -> None:
        self._chunks.append(chunk)
        if self._status == "DONE":
            self._render_capture()

    # ── Internal ──────────────────────────────────────────────────────────────
    def _set_status(self, status: str) -> None:
        self._status = status
        color = _STATUS_COLORS.get(status, "#ffffff")
        self._status_label.setStyleSheet(
            f"color:{color}; font-weight:bold; font-size:13px;"
        )
        self._status_label.setText(status)

    def _on_configure(self) -> None:
        trigger     = self._trigger_combo.currentIndex()
        signal_mask = 0xFF  # simplified: all signals
        pre         = self._pre_spin.value()
        post        = self._post_spin.value()
        self._chunks.clear()
        self.configure_requested.emit(trigger, signal_mask, pre, post)

    def _render_capture(self) -> None:
        if not self._chunks:
            return
        raw = b"".join(self._chunks)
        # Raw data is a flat array of float32 samples (simplified assumption)
        if len(raw) < 4:
            return
        vals = np.frombuffer(raw, dtype=np.float32)
        xs   = np.arange(len(vals), dtype=np.float32)
        self._plot_widget.clear()
        self._plot_widget.plot(x=xs, y=vals,
                               pen=pg.mkPen(color="#ef5350", width=1),
                               name="capture")

    def _on_export(self) -> None:
        if not self._chunks:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export capture", "", "CSV (*.csv)"
        )
        if not path:
            return
        raw  = b"".join(self._chunks)
        vals = np.frombuffer(raw, dtype=np.float32)
        with open(path, "w", newline="", encoding="utf-8") as f:
            import csv
            w = csv.writer(f)
            w.writerow(["sample_index", "value"])
            for i, v in enumerate(vals):
                w.writerow([i, float(v)])
