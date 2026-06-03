---
phase: 03-polish-distribution
plan: "01"
subsystem: ui
tags: [ux, post-import, session-persistence, qsettings, tdd]
requires: [02-05-SUMMARY.md]
provides: [populate_post_import_summary, save_session, load_session, QSettings plist]
affects: [ui/track_panel.py, ui/main_window.py]
tech-stack:
  added: [QSettings NativeFormat plist]
  patterns: [TDD RED/GREEN, standalone DI-injectable helpers, TrackPanel mode extension]
key-files:
  created:
    - tests/test_track_panel.py
    - tests/test_session_state.py
  modified:
    - ui/track_panel.py
    - ui/main_window.py
key-decisions:
  - Post-import summary delivered as TrackPanel post_import mode (not new widget) per D-02
  - save_session / load_session extracted as standalone functions for test DI (not methods)
  - Per-playlist DUPLICATE counts as imported (controller already linked the entry)
  - Disconnect failures caught as RuntimeError but PySide6 emits RuntimeWarning in test context — harmless
requirements-completed: [UX-03, UX-04]
duration: "10 min"
completed: "2026-06-03"
---

# Phase 3 Plan 01: Post-Import Summary + Session Persistence Summary

Post-import per-playlist result table (UX-03) and QSettings plist session persistence (UX-04) implemented via TrackPanel mode extension and standalone save/load helpers with test dependency injection.

**Duration:** 10 min | **Start:** 2026-06-03T12:09:21Z | **End:** 2026-06-03T12:20:04Z
**Tasks:** 2 completed | **New files:** 2 | **Modified files:** 2

---

## Tasks Completed

### Task 1: TrackPanel post_import mode (UX-03)

**Commits:**
- `acd455c` — `test(03-01): add failing tests for TrackPanel post_import mode` (RED)
- `685e467` — `feat(03-01): implement TrackPanel post_import mode (UX-03)` (GREEN)

**Changes to `ui/track_panel.py`:**
- Added `RESULT_COLUMNS = ["PLAYLIST", "IMPORTED", "SKIPPED", "FAILED"]` constant
- Added `populate_post_import_summary(result, plan)` method:
  - Sets `_mode = "post_import"`
  - Hides `_back_btn`, relabels `_confirm_btn` to "Done" (D-02)
  - Shows aggregate counts in `_backup_label` ("N imported | N skipped | N failed")
  - One row per playlist in `plan.selected_playlists`
  - Per-row counts: SKIP = skipped, DUPLICATE (with or without force_import) = imported, NEW = imported
  - Column 0 stretch, cols 1-3 fixed 90px
- Updated `restore_browse_mode()` to restore `_back_btn` visibility and reset button text to "Confirm Import"
- Added `from core.import_controller import ImportPlan, ImportResult, TrackImportStatus`

**Tests (`tests/test_track_panel.py`) — 7 tests:**
1. `test_post_import_summary_rows` — 2 playlists produce 2 rows
2. `test_post_import_summary_columns` — 4 columns with correct headers
3. `test_post_import_summary_done_button` — back hidden, confirm says "Done"
4. `test_post_import_summary_aggregate_label` — aggregate counts in label
5. `test_restore_browse_from_post_import` — mode resets to browse
6. `test_restore_browse_mode_restores_back_btn` — back button un-hidden, text reset
7. `test_post_import_per_playlist_counts` — per-playlist imported/skipped/failed counts

---

### Task 2: QSettings session persistence + MainWindow wiring (UX-04)

**Commits:**
- `6cf2bfe` — `test(03-01): add failing tests for QSettings session persistence (UX-04)` (RED)
- `a2b3b47` — `feat(03-01): implement QSettings session persistence + MainWindow wiring (UX-04)` (GREEN)

