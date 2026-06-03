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

from PySide6.QtCore import QObject, QRunnable, QSettings, QThreadPool, Qt, Signal
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
from core.duplicate_detector import check_duplicate
from core.format_detector import USB_04_ERROR_MESSAGE, UsbFormat
from core.import_controller import ImportController, ImportPlan, ImportResult, TrackImportStatus
from core.usb_scanner import USBScanner
from ui.log_panel import LogPanel
from ui.playlist_panel import PlaylistPanel
from ui.track_panel import TrackPanel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# QSettings helpers (D-03, UX-04)
# ---------------------------------------------------------------------------

def _settings() -> QSettings:
    """Return a QSettings instance backed by the macOS NativeFormat plist.

    Maps to: ~/Library/Preferences/com.com-inevents-mainz.PlaylistConverter.plist
    (Qt prepends the org name — cosmetic quirk, data is correct.)
    """
    return QSettings(
        QSettings.Format.NativeFormat,
        QSettings.Scope.UserScope,
        "com.inevents-mainz",
        "PlaylistConverter",
    )


def save_session(
    usb_mount,
    selected_ids,
    settings: QSettings | None = None,
) -> None:
    """Persist last USB mount path and selected playlist IDs to QSettings.

    Args:
        usb_mount: Path or str of the USB mount point, or None.
        selected_ids: Iterable of int playlist IDs to persist.
        settings: Optional QSettings instance for dependency injection (tests).
                  Uses _settings() when None.
    """
    s = settings if settings is not None else _settings()
    if usb_mount is not None:
        s.setValue("usb/last_mount", str(usb_mount))
    s.setValue("usb/selected_playlist_ids", sorted(int(x) for x in selected_ids))
    s.sync()


def load_session(
    settings: QSettings | None = None,
) -> tuple:
    """Read persisted USB mount and playlist IDs from QSettings.

    Args:
        settings: Optional QSettings instance for dependency injection (tests).
                  Uses _settings() when None.

    Returns:
        Tuple of (mount_str: str | None, ids: set[int]).
        mount_str is None when no prior save exists.
    """
    s = settings if settings is not None else _settings()
    mount_str = s.value("usb/last_mount", None)
    raw_ids = s.value("usb/selected_playlist_ids", [], type=list)
    ids = {int(x) for x in raw_ids if x is not None}
    return (mount_str, ids)


class _ImportSignals(QObject):
    """Qt signals for cross-thread communication from the import worker."""
    progress = Signal(str)
    finished = Signal(object)
    error = Signal(str)


