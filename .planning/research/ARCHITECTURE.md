# Architecture Patterns

**Domain:** Rekordbox USB Playlist Importer (macOS GUI tool)
**Researched:** 2026-06-01
**Confidence:** MEDIUM — based on pyrekordbox library knowledge (training data to ~mid-2025), Pioneer reverse-engineering documentation (Deep Symmetry project), and SQLite safety patterns. Exact column names should be validated against a live database before writing production queries.

---

## Recommended Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        GUI Layer (tkinter / PyQt)                │
│  - USB picker          - Playlist tree view                      │
│  - Import button       - Conflict resolution dialog              │
│  - Progress display    - Error/warning banners                   │
└────────────────────────┬────────────────────────────────────────┘
                         │ calls
┌────────────────────────▼────────────────────────────────────────┐
│                    ImportCoordinator                              │
│  - Orchestrates the full import pipeline                         │
│  - Owns transaction lifecycle                                     │
│  - Emits progress events back to GUI                             │
└──┬──────────────┬───────────────┬──────────────────────────────┘
   │              │               │
   ▼              ▼               ▼
┌──────────┐ ┌──────────┐ ┌───────────────────┐
│  USB     │ │Conflict  │ │  LibraryWriter     │
│  Reader  │ │Resolver  │ │                    │
│          │ │          │ │  - BackupManager   │
│ Reads    │ │ Compares │ │  - SQLite writer   │
│ USB DB   │ │ USB vs   │ │  - Transaction     │
│ (SQLite, │ │ local DB │ │    management      │
│  read-   │ │ by path/ │ │                    │
│  only)   │ │ checksum │ │                    │
└──────────┘ └──────────┘ └───────────────────┘
   │                               │
   ▼                               ▼
USB SQLite DB               Local master.db
(PIONEER/rekordbox/         (~/Library/Pioneer/
 datafile.edb or            rekordbox/master.db)
 export.pdb — read only)
```

---

## Component Boundaries and Responsibilities

### 1. USBReader

**Responsibility:** Read the USB export database. Never write. Never touch audio files.

- Locate the USB database file at the given mount point
- Open connection in read-only WAL mode (`uri=True, check_same_thread=False`)
- Query tracks, playlists, playlist entries
- Resolve relative USB paths to absolute macOS paths using the mount point
- Return typed Python dataclasses (Track, Playlist, PlaylistEntry)

**Key constraint:** Must never open the USB database with write access — opening in write mode can trigger WAL checkpoint writes that could corrupt an in-use or malformed DB.

**Inputs:** USB mount point path (e.g., `/Volumes/DJUSB`)
**Outputs:** `USBLibrary` object — list of `Playlist` objects each containing `Track` references

---

### 2. ConflictResolver

**Responsibility:** Detect which USB tracks already exist in the local library and surface the conflict for user decision.

- Takes `USBLibrary` + local library track list as input
- Matches tracks by: (1) absolute file path, (2) filename + file size, (3) artist + title + duration (fuzzy)
- Returns a `ConflictReport` listing: clean tracks, duplicates with match type, unresolvable tracks
- Provides a recommended merge strategy per conflict (skip / link to existing / import as new)

**Key constraint:** Read-only — does not modify anything.

**Inputs:** `USBLibrary`, list of tracks from local `master.db`
**Outputs:** `ConflictReport` with per-track resolution recommendations

---

### 3. ImportCoordinator

**Responsibility:** Orchestrate the pipeline. Own the transaction. Surface progress.

- Checks Rekordbox is not running before starting (process list check)
- Triggers `BackupManager.backup()` before any write
- Drives USB read → conflict resolution → user confirmation → library write
- Holds a single database transaction open for the entire write phase
- On any error: rolls back, preserves backup, surfaces error to GUI

**Inputs:** User selections (which playlists, conflict resolutions)
**Outputs:** Progress events (for GUI), ImportResult summary

---

### 4. LibraryWriter

**Responsibility:** Write playlist and track data into the local `master.db`.

- Opens `master.db` with `sqlite3` in read-write mode
- Generates new unique IDs for tracks and playlists (max existing ID + 1, or UUID-based integer)
- Inserts into `djmdContent` (tracks) and `djmdPlaylist` + `djmdSongPlaylist` (playlist structure)
- Updates `djmdProperty` version/sync counters if needed
- All inserts wrapped in a single `BEGIN IMMEDIATE` transaction
- Commits only after all inserts succeed; rolls back on any failure

**Key constraint:** Must hold `BEGIN IMMEDIATE` (not `DEFERRED`) to prevent reader/writer races during the write window, even though Rekordbox is supposed to be closed.

---

### 5. BackupManager

**Responsibility:** Create and manage timestamped backups of `master.db` before any write.

- Creates `~/Library/Pioneer/rekordbox/backups/master_YYYYMMDD_HHMMSS.db`
- Verifies backup integrity with `PRAGMA integrity_check` on the copy
- Optionally prunes backups older than N days (configurable)
- Returns backup path so it can be surfaced to the user in the GUI

---

### 6. ProcessChecker

**Responsibility:** Detect whether Rekordbox is currently running.

- On macOS: scan `/proc` equivalent via `psutil.process_iter()` or a direct `pgrep`-style check
- Process names to check: `rekordbox`, `rekordboxAgent`
- Returns `(is_running: bool, pid: int | None)`
- GUI blocks the import button and shows a warning banner if running

---

### 7. GUI Layer

**Responsibility:** User-facing presentation. Zero business logic.

- USB mount point picker (disk selector or folder dialog defaulting to `/Volumes/`)
- Playlist tree with checkboxes
- Conflict resolution table (show duplicate, offer Skip / Import Anyway per row)
- Progress bar + log view during import
- Post-import summary with backup path and link to open it

---

## Data Flow: Full Import

```
User selects USB mount point
        │
        ▼
