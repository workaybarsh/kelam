"""Verify the packaged exe keeps its own folder clean and stores data in %APPDATA%."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

EXE = Path(__file__).resolve().parent / "dist" / "Kelam.exe"
APPDATA_DIR = Path(os.environ["APPDATA"]) / "Kelam"
CHECKS = 0


def check(name: str, condition: bool, extra: str = "") -> None:
    global CHECKS
    if condition:
        CHECKS += 1
        print(f"  [OK]   {name}")
    else:
        print(f"  [FAIL] {name} {extra}")
        raise SystemExit(1)


def snapshot(folder: Path) -> set[str]:
    return {p.name for p in folder.iterdir()}


def main() -> int:
    check("exe exists", EXE.is_file(), str(EXE))

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        work = Path(tmp)
        exe = work / "Kelam.exe"
        shutil.copy2(EXE, exe)
        before = snapshot(work)

        print("\n --diagnostics")
        out = work.parent / "kelam_diag.json"
        result = subprocess.run(
            [str(exe), "--diagnostics", str(out)],
            cwd=str(work),
            capture_output=True,
            timeout=180,
        )
        check("diagnostics exit code 0", result.returncode == 0, str(result.returncode))
        check("diagnostics file written", out.is_file())
        data = json.loads(out.read_text("utf-8"))
        check("base_dir is %APPDATA%\\Kelam", data["base_dir"].lower() == str(APPDATA_DIR).lower(), data["base_dir"])
        check("config path is in %APPDATA%", data["config_path"].lower().startswith(str(APPDATA_DIR).lower()), data["config_path"])
        out.unlink(missing_ok=True)

        after = snapshot(work)
        added = after - before
        check("no files created next to the exe", not added, str(added))

        print("\n GUI run (6 s)")
        proc = subprocess.Popen([str(exe)], cwd=str(work))
        time.sleep(6)
        subprocess.run(
            ['taskkill', '/IM', 'Kelam.exe', '/F', '/T'],
            capture_output=True,
            creationflags=0x08000000,
        )
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        time.sleep(2)
        after_gui = snapshot(work)
        added = after_gui - before
        check("still no files next to the exe", not added, str(added))

    print("\n %APPDATA% content")
    check("settings folder exists", APPDATA_DIR.is_dir(), str(APPDATA_DIR))
    names = sorted(p.name for p in APPDATA_DIR.iterdir())
    print("     " + ", ".join(names))
    check("config.json lives there", "config.json" in names, str(names))
    check(
        "no config.json left in the program folder",
        not (Path(__file__).resolve().parent / "config.json").exists(),
    )

    print(f"\n EXE CLEAN TEST PASSED ({CHECKS} checks)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
