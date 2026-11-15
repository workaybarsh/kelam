"""End-to-end install / uninstall test.

It really runs the wizard (mainloop included), walks the pages programmatically
and verifies what install and uninstall leave behind.

    python tests/test_flow.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as cfg  # noqa: E402
import service  # noqa: E402
import wizard as wizard_mod  # noqa: E402

RESULTS = []
DIALOGS = []


def _record(kind):
    def handler(title=None, message=None, **_kwargs):
        DIALOGS.append((kind, title, message))
        return True

    return handler


# Do not let modal dialogs block the test: record and continue.
wizard_mod.messagebox.showwarning = _record("warning")
wizard_mod.messagebox.showerror = _record("error")
wizard_mod.messagebox.showinfo = _record("info")
wizard_mod.messagebox.askyesno = _record("ask")


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}" + (f"  ({detail})" if detail else ""), flush=True)
    return bool(condition)


def fake_hid_event():
    """Exactly the report the real remote sends."""
    return {
        "type": "hid",
        "vid": 0x1915,
        "pid": 0x1025,
        "usage_page": 0x000C,
        "usage": 0x00CF,
        "report_id": 2,
        "report_len": 3,
        "path": r"\\?\hid#vid_1915&pid_1025&mi_03&col02#test",
        "raw": "02cf00",
        "time": time.time(),
    }


def clear_previous():
    print("\n=== 0. Initial cleanup ===")
    wizard_mod.uninstall_all()
    check("clean start: bridge stopped", not service.is_running())
    check("clean start: no config file", not os.path.isfile(cfg.CONFIG_PATH))


def run_wizard():
    """Runs the wizard with mainloop and walks the pages in order."""
    app = wizard_mod.SetupWizard()
    state = {"done": False, "error": None, "install_started": False}

    def driver():
        try:
            check("wizard opened (page 1)", app.page == 0)

            app.next_button.invoke()
            check("moved to license page", app.page == 1)

            app.next_button.invoke()  # kabul etmeden
            check(
                "does not advance without accepting the license",
                app.page == 1 and DIALOGS and DIALOGS[-1][0] == "warning",
                str(DIALOGS[-1][:2]) if DIALOGS else "no warning",
            )

            app.accepted_license.set(True)
            app.next_button.invoke()
            check("advanced after accepting the license", app.page == 2)

            # Key capture: feed the same event the listener produces
            app.capture._on_hid(fake_hid_event())
            app._poll_capture()
            check("key captured", app.trigger is not None, str(app.trigger))
            check(
                "key identity correct",
                app.trigger == {
                    "type": "hid", "vid": 0x1915, "pid": 0x1025,
                    "usage_page": 0x000C, "usage": 0x00CF, "report_id": 2,
                },
                str(app.trigger),
            )
            check(
                "readable label shown",
                "Voice Command" in app.captured_label.get(),
                app.captured_label.get(),
            )

            app._on_return(None)  # Enter ile onay
            check("confirmed with Enter", app.page == 3)

            app.next_button.invoke()
            check("action page passed", app.page == 4)
            check("beep off by default", app.beep.get() is False)
            check("desktop shortcut on by default", app.create_shortcut.get() is True)

            app.next_button.invoke()
            check("moved to summary page", app.page == 5)
            check("button became 'Install'", app.next_button.cget("text") == "Install")

            app.next_button.invoke()
            state["install_started"] = True
        except Exception as exc:  # noqa: BLE001
            state["error"] = exc
            app.root.quit()
            return
        poll()

    def poll():
        if app.page == 7:
            state["done"] = True
            app.root.quit()
            return
        app.root.after(100, poll)

    app.root.after(250, driver)
    app.root.mainloop()

    app.capture.stop()
    if not app.root.winfo_exists():
        pass
    try:
        app.root.destroy()
    except Exception:
        pass
    return app, state


def test_install():
    print("\n=== 1. Setup wizard ===")
    app, state = run_wizard()
    check("flow without errors", state["error"] is None, repr(state["error"]))
    check("install finished (last page)", state["done"], f"page={app.page}")

    print("\n--- file and system verification ---")
    check("config.json written", os.path.isfile(cfg.CONFIG_PATH))
    data = cfg.load()
    bindings = data.get("bindings") or []
    check("config: one key stored", len(bindings) == 1, str(len(bindings)))
    first = bindings[0] if bindings else {}
    check(
        "config: key correct",
        (first.get("trigger") or {}).get("usage") == 0xCF,
        str(first.get("trigger")),
    )
    check(
        "config: action win+h",
        (first.get("action") or {}).get("hotkey") == "win+h",
        str(first.get("action")),
    )
    check("config: beep off", data.get("beep") is False)
    check("config: autostart on", data.get("autostart") is True)

    run_value = service.autostart_value()
    check("startup entry written", bool(run_value), str(run_value))
    check("startup command correct", run_value == service.autostart_command())

    menu_link = service.start_menu_shortcut_path()
    desktop_link = service.desktop_shortcut_path()
    check("Start Menu shortcut exists", bool(menu_link) and os.path.isfile(menu_link))
    check("desktop shortcut exists", bool(desktop_link) and os.path.isfile(desktop_link))

    entry = service.uninstall_entry()
    check("Apps & features entry exists", entry is not None, str(entry))
    if entry:
        check("entry name is Kelam", entry.get("DisplayName") == "Kelam")
        check(
            "uninstall command contains --uninstall",
            "--uninstall" in (entry.get("UninstallString") or ""),
            entry.get("UninstallString", ""),
        )
        check(
            "install location correct",
            os.path.normcase(entry.get("InstallLocation") or "")
            == os.path.normcase(service.BASE_DIR),
        )

    check("bridge running", service.is_running(), f"pid={service.running_pid()}")
    time.sleep(1.2)
    log_path = os.path.join(service.BASE_DIR, "bridge.log")
    log_text = ""
    if os.path.isfile(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            log_text = f.read()
    check("log: 'started' line", "started" in log_text)
    check("log: 'listening' line", "listening" in log_text)


def test_settings_window():
    """Settings window: key list, add, remove and Save."""
    print("\n=== 1b. Settings window ===")
    app = wizard_mod.SettingsWindow()
    app.root.update()

    check("title is 'Settings'", app.root.title() == "Settings", app.root.title())
    check("no wizard button", not hasattr(app, "next_button"))
    check("Save button", app.save_button.cget("text") == "Save")
    check("one key listed", len(app.bindings) == 1, str(len(app.bindings)))
    check(
        "key correct",
        (app.bindings[0].get("trigger") or {}).get("usage") == 0xCF,
        str(app.bindings[0].get("trigger")),
    )

    # add a new key
    app._add_key()
    check("capture started", app.listening is True)
    app.capture._on_hid(_hid_event(0x0224, "022402"))
    app._poll_capture()
    check("new key added", len(app.bindings) == 2, str(len(app.bindings)))
    check(
        "second key correct",
        (app.bindings[1].get("trigger") or {}).get("usage") == 0x0224,
        str(app.bindings[1].get("trigger")),
    )

    # remove the selected one
    app.selected = 1
    app._remove_selected()
    check("key removed", len(app.bindings) == 1, str(len(app.bindings)))

    # save
    app.root.after(300, app._save)
    app.root.after(30000, app.root.quit)
    app.root.mainloop()
    time.sleep(1.5)

    check("window closed after save", not _window_alive(app))
    check("bridge running", service.is_running())
    saved = cfg.load().get("bindings") or []
    check("config has a single key", len(saved) == 1, str(len(saved)))
    check("key preserved", (saved[0].get("trigger") or {}).get("usage") == 0xCF)


def test_multi_key():
    """With two keys saved the bridge must listen to both."""
    print("\n=== 1c. Multiple keys ===")
    app = wizard_mod.SettingsWindow()
    app.root.update()

    app._add_key()
    app.capture._on_hid(_hid_event(0x0224, "022402"))
    app._poll_capture()
    check("two keys present", len(app.bindings) == 2, str(len(app.bindings)))

    app.root.after(300, app._save)
    app.root.after(30000, app.root.quit)
    app.root.mainloop()
    time.sleep(2.0)

    saved = cfg.load().get("bindings") or []
    check("config has two keys", len(saved) == 2, str(len(saved)))
    check("bridge running", service.is_running())

    log_path = os.path.join(service.BASE_DIR, "bridge.log")
    log_text = ""
    if os.path.isfile(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            log_text = f.read()
    check("log lists both keys", "[2]" in log_text, log_text[-120:])

    # back to a single key for the following tests
    data = cfg.load()
    data["bindings"] = [b for b in data["bindings"] if (b.get("trigger") or {}).get("usage") == 0xCF]
    cfg.save(data)
    service.restart()
    time.sleep(1.5)


def _hid_event(usage, raw):
    return {
        "type": "hid", "vid": 0x1915, "pid": 0x1025,
        "usage_page": 0x000C, "usage": usage, "report_id": 2,
        "report_len": 3, "path": "test", "raw": raw, "time": time.time(),
    }


def _window_alive(app):
    try:
        return bool(app.root.winfo_exists())
    except Exception:
        return False


def test_uninstall():
    print("\n=== 2. Uninstall (removal wizard) ===")
    check("bridge running before uninstall", service.is_running())

    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    dialog = wizard_mod.UninstallWizard(root)
    check("removal wizard opened", bool(dialog.win.winfo_exists()))
    dialog._start()

    def poll():
        if dialog.removed:
            root.quit()
            return
        root.after(120, poll)

    root.after(250, poll)
    root.mainloop()
    print("   silinenler:", ", ".join(dialog.removed))
    check("removal finished", bool(dialog.removed) and not any(
        r.startswith("HATA") for r in dialog.removed
    ), str(dialog.removed[:2]))
    try:
        root.destroy()
    except Exception:
        pass

    check("bridge stopped", not service.is_running())
    check("startup entry deleted", service.autostart_value() is None)
    check("Apps & features entry deleted", not service.uninstall_registered())
    check(
        "Start Menu shortcut deleted",
        not os.path.isfile(service.start_menu_shortcut_path() or ""),
    )
    check(
        "desktop shortcut deleted",
        not os.path.isfile(service.desktop_shortcut_path() or ""),
    )
    for name in (
        "config.json", "bridge.log", "bridge.log.1", "bridge.out", "bridge.pid",
    ):
        check(f"{name} deleted", not os.path.exists(os.path.join(service.BASE_DIR, name)))
    check(
        "__pycache__ deleted",
        not os.path.isdir(os.path.join(service.BASE_DIR, "__pycache__")),
    )
    check(
        "code files preserved",
        os.path.isfile(os.path.join(service.BASE_DIR, "wizard.py")),
    )


def main():
    print("Kelam end-to-end test")
    print("=" * 60)
    clear_previous()
    test_install()
    test_settings_window()
    test_multi_key()
    test_uninstall()

    failed = [r for r in RESULTS if not r[1]]
    print("\n" + "=" * 60)
    print(
        f"TOPLAM {len(RESULTS)} kontrol | "
        f"PASS {len(RESULTS) - len(failed)} | FAIL {len(failed)}"
    )
    for name, _ok, detail in failed:
        print(f"  FAIL -> {name} {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
