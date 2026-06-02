"""
Main application window for Playlist Converter.

Provides MainWindow: QMainWindow shell with:
  - Toolbar row: USB source label, USB picker QComboBox, Import button (disabled)
  - Main QSplitter: PlaylistPanel (left) + TrackPanel (right)
  - LogPanel at the bottom

USB watcher (D-01, D-02):
  - USBScanner watches /Volumes and emits usbs_changed on plug/unplug
  - Single USB auto-selected (D-02); multiple USBs show picker; none shows placeholder
  - DB open routed by format (DEVICE_LIBRARY_PLUS vs REKORDBOX_PDB)
  - REKORDBOX_PDB-only USB shows USB-04 error in log and tree (USB-04)

All DB open operations are delegated to core/db_loader.py which runs them in a
background QThreadPool worker (D-03 / T-03-03: keep GUI responsive during DB open).

Security (T-03-01): DB path validation is handled in db_loader.open_usb_db_async
and format_detector.detect_usb_format — paths are resolved before use.
"""

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.db_loader import PdbDatabase, open_usb_db_async
from core.format_detector import USB_04_ERROR_MESSAGE, UsbFormat
from core.usb_scanner import USBScanner
from ui.log_panel import LogPanel
from ui.playlist_panel import PlaylistPanel
from ui.track_panel import TrackPanel

logger = logging.getLogger(__name__)

_MAX_PLAYLIST_DEPTH = 50  # T-06-02: DoS guard — Rekordbox never exceeds ~10 levels


def _iter_all_playlists(playlists: list, _depth: int = 0) -> list:
    """Return a flat list of all playlists (including nested children).

    Used for track-count calculation in _on_db_loaded.

    Security (T-06-02): Recursion depth is limited to _MAX_PLAYLIST_DEPTH.
    Rekordbox USB exports never exceed 5–10 nesting levels in practice; the
    limit guards against corrupt / crafted PDB files with circular references.

    Args:
        playlists: list of PlaylistRow (or duck-typing-compatible) objects.
        _depth: internal recursion counter; do not pass from call sites.

    Returns:
        Flat list containing every playlist node reachable from `playlists`.
    """
    if _depth > _MAX_PLAYLIST_DEPTH:
        logger.warning(
            "_iter_all_playlists: max depth %d reached — truncating recursion",
            _MAX_PLAYLIST_DEPTH,
        )
        return []
    result = []
    for p in playlists:
        result.append(p)
        children = getattr(p, "Children", None) or getattr(p, "children", None) or []
        if children:
            result.extend(_iter_all_playlists(children, _depth + 1))
    return result


