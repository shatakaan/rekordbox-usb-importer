# Technology Stack

**Project:** Rekordbox USB Playlist Importer
**Researched:** 2026-06-01
**Research basis:** Training knowledge (cutoff August 2025) — live tool lookups were unavailable in this session. All GitHub links and version numbers should be manually verified before implementation.

---

## Recommended Stack

### Database Layer

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pyrekordbox | 0.3.x (verify on PyPI) | Read/write Rekordbox 6/7 SQLite DBs | Only purpose-built Python library for Rekordbox DB access; handles the proprietary SQLite encryption Pioneer uses |
| Python `sqlite3` (stdlib) | built-in | Direct fallback queries when pyrekordbox abstraction is insufficient | Zero dependency, always available, sufficient for raw SELECT/INSERT once schema is known |

**pyrekordbox status (as of training cutoff, verify current):**

- GitHub: https://github.com/dylanljones/pyrekordbox
- PyPI: https://pypi.org/project/pyrekordbox/
- Actively maintained as of mid-2025; Dylan Jones has been the primary author
- Supports Rekordbox 6 database (`master.db`) read and write
- Supports reading USB-exported databases (the `PIONEER/rekordbox/` folder structure)
- Handles the AES-based SQLite encryption that Rekordbox 6/7 applies to certain tables — this is the single most important reason to use it over raw sqlite3, because decrypting the DB manually requires reverse-engineered keys that pyrekordbox already embeds
- Exposes Python objects for: tracks (`DjmdContent`), playlists (`DjmdPlaylist`), playlist membership (`DjmdSongPlaylist`), and cue points
- Rekordbox 7 support: partially introduced; verify current table schema coverage before committing
- Key limitation: pyrekordbox does not manage file I/O or path resolution — that logic stays in application code
- Key limitation: it requires `pysqlcipher3` or `sqlcipher` on the system for the encrypted tables; this complicates bundling (see Bundling section below)

**Confidence: MEDIUM** — pyrekordbox's core capabilities are well-documented in its README and confirmed by community usage, but version-specific Rekordbox 7 support should be verified against the current changelog before relying on it. The sqlcipher dependency situation needs live verification.

---

### GUI Framework

**Recommendation: PySide6 (Qt 6 via the official Python binding)**

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PySide6 | 6.7.x (verify on PyPI) | macOS GUI | Native macOS look with minimal effort; LGPL license (distributable without open-sourcing app); Qt6 is the current generation; works with PyInstaller |

**Rationale over alternatives:**

- Qt/PySide6 produces genuinely native-feeling macOS apps with minimal styling effort. The `QApplication` + `QMainWindow` pattern is mature and well-understood.
- For this tool the UI surface is small: a file picker or USB device list, a checkbox list of playlists, an import button, a log/progress area. PySide6 handles this in ~200 lines of straightforward code.
- LGPL license means you can ship a closed or proprietary `.app` without triggering copyleft — PyQt6 (the alternative Qt binding) requires a commercial license for closed-source distribution or GPL compliance.
- PySide6 bundles cleanly with PyInstaller. The `--collect-all PySide6` flag pulls in what's needed.

**Confidence: HIGH** — PySide6 licensing and PyInstaller compatibility are well-established facts as of training cutoff.

---

### Bundling / Distribution

**Recommendation: PyInstaller 6.x**

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PyInstaller | 6.x | Bundle Python app as standalone macOS `.app` | Most mature option; best community support for PySide6; produces proper `.app` bundle; handles hooks for native libs |

**Rationale:**

- PyInstaller is the de-facto standard for Python-to-macOS-app bundling as of 2025. It has explicit hooks for PySide6 and handles Qt plugin discovery automatically.
- Produces a `.app` bundle (with `--windowed` flag) that can be zipped and distributed without any installer.
- For notarization and Gatekeeper compliance you will eventually need to code-sign, but for initial development and internal distribution it works unsigned.
- The sqlcipher / pysqlcipher3 dependency (required by pyrekordbox for encrypted tables) needs a custom PyInstaller hook or `--add-binary` directive to bundle the native `.dylib`. This is the highest-risk bundling issue — plan a spike here.

**Confidence: HIGH** for PyInstaller as the correct choice. **MEDIUM** for the sqlcipher bundling path — this needs a concrete test on the target machine before committing to the approach.

