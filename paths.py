"""Application paths: the right folder for both scripts and PyInstaller exes."""

import os
import sys


def is_frozen() -> bool:
    """Is this a PyInstaller build?"""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> str:
    """Real folder for settings and logs (next to the exe)."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource_dir() -> str:
    """Location of read-only resources (temp extraction folder when packaged)."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return bundled
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = app_dir()
RESOURCE_DIR = resource_dir()
