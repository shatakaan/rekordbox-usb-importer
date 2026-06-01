"""
Live USB volume detection for Rekordbox USB sticks.

Watches /Volumes/ for directory changes via QFileSystemWatcher and emits
`usbs_changed` with the current list of Rekordbox USB volumes whenever a
change is detected. A 250ms settle delay (Pitfall 4 from RESEARCH.md) is
applied after each `directoryChanged` signal to allow macOS to finish
mounting the PIONEER/ folder before scanning.

Security: All paths produced by QStorageInfo.mountedVolumes() are passed
through detect_usb_format() which calls Path.resolve() before any file
existence check, guarding against path traversal via malicious volume names.
"""

import logging
from pathlib import Path

from PySide6.QtCore import (
    QFileSystemWatcher,
    QObject,
    QStorageInfo,
    QTimer,
    Signal,
)

from core.format_detector import UsbFormat, detect_usb_format

logger = logging.getLogger(__name__)


class USBScanner(QObject):
    """Watches /Volumes/ for Rekordbox USB insertion and removal.

    Emits `usbs_changed` with an updated list of
    ``(mount_path: Path, format: UsbFormat)`` tuples whenever the set of
    connected Rekordbox USB volumes changes.
    """

    usbs_changed = Signal(list)  # list of (mount_path: Path, format: UsbFormat)

    MOUNT_SETTLE_MS = 250  # delay after directoryChanged before scanning (Pitfall 4)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.addPath("/Volumes")
        self._watcher.directoryChanged.connect(self._schedule_scan)

    def current_usbs(self) -> list:
        """Return the current list of Rekordbox USB volumes synchronously.

        Returns:
            list of (mount_path: Path, format: UsbFormat) tuples.
            Suitable for the initial load on application startup.
        """
        return self._scan()

    def _schedule_scan(self, _path: str):
        """Schedule a scan after the mount settle delay.

        The 250ms delay prevents false-negative scans when directoryChanged
        fires before the PIONEER/ folder is accessible (RESEARCH.md Pitfall 4).
        """
        QTimer.singleShot(self.MOUNT_SETTLE_MS, self._emit_scan)

    def _emit_scan(self):
        """Run a scan and emit usbs_changed with the result."""
        self.usbs_changed.emit(self._scan())

    def _scan(self) -> list:
        """Scan all mounted volumes and return Rekordbox USBs.

        Returns:
            list of (mount_path: Path, format: UsbFormat) tuples,
            excluding volumes where detect_usb_format returns NOT_REKORDBOX.
        """
        result = []
        for vol_info in QStorageInfo.mountedVolumes():
            mount = Path(vol_info.rootPath())
            fmt = detect_usb_format(mount)
            if fmt != UsbFormat.NOT_REKORDBOX:
                result.append((mount, fmt))
                logger.debug("Found Rekordbox USB: %s (%s)", mount, fmt.name)
        return result