---

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pathlib` (stdlib) | built-in | USB path resolution, mount point detection | Always — cleaner than `os.path` for cross-path manipulation |
| `shutil` (stdlib) | built-in | Database backup before write | Always — `shutil.copy2` preserves metadata |
| `subprocess` (stdlib) | built-in | Detect running Rekordbox process | Always — `pgrep rekordbox` or `ps aux` grep |
| `logging` (stdlib) | built-in | Structured log output to GUI log area | Always — wire to a QTextEdit via a logging handler |

No external supporting libraries are needed beyond pyrekordbox and PySide6. Keeping dependencies minimal is critical for reliable bundling.

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| DB access | pyrekordbox | Raw `sqlite3` + manual schema | Pioneer encrypts key tables in RB6/7; raw sqlite3 cannot read them without the cipher key. You would need to reverse-engineer or hard-code the AES key — pyrekordbox already did this work |
| DB access | pyrekordbox | rekordcrate (Rust) | Excellent for read-only parsing; not usable from Python without FFI; overkill for this scope |
| DB access | pyrekordbox | rekordcloud / rekordbox-sdk | No public Python SDK from Pioneer; Pioneer's own SDK targets C++ |
| GUI | PySide6 | PyQt6 | Functionally identical to PySide6 but requires commercial license for closed-source distribution. Use PySide6 instead |
| GUI | PySide6 | tkinter | Ships with Python (zero install), but looks distinctly non-native on macOS Ventura+. Acceptable for internal tools, not acceptable for distribution to DJs |
| GUI | PySide6 | wxPython | Truly native macOS widgets, but documentation is sparse, community smaller, and PyInstaller integration is more fragile than PySide6 |
| GUI | PySide6 | Dear PyGui / PySimpleGUI | Immediate-mode GUI; simpler API but less native feel; PySimpleGUI relicensed to commercial in 2023 — avoid |
| Bundling | PyInstaller | py2app | macOS-only (acceptable here), but less actively maintained than PyInstaller and worse PySide6 support. Use PyInstaller |
| Bundling | PyInstaller | Briefcase (BeeWare) | Higher-level abstraction; targets multiple platforms. For a macOS-only tool it adds complexity without benefit. PyInstaller gives more direct control over the bundle |
| Bundling | PyInstaller | cx_Freeze | Less community support for Qt apps on macOS compared to PyInstaller |
| Language | Python | Swift/SwiftUI | Excellent native macOS app; but no equivalent of pyrekordbox exists in Swift — you would need to reimplement DB parsing from scratch. Not worth it unless Python bundling proves unworkable |
| Language | Python | Electron/Node.js | No mature Rekordbox DB library in Node; adds a browser runtime for a desktop-utility use case |

---

## What NOT to Use and Why

**PySimpleGUI** — relicensed to commercial/subscription in 2023. Previously popular in tutorials; now a liability for open or freely distributed tools.

**PyQt6** — technically identical to PySide6 in capability, but GPL/commercial dual-license. PySide6 is the LGPL-licensed official Qt binding. There is no technical reason to choose PyQt6 over PySide6 for a new project.

**tkinter** — acceptable for internal scripts; unacceptable for user-facing macOS apps. The default macOS look is dated and inconsistent across macOS versions.

**py2app** — do not choose it as the primary bundling tool. It has known issues with Qt 6 and PySide6 bundles and is not actively keeping up with macOS security requirements (hardened runtime, notarization). PyInstaller has an active maintainer team with explicit macOS support.

**Direct SQLite access without pyrekordbox** — Pioneer applies SQLCipher-based encryption to `master.db` in Rekordbox 6/7. You cannot open the file with standard `sqlite3` and get meaningful data. pyrekordbox contains the reverse-engineered cipher configuration. Bypassing pyrekordbox means re-implementing this decryption yourself.

---

## Critical Dependency Risk: sqlcipher / pysqlcipher3

This is the highest-risk item in the stack.

pyrekordbox depends on `pysqlcipher3` (a Python binding for SQLCipher, the encrypted SQLite variant). `pysqlcipher3` in turn requires a compiled `libsqlcipher` native library. On a developer machine this is typically installed via Homebrew (`brew install sqlcipher`).

**The problem:** When bundling with PyInstaller into a standalone `.app`, the native `libsqlcipher.dylib` must be explicitly included and the `pysqlcipher3` extension must resolve its `DYLIB` path at runtime relative to the bundle, not to `/usr/local/lib/`. This requires:

1. A PyInstaller hook that adds the `.dylib` to the bundle
2. Using `install_name_tool` or `delocate` to fix the dynamic library references inside the bundle
3. Testing on a machine without Homebrew to confirm no external dependencies leak through

**Mitigation options (verify current state before committing):**

- Check whether pyrekordbox 0.3.x+ ships a vendored or statically linked sqlcipher option
- Check whether the `apsw` package (another SQLite Python binding) has SQLCipher support that bundles more cleanly
- Alternatively: open the DB once on a developer machine to extract and cache the decrypted schema, then operate on a copy — but this is fragile and not suitable for a user-facing tool

**Recommendation:** The very first technical spike in Phase 1 should be: install pyrekordbox, open a real USB database, bundle with PyInstaller, run the bundle on a machine without Homebrew. This validates the core assumption before any GUI work.

**Confidence: MEDIUM** — the sqlcipher bundling path is known to be non-trivial but is solvable. The exact current state of pyrekordbox's dependency management needs live verification.

---

## Existing Open-Source Tools (Similar Scope)

Based on training knowledge, no widely adopted open-source tool exists that does exactly what this project does (playlist import without file copy for Rekordbox 6/7). The closest known projects:

- **pyrekordbox** itself — the library, not a GUI tool. https://github.com/dylanljones/pyrekordbox
- **rekordcrate** (Rust) — read-only parsing of Rekordbox USB databases, no write capability. https://github.com/Holzhaus/rekordcrate
- **DJ collection exporter** — export tools exist (RB to Serato, RB to Traktor) but they work in the export direction, not import-without-copy
- **DJCU (DJ Conversion Utility)** — commercial macOS app; not open-source; converts between DJ software libraries; not free

**Confidence: LOW** — this is a niche use case and the open-source landscape changes. A GitHub search for `rekordbox import playlist usb` before starting implementation is strongly recommended.

---

## Recommended Python Version

**Python 3.11** — use this specific version.

- 3.11 is the most widely tested version with both pyrekordbox and PySide6 as of mid-2025
- 3.12 introduced some changes that affected a small number of PyInstaller hooks; 3.11 is the safer choice until 3.12 compatibility is confirmed in pyrekordbox's CI
- 3.10 minimum is required by PySide6 6.x; 3.9 is end-of-life

**Confidence: MEDIUM** — Python version compatibility should be confirmed against pyrekordbox's current `setup.cfg` or `pyproject.toml` before creating the virtual environment.

---

## Installation (Development Setup)

```bash
# Create isolated environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install Homebrew dependency (developer machine only — NOT required in bundled .app)
brew install sqlcipher

