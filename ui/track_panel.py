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
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

COLUMNS = ["TITLE", "ARTIST", "ALBUM", "BPM", "KEY", "DURATION", "RATING"]


class TrackPanel(QWidget):
    """Right panel — QTableWidget with 7 columns for track display.

    Read-only, sortable, multi-row selectable. Populated by calling
    populate(playlist) with a DjmdPlaylist ORM object.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)

        # Column sizing per UI-SPEC
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        for col in (3, 4, 5, 6):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)

        # Set minimum widths for Interactive columns
        self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(2, 120)
        # Set fixed widths for Fixed columns
        self.table.setColumnWidth(3, 64)
        self.table.setColumnWidth(4, 56)
        self.table.setColumnWidth(5, 76)
        self.table.setColumnWidth(6, 68)

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

        layout.addWidget(self.table)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
