# Phase 3: Polish + Distribution — Research

**Researched:** 2026-06-03
**Domain:** PySide6 UX (QSettings), PyInstaller macOS bundling, DMG creation, Gatekeeper / ad-hoc signing
**Confidence:** HIGH (all major findings verified against live codebase and tools on the build machine)

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| UX-03 | After import, user sees human-readable summary listing every playlist and track that was imported, skipped, or failed | `ImportResult` dataclass already carries `imported_count`, `skipped_count`, `failed_count`, `backup_path`. `_on_import_finished` in `main_window.py` currently just logs — a SummaryPanel replaces the TrackPanel view |
| UX-04 | App can be closed and reopened without losing USB detection or import state | `QSettings` (NativeFormat → plist in `~/Library/Preferences/`) stores `usb/last_mount` and `usb/selected_playlist_ids`; `_on_usbs_changed` restores on startup |
| DIST-01 | Standalone macOS .app — no Python/Homebrew needed | `.app` already builds via `build/app.spec`; sqlcipher3 is statically linked; BLOB key is embedded in `pyrekordbox.db6.database`; 657 MB unstripped |
| DIST-02 | .dmg disk image for drag-to-Applications installation | `dmgbuild` (Python, PyPI) produces standard macOS DMG; ad-hoc signing is already in place; notarization requires Apple Developer account |

</phase_requirements>

---

## Summary

Phase 3 is the polish and distribution phase. The full import pipeline is complete. Three things remain: (1) a post-import summary panel visible after a successful import, (2) session state persistence so the app re-opens in a useful state, and (3) a distributable `.dmg`.

The good news discovered during research: the hardest bundling risk from the CLAUDE.md notes (sqlcipher3 native library) is already resolved. The `sqlcipher3._sqlite3.cpython-311-darwin.so` binary is statically linked against only `/usr/lib/libSystem.B.dylib` — no Homebrew libsqlcipher, no custom dylib. It is already present in the built `.app` bundle under `Contents/Frameworks/sqlcipher3/`. The BLOB key for database decryption is embedded as a Python bytes literal directly in `pyrekordbox.db6.database` — it travels in the frozen bytecode. No external key file is needed.

The .app is 657 MB because `collect_all('PySide6')` pulls the entire Qt SDK including 3D, WebEngine, and Bluetooth modules. Only `QtWidgets`, `QtCore`, and `QtGui` are actually used. Switching to selective collection can bring the bundle to approximately 100–150 MB. This is worth doing before creating the DMG — a 657 MB download is unreasonable.

The current .app has `adhoc` code signature (`codesign --display` confirms `Signature=adhoc`, `flags=0x2(adhoc)`). `spctl --assess` returns `rejected`. Distribution without notarization requires the recipient to right-click → Open, which generates a one-time Gatekeeper exception. This is acceptable for a DJ-to-DJ tool — the user base expects some technical friction. Notarization requires an Apple Developer account ($99/year) which this project does not currently have.

**Primary recommendation:** UX-03 uses a new post-import summary panel replacing TrackPanel in its existing "summary mode" pattern. UX-04 uses `QSettings` NativeFormat (plist-backed, no extra files). DIST-01 fixes the spec to use selective PySide6 collection. DIST-02 uses `dmgbuild` (Python, on PyPI, slopcheck [OK]).

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Post-import summary display (UX-03) | Frontend (UI layer) | — | Pure display of `ImportResult` data already produced by ImportController; no new data access needed |
| Session state read/write (UX-04) | Frontend (UI layer) | OS plist | `QSettings` writes to `~/Library/Preferences/`; logic lives in `MainWindow.__init__` (restore) and `_on_import_finished` (persist) |
| USB path persistence | Frontend + OS | — | Store `str(mount)` in QSettings; re-scan `/Volumes` on startup and match by name |
| .app bundling (DIST-01) | Build tooling | — | PyInstaller spec edit; no app logic changes |
| .dmg creation (DIST-02) | Build tooling | macOS hdiutil | `dmgbuild` script wraps hdiutil; run at CI / release time |
| Gatekeeper signing | Build tooling | — | Ad-hoc `codesign` already applied by PyInstaller; deeper signing requires Apple Developer account |

---

## Standard Stack

### Core (phase 3 additions)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `PySide6.QtCore.QSettings` | 6.11.1 (already installed) | Persist session state (last USB mount, selected playlist IDs) | Stdlib Qt; NativeFormat uses macOS NSUserDefaults / plist; no extra files, no extra dependencies |
| `dmgbuild` | 1.6.7 | Create distributable macOS DMG | Python package, no npm/Homebrew dependency; slopcheck [OK]; well-maintained (github.com/dmgbuild/dmgbuild) |

