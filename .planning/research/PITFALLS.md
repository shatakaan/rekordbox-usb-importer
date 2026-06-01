# Domain Pitfalls: Rekordbox USB Playlist Importer

**Domain:** Rekordbox database manipulation / macOS GUI tool
**Researched:** 2026-06-01
**Confidence note:** External tools (WebSearch, WebFetch, Context7 CLI) were unavailable in this session.
All findings are derived from training knowledge covering pyrekordbox reverse-engineering
documentation, Rekordbox 6/7 SQLite schema analysis, macOS distribution requirements, and
SQLite transaction semantics. Confidence levels are noted per pitfall.

---

## Critical Pitfalls

### Pitfall C1: Writing to `master.db` While Rekordbox Holds an Open Handle
**Severity:** Critical
**Confidence:** HIGH — this is documented SQLite behavior, not speculation.

**What goes wrong:**
If Rekordbox is running and has `master.db` open in WAL mode (Write-Ahead Logging), a second
process writing to the same database can corrupt the WAL index or produce silently inconsistent
data. The WAL file (`master.db-wal`) and shared-memory file (`master.db-shm`) must be consistent
with what the owning connection expects. A partial commit from an external writer can leave
Rekordbox in a state where it cannot recover the WAL on next open, causing it to mark the
database as corrupt and prompt the user to reset their library.

**Why it happens:**
Developers test with Rekordbox closed during development, then a user runs the tool without
closing Rekordbox first, or Rekordbox relaunches automatically (e.g., via macOS "Reopen windows"
setting after the app quits).

**Warning signs:**
- Rekordbox opens and shows an empty library after a previously successful import
- Rekordbox prompts "Library could not be loaded, would you like to reset?"
- `master.db-wal` file is larger than expected and not checkpointed

**Prevention:**
1. Check for running Rekordbox processes via `NSWorkspace.runningApplications` (Swift) or
   `psutil.process_iter()` (Python) before ANY database open call.
2. Block the import entirely if Rekordbox is detected — show a clear dialog.
3. After confirming Rekordbox is closed, do NOT open the database in WAL mode yourself
   unless you checkpoint properly on close. Use `PRAGMA journal_mode=DELETE` or open
   read-only for the backup phase.
4. Check for stale `-wal` and `-shm` files. If present when Rekordbox is closed, the last
   session may have crashed — attempt a recovery checkpoint, or refuse to proceed and tell
   the user to open/close Rekordbox cleanly first.

**Phase:** Core import logic (Phase 1 / wherever database writes are first introduced).

---

### Pitfall C2: Non-Atomic Import Leaves Database in Partially Imported State
**Severity:** Critical
**Confidence:** HIGH — standard SQLite transaction semantics.

**What goes wrong:**
If the tool crashes, the user force-quits, or macOS kills the process mid-import (e.g., low
memory), a partially committed import leaves orphaned track entries in `djmdContent` without
corresponding playlist membership entries in `djmdSongPlaylist`, or vice versa. Rekordbox may
show phantom tracks, broken playlists, or refuse to load.

**Why it happens:**
Developers use individual `INSERT` calls or multiple transactions across different tables
(tracks inserted, then playlist rows inserted as a separate step). Any interruption between
those two commits leaves an inconsistent state.

**Warning signs:**
- Playlists appear in Rekordbox but contain zero tracks
- Tracks appear in "All Tracks" view but do not belong to any playlist
- Rekordbox shows import as complete but track count is wrong

**Prevention:**
1. Wrap the ENTIRE import (all track inserts + all playlist membership inserts) in a single
   SQLite transaction. Use `BEGIN IMMEDIATE` to acquire a write lock upfront, preventing
   interleaving reads during the operation.
2. Use `SAVEPOINT` for nested rollback points within a large import.
3. Only call `COMMIT` after ALL tables have been written successfully.
4. Make the backup the first step before `BEGIN IMMEDIATE`. If the import is interrupted,
   the backup provides a clean restore path — document this in the UI.
