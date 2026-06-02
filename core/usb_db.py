"""
Gemeinsame Datenabstraktionsklassen für USB-Datenbankquellen.
Duck-typing-kompatibel mit pyrekordbox DjmdPlaylist/DjmdContent-ORM-Objekten.

Diese Klassen ermöglichen es ui/playlist_panel.py und ui/track_panel.py ohne
if-Branches zu funktionieren, unabhängig davon ob die Daten aus dem
pyrekordbox-ORM oder dem PDB-Parser stammen.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class _NamedObj:
    """Proxy-Objekt das einen Namen über .name (klein) und .Name (gross) bereitstellt.

    track_panel liest getattr(content.Artist, "Name", "") — daher brauchen
    Artist und Album ein Objekt mit .Name-Property, nicht direkt einen String.
    """

    name: str

    @property
    def Name(self) -> str:  # noqa: N802
        return self.name


@dataclass
class TrackRow:
    """Repräsentiert einen einzelnen Track vom USB-Stick.

    Duck-typing-kompatibel mit pyrekordbox DjmdContent ORM-Objekt.
    Properties entsprechen exakt den Attributnamen, die track_panel.py erwartet.
    """

    track_id: int
    title: str
    artist_name: str
    album_name: str
    bpm: float | None
    key: str | None
    duration_secs: int | None
    rating: int | None

    # ------------------------------------------------------------------
    # Duck-typing-Properties (passend zu DjmdContent-ORM-Attributnamen)
    # ------------------------------------------------------------------

    @property
    def Title(self) -> str:  # noqa: N802
        return self.title

    @property
    def Artist(self) -> _NamedObj:  # noqa: N802
        """Gibt _NamedObj zurück; track_panel liest content.Artist.Name."""
        return _NamedObj(self.artist_name)

    @property
    def Album(self) -> _NamedObj:  # noqa: N802
        """Gibt _NamedObj zurück; track_panel liest content.Album.Name."""
        return _NamedObj(self.album_name)

    @property
    def BPM(self) -> float | None:  # noqa: N802
        return self.bpm

    @property
    def Tonality(self) -> str | None:  # noqa: N802
        """Tonart (Key) des Tracks; track_panel liest content.Tonality."""
        return self.key

    @property
    def Length(self) -> int | None:  # noqa: N802
        """Dauer in Sekunden; track_panel liest content.Length."""
        return self.duration_secs

    @property
    def Rating(self) -> int | None:  # noqa: N802
        return self.rating


@dataclass
class SongEntry:
    """Repräsentiert die Mitgliedschaft eines Tracks in einer Playlist.

    Duck-typing-kompatibel mit pyrekordbox DjmdSongPlaylist ORM-Objekt.
    track_panel liest song.Content um das Track-Objekt zu erhalten.
    """

    content: TrackRow

    @property
    def Content(self) -> TrackRow:  # noqa: N802
        """Gibt das zugehörige TrackRow-Objekt zurück."""
        return self.content


@dataclass
class PlaylistRow:
    """Repräsentiert einen Playlist- oder Ordner-Knoten im PlaylistTree.

    Duck-typing-kompatibel mit pyrekordbox DjmdPlaylist ORM-Objekt.
    Properties entsprechen exakt den Attributnamen, die playlist_panel.py
    und MainWindow erwarten.
    """

    id: int
    name: str
    is_folder: bool
    parent_id: int
    children: list[PlaylistRow] = field(default_factory=list)
    songs: list[SongEntry] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Duck-typing-Properties (passend zu DjmdPlaylist-ORM-Attributnamen)
    # ------------------------------------------------------------------

    @property
    def Name(self) -> str:  # noqa: N802
        """playlist_panel liest getattr(playlist, 'Name', '<unnamed>')."""
        return self.name

    @property
    def Attribute(self) -> int:  # noqa: N802
        """Ordner-Flag: 1 wenn is_folder=True, 0 sonst.

        playlist_panel prüft getattr(playlist, 'Attribute', None) == 1.
        """
        return 1 if self.is_folder else 0

    @property
    def ParentID(self) -> int:  # noqa: N802
        """MainWindow filtert getattr(p, "ParentID", None) in (None, 0)."""
        return self.parent_id

    @property
    def Children(self) -> list[PlaylistRow]:  # noqa: N802
        """playlist_panel liest getattr(playlist, 'Children', None)."""
        return self.children

    @property
    def Songs(self) -> list[SongEntry]:  # noqa: N802
        """track_panel liest playlist.Songs."""
        return self.songs
