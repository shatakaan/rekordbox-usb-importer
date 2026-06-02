---
phase: 02-full-import-pipeline
plan: "01"
subsystem: data-layer
tags: [tdd, analyze_path, pdb_parser, test_scaffold, wave-1]

dependency_graph:
  requires: []
  provides:
    - TrackRow.analyze_path field (core/usb_db.py)
    - pdb_parser str_offs[14] decode (core/pdb_parser.py)
    - Wave-0 test fixtures (tests/conftest.py)
    - Wave-0 stub tests for Plans 02-02/02-03 (test_import_controller, test_duplicate_detector)
  affects:
    - core/usb_db.py (TrackRow extended)
    - core/pdb_parser.py (parse_track_row extended, TrackRow constructor call)
    - tests/ (3 new files)

tech_stack:
  added: []
  patterns:
    - TDD (RED -> GREEN commit sequence)
    - Synthetic PDB binary fixture (pure struct.pack, no external files)
    - pytest.importorskip for stub tests referencing future modules

key_files:
  created:
    - tests/conftest.py
    - tests/test_import_controller.py
    - tests/test_duplicate_detector.py
    - .planning/phases/02-full-import-pipeline/02-01-SUMMARY.md
  modified:
    - core/usb_db.py
    - core/pdb_parser.py
    - tests/test_pdb_parser.py

decisions:
  - "analyze_path placed after rating field with default=None so all existing TrackRow call sites remain valid without changes"
  - "empty string from decode_devicesql_string normalized to None (analyze_raw or None) per T-02-01-01 threat mitigation"
  - "Stub tests use pytest.importorskip at module level — entire file skips cleanly when core.import_controller / core.duplicate_detector do not yet exist; this satisfies 'pytest runs through without CollectionError'"
  - "Synthetic PDB fixture built with pure struct.pack — no file on disk required, fully self-contained in test_pdb_parser.py"
  - "conftest.py mock_rb6_db creates a real tmp_path _db_dir with master.db placeholder so backup-path assertions in Plan 02-02 can stat the file"

metrics:
  duration_seconds: 600
  completed_date: "2026-06-02"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 6
---

# Phase 2 Plan 01: Data Layer Extension + Wave-0 Test Scaffold Summary

**One-liner:** TrackRow.analyze_path field added via TDD (str_offs[14] in PDB parser); Wave-0 test scaffold with shared fixtures and 8 stub tests ready for Plans 02-02 and 02-03.

## What Was Built

### Task 1 (TDD): TrackRow.analyze_path + pdb_parser str_offs[14]

**core/usb_db.py** — `TrackRow` dataclass extended with:
```python
analyze_path: str | None = None  # ANLZ file path from PDB str_offs[14]
```
Field placed after `rating` with a default of `None`, so all existing constructor call sites continue to work unchanged.

**core/pdb_parser.py** — `parse_track_row()` extended to read String Offset 14:
```python
analyze_raw, _  = decode_devicesql_string(page_data, rbase + str_offs[14])
# returned in dict as:
"analyze_path": analyze_raw or None,  # empty string -> None (T-02-01-01)
```
The `TrackRow` constructor call in `parse_export_pdb` step 5 was updated with:
```python
analyze_path=raw_track.get("analyze_path"),
```

**tests/test_pdb_parser.py** — 3 new tests added (Gruppe C):
- `test_trackrow_has_analyze_path_field`: verifies attribute exists, default is None
- `test_analyze_path_none_when_missing`: verifies explicit None is accepted
- `test_analyze_path_extracted`: synthetic PDB fixture with str_offs[14] set; asserts returned TrackRow has analyze_path starting with "/PIONEER"

TDD gate sequence respected: RED commit `13fea32` (tests fail) → GREEN commit `362a839` (implementation passes tests).

### Task 2: Wave-0 Test Scaffold

**tests/conftest.py** — 3 shared fixtures:
- `mock_rb6_db`: MagicMock simulating Rekordbox6Database with real `_db_dir` (tmp_path), `master.db` placeholder, `generate_unused_id` side_effect counter
- `make_track_row`: Factory fixture producing TrackRow objects with sensible defaults; accepts title, artist, file_path, analyze_path, bpm, duration_secs, rating, track_id
- `usb_mount`: tmp_path-based fake USB mount with `Contents/test.mp3` (0 bytes)

**tests/test_import_controller.py** — 6 stub tests (skip via `pytest.importorskip` until Plan 02-02):
- `test_blocks_when_rekordbox_running` (SAFE-01)
- `test_backup_created` (SAFE-02)
- `test_backup_path_logged` (SAFE-03)
- `test_rollback_on_error` (SAFE-04)
- `test_folderpath_is_usb_path` (PLAY-03)
- `test_bpm_scaling` (META-03)

**tests/test_duplicate_detector.py** — 2 stub tests (skip via `pytest.importorskip` until Plan 02-02):
- `test_detect_by_path` (UX-01)
- `test_new_track_returns_none` (UX-01)

## Verification Results

```
python -m pytest tests/ -x -q
...s......ssss..........   [100%]
19 passed, 7 skipped in 0.27s
```

All 4 live-USB tests skipped (no USB connected). All unit tests pass. 2 stub-test files skipped at collection level (modules not yet implemented — expected for Wave-0).

Additional spot checks:
```
python -c "from core.usb_db import TrackRow; t = TrackRow(1,'t','a','',128.0,None,240,0); print(t.analyze_path)"
# Output: None

grep -n "str_offs\[14\]" core/pdb_parser.py
# 217: analyze_raw, _  = decode_devicesql_string(page_data, rbase + str_offs[14])
# 509: analyze_path=raw_track.get("analyze_path"),
```

## Deviations from Plan

None — plan executed exactly as written.

The worktree branch was behind master at agent start (worktree created before Phase 1 work landed). Resolved with `git merge master --ff-only` before any file changes. Not a code deviation — infrastructure only.

## TDD Gate Compliance

RED gate: commit `13fea32` — `test(02-01): add failing tests for TrackRow.analyze_path`
GREEN gate: commit `362a839` — `feat(02-01): add TrackRow.analyze_path field and read str_offs[14]`
REFACTOR gate: not needed — code was clean in GREEN phase.

## Known Stubs

`tests/test_import_controller.py` and `tests/test_duplicate_detector.py` reference `core.import_controller` and `core.duplicate_detector` which do not exist yet. These are intentional stubs — Plan 02-02 implements these modules and makes the tests go green.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced. The `analyze_path` field is read-only from PDB binary data; the empty-string-to-None normalization satisfies T-02-01-01.

## Self-Check: PASSED

Files exist:
- core/usb_db.py: FOUND
- core/pdb_parser.py: FOUND
- tests/conftest.py: FOUND
- tests/test_import_controller.py: FOUND
- tests/test_duplicate_detector.py: FOUND
- tests/test_pdb_parser.py: FOUND

Commits exist:
- 13fea32: FOUND (RED)
- 362a839: FOUND (GREEN)
- 4af3944: FOUND (Task 2 scaffold)
