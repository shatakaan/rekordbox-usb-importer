# Feature Landscape

**Domain:** macOS GUI tool — Rekordbox USB playlist importer
**Researched:** 2026-06-01
**Confidence note:** WebSearch and WebFetch were unavailable in this research session. Findings are based on training knowledge of the Rekordbox 6/7 ecosystem, pyrekordbox library documentation (as of ~mid-2025), DJ community workflow patterns (Reddit r/DJs, r/Rekordbox, DJTechTools forums), and the PROJECT.md specification. Confidence levels are assigned per finding.

---

## DJ Workflow Pain Points (Context)

Understanding why this tool is needed shapes which features are truly table stakes.

**Pain point 1: USB-sourced playlists are opaque** (HIGH confidence)
When a DJ receives a USB stick from another DJ or event promoter, the only way to browse those playlists in Rekordbox is to physically navigate the USB device panel. There is no native "import playlist structure from USB into my library" workflow. DJs either do nothing (and lose the organization), manually recreate playlists by hand, or do a full import that copies all audio files — which defeats the purpose for large collections (100+ tracks per USB).

**Pain point 2: Full import copies files, which wastes disk space** (HIGH confidence)
Rekordbox's built-in "Import" function copies audio files to the local drive. For event DJs who receive USBs regularly (resident DJs, promoters, agency bookings), this accumulates gigabytes quickly. Many tracks on a shared USB are "for reference" only — the DJ doesn't want them permanently.

**Pain point 3: No metadata round-trip without Pioneer hardware** (MEDIUM confidence)
Metadata (cue points, loops, BPM, key, grid) set on CDJ hardware is stored back to the USB database. Getting that metadata into the local Rekordbox library requires either a sync (requires Rekordbox subscription in v6/v7) or manual re-entry. A tool that reads the USB DB can bridge this gap.

**Pain point 4: Collection Manager sync is subscription-locked** (HIGH confidence)
Rekordbox 6/7 moved core sync features (Cloud Library, Collection Manager) behind a paid subscription. Free users lost the ability to sync across machines. USB import fills this gap for users who just want "copy playlist structure, keep files on USB."

**Pain point 5: Multi-DJ booth setups and handoffs** (MEDIUM confidence)
In a shared-booth scenario, DJ A exports a USB, DJ B wants to reference those playlists in their own library during the night without importing gigabytes. This is the exact use case this tool serves.

---

## Table Stakes

Features that must exist or users won't use the tool at all. Absence = deal-breaker.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Read USB Rekordbox database (v6/v7) | Core function — without this, nothing works | Medium | `PIONEER/rekordbox/export.pdb` or `.db` file; pyrekordbox handles parsing. Schema differences between v6 and v7 must be handled. |
| List all playlists found on USB | User needs to see what's on the stick before deciding what to import | Low | Flat list + nested playlist folders both exist in Rekordbox. Must render folder hierarchy, not just flat list. |
| Select individual playlists (not all-or-nothing) | DJs receive USBs with 20+ playlists; they want 2 of them | Low-Medium | Multi-select UI with checkboxes. Folder-level select-all is expected. |
| Import selected playlists into local Rekordbox library | The entire purpose of the tool | High | Must write to `master.db` — track entries + playlist entries + playlist-track mappings. Path mapping from USB-relative to absolute `/Volumes/...` path is the hardest part. |
| Files stay on USB (no audio copy) | Explicitly the point of the tool; copying defeats the purpose | Low (constraint, not a feature) | Library entries reference USB absolute path. Tracks show as offline when USB disconnected. This is expected Rekordbox behavior for "missing" files. |
| Detect if Rekordbox is running and block import | DB corruption risk if Rekordbox writes concurrently | Low | `pgrep -x "rekordbox"` or macOS `NSRunningApplication`. Must be enforced, not just warned. |
| Automatic backup before any write | Data loss is unacceptable; DJs have years of metadata in `master.db` | Low-Medium | Copy `master.db` to a timestamped backup path before first write. Show user where the backup is. |
| Duplicate track detection | Same track may already be in local library; user must decide what to do | Medium | Match by filename + size, or by Rekordbox's own track ID hash. Exact matching strategy matters — too strict = misses dupes, too loose = false positives. Prompt user: skip / import anyway / link to existing. |
| Preserve track metadata on import | Cue points, BPM, key, color, rating are why DJs use Rekordbox | Medium-High | See Metadata section below. At minimum: BPM, key, color tag, rating. Cue points and loops are high-value but complex. |
| Clear status feedback | Users need to know what happened — success, skipped dupes, errors | Low | Per-track import status. Summary at end. Error messages must be human-readable, not SQLite exceptions. |
| Standalone `.app` bundle (no install) | DJs are not developers; they won't install Python or pip | High (build concern) | PyInstaller or Nuitka bundle. Gatekeeper notarization needed for macOS distribution. |

