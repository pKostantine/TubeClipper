"""TubeClipper -- take a YouTube link, trim it, export video or audio."""

from __future__ import annotations

import os
import sys

__version__ = "1.1.0"
__all__ = ["ffmpegtool", "source", "formats", "engine", "jobs",
           "timeline", "player", "ui"]


def resource_path(*parts):
    """Absolute path to a bundled file, frozen or not.

    PyInstaller unpacks data files into a temporary directory and points
    ``sys._MEIPASS`` at it; from source the same files sit next to the
    package.  One helper so nothing has to care which case it is in.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def app_data_dir():
    """Per-user directory for things we fetch at runtime.

    ffmpeg lands here when it was not bundled, along with the download
    cache.  It is deliberately under the user's own profile so nothing
    ever needs an administrator prompt.
    """
    if sys.platform.startswith("win"):
        root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        path = os.path.join(root, "TubeClipper")
    elif sys.platform == "darwin":
        path = os.path.expanduser("~/Library/Application Support/TubeClipper")
    else:
        root = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        path = os.path.join(root, "TubeClipper")
    os.makedirs(path, exist_ok=True)
    return path


def cache_dir():
    """Where whole-video downloads are kept between clips."""
    path = os.path.join(app_data_dir(), "cache")
    os.makedirs(path, exist_ok=True)
    return path
