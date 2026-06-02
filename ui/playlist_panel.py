"""
Left panel — playlist tree with checkboxes.

Provides PlaylistPanel: a QWidget containing a QTreeWidget that displays
Rekordbox playlists and folders in a hierarchical tree. Each row has a
checkbox (Qt.ItemFlag.ItemIsUserCheckable). Selecting a row emits the
playlist_selected signal with the DjmdPlaylist ORM object.

Schema assumptions (verified during live USB spike, RESEARCH.md Pitfall 5):
  - playlist.Name: display name string
  - playlist.Children (or getattr fallback 'children'): child playlist list
  - Folder detection: hasattr(playlist, 'Children') and len(children) > 0,
    OR getattr(playlist, 'Attribute', None) == 1
  If these attribute names differ on the real schema, AttributeErrors are
  caught and logged; the app does not crash (RESEARCH.md Pitfall 5 mitigation).
"""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class PlaylistPanel(QWidget):
    """Left panel — QTreeWidget with checkboxes for playlist/folder selection.

    Signals:
        playlist_selected(object): emitted when a playlist row is selected;
            carries the DjmdPlaylist ORM object for the selected row.
    """

    playlist_selected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header_label = QLabel("PLAYLISTS")
        header_label.setObjectName("sectionHeader")
        header_label.setContentsMargins(12, 8, 12, 4)
        layout.addWidget(header_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.tree)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def populate(self, playlists: list) -> None:
        """Populate the tree from a list of root-level playlist objects.

        Args:
            playlists: list of DjmdPlaylist ORM objects at the root level
                (ParentID is None or 0). Folders are recursed automatically
                via _make_item().
        """
        self.tree.clear()
        for playlist in playlists:
            try:
                item = self._make_item(playlist)
                self.tree.addTopLevelItem(item)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to create tree item for playlist '%s'",
                    getattr(playlist, "Name", "<unknown>"),
                )
        self.tree.expandAll()

    def set_empty_state(self, message: str) -> None:
        """Clear the tree and display a single non-selectable status message.

        Args:
            message: the text to display (e.g. "Connect a Rekordbox USB stick",
                "Loading playlists...", "Unsupported USB format — see log for details").
        """
        self.tree.clear()
        item = QTreeWidgetItem([message])
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.tree.addTopLevelItem(item)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _make_item(self, playlist) -> QTreeWidgetItem:
        """Create a QTreeWidgetItem for a playlist or folder, recursing into children.

        Folder detection heuristic (RESEARCH.md Pitfall 5 — schema field names
        not confirmed until live test):
          1. Check getattr(playlist, 'Attribute', None) == 1 (Rekordbox folder flag).
          2. Fallback: check if children list is non-empty (any parent is a folder).
        If both checks raise AttributeError the item is treated as a leaf playlist.
        """
        name = getattr(playlist, "Name", "<unnamed>")
        item = QTreeWidgetItem([name])
        item.setData(0, Qt.ItemDataRole.UserRole, playlist)

        # Add checkbox to all rows (D-05, PLAY-01)
        item.setFlags(
            item.flags()
            | Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsEnabled
        )
        item.setCheckState(0, Qt.CheckState.Unchecked)

        # Detect if this row is a folder (has children)
        children = (
            getattr(playlist, "Children", None)
            or getattr(playlist, "children", None)
            or []
        )
        is_folder = bool(
            getattr(playlist, "Attribute", None) == 1 or len(children) > 0
        )

        if is_folder:
            # Bold font for folder rows per UI-SPEC Left Panel section
            font = QFont()
            font.setWeight(QFont.Weight.DemiBold)
            item.setFont(0, font)
            # Enable tri-state checkboxes for folders (UI-SPEC: tri-state)
            item.setFlags(
                item.flags() | Qt.ItemFlag.ItemIsAutoTristate
            )

        for child in children:
            try:
                child_item = self._make_item(child)
                item.addChild(child_item)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to create child tree item for '%s'",
                    getattr(child, "Name", "<unknown>"),
                )

        return item

    def _on_selection_changed(self) -> None:
        """Emit playlist_selected with the selected item's ORM object."""
        items = self.tree.selectedItems()
        if items:
            playlist = items[0].data(0, Qt.ItemDataRole.UserRole)
            if playlist is not None:
                self.playlist_selected.emit(playlist)