5. Register a signal handler (`SIGTERM`, `SIGINT`) that rolls back the active transaction
   before exiting.

**Phase:** Core import logic — must be designed in from day one, cannot be bolted on.

---

### Pitfall C3: Path Encoding Mismatch Between USB Database and Local Library
**Severity:** Critical
**Confidence:** HIGH — pyrekordbox documentation and Rekordbox reverse-engineering notes
confirm this. The exact encoding format is well-established.

**What goes wrong:**
Rekordbox stores file paths in `djmdContent.FolderPath` and related columns as percent-encoded
URI paths with a `file://localhost/` prefix, NOT as POSIX paths. Example:

    file://localhost/Volumes/DJUSB/Contents/Tracks/My%20Track%20%28Original%29.mp3

The percent-encoding uses uppercase hex (`%20` not `%2b`), and Rekordbox applies Unicode NFC
normalization to filenames. macOS HFS+/APFS stores filenames in NFD (decomposed). This creates
a mismatch: a file named `Café.mp3` (NFC, Rekordbox side) vs `Café.mp3` (NFD,
filesystem side). Rekordbox will show the track as missing even though the file exists, because
the path comparison is byte-exact.

**Why it happens:**
Developers construct paths with Python's `pathlib` or `os.path.join` and insert them directly.
The POSIX path is not the same as what Rekordbox expects.

**Warning signs:**
- Tracks appear in the imported playlist but show as "missing" immediately, even with the USB
  connected
- Only tracks with ASCII-only filenames work correctly; accented characters or special symbols fail
- Tracks with parentheses, ampersands, or spaces in filenames fail

**Prevention:**
1. Construct paths as `file://localhost` + percent-encoded POSIX path. Use Python's
   `urllib.parse.quote(path, safe='/')` but do NOT quote the leading `/Volumes/...` slash.
2. Apply NFC normalization to filenames before encoding: `unicodedata.normalize('NFC', name)`.
3. Test with a track containing: spaces, parentheses, ampersands, umlauts (ä ö ü), Japanese
   characters, and emoji in the filename. All must round-trip correctly.
4. When reading USB database paths to detect duplicates, normalize both sides to NFC before
   comparison — do not compare raw bytes.
5. Verify by reading back the inserted row and constructing the OS path to confirm the file
   exists at that path.

**Phase:** Path mapping / track insertion — first time a track row is written.

---

### Pitfall C4: Rekordbox Database Schema Changes Between Minor Versions
**Severity:** Critical
**Confidence:** MEDIUM — schema changes between Rekordbox 6 and 7 are documented in
pyrekordbox issue tracker and community reverse-engineering. Exact column-level changes
between 6.x minor versions are less certain without live access to issue tracker.

**What goes wrong:**
Rekordbox 6 and Rekordbox 7 share a broadly similar SQLite schema but differ in:
- Column presence in `djmdContent` (Rekordbox 7 added columns for stems, lighting metadata)
- `DevLibraryRevision` / `SchemaVersion` pragma values in `masterSettings` or a dedicated
  metadata table
- The `AnlzPath` column format for analysis files changed between certain 6.x releases

If the tool hardcodes column names or INSERT statement column lists, it will fail with a
"table has no column X" SQLite error on versions that don't have that column, or silently
produce rows with missing data on versions that have additional required columns.

**Why it happens:**
The developer tests against one specific Rekordbox installation. The schema difference is only
discovered when a user reports a failure.

**Warning signs:**
- `OperationalError: table djmdContent has no column named Stems` (or similar)
- Import succeeds on Rekordbox 6.8 but fails on 7.x
- `SchemaVersion` mismatch logged but ignored

**Prevention:**
1. On startup, read the schema version from `masterSettings` or `PRAGMA user_version` in the
   local `master.db`. Compare against a tested compatibility matrix.
