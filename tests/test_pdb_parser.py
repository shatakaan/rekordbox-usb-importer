"""
Tests für core/pdb_parser.py — Pioneer DeviceSQL export.pdb Parser.

Gruppe A: Integrations-Tests via echtem USB (skipif wenn nicht gemountet).
Gruppe B: Unit-Tests ohne USB-Hardware.
"""

import inspect
import struct
from pathlib import Path

import pytest

import core.pdb_parser
from core.pdb_parser import PdbParseError, parse_export_pdb
from core.pdb_parser import decode_devicesql_string, parse_playlist_tree_row
from core.usb_db import TrackRow, SongEntry

# ---------------------------------------------------------------------------
# Gruppe A — Integrations-Tests via echtem USB (skipif wenn nicht gemountet)
# ---------------------------------------------------------------------------

USB_PDB = Path("/Volumes/USB DISK/PIONEER/rekordbox/export.pdb")


@pytest.mark.skipif(not USB_PDB.exists(), reason="Rekordbox USB not connected")
def test_live_usb_returns_data():
    """parse_export_pdb gibt (list, dict) zurück; tracks-dict ist nicht leer."""
    playlists, tracks = parse_export_pdb(USB_PDB)
    assert isinstance(playlists, list)
    assert isinstance(tracks, dict)
    assert len(tracks) > 0, "tracks-dict darf nicht leer sein wenn USB verbunden"


@pytest.mark.skipif(not USB_PDB.exists(), reason="Rekordbox USB not connected")
def test_live_usb_playlist_tree():
    """root_playlists ist Liste; mindestens ein Element; korrekte Attribute."""
    playlists, _ = parse_export_pdb(USB_PDB)
    assert isinstance(playlists, list)
    assert len(playlists) >= 1, "Mindestens eine Root-Playlist erwartet"
    for p in playlists:
        assert hasattr(p, "Name"), "PlaylistRow muss .Name haben"
        assert hasattr(p, "is_folder"), "PlaylistRow muss .is_folder haben"
        assert p.parent_id == 0, "Alle Root-Playlists müssen parent_id=0 haben"


@pytest.mark.skipif(not USB_PDB.exists(), reason="Rekordbox USB not connected")
def test_live_usb_track_fields():
    """Erster Track hat non-empty title; bpm >= 0; duration_secs >= 0; rating in 0-5."""
    _, tracks = parse_export_pdb(USB_PDB)
    assert len(tracks) > 0
    first_track = next(iter(tracks.values()))
    assert isinstance(first_track, TrackRow)
    assert isinstance(first_track.title, str) and len(first_track.title) > 0, (
        "title darf nicht leer sein"
    )
    assert first_track.bpm is not None and first_track.bpm >= 0, (
        f"bpm muss >= 0 sein, war: {first_track.bpm}"
    )
    assert first_track.duration_secs is not None and first_track.duration_secs >= 0, (
        f"duration_secs muss >= 0 sein, war: {first_track.duration_secs}"
    )
    assert first_track.rating in range(0, 6), (
        f"rating muss 0-5 sein, war: {first_track.rating}"
    )


@pytest.mark.skipif(not USB_PDB.exists(), reason="Rekordbox USB not connected")
def test_live_usb_song_entries():
    """SongEntry-Struktur: Songs in Playlists sind SongEntry-Instanzen mit TrackRow.Content.

    Pitfall 10 (01-PDB-RESEARCH.md): Diese USB hat nur 1 PlaylistTree-Knoten (id=1,
    Ordner "PeakTime") mit track_id=0 (ungültig). PlaylistEntry-Zeilen für
    playlist_id=2–17 haben keinen PlaylistTree-Eintrag und werden graceful ignoriert.
    Daher können auf dieser USB 0 Songs in bekannten Playlists stehen — das ist korrekt.

    Stattdessen prüfen wir: Songs-Liste ist immer korrekt typisiert (Liste von SongEntry).
    """
    playlists, tracks = parse_export_pdb(USB_PDB)

    def _collect_all(nodes):
        result = []
        for node in nodes:
            result.append(node)
            result.extend(_collect_all(node.children))
        return result

    all_playlists = _collect_all(playlists)
    # Jede Playlist muss eine Liste haben (auch wenn leer)
    for p in all_playlists:
        assert isinstance(p.songs, list), f"songs muss list sein für playlist {p.id}"
        for song in p.songs:
            assert isinstance(song, SongEntry), f"Jeder Song muss SongEntry sein"
            assert isinstance(song.Content, TrackRow), "song.Content muss TrackRow sein"

    # Der Tracks-dict muss nicht leer sein (tracks existieren unabhängig von Playlists)
    assert len(tracks) > 0, "tracks-dict muss mindestens 1 Track enthalten"


# ---------------------------------------------------------------------------
# Gruppe B — Unit-Tests (kein USB benötigt)
# ---------------------------------------------------------------------------


def test_pdb_parse_error_missing_file():
    """Nicht existierende Datei wirft PdbParseError (nicht FileNotFoundError)."""
    with pytest.raises(PdbParseError):
        parse_export_pdb(Path("/nonexistent/export.pdb"))


