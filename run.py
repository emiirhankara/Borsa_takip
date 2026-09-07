"""BIST ve ABD hisseleri icin masaustu takip uygulamasi."""
import sys
import logging
import traceback
from pathlib import Path


def _configure_logging() -> None:
    log_path = Path(__file__).with_name("app.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()],
    )


def main() -> int:
    from PyQt5.QtWidgets import QApplication
    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("PiyasaRadar")
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    _configure_logging()
    try:
        raise SystemExit(main())
    except Exception:
        error_text = traceback.format_exc()
        Path(__file__).with_name("startup_error.log").write_text(error_text, encoding="utf-8")
        print(error_text, file=sys.stderr)
        try:
            from PyQt5.QtWidgets import QApplication, QMessageBox

            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(
                None,
                "PiyasaRadar başlatılamadı",
                "Uygulama başlatılırken hata oluştu. Ayrıntılar startup_error.log dosyasına kaydedildi.",
            )
        finally:
            input("Kapatmak için Enter'a basın...")
        raise
