"""
Tests for core/import_controller.py — ImportController (Plan 02-02).

Requirements covered:
  SAFE-01: Rekordbox-running guard blocks import
  SAFE-02: Backup file created before DB write
  SAFE-03: Backup path logged
  SAFE-04: DB rollback on error
  PLAY-03: Track stored with USB-absolute path (FolderPath starts with USB mount)
  META-03: BPM scaled by 100 when passed to add_content (Rekordbox stores BPM * 100)

All tests import the module under test — if the module does not exist yet,
tests are skipped via pytest.importorskip so pytest collection succeeds.
When the module exists but the feature is not implemented, tests raise
AssertionError / specific exceptions as documented below.
"""

import pytest

ImportController = pytest.importorskip(
    "core.import_controller",
    reason="core.import_controller not yet implemented (Plan 02-02)",
).ImportController


# ---------------------------------------------------------------------------
# SAFE-01: Rekordbox-running guard
# ---------------------------------------------------------------------------

def test_blocks_when_rekordbox_running(mock_rb6_db, usb_mount, make_track_row):
    """ImportController.run_preflight() returns an error / raises when Rekordbox is running.

    Requirement SAFE-01 (02-CONTEXT.md D-13): if get_rekordbox_pid() != 0, import
    must be blocked with a clear message.
    """
    controller = ImportController(db=mock_rb6_db, usb_mount=usb_mount)

    # Patch the process-detection helper to simulate Rekordbox running
    import unittest.mock as mock
    with mock.patch(
        "core.import_controller.get_rekordbox_pid", return_value=12345
    ):
        result = controller.run_preflight()

    # Either returns a falsy/error result or raises — both are acceptable
    if result is None:
        pytest.fail("run_preflight() returned None; expected an error indicator")
    assert not result.ok, (
        "run_preflight() must report failure when Rekordbox is running"
    )
    assert "rekordbox" in result.message.lower(), (
        "Error message must mention 'rekordbox'"
    )


# ---------------------------------------------------------------------------
# SAFE-02: Backup created
# ---------------------------------------------------------------------------

def test_backup_created(mock_rb6_db, usb_mount, make_track_row):
    """After run_import(), a backup file master.db.backup.* exists in db_dir.

    Requirement SAFE-02 / D-14: backup created after confirmation, before DB writes.
    """
    track = make_track_row(file_path="/Contents/test.mp3")
    controller = ImportController(db=mock_rb6_db, usb_mount=usb_mount)

    import unittest.mock as mock
    with mock.patch("core.import_controller.get_rekordbox_pid", return_value=0):
        controller.run_import(tracks=[track], playlist_name="TestPlaylist")

    db_dir = mock_rb6_db._db_dir
    backup_files = list(db_dir.glob("master.db.backup.*"))
    assert len(backup_files) >= 1, (
        f"Expected at least one backup file in {db_dir}, found none"
    )


# ---------------------------------------------------------------------------
# SAFE-03: Backup path logged
# ---------------------------------------------------------------------------

def test_backup_path_logged(mock_rb6_db, usb_mount, make_track_row, caplog):
    """The backup file path appears in log output during run_import().

    Requirement SAFE-03: backup path must be shown in log so DJ knows where it is.
    """
    import logging

    track = make_track_row(file_path="/Contents/test.mp3")
    controller = ImportController(db=mock_rb6_db, usb_mount=usb_mount)

    import unittest.mock as mock
    with mock.patch("core.import_controller.get_rekordbox_pid", return_value=0):
        with caplog.at_level(logging.INFO):
            controller.run_import(tracks=[track], playlist_name="TestPlaylist")

    log_text = caplog.text.lower()
    assert "backup" in log_text, (
        "Expected 'backup' to appear in log output; log was:\n" + caplog.text
    )
    assert "master.db" in log_text, (
        "Expected 'master.db' to appear in log output; log was:\n" + caplog.text
    )


# ---------------------------------------------------------------------------
# SAFE-04: Rollback on error
# ---------------------------------------------------------------------------

def test_rollback_on_error(mock_rb6_db, usb_mount, make_track_row):
    """db.rollback() is called when add_content() raises an exception.

    Requirement SAFE-04 / D-15: atomic write — rollback on failure.
    """
    mock_rb6_db.add_content.side_effect = RuntimeError("simulated DB write error")

    track = make_track_row(file_path="/Contents/test.mp3")
    controller = ImportController(db=mock_rb6_db, usb_mount=usb_mount)

    import unittest.mock as mock
    with mock.patch("core.import_controller.get_rekordbox_pid", return_value=0):
        try:
            controller.run_import(tracks=[track], playlist_name="TestPlaylist")
        except Exception:
            pass  # exception propagation is acceptable as long as rollback was called

    mock_rb6_db.rollback.assert_called_once(), (
        "db.rollback() must be called exactly once when add_content raises"
    )


