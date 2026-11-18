"""Setup-specific checks: language page and the 'Remove installation' button.

Run:  python test_setup.py
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import config  # noqa: E402
import i18n  # noqa: E402
import wizard as wizard_mod  # noqa: E402

CHECKS = 0


def check(name: str, condition: bool, extra: str = "") -> None:
    global CHECKS
    if condition:
        CHECKS += 1
        print(f"  [OK]   {name}")
    else:
        print(f"  [FAIL] {name} {extra}")
        raise SystemExit(1)


def find_buttons(widget, found=None):
    found = [] if found is None else found
    try:
        if widget.winfo_class() in ("TButton", "Button"):
            found.append(widget)
    except Exception:  # noqa: BLE001
        pass
    for child in widget.winfo_children():
        find_buttons(child, found)
    return found


def find_widgets(widget, class_name: str, found=None):
    found = [] if found is None else found
    try:
        if widget.winfo_class() == class_name:
            found.append(widget)
    except Exception:  # noqa: BLE001
        pass
    for child in widget.winfo_children():
        find_widgets(child, class_name, found)
    return found


def widget_texts(widget) -> list[str]:
    texts = []
    for child in widget.winfo_children():
        try:
            texts.append(str(child.cget("text")))
        except Exception:  # noqa: BLE001
            pass
        texts.extend(widget_texts(child))
    return texts


def main() -> int:
    data = config.load()
    data["language"] = "en"
    config.save(data)
    i18n.set_lang("en")

    print("\n Setup: language page")
    app = wizard_mod.SetupWizard()
    app.root.withdraw()
    app.root.update()

    check("language page is the second step", app._sequence[1] == "language", str(app._sequence[:3]))
    app._show_page(1)
    app.root.update()

    lists = find_widgets(app.content, "Listbox")
    check("language list rendered", bool(lists), str([w.winfo_class() for w in app.content.winfo_children()]))
    items = [lists[0].get(i) for i in range(lists[0].size())] if lists else []
    check("list has English and Turkish", any("English" in i for i in items) and any("Türkçe" in i for i in items), str(items))

    print("\n Setup: switching language")
    app._set_language("tr")
    app.root.update()
    check("language switched to Turkish", i18n.get_lang() == "tr")
    check("choice written to config.json", config.load().get("language") == "tr")
    texts = widget_texts(app.content)
    check("page redrawn in Turkish", any("Dil" in t for t in texts), str(texts[:4]))

    app._set_language("en")
    app.root.update()
    check("switched back to English", i18n.get_lang() == "en")

    print("\n Setup: 'Remove installation' button")
    app._show_page(0)
    app.root.update()
    buttons = {str(b.cget("text")): b for b in find_buttons(app.content)}
    check("button exists on the welcome page", "Remove installation" in buttons, str(list(buttons)))

    calls = {"created": 0, "removed": True}

    class FakeUninstall:
        def __init__(self, parent):
            calls["created"] += 1
            self.removed = calls["removed"]

        def run(self):
            calls["ran"] = True

    original = wizard_mod.UninstallWizard
    wizard_mod.UninstallWizard = FakeUninstall
    try:
        buttons["Remove installation"].invoke()
        check("opens the uninstall wizard", calls["created"] == 1, str(calls))
        check("uninstall wizard ran", calls.get("ran") is True)
        destroyed = False
        try:
            destroyed = not app.root.winfo_exists()
        except Exception:  # noqa: BLE001
            destroyed = True
        check("wizard closes after removal", destroyed)
    finally:
        wizard_mod.UninstallWizard = original

    print("\n Setup: the choice survives a restart")
    app2 = wizard_mod.SetupWizard()
    app2.root.withdraw()
    app2.root.update()
    check("remembered on the next start", i18n.get_lang() == config.load().get("language"))
    app2.capture.stop()
    app2.root.destroy()

    print(f"\n SETUP TEST PASSED ({CHECKS} checks)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
