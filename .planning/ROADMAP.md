# Roadmap: Rekordbox USB Playlist Importer

## Overview

Three phases gate-check the two biggest technical unknowns before any data is written, then ship a complete safe import pipeline, then harden the experience for distribution. Phase 1 validates that pyrekordbox can open a real USB database AND PyInstaller can bundle it — this spike is the single gate for everything else. Phase 2 delivers the full import pipeline with all metadata and cue points in one coherent vertical slice. Phase 3 polishes the experience and produces a distributable .dmg.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: USB Read Display + Bundling Spike** - Validate core unknowns and deliver a working read-only USB browser as a .app (gap closure in progress) (completed 2026-06-02)
- [x] **Phase 2: Full Import Pipeline** - Complete safe import with all metadata, cue points, conflict handling, and write-safety guarantees
- [ ] **Phase 3: Polish + Distribution** - Summary log, state persistence, and distributable notarized .dmg

## Phase Details

### Phase 1: USB Read Display + Bundling Spike

**Goal**: A DJ can connect a Rekordbox USB stick, launch the app, and browse all its playlists and tracks — with no import yet — confirming the technical foundation works as a standalone .app on a machine without Python installed

**Mode:** mvp

**Depends on**: Nothing (first phase)

**Requirements**: USB-01, USB-02, USB-03, USB-04, PLAY-01

**Success Criteria** (what must be TRUE):

1. User launches the .app on a machine without Python or Homebrew and it opens without errors
2. User connects a Rekordbox-exported USB stick and the app detects it and lists its playlists and playlist folders automatically
3. User can manually pick a USB mount point from a dropdown or file picker if auto-detection does not find it or multiple USBs are present
4. User can expand playlist folders and select one or more playlists to prepare for import (selection UI — no actual write yet)
5. User sees a clear, specific error message when the USB database format is unsupported (e.g. Rekordbox 5 binary export), not a generic crash

**Plans:** 6/6 plans complete
Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Environment setup: Python 3.11 venv, dependency install (with package legitimacy checkpoint), pytest scaffold for format_detector and db_loader

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Core data layer: format_detector (USB-04), usb_scanner (D-01/D-02), db_loader (async DeviceLibraryPlus open), resources utility

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — Full UI vertical slice: main_window, playlist_panel (checkboxes D-05), track_panel (7 columns D-04), log_panel (D-08), wired end-to-end; walking skeleton human verification

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-04-PLAN.md — PyInstaller bundling spike: build/app.spec with sqlcipher3 hiddenimports and Info.plist; D-06 spike gate checkpoint

**Wave 5 — Gap Closure** *(blocked on Wave 4; closes SC2 PARTIAL FAIL)*

- [x] 01-05-PLAN.md — PDB parser + data abstraction: core/pdb_parser.py (MPDB-Testformat via struct), core/usb_db.py (PlaylistRow/TrackRow duck-typing), tests mit synthetischer Fixture

**Wave 6 — Gap Closure** *(blocked on Wave 5)*

- [x] 01-06-PLAN.md — Integration: db_loader REKORDBOX_PDB-Branch auf pdb_parser umschalten, main_window._on_db_loaded dispatch, duck-typing-Verifikation, menschliche Checkpoint-Verifikation mit echtem USB

**UI hint**: yes

### Phase 2: Full Import Pipeline

**Goal**: A DJ can select playlists on the USB, resolve any duplicates, click Import, and find those playlists fully populated in their local Rekordbox library — with all metadata and cue points — knowing the operation was safe, atomic, and backed up

**Mode:** mvp

**Depends on**: Phase 1

**Requirements**: PLAY-02, PLAY-03, PLAY-04, META-01, META-02, META-03, SAFE-01, SAFE-02, SAFE-03, SAFE-04, UX-01, UX-02

**Success Criteria** (what must be TRUE):

1. Imported playlists appear in Rekordbox with their original folder hierarchy, hot cue points, memory cue points, BPM, key, color tag, and star rating intact — nothing is missing
2. Imported track entries reference files on the USB stick; no audio file is copied to the local drive; tracks show as "offline" in Rekordbox when the USB is disconnected
3. If Rekordbox or rekordboxAgent is running when the user clicks Import, the import is blocked entirely with a clear explanation — not just a warning
4. A timestamped backup of master.db is created before any write; the backup file path is shown on screen before the import starts and again after it completes
5. If the import is cancelled or the app crashes mid-run, the local Rekordbox database is left completely unchanged (no orphaned rows, no partial playlists)
6. Tracks already present in the local library are flagged before import starts; user can choose to skip or import each duplicate individually

**Plans:** 1/5 plans complete
Plans:

**Wave 1** *(parallel)*

- [x] 02-01-PLAN.md — Datenschicht + Test-Scaffold: TrackRow.analyze_path, pdb_parser str_offs[14], Wave-0-Tests (conftest, test_import_controller Stubs, test_duplicate_detector Stubs) (completed 2026-06-02)
- [ ] 02-02-PLAN.md — Import-Core: ImportController (Prozess-Guard, Backup, Duplikat-Detection, DB-Write-Logik), DuplicateDetector, alle Kern-Unit-Tests

**Wave 3** *(blocked auf Wave 2 / Wave 1 parallel)*

- [ ] 02-03-PLAN.md — ANLZ Cue Import: _import_cues (AnlzFile PCO2/PCOB), DjmdCue-Schreiben, 4 Cue-Tests
- [ ] 02-04-PLAN.md — Summary-Panel UI: TrackPanel Mode-Switch (populate_import_summary, restore_browse_mode, get_import_selections), STATUS-Spalte, Back/Confirm-Buttons

**Wave 4** *(blocked auf Wave 3)*

- [ ] 02-05-PLAN.md — End-to-End-Verdrahtung: main_window Import-Button → ImportController, _ImportWorker QRunnable, Live-Log, menschliche Verifikation

**UI hint**: yes

### Phase 3: Polish + Distribution

**Goal**: A DJ who has never installed developer tooling can download the app, drag it to Applications, and use it reliably — with a clear post-import summary and a session that survives closing and reopening the app

**Mode:** mvp

**Depends on**: Phase 2

**Requirements**: UX-03, UX-04, DIST-01, DIST-02

**Success Criteria** (what must be TRUE):

1. After an import completes, the user sees a human-readable summary listing every playlist and track that was imported, skipped, or failed
2. User can close the app and reopen it without losing USB detection state or needing to re-select the USB stick
3. User can download a .dmg, drag the .app to Applications, double-click it, and it runs on macOS without any "unidentified developer" block or installation of Python, Homebrew, or any dependency

**Plans**: TBD

**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. USB Read Display + Bundling Spike | 6/6 | Complete    | 2026-06-02 |
| 2. Full Import Pipeline | 5/5 | Complete    | 2026-06-03 |
| 3. Polish + Distribution | 0/? | Not started | - |
