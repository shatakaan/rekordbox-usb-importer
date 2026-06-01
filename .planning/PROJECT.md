# Rekordbox USB Playlist Importer

## What This Is

A macOS GUI app for DJs that reads Rekordbox-exported USB sticks and imports the playlists into the local Rekordbox library — without copying the audio files to the hard drive. Tracks remain on the external medium and appear as offline in the library when the USB is not connected. Built to be distributed as a standalone `.app` bundle with no additional installation requirements.

## Core Value

A DJ can use playlists received on a USB stick directly in their local Rekordbox library, with files staying on the USB, without any manual scrolling or full import with file copy.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Read Rekordbox-exported USB database (Rekordbox 6 and 7 format)
- [ ] List all playlists found on the USB stick for user selection
- [ ] Import selected playlists into the local Rekordbox library
- [ ] Audio files stay on USB — library entries reference the USB path, not a local copy
- [ ] Tracks appear as "offline" in Rekordbox when USB is not connected
- [ ] Detect duplicate tracks (same file already in local library) and prompt user
- [ ] Warn user and block import if Rekordbox is currently running
- [ ] Distribute as standalone macOS `.app` bundle (no Python/dependencies to install)
- [ ] Automatic backup of local Rekordbox database before any modification

### Out of Scope

- Copying audio files to local hard drive — the whole point is to avoid this
- Syncing metadata, cue points, or loops back to the USB
- Modifying the USB stick's database in any way
- Windows or Linux support — macOS only for now
- Live import while Rekordbox is running — too risky for DB integrity
- Rekordbox 5 support — v6/v7 database format only

## Context

Rekordbox 6/7 stores its local library as a SQLite database at `~/Library/Pioneer/rekordbox/master.db` (exact filename may vary by version). When a USB stick is exported from Rekordbox, it creates a `PIONEER/` folder containing a similar SQLite database with track metadata and playlist structure.

The core technical challenge is path mapping: tracks on the USB are stored with relative paths (e.g., `Contents/Tracks/Artist/Song.mp3`), which must be mapped to absolute macOS paths at the USB mount point (e.g., `/Volumes/DJUSB/Contents/Tracks/Artist/Song.mp3`). The mount point name varies per USB stick and per machine, so the tool must resolve this at import time.

The Python library `pyrekordbox` exists on GitHub and supports reading/writing Rekordbox 6 databases — a key candidate for the implementation layer. Bundling Python via PyInstaller or similar would allow distribution as a self-contained `.app`.

Rekordbox must be closed during import to avoid database locking and potential corruption. The tool will detect the running process and block if necessary. A pre-import database backup is required as a safety net.

## Constraints

- **Platform**: macOS only — DJ workflow is macOS-centric; simplifies distribution
- **Distribution**: Standalone `.app` bundle — no Homebrew, Python, or pip required for end users
- **Safety**: Local Rekordbox DB must be backed up before any write operation — data loss is unacceptable
- **Rekordbox version**: Target 6 and 7 only — v5 uses a different format and has a shrinking user base
- **DB access**: Rekordbox must be closed — concurrent SQLite writes risk corruption
- **No file operations**: Tool never moves, copies, or modifies audio files — read-only for media

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| macOS only | DJ ecosystem skews macOS; reduces scope and complexity | — Pending |
| Rekordbox 6/7 only | Active user base; consistent DB format; v5 is end-of-life | — Pending |
| Files stay on USB | Core feature requirement — this is why the tool exists | — Pending |
| Standalone .app bundle | DJs shouldn't need to install developer tooling | — Pending |

---

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-01 after initialization*
