"""Process control, Windows startup entry and shortcuts.

Works both as `python wizard.py` and as a packaged `Kelam.exe`.
In packaged mode the bridge is started via the same exe with `--bridge`.
"""

import ctypes
import os
import subprocess
import sys
import tempfile
import time
import winreg

import paths

BASE_DIR = paths.BASE_DIR
BRIDGE_PY = os.path.join(BASE_DIR, "bridge.py")
WIZARD_PY = os.path.join(BASE_DIR, "wizard.py")
PID_FILE = os.path.join(BASE_DIR, "bridge.pid")

APP_NAME = "Kelam"
APP_ID = "Kelam"
VERSION = "1.0.0"
PUBLISHER = "workaybarsh"
DESCRIPTION = "Voice typing with a remote mic button"

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Kelam"
SHELL_FOLDERS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"

CREATE_NO_WINDOW = 0x08000000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259

# Files allowed to exist in the packaged folder
FROZEN_ALLOWED = {
    f"{APP_NAME}.exe",
    "_internal",
    "config.json",
    "config.json.tmp",
    "bridge.log",
    "bridge.log.1",
    "bridge.out",
    "bridge.pid",
    "README.md",
    "LICENSE",
    "__pycache__",
}


def is_frozen():
    return paths.is_frozen()


# ---------------------------------------------------------------- komutlar
def pythonw():
    """Python interpreter without a console (script mode)."""
    exe = sys.executable or "python.exe"
    candidate = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return candidate if os.path.isfile(candidate) else exe


def _child_env():
    """Strip PyInstaller temp-folder variables from the child process.

    In onefile mode the bridge restarts the same exe; if those variables are
    inherited, the parent's _MEI folder cannot be removed ("Failed to remove
    temporary directory").
    """
    drop = {
        "_MEIPASS",
        "_PYI_APPLICATION_HOME_DIR",
        "_PYI_ARCHIVE_FILE",
        "_PYI_PARENT_PROCESS_LEVEL",
        "_PYI_SPLASH_IPC",
    }
    return {
        key: value
        for key, value in os.environ.items()
        if key not in drop and not key.startswith("_PYI_")
    }


def bridge_command():
    if is_frozen():
        return [sys.executable, "--bridge"]
    return [pythonw(), "-u", BRIDGE_PY]


def wizard_launch():
    """Shortcut target and arguments."""
    if is_frozen():
        return sys.executable, ""
    return pythonw(), f'-u "{WIZARD_PY}"'


def autostart_command():
    if is_frozen():
        return f'"{sys.executable}" --bridge'
    return f'"{pythonw()}" -u "{BRIDGE_PY}"'


# ------------------------------------------------------------------ process
def _is_alive(pid):
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def running_pid():
    try:
        with open(PID_FILE, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return None
    return pid if _is_alive(pid) else None


def is_running():
    return running_pid() is not None


def stop():
    """Stops the bridge; returns True if it was actually stopped."""
    pid = running_pid()
    if not pid:
        _remove_pid_file()
        return False
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/F"],
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
    )
    _remove_pid_file()
    return True


def _remove_pid_file():
    for _ in range(10):
        try:
            os.remove(PID_FILE)
            return
        except FileNotFoundError:
            return
        except OSError:
            time.sleep(0.1)


def start():
    """Starts the bridge without a window; returns the process id."""
    existing = running_pid()
    if existing:
        return existing
    command = bridge_command()
    if not is_frozen() and not os.path.isfile(BRIDGE_PY):
        return None

    kwargs = dict(
        cwd=BASE_DIR,
        creationflags=CREATE_NO_WINDOW,
        close_fds=True,
        env=_child_env(),
    )
    if not is_frozen():
        out = open(os.path.join(BASE_DIR, "bridge.out"), "ab")
        kwargs.update(stdout=out, stderr=out)
    try:
        proc = subprocess.Popen(command, **kwargs)
    finally:
        if not is_frozen():
            out.close()

    # The bridge writes its pid file a moment later; wait until it is really up.
    deadline = time.time() + 4.0
    while time.time() < deadline:
        pid = running_pid()
        if pid:
            return pid
        if proc.poll() is not None:
            return None
        time.sleep(0.1)
    return proc.pid if proc.poll() is None else None