# Core dependencies
pip install pyrekordbox PySide6

# Bundling
pip install pyinstaller

# Verify pyrekordbox can open a real USB database before writing any GUI code
python -c "import pyrekordbox; print(pyrekordbox.__version__)"
```

---

## Sources

All sources are training-knowledge references — verify currency before use:

- pyrekordbox GitHub: https://github.com/dylanljones/pyrekordbox
- pyrekordbox PyPI: https://pypi.org/project/pyrekordbox/
- PySide6 docs: https://doc.qt.io/qtforpython-6/
- PySide6 PyPI: https://pypi.org/project/PySide6/
- PyInstaller docs: https://pyinstaller.org/en/stable/
- PyInstaller PySide6 guide: https://pyinstaller.org/en/stable/hooks-config.html#pyside6
- rekordcrate (Rust, read-only): https://github.com/Holzhaus/rekordcrate
- SQLCipher: https://www.zetetic.net/sqlcipher/
- pysqlcipher3: https://github.com/rigglemania/pysqlcipher3

**IMPORTANT:** This research was produced without live tool access (WebSearch, WebFetch, and Bash were all denied in the research session). Every version number, current maintenance status, and compatibility claim must be verified against live sources before beginning implementation. The pyrekordbox sqlcipher bundling path in particular carries the most uncertainty and must be spiked early.
