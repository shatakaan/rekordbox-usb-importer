# Project Research Summary

**Project:** Rekordbox USB Playlist Importer
**Domain:** macOS GUI tool — Rekordbox 6/7 database manipulation
**Researched:** 2026-06-01
**Confidence:** MEDIUM (core domain HIGH, pyrekordbox v7 compatibility and bundling MEDIUM)

---

## Executive Summary

This is a macOS utility that reads a Rekordbox USB export database, displays its playlist structure, and imports selected playlists — including full track metadata and cue points — into the user's local `master.db` without copying audio files. The audio stays on the USB stick; Rekordbox will show the imported tracks as "offline" when the USB is not connected, which is the expected and documented behavior for this use case. No equivalent open-source tool exists for Rekordbox 6/7 as of mid-2025, making this a genuine gap in the DJ tooling ecosystem.

The recommended approach is: Python 3.11 + pyrekordbox (USB reads) + raw sqlite3 (local writes) + PySide6 (GUI) + PyInstaller (distribution). This stack is opinionated and well-justified. pyrekordbox is the only Python library that handles the proprietary SQLite cipher Pioneer uses, so there is no viable alternative for reading USB databases. PySide6 is chosen over PyQt6 for its LGPL license (distributable without open-sourcing the app). Writing to `master.db` uses raw parameterized SQL — not pyrekordbox's ORM — so that write logic is independent of pyrekordbox version changes.

The highest risks are: (1) the sqlcipher/pysqlcipher3 native dependency, which requires a custom PyInstaller hook to bundle correctly and must be spiked in Phase 1 before any other work; (2) path encoding — Rekordbox stores paths as `file://localhost/`-prefixed, NFC-normalized, percent-encoded URIs, not POSIX paths, and getting this wrong produces tracks that appear imported but are permanently "missing"; and (3) database corruption from concurrent access if Rekordbox is running during import. All three have known mitigations and must be designed in from day one.

---

## Key Findings

### Recommended Stack

The stack is minimal by design — fewer bundled dependencies means a more reliable PyInstaller build. Beyond pyrekordbox and PySide6, the entire supporting layer is Python stdlib (`pathlib`, `shutil`, `subprocess`, `sqlite3`, `logging`).

**Core technologies:**

| Technology | Version | Purpose | Rationale |
|---|---|---|---|
| Python | 3.11 | Runtime | Most tested with pyrekordbox + PySide6; safer than 3.12 until pyrekordbox CI confirms |
| pyrekordbox | 0.3.x (verify on PyPI) | Read USB databases | Only library that handles Pioneer's SQLCipher-based encryption; also parses ANLZ analysis files |
| PySide6 | 6.7.x | macOS GUI | LGPL (distributable); native macOS look; clean PyInstaller integration |
| PyInstaller | 6.x | Standalone .app bundle | De-facto standard; explicit PySide6 hooks; produces Gatekeeper-compatible .app |
| sqlite3 (stdlib) | built-in | Write local master.db | Raw parameterized SQL for all writes; keeps write path independent of pyrekordbox ORM |

**Critical dependency risk:** pyrekordbox requires `pysqlcipher3`, which requires a compiled `libsqlcipher.dylib`. On a developer machine this comes from Homebrew. In the bundled `.app`, the dylib must be explicitly included and its load path fixed with `install_name_tool` or `delocate`. **The very first technical spike must be: install pyrekordbox, open a real USB database, bundle with PyInstaller, run on a machine without Homebrew.** If this spike fails, the entire approach needs re-evaluation before any GUI work begins.

See `.planning/research/STACK.md` for full alternatives considered.

---

### Expected Features

**Must have (table stakes) — a DJ will not use the tool without all of these:**

1. Read USB Rekordbox 6/7 database (`PIONEER/rekordbox/datafile.edb` or `export.pdb`)
2. List playlist folder hierarchy (not just flat list — folders within folders)
3. Multi-select playlists with folder-level select-all
4. Import selected playlists into local `master.db` — tracks, playlist entries, playlist-track mappings
5. Preserve BPM, musical key, color tag, rating, hot cues, memory cues — **cue points are non-negotiable; losing them means hours of re-cueing and the tool will be abandoned immediately**
6. Files stay on USB (no audio copy) — tracks show as "offline" when USB disconnected, which is expected behavior
7. Duplicate track detection with skip/import-anyway prompt
8. Detect Rekordbox running and block import entirely (not just warn — block)
9. Automatic timestamped backup of `master.db` before any write
10. Clear per-track status and human-readable error messages
11. Standalone `.app` bundle — DJs are not developers