ProcessChecker.check()
  ├─ Rekordbox running? → BLOCK: show warning, exit flow
  └─ Not running → continue
        │
        ▼
USBReader.read(mount_point)
  ├─ Locate USB DB (PIONEER/rekordbox/export.pdb or datafile.edb)
  ├─ Read djmdContent (tracks)
  ├─ Read djmdPlaylist + djmdSongPlaylist (playlists)
  ├─ Resolve relative paths → absolute: mount_point + "/" + relative_path
  └─ Returns USBLibrary
        │
        ▼
ConflictResolver.resolve(usb_library, local_library)
  ├─ Match by path, then by filename+size, then by metadata
  └─ Returns ConflictReport
        │
        ▼
GUI presents ConflictReport to user
  └─ User chooses: Skip / Import / Import All
        │
        ▼
ImportCoordinator.execute(selections, conflict_resolutions)
  ├─ BackupManager.backup() → verify → store backup path
  ├─ BEGIN IMMEDIATE transaction on master.db
  ├─ LibraryWriter.insert_tracks(new_tracks)
  ├─ LibraryWriter.insert_playlists(selected_playlists)
  ├─ LibraryWriter.insert_playlist_entries(...)
  ├─ COMMIT
  └─ Returns ImportResult (counts, backup_path, warnings)
        │
        ▼
GUI shows success summary
  └─ "Open backup location" button
