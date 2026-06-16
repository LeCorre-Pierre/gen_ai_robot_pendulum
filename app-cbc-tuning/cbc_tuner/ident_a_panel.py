"""
ident_a_panel.py — pole 'a' (upright unstable pendulum) identification panel.

Method: free-fall trial. Robot upright, mode identification active (CBC
bypassed, drive parked at 0 via VCP_TYPE_CMD_SET_DRIVE — see ident_k_panel),
held at a small angle then released. With no control, θ̈ = a²·θ (unstable
pendulum), so θ and θ̇ both grow without bound. Timing of the release and
the initial angle/velocity don't matter — both are absorbed into the energy
identity derived below — so trials can be repeated freely and pooled.

Identification trick (avoids any numerical differentiation): multiplying
θ̈ = a²·θ by θ̇ and integrating gives the conserved-energy-style relation

    θ̇² = a²·θ² + C        (C depends on the trial's initial conditions)

θ and θ̇ are both measured directly (pitch + gyro), no derivative needed.
A single trial gives one (θ², θ̇²) cloud with an unknown offset C; centering
each trial by its own mean removes C, so all trials can be pooled into one
regression for a² — precision improves as more trials are added.

Comparison: a² = g/L for a point-mass pendulum of height L (CoM above the
wheel axle) — entering L from a physical measurement gives a theoretical a
to sanity-check the fitted value against.
"""
from __future__ import annotations

import json
import math
import time as _time
from datetime import datetime
from pathlib import Path

import numpy as np
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)
import pyqtgraph as pg

_G = 9.81
_TRIAL_COLORS = ["#ef5350", "#ffa726", "#66bb6a", "#29b6f6", "#ab47bc",
                  "#ec407a", "#26c6da", "#d4e157"]


