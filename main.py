"""Kelam entry point.

    Kelam.exe              -> setup / settings wizard
    Kelam.exe --bridge     -> background bridge (startup and shortcuts)
    Kelam.exe --diagnostics <file> -> self-check info file
    python main.py --bridge
"""

import os
import sys

# In PyInstaller's windowed mode stdout/stderr are None; keep print() safe.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")


def write_diagnostics(target: str) -> int:
    """Writes paths/commands of the packaged build to a file (for tests)."""
    import json

    import paths
    import service

    data = {
        "frozen": paths.is_frozen(),
        "version": service.VERSION,
        "base_dir": paths.BASE_DIR,
        "resource_dir": paths.RESOURCE_DIR,
        "python": sys.executable,
        "bridge_command": service.bridge_command(),
        "autostart_command": service.autostart_command(),
        "shortcut_target": service.wizard_launch(),
        "config_path": os.path.join(paths.BASE_DIR, "config.json"),
        "can_self_delete": service.can_self_delete(),
        "config_defaults": __import__("config").DEFAULT_CONFIG,
    }
    with open(target, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return 0


def main() -> int:
    argv = sys.argv[1:]

    if "--diagnostics" in argv:
        index = argv.index("--diagnostics")
        target = argv[index + 1] if len(argv) > index + 1 else "diagnostics.json"
        return write_diagnostics(target)

    if "--bridge" in argv:
        sys.argv = [arg for arg in sys.argv if arg != "--bridge"]
        import bridge

        return bridge.main()

    if "--uninstall" in argv:
        import service
        import wizard

        if "--quiet" in argv:
            wizard.uninstall_all()
            if service.can_self_delete():
                service.schedule_folder_delete()
            return 0

        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        dialog = wizard.UninstallWizard(root)
        dialog.run()
        removed = bool(dialog.removed)
        try:
            if root.winfo_exists():
                root.destroy()
        except tk.TclError:
            pass
        if removed and service.can_self_delete():
            service.schedule_folder_delete()
        return 0

    import config as cfg
    import service
    import wizard

    installed = os.path.isfile(cfg.CONFIG_PATH) or service.is_running()
    if installed:
        wizard.SettingsWindow().run()
    else:
        wizard.SetupWizard().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
