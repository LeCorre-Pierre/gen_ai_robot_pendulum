"""
ident_k_panel.py — K (actuator gain) identification panel.

Excitation: square wave RPM setpoint (configurable amplitude + half-period).
Firmware bypasses CBC via VCP_TYPE_CMD_SET_SP (0x21) override flag (500 ms timeout).

Regression:  θ̈ = K·u + a·θ + c
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

_MAX_RPM = 85


class IdentKPanel(QWidget):
    send_sp = Signal(int)   # RPM setpoint [-85..+85] → gui._send_sp

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
        self._current_rpm = 0

        self._build_ui()

        # Square-wave generator
        self._sw_timer = QTimer(self, singleShot=False)
        self._sw_timer.timeout.connect(self._toggle_phase)

        # Keep-alive for square wave: resend at 4 Hz to hold the 500 ms override window
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
        lay.addWidget(self._build_signal_grp())
        lay.addWidget(self._build_telem_grp())
        lay.addWidget(self._build_result_grp())
        lay.addStretch()
        return w

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
        self._amp_spin.setRange(5, _MAX_RPM)
        self._amp_spin.setValue(40)
        self._amp_spin.setSuffix(" RPM")
        self._amp_spin.setToolTip("Amplitude ± du signal carré (RPM)")
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
        grp = QGroupBox("Résultat OLS  :  θ̈ = K·u + a·θ + c")
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

        self._a_lbl = QLabel("a = —")
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
            pen=pg.mkPen("#66bb6a", width=2), name="drive × 100 RPM")
        self._c_rate = self._pw_ts.plot(
            pen=pg.mkPen("#ef5350", width=2), name="pitch_rate (°/s)")
        tl.addWidget(self._pw_ts)
        lay.addWidget(ts_grp, stretch=2)

        # ── Bottom plot: scatter θ̈ vs drive ──────────────────────────────────
        sc_grp = QGroupBox("Scatter  θ̈  vs  drive  (régression OLS)")
        sc_grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        sl = QVBoxLayout(sc_grp)
        self._pw_sc = pg.PlotWidget()
        self._pw_sc.setLabel("left",   "θ̈  (°/s²)")
        self._pw_sc.setLabel("bottom", "drive normalisé")
        self._pw_sc.showGrid(x=True, y=True, alpha=0.2)
        self._pw_sc.addLine(x=0, pen=pg.mkPen("#37474f", width=1,
                                               style=Qt.PenStyle.DashLine))
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
        if self._running:
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
        self._current_rpm = 0
        self.send_sp.emit(0)

        self._start_btn.setEnabled(True)
        self._status_lbl.setText("⏹ Arrêté")
        self._status_lbl.setStyleSheet(
            "font-size:14px;font-family:Consolas;font-weight:bold;"
            "color:#546e7a;padding:4px;"
        )
        self._update_regression()

    def _toggle_phase(self):
        amp = self._amp_spin.value()
        self._current_rpm = amp if self._phase_pos else -amp
        self._phase_pos   = not self._phase_pos
        self.send_sp.emit(self._current_rpm)

    def _keepalive(self):
        if self._running:
            self.send_sp.emit(self._current_rpm)

    def _sine_tick(self):
        if not self._running:
            return
        elapsed = _time.monotonic() - self._t_start
        period  = self._half_spin.value() * 2.0
        amp     = self._amp_spin.value()
        rpm     = int(round(amp * math.sin(2.0 * math.pi * elapsed / period)))
        self._current_rpm = rpm
        self.send_sp.emit(rpm)

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
        drv  = arr[:, 2] * _MAX_RPM         # scale to RPM for readability
        rate = arr[:, 3]
        self._c_drv.setData(x=list(t), y=list(drv))
        self._c_rate.setData(x=list(t), y=list(rate))

    # ── OLS regression ────────────────────────────────────────────────────────

    def _update_regression(self):
        n = len(self._samples)
        if n < 20:
            return

        arr   = np.array(self._samples, dtype=float)
        theta = np.deg2rad(arr[:, 1])
        u     = arr[:, 2]
        omega = np.deg2rad(arr[:, 3])
        t     = arr[:, 0]

        # Use median dt: serial reader delivers frames in bursts, so
        # consecutive Python timestamps can be near-identical (→ dt≈0 → θ̈→∞).
        raw_dt = np.diff(t)
        dt_med = float(np.median(raw_dt[raw_dt > 1e-4]))
        if dt_med < 1e-4:
            return
        ddot   = np.diff(omega) / dt_med
        th_mid = (theta[:-1] + theta[1:]) / 2.0
        u_mid  = (u[:-1] + u[1:]) / 2.0

        m = len(ddot)
        if m < 10:
            return

        A = np.column_stack([u_mid, th_mid, np.ones(m)])
        coeffs, _, _, _ = np.linalg.lstsq(A, ddot, rcond=None)
        K_rad = float(coeffs[0])
        a_rad = float(coeffs[1])
        c_rad = float(coeffs[2])
        K_deg = float(np.rad2deg(K_rad))

        y_pred = A @ coeffs
        SS_res = float(np.sum((ddot - y_pred) ** 2))
        SS_tot = float(np.sum((ddot - ddot.mean()) ** 2))
        r2     = max(0.0, 1.0 - SS_res / max(SS_tot, 1e-12))

        try:
            cov  = np.linalg.inv(A.T @ A) * (SS_res / max(m - 3, 1))
            se_K = float(np.rad2deg(np.sqrt(max(cov[0, 0], 0.0))))
        except np.linalg.LinAlgError:
            se_K = float("nan")

        col = "#66bb6a" if r2 > 0.55 else "#ffd54f" if r2 > 0.25 else "#ef5350"
        self._k_lbl.setText(f"K = {K_deg:+.0f}  ±  {se_K:.0f}  °/s²")
        self._k_lbl.setStyleSheet(
            f"font-size:20px;font-family:Consolas;font-weight:bold;color:{col};"
        )
        self._r2_lbl.setText(f"R² = {r2:.3f}   n = {m} pts")

        if a_rad > 0.1:
            wn  = float(np.sqrt(a_rad))
            L   = 9.81 / a_rad
            self._a_lbl.setText(f"a = {a_rad:.1f} rad/s²  →  ωn={wn:.1f} rad/s,  L={L*100:.1f} cm")
        else:
            self._a_lbl.setText(f"a = {a_rad:.1f} rad/s²  (négatif → upside-down ✓)")

        exc = float(np.mean(np.abs(u_mid)))
        if exc < 0.05:
            q, qc = "⚠ Excitation trop faible — augmenter amplitude", "#ffd54f"
        elif r2 < 0.25:
            q, qc = "⚠ R² faible — bruit ou trop peu de cycles", "#ef5350"
        elif not np.isnan(se_K) and abs(K_deg) > 0 and se_K / abs(K_deg) > 0.5:
            q, qc = f"⚠ Incertitude élevée — ajouter des cycles", "#ffd54f"
        else:
            q, qc = f"✓ OK  (excitation moy. {exc:.2f})", "#66bb6a"
        self._q_lbl.setText(q)
        self._q_lbl.setStyleSheet(f"font-size:10px;font-family:Consolas;color:{qc};")

        # Store result for JSON export
        self._last_result = {
            "K_deg_s2":    round(K_deg, 1),
            "K_sigma_deg_s2": round(se_K, 1) if not np.isnan(se_K) else None,
            "R2":          round(r2, 4),
            "a_rad_s2":    round(a_rad, 2),
            "c_rad_s2":    round(c_rad, 4),
            "n_pts":       int(m),
            "excitation_mean": round(float(exc), 3),
            "quality":     q,
        }
        self._save_btn.setEnabled(True)

        # Scatter + fit line
        ddot_deg = np.rad2deg(ddot)
        self._sc_pts.setData(x=list(u_mid), y=list(ddot_deg))
        u_span = float(u_mid.max() - u_mid.min())
        if u_span > 0.01:
            u_line    = np.linspace(float(u_mid.min()), float(u_mid.max()), 60)
            ddot_line = np.rad2deg(K_rad * u_line + a_rad * float(th_mid.mean()) + c_rad)
            self._sc_fit.setData(x=list(u_line), y=list(ddot_line))

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
                "amplitude_rpm":  self._amp_spin.value(),
                "half_period_s":  round(self._half_spin.value(), 3),
                "nb_cycles":      self._ncyc_spin.value(),
            },
            "results": self._last_result,
        }
        Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
