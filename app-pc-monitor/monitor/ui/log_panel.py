"""
Log panel: scrolling display of LOG_TEXT packets with level and module filters.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QCheckBox, QLabel, QFileDialog, QGroupBox,
)

_LEVEL_NAMES = ["ERROR", "WARN", "INFO", "DEBUG", "TRACE"]
_LEVEL_COLORS = {
    0: "#ef5350",   # ERROR — red
    1: "#ff8a65",   # WARN  — orange
    2: "#e0e0e0",   # INFO  — white
    3: "#90a4ae",   # DEBUG — grey
    4: "#546e7a",   # TRACE — dark grey
}

_MODULE_NAMES = ["SYSTEM", "CONTROL", "IMU", "MOTOR", "ENCODER", "COMM", "SAFETY", "STORAGE"]


class LogPanel(QWidget):

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._paused    = False
        self._pending:  list[str] = []   # lines buffered while paused
        self._level_filter:  set[int] = set(range(5))   # all on
        self._module_filter: set[int] = set(range(8))   # all on

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── Filter row ────────────────────────────────────────────────────
        filter_box = QGroupBox("Filters")
        filter_lay = QVBoxLayout(filter_box)
        filter_lay.setSpacing(2)
        filter_lay.setContentsMargins(4, 4, 4, 4)

        level_row = QHBoxLayout()
        level_row.addWidget(QLabel("Level:"))
        self._level_checks: list[QCheckBox] = []
        for i, name in enumerate(_LEVEL_NAMES):
            cb = QCheckBox(name)
            cb.setChecked(True)
            color = _LEVEL_COLORS[i]
            cb.setStyleSheet(f"QCheckBox {{ color: {color}; }}")
            cb.stateChanged.connect(lambda state, idx=i: self._toggle_level(idx, bool(state)))
            self._level_checks.append(cb)
            level_row.addWidget(cb)
        level_row.addStretch()
        filter_lay.addLayout(level_row)

        module_row = QHBoxLayout()
        module_row.addWidget(QLabel("Module:"))
        self._module_checks: list[QCheckBox] = []
        for i, name in enumerate(_MODULE_NAMES):
            cb = QCheckBox(name)
            cb.setChecked(True)
            cb.stateChanged.connect(lambda state, idx=i: self._toggle_module(idx, bool(state)))
            self._module_checks.append(cb)
            module_row.addWidget(cb)
        module_row.addStretch()
        filter_lay.addLayout(module_row)
        root.addWidget(filter_box)

        # ── Log display ───────────────────────────────────────────────────
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(QFont("Consolas", 9))
        self._text.setStyleSheet("background:#1a1a1a; color:#e0e0e0;")
        self._text.document().setMaximumBlockCount(5000)
        root.addWidget(self._text)

        # ── Button row ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._pause_btn = QPushButton("Pause")
        self._pause_btn.setCheckable(True)
        self._pause_btn.toggled.connect(self._on_pause)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._text.clear)
        export_btn = QPushButton("Export log…")
        export_btn.clicked.connect(self._on_export)
        btn_row.addWidget(self._pause_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        btn_row.addWidget(export_btn)
        root.addLayout(btn_row)

    # ── Public slot ───────────────────────────────────────────────────────────
    def on_log(self, ts_ms: int, level: int, module: int, text: str) -> None:
        if level not in self._level_filter:
            return
        if module not in self._module_filter:
            return

        level_name  = _LEVEL_NAMES[level]  if level  < len(_LEVEL_NAMES)  else f"L{level}"
        module_name = _MODULE_NAMES[module] if module < len(_MODULE_NAMES) else f"M{module}"
        color       = _LEVEL_COLORS.get(level, "#e0e0e0")

        s  = ts_ms // 1000
        ms = ts_ms % 1000
        h, rem = divmod(s, 3600)
        m, sc  = divmod(rem, 60)
        ts_str = f"{h:02d}:{m:02d}:{sc:02d}.{ms:03d}"

        line = (f'<span style="color:#546e7a;">[{ts_str}]</span> '
                f'<span style="color:{color};font-weight:bold;">[{level_name:<5}]</span> '
                f'<span style="color:#80cbc4;">[{module_name:<8}]</span> '
                f'<span style="color:{color};">{_escape(text)}</span>')

        if self._paused:
            self._pending.append(line)
        else:
            self._append(line)

    # ── Internal ──────────────────────────────────────────────────────────────
    def _append(self, html: str) -> None:
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(html + "<br/>")
        self._text.setTextCursor(cursor)
        self._text.ensureCursorVisible()

    def _on_pause(self, checked: bool) -> None:
        self._paused = checked
        self._pause_btn.setText("Unpause" if checked else "Pause")
        if not checked:
            for line in self._pending:
                self._append(line)
            self._pending.clear()

    def _toggle_level(self, idx: int, enabled: bool) -> None:
        if enabled:
            self._level_filter.add(idx)
        else:
            self._level_filter.discard(idx)

    def _toggle_module(self, idx: int, enabled: bool) -> None:
        if enabled:
            self._module_filter.add(idx)
        else:
            self._module_filter.discard(idx)

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export log", "", "Text files (*.txt)"
        )
        if path:
            Path(path).write_text(self._text.toPlainText(), encoding="utf-8")


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
