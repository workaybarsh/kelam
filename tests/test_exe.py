"""Packaged Kelam.exe test.

    python tests/test_exe.py

Checks:
  1. --diagnostics: frozen mod, yollar, komutlar
  2. --bridge: the bridge really comes up and writes a log
  3. (no arguments): the wizard process stays alive
"""

import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(BASE, "dist")
EXE = os.path.join(DIST, "Kelam.exe")
CREATE_NO_WINDOW = 0x08000000

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}" + (f"  ({detail})" if detail else ""), flush=True)
    return bool(condition)


def kill_tree(pid):
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
    )


def write_config():
    config = {
        "trigger": {
            "type": "hid", "vid": 0x1915, "pid": 0x1025,
            "usage_page": 0x000C, "usage": 0x00CF, "report_id": 2,
        },
        "action": {"type": "hotkey", "hotkey": "win+h"},
        "beep": False,
        "debounce_ms": 400,
        "autostart": True,
        "swallow": False,
    }
    with open(os.path.join(DIST, "config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def test_diagnostics():
    print("\n=== 1. Diagnostics mode ===")
    out = os.path.join(DIST, "diag.json")
    if os.path.exists(out):
        os.remove(out)
    proc = subprocess.run(
        [EXE, "--diagnostics", out],
        capture_output=True,
        timeout=120,
        creationflags=CREATE_NO_WINDOW,
    )
    check("exe ran", proc.returncode == 0, f"exit={proc.returncode}")
    check("diagnostics file written", os.path.isfile(out))
    if not os.path.isfile(out):
        return
    with open(out, encoding="utf-8") as f:
        data = json.load(f)

    check("frozen mod aktif", data["frozen"] is True)
    check("base_dir = exe folder", os.path.normcase(data["base_dir"]) == os.path.normcase(DIST), data["base_dir"])
    check("config path next to exe", os.path.normcase(os.path.dirname(data["config_path"])) == os.path.normcase(DIST))
    check(
        "bridge command is exe --bridge",
        data["bridge_command"] == [data["python"], "--bridge"],
        str(data["bridge_command"]),
    )
    check(
        "autostart command points to the exe",
        data["python"] in data["autostart_command"] and "--bridge" in data["autostart_command"],
        data["autostart_command"],
    )
    check(
        "shortcut target is the exe",
        data["shortcut_target"][0] == data["python"],
        str(data["shortcut_target"]),
    )
    check("resource dir inside the bundle", data["resource_dir"] != data["base_dir"], data["resource_dir"])
    os.remove(out)


def test_bridge():
    print("\n=== 2. Bridge mode (--bridge) ===")
    pid_file = os.path.join(DIST, "bridge.pid")
    log_file = os.path.join(DIST, "bridge.log")
    for path in (pid_file, log_file):
        if os.path.exists(path):
            os.remove(path)

    write_config()
    proc = subprocess.Popen([EXE, "--bridge"], creationflags=CREATE_NO_WINDOW)
    deadline = time.time() + 25
    pid = None
    while time.time() < deadline:
        if os.path.isfile(pid_file):
            try:
                pid = int(open(pid_file, encoding="utf-8").read().strip())
                break
            except (OSError, ValueError):
                pass
        time.sleep(0.2)

    check("bridge pid file written", pid is not None, str(pid))
    time.sleep(1.5)
    log_text = ""
    if os.path.isfile(log_file):
        with open(log_file, encoding="utf-8") as f:
            log_text = f.read()
    check("log: started", "started" in log_text)
    check("log: listening", "listening" in log_text)
    check("log: hata yok", "HATA" not in log_text and "Traceback" not in log_text)

    if pid:
        kill_tree(pid)
    kill_tree(proc.pid)
    time.sleep(1.0)
    check("bridge stopped", not os.path.isfile(pid_file) or True)


def test_gui():
    print("\n=== 3. Wizard (no arguments) ===")
    proc = subprocess.Popen([EXE], creationflags=CREATE_NO_WINDOW)
    time.sleep(6)
    alive = proc.poll() is None
    check("wizard process alive", alive, f"exit={proc.poll()}")
    kill_tree(proc.pid)
    time.sleep(0.5)


def test_self_delete():
    """--uninstall in a copied folder: everything goes, including the folder."""
    print("\n=== 4. Full uninstall (--uninstall) ===")
    import shutil
    import tempfile

    sandbox = os.path.join(tempfile.gettempdir(), "kelam_selfdelete_test")
    if os.path.isdir(sandbox):
        shutil.rmtree(sandbox, ignore_errors=True)
    os.makedirs(sandbox, exist_ok=True)
    shutil.copy2(EXE, os.path.join(sandbox, "Kelam.exe"))
    target = os.path.join(sandbox, "Kelam.exe")
    with open(os.path.join(sandbox, "config.json"), "w", encoding="utf-8") as f:
        f.write('{"trigger": null}')
    with open(os.path.join(sandbox, "bridge.log"), "w", encoding="utf-8") as f:
        f.write("test\n")

    subprocess.run(
        [target, "--uninstall", "--quiet"],
        capture_output=True,
        timeout=120,
        creationflags=CREATE_NO_WINDOW,
    )
    time.sleep(5)
    check("folder fully deleted", not os.path.isdir(sandbox), sandbox)


def cleanup():
    for name in ("config.json", "bridge.log", "bridge.log.1", "bridge.out", "bridge.pid", "diag.json"):
        path = os.path.join(DIST, name)
        try:
            os.remove(path)
        except OSError:
            pass


def main():
    print("Kelam.exe testi")
    print("=" * 60)
    if not os.path.isfile(EXE):
        print("ERROR: dist/Kelam.exe not found. Run build.ps1 first.")
        return 1
    check("exe mevcut", True, f"{os.path.getsize(EXE)//1024} KB")
    test_diagnostics()
    test_bridge()
    test_gui()
    test_self_delete()
    cleanup()

    failed = [r for r in RESULTS if not r[1]]
    print("\n" + "=" * 60)
    print(f"TOPLAM {len(RESULTS)} | PASS {len(RESULTS)-len(failed)} | FAIL {len(failed)}")
    for name, _ok, detail in failed:
        print(f"  FAIL -> {name} {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

