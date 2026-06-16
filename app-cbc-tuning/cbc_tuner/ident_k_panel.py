"""
ident_k_panel.py — K (actuator gain) identification panel.

Excitation: square/sine wave direct drive command (configurable amplitude +
half-period). Sent via VCP_TYPE_CMD_SET_DRIVE (0x29), which drives both
wheels identically and bypasses the balance loop entirely (ctrl_mode=2) —
so 'u' is a true open-loop input.

Identification method — sinusoidal (frequency-response) fit, not point-wise
OLS: the chassis pitch dynamics generally include a phase lag (sensor +
mechanical inertia), so comparing θ̈(t) to u(t) at equal time index scrambles
the data (clean periodic signal in time → patternless scatter). Since the
excitation is a single known frequency ω, the steady-state response is
fitted directly as  pitch_rate(t) ≈ p·sin(ωt) + q·cos(ωt) + offset.
For the assumed model  θ̈ = K·u + a·θ + c  (a·θ, c negligible / absorbed by
offset), the response amplitude  R = √(p²+q²)  relates to K by
R = |K|·A_u/ω — independent of any phase lag, since a lag only rotates the
phasor (p,q), it doesn't change its magnitude. The phase ψ = atan2(q,p) is
reported separately as a diagnostic (ideal value −90° for a pure K·u term;
deviation from −90° indicates extra delay/dynamics).
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
    QComboBox, QDoubleSpinBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)
import pyqtgraph as pg

class IdentKPanel(QWidget):
    send_drive = Signal(float)  # direct drive [-1..+1] → gui._send_drive
    send_sp    = Signal(int)    # SP(0) used only to exit direct-drive mode on stop

    def __init__(self, parent=None):
        super().__init__(parent)

        self._running    = False
        self._phase_pos  = True

        # (t_recv, pitch_deg, drive_norm, pitch_rate_dps)
        self._samples: list[tuple[float, float, float, float]] = []
        self._prev_rate  = 0.0
        self._last_imu_t = 0.0
        self._last_result: dict | None = None  # stores last valid regression
        self._t_start    = 0.0
        self._current_drive = 0.0

        self._build_ui()

        # Square-wave generator
        self._sw_timer = QTimer(self, singleShot=False)
        self._sw_timer.timeout.connect(self._toggle_phase)

        # Resend the current drive at 4 Hz so a half-period longer than the
        # firmware's no-command hold window doesn't get cut short to 0.
        self._ka_timer = QTimer(self, interval=250)
        self._ka_timer.timeout.connect(self._keepalive)

        # Sine wave generator at 50 Hz — also acts as keep-alive
        self._sine_timer = QTimer(self, interval=20)
        self._sine_timer.timeout.connect(self._sine_tick)

        # Regression refresh while running
        self._reg_timer = QTimer(self, interval=800)
        self._reg_timer.timeout.connect(self._update_regression)

        # Plot refresh at ~25 Hz
        self._plot_timer = QTimer(self, interval=40)
        self._plot_timer.timeout.connect(self._refresh_plot)

    # ── Public API ────────────────────────────────────────────────────────────

    def feed_imu(self, pitch: float, drive_pct: float, pitch_rate: float):
        now  = _time.monotonic()
        dt   = max(now - self._last_imu_t, 5e-4) if self._last_imu_t else 0.005
        self._last_imu_t = now
        self._prev_rate  = pitch_rate
        drive_norm = drive_pct / 100.0

        if self._running:
            self._samples.append((now, pitch, drive_norm, pitch_rate))
            self._n_lbl.setText(f"{len(self._samples)} pts")

        self._lbl_pitch.setText(f"{pitch:+.2f} °")
        self._lbl_rate.setText(f"{pitch_rate:+.1f} °/s")
        self._lbl_drive.setText(f"{drive_norm:+.3f}")

    def feed_motor(self, pv_l: int, pv_r: int, _pwml: float, _pwmr: float, sp_rpm: int):
        self._lbl_rpm_l.setText(f"{pv_l:+d}")
        self._lbl_rpm_r.setText(f"{pv_r:+d}")
        self._lbl_sp.setText(f"{sp_rpm:+d}")

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)
        root.addWidget(self._build_left(), stretch=0)
        root.addWidget(self._build_right(), stretch=1)

    # ── Left column ───────────────────────────────────────────────────────────

    def _build_left(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(270)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(self._build_mode_grp())
        lay.addWidget(self._build_signal_grp())
        lay.addWidget(self._build_telem_grp())
        lay.addWidget(self._build_result_grp())
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
            "Robot à l'envers avant d'entrer.\n"
            "Ne sortir qu'une fois le robot reposé sur ses roues —\n"
            "la sortie réactive immédiatement l'équilibre."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size:9px;color:#ff7043;font-family:Consolas;")
        lay.addWidget(hint)

        return grp

    def _on_mode_toggle(self, checked: bool):
        if checked:
            self._current_drive = 0.0
            self.send_drive.emit(0.0)   # enters ctrl_mode=2, drive parked at 0
            self._mode_btn.setText("🔒 Sortir du mode identification")
            self._start_btn.setEnabled(True)
        else:
            self._stop()
            self.send_sp.emit(0)        # exits to normal balance (ctrl_mode=0)
            self._mode_btn.setText("🔓 Entrer en mode identification")
            self._start_btn.setEnabled(False)

    def _build_signal_grp(self) -> QGroupBox:
        grp = QGroupBox("Signal d'excitation  —  signal carré")
        grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        lay = QVBoxLayout(grp)
        lay.setSpacing(6)

        def _row(label, widget):
            h = QHBoxLayout()
            h.setContentsMargins(0, 0, 0, 0)
            l = QLabel(label)
            l.setStyleSheet("font-size:10px;color:#90a4ae;")
            l.setFixedWidth(110)
            h.addWidget(l)
            h.addWidget(widget, stretch=1)
            lay.addLayout(h)

        self._amp_spin = QSpinBox()
        self._amp_spin.setRange(5, 100)
        self._amp_spin.setValue(25)
        self._amp_spin.setSuffix(" %")
        self._amp_spin.setToolTip("Amplitude ± du drive direct (% du drive max)")
        _row("Amplitude ±", self._amp_spin)

        self._half_spin = QDoubleSpinBox()
        self._half_spin.setRange(0.10, 5.0)
        self._half_spin.setValue(0.40)
        self._half_spin.setDecimals(2)
        self._half_spin.setSingleStep(0.05)
        self._half_spin.setSuffix(" s")
        self._half_spin.setToolTip("Durée de chaque demi-période")
        _row("Demi-période", self._half_spin)

        self._ncyc_spin = QSpinBox()
        self._ncyc_spin.setRange(3, 100)
        self._ncyc_spin.setValue(15)
        self._ncyc_spin.setToolTip("Nombre de cycles avant arrêt automatique")
        _row("Nb cycles", self._ncyc_spin)

        self._wave_combo = QComboBox()
        self._wave_combo.addItems(["Carré", "Sinus"])
        self._wave_combo.setCurrentIndex(1)   # default: sine
        self._wave_combo.setToolTip("Forme du signal d'excitation")
        _row("Forme d'onde", self._wave_combo)

        # Status display
        self._status_lbl = QLabel("⚫ Arrêté")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setStyleSheet(
            "font-size:14px;font-family:Consolas;font-weight:bold;"
            "color:#546e7a;padding:4px;"
        )
        lay.addWidget(self._status_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        self._start_btn = QPushButton("▶ Lancer")
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

        clr_btn = QPushButton("🗑 Effacer données")
        clr_btn.setFixedHeight(22)
        clr_btn.clicked.connect(self._clear)
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
        self._lbl_pitch = self._trow(lay, "Pitch",       "°",   "#ef5350", "16px")
        self._lbl_rate  = self._trow(lay, "pitch_rate",  "°/s", "#ffd54f", "11px")
        self._lbl_drive = self._trow(lay, "Drive norm.", "",    "#ffffff",  "11px")
        self._lbl_sp    = self._trow(lay, "SP RPM",      "RPM", "#b0bec5",  "11px")
        self._lbl_rpm_l = self._trow(lay, "RPM Gauche",  "RPM", "#ffd54f",  "11px")
        self._lbl_rpm_r = self._trow(lay, "RPM Droite",  "RPM", "#4dd0e1",  "11px")
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
        grp = QGroupBox("Résultat (fit sinusoïdal)  :  pitch_rate ≈ R·sin(ωt+ψ)")
        grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        lay = QVBoxLayout(grp)

        self._k_lbl = QLabel("K = —")
        self._k_lbl.setStyleSheet(
            "font-size:20px;font-family:Consolas;font-weight:bold;color:#66bb6a;"
        )
        lay.addWidget(self._k_lbl)

        self._r2_lbl = QLabel("R² = —   n = —")
        self._r2_lbl.setStyleSheet("font-size:10px;font-family:Consolas;color:#90a4ae;")
        lay.addWidget(self._r2_lbl)

        self._a_lbl = QLabel("ψ = —")
        self._a_lbl.setStyleSheet("font-size:10px;font-family:Consolas;color:#78909c;")
        lay.addWidget(self._a_lbl)

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

    # ── Right column : plots ──────────────────────────────────────────────────

    def _build_right(self) -> QWidget:
        w   = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # ── Top plot: drive (command) + pitch_rate ────────────────────────────
        ts_grp = QGroupBox("Signal  —  drive commandé  et  pitch_rate mesuré")
        ts_grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        tl = QVBoxLayout(ts_grp)
        self._pw_ts = pg.PlotWidget()
        self._pw_ts.showGrid(x=True, y=True, alpha=0.25)
        self._pw_ts.setLabel("bottom", "t (s)")
        self._pw_ts.addLegend(offset=(10, 10))
        self._pw_ts.addLine(y=0, pen=pg.mkPen("#37474f", width=1,
                                               style=Qt.PenStyle.DashLine))
        self._c_drv  = self._pw_ts.plot(
            pen=pg.mkPen("#66bb6a", width=2), name="drive × 100 (%)")
        self._c_rate = self._pw_ts.plot(
            pen=pg.mkPen("#ef5350", width=2), name="pitch_rate (°/s)")
        tl.addWidget(self._pw_ts)
        lay.addWidget(ts_grp, stretch=2)

        # ── Bottom plot: pitch_rate measured vs fitted sinusoid ──────────────
        sc_grp = QGroupBox("pitch_rate mesuré  vs  fit sinusoïdal  R·sin(ωt+ψ)")
        sc_grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        sl = QVBoxLayout(sc_grp)
        self._pw_sc = pg.PlotWidget()
        self._pw_sc.setLabel("left",   "pitch_rate  (°/s)")
        self._pw_sc.setLabel("bottom", "t (s)  (depuis le début du test)")
        self._pw_sc.showGrid(x=True, y=True, alpha=0.2)
        self._pw_sc.addLine(y=0, pen=pg.mkPen("#37474f", width=1,
                                               style=Qt.PenStyle.DashLine))
        self._sc_pts  = self._pw_sc.plot(
            pen=None, symbol="o", symbolSize=4,
            symbolBrush=pg.mkBrush("#ffd54f50"), symbolPen=None,
        )
        self._sc_fit = self._pw_sc.plot(pen=pg.mkPen("#66bb6a", width=2))
        sl.addWidget(self._pw_sc)
        lay.addWidget(sc_grp, stretch=1)

        return w

    # ── Square-wave control ───────────────────────────────────────────────────

    def _start(self):
        if self._running or not self._mode_btn.isChecked():
            return
        self._running    = True
        self._phase_pos  = True
        self._t_start    = _time.monotonic()
        self._samples.clear()

        half_ms  = int(self._half_spin.value() * 1000)
        total_ms = half_ms * 2 * self._ncyc_spin.value()

        if self._wave_combo.currentIndex() == 0:   # Carré
            self._sw_timer.start(half_ms)
            self._ka_timer.start()
            self._toggle_phase()                   # first edge immediately
        else:                                       # Sinus
            self._sine_timer.start(20)             # 50 Hz
            self._sine_tick()                      # first sample immediately

        self._reg_timer.start()
        self._plot_timer.start()
        QTimer.singleShot(total_ms, self._stop)

        self._start_btn.setEnabled(False)
        self._status_lbl.setText("🟢 En cours…")
        self._status_lbl.setStyleSheet(
            "font-size:14px;font-family:Consolas;font-weight:bold;"
            "color:#66bb6a;padding:4px;"
        )

    def _stop(self):
        if not self._running:
            return
        self._running = False
        self._sw_timer.stop()
        self._ka_timer.stop()
        self._sine_timer.stop()
        self._reg_timer.stop()
        self._plot_timer.stop()
        self._current_drive = 0.0
        self.send_drive.emit(0.0)   # parks at drive=0, stays in identification mode

        self._start_btn.setEnabled(self._mode_btn.isChecked())
        self._status_lbl.setText("⏹ Arrêté")
        self._status_lbl.setStyleSheet(
            "font-size:14px;font-family:Consolas;font-weight:bold;"
            "color:#546e7a;padding:4px;"
        )
        self._update_regression()

    def _toggle_phase(self):
        amp = self._amp_spin.value() / 100.0
        self._current_drive = amp if self._phase_pos else -amp
        self._phase_pos      = not self._phase_pos
        self.send_drive.emit(self._current_drive)

    def _keepalive(self):
        if self._running:
            self.send_drive.emit(self._current_drive)

    def _sine_tick(self):
        if not self._running:
            return
        elapsed = _time.monotonic() - self._t_start
        period  = self._half_spin.value() * 2.0
        amp     = self._amp_spin.value() / 100.0
        drive   = amp * math.sin(2.0 * math.pi * elapsed / period)
        self._current_drive = drive
        self.send_drive.emit(drive)

    def _clear(self):
        self._samples.clear()
        self._n_lbl.setText("0 pts")
        self._c_drv.setData([], [])
        self._c_rate.setData([], [])
        self._sc_pts.setData([], [])
        self._sc_fit.setData([], [])

    # ── Plot refresh ──────────────────────────────────────────────────────────

    def _refresh_plot(self):
        n = len(self._samples)
        if n < 2:
            return
        arr  = np.array(self._samples[-2000:], dtype=float)
        t    = arr[:, 0] - arr[0, 0]
        drv  = arr[:, 2] * 100.0            # scale to % for readability
        rate = arr[:, 3]
        self._c_drv.setData(x=list(t), y=list(drv))
        self._c_rate.setData(x=list(t), y=list(rate))

    # ── Sinusoidal (frequency-response) fit ─────────────────────────────────────

    def _update_regression(self):
        n = len(self._samples)
        if n < 20:
            return

        arr      = np.array(self._samples, dtype=float)
        t        = arr[:, 0] - self._t_start
        rate_dps = arr[:, 3]

        period  = self._half_spin.value() * 2.0
        omega_w = 2.0 * math.pi / period
        amp_cmd = self._amp_spin.value() / 100.0
        # Fourier fundamental amplitude: matches A_u directly for a sine
        # excitation, or 4/π·A_u for the fundamental of an ideal square wave.
        amp_eff = amp_cmd * (4.0 / math.pi) if self._wave_combo.currentIndex() == 0 else amp_cmd

        rate_rad = np.deg2rad(rate_dps)
        s_basis  = np.sin(omega_w * t)
        c_basis  = np.cos(omega_w * t)
        A = np.column_stack([s_basis, c_basis, np.ones_like(t)])
        coeffs, _, _, _ = np.linalg.lstsq(A, rate_rad, rcond=None)
        p, q, offset = (float(c) for c in coeffs)

        R   = math.hypot(p, q)        # rad/s — amplitude of the pitch_rate response
        psi = math.atan2(q, p)        # rad  — phase of pitch_rate vs sin(ωt)

        # |K| from the amplitude ratio is immune to phase lag (a lag only
        # rotates the (p,q) phasor, it doesn't change its magnitude).
        K_rad = -math.copysign(1.0, q) * R * omega_w / amp_eff if amp_eff > 1e-6 else 0.0
        K_deg = math.degrees(K_rad)

        y_pred = A @ coeffs
        SS_res = float(np.sum((rate_rad - y_pred) ** 2))
        SS_tot = float(np.sum((rate_rad - rate_rad.mean()) ** 2))
        r2     = max(0.0, 1.0 - SS_res / max(SS_tot, 1e-12))

        try:
            cov     = np.linalg.inv(A.T @ A) * (SS_res / max(n - 3, 1))
            var_R   = ((p / R) ** 2 * cov[0, 0] + (q / R) ** 2 * cov[1, 1]
                       + 2.0 * (p / R) * (q / R) * cov[0, 1]) if R > 1e-9 else float("nan")
            se_K_deg = math.degrees(math.sqrt(max(var_R, 0.0)) * omega_w / amp_eff)
        except np.linalg.LinAlgError:
            se_K_deg = float("nan")

        col = "#66bb6a" if r2 > 0.85 else "#ffd54f" if r2 > 0.5 else "#ef5350"
        self._k_lbl.setText(f"K = {K_deg:+.0f}  ±  {se_K_deg:.0f}  °/s²")
        self._k_lbl.setStyleSheet(
            f"font-size:20px;font-family:Consolas;font-weight:bold;color:{col};"
        )
        self._r2_lbl.setText(f"R² = {r2:.3f}   n = {n} pts")

        # Phase diagnostic: ideal value is -90° for a pure K·u term with K>0
        # (response = integral of θ̈), or +90° if K<0. Deviation from that
        # ideal phase = extra delay/dynamics.
        ideal_psi  = -math.pi / 2.0 if K_rad >= 0.0 else math.pi / 2.0
        extra_phase = psi - ideal_psi
        extra_phase = ((extra_phase + math.pi) % (2.0 * math.pi)) - math.pi
        extra_delay_ms = -extra_phase / omega_w * 1000.0
        self._a_lbl.setText(
            f"ψ = {math.degrees(psi):+.0f}°  (idéal {math.degrees(ideal_psi):+.0f}°)   "
            f"retard suppl. ≈ {extra_delay_ms:+.0f} ms"
        )

        if amp_cmd < 0.05:
            q_txt, qc = "⚠ Excitation trop faible — augmenter amplitude", "#ffd54f"
        elif r2 < 0.5:
            q_txt, qc = "⚠ R² faible — bruit ou signal non périodique", "#ef5350"
        elif not math.isnan(se_K_deg) and abs(K_deg) > 0 and se_K_deg / abs(K_deg) > 0.3:
            q_txt, qc = "⚠ Incertitude élevée — ajouter des cycles", "#ffd54f"
        else:
            q_txt, qc = f"✓ OK  (excitation {amp_cmd:.2f}, ψ={math.degrees(psi):+.0f}°)", "#66bb6a"
        self._q_lbl.setText(q_txt)
        self._q_lbl.setStyleSheet(f"font-size:10px;font-family:Consolas;color:{qc};")

        # Store result for JSON export
        self._last_result = {
            "K_deg_s2":                  round(K_deg, 1),
            "K_sigma_deg_s2":            round(se_K_deg, 1) if not math.isnan(se_K_deg) else None,
            "R2":                        round(r2, 4),
            "psi_deg":                   round(math.degrees(psi), 1),
            "extra_delay_ms":            round(extra_delay_ms, 1),
            "response_amplitude_deg_s":  round(math.degrees(R), 2),
            "n_pts":                     int(n),
            "excitation_amplitude":      round(amp_cmd, 3),
            "quality":                   q_txt,
        }
        self._save_btn.setEnabled(True)

        # Measured pitch_rate + fitted sinusoid overlay
        self._sc_pts.setData(x=list(t), y=list(rate_dps))
        if float(t.max()) > 0.01:
            t_dense = np.linspace(0.0, float(t.max()), 200)
            fit_dps = np.rad2deg(p * np.sin(omega_w * t_dense)
                                  + q * np.cos(omega_w * t_dense) + offset)
            self._sc_fit.setData(x=list(t_dense), y=list(fit_dps))

    # ── JSON export ───────────────────────────────────────────────────────────

    def _save_json(self):
        if not self._last_result:
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"ident_K_{ts}.json"
        default_dir  = str(Path(__file__).parent.parent / "sweeps")

        path, _ = QFileDialog.getSaveFileName(
            self, "Sauvegarder résultat identification K",
            str(Path(default_dir) / default_name),
            "JSON files (*.json)",
        )
        if not path:
            return

        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "type": "ident_K",
            "parameters": {
                "waveform":       self._wave_combo.currentText(),
                "amplitude_pct":  self._amp_spin.value(),
                "half_period_s":  round(self._half_spin.value(), 3),
                "nb_cycles":      self._ncyc_spin.value(),
            },
            "results": self._last_result,
        }
        Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