### Supporting (already in project, no new installs needed)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pyinstaller` | 6.20.0 (already installed) | Rebuild .app with reduced PySide6 footprint | DIST-01 spec edit + rebuild |
| `codesign` (macOS system) | system | Ad-hoc sign for Gatekeeper bypass via right-click | Already applied by PyInstaller; no action needed unless spec changes |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `QSettings` NativeFormat | JSON config file | JSON is simpler to inspect but requires manual file path management; QSettings NativeFormat is the macOS-native approach and survives app renames cleanly |
| `QSettings` NativeFormat | `QSettings` IniFormat | IniFormat writes to `~/.config/` — fine for Linux but non-idiomatic on macOS; NativeFormat uses the plist backend that macOS apps use |
| `dmgbuild` | `hdiutil` (stdlib macOS) | hdiutil is always available but requires a multi-step shell script to set window layout, icon positions, and Applications symlink; dmgbuild provides a settings file for all of that in pure Python |
| `dmgbuild` | `create-dmg` (npm) | Adds a Node.js dependency to a Python project; npm v8.1.0 is present on this machine but the package is not installed; avoid cross-ecosystem dependency |

**Installation (new package only):**
```bash
pip install dmgbuild==1.6.7
```
`dmgbuild` is a dev/build dependency — it does not need to be bundled in the `.app`.

---

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| dmgbuild | PyPI | ~10 yrs (first release 2014) | multiple thousand/week | github.com/dmgbuild/dmgbuild | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

---

## Architecture Patterns

### System Architecture Diagram

```
ImportController.run_import_plan()
          │
          │ ImportResult {imported_count, skipped_count, failed_count, backup_path}
          ▼
MainWindow._on_import_finished()
          │
          ├─ write QSettings ──────────────────────► plist (~Library/Preferences/)
          │   usb/last_mount
          │   usb/selected_playlist_ids
          │
          └─ show SummaryPanel ────────────────────► TrackPanel (mode = "post_import")
              per-playlist breakdown
              total counts
              backup path
              "Done" button → restore_browse_mode()

On app startup:
QApplication → MainWindow.__init__()
          │
          ├─ read QSettings ────────────────────────► last_mount, selected_ids
          │
          ├─ USBScanner.current_usbs() ─────────────► /Volumes scan
          │
          └─ if last_mount volume is present: auto-select + pre-check saved playlists
             if absent: show "USB DISK was last used — connect it again"
```

### Recommended Project Structure (additions only)

```
ui/
├── summary_panel.py     # New: post-import summary panel
build/
├── app.spec             # Edit: selective PySide6 collection, replace collect_all
├── dmgbuild_settings.py # New: dmgbuild configuration file
dist/
└── PlaylistConverter-1.0.0.dmg  # output of build step
```

---

## Area 1: Post-Import Summary Panel (UX-03)

### Verified Current State

`main_window._on_import_finished()` currently restores the browse view immediately and logs aggregate counts. `ImportResult` carries `imported_count`, `skipped_count`, `failed_count`, `backup_path`. The TrackPanel already has a "summary mode" (`populate_import_summary` / `restore_browse_mode` / `_summary_header`).

### Recommended Design

**Reuse the TrackPanel's existing mode-switch pattern.** Add a third mode: `"post_import"`. This avoids a new window and reuses the established `back_clicked` / `confirm_clicked` signal infrastructure.

What the post-import summary shows:
- Header: "Import Complete" + aggregate counts (N imported, N skipped, N failed)
- Table: one row per playlist that was imported (playlist name, track count, status)
- Backup path label (already in `_backup_label`)
- Single "Done" button that calls `restore_browse_mode()`

**Data source:** `ImportResult` already has the aggregate counts. The per-playlist breakdown needs the `ImportPlan.selected_playlists` list (available in `MainWindow._import_plan` at the time `_on_import_finished` is called).

**Alternative: full-screen dialog** (`QDialog`) — rejected because it would break the established "TrackPanel as summary view" pattern set in Phase 2 (CONTEXT.md D-03). The planner must keep the same panel reuse approach.

### Pattern: Adding Post-Import Mode to TrackPanel

```python
# In TrackPanel — add new mode "post_import"
RESULT_COLUMNS = ["PLAYLIST", "IMPORTED", "SKIPPED", "FAILED"]

def populate_post_import_summary(
    self,
    result: ImportResult,
    plan: ImportPlan,
) -> None:
    """Switch to post-import summary mode."""
    self._mode = "post_import"
    self._summary_header.setVisible(True)
    self._back_btn.setVisible(False)       # hide Back
    self._confirm_btn.setText("Done")      # repurpose Confirm → Done

    agg_text = (
        f"{result.imported_count} imported  |  "
        f"{result.skipped_count} skipped  |  "
        f"{result.failed_count} failed"
    )
    self._backup_label.setText(agg_text)

    self.table.setSortingEnabled(False)
    self.table.setColumnCount(len(RESULT_COLUMNS))
    self.table.setHorizontalHeaderLabels(RESULT_COLUMNS)
    # populate per-playlist rows from plan.selected_playlists
    ...
```

`_on_import_finished` in `MainWindow` becomes:

```python
def _on_import_finished(self, result: ImportResult) -> None:
    self.track_panel.populate_post_import_summary(result, self._import_plan)
    self.track_panel.confirm_clicked.connect(self._on_summary_done)
    logger.info(
        "Import complete — %d imported, %d skipped, %d failed. Backup: %s",
        result.imported_count, result.skipped_count, result.failed_count, result.backup_path,
    )
```

---

## Area 2: Session State Persistence (UX-04)

### What to Persist

