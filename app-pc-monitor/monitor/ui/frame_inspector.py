"""
Frame Inspector panel.

Displays every TX/RX frame in a structured table with decoded fields.
Each row shows: Time | Dir | Seq | Type | Fields (decoded) | Hex payload (tooltip = full).
"""

from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QCheckBox, QComboBox, QLabel, QFileDialog,
)

from monitor.serial.protocol import FrameRecord

_MAX_ROWS         = 1000   # visible rows in table
_MAX_HISTORY      = 5_000  # total records kept in memory
_FLUSH_INTERVAL   = 100    # ms — batch-flush to table at 10 Hz
_COLOR_TX         = "#42a5f5"   # blue
_COLOR_RX         = "#66bb6a"   # green
_COLOR_TEXT       = "#e0e0e0"
_COLS             = ["Time", "Dir", "Seq", "Type", "Fields", "Hex payload"]
_TELEMETRY_TYPES  = frozenset(["TELEMETRY_SAMPLE", "TELEMETRY_BURST"])


class FrameInspector(QWidget):

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._paused          = False
        self._batch:          list[FrameRecord] = []   # buffered, not yet in table
        self._all:            list[FrameRecord] = []   # full history (capped)
        self._show_tx         = True
        self._show_rx         = True
        self._show_telemetry  = False   # off by default — too noisy at high rate
        self._type_filter     = "ALL"
        self._build_ui()

        # Flush buffered frames to the table at 10 Hz (decouples insertion rate
        # from the signal rate, which can be 100+ Hz during streaming)
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(_FLUSH_INTERVAL)
        self._flush_timer.timeout.connect(self._flush_batch)
        self._flush_timer.start()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Filter row
        frow = QHBoxLayout()
        frow.addWidget(QLabel("Show:"))

        self._tx_cb = QCheckBox("TX")
        self._tx_cb.setChecked(True)
        self._tx_cb.setStyleSheet(f"color:{_COLOR_TX};")
        self._tx_cb.stateChanged.connect(
            lambda s: self._set_dir_filter(tx=bool(s)))

        self._rx_cb = QCheckBox("RX")
        self._rx_cb.setChecked(True)
        self._rx_cb.setStyleSheet(f"color:{_COLOR_RX};")
        self._rx_cb.stateChanged.connect(
            lambda s: self._set_dir_filter(rx=bool(s)))

        self._telem_cb = QCheckBox("Telemetry")
        self._telem_cb.setChecked(False)
        self._telem_cb.setToolTip(
            "Show TELEMETRY_SAMPLE / TELEMETRY_BURST frames.\n"
            "Keep off during streaming — these arrive at 50–200 Hz."
        )
        self._telem_cb.stateChanged.connect(
            lambda s: self._set_telemetry_filter(bool(s)))

        self._type_combo = QComboBox()
        self._type_combo.addItem("All types")
        self._type_combo.setMinimumWidth(180)
        self._type_combo.currentTextChanged.connect(self._on_type_filter)

        frow.addWidget(self._tx_cb)
        frow.addWidget(self._rx_cb)
        frow.addWidget(self._telem_cb)
        frow.addSpacing(12)
        frow.addWidget(QLabel("Type:"))
        frow.addWidget(self._type_combo)
        frow.addStretch()
        root.addLayout(frow)

        # Table
        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        self._table.setFont(QFont("Consolas", 9))
        self._table.setStyleSheet(
            "QTableWidget { background:#1a1a1a; color:#e0e0e0;"
            "  gridline-color:#333; }"
            "QHeaderView::section { background:#2d2d2d; color:#ccc;"
            "  border:1px solid #444; padding:2px; }"
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(True)
        self._table.setAlternatingRowColors(False)

        hdr = self._table.horizontalHeader()
        for col, mode in enumerate([
            QHeaderView.ResizeMode.ResizeToContents,  # Time
            QHeaderView.ResizeMode.ResizeToContents,  # Dir
            QHeaderView.ResizeMode.ResizeToContents,  # Seq
            QHeaderView.ResizeMode.ResizeToContents,  # Type
            QHeaderView.ResizeMode.Stretch,            # Fields
            QHeaderView.ResizeMode.ResizeToContents,  # Hex
        ]):
            hdr.setSectionResizeMode(col, mode)

        root.addWidget(self._table)

        # Button row
        brow = QHBoxLayout()
        self._pause_btn = QPushButton("Pause")
        self._pause_btn.setCheckable(True)
        self._pause_btn.toggled.connect(self._on_pause)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear)
        export_btn = QPushButton("Export CSV…")
        export_btn.clicked.connect(self._export_csv)
        self._count_lbl = QLabel("0 frames")

        brow.addWidget(self._pause_btn)
        brow.addWidget(clear_btn)
        brow.addWidget(self._count_lbl)
        brow.addStretch()
        brow.addWidget(export_btn)
        root.addLayout(brow)

    # ── Public slot ───────────────────────────────────────────────────────────

    def on_frame(self, record: FrameRecord) -> None:
        """Receives every frame signal. Buffers; the flush timer drains at 10 Hz."""
        self._batch.append(record)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _flush_batch(self) -> None:
        """Called by QTimer at 10 Hz — drains the batch buffer into the table."""
        if not self._batch:
            return
        batch, self._batch = self._batch, []
        if self._paused:
            # While paused just keep history; don't touch the table
            for r in batch:
                self._store(r)
            return
        self._table.setUpdatesEnabled(False)
        try:
            for r in batch:
                self._store(r)
                if self._visible(r):
                    self._append_row(r)
            self._trim()
        finally:
            self._table.setUpdatesEnabled(True)
        self._count_lbl.setText(f"{self._table.rowCount()} frames")

    def _store(self, record: FrameRecord) -> None:
        """Add to history and update type combo. Caps history at _MAX_HISTORY."""
        if len(self._all) >= _MAX_HISTORY:
            self._all = self._all[-(_MAX_HISTORY // 2):]   # trim oldest half
        self._all.append(record)
        if record.type_name not in self._known_types():
            self._type_combo.addItem(record.type_name)

    def _known_types(self) -> set[str]:
        return {self._type_combo.itemText(i)
                for i in range(1, self._type_combo.count())}

    def _visible(self, r: FrameRecord) -> bool:
        if r.direction == "TX" and not self._show_tx:
            return False
        if r.direction == "RX" and not self._show_rx:
            return False
        if r.type_name in _TELEMETRY_TYPES and not self._show_telemetry:
            return False
        if self._type_filter != "ALL" and r.type_name != self._type_filter:
            return False
        return True

    def _append_row(self, r: FrameRecord) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        dir_color = QColor(_COLOR_TX if r.direction == "TX" else _COLOR_RX)
        text_color = QColor(_COLOR_TEXT)

        # Time
        ts = r.ts_ms
        sc, ms = divmod(ts, 1000)
        mn, sc = divmod(sc, 60)
        hr, mn = divmod(mn, 60)
        ts_str = f"{hr:02d}:{mn:02d}:{sc:02d}.{ms:03d}"

        # Fields summary
        fields_str = "  ".join(f"{k}={v}" for k, v in r.fields.items())

        # Hex: truncated in cell, full in tooltip
        payload_hex = r.payload.hex(" ").upper() if r.payload else ""
        cell_hex = (payload_hex[:47] + "…") if len(payload_hex) > 48 else payload_hex
        tip_hex = payload_hex
        if r.raw:
            tip_hex += f"\n\nFull frame:\n{r.raw.hex(' ').upper()}"

        cells = [ts_str, r.direction, str(r.seq), r.type_name, fields_str, cell_hex]
        for col, text in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setForeground(dir_color if col == 1 else text_color)
            if col == 3:  # Type column: bold
                font = QFont("Consolas", 9, QFont.Weight.Bold)
                item.setFont(font)
            if col == 5:
                item.setToolTip(tip_hex)
            self._table.setItem(row, col, item)

        self._table.scrollToBottom()

    def _trim(self) -> None:
        while self._table.rowCount() > _MAX_ROWS:
            self._table.removeRow(0)

    def _rebuild(self) -> None:
        self._table.setRowCount(0)
        for r in self._all[-_MAX_ROWS:]:
            if self._visible(r):
                self._append_row(r)
        self._count_lbl.setText(f"{self._table.rowCount()} frames")

    def _set_dir_filter(self, tx: bool | None = None,
                        rx: bool | None = None) -> None:
        if tx is not None:
            self._show_tx = tx
        if rx is not None:
            self._show_rx = rx
        self._rebuild()

    def _set_telemetry_filter(self, show: bool) -> None:
        self._show_telemetry = show
        self._rebuild()

    def _on_type_filter(self, text: str) -> None:
        self._type_filter = "ALL" if text == "All types" else text
        self._rebuild()

    def _on_pause(self, checked: bool) -> None:
        self._paused = checked
        self._pause_btn.setText("Resume" if checked else "Pause")
        if not checked:
            # Drain the batch immediately on unpause
            self._flush_batch()

    def _clear(self) -> None:
        self._batch.clear()
        self._all.clear()
        self._table.setRowCount(0)
        self._count_lbl.setText("0 frames")

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export frames", "", "CSV files (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                ["time_ms", "direction", "seq", "type",
                 "fields", "payload_hex", "frame_hex"])
            for r in self._all:
                writer.writerow([
                    r.ts_ms, r.direction, r.seq, r.type_name,
                    "  ".join(f"{k}={v}" for k, v in r.fields.items()),
                    r.payload.hex(" ").upper(),
                    r.raw.hex(" ").upper() if r.raw else "",
                ])
