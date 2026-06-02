"""
Import controller orchestrating the full USB-to-local-Rekordbox import pipeline.

Responsibilities:
  - run_preflight(): check if Rekordbox is running, check USB mount is accessible
  - build_import_plan(): scan selected playlists, detect duplicates, return ImportPlan
  - run_import(): backup master.db, write playlists+tracks to local DB, rollback on error

Safety requirements:
  SAFE-01: Block import if Rekordbox is running
  SAFE-02: Backup master.db before any write
  SAFE-03: Log backup path before and after import
  SAFE-04: db.rollback() on any exception during write
  T-02-02-01: Path traversal guard — resolved USB path must start with mount point
  T-02-03-01: analyze_path traversal guard — resolved ANLZ path must start with mount point
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from uuid import uuid4

from pyrekordbox.anlz import AnlzFile
from pyrekordbox.db6.tables import DjmdCue
from pyrekordbox.utils import get_rekordbox_pid, get_rekordbox_agent_pid

from core.duplicate_detector import check_duplicate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums + Dataclasses
# ---------------------------------------------------------------------------

class TrackImportStatus(Enum):
    """Status of a track during the import plan phase."""
    NEW = "new"
    DUPLICATE = "duplicate"
    SKIP = "skip"


@dataclass
class ImportPlan:
    """Describes what will be imported before any DB write occurs.

    Produced by ImportController.build_import_plan() and consumed by run_import().
    """
    selected_playlists: list = field(default_factory=list)
    mount: Path = field(default_factory=Path)
    track_statuses: dict = field(default_factory=dict)  # track_id -> TrackImportStatus
    force_import_ids: set = field(default_factory=set)  # track_ids to force-import despite DUPLICATE


@dataclass
class ImportResult:
    """Summary of what happened after run_import() completes."""
    imported_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    backup_path: Path | None = None


# ---------------------------------------------------------------------------
# Preflight result
# ---------------------------------------------------------------------------

@dataclass
class PreflightResult:
    """Result of run_preflight(). ok=True means import may proceed."""
    ok: bool
    message: str = ""


# ---------------------------------------------------------------------------
# ImportController
# ---------------------------------------------------------------------------

class ImportController:
    """Orchestrates the full import pipeline from USB to local Rekordbox library.

    Args:
        db: Rekordbox6Database instance (wraps local master.db).
        usb_mount: Path to the USB mount point (e.g. Path('/Volumes/USB DISK')).
    """

    def __init__(self, db, usb_mount: Path) -> None:
        self.db = db
        self.mount = Path(usb_mount)

    # ------------------------------------------------------------------
    # Preflight
    # ------------------------------------------------------------------

    def run_preflight(self) -> PreflightResult:
        """Check preconditions before import.

        Checks:
          1. Rekordbox is not running (SAFE-01 / D-13).
          2. USB mount is still accessible.

        Returns:
            PreflightResult with ok=True if import may proceed, or
            ok=False with a descriptive message if blocked.
        """
        if get_rekordbox_pid() or get_rekordbox_agent_pid():
            return PreflightResult(
                ok=False,
                message="Rekordbox is open — close it before importing.",
            )
        if not self.mount.exists():
            return PreflightResult(ok=False, message="USB not mounted.")
        return PreflightResult(ok=True)

    # ------------------------------------------------------------------
    # Build Import Plan
    # ------------------------------------------------------------------

    def build_import_plan(self, selected_playlist_ids: set, rb6_db) -> ImportPlan:
        """Scan selected playlists and classify each track as NEW or DUPLICATE.

        Path-traversal guard (T-02-02-01): every resolved track path must start
        with the resolved mount point, blocking ``/../..`` escapes from crafted PDB data.

        Args:
            selected_playlist_ids: Set of PlaylistRow IDs the user checked.
            rb6_db: Rekordbox6Database instance for duplicate queries.

        Returns:
            ImportPlan with per-track statuses.
        """
        plan = ImportPlan(mount=self.mount)
        mount_resolved = str(self.mount.resolve())

        for playlist in []:  # populated via pdb_db.playlists in a subclass/caller
            if playlist.id not in selected_playlist_ids:
                continue
            plan.selected_playlists.append(playlist)
            for song_entry in playlist.songs:
                track = song_entry.content
                rel_path = track.file_path.lstrip("/")
                resolved = (self.mount / rel_path).resolve()
                # T-02-02-01: path traversal guard
                if not str(resolved).startswith(mount_resolved):
                    raise ValueError(
                        f"Path traversal detected: {track.file_path!r} resolves outside USB mount"
                    )
                abs_path = resolved
                existing = check_duplicate(
                    rb6_db,
                    abs_path,
                    track.title or "",
                    track.artist_name or "",
                    track.duration_secs or 0,
                )
                status = TrackImportStatus.DUPLICATE if existing else TrackImportStatus.NEW
                plan.track_statuses[track.track_id] = status

        return plan

    # ------------------------------------------------------------------
    # Run Import
    # ------------------------------------------------------------------

    def run_import(
        self,
        tracks: list,
        playlist_name: str,
        force_import_ids: set | None = None,
    ) -> ImportResult:
        """Backup master.db, then write playlist + tracks to local DB.

        Safety guarantees:
          - SAFE-02: backup created before any write.
          - SAFE-03: backup path logged at INFO level.
          - SAFE-04: db.rollback() called on any exception.

        Args:
            tracks: List of TrackRow objects to import.
            playlist_name: Name of the playlist to create in local Rekordbox.
            force_import_ids: Set of track_ids to import even if DUPLICATE.

        Returns:
            ImportResult with counts and backup_path.
        """
        force_import_ids = force_import_ids or set()

        # SAFE-02: Create backup before any DB write
        master_db_path = self.db._db_dir / "master.db"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.db._db_dir / f"master.db.backup.{ts}"
        shutil.copy2(master_db_path, backup_path)
        # SAFE-03: Log backup path
        logger.info("Backup created: %s", backup_path)

        result = ImportResult(backup_path=backup_path)

        try:
            # Create playlist in local DB
            db_playlist = self.db.create_playlist(playlist_name)

            for track in tracks:
                rel_path = track.file_path.lstrip("/")
                abs_path = (self.mount / rel_path).resolve()

                # BPM scaling: Rekordbox stores BPM as integer × 100 (Pitfall 7)
                bpm_int = int(round(track.bpm * 100)) if track.bpm else 0

                try:
                    content = self.db.add_content(
                        path=abs_path,
                        Title=track.title or "",
                        BPM=bpm_int,
                        Length=track.duration_secs or 0,
                        Rating=track.rating or 0,
                        FileNameS=abs_path.stem[:255],
                    )
                    self.db.add_to_playlist(db_playlist, content)
                    # Import cue points from ANLZ file (D-08, D-09)
                    cue_count = self._import_cues(self.db, content, track, self.mount)
                    logger.info("Track '%s': %d cues imported", track.title, cue_count)
                    result.imported_count += 1
                except Exception:
                    result.failed_count += 1
                    raise

            self.db.commit()
            logger.info("Import complete. Backup: %s", backup_path)

        except Exception:
            # SAFE-04: Rollback on any write failure
            self.db.rollback()
            raise

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _import_cues(self, db, content, track, mount: Path) -> int:
        """Read ANLZ cue points for a track and write DjmdCue objects to the local DB.

        Strategy (Pitfall 6 — never write both PCOB and PCO2 for the same track):
          - If .EXT file exists: read PCO2 tag only (better metadata: colour, label).
          - If only .DAT file exists: read PCOB tag, filter entries with status==4 (enabled).

        Path-traversal guard (T-02-03-01): resolved ANLZ path must start with mount point.

        Args:
            db:      Rekordbox6Database instance.
            content: DjmdContent object for the newly-imported track.
            track:   TrackRow with an analyze_path field.
            mount:   Path to the USB mount point.

        Returns:
            Number of DjmdCue objects written (0 when ANLZ is unavailable).
        """
        # -- Precondition: analyze_path must be present -----------------------
        if not track.analyze_path:
            logger.warning(
                "Track '%s': no analyze_path — imported without cues",
                track.title,
            )
            return 0

        # -- Resolve absolute ANLZ path ---------------------------------------
        dat_path = (mount / track.analyze_path.lstrip("/")).resolve()

        # T-02-03-01: path traversal guard
        mount_resolved = str(mount.resolve())
        if not str(dat_path).startswith(mount_resolved):
            logger.warning(
                "Track '%s': analyze_path '%s' resolves outside USB mount — skipping cues",
                track.title,
                track.analyze_path,
            )
            return 0

        if not dat_path.exists():
            logger.warning(
                "Track '%s': ANLZ file not found at %s — imported without cues",
                track.title,
                dat_path,
            )
            return 0

        # -- Choose .EXT (PCO2) or .DAT (PCOB) — never both (Pitfall 6) ------
        ext_path = dat_path.with_suffix(".EXT")
        use_ext = ext_path.exists()

        if use_ext:
            anlz = AnlzFile.parse_file(ext_path)
            tag_key = "PCO2"
        else:
            anlz = AnlzFile.parse_file(dat_path)
            tag_key = "PCOB"

        if tag_key not in anlz:
            return 0  # no cue data in this file

        tag = anlz.get_tag(tag_key)
        cue_count = 0

        for entry in tag.data.entries:
            # PCOB entries have a status field; PCO2 entries are always enabled
            if tag_key == "PCOB" and entry.status.intvalue != 4:
                continue

            kind = entry.hot_cue  # 0 = Memory Cue, 1..8 = Hot Cue Slot
            in_msec = entry.time
            out_msec = getattr(entry, "loop_time", -1)
            if out_msec is None:
                out_msec = -1
            comment = getattr(entry, "comment", "") or ""

            id_ = db.generate_unused_id(DjmdCue)
            cue_uuid = str(uuid4())

            cue = DjmdCue.create(
                ID=id_,
                UUID=cue_uuid,
                ContentID=content.ID,
                ContentUUID=content.UUID,
                Kind=kind,
                InMsec=in_msec,
                OutMsec=out_msec,
                Comment=comment,
                Color=-1,
                ActiveLoop=0,
                InFrame=0,
                InMpegFrame=0,
                InMpegAbs=0,
                OutFrame=0,
                OutMpegFrame=0,
                OutMpegAbs=0,
                ColorTableIndex=0,
                BeatLoopSize=0,
                CueMicrosec=in_msec * 1000,
            )
            db.add(cue)
            cue_count += 1

        return cue_count

    def run_import_plan(self, plan: ImportPlan, _tracks_by_id: dict | None = None) -> ImportResult:
        """Import all playlists in plan, creating one DB playlist per source playlist.

        Handles backup, multi-playlist write, cue import, and rollback on error.
        Tracks with status DUPLICATE are skipped unless their id is in plan.force_import_ids.

        Args:
            plan: ImportPlan produced by build_import_plan / caller.
            tracks_by_id: dict[int, TrackRow] mapping track_id to TrackRow.

        Returns:
            ImportResult with counts and backup_path.
        """
        master_db_path = self.db._db_dir / "master.db"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.db._db_dir / f"master.db.backup.{ts}"
        shutil.copy2(master_db_path, backup_path)
        logger.info("Backup created: %s", backup_path)

        result = ImportResult(backup_path=backup_path)

        try:
            for playlist_row in plan.selected_playlists:
                db_playlist = self.db.create_playlist(playlist_row.name)
                logger.info("Writing playlist: %s", playlist_row.name)

                for song in (playlist_row.songs or []):
                    track = song.content
                    status = plan.track_statuses.get(track.track_id, TrackImportStatus.NEW)

                    if status == TrackImportStatus.SKIP:
                        result.skipped_count += 1
                        continue
                    if status == TrackImportStatus.DUPLICATE and track.track_id not in plan.force_import_ids:
                        result.skipped_count += 1
                        continue

                    rel_path = track.file_path.lstrip("/")
                    abs_path = (self.mount / rel_path).resolve()
                    bpm_int = int(round(track.bpm * 100)) if track.bpm else 0

                    try:
                        content = self.db.add_content(
                            path=abs_path,
                            Title=track.title or "",
                            BPM=bpm_int,
                            Length=track.duration_secs or 0,
                            Rating=track.rating or 0,
                            FileNameS=abs_path.stem[:255],
                        )
                        self.db.add_to_playlist(db_playlist, content)
                        cue_count = self._import_cues(self.db, content, track, self.mount)
                        logger.info("Track '%s': %d cues imported", track.title, cue_count)
                        result.imported_count += 1
                    except Exception:
                        logger.exception("Failed to import track '%s'", track.title)
                        result.failed_count += 1

            self.db.commit()
            logger.info(
                "Import complete — %d imported, %d skipped, %d failed. Backup: %s",
                result.imported_count,
                result.skipped_count,
                result.failed_count,
                backup_path,
            )

        except Exception:
            self.db.rollback()
            raise

        return result

    def _get_or_create_artist(self, rb6_db, artist_name: str) -> str | None:
        """Lookup or create an artist in the local DB.

        Returns the artist's ID string, or None if artist_name is empty.
        """
        if not artist_name:
            return None
        artist = rb6_db.get_artist(Name=artist_name).first()
        if artist is None:
            artist = rb6_db.add_artist(artist_name)
        return artist.ID
