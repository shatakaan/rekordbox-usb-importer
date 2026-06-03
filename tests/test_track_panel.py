"""
Unit tests for TrackPanel — post_import mode (UX-03).

Tests TDD RED phase for populate_post_import_summary().

Uses QT_QPA_PLATFORM=offscreen (set via conftest or environment) to run
Qt widgets without a real display.
"""

import os
import sys
from types import SimpleNamespace

import pytest

# Ensure offscreen platform is set before any Qt imports
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.track_panel import TrackPanel


# ---------------------------------------------------------------------------
# QApplication singleton (required for any QWidget test)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    """Create (or reuse) a QApplication for the test session."""
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


# ---------------------------------------------------------------------------
# Minimal stubs for ImportResult and ImportPlan
# ---------------------------------------------------------------------------

def _make_song(track_id: int, title: str = "Track"):
    """Return a minimal song stub with .content.track_id."""
    content = SimpleNamespace(track_id=track_id, title=title)
    return SimpleNamespace(content=content)


def _make_playlist(name: str, song_track_ids: list):
    songs = [_make_song(tid) for tid in song_track_ids]
    return SimpleNamespace(name=name, songs=songs)


def _make_plan(playlists, track_statuses=None, force_import_ids=None):
    from core.import_controller import TrackImportStatus
    if track_statuses is None:
        track_statuses = {}
    if force_import_ids is None:
        force_import_ids = set()
    return SimpleNamespace(
        selected_playlists=playlists,
        track_statuses=track_statuses,
        force_import_ids=force_import_ids,
    )


def _make_result(imported=0, skipped=0, failed=0):
    return SimpleNamespace(
        imported_count=imported,
        skipped_count=skipped,
        failed_count=failed,
        backup_path=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPostImportSummary:

    def test_post_import_summary_rows(self, qapp):
        """populate_post_import_summary with 2 playlists produces exactly 2 rows."""
        from core.import_controller import TrackImportStatus
        panel = TrackPanel()
        pl1 = _make_playlist("Playlist A", [1, 2])
        pl2 = _make_playlist("Playlist B", [3])
        statuses = {
            1: TrackImportStatus.NEW,
            2: TrackImportStatus.NEW,
            3: TrackImportStatus.NEW,
        }
        plan = _make_plan([pl1, pl2], track_statuses=statuses)
        result = _make_result(imported=3)
        panel.populate_post_import_summary(result, plan)
        assert panel.table.rowCount() == 2

    def test_post_import_summary_columns(self, qapp):
        """Table has 4 columns: PLAYLIST, IMPORTED, SKIPPED, FAILED."""
        from core.import_controller import TrackImportStatus
        panel = TrackPanel()
        plan = _make_plan([_make_playlist("X", [1])], {1: TrackImportStatus.NEW})
        result = _make_result(imported=1)
        panel.populate_post_import_summary(result, plan)
        assert panel.table.columnCount() == 4
        headers = [
            panel.table.horizontalHeaderItem(i).text()
            for i in range(panel.table.columnCount())
        ]
        assert headers == ["PLAYLIST", "IMPORTED", "SKIPPED", "FAILED"]

    def test_post_import_summary_done_button(self, qapp):
        """After populate_post_import_summary: _back_btn hidden, _confirm_btn says 'Done'."""
        from core.import_controller import TrackImportStatus
        panel = TrackPanel()
        plan = _make_plan([_make_playlist("X", [1])], {1: TrackImportStatus.NEW})
        result = _make_result(imported=1)
        panel.populate_post_import_summary(result, plan)
        assert not panel._back_btn.isVisible(), "_back_btn should be hidden in post_import mode"
        assert panel._confirm_btn.text() == "Done"

    def test_post_import_summary_aggregate_label(self, qapp):
        """_backup_label contains aggregate counts 'N imported | N skipped | N failed'."""
        from core.import_controller import TrackImportStatus
        panel = TrackPanel()
        plan = _make_plan([_make_playlist("X", [1, 2])], {
            1: TrackImportStatus.NEW,
            2: TrackImportStatus.SKIP,
        })
        result = _make_result(imported=1, skipped=1, failed=0)
        panel.populate_post_import_summary(result, plan)
        label_text = panel._backup_label.text()
        assert "1 imported" in label_text
        assert "1 skipped" in label_text
        assert "0 failed" in label_text

    def test_restore_browse_from_post_import(self, qapp):
        """restore_browse_mode() after post_import: mode is 'browse', _summary_header hidden."""
        from core.import_controller import TrackImportStatus
        panel = TrackPanel()
        plan = _make_plan([_make_playlist("X", [1])], {1: TrackImportStatus.NEW})
        result = _make_result(imported=1)
        panel.populate_post_import_summary(result, plan)
        panel.restore_browse_mode()
        assert panel._mode == "browse"
        assert not panel._summary_header.isVisible()

    def test_restore_browse_mode_restores_back_btn(self, qapp):
        """restore_browse_mode() makes _back_btn visible again."""
        from core.import_controller import TrackImportStatus
        panel = TrackPanel()
        plan = _make_plan([_make_playlist("X", [1])], {1: TrackImportStatus.NEW})
        result = _make_result(imported=1)
        panel.populate_post_import_summary(result, plan)
        panel.restore_browse_mode()
        assert panel._back_btn.isVisible(), "_back_btn should be visible after restore_browse_mode"
        assert panel._confirm_btn.text() == "Confirm Import"

    def test_post_import_per_playlist_counts(self, qapp):
        """Per-playlist row correctly shows imported/skipped/failed counts."""
        from core.import_controller import TrackImportStatus
        panel = TrackPanel()
        # Playlist A: 2 NEW tracks, 1 SKIP -> imported=2, skipped=1
        # Playlist B: 1 DUPLICATE in force_import_ids -> imported=1
        pl_a = _make_playlist("Playlist A", [1, 2, 3])
        pl_b = _make_playlist("Playlist B", [4])
        statuses = {
            1: TrackImportStatus.NEW,
            2: TrackImportStatus.NEW,
            3: TrackImportStatus.SKIP,
            4: TrackImportStatus.DUPLICATE,
        }
        force_import_ids = {4}
        plan = _make_plan([pl_a, pl_b], statuses, force_import_ids)
        result = _make_result(imported=3, skipped=1, failed=0)
        panel.populate_post_import_summary(result, plan)

        # Row 0 = Playlist A
        assert panel.table.item(0, 0).text() == "Playlist A"
        assert panel.table.item(0, 1).text() == "2"  # imported
        assert panel.table.item(0, 2).text() == "1"  # skipped
        assert panel.table.item(0, 3).text() == "0"  # failed

        # Row 1 = Playlist B (DUPLICATE in force_import_ids -> counts as imported)
        assert panel.table.item(1, 0).text() == "Playlist B"
        assert panel.table.item(1, 1).text() == "1"  # imported
        assert panel.table.item(1, 2).text() == "0"  # skipped
        assert panel.table.item(1, 3).text() == "0"  # failed