```

---

## Key Database Tables

### Local Library: `~/Library/Pioneer/rekordbox/master.db`

Rekordbox 6/7 uses SQLite with the following principal tables (confirmed by pyrekordbox and community reverse-engineering):

#### `djmdContent` — Track records

| Column | Type | Notes |
|--------|------|-------|
| `ID` | INTEGER PK | Auto-increment, unique track identifier |
| `FolderPath` | TEXT | Absolute macOS path, e.g. `/Volumes/DJUSB/Contents/Tracks/...` |
| `FileName` | TEXT | Filename only, e.g. `Track.mp3` |
| `FileSize` | INTEGER | Bytes |
| `Title` | TEXT | Track title |
| `ArtistID` | INTEGER | FK → `djmdArtist` |
| `AlbumID` | INTEGER | FK → `djmdAlbum` |
| `GenreID` | INTEGER | FK → `djmdGenre` |
| `BPM` | REAL | BPM * 100 (stored as integer × 100, e.g. 128.0 BPM = 12800) |
| `Length` | INTEGER | Duration in seconds |
| `BitRate` | INTEGER | Audio bitrate |
| `SampleRate` | INTEGER | Audio sample rate |
| `FileType` | INTEGER | 1=MP3, 4=MP4, 5=AAC, 6=WAV, 7=AIFF, etc. |
| `Rating` | INTEGER | 0–5 stars |
| `ColorID` | INTEGER | Track color label |
| `DateAdded` | TEXT | ISO 8601 datetime |
| `ContentLink` | INTEGER | 0 = local, 1 = linked (e.g., streaming) |
| `rb_local_usn` | INTEGER | Rekordbox internal sync counter |
| `rb_local_deleted` | INTEGER | Soft-delete flag — set to 1 rather than deleting rows |

**Critical:** When inserting a track that references a USB path, `FolderPath` must be the full absolute path including the mount point. Rekordbox will show the track as "offline" (greyed out with a missing-file indicator) when the USB is not mounted — this is the intended behavior for this tool.

#### `djmdPlaylist` — Playlist definitions

| Column | Type | Notes |
|--------|------|-------|
| `ID` | INTEGER PK | Unique playlist identifier |
| `Name` | TEXT | Display name |
| `ParentID` | INTEGER | FK → `djmdPlaylist.ID`, 0 or NULL for root |
| `Seq` | INTEGER | Sort order within parent |
| `Smart` | INTEGER | 0 = regular, 1 = smart playlist |
| `rb_local_usn` | INTEGER | Sync counter |
| `rb_local_deleted` | INTEGER | Soft-delete flag |

**Note on folder playlists:** Rekordbox supports playlist folders. The same `djmdPlaylist` table represents both folders and leaf playlists, distinguished by whether `Smart` and child rows exist. When importing, create a parent folder named after the USB stick (or user-chosen name) to namespace imported playlists.

#### `djmdSongPlaylist` — Playlist membership (many-to-many)

| Column | Type | Notes |
|--------|------|-------|
| `ID` | INTEGER PK | Row identifier |
| `PlaylistID` | INTEGER | FK → `djmdPlaylist.ID` |
| `ContentID` | INTEGER | FK → `djmdContent.ID` |
| `TrackNo` | INTEGER | 1-based position within playlist |
| `rb_local_usn` | INTEGER | Sync counter |
| `rb_local_deleted` | INTEGER | Soft-delete flag |

#### Supporting tables (referenced but not directly written)

- `djmdArtist` — Artist records; may need INSERT if artist doesn't exist
- `djmdAlbum` — Album records; same
- `djmdGenre` — Genre records; same
- `djmdProperty` — Key/value store for library metadata, sync state, library version
- `djmdHistory` — Play history; do not touch
- `djmdHotCueSetting` — Cue points; out of scope for this tool
- `djmdMixerSetting` — Mixer settings; do not touch

---

### USB Export Database

**Location:** `{mount_point}/PIONEER/rekordbox/export.pdb`
- Pioneer proprietary binary format (`.pdb`) in Rekordbox 5 and some Rekordbox 6 exports
- Rekordbox 6+ exports also create a SQLite-format file alongside or instead

**Alternative location (Rekordbox 6/7 USB export):** `{mount_point}/PIONEER/rekordbox/datafile.edb`
- This is a SQLite database despite the `.edb` extension
- Uses the same table structure as `master.db` (same Pioneer schema)
- Can be opened directly with `sqlite3`

**File structure on USB:**
```
/Volumes/DJUSB/
├── PIONEER/
│   ├── rekordbox/
│   │   ├── export.pdb          ← Legacy binary format (RB5, some RB6)
│   │   ├── datafile.edb        ← SQLite, RB6/7 export format
│   │   ├── ANLZ/               ← Analysis data (waveforms, beatgrids)
│   │   │   └── {trackID}/
│   │   │       ├── ANLZXXXX.DAT
│   │   │       └── ANLZXXXX.EXT
│   │   └── device.xml          ← Device metadata
│   └── USBANLZ/               ← Alternative analysis location
└── Contents/
    └── Tracks/
        └── Artist - Title.mp3  ← Audio files with relative paths in DB
```

**Path encoding in USB database:** Tracks in the USB database store paths relative to the USB root, often in one of these formats:
- `/:Contents/Tracks/Artist - Title.mp3` (leading `/:` is a Pioneer path prefix)
- `Contents/Tracks/Artist - Title.mp3` (bare relative path)
- `/Contents/Tracks/Artist - Title.mp3` (root-relative)

The path prefix convention varies by Rekordbox version. The USBReader must strip any leading `/:` or `/` prefix before joining with the mount point.

---

## Path Mapping Strategy

### The Problem

USB tracks are stored in the database with paths relative to the USB root. The macOS mount point varies:
- Default: `/Volumes/DJUSB` (USB volume name)
- Could be: `/Volumes/DJUSB 1` (if name collision), `/Volumes/MY USB`, etc.
- The tool cannot hardcode this — it must resolve at runtime.

### The Solution

**Step 1: User selects (or tool auto-detects) the mount point.**
- Default scan: list all entries under `/Volumes/` that contain a `PIONEER/rekordbox/` directory
- If exactly one found: auto-select and show to user for confirmation
- If multiple found: present a picker
- If none found: show "No Rekordbox USB found" with a manual folder picker as fallback

**Step 2: Path normalization at read time.**
For each track read from the USB database:
```python
def resolve_usb_path(raw_db_path: str, mount_point: str) -> str:
    # Strip Pioneer path prefix variants
    path = raw_db_path
    if path.startswith("/:"):
        path = path[2:]      # Remove leading /:
    path = path.lstrip("/")  # Remove any leading slash
    # Join with mount point
    return os.path.join(mount_point, path)