class IdentAPanel(QWidget):
    send_drive = Signal(float)  # direct drive [-1..+1] → gui._send_drive
    send_sp    = Signal(int)    # SP(0) used only to exit direct-drive mode on stop

    def __init__(self, parent=None):
        super().__init__(parent)

        self._running = False
        self._samples: list[tuple[float, float, float]] = []  # (t, pitch_deg, rate_dps)
        self._trials: list[dict] = []   # each: {"t":, "theta_rad":, "omega_rad":}
        self._last_result: dict | None = None
        self._t_start = 0.0

        self._build_ui()

        self._plot_timer = QTimer(self, interval=40)
        self._plot_timer.timeout.connect(self._refresh_live_plot)

    # ── Public API ────────────────────────────────────────────────────────────

    def feed_imu(self, pitch: float, drive_pct: float, pitch_rate: float):
        self._lbl_pitch.setText(f"{pitch:+.2f} °")
        self._lbl_rate.setText(f"{pitch_rate:+.1f} °/s")

        if not self._running:
            return
        now = _time.monotonic() - self._t_start
        self._samples.append((now, pitch, pitch_rate))
        self._n_lbl.setText(f"{len(self._samples)} pts")

        angle_max = self._angle_spin.value()
        if abs(pitch) >= angle_max:
            self._stop()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)
        root.addWidget(self._build_left(), stretch=0)
        root.addWidget(self._build_right(), stretch=1)

    def _build_left(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(280)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(self._build_mode_grp())
        lay.addWidget(self._build_capture_grp())
        lay.addWidget(self._build_telem_grp())
        lay.addWidget(self._build_result_grp())
        lay.addWidget(self._build_compare_grp())
        lay.addStretch()
        return w

    def _build_mode_grp(self) -> QGroupBox:
        grp = QGroupBox("Mode identification  (boucle équilibre)")
        grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        lay = QVBoxLayout(grp)

        self._mode_btn = QPushButton("🔓 Entrer en mode identification")
        self._mode_btn.setCheckable(True)
        self._mode_btn.setFixedHeight(32)
        self._mode_btn.setStyleSheet(
            "QPushButton{background:#37474f;color:white;font-weight:bold;}"
            "QPushButton:checked{background:#ab47bc;}"
            "QPushButton:hover{background:#455a64;}"
        )
        self._mode_btn.toggled.connect(self._on_mode_toggle)
        lay.addWidget(self._mode_btn)

        hint = QLabel(
            "Robot à l'endroit (pas à l'envers).\n"
            "⚠ Le robot va tomber SANS contrôle une fois lâché —\n"
            "tiens-toi prêt à le rattraper ou pose un tapis.\n"
            "Ne sortir qu'une fois le robot reposé/tenu stable —\n"
            "la sortie réactive immédiatement l'équilibre."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size:9px;color:#ff7043;font-family:Consolas;")
        lay.addWidget(hint)

        return grp

    def _on_mode_toggle(self, checked: bool):
        if checked:
            self.send_drive.emit(0.0)   # enters ctrl_mode=2, drive parked at 0
            self._mode_btn.setText("🔒 Sortir du mode identification")
            self._start_btn.setEnabled(True)
        else:
            self._stop()
            self.send_sp.emit(0)        # exits to normal balance (ctrl_mode=0)
            self._mode_btn.setText("🔓 Entrer en mode identification")
            self._start_btn.setEnabled(False)

    def _build_capture_grp(self) -> QGroupBox:
        grp = QGroupBox("Essai de chute libre")
        grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        lay = QVBoxLayout(grp)
        lay.setSpacing(6)

        def _row(label, widget):
            h = QHBoxLayout()
            h.setContentsMargins(0, 0, 0, 0)
            l = QLabel(label)
            l.setStyleSheet("font-size:10px;color:#90a4ae;")
            l.setFixedWidth(120)
            h.addWidget(l)
            h.addWidget(widget, stretch=1)
            lay.addLayout(h)

        self._dur_spin = QDoubleSpinBox()
        self._dur_spin.setRange(0.3, 5.0)
        self._dur_spin.setValue(1.0)
        self._dur_spin.setDecimals(1)
        self._dur_spin.setSingleStep(0.1)
        self._dur_spin.setSuffix(" s")
        self._dur_spin.setToolTip("Durée max de capture (arrêt auto si atteinte avant l'angle max)")
        _row("Durée max", self._dur_spin)

        self._angle_spin = QDoubleSpinBox()
        self._angle_spin.setRange(10.0, 45.0)
        self._angle_spin.setValue(30.0)
        self._angle_spin.setDecimals(0)
        self._angle_spin.setSuffix(" °")
        self._angle_spin.setToolTip(
            "Angle au-delà duquel l'approximation petit angle n'est plus valide — "
            "arrête la capture et exclut les points au-delà"
        )
        _row("Angle max valide", self._angle_spin)

        self._status_lbl = QLabel("⚫ Arrêté")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setStyleSheet(
            "font-size:13px;font-family:Consolas;font-weight:bold;"
            "color:#546e7a;padding:4px;"
        )
        lay.addWidget(self._status_lbl)

        btn_row = QHBoxLayout()
        self._start_btn = QPushButton("▶ Démarrer essai")
        self._start_btn.setFixedHeight(30)
        self._start_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:white;font-weight:bold;}"
            "QPushButton:hover{background:#43a047;}"
            "QPushButton:disabled{background:#37474f;color:#546e7a;}"
        )
        self._start_btn.clicked.connect(self._start)
        self._start_btn.setEnabled(False)   # requires mode identification active
        btn_row.addWidget(self._start_btn)

        self._stop_btn = QPushButton("⏹ STOP")
        self._stop_btn.setFixedHeight(30)
        self._stop_btn.setStyleSheet(
            "QPushButton{background:#c62828;color:white;font-weight:bold;}"
            "QPushButton:hover{background:#ef5350;}"
        )
        self._stop_btn.clicked.connect(self._stop)
        btn_row.addWidget(self._stop_btn)
        lay.addLayout(btn_row)

        clr_btn = QPushButton("🗑 Effacer tous les essais")
        clr_btn.setFixedHeight(22)
        clr_btn.clicked.connect(self._clear_all)
        lay.addWidget(clr_btn)

        self._n_lbl = QLabel("0 pts")
        self._n_lbl.setStyleSheet("font-size:9px;color:#546e7a;font-family:Consolas;")
        lay.addWidget(self._n_lbl)

        return grp

    def _build_telem_grp(self) -> QGroupBox:
        grp = QGroupBox("Télémétrie")
        grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        lay = QVBoxLayout(grp)
        lay.setSpacing(2)
        self._lbl_pitch = self._trow(lay, "Pitch",      "°",   "#ef5350", "16px")
        self._lbl_rate  = self._trow(lay, "pitch_rate", "°/s", "#ffd54f", "11px")
        return grp

    @staticmethod
    def _trow(lay, label, unit, col, sz) -> QLabel:
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        l = QLabel(label)
        l.setStyleSheet("font-size:10px;color:#78909c;font-family:Consolas;")
        l.setFixedWidth(90)
        v = QLabel("—")
        v.setStyleSheet(f"font-size:{sz};font-family:Consolas;font-weight:bold;color:{col};")
        v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        u = QLabel(unit)
        u.setStyleSheet("font-size:9px;color:#546e7a;")
        u.setFixedWidth(32)
        h.addWidget(l); h.addWidget(v, stretch=1); h.addWidget(u)
        lay.addLayout(h)
        return v

    def _build_result_grp(self) -> QGroupBox:
        grp = QGroupBox("Résultat cumulé  :  θ̇² = a²·θ² + C")
        grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        lay = QVBoxLayout(grp)

        self._a_lbl = QLabel("a = —")
        self._a_lbl.setStyleSheet(
            "font-size:20px;font-family:Consolas;font-weight:bold;color:#66bb6a;"
        )
        lay.addWidget(self._a_lbl)

        self._r2_lbl = QLabel("R² = —   essais = 0   pts = 0")
        self._r2_lbl.setStyleSheet("font-size:10px;font-family:Consolas;color:#90a4ae;")
        lay.addWidget(self._r2_lbl)

        self._q_lbl = QLabel("")
        self._q_lbl.setStyleSheet("font-size:10px;font-family:Consolas;")
        self._q_lbl.setWordWrap(True)
        lay.addWidget(self._q_lbl)

        self._save_btn = QPushButton("💾 Sauvegarder JSON")
        self._save_btn.setFixedHeight(26)
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_json)
        lay.addWidget(self._save_btn)

        return grp

    def _build_compare_grp(self) -> QGroupBox:
        grp = QGroupBox("Comparaison  —  mesure physique du centre de masse")
        grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        lay = QVBoxLayout(grp)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        l = QLabel("L (hauteur CoM)")
        l.setStyleSheet("font-size:10px;color:#90a4ae;")
        l.setFixedWidth(110)
        row.addWidget(l)
        self._L_spin = QDoubleSpinBox()
        self._L_spin.setRange(1.0, 50.0)
        self._L_spin.setValue(18.0)
        self._L_spin.setDecimals(1)
        self._L_spin.setSuffix(" cm")
        self._L_spin.setToolTip("Distance mesurée physiquement entre l'axe des roues et le centre de masse")
        self._L_spin.valueChanged.connect(self._update_compare)
        row.addWidget(self._L_spin, stretch=1)
        lay.addLayout(row)

        self._compare_lbl = QLabel("a théorique = —")
        self._compare_lbl.setWordWrap(True)
        self._compare_lbl.setStyleSheet("font-size:10px;font-family:Consolas;color:#78909c;")
        lay.addWidget(self._compare_lbl)

        return grp

    # ── Right column : plots ──────────────────────────────────────────────────

    def _build_right(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        ts_grp = QGroupBox("Essai en cours  —  pitch  et  pitch_rate")
        ts_grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        tl = QVBoxLayout(ts_grp)
        self._pw_ts = pg.PlotWidget()
        self._pw_ts.showGrid(x=True, y=True, alpha=0.25)
        self._pw_ts.setLabel("bottom", "t (s)  depuis le début de l'essai")
        self._pw_ts.addLegend(offset=(10, 10))
        self._pw_ts.addLine(y=0, pen=pg.mkPen("#37474f", width=1, style=Qt.PenStyle.DashLine))
        self._c_pitch = self._pw_ts.plot(pen=pg.mkPen("#ef5350", width=2), name="pitch (°)")
        self._c_rate  = self._pw_ts.plot(pen=pg.mkPen("#ffd54f", width=2), name="pitch_rate (°/s)")
        tl.addWidget(self._pw_ts)
        lay.addWidget(ts_grp, stretch=1)

        sc_grp = QGroupBox(
            "Tous les essais (centrés)  —  θ̇²  vs  θ²   (pente commune = a²)"
        )
        sc_grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        sl = QVBoxLayout(sc_grp)
        self._pw_sc = pg.PlotWidget()
        self._pw_sc.setLabel("left",   "θ̇² centré  ((°/s)²)")
        self._pw_sc.setLabel("bottom", "θ² centré  ((°)²)")
        self._pw_sc.showGrid(x=True, y=True, alpha=0.2)
        self._pw_sc.addLine(x=0, pen=pg.mkPen("#37474f", width=1, style=Qt.PenStyle.DashLine))
        self._pw_sc.addLine(y=0, pen=pg.mkPen("#37474f", width=1, style=Qt.PenStyle.DashLine))
        self._sc_fit = self._pw_sc.plot(pen=pg.mkPen("#66bb6a", width=2))
        self._sc_trial_items: list[pg.PlotDataItem] = []
        sl.addWidget(self._pw_sc)
        lay.addWidget(sc_grp, stretch=1)

        return w

    # ── Capture control ──────────────────────────────────────────────────────

    def _start(self):
        if self._running or not self._mode_btn.isChecked():
            return
        self._running = True
        self._samples.clear()
        self._t_start = _time.monotonic()

        self._plot_timer.start()
        QTimer.singleShot(int(self._dur_spin.value() * 1000), self._stop)

        self._start_btn.setEnabled(False)
        self._status_lbl.setText("🟢 Capture…  lâche le robot !")
        self._status_lbl.setStyleSheet(
            "font-size:13px;font-family:Consolas;font-weight:bold;color:#66bb6a;padding:4px;"
        )

    def _stop(self):
        if not self._running:
            return
        self._running = False
        self._plot_timer.stop()
        self._start_btn.setEnabled(self._mode_btn.isChecked())

        n = len(self._samples)
        angle_max = self._angle_spin.value()
        added = False
        if n >= 10:
            arr   = np.array(self._samples, dtype=float)
            mask  = np.abs(arr[:, 1]) <= angle_max
            if int(mask.sum()) >= 10:
                self._trials.append({
                    "t":         arr[mask, 0],
                    "theta_rad": np.deg2rad(arr[mask, 1]),
                    "omega_rad": np.deg2rad(arr[mask, 2]),
                })
                added = True

        if added:
            self._status_lbl.setText(f"⏹ Essai #{len(self._trials)} ajouté")
            self._status_lbl.setStyleSheet(
                "font-size:13px;font-family:Consolas;font-weight:bold;color:#42a5f5;padding:4px;"
            )
            self._recompute_fit()
        else:
            self._status_lbl.setText("⚠ Essai trop court — ignoré")
            self._status_lbl.setStyleSheet(
                "font-size:13px;font-family:Consolas;font-weight:bold;color:#ffd54f;padding:4px;"
            )

    def _clear_all(self):
        self._trials.clear()
        self._samples.clear()
        self._last_result = None
        self._save_btn.setEnabled(False)
        self._n_lbl.setText("0 pts")
        self._a_lbl.setText("a = —")
        self._a_lbl.setStyleSheet(
            "font-size:20px;font-family:Consolas;font-weight:bold;color:#66bb6a;"
        )
        self._r2_lbl.setText("R² = —   essais = 0   pts = 0")
        self._q_lbl.setText("")
        self._c_pitch.setData([], [])
        self._c_rate.setData([], [])
        self._sc_fit.setData([], [])
        for item in self._sc_trial_items:
            self._pw_sc.removeItem(item)
        self._sc_trial_items.clear()
        self._update_compare()

    # ── Live plot ─────────────────────────────────────────────────────────────

    def _refresh_live_plot(self):
        n = len(self._samples)
        if n < 2:
            return
        arr = np.array(self._samples, dtype=float)
        self._c_pitch.setData(x=list(arr[:, 0]), y=list(arr[:, 1]))
        self._c_rate.setData(x=list(arr[:, 0]), y=list(arr[:, 2]))

    # ── Pooled fit across all trials ────────────────────────────────────────────

    def _recompute_fit(self):
        if not self._trials:
            return

        xs, ys = [], []
        for trial in self._trials:
            theta2 = trial["theta_rad"] ** 2
            omega2 = trial["omega_rad"] ** 2
            xs.append(theta2 - theta2.mean())
            ys.append(omega2 - omega2.mean())
        X = np.concatenate(xs)
        Y = np.concatenate(ys)
        n_total  = len(X)
        n_trials = len(self._trials)

        Sxx = float(np.sum(X * X))
        if Sxx < 1e-12:
            return
        Sxy = float(np.sum(X * Y))
        a2  = Sxy / Sxx

        resid  = Y - a2 * X
        SS_res = float(np.sum(resid ** 2))
        SS_tot = float(np.sum(Y ** 2))
        r2     = max(0.0, 1.0 - SS_res / max(SS_tot, 1e-12))

        dof   = max(n_total - n_trials - 1, 1)
        sigma2 = SS_res / dof
        se_a2  = math.sqrt(sigma2 / Sxx)

        if a2 > 0:
            a_rad   = math.sqrt(a2)
            sigma_a = se_a2 / (2.0 * a_rad)
        else:
            a_rad   = float("nan")
            sigma_a = float("nan")

        if math.isnan(a_rad):
            self._a_lbl.setText("a = — (pente négative, non physique)")
            self._a_lbl.setStyleSheet(
                "font-size:20px;font-family:Consolas;font-weight:bold;color:#ef5350;"
            )
            q_txt, qc = "⚠ a² < 0 — pas un pendule inversé instable ? robot bien à l'endroit ?", "#ef5350"
        else:
            col = "#66bb6a" if r2 > 0.85 else "#ffd54f" if r2 > 0.5 else "#ef5350"
            self._a_lbl.setText(f"a = {a_rad:.3f}  ±  {sigma_a:.3f}  rad/s")
            self._a_lbl.setStyleSheet(
                f"font-size:20px;font-family:Consolas;font-weight:bold;color:{col};"
            )
            if r2 < 0.5:
                q_txt, qc = "⚠ R² faible — bruit ou angle max trop petit", "#ef5350"
            elif sigma_a / a_rad > 0.15:
                q_txt, qc = "⚠ incertitude élevée — ajouter des essais", "#ffd54f"
            else:
                q_txt, qc = "✓ OK", "#66bb6a"

        self._r2_lbl.setText(f"R² = {r2:.3f}   essais = {n_trials}   pts = {n_total}")
        self._q_lbl.setText(q_txt)
        self._q_lbl.setStyleSheet(f"font-size:10px;font-family:Consolas;color:{qc};")

        self._last_result = {
            "a_rad_s":       round(a_rad, 4) if not math.isnan(a_rad) else None,
            "a_sigma_rad_s": round(sigma_a, 4) if not math.isnan(sigma_a) else None,
            "R2":            round(r2, 4),
            "n_trials":      n_trials,
            "n_pts":         n_total,
            "quality":       q_txt,
        }
        self._save_btn.setEnabled(True)
        self._update_compare()
        self._refresh_scatter(a2)

    def _refresh_scatter(self, a2: float):
        for item in self._sc_trial_items:
            self._pw_sc.removeItem(item)
        self._sc_trial_items.clear()

        x_all = []
        for i, trial in enumerate(self._trials):
            theta2_deg = np.rad2deg(trial["theta_rad"]) ** 2
            omega2_deg = np.rad2deg(trial["omega_rad"]) ** 2
            xc = theta2_deg - theta2_deg.mean()
            yc = omega2_deg - omega2_deg.mean()
            x_all.append(xc)
            color = _TRIAL_COLORS[i % len(_TRIAL_COLORS)]
            item = self._pw_sc.plot(
                x=list(xc), y=list(yc), pen=None, symbol="o", symbolSize=5,
                symbolBrush=pg.mkBrush(color + "90"), symbolPen=None,
            )
            self._sc_trial_items.append(item)

        if x_all:
            # a² is the same ratio in deg²/deg² as in rad²/rad² (common scale
            # factor cancels), so the fit line uses a2 directly here.
            x_span = np.concatenate(x_all)
            x_line = np.linspace(float(x_span.min()), float(x_span.max()), 2)
            self._sc_fit.setData(x=list(x_line), y=list(a2 * x_line))

    def _update_compare(self):
        L_m   = self._L_spin.value() / 100.0
        a_theo = math.sqrt(_G / L_m)
        if self._last_result and self._last_result.get("a_rad_s") is not None:
            a_meas   = self._last_result["a_rad_s"]
            diff_pct = (a_meas - a_theo) / a_theo * 100.0
            self._compare_lbl.setText(
                f"a théorique = {a_theo:.3f} rad/s  (L={self._L_spin.value():.1f} cm)\n"
                f"a mesuré     = {a_meas:.3f} rad/s   →   écart = {diff_pct:+.1f} %"
            )
        else:
            self._compare_lbl.setText(
                f"a théorique = {a_theo:.3f} rad/s  (L={self._L_spin.value():.1f} cm)\n"
                f"a mesuré     = —"
            )

    # ── JSON export ───────────────────────────────────────────────────────────

    def _save_json(self):
        if not self._last_result:
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"ident_a_{ts}.json"
        default_dir  = str(Path(__file__).parent.parent / "sweeps")

        path, _ = QFileDialog.getSaveFileName(
            self, "Sauvegarder résultat identification a",
            str(Path(default_dir) / default_name),
            "JSON files (*.json)",
        )
        if not path:
            return

        L_m = self._L_spin.value() / 100.0
        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "type": "ident_a",
            "parameters": {
                "duree_max_s":     round(self._dur_spin.value(), 2),
                "angle_max_deg":   round(self._angle_spin.value(), 1),
                "L_com_cm":        round(self._L_spin.value(), 1),
                "a_theorique_rad_s": round(math.sqrt(_G / L_m), 4),
            },
            "results": self._last_result,
            "trials": [
                {
                    "t_s":         [round(float(v), 4) for v in trial["t"]],
                    "theta_rad":   [round(float(v), 5) for v in trial["theta_rad"]],
                    "omega_rad_s": [round(float(v), 5) for v in trial["omega_rad"]],
                }
                for trial in self._trials
            ],
        }
        Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