def test_pdb_parse_error_invalid_header(tmp_path):
    """Datei mit ungültigem Header wirft PdbParseError."""
    bad_file = tmp_path / "export.pdb"
    bad_file.write_bytes(b"JUNK" * 20)
    with pytest.raises(PdbParseError):
        parse_export_pdb(bad_file)


def test_pdb_parse_error_too_short(tmp_path):
    """Datei mit nur 10 Bytes wirft PdbParseError."""
    short_file = tmp_path / "export.pdb"
    short_file.write_bytes(b"\x00" * 10)
    with pytest.raises(PdbParseError):
        parse_export_pdb(short_file)


def test_decode_short_ascii_peaktime():
    """Short-ASCII 'PeakTime': flag=0x13, actual_len = raw_len - 1 (Pitfall 5)."""
    # 0x13 = 19 dez; raw_len = 19 >> 1 = 9; actual_len = 8 = len("PeakTime")
    # consumed = 1 (flag) + 9 (raw_len incl. null) = 10
    data = bytes([0x13]) + b"PeakTime\x00"
    text, consumed = decode_devicesql_string(data, 0)
    assert text == "PeakTime", f"Erwartet 'PeakTime', bekam '{text}'"
    assert consumed == 10, f"Erwartet consumed=10, bekam {consumed}"


def test_decode_null_string():
    """Null-String (flag=0x00) gibt leeren String zurück, verbraucht 1 Byte."""
    text, consumed = decode_devicesql_string(bytes([0x00]), 0)
    assert text == ""
    assert consumed == 1


def test_parse_playlist_tree_row_folder():
    """Synthetische PlaylistTree-Seite: Folder-Zeile korrekt geparst."""
    # 32 Bytes Seiten-Header-Platzhalter + PlaylistTree-Zeile ab rs=32
    page_header = b"\x00" * 32

    # Struct: <IIIIIII (28 Bytes): id=1, unk1=0, sort_order=1, parent_id=0,
    #          unk2=0, raw_is_folder=1, unk3=0
    tree_fixed = struct.pack("<IIIIIII", 1, 0, 1, 0, 0, 1, 0)
    # Short-ASCII "PeakTime": flag=0x13, dann "PeakTime\x00"
    name_bytes = bytes([0x13]) + b"PeakTime\x00"

    page_data = page_header + tree_fixed + name_bytes
    # Fülle auf mindestens 4096 Bytes auf (get_row_positions erwartet volle Seite)
    page_data = page_data.ljust(4096, b"\x00")

    rs = 32  # Zeile beginnt direkt nach Header
    result = parse_playlist_tree_row(page_data, rs)

    assert result["id"] == 1
    assert result["parent_id"] == 0
    assert result["is_folder"] is True
    assert result["name"] == "PeakTime"


def test_no_forbidden_imports():
    """pdb_parser.py darf construct, pyrekordbox und sqlcipher3 nicht importieren."""
    src = inspect.getsource(core.pdb_parser)
    assert "import construct" not in src, "construct darf nicht importiert werden"
    assert "import pyrekordbox" not in src, "pyrekordbox darf nicht importiert werden"
    assert "import sqlcipher3" not in src, "sqlcipher3 darf nicht importiert werden"


# ---------------------------------------------------------------------------
# Gruppe C — Phase-2 Tests: TrackRow.analyze_path (Wave 1, Plan 02-01)
# ---------------------------------------------------------------------------


def test_trackrow_has_analyze_path_field():
    """TrackRow hat analyze_path-Attribut; kein AttributeError beim Zugriff."""
    track = TrackRow(
        track_id=1,
        title="Test Track",
        artist_name="Artist",
        album_name="",
        bpm=128.0,
        key=None,
        duration_secs=240,
        rating=0,
    )
    # Attribut muss existieren — kein AttributeError
    assert hasattr(track, "analyze_path"), "TrackRow muss analyze_path-Attribut haben"
    assert track.analyze_path is None, "Default-Wert muss None sein"


def test_analyze_path_none_when_missing():
    """TrackRow mit analyze_path=None bleibt valide — kein AttributeError."""
    track = TrackRow(
        track_id=2,
        title="Another Track",
        artist_name="DJ",
        album_name="",
        bpm=140.0,
        key=None,
        duration_secs=300,
        rating=3,
        analyze_path=None,
    )
    assert track.analyze_path is None


