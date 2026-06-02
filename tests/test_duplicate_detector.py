"""
Tests for core/duplicate_detector.py — DuplicateDetector (Plan 02-02).

Requirements covered:
  UX-01: Duplicate detection by FolderPath; fallback to title+artist+duration.
         check_duplicate() returns existing DjmdContent when match found, None otherwise.

All tests import the module under test — if the module does not exist yet,
tests are skipped via pytest.importorskip so pytest collection succeeds.
"""

import pytest
from unittest.mock import MagicMock

DuplicateDetector = pytest.importorskip(
    "core.duplicate_detector",
    reason="core.duplicate_detector not yet implemented (Plan 02-02)",
).DuplicateDetector


# ---------------------------------------------------------------------------
# UX-01: Detect duplicate by FolderPath
# ---------------------------------------------------------------------------

def test_detect_by_path(mock_rb6_db, make_track_row):
    """check_duplicate() returns a DjmdContent-like object when FolderPath matches.

    Requirement UX-01 / D-05: first check is FolderPath (ContentPath in DjmdContent).
    If a match exists in the local DB, return it so the pre-import summary can
    mark the track as DUPLICATE.
    """
    existing_content = MagicMock()
    existing_content.FolderPath = "/Volumes/USB DISK/Contents/test.mp3"

    # db.query(...).filter_by(FolderPath=...).first() returns existing_content
    mock_query = MagicMock()
    mock_query.filter_by.return_value.first.return_value = existing_content
    mock_rb6_db.query.return_value = mock_query

    detector = DuplicateDetector(db=mock_rb6_db)
    track = make_track_row(file_path="/Contents/test.mp3")

    result = detector.check_duplicate(track, usb_mount="/Volumes/USB DISK")

    assert result is not None, (
        "check_duplicate() must return the existing content object when a path match exists"
    )
    assert result is existing_content, (
        "check_duplicate() must return the exact DjmdContent object from the DB query"
    )


# ---------------------------------------------------------------------------
# UX-01: New track returns None
# ---------------------------------------------------------------------------

def test_new_track_returns_none(mock_rb6_db, make_track_row):
    """check_duplicate() returns None when no match found in local DB.

    Requirement UX-01 / D-05: if neither path nor title+artist+duration match,
    the track is NEW and check_duplicate() returns None.
    """
    # All queries return no match
    mock_query = MagicMock()
    mock_query.filter_by.return_value.first.return_value = None
    mock_query.filter.return_value.first.return_value = None
    mock_rb6_db.query.return_value = mock_query

    detector = DuplicateDetector(db=mock_rb6_db)
    track = make_track_row(
        title="Completely New Track",
        artist="Unknown DJ",
        file_path="/Contents/new_track.mp3",
    )

    result = detector.check_duplicate(track, usb_mount="/Volumes/USB DISK")

    assert result is None, (
        "check_duplicate() must return None when no match exists in the local DB"
    )


# ---------------------------------------------------------------------------
# UX-01: Fallback by title + duration when path doesn't match
# ---------------------------------------------------------------------------

def test_fallback_by_title_artist(mock_rb6_db, make_track_row):
    """check_duplicate() falls back to title+duration match when FolderPath doesn't match.

    Requirement UX-01 / D-05: if FolderPath check returns nothing, fall back to
    title + duration (±2 sec) comparison. Returns existing DjmdContent if fallback matches.
    """
    existing_content = MagicMock()
    existing_content.Title = "Fallback Track"
    existing_content.Length = 240

    mock_query = MagicMock()
    # FolderPath query: no match
    mock_query.filter_by.return_value.first.return_value = None
    # Title+duration fallback: match found
    mock_query.filter.return_value.first.return_value = existing_content
    mock_rb6_db.query.return_value = mock_query

    detector = DuplicateDetector(db=mock_rb6_db)
    track = make_track_row(
        title="Fallback Track",
        artist="Some DJ",
        file_path="/Contents/different_path.mp3",
        duration_secs=240,
    )

    result = detector.check_duplicate(track, usb_mount="/Volumes/USB DISK")

    assert result is not None, (
        "check_duplicate() must return the existing content when title+duration matches"
    )
    assert result is existing_content, (
        "check_duplicate() must return the DjmdContent from the fallback query"
    )
