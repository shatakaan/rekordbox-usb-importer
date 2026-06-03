---
phase: 02-full-import-pipeline
plan: "05"
subsystem: e2e-wiring
tags: [ui, main_window, import_worker, e2e, human-verified, wave-4]

key_files:
  modified:
    - ui/main_window.py
    - core/import_controller.py
    - tests/test_import_controller.py

decisions:
  - "_get_checked_playlists: removed is_folder guard — PDB root containers have Attribute=1 but hold songs directly; any checked PlaylistRow is importable"
  - "DUPLICATE tracks: link existing DjmdContent to new playlist instead of skipping — correct DJ workflow (user wants complete playlist, not just new tracks)"
  - "Cue import is best-effort: failure logs warning but does not fail the track"
  - "_import_cues: tag.entries (not tag.data.entries) — pyrekordbox returns body object directly from get_tag(), not a wrapper"
  - "_on_import_back/_on_import_finished: call _repopulate_selected_playlist() so TrackPanel restores current playlist view"
  - "run_import_plan added to ImportController as the multi-playlist orchestrator — preserves existing run_import signature for test compatibility"

bugs_found_during_verification:
  - "tag.data.entries → tag.entries (pyrekordbox API mismatch — tests used mocks that hid this)"
  - "Attribute=1 PDB root container was excluded by folder check — USB export.pdb wraps all playlists in a root folder node"
  - "DUPLICATE tracks were completely skipped — correct behavior is to link to existing DjmdContent"
  - "TrackPanel not repopulated after restore_browse_mode — needs explicit repopulate call"

metrics:
  completed_date: "2026-06-03"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 3
  human_checkpoint: "import-verified"
---

# Phase 2 Plan 05: E2E Wiring + Human Verification

**One-liner:** Import pipeline fully wired end-to-end and verified with a real Rekordbox USB stick — 14-track playlist imported successfully with DUPLICATE linking and cue import.

## What Was Built

### ui/main_window.py
- `_ImportSignals` (QObject) + `_ImportWorker` (QRunnable) for thread-safe background import
- `_on_import_clicked`: preflight → build plan → show TrackPanel summary mode
- `_on_confirm_import`: reads user selections, starts worker via QThreadPool  
- `_on_import_back` / `_on_import_finished`: restore browse mode + repopulate TrackPanel
- `_on_playlist_check_changed` + `_any_playlist_checked`: enable Import button when any playlist is checked
- `_get_checked_playlists`: collect all checked PlaylistRow objects (any Attribute value)
- `_repopulate_selected_playlist`: restore TrackPanel after mode switch

### core/import_controller.py
- `run_import_plan(plan, _tracks_by_id)`: multi-playlist orchestrator with backup, DUPLICATE linking, cue import, rollback
- DUPLICATE → `add_to_playlist(existing_content)` instead of skip
- Cue import isolated in nested try/except (best-effort)
- `_import_cues`: fixed `tag.entries` (was `tag.data.entries`)

## Human Verification Result

Tested with `/Volumes/USB DISK` (DEVICE_LIBRARY_PLUS format, SQLCipher fallback to export.pdb):
- 1 root playlist "PeakTime", 14 tracks (11 duplicates + 3 new)
- Import button enables on checkbox ✓
- Summary panel shows STATUS column (DUPLICATE=orange, NEW=blue) ✓  
- Confirm Import: backup created, all 14 tracks written to local Rekordbox ✓
- Duplicate tracks linked to existing library entries ✓
- New tracks added as offline entries (USB path) ✓
- Back button restores browse mode with tracks visible ✓
- Cue points: best-effort (ANLZ entries resolved via tag.entries) ✓

**Resume signal:** import-verified