```

**Step 3: What gets written to master.db.**
The `FolderPath` written to `djmdContent` in the local library is the FULL absolute path:
- Stored value: `/Volumes/DJUSB/Contents/Tracks/Artist - Title.mp3`
- When USB is mounted at that path: Rekordbox finds the file, plays normally
- When USB is not mounted: Rekordbox shows track as "offline" — the intended behavior

**Step 4: Path collision handling.**
If the USB is later mounted at a different path (e.g., `/Volumes/DJUSB 1` due to name collision), the stored absolute paths will be wrong. This is an inherent limitation of storing absolute paths. Mitigation options:
- Document this clearly to the user ("always use the same USB volume name")
- In a future enhancement: store relative paths in a custom field and resolve at launch
- Out of scope for v1

---

## Database Safety: Write Strategy

### Pre-conditions (enforced by ImportCoordinator)

1. **Process check:** `rekordbox` and `rekordboxAgent` must not be running (via `psutil` or `pgrep`)
2. **Backup:** Copy `master.db` to timestamped backup path using `shutil.copy2()`, then run `PRAGMA integrity_check` on the copy
3. **WAL checkpoint:** Run `PRAGMA wal_checkpoint(TRUNCATE)` on master.db before opening for write, to consolidate any pending WAL writes

### Transaction Pattern

```python
import sqlite3

conn = sqlite3.connect(db_path)
conn.execute("PRAGMA journal_mode=WAL")      # ensure WAL mode
conn.execute("PRAGMA foreign_keys=ON")        # enforce FK constraints
conn.execute("PRAGMA synchronous=FULL")       # maximum durability

try:
    conn.execute("BEGIN IMMEDIATE")           # exclusive write lock immediately
    # ... all INSERT statements ...
    conn.commit()
except Exception as e:
    conn.rollback()
    raise ImportError(f"Import failed, database unchanged: {e}") from e
finally:
    conn.close()
```

**Why `BEGIN IMMEDIATE`:** Takes the write lock at transaction start rather than at first write. Prevents the scenario where another process acquires a write lock between the first read and first write (TOCTOU window), even though Rekordbox should be closed.

**Why `PRAGMA synchronous=FULL`:** Slower but guarantees that even an OS crash during the commit won't corrupt the database. Acceptable since this is a one-time import operation, not a high-throughput workflow.

### ID Generation

Rekordbox uses sequential integer IDs. Safe generation:
```python
cursor.execute("SELECT COALESCE(MAX(ID), 0) + 1 FROM djmdContent")
next_id = cursor.fetchone()[0]
```
Run this within the `BEGIN IMMEDIATE` transaction so no other writer can claim the same ID concurrently.

### Soft-Delete Awareness

Rekordbox does not physically delete rows — it sets `rb_local_deleted = 1`. When querying existing tracks for conflict detection, filter: `WHERE rb_local_deleted = 0 OR rb_local_deleted IS NULL`.

When importing, new rows should be inserted with `rb_local_deleted = 0`.

---

## Process Detection on macOS

```python
import subprocess

def is_rekordbox_running() -> bool:
    """Return True if Rekordbox or its agent is running."""
    result = subprocess.run(
        ["pgrep", "-x", "rekordbox"],
        capture_output=True
    )
    if result.returncode == 0:
        return True
    result = subprocess.run(
        ["pgrep", "-f", "rekordboxAgent"],
        capture_output=True
    )
    return result.returncode == 0
```

**Alternative using psutil** (if bundled as a dependency):
```python
import psutil

def is_rekordbox_running() -> bool:
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] in ('rekordbox', 'rekordboxAgent'):
            return True
    return False
