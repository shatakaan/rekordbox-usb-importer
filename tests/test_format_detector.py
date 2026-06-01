"""
Tests for core.format_detector — USB format detection logic.

Covers:
- DEVICE_LIBRARY_PLUS detection (exportLibrary.db present)
- REKORDBOX_PDB detection (export.pdb only — CDJ-2000NXS2/CDJ-3000)
- NOT_REKORDBOX (no PIONEER/ directory)
- Priority: DEVICE_LIBRARY_PLUS wins when both files present
- Path traversal / OSError handling via Path.resolve()

All 6 tests run without real USB hardware.
"""

import pytest
from pathlib import Path
from unittest.mock import patch

from core.format_detector import UsbFormat, detect_usb_format


def test_device_library_plus_detected(tmp_path):
    """exportLibrary.db present -> DEVICE_LIBRARY_PLUS."""
    pioneer_dir = tmp_path / "PIONEER" / "rekordbox"
    pioneer_dir.mkdir(parents=True)
    (pioneer_dir / "exportLibrary.db").touch()

    result = detect_usb_format(tmp_path)

    assert result == UsbFormat.DEVICE_LIBRARY_PLUS


def test_rekordbox_pdb_detected(tmp_path):
    """export.pdb only (no exportLibrary.db) -> REKORDBOX_PDB.

    Covers CDJ-3000/CDJ-2000NXS2 hardware export format.
    """
    pioneer_dir = tmp_path / "PIONEER" / "rekordbox"
    pioneer_dir.mkdir(parents=True)
    (pioneer_dir / "export.pdb").touch()
    # Explicitly confirm no exportLibrary.db is present
    assert not (pioneer_dir / "exportLibrary.db").exists()

    result = detect_usb_format(tmp_path)

    assert result == UsbFormat.REKORDBOX_PDB


def test_not_rekordbox(tmp_path):
    """No PIONEER directory -> NOT_REKORDBOX."""
    # tmp_path is empty — no PIONEER/ structure
    result = detect_usb_format(tmp_path)

    assert result == UsbFormat.NOT_REKORDBOX


def test_both_formats_prefers_device_library_plus(tmp_path):
    """When both exportLibrary.db AND export.pdb present, DEVICE_LIBRARY_PLUS wins.

    Detection order: exportLibrary.db checked first (takes priority).
    """
    pioneer_dir = tmp_path / "PIONEER" / "rekordbox"
    pioneer_dir.mkdir(parents=True)
    (pioneer_dir / "exportLibrary.db").touch()
    (pioneer_dir / "export.pdb").touch()

    result = detect_usb_format(tmp_path)

    assert result == UsbFormat.DEVICE_LIBRARY_PLUS


def test_path_traversal_returns_not_rekordbox(tmp_path):
    """Path.resolve() raising PermissionError (an OSError subclass) -> NOT_REKORDBOX.

    This verifies the OSError handler in detect_usb_format gracefully catches
    PermissionError from Path.resolve() and returns NOT_REKORDBOX instead of
    propagating the exception. PermissionError is chosen because it is a concrete
    subclass of OSError that could occur on a malicious or restricted mount point.
    """
    with patch("pathlib.Path.resolve", side_effect=PermissionError("permission denied")):
        result = detect_usb_format(tmp_path)

    assert result == UsbFormat.NOT_REKORDBOX


def test_rekordbox_pdb_format_alone(tmp_path):
    """Only export.pdb present (no other files) -> REKORDBOX_PDB, not NOT_REKORDBOX.

    Explicit regression guard: confirms REKORDBOX_PDB is not masked by any
    fallback to NOT_REKORDBOX when only export.pdb is present.
    """
    pioneer_dir = tmp_path / "PIONEER" / "rekordbox"
    pioneer_dir.mkdir(parents=True)
    (pioneer_dir / "export.pdb").touch()
    # Confirm no other Rekordbox files exist in the directory
    files_in_dir = list(pioneer_dir.iterdir())
    assert len(files_in_dir) == 1 and files_in_dir[0].name == "export.pdb"

    result = detect_usb_format(tmp_path)

    assert result == UsbFormat.REKORDBOX_PDB