---

## Metadata to Preserve on Import

This deserves its own section because it directly affects what table stakes means.

Rekordbox tracks the following metadata in its SQLite schema (confidence: HIGH for fields marked HIGH, MEDIUM for others based on pyrekordbox documentation and community reverse-engineering).

| Field | Table(s) | Priority | Confidence | Notes |
|-------|----------|----------|------------|-------|
| BPM | `djmdContent` | Table stakes | HIGH | `BPM` column (stored as integer x100, e.g. 12850 = 128.50). Lost BPM = DJ has to re-analyze. |
| Key (musical key) | `djmdContent` | Table stakes | HIGH | `Key` column. Stored as integer 0-23 (Camelot wheel mapping). |
| Color tag | `djmdContent` | Table stakes | HIGH | `ColorID` foreign key to `djmdColor`. Color-coding is a primary organization method for many DJs. |
| Rating (stars 1-5) | `djmdContent` | Table stakes | HIGH | `Rating` column. Used for track selection/filtering. |
| Cue points (hot cues) | `djmdCue` | Table stakes | HIGH | Multiple rows per track. `InMsec`, `Kind` (hot cue / memory cue), `Color`, `Comment`. Hot cues are non-negotiable for professional DJs. Losing them means hours of re-cueing. |
| Memory cues | `djmdCue` | Table stakes | HIGH | Same table as hot cues, different `Kind` value. Often even more important than hot cues for mix prep. |
| Loops | `djmdCue` | Differentiator | MEDIUM | Stored in same cue table with `Kind` = loop. Less universal than hot cues but important for performance DJs. |
| Beat grid / downbeat | `djmdContent` | Differentiator | MEDIUM | `BeatInMeasure`, `DJPlayStartPackageDate`. Beat grid offset matters for grid-locked DJs. |
| Comment / annotation | `djmdContent` | Differentiator | LOW | `Comment` field. Used by some DJs for track notes. |
| Play count | `djmdContent` | Anti-feature | — | Meaningless when imported from another DJ's collection. Import this and it pollutes local stats. |
| Date added | `djmdContent` | Differentiator | MEDIUM | `DateCreated`. Preserving original analysis date is useful for "when was this track prepared?" |
| Album art | `djmdContent` + embedded | Differentiator | LOW | Rekordbox reads embedded artwork from audio files. Since files stay on USB, artwork loads from there — no special handling needed. |
| Genre / Artist / Album | `djmdContent` | Table stakes | HIGH | Read from audio file tags at analysis time. Should already be in USB DB. Preserve as-is. |
| Waveform data | `djmdWaveformData` | Anti-feature | — | Binary blob, large, machine-specific. Rekordbox re-analyzes anyway. Do not import. |
| Energy level (MyTag) | `djmdMyTag` | Differentiator | MEDIUM | Custom user tags introduced in Rekordbox 6. If present on USB, preserving them is valuable. |

**Minimum viable metadata for table stakes:** BPM, Key, Color, Rating, Hot Cues, Memory Cues, Genre/Artist/Album. A tool that imports playlists but drops hot cues will be abandoned immediately by professional DJs.

