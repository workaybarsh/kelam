"""Application paths: read-only program files vs. writable user data.

Program files (exe, bridge.py, assets) stay where they are installed, but every
file the app *creates* — settings, logs, pid — goes to %APPDATA%\\Kelam so that
running the exe never litters its own folder.
"""

import os
import shutil
import sys

APP_NAME = "Kelam"


def is_frozen() -> bool:
    """Is this a PyInstaller build?"""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> str:
    """Folder that holds the program files (source tree or the exe folder)."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def data_dir() -> str:
    """Writable folder for settings and logs: %APPDATA%\\Kelam."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        path = os.path.dirname(os.path.abspath(__file__))
    return path


def resource_dir() -> str:
    """Location of read-only resources (temp extraction folder when packaged)."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return bundled
    return os.path.dirname(os.path.abspath(__file__))


def _migrate_legacy_config(target: str) -> None:
    """Older builds stored config.json next to the exe; move it once."""
    legacy = os.path.join(app_dir(), "config.json")
    current = os.path.join(target, "config.json")
    if os.path.isfile(legacy) and not os.path.isfile(current):
        try:
            shutil.copy2(legacy, current)
        except OSError:
            pass


APP_DIR = app_dir()
RESOURCE_DIR = resource_dir()
BASE_DIR = data_dir()

_migrate_legacy_config(BASE_DIR)
