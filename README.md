# Playlist Converter for Rekordbox

Import playlists from a USB stick directly into your local Rekordbox library — without copying the audio files to your hard drive.

> **Beta 2** — tested with Rekordbox 6/7 on macOS 13+. Please report issues.

---

## What it does

You receive a USB stick from another DJ. It has playlists you want to use. Normally you'd manually scroll through hundreds of tracks or do a full import that copies every file to your hard drive.

**Playlist Converter** imports the playlists into your local Rekordbox library in one click. The audio files stay on the USB stick. When the USB is connected, the tracks play normally. When it's disconnected, they show as offline — exactly like any other offline track in Rekordbox.

Everything that matters is preserved:

- ✅ Playlist folder hierarchy
- ✅ Hot cue points and memory cues
- ✅ BPM, musical key, star rating, color tags
- ✅ Tracks already in your library are linked — not duplicated

---

## Requirements

- macOS 13 (Ventura) or later — Apple Silicon (M1/M2/M3) and Intel
- Rekordbox 6 or 7
- USB stick exported from Rekordbox (via **File → Export Mode** on a CDJ or via Rekordbox's export function)

---

## Installation

1. Download `PlaylistConverter-1.0.0.dmg` from the [Releases](https://github.com/shatakaan/rekordbox-usb-importer/releases) page
2. Open the DMG and drag **PlaylistConverter.app** to your Applications folder
3. Double-click the app — macOS blocks it with a warning. Click **Cancel** (not "Move to Trash")
4. Open **System Settings → Privacy & Security**, scroll down, click **"Open Anyway"** next to PlaylistConverter
5. Enter your password if prompted — the app opens

After the first launch, double-click works normally.

**Alternative via Terminal:**

```bash
xattr -cr /Applications/PlaylistConverter.app
```

Then double-click the app.

> The app is not notarized. This is a one-time step — macOS only asks once.

---

## How to use

1. **Close Rekordbox** — the app writes to the Rekordbox database directly; Rekordbox must be closed during import
2. Launch Playlist Converter
3. Connect your Rekordbox USB stick — playlists load automatically in the left panel
4. Check the playlists you want to import
5. Click **Import Selected**
6. Review the summary: green = new track, orange = already in your library (will be linked)
7. Click **Confirm Import**
8. Open Rekordbox — your playlists are there

---

## What happens to duplicate tracks?

If a track is already in your Rekordbox library (matched by file path, or by title + duration), it won't be imported twice. Instead, the existing library entry is added to the new playlist. You get a complete playlist with no duplicates.

---

## Session restore

The app remembers which USB stick and playlists you last used. When you relaunch with the same USB connected, it auto-selects the USB and pre-checks the same playlists.

---

## Known limitations (Beta)

- **Rekordbox 5** is not supported (different database format)
- **DEVICE_LIBRARY_PLUS** format (CDJ-3000 / newer exports with `exportLibrary.db`) falls back to the older `export.pdb` parser if the database is encrypted — this works for most USB sticks
- Chinese, Japanese and Korean characters in track/playlist names may not display correctly on all devices

---

## Safety

Before any write operation, the app:

1. Checks that Rekordbox is not running
2. Creates a timestamped backup of your `master.db` at `~/Library/Pioneer/rekordbox/master.db.backup.YYYYMMDD_HHMMSS`
3. Shows you the backup path before proceeding

If anything goes wrong mid-import, all changes are rolled back automatically.

---

## Tech stack

Built with Python 3.11, PySide6, pyrekordbox, and PyInstaller. macOS only.

---

## Feedback & bugs

Open an issue on [GitHub](https://github.com/shatakaan/rekordbox-usb-importer/issues) with:

- Your macOS version
- Your Rekordbox version
- The log output from the app (copy from the log panel at the bottom)
