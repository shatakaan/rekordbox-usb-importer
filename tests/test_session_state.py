"""
Unit tests for QSettings session persistence (UX-04).

Tests TDD RED phase for save_session / load_session standalone functions
in ui/main_window.py.

Uses IniFormat + temp dir for isolation — never writes to real user plist.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication


# ---------------------------------------------------------------------------
# QApplication singleton
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


# ---------------------------------------------------------------------------
# Isolated QSettings fixture (IniFormat, temp dir)
# ---------------------------------------------------------------------------

@pytest.fixture()
def ini_settings(tmp_path):
    """Return a QSettings instance backed by a temp .ini file."""
    ini_path = str(tmp_path / "test_session.ini")
    s = QSettings(ini_path, QSettings.Format.IniFormat)
    yield s
    s.sync()


# ---------------------------------------------------------------------------
# Import standalone helpers from main_window
# ---------------------------------------------------------------------------

def _import_helpers():
    from ui.main_window import save_session, load_session
    return save_session, load_session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSaveLoadSession:

    def test_save_load_round_trip(self, qapp, ini_settings):
        """save_session then load_session returns identical mount + ids."""
        save_session, load_session = _import_helpers()
        mount = Path("/Volumes/USB DISK")
        ids = {1, 42, 99}
        save_session(mount, ids, settings=ini_settings)
        ini_settings.sync()
        restored_mount, restored_ids = load_session(settings=ini_settings)
        assert restored_mount == str(mount)
        assert restored_ids == ids
        # All values must be ints (not strings)
        assert all(isinstance(x, int) for x in restored_ids)

    def test_load_session_empty(self, qapp, ini_settings):
        """load_session with no prior save returns (None, set())."""
        save_session, load_session = _import_helpers()
        result_mount, result_ids = load_session(settings=ini_settings)
        assert result_mount is None
        assert result_ids == set()

    def test_usb_name_match(self, qapp, ini_settings):
        """Name match is by Path.name equality — different suffix = no match."""
        save_session, load_session = _import_helpers()
        save_session(Path("/Volumes/USB DISK"), {1}, settings=ini_settings)
        ini_settings.sync()
        restored_mount, _ = load_session(settings=ini_settings)
        last_name = Path(restored_mount).name
        # Exact same name matches
        assert last_name == Path("/Volumes/USB DISK").name
        # Different suffix does NOT match
        assert last_name != Path("/Volumes/USB DISK 1").name

    def test_save_session_no_mount(self, qapp, ini_settings):
        """save_session(None, set()) must not write usb/last_mount key."""
        save_session, load_session = _import_helpers()
        save_session(None, set(), settings=ini_settings)
        ini_settings.sync()
        # Key must not exist
        assert ini_settings.value("usb/last_mount", None) is None

    def test_playlist_id_type_preservation(self, qapp, ini_settings):
        """IDs survive QSettings round-trip as ints, not strings."""
        save_session, load_session = _import_helpers()
        save_session(Path("/Volumes/TEST"), {7, 13, 256}, settings=ini_settings)
        ini_settings.sync()
        _, ids = load_session(settings=ini_settings)
        assert ids == {7, 13, 256}
        assert all(isinstance(i, int) for i in ids)


class TestImportFinishedShowsSummary:
    """Integration test: _on_import_finished routes to populate_post_import_summary."""

    def test_import_finished_shows_summary(self, qapp):
        """_on_import_finished calls populate_post_import_summary, not restore_browse_mode."""
        import sys
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch

        # We test that _on_import_finished calls populate_post_import_summary
        # We do this by patching track_panel.populate_post_import_summary on the instance
        # and verifying it is called with the result and the stored import plan.

        # Build a minimal ImportResult stub
        from core.import_controller import ImportResult, ImportPlan, TrackImportStatus
        result = ImportResult(imported_count=2, skipped_count=1, failed_count=0)
        plan = ImportPlan(
            selected_playlists=[],
            track_statuses={},
        )

        # Import MainWindow — it requires QApplication to already exist
        with patch("ui.main_window.USBScanner") as mock_scanner_cls, \
             patch("ui.main_window.QSettings"):
            mock_scanner = MagicMock()
            mock_scanner.current_usbs.return_value = []
            mock_scanner_cls.return_value = mock_scanner

            from ui.main_window import MainWindow
            win = MainWindow()
            win._import_plan = plan

        # Patch populate_post_import_summary on the track_panel instance
        win.track_panel.populate_post_import_summary = MagicMock()
        win.track_panel.restore_browse_mode = MagicMock()

        win._on_import_finished(result)

        # populate_post_import_summary must be called (not restore_browse_mode directly)
        win.track_panel.populate_post_import_summary.assert_called_once_with(result, plan)
        win.track_panel.restore_browse_mode.assert_not_called()
