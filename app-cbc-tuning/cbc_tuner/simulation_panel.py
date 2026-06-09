"""
simulation_panel.py — PID simulation for UFOPDT inverted pendulum.

Manuel : gains via sliders → simulation instantanée à chaque changement.
Sweep  : grid Kp×Kd → heatmap + top résultats.

Model:  θ̈ = a²·θ − K·u(t−τd)
"""
from __future__ import annotations

from collections import deque

import numpy as np
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractSpinBox, QComboBox, QDoubleSpinBox, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QProgressBar, QPushButton,
    QSlider, QSpinBox, QStackedWidget, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)
import pyqtgraph as pg

_DT     = 0.005
_SAFETY = 45.0

C_ANGLE = "#ef5350"
C_DRIVE = "#ffffff"
C_PP    = "#ef5350"
C_PI    = "#66bb6a"
C_PD    = "#42a5f5"
C_SAFE  = "#ff7043"
C_ZERO  = "#546e7a"


# ── Gain slider with adjustable range ────────────────────────────────────────

class _GainSlider(QWidget):
    """
    Spinbox + horizontal slider for a PID gain.
    The lo/hi bounds are editable inline so the user can rescale anytime.
    """
    TICKS = 1000

    def __init__(self, label: str, val: float, lo: float, hi: float,
                 dec: int, parent=None):
        super().__init__(parent)
        self._dec     = dec
        self._blocked = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 3)
        lay.setSpacing(1)

        # ── row 1 : label + value spinbox ────────────────────────────────────
        top = QHBoxLayout(); top.setContentsMargins(0, 0, 0, 0); top.setSpacing(4)
        lbl = QLabel(label)
        lbl.setStyleSheet("font-size:10px;font-family:Consolas;color:#cccccc;")
        lbl.setFixedWidth(24)
        top.addWidget(lbl)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(lo, hi)
        self._spin.setDecimals(dec)
        self._spin.setValue(val)
        self._spin.setFixedWidth(72)
        self._spin.setStepType(QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        self._spin.setStyleSheet("font-size:11px;font-family:Consolas;")
        top.addWidget(self._spin)
        top.addStretch()
        lay.addLayout(top)

        # ── row 2 : [lo] ====slider==== [hi] ─────────────────────────────────
        bot = QHBoxLayout(); bot.setContentsMargins(0, 0, 0, 0); bot.setSpacing(3)

        self._lo = QDoubleSpinBox()
        self._lo.setRange(-1000.0, 1000.0); self._lo.setDecimals(dec); self._lo.setValue(lo)
        self._lo.setFixedWidth(54); self._lo.setFixedHeight(18)
        self._lo.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._lo.setStyleSheet("font-size:9px;color:#546e7a;padding:0;")
        bot.addWidget(self._lo)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, self.TICKS)
        self._slider.setValue(self._v2t(val, lo, hi))
        self._slider.setFixedHeight(18)
        bot.addWidget(self._slider, stretch=1)

        self._hi = QDoubleSpinBox()
        self._hi.setRange(-1000.0, 1000.0); self._hi.setDecimals(dec); self._hi.setValue(hi)
        self._hi.setFixedWidth(54); self._hi.setFixedHeight(18)
        self._hi.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._hi.setStyleSheet("font-size:9px;color:#546e7a;padding:0;")
        bot.addWidget(self._hi)

        lay.addLayout(bot)

        self._spin.valueChanged.connect(self._on_spin)
        self._slider.valueChanged.connect(self._on_slider)
        self._lo.valueChanged.connect(self._on_range)
        self._hi.valueChanged.connect(self._on_range)

    # ── internal helpers ──────────────────────────────────────────────────────

    def _v2t(self, v, lo, hi):
        rng = hi - lo
        return int(round((v - lo) / rng * self.TICKS)) if rng else 0

    def _t2v(self, t):
        lo = self._lo.value(); hi = self._hi.value()
        return round(lo + t / self.TICKS * (hi - lo), self._dec)

    def _on_spin(self, v):
        if self._blocked: return
        self._blocked = True
        self._slider.setValue(self._v2t(v, self._lo.value(), self._hi.value()))
        self._blocked = False

    def _on_slider(self, t):
        if self._blocked: return
        self._blocked = True
        self._spin.setValue(self._t2v(t))
        self._blocked = False

    def _on_range(self):
        lo = self._lo.value(); hi = self._hi.value()
        if lo >= hi: return
        self._spin.setRange(lo, hi)
        self._blocked = True
        self._slider.setValue(self._v2t(self._spin.value(), lo, hi))
        self._blocked = False

    # ── public API ────────────────────────────────────────────────────────────

    def value(self):
        return self._spin.value()

    def set_value(self, v):
        self._spin.setValue(v)

    def connect(self, slot):
        self._spin.valueChanged.connect(slot)