# ---------------------------------------------------------------------------
# PLAY-03: FolderPath starts with USB mount
# ---------------------------------------------------------------------------

def test_folderpath_is_usb_path(mock_rb6_db, usb_mount, make_track_row):
    """add_content is called with a path rooted at the USB mount point.

    Requirement PLAY-03 / D-11: tracks stored with absolute USB path so Rekordbox
    finds them when USB is connected.
    """
    relative_path = "/Contents/test.mp3"
    track = make_track_row(file_path=relative_path)
    controller = ImportController(db=mock_rb6_db, usb_mount=usb_mount)

    import unittest.mock as mock
    with mock.patch("core.import_controller.get_rekordbox_pid", return_value=0):
        controller.run_import(tracks=[track], playlist_name="TestPlaylist")

    assert mock_rb6_db.add_content.called, "add_content must have been called"
    call_args = mock_rb6_db.add_content.call_args

    # Path may be passed as positional or keyword argument
    path_arg = None
    if call_args.args:
        path_arg = str(call_args.args[0])
    elif "path" in call_args.kwargs:
        path_arg = str(call_args.kwargs["path"])
    elif "FolderPath" in call_args.kwargs:
        path_arg = str(call_args.kwargs["FolderPath"])

    assert path_arg is not None, "Could not find path argument in add_content call"
    assert path_arg.startswith(str(usb_mount)), (
        f"Track path must start with USB mount {usb_mount}, got: {path_arg!r}"
    )


# ---------------------------------------------------------------------------
# META-03: BPM scaling (128.0 -> 12800)
# ---------------------------------------------------------------------------

def test_bpm_scaling(mock_rb6_db, usb_mount, make_track_row):
    """BPM=128.0 in TrackRow is passed as 12800 (BPM * 100) to add_content.

    Requirement META-03: Rekordbox stores BPM as integer * 100 internally.
    """
    track = make_track_row(file_path="/Contents/test.mp3", bpm=128.0)
    controller = ImportController(db=mock_rb6_db, usb_mount=usb_mount)

    import unittest.mock as mock
    with mock.patch("core.import_controller.get_rekordbox_pid", return_value=0):
        controller.run_import(tracks=[track], playlist_name="TestPlaylist")

    assert mock_rb6_db.add_content.called, "add_content must have been called"
    call_args = mock_rb6_db.add_content.call_args

    # BPM may be passed as positional or keyword argument
    bpm_value = call_args.kwargs.get("BPM") or call_args.kwargs.get("bpm")
    if bpm_value is None and call_args.args:
        # Fall back: check all positional args for 12800
        bpm_value = next((a for a in call_args.args if a == 12800), None)

    assert bpm_value == 12800, (
        f"Expected BPM=12800 (128.0 * 100) passed to add_content, got: {bpm_value!r}"
    )


# ---------------------------------------------------------------------------
# Cue Point Import Tests (Plan 02-03)
# ---------------------------------------------------------------------------