2. Use `PRAGMA table_info(djmdContent)` to dynamically discover which columns exist before
   constructing INSERT statements. Only populate columns that exist in the target schema.
3. For any column that is NOT NULL without a default value in the target schema, either supply
   a safe default or refuse to proceed.
4. Maintain a `SUPPORTED_SCHEMA_VERSIONS` list and show a warning (not a silent failure) if
   the detected version is outside that list.
5. Do not INSERT by positional column order — always name columns explicitly:
   `INSERT INTO djmdContent (Id, FolderPath, Title, ...) VALUES (?, ?, ?, ...)`.

**Phase:** Database read/write layer — schema introspection must happen before first write.
Flag this phase as requiring deeper research with the actual installed Rekordbox version.

---

## High Severity Pitfalls

### Pitfall H1: Primary Key and UUID Collision When Inserting Tracks
**Severity:** High
**Confidence:** HIGH — standard SQLite integer PK behavior, confirmed by pyrekordbox usage patterns.

**What goes wrong:**
`djmdContent` uses an integer primary key (`Id`) that Rekordbox assigns sequentially. If the
tool picks an `Id` that already exists (e.g., by starting from 1, or by re-using an ID from the
USB database), the INSERT fails with a UNIQUE constraint violation. Worse, if `INSERT OR REPLACE`
is used naively, it silently overwrites an existing local track with the USB track's metadata,
destroying local cue points, loops, and ratings.

**Why it happens:**
The USB database has its own ID sequence starting from low integers. A naive copy of
`djmdContent` rows from USB to local uses the same IDs, which may collide with existing library
entries.

**Prevention:**
1. Never copy the `Id` value from the USB database to the local database.
2. Let SQLite auto-assign IDs: use `INSERT INTO djmdContent (...) VALUES (...)` without
   specifying `Id`, and retrieve the new ID with `last_insert_rowid()`.
3. For duplicate detection, match on `FolderPath` (normalized) or a content hash, NOT on
   numeric ID.
4. Use `INSERT OR IGNORE` only after confirming the ignore case is truly intentional
   (i.e., track already exists — skip it). Never use `INSERT OR REPLACE` for tracks.

**Phase:** Duplicate detection + track insertion logic.

---

### Pitfall H2: USB Mount Point Is Not Deterministic
**Severity:** High
**Confidence:** HIGH — standard macOS volume behavior.

**What goes wrong:**
macOS mounts USB volumes at `/Volumes/<label>`. If the label is "DJUSB", the first mount is
`/Volumes/DJUSB`. But if a volume with the same label is already mounted (or was recently
unmounted), macOS uses `/Volumes/DJUSB 1`, `/Volumes/DJUSB 2`, etc. The local library entry
that was imported with `/Volumes/DJUSB/...` paths will show as missing because the current
mount is at `/Volumes/DJUSB 1/...`.

This also applies between sessions: the user ejects and re-inserts the same stick; macOS may
assign a different suffix.

**Why it happens:**
The path is captured at import time and stored permanently. The mount point assumed during
import is not guaranteed to match at playback time.

**Warning signs:**
- Tracks show as missing in Rekordbox after unplugging and re-plugging the USB stick
- Track paths in `master.db` contain `/Volumes/DJUSB 1/` after a second plug-in

**Prevention:**
1. Document this as a known limitation in the UI: "Track paths reference the USB stick by its
   volume label. If macOS mounts the stick under a different name (e.g., 'DJUSB 1'), tracks
   will show as missing. Eject all other volumes with the same name before re-importing."
2. During import, store the volume UUID (from `diskutil info`) alongside the imported paths
   in an app-specific metadata table, enabling a future "re-link" feature.
3. Warn the user at import time if the volume is mounted at a path containing a numeric suffix.

**Phase:** USB detection / path mapping. Document limitation in Phase 1, build re-link in a
later phase.

---

