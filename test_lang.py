"""Smoke test: language page, switching, and that data goes to %APPDATA%."""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import config  # noqa: E402
import i18n  # noqa: E402
import paths  # noqa: E402
import wizard  # noqa: E402

CHECKS = 0


def check(name: str, condition: bool, extra: str = "") -> None:
    global CHECKS
    if condition:
        CHECKS += 1
        print(f"  [OK]   {name}")
    else:
        print(f"  [FAIL] {name} {extra}")
        raise SystemExit(1)


def main() -> int:
    print("\n Paths")
    check("data dir is %APPDATA%\\Kelam", paths.BASE_DIR.lower().startswith(os.environ["APPDATA"].lower()), paths.BASE_DIR)
    check("data dir != program dir", paths.BASE_DIR.lower() != paths.APP_DIR.lower(), paths.APP_DIR)
    check("config lives in the data dir", config.CONFIG_PATH.startswith(paths.BASE_DIR), config.CONFIG_PATH)

    print("\n Wizard")
    app = wizard.SetupWizard()
    app.root.withdraw()
    app.root.update()
    check("language page exists", "language" in app._sequence, str(app._sequence))
    check("language page is second", app._sequence[1] == "language", app._sequence[1])

    index = app._sequence.index("language")
    app._show_page(index)
    app.root.update()
    check("wizard starts in English", i18n.get_lang() == "en", i18n.get_lang())

    app._set_language("tr")
    app.root.update()
    check("switched to Turkish", i18n.get_lang() == "tr")
    saved = config.load().get("language")
    check("choice saved to config.json", saved == "tr", str(saved))

    app._show_page(app._sequence.index("license"))
    app.root.update()
    texts = []
    for child in app.content.winfo_children():
        try:
            texts.append(str(child.cget("text")))
        except Exception:  # noqa: BLE001
            pass
    check("license page is Turkish", any("Lisans" in t for t in texts), str(texts[:3]))

    app._set_language("en")
    app.root.update()
    check("back to English", i18n.get_lang() == "en")

    app.capture.stop()
    app.root.destroy()

    print(f"\n WIZARD LANGUAGE TEST PASSED ({CHECKS} checks)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
