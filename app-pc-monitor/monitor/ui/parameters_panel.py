"""
Parameters panel: tree-grouped, inline validation, preset import/export.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTreeView,
    QHeaderView, QFileDialog, QMessageBox, QLineEdit, QLabel,
)

from monitor.model.parameters import ParameterModel, COLUMN_HEADERS


class ParametersPanel(QWidget):

    save_to_flash_requested = Signal()
    load_defaults_requested = Signal()

    def __init__(self, model: ParameterModel, parent=None) -> None:
        super().__init__(parent)
        self._model = model
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── Search bar ────────────────────────────────────────────────────
        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter parameters…")
        self._search.textChanged.connect(self._on_filter)
        search_row.addWidget(QLabel("🔍"))
        search_row.addWidget(self._search)
        root.addLayout(search_row)

        # ── Tree view ─────────────────────────────────────────────────────
        self._tree = QTreeView()
        self._tree.setModel(self._model)
        self._tree.setAlternatingRowColors(True)
        self._tree.setEditTriggers(
            QTreeView.EditTrigger.DoubleClicked |
            QTreeView.EditTrigger.SelectedClicked
        )
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.expandAll()
        root.addWidget(self._tree)

        # ── Action buttons ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._save_btn    = QPushButton("Save to flash")
        self._defaults_btn = QPushButton("Load defaults")
        self._export_btn  = QPushButton("Export preset…")
        self._import_btn  = QPushButton("Import preset…")

        self._save_btn.setToolTip("Write all current values to firmware flash")
        self._defaults_btn.setToolTip("Reset all parameters to factory defaults")
        self._export_btn.setToolTip("Save current values to a local JSON file")
        self._import_btn.setToolTip("Load values from a local JSON file and write to firmware")

        self._save_btn.clicked.connect(self.save_to_flash_requested)
        self._defaults_btn.clicked.connect(self.load_defaults_requested)
        self._export_btn.clicked.connect(self._on_export)
        self._import_btn.clicked.connect(self._on_import)

        btn_row.addWidget(self._save_btn)
        btn_row.addWidget(self._defaults_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._export_btn)
        btn_row.addWidget(self._import_btn)
        root.addLayout(btn_row)

    # ── Slots ─────────────────────────────────────────────────────────────────
    def _on_filter(self, text: str) -> None:
        text = text.lower()
        for g_row in range(self._model.rowCount()):
            g_idx = self._model.index(g_row, 0)
            any_visible = False
            for p_row in range(self._model.rowCount(g_idx)):
                p_idx = self._model.index(p_row, 0, g_idx)
                name  = (self._model.data(p_idx) or "").lower()
                show  = text in name
                self._tree.setRowHidden(p_row, g_idx, not show)
                if show:
                    any_visible = True
            self._tree.setRowHidden(g_row, self._model.index(-1, -1), not any_visible)

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export parameter preset", "",
            "JSON files (*.json)"
        )
        if not path:
            return
        data = self._model.get_all_values()
        try:
            Path(path).write_text(json.dumps(data, indent=2))
        except OSError as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import parameter preset", "",
            "JSON files (*.json)"
        )
        if not path:
            return
        try:
            data: dict = json.loads(Path(path).read_text())
        except (OSError, json.JSONDecodeError) as e:
            QMessageBox.critical(self, "Import failed", str(e))
            return

        # Write values through the model (triggers WRITE_PARAMETER signals)
        for g_row in range(self._model.rowCount()):
            g_idx = self._model.index(g_row, 0)
            for p_row in range(self._model.rowCount(g_idx)):
                name_idx  = self._model.index(p_row, 0, g_idx)
                val_idx   = self._model.index(p_row, 1, g_idx)
                name      = self._model.data(name_idx)
                if name in data:
                    self._model.setData(val_idx, data[name], Qt.EditRole)