### Pitfall H3: Tracks Missing Required Metadata Fields Cause Rekordbox to Silently Malfunction
**Severity:** High
**Confidence:** MEDIUM — based on reverse-engineering documentation. Exact required vs.
optional columns need validation against a live Rekordbox instance.

**What goes wrong:**
`djmdContent` has many columns. Some have NOT NULL constraints with defaults (safe to omit);
others are functionally required even without a DB-level constraint. Known examples:

- `FolderPath`: must be the full `file://localhost/...` URI — without this, the track cannot
  be loaded into a deck.
- `FileSize`: Rekordbox uses this for integrity checks. A zero or NULL value causes the track
  to show a warning icon.
- `TrackNo` / `DiskNo`: If NULL, Rekordbox may order tracks incorrectly in album views.
- `ColorId`: Must be a valid foreign key into `djmdColor` or NULL — not an arbitrary integer.
- `MasterDbId` and `DeviceLibraryId`: These link to the originating device. Wrong values here
  can cause Rekordbox's sync logic to behave unexpectedly in future versions.
- `AnalysisDataPath` (`AnlzPath`): Points to `.DAT`/`.EXT` analysis files. If set to a path
  that doesn't exist, Rekordbox shows the track as un-analyzed. If set to a USB path and the
  USB is disconnected, Rekordbox may repeatedly attempt and fail to load waveforms.

**Prevention:**
1. Copy all available metadata from the USB `djmdContent` row — do not only copy
   `FolderPath` and `Title`.
2. Set `AnalysisDataPath` to NULL or to the USB path explicitly — do NOT set it to a
   local path unless you are also copying the analysis files.
