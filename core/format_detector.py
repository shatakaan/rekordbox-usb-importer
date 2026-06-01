"""
USB format detection for Rekordbox exports.

Detects whether a USB mount point contains a supported Rekordbox export format
by inspecting the PIONEER/rekordbox/ directory structure.

Decision tree (from RESEARCH.md Pitfall 1):
1. exportLibrary.db exists -> DEVICE_LIBRARY_PLUS (open with DeviceLibraryPlus)
2. export.pdb only         -> REKORDBOX_PDB (CDJ-era format — read-only supported)
3. Neither                 -> NOT_REKORDBOX (ignore)

Security: Path.resolve() is called before existence checks to guard against
path traversal via malicious USB volume names (RESEARCH.md Security Domain).
"""

import logging
from enum import Enum, auto
from pathlib import Path

logger = logging.getLogger(__name__)


class UsbFormat(Enum):
    DEVICE_LIBRARY_PLUS = auto()  # exportLibrary.db present — RB6/7, fully supported
    REKORDBOX_PDB = auto()        # export.pdb only — CDJ-2000NXS2/CDJ-3000 hardware export
    NOT_REKORDBOX = auto()        # neither file found — not a Rekordbox USB


def detect_usb_format(mount: Path) -> UsbFormat:
    """
    Detect the Rekordbox export format on a USB mount point.

    Args:
        mount: Path to the USB mount point (e.g. /Volumes/USB_STICK).

    Returns:
        UsbFormat enum value indicating the detected format.
    """
    pioneer_dir = mount / "PIONEER" / "rekordbox"

    # Resolve to guard against path traversal (Security: ASVS V4/V5)
    try:
        pioneer_dir = pioneer_dir.resolve()
    except OSError:
        logger.warning("Path resolution failed for %s — returning NOT_REKORDBOX", mount)
        return UsbFormat.NOT_REKORDBOX

    has_exportlib = (pioneer_dir / "exportLibrary.db").exists()
    has_pdb = (pioneer_dir / "export.pdb").exists()

    if has_exportlib:
        logger.debug("Detected DEVICE_LIBRARY_PLUS at %s", mount)
        return UsbFormat.DEVICE_LIBRARY_PLUS
    elif has_pdb:
        logger.debug("Detected REKORDBOX_PDB at %s", mount)
        return UsbFormat.REKORDBOX_PDB
    else:
        logger.debug("No Rekordbox format detected at %s", mount)
        return UsbFormat.NOT_REKORDBOX


USB_04_ERROR_MESSAGE = (
    "This USB uses a format not supported by this app. "
    "Please re-export from Rekordbox 6 or 7 with Device Library Plus enabled."
)
