"""
Log panel widget — QPlainTextEdit + QLogHandler for in-app status messages.

Provides:
  - QLogHandler: logging.Handler subclass that routes Python log records to a
    QPlainTextEdit widget with [HH:MM:SS] timestamps.
  - LogPanel: QWidget containing a label, the QPlainTextEdit, and wires
    QLogHandler to the root logger at INFO level.

Thread safety: QLogHandler.emit() must be called from the main thread only.
In Phase 1 the DbLoadWorker communicates results via Qt signals, which Qt
delivers on the main thread — so emit() is always called correctly.
If future phases call logging from QThread workers directly, add a Signal(str)
relay mechanism before calling appendPlainText() from a background thread.
"""

import logging

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QFrame, QLabel, QPlainTextEdit, QVBoxLayout

logger = logging.getLogger(__name__)


class QLogHandler(logging.Handler):
    """Routes Python log records to a QPlainTextEdit widget.

    Uses a [HH:MM:SS] timestamp prefix on each log entry (datefmt="%H:%M:%S").

    NOTE: emit() must be called from the main thread. If called from a
    QRunnable/QThread worker, relay via a Qt signal (Signal(str)) to the main
    thread before calling appendPlainText() — direct cross-thread widget access
    is not safe in Qt.
    """

    def __init__(self, widget: QPlainTextEdit):
        super().__init__()
        self._widget = widget
        self.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        """Format the log record and append it to the widget."""
        try:
            msg = self.format(record)
            self._widget.appendPlainText(msg)
            # Scroll to bottom after each new entry
            self._widget.verticalScrollBar().setValue(
                self._widget.verticalScrollBar().maximum()
            )
        except Exception:  # noqa: BLE001
            self.handleError(record)


class LogPanel(QFrame):
    """Bottom log panel — QPlainTextEdit wired to the root Python logger.

    Displays in-app status messages with [HH:MM:SS] timestamps in a
    system monospace font. Capped at 500 lines to prevent unbounded memory
    growth (UI-SPEC: setMaximumBlockCount(500)).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logFrame")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 8)
        layout.setSpacing(4)

        label = QLabel("ACTIVITY LOG")
        label.setObjectName("sectionHeader")
        layout.addWidget(label)

        self._text = QPlainTextEdit()
        self._text.setObjectName("logText")
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(500)
        mono_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono_font.setPointSize(11)
        self._text.setFont(mono_font)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._text)

        # Wire QLogHandler to root logger at INFO level
        self._handler = QLogHandler(self._text)
        self._handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(self._handler)

    def log_error(self, message: str) -> None:
        """Append a visually distinct error line directly to the log panel.

        Use for errors that need immediate display without going through the
        logger (e.g., from _show_error in MainWindow). The message is also
        available via the standard logging pipeline if called via logger.error().
        """
        self._text.appendPlainText(f"ERROR: {message}")
        self._text.verticalScrollBar().setValue(
            self._text.verticalScrollBar().maximum()
        )
