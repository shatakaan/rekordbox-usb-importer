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
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.db_loader import open_usb_db_async
from core.format_detector import USB_04_ERROR_MESSAGE, UsbFormat
from core.usb_scanner import USBScanner
from ui.log_panel import LogPanel
from ui.playlist_panel import PlaylistPanel
from ui.track_panel import TrackPanel

logger = logging.getLogger(__name__)


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
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(4)

        # --- Toolbar row (44px fixed height) ---
        toolbar_row = QHBoxLayout()
        toolbar_row.setContentsMargins(0, 0, 0, 0)
        toolbar_row.setSpacing(8)

        usb_label = QLabel("USB Source:")
        toolbar_row.addWidget(usb_label)

        self.usb_combo = QComboBox()
        self.usb_combo.setMinimumWidth(200)
        toolbar_row.addWidget(self.usb_combo)

        toolbar_row.addStretch()  # push Import button to the right

        self.import_btn = QPushButton("Import Selected")
        self.import_btn.setEnabled(False)
        self.import_btn.setFixedHeight(32)
        self.import_btn.setToolTip(
            "Import is not active in this version. "
            "Select playlists to prepare for import."
        )
        self.import_btn.setAccessibleName(
            "Import selected playlists button, currently disabled"
        )
        toolbar_row.addWidget(self.import_btn)

        root_layout.addLayout(toolbar_row)

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
        self.log_panel.setMaximumHeight(240)
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

        supported_usbs = [
            (m, f) for m, f in usbs if f == UsbFormat.DEVICE_LIBRARY_PLUS
        ]
        pdb_usbs = [
            (m, f) for m, f in usbs if f == UsbFormat.REKORDBOX_PDB
        ]

        # Log PDB USBs present alongside supported USBs (informational)
        for mount, _ in pdb_usbs:
            logger.warning(
                "USB at %s uses export.pdb format — not yet fully supported. "
                "Re-export from Rekordbox 6 or 7 with Device Library Plus enabled.",
                mount,
            )

        if not usbs:
            # No Rekordbox USB detected at all
            placeholder = self.usb_combo.model().item(0) if False else None
            self.usb_combo.addItem("No Rekordbox USB found")
            # Make non-selectable
            model = self.usb_combo.model()
            model.item(0).setEnabled(False)
            self.playlist_panel.set_empty_state("Connect a Rekordbox USB stick")
            logger.info("No Rekordbox USB found")

        elif not supported_usbs:
            # Only PDB USB(es) — unsupported format
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
            db: Rekordbox6Database instance (or future DeviceLibraryPlus) opened
                by DbLoadWorker. Called on the main thread via Qt signal.
        """
        try:
            all_playlists = list(db.get_playlist())
        except Exception:  # noqa: BLE001
            logger.exception("Failed to list playlists from DB")
            self.playlist_panel.set_empty_state("Error loading playlists — see log")
            return

        # Count tracks across all playlists (best-effort — attribute name may vary)
        track_count = 0
        for p in all_playlists:
            try:
                songs = getattr(p, "Songs", None) or []
                track_count += len(songs)
            except Exception:  # noqa: BLE001
                pass

        logger.info(
            "Loaded %d playlists, %d tracks", len(all_playlists), track_count
        )

        # Build root-level playlist list (ParentID None or 0)
        # SPIKE NOTE: if AttributeError on ParentID, fall back to flat list.
        # Record actual attribute name in SUMMARY for Phase 2 schema fix.
        try:
            roots = [
                p for p in all_playlists
                if getattr(p, "ParentID", None) in (None, 0)
            ]
        except Exception:  # noqa: BLE001
            logger.warning(
                "ParentID attribute not found on DjmdPlaylist — "
                "falling back to flat list. Note actual attribute name for Phase 2."
            )
            roots = all_playlists

        self.playlist_panel.populate(roots)

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
