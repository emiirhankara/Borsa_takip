"""BIST ve ABD hisseleri icin masaustu takip uygulamasi."""
import sys
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PiyasaRadar")
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
