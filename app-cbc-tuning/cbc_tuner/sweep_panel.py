"""
cbc_tuner/sweep_panel.py — Panneau d'analyse comparative des sweeps PID.

Chargement de fichiers JSON produits par run_sweep (MCP), affichage :
  - Overlay multi-courbes pitch (couleur = score RMS)
  - Tableau métriques trié et cliquable
  - Heatmap Kp × Kd
  - Bouton "Appliquer ces gains"
"""
from __future__ import annotations

import json
import math
import sys
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

_TOOLS_DIR = str(Path(__file__).parent.parent.parent / "tools")
_IPC_URL   = "http://127.0.0.1:3334"

C_ZERO   = "#546e7a"
C_THRESH = "#37474f"


def _rms_to_color(rms: float, rms_min: float, rms_max: float) -> QColor:
    """HSV : vert (hue=0.33) pour rms_min, rouge (hue=0.0) pour rms_max."""
    span = rms_max - rms_min
    t    = (rms - rms_min) / span if span > 0 else 0.0
    t    = max(0.0, min(1.0, t))
    hue  = (1.0 - t) * 0.33   # 0.33 = vert, 0.0 = rouge
    return QColor.fromHsvF(hue, 0.85, 0.95)


def _load_sweeps(directory: str) -> list[dict[str, Any]]:
    """Charge les fichiers JSON du dossier (réutilise sweep_analysis si dispo)."""
    if _TOOLS_DIR not in sys.path:
        sys.path.insert(0, _TOOLS_DIR)
    try:
        from sweep_analysis import load_sweeps
        return load_sweeps(directory)
    except ImportError:
        pass
    # Fallback minimal sans sweep_analysis
    trials = []
    for f in sorted(Path(directory).glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if "trial" in data and "metrics" in data:
                data["_file"] = f.name
                trials.append(data)
        except Exception:
            pass
    return trials


def _rank_trials(
    trials: list[dict],
    key: str = "rms_deg",
    survived_only: bool = True,
) -> list[dict]:
    if _TOOLS_DIR not in sys.path:
        sys.path.insert(0, _TOOLS_DIR)
    try:
        from sweep_analysis import rank_trials
        return rank_trials(trials, key=key, survived_only=survived_only)
    except ImportError:
        filtered = [t for t in trials if not survived_only or t.get("result") == "survived"]
        return sorted(filtered, key=lambda t: t.get("metrics", {}).get(key, math.inf))


def _stability_map(
    trials: list[dict],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if _TOOLS_DIR not in sys.path:
        sys.path.insert(0, _TOOLS_DIR)
    try:
        from sweep_analysis import stability_map
        return stability_map(trials)
    except ImportError:
        return np.array([]), np.array([]), np.array([[]])


# ── Composant heatmap ─────────────────────────────────────────────────────────

class _HeatmapWidget(QWidget):
    """Heatmap Kp × Kd utilisant un pyqtgraph ImageItem."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._pw = pg.PlotWidget(title="Heatmap Kp × Kd  (RMS °)")
        self._pw.setLabel("bottom", "Kd")
        self._pw.setLabel("left", "Kp")
        self._img = pg.ImageItem()
        self._pw.addItem(self._img)

        # Lookup table : vert→rouge (bonne → mauvaise performance)
        lut = np.zeros((256, 3), dtype=np.uint8)
        for i in range(256):
            t   = i / 255.0
            hue = (1.0 - t) * 0.33
            c   = QColor.fromHsvF(hue, 0.85, 0.90)
            lut[i] = [c.red(), c.green(), c.blue()]
        self._img.setLookupTable(lut)

        layout.addWidget(self._pw)

    def update_map(
        self,
        kp_arr: np.ndarray,
        kd_arr: np.ndarray,
        grid: np.ndarray,
    ) -> None:
        if len(kp_arr) < 2 or len(kd_arr) < 2:
            self._img.clear()
            return

        valid = grid[~np.isnan(grid)]
        v_min = float(valid.min()) if len(valid) else 0.0
        v_max = float(valid.max()) if len(valid) else 10.0

        # Remplacer NaN par -1 (hors plage → couleur neutre)
        display = np.where(np.isnan(grid), -1.0, (grid - v_min) / max(v_max - v_min, 1e-9))
        # ImageItem: shape (n_x, n_y) → (n_kd, n_kp) ici
        self._img.setImage(display.T * 255.0, autoLevels=False, levels=(0, 255))

        # Ticks axes
        kd_ticks = [(i, f"{v:.4f}") for i, v in enumerate(kd_arr)]
        kp_ticks = [(i, f"{v:.3f}") for i, v in enumerate(kp_arr)]
        self._pw.getAxis("bottom").setTicks([kd_ticks])
        self._pw.getAxis("left").setTicks([kp_ticks])
        self._pw.setXRange(-0.5, len(kd_arr) - 0.5, padding=0)
        self._pw.setYRange(-0.5, len(kp_arr) - 0.5, padding=0)


# ── Panneau principal ─────────────────────────────────────────────────────────

class SweepPanel(QWidget):
    """Onglet d'analyse comparative des sweeps PID."""

    _COLS = ["#", "kp", "ki", "kd", "rms°", "max°", "settle s", "sat%", "énergie", "résultat"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._trials:  list[dict] = []
        self._ranked:  list[dict] = []
        self._curves:  list[pg.PlotDataItem] = []
        self._build_ui()

    # ── Construction UI ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Toolbar
        root.addLayout(self._build_toolbar())

        # Splitter H : plots | table
        h_split = QSplitter(Qt.Orientation.Horizontal)

        # ── Côté gauche : overlay + heatmap ───────────────────────────────────
        lw = QWidget()
        ll = QVBoxLayout(lw)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)

        v_split = QSplitter(Qt.Orientation.Vertical)

        self._pw_overlay = pg.PlotWidget(title="Overlay Pitch (°)")
        self._pw_overlay.showGrid(x=True, y=True, alpha=0.25)
        self._pw_overlay.setLabel("left", "pitch", units="°")
        self._pw_overlay.setLabel("bottom", "temps", units="s")
        self._pw_overlay.addLine(y=0,  pen=pg.mkPen(C_ZERO,  width=1, style=Qt.PenStyle.DashLine))
        self._pw_overlay.addLine(y=2,  pen=pg.mkPen(C_THRESH, width=1, style=Qt.PenStyle.DotLine))
        self._pw_overlay.addLine(y=-2, pen=pg.mkPen(C_THRESH, width=1, style=Qt.PenStyle.DotLine))
        self._pw_overlay.addLegend(offset=(10, 10))

        self._heatmap = _HeatmapWidget()

        v_split.addWidget(self._pw_overlay)
        v_split.addWidget(self._heatmap)
        v_split.setSizes([400, 250])
        ll.addWidget(v_split)

        # ── Côté droit : tableau + bouton ─────────────────────────────────────
        rw = QWidget()
        rl = QVBoxLayout(rw)
        rl.setContentsMargins(4, 0, 0, 0)

        self._table = QTableWidget(0, len(self._COLS))
        self._table.setHorizontalHeaderLabels(self._COLS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.setAlternatingRowColors(True)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        self._apply_btn = QPushButton("Appliquer ces gains au robot")
        self._apply_btn.setEnabled(False)
        self._apply_btn.setStyleSheet(
            "QPushButton { background:#1b5e20; color:white; font-weight:bold; padding:6px; }"
            "QPushButton:hover { background:#2e7d32; }"
            "QPushButton:disabled { background:#37474f; color:#607d8b; }"
        )
        self._apply_btn.clicked.connect(self._apply_gains)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color:#90a4ae; font-size:10px;")

        rl.addWidget(self._table)
        rl.addWidget(self._apply_btn)
        rl.addWidget(self._status_label)

        h_split.addWidget(lw)
        h_split.addWidget(rw)
        h_split.setSizes([700, 350])
        root.addWidget(h_split)

    def _build_toolbar(self) -> QHBoxLayout:
        tb = QHBoxLayout()
        tb.setSpacing(6)

        self._dir_label = QLabel("Dossier : (aucun chargé)")
        self._dir_label.setStyleSheet("color:#90a4ae; font-size:10px;")

        browse_btn = QPushButton("Parcourir…")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse)

        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["Survived seulement", "Tous les essais"])
        self._filter_combo.currentIndexChanged.connect(self._refresh_view)

        self._sort_combo = QComboBox()
        self._sort_combo.addItems(["rms_deg", "max_abs_deg", "settling_time_s", "energy"])
        self._sort_combo.currentIndexChanged.connect(self._refresh_view)

        reload_btn = QPushButton("↺")
        reload_btn.setFixedWidth(28)
        reload_btn.setToolTip("Recharger le dossier")
        reload_btn.clicked.connect(self._reload)
        self._reload_btn = reload_btn
        self._current_dir: str | None = None

        tb.addWidget(QLabel("Tri :"))
        tb.addWidget(self._sort_combo)
        tb.addWidget(QLabel("Filtre :"))
        tb.addWidget(self._filter_combo)
        tb.addWidget(browse_btn)
        tb.addWidget(reload_btn)
        tb.addWidget(self._dir_label)
        tb.addStretch()
        return tb

    # ── Chargement des données ────────────────────────────────────────────────

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Sélectionner le dossier sweeps")
        if d:
            self._load_dir(d)

    def _reload(self) -> None:
        if self._current_dir:
            self._load_dir(self._current_dir)

    def _load_dir(self, directory: str) -> None:
        try:
            self._trials = _load_sweeps(directory)
        except Exception as exc:
            self._dir_label.setText(f"Erreur : {exc}")
            return
        self._current_dir = directory
        survived = sum(1 for t in self._trials if t.get("result") == "survived")
        self._dir_label.setText(
            f"{Path(directory).name}/  —  {len(self._trials)} fichiers, {survived} survived"
        )
        self._refresh_view()

    # ── Mise à jour des vues ──────────────────────────────────────────────────

    def _refresh_view(self) -> None:
        if not self._trials:
            return
        survived_only = self._filter_combo.currentIndex() == 0
        sort_key      = self._sort_combo.currentText()
        self._ranked  = _rank_trials(self._trials, key=sort_key, survived_only=survived_only)

        self._update_overlay()
        self._update_heatmap()
        self._update_table()

    def _update_overlay(self) -> None:
        for c in self._curves:
            self._pw_overlay.removeItem(c)
        self._curves.clear()

        if not self._ranked:
            return

        rms_vals = [t.get("metrics", {}).get("rms_deg", 0.0) for t in self._ranked]
        rms_min  = min(rms_vals) if rms_vals else 0.0
        rms_max  = max(rms_vals) if rms_vals else 1.0

        for t in self._ranked:
            samples = t.get("samples", [])
            if not samples:
                continue
            ts  = np.array([s["t_s"]   for s in samples])
            pts = np.array([s["pitch"] for s in samples])
            rms = t.get("metrics", {}).get("rms_deg", 0.0)
            col = _rms_to_color(rms, rms_min, rms_max)
            tr  = t["trial"]
            label = f"kp={tr['kp']:.3f} kd={tr['kd']:.4f} rms={rms:.2f}°"
            c = self._pw_overlay.plot(
                x=ts, y=pts,
                pen=pg.mkPen(col, width=1.5),
                name=label,
            )
            c.setDownsampling(auto=True, method="subsample")
            c.setClipToView(True)
            self._curves.append(c)

    def _update_heatmap(self) -> None:
        kp_arr, kd_arr, grid = _stability_map(self._trials)
        self._heatmap.update_map(kp_arr, kd_arr, grid)

    def _update_table(self) -> None:
        self._table.setRowCount(0)
        for rank, t in enumerate(self._ranked, 1):
            tr = t["trial"]
            m  = t.get("metrics", {})
            row = self._table.rowCount()
            self._table.insertRow(row)
            values = [
                str(rank),
                f"{tr['kp']:.3f}",
                f"{tr['ki']:.3f}",
                f"{tr['kd']:.4f}",
                f"{m.get('rms_deg',          float('nan')):.3f}",
                f"{m.get('max_abs_deg',       float('nan')):.3f}",
                f"{m.get('settling_time_s',   float('nan')):.3f}",
                f"{m.get('saturation_pct',    float('nan')):.1f}",
                f"{m.get('energy',            float('nan')):.3f}",
                t.get("result", "?"),
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                # Colorier la colonne résultat
                if col == len(self._COLS) - 1:
                    if val == "survived":
                        item.setForeground(QColor("#66bb6a"))
                    elif val == "early_stop":
                        item.setForeground(QColor("#ffa726"))
                    else:
                        item.setForeground(QColor("#ef5350"))
                self._table.setItem(row, col, item)

        self._apply_btn.setEnabled(False)

    # ── Interactions ──────────────────────────────────────────────────────────

    def _on_selection_changed(self) -> None:
        row = self._table.currentRow()
        self._apply_btn.setEnabled(row >= 0)

        # Mettre en surbrillance la courbe sélectionnée
        for i, c in enumerate(self._curves):
            selected = (i == row)
            width    = 3 if selected else 1.2
            alpha    = 255 if selected else 80
            col = c.opts["pen"].color()
            col.setAlpha(alpha)
            c.setPen(pg.mkPen(col, width=width))

    def _apply_gains(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._ranked):
            return
        tr  = self._ranked[row]["trial"]
        kp, ki, kd = float(tr["kp"]), float(tr["ki"]), float(tr["kd"])

        body = json.dumps({"kp": kp, "ki": ki, "kd": kd}).encode()
        req  = urllib.request.Request(
            f"{_IPC_URL}/gains", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=2.0) as r:
                resp = json.loads(r.read())
            if resp.get("ok"):
                self._status_label.setText(
                    f"✓ Gains appliqués : Kp={kp:.3f}  Ki={ki:.3f}  Kd={kd:.4f}"
                )
            else:
                self._status_label.setText(f"⚠ {resp.get('error', 'Erreur inconnue')}")
        except Exception as exc:
            self._status_label.setText(f"⚠ Impossible de joindre l'IPC : {exc}")
