# Phase 3: Polish + Distribution — Context

**Created:** 2026-06-03
**Phase:** 03-polish-distribution
**Source:** User decisions locked during /gsd-discuss-phase + RESEARCH.md verification

---

## Decisions

### D-01: Post-Import Summary — Per-Playlist Breakdown (UX-03)

The summary panel after a successful import shows a per-playlist table (one row per
imported playlist: playlist name, imported count, skipped count, failed count).
Not aggregate-only. This directly answers "did my playlist import?" — the DJ's core question.

**Locked by:** User decision (summary: per-playlist with per-track status breakdown)

---

### D-02: Summary Delivered via TrackPanel Mode Extension (UX-03)

The post-import summary is delivered by adding a third mode (`"post_import"`) to the
existing `TrackPanel`, NOT by creating a new `ui/summary_panel.py` widget.

Rationale from RESEARCH.md: Phase 2 established the TrackPanel mode-switch pattern (browse /
summary / post_import). A new SummaryPanel widget would duplicate the header/button/table
infrastructure. The RESEARCH explicitly recommends reuse and rejected QDialog.

**What changes in TrackPanel:**
- Add `RESULT_COLUMNS = ["PLAYLIST", "IMPORTED", "SKIPPED", "FAILED"]` constant
- Add `populate_post_import_summary(result: ImportResult, plan: ImportPlan) -> None`
- In that method: hide Back button, relabel Confirm → "Done", show aggregate in
  `_backup_label`, one row per playlist from `plan.selected_playlists`
- Done button calls `restore_browse_mode()` via `confirm_clicked` signal (already wired)

**Data source:** `ImportResult` has aggregate counts. Per-playlist breakdown is derived
by iterating `plan.selected_playlists` and summing per-track statuses from
`plan.track_statuses` at the time `_on_import_finished` is called.

---

### D-03: Session Persistence via QSettings NativeFormat (UX-04)

QSettings with NativeFormat (macOS plist backend) persists two values:
- `usb/last_mount` — `str`, absolute path of last USB mount point
- `usb/selected_playlist_ids` — `list[int]`, playlist IDs checked before import

**QSettings constructor:**
```
QSettings(QSettings.Format.NativeFormat, QSettings.Scope.UserScope,
          "com.inevents-mainz", "PlaylistConverter")
```
Maps to: `~/Library/Preferences/com.com-inevents-mainz.PlaylistConverter.plist`
(Qt prepends org name — this is a cosmetic naming quirk, data is correct.)

**Save points:** (1) when `_on_confirm_import` starts, (2) when user selects a USB
from the combo. This covers normal exits and crash scenarios.

**Restore:** In `MainWindow.__init__`, after `_setup_usb_watcher()`, call
`_restore_session()`. Store `_last_usb_name = Path(last_mount).name` and
`_restored_playlist_ids = {int(x) for x in raw_ids}`.

**USB name match:** Match by volume name (`Path(mount).name`) NOT full path, because
macOS may append a numeric suffix (`USB DISK 1`) on remount. See RESEARCH Pitfall 6.

**Type safety:** Always read playlist IDs with `type=list` and normalize via
`{int(x) for x in raw_ids}` to prevent string/int mismatch. See RESEARCH Pitfall 4.

**Absent USB on reopen:** Call `playlist_panel.set_empty_state(f"'{name}' was last used — connect it to continue")`.

---

### D-04: Bundle Identifier (DIST-01)

`CFBundleIdentifier` is set to `com.inevents-mainz.playlist-converter`.

**Locked by:** User decision.

---

### D-05: Ship at ~657 MB — No PySide6 Size-Reduction Spike (DIST-01)

Keep `collect_all('PySide6')` in `build/app.spec`. Do NOT attempt selective
Qt module collection in Phase 3. The RESEARCH confirmed ~657 MB is functional.
Size reduction is deferred to a future phase.

**Locked by:** User decision (bundle size: ship at ~657 MB).

---

### D-06: Ad-Hoc Signing Only — No Notarization (DIST-01 / DIST-02)

Phase 3 ships ad-hoc signed only. PyInstaller already applies ad-hoc signing.
No additional `codesign` call is needed.

First-launch instruction for recipients: right-click (ctrl-click) the .app → Open.

Notarization requires a paid Apple Developer account ($99/yr) — not available.

---

### D-07: DMG via dmgbuild 1.6.7 (DIST-02)

`dmgbuild` 1.6.7 (PyPI, slopcheck [OK]) creates the distributable DMG with
Applications symlink. Build settings file: `build/dmgbuild_settings.py`.

**Build sequence:** `pyinstaller build/app.spec` → `codesign --verify` →
`dmgbuild -s build/dmgbuild_settings.py -D app=dist/PlaylistConverter.app ...`

DMG output: `dist/PlaylistConverter-1.0.0.dmg`

---

### D-08: spec Updates (DIST-01)

Changes to `build/app.spec` in Phase 3:
1. Update `bundle_identifier` from `'com.example.playlist-converter'` to
   `'com.inevents-mainz.playlist-converter'` (D-04)
2. Update `LSMinimumSystemVersion` from `'14.0'` to `'13.0'`
3. Confirm `NSHighResolutionCapable: True` (already present)
4. Add explicit `pyrekordbox` submodule hiddenimports (prevent frozen-app
   ModuleNotFoundError — see RESEARCH hiddenimports audit)
5. Keep `collect_all('PySide6')` (D-05)

---

## Deferred Ideas

- PySide6 selective collection for bundle size reduction (~100–150 MB target)
- Notarization via `xcrun notarytool` (requires Apple Developer account)
- Universal Binary (x86_64 + arm64) — `lipo` broken on dev machine; current build is arm64
- Custom DMG background image (currently uses `builtin-arrow`)
- App icon (currently `icon=None` in spec)

---

## Open Items (Not Blocking Phase 3)

- SHA256 checksum in release notes (supply chain best practice for ad-hoc signed DMG)
- `/dist/PlaylistConverter-1.0.0.dmg` version string should align with `CFBundleShortVersionString`
  in spec (currently `0.1.0`); consider updating to `1.0.0` if this is the first release.