**Should have (differentiators that drive word-of-mouth):**

- Loop import (same `djmdCue` table as hot cues — trivial once cues are done)
- Beat grid import (prevents re-analysis jitter on complex tracks)
- Playlist folder hierarchy preservation in local library
- Track preview before import (read-only table view: BPM, key, title, artist)
- Import history log (JSON/SQLite sidecar — "what came from which USB")
- USB identification display (volume label, track count, export date)

**Defer to v2+:**

- MyTag (custom energy/mood tags) — ID-mapping complexity between databases
- Merge-duplicate-to-existing-entry — high complexity, requires DB surgery on playlist FK references
- Drag-and-drop USB selection
- Re-link tracks when USB mounts at different path suffix

**Never build:**

- Audio file copy (defeats the purpose; Rekordbox's own import does this)
- Write to USB database (corruption risk, breaks read-only safety contract)
- Waveform data import (machine-specific binary blob; Rekordbox re-analyzes anyway)
- Play count import (another DJ's stats are meaningless; always set to 0)
- Rekordbox 5 support (binary `.pdb` format, completely different, tiny user base)
- Windows/Linux support in v1

See `.planning/research/FEATURES.md` for full metadata field analysis.

---

### Architecture Approach

The tool has a clean 5-component separation: USBReader (read-only USB DB access), ConflictResolver (pure comparison logic, no writes), BackupManager + LibraryWriter (write side, always inside one transaction), ImportCoordinator (pipeline orchestration, owns transaction lifecycle), and GUI layer (zero business logic). The hybrid read/write strategy — pyrekordbox for USB reads, raw sqlite3 for local writes — is deliberate: pyrekordbox's ORM session model conflicts with the requirement for a single `BEGIN IMMEDIATE` transaction that wraps all writes. Raw sqlite3 gives full control.

**Major components:**

1. **USBReader** — locates and opens USB database read-only; resolves Pioneer path prefix variants (`/:` stripping) to absolute macOS paths; returns typed Python dataclasses
2. **ConflictResolver** — matches USB tracks against local library by (1) normalized path, (2) filename + file size, (3) artist + title + duration; returns ConflictReport; never writes
3. **BackupManager** — copies `master.db` to timestamped path, runs `PRAGMA integrity_check`, surfaces backup path to user
4. **LibraryWriter** — all INSERTs into `djmdContent`, `djmdPlaylist`, `djmdSongPlaylist`; resolves FK chains (artist/album/genre) via resolve-or-create helpers; wrapped in `BEGIN IMMEDIATE`
5. **ImportCoordinator** — checks process, triggers backup, drives pipeline, owns transaction, handles rollback on any failure
6. **ProcessChecker** — `pgrep -x rekordbox` + `pgrep -f rekordboxAgent` via subprocess; no psutil dependency needed
7. **GUI Layer** — PySide6; USB picker, playlist tree with checkboxes, conflict table, progress display, post-import summary with backup path

**Path encoding rule (critical):** `FolderPath` written to `djmdContent` must be a `file://localhost/`-prefixed, percent-encoded (`urllib.parse.quote`), NFC-normalized URI. Not a POSIX path. Getting this wrong produces permanently "missing" tracks with no obvious error.

**Write safety pattern:** `BEGIN IMMEDIATE` transaction; `PRAGMA foreign_keys=ON`; `PRAGMA synchronous=FULL`; commit only after all tables written; rollback on any exception; signal handler catches SIGTERM/SIGINT to rollback before exit.

See `.planning/research/ARCHITECTURE.md` for full component specs, table schemas, and code patterns.

---

### Critical Pitfalls

Ranked by severity. All have known mitigations — none are blockers if addressed in the right phase.

**1. Concurrent write while Rekordbox holds DB open [CRITICAL]**
If Rekordbox is running and has `master.db` open in WAL mode, an external writer can corrupt the WAL index. Rekordbox then prompts the user to reset their entire library. Mitigation: block import (not warn) if `rekordbox` or `rekordboxAgent` processes are detected. Also check for stale `-wal`/`-shm` files after Rekordbox closes — they indicate a crash. Build this check before any DB open call.

**2. Path encoding mismatch — `file://localhost/` + percent-encode + NFC [CRITICAL]**
Rekordbox expects `file://localhost/Volumes/DJUSB/Contents/Tracks/My%20Track.mp3` with uppercase hex encoding and NFC Unicode normalization. macOS HFS+/APFS stores filenames in NFD. A POSIX path inserted directly causes tracks to show as "missing" immediately, even with the USB connected. Only tracks with ASCII-only filenames work by accident. Mitigation: `unicodedata.normalize('NFC', name)` then `urllib.parse.quote(path, safe='/')`, always. Test with spaces, parentheses, umlauts, and emoji in filenames.

**3. Non-atomic import leaves orphaned rows [CRITICAL]**
Crash or force-quit between inserting `djmdContent` rows and `djmdSongPlaylist` rows leaves tracks that appear in "All Tracks" but not in any playlist, or empty playlists. Mitigation: wrap the entire import in one `BEGIN IMMEDIATE` transaction. Register `SIGTERM`/`SIGINT` handlers that rollback before exit. The backup IS the undo mechanism — surface the backup path prominently.

**4. FK IDs copied from USB instead of resolved locally [HIGH]**
`ArtistId`, `AlbumId`, `GenreId`, `ColorId` in the USB `djmdContent` refer to rows in the USB's own lookup tables, not the local ones. Copying the integer value unchanged either maps to the wrong local entity or leaves a dangling FK. Mitigation: build resolve-or-create helpers for every FK table: look up by name in local DB, INSERT if missing, use the local ID. Never copy numeric IDs from USB to local.

**5. Schema version mismatch between Rekordbox versions [CRITICAL]**
Rekordbox 6 and 7 differ in `djmdContent` column presence (RB7 added stems, lighting columns). Hardcoded INSERT column lists fail on mismatched versions. Mitigation: use `PRAGMA table_info(djmdContent)` to discover schema dynamically; always name columns explicitly in INSERT statements (never positional); maintain a `SUPPORTED_SCHEMA_VERSIONS` list using `PRAGMA user_version`; warn if version is outside tested range.

**6. sqlcipher bundling in PyInstaller .app [HIGH]**
`libsqlcipher.dylib` is a Homebrew-installed native library. PyInstaller does not automatically bundle it. Mitigation: spike this in Phase 1 using `--add-binary` directive and `install_name_tool`/`delocate` to fix dylib load paths. Test on a machine without Homebrew before writing any other code.

**7. macOS TCC blocks ~/Library/Pioneer/ access [MEDIUM]**
First-run `sqlite3.OperationalError` on `master.db` open looks like "file not found" but is actually a permissions denial. Mitigation: catch `EACCES`/`EPERM`; show specific instructions for System Settings > Privacy & Security. Consider NSOpenPanel on first run to grant security-scoped access.

**8. USB volume label non-determinism [HIGH]**
macOS mounts to `/Volumes/DJUSB 1` if `/Volumes/DJUSB` is already taken. Stored absolute paths from a prior import then show as "missing." Mitigation: warn user at import time if volume path contains a numeric suffix. Document the limitation. Store relative path + file size alongside import for future re-link capability.

See `.planning/research/PITFALLS.md` for full pitfall catalog with warning signs and phase-specific table.

---

## Implications for Roadmap

The phase structure is driven by two hard constraints: (1) never write to any database until reads are fully validated, and (2) the sqlcipher bundling spike gates everything else. Research suggests 4 phases.

### Phase 1: Read-Only USB Display + Bundling Spike

**Rationale:** Validate the two biggest unknowns before writing a line of GUI code: pyrekordbox opens real USB databases, and PyInstaller bundles the result correctly. If either fails, the entire approach changes. Only after this validation does GUI and feature work begin. This phase has no writes and cannot corrupt any data.

**Delivers:** Working `.app` that detects USB sticks, opens their database, and displays the playlist hierarchy with track metadata in a read-only tree view. Bundling spike results documented.

**Features addressed:**
- USB database detection (scan `/Volumes/` for `PIONEER/rekordbox/` directory)
- Playlist folder hierarchy display
- Track preview per playlist (BPM, key, title, artist)
- USB identification (volume label, track count, export date)

**Pitfalls to avoid:**
- C3: Validate path prefix stripping (`/:` variants) against a real USB in this phase
- M3: Validate pyrekordbox can open the USB DB (encryption key correct for this RB version)
- M7: Build multi-location DB discovery for both USB and local DB in this phase
- M2: Spike PyInstaller bundling with sqlcipher — resolve before Phase 2

**Research flag:** Needs live validation against a real USB stick (multiple Rekordbox export versions if possible). The bundling spike especially cannot be done from training knowledge alone.

---

### Phase 2: Conflict Detection (Still No Writes)

**Rationale:** Conflict detection is pure comparison logic — no writes, low risk. Implementing it before any write logic means the write phase can proceed directly to wiring up a pre-validated conflict result rather than building two complex systems simultaneously.

**Delivers:** Full import UI flow up to the "confirm" button — USB playlists visible, conflicts flagged per track, user can choose skip/import-anyway per conflict. Nothing is written yet.

**Features addressed:**
- Read local `master.db` track list (read-only query)
- Match by normalized path, then filename+size, then metadata
- Conflict resolution table in GUI

**Pitfalls to avoid:**
- M4: Match on relative path (strip volume component) + file metadata, not absolute path, to handle volume label changes
- H1: Understand that USB numeric IDs cannot be used for matching — match on content only

**Research flag:** Standard SQLite query patterns. No deeper research needed for this phase.

---

### Phase 3: Safe Writes — Core Import

**Rationale:** This is the high-risk phase. All safety infrastructure (backup, process check, transaction design, FK resolution) must be built before the first write. Ship nothing until all write-safety mechanisms are wired together and tested end-to-end against a real Rekordbox installation.

**Delivers:** Complete import pipeline. User can select playlists, resolve conflicts, click Import, and find those playlists in Rekordbox with full metadata and cue points.

**Features addressed:**
- Rekordbox-running detection and block
- Timestamped backup with integrity check
- Track insertion into `djmdContent` with all metadata (BPM, key, color, rating, FileSize, FolderPath as `file://localhost/` URI)
- Hot cue + memory cue insertion into `djmdCue`
- FK resolution (artist, album, genre — resolve-or-create helpers)
- Playlist + playlist-tree insertion into `djmdPlaylist` + `djmdSongPlaylist`
- Schema version introspection (`PRAGMA table_info`, `PRAGMA user_version`)
- Single `BEGIN IMMEDIATE` transaction for entire write
- SIGTERM/SIGINT rollback handler

**Pitfalls to avoid:**
- C1: Process check before any DB open call
- C2: Single transaction wrapping all tables
- C3: `file://localhost/` + NFC + percent-encode — test with umlauts and spaces
- C4: `PRAGMA table_info` schema introspection before first INSERT
- H1: Never copy USB numeric IDs; use `last_insert_rowid()`
- H3: Validate required `djmdContent` columns against a live DB before writing production queries
- H4: Resolve-or-create helpers for all FK tables

**Research flag:** Requires a live Rekordbox database to verify exact column names, NOT NULL constraints, and required fields in `djmdContent` for RB6 and RB7 before writing production INSERT statements. This is the phase that most needs `--research-phase` treatment during planning.

---

### Phase 4: Polish, Edge Cases, and Distribution

**Rationale:** All core functionality works. This phase hardens it for real-world use and prepares it for distribution to DJs who are not developers.

**Delivers:** Distributable notarized `.app` with hardened error handling, backup management UI, and clear user-facing messages for every failure mode.

**Features addressed:**
- Loop import (same `djmdCue` table as hot cues — add `Kind = loop` rows)
- Import history log (JSON sidecar file)
- Backup pruning and backup location UI
- All edge case error handling (missing `master.db`, corrupt USB DB, TCC permissions denial, volume label collision, playlist name collision)
- macOS TCC first-run flow (NSOpenPanel security-scoped bookmark for `~/Library/Pioneer/`)
- PyInstaller `.app` notarization + Hardened Runtime entitlements
- Code-sign all bundled dylibs individually before `codesign --deep`
- End-to-end test on clean macOS account with no prior Rekordbox exposure

**Pitfalls to avoid:**
- M1: Hardened Runtime + security-scoped bookmarks for `~/Library/Pioneer/` access
- M2: Test bundle on machine without Python or Homebrew; use CI (GitHub Actions `macos-latest`)
- M6: Catch EACCES on DB open; show specific instructions, not generic "file not found"

**Research flag:** Notarization + Hardened Runtime entitlements for programmatic `~/Library` access are well-documented by Apple. No deeper research phase needed — follow Apple developer docs directly.

---

### Phase Ordering Rationale

- Phase 1 before Phase 3: reads must work before writes; bundling spike must resolve before feature work piles up
- Phase 2 before Phase 3: conflict detection is pure logic with no risk; validating it independently prevents building conflict + write simultaneously
- Phase 4 last: distribution hardening assumes a working, tested core; macOS notarization is a known process with stable documentation

### Research Flags

**Needs research-phase during planning:**
- **Phase 1:** Live spike with real USB stick — cannot be validated from training knowledge; bundling spike especially critical
- **Phase 3:** Live `master.db` schema inspection — exact column names, NOT NULL constraints, required fields for RB6 vs RB7; `PRAGMA user_version` values for tested versions; exact `djmdCue` table structure for cue point insertion

**Standard patterns (skip research-phase):**
- **Phase 2:** Pure SQLite query comparison logic — well-documented patterns
- **Phase 4:** Apple notarization process — Apple developer docs are the authoritative source; no research agent needed

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | Core choices (pyrekordbox, PySide6, PyInstaller) are solid; sqlcipher bundling path is the unknown — needs live spike |
| Features | HIGH | DJ workflow pain points, table stakes features, and metadata importance (especially cue points) are well-grounded in community knowledge |
| Architecture | MEDIUM | Component split and transaction patterns are sound; exact column names and required fields need live DB verification before Phase 3 coding |
| Pitfalls | HIGH | WAL corruption, path encoding, transaction atomicity, FK ID copying, and TCC are all well-documented behaviors — not speculation |

**Overall confidence:** MEDIUM — the approach is correct and the design is sound, but two things require live validation before implementation can proceed confidently: (1) the sqlcipher PyInstaller bundling path, and (2) the exact `djmdContent` schema for the target Rekordbox installation.

### Gaps to Address

| Gap | How to Handle |
|-----|---------------|
| pyrekordbox v7 support completeness | Check current changelog and issues before Phase 1 coding begins; open a real RB7 USB database and verify `djmdContent`, `djmdPlaylist`, `djmdSongPlaylist` are all accessible |
| sqlcipher PyInstaller bundling | Spike in Phase 1, first task; do not proceed to GUI work until resolved |
| `PRAGMA user_version` values for RB6.x and RB7.x | Inspect real databases during Phase 1 spike; build `SUPPORTED_SCHEMA_VERSIONS` list before Phase 3 |
| Exact NOT NULL columns in `djmdContent` | Run `PRAGMA table_info(djmdContent)` on local master.db during Phase 1 spike; document results |
| `export.pdb` vs `rekordbox.db` vs `datafile.edb` naming | Test against real USB exports from multiple Rekordbox versions; build multi-name detection |
| `rekordboxAgent` process name on RB7 | Verify via Activity Monitor during Phase 3 testing |
| macOS `~/Library` path variation (with/without version suffix) | Build multi-location discovery function in Phase 1; do not hardcode |

---

## Sources

### Primary (HIGH confidence)
- pyrekordbox GitHub (dylanljones/pyrekordbox) — USB database parsing, ORM structure, SQLCipher handling
- SQLite official documentation — WAL mode, transaction semantics, `BEGIN IMMEDIATE`
- Apple developer documentation — TCC, Hardened Runtime, notarization entitlements
- macOS `diskutil` / volume mounting behavior — volume label non-determinism

### Secondary (MEDIUM confidence)
- pyrekordbox PyPI / README — version-specific Rekordbox 6/7 support claims
- Deep Symmetry reverse-engineering documentation (rekordcrate) — binary format details, SQLite schema column names
- Pioneer/AlphaTheta community reverse-engineering — table names `djmdContent`, `djmdPlaylist`, `djmdSongPlaylist`, path encoding format
- DJ community forums (r/DJs, r/Rekordbox, DJTechTools) — workflow pain points, cue point importance

### Tertiary (LOW confidence, verify before use)
- Exact `PRAGMA user_version` values per Rekordbox release — needs live verification
- pyrekordbox API surface for current version — may have changed since training cutoff
- USB database filename convention (`export.pdb` vs `rekordbox.db` vs `datafile.edb`) — version-dependent, needs live testing

---

*Research completed: 2026-06-01*
*Ready for roadmap: yes*