**Changes to `ui/main_window.py`:**
- Added `QSettings` to PySide6.QtCore imports
- Added module-level `_settings()` helper returning NativeFormat plist-backed QSettings
- Added standalone `save_session(usb_mount, selected_ids, settings=None)` with optional DI
- Added standalone `load_session(settings=None) -> tuple[str|None, set[int]]` with optional DI
- Added `_last_usb_name: str` and `_restored_playlist_ids: set` instance variables
- Added `_restore_session()` called in `__init__` after `_setup_usb_watcher()`
- Added `_save_session()` / `_restore_session()` instance methods
- Added `_get_checked_playlist_ids()` / `_collect_checked_ids()` tree-walk helpers
- Added `_apply_restored_checkboxes()` / `_check_matching_items()` for pre-checking on DB load
- Wired `_save_session()` in `_on_import_clicked` (before plan build) and `_on_usb_combo_changed`
- No-USB branch: shows `"'<name>' was last used — connect it to continue"` when `_last_usb_name` set
- Auto-select branch: logs `"Session restored: auto-selecting <name>"` on name match
- Rewired `_on_import_finished`: calls `populate_post_import_summary` + wires Done to `_on_summary_done`
- Added `_on_summary_done`: `restore_browse_mode` + `_repopulate_selected_playlist` + disconnect + re-enable import_btn

**Tests (`tests/test_session_state.py`) — 6 tests:**
1. `test_save_load_round_trip` — mount + ids round-trip correctly
2. `test_load_session_empty` — empty state returns (None, set())
3. `test_usb_name_match` — name match is `Path.name` equality
4. `test_save_session_no_mount` — None mount does not write key
5. `test_playlist_id_type_preservation` — ids survive as ints
6. `test_import_finished_shows_summary` — `_on_import_finished` calls `populate_post_import_summary`

---

## Verification

```
QT_QPA_PLATFORM=offscreen python -m pytest -v
45 passed, 5 skipped, 2 warnings in 0.62s
```

The 5 skips are pre-existing (require real USB/DB hardware). The 2 warnings are
PySide6 `RuntimeWarning` from disconnect attempts in test context where handlers
were never connected — caught in production code via `try/except RuntimeError`.

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_restore_browse_mode_restores_back_btn used isVisible() incorrectly**
- **Found during:** Task 1 GREEN
- **Issue:** `panel._back_btn.isVisible()` returns False even after `setVisible(True)` because
  the parent `_summary_header` is hidden in browse mode — effective visibility propagates from parent.
- **Fix:** Changed test to use `isHidden()` which checks the widget's own explicit hide flag,
  not effective visibility. Added corresponding `isHidden()` assertion for post_import mode.
- **Files modified:** `tests/test_track_panel.py`
- **Commit:** `685e467`

**Total deviations:** 1 auto-fixed (Rule 1 - test correctness). **Impact:** none on production code.

---

## Known Stubs

None — all data flows are wired to live ImportResult/ImportPlan data.

---

## Threat Flags

No new network endpoints, auth paths, or trust boundaries introduced.

| Flag | File | Description |
|------|------|-------------|
| plist read at startup | `ui/main_window.py` | QSettings reads from ~/Library/Preferences/ — T-03-01-01 mitigated: path used only for .name comparison, never as writable path. T-03-01-02 mitigated: IDs normalized via {int(x) for x in raw_ids}. |

---

## Self-Check

- [x] `tests/test_track_panel.py` exists on disk
- [x] `tests/test_session_state.py` exists on disk
- [x] `def populate_post_import_summary` in `ui/track_panel.py`
- [x] `def save_session` in `ui/main_window.py`
- [x] `def load_session` in `ui/main_window.py`
- [x] `def _save_session` in `ui/main_window.py`
- [x] `def _restore_session` in `ui/main_window.py`
- [x] `def _apply_restored_checkboxes` in `ui/main_window.py`
- [x] Commits acd455c, 685e467, 6cf2bfe, a2b3b47 exist in git log

## Self-Check: PASSED

Ready for 03-02 (distribution/DMG build).