# ── Labelled spinbox (for system params) ─────────────────────────────────────

class _Row(QWidget):
    def __init__(self, label, val, lo, hi, dec, step, unit="", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(4)
        lbl = QLabel(label); lbl.setFixedWidth(72)
        lbl.setStyleSheet("font-size:10px;font-family:Consolas;color:#cccccc;")
        lay.addWidget(lbl)
        self._spin = QDoubleSpinBox()
        self._spin.setRange(lo, hi); self._spin.setDecimals(dec)
        self._spin.setValue(val); self._spin.setSingleStep(step)
        self._spin.setFixedWidth(84)
        self._spin.setStepType(QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        self._spin.setStyleSheet("font-size:11px;font-family:Consolas;")
        lay.addWidget(self._spin)
        if unit:
            u = QLabel(unit); u.setStyleSheet("font-size:9px;color:#78909c;"); u.setFixedWidth(34)
            lay.addWidget(u)
        lay.addStretch()

    def value(self):         return self._spin.value()
    def set_value(self, v):  self._spin.setValue(v)
    def connect(self, slot): self._spin.valueChanged.connect(slot)


# ── Robot silhouette ──────────────────────────────────────────────────────────

class _RobotViz(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self._theta = 2.0; self._crashed = False

    def set_angle(self, deg):
        self._theta = max(-89.0, min(89.0, deg))
        self._crashed = abs(deg) >= _SAFETY
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#1e1e1e"))
        w, h    = self.width(), self.height()
        floor_y = h - 20
        p.setPen(QPen(QColor("#546e7a"), 1))
        p.drawLine(10, int(floor_y), w - 10, int(floor_y))
        p.save()
        p.translate(w / 2, floor_y - 13); p.rotate(self._theta)
        bc = QColor("#ef5350" if self._crashed else "#37474f")
        hl = QColor("#546e7a")
        for dx in (-13, 13):
            p.setBrush(QBrush(QColor("#263238")))
            p.setPen(QPen(QColor("#ef5350" if self._crashed else "#78909c"), 1.5))
            p.drawEllipse(QRectF(dx - 13, -13, 26, 26))
            p.setBrush(QBrush(hl)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(dx - 3, -3, 6, 6))
        p.setBrush(QBrush(bc)); p.setPen(QPen(hl, 1.5))
        p.drawRoundedRect(QRectF(-16, -62, 32, 42), 5, 5)
        p.drawRoundedRect(QRectF(-11, -86, 22, 20), 4, 4)
        p.setBrush(QBrush(QColor("#42a5f5"))); p.setPen(Qt.PenStyle.NoPen)
        for ex in (-8, 2): p.drawEllipse(QRectF(ex, -82, 6, 6))
        p.restore()
        col = "#ef5350" if self._crashed else ("#ffd54f" if abs(self._theta) > 15 else "#66bb6a")
        p.setPen(QPen(QColor(col)))
        p.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        p.drawText(QRectF(0, floor_y + 2, w, 16), Qt.AlignmentFlag.AlignHCenter,
                   f"{self._theta:+.1f}°")


# ── Main panel ────────────────────────────────────────────────────────────────

class SimPanel(QWidget):
    _DEF_A   = 7.38
    _DEF_K   = 2000.0
    _DEF_TAU = 0.189

    def __init__(self, parent=None):
        super().__init__(parent)

        self._live_kp = self._live_ki = self._live_kd = 0.0
        self._instant_result = None

        # sweep state
        self._sweep_kp_vals = None
        self._sweep_kd_vals = None
        self._sweep_res     = None
        self._sweep_abort   = False
        self._sweep_i       = 0
        self._sweep_timer   = QTimer(self, interval=0)
        self._sweep_timer.timeout.connect(self._sweep_next_row)

        # debounce timer for instant sim
        self._debounce = QTimer(self, singleShot=True, interval=30)
        self._debounce.timeout.connect(self._run_instant)

        # replay animation for robot viz
        self._replay_idx = 0
        self._replay_angs = None
        self._replay_timer = QTimer(self, interval=20)
        self._replay_timer.timeout.connect(self._replay_tick)

        self._build_ui()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4); root.setSpacing(6)

        left = QWidget(); left.setFixedWidth(320)
        ll = QVBoxLayout(left); ll.setContentsMargins(2, 2, 2, 2); ll.setSpacing(6)
        ll.addWidget(self._build_sys_grp())

        self._left_tabs = QTabWidget()
        self._left_tabs.addTab(self._build_manual_tab(), "Manuel")
        self._left_tabs.addTab(self._build_sweep_tab(),  "Sweep")
        self._left_tabs.currentChanged.connect(
            lambda i: self._right_stack.setCurrentIndex(i))
        ll.addWidget(self._left_tabs, stretch=1)
        root.addWidget(left)

        self._right_stack = QStackedWidget()
        self._right_stack.addWidget(self._build_manual_plots())
        self._right_stack.addWidget(self._build_sweep_plots())
        root.addWidget(self._right_stack, stretch=1)

    # ── System params (shared) ────────────────────────────────────────────────

    def _build_sys_grp(self):
        grp = QGroupBox("Système  (UFOPDT)  —  θ̈ = a²·θ − K·u(t−τd)")
        grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:10px;}")
        sl = QVBoxLayout(grp); sl.setContentsMargins(6, 14, 6, 6); sl.setSpacing(4)
        self._r_a   = _Row("Pôle  a",   self._DEF_A,   0.1, 20.0, 2, 0.5,  "rad/s")
        self._r_k   = _Row("Gain  K",   self._DEF_K,   1.0, 5000.,0, 50.,  "°/s²")
        self._r_tau = _Row("Retard τd", self._DEF_TAU, 0.0, 0.5,  3, 0.005,"s")
        for r in (self._r_a, self._r_k, self._r_tau):
            sl.addWidget(r); r.connect(self._schedule_instant)
        return grp

    # ── Manuel tab ────────────────────────────────────────────────────────────

    def _build_manual_tab(self):
        w = QWidget()
        ll = QVBoxLayout(w); ll.setContentsMargins(2, 2, 2, 2); ll.setSpacing(6)

        # PID gains with adjustable sliders
        gb_pid = QGroupBox("Gains PID  (sliders réglables : éditer les bornes)")
        gb_pid.setStyleSheet("QGroupBox{font-weight:bold;font-size:10px;}")
        pl = QVBoxLayout(gb_pid); pl.setContentsMargins(6, 16, 6, 6); pl.setSpacing(4)

        self._r_kp = _GainSlider("Kp", 0.150, 0.0, 0.5,  3)
        self._r_ki = _GainSlider("Ki", 0.000, 0.0, 0.2,  3)
        self._r_kd = _GainSlider("Kd", 0.030, 0.0, 0.1,  3)
        for r in (self._r_kp, self._r_ki, self._r_kd):
            pl.addWidget(r); r.connect(self._schedule_instant)

        hint = QLabel("← bornes grises éditables  |  valeur = spinbox bleu")
        hint.setStyleSheet("font-size:8px;color:#37474f;font-family:Consolas;")
        pl.addWidget(hint)

        self._sync_btn = QPushButton("↓ Copier depuis Live")
        self._sync_btn.setFixedHeight(24); self._sync_btn.setEnabled(False)
        self._sync_btn.clicked.connect(self._on_sync)
        pl.addWidget(self._sync_btn)
        ll.addWidget(gb_pid)

        # Simulation settings
        gb_cfg = QGroupBox("Paramètres de simulation")
        gb_cfg.setStyleSheet("QGroupBox{font-weight:bold;font-size:10px;}")
        cl = QVBoxLayout(gb_cfg); cl.setContentsMargins(6, 14, 6, 6); cl.setSpacing(4)
        row_cfg = QHBoxLayout(); row_cfg.setContentsMargins(0,0,0,0); row_cfg.setSpacing(6)
        row_cfg.addWidget(QLabel("θ₀"))
        self._r_theta0 = QDoubleSpinBox(); self._r_theta0.setRange(0.1, 30.0)
        self._r_theta0.setValue(2.0); self._r_theta0.setDecimals(1)
        self._r_theta0.setSuffix("°"); self._r_theta0.setFixedWidth(62)
        self._r_theta0.valueChanged.connect(self._schedule_instant)
        row_cfg.addWidget(self._r_theta0)
        row_cfg.addWidget(QLabel("Durée"))
        self._r_dur = QDoubleSpinBox(); self._r_dur.setRange(1.0, 60.0)
        self._r_dur.setValue(5.0); self._r_dur.setDecimals(1)
        self._r_dur.setSuffix("s"); self._r_dur.setFixedWidth(62)
        self._r_dur.valueChanged.connect(self._schedule_instant)
        row_cfg.addWidget(self._r_dur)
        row_cfg.addStretch()
        cl.addLayout(row_cfg)
        ll.addWidget(gb_cfg)

        # Status
        self._status = QLabel("Déplacer un curseur pour simuler…")
        self._status.setStyleSheet(
            "font-size:10px;font-family:Consolas;color:#90a4ae;"
            "padding:4px;border:1px solid #37474f;border-radius:3px;")
        self._status.setWordWrap(True)
        ll.addWidget(self._status)

        # Robot viz
        gb_viz = QGroupBox("Visualisation (rejoue en boucle)")
        gb_viz.setStyleSheet("QGroupBox{font-weight:bold;font-size:10px;}")
        vl = QVBoxLayout(gb_viz); vl.setContentsMargins(4, 12, 4, 4)
        self._viz = _RobotViz(); self._viz.set_angle(2.0)
        vl.addWidget(self._viz)
        ll.addWidget(gb_viz)
        ll.addStretch()
        return w

    # ── Sweep tab ─────────────────────────────────────────────────────────────

    def _build_sweep_tab(self):
        w = QWidget()
        ll = QVBoxLayout(w); ll.setContentsMargins(2, 2, 2, 2); ll.setSpacing(5)

        gb_sw = QGroupBox("Plage des gains")
        gb_sw.setStyleSheet("QGroupBox{font-weight:bold;font-size:10px;}")
        sl = QVBoxLayout(gb_sw); sl.setContentsMargins(6, 14, 6, 6); sl.setSpacing(3)

        def _range_row(label, def_lo, def_hi, def_n):
            h = QHBoxLayout(); h.setContentsMargins(0,0,0,0); h.setSpacing(3)
            l = QLabel(label); l.setStyleSheet("font-size:10px;color:#cccccc;font-family:Consolas;"); l.setFixedWidth(22)
            h.addWidget(l)
            lo = QDoubleSpinBox(); lo.setRange(0.0, 100.0); lo.setDecimals(3); lo.setValue(def_lo)
            lo.setFixedWidth(60); lo.setStepType(QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
            h.addWidget(lo); h.addWidget(QLabel("→"))
            hi = QDoubleSpinBox(); hi.setRange(0.0, 100.0); hi.setDecimals(3); hi.setValue(def_hi)
            hi.setFixedWidth(60); hi.setStepType(QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
            h.addWidget(hi); h.addWidget(QLabel("N"))
            n = QSpinBox(); n.setRange(2, 9999); n.setValue(def_n); n.setFixedWidth(52)
            h.addWidget(n)
            sl.addLayout(h)
            return lo, hi, n

        self._kp_lo, self._kp_hi, self._kp_n = _range_row("Kp", 0.04, 0.30, 10)
        self._kd_lo, self._kd_hi, self._kd_n = _range_row("Kd", 0.005, 0.06, 10)

        ki_row = QHBoxLayout(); ki_row.setContentsMargins(0,0,0,0); ki_row.setSpacing(4)
        ki_row.addWidget(QLabel("Ki fixe"))
        self._ki_fixed = QDoubleSpinBox(); self._ki_fixed.setRange(0.0, 10.0)
        self._ki_fixed.setDecimals(3); self._ki_fixed.setValue(0.0); self._ki_fixed.setFixedWidth(60)
        ki_row.addWidget(self._ki_fixed); ki_row.addStretch()
        sl.addLayout(ki_row)

        cfg_row = QHBoxLayout(); cfg_row.setContentsMargins(0,0,0,0); cfg_row.setSpacing(4)
        cfg_row.addWidget(QLabel("θ₀"))
        self._sw_theta0 = QDoubleSpinBox(); self._sw_theta0.setRange(0.5, 30.0)
        self._sw_theta0.setValue(2.0); self._sw_theta0.setDecimals(1); self._sw_theta0.setSuffix("°")
        self._sw_theta0.setFixedWidth(56); cfg_row.addWidget(self._sw_theta0)
        cfg_row.addWidget(QLabel("dur."))
        self._sw_dur = QDoubleSpinBox(); self._sw_dur.setRange(1.0, 60.0)
        self._sw_dur.setValue(5.0); self._sw_dur.setDecimals(1); self._sw_dur.setSuffix("s")
        self._sw_dur.setFixedWidth(56); cfg_row.addWidget(self._sw_dur)
        cfg_row.addStretch()
        sl.addLayout(cfg_row)
        ll.addWidget(gb_sw)

        self._sw_count_lbl = QLabel("10 × 10 = 100 essais  (~0.1 s)")
        self._sw_count_lbl.setStyleSheet("font-size:9px;color:#78909c;font-family:Consolas;")
        ll.addWidget(self._sw_count_lbl)
        for s in (self._kp_n, self._kd_n, self._sw_dur):
            s.valueChanged.connect(self._update_count_lbl)

        br2 = QHBoxLayout()
        self._sw_run_btn = QPushButton("▶ Lancer sweep")
        self._sw_run_btn.setFixedHeight(28)
        self._sw_run_btn.setStyleSheet(
            "QPushButton{background:#1565c0;color:white;font-weight:bold;border-radius:3px;}"
            "QPushButton:hover{background:#1976d2;}"
            "QPushButton:disabled{background:#37474f;color:#546e7a;}")
        self._sw_run_btn.clicked.connect(self._launch_sweep)
        br2.addWidget(self._sw_run_btn)
        self._sw_stop_btn = QPushButton("⏹"); self._sw_stop_btn.setFixedWidth(32)
        self._sw_stop_btn.setFixedHeight(28); self._sw_stop_btn.setEnabled(False)
        self._sw_stop_btn.clicked.connect(self._abort_sweep)
        br2.addWidget(self._sw_stop_btn)
        ll.addLayout(br2)

        self._sw_progress = QProgressBar()
        self._sw_progress.setRange(0, 100); self._sw_progress.setValue(0)
        self._sw_progress.setFixedHeight(12)
        ll.addWidget(self._sw_progress)
        self._sw_status_lbl = QLabel("—")
        self._sw_status_lbl.setStyleSheet("font-size:9px;color:#78909c;font-family:Consolas;")
        ll.addWidget(self._sw_status_lbl)

        mr = QHBoxLayout(); mr.setContentsMargins(0,0,0,0)
        mr.addWidget(QLabel("Couleur :"))
        self._metric_combo = QComboBox()
        self._metric_combo.addItems(["RMS 1s (°)", "Max absolu (°)", "Settling (s)", "Saturation (%)"])
        self._metric_combo.setFixedHeight(22)
        self._metric_combo.currentIndexChanged.connect(self._refresh_heatmap)
        mr.addWidget(self._metric_combo); mr.addStretch()
        ll.addLayout(mr)

        self._sw_table = QTableWidget(0, 6)
        self._sw_table.setHorizontalHeaderLabels(["Kp", "Kd", "Ki", "RMS°", "Max°", "Settled"])
        self._sw_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._sw_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._sw_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._sw_table.setStyleSheet("font-size:10px;font-family:Consolas;")
        self._sw_table.setMaximumHeight(150)
        self._sw_table.cellClicked.connect(self._on_table_row_click)
        ll.addWidget(self._sw_table)

        apply_btn = QPushButton("→ Appliquer dans Manuel")
        apply_btn.setFixedHeight(24); apply_btn.clicked.connect(self._apply_selected)
        ll.addWidget(apply_btn)
        ll.addStretch()
        return w

    # ── Manuel plots ──────────────────────────────────────────────────────────

    def _build_manual_plots(self):
        glw = pg.GraphicsLayoutWidget()
        glw.setBackground("#1e1e1e")

        self._p_angle = glw.addPlot(row=0, col=0, title="Angle de tangage (°)")
        self._p_angle.showGrid(x=True, y=True, alpha=0.25)
        self._p_angle.setLabel("left", "angle (°)"); self._p_angle.addLegend(offset=(10,10))
        self._p_angle.setYRange(-55, 55, padding=0)
        for y in (0, _SAFETY, -_SAFETY):
            self._p_angle.addLine(y=y, pen=pg.mkPen(
                C_SAFE if abs(y)==_SAFETY else C_ZERO, width=1, style=Qt.PenStyle.DashLine))
        self._c_ang = self._p_angle.plot(pen=pg.mkPen(C_ANGLE, width=2), name="θ")

        self._p_pid = glw.addPlot(row=1, col=0, title="Sortie PID (normalisée)")
        self._p_pid.showGrid(x=True, y=True, alpha=0.25)
        self._p_pid.setLabel("left", "normalisé"); self._p_pid.setLabel("bottom", "t (s)")
        self._p_pid.addLegend(offset=(10,10)); self._p_pid.setYRange(-1.3, 1.3, padding=0)
        for y in (0, 1, -1):
            self._p_pid.addLine(y=y, pen=pg.mkPen(
                "#37474f" if abs(y)==1 else C_ZERO, width=1, style=Qt.PenStyle.DashLine))
        self._c_drv = self._p_pid.plot(pen=pg.mkPen(C_DRIVE, width=2,
                                                      style=Qt.PenStyle.DashLine), name="drive")
        self._c_pp  = self._p_pid.plot(pen=pg.mkPen(C_PP, width=1.5), name="P")
        self._c_pi  = self._p_pid.plot(pen=pg.mkPen(C_PI, width=1.5), name="I")
        self._c_pd  = self._p_pid.plot(pen=pg.mkPen(C_PD, width=1.5), name="D")
        self._p_pid.setXLink(self._p_angle)
        glw.ci.setSpacing(8)
        return glw

    # ── Sweep plots ───────────────────────────────────────────────────────────

    def _build_sweep_plots(self):
        w = QWidget()
        lay = QVBoxLayout(w); lay.setContentsMargins(0,0,0,0); lay.setSpacing(4)

        self._pw_heat = pg.PlotWidget()
        self._pw_heat.setBackground("#1e1e1e")
        self._pw_heat.setLabel("bottom", "Kp"); self._pw_heat.setLabel("left", "Kd")
        self._pw_heat.setTitle("Heatmap Kp × Kd  (vert=bon, rouge=mauvais, rouge foncé=crash)")
        self._pw_heat.showGrid(x=True, y=True, alpha=0.15)
        self._heat_img = pg.ImageItem()
        self._heat_img.mouseClickEvent = self._on_heat_click
        self._pw_heat.addItem(self._heat_img)
        self._heat_sel = pg.ScatterPlotItem(
            size=14, pen=pg.mkPen("white", width=2), brush=pg.mkBrush(None))
        self._pw_heat.addItem(self._heat_sel)
        lay.addWidget(self._pw_heat, stretch=2)

        self._pw_sel = pg.PlotWidget()
        self._pw_sel.setBackground("#1e1e1e")
        self._pw_sel.setTitle("Essai sélectionné — angle (°)")
        self._pw_sel.setLabel("bottom", "t (s)"); self._pw_sel.setLabel("left", "angle (°)")
        self._pw_sel.showGrid(x=True, y=True, alpha=0.2)
        for y in (0, _SAFETY, -_SAFETY):
            self._pw_sel.addLine(y=y, pen=pg.mkPen(
                C_SAFE if abs(y)==_SAFETY else C_ZERO, width=1, style=Qt.PenStyle.DashLine))
        self._sel_curve = self._pw_sel.plot(pen=pg.mkPen("#42a5f5", width=2))
        self._sel_info  = pg.TextItem("Cliquer sur une cellule", anchor=(0, 1), color="#90a4ae")
        self._pw_sel.addItem(self._sel_info)
        lay.addWidget(self._pw_sel, stretch=1)
        return w

    # ── Core trial runner ─────────────────────────────────────────────────────

    @staticmethod
    def _run_trial(a, K, tau, kp, ki, kd, theta0=2.0, duration_s=5.0,
                   full=False):
        dt = _DT; n = int(duration_s / dt)
        dn = max(1, round(tau / dt))
        dbuf = deque([0.0] * dn, maxlen=dn)
        theta = theta0; theta_d = 0.0; i_acc = 0.0; a2 = a * a

        angs = np.empty(n); us = np.empty(n)
        pps  = np.empty(n) if full else None
        pis  = np.empty(n) if full else None
        pds  = np.empty(n) if full else None
        valid = n

        for step in range(n):
            p = kp * theta
            i_acc = max(-0.5, min(0.5, i_acc + theta * dt))
            d = kd * theta_d
            u = max(-1.0, min(1.0, p + ki * i_acc + d))
            u_del = dbuf[0]; dbuf.append(u)
            theta_d += (a2 * theta - K * u_del) * dt
            theta   += theta_d * dt
            angs[step] = theta; us[step] = u
            if full:
                pps[step] = p; pis[step] = ki * i_acc; pds[step] = d
            if abs(theta) >= _SAFETY:
                valid = step + 1; break

        survived = valid == n
        v_ang = angs[:valid]; v_us = us[:valid]
        last_n  = max(1, int(min(1.0, valid * dt) / dt))
        rms     = float(np.std(v_ang[-last_n:])) if survived else 99.0
        max_a   = float(np.max(np.abs(v_ang))) if valid > 0 else 0.0
        within2 = np.where(np.abs(v_ang) < 2.0)[0]
        settled = float(within2[0] * dt) if len(within2) > 0 else float("inf")
        sat_pct = float(np.mean(np.abs(v_us) >= 0.99)) * 100.0 if valid > 0 else 0.0

        return {
            "survived": survived, "rms_deg": rms, "max_abs_deg": max_a,
            "settling_s": settled, "sat_pct": sat_pct,
            "angs": angs, "us": us, "pps": pps, "pis": pis, "pds": pds,
            "valid": valid,
        }

    # ── Instant manual simulation ─────────────────────────────────────────────

    def _schedule_instant(self):
        self._debounce.start()

    def _run_instant(self):
        r = self._run_trial(
            self._r_a.value(), self._r_k.value(), self._r_tau.value(),
            self._r_kp.value(), self._r_ki.value(), self._r_kd.value(),
            self._r_theta0.value(), self._r_dur.value(), full=True,
        )
        self._instant_result = r
        v = r["valid"]
        t = np.arange(v) * _DT

        self._c_ang.setData(x=t, y=r["angs"][:v])
        self._c_drv.setData(x=t, y=r["us"][:v])
        self._c_pp.setData( x=t, y=r["pps"][:v])
        self._c_pi.setData( x=t, y=r["pis"][:v])
        self._c_pd.setData( x=t, y=r["pds"][:v])

        dur = self._r_dur.value()
        self._p_angle.setXRange(0, dur, padding=0.02)

        if r["survived"]:
            rms = r["rms_deg"]; col = "#66bb6a" if rms < 1.5 else ("#ffd54f" if rms < 5.0 else "#ef5350")
            sett = f"{r['settling_s']:.2f}s" if r["settling_s"] != float("inf") else "∞"
            self._set_status(
                f"Survécu   RMS={rms:.2f}°   Max={r['max_abs_deg']:.1f}°   Settled={sett}", col)
        else:
            t_crash = v * _DT
            self._set_status(
                f"CRASH  t={t_crash:.2f}s   θ={r['angs'][v-1]:.1f}°", "#ef5350")

        # robot viz replay
        self._replay_timer.stop()
        self._replay_angs = r["angs"][:v]
        self._replay_idx  = 0
        self._replay_timer.start()

    def _replay_tick(self):
        if self._replay_angs is None: return
        # advance 4 frames per tick (≈ 5× speed at 20ms tick)
        self._replay_idx += 4
        if self._replay_idx >= len(self._replay_angs):
            self._replay_idx = 0
        self._viz.set_angle(self._replay_angs[self._replay_idx])

    def _set_status(self, text, color):
        self._status.setText(text)
        self._status.setStyleSheet(
            f"font-size:10px;font-family:Consolas;color:{color};"
            "padding:4px;border:1px solid #37474f;border-radius:3px;")

    # ── Live gains sync ───────────────────────────────────────────────────────

    def sync_gains(self, kp, ki, kd):
        self._live_kp, self._live_ki, self._live_kd = kp, ki, kd
        self._sync_btn.setEnabled(True)

    def _on_sync(self):
        self._r_kp.set_value(self._live_kp)
        self._r_ki.set_value(self._live_ki)
        self._r_kd.set_value(self._live_kd)

    # ── Sweep ─────────────────────────────────────────────────────────────────

    def _update_count_lbl(self):
        n = self._kp_n.value() * self._kd_n.value()
        dur = self._sw_dur.value()
        steps = n * int(dur / _DT)
        # rough estimate: ~3M iterations/s in CPython
        est_s = steps / 3_000_000
        est_str = f"~{est_s:.0f} s" if est_s >= 1.0 else f"~{est_s*1000:.0f} ms"
        self._sw_count_lbl.setText(
            f"{self._kp_n.value()} × {self._kd_n.value()} = {n} essais  ({est_str})")

    def _launch_sweep(self):
        self._sweep_kp_vals = np.linspace(
            self._kp_lo.value(), self._kp_hi.value(), self._kp_n.value())
        self._sweep_kd_vals = np.linspace(
            self._kd_lo.value(), self._kd_hi.value(), self._kd_n.value())
        n_kp = len(self._sweep_kp_vals); n_kd = len(self._sweep_kd_vals)
        self._sweep_res = [[None]*n_kd for _ in range(n_kp)]
        self._sweep_abort = False; self._sweep_i = 0
        self._sw_progress.setValue(0); self._sw_table.setRowCount(0)
        self._heat_img.clear()
        self._sw_run_btn.setEnabled(False); self._sw_stop_btn.setEnabled(True)
        self._sweep_timer.start()

    def _sweep_next_row(self):
        i = self._sweep_i
        n_kp = len(self._sweep_kp_vals); n_kd = len(self._sweep_kd_vals)
        if i >= n_kp or self._sweep_abort:
            self._finish_sweep(); return
        kp = self._sweep_kp_vals[i]; ki = self._ki_fixed.value()
        a = self._r_a.value(); K = self._r_k.value(); tau = self._r_tau.value()
        t0 = self._sw_theta0.value(); dur = self._sw_dur.value()
        for j, kd in enumerate(self._sweep_kd_vals):
            self._sweep_res[i][j] = self._run_trial(a, K, tau, kp, ki, kd, t0, dur)
        done = (i + 1) * n_kd; total = n_kp * n_kd
        self._sw_progress.setValue(int(done * 100 / total))
        self._sw_status_lbl.setText(f"{done}/{total}  Kp={kp:.3f}")
        self._refresh_heatmap()
        self._sweep_i += 1

    def _abort_sweep(self): self._sweep_abort = True

    def _finish_sweep(self):
        self._sweep_timer.stop()
        self._sw_run_btn.setEnabled(True); self._sw_stop_btn.setEnabled(False)
        self._sw_progress.setValue(100 if not self._sweep_abort else self._sw_progress.value())
        n_kp = len(self._sweep_kp_vals); n_kd = len(self._sweep_kd_vals)
        if not self._sweep_abort:
            surv = sum(1 for i in range(n_kp) for j in range(n_kd)
                       if self._sweep_res[i][j] and self._sweep_res[i][j]["survived"])
            self._sw_status_lbl.setText(f"Terminé — {surv}/{n_kp*n_kd} survivants")
        else:
            self._sw_status_lbl.setText("Interrompu.")
        self._refresh_heatmap()
        self._fill_results_table()

    def _refresh_heatmap(self):
        if self._sweep_res is None: return
        kp_vals = self._sweep_kp_vals; kd_vals = self._sweep_kd_vals
        n_kp = len(kp_vals); n_kd = len(kd_vals)
        metric = self._metric_combo.currentIndex()

        vals = np.full((n_kp, n_kd), np.nan)
        for i in range(n_kp):
            for j in range(n_kd):
                r = self._sweep_res[i][j]
                if r is None or not r["survived"]: continue
                vals[i, j] = (r["rms_deg"], r["max_abs_deg"],
                               r["settling_s"] if r["settling_s"] != float("inf") else 30.0,
                               r["sat_pct"])[metric]

        valid = vals[~np.isnan(vals)]
        vmin = float(valid.min()) if len(valid) else 0.0
        vmax = float(valid.max()) if len(valid) else 1.0
        if vmax == vmin: vmax = vmin + 1.0

        img = np.zeros((n_kp, n_kd, 4), dtype=np.uint8)
        for i in range(n_kp):
            for j in range(n_kd):
                r = self._sweep_res[i][j]
                if r is None:
                    img[i, j] = [30, 30, 30, 255]
                elif not r["survived"]:
                    img[i, j] = [120, 20, 20, 255]
                else:
                    t = float(np.clip((vals[i, j] - vmin) / (vmax - vmin), 0.0, 1.0))
                    img[i, j] = ([int(255*t*2), 200, 0, 255] if t < 0.5
                                  else [200, int(200*(1-(t-0.5)*2)), 0, 255])

        self._heat_img.setImage(img, autoLevels=False)
        if n_kp > 1 and n_kd > 1:
            kp_s = (kp_vals[-1]-kp_vals[0])/(n_kp-1)
            kd_s = (kd_vals[-1]-kd_vals[0])/(n_kd-1)
            self._heat_img.setRect(QRectF(
                kp_vals[0]-kp_s/2, kd_vals[0]-kd_s/2,
                kp_vals[-1]-kp_vals[0]+kp_s, kd_vals[-1]-kd_vals[0]+kd_s))

    def _fill_results_table(self):
        if self._sweep_res is None: return
        ki = self._ki_fixed.value(); rows = []
        for i, kp in enumerate(self._sweep_kp_vals):
            for j, kd in enumerate(self._sweep_kd_vals):
                r = self._sweep_res[i][j]
                if r and r["survived"]:
                    rows.append((r["rms_deg"], kp, kd, ki,
                                  r["max_abs_deg"], r["settling_s"], i, j))
        rows.sort(key=lambda x: x[0])
        top = rows[:15]; self._sw_table.setRowCount(len(top))
        for ri, (rms, kp, kd, ki_, max_a, sett, _i, _j) in enumerate(top):
            sett_str = f"{sett:.2f}" if sett != float("inf") else "∞"
            for ci, val in enumerate([f"{kp:.3f}", f"{kd:.3f}", f"{ki_:.3f}",
                                       f"{rms:.2f}", f"{max_a:.1f}", sett_str]):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if ci == 3:
                    item.setForeground(QColor(
                        "#66bb6a" if rms < 1.0 else ("#ffd54f" if rms < 3.0 else "#ef9a9a")))
                item.setData(Qt.ItemDataRole.UserRole, (_i, _j))
                self._sw_table.setItem(ri, ci, item)

    def _on_table_row_click(self, row, _col):
        item = self._sw_table.item(row, 0)
        if item: self._show_trial(*item.data(Qt.ItemDataRole.UserRole))

    def _on_heat_click(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton or self._sweep_res is None:
            return
        pos = ev.pos()
        n_kp = len(self._sweep_kp_vals); n_kd = len(self._sweep_kd_vals)
        i = max(0, min(n_kp-1, int(pos.x())))
        j = max(0, min(n_kd-1, int(pos.y())))
        self._show_trial(i, j); ev.accept()

    def _show_trial(self, i, j):
        if self._sweep_res is None: return
        r = self._sweep_res[i][j]
        if r is None: return
        kp = self._sweep_kp_vals[i]; kd = self._sweep_kd_vals[j]
        ki = self._ki_fixed.value()
        self._heat_sel.setData(x=[kp], y=[kd])
        v = r["valid"]
        t = np.arange(v) * _DT
        self._sel_curve.setData(x=list(t), y=list(r["angs"][:v]))
        status = "OK" if r["survived"] else f"CRASH t={v*_DT:.2f}s"
        sett = f"{r['settling_s']:.2f}s" if r["settling_s"] != float("inf") else "∞"
        self._sel_info.setText(
            f"Kp={kp:.3f}  Kd={kd:.3f}  Ki={ki:.3f}  |  "
            f"{status}  RMS={r['rms_deg']:.2f}°  settled={sett}")
        self._sel_info.setPos(0.0, -_SAFETY + 2)

    def _apply_selected(self):
        sel = self._sw_table.selectedItems()
        if not sel: return
        item = self._sw_table.item(sel[0].row(), 0)
        if item is None: return
        i, j = item.data(Qt.ItemDataRole.UserRole)
        self._r_kp.set_value(self._sweep_kp_vals[i])
        self._r_kd.set_value(self._sweep_kd_vals[j])
        self._r_ki.set_value(self._ki_fixed.value())
        self._left_tabs.setCurrentIndex(0)
        self._schedule_instant()
