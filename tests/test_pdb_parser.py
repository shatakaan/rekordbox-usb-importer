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
