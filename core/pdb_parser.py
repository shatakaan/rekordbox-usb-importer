"""
Pure stdlib Pioneer DeviceSQL PDB Parser.

Liest das export.pdb-Binärformat von Rekordbox-exportierten USB-Sticks.
Alle Strukturen und Implementierungen basieren auf live-verifizierten
Ergebnissen aus 01-PDB-RESEARCH.md (2026-06-02).

Sicherheitshinweise:
  - T-05-01: Alle struct.unpack_from-Aufrufe sind in try/except struct.error
    gewrappt und werfen PdbParseError
  - T-05-02: Maximale Dateigrösse 50 MB; max 10'000 Tracks/Playlists
  - Keine externen Dependencies — reine Python-stdlib

Exports:
  parse_export_pdb(path: Path) -> tuple[list[PlaylistRow], dict[int, TrackRow]]
  PdbParseError
"""

import logging
import struct
from collections import defaultdict
from pathlib import Path
from typing import Generator

from core.usb_db import PlaylistRow, SongEntry, TrackRow

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Konstanten (direkt aus 01-PDB-RESEARCH.md Abschnitt 8)
# ---------------------------------------------------------------------------

PAGE_SIZE = 4096
HEADER_END = 32          # Bytes im Seiten-Header

TABLE_TRACKS = 0
TABLE_ARTISTS = 2
TABLE_ALBUMS = 3         # Optional — TODO für spätere Phase
TABLE_PLAYLIST_TREE = 7
TABLE_PLAYLIST_ENTRIES = 8

TABLE_START_OFF = 0x1C   # Pitfall 3: NICHT 0x14; Stride 16 NICHT 12

MAX_FILE_SIZE = 50 * 1024 * 1024   # 50 MB — T-05-02
MAX_ENTRIES = 10_000               # T-05-02


# ---------------------------------------------------------------------------
# Fehlerklasse
# ---------------------------------------------------------------------------

class PdbParseError(Exception):
    """Wird geworfen bei ungültigem Header, Datei nicht gefunden,
    Dateigrösse > 50 MB oder struct.error beim Parsing."""


# ---------------------------------------------------------------------------
# Hilfsfunktionen (Implementierungen aus 01-PDB-RESEARCH.md)
# ---------------------------------------------------------------------------

def parse_page_header(page_data: bytes) -> dict:
    """Liest den 32-Byte-Seiten-Header und gibt relevante Felder zurück.

    Pitfall 1+2: is_data = (page_flags & 0x40) == 0 — Bit-6-Maske,
    NICHT Byte-Gleichheit mit 0x24.

    Args:
        page_data: 4096-Byte-Seiten-Daten.

    Returns:
        dict mit page_idx, type, next_pg, num_row_offsets, page_flags, is_data.
    """
    page_idx = struct.unpack_from("<I", page_data, 4)[0]
    ptype    = struct.unpack_from("<I", page_data, 8)[0]
    next_pg  = struct.unpack_from("<I", page_data, 12)[0]
    b0, b1, b2 = page_data[24], page_data[25], page_data[26]
    num_row_offsets = (b0 | (b1 << 8)) & 0x1FFF
    page_flags = page_data[27]
    is_data = (page_flags & 0x40) == 0   # Pitfall 1+2: Bit-6-Maske
    return {
        "page_idx": page_idx,
        "type": ptype,
        "next_pg": next_pg,
        "num_row_offsets": num_row_offsets,
        "page_flags": page_flags,
        "is_data": is_data,
    }