class MainWindow(QMainWindow):
    """QMainWindow shell — two-panel playlist browser with live USB watcher.

    Layout:
      ┌─ Toolbar (44px) ──────────────────────────────────────────┐
      │  USB Source: [QComboBox]          [Import Selected] (off)  │
      ├─ QSplitter (Horizontal, stretch=1) ───────────────────────┤
      │  PlaylistPanel (260px)  │  TrackPanel (fill)              │
      ├─ LogPanel (120px, min 80px) ──────────────────────────────┤
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Playlist Converter")
        self.setMinimumSize(960, 640)
        self.resize(960, 640)

        self._build_ui()
        self._setup_usb_watcher()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Build the central widget layout."""
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- Toolbar (styled QFrame, edge-to-edge) ---
        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        toolbar.setFixedHeight(52)
        toolbar_row = QHBoxLayout(toolbar)
        toolbar_row.setContentsMargins(12, 0, 12, 0)
        toolbar_row.setSpacing(10)

        usb_label = QLabel("USB SOURCE")
        usb_label.setObjectName("sectionHeader")
        toolbar_row.addWidget(usb_label)

        self.usb_combo = QComboBox()
        self.usb_combo.setMinimumWidth(220)
        toolbar_row.addWidget(self.usb_combo)

        toolbar_row.addStretch()

        self.import_btn = QPushButton("Import Selected")
        self.import_btn.setObjectName("primaryBtn")
        self.import_btn.setEnabled(False)
        self.import_btn.setFixedHeight(34)
        self.import_btn.setToolTip(
            "Import is not active in this version. "
            "Select playlists to prepare for import."
        )
        self.import_btn.setAccessibleName(
            "Import selected playlists button, currently disabled"
        )
        toolbar_row.addWidget(self.import_btn)

        root_layout.addWidget(toolbar)

        # --- Main splitter (Horizontal) ---
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.playlist_panel = PlaylistPanel()
        self.track_panel = TrackPanel()
        main_splitter.addWidget(self.playlist_panel)
        main_splitter.addWidget(self.track_panel)
        main_splitter.setSizes([260, 700])
        main_splitter.setMinimumHeight(400)
        root_layout.addWidget(main_splitter, stretch=1)

        # --- Log panel ---
        self.log_panel = LogPanel()
        self.log_panel.setMinimumHeight(80)
        self.log_panel.setMaximumHeight(220)
        root_layout.addWidget(self.log_panel, stretch=0)

        # --- Wire playlist selection → track population ---
        self.playlist_panel.playlist_selected.connect(self.track_panel.populate)

        # --- Initial tree state before any USB scan ---
        self.playlist_panel.set_empty_state("Connect a Rekordbox USB stick")

        # --- USB combo change handler ---
        self.usb_combo.currentIndexChanged.connect(self._on_usb_combo_changed)

    # ------------------------------------------------------------------
    # USB watcher wiring (D-01, D-02)
    # ------------------------------------------------------------------

    def _setup_usb_watcher(self) -> None:
        """Instantiate USBScanner and wire usbs_changed signal."""
        self._scanner = USBScanner(parent=self)
        self._scanner.usbs_changed.connect(self._on_usbs_changed)
        # Trigger initial scan synchronously on startup
        self._on_usbs_changed(self._scanner.current_usbs())

    def _on_usbs_changed(self, usbs: list) -> None:
        """Handle USB plug/unplug events from USBScanner.

        Args:
            usbs: list of (mount_path: Path, format: UsbFormat) tuples,
                already filtered to non-NOT_REKORDBOX by USBScanner._scan().
        """
        # Disconnect combo signal to prevent spurious _on_usb_combo_changed
        # calls while we rebuild the item list
        self.usb_combo.blockSignals(True)
        self.usb_combo.clear()

        # Both DEVICE_LIBRARY_PLUS and REKORDBOX_PDB are now fully supported.
        # (REKORDBOX_PDB is handled via pdb_parser since Plan 01-06.)
        supported_usbs = [
            (m, f)
            for m, f in usbs
            if f in (UsbFormat.DEVICE_LIBRARY_PLUS, UsbFormat.REKORDBOX_PDB)
        ]

        if not usbs:
            # No Rekordbox USB detected at all
            self.usb_combo.addItem("No Rekordbox USB found")
            # Make non-selectable
            model = self.usb_combo.model()
            model.item(0).setEnabled(False)
            self.playlist_panel.set_empty_state("Connect a Rekordbox USB stick")
            logger.info("No Rekordbox USB found")

        elif not supported_usbs:
            # USBs present but none in a supported format
            self.usb_combo.addItem("No supported USB found (see log)")
            model = self.usb_combo.model()
            model.item(0).setEnabled(False)
            self.playlist_panel.set_empty_state(
                "Unsupported USB format — see log for details"
            )
            logger.error(USB_04_ERROR_MESSAGE)

        elif len(supported_usbs) == 1:
            # Exactly one supported USB — auto-select (D-02)
            mount, fmt = supported_usbs[0]
            label = f"{mount.name} (auto-selected)"
            self.usb_combo.addItem(label, userData=(mount, fmt))
            logger.info("USB detected: %s", mount)
            # Auto-load the single USB
            self._load_usb(mount, fmt)

        else:
            # Multiple supported USBs — show picker (D-02)
            placeholder_item_label = "Select a USB source..."
            self.usb_combo.addItem(placeholder_item_label, userData=None)
            model = self.usb_combo.model()
            model.item(0).setEnabled(False)
            for mount, fmt in supported_usbs:
                self.usb_combo.addItem(str(mount.name), userData=(mount, fmt))
            logger.info(
                "Multiple Rekordbox USB sticks detected. Select one from the dropdown."
            )
            self.playlist_panel.set_empty_state("Connect a Rekordbox USB stick")

        self.usb_combo.blockSignals(False)

    def _on_usb_combo_changed(self, index: int) -> None:
        """Handle user selecting a USB from the combo box.

        Args:
            index: the newly selected combo item index.
        """
        data = self.usb_combo.itemData(index)
        if data is None:
            return
        mount, fmt = data
        self._load_usb(mount, fmt)

    def _load_usb(self, mount: Path, usb_format: UsbFormat) -> None:
        """Trigger async DB open for the selected USB.

        Args:
            mount: Path to the USB mount point.
            usb_format: Detected format for format-specific routing.
        """
        logger.info(
            "Opening database on %s (format: %s)", mount.name, usb_format.name
        )
        self.playlist_panel.set_empty_state("Loading playlists...")
        open_usb_db_async(mount, usb_format, self._on_db_loaded, self._on_db_error)

    def _on_db_loaded(self, db) -> None:
        """Handle successful DB open from the background worker.

        Args:
            db: Either PdbDatabase (from pdb_parser, REKORDBOX_PDB format) or
                Rekordbox6Database (from pyrekordbox, DEVICE_LIBRARY_PLUS format).
                Called on the main thread via Qt signal.
        """
        try:
            if isinstance(db, PdbDatabase):
                # PDB path (export.pdb via pdb_parser)
                root_playlists = db.playlists
                track_count = sum(
                    len(p.Songs) for p in _iter_all_playlists(root_playlists)
                )
                logger.info(
                    "Loaded %d playlists, %d tracks (PDB)",
                    len(root_playlists), track_count,
                )
                self.playlist_panel.populate(root_playlists)
            else:
                # pyrekordbox ORM path (Rekordbox6Database — local master.db or
                # DEVICE_LIBRARY_PLUS exportLibrary.db)
                all_playlists = list(db.get_playlist())
                track_count = 0
                for p in all_playlists:
                    try:
                        songs = getattr(p, "Songs", None) or []
                        track_count += len(songs)
                    except Exception:  # noqa: BLE001
                        pass
                logger.info(
                    "Loaded %d playlists, %d tracks (ORM)",
                    len(all_playlists), track_count,
                )
                roots = [
                    p for p in all_playlists
                    if getattr(p, "ParentID", None) in (None, 0)
                ]
                self.playlist_panel.populate(roots)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to process loaded DB")
            self.playlist_panel.set_empty_state("Error loading playlists — see log")

    def _on_db_error(self, msg: str) -> None:
        """Handle DB open failure from the background worker.

        Args:
            msg: error message string from DbLoadWorker.
        """
        logger.error("DB open failed: %s", msg)
        self.playlist_panel.set_empty_state("Error loading DB — see log")

    def _show_error(self, message: str) -> None:
        """Log an error to both the Python logger and the log panel widget.

        Args:
            message: error description to display.
        """
        logger.error(message)
        self.log_panel.log_error(message)
