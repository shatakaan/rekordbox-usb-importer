<!-- GSD:project-start source:PROJECT.md -->

## Project

**Rekordbox USB Playlist Importer**

A macOS GUI app for DJs that reads Rekordbox-exported USB sticks and imports the playlists into the local Rekordbox library — without copying the audio files to the hard drive. Tracks remain on the external medium and appear as offline in the library when the USB is not connected. Built to be distributed as a standalone `.app` bundle with no additional installation requirements.

**Core Value:** A DJ can use playlists received on a USB stick directly in their local Rekordbox library, with files staying on the USB, without any manual scrolling or full import with file copy.

### Constraints

- **Platform**: macOS only — DJ workflow is macOS-centric; simplifies distribution
- **Distribution**: Standalone `.app` bundle — no Homebrew, Python, or pip required for end users
- **Safety**: Local Rekordbox DB must be backed up before any write operation — data loss is unacceptable
- **Rekordbox version**: Target 6 and 7 only — v5 uses a different format and has a shrinking user base
- **DB access**: Rekordbox must be closed — concurrent SQLite writes risk corruption
- **No file operations**: Tool never moves, copies, or modifies audio files — read-only for media

<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

## Recommended Stack

### Database Layer

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pyrekordbox | 0.3.x (verify on PyPI) | Read/write Rekordbox 6/7 SQLite DBs | Only purpose-built Python library for Rekordbox DB access; handles the proprietary SQLite encryption Pioneer uses |
| Python `sqlite3` (stdlib) | built-in | Direct fallback queries when pyrekordbox abstraction is insufficient | Zero dependency, always available, sufficient for raw SELECT/INSERT once schema is known |

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

### GUI Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PySide6 | 6.7.x (verify on PyPI) | macOS GUI | Native macOS look with minimal effort; LGPL license (distributable without open-sourcing app); Qt6 is the current generation; works with PyInstaller |

- Qt/PySide6 produces genuinely native-feeling macOS apps with minimal styling effort. The `QApplication` + `QMainWindow` pattern is mature and well-understood.
- For this tool the UI surface is small: a file picker or USB device list, a checkbox list of playlists, an import button, a log/progress area. PySide6 handles this in ~200 lines of straightforward code.
- LGPL license means you can ship a closed or proprietary `.app` without triggering copyleft — PyQt6 (the alternative Qt binding) requires a commercial license for closed-source distribution or GPL compliance.
- PySide6 bundles cleanly with PyInstaller. The `--collect-all PySide6` flag pulls in what's needed.

### Bundling / Distribution

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PyInstaller | 6.x | Bundle Python app as standalone macOS `.app` | Most mature option; best community support for PySide6; produces proper `.app` bundle; handles hooks for native libs |

- PyInstaller is the de-facto standard for Python-to-macOS-app bundling as of 2025. It has explicit hooks for PySide6 and handles Qt plugin discovery automatically.
- Produces a `.app` bundle (with `--windowed` flag) that can be zipped and distributed without any installer.
- For notarization and Gatekeeper compliance you will eventually need to code-sign, but for initial development and internal distribution it works unsigned.
- The sqlcipher / pysqlcipher3 dependency (required by pyrekordbox for encrypted tables) needs a custom PyInstaller hook or `--add-binary` directive to bundle the native `.dylib`. This is the highest-risk bundling issue — plan a spike here.

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pathlib` (stdlib) | built-in | USB path resolution, mount point detection | Always — cleaner than `os.path` for cross-path manipulation |
| `shutil` (stdlib) | built-in | Database backup before write | Always — `shutil.copy2` preserves metadata |
| `subprocess` (stdlib) | built-in | Detect running Rekordbox process | Always — `pgrep rekordbox` or `ps aux` grep |
| `logging` (stdlib) | built-in | Structured log output to GUI log area | Always — wire to a QTextEdit via a logging handler |

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

## What NOT to Use and Why

## Critical Dependency Risk: sqlcipher / pysqlcipher3

- Check whether pyrekordbox 0.3.x+ ships a vendored or statically linked sqlcipher option
- Check whether the `apsw` package (another SQLite Python binding) has SQLCipher support that bundles more cleanly
- Alternatively: open the DB once on a developer machine to extract and cache the decrypted schema, then operate on a copy — but this is fragile and not suitable for a user-facing tool

## Existing Open-Source Tools (Similar Scope)

- **pyrekordbox** itself — the library, not a GUI tool. https://github.com/dylanljones/pyrekordbox
- **rekordcrate** (Rust) — read-only parsing of Rekordbox USB databases, no write capability. https://github.com/Holzhaus/rekordcrate
- **DJ collection exporter** — export tools exist (RB to Serato, RB to Traktor) but they work in the export direction, not import-without-copy
- **DJCU (DJ Conversion Utility)** — commercial macOS app; not open-source; converts between DJ software libraries; not free

## Recommended Python Version

- 3.11 is the most widely tested version with both pyrekordbox and PySide6 as of mid-2025
- 3.12 introduced some changes that affected a small number of PyInstaller hooks; 3.11 is the safer choice until 3.12 compatibility is confirmed in pyrekordbox's CI
- 3.10 minimum is required by PySide6 6.x; 3.9 is end-of-life

## Installation (Development Setup)

# Create isolated environment

# Install Homebrew dependency (developer machine only — NOT required in bundled .app)

# Core dependencies

# Bundling

# Verify pyrekordbox can open a real USB database before writing any GUI code

## Sources

- pyrekordbox GitHub: https://github.com/dylanljones/pyrekordbox
- pyrekordbox PyPI: https://pypi.org/project/pyrekordbox/
- PySide6 docs: https://doc.qt.io/qtforpython-6/
- PySide6 PyPI: https://pypi.org/project/PySide6/
- PyInstaller docs: https://pyinstaller.org/en/stable/
- PyInstaller PySide6 guide: https://pyinstaller.org/en/stable/hooks-config.html#pyside6
- rekordcrate (Rust, read-only): https://github.com/Holzhaus/rekordcrate
- SQLCipher: https://www.zetetic.net/sqlcipher/
- pysqlcipher3: https://github.com/rigglemania/pysqlcipher3

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