def get_row_positions(page_data: bytes, num_row_offsets: int) -> list[tuple[int, bool]]:
    """Gibt Liste von (abs_row_start, is_present) für alle Zeilen einer Seite zurück.

    Pitfall 4: Offsets kommen ZUERST (pos + slot*2), rpf steht NACH den
    Offsets (pos + n_in_group*2). Reihenfolge: [offset_0][offset_1]...[rpf][txf]

    Args:
        page_data: 4096-Byte-Seiten-Daten.
        num_row_offsets: Anzahl allozierter Slots (aus Seiten-Header).

    Returns:
        Liste von (abs_start, is_present) Tuples.
    """
    rows = []
    n_remaining = num_row_offsets
    pos = PAGE_SIZE  # von hinten nach vorne

    while n_remaining > 0:
        n_in_group = min(16, n_remaining)
        # Gruppe: n_in_group × u16 Offsets + u16 rpf + u16 txf
        group_size = n_in_group * 2 + 4
        pos -= group_size

        # rpf steht NACH den Offsets (Pitfall 4)
        rpf = struct.unpack_from("<H", page_data, pos + n_in_group * 2)[0]

        for slot in range(n_in_group):
            raw_off = struct.unpack_from("<H", page_data, pos + slot * 2)[0]
            # raw_off ist relativ zu HEADER_END (32)
            abs_start = HEADER_END + raw_off
            present = bool(rpf & (1 << slot))
            rows.append((abs_start, present))

        n_remaining -= n_in_group

    return rows


def decode_devicesql_string(data: bytes, pos: int) -> tuple[str, int]:
    """Liest einen DeviceSQL-String ab Position pos.

    Unterstützte Kodierungen:
      flag & 0x01 -> Short ASCII (Pitfall 5: Null-Terminator nicht kopieren)
      flag == 0x40 -> Long ASCII  (3-Byte-Header: flag + u16 length, Pitfall 11)
      flag == 0x90 -> Long UTF-16LE
      flag == 0x00 -> Null-String (kein Name)

    Args:
        data: Byte-Puffer (typischerweise Seiten-Daten).
        pos: Absoluter Byte-Offset im Puffer.

    Returns:
        (text, consumed_bytes) Tuple.
    """
    if pos >= len(data):
        return ("", 0)

    flag = data[pos]

    if flag & 0x01:
        # Kurzes ASCII: Länge = flag >> 1, INKL. Null-Terminator
        # => tatsächliche Textlänge = (flag >> 1) - 1 (wenn > 0)  — Pitfall 5
        raw_len = flag >> 1
        if raw_len == 0:
            return ("", 1)
        actual_len = raw_len - 1
        text = data[pos + 1: pos + 1 + actual_len].decode("ascii", errors="replace")
        return (text, 1 + raw_len)

    elif flag == 0x40:
        # Langes ASCII: flag(1) + length(u16-LE, 2) + text(length Bytes) — Pitfall 11
        if pos + 3 > len(data):
            return ("", 1)
        str_len = struct.unpack_from("<H", data, pos + 1)[0]
        text = data[pos + 3: pos + 3 + str_len].decode("ascii", errors="replace").rstrip("\x00")
        return (text, 3 + str_len)

    elif flag == 0x90:
        # Langes UTF-16LE: flag(1) + length(u16-LE, 2) + text(length Bytes) — Pitfall 11
        if pos + 3 > len(data):
            return ("", 1)
        str_len = struct.unpack_from("<H", data, pos + 1)[0]
        text = data[pos + 3: pos + 3 + str_len].decode("utf-16-le", errors="replace").rstrip("\x00")
        return (text, 3 + str_len)

    elif flag == 0x00:
        # Null-String (kein Name, z.B. Root-Ordner)
        return ("", 1)

    else:
        # Unbekannte Kodierung — defensiv behandeln
        return (f"<unknown-flag-0x{flag:02x}>", 1)


# ---------------------------------------------------------------------------
# Zeilen-Parser (Implementierungen aus 01-PDB-RESEARCH.md Abschnitt 6)
# ---------------------------------------------------------------------------

TRACK_CONTENT_OFFSET = 8  # 8-Byte-Präfix bei Track-Zeilen — Pitfall 7