def restart():
    stop()
    time.sleep(0.5)
    return start()


# ------------------------------------------------------------------ otomatik
def set_autostart(enabled):
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        if enabled:
            winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(key, APP_ID)
            except FileNotFoundError:
                pass


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_ID)
            return True
    except OSError:
        return False


def autostart_value():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_ID)
            return value
    except OSError:
        return None


# ----------------------------------------------------------------- shortcut
def _known_folder(name, fallback):
    """Reads the real folder path from the registry (handles OneDrive redirection)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SHELL_FOLDERS) as key:
            value, _ = winreg.QueryValueEx(key, name)
        value = os.path.expandvars(value)
        if os.path.isdir(value):
            return value
    except OSError:
        pass
    if os.path.isdir(fallback):
        return fallback
    return None


def start_menu_dir():
    return _known_folder(
        "Programs",
        os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft", "Windows", "Start Menu", "Programs",
        ),
    )


def desktop_dir():
    return _known_folder(
        "Desktop", os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
    )


def startup_dir():
    menu = start_menu_dir()
    return os.path.join(menu, "Startup") if menu else None


def start_menu_shortcut_path():
    menu = start_menu_dir()
    return os.path.join(menu, f"{APP_NAME}.lnk") if menu else None


def desktop_shortcut_path():
    desktop = desktop_dir()
    return os.path.join(desktop, f"{APP_NAME}.lnk") if desktop else None


def shortcut_icon():
    """Shortcut icon: the exe icon when packaged, assets/kelam.ico in script mode."""
    if is_frozen():
        return f"{sys.executable},0"
    icon = os.path.join(paths.RESOURCE_DIR, "assets", "kelam.ico")
    return icon if os.path.isfile(icon) else None


# -------------------------------------------------- Apps & features entry
def uninstall_command(quiet=False):
    """Uninstall command invoked from Control Panel."""
    suffix = " --uninstall --quiet" if quiet else " --uninstall"
    if is_frozen():
        return f'"{sys.executable}"{suffix}'
    main_py = os.path.join(BASE_DIR, "main.py")
    return f'"{pythonw()}" -u "{main_py}"{suffix}'


def install_size_kb():
    total = 0
    for root, _dirs, files in os.walk(BASE_DIR):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return max(1, total // 1024)


def register_uninstall():
    """Adds the app to the Windows uninstall list."""
    icon = shortcut_icon() or pythonw()
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        values = {
            "DisplayName": APP_NAME,
            "DisplayVersion": VERSION,
            "Publisher": PUBLISHER,
            "DisplayIcon": icon,
            "InstallLocation": BASE_DIR,
            "UninstallString": uninstall_command(),
            "QuietUninstallString": uninstall_command(quiet=True),
            "Comments": DESCRIPTION,
        }
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        for name in ("NoModify", "NoRepair"):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(
            key, "EstimatedSize", 0, winreg.REG_DWORD, install_size_kb()
        )


def unregister_uninstall():
    """Removes the registry entry, including subkeys."""

    def delete_tree(path):
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS
            ) as key:
                while True:
                    try:
                        sub = winreg.EnumKey(key, 0)
                    except OSError:
                        break
                    delete_tree(path + "\\" + sub)
        except OSError:
            return
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            pass

    delete_tree(UNINSTALL_KEY)


def uninstall_registered():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            winreg.QueryValueEx(key, "DisplayName")
            return True
    except OSError:
        return False


def uninstall_entry():
    """Summary of the registry entry, for tests and diagnostics."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            names = ("DisplayName", "DisplayVersion", "UninstallString", "InstallLocation")
            return {name: winreg.QueryValueEx(key, name)[0] for name in names}
    except OSError:
        return None


