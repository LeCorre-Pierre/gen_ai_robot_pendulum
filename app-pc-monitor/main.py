import signal
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer
from monitor.ui.main_window import MainWindow


def main() -> None:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Robot Monitor")
    app.setOrganizationName("robot-pendulum")

    # Allow Ctrl+C to close the app.
    # Qt's C++ event loop blocks Python signal delivery; a periodic no-op timer
    # wakes Python up so it can process SIGINT.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    _sigint_timer = QTimer()
    _sigint_timer.start(200)
    _sigint_timer.timeout.connect(lambda: None)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