def parse_track_row(page_data: bytes, rs: int) -> dict:
    """Parse eine Track-Zeile und gibt ein dict mit Metadaten zurück.

    Pitfall 7: 8-Byte-Präfix — rbase = rs + 8.
    Pitfall 6: String-Offsets sind relativ zu rbase, NICHT rs.

    Args:
        page_data: 4096-Byte-Seiten-Daten.
        rs: Absoluter Zeilenanfang in der Seite.

    Returns:
        dict mit id, title, artist_id, album_id, bpm, duration, rating, file_path.
    """
    rbase = rs + TRACK_CONTENT_OFFSET  # Pitfall 7: 8-Byte-Präfix
    tempo    = struct.unpack_from("<I", page_data, rbase + 0x38)[0]
    album_id = struct.unpack_from("<I", page_data, rbase + 0x40)[0]
    artist_id = struct.unpack_from("<I", page_data, rbase + 0x44)[0]
    track_id = struct.unpack_from("<I", page_data, rbase + 0x48)[0]
    duration = struct.unpack_from("<H", page_data, rbase + 0x54)[0]
    rating   = page_data[rbase + 0x59]

    # String-Offsets: 21 × u16 ab rbase+0x5E (Pitfall 6: relativ zu rbase)
    # Bounds: str_offs has indices 0..20; 0 means "not set" -> decode_devicesql_string returns ""
    str_offs = list(struct.unpack_from("<21H", page_data, rbase + 0x5E))
    title, _        = decode_devicesql_string(page_data, rbase + str_offs[17])
    filepath, _     = decode_devicesql_string(page_data, rbase + str_offs[20])
    analyze_raw, _  = decode_devicesql_string(page_data, rbase + str_offs[14])  # T-02-01-01: str_offs[14]

    return {
        "id":           track_id,
        "title":        title,
        "artist_id":    artist_id,
        "album_id":     album_id,
        "bpm":          tempo / 100.0,
        "duration":     duration,
        "rating":       rating,
        "file_path":    filepath,
        "analyze_path": analyze_raw or None,  # empty string -> None (T-02-01-01)
    }


def parse_playlist_tree_row(page_data: bytes, rs: int) -> dict:
    """Parse eine PlaylistTree-Zeile.

    Pitfall 7: KEIN 8-Byte-Präfix. Felder beginnen direkt bei rs.
    Pitfall 10: Root-Ordner haben parent_id == 0 und raw_is_folder == 1.

    Args:
        page_data: Seiten-Daten (mind. rs + 28 Bytes lang).
        rs: Absoluter Zeilenanfang.

    Returns:
        dict mit id, parent_id, sort_order, is_folder, name.
    """
    id_, unk1, sort_ord, parent_id, unk2, raw_is_folder, unk3 = struct.unpack_from(
        "<IIIIIII", page_data, rs
    )
    name, _ = decode_devicesql_string(page_data, rs + 28)
    return {
        "id":         id_,
        "parent_id":  parent_id,
        "sort_order": sort_ord,
        "is_folder":  raw_is_folder != 0,  # Pitfall 10: != 0, nicht == 1
        "name":       name,
    }


def parse_playlist_entry_row(page_data: bytes, rs: int) -> dict:
    """Parse eine PlaylistEntry-Zeile.

    Pitfall 7: KEIN 8-Byte-Präfix. Exakt 3 × u32.

    Args:
        page_data: Seiten-Daten.
        rs: Absoluter Zeilenanfang.

    Returns:
        dict mit entry_index, track_id, playlist_id.
    """
    # Field order confirmed via live USB analysis:
    # (entry_index, playlist_id, track_id) — NOT (entry_index, track_id, playlist_id).
    # The Kaitai KSY schema lists track_id before playlist_id, but live binary
    # analysis of this USB shows field 2 is always 1 (the only PlaylistTree node)
    # when parsed as playlist_id, and field 3 maps to real track IDs 2-17.
    entry_index, playlist_id, track_id = struct.unpack_from("<III", page_data, rs)
    return {
        "entry_index": entry_index,
        "track_id":    track_id,
        "playlist_id": playlist_id,
    }


