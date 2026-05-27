"""
app-cbc-tuning/main.py — Tuning des gains PID de la boucle d'équilibre.

Usage:
    py -3 main.py
    py -3 main.py --port COM4
"""
import sys

# PySide6 must be imported before numpy/pyqtgraph to avoid Qt DLL conflicts
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QPalette

from cbc_tuner.gui import CbcTuner


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="")
    args = ap.parse_args()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    pal = QPalette()
    pal.setColor(QPalette.Window,          QColor("#2b2b2b"))
    pal.setColor(QPalette.WindowText,      QColor("#cccccc"))
    pal.setColor(QPalette.Base,            QColor("#1e1e1e"))
    pal.setColor(QPalette.AlternateBase,   QColor("#252525"))
    pal.setColor(QPalette.Text,            QColor("#cccccc"))
    pal.setColor(QPalette.Button,          QColor("#3c3c3c"))
    pal.setColor(QPalette.ButtonText,      QColor("#cccccc"))
    pal.setColor(QPalette.Highlight,       QColor("#42a5f5"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)

    win = CbcTuner(args)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
