"""
Smoke tests for core.db_loader — USB database open functionality.

Hardware-dependent tests are skipped without a real Rekordbox USB connected.
The function-existence test runs in any environment.
"""

import pytest
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Hardware-independent: verify that the async open function exists
# ---------------------------------------------------------------------------

def test_open_usb_db_async_is_callable():
    """open_usb_db_async must exist and be callable (no USB hardware needed)."""
    core_db_loader = pytest.importorskip(
        "core.db_loader",
        reason="core.db_loader not yet implemented — will be created in Plan 02",
    )
    assert callable(getattr(core_db_loader, "open_usb_db_async", None)), (
        "core.db_loader must expose an 'open_usb_db_async' callable"
    )


# ---------------------------------------------------------------------------
# Plan 01-06: PdbDatabase dataclass tests (no USB hardware needed)
# ---------------------------------------------------------------------------

def test_pdb_database_dataclass():
    """PdbDatabase must be instantiable with playlists=[] and tracks={}."""
    from core.db_loader import PdbDatabase

    db = PdbDatabase()
    assert db.playlists == []
    assert db.tracks == {}

    # Also test non-empty construction
    db2 = PdbDatabase(playlists=["fake"], tracks={1: "track"})
    assert db2.playlists == ["fake"]
    assert db2.tracks == {1: "track"}


def test_rekordbox_pdb_branch_calls_pdb_parser():
    """DbLoadWorker with REKORDBOX_PDB format must call parse_export_pdb."""
    from core.db_loader import DbLoadWorker, PdbDatabase
    from core.format_detector import UsbFormat
    from core.usb_db import PlaylistRow, TrackRow

    # Synthetic data for the mock
    fake_playlist = PlaylistRow(
        id=1, name="Test Playlist", is_folder=False, parent_id=0
    )
    fake_track = TrackRow(
        track_id=1,
        title="Test Track",
        artist_name="Test Artist",
        album_name="",
        bpm=128.0,
        key=None,
        duration_secs=240,
        rating=4,
    )

    finished_results = []
    error_results = []

    with patch("core.db_loader.parse_export_pdb") as mock_parse:
        mock_parse.return_value = ([fake_playlist], {1: fake_track})

        worker = DbLoadWorker(
            mount=Path("/fake/mount"),
            usb_format=UsbFormat.REKORDBOX_PDB,
        )
        worker.signals.finished.connect(lambda db: finished_results.append(db))
        worker.signals.error.connect(lambda msg: error_results.append(msg))

        # Run synchronously (direct call — not via QThreadPool)
        worker.run()

    # parse_export_pdb must have been called with the resolved pdb path
    mock_parse.assert_called_once()
    call_arg = mock_parse.call_args[0][0]
    assert str(call_arg).endswith("export.pdb"), (
        f"Expected parse_export_pdb called with export.pdb path, got: {call_arg}"
    )

    # No errors
    assert error_results == [], f"Unexpected errors: {error_results}"

    # finished signal emitted with a PdbDatabase
    assert len(finished_results) == 1
    assert isinstance(finished_results[0], PdbDatabase)
    assert len(finished_results[0].playlists) == 1
    assert finished_results[0].playlists[0].name == "Test Playlist"


# ---------------------------------------------------------------------------
# Hardware-dependent: open a real Rekordbox USB exportLibrary.db
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="Requires real Rekordbox USB hardware")
def test_db_open_smoke():
    """
    Smoke test: open exportLibrary.db from a connected Rekordbox USB.

    Run this test manually during the Phase 1 spike with a USB connected:
        pytest tests/test_db_loader.py::test_db_open_smoke -v --no-header

    Expected outcome:
    - DeviceLibraryPlus opens without exception
    - At least one playlist is accessible via db.get_playlists()
    """
    from pyrekordbox import DeviceLibraryPlus

    # Locate first Rekordbox USB under /Volumes
    volumes = Path("/Volumes")
    db_path = None
    for volume in volumes.iterdir():
        candidate = volume / "PIONEER" / "rekordbox" / "exportLibrary.db"
        if candidate.exists():
            db_path = candidate
            break

    assert db_path is not None, (
        "No Rekordbox USB found under /Volumes — connect a USB with exportLibrary.db"
    )

    # Attempt to open the DB — must not raise
    db = DeviceLibraryPlus(str(db_path))
    assert db is not None

    # Basic sanity: playlists should be accessible
    playlists = db.get_playlists()
    assert isinstance(playlists, list), (
        f"Expected list from get_playlists(), got {type(playlists)}"
    )