| Key | Type | Value |
|-----|------|-------|
| `usb/last_mount` | `str` | Last USB mount path, e.g. `/Volumes/USB DISK` |
| `usb/selected_playlist_ids` | `list[int]` | Playlist IDs the user had checked before import |

**Do not persist:** import results, DB state, track data. Only the two discovery parameters.

### QSettings Verified API

`QSettings` NativeFormat on macOS writes a `.plist` file to `~/Library/Preferences/`. Verified live on this machine:

```python
# Source: live test on PySide6 6.11.1 on this machine [VERIFIED]
from PySide6.QtCore import QSettings

s = QSettings(
    QSettings.Format.NativeFormat,
    QSettings.Scope.UserScope,
    "com.example",         # organization — should match CFBundleIdentifier domain
    "PlaylistConverter",   # app name
)
# Path: ~/Library/Preferences/com.com-example.PlaylistConverter.plist
# (Qt prepends org domain oddly — use IniFormat if plist path hygiene matters)

s.setValue("usb/last_mount", str(mount))
s.setValue("usb/selected_playlist_ids", list(selected_ids))
s.sync()  # flush to disk immediately

# Read back — no type coercion needed for str and list[int] when writing from Python
mount_str = s.value("usb/last_mount", None)           # returns str or None
ids = s.value("usb/selected_playlist_ids", [], type=list)  # returns list
```

**Verified behaviors (live test on PySide6 6.11.1):**
- `s.value("missing_key")` returns `None` — safe to check with `if mount_str:` [VERIFIED]
- `list[int]` round-trips correctly through NativeFormat [VERIFIED]
- `type=list` coercion in `value()` returns `[]` when key absent [VERIFIED]

