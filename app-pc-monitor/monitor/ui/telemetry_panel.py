"""
Telemetry panel: live scrolling plots backed by numpy ring buffers.
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QGroupBox,
    QCheckBox, QComboBox, QPushButton, QLabel, QSplitter,
    QSizePolicy, QFrame,
)

from monitor.model.ring_buffer import RingBuffer
from monitor.model.telemetry import STREAM_DEFS, StreamDef, SignalDef

pg.setConfigOptions(antialias=True, background="#1e1e1e", foreground="#cccccc")

_PERIODS_MS  = [5, 10, 20, 50, 100]
_BUFFER_DEPTH = 10_000

# Time window options for the scrolling X axis: (label, seconds or None=all)
_WINDOWS: list[tuple[str, float | None]] = [
    ("5 s",   5.0),
    ("10 s",  10.0),
    ("30 s",  30.0),
    ("1 min", 60.0),
    ("5 min", 300.0),
    ("All",   None),
]
_DEFAULT_WINDOW_IDX = 1   # 10 s


class _SignalTrack:
    """Runtime state for one signal: ring buffer + plot curve."""

    def __init__(self, sig: SignalDef, plot: pg.PlotItem) -> None:
        self.sig     = sig
        self.buffer  = RingBuffer(_BUFFER_DEPTH)
        self.visible = sig.default_visible
        pen = pg.mkPen(color=sig.color, width=1)
        self.curve: pg.PlotDataItem = plot.plot(
            np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64),
            pen=pen, name=sig.name,
        )
        # Only render points visible in the current view; auto-subsample the rest.
        # This keeps frame time constant regardless of ring-buffer size.
        self.curve.setDownsampling(auto=True, method="subsample")
        self.curve.setClipToView(True)
        self.curve.setVisible(self.visible)

    def push(self, ts: float, value: float) -> None:
        self.buffer.push(ts, value)

    def refresh(self, window_s: float | None = None) -> None:
        if not self.visible or self.buffer.count == 0:
            return
        times, vals = self.buffer.get_arrays()
        if window_s is not None and len(times) > 0:
            cutoff = times[-1] - window_s
            idx = int(np.searchsorted(times, cutoff))
            times = times[idx:]
            vals  = vals[idx:]
        if len(times):
            self.curve.setData(x=times, y=vals)

    def set_visible(self, v: bool) -> None:
        self.visible = v
        self.curve.setVisible(v)
        if not v:
            self.curve.setData([], [])

    def clear(self) -> None:
        self.buffer.clear()
        self.curve.setData([], [])


class _StreamWidget(QGroupBox):
    """Collapsible group: controls + one PlotWidget per stream."""

    stream_enable_changed = Signal(int, bool, int)  # stream_id, enable, period_ms

    def __init__(self, sdef: StreamDef, parent=None) -> None:
        super().__init__(parent)
        self._sdef   = sdef
        self._tracks: dict[str, _SignalTrack] = {}
        self._frozen = False

        self.setTitle(f"  Stream 0x{sdef.stream_id:02X} — {sdef.label}")
        self.setCheckable(True)
        self.setChecked(False)
        self.toggled.connect(self._on_toggled)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── Controls row ──────────────────────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.setSpacing(6)

        self._period_combo = QComboBox()
        for p in _PERIODS_MS:
            self._period_combo.addItem(f"{p} ms", userData=p)
        default_idx = _PERIODS_MS.index(sdef.default_period_ms) \
                      if sdef.default_period_ms in _PERIODS_MS else 1
        self._period_combo.setCurrentIndex(default_idx)
        self._period_combo.currentIndexChanged.connect(self._on_toggled)

        self._window_combo = QComboBox()
        for label, secs in _WINDOWS:
            self._window_combo.addItem(label, userData=secs)
        self._window_combo.setCurrentIndex(_DEFAULT_WINDOW_IDX)
        self._window_combo.setToolTip("Scrolling time window shown on the plot")

        self._freeze_btn = QPushButton("Freeze")
        self._freeze_btn.setCheckable(True)
        self._freeze_btn.setFixedWidth(70)
        self._freeze_btn.toggled.connect(self._on_freeze)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setFixedWidth(60)
        self._clear_btn.clicked.connect(self._on_clear)

        ctrl.addWidget(QLabel("Period:"))
        ctrl.addWidget(self._period_combo)
        ctrl.addWidget(QLabel("Window:"))
        ctrl.addWidget(self._window_combo)
        ctrl.addWidget(self._freeze_btn)
        ctrl.addWidget(self._clear_btn)
        ctrl.addStretch()

        # Signal checkboxes
        self._checkboxes: dict[str, QCheckBox] = {}
        for sig in sdef.signals:
            cb = QCheckBox()
            cb.setChecked(sig.default_visible)
            cb.setStyleSheet(f"QCheckBox::indicator {{ background: {sig.color}; }}")
            cb.setToolTip(sig.name)
            cb.stateChanged.connect(
                lambda state, s=sig.name: self._on_signal_toggle(s, state)
            )
            ctrl.addWidget(cb)
            ctrl.addWidget(QLabel(sig.name))
            self._checkboxes[sig.name] = cb

        root.addLayout(ctrl)

        # ── Plot ──────────────────────────────────────────────────────────
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setMinimumHeight(160)
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._plot_widget.getPlotItem().addLegend(offset=(10, 10))
        self._plot_widget.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        # Disable X-axis auto-range so our manual setXRange is never
        # silently overridden by pyqtgraph after each setData() call.
        self._plot_widget.getPlotItem().getViewBox().disableAutoRange(
            pg.ViewBox.XAxis
        )

        plot_item = self._plot_widget.getPlotItem()
        for sig in sdef.signals:
            track = _SignalTrack(sig, plot_item)
            self._tracks[sig.name] = track

        root.addWidget(self._plot_widget)

    # ── Public ────────────────────────────────────────────────────────────────
    def push_sample(self, data: dict[str, float]) -> None:
        if self._frozen:
            return
        ts = data.get("timestamp_ms", time.monotonic() * 1000)
        for name, track in self._tracks.items():
            if name in data:
                track.push(ts / 1000.0, data[name])

    def refresh_plots(self) -> None:
        if self._frozen:
            return
        window_s: float | None = self._window_combo.currentData()

        # Use the latest timestamp present in the buffers as "now".
        # Do NOT use time.monotonic(): the buffer timestamps may be firmware
        # uptime (seconds since MCU boot) which is on a completely different
        # scale from the PC clock.
        t_now: float | None = None
        for track in self._tracks.values():
            t = track.buffer.latest_time
            if t is not None and (t_now is None or t > t_now):
                t_now = t

        for track in self._tracks.values():
            track.refresh(window_s=window_s)

        if window_s is not None and t_now is not None:
            self._plot_widget.setXRange(t_now - window_s, t_now, padding=0)
        else:
            self._plot_widget.enableAutoRange(axis="x")

    def clear_all(self) -> None:
        for track in self._tracks.values():
            track.clear()

    @property
    def stream_id(self) -> int:
        return self._sdef.stream_id

    @property
    def enabled(self) -> bool:
        return self.isChecked()

    @property
    def period_ms(self) -> int:
        return self._period_combo.currentData()

    # ── Slots ─────────────────────────────────────────────────────────────────
    def _on_toggled(self, *_) -> None:
        self.stream_enable_changed.emit(
            self._sdef.stream_id, self.isChecked(), self.period_ms
        )

    def _on_signal_toggle(self, name: str, state: int) -> None:
        track = self._tracks.get(name)
        if track:
            track.set_visible(bool(state))

    def _on_freeze(self, checked: bool) -> None:
        self._frozen = checked
        self._freeze_btn.setText("Unfreeze" if checked else "Freeze")

    def _on_clear(self) -> None:
        self.clear_all()


class TelemetryPanel(QWidget):
    """
    Main telemetry panel: one _StreamWidget per defined stream,
    all placed in a scroll area.
    A QTimer drives plot refresh at ~30 FPS.
    """

    stream_enable_changed = Signal(int, bool, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._stream_widgets: dict[int, _StreamWidget] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        self._vbox = QVBoxLayout(container)
        self._vbox.setSpacing(8)
        self._vbox.setContentsMargins(4, 4, 4, 4)

        for sid, sdef in STREAM_DEFS.items():
            w = _StreamWidget(sdef)
            w.stream_enable_changed.connect(self.stream_enable_changed)
            self._stream_widgets[sid] = w
            self._vbox.addWidget(w)

        self._vbox.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll)

        # 30 FPS refresh timer
        from PySide6.QtCore import QTimer
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._refresh_all)
        self._timer.start()

    # ── Public slots ─────────────────────────────────────────────────────────
    def on_telemetry_sample(self, stream_id: int, data: dict) -> None:
        w = self._stream_widgets.get(stream_id)
        if w:
            w.push_sample(data)

    # ── Internal ──────────────────────────────────────────────────────────────
    def _refresh_all(self) -> None:
        for w in self._stream_widgets.values():
            if w.enabled:
                w.refresh_plots()