def _build_synthetic_pdb_with_track(
    title: str = "TestTrack",
    file_path: str = "/Contents/test.mp3",
    analyze_path: str = "/PIONEER/USBANLZ/ab/cd1234ef.DAT",
) -> bytes:
    """Baut ein minimales synthetisches export.pdb mit einem Track-Eintrag.

    Track-Zeile Aufbau (pdb_parser.py, parse_track_row):
      - 8-Byte-Praefix (rbase = rs + 8)
      - +0x38: tempo (u32) = 12800 (= 128.00 BPM)
      - +0x40: album_id (u32) = 0
      - +0x44: artist_id (u32) = 0
      - +0x48: track_id (u32) = 1
      - +0x54: duration (u16) = 240
      - +0x59: rating (u8) = 0
      - +0x5E: 21 x u16 string offsets (relativ zu rbase)
      - Strings: title @ str_offs[17], file_path @ str_offs[20],
                 analyze_path @ str_offs[14]
    """
    PAGE_SIZE_LOCAL = 4096
    HEADER_END_LOCAL = 32
    TABLE_START_OFF_LOCAL = 0x1C

    def short_ascii(s: str) -> bytes:
        """Encode string as DeviceSQL short ASCII."""
        encoded = s.encode("ascii") + b"\x00"
        raw_len = len(encoded)
        flag = (raw_len << 1) | 0x01
        return bytes([flag]) + encoded

    title_bytes = short_ascii(title)
    fp_bytes = short_ascii(file_path)
    ap_bytes = short_ascii(analyze_path)

    # Track-Zeile: 8-Byte-Praefix + feste Felder + 21 String-Offsets + Strings
    # Feste Felder belegen: maximal bis 0x5E + 21*2 = 0x5E + 42 = 136 Bytes ab rbase
    FIXED_SIZE = 0x5E + 21 * 2  # 136 Bytes ab rbase

    # String-Daten haengen ab FIXED_SIZE an (relativ zu rbase)
    str_data_start = FIXED_SIZE

    off_title = str_data_start
    off_fp = off_title + len(title_bytes)
    off_ap = off_fp + len(fp_bytes)

    offsets = [0] * 21
    offsets[17] = off_title
    offsets[20] = off_fp
    offsets[14] = off_ap

    fixed = bytearray(FIXED_SIZE)
    struct.pack_into("<I", fixed, 0x38, 12800)   # tempo = 12800 (= 128.00 BPM)
    struct.pack_into("<I", fixed, 0x48, 1)        # track_id = 1
    struct.pack_into("<H", fixed, 0x54, 240)      # duration = 240
    struct.pack_into("<21H", fixed, 0x5E, *offsets)

    prefix = b"\x00" * 8
    track_row_bytes = prefix + bytes(fixed) + title_bytes + fp_bytes + ap_bytes

    # Seite aufbauen (4096 Bytes)
    # Zeile: rs = HEADER_END_LOCAL = 32
    # Row-Offset-Gruppe am Ende: 1 Slot
    group_bytes = struct.pack("<HHH",
        0,      # raw_off = 0 (rs - HEADER_END = 0)
        0x01,   # rpf: Bit 0 gesetzt = Slot 0 present
        0x01,   # txf
    )

    page = bytearray(PAGE_SIZE_LOCAL)
    struct.pack_into("<I", page, 4, 1)    # page_idx = 1
    struct.pack_into("<I", page, 8, 0)    # type = TABLE_TRACKS = 0
    struct.pack_into("<I", page, 12, 0)   # next_pg = 0
    page[24] = 1   # num_row_offsets = 1
    page[25] = 0
    page[26] = 0
    page[27] = 0   # page_flags: is_data = True (bit 6 unset)

    row_start = HEADER_END_LOCAL
    page[row_start: row_start + len(track_row_bytes)] = track_row_bytes
    page[PAGE_SIZE_LOCAL - len(group_bytes): PAGE_SIZE_LOCAL] = group_bytes

    # PDB-Datei-Header (erste Seite = Seite 0)
    file_header = bytearray(PAGE_SIZE_LOCAL)
    struct.pack_into("<I", file_header, 0, 0)        # _zero = 0
    struct.pack_into("<I", file_header, 4, 4096)     # page_size = 4096
    struct.pack_into("<I", file_header, 8, 1)        # num_tables = 1
    # Table-Eintrag: (type=0, unk=0, first_page=1, last_page=1)
    struct.pack_into("<IIII", file_header, TABLE_START_OFF_LOCAL, 0, 0, 1, 1)

    return bytes(file_header) + bytes(page)


def test_analyze_path_extracted(tmp_path):
    """parse_export_pdb gibt TrackRow mit analyze_path zurueck wenn str_offs[14] gesetzt."""
    pdb_file = tmp_path / "export.pdb"
    pdb_data = _build_synthetic_pdb_with_track(
        title="SynthTrack",
        file_path="/Contents/synth.mp3",
        analyze_path="/PIONEER/USBANLZ/ab/cd1234ef.DAT",
    )
    pdb_file.write_bytes(pdb_data)

    _, tracks = parse_export_pdb(pdb_file)
    assert len(tracks) == 1, f"Erwartet 1 Track, bekam {len(tracks)}"
    track = next(iter(tracks.values()))
    # analyze_path muss gesetzt sein und mit /PIONEER beginnen
    assert track.analyze_path is not None, (
        "analyze_path darf nicht None sein wenn str_offs[14] gesetzt ist"
    )
    assert track.analyze_path.startswith("/PIONEER"), (
        f"analyze_path soll mit /PIONEER beginnen, war: {track.analyze_path!r}"
    )