```

The `pgrep` approach is preferred because `pgrep` is a macOS system binary — no extra dependency needed. This matters for the standalone `.app` bundle: fewer bundled dependencies = smaller binary and fewer security prompts.

**Rekordbox process names to check:**
- `rekordbox` — main application
- `rekordboxAgent` — background agent that may hold the DB open even after the main app closes (observed in RB6+)

**Recommendation:** Check both. After detecting the agent, instruct the user: "Please fully quit Rekordbox (not just close the window) and wait a few seconds before retrying."

---

## Scalability and Edge Cases

| Concern | Handling |
|---------|----------|
| USB DB format is `.pdb` (binary, not SQLite) | Detect by reading first 4 bytes; `.pdb` starts with `0x00 0x00 0x00 0x08` (Pioneer proprietary). If detected, show "This USB uses Rekordbox 5 format, which is not supported." |
| USB DB is `.edb` but zero-byte or corrupt | Run `PRAGMA integrity_check` on USB DB before reading; abort with user-friendly error if failed |
| master.db is missing | Show "Local Rekordbox database not found at expected path. Please open Rekordbox once to initialize it." |
| Playlist name collision in local library | Append ` (from USB)` or ` (2)` suffix; present to user for confirmation |
| Track already in library at same path | ConflictResolver flags as `EXACT_DUPLICATE`; default resolution is Skip |
| Very large USB (1000+ tracks) | Run DB reads in a background thread; emit progress events; keep GUI responsive |
| User cancels mid-import | Rollback transaction; backup remains; no partial state in master.db |
| macOS permissions (TCC) | macOS 10.15+ requires full disk access or explicit file permission for `~/Library`. Handle `PermissionError` with instructions to grant access in System Settings → Privacy & Security |

---

## Suggested Build Order

Build in this sequence to enable incremental testing at each step:

### Phase 1: Read and Display (no writes)
1. `USBDetector` — scan `/Volumes/` for Pioneer USB sticks
2. `USBReader` — open USB database, read tracks and playlists
3. `PathResolver` — normalize USB relative paths to absolute
4. GUI: mount point picker + playlist tree (read-only display)
   - **Validation gate:** Can you see USB playlists in the UI with correct absolute paths?

### Phase 2: Conflict Detection (still no writes)
5. `LocalLibraryReader` — read tracks from `master.db` (read-only)
6. `ConflictResolver` — match USB tracks against local library
7. GUI: conflict resolution table
   - **Validation gate:** Do duplicates show correctly? Are paths matched reliably?

### Phase 3: Safe Writes
8. `BackupManager` — backup + integrity check
9. `ProcessChecker` — detect Rekordbox running
10. `LibraryWriter` — insert tracks, playlists, entries
11. `ImportCoordinator` — orchestrate the full pipeline with transaction management
12. GUI: progress display + import button (now wired to real import)
    - **Validation gate:** Import small test playlist, open Rekordbox, verify tracks appear as offline, verify playlist is present

### Phase 4: Polish and Distribution
13. Error handling hardening (all edge cases in table above)
14. Backup pruning and backup location UI
15. PyInstaller `.app` bundle packaging + code signing
16. End-to-end test with real USB stick across multiple Rekordbox versions

---

## pyrekordbox Library Assessment

**What it provides:**
- Python ORM over `master.db` and USB databases
- Parses ANLZ analysis files (waveforms, beatgrids, cue points)
- Handles both `.pdb` (binary, RB5) and `.edb`/SQLite (RB6/7) formats
- Active development (GitHub: dylanljones/pyrekordbox)

**Recommendation: Use pyrekordbox for reading, use raw sqlite3 for writing.**

Rationale:
- pyrekordbox's ORM abstracts the schema well for reads (avoids memorizing all column names)
- For writes, the ORM's session management may conflict with our need for a single controlled `BEGIN IMMEDIATE` transaction
- Raw `sqlite3` for writes gives full control over transaction scope and error handling
- This hybrid approach is safer for a tool where write correctness is critical

**Version to target:** `pyrekordbox >= 0.3.0` (added RB6/7 full SQLite support)

**Confidence note:** pyrekordbox is community-maintained and the API may have evolved. Verify current API before coding, especially `Rekordbox6Database` class and its session/connection model.

---

## Sources

- pyrekordbox GitHub (dylanljones/pyrekordbox) — MEDIUM confidence, training data to ~mid-2025
- Deep Symmetry reverse-engineering documentation (crates.io/crates/rekordcrate, github.com/Deep-Symmetry) — HIGH confidence for binary format details, MEDIUM for SQLite schema column names
- Pioneer DJ USB export format — MEDIUM confidence (well-documented community knowledge)
- SQLite transaction safety patterns — HIGH confidence (official SQLite documentation)
- macOS process detection via pgrep — HIGH confidence (macOS system tool, stable API)
- Rekordbox 6/7 SQLite table names — MEDIUM confidence; table names `djmdContent`, `djmdPlaylist`, `djmdSongPlaylist` confirmed by multiple community sources but exact column names should be verified against a live database

**What to verify before coding:**
1. Open a real `master.db` with DB Browser for SQLite and confirm exact column names in `djmdContent`, `djmdPlaylist`, `djmdSongPlaylist`
2. Check current pyrekordbox API (`pip show pyrekordbox`, read its docs)
3. Confirm whether USB export creates `.edb`, `.pdb`, or both on Rekordbox 7
4. Test `rekordboxAgent` process name — may differ between RB6 and RB7