def parse_artist_row(page_data: bytes, rs: int) -> dict:
    """Parse eine Artist-Zeile.

    Pitfall 7: 8-Byte-Präfix — rbase = rs + 8.
    Near/Far-Offset abhängig von subtype & 0x04.

    Args:
        page_data: Seiten-Daten.
        rs: Absoluter Zeilenanfang.

    Returns:
        dict mit id, name.
    """
    rbase = rs + 8  # Pitfall 7: 8-Byte-Präfix
    subtype   = struct.unpack_from("<H", page_data, rbase)[0]
    artist_id = struct.unpack_from("<I", page_data, rbase + 4)[0]
    if subtype & 0x04:  # Far-Offset: 2 Bytes
        ofs_name = struct.unpack_from("<H", page_data, rbase + 10)[0]
    else:               # Near-Offset: 1 Byte
        ofs_name = page_data[rbase + 9]
    name, _ = decode_devicesql_string(page_data, rbase + ofs_name)
    return {"id": artist_id, "name": name}


# ---------------------------------------------------------------------------
# Seiten-Traversal-Generator (aus 01-PDB-RESEARCH.md Abschnitt 7)
# ---------------------------------------------------------------------------

def iter_table_rows(
    file_data: bytes, table_type_id: int, page_size: int = PAGE_SIZE
) -> Generator[tuple[bytes, int], None, None]:
    """Generator: liefert (page_data, row_abs_offset) für alle vorhandenen
    Zeilen einer Tabelle — traversiert die Seitenkette.

    Pitfall 3: ToC beginnt bei TABLE_START_OFF = 0x1C, Stride = 16.
    Pitfall 8: Chain per next_pg == 0 oder Visited-Set terminieren.
    Pitfall 1: is_data-Gate vor jedem Zeilen-Parse.

    Args:
        file_data: Vollständige PDB-Datei als bytes.
        table_type_id: Tabellen-Typ-ID (z.B. TABLE_TRACKS = 0).
        page_size: Seitengrösse (Standard: 4096).

    Yields:
        (page_data, rs) Tuples — page_data ist 4096-Byte-Seite, rs ist der
        absolute Zeilenanfang innerhalb der Seite.
    """
    num_tables = struct.unpack_from("<I", file_data, 8)[0]
    first_page = None
    for i in range(num_tables):
        off = TABLE_START_OFF + i * 16  # Pitfall 3: Stride 16, Start 0x1C
        ttype, _, fp, _lp = struct.unpack_from("<IIII", file_data, off)
        if ttype == table_type_id:
            first_page = fp
            break
    if first_page is None:
        return

    pg_num = first_page
    visited: set[int] = set()

    while pg_num not in visited and pg_num != 0:
        visited.add(pg_num)
        page_data = file_data[pg_num * page_size: (pg_num + 1) * page_size]
        if len(page_data) < page_size:
            break

        header = parse_page_header(page_data)

        if header["is_data"] and header["num_row_offsets"] > 0:  # Pitfall 1
            rows = get_row_positions(page_data, header["num_row_offsets"])
            for rs, present in rows:
                if present:
                    yield page_data, rs

        next_pg = header["next_pg"]
        if next_pg == 0 or next_pg == 0xFFFFFFFF:  # Pitfall 8
            break
        pg_num = next_pg


# ---------------------------------------------------------------------------
# Haupt-Export-Funktion
# ---------------------------------------------------------------------------

