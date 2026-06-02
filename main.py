"""
Application entry point for Playlist Converter.

Run with:
    source .venv/bin/activate && python main.py

The application requires a PySide6-compatible display. On macOS this is the
default Aqua backend. For headless automated testing, set QT_QPA_PLATFORM=offscreen.
"""

import logging
import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.theme import apply_theme


def main() -> None:
    """Start the Playlist Converter application."""
    logging.basicConfig(level=logging.DEBUG)
    app = QApplication(sys.argv)
    apply_theme(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
