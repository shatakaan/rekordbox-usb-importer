"""
Smoke tests for core.db_loader — USB database open functionality.

Hardware-dependent tests are skipped without a real Rekordbox USB connected.
The function-existence test runs in any environment.
"""

import pytest
from pathlib import Path


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
