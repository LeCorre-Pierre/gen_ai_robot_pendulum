"""
cbc_tuner/sweep_runner.py — Runner manuel de sweep PID.

Workflow par test :
  1. Utilisateur clique "▶ Lancer" → compte à rebours (delay_s)
  2. Gains appliqués au robot → test run (hold_s ou arrêt manuel)
  3. Moteurs coupés (gains → 0)
  4. Utilisateur note 0-5 étoiles, clique "✓ Suivant"
  5. JSON sauvegardé, test suivant chargé
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)


# ── Sélecteur d'étoiles ───────────────────────────────────────────────────────

class _StarRating(QWidget):

    rating_changed = Signal(int)

    _LABELS = {
        0: "(non noté)",
        1: "Chute immédiate",
        2: "Tient un peu",
        3: "Instable mais debout",
        4: "Bon équilibre",
        5: "Parfait",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rating = 0

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        lay.addWidget(QLabel("Score :"))

        self._btns: list[QPushButton] = []
        for i in range(1, 6):
            btn = QPushButton("☆")
            btn.setFixedSize(38, 38)
            btn.clicked.connect(lambda _, n=i: self._set(n))
            self._btns.append(btn)
            lay.addWidget(btn)

        self._desc_lbl = QLabel(self._LABELS[0])
        self._desc_lbl.setStyleSheet("color:#78909c;font-size:10px;font-family:Consolas;")
        lay.addWidget(self._desc_lbl)
        lay.addStretch()

        self._apply_style()

    def _set(self, n: int) -> None:
        self._rating = n if self._rating != n else 0
        self._apply_style()
        self.rating_changed.emit(self._rating)

    def _apply_style(self) -> None:
        for i, btn in enumerate(self._btns, 1):
            filled = i <= self._rating
            btn.setText("★" if filled else "☆")
            color = "#ffd54f" if filled else "#546e7a"
            btn.setStyleSheet(
                f"QPushButton {{ font-size:22px; background:transparent; border:none; color:{color}; }}"
                "QPushButton:hover { color:#ffd54f; }"
                "QPushButton:disabled { color:#263238; }"
            )
        self._desc_lbl.setText(self._LABELS.get(self._rating, ""))

    def rating(self) -> int:
        return self._rating

    def reset(self) -> None:
        self._rating = 0
        self._apply_style()

    def set_enabled(self, v: bool) -> None:
        for btn in self._btns:
            btn.setEnabled(v)


# ── Panneau runner ────────────────────────────────────────────────────────────

class SweepRunnerPanel(QWidget):

    gains_to_apply = Signal(float, float, float)
    sweep_complete = Signal(str)

    _IDLE    = "idle"
    _DELAY   = "delay"
    _RUNNING = "running"
    _RATING  = "rating"
    _DONE    = "done"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tests:   list[dict] = []
        self._idx:     int        = 0
        self._out_dir: str        = ""
        self._delay_s: float      = 3.0
        self._hold_s:  float      = 5.0
        self._state:   str        = self._IDLE

        self._samples:  list[dict] = []
        self._t_start:  float      = 0.0
        self._deadline: float      = 0.0

        self._tick = QTimer(interval=80)
        self._tick.timeout.connect(self._on_tick)

        self._build_ui()
        self._enter_idle()

    # ── API publique ──────────────────────────────────────────────────────────

    def load_plan(
        self,
        tests:   list[dict],
        out_dir: str,
        delay_s: float,
        hold_s:  float,
    ) -> None:
        self._tests   = list(tests)
        self._out_dir = out_dir
        self._delay_s = delay_s
        self._hold_s  = hold_s
        self._idx     = 0
        self._log.clear()
        self._enter_idle()
        self._log_append(
            f"Plan chargé : {len(tests)} tests — délai {delay_s:.1f} s — hold {hold_s:.1f} s"
        )

    def feed_imu(self, pitch: float, drive: float, t_mono: float) -> None:
        """Appelé depuis le main thread à chaque trame IMU (drive normalisé [-1, +1])."""
        color = (
            "#ef5350" if abs(pitch) > 20
            else "#ffd54f" if abs(pitch) > 8
            else "#66bb6a"
        )
        self._pitch_lbl.setText(f"{pitch:+.1f}°")
        self._pitch_lbl.setStyleSheet(
            f"font-size:36px;font-family:Consolas;font-weight:bold;color:{color};"
        )
        if self._state == self._RUNNING:
            self._samples.append({
                "t_s":   round(t_mono - self._t_start, 4),
                "pitch": round(pitch, 3),
                "drive": round(drive, 4),
            })

    # ── Construction UI ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # En-tête : test en cours
        hdr = QGroupBox("Test en cours")
        hdr.setStyleSheet("QGroupBox { font-weight:bold; font-size:11px; }")
        h_lay = QHBoxLayout(hdr)
        h_lay.setSpacing(16)

        self._progress_lbl = QLabel("—")
        self._progress_lbl.setStyleSheet("font-size:12px;font-family:Consolas;color:#90a4ae;")

        self._gains_lbl = QLabel("—")
        self._gains_lbl.setStyleSheet(
            "font-size:13px;font-family:Consolas;font-weight:bold;color:#e0e0e0;"
        )

        self._pitch_lbl = QLabel("—")
        self._pitch_lbl.setFixedWidth(110)
        self._pitch_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._pitch_lbl.setStyleSheet(
            "font-size:36px;font-family:Consolas;font-weight:bold;color:#546e7a;"
        )

        h_lay.addWidget(self._progress_lbl)
        h_lay.addWidget(self._gains_lbl, stretch=1)
        h_lay.addWidget(QLabel("pitch :"))
        h_lay.addWidget(self._pitch_lbl)
        root.addWidget(hdr)

        # Compte à rebours
        cd_grp = QGroupBox("Compte à rebours")
        cd_grp.setStyleSheet("QGroupBox { font-weight:bold; font-size:11px; }")
        cd_lay = QHBoxLayout(cd_grp)
        cd_lay.setSpacing(16)

        self._cd_lbl = QLabel("—")
        self._cd_lbl.setFixedWidth(100)
        self._cd_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cd_lbl.setStyleSheet(
            "font-size:48px;font-family:Consolas;font-weight:bold;color:#546e7a;"
        )

        self._cd_msg = QLabel("")
        self._cd_msg.setStyleSheet("font-size:11px;color:#78909c;")
        self._cd_msg.setWordWrap(True)

        cd_lay.addWidget(self._cd_lbl)
        cd_lay.addWidget(self._cd_msg, stretch=1)
        root.addWidget(cd_grp)

        # Boutons d'action
        btn_grp = QGroupBox("Actions")
        btn_grp.setStyleSheet("QGroupBox { font-weight:bold; font-size:11px; }")
        b_lay = QHBoxLayout(btn_grp)
        b_lay.setSpacing(8)

        def _btn(txt: str, bg: str | None = None, width: int = 0) -> QPushButton:
            b = QPushButton(txt)
            b.setFixedHeight(36)
            if width:
                b.setFixedWidth(width)
            if bg:
                b.setStyleSheet(
                    f"QPushButton {{ background:{bg}; color:white; font-weight:bold; font-size:12px; }}"
                    f"QPushButton:hover {{ background:{bg}cc; }}"
                    "QPushButton:disabled { background:#37474f; color:#607d8b; }"
                )
            else:
                b.setStyleSheet(
                    "QPushButton { background:#37474f; color:#90a4ae; font-size:11px; }"
                    "QPushButton:hover { background:#455a64; color:#e0e0e0; }"
                    "QPushButton:disabled { background:#263238; color:#455a64; }"
                )
            return b

        self._launch_btn  = _btn("▶  Lancer ce test",   "#1565c0", 180)
        self._stop_btn    = _btn("⏹  Terminer le test",  "#b71c1c", 180)
        self._next_btn    = _btn("✓  Test suivant",      "#1b5e20", 150)
        self._skip_btn    = _btn("Skip →",               None,       80)
        self._prev_btn    = _btn("↺  Retour",            "#e65100", 100)

        self._launch_btn.clicked.connect(self._on_launch)
        self._stop_btn.clicked.connect(self._on_stop_test)
        self._next_btn.clicked.connect(self._on_next)
        self._skip_btn.clicked.connect(self._on_skip)
        self._prev_btn.clicked.connect(self._on_prev)

        b_lay.addWidget(self._launch_btn)
        b_lay.addWidget(self._stop_btn)
        b_lay.addSpacing(12)
        b_lay.addWidget(self._next_btn)
        b_lay.addWidget(self._skip_btn)
        b_lay.addStretch()
        b_lay.addWidget(self._prev_btn)
        root.addWidget(btn_grp)

        # Notation étoiles
        rat_grp = QGroupBox("Notation du test")
        rat_grp.setStyleSheet("QGroupBox { font-weight:bold; font-size:11px; }")
        r_lay = QVBoxLayout(rat_grp)
        r_lay.setSpacing(4)

        self._stars = _StarRating()
        r_lay.addWidget(self._stars)

        self._note_lbl = QLabel("")
        self._note_lbl.setStyleSheet("color:#90a4ae;font-size:10px;font-family:Consolas;")
        r_lay.addWidget(self._note_lbl)
        root.addWidget(rat_grp)

        # Journal
        log_grp = QGroupBox("Journal")
        log_grp.setStyleSheet("QGroupBox { font-weight:bold; font-size:11px; }")
        l_lay = QVBoxLayout(log_grp)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(170)
        self._log.setStyleSheet(
            "background:#1a1a2e;color:#90a4ae;font-size:10px;font-family:Consolas;"
        )
        l_lay.addWidget(self._log)
        root.addWidget(log_grp)

    # ── Machine d'états ───────────────────────────────────────────────────────

    def _enter_idle(self) -> None:
        self._state = self._IDLE
        self._tick.stop()
        self._samples.clear()

        no_plan = not self._tests
        done    = self._idx >= len(self._tests)

        if no_plan:
            self._progress_lbl.setText("Aucun plan chargé")
            self._gains_lbl.setText("→ Configurer un plan dans l'onglet Plan")
            self._cd_lbl.setText("—")
            self._cd_lbl.setStyleSheet(
                "font-size:48px;font-family:Consolas;font-weight:bold;color:#546e7a;"
            )
            self._cd_msg.setText("")
        elif done:
            self._progress_lbl.setText(f"Sweep terminé  —  {len(self._tests)} tests")
            self._gains_lbl.setText("Tous les tests effectués")
            self._cd_lbl.setText("✓")
            self._cd_lbl.setStyleSheet(
                "font-size:48px;font-family:Consolas;font-weight:bold;color:#66bb6a;"
            )
            self._cd_msg.setText("")
            self._state = self._DONE
        else:
            t = self._tests[self._idx]
            self._progress_lbl.setText(f"Test {self._idx + 1} / {len(self._tests)}")
            self._gains_lbl.setText(
                f"Kp={t['kp']:.4f}   Ki={t['ki']:.4f}   Kd={t['kd']:.5f}"
            )
            self._cd_lbl.setText(f"{self._delay_s:.0f}s")
            self._cd_lbl.setStyleSheet(
                "font-size:48px;font-family:Consolas;font-weight:bold;color:#546e7a;"
            )
            self._cd_msg.setText(
                "Cliquez ▶ Lancer pour démarrer le compte à rebours,\n"
                "puis positionnez le robot avant que le décompte atteigne 0."
            )

        active = not no_plan and not done
        self._launch_btn.setEnabled(active)
        self._stop_btn.setEnabled(False)
        self._next_btn.setEnabled(False)
        self._skip_btn.setEnabled(active)
        self._prev_btn.setEnabled(self._idx > 0 and not no_plan)
        self._stars.set_enabled(False)
        self._stars.reset()
        self._note_lbl.setText("")

    def _enter_delay(self) -> None:
        self._state    = self._DELAY
        self._deadline = time.monotonic() + self._delay_s
        self._samples.clear()

        self._launch_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)
        self._next_btn.setEnabled(False)
        self._skip_btn.setEnabled(False)
        self._prev_btn.setEnabled(False)
        self._stars.set_enabled(False)
        self._stars.reset()
        self._cd_msg.setText(
            "Positionnez le robot — les gains seront appliqués au compte à rebours 0"
        )
        self._tick.start()

    def _enter_running(self) -> None:
        self._state    = self._RUNNING
        self._t_start  = time.monotonic()
        self._deadline = self._t_start + self._hold_s

        t = self._tests[self._idx]
        self.gains_to_apply.emit(t["kp"], t["ki"], t["kd"])
        self._log_append(
            f"[{self._idx + 1}/{len(self._tests)}]"
            f"  Kp={t['kp']:.4f}  Ki={t['ki']:.4f}  Kd={t['kd']:.5f}  → gains envoyés"
        )
        self._stop_btn.setEnabled(True)
        self._cd_lbl.setStyleSheet(
            "font-size:48px;font-family:Consolas;font-weight:bold;color:#66bb6a;"
        )
        self._cd_msg.setText(
            f"Test en cours — cliquez ⏹ Terminer ou attendez {self._hold_s:.0f} s"
        )

    def _enter_rating(self) -> None:
        self._state = self._RATING
        self._tick.stop()

        self.gains_to_apply.emit(0.0, 0.0, 0.0)
        self._log_append("    Gains → 0 (moteurs coupés)")

        self._stop_btn.setEnabled(False)
        self._next_btn.setEnabled(True)
        self._skip_btn.setEnabled(False)
        self._prev_btn.setEnabled(True)
        self._stars.set_enabled(True)

        self._cd_lbl.setText("★")
        self._cd_lbl.setStyleSheet(
            "font-size:48px;font-family:Consolas;font-weight:bold;color:#ffd54f;"
        )
        self._cd_msg.setText("Notez le test puis cliquez ✓ Test suivant")
        n_drive = sum(1 for s in self._samples if "drive" in s)
        self._note_lbl.setText(
            f"Échantillons : {len(self._samples)}  (drive : {n_drive})"
        )

    # ── Timer ─────────────────────────────────────────────────────────────────

    def _on_tick(self) -> None:
        now = time.monotonic()

        if self._state == self._DELAY:
            remaining = self._deadline - now
            if remaining <= 0:
                self._cd_lbl.setText("GO")
                self._cd_lbl.setStyleSheet(
                    "font-size:48px;font-family:Consolas;font-weight:bold;color:#66bb6a;"
                )
                self._enter_running()
            else:
                col = (
                    "#ef5350" if remaining < 1.5
                    else "#ffd54f" if remaining < 3.0
                    else "#42a5f5"
                )
                self._cd_lbl.setText(f"{remaining:.1f}s")
                self._cd_lbl.setStyleSheet(
                    f"font-size:48px;font-family:Consolas;font-weight:bold;color:{col};"
                )

        elif self._state == self._RUNNING:
            remaining = self._deadline - now
            elapsed   = now - self._t_start
            col = "#ef5350" if remaining < 2 else "#66bb6a"
            self._cd_lbl.setText(f"{remaining:.1f}s")
            self._cd_lbl.setStyleSheet(
                f"font-size:48px;font-family:Consolas;font-weight:bold;color:{col};"
            )
            self._cd_msg.setText(
                f"Test en cours — {elapsed:.1f} s / {self._hold_s:.0f} s"
            )
            if remaining <= 0:
                self._enter_rating()

    # ── Boutons ───────────────────────────────────────────────────────────────

    def _on_launch(self) -> None:
        if self._idx < len(self._tests):
            self._enter_delay()

    def _on_stop_test(self) -> None:
        self._enter_rating()

    def _on_next(self) -> None:
        if self._idx >= len(self._tests):
            return
        self._save_current()
        self._idx += 1
        self._enter_idle()
        if self._idx >= len(self._tests):
            self._log_append(f"=== Sweep terminé — {len(self._tests)} tests ===")
            self.sweep_complete.emit(self._out_dir)

    def _on_skip(self) -> None:
        self._log_append(f"[{self._idx + 1}/{len(self._tests)}]  skippé")
        self._idx += 1
        self._enter_idle()
        if self._idx >= len(self._tests):
            self._log_append(f"=== Sweep terminé — {len(self._tests)} tests ===")
            self.sweep_complete.emit(self._out_dir)

    def _on_prev(self) -> None:
        if self._idx > 0:
            self._idx -= 1
        self._enter_idle()

    # ── Sauvegarde ────────────────────────────────────────────────────────────

    def _save_current(self) -> None:
        if self._idx >= len(self._tests):
            return
        t     = self._tests[self._idx]
        score = self._stars.rating()
        samps = list(self._samples)

        pitches = [s["pitch"] for s in samps]
        drives  = [s["drive"] for s in samps if "drive" in s]
        if pitches:
            arr     = np.array(pitches, dtype=float)
            rms     = float(np.sqrt(np.mean(arr ** 2)))
            max_abs = float(np.max(np.abs(arr)))
        else:
            rms = max_abs = float("nan")

        if drives:
            drv_arr   = np.array(drives, dtype=float)
            rms_motor = float(np.sqrt(np.mean(drv_arr ** 2)))
        else:
            rms_motor = float("nan")

        record = {
            "trial": {
                "id":     t["id"],
                "kp":     t["kp"],
                "ki":     t["ki"],
                "kd":     t["kd"],
                "hold_s": self._hold_s,
            },
            "result":  "rated",
            "score":   score,
            "metrics": {
                "rms_deg":        round(rms, 4)       if not math.isnan(rms)       else None,
                "max_abs_deg":    round(max_abs, 4)   if not math.isnan(max_abs)   else None,
                "rms_motor":      round(rms_motor, 4) if not math.isnan(rms_motor) else None,
                "settling_time_s": None,
                "saturation_pct":  None,
            },
            "samples": samps,
        }

        ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{ts}_kp{t['kp']:.3f}_ki{t['ki']:.3f}_kd{t['kd']:.4f}.json"
        out   = Path(self._out_dir) / fname if self._out_dir else Path(fname)
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(record, indent=2), encoding="utf-8")
            stars_str  = "★" * score + "☆" * (5 - score)
            rms_txt    = f"{rms:.2f}°"      if not math.isnan(rms)       else "—"
            motor_txt  = f"{rms_motor:.3f}" if not math.isnan(rms_motor) else "—"
            self._log_append(
                f"    {stars_str}  rms={rms_txt}  drive_rms={motor_txt}  → {out.name}"
            )
        except Exception as exc:
            self._log_append(f"    ⚠ Erreur sauvegarde : {exc}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log_append(self, msg: str) -> None:
        self._log.append(msg)
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())
