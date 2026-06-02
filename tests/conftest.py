"""
Shared pytest fixtures for Phase 2 tests.

Fixtures:
  - mock_rb6_db:   MagicMock simulating Rekordbox6Database write API
  - make_track_row: Factory fixture producing TrackRow objects with sensible defaults
  - usb_mount:     tmp_path-based fake USB mount with a dummy audio file
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.usb_db import TrackRow


# ---------------------------------------------------------------------------
# mock_rb6_db
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_rb6_db(tmp_path):
    """MagicMock that simulates a Rekordbox6Database instance.

    Provides all write-API methods expected by ImportController:
      .commit(), .rollback(), .add_content(), .create_playlist(),
      .create_playlist_folder(), .add_to_playlist(), .add(), .generate_unused_id(),
      .query(), ._db_dir

    _db_dir is a real tmp_path so backup-path assertions work without a real DB.
    """
    db = MagicMock()
    db._db_dir = tmp_path / "rb6_db"
    db._db_dir.mkdir(parents=True, exist_ok=True)

    # Create a placeholder master.db so backup logic can stat it
    (db._db_dir / "master.db").write_bytes(b"")

    # generate_unused_id returns an incrementing int by default
    _id_counter = [1000]

    def _gen_id(*args, **kwargs):
        _id_counter[0] += 1
        return _id_counter[0]

    db.generate_unused_id.side_effect = _gen_id
    db.query.return_value = []

    return db


# ---------------------------------------------------------------------------
# make_track_row
# ---------------------------------------------------------------------------

@pytest.fixture()
def make_track_row():
    """Factory fixture: returns a callable that produces TrackRow objects.

    Usage:
        def test_something(make_track_row):
            track = make_track_row(title="My Track", bpm=130.0)
    """

    def _factory(
        title: str = "Test Track",
        artist: str = "Artist",
        file_path: str = "/Contents/test.mp3",
        analyze_path: str | None = None,
        bpm: float = 128.0,
        duration_secs: int = 240,
        rating: int = 0,
        track_id: int = 1,
    ) -> TrackRow:
        return TrackRow(
            track_id=track_id,
            title=title,
            artist_name=artist,
            album_name="",
            bpm=bpm,
            key=None,
            duration_secs=duration_secs,
            rating=rating,
            analyze_path=analyze_path,
        )

    return _factory


# ---------------------------------------------------------------------------
# usb_mount
# ---------------------------------------------------------------------------

@pytest.fixture()
def usb_mount(tmp_path):
    """Fake USB mount point with a dummy audio file.

    Creates:
        <tmp_path>/usb/Contents/test.mp3  (0 bytes)

    Returns the usb root path so tests can build absolute track paths.
    """
    usb_root = tmp_path / "usb"
    contents_dir = usb_root / "Contents"
    contents_dir.mkdir(parents=True, exist_ok=True)
    (contents_dir / "test.mp3").write_bytes(b"")  # 0-byte placeholder
    return usb_root
