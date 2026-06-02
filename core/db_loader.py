"""
Async Rekordbox USB database opener.

Provides DbLoadWorker (QRunnable), PdbDatabase dataclass, and
open_usb_db_async() for opening a Rekordbox USB database in a background
thread via QThreadPool, avoiding GUI freeze during the DB-open step.

Format routing:
  - UsbFormat.DEVICE_LIBRARY_PLUS -> Rekordbox6Database(exportLibrary.db, unlock=False)
    exportLibrary.db — CDJ-TOUR2, XDJ-RX3, and newer hardware.
    USB exports are NOT encrypted (confirmed Assumption A3 — download-key
    removed in 0.4.4), so unlock=False skips the sqlcipher decryption step.
    Fallback: if exportLibrary.db raises "file is not a database", attempt
    export.pdb via pdb_parser (T-06-01).
  - UsbFormat.REKORDBOX_PDB       -> parse_export_pdb(export.pdb)
    export.pdb — CDJ-3000, CDJ-2000NXS2, CDJ-2000, DDJ-1000.
    Parsed with pure stdlib pdb_parser; returns PdbDatabase.

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
  - Paths resolved via Path.resolve() before any open call
    (path traversal guard, ASVS V5, T-06-01).
  - Unsupported formats (NOT_REKORDBOX, UNSUPPORTED) are rejected in
    open_usb_db_async before any DB constructor is called (T-02-05).
  - No explicit write calls — Phase 1 is strictly read-only (T-02-03).

Anti-pattern avoided: Rekordbox6Database with no path argument opens
~/Library/Pioneer/rekordbox/master.db. Always pass path= explicitly for
USB databases.
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from pyrekordbox import Rekordbox6Database
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from core.format_detector import UsbFormat
from core.pdb_parser import PdbParseError, parse_export_pdb
from core.usb_db import PlaylistRow, TrackRow

logger = logging.getLogger(__name__)

# Lazy import for sqlalchemy exception — avoid hard dependency at module level
try:
    from sqlalchemy.exc import DatabaseError as _SqlAlchemyDBError
except ImportError:
    _SqlAlchemyDBError = None  # type: ignore[assignment,misc]

# Type alias matching the planned DeviceLibraryPlus/DeviceLibrary interface.
# In pyrekordbox 0.4.4 both USB formats are opened via Rekordbox6Database.
_RekordboxDb = Rekordbox6Database


@dataclass
class PdbDatabase:
    """Ergebnis von parse_export_pdb() — container für Playlists und Tracks.

    Duck-typing-equivalent of Rekordbox6Database for the REKORDBOX_PDB format.
    Carries the already-parsed PlaylistRow tree and TrackRow lookup dict so
    _on_db_loaded() can immediately populate the GUI without a second parse.
    """

    playlists: list[PlaylistRow] = field(default_factory=list)
    """Root-level playlists (parent_id == 0), sorted by id."""

    tracks: dict[int, TrackRow] = field(default_factory=dict)
    """All tracks keyed by track_id."""


def _is_db_error(exc: Exception) -> bool:
    """Return True if exc indicates a corrupt / unreadable SQLite DB.

    Covers:
      - sqlite3.DatabaseError ("file is not a database", wrong key, etc.)
      - sqlalchemy.exc.DatabaseError (when SQLAlchemy wraps sqlite3)
      - Exception with the characteristic error message string
    """
    msg = str(exc).lower()
    if "file is not a database" in msg or "database disk image is malformed" in msg:
        return True
    if isinstance(exc, sqlite3.DatabaseError):
        return True
    if _SqlAlchemyDBError is not None and isinstance(exc, _SqlAlchemyDBError):
        return True
    return False


class DbLoadWorker(QRunnable):
    """Opens a Rekordbox USB database in a background thread.

    Routes to the correct open call based on the detected USB format:
      - DEVICE_LIBRARY_PLUS: Rekordbox6Database(exportLibrary.db, unlock=False)
        with automatic fallback to export.pdb via pdb_parser on DB-error.
      - REKORDBOX_PDB: parse_export_pdb(export.pdb) → PdbDatabase

    Communicate results back to the main thread exclusively via Qt signals —
    never call Qt widget methods directly from the worker thread.
    """

    class Signals(QObject):
        """Qt signals for DbLoadWorker result delivery."""

        finished = Signal(object)  # PdbDatabase or Rekordbox6Database
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
                db_path = pioneer_dir / "exportLibrary.db"
                logger.info("Opening DeviceLibraryPlus: %s", db_path)
                try:
                    db = Rekordbox6Database(path=str(db_path), unlock=False)
                    logger.info("DeviceLibraryPlus (Rekordbox6Database) opened successfully")
                    self.signals.finished.emit(db)
                except Exception as e:  # noqa: BLE001
                    if _is_db_error(e):
                        # SQLCipher key mismatch or unreadable DB —
                        # attempt fallback to export.pdb (T-06-01)
                        pdb_fallback = (
                            self.mount / "PIONEER" / "rekordbox" / "export.pdb"
                        ).resolve()  # T-06-01: resolve() prevents path traversal
                        if pdb_fallback.exists():
                            logger.warning(
                                "exportLibrary.db not readable (SQLCipher key mismatch) — "
                                "falling back to export.pdb for %s",
                                self.mount,
                            )
                            try:
                                root_playlists, tracks = parse_export_pdb(pdb_fallback)
                                db_pdb = PdbDatabase(
                                    playlists=root_playlists, tracks=tracks
                                )
                                logger.info(
                                    "PDB fallback: %d playlists, %d tracks",
                                    len(root_playlists), len(tracks),
                                )
                                self.signals.finished.emit(db_pdb)
                            except PdbParseError as e2:
                                self.signals.error.emit(
                                    f"PDB fallback also failed: {e2}"
                                )
                        else:
                            self.signals.error.emit(str(e))
                    else:
                        logger.error("DB open failed: %s", e)
                        self.signals.error.emit(str(e))

            elif self.usb_format == UsbFormat.REKORDBOX_PDB:
                pdb_path = (
                    self.mount / "PIONEER" / "rekordbox" / "export.pdb"
                ).resolve()
                logger.info("Opening export.pdb via pdb_parser: %s", pdb_path)
                try:
                    root_playlists, tracks = parse_export_pdb(pdb_path)
                    db = PdbDatabase(playlists=root_playlists, tracks=tracks)
                    logger.info(
                        "PDB parsed: %d playlists, %d tracks",
                        len(root_playlists), len(tracks),
                    )
                    self.signals.finished.emit(db)
                except PdbParseError as e:
                    msg = f"PDB parse failed: {e}"
                    logger.error(msg)
                    self.signals.error.emit(msg)

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