def parse_export_pdb(path: Path) -> tuple[list[PlaylistRow], dict[int, TrackRow]]:
    """Parse eine Pioneer DeviceSQL export.pdb-Datei.

    Liest Tracks, Artists, PlaylistTree und PlaylistEntries und baut daraus
    PlaylistRow- und TrackRow-Objekte mit vollständig verknüpftem Baum auf.

    Sicherheitsgates (T-05-01, T-05-02):
      - Datei muss existieren
      - Dateigrösse <= 50 MB
      - Gültiger Pioneer-PDB-Header (_zero == 0, page_size == 4096, num_tables > 0)

    Args:
        path: Pfad zur export.pdb-Datei.

    Returns:
        (root_playlists, tracks) Tuple:
          - root_playlists: Sortierte Liste von PlaylistRow-Objekten (parent_id == 0)
          - tracks: dict[int, TrackRow] mit track_id als Schlüssel

    Raises:
        PdbParseError: Bei ungültigem Header, fehlender Datei, Dateigrösse > 50 MB
            oder struct.error beim Parsing.
    """
    # --- Gate 1: Datei muss existieren (T-05-01) ---
    if not path.exists():
        raise PdbParseError(f"PDB file not found: {path}")

    # --- Gate 2: Dateigrösse prüfen (T-05-02) ---
    file_size = path.stat().st_size
    if file_size == 0:
        raise PdbParseError(f"PDB file is empty: {path}")
    if file_size > MAX_FILE_SIZE:
        raise PdbParseError(
            f"PDB file too large: {file_size} bytes (max {MAX_FILE_SIZE})"
        )

    try:
        data = path.read_bytes()
    except OSError as exc:
        raise PdbParseError(f"Cannot read PDB file {path}: {exc}") from exc

    # --- Gate 3: Header validieren (T-05-01) ---
    if len(data) < 28:
        raise PdbParseError(f"PDB file too short ({len(data)} bytes): {path}")

    try:
        _zero    = struct.unpack_from("<I", data, 0)[0]
        page_size = struct.unpack_from("<I", data, 4)[0]
        num_tables = struct.unpack_from("<I", data, 8)[0]
    except struct.error as exc:
        raise PdbParseError(f"Cannot read PDB header: {exc}") from exc

    if _zero != 0 or page_size != 4096 or num_tables == 0:
        raise PdbParseError(
            f"Not a valid Pioneer PDB file: "
            f"_zero={_zero}, page_size={page_size}, num_tables={num_tables}"
        )

    # --- 1. Artists lesen ---
    artists: dict[int, str] = {}
    try:
        for page_data, rs in iter_table_rows(data, TABLE_ARTISTS):
            try:
                a = parse_artist_row(page_data, rs)
                if a["id"]:
                    artists[a["id"]] = a["name"]
            except struct.error as exc:
                logger.debug("Skipping artist row at rs=%d: %s", rs, exc)
    except struct.error as exc:
        raise PdbParseError(f"Error parsing Artists table: {exc}") from exc

    # --- 2. Tracks lesen ---
    raw_tracks: dict[int, dict] = {}
    try:
        for page_data, rs in iter_table_rows(data, TABLE_TRACKS):
            try:
                t = parse_track_row(page_data, rs)
                if t["id"]:
                    raw_tracks[t["id"]] = t
                    if len(raw_tracks) > MAX_ENTRIES:  # T-05-02
                        raise PdbParseError(
                            f"Too many tracks (>{MAX_ENTRIES}) — possible corrupt file"
                        )
            except struct.error as exc:
                logger.debug("Skipping track row at rs=%d: %s", rs, exc)
    except PdbParseError:
        raise
    except struct.error as exc:
        raise PdbParseError(f"Error parsing Tracks table: {exc}") from exc

    # --- 3. PlaylistTree lesen ---
    playlist_nodes: dict[int, dict] = {}
    try:
        for page_data, rs in iter_table_rows(data, TABLE_PLAYLIST_TREE):
            try:
                p = parse_playlist_tree_row(page_data, rs)
                if p["id"]:
                    playlist_nodes[p["id"]] = p
                    if len(playlist_nodes) > MAX_ENTRIES:  # T-05-02
                        raise PdbParseError(
                            f"Too many playlist nodes (>{MAX_ENTRIES}) — possible corrupt file"
                        )
            except struct.error as exc:
                logger.debug("Skipping playlist tree row at rs=%d: %s", rs, exc)
    except PdbParseError:
        raise
    except struct.error as exc:
        raise PdbParseError(f"Error parsing PlaylistTree table: {exc}") from exc

    # --- 4. PlaylistEntries lesen ---
    entries_by_playlist: dict[int, list[tuple[int, int]]] = defaultdict(list)
    try:
        for page_data, rs in iter_table_rows(data, TABLE_PLAYLIST_ENTRIES):
            try:
                e = parse_playlist_entry_row(page_data, rs)
                # Filter stale/sentinel entries (playlist_id=0 or track_id=0 are invalid)
                if e["playlist_id"] == 0 or e["track_id"] == 0:
                    continue
                # Pitfall 10: playlist_id ohne Knoten in playlist_nodes -> graceful ignorieren
                entries_by_playlist[e["playlist_id"]].append(
                    (e["entry_index"], e["track_id"])
                )
            except struct.error as exc:
                logger.debug("Skipping playlist entry row at rs=%d: %s", rs, exc)
    except struct.error as exc:
        raise PdbParseError(f"Error parsing PlaylistEntries table: {exc}") from exc

    # --- 5. TrackRow-Objekte bauen ---
    tracks: dict[int, TrackRow] = {}
    for raw_track in raw_tracks.values():
        artist_name = artists.get(raw_track["artist_id"], "")
        album_name = ""  # Albums optional — TODO für spätere Phase
        tracks[raw_track["id"]] = TrackRow(
            track_id=raw_track["id"],
            title=raw_track["title"],
            artist_name=artist_name,
            album_name=album_name,
            bpm=raw_track["bpm"],
            key=None,  # Keys-Tabelle optional — TODO
            duration_secs=raw_track["duration"],
            rating=raw_track["rating"],
            file_path=raw_track.get("file_path", ""),  # relative USB path — used for import path construction (D-11)
            analyze_path=raw_track.get("analyze_path"),  # str_offs[14] — cue point resolution (D-08, D-09)
        )

    # --- 6. PlaylistRow-Objekte bauen ---
    # Stufe A: Alle Knoten erstellen
    playlist_rows: dict[int, PlaylistRow] = {}
    for node in playlist_nodes.values():
        playlist_rows[node["id"]] = PlaylistRow(
            id=node["id"],
            name=node["name"],
            is_folder=node["is_folder"],
            parent_id=node["parent_id"],
            children=[],  # wird in Stufe B befüllt
            songs=[],     # wird in Stufe C befüllt
        )

    # Stufe B: children verlinken
    for p in playlist_rows.values():
        if p.parent_id != 0 and p.parent_id in playlist_rows:
            playlist_rows[p.parent_id].children.append(p)
    # children nach id sortieren (stabile Reihenfolge)
    for p in playlist_rows.values():
        if p.children:
            p.children.sort(key=lambda x: x.id)

    # Stufe C: SongEntry-Listen befüllen
    for playlist_id, entries_list in entries_by_playlist.items():
        if playlist_id not in playlist_rows:
            # Pitfall 10: playlist_id ohne Knoten -> graceful ignorieren
            logger.debug(
                "Ignoring %d entries for unknown playlist_id=%d",
                len(entries_list), playlist_id,
            )
            continue
        sorted_entries = sorted(entries_list, key=lambda x: x[0])  # nach entry_index
        songs = []
        for _, track_id in sorted_entries:
            if track_id in tracks:
                songs.append(SongEntry(content=tracks[track_id]))
        playlist_rows[playlist_id].songs = songs

    # --- 7. Root-Playlists filtern (parent_id == 0) ---
    root_playlists = [p for p in playlist_rows.values() if p.parent_id == 0]
    root_playlists.sort(key=lambda p: p.id)

    logger.info(
        "Parsed %d root playlists, %d tracks from %s",
        len(root_playlists), len(tracks), path.name,
    )

    return (root_playlists, tracks)