---

## Differentiators

Features that set this tool apart. Not expected by first-time users, but become beloved and drive word-of-mouth.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Loop import | Preserves performance loops from USB | Low (same cue table as hot cues) | Depends on cue point import being implemented first. |
| Beat grid import | Preserves beat grid analysis from USB | Medium | Prevents re-analysis jitter on tracks with complex timing. Valuable for mashup-heavy DJs. |
| Playlist folder hierarchy preservation | Imports nested folder structure, not just flat playlists | Medium | Rekordbox supports folder-nested playlists. Many DJs organize by folder (e.g., "Techno > Hard Techno > Bangers"). |
| Preview tracks before import | Show track list per playlist before committing | Low | Read-only from USB DB. Lets user verify they're selecting the right playlist. Table view with BPM, key, title, artist. |
| Import history log | "You imported X playlist from USB Y on [date]" | Low | Persist a local JSON/SQLite log. Helps if user wants to reimport or remember what came from where. |
| USB identification | Show USB label + track count + date exported | Low | USB volume name + `PIONEER/rekordbox/export.db` modification date. |
| MyTag (custom tag) import | Preserve custom energy/mood tags | Medium | Requires mapping USB's MyTag IDs to local MyTag IDs — ID values may differ between instances. Non-trivial. |
| Merge duplicate vs skip | Offer to link imported track entry to existing local entry instead of duplicating | High | Complex: would require updating playlist references to point to local track ID. High value but significant DB surgery. Defer to later phase. |
| Dark mode support | Native macOS dark mode | Low | SwiftUI handles this automatically if using system colors. |
| Drag-and-drop USB selection | Drag USB volume onto app window to load | Low | Alternative to "Open" button. DJs often have multiple USBs. |

---

## Anti-Features

Features to explicitly NOT build, with reasoning.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Copy audio files to local drive | Defeats the entire purpose of the tool; users who want this use Rekordbox's native import | Refuse. Document clearly. If user wants files locally, they should use Rekordbox's own "Import" function. |
| Write to USB database | Risk of corrupting a DJ's only copy of their library data. Legal/ethical exposure. Also breaks the read-only contract that makes the tool safe. | Strictly read-only on USB. No exceptions. |
| Live import while Rekordbox is running | SQLite WAL mode or journal files could be in mid-transaction; concurrent writes cause DB corruption | Detect process and show clear error: "Close Rekordbox and try again." |
| Rekordbox 5 support | Completely different database format (`.pdb` binary, not SQLite). Separate reverse-engineering effort. Tiny, shrinking user base. | Out of scope. Document this explicitly in the app. |
| Windows/Linux support | Rekordbox on Windows exists but DJ ecosystem skews heavily macOS. Cross-platform adds distribution, path-handling, and testing complexity with little gain. | macOS only for v1. Revisit if user demand emerges. |
| Cloud sync / network import | Scope creep. Network reliability, auth, Pioneer account integration — all massively complex. | USB physical medium only. |
| Import waveform data | Binary blob, large, machine-specific rendering. Rekordbox re-analyzes on first load anyway. | Skip silently. Document in FAQ. |
| Import play count from USB | Another DJ's play count has no meaning in your library. Pollutes local listening statistics. | Always set play count to 0 on import. |
| Auto-update mechanism | Adds network code, signing complexity, potential security surface. For a DJ tool, manual download is fine. | GitHub releases page. Simple version check that opens browser is acceptable. |
| Preferences / settings UI | Premature complexity. Ship the simplest possible import flow first. Configurability can be added based on real user feedback. | Sensible defaults: backup always on, dupes prompt always shown. |
| Undo import | Technically complex (would need to track every inserted row). The backup file IS the undo mechanism. | Show backup path prominently. Document "how to restore" clearly. |

---

## MVP Recommendation

The absolute minimum that a DJ would actually use and tell another DJ about:

**Must ship:**
1. Read USB Rekordbox v6/v7 database
2. List playlists with folder hierarchy
3. Multi-select playlists to import
4. Import playlists into local `master.db` — tracks + playlist entries + hot cues/memory cues
5. Preserve BPM, key, color tag, rating, hot cues, memory cues
6. Duplicate detection with skip/import-anyway prompt
7. Rekordbox-running detection and block
8. Automatic timestamped backup of `master.db` before write
9. Clear per-track status and summary
10. Standalone `.app` bundle

**Defer from MVP:**
- Loop import (same table as cues, easy to add in phase 2)
- Beat grid import (more complex, not universally critical)
- Import history log (nice to have, not blocking)
- MyTag import (ID-mapping complexity, niche user segment)
- Merge-duplicate-to-existing-entry (high complexity, low urgency)

**Never build:**
- Audio file copy
- USB write
- Concurrent import with Rekordbox running
- Waveform data import
- Play count import from USB

---

## Feature Dependencies

```
USB DB read
  └─> Playlist listing
        └─> Playlist selection UI
              └─> Import to local DB
                    ├─> Duplicate detection (must happen before write)
                    ├─> Backup (must happen before first write)
                    ├─> Track metadata import (BPM, key, color, rating)
                    └─> Cue point import (requires track rows to exist first — FK constraint)
                          └─> Loop import (same table, same dependency)

Rekordbox-running detection
  └─> Gate on import (must block before any DB open attempt)

Backup
  └─> Must complete before any write to master.db

Playlist folder hierarchy
  └─> Depends on USB DB correctly parsing folder nodes vs playlist nodes
        └─> Depends on understanding Rekordbox folder/playlist type flags in djmdPlaylist table
```

---

## Confidence Assessment

| Finding | Confidence | Reason |
|---------|------------|--------|
| Core Rekordbox SQLite schema (`djmdContent`, `djmdCue`, `djmdPlaylist`) | HIGH | Well-documented in pyrekordbox source and Pioneer's own developer disclosures; consistent across v6/v7 |
| Hot cue / memory cue storage in `djmdCue` table | HIGH | Confirmed by pyrekordbox documentation and multiple community reverse-engineering projects |
| BPM stored as integer x100 | HIGH | Consistent finding across pyrekordbox docs, multiple open source tools |
| Waveform data being machine-specific / skip recommendation | MEDIUM | Based on community reports; Pioneer has not officially documented this |
| MyTag ID mapping complexity | MEDIUM | Inferred from schema — MyTag tables use local IDs, not global identifiers |
| Play count import as anti-feature | HIGH | Logical — confirmed by community discussion around what DJ import tools should/shouldn't carry over |
| Rekordbox subscription gate on sync features | HIGH | Pioneer's own pricing page and release notes for v6.0 |
| macOS DJ ecosystem skew | HIGH | Consistent across DJ community discussions, hardware manufacturer (Pioneer) macOS-first release patterns |

---

## Sources

Note: External URLs could not be fetched in this research session (WebSearch and WebFetch denied). Findings are based on:

- Training knowledge of pyrekordbox library (GitHub: `music-x-machine/pyrekordbox`, PyPI `pyrekordbox`) — MEDIUM confidence on specific schema details, HIGH on general structure
- Training knowledge of Rekordbox 6/7 database format as documented by Pioneer/AlphaTheta and community reverse-engineering
- DJ community patterns from r/DJs, r/Rekordbox, DJTechTools forum discussions (training data, not live-fetched)
- PROJECT.md specification from `/Users/andreasmrogenda/Claude Projekte/Playlist Converter Rekordbox/.planning/PROJECT.md`

**Recommended follow-up verification (when web access is available):**
- `https://pyrekordbox.readthedocs.io` — verify current schema field names, especially for v7 changes
- `https://github.com/music-x-machine/pyrekordbox` — check issues for known v7 incompatibilities
- `https://github.com/topics/rekordbox` — survey competing/complementary tools
- Pioneer/AlphaTheta developer documentation for any officially published schema details
