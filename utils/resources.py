"""
Bundle-safe resource path resolution for PyInstaller .app bundles.

When the app is frozen by PyInstaller, bundled resources are extracted to a
temporary directory stored in sys._MEIPASS. This module provides a single
helper that resolves resource paths correctly in both development and
bundled contexts.

Usage:
    from utils.resources import get_resource_path

    icon_path = get_resource_path("assets/icon.icns")

Reference: https://pyinstaller.org/en/stable/runtime-information.html
"""

import sys
from pathlib import Path


def get_resource_path(relative_path: str) -> Path:
    """Resolve a path to a bundled resource.

    Works in both development mode (relative to the project root) and in a
    PyInstaller .app bundle (relative to sys._MEIPASS temp directory).

    Args:
        relative_path: Path relative to the project root (development) or
            the PyInstaller extraction directory (bundle).

    Returns:
        Absolute Path to the requested resource.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Running in a PyInstaller bundle — resources are in the temp dir
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        # Running in development — project root is two levels above this file
        # utils/resources.py -> utils/ -> project root
        base = Path(__file__).parent.parent

    return base / relative_path
