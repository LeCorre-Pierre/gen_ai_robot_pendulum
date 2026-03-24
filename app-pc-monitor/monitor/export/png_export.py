"""
PNG export for pyqtgraph PlotWidget.
"""

from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtCore import QSize
from PySide6.QtGui import QPixmap


def export_plot(plot_widget: pg.PlotWidget, path: str,
                width: int = 1280, height: int = 480) -> None:
    """
    Save `plot_widget` contents to a PNG file at `path`.
    Uses pyqtgraph's built-in exporter for lossless output.
    """
    exporter = pg.exporters.ImageExporter(plot_widget.getPlotItem())
    exporter.parameters()["width"]  = width
    exporter.parameters()["height"] = height
    exporter.export(path)