def test_cue_import_from_ext(mock_rb6_db, usb_mount, make_track_row):
    """_import_cues reads PCO2 from .EXT file and calls db.add() for each entry.

    When .EXT file exists, ONLY PCO2 is used — .DAT (PCOB) is never read.
    This enforces Pitfall 6: never write both PCOB and PCO2 for the same track.

    Requirements: D-08, D-09, META-01, META-02
    """
    import unittest.mock as mock
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    # Create fake ANLZ directory and files in usb_mount
    anlz_dir = usb_mount / "PIONEER" / "USBANLZ" / "d44" / "abcd-1234"
    anlz_dir.mkdir(parents=True, exist_ok=True)
    dat_path = anlz_dir / "ANLZ0000.DAT"
    ext_path = anlz_dir / "ANLZ0000.EXT"
    dat_path.write_bytes(b"")
    ext_path.write_bytes(b"")

    relative_anlz = "/PIONEER/USBANLZ/d44/abcd-1234/ANLZ0000.DAT"
    track = make_track_row(
        file_path="/Contents/test.mp3",
        analyze_path=relative_anlz,
    )

    # Build mock AnlzFile for .EXT with PCO2 entries
    entry1 = MagicMock()
    entry1.hot_cue = 1
    entry1.time = 10000
    entry1.loop_time = -1
    entry1.comment = "Drop"

    entry2 = MagicMock()
    entry2.hot_cue = 0
    entry2.time = 5000
    entry2.loop_time = -1
    entry2.comment = ""

    mock_tag = MagicMock()
    mock_tag.entries = [entry1, entry2]

    mock_anlz_ext = MagicMock()
    mock_anlz_ext.__contains__ = MagicMock(side_effect=lambda k: k == "PCO2")
    mock_anlz_ext.get_tag.return_value = mock_tag

    mock_content = MagicMock()
    mock_content.ID = "content-id-1"
    mock_content.UUID = "content-uuid-1"
    mock_rb6_db.add_content.return_value = mock_content

    controller = ImportController(db=mock_rb6_db, usb_mount=usb_mount)

    with patch("core.import_controller.AnlzFile.parse_file", return_value=mock_anlz_ext) as mock_parse:
        with mock.patch("core.import_controller.get_rekordbox_pid", return_value=0):
            controller.run_import(tracks=[track], playlist_name="TestPlaylist")

    # parse_file should be called with .EXT path (not .DAT for cues)
    assert mock_parse.called, "_import_cues must call AnlzFile.parse_file"
    called_path = str(mock_parse.call_args[0][0])
    assert called_path.endswith(".EXT"), (
        f"When .EXT exists, parse_file must be called with .EXT path, got: {called_path}"
    )

    # db.add() must be called twice (once per cue entry)
    add_calls = mock_rb6_db.add.call_count
    assert add_calls >= 2, (
        f"Expected db.add() called at least 2 times for 2 PCO2 entries, got: {add_calls}"
    )


def test_cue_import_dat_fallback(mock_rb6_db, usb_mount, make_track_row):
    """_import_cues falls back to .DAT (PCOB) when .EXT file does not exist.

    Only entries with status.intvalue == 4 (enabled) are imported from PCOB.

    Requirements: D-08, D-09, META-01, META-02
    """
    import unittest.mock as mock
    from unittest.mock import MagicMock, patch

    # Create ONLY the .DAT file — no .EXT
    anlz_dir = usb_mount / "PIONEER" / "USBANLZ" / "d44" / "abcd-5678"
    anlz_dir.mkdir(parents=True, exist_ok=True)
    dat_path = anlz_dir / "ANLZ0000.DAT"
    dat_path.write_bytes(b"")
    # .EXT intentionally NOT created

    relative_anlz = "/PIONEER/USBANLZ/d44/abcd-5678/ANLZ0000.DAT"
    track = make_track_row(
        file_path="/Contents/test.mp3",
        analyze_path=relative_anlz,
    )

    # One enabled entry, one disabled entry
    enabled_entry = MagicMock()
    enabled_entry.hot_cue = 1
    enabled_entry.time = 8000
    enabled_entry.loop_time = -1
    enabled_entry.status.intvalue = 4   # enabled

    disabled_entry = MagicMock()
    disabled_entry.hot_cue = 2
    disabled_entry.time = 9000
    disabled_entry.loop_time = -1
    disabled_entry.status.intvalue = 0  # disabled — must NOT be imported

    mock_tag = MagicMock()
    mock_tag.entries = [enabled_entry, disabled_entry]

    mock_anlz_dat = MagicMock()
    mock_anlz_dat.__contains__ = MagicMock(side_effect=lambda k: k == "PCOB")
    mock_anlz_dat.get_tag.return_value = mock_tag

    mock_content = MagicMock()
    mock_content.ID = "content-id-2"
    mock_content.UUID = "content-uuid-2"
    mock_rb6_db.add_content.return_value = mock_content

    controller = ImportController(db=mock_rb6_db, usb_mount=usb_mount)

    with patch("core.import_controller.AnlzFile.parse_file", return_value=mock_anlz_dat) as mock_parse:
        with mock.patch("core.import_controller.get_rekordbox_pid", return_value=0):
            controller.run_import(tracks=[track], playlist_name="TestPlaylist")

    # parse_file called with .DAT path (no .EXT exists)
    assert mock_parse.called, "_import_cues must call AnlzFile.parse_file"
    called_path = str(mock_parse.call_args[0][0])
    assert called_path.endswith(".DAT"), (
        f"When only .DAT exists, parse_file must be called with .DAT, got: {called_path}"
    )

    # Only the enabled entry should result in db.add()
    add_calls = mock_rb6_db.add.call_count
    assert add_calls == 1, (
        f"Expected exactly 1 db.add() call (enabled entry only), got: {add_calls}"
    )


