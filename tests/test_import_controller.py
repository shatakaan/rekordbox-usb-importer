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
