"""
motor_calib_panel.py — Dead-zone & motor characterisation tool.

Test sequence (~65 s, wheels in the air):
  Ph 0   : zero baseline
  Ph 1-5 : positive fine + coarse ramp up/down
  Ph 6-11: negative mirror
  Ph 12  : separator
  Ph 13  : positive step responses (10 amplitudes 5–100%)
  Ph 14  : negative step responses
  Ph 15  : reversal ±0.50  × 4 cycles
  Ph 16  : reversal ±0.75  × 4 cycles

Analysis tabs (shown after acquisition completes):
  Statique     — static transfer function vel = f(drive), dead-zone markers
  Hystérésis   — ramp-up vs ramp-down overlay, hysteresis loop
  Zone morte   — zoomed [-0.30..+0.30] with shaded DZ region, per-motor thresholds
  Indicielle   — step responses waterfall (delay + τ vs amplitude)
  Renversement — time-domain direction-change response
  Compensation — identified parameters + C code generator
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from itertools import groupby
from pathlib import Path
from typing import List, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QSizePolicy, QSpinBox, QDoubleSpinBox, QStackedWidget,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QVBoxLayout, QWidget,
)

_CALIB_DURATION_S = 65.0   # approximate total, for progress bar

# Phase groupings
_PHASES_RAMP_POS_UP   = {1, 2}   # positive ramp up
_PHASES_RAMP_POS_DN   = {4, 5}   # positive ramp down
_PHASES_RAMP_NEG_DN   = {7, 8}   # negative ramp down
_PHASES_RAMP_NEG_UP   = {10, 11} # negative ramp up
_PHASES_ALL_RAMP      = _PHASES_RAMP_POS_UP | _PHASES_RAMP_POS_DN \
                      | _PHASES_RAMP_NEG_DN | _PHASES_RAMP_NEG_UP
_PHASE_STEPS_POS      = 13
_PHASE_STEPS_NEG      = 14
_PHASE_REVERSAL_SMALL = 15
_PHASE_REVERSAL_LARGE = 16

# Amplitudes defined in the firmware sequence (drive fraction)
_STEP_AMPS = [0.05, 0.08, 0.10, 0.13, 0.15, 0.20, 0.30, 0.50, 0.75, 1.00]

VEL_DEAD_THRESHOLD = 4.0  # RPM — below this = motor not moving


@dataclass
class CalibSample:
    ts_ms:       int
    drive:       float   # [-1.0 .. +1.0]
    vel_l:       float   # RPM
    vel_r:       float   # RPM
    phase:       int
    calib_active: int    # 1=running, 0=last packet


# ── Analysis helpers ──────────────────────────────────────────────────────────

def _steady_state_points(
    samples: List[CalibSample], phases: set
) -> tuple[list, list]:
    """
    From ramp-phase samples, extract one (drive, vel_L, vel_R) steady-state
    point per hold period by grouping consecutive same-drive values and taking
    the last 50 %.
    """
    pts_l: list[tuple[float, float]] = []
    pts_r: list[tuple[float, float]] = []

    filt = [(s.drive, s.vel_l, s.vel_r) for s in samples if s.phase in phases]
    for drv, grp in groupby(filt, key=lambda x: round(x[0], 4)):
        pts = list(grp)
        n   = max(1, len(pts) // 2)
        sl  = pts[n:]
        vl  = sum(p[1] for p in sl) / len(sl)
        vr  = sum(p[2] for p in sl) / len(sl)
        pts_l.append((drv, vl))
        pts_r.append((drv, vr))

    return pts_l, pts_r


def _detect_dead_zone(pts: list[tuple[float, float]], positive: bool) -> float | None:
    """First drive value (in the correct direction) where |vel| > threshold."""
    sign = 1 if positive else -1
    ordered = sorted(pts, key=lambda p: sign * p[0])
    for drv, vel in ordered:
        if sign * drv > 0 and abs(vel) > VEL_DEAD_THRESHOLD:
            return drv
    return None


def _extract_steps(
    samples: List[CalibSample], phase: int
) -> list[dict]:
    """
    Extract per-amplitude step responses from phase 13 or 14.
    Returns list of dicts: amplitude, t_rel_s, vel_l, vel_r.
    """
    filt = [s for s in samples if s.phase == phase]
    steps = []

    for i in range(1, len(filt)):
        prev = filt[i - 1]
        curr = filt[i]
        if abs(prev.drive) < 0.01 and abs(curr.drive) > 0.01:
            amp = curr.drive
            # Find end of step (first return to zero after onset)
            end = i
            for j in range(i + 1, len(filt)):
                if abs(filt[j].drive) < 0.01:
                    end = j
                    break
            # Window: 10 samples before onset, 40 after end
            win = filt[max(0, i - 10): min(len(filt), end + 40)]
            t0  = filt[i].ts_ms
            steps.append({
                "amplitude": amp,
                "t_rel_s":   [(s.ts_ms - t0) / 1000.0 for s in win],
                "vel_l":     [s.vel_l for s in win],
                "vel_r":     [s.vel_r for s in win],
            })
    return steps


def _estimate_tau(t_s: list, vel: list) -> dict:
    """Estimate delay and 63% time constant from a step response."""
    if len(vel) < 4:
        return {"delay_s": None, "tau_63_s": None, "final_rpm": 0.0}

    n      = len(vel)
    v_init = float(np.mean(vel[:3]))
    v_fin  = float(np.mean(vel[max(0, n - max(1, n // 4)):]))
    span   = v_fin - v_init
    if abs(span) < 1.0:
        return {"delay_s": None, "tau_63_s": None, "final_rpm": v_fin}

    thr10 = v_init + 0.10 * span
    thr63 = v_init + 0.63 * span

    delay_s = tau_63_s = None
    for i, (t, v) in enumerate(zip(t_s, vel)):
        if t < 0:
            continue
        if delay_s is None and (span > 0 and v >= thr10 or span < 0 and v <= thr10):
            delay_s = t
        if tau_63_s is None and (span > 0 and v >= thr63 or span < 0 and v <= thr63):
            tau_63_s = t
            break

    return {"delay_s": delay_s, "tau_63_s": tau_63_s, "final_rpm": v_fin}


# ── Main panel ────────────────────────────────────────────────────────────────

class MotorCalibPanel(QWidget):
    """
    Complete motor dead-zone characterisation panel.

    Signals:
      start_calib(bool)  — True=start, False=abort → gui.py sends VCP command
    """
    start_calib = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._samples: List[CalibSample] = []
        self._running  = False
        self._t_start  = 0

        self._build_ui()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)

        # ── Top bar ───────────────────────────────────────────────────────────
        top = QHBoxLayout(); top.setContentsMargins(0, 0, 0, 0); top.setSpacing(6)

        self._start_btn = QPushButton("▶ Démarrer test (~65 s)")
        self._start_btn.setFixedHeight(30)
        self._start_btn.setStyleSheet(
            "QPushButton{background:#1565c0;color:white;font-weight:bold;border-radius:3px;}"
            "QPushButton:hover{background:#1976d2;}"
            "QPushButton:disabled{background:#37474f;color:#546e7a;}")
        self._start_btn.clicked.connect(self._on_start)
        top.addWidget(self._start_btn)

        self._abort_btn = QPushButton("⏹ Arrêt")
        self._abort_btn.setFixedHeight(30); self._abort_btn.setFixedWidth(70)
        self._abort_btn.setEnabled(False)
        self._abort_btn.clicked.connect(self._on_abort)
        top.addWidget(self._abort_btn)

        self._save_btn = QPushButton("💾 Sauvegarder")
        self._save_btn.setFixedHeight(30); self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_json)
        top.addWidget(self._save_btn)

        self._load_btn = QPushButton("📂 Charger")
        self._load_btn.setFixedHeight(30)
        self._load_btn.clicked.connect(self._load_json)
        top.addWidget(self._load_btn)

        top.addStretch()

        self._status_lbl = QLabel("Prêt — roues en l'air avant de démarrer")
        self._status_lbl.setStyleSheet("color:#90a4ae;font-size:10px;font-family:Consolas;")
        top.addWidget(self._status_lbl)

        root.addLayout(top)

        self._progress = QProgressBar()
        self._progress.setRange(0, 1000); self._progress.setValue(0)
        self._progress.setFixedHeight(8)
        self._progress.setTextVisible(False)
        root.addWidget(self._progress)

        # ── Stacked widget: live vs analysis ──────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_live_widget())
        self._stack.addWidget(self._build_analysis_widget())
        root.addWidget(self._stack, stretch=1)

    # ── Live view ─────────────────────────────────────────────────────────────

    def _build_live_widget(self):
        w = QWidget()
        lay = QVBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0)

        info = QLabel(
            "Séquence de calibration moteur\n"
            "• Maintenez le robot avec les roues libres (en l'air)\n"
            "• La séquence dure ~65 s et couvre :\n"
            "  Ph 1-11 : rampes lente et rapide ±100% avec hystérésis\n"
            "  Ph 13-14 : réponses indicielle à 10 amplitudes (5%→100%)\n"
            "  Ph 15-16 : renversements ±50% et ±75%\n"
            "• Les roues tournent : attention aux câbles !"
        )
        info.setStyleSheet("font-size:10px;font-family:Consolas;color:#78909c;"
                           "padding:12px;border:1px solid #37474f;border-radius:4px;")
        info.setWordWrap(True)
        lay.addWidget(info)

        glw = pg.GraphicsLayoutWidget(); glw.setBackground("#1e1e1e")
        self._live_drv   = glw.addPlot(row=0, col=0, title="Drive command")
        self._live_drv.setYRange(-1.1, 1.1, padding=0)
        self._live_drv.showGrid(x=True, y=True, alpha=0.2)
        self._curve_drv  = self._live_drv.plot(pen=pg.mkPen("#ffffff", width=1.5))

        self._live_vel   = glw.addPlot(row=1, col=0, title="Wheel velocity (RPM)")
        self._live_vel.setYRange(-100, 100, padding=0)
        self._live_vel.showGrid(x=True, y=True, alpha=0.2)
        self._live_vel.setLabel("bottom", "t (s)")
        self._curve_vl   = self._live_vel.plot(pen=pg.mkPen("#42a5f5", width=1.5), name="L")
        self._curve_vr   = self._live_vel.plot(pen=pg.mkPen("#ef5350", width=1.5), name="R")
        self._live_vel.addLegend(offset=(10, 10))
        self._live_vel.setXLink(self._live_drv)

        lay.addWidget(glw, stretch=1)
        return w

    # ── Analysis view ─────────────────────────────────────────────────────────

    def _build_analysis_widget(self):
        w    = QWidget()
        lay  = QVBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget()
        tabs.addTab(self._build_tab_static(),       "Statique")
        tabs.addTab(self._build_tab_hysteresis(),  "Hystérésis")
        tabs.addTab(self._build_tab_dead_zone(),   "Zone morte")
        tabs.addTab(self._build_tab_steps(),       "Indicielle")
        tabs.addTab(self._build_tab_reversal(),    "Renversement")
        tabs.addTab(self._build_tab_compensation(),"Compensation")
        lay.addWidget(tabs)
        return w

    # ── Tab : static transfer function ────────────────────────────────────────

    def _build_tab_static(self):
        w   = QWidget()
        lay = QVBoxLayout(w); lay.setContentsMargins(4, 4, 4, 4)

        desc = QLabel("Caractéristique statique vel = f(drive) — rampes lentes (phases 1-11)\n"
                      "Bleu = rampe montante positive, Rouge = rampe descendante positive, "
                      "Vert = rampe montante négative, Orange = rampe descendante négative.\n"
                      "Lignes tiretées = zone morte détectée. "
                      "L = gauche (cercles), R = droite (carrés).")
        desc.setStyleSheet("font-size:9px;color:#78909c;font-family:Consolas;")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        self._pw_static = pg.PlotWidget()
        self._pw_static.setBackground("#1e1e1e")
        self._pw_static.setLabel("bottom", "Drive"); self._pw_static.setLabel("left", "Vitesse (RPM)")
        self._pw_static.showGrid(x=True, y=True, alpha=0.2)
        self._pw_static.addLegend(offset=(10, 10))
        for y in (0,): self._pw_static.addLine(y=y, pen=pg.mkPen("#546e7a", style=Qt.PenStyle.DashLine))
        lay.addWidget(self._pw_static, stretch=2)

        self._static_info = QLabel("—")
        self._static_info.setStyleSheet("font-size:10px;font-family:Consolas;color:#90a4ae;"
                                        "padding:4px;border:1px solid #37474f;border-radius:3px;")
        lay.addWidget(self._static_info)
        return w

    # ── Tab : hysteresis ──────────────────────────────────────────────────────

    def _build_tab_hysteresis(self):
        w   = QWidget()
        lay = QVBoxLayout(w); lay.setContentsMargins(4, 4, 4, 4)

        desc = QLabel("Zoom zone morte ±0.30 : rampe montante vs descendante.\n"
                      "La boucle montre l'hystérésis du réducteur + frottement statique.")
        desc.setStyleSheet("font-size:9px;color:#78909c;font-family:Consolas;")
        lay.addWidget(desc)

        self._pw_hyst = pg.PlotWidget()
        self._pw_hyst.setBackground("#1e1e1e")
        self._pw_hyst.setLabel("bottom", "Drive"); self._pw_hyst.setLabel("left", "Vitesse (RPM)")
        self._pw_hyst.showGrid(x=True, y=True, alpha=0.25)
        self._pw_hyst.setXRange(-0.35, 0.35, padding=0)
        self._pw_hyst.addLegend(offset=(10, 10))
        lay.addWidget(self._pw_hyst, stretch=1)
        return w

    # ── Tab : dead zone zoom ──────────────────────────────────────────────────

    def _build_tab_dead_zone(self):
        w   = QWidget()
        lay = QVBoxLayout(w); lay.setContentsMargins(4, 4, 4, 4)

        desc = QLabel(
            "Zoom ±0.30 — où le moteur commence-t-il à bouger ?\n"
            "Bleu=rampe montante  Rouge=rampe descendante  |  L=cercles  R=carrés\n"
            "Zone jaune = zone morte identifiée (moteur L)  |  "
            "Tirets fines jaunes = seuil de détection ±4 RPM"
        )
        desc.setStyleSheet("font-size:9px;color:#78909c;font-family:Consolas;")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        self._pw_dz = pg.PlotWidget()
        self._pw_dz.setBackground("#1e1e1e")
        self._pw_dz.setLabel("bottom", "Drive")
        self._pw_dz.setLabel("left", "Vitesse (RPM)")
        self._pw_dz.showGrid(x=True, y=True, alpha=0.25)
        self._pw_dz.setXRange(-0.32, 0.32, padding=0)
        self._pw_dz.setYRange(-18, 18, padding=0)
        self._pw_dz.addLegend(offset=(10, 10))
        lay.addWidget(self._pw_dz, stretch=2)

        self._dz_summary = QLabel("—")
        self._dz_summary.setStyleSheet(
            "font-size:11px;font-family:Consolas;color:#ffd54f;"
            "padding:6px;border:1px solid #37474f;border-radius:3px;")
        lay.addWidget(self._dz_summary)
        return w

    # ── Tab : step responses ──────────────────────────────────────────────────

    def _build_tab_steps(self):
        w   = QWidget()
        lay = QHBoxLayout(w); lay.setContentsMargins(4, 4, 4, 4); lay.setSpacing(6)

        self._pw_steps = pg.PlotWidget()
        self._pw_steps.setBackground("#1e1e1e")
        self._pw_steps.setTitle("Réponses indicielle superposées (L=plein, R=tirets)")
        self._pw_steps.setLabel("bottom", "t depuis front (s)")
        self._pw_steps.setLabel("left", "Vitesse (RPM)")
        self._pw_steps.showGrid(x=True, y=True, alpha=0.2)
        self._pw_steps.addLegend(offset=(10, 10))
        lay.addWidget(self._pw_steps, stretch=2)

        right = QWidget(); right.setFixedWidth(280)
        rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("Paramètres par amplitude (+ moteur L)"))
        self._step_table = QTableWidget(0, 4)
        self._step_table.setHorizontalHeaderLabels(["Amp", "Retard (ms)", "τ63 (ms)", "RPM final"])
        self._step_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._step_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._step_table.setStyleSheet("font-size:10px;font-family:Consolas;")
        rl.addWidget(self._step_table)
        lay.addWidget(right)
        return w

    # ── Tab : reversal ────────────────────────────────────────────────────────

    def _build_tab_reversal(self):
        w   = QWidget()
        lay = QVBoxLayout(w); lay.setContentsMargins(4, 4, 4, 4)

        desc = QLabel("Renversements ±50% et ±75% : montre le temps mort au passage par zéro.")
        desc.setStyleSheet("font-size:9px;color:#78909c;font-family:Consolas;")
        lay.addWidget(desc)

        glw = pg.GraphicsLayoutWidget(); glw.setBackground("#1e1e1e")
        self._pw_rev_s = glw.addPlot(row=0, col=0, title="Renversement ±50%")
        self._pw_rev_l = glw.addPlot(row=1, col=0, title="Renversement ±75%")
        for p in (self._pw_rev_s, self._pw_rev_l):
            p.showGrid(x=True, y=True, alpha=0.2)
            p.setLabel("left", "RPM")
            p.addLine(y=0, pen=pg.mkPen("#546e7a", style=Qt.PenStyle.DashLine))
        self._pw_rev_l.setLabel("bottom", "t (s)")
        self._pw_rev_l.setXLink(self._pw_rev_s)
        lay.addWidget(glw, stretch=1)
        return w

    # ── Tab : compensation ────────────────────────────────────────────────────

    def _build_tab_compensation(self):
        w   = QWidget()
        lay = QHBoxLayout(w); lay.setContentsMargins(4, 4, 4, 4); lay.setSpacing(8)

        # Left: parameters + code
        left = QWidget(); left.setFixedWidth(360)
        ll   = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Paramètres identifiés"))

        self._param_table = QTableWidget(8, 2)
        self._param_table.setHorizontalHeaderLabels(["Paramètre", "Valeur"])
        self._param_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._param_table.verticalHeader().setVisible(False)
        self._param_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._param_table.setStyleSheet("font-size:10px;font-family:Consolas;")
        self._param_table.setFixedHeight(200)
        ll.addWidget(self._param_table)

        ll.addWidget(QLabel("Code C — compensation zone morte"))
        self._code_edit = QTextEdit()
        self._code_edit.setFont(QFont("Consolas", 9))
        self._code_edit.setReadOnly(True)
        self._code_edit.setStyleSheet("background:#141414;color:#e0e0e0;")
        ll.addWidget(self._code_edit)

        copy_btn = QPushButton("Copier le code")
        copy_btn.clicked.connect(lambda: __import__("PySide6.QtWidgets", fromlist=["QApplication"])
                                 .QApplication.clipboard().setText(self._code_edit.toPlainText()))
        ll.addWidget(copy_btn)
        lay.addWidget(left)

        # Right: raw vs compensated curve
        self._pw_comp = pg.PlotWidget()
        self._pw_comp.setBackground("#1e1e1e")
        self._pw_comp.setTitle("Sans (gris) vs avec compensation zone morte (vert)")
        self._pw_comp.setLabel("bottom", "Drive envoyé"); self._pw_comp.setLabel("left", "Drive effectif")
        self._pw_comp.showGrid(x=True, y=True, alpha=0.2)
        self._pw_comp.addLegend(offset=(10, 10))
        lay.addWidget(self._pw_comp, stretch=1)
        return w

    # ── Packet reception ──────────────────────────────────────────────────────

    def on_calib_packet(self, ts_ms: int, drive: float,
                        vel_l: float, vel_r: float,
                        phase: int, active: int):
        s = CalibSample(ts_ms=ts_ms, drive=drive, vel_l=vel_l, vel_r=vel_r,
                        phase=phase, calib_active=active)
        self._samples.append(s)

        # Update progress bar (estimate from timestamp)
        if self._running and self._t_start == 0:
            self._t_start = ts_ms
        elapsed = (ts_ms - self._t_start) / 1000.0 if self._t_start else 0.0
        pct     = min(1.0, elapsed / _CALIB_DURATION_S)
        self._progress.setValue(int(pct * 1000))

        # Update live plot (last 300 samples)
        n      = min(300, len(self._samples))
        recent = self._samples[-n:]
        ts     = [(r.ts_ms - recent[0].ts_ms) / 1000.0 for r in recent]
        self._curve_drv.setData(x=ts, y=[r.drive for r in recent])
        self._curve_vl.setData( x=ts, y=[r.vel_l for r in recent])
        self._curve_vr.setData( x=ts, y=[r.vel_r for r in recent])

        phase_names = {
            0: "Ph 0 : zéro baseline", 1: "Ph 1 : rampe montante fine +",
            2: "Ph 2 : rampe montante coarse +", 3: "Ph 3 : maintien +100%",
            4: "Ph 4 : rampe descend. coarse +", 5: "Ph 5 : rampe descend. fine +",
            6: "Ph 6 : pause zéro", 7: "Ph 7 : rampe descend. fine −",
            8: "Ph 8 : rampe descend. coarse −", 9: "Ph 9 : maintien −100%",
            10: "Ph 10 : rampe montante coarse −", 11: "Ph 11 : rampe montante fine −",
            12: "Ph 12 : séparateur", 13: "Ph 13 : indicielle +",
            14: "Ph 14 : indicielle −", 15: "Ph 15 : renversement ±50%",
            16: "Ph 16 : renversement ±75%",
        }
        self._status_lbl.setText(
            f"{phase_names.get(phase, f'Ph {phase}')}  |  "
            f"drive={drive:+.3f}  Vl={vel_l:+.0f}  Vr={vel_r:+.0f} RPM  |  "
            f"t={elapsed:.1f} s")

        # Enable save as soon as we have data (don't wait for EOF packet)
        if len(self._samples) == 20:
            self._save_btn.setEnabled(True)

        if active == 0:
            self._on_done()

    # ── Button handlers ───────────────────────────────────────────────────────

    def _on_start(self):
        self._samples.clear()
        self._running  = True
        self._t_start  = 0
        self._progress.setValue(0)
        self._stack.setCurrentIndex(0)
        self._start_btn.setEnabled(False)
        self._abort_btn.setEnabled(True)
        self._save_btn.setEnabled(False)
        self._status_lbl.setStyleSheet(
            "color:#ffd54f;font-size:10px;font-family:Consolas;font-weight:bold;")
        self._status_lbl.setText("En cours…")
        self.start_calib.emit(True)

    def _on_abort(self):
        self._running = False
        self.start_calib.emit(False)
        self._start_btn.setEnabled(True)
        self._abort_btn.setEnabled(False)
        self._status_lbl.setStyleSheet("color:#ef5350;font-size:10px;font-family:Consolas;")
        self._status_lbl.setText("Interrompu.")

    def _on_done(self):
        self._running = False
        self._progress.setValue(1000)
        self._start_btn.setEnabled(True)
        self._abort_btn.setEnabled(False)
        self._save_btn.setEnabled(True)
        self._status_lbl.setStyleSheet("color:#66bb6a;font-size:10px;font-family:Consolas;font-weight:bold;")
        self._status_lbl.setText(f"Terminé — {len(self._samples)} échantillons")
        self._analyze()
        self._stack.setCurrentIndex(1)

    # ── Analysis ──────────────────────────────────────────────────────────────

    def _analyze(self):
        if len(self._samples) < 20:
            return
        self._analyze_static()
        self._analyze_hysteresis()
        self._analyze_dead_zone()
        self._analyze_steps()
        self._analyze_reversal()
        self._analyze_compensation()

    def _analyze_static(self):
        pw = self._pw_static
        pw.clear()
        pw.addLine(y=0, pen=pg.mkPen("#546e7a", style=Qt.PenStyle.DashLine))

        colors = {
            "up_pos":   ("#1976d2", "#42a5f5"),
            "dn_pos":   ("#c62828", "#ef5350"),
            "dn_neg":   ("#2e7d32", "#66bb6a"),
            "up_neg":   ("#e65100", "#ffa726"),
        }

        def _scatter(phases, label, c_l, c_r, symbol_l="o", symbol_r="s"):
            pl, pr = _steady_state_points(self._samples, phases)
            if pl:
                xs = [p[0] for p in pl]; ys = [p[1] for p in pl]
                pw.plot(x=xs, y=ys, pen=None,
                        symbol=symbol_l, symbolBrush=c_l, symbolSize=6, name=f"{label} L")
            if pr:
                xs = [p[0] for p in pr]; ys = [p[1] for p in pr]
                pw.plot(x=xs, y=ys, pen=None,
                        symbol=symbol_r, symbolBrush=c_r, symbolSize=6, name=f"{label} R")
            return pl, pr

        pu_pl, pu_pr = _scatter(_PHASES_RAMP_POS_UP, "↑+", *colors["up_pos"])
        _scatter(_PHASES_RAMP_POS_DN, "↓+", *colors["dn_pos"])
        _scatter(_PHASES_RAMP_NEG_DN, "↓−", *colors["dn_neg"])
        _scatter(_PHASES_RAMP_NEG_UP, "↑−", *colors["up_neg"])

        # Dead zone detection
        all_pts_l = _steady_state_points(self._samples, _PHASES_ALL_RAMP)[0]
        dz_fp     = _detect_dead_zone(all_pts_l, positive=True)
        dz_fn     = _detect_dead_zone(all_pts_l, positive=False)

        info_parts = []
        for label, dz in (("DZ fwd L", dz_fp), ("DZ rev L", dz_fn)):
            if dz is not None:
                pw.addLine(x=dz, pen=pg.mkPen("#ffd54f", width=1.5,
                                               style=Qt.PenStyle.DashLine))
                info_parts.append(f"{label} = {dz:+.3f}")

        # Linear fit in active region
        active_l = [(d, v) for d, v in all_pts_l
                    if dz_fp and d > dz_fp and abs(v) > VEL_DEAD_THRESHOLD]
        if len(active_l) > 3:
            xs_a = np.array([p[0] for p in active_l])
            ys_a = np.array([p[1] for p in active_l])
            m, b  = np.polyfit(xs_a, ys_a, 1)
            xs_fit = np.linspace(xs_a.min(), xs_a.max(), 50)
            pw.plot(x=xs_fit, y=m * xs_fit + b,
                    pen=pg.mkPen("#ffd54f", width=2, style=Qt.PenStyle.DotLine), name="fit linéaire")
            info_parts.append(f"gain={m:.1f} RPM/unit")

        self._static_info.setText("  |  ".join(info_parts) if info_parts else
                                   "Pas assez de données pour identifier la zone morte")

    def _analyze_hysteresis(self):
        pw = self._pw_hyst
        pw.clear()
        pw.addLine(y=0, pen=pg.mkPen("#546e7a", style=Qt.PenStyle.DashLine))
        pw.addLine(x=0, pen=pg.mkPen("#546e7a", style=Qt.PenStyle.DashLine))

        combos = [
            (_PHASES_RAMP_POS_UP, "↑+ L", "#42a5f5", "↑+ R", "#82b1ff"),
            (_PHASES_RAMP_POS_DN, "↓+ L", "#ef5350", "↓+ R", "#ff8a80"),
            (_PHASES_RAMP_NEG_DN, "↓− L", "#66bb6a", "↓− R", "#b9f6ca"),
            (_PHASES_RAMP_NEG_UP, "↑− L", "#ffa726", "↑− R", "#ffe57f"),
        ]
        for phases, nl, cl, nr, cr in combos:
            pl, pr = _steady_state_points(self._samples, phases)
            for pts, name, col in ((pl, nl, cl), (pr, nr, cr)):
                if pts:
                    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
                    pw.plot(x=xs, y=ys, pen=pg.mkPen(col, width=2), name=name)

    def _analyze_dead_zone(self):
        pw = self._pw_dz
        pw.clear()
        pw.addLine(y=0, pen=pg.mkPen("#546e7a", style=Qt.PenStyle.DashLine))
        pw.addLine(x=0, pen=pg.mkPen("#546e7a", style=Qt.PenStyle.DashLine))
        # Detection threshold lines
        for y in (VEL_DEAD_THRESHOLD, -VEL_DEAD_THRESHOLD):
            pw.addLine(y=y, pen=pg.mkPen("#ffd54f", width=1, style=Qt.PenStyle.DashLine))

        # Zoomed scatter: up-ramp (all positive+negative ramp-up phases), down-ramp
        up_phases = _PHASES_RAMP_POS_UP | _PHASES_RAMP_NEG_UP
        dn_phases = _PHASES_RAMP_POS_DN | _PHASES_RAMP_NEG_DN

        def _zoom_scatter(phases, label, c_l, c_r):
            pl, pr = _steady_state_points(self._samples, phases)
            pl = [(d, v) for d, v in pl if abs(d) <= 0.32]
            pr = [(d, v) for d, v in pr if abs(d) <= 0.32]
            if pl:
                pw.plot(x=[p[0] for p in pl], y=[p[1] for p in pl],
                        pen=None, symbol="o", symbolBrush=c_l, symbolSize=7,
                        name=f"{label} L")
            if pr:
                pw.plot(x=[p[0] for p in pr], y=[p[1] for p in pr],
                        pen=None, symbol="s", symbolBrush=c_r, symbolSize=7,
                        name=f"{label} R")
            return pl, pr

        _zoom_scatter(up_phases, "↑rampe", "#42a5f5", "#82b1ff")
        _zoom_scatter(dn_phases, "↓rampe", "#ef5350", "#ff8a80")

        # Dead zone detection per motor
        all_l, all_r = _steady_state_points(self._samples, _PHASES_ALL_RAMP)
        dz_fwd_l = _detect_dead_zone(all_l, positive=True)
        dz_rev_l = _detect_dead_zone(all_l, positive=False)
        dz_fwd_r = _detect_dead_zone(all_r, positive=True)
        dz_rev_r = _detect_dead_zone(all_r, positive=False)

        # Shaded dead zone region (L motor bounds)
        dz_neg = dz_rev_l if dz_rev_l is not None else -0.10
        dz_pos = dz_fwd_l if dz_fwd_l is not None else  0.10
        region = pg.LinearRegionItem(
            [dz_neg, dz_pos], movable=False,
            brush=pg.mkBrush(255, 213, 79, 35),
            pen=pg.mkPen("#ffd54f", width=1.5, style=Qt.PenStyle.DotLine))
        pw.addItem(region)

        # Per-motor threshold markers with text labels
        marker_defs = [
            ("L fwd", dz_fwd_l, "#42a5f5",  0.80),
            ("L rev", dz_rev_l, "#82b1ff",  0.72),
            ("R fwd", dz_fwd_r, "#ef5350",  0.64),
            ("R rev", dz_rev_r, "#ff8a80",  0.56),
        ]
        for name, val, color, ypos in marker_defs:
            if val is None:
                continue
            il = pg.InfiniteLine(
                pos=val, angle=90, movable=False,
                pen=pg.mkPen(color, width=2, style=Qt.PenStyle.DashLine))
            pw.addItem(il)
            txt = pg.TextItem(text=f"{name}={val:+.3f}", color=color, anchor=(0.5, 0.0))
            txt.setPos(val, 18 * ypos - 9)
            pw.addItem(txt)

        # Summary label
        def _fmt(v): return f"{v:+.3f}" if v is not None else "N/A"
        hyst_l = abs((dz_fwd_l or 0.0) - abs(dz_rev_l or 0.0))
        hyst_r = abs((dz_fwd_r or 0.0) - abs(dz_rev_r or 0.0))
        self._dz_summary.setText(
            f"DZ fwd L={_fmt(dz_fwd_l)}  DZ rev L={_fmt(dz_rev_l)}  "
            f"Hystérésis L={hyst_l:.3f}   |   "
            f"DZ fwd R={_fmt(dz_fwd_r)}  DZ rev R={_fmt(dz_rev_r)}  "
            f"Hystérésis R={hyst_r:.3f}")

    def _analyze_steps(self):
        pw = self._pw_steps
        pw.clear()
        pw.addLine(y=0, pen=pg.mkPen("#546e7a", style=Qt.PenStyle.DashLine))
        pw.addLine(x=0, pen=pg.mkPen("#546e7a", width=2))

        steps_pos = _extract_steps(self._samples, _PHASE_STEPS_POS)
        steps_neg = _extract_steps(self._samples, _PHASE_STEPS_NEG)

        # Color gradient: blue (small amp) → red (large amp)
        n_amps = len(_STEP_AMPS)
        def _amp_color(i, total):
            t = i / max(1, total - 1)
            r = int(66 + t * (239 - 66))
            g = int(165 - t * 165)
            b = int(244 - t * 200)
            return pg.mkColor(r, g, b)

        self._step_table.setRowCount(0)

        for i, step in enumerate(steps_pos):
            c = _amp_color(i, n_amps)
            t = step["t_rel_s"]; vl = step["vel_l"]; vr = step["vel_r"]
            pw.plot(x=t, y=vl, pen=pg.mkPen(c, width=2),
                    name=f"{step['amplitude']*100:.0f}% L")
            pw.plot(x=t, y=vr, pen=pg.mkPen(c, width=1.5, style=Qt.PenStyle.DashLine))
            tau = _estimate_tau(t, vl)
            row = self._step_table.rowCount(); self._step_table.insertRow(row)
            vals = [
                f"{step['amplitude']*100:.0f}%",
                f"{tau['delay_s']*1000:.0f}" if tau['delay_s'] is not None else "—",
                f"{tau['tau_63_s']*1000:.0f}" if tau['tau_63_s'] is not None else "—",
                f"{tau['final_rpm']:.1f}",
            ]
            for ci, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if ci == 1 and tau['delay_s'] is not None:
                    ms = tau['delay_s'] * 1000
                    item.setForeground(QColor("#66bb6a" if ms < 30 else ("#ffd54f" if ms < 80 else "#ef5350")))
                self._step_table.setItem(row, ci, item)

        for step in steps_neg:
            i = min(len(steps_neg) - 1, _STEP_AMPS.index(abs(step["amplitude"]))
                    if abs(step["amplitude"]) in _STEP_AMPS else 0)
            c = _amp_color(i, n_amps)
            t = step["t_rel_s"]; vl = step["vel_l"]
            pw.plot(x=t, y=vl, pen=pg.mkPen(c, width=1.5, style=Qt.PenStyle.DotLine))

    def _analyze_reversal(self):
        for phase, pw in ((_PHASE_REVERSAL_SMALL, self._pw_rev_s),
                           (_PHASE_REVERSAL_LARGE, self._pw_rev_l)):
            pw.clear()
            pw.addLine(y=0, pen=pg.mkPen("#546e7a", style=Qt.PenStyle.DashLine))
            filt = [s for s in self._samples if s.phase == phase]
            if not filt:
                continue
            t0 = filt[0].ts_ms
            ts = [(s.ts_ms - t0) / 1000.0 for s in filt]
            pw.plot(x=ts, y=[s.drive * 80 for s in filt],
                    pen=pg.mkPen("#ffffff", width=1.5, style=Qt.PenStyle.DashLine),
                    name="drive×80 (proxy)")
            pw.plot(x=ts, y=[s.vel_l for s in filt],
                    pen=pg.mkPen("#42a5f5", width=2), name="Vl RPM")
            pw.plot(x=ts, y=[s.vel_r for s in filt],
                    pen=pg.mkPen("#ef5350", width=2), name="Vr RPM")
            pw.addLegend(offset=(10, 10))

    def _analyze_compensation(self):
        # Identify dead zone thresholds from all ramp data
        all_l = _steady_state_points(self._samples, _PHASES_ALL_RAMP)[0]
        dz_fwd_l = _detect_dead_zone(all_l, positive=True)  or 0.10
        dz_rev_l = abs(_detect_dead_zone(all_l, positive=False) or -0.10)
        dz_avg   = (dz_fwd_l + dz_rev_l) / 2.0

        # Gain in linear region
        act = [(d, v) for d, v in all_l
               if d > dz_fwd_l and abs(v) > VEL_DEAD_THRESHOLD]
        gain = 0.0
        if len(act) > 2:
            xs_a = np.array([p[0] for p in act])
            ys_a = np.array([p[1] for p in act])
            gain = float(np.polyfit(xs_a, ys_a, 1)[0])

        # Step response summary
        steps = _extract_steps(self._samples, _PHASE_STEPS_POS)
        delays   = [_estimate_tau(s["t_rel_s"], s["vel_l"])["delay_s"]
                    for s in steps if s["amplitude"] < 0.30]
        avg_delay = float(np.mean([d * 1000 for d in delays if d is not None])) if delays else 0.0

        # Fill param table
        rows = [
            ("DZ avant L",       f"{dz_fwd_l:.4f}"),
            ("DZ arrière L",     f"{dz_rev_l:.4f}"),
            ("DZ moyen",         f"{dz_avg:.4f}"),
            ("Hystérésis",       f"{abs(dz_fwd_l - dz_rev_l):.4f}"),
            ("Gain (RPM/unit)",  f"{gain:.1f}"),
            ("Retard moy. (ms)", f"{avg_delay:.0f}"),
            ("Échantillons",     f"{len(self._samples)}"),
            ("VEL_DEAD_THR",     f"{VEL_DEAD_THRESHOLD:.1f} RPM"),
        ]
        self._param_table.setRowCount(len(rows))
        for ri, (name, val) in enumerate(rows):
            n_item = QTableWidgetItem(name); v_item = QTableWidgetItem(val)
            n_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            v_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            v_item.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            self._param_table.setItem(ri, 0, n_item)
            self._param_table.setItem(ri, 1, v_item)

        # C code
        dz = dz_avg
        code = (
            f"/* Motor dead-zone compensation\n"
            f" * Identified dead-zone: {dz:.4f} (avg fwd={dz_fwd_l:.4f} rev={dz_rev_l:.4f})\n"
            f" * Maps drive=0 → 0, drive→±ε → ±DZ + slope.\n"
            f" * Insert in motor_control.c before MTR_SetSpeed() calls. */\n\n"
            f"#define MTR_DEAD_ZONE_FWD  {dz_fwd_l:.4f}f\n"
            f"#define MTR_DEAD_ZONE_REV  {dz_rev_l:.4f}f\n\n"
            f"static inline float MTR_CompensateDeadZone(float u)\n"
            f"{{\n"
            f"    if (u >  1e-3f) return MTR_DEAD_ZONE_FWD + (1.0f - MTR_DEAD_ZONE_FWD) * u;\n"
            f"    if (u < -1e-3f) return -MTR_DEAD_ZONE_REV + (1.0f - MTR_DEAD_ZONE_REV) * u;\n"
            f"    return 0.0f;\n"
            f"}}\n\n"
            f"/* Usage: replace MTR_SetDifferential(drive, drive) with\n"
            f"   MTR_SetDifferential(MTR_CompensateDeadZone(drive),\n"
            f"                       MTR_CompensateDeadZone(drive));  */\n"
        )
        self._code_edit.setPlainText(code)

        # Compensation curve plot
        pw = self._pw_comp; pw.clear()
        u  = np.linspace(-1.0, 1.0, 500)
        u_comp = np.where(u > 1e-3,  dz_fwd_l + (1.0 - dz_fwd_l) * u,
                 np.where(u < -1e-3, -dz_rev_l + (1.0 - dz_rev_l) * u, 0.0))
        pw.plot(x=list(u), y=list(u),      pen=pg.mkPen("#546e7a", width=2), name="identité")
        pw.plot(x=list(u), y=list(u_comp), pen=pg.mkPen("#66bb6a", width=2.5), name="compensée")
        # Mark dead zone region
        pw.addLinearRegion = lambda: None  # suppress auto-call
        for x0 in (-dz_rev_l, dz_fwd_l):
            pw.addLine(x=x0, pen=pg.mkPen("#ffd54f", width=1, style=Qt.PenStyle.DashLine))

    # ── Save / Load ───────────────────────────────────────────────────────────

    def _save_json(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Sauvegarder calibration", "", "JSON (*.json)")
        if not path:
            return
        data = {
            "type":    "motor_calib",
            "n":       len(self._samples),
            "samples": [{"ts_ms": s.ts_ms, "drive": s.drive,
                          "vel_l": s.vel_l, "vel_r": s.vel_r,
                          "phase": s.phase} for s in self._samples],
        }
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._status_lbl.setText(f"Sauvegardé → {Path(path).name}")

    def _load_json(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Charger calibration", "", "JSON (*.json)")
        if not path:
            return
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if raw.get("type") != "motor_calib":
            self._status_lbl.setText("Fichier invalide (type != motor_calib)")
            return
        self._samples = [
            CalibSample(ts_ms=s["ts_ms"], drive=s["drive"],
                        vel_l=s["vel_l"],  vel_r=s["vel_r"],
                        phase=s["phase"],  calib_active=0)
            for s in raw["samples"]
        ]
        self._analyze()
        self._stack.setCurrentIndex(1)
        self._save_btn.setEnabled(True)
        self._status_lbl.setText(f"Chargé {len(self._samples)} échantillons ← {Path(path).name}")
