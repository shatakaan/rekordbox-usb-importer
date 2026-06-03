"""
Right panel — track list with 7 columns.

Provides TrackPanel: a QWidget containing a QTableWidget that displays the
tracks of the selected Rekordbox playlist. The table is read-only, sortable,
and uses alternating row colors for readability.

Column specification (D-04, UI-SPEC Right Panel — Track List):
  0: Title    — stretch (fills remaining width)
  1: Artist   — interactive, min 140px
  2: Album    — interactive, min 120px
  3: BPM      — fixed 60px, right-aligned
  4: Key      — fixed 52px, center-aligned
  5: Duration — fixed 60px, right-aligned
  6: Rating   — fixed 64px, center-aligned

Schema assumptions (RESEARCH.md Pitfall 5):
  - playlist.Songs: ORM relationship returning song membership rows
  - song.Content: the DjmdContent track object
  - content.Title, content.BPM, content.Tonality, content.Length, content.Rating
  - content.Artist.Name, content.Album.Name (may be None)
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.import_controller import ImportPlan, ImportResult, TrackImportStatus

logger = logging.getLogger(__name__)

COLUMNS = ["TITLE", "ARTIST", "ALBUM", "BPM", "KEY", "DURATION", "RATING"]
SUMMARY_COLUMNS = ["", "TITLE", "ARTIST", "BPM", "DURATION", "STATUS"]
RESULT_COLUMNS = ["PLAYLIST", "IMPORTED", "SKIPPED", "FAILED"]

_STATUS_COLORS = {
    "NEW": "#ADC6FF",
    "DUPLICATE": "#FFA040",
    "SKIP": "#8B90A0",
}


class TrackPanel(QWidget):
    """Right panel — QTableWidget with 7 columns for track display.

    Read-only, sortable, multi-row selectable. Populated by calling
    populate(playlist) with a DjmdPlaylist ORM object.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "browse"
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # --- Summary header (hidden in browse mode) ---
        self._summary_header = QWidget()
        self._summary_header.setObjectName("summaryHeader")
        header_layout = QHBoxLayout(self._summary_header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(8)

        self._back_btn = QPushButton("Back")
        self._back_btn.setObjectName("secondaryBtn")
        self._back_btn.setFixedWidth(72)
        header_layout.addWidget(self._back_btn)

        header_layout.addStretch()

        self._backup_label = QLabel("")
        self._backup_label.setObjectName("sectionHeader")
        header_layout.addWidget(self._backup_label)

        header_layout.addStretch()

        self._confirm_btn = QPushButton("Confirm Import")
        self._confirm_btn.setObjectName("primaryBtn")
        header_layout.addWidget(self._confirm_btn)

        self._summary_header.setVisible(False)
        self._layout.addWidget(self._summary_header)

        # Public signal aliases so MainWindow can connect without accessing private buttons
        self.back_clicked = self._back_btn.clicked
        self.confirm_clicked = self._confirm_btn.clicked

        # --- Track table ---
        self.table = QTableWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)

        self._apply_browse_column_sizes()

        # Behaviour flags (UI-SPEC Right Panel)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)

        self._layout.addWidget(self.table)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def populate_import_summary(
        self,
        plan,
        tracks: dict,
        backup_path_str: str = "",
    ) -> None:
        """Switch to summary mode showing import plan with STATUS column.

        Args:
            plan: ImportPlan with .track_statuses dict[int, TrackImportStatus].
            tracks: dict[int, TrackRow] mapping track_id to TrackRow.
            backup_path_str: Backup path string shown in header label.
        """
        self._mode = "summary"
        self._summary_header.setVisible(True)
        self._backup_label.setText(f"Backup: {backup_path_str}" if backup_path_str else "")

        self.table.setSortingEnabled(False)
        self.table.setColumnCount(len(SUMMARY_COLUMNS))
        self.table.setHorizontalHeaderLabels(SUMMARY_COLUMNS)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 32)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in (2, 3, 4):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(col, 100)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(5, 90)

        self.table.setRowCount(0)

        for track_id, status in plan.track_statuses.items():
            track = tracks.get(track_id)
            if track is None:
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)

            # Col 0: checkbox
            check_item = QTableWidgetItem()
            check_item.setData(Qt.ItemDataRole.UserRole, track_id)
            flags = Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            if status.value == "skip":
                flags = Qt.ItemFlag.ItemIsUserCheckable  # disabled
                check_item.setCheckState(Qt.CheckState.Unchecked)
            elif status.value == "duplicate":
                check_item.setCheckState(Qt.CheckState.Unchecked)
            else:
                check_item.setCheckState(Qt.CheckState.Checked)
            check_item.setFlags(flags)
            self.table.setItem(row, 0, check_item)

            # Col 1: Title
            self.table.setItem(row, 1, QTableWidgetItem(getattr(track, "title", "") or ""))

            # Col 2: Artist
            self.table.setItem(row, 2, QTableWidgetItem(getattr(track, "artist_name", "") or ""))

            # Col 3: BPM
            bpm = getattr(track, "bpm", None)
            bpm_str = str(int(bpm)) if bpm and bpm == int(bpm) else (f"{bpm:.1f}" if bpm else "")
            item_bpm = QTableWidgetItem(bpm_str)
            item_bpm.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, item_bpm)

            # Col 4: Duration
            dur_str = self._format_duration(getattr(track, "duration_secs", None))
            item_dur = QTableWidgetItem(dur_str)
            item_dur.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 4, item_dur)

            # Col 5: STATUS with color
            status_key = status.value.upper()
            status_item = QTableWidgetItem(status_key)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            color_hex = _STATUS_COLORS.get(status_key, "#8B90A0")
            status_item.setForeground(QBrush(QColor(color_hex)))
            self.table.setItem(row, 5, status_item)

    def get_import_selections(self) -> dict:
        """Return {track_id: will_import} from checkbox states in summary mode."""
        result = {}
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None:
                continue
            track_id = item.data(Qt.ItemDataRole.UserRole)
            will_import = item.checkState() == Qt.CheckState.Checked
            result[track_id] = will_import
        return result

    def populate_post_import_summary(
        self,
        result: "ImportResult",
        plan: "ImportPlan",
    ) -> None:
        """Switch to post_import mode showing per-playlist result table (UX-03, D-01, D-02).

        Args:
            result: ImportResult with aggregate imported/skipped/failed counts.
            plan: ImportPlan with selected_playlists, track_statuses, force_import_ids.
        """
        self._mode = "post_import"
        self._summary_header.setVisible(True)

        # D-02: hide Back button, relabel Confirm -> "Done"
        self._back_btn.setVisible(False)
        self._confirm_btn.setText("Done")

        # Aggregate header label
        self._backup_label.setText(
            f"{result.imported_count} imported  |  "
            f"{result.skipped_count} skipped  |  "
            f"{result.failed_count} failed"
        )

        # Configure table for RESULT_COLUMNS
        self.table.setSortingEnabled(False)
        self.table.setColumnCount(len(RESULT_COLUMNS))
        self.table.setHorizontalHeaderLabels(RESULT_COLUMNS)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(col, 90)

        self.table.setRowCount(0)

        # One row per selected playlist
        for playlist in plan.selected_playlists:
            imported = 0
            skipped = 0
            failed = 0

            for song in (getattr(playlist, "songs", None) or []):
                track_id = song.content.track_id
                status = plan.track_statuses.get(track_id)

                if status is None:
                    # No status entry — treat as imported (controller linked it)
                    imported += 1
                elif status == TrackImportStatus.SKIP:
                    skipped += 1
                elif status == TrackImportStatus.DUPLICATE:
                    if track_id in plan.force_import_ids:
                        imported += 1
                    else:
                        # DUPLICATE not force-imported: linked as existing entry
                        imported += 1
                else:
                    # NEW (or unknown positive status)
                    imported += 1

            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(getattr(playlist, "name", "") or ""))

            item_imp = QTableWidgetItem(str(imported))
            item_imp.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 1, item_imp)

            item_skip = QTableWidgetItem(str(skipped))
            item_skip.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, item_skip)

            item_fail = QTableWidgetItem(str(failed))
            item_fail.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, item_fail)

    def restore_browse_mode(self) -> None:
        """Switch back to the 7-column browse mode."""
        self._mode = "browse"
        self._summary_header.setVisible(False)
        self._back_btn.setVisible(True)
        self._confirm_btn.setText("Confirm Import")
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self._apply_browse_column_sizes()
        self.table.setRowCount(0)
        self.table.setSortingEnabled(True)

    def populate(self, playlist) -> None:
        """Load tracks from a DjmdPlaylist object into the table.

        Args:
            playlist: DjmdPlaylist ORM object whose .Songs relationship
                provides the track membership rows.
        """
        self.table.setSortingEnabled(False)  # disable during fill for performance
        self.table.setRowCount(0)
        try:
            songs = getattr(playlist, "Songs", None) or []
            for song in songs:
                try:
                    content = song.Content
                    row = self.table.rowCount()
                    self.table.insertRow(row)

                    # Title (col 0)
                    self._set_cell(row, 0, content.Title or "")

                    # Artist (col 1)
                    artist = (
                        getattr(content.Artist, "Name", "")
                        if getattr(content, "Artist", None)
                        else ""
                    )
                    self._set_cell(row, 1, artist or "")

                    # Album (col 2)
                    album = (
                        getattr(content.Album, "Name", "")
                        if getattr(content, "Album", None)
                        else ""
                    )
                    self._set_cell(row, 2, album or "")

                    # BPM (col 3) — integer display, 1 decimal only if non-integer
                    bpm_val = getattr(content, "BPM", None)
                    if bpm_val is not None:
                        bpm_str = (
                            str(int(bpm_val))
                            if bpm_val == int(bpm_val)
                            else f"{bpm_val:.1f}"
                        )
                    else:
                        bpm_str = ""
                    item_bpm = QTableWidgetItem(bpm_str)
                    item_bpm.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                    self.table.setItem(row, 3, item_bpm)

                    # Key / Tonality (col 4)
                    key_val = getattr(content, "Tonality", None) or ""
                    item_key = QTableWidgetItem(str(key_val))
                    item_key.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )
                    self.table.setItem(row, 4, item_key)

                    # Duration (col 5)
                    duration_str = self._format_duration(
                        getattr(content, "Length", None)
                    )
                    item_dur = QTableWidgetItem(duration_str)
                    item_dur.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                    self.table.setItem(row, 5, item_dur)

                    # Rating (col 6)
                    rating_val = getattr(content, "Rating", None)
                    rating_str = str(rating_val) if rating_val is not None else ""
                    item_rating = QTableWidgetItem(rating_str)
                    item_rating.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )
                    self.table.setItem(row, 6, item_rating)

                except Exception:  # noqa: BLE001
                    logger.exception("Failed to load track row %d", row if 'row' in dir() else -1)

        except Exception:  # noqa: BLE001
            logger.exception("Failed to load tracks from playlist")

        self.table.setSortingEnabled(True)

    def set_empty_state(self, message: str) -> None:
        """Clear the table and log the empty state message.

        Args:
            message: reason for the empty state (e.g. "Select a playlist to view tracks").
        """
        self.table.setRowCount(0)
        logger.debug("TrackPanel empty state: %s", message)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_browse_column_sizes(self) -> None:
        """Set column resize modes and widths for the 7-column browse layout."""
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        for col in (3, 4, 5, 6):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 64)
        self.table.setColumnWidth(4, 56)
        self.table.setColumnWidth(5, 76)
        self.table.setColumnWidth(6, 68)

    def _set_cell(self, row: int, col: int, text: str) -> None:
        """Insert a plain left-aligned QTableWidgetItem."""
        self.table.setItem(row, col, QTableWidgetItem(text))

    @staticmethod
    def _format_duration(seconds) -> str:
        """Format a duration in seconds as M:SS.

        Args:
            seconds: integer or float duration, or None.

        Returns:
            Formatted string e.g. "4:32". Returns "" for None or 0.
        """
        if not seconds:
            return ""
        m, s = divmod(int(seconds), 60)
        return f"{m}:{s:02d}"