def _make_shortcut(path, target, arguments, working_dir, description, icon=None):
    values = {
        "path": path, "target": target, "args": arguments,
        "wd": working_dir, "desc": description,
    }
    escaped = {k: v.replace("'", "''") for k, v in values.items()}
    script = (
        "$ws = New-Object -ComObject WScript.Shell;"
        f"$s = $ws.CreateShortcut('{escaped['path']}');"
        f"$s.TargetPath = '{escaped['target']}';"
        f"$s.Arguments = '{escaped['args']}';"
        f"$s.WorkingDirectory = '{escaped['wd']}';"
        f"$s.Description = '{escaped['desc']}';"
    )
    if icon:
        script += f"$s.IconLocation = '{icon}';"
    script += "$s.WindowStyle = 1;$s.Save()"
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
    )
    return os.path.isfile(path)


def create_shortcuts(desktop=False):
    """Creates the Start Menu (and optionally desktop) shortcut."""
    target, args = wizard_launch()
    icon = shortcut_icon()
    created = []

    path = start_menu_shortcut_path()
    if path and _make_shortcut(path, target, args, BASE_DIR, DESCRIPTION, icon):
        created.append(path)

    if desktop:
        path = desktop_shortcut_path()
        if path and _make_shortcut(path, target, args, BASE_DIR, DESCRIPTION, icon):
            created.append(path)
    return created


def remove_shortcuts():
    """Deletes every shortcut the installer created."""
    candidates = [
        start_menu_shortcut_path(),
        desktop_shortcut_path(),
        os.path.join(startup_dir() or "", "Kelam-Bridge.lnk"),
        os.path.join(startup_dir() or "", "MicTus-Kopru.lnk"),
        os.path.join(startup_dir() or "", "MicTus-Kopru.lnk"),
    ]
    for path in candidates:
        if not path:
            continue
        try:
            os.remove(path)
        except OSError:
            pass


# ------------------------------------------------------- kendi kendini silme
def can_self_delete():
    """True when the packaged folder contains only our own files."""
    if not is_frozen():
        return False
    try:
        entries = os.listdir(BASE_DIR)
    except OSError:
        return False
    return all(name in FROZEN_ALLOWED for name in entries)


def _short_path(path):
    """Prefer the 8.3 (ASCII) path: batch files are read as ANSI."""
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.GetShortPathNameW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint,
        ]
        buf = ctypes.create_unicode_buffer(1024)
        length = kernel32.GetShortPathNameW(path, buf, 1024)
        if 0 < length < 1024:
            return buf.value
    except Exception:
        pass
    return path


def schedule_folder_delete():
    """Deletes the folder after the process exits (the exe cannot delete itself).

    `timeout` does not wait without a console, so ping is used;
    removal is retried so a late file lock does not break it.
    """
    target = _short_path(BASE_DIR)
    bat = os.path.join(tempfile.gettempdir(), f"kelam_uninstall_{os.getpid()}.bat")
    script = (
        "@echo off\r\n"
        "ping -n 5 127.0.0.1 >nul\r\n"
        "for /l %%i in (1,1,12) do (\r\n"
        f'  rmdir /s /q "{target}" 2>nul\r\n'
        f'  if not exist "{target}" goto done\r\n'
        "  ping -n 2 127.0.0.1 >nul\r\n"
        ")\r\n"
        ":done\r\n"
        'del "%~f0" >nul 2>&1\r\n'
    )
    try:
        with open(bat, "w", encoding="ascii", errors="replace") as f:
            f.write(script)
        subprocess.Popen(
            ["cmd", "/c", bat],
            cwd=tempfile.gettempdir(),
            creationflags=CREATE_NO_WINDOW,
            close_fds=True,
        )
        return True
    except OSError:
        return False


