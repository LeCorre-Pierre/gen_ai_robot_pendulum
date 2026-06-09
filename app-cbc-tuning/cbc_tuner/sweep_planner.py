"""
cbc_tuner/sweep_planner.py — Panneau de définition d'un plan de sweep PID.

Grille Kp × Ki × Kd, délai avant application des gains, durée de test,
sauvegarde / chargement du plan JSON, envoi au runner.
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox, QDoubleSpinBox, QFileDialog, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)


def _frange(start: float, stop: float, step: float) -> list[float]:
    """Range flottant inclusif avec gestion des erreurs d'arrondi."""
    if step <= 0 or start > stop + 1e-9:
        return [round(start, 6)]
    result = []
    n = round((stop - start) / step)
    for i in range(n + 1):
        v = round(start + i * step, 6)
        if v <= stop + step * 0.01:
            result.append(v)
    return result or [round(start, 6)]


# ── Ligne min / max / pas ─────────────────────────────────────────────────────

class _RangeRow(QWidget):

    changed = Signal()

    def __init__(
        self,
        label: str,
        v_max: float,
        default_min: float,
        default_max: float,
        default_step: float,
        decimals: int = 4,
        parent=None,
    ):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(6)

        lbl = QLabel(label)
        lbl.setFixedWidth(24)
        lbl.setStyleSheet(
            "color:#cccccc;font-size:11px;font-family:Consolas;font-weight:bold;"
        )
        lay.addWidget(lbl)

        def _spin(val: float) -> QDoubleSpinBox:
            s = QDoubleSpinBox()
            s.setRange(0.0, v_max)
            s.setDecimals(decimals)
            s.setValue(val)
            s.setStepType(QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
            s.setFixedWidth(90)
            s.setStyleSheet("font-size:11px;font-family:Consolas;")
            s.valueChanged.connect(self.changed)
            return s

        for txt, attr, val in (
            ("min",  "_spin_min",  default_min),
            ("max",  "_spin_max",  default_max),
            ("pas",  "_spin_step", default_step),
        ):
            lay.addWidget(QLabel(txt))
            sp = _spin(val)
            setattr(self, attr, sp)
            lay.addWidget(sp)

        self._count_lbl = QLabel("1 val")
        self._count_lbl.setStyleSheet("color:#78909c;font-size:10px;")
        self._count_lbl.setFixedWidth(46)
        lay.addWidget(self._count_lbl)
        lay.addStretch()

        self.changed.connect(self._update_count)
        self._update_count()

    def _update_count(self) -> None:
        n = len(self.values())
        self._count_lbl.setText(f"{n} val{'s' if n > 1 else ''}")

    # ── Accesseurs ────────────────────────────────────────────────────────────

    def values(self) -> list[float]:
        return _frange(
            self._spin_min.value(),
            self._spin_max.value(),
            self._spin_step.value(),
        )

    def set_range(self, mn: float, mx: float, step: float) -> None:
        self._spin_min.setValue(mn)
        self._spin_max.setValue(mx)
        self._spin_step.setValue(step)

    def min_val(self)  -> float: return self._spin_min.value()
    def max_val(self)  -> float: return self._spin_max.value()
    def step_val(self) -> float: return self._spin_step.value()


# ── Panneau principal ─────────────────────────────────────────────────────────

class SweepPlannerPanel(QWidget):
    """Onglet Plan : grille de paramètres + délai + sortie."""

    # tests: list[dict], out_dir: str, delay_s: float, hold_s: float
    plan_ready = Signal(list, str, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    # ── Construction UI ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # Grille PID
        grp_grid = QGroupBox("Grille de test  Kp × Ki × Kd")
        grp_grid.setStyleSheet("QGroupBox { font-weight:bold; font-size:11px; }")
        g_lay = QVBoxLayout(grp_grid)
        g_lay.setSpacing(2)

        self._kp = _RangeRow("Kp", 0.500, 0.10,  0.25,  0.05,  decimals=4)
        self._ki = _RangeRow("Ki", 0.200, 0.00,  0.00,  0.00,  decimals=4)
        self._kd = _RangeRow("Kd", 0.050, 0.005, 0.030, 0.005, decimals=5)

        for row in (self._kp, self._ki, self._kd):
            g_lay.addWidget(row)
            row.changed.connect(self._update_preview)
        root.addWidget(grp_grid)

        # Paramètres temporels
        grp_time = QGroupBox("Paramètres temporels")
        grp_time.setStyleSheet("QGroupBox { font-weight:bold; font-size:11px; }")
        t_lay = QHBoxLayout(grp_time)
        t_lay.setSpacing(12)

        def _dspin(val: float, lo: float, hi: float, suffix: str = "") -> QDoubleSpinBox:
            s = QDoubleSpinBox()
            s.setRange(lo, hi)
            s.setDecimals(1)
            s.setValue(val)
            if suffix:
                s.setSuffix(f" {suffix}")
            s.setFixedWidth(76)
            s.setStyleSheet("font-size:11px;font-family:Consolas;")
            s.valueChanged.connect(self._update_preview)
            return s

        self._delay_spin = _dspin(3.0, 0.5, 30.0, "s")
        self._hold_spin  = _dspin(5.0, 1.0, 60.0, "s")

        def _lbl(txt: str) -> QLabel:
            l = QLabel(txt)
            l.setStyleSheet("font-size:11px;color:#cccccc;")
            return l

        t_lay.addWidget(_lbl("Délai avant gains :"))
        t_lay.addWidget(self._delay_spin)
        t_lay.addWidget(QLabel("(pour positionner le robot)"))
        t_lay.addSpacing(24)
        t_lay.addWidget(_lbl("Durée du test :"))
        t_lay.addWidget(self._hold_spin)
        t_lay.addStretch()
        root.addWidget(grp_time)

        # Dossier de sortie
        grp_out = QGroupBox("Dossier de sortie")
        grp_out.setStyleSheet("QGroupBox { font-weight:bold; font-size:11px; }")
        o_lay = QHBoxLayout(grp_out)

        self._dir_edit = QLineEdit()
        self._dir_edit.setStyleSheet("font-size:11px;font-family:Consolas;")
        default_out = str(Path(__file__).parent.parent / "sweeps")
        self._dir_edit.setText(default_out)

        browse_btn = QPushButton("Parcourir…")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_dir)

        o_lay.addWidget(self._dir_edit, stretch=1)
        o_lay.addWidget(browse_btn)
        root.addWidget(grp_out)

        # Prévisualisation
        grp_prev = QGroupBox("Prévisualisation")
        grp_prev.setStyleSheet("QGroupBox { font-weight:bold; font-size:11px; }")
        p_lay = QVBoxLayout(grp_prev)

        self._preview_lbl = QLabel("")
        self._preview_lbl.setStyleSheet(
            "font-size:11px;font-family:Consolas;color:#90a4ae;"
        )
        self._preview_lbl.setWordWrap(True)
        p_lay.addWidget(self._preview_lbl)
        root.addWidget(grp_prev)

        # Boutons
        btn_row = QHBoxLayout()

        save_btn = QPushButton("Sauvegarder le plan…")
        save_btn.clicked.connect(self._save_plan)

        load_btn = QPushButton("Charger un plan…")
        load_btn.clicked.connect(self._load_plan)

        self._go_btn = QPushButton("Envoyer au Run  ▶")
        self._go_btn.setFixedHeight(34)
        self._go_btn.setStyleSheet(
            "QPushButton { background:#1565c0; color:white; font-weight:bold;"
            "              font-size:12px; padding:0 16px; }"
            "QPushButton:hover { background:#1976d2; }"
        )
        self._go_btn.clicked.connect(self._emit_plan)

        btn_row.addWidget(save_btn)
        btn_row.addWidget(load_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._go_btn)
        root.addLayout(btn_row)

        root.addStretch()
        self._update_preview()

    # ── Logique ───────────────────────────────────────────────────────────────

    def _build_tests(self) -> list[dict]:
        idx = 0
        tests = []
        for kp in self._kp.values():
            for ki in self._ki.values():
                for kd in self._kd.values():
                    tests.append({"id": idx, "kp": kp, "ki": ki, "kd": kd})
                    idx += 1
        return tests

    def _update_preview(self) -> None:
        tests   = self._build_tests()
        n       = len(tests)
        delay   = self._delay_spin.value()
        hold    = self._hold_spin.value()
        total_m = n * (delay + hold) / 60.0

        lines = [
            f"  Kp : {self._kp.values()}",
            f"  Ki : {self._ki.values()}",
            f"  Kd : {self._kd.values()}",
            "",
            f"  {n} tests  ×  ({delay:.1f} s délai + {hold:.1f} s test)"
            f"  =  {total_m:.1f} min estimé",
        ]
        self._preview_lbl.setText("\n".join(lines))

    def _browse_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Dossier de sortie des sweeps")
        if d:
            self._dir_edit.setText(d)

    def _save_plan(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Sauvegarder le plan", "", "JSON (*.json)"
        )
        if not path:
            return
        plan = {
            "version": 1,
            "params": {
                "kp":      {"min": self._kp.min_val(), "max": self._kp.max_val(), "step": self._kp.step_val()},
                "ki":      {"min": self._ki.min_val(), "max": self._ki.max_val(), "step": self._ki.step_val()},
                "kd":      {"min": self._kd.min_val(), "max": self._kd.max_val(), "step": self._kd.step_val()},
                "delay_s": self._delay_spin.value(),
                "hold_s":  self._hold_spin.value(),
                "out_dir": self._dir_edit.text(),
            },
            "tests": self._build_tests(),
        }
        Path(path).write_text(json.dumps(plan, indent=2), encoding="utf-8")

    def _load_plan(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Charger un plan", "", "JSON (*.json)")
        if not path:
            return
        try:
            plan = json.loads(Path(path).read_text(encoding="utf-8"))
            p = plan.get("params", {})
            for key, row in (("kp", self._kp), ("ki", self._ki), ("kd", self._kd)):
                d = p.get(key, {})
                if all(k in d for k in ("min", "max", "step")):
                    row.set_range(d["min"], d["max"], d["step"])
            if "delay_s" in p: self._delay_spin.setValue(p["delay_s"])
            if "hold_s"  in p: self._hold_spin.setValue(p["hold_s"])
            if "out_dir" in p: self._dir_edit.setText(p["out_dir"])
            self._update_preview()
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Erreur chargement plan", str(exc))

    def _emit_plan(self) -> None:
        tests   = self._build_tests()
        out_dir = self._dir_edit.text().strip()
        if out_dir:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
        self.plan_ready.emit(tests, out_dir, self._delay_spin.value(), self._hold_spin.value())