def test_cue_missing_anlz_logs_warning(mock_rb6_db, usb_mount, make_track_row, caplog):
    """When analyze_path is None, log warning and do not call db.add() for cues.

    Non-blocking per D-10: track is still imported, just without cue points.
    """
    import logging
    import unittest.mock as mock
    from unittest.mock import MagicMock, patch

    track_no_path = make_track_row(
        file_path="/Contents/test.mp3",
        analyze_path=None,  # No analyze_path
    )

    mock_content = MagicMock()
    mock_rb6_db.add_content.return_value = mock_content

    controller = ImportController(db=mock_rb6_db, usb_mount=usb_mount)

    with patch("core.import_controller.AnlzFile.parse_file") as mock_parse:
        with mock.patch("core.import_controller.get_rekordbox_pid", return_value=0):
            with caplog.at_level(logging.WARNING):
                controller.run_import(tracks=[track_no_path], playlist_name="TestPlaylist")

    # parse_file must NOT be called when analyze_path is None
    assert not mock_parse.called, (
        "AnlzFile.parse_file must not be called when analyze_path is None"
    )

    # db.add() must NOT be called (no cues to write)
    assert mock_rb6_db.add.call_count == 0, (
        "db.add() must not be called for cues when analyze_path is None"
    )

    # A WARNING must be logged
    warning_logs = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warning_logs) >= 1, (
        "Expected at least one WARNING log when analyze_path is None; got none.\n"
        f"All log records: {[r.message for r in caplog.records]}"
    )


def test_cue_kind_mapping(mock_rb6_db, usb_mount, make_track_row):
    """Memory Cue (hot_cue=0) produces DjmdCue with Kind=0; Hot Cue (hot_cue=1) -> Kind=1.

    Verifies Assumption A1/A2 from RESEARCH.md: Kind matches hot_cue field value.
    """
    import unittest.mock as mock
    from unittest.mock import MagicMock, patch

    # Create .EXT file so PCO2 path is taken
    anlz_dir = usb_mount / "PIONEER" / "USBANLZ" / "d44" / "abcd-kind"
    anlz_dir.mkdir(parents=True, exist_ok=True)
    (anlz_dir / "ANLZ0000.DAT").write_bytes(b"")
    (anlz_dir / "ANLZ0000.EXT").write_bytes(b"")

    relative_anlz = "/PIONEER/USBANLZ/d44/abcd-kind/ANLZ0000.DAT"
    track = make_track_row(
        file_path="/Contents/test.mp3",
        analyze_path=relative_anlz,
    )

    memory_entry = MagicMock()
    memory_entry.hot_cue = 0   # Memory Cue
    memory_entry.time = 3000
    memory_entry.loop_time = -1
    memory_entry.comment = ""

    hot_entry = MagicMock()
    hot_entry.hot_cue = 1    # Hot Cue Slot 1
    hot_entry.time = 7000
    hot_entry.loop_time = -1
    hot_entry.comment = "Chorus"

    mock_tag = MagicMock()
    mock_tag.entries = [memory_entry, hot_entry]

    mock_anlz = MagicMock()
    mock_anlz.__contains__ = MagicMock(side_effect=lambda k: k == "PCO2")
    mock_anlz.get_tag.return_value = mock_tag

    mock_content = MagicMock()
    mock_content.ID = "content-id-3"
    mock_content.UUID = "content-uuid-3"
    mock_rb6_db.add_content.return_value = mock_content

    # Capture what DjmdCue.create receives
    created_cues = []

    def capture_create(**kwargs):
        created_cues.append(kwargs)
        return MagicMock()

    controller = ImportController(db=mock_rb6_db, usb_mount=usb_mount)

    with patch("core.import_controller.AnlzFile.parse_file", return_value=mock_anlz):
        with patch("core.import_controller.DjmdCue.create", side_effect=capture_create):
            with mock.patch("core.import_controller.get_rekordbox_pid", return_value=0):
                controller.run_import(tracks=[track], playlist_name="TestPlaylist")

    assert len(created_cues) == 2, (
        f"Expected DjmdCue.create called twice, got {len(created_cues)} times"
    )

    kinds = [c["Kind"] for c in created_cues]
    assert 0 in kinds, (
        f"Expected Kind=0 (Memory Cue) among created cues; got kinds={kinds}"
    )
    assert 1 in kinds, (
        f"Expected Kind=1 (Hot Cue Slot 1) among created cues; got kinds={kinds}"
    )