**NativeFormat path quirk:** Qt constructs the plist name as `com.com-example.PlaylistConverter.plist` — it prepends the org name as-is before the app name. This is cosmetic only. If the bundle identifier is later changed to `com.example.playlist-converter`, the org should be set to `"playlist-converter"` and app to `"PlaylistConverter"` so the plist is named cleanly. [ASSUMED — plist naming follows Qt's org+app concatenation logic; confirmed empirically but depends on Qt version]

**Alternative: IniFormat** writes to `~/.config/com.example/PlaylistConverter.ini`. Equally valid, slightly less macOS-native. NativeFormat is recommended because it matches macOS conventions for a distributable app.

### Restore Logic on Startup

```python
# In MainWindow.__init__ — after _setup_usb_watcher():
self._restore_session()

def _restore_session(self) -> None:
    s = QSettings(
        QSettings.Format.NativeFormat, QSettings.Scope.UserScope,
        "com.example", "PlaylistConverter"
    )
    self._last_usb_name = Path(s.value("usb/last_mount", "")).name  # e.g. "USB DISK"
    self._restored_playlist_ids = set(
        s.value("usb/selected_playlist_ids", [], type=list)
    )
```

`_on_usbs_changed` uses `self._last_usb_name` to auto-select the previously used USB from the combo. `PlaylistPanel.populate()` uses `self._restored_playlist_ids` to pre-check rows whose `PlaylistRow.id` is in the set.

**Edge case: USB not present on reopen.** The combo will show "No Rekordbox USB found" but the app should also show a subtle hint in the playlist panel:

```
"USB DISK was last used — connect it to continue"
```
This requires `playlist_panel.set_empty_state()` to accept a custom message, which it already does.

### Save on Import Completion

```python
def _save_session(self) -> None:
    s = QSettings(
        QSettings.Format.NativeFormat, QSettings.Scope.UserScope,
        "com.example", "PlaylistConverter"
    )
    if self._usb_mount:
        s.setValue("usb/last_mount", str(self._usb_mount))
    checked = self._get_checked_playlist_ids()
    s.setValue("usb/selected_playlist_ids", list(checked))
    s.sync()
```

Call `_save_session()` at two points: (1) when `_on_confirm_import` starts, (2) when the user selects a USB from the combo. This covers normal exits and crash scenarios.

---

## Area 3: PyInstaller .app Bundling (DIST-01)

### Current State Assessment

`build/app.spec` already exists and produces a working `.app`. Verified:
- `dist/PlaylistConverter.app` builds and is 657 MB
- Code signature: `adhoc` (flags=0x2) — already signed, just not notarized
- `sqlcipher3._sqlite3.cpython-311-darwin.so` is in `Contents/Frameworks/sqlcipher3/` — the critical native dependency is already bundled [VERIFIED: live file check]
- `sqlcipher3` `.so` links only against `/usr/lib/libSystem.B.dylib` — statically linked SQLCipher, no Homebrew dependency [VERIFIED: `otool -L` output]
- BLOB key is embedded as bytes literal in `pyrekordbox.db6.database` (line 40) — travels with frozen bytecode, no external key file needed [VERIFIED: source inspection]
- `target_arch=None` in the spec — current build is `arm64` only (confirmed by `Format=app bundle with Mach-O thin (arm64)`), NOT universal. Comment in spec says "lipo broken on this dev machine" [VERIFIED: codesign output]

### Blocker: Bundle Size (657 MB)

The spec uses `collect_all('PySide6')` which pulls the entire Qt SDK. The app only uses `QtWidgets`, `QtCore`, `QtGui`, `QtSvg` (for rendering), and `QtPrintSupport` (macOS requirement for QtWidgets). The 3D, WebEngine, Bluetooth, and QML modules (which account for most of the 554 MB PySide6 directory) are unused.

**Fix: Replace `collect_all('PySide6')` with selective collection:**

```python
# build/app.spec — replace the collect_all block:

# BEFORE (pulls entire Qt SDK):
# tmp_ret = collect_all('PySide6')
# datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# AFTER (only modules the app actually imports):
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

hiddenimports += [
    'PySide6.QtWidgets',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtSvg',           # required by macOS Qt platform plugin
    'PySide6.QtPrintSupport',  # required by QtWidgets on macOS
    'shiboken6',
    'PySide6.support.deprecated',  # required since PySide6 6.4
]
# Still need platform plugin data (macOS .app requires this):
datas += collect_data_files('PySide6', includes=['plugins/platforms/*'])
datas += collect_data_files('PySide6', includes=['plugins/styles/*'])
```

**Expected result:** ~100–200 MB vs 657 MB. [ASSUMED — size estimate based on Qt module exclusion; actual size depends on which Qt transitive dependencies survive. A test build is required to verify.]

**Safer approach for Phase 3:** Keep `collect_all('PySide6')` for correctness; add a Wave 0 task to investigate size reduction as a build-time spike. Ship at 657 MB if size reduction breaks the build. A 657 MB DMG is large but functional.

### hiddenimports Audit

Current spec includes `['sqlcipher3', 'pyrekordbox']`. Add explicit submodule imports to prevent runtime `ModuleNotFoundError` in the frozen app:

```python
hiddenimports += [
    'sqlcipher3',
    'sqlcipher3.dbapi2',
    'pyrekordbox',
    'pyrekordbox.anlz',
    'pyrekordbox.anlz.file',
    'pyrekordbox.anlz.structs',
    'pyrekordbox.anlz.tags',
    'pyrekordbox.config',
    'pyrekordbox.db6',
    'pyrekordbox.db6.database',
    'pyrekordbox.db6.tables',
    'pyrekordbox.db6.registry',
    'pyrekordbox.db6.smartlist',
    'pyrekordbox.utils',
    'pyrekordbox.mysettings',
    'packaging',        # pyrekordbox.config imports packaging.version
    'packaging.version',
]
```

`packaging` is a transitive dependency of pyrekordbox (used in `config.py` for version comparison) that PyInstaller may miss. [VERIFIED: `pyrekordbox/config.py` imports `packaging.version`]

### Info.plist Gaps

Current Info.plist is missing:
- `CFBundleIdentifier`: set to `com.example.playlist-converter` — acceptable for Phase 3 but should be updated to a real domain before public distribution
- `LSUIElement`: not set — app appears in the Dock (correct for a window-based app)
- `NSAppleEventsUsageDescription`: not needed (no Apple Events)

No missing required keys that would block Gatekeeper for ad-hoc distribution.

### Build Command

```bash
cd "/path/to/project"
source .venv/bin/activate
pyinstaller build/app.spec
# Output: dist/PlaylistConverter.app
```

No `PYTHONHASHSEED=0` is needed for reproducibility at this project scale — the BLOB key is hardcoded, not hash-dependent.

---

## Area 4: .dmg Creation (DIST-02)

### Recommended Tool: dmgbuild

`dmgbuild` 1.6.7 is a Python package (slopcheck [OK], github.com/dmgbuild/dmgbuild). It wraps `hdiutil` with a Python settings file. `hdiutil` is always present on macOS (stdlib) and is what dmgbuild uses internally. `dmgbuild` adds the standard macOS DMG window layout (Applications symlink, icon positions, custom background) without a shell script.

Install as a dev dependency:
```bash
pip install dmgbuild==1.6.7
```

### dmgbuild Settings File

```python
# build/dmgbuild_settings.py
# Source: dmgbuild documentation, github.com/dmgbuild/dmgbuild

application = defines.get('app', '../dist/PlaylistConverter.app')
appname = 'PlaylistConverter'

files = [application]
symlinks = {'Applications': '/Applications'}
icon_locations = {
    appname + '.app': (150, 160),
    'Applications': (350, 160),
}
background = 'builtin-arrow'  # built-in arrow background; replace with custom PNG if desired
window_rect = ((100, 100), (500, 320))
icon_size = 80
text_size = 12
```

### Build Command

```bash
# Run after pyinstaller build:
dmgbuild -s build/dmgbuild_settings.py \
  "Playlist Converter" \
  dist/PlaylistConverter-1.0.0.dmg
```

### hdiutil Fallback (if dmgbuild unavailable)

```bash
# Minimal DMG without custom window layout (for CI environments):
hdiutil create \
  -volname "Playlist Converter" \
  -srcfolder dist/PlaylistConverter.app \
  -ov -format UDZO \
  dist/PlaylistConverter-1.0.0.dmg
```

This produces a functional DMG but without the Applications symlink drag-target. Acceptable for developer testing.

### Expected DMG Size

With the current 657 MB `.app`, the compressed DMG will be approximately 400–500 MB (UDZO = zlib compression). After PySide6 size reduction, approximately 80–120 MB. [ASSUMED — compression ratio estimate based on typical Qt framework compression rates]

---

## Area 5: Gatekeeper / Notarization (DIST-02)

### Current Signing State (Verified)

```
Signature=adhoc
flags=0x2(adhoc)
TeamIdentifier=not set
```

`spctl --assess` returns `rejected` — Gatekeeper blocks the app on other Macs when downloaded from the internet. [VERIFIED: live `spctl` check]

### Three Distribution Tiers

| Tier | Requirement | User experience | Phase 3 target? |
|------|-------------|-----------------|-----------------|
| Ad-hoc signed | No Apple account | Right-click → Open bypasses Gatekeeper | YES (current state) |
| Developer ID signed | $99/yr Apple account, `codesign --sign "Developer ID..."` | Gatekeeper passes silently | No (no account available) |
| Notarized | Developer ID + `xcrun notarytool submit` | Gatekeeper passes, no quarantine warning | No (requires Apple account + paid plan) |

### Recommended Approach for Phase 3

**Ship ad-hoc signed only.** `xcrun notarytool` is present at `/Applications/Xcode.app/Contents/Developer/usr/bin/notarytool` but requires valid Apple Developer credentials (`security find-identity -v -p codesigning` returns 0 valid identities). [VERIFIED: live check]

**User instruction to include in README / DMG background:**
```
First launch: right-click (or ctrl-click) PlaylistConverter.app → Open
Click "Open" in the dialog. You only need to do this once.
```

This is the standard distribution method for unsigned macOS apps. Rekordbox itself originally required this flow for many users.

### Ad-hoc Signing After Build

PyInstaller already applies `--codesign_identity=None` which triggers ad-hoc signing automatically. No additional `codesign` call is needed in the build script unless rebuilding removes the signature.

To explicitly re-sign (if ever needed):
```bash
codesign --sign - --force --deep --preserve-metadata=entitlements,requirements \
  dist/PlaylistConverter.app
```

**Pitfall: `--deep` damages nested bundles.** The `--deep` flag was deprecated in Apple's toolchain — it can break nested framework signatures. Use it only as a last resort. The correct approach for multi-framework bundles is to sign each framework separately, then sign the outer bundle. PyInstaller handles this correctly; don't re-sign unless something broke. [CITED: Apple Technical Note TN2206]

### Why Not Notarize in Phase 3

- Requires paid Apple Developer Program membership ($99/yr)
- Requires an internet connection to the Apple notary service at build time
- The notarytool workflow adds 5–30 minutes to the build process
- The DJ community target audience understands right-click → Open

This can be added in a future phase if the app reaches public distribution.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Settings persistence | Custom JSON/pickle file | `QSettings` | QSettings handles atomic writes, plist format, OS migrations, key/value namespace; JSON in `~/Library/` is non-idiomatic and loses OS-level features |
| DMG window layout | `hdiutil` shell script with AppleScript positioning | `dmgbuild` | AppleScript-based icon positioning is fragile, macOS-version-sensitive, and requires GUI access; dmgbuild does it with a Python dict |
| sqlcipher3 bundling | Copy `.so` manually with `--add-binary` | Already bundled by `hiddenimports += ['sqlcipher3']` in existing spec | Already resolved; don't duplicate |
| Post-import summary window | `QDialog` popup | Extend existing TrackPanel mode-switch | Phase 2 established the pattern (D-03); a dialog would break the established UX flow |

---

## Common Pitfalls

### Pitfall 1: `collect_all('PySide6')` Produces Unreasonable Bundle Size

**What goes wrong:** The current spec uses `collect_all('PySide6')` which pulls all Qt modules including 3D, WebEngine, Bluetooth, and QML. The result is 657 MB — too large for a DMG download.
**Why it happens:** `collect_all` is the safe default that guarantees no missing modules; it trades size for safety.
**How to avoid:** Enumerate only the Qt modules the app imports (`QtWidgets`, `QtCore`, `QtGui`, `QtSvg`, `QtPrintSupport`) plus the platform plugin data. A test build after reducing the spec verifies no missing-module crash at startup.
**Warning signs:** DMG is 400+ MB; build takes >5 minutes.

### Pitfall 2: QSettings NativeFormat Plist Path Naming

**What goes wrong:** Qt constructs the plist filename as `com.com-example.PlaylistConverter.plist` when org is `"com.example"` — it concatenates without a separator, producing an ugly double-`com`. Settings written by the dev build and settings written by the packaged `.app` diverge if bundle identifier changes between phases.
**Why it happens:** Qt's NativeFormat plist naming formula is `{org}.{app}.plist` where org is the raw string passed to QSettings constructor, not the domain-style bundle identifier.
**How to avoid:** Use `QCoreApplication.setOrganizationDomain()` and `QCoreApplication.setApplicationName()` in `main.py` and call `QSettings()` with no constructor args. Qt reads those from the application context. OR: use a single stable org string like `"com.example"` and accept the plist naming quirk — the data still persists correctly.
**Warning signs:** `QSettings().value("key")` returns `None` after upgrade even though user had valid settings previously — means org/app name changed and plist is in a different path.

### Pitfall 3: Ad-hoc Signature Broken After Manual File Edits

**What goes wrong:** After `pyinstaller build/app.spec`, any manual file modification inside the `.app` bundle invalidates the ad-hoc signature. `spctl --assess` gives `"CSSM_APPLE_TP_ACTION: code or signature modified"`.
**Why it happens:** Ad-hoc signing seals the Sealed Resources list (5,309 files in this build). Any change to any file breaks the seal.
**How to avoid:** Never edit files inside `dist/PlaylistConverter.app` after build. If post-build patching is needed, run `pyinstaller build/app.spec` again after the patch, then re-sign.
**Warning signs:** `codesign --verify dist/PlaylistConverter.app` returns non-zero exit code.

### Pitfall 4: QSettings `selected_playlist_ids` Type Loss on Reopen

**What goes wrong:** Playlist IDs are integers (e.g., `1, 2, 99`) but when read back via `QSettings.value("key")` without a `type=` argument, they may be returned as strings (`"1"`, `"2"`, `"99"`) depending on plist serialization. A set intersection `{1, 2} & {set of stored ids}` fails silently if stored ids are strings.
**Why it happens:** NativeFormat serializes small integers through NSUserDefaults which may or may not preserve Python int type depending on Qt version.
**How to avoid:** Always read with explicit type coercion: `s.value("usb/selected_playlist_ids", [], type=list)` and then `{int(x) for x in ids}` to normalize. Verified: `list[int]` round-trips correctly in PySide6 6.11.1 NativeFormat. [VERIFIED: live test]
**Warning signs:** Pre-checked playlists are not restored on reopen even though settings file contains the IDs.

### Pitfall 5: dmgbuild Requires `.app` at Build Time (Obvious but Easy to Miss)

**What goes wrong:** Running the dmgbuild step before `pyinstaller build/app.spec` completes (or in a parallel CI job) produces an empty or broken DMG.
**Why it happens:** dmgbuild copies the `.app` from `dist/` at the time it runs.
**How to avoid:** In the build script, `pyinstaller` must complete before `dmgbuild` runs. Document the explicit sequence: `pyinstaller` → `codesign` check → `dmgbuild`.
**Warning signs:** DMG mounts but `.app` is missing or zero-byte.

### Pitfall 6: USB Volume Name Changes Between Sessions

**What goes wrong:** User stores `last_mount = /Volumes/USB DISK`. The DJ reconnects the same USB stick but macOS mounts it as `/Volumes/USB DISK 1` (because another `/Volumes/USB DISK` path is still registered). The stored path is a dead letter.
**Why it happens:** macOS appends a numeric suffix when the volume name conflicts with an already-mounted path.
**How to avoid:** `USBScanner` already returns the live mount paths. The restore logic should match by volume `name` (i.e., `Path(last_mount).name == current_mount.name`) rather than full path equality. If the match is ambiguous (two USBs with the same volume name), fall back to "multiple USBs found, please select".
**Warning signs:** "USB DISK was last used — connect it" shown even when the USB is clearly plugged in.

---

## Code Examples

### QSettings: Save and Restore Session

```python
# Source: PySide6 6.11.1, live test on this machine [VERIFIED]
from PySide6.QtCore import QSettings
from pathlib import Path

ORG = "com.example"
APP = "PlaylistConverter"

def _settings() -> QSettings:
    return QSettings(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, ORG, APP)

def save_session(usb_mount: Path, selected_ids: set[int]) -> None:
    s = _settings()
    s.setValue("usb/last_mount", str(usb_mount))
    s.setValue("usb/selected_playlist_ids", sorted(selected_ids))
    s.sync()

def load_session() -> tuple[str | None, set[int]]:
    s = _settings()
    mount_str = s.value("usb/last_mount", None)
    raw_ids = s.value("usb/selected_playlist_ids", [], type=list)
    ids = {int(x) for x in raw_ids if x is not None}
    return mount_str, ids
```

### dmgbuild Settings File

```python
# build/dmgbuild_settings.py
# Source: dmgbuild docs, github.com/dmgbuild/dmgbuild [CITED]

application = defines.get('app', '../dist/PlaylistConverter.app')
appname = 'PlaylistConverter'

files = [application]
symlinks = {'Applications': '/Applications'}
icon_locations = {
    'PlaylistConverter.app': (150, 160),
    'Applications': (350, 160),
}
background = 'builtin-arrow'
window_rect = ((100, 100), (500, 320))
icon_size = 80
text_size = 12
format = 'UDZO'  # zlib-compressed read-only image
```

### Build Script Sequence

```bash
#!/bin/bash
set -e
source .venv/bin/activate

# 1. Build .app
pyinstaller build/app.spec

# 2. Verify signature (ad-hoc, applied automatically by PyInstaller)
codesign --verify --verbose dist/PlaylistConverter.app

# 3. Create DMG
APP_PATH=dist/PlaylistConverter.app
VERSION=$(defaults read "$APP_PATH/Contents/Info.plist" CFBundleShortVersionString)
dmgbuild \
  -s build/dmgbuild_settings.py \
  -D app="$APP_PATH" \
  "Playlist Converter" \
  "dist/PlaylistConverter-${VERSION}.dmg"

echo "Done: dist/PlaylistConverter-${VERSION}.dmg"
```

### PyInstaller Spec: Selective PySide6 Collection (Investigation Target)

```python
# build/app.spec — selective collection (test in Wave 0 spike)
# Source: PyInstaller docs, pyinstaller.org/en/stable/hooks-config.html [CITED: ASSUMED]

from PyInstaller.utils.hooks import collect_data_files

datas = []
binaries = []
hiddenimports = [
    # PySide6 — only what the app actually imports
    'PySide6.QtWidgets',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtSvg',          # macOS platform plugin dependency
    'PySide6.QtPrintSupport', # QtWidgets requires this on macOS
    'shiboken6',
    'PySide6.support.deprecated',

    # pyrekordbox — all submodules (PyInstaller may not auto-discover them)
    'pyrekordbox', 'pyrekordbox.anlz', 'pyrekordbox.anlz.file',
    'pyrekordbox.anlz.structs', 'pyrekordbox.anlz.tags',
    'pyrekordbox.config', 'pyrekordbox.db6', 'pyrekordbox.db6.database',
    'pyrekordbox.db6.tables', 'pyrekordbox.db6.registry',
    'pyrekordbox.db6.smartlist', 'pyrekordbox.utils',
    'pyrekordbox.mysettings', 'pyrekordbox.mysettings.file',

    # sqlcipher3 — native .so already present; keep hiddenimport for dbapi2 submodule
    'sqlcipher3', 'sqlcipher3.dbapi2',

    # transitive deps
    'packaging', 'packaging.version', 'sqlalchemy',
]

# Qt platform plugins and styles are required at runtime even if not imported directly
datas += collect_data_files('PySide6', includes=['plugins/platforms/*'])
datas += collect_data_files('PySide6', includes=['plugins/styles/*'])
datas += collect_data_files('PySide6', includes=['plugins/imageformats/*'])
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| PyInstaller 5.x manual Qt hooks | PyInstaller 6.x auto-discovers PySide6 modules via built-in hooks | PyInstaller 6.0 (2023) | No need to manually specify Qt binaries; `collect_all` or `hiddenimports` suffices |
| pysqlcipher3 (requires Homebrew libsqlcipher) | sqlcipher3 (statically linked) | pyrekordbox 0.3.x onwards | Eliminates the hardest bundling risk; no Homebrew dependency in the bundle |
| xcrun altool for notarization | xcrun notarytool | Xcode 13 / 2021 | `altool` was deprecated; `notarytool` is the current tool |
| Right-click → Open workaround universal | Still required for ad-hoc signed apps | N/A — macOS 13+ | Gatekeeper still blocks unsigned downloads; right-click → Open is the canonical bypass |

**Deprecated:**
- `xcrun altool notarize`: removed in Xcode 15; use `notarytool`
- `pysqlcipher3`: effectively superseded by `sqlcipher3` for the pyrekordbox use case

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Selective PySide6 collection (replacing `collect_all`) will produce a ~100–200 MB bundle | DIST-01 / Pitfall 1 | If Qt transitive dependencies fail to load, app crashes at startup; mitigation: spike task in Wave 0 |
| A2 | DMG with 657 MB `.app` will compress to ~400–500 MB (UDZO format) | Area 4 | DMG could be larger; check with `du -sh dist/*.dmg` after build |
| A3 | `packaging.version` is not auto-discovered by PyInstaller and needs explicit `hiddenimport` | DIST-01 hiddenimports | If packaging is auto-discovered, the extra hiddenimport entry is harmless (no-op) |
| A4 | `QSettings` plist naming quirk (`com.com-example.PlaylistConverter.plist`) will not cause problems if org string stays constant | Area 2 | If org string ever changes (e.g., when real bundle ID is set), existing user settings are silently lost |
| A5 | Per-playlist breakdown in the post-import summary can be derived from `ImportPlan.selected_playlists` + per-track status counts at the time `_on_import_finished` is called | Area 1 | `ImportResult` only has aggregate counts; per-playlist breakdown requires iterating `plan.selected_playlists` in `_on_import_finished` — plan must pass `self._import_plan` to `populate_post_import_summary` |

---

## Open Questions (RESOLVED)

1. **Per-playlist breakdown vs aggregate-only?**
   RESOLVED: Per-playlist breakdown — user decision confirmed before planning.

2. **PySide6 size reduction spike or ship at 657 MB?**
   RESOLVED: Ship at ~657 MB directly — no size reduction spike. User decision confirmed.

3. **CFBundleIdentifier domain?**
   RESOLVED: `com.inevents-mainz.playlist-converter` — based on user's email domain. Locked in CONTEXT.md D-04.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `pyinstaller` | DIST-01 | ✓ | 6.20.0 | — |
| `PySide6` | UX-03, UX-04 | ✓ | 6.11.1 | — |
| `pyrekordbox` | DIST-01 (bundle verification) | ✓ | 0.4.4 | — |
| `sqlcipher3` | DIST-01 (already in .app) | ✓ | statically linked | — |
| `dmgbuild` | DIST-02 | ✓ (installed by slopcheck test) | 1.6.7 | `hdiutil` shell script |
| `codesign` (macOS system) | DIST-01, DIST-02 | ✓ | macOS system | — |
| `xcrun notarytool` | Notarization (post-Phase 3) | ✓ (binary present) | Xcode toolchain | N/A — no Apple Developer account |
| Apple Developer account | Notarization | ✗ | — | Right-click → Open workflow |
| `create-dmg` (npm) | DIST-02 alternative | ✗ | — | dmgbuild (preferred) |

**Missing dependencies with no fallback:**
- Apple Developer account — blocks notarization. Phase 3 scoped to ad-hoc signing only.

**Missing dependencies with fallback:**
- `dmgbuild` — fallback is `hdiutil create` (always present); dmgbuild is already installed in venv.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >= 7.0 |
| Config file | `pytest.ini` (testpaths = tests, addopts = -x -q) |
| Quick run command | `python -m pytest -x -q` |
| Full suite command | `python -m pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| UX-03 | `TrackPanel.populate_post_import_summary()` populates correct row counts | unit | `pytest tests/test_track_panel.py::test_post_import_summary -x` | ❌ Wave 0 |
| UX-03 | `_on_import_finished` transitions to post_import mode | unit | `pytest tests/test_main_window.py::test_import_finished_shows_summary -x` | ❌ Wave 0 |
| UX-04 | `save_session` / `load_session` round-trip via QSettings | unit | `pytest tests/test_session_state.py -x` | ❌ Wave 0 |
| UX-04 | USB name match logic (path vs volume name) | unit | `pytest tests/test_session_state.py::test_usb_name_match -x` | ❌ Wave 0 |
| DIST-01 | `dist/PlaylistConverter.app` exists and has valid ad-hoc signature | manual / build | `codesign --verify --verbose dist/PlaylistConverter.app` | ❌ Wave 0 (build script) |
| DIST-02 | `.dmg` mounts and contains `.app` + Applications symlink | manual | Mount DMG, verify contents | ❌ Wave 0 (build script) |

### Sampling Rate

- Per task commit: `python -m pytest tests/test_session_state.py tests/test_track_panel.py -x -q`
- Per wave merge: `python -m pytest`
- Phase gate: Full suite green + manual DMG verification before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_session_state.py` — covers UX-04 (QSettings round-trip, USB name match)
- [ ] `tests/test_track_panel.py` — extend with `test_post_import_summary` covering UX-03
- [ ] `tests/test_main_window.py` — extend with `test_import_finished_shows_summary`

*(Note: GUI tests for TrackPanel and MainWindow require `QT_QPA_PLATFORM=offscreen` to run headlessly — set in conftest.py `autouse` fixture.)*

---

## Security Domain

`security_enforcement: true` in `.planning/config.json`. ASVS Level 1 applies.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A — local desktop app, no login |
| V3 Session Management | partial | QSettings stores mount path + playlist IDs; no secrets, no tokens — low risk |
| V4 Access Control | no | Single-user desktop app |
| V5 Input Validation | yes | `last_mount` path read from QSettings must be validated before use (path traversal guard already in import controller) |
| V6 Cryptography | no | No new crypto in Phase 3; SQLCipher handled by pyrekordbox |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| QSettings path poisoning: attacker modifies the plist file to inject a malicious mount path | Tampering | Validate `last_mount` with `Path(mount_str).is_absolute()` and `Path(mount_str).name` check before using; existing path traversal guard in `_on_import_clicked` applies |
| .dmg substitution (supply chain): DMG downloaded from third-party host | Repudiation | Notarization resolves this; for Phase 3, document download source and provide SHA256 checksum in release notes |

---

## Sources

### Primary (HIGH confidence)
- Live codebase: `build/app.spec`, `core/import_controller.py`, `ui/track_panel.py`, `ui/main_window.py` — read at research time
- Live tool output: `codesign --display`, `spctl --assess`, `otool -L sqlcipher3/_sqlite3.so`, `QSettings` constructor test — all run on this machine
- `pyrekordbox.db6.database` source inspection — BLOB on line 40, sqlcipher3 import on line 27

### Secondary (MEDIUM confidence)
- dmgbuild GitHub README: github.com/dmgbuild/dmgbuild — settings file format
- PyInstaller PySide6 hook source: `.venv/lib/python3.11/site-packages/PyInstaller/hooks/hook-PySide6.py` — verified hiddenimports pattern
- PyInstaller documentation: pyinstaller.org/en/stable/hooks-config.html — hooksconfig options

### Tertiary (LOW confidence)
- A1: PySide6 selective collection bundle size estimate (~100–150 MB) — based on typical Qt module sizes; unverified without a test build
- A4: QSettings org/app plist naming — observed empirically but Qt version-sensitive

---

## Metadata

**Confidence breakdown:**
- UX-03 (Summary Panel): HIGH — TrackPanel mode-switch pattern verified in code; `ImportResult` fields confirmed
- UX-04 (QSettings): HIGH — live API test on PySide6 6.11.1; round-trip verified
- DIST-01 (PyInstaller): HIGH for current state; MEDIUM for size reduction (test build needed)
- DIST-02 (DMG + signing): HIGH — dmgbuild installed and verified; signing state confirmed live

**Research date:** 2026-06-03
**Valid until:** 2026-07-03 (stable stack; pyrekordbox and PySide6 move slowly)
