import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from monitor.ui.main_window import MainWindow


def main() -> None:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Robot Monitor")
    app.setOrganizationName("robot-pendulum")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