3. Validate that `ColorId`, `ArtistId`, `AlbumId`, `GenreId` foreign keys either point to
   existing rows in the local `djmdColor`/`djmdArtist`/etc. tables, or are set to NULL.
   Dangling foreign keys do not cause SQLite errors (FK enforcement is off by default in
   Rekordbox's SQLite build) but cause missing artist/album metadata in the UI.
4. Test with a track that has a color tag, cue points, and a non-ASCII artist name. Verify
   all are preserved correctly.

**Phase:** Track insertion — requires a field-by-field audit of `djmdContent` columns against
a known-good Rekordbox database.

---

### Pitfall H4: Foreign Key Chains Across `djmdArtist`, `djmdAlbum`, `djmdGenre` Tables
**Severity:** High
**Confidence:** MEDIUM — common pattern in Rekordbox schema, confirmed by pyrekordbox
source but exact table names need verification against current schema.

**What goes wrong:**
`djmdContent.ArtistId` is a foreign key into `djmdArtist`. When importing a track from a USB
database, the `ArtistId` from the USB refers to a row in the USB's `djmdArtist` table, not
in the local `djmdArtist` table. If you INSERT the track row with the USB's `ArtistId` value
unchanged, Rekordbox will either show no artist (if no matching local ID exists) or show the
wrong artist (if a local row happens to have the same numeric ID with a different name).

**Why it happens:**
Developers see matching integer IDs and assume they refer to the same entity. They don't — IDs
are local to each database.

**Prevention:**
1. For each referenced artist/album/genre/label/key on a USB track:
   a. Look up the text value (e.g., artist name) in the USB `djmdArtist` table.
   b. Check if that name already exists in the local `djmdArtist` table.
   c. If yes, use the local ID. If no, INSERT a new row and use the new local ID.
   d. Set `djmdContent.ArtistId` to the resolved local ID.
2. Build a reusable "resolve or create" helper that all FK fields go through.
3. Wrap all of this in the single transaction from Pitfall C2.

**Phase:** Track insertion — the FK resolution logic is the most complex part of the import.

---

### Pitfall H5: pyrekordbox Library Version Lag Behind Rekordbox Updates
**Severity:** High
**Confidence:** MEDIUM — based on general open-source library maintenance patterns and the
fact that Rekordbox releases updates 3-5x per year.

**What goes wrong:**
Pioneer/AlphaTheta releases a Rekordbox update that changes the database schema (new columns,
new tables, changed constraints). pyrekordbox may not be updated immediately. If the tool
depends on pyrekordbox's ORM layer for writes, the generated SQL may be wrong for the new
schema version. If it uses pyrekordbox only for reading the USB database and writes raw SQL
to the local database, the exposure is lower but still present for read parsing.

**Why it happens:**
pyrekordbox is maintained by one primary contributor (as of 2024) with community support.
It is not an official Pioneer product.

**Prevention:**
1. Pin pyrekordbox to a tested version in your bundle. Do not auto-update.
2. Write database inserts using raw parameterized SQL, not pyrekordbox's ORM write path.
   This makes the write path independent of pyrekordbox updates.
3. Use pyrekordbox only for reading the USB database (where the format is fixed at the
   time of export) — not for writing the local database.
4. On startup, compare `PRAGMA user_version` of the local `master.db` against a tested
   compatibility list. Warn if the version has changed (indicating a Rekordbox update).

**Phase:** Dependency management — pin versions from day one.

---

## Medium Severity Pitfalls

### Pitfall M1: macOS App Notarization and Hardened Runtime Conflict with SQLite File Access
**Severity:** Medium
**Confidence:** HIGH — documented Apple notarization requirements as of macOS 13+.

**What goes wrong:**
For a standalone `.app` bundle distributed outside the App Store (direct download), Apple
requires notarization. Notarization requires the Hardened Runtime entitlement. The Hardened
Runtime restricts certain behaviors:
- `com.apple.security.files.user-selected.read-write` entitlement is needed to open files
  the user selects via an Open Panel.
- `~/Library/Pioneer/` is NOT a user-selected file — the app opens it programmatically.
  This requires `com.apple.security.files.all` (a restricted entitlement, rarely granted)
  OR the app must be sandboxed with a specific container exception.
- PyInstaller-bundled apps historically had issues passing notarization because of unsigned
  or improperly signed dylibs inside the bundle.

**Why it happens:**
Developers build and test locally where Hardened Runtime restrictions are not enforced, then
hit failures only during notarization or on end-user machines with SIP enabled.

**Prevention:**
1. If NOT using App Store: Distribute with notarization + Hardened Runtime. Add the
   `com.apple.security.files.user-selected.read-write` entitlement. For `~/Library/Pioneer/`,
   either require the user to grant access via an NSOpenPanel (first-run) and save a
   security-scoped bookmark, OR use the `com.apple.security.temporary-exception.files.absolute-path.read-write`
   entitlement (requires justification to Apple). The bookmark approach is more robust.
2. If using App Store: Full sandbox is required. `~/Library/Pioneer/` is inaccessible
   without a user-initiated open. The App Store path is significantly harder for a tool that
   needs transparent access to the Rekordbox library.
3. Test the notarized build on a fresh macOS account before release — sandbox behavior differs
   between developer machines (with SIP partially disabled) and user machines.
4. For PyInstaller: all bundled `.dylib` and `.so` files must be individually code-signed with
   the same Developer ID certificate before `codesign --deep` on the bundle. Use `codesign -vvv`
   to verify the entire bundle.

**Phase:** Distribution/packaging phase. Design the file-access pattern (security-scoped bookmark)
in the core phase so it doesn't require a rewrite later.

---

### Pitfall M2: PyInstaller Bundle Misses Python Extension Modules or Dylibs
**Severity:** Medium
**Confidence:** HIGH — well-documented PyInstaller limitation with SQLite-heavy packages.

**What goes wrong:**
PyInstaller's analysis step may miss:
- `_sqlite3.so` (Python's built-in SQLite extension) — if the Python installation does not
  have it compiled in, the bundle will fail at runtime with `ModuleNotFoundError: No module
  named '_sqlite3'`.
- `libcrypto` / `libssl` (needed if pyrekordbox uses any encryption for certain Rekordbox
  database fields — Rekordbox 6 uses a modified SQLite with some encrypted fields).
- Native macOS frameworks (e.g., `CoreFoundation`, `Security`) needed for process detection.
- Hidden imports from pyrekordbox's lazy-loading patterns.

**Prevention:**
1. Use a `.spec` file with explicit `hiddenimports` and `binaries` lists rather than relying
   on automatic analysis.
2. Test the built `.app` on a machine that does NOT have Python installed — this is the only
   way to catch missing dependencies.
3. Use a CI build matrix against clean macOS VMs (GitHub Actions `macos-latest`) to catch
   missing deps before release.
4. If pyrekordbox requires a specific SQLite build (with certain compile flags), bundle that
   SQLite binary explicitly rather than relying on the system SQLite.

**Phase:** Packaging phase.

---

### Pitfall M3: Rekordbox 6/7 SQLite Uses a Non-Standard Encryption Layer on Some Columns
**Severity:** Medium
**Confidence:** MEDIUM — reported in pyrekordbox documentation and Rekordbox reverse-engineering
community. The local `master.db` is not encrypted, but some older Rekordbox 6 configurations
and all `device.db` files on USB sticks use an XOR-based obfuscation key.

**What goes wrong:**
The USB stick's database (`/PIONEER/rekordbox/export.pdb` or `rekordbox.db`) may require a
specific SQLite key or XOR decryption before it can be read. Tools that simply open the file
with standard SQLite will see garbage data or a "file is not a database" error. pyrekordbox
handles this transparently for supported versions, but the decryption key has changed between
Rekordbox versions, and an incorrect key produces silent garbage — not an error.

**Prevention:**
1. Use pyrekordbox's `RekordboxDatabase` open method rather than `sqlite3.connect()` directly
   for USB databases — it handles key negotiation.
2. Verify the opened database contains expected tables (`djmdContent`, `djmdPlaylist`) before
   proceeding. If the table list is empty or unexpected, the decryption key is wrong.
3. Log the detected database version and the key used — makes debugging version mismatch issues
   much easier.

**Phase:** USB database reading layer — must be validated against real USB sticks exported from
multiple Rekordbox versions (6.6, 6.8, 7.x).

---

### Pitfall M4: Duplicate Detection by Path Is Fragile When USB Volume Label Changes
**Severity:** Medium
**Confidence:** HIGH — logical consequence of path-based storage.

**What goes wrong:**
The tool detects duplicates by comparing the track's path (from the USB database) against
`FolderPath` values in the local `master.db`. If the same USB stick was previously imported
with volume label `DJUSB` and is now mounted as `DJUSB 1` (see Pitfall H2), the path
comparison fails to detect the duplicate. The same track gets imported twice with different
paths, both showing as missing.

**Prevention:**
1. Normalize paths before comparison: strip the volume component and compare only the
   relative path within the USB structure (`Contents/Tracks/Artist/Song.mp3`).
2. As a secondary check, compare file metadata: `FileSize` + `Title` + `Artist` to
   identify likely duplicates even when paths differ.
3. Consider storing a hash of the relative path + file size in an app-specific sidecar table
   to enable robust re-import detection.

**Phase:** Duplicate detection logic.

---

### Pitfall M5: `djmdPlaylist` Parent/Child Tree Integrity
**Severity:** Medium
**Confidence:** HIGH — tree structures in SQL are a known source of subtle corruption.

**What goes wrong:**
Rekordbox organizes playlists in a tree (`djmdPlaylist` has a `ParentId` column). When
importing a playlist from a USB database, the tool must also import its parent folders to
preserve the hierarchy. If only leaf playlists are imported (and parent folders are not
created in the local database), Rekordbox may display the playlists at the root level, or
not display them at all, depending on whether `ParentId` must reference a valid local row.

Additionally, if two playlists from different USB sticks have the same name and parent
structure, importing both creates duplicates that are visually indistinguishable.

**Prevention:**
1. Walk the playlist ancestry chain from leaf to root before inserting. Create parent folder
   entries if they don't exist locally.
2. Use the same "resolve or create by name" pattern for playlist folders as for artist/album
   (Pitfall H4).
3. Present the full playlist path (e.g., "DJSet 2024 / House / Peak Hour") in the UI so
   users understand what hierarchy they are importing.
4. Check for name collisions at each level of the hierarchy and prompt the user if one exists.

**Phase:** Playlist import logic.

---

### Pitfall M6: macOS `~/Library` Access Prompts on First Launch (TCC)
**Severity:** Medium
**Confidence:** HIGH — macOS TCC (Transparency, Consent, and Control) behavior since macOS 10.15.

**What goes wrong:**
macOS requires user consent to access `~/Library` directories belonging to other applications.
For a non-sandboxed app, the first attempt to open `~/Library/Pioneer/rekordbox/master.db`
triggers a TCC consent dialog if the app is not recognized. If the user denies this (or it
fails silently in a CI environment), the database open returns a "permission denied" error
that looks like a missing file.

**Why it happens:**
This only manifests on user machines, not in development (where the developer account owns the
file). The error message from SQLite ("unable to open database file") does not indicate it is
a permissions issue.

**Prevention:**
1. Catch `sqlite3.OperationalError` on database open and check `errno.EACCES` or `errno.EPERM`
   — show a specific "permissions denied" error message with instructions to grant access in
   System Settings > Privacy & Security > Files and Folders.
2. For first-run, consider using an `NSOpenPanel` to let the user navigate to and confirm the
   Rekordbox library path — this grants the app access rights and stores a security-scoped
   bookmark for future launches.
3. Test on a freshly created macOS user account (not the developer's own account) before release.

**Phase:** App startup / first-run flow.

---

### Pitfall M7: `rekordbox.db` vs `master.db` Naming and Location Varies by Installation
**Severity:** Medium
**Confidence:** MEDIUM — based on observed behavior across Rekordbox versions. The exact
file locations and naming have shifted.

**What goes wrong:**
- Rekordbox 6: local library at `~/Library/Pioneer/rekordbox6/master.db` (some installs use
  `rekordbox/master.db` without the version suffix).
- Rekordbox 7: may use `~/Library/Application Support/Pioneer/rekordbox/` on some macOS
  versions instead of `~/Library/Pioneer/`.
- USB export: database at `/PIONEER/rekordbox/export.pdb` (older) or
  `/PIONEER/rekordbox/rekordbox.db` (newer) — both names have been observed.
- Some users have multiple Rekordbox installations (6 and 7 co-installed) — both databases
  exist and the tool must target the right one.

**Prevention:**
1. Do NOT hardcode a single path. Build a path-discovery function that checks multiple known
   locations in priority order and returns the first one that contains a valid Rekordbox schema.
2. If multiple valid databases are found, ask the user which one to use (do not guess).
3. For USB databases, check for both `export.pdb` and `rekordbox.db` at the expected location.
4. Validate the discovered database contains expected tables before proceeding — a file at the
   right path that isn't a Rekordbox database (e.g., a corrupt/empty file) should produce a
   clear error, not a crash.

**Phase:** Database discovery / startup — must be solid before any read or write logic is built.

---

## Phase-Specific Warnings

| Phase / Topic | Likely Pitfall | Mitigation | Severity |
|---|---|---|---|
| USB database reading | Encryption key wrong for this RB version | Validate table list after open | Critical |
| Path construction | URL encoding, NFC normalization | Use `urllib.parse.quote` + NFC before encoding | Critical |
| Track insertion | FK IDs copied from USB instead of resolved locally | Build resolve-or-create helpers for all FK tables | High |
| Track insertion | Schema column mismatch for local RB version | Use `PRAGMA table_info` to introspect schema | Critical |
| Playlist insertion | ParentId references not created locally | Walk ancestry before leaf insert | Medium |
| Duplicate detection | Path-based check fails on volume label change | Match on relative path + file metadata | Medium |
| Transaction design | Partial import on crash | Wrap entire import in single `BEGIN IMMEDIATE` | Critical |
| Process detection | Rekordbox relaunches automatically | Re-check after user confirms closure | Critical |
| Distribution | Hardened Runtime blocks `~/Library/Pioneer/` access | Security-scoped bookmarks on first-run | Medium |
| Distribution | PyInstaller misses SQLite or crypto dylibs | Test on clean machine in CI | Medium |
| Distribution | Notarization fails on unsigned bundled dylibs | Code-sign all dylibs individually before bundle | Medium |
| First-run | TCC dialog denied → opaque "file not found" error | Catch EACCES, show specific instructions | Medium |
| Multi-version | User has RB6 and RB7 installed | Discover and prompt, never guess | Medium |

---

## What MUST Be Present for Tracks to Work in Rekordbox (Minimum Viable Row)

This is the minimum `djmdContent` row content required for a track to be functional in
Rekordbox. Missing any of these will cause visible failures:

| Column | Requirement | Failure if missing |
|---|---|---|
| `FolderPath` | Full `file://localhost/...` URI, NFC, percent-encoded | Track cannot be loaded |
| `Title` | Non-null string | Track shows blank in UI |
| `FileSize` | Accurate byte count | Warning icon, integrity check fails |
| `FileKind` | Integer file type code (MP3=1, AAC=4, WAV=11, FLAC=13) | Track may not load into deck |
| `StockDate` | Import timestamp | May affect sorting/display |
| `ColorId` | NULL or valid FK into `djmdColor` | Crash or wrong color tag if invalid FK |
| `ArtistId` | NULL or valid local FK (not USB FK) | Missing artist metadata |
| `AlbumId` | NULL or valid local FK | Missing album metadata |

**Do NOT set `AnalysisDataPath`** to a local path unless you are copying analysis files.
Set it to NULL or the USB path. Rekordbox will re-analyze the track if it needs to (when the
USB is connected), rather than failing to load cached waveform data from a path that doesn't
exist on the local machine.

---

## Sources and Confidence

| Claim | Confidence | Basis |
|---|---|---|
| WAL mode corruption risk | HIGH | SQLite official documentation, well-established behavior |
| `file://localhost/` path format | HIGH | pyrekordbox source code comments, Rekordbox forum posts |
| NFC/NFD normalization trap | HIGH | macOS HFS+/APFS filesystem behavior, Python unicodedata docs |
| Schema version changes RB6→7 | MEDIUM | pyrekordbox changelog, community reverse-engineering |
| XOR encryption on USB databases | MEDIUM | pyrekordbox README / issues (pre-training data) |
| Exact required columns in `djmdContent` | MEDIUM | pyrekordbox ORM model definitions (may be incomplete) |
| `ArtistId`/`AlbumId` FK behavior | HIGH | Standard SQLite FK semantics |
| TCC / Hardened Runtime behavior | HIGH | Apple developer documentation |
| PyInstaller dylib signing | HIGH | Apple notarization documentation |
| Volume label non-determinism | HIGH | macOS `diskutil` behavior, standard observation |
| Database location variations | MEDIUM | Community reports, no official Pioneer documentation |

**Gaps requiring live validation:**
- The exact `PRAGMA user_version` values for Rekordbox 6.6, 6.8, 7.0, 7.x — needs a
  test matrix against real installations.
- Whether pyrekordbox 0.3.x / 0.4.x handles Rekordbox 7.x USB databases correctly.
- Exact column names and NOT NULL constraints in `djmdContent` for current Rekordbox 7 schema.
- Whether `export.pdb` or `rekordbox.db` naming is version-dependent or configuration-dependent.
