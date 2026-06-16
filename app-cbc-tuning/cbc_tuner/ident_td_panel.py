"""
ident_td_panel.py — Transport delay (dead time td) identification panel.

Method: injects a square-wave direct drive command (VCP_TYPE_CMD_SET_DRIVE,
bypasses the balance loop) and cross-correlates the drive signal with the
measured angular acceleration θ̈.
Peak lag in causal region [0, half_period] = td.

Results + raw samples (pitch_rate_dps, drive_norm) saved to JSON.
Overlay: load multiple JSON files and superimpose xcorr curves.
"""
from __future__ import annotations

import json
import time as _time
from datetime import datetime
from pathlib import Path

import numpy as np
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)
import pyqtgraph as pg

_OV_COLORS = ["#ef5350", "#ffa726", "#66bb6a", "#29b6f6", "#ab47bc", "#ec407a", "#26c6da"]


class IdentTdPanel(QWidget):
    send_drive = Signal(float)  # direct drive [-1..+1] → gui._send_drive
    send_sp    = Signal(int)    # SP(0) used only to exit direct-drive mode on stop

    def __init__(self, parent=None):
        super().__init__(parent)

        self._running   = False
        self._phase_pos = True

        # samples: (t_recv, pitch_rate_dps, drive_norm)
        self._samples: list[tuple[float, float, float]] = []
        self._cur_drive    = 0.0
        self._command_drive = 0.0
        self._last_result: dict | None = None
        self._overlay: list[dict] = []

        self._build_ui()

        self._sw_timer    = QTimer(self, singleShot=False)
        self._sw_timer.timeout.connect(self._toggle_phase)

        # Resend the current drive at 10 Hz so a half-period longer than the
        # firmware's no-command hold window doesn't get cut short to 0.
        self._ka_timer = QTimer(self, interval=100)
        self._ka_timer.timeout.connect(self._keepalive)

        self._xcorr_timer = QTimer(self, interval=800)
        self._xcorr_timer.timeout.connect(self._update_xcorr)

        # live time-series refresh at 25 Hz
        self._plot_timer  = QTimer(self, interval=40)
        self._plot_timer.timeout.connect(self._refresh_ts)

    # ── Public API ────────────────────────────────────────────────────────────

    def feed_imu(self, pitch: float, drive_pct: float, pitch_rate: float):
        now = _time.monotonic()
        self._cur_drive = drive_pct / 100.0
        if self._running:
            self._samples.append((now, pitch_rate, self._cur_drive))
            self._sample_lbl.setText(f"{len(self._samples)} échantillons")
        self._lbl_pitch.setText(f"{pitch:+.2f}°")
        self._lbl_rate.setText(f"{pitch_rate:+.2f} °/s")
        self._lbl_drive.setText(f"{self._cur_drive:+.3f}")

    def feed_motor(self, pv_l: int, pv_r: int, _pwm_l: float, _pwm_r: float, sp_rpm: int):
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

    def _build_left(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(290)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(self._build_mode_grp())
        lay.addWidget(self._build_sw_grp())
        lay.addWidget(self._build_telem_grp())
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
            self._command_drive = 0.0
            self.send_drive.emit(0.0)   # enters ctrl_mode=2, drive parked at 0
            self._mode_btn.setText("🔒 Sortir du mode identification")
            self._start_btn.setEnabled(True)
        else:
            self._stop()
            self.send_sp.emit(0)        # exits to normal balance (ctrl_mode=0)
            self._mode_btn.setText("🔓 Entrer en mode identification")
            self._start_btn.setEnabled(False)

    def _build_sw_grp(self) -> QGroupBox:
        grp = QGroupBox("Générateur signal carré")
        grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        lay = QVBoxLayout(grp)
        lay.setSpacing(6)

        def _row(label, widget, unit=""):
            h = QHBoxLayout()
            h.setContentsMargins(0, 0, 0, 0)
            l = QLabel(label)
            l.setStyleSheet("font-size:10px;color:#90a4ae;")
            l.setFixedWidth(120)
            h.addWidget(l)
            h.addWidget(widget, stretch=1)
            if unit:
                h.addWidget(QLabel(unit))
            lay.addLayout(h)

        self._amp_spin = QSpinBox()
        self._amp_spin.setRange(5, 100)
        self._amp_spin.setValue(20)
        self._amp_spin.setSuffix(" %")
        self._amp_spin.setToolTip("Amplitude ± du drive direct (% du drive max)")
        _row("Amplitude ±", self._amp_spin)

        self._half_spin = QDoubleSpinBox()
        self._half_spin.setRange(0.05, 5.0)
        self._half_spin.setValue(0.25)
        self._half_spin.setDecimals(2)
        self._half_spin.setSingleStep(0.05)
        _row("Demi-période", self._half_spin, "s")

        self._ncyc_spin = QSpinBox()
        self._ncyc_spin.setRange(2, 200)
        self._ncyc_spin.setValue(20)
        _row("Nb cycles", self._ncyc_spin)

        self._status_lbl = QLabel("⚫ Arrêté")
        self._status_lbl.setStyleSheet(
            "font-size:13px;font-family:Consolas;font-weight:bold;color:#546e7a;"
        )
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._status_lbl)

        btn_row = QHBoxLayout()
        self._start_btn = QPushButton("▶ Démarrer")
        self._start_btn.setFixedHeight(28)
        self._start_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:white;font-weight:bold;}"
            "QPushButton:hover{background:#43a047;}"
            "QPushButton:disabled{background:#37474f;color:#546e7a;}"
        )
        self._start_btn.clicked.connect(self._start)
        self._start_btn.setEnabled(False)   # requires mode identification active
        btn_row.addWidget(self._start_btn)

        stop_btn = QPushButton("⏹ STOP")
        stop_btn.setFixedHeight(28)
        stop_btn.setStyleSheet(
            "QPushButton{background:#c62828;color:white;font-weight:bold;}"
            "QPushButton:hover{background:#ef5350;}"
        )
        stop_btn.clicked.connect(self._stop)
        btn_row.addWidget(stop_btn)
        lay.addLayout(btn_row)

        clr_btn = QPushButton("🗑 Effacer données")
        clr_btn.setFixedHeight(22)
        clr_btn.clicked.connect(self._clear)
        lay.addWidget(clr_btn)

        self._sample_lbl = QLabel("0 échantillons")
        self._sample_lbl.setStyleSheet("font-size:9px;color:#546e7a;font-family:Consolas;")
        lay.addWidget(self._sample_lbl)

        return grp

    def _build_telem_grp(self) -> QGroupBox:
        grp = QGroupBox("Télémétrie")
        grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        lay = QVBoxLayout(grp)
        lay.setSpacing(2)

        def _lbl_row(label, unit="") -> QLabel:
            h = QHBoxLayout()
            h.setContentsMargins(0, 0, 0, 0)
            l = QLabel(label)
            l.setStyleSheet("font-size:10px;color:#78909c;font-family:Consolas;")
            l.setFixedWidth(100)
            v = QLabel("—")
            v.setStyleSheet("font-size:11px;font-family:Consolas;color:#e0e0e0;")
            v.setAlignment(Qt.AlignmentFlag.AlignRight)
            u = QLabel(unit)
            u.setStyleSheet("font-size:9px;color:#546e7a;")
            u.setFixedWidth(36)
            h.addWidget(l); h.addWidget(v, stretch=1); h.addWidget(u)
            lay.addLayout(h)
            return v

        self._lbl_pitch = _lbl_row("Pitch", "°")
        self._lbl_rate  = _lbl_row("pitch_rate", "°/s")
        self._lbl_drive = _lbl_row("Drive norm.", "")
        self._lbl_sp    = _lbl_row("SP RPM", "RPM")
        self._lbl_rpm_l = _lbl_row("RPM Gauche", "RPM")
        self._lbl_rpm_r = _lbl_row("RPM Droite", "RPM")
        return grp

    def _build_right(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # ── Result + actions ──────────────────────────────────────────────────
        res_grp = QGroupBox("Résultat — td (délai de transport)")
        res_grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        rl = QVBoxLayout(res_grp)

        self._td_lbl = QLabel("td = —  ms")
        self._td_lbl.setStyleSheet(
            "font-size:28px;font-family:Consolas;font-weight:bold;color:#42a5f5;"
        )
        rl.addWidget(self._td_lbl)

        self._td_detail = QLabel("—")
        self._td_detail.setStyleSheet("font-size:10px;font-family:Consolas;color:#78909c;")
        rl.addWidget(self._td_detail)

        act_row = QHBoxLayout()
        self._save_btn = QPushButton("💾 Sauvegarder JSON")
        self._save_btn.setFixedHeight(26)
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_json)
        act_row.addWidget(self._save_btn)

        load_btn = QPushButton("📂 Charger overlay")
        load_btn.setFixedHeight(26)
        load_btn.clicked.connect(self._load_overlay)
        act_row.addWidget(load_btn)
        rl.addLayout(act_row)
        lay.addWidget(res_grp)

        # ── Overlay list ──────────────────────────────────────────────────────
        ov_grp = QGroupBox("Superposition")
        ov_grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        ol = QVBoxLayout(ov_grp)

        self._overlay_list = QListWidget()
        self._overlay_list.setFixedHeight(68)
        self._overlay_list.setStyleSheet(
            "font-size:10px;font-family:Consolas;background:#1a232a;border:1px solid #37474f;"
        )
        ol.addWidget(self._overlay_list)

        clr_ov_btn = QPushButton("🗑 Effacer superposition")
        clr_ov_btn.setFixedHeight(22)
        clr_ov_btn.clicked.connect(self._clear_overlay)
        ol.addWidget(clr_ov_btn)
        lay.addWidget(ov_grp)

        # ── Cross-correlation plot ─────────────────────────────────────────────
        xcorr_grp = QGroupBox("Cross-corrélation  drive  ⋆  θ̈")
        xcorr_grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        xl = QVBoxLayout(xcorr_grp)
        self._pw_xcorr = pg.PlotWidget()
        self._pw_xcorr.setLabel("left",   "corrélation (normalisée)")
        self._pw_xcorr.setLabel("bottom", "lag (ms)")
        self._pw_xcorr.showGrid(x=True, y=True, alpha=0.2)
        self._pw_xcorr.addLine(x=0, pen=pg.mkPen("#546e7a", width=1,
                                                   style=Qt.PenStyle.DashLine))
        self._xcorr_live_curve = self._pw_xcorr.plot(pen=pg.mkPen("#42a5f5", width=2))
        self._xcorr_live_peak  = self._pw_xcorr.plot(
            pen=None, symbol="o", symbolSize=10,
            symbolBrush=pg.mkBrush("#ef5350"), symbolPen=None,
        )
        xl.addWidget(self._pw_xcorr)
        lay.addWidget(xcorr_grp, stretch=1)

        # ── Time series ───────────────────────────────────────────────────────
        ts_grp = QGroupBox("Série temporelle  —  drive  et  pitch_rate")
        ts_grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:11px;}")
        tl = QVBoxLayout(ts_grp)
        self._pw_ts = pg.PlotWidget()
        self._pw_ts.showGrid(x=True, y=True, alpha=0.2)
        self._pw_ts.addLegend(offset=(10, 10))
        self._ts_drive = self._pw_ts.plot(
            pen=pg.mkPen("#66bb6a", width=2), name="drive × 100")
        self._ts_rate  = self._pw_ts.plot(
            pen=pg.mkPen("#ffd54f", width=1.5), name="pitch_rate (°/s)")
        tl.addWidget(self._pw_ts)
        lay.addWidget(ts_grp, stretch=1)

        return w

    # ── Square-wave control ───────────────────────────────────────────────────

    def _start(self):
        if self._running or not self._mode_btn.isChecked():
            return
        self._running   = True
        self._phase_pos = True
        self._samples.clear()
        self._last_result = None
        self._save_btn.setEnabled(False)

        half_ms  = int(self._half_spin.value() * 1000)
        total_ms = half_ms * 2 * self._ncyc_spin.value()

        self._sw_timer.start(half_ms)
        self._ka_timer.start()
        self._xcorr_timer.start()
        self._plot_timer.start()
        self._toggle_phase()
        QTimer.singleShot(total_ms, self._stop)

        self._start_btn.setEnabled(False)
        self._status_lbl.setText("🟢 En cours…")
        self._status_lbl.setStyleSheet(
            "font-size:13px;font-family:Consolas;font-weight:bold;color:#66bb6a;"
        )

    def _stop(self):
        if not self._running:
            return
        self._running = False
        self._sw_timer.stop()
        self._ka_timer.stop()
        self._xcorr_timer.stop()
        self._plot_timer.stop()
        self._command_drive = 0.0
        self.send_drive.emit(0.0)   # parks at drive=0, stays in identification mode
        self._start_btn.setEnabled(self._mode_btn.isChecked())
        self._status_lbl.setText("⏹ Arrêté")
        self._status_lbl.setStyleSheet(
            "font-size:13px;font-family:Consolas;font-weight:bold;color:#546e7a;"
        )
        self._update_xcorr()

    def _toggle_phase(self):
        amp = self._amp_spin.value() / 100.0
        self._command_drive = amp if self._phase_pos else -amp
        self._phase_pos      = not self._phase_pos
        self.send_drive.emit(self._command_drive)

    def _keepalive(self):
        if self._running:
            self.send_drive.emit(self._command_drive)

    def _clear(self):
        self._samples.clear()
        self._last_result = None
        self._save_btn.setEnabled(False)
        self._sample_lbl.setText("0 échantillons")
        self._xcorr_live_curve.setData([], [])
        self._xcorr_live_peak.setData([], [])
        self._ts_drive.setData([], [])
        self._ts_rate.setData([], [])
        self._td_lbl.setText("td = —  ms")
        self._td_detail.setText("—")

    # ── Live time series ──────────────────────────────────────────────────────

    def _refresh_ts(self):
        n = len(self._samples)
        if n < 2:
            return
        arr = np.array(self._samples[-800:], dtype=float)
        t   = arr[:, 0] - arr[0, 0]
        self._ts_drive.setData(x=list(t), y=list(arr[:, 2] * 100.0))
        self._ts_rate.setData( x=list(t), y=list(arr[:, 1]))

    # ── Cross-correlation ─────────────────────────────────────────────────────

    def _xcorr_from_array(self, arr: np.ndarray, half_s: float) -> dict | None:
        """
        Compute cross-correlation from sample array (N×3): t_recv, pitch_rate_dps, drive_norm.
        Returns result dict or None on failure.
        """
        t     = arr[:, 0]
        rate  = arr[:, 1]
        drive = arr[:, 2]

        raw_dt = np.diff(t)
        valid  = raw_dt[raw_dt > 1e-4]
        if len(valid) < 10:
            return None
        dt_med = float(np.median(valid))

        t_uni  = np.arange(t[0], t[-1], dt_med)
        rate_u = np.interp(t_uni, t, rate)
        drv_u  = np.interp(t_uni, t, drive)

        # θ̈ from resampled rate (uniform dt → clean derivative)
        omega_u = np.deg2rad(rate_u)
        ddot_u  = np.diff(omega_u) / dt_med
        drv_mid = (drv_u[:-1] + drv_u[1:]) / 2.0
        m       = len(ddot_u)
        if m < 20:
            return None

        ddot_u  = ddot_u  - ddot_u.mean()
        drv_mid = drv_mid - drv_mid.mean()

        xcorr    = np.correlate(ddot_u, drv_mid, mode="full")
        norm_fac = (np.std(ddot_u) * np.std(drv_mid) * m) + 1e-10
        xcorr   /= norm_fac

        lags_ms = np.arange(-(m - 1), m) * dt_med * 1000.0

        half_ms = half_s * 1000.0
        causal  = (lags_ms >= 0) & (lags_ms <= half_ms)
        if causal.sum() < 3:
            return None
        idx_peak = int(np.argmax(xcorr[causal]))
        td_ms    = float(lags_ms[causal][idx_peak])
        peak_val = float(xcorr[causal][idx_peak])

        view = (lags_ms >= -half_ms) & (lags_ms <= 2 * half_ms)
        return {
            "td_ms":        td_ms,
            "peak_val":     peak_val,
            "n":            int(len(arr)),
            "dt_med_ms":    dt_med * 1000.0,
            "lags_ms_view": list(lags_ms[view]),
            "xcorr_view":   list(xcorr[view]),
        }

    def _update_xcorr(self):
        n = len(self._samples)
        if n < 30:
            return
        arr    = np.array(self._samples, dtype=float)
        result = self._xcorr_from_array(arr, self._half_spin.value())
        if result is None:
            return

        self._xcorr_live_curve.setData(x=result["lags_ms_view"], y=result["xcorr_view"])
        self._xcorr_live_peak.setData(x=[result["td_ms"]], y=[result["peak_val"]])
        self._apply_result(result)
        self._last_result = result
        self._save_btn.setEnabled(True)

    def _apply_result(self, result: dict):
        td  = result["td_ms"]
        col = "#42a5f5" if td < 50 else "#ffd54f" if td < 150 else "#ef5350"
        self._td_lbl.setText(f"td = {td:.1f} ms")
        self._td_lbl.setStyleSheet(
            f"font-size:28px;font-family:Consolas;font-weight:bold;color:{col};"
        )
        self._td_detail.setText(
            f"peak={result['peak_val']:.3f}   n={result['n']}   "
            f"dt_med={result['dt_med_ms']:.1f} ms"
        )

    # ── Save JSON ─────────────────────────────────────────────────────────────

    def _save_json(self):
        if not self._last_result or not self._samples:
            return
        ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
        default = str(Path(__file__).parent.parent / "sweeps" / f"ident_td_{ts}.json")
        path, _ = QFileDialog.getSaveFileName(
            self, "Sauvegarder identification td", default, "JSON files (*.json)"
        )
        if not path:
            return

        arr = np.array(self._samples, dtype=float)
        t0  = float(arr[0, 0])
        samples_out = [
            {
                "t_s":           round(float(r[0]) - t0, 4),
                "pitch_rate_dps": round(float(r[1]), 4),
                "drive":          round(float(r[2]), 5),
            }
            for r in arr
        ]
        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "type": "ident_td",
            "parameters": {
                "amplitude_pct": self._amp_spin.value(),
                "half_period_s": round(self._half_spin.value(), 3),
                "nb_cycles":     self._ncyc_spin.value(),
            },
            "results": {
                "td_ms":     round(self._last_result["td_ms"], 2),
                "peak_corr": round(self._last_result["peak_val"], 4),
                "n_samples": self._last_result["n"],
                "dt_med_ms": round(self._last_result["dt_med_ms"], 2),
            },
            "samples": samples_out,
        }
        Path(path).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ── Overlay ───────────────────────────────────────────────────────────────

    def _load_overlay(self):
        default_dir = str(Path(__file__).parent.parent / "sweeps")
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Charger fichier(s) ident_td", default_dir, "JSON files (*.json)"
        )
        for p in paths:
            self._add_overlay_from_file(p)

    def _add_overlay_from_file(self, path: str):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return
        if data.get("type") != "ident_td":
            return
        samples = data.get("samples", [])
        if len(samples) < 30:
            return

        arr    = np.array(
            [[s["t_s"], s["pitch_rate_dps"], s["drive"]] for s in samples],
            dtype=float,
        )
        half_s = data.get("parameters", {}).get("half_period_s", self._half_spin.value())
        result = self._xcorr_from_array(arr, half_s)
        if result is None:
            return

        color = _OV_COLORS[len(self._overlay) % len(_OV_COLORS)]
        label = f"{Path(path).stem}  td={result['td_ms']:.0f}ms"

        dash = Qt.PenStyle.DashLine
        dot  = Qt.PenStyle.DotLine

        xc = self._pw_xcorr.plot(pen=pg.mkPen(color, width=1.5, style=dash))
        xp = self._pw_xcorr.plot(
            pen=None, symbol="d", symbolSize=8,
            symbolBrush=pg.mkBrush(color), symbolPen=None,
        )
        tc = self._pw_ts.plot(pen=pg.mkPen(color, width=1.5, style=dash), name=Path(path).stem)
        td = self._pw_ts.plot(pen=pg.mkPen(color, width=1.0, style=dot))

        xc.setData(x=result["lags_ms_view"], y=result["xcorr_view"])
        xp.setData(x=[result["td_ms"]], y=[result["peak_val"]])
        t_rel = arr[:, 0] - arr[0, 0]
        tc.setData(x=list(t_rel), y=list(arr[:, 1]))
        td.setData(x=list(t_rel), y=list(arr[:, 2] * 100.0))

        item = QListWidgetItem(label)
        item.setForeground(pg.mkColor(color))
        self._overlay_list.addItem(item)
        self._overlay.append({"xc": xc, "xp": xp, "tc": tc, "td": td})

    def _clear_overlay(self):
        for ov in self._overlay:
            self._pw_xcorr.removeItem(ov["xc"])
            self._pw_xcorr.removeItem(ov["xp"])
            self._pw_ts.removeItem(ov["tc"])
            self._pw_ts.removeItem(ov["td"])
        self._overlay.clear()
        self._overlay_list.clear()
