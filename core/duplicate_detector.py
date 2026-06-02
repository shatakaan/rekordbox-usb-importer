"""
Duplicate detection for USB tracks against the local Rekordbox 6 database.

Strategy (per D-05):
  1. Exact FolderPath match — db.query(DjmdContent).filter_by(FolderPath=str(abs_path)).first()
  2. Title + Length fallback (±2 sec) — when path doesn't match but title+duration do.

Both strategies must fail for a track to be considered NEW.
"""

from __future__ import annotations

from pathlib import Path

from pyrekordbox.db6 import tables as rb_tables

DjmdContent = rb_tables.DjmdContent


class DuplicateDetector:
    """Checks whether a USB track already exists in the local Rekordbox library.

    Usage:
        detector = DuplicateDetector(db=rb6_db)
        existing = detector.check_duplicate(track, usb_mount="/Volumes/USB DISK")
        if existing is not None:
            # track is a DUPLICATE
    """

    def __init__(self, db) -> None:
        """
        Args:
            db: Rekordbox6Database instance (or mock with .query() method).
        """
        self.db = db

    def check_duplicate(
        self,
        track,
        usb_mount: str | Path = "",
    ) -> "DjmdContent | None":
        """Check if a USB track already exists in the local DB.

        Strategy 1: exact FolderPath match (primary).
        Strategy 2: Title + Length (±2 sec) match (fallback per D-05).

        Args:
            track: TrackRow object with .file_path, .title, .duration_secs.
            usb_mount: USB mount point (str or Path) used to build the absolute path.

        Returns:
            Existing DjmdContent object if found, None if track is new.
        """
        abs_path = Path(usb_mount) / track.file_path.lstrip("/")

        # Strategy 1: FolderPath exact match
        existing = (
            self.db.query(DjmdContent)
            .filter_by(FolderPath=str(abs_path))
            .first()
        )
        if existing is not None:
            return existing

        # Strategy 2: Title + Length fallback (±2 seconds tolerance)
        duration = track.duration_secs or 0
        title = track.title or ""
        if title:
            existing = (
                self.db.query(DjmdContent)
                .filter(
                    DjmdContent.Title == title,
                    DjmdContent.Length.between(duration - 2, duration + 2),
                )
                .first()
            )
            if existing is not None:
                return existing

        return None


def check_duplicate(
    db,
    abs_path: Path,
    title: str = "",
    artist_name: str = "",
    duration_secs: int = 0,
) -> "DjmdContent | None":
    """Standalone function interface for duplicate detection.

    Convenience wrapper around DuplicateDetector for callers that prefer a
    functional API.

    Args:
        db: Rekordbox6Database instance.
        abs_path: Absolute path to the track file on the USB.
        title: Track title (for fallback matching).
        artist_name: Artist name (for fallback matching, not currently used in query).
        duration_secs: Track duration in seconds (for fallback ±2 sec tolerance).

    Returns:
        Existing DjmdContent if found, None otherwise.
    """
    # Strategy 1: exact FolderPath match
    existing = (
        db.query(DjmdContent)
        .filter_by(FolderPath=str(abs_path))
        .first()
    )
    if existing is not None:
        return existing

    # Strategy 2: Title + Length fallback
    if title:
        existing = (
            db.query(DjmdContent)
            .filter(
                DjmdContent.Title == title,
                DjmdContent.Length.between(duration_secs - 2, duration_secs + 2),
            )
            .first()
        )
        if existing is not None:
            return existing

    return None
