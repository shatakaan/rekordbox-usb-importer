---
phase: 02-full-import-pipeline
plan: "04"
subsystem: summary-panel-ui
tags: [ui, track_panel, summary_mode, import_confirmation, wave-3]

key_files:
  modified:
    - ui/track_panel.py

decisions:
  - "populate_import_summary takes a separate `tracks: dict[int, TrackRow]` parameter instead of reading from plan directly — keeps ImportPlan decoupled from UI layer"
  - "_apply_browse_column_sizes() extracted as private helper so both __init__ and restore_browse_mode use the same sizing logic"
  - "QBrush(QColor(...)) used for status color — QTableWidgetItem.setForeground requires a QBrush, not a plain string"
  - "back_clicked/confirm_clicked as public signal aliases on the panel — MainWindow connects to these without accessing private button references"

metrics:
  duration_seconds: 360
  completed_date: "2026-06-02"
  tasks_completed: 1
  tasks_total: 1
  files_changed: 1
---

# Phase 2 Plan 04: Summary Panel UI

**One-liner:** TrackPanel extended with summary mode — 6-column pre-import view with checkbox per track, STATUS column (color-coded), Back/Confirm buttons, and restore back to browse mode.

## What Was Built

**ui/track_panel.py** extended with:

### New constants
```python
SUMMARY_COLUMNS = ["", "TITLE", "ARTIST", "BPM", "DURATION", "STATUS"]
_STATUS_COLORS = {"NEW": "#ADC6FF", "DUPLICATE": "#FFA040", "SKIP": "#8B90A0"}
```

### Summary header widget (hidden in browse mode)
- `self._summary_header`: QWidget with Back button, backup path label, Confirm Import button
- `self.back_clicked = self._back_btn.clicked` — public signal alias
- `self.confirm_clicked = self._confirm_btn.clicked` — public signal alias

### New methods
- `populate_import_summary(plan, tracks, backup_path_str="")` — switches to 6-column summary layout; NEW rows checked, DUPLICATE/SKIP unchecked; STATUS column color-coded
- `get_import_selections() -> dict` — reads checkbox states, returns `{track_id: bool}`
- `restore_browse_mode()` — resets to 7-column browse layout, hides summary header

### Private helper
- `_apply_browse_column_sizes()` — extracted from __init__ so restore_browse_mode can reuse the same sizing

## Verification
```
python -c "from ui.track_panel import TrackPanel; ..."
→ populate_import_summary: True
→ restore_browse_mode: True
→ get_import_selections: True

pytest tests/ --tb=short → 28 passed, 5 skipped
```
