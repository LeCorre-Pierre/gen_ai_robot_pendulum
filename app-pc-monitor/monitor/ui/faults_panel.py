"""
Events and Faults panel: two sub-tabs with structured log tables.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTableView,
    QPushButton, QHeaderView, QAbstractItemView, QFileDialog,
    QDialog, QTextEdit, QLabel, QDialogButtonBox,
)

# ── Events table ──────────────────────────────────────────────────────────────
_EVENT_COLS = ["Timestamp", "Code", "Name", "Context"]


class EventTableModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[tuple] = []

    def add_event(self, ts_ms: int, code: int, name: str, context: bytes) -> None:
        row_idx = len(self._rows)
        self.beginInsertRows(QModelIndex(), row_idx, row_idx)
        ctx_str = context.hex() if context else ""
        self._rows.append((_fmt_ts(ts_ms), f"0x{code:04X}", name, ctx_str))
        self.endInsertRows()

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(_EVENT_COLS)

    def headerData(self, s, o, r=Qt.DisplayRole):
        if o == Qt.Horizontal and r == Qt.DisplayRole:
            return _EVENT_COLS[s]
        return None

    def data(self, idx: QModelIndex, role=Qt.DisplayRole) -> Any:
        if not idx.isValid():
            return None
        row = self._rows[idx.row()]
        if role == Qt.DisplayRole:
            return row[idx.column()]
        return None

    def export_csv(self, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(_EVENT_COLS)
            w.writerows(self._rows)


# ── Faults table ──────────────────────────────────────────────────────────────
_FAULT_COLS = [
    "Timestamp", "Code", "Name",
    "pitch°", "vel_L rpm", "vel_R rpm",
    "cmd_L", "cmd_R", "batt V", "i_L A", "i_R A",
]

import struct as _struct


def _parse_fault_payload(payload: bytes) -> dict:
    """Extract fields from FAULT packet payload (§10.3)."""
    result = {}
    if len(payload) < 2:
        return result
    result["code"] = _struct.unpack_from("<H", payload, 0)[0]
    if len(payload) >= 3:
        result["mode"] = payload[2]
    if len(payload) >= 48:
        fields = _struct.unpack_from("<IHffffffff", payload, 4)
        names  = ["ts_ms", "fault_code2", "pitch_deg",
                  "vel_left_rpm", "vel_right_rpm",
                  "motor_left_cmd", "motor_right_cmd",
                  "battery_v", "current_left_a", "current_right_a"]
        for n, v in zip(names, fields):
            result[n] = v
    return result


class FaultTableModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[tuple] = []
        self._payloads: list[bytes] = []

    def add_fault(self, ts_ms: int, code: int, name: str,
                  payload: bytes) -> None:
        row_idx = len(self._rows)
        self.beginInsertRows(QModelIndex(), row_idx, row_idx)
        p = _parse_fault_payload(payload)
        self._rows.append((
            _fmt_ts(ts_ms),
            f"0x{code:04X}",
            name,
            f"{p.get('pitch_deg', '—'):.1f}" if 'pitch_deg' in p else "—",
            f"{p.get('vel_left_rpm', '—'):.0f}" if 'vel_left_rpm' in p else "—",
            f"{p.get('vel_right_rpm', '—'):.0f}" if 'vel_right_rpm' in p else "—",
            f"{p.get('motor_left_cmd', '—'):.2f}" if 'motor_left_cmd' in p else "—",
            f"{p.get('motor_right_cmd', '—'):.2f}" if 'motor_right_cmd' in p else "—",
            f"{p.get('battery_v', '—'):.1f}" if 'battery_v' in p else "—",
            f"{p.get('current_left_a', '—'):.2f}" if 'current_left_a' in p else "—",
            f"{p.get('current_right_a', '—'):.2f}" if 'current_right_a' in p else "—",
        ))
        self._payloads.append(payload)
        self.endInsertRows()

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(_FAULT_COLS)

    def headerData(self, s, o, r=Qt.DisplayRole):
        if o == Qt.Horizontal and r == Qt.DisplayRole:
            return _FAULT_COLS[s]
        return None

    def data(self, idx: QModelIndex, role=Qt.DisplayRole) -> Any:
        if not idx.isValid():
            return None
        row = self._rows[idx.row()]
        if role == Qt.DisplayRole:
            return row[idx.column()]
        if role == Qt.BackgroundRole:
            return QColor("#4a1010")
        if role == Qt.ForegroundRole:
            return QColor("#ffcdd2")
        return None

    def payload_for_row(self, row: int) -> bytes:
        return self._payloads[row] if row < len(self._payloads) else b""

    def export_csv(self, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(_FAULT_COLS)
            w.writerows(self._rows)


# ── Panel ──────────────────────────────────────────────────────────────────────
class FaultsPanel(QWidget):

    clear_fault_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._session_start_ms: int = 0
        self._event_model = EventTableModel()
        self._fault_model  = FaultTableModel()
        self._build_ui()

    def set_session_start_ms(self, ts: int) -> None:
        self._session_start_ms = ts

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)

        tabs = QTabWidget()

        # ── Events tab ──────────────────────────────────────────────────
        ev_widget = QWidget()
        ev_lay = QVBoxLayout(ev_widget)
        self._event_view = QTableView()
        self._event_view.setModel(self._event_model)
        self._event_view.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._event_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        ev_btn_row = QHBoxLayout()
        ev_export = QPushButton("Export CSV…")
        ev_export.clicked.connect(self._export_events)
        ev_btn_row.addStretch()
        ev_btn_row.addWidget(ev_export)
        ev_lay.addWidget(self._event_view)
        ev_lay.addLayout(ev_btn_row)
        tabs.addTab(ev_widget, "Events")

        # ── Faults tab ──────────────────────────────────────────────────
        fa_widget = QWidget()
        fa_lay = QVBoxLayout(fa_widget)
        self._fault_view = QTableView()
        self._fault_view.setModel(self._fault_model)
        self._fault_view.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._fault_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._fault_view.doubleClicked.connect(self._on_fault_double_click)

        fa_btn_row = QHBoxLayout()
        clear_btn = QPushButton("Clear fault")
        clear_btn.clicked.connect(self.clear_fault_requested)
        fa_export = QPushButton("Export CSV…")
        fa_export.clicked.connect(self._export_faults)
        fa_btn_row.addWidget(clear_btn)
        fa_btn_row.addStretch()
        fa_btn_row.addWidget(fa_export)
        fa_lay.addWidget(self._fault_view)
        fa_lay.addLayout(fa_btn_row)
        tabs.addTab(fa_widget, "Faults")

        root.addWidget(tabs)

    # ── Public slots ──────────────────────────────────────────────────────────
    def on_event(self, code: int, name: str, context: bytes) -> None:
        import time
        ts = int(time.monotonic() * 1000)
        self._event_model.add_event(ts, code, name, context)
        self._event_view.scrollToBottom()

    def on_fault(self, code: int, name: str, payload: bytes) -> None:
        import time
        ts = int(time.monotonic() * 1000)
        self._fault_model.add_fault(ts, code, name, payload)
        self._fault_view.scrollToBottom()

    # ── Internal ──────────────────────────────────────────────────────────────
    def _on_fault_double_click(self, idx: QModelIndex) -> None:
        payload = self._fault_model.payload_for_row(idx.row())
        parsed  = _parse_fault_payload(payload)
        dlg = QDialog(self)
        dlg.setWindowTitle("Fault detail")
        lay = QVBoxLayout(dlg)
        txt = QTextEdit()
        txt.setReadOnly(True)
        lines = [f"{k}: {v}" for k, v in parsed.items()]
        lines.append(f"\nRaw hex:\n{payload.hex(' ')}")
        txt.setPlainText("\n".join(lines))
        lay.addWidget(txt)
        btn = QDialogButtonBox(QDialogButtonBox.Ok)
        btn.accepted.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.resize(420, 300)
        dlg.exec()

    def _export_events(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export events", "", "CSV (*.csv)"
        )
        if path:
            self._event_model.export_csv(path)

    def _export_faults(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export faults", "", "CSV (*.csv)"
        )
        if path:
            self._fault_model.export_csv(path)


def _fmt_ts(ms: int) -> str:
    s  = ms // 1000
    ms_r = ms % 1000
    h, rem = divmod(s, 3600)
    m, sc  = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sc:02d}.{ms_r:03d}"
