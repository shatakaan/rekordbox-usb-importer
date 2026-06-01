"""
Async Rekordbox USB database opener.

Provides DbLoadWorker (QRunnable) and open_usb_db_async() for opening a
Rekordbox USB database in a background thread via QThreadPool, avoiding
GUI freeze during the sqlcipher decryption step (typically 0.5–2s).

Format routing (pyrekordbox 0.4.4 API):
  - UsbFormat.DEVICE_LIBRARY_PLUS -> Rekordbox6Database(exportLibrary.db, unlock=False)
    exportLibrary.db — CDJ-TOUR2, XDJ-RX3, and newer hardware.
    USB exports are NOT encrypted (confirmed Assumption A3 — download-key
    removed in 0.4.4), so unlock=False skips the sqlcipher decryption step.
  - UsbFormat.REKORDBOX_PDB       -> Rekordbox6Database(export.pdb, unlock=False)
    export.pdb — CDJ-3000, CDJ-2000NXS2, CDJ-2000, DDJ-1000.
    Also unencrypted on USB media.

NOTE on API: PATTERNS.md described DeviceLibraryPlus / DeviceLibrary as the
intended classes. These do NOT exist in pyrekordbox 0.4.4 — the package only
exposes Rekordbox6Database (the local master.db handler). Rekordbox6Database
accepts an explicit path= argument and can open any Rekordbox SQLite DB,
including USB exports, when called with unlock=False (for the unencrypted USB
exports) or unlock=True with the default embedded key. This is the correct
API to use in 0.4.4; DeviceLibraryPlus/DeviceLibrary may be added in a future
version. When upgrading pyrekordbox, check whether those classes exist and
migrate db_loader.py accordingly.

Security:
  - Paths resolved via Path.resolve() before passing to Rekordbox6Database
    (path traversal guard, ASVS V5).
  - Unsupported formats (NOT_REKORDBOX, UNSUPPORTED) are rejected in
    open_usb_db_async before any DB constructor is called (T-02-05).
  - No explicit write calls — Phase 1 is strictly read-only (T-02-03).

Anti-pattern avoided: Rekordbox6Database with no path argument opens
~/Library/Pioneer/rekordbox/master.db. Always pass path= explicitly for
USB databases.
"""

import logging
from pathlib import Path

from pyrekordbox import Rekordbox6Database
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from core.format_detector import UsbFormat

logger = logging.getLogger(__name__)

# Type alias matching the planned DeviceLibraryPlus/DeviceLibrary interface.
# In pyrekordbox 0.4.4 both USB formats are opened via Rekordbox6Database.
_RekordboxDb = Rekordbox6Database


class DbLoadWorker(QRunnable):
    """Opens a Rekordbox USB database in a background thread.

    Routes to the correct pyrekordbox open call based on the detected USB
    format. In pyrekordbox 0.4.4 both DEVICE_LIBRARY_PLUS and REKORDBOX_PDB
    formats use Rekordbox6Database(path=..., unlock=False) because USB exports
    are unencrypted (Assumption A3 confirmed).

    Communicate results back to the main thread exclusively via Qt signals —
    never call Qt widget methods directly from the worker thread.
    """

    class Signals(QObject):
        """Qt signals for DbLoadWorker result delivery."""

        finished = Signal(object)  # Rekordbox6Database instance (USB opened)
        error = Signal(str)        # error message string

    def __init__(self, mount: Path, usb_format: UsbFormat):
        """Initialise the worker.

        Args:
            mount: Path to the USB mount point (e.g. /Volumes/USB_STICK).
            usb_format: The format detected by detect_usb_format().
        """
        super().__init__()
        self.mount = mount
        self.usb_format = usb_format
        self.signals = DbLoadWorker.Signals()

    def run(self):
        """Open the database and emit finished or error signal.

        Called by QThreadPool in a background thread — do NOT call directly.
        """
        try:
            if self.usb_format == UsbFormat.DEVICE_LIBRARY_PLUS:
                pioneer_dir = (self.mount / "PIONEER" / "rekordbox").resolve()
                # Matches planned DeviceLibraryPlus(str(pioneer_dir)) call.
                # In 0.4.4: pass the directory; Rekordbox6Database locates
                # exportLibrary.db within it via db_dir. USB exports are
                # unencrypted — unlock=False skips sqlcipher.
                db_path = pioneer_dir / "exportLibrary.db"
                logger.info("Opening DeviceLibraryPlus: %s", db_path)
                db = Rekordbox6Database(path=str(db_path), unlock=False)
                logger.info("DeviceLibraryPlus (Rekordbox6Database) opened successfully")
                self.signals.finished.emit(db)

            elif self.usb_format == UsbFormat.REKORDBOX_PDB:
                pdb_path = (
                    self.mount / "PIONEER" / "rekordbox" / "export.pdb"
                ).resolve()
                logger.info("Opening DeviceLibrary (export.pdb): %s", pdb_path)
                # Matches planned DeviceLibrary(str(pdb_path)) call.
                db = Rekordbox6Database(path=str(pdb_path), unlock=False)
                logger.info("DeviceLibrary (export.pdb) opened successfully")
                self.signals.finished.emit(db)

            else:
                # Should not be reached if open_usb_db_async validates format first
                msg = f"Unsupported USB format in worker: {self.usb_format}"
                logger.error(msg)
                self.signals.error.emit(msg)

        except Exception as e:  # noqa: BLE001
            logger.error("DB open failed: %s", e)
            self.signals.error.emit(str(e))


def open_usb_db_async(
    mount: Path,
    usb_format: UsbFormat,
    on_success,
    on_error,
) -> None:
    """Open a Rekordbox USB database asynchronously via QThreadPool.

    Routes to the correct pyrekordbox open call based on usb_format, then
    calls on_success with the opened DB object or on_error with an error
    message string.

    Args:
        mount: Path to the USB mount point.
        usb_format: Format detected by detect_usb_format(). Must be
            DEVICE_LIBRARY_PLUS or REKORDBOX_PDB — passing NOT_REKORDBOX or
            UNSUPPORTED calls on_error immediately without opening any DB
            (T-02-05 mitigation).
        on_success: Callable(Rekordbox6Database) — called on the main thread
            via Qt signal when the DB is ready.
        on_error: Callable(str) — called on the main thread via Qt signal on
            failure.
    """
    # Validate format before starting a background thread (T-02-05)
    if usb_format not in (UsbFormat.DEVICE_LIBRARY_PLUS, UsbFormat.REKORDBOX_PDB):
        msg = f"Cannot open database: unsupported format {usb_format}"
        logger.error(msg)
        on_error(msg)
        return

    worker = DbLoadWorker(mount, usb_format)
    worker.signals.finished.connect(on_success)
    worker.signals.error.connect(on_error)
    QThreadPool.globalInstance().start(worker)