class _ImportWorker(QRunnable):
    """Background QRunnable that executes the full import pipeline.

    All UI updates must go via signals — never touch widgets from run().
    """

    def __init__(self, controller: ImportController, plan: ImportPlan) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self.signals = _ImportSignals()
        self._controller = controller
        self._plan = plan

    def run(self) -> None:
        try:
            result = self._controller.run_import_plan(self._plan)
            self.signals.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(str(exc))

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

        # Import pipeline state
        self._pdb_db = None          # USB PDB database (read)
        self._usb_mount: Path | None = None
        self._rb6_db = None          # local Rekordbox6Database (write)
        self._import_plan: ImportPlan | None = None
        self._import_controller: ImportController | None = None
        self._import_tracks: dict = {}  # track_id -> TrackRow

        # Session state (UX-04, D-03)
        self._last_usb_name: str = ""
        self._restored_playlist_ids: set = set()

        self._build_ui()
        self._setup_usb_watcher()
        self._restore_session()

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
        self.import_btn.setToolTip("Select playlists to enable import")
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

        # --- Wire import button ---
        self.import_btn.clicked.connect(self._on_import_clicked)

        # --- Enable import button when any playlist is checked ---
        self.playlist_panel.tree.itemChanged.connect(self._on_playlist_check_changed)

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
            if self._last_usb_name:
                self.playlist_panel.set_empty_state(
                    f"'{self._last_usb_name}' was last used — connect it to continue"
                )
            else:
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
            # Session restore: log when last USB matches by name (D-03)
            if self._last_usb_name and supported_usbs[0][0].name == self._last_usb_name:
                logger.info("Session restored: auto-selecting %s", mount.name)
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
        self._usb_mount = mount
        # Persist last-selected USB even if user never clicks Import (D-03)
        self._save_session()
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
                # Store USB database + mount for import pipeline
                self._pdb_db = db
                data = self.usb_combo.currentData()
                if data:
                    self._usb_mount = data[0]
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
                self._apply_restored_checkboxes()
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
                self._apply_restored_checkboxes()
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

    # ------------------------------------------------------------------
    # Import pipeline handlers (D-01..D-04, SAFE-01..04)
    # ------------------------------------------------------------------

    def _on_playlist_check_changed(self, _item) -> None:
        """Enable Import button when at least one playlist checkbox is checked."""
        has_checked = self._any_playlist_checked(self.playlist_panel.tree.invisibleRootItem())
        self.import_btn.setEnabled(has_checked)

    def _any_playlist_checked(self, parent_item) -> bool:
        """Recursively check if any tree item has a checked state."""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.checkState(0) != Qt.CheckState.Unchecked:
                return True
            if self._any_playlist_checked(child):
                return True
        return False

    def _on_import_clicked(self) -> None:
        """Handle Import button click — preflight, build plan, show summary."""
        if self._pdb_db is None or self._usb_mount is None:
            logger.error("No USB database loaded — cannot import")
            return

        selected_playlists = self._get_checked_playlists(
            self.playlist_panel.tree.invisibleRootItem()
        )
        if not selected_playlists:
            logger.warning("No playlists selected")
            return

        # Save session before building plan (covers crash scenarios — D-03)
        self._save_session()

        # Open local Rekordbox6Database
        try:
            from pyrekordbox import Rekordbox6Database
            self._rb6_db = Rekordbox6Database()
        except Exception:
            logger.exception("Failed to open local Rekordbox database")
            return

        # Preflight: block if Rekordbox is running, USB not mounted
        self._import_controller = ImportController(self._rb6_db, self._usb_mount)
        preflight = self._import_controller.run_preflight()
        if not preflight.ok:
            logger.error("Import blocked: %s", preflight.message)
            return

        # Build import plan — check each track against local DB for duplicates
        plan = ImportPlan(mount=self._usb_mount, selected_playlists=selected_playlists)
        self._import_tracks = {}
        mount_resolved = str(self._usb_mount.resolve())

        for playlist_row in selected_playlists:
            for song in (playlist_row.songs or []):
                track = song.content
                if track.track_id in plan.track_statuses:
                    continue
                rel_path = track.file_path.lstrip("/")
                abs_path = (self._usb_mount / rel_path).resolve()
                if not str(abs_path).startswith(mount_resolved):
                    logger.warning("Skipping track with unsafe path: %s", track.file_path)
                    plan.track_statuses[track.track_id] = TrackImportStatus.SKIP
                else:
                    existing = check_duplicate(
                        self._rb6_db, abs_path,
                        track.title or "", track.artist_name or "",
                        track.duration_secs or 0,
                    )
                    status = TrackImportStatus.DUPLICATE if existing else TrackImportStatus.NEW
                    plan.track_statuses[track.track_id] = status
                self._import_tracks[track.track_id] = track

        # Build full playlist-by-id map for folder hierarchy reconstruction
        all_playlists: dict = {}

        def _collect_all(playlists: list) -> None:
            for p in playlists:
                all_playlists[p.id] = p
                _collect_all(getattr(p, "children", None) or [])

        _collect_all(self._pdb_db.playlists)
        plan.all_playlists_by_id = all_playlists

        self._import_plan = plan

        # Preview backup path (SAFE-03 / D-14)
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_preview = str(self._rb6_db._db_dir / f"master.db.backup.{ts}")
        logger.info("Backup will be created at: %s", backup_preview)

        # Switch TrackPanel to summary mode (D-01, D-03)
        self.track_panel.populate_import_summary(
            plan, self._import_tracks, backup_path_str=backup_preview
        )
        self.track_panel.back_clicked.connect(self._on_import_back)
        self.track_panel.confirm_clicked.connect(self._on_confirm_import)
        self.import_btn.setEnabled(False)

    def _on_import_back(self) -> None:
        """Handle Back button — return to browse view."""
        self.track_panel.restore_browse_mode()
        self._repopulate_selected_playlist()
        try:
            self.track_panel.back_clicked.disconnect(self._on_import_back)
            self.track_panel.confirm_clicked.disconnect(self._on_confirm_import)
        except RuntimeError:
            pass
        self.import_btn.setEnabled(True)

    def _on_confirm_import(self) -> None:
        """Handle Confirm Import — update force_import_ids and start worker."""
        if self._import_plan is None or self._import_controller is None:
            return

        # Read user's per-track selections (DUPLICATE override via checked state)
        selections = self.track_panel.get_import_selections()
        self._import_plan.force_import_ids = {
            tid
            for tid, will in selections.items()
            if will and self._import_plan.track_statuses.get(tid) == TrackImportStatus.DUPLICATE
        }

        worker = _ImportWorker(self._import_controller, self._import_plan)
        worker.signals.progress.connect(lambda msg: logger.info("%s", msg))
        worker.signals.finished.connect(self._on_import_finished)
        worker.signals.error.connect(lambda err: logger.error("Import error: %s", err))

        # Disable buttons while import runs (T-02-05-03)
        self.import_btn.setEnabled(False)
        self.track_panel._confirm_btn.setEnabled(False)
        self.track_panel._back_btn.setEnabled(False)

        QThreadPool.globalInstance().start(worker)

    def _on_import_finished(self, result: ImportResult) -> None:
        """Handle import completion — show post-import summary panel (UX-03)."""
        logger.info(
            "Import complete — %d imported, %d skipped, %d failed. Backup: %s",
            result.imported_count,
            result.skipped_count,
            result.failed_count,
            result.backup_path,
        )
        # Persist successful import state (D-03)
        self._save_session()

        # Disconnect import-phase signal handlers
        try:
            self.track_panel.back_clicked.disconnect(self._on_import_back)
            self.track_panel.confirm_clicked.disconnect(self._on_confirm_import)
        except RuntimeError:
            pass

        # Re-enable buttons before switching mode (populate_post_import_summary
        # will disable Back and relabel Confirm -> Done)
        self.track_panel._confirm_btn.setEnabled(True)
        self.track_panel._back_btn.setEnabled(True)

        # Show per-playlist result table (UX-03, D-01, D-02)
        self.track_panel.populate_post_import_summary(result, self._import_plan)

        # Wire Done button to summary-done handler
        self.track_panel.confirm_clicked.connect(self._on_summary_done)

    def _on_summary_done(self) -> None:
        """Handle Done button in post-import mode — return to browse view."""
        self.track_panel.restore_browse_mode()
        self._repopulate_selected_playlist()
        try:
            self.track_panel.confirm_clicked.disconnect(self._on_summary_done)
        except RuntimeError:
            pass
        self.import_btn.setEnabled(True)

    def _repopulate_selected_playlist(self) -> None:
        """Re-populate the TrackPanel with the currently selected playlist."""
        selected = self.playlist_panel.tree.selectedItems()
        if selected:
            playlist = selected[0].data(0, Qt.ItemDataRole.UserRole)
            if playlist is not None:
                self.track_panel.populate(playlist)

    def _get_checked_playlists(self, parent_item) -> list:
        """Return all checked PlaylistRow objects (any Attribute value).

        A PlaylistRow is included if its checkbox is Checked, regardless of
        whether it is flagged as a folder — PDB root containers can have
        Attribute=1 (folder) while directly holding songs.
        For PartiallyChecked items, recurse into children to find fully
        checked entries.
        """
        result = []
        for i in range(parent_item.childCount()):
            item = parent_item.child(i)
            playlist = item.data(0, Qt.ItemDataRole.UserRole)
            state = item.checkState(0)
            if playlist is not None and state == Qt.CheckState.Checked:
                result.append(playlist)
                # Still recurse — nested playlists inside a checked folder
                # should also be importable individually
            if state != Qt.CheckState.Unchecked:
                result.extend(self._get_checked_playlists(item))
        return result

    # ------------------------------------------------------------------
    # Session persistence (UX-04, D-03)
    # ------------------------------------------------------------------

    def _save_session(self) -> None:
        """Persist USB mount and checked playlist IDs to QSettings plist."""
        checked_ids = self._get_checked_playlist_ids()
        save_session(self._usb_mount, checked_ids)

    def _restore_session(self) -> None:
        """Read persisted USB mount and playlist IDs from QSettings plist."""
        mount_str, ids = load_session()
        self._last_usb_name = Path(mount_str).name if mount_str else ""
        self._restored_playlist_ids = ids

    def _get_checked_playlist_ids(self) -> set:
        """Return IDs of all checked playlist tree items.

        Returns:
            set of int playlist IDs.
        """
        ids: set = set()
        self._collect_checked_ids(self.playlist_panel.tree.invisibleRootItem(), ids)
        return ids

    def _collect_checked_ids(self, parent_item, ids: set) -> None:
        """Recursively collect checked playlist IDs from the tree."""
        for i in range(parent_item.childCount()):
            item = parent_item.child(i)
            playlist = item.data(0, Qt.ItemDataRole.UserRole)
            if playlist is not None and item.checkState(0) == Qt.CheckState.Checked:
                ids.add(int(playlist.id))
            self._collect_checked_ids(item, ids)

    def _apply_restored_checkboxes(self) -> None:
        """Pre-check playlist tree items whose IDs match the restored session.

        Called after playlist_panel.populate() in _on_db_loaded.
        Clears _restored_playlist_ids after applying so a subsequent USB
        swap does not re-apply stale IDs.
        """
        if not self._restored_playlist_ids:
            return
        self._check_matching_items(
            self.playlist_panel.tree.invisibleRootItem(),
            self._restored_playlist_ids,
        )
        self._restored_playlist_ids = set()

    def _check_matching_items(self, parent_item, ids: set) -> None:
        """Recursively set Checked state on items whose playlist.id is in ids."""
        for i in range(parent_item.childCount()):
            item = parent_item.child(i)
            playlist = item.data(0, Qt.ItemDataRole.UserRole)
            if playlist is not None and int(playlist.id) in ids:
                item.setCheckState(0, Qt.CheckState.Checked)
            self._check_matching_items(item, ids)

    def _show_error(self, message: str) -> None:
        """Log an error to both the Python logger and the log panel widget.

        Args:
            message: error description to display.
        """
        logger.error(message)
        self.log_panel.log_error(message)
