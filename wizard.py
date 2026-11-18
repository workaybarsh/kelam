"""Kelam setup wizard.

Flow (same skeleton as the reference SetupWizard):
    Welcome -> License -> Teach key -> Action -> Extra tasks
    -> Ready -> Installing -> Done

Uninstall: a separate removal wizard; it stops the bridge, then deletes the
startup entry, shortcuts, settings and logs, leaving no trace behind.
"""

from __future__ import annotations

import os
import queue
import shutil
import threading
import time
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

import config as cfg
import hotkey
import keyhook
import paths
import service
import trigger
import i18n
from i18n import tr

BRAND_BG = "#10243a"
BRAND_BG2 = "#1d4a6b"
BRAND_FG = "#eaf3fb"
ACCENT = "#2f9bd6"


def paint_brand(canvas, mode="install", version=None):
    """Draws the left brand panel (over the photo when available)."""
    height, width = 500, 190
    version = version or service.VERSION

    image = None
    side_path = os.path.join(paths.RESOURCE_DIR, "assets", "side.png")
    if os.path.isfile(side_path):
        try:
            image = tk.PhotoImage(file=side_path)
            canvas.create_image(0, 0, image=image, anchor="nw")
        except tk.TclError:
            image = None

    if image is None:  # fall back to a gradient
        start, end = (0x10, 0x24, 0x3A), (0x1D, 0x4A, 0x6B)
        for y in range(height):
            ratio = y / max(1, height - 1)
            color = "#%02x%02x%02x" % tuple(
                int(start[i] + (end[i] - start[i]) * ratio) for i in range(3)
            )
            canvas.create_line(0, y, width, y, fill=color)

    def text(x, y, value, fill, font, anchor="nw", justify="left"):
        # 1 px shadow for readability
        canvas.create_text(
            x + 1, y + 1, text=value, anchor=anchor, fill="#000000",
            font=font, justify=justify,
        )
        canvas.create_text(
            x, y, text=value, anchor=anchor, fill=fill, font=font, justify=justify,
        )

    text(22, 34, "Kelam", BRAND_FG, ("Segoe UI", 26, "bold"))
    canvas.create_line(22, 86, 104, 86, fill=ACCENT, width=2)

    # Texts sit on the hand so the cat's face stays visible
    text(20, 300, "Voice typing with\nyour remote", "#e6f0f8", ("Segoe UI", 11))
    steps = (
        "1. Teach the key\n2. Pick an action\n3. Install and use"
        if mode == "install"
        else "1. Change the key\n2. Adjust options\n3. Save"
    )
    text(20, 366, steps, "#cfe0ee", ("Segoe UI", 10))
    text(20, 468, version, "#8fb4cd", ("Segoe UI", 9))
    return image


class CaptureSession:
    """Capture session that listens for remote buttons while the wizard is open."""

    def __init__(self):
        self.events: list[dict] = []
        self.lock = threading.Lock()
        self.stop_flag = threading.Event()
        self._threads: list[threading.Thread] = []
        self._key_listener: keyhook.KeyboardListener | None = None
        self._active = False

    def start(self):
        if self._active:
            return
        self._active = True
        self.stop_flag = threading.Event()
        with self.lock:
            self.events.clear()
        self._threads = trigger.capture_listeners(self._on_hid, self.stop_flag)
        self._key_listener = keyhook.KeyboardListener(self._on_key)
        self._key_listener.start()

    def stop(self):
        if not self._active:
            return
        self._active = False
        self.stop_flag.set()
        if self._key_listener:
            self._key_listener.stop()
            self._key_listener = None

    def _on_hid(self, event):
        with self.lock:
            self.events.append(event)

    def _on_key(self, event):
        if keyhook.is_modifier(event["vk"]) or event["vk"] == 0x0D:
            return False
        with self.lock:
            self.events.append(event)
        return False

    def snapshot(self):
        with self.lock:
            return list(self.events)

    def last_trigger(self):
        """Picks the trigger to confirm, preferring a keyboard key when present."""
        events = self.snapshot()
        key_events = [e for e in events if e["type"] == "key"]
        if key_events:
            ev = key_events[-1]
            return {
                "type": "key",
                "vk": ev["vk"],
                "scan": ev["scan"],
                "extended": ev["extended"],
                "name": cfg.vk_name(ev["vk"]),
            }
        hid_events = [e for e in events if e["type"] == "hid"]
        if not hid_events:
            return None
        ev = hid_events[-1]
        return {
            "type": "hid",
            "vid": ev["vid"],
            "pid": ev["pid"],
            "usage_page": ev["usage_page"],
            "usage": ev["usage"],
            "report_id": ev["report_id"],
        }


class UiQueue:
    """Safe access to Tk from background threads.

    Tk is not thread-safe: calling widgets/after directly from a worker thread
    can deadlock. Workers only enqueue; the main thread applies.
    """

    def __init__(self, root):
        self.root = root
        self.queue = queue.Queue()
        self._after_id = None
        try:
            root.bind("<Destroy>", self._on_destroy, add="+")
        except tk.TclError:
            pass
        self._poll()

    def _on_destroy(self, event):
        if event.widget is self.root:
            self.stop()

    def stop(self):
        """Bekleyen zamanlayıcıyı iptal eder (pencere kapanırken)."""
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _poll(self):
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        try:
            while True:
                fn, args = self.queue.get_nowait()
                try:
                    fn(*args)
                except Exception:  # noqa: BLE001
                    pass
        except queue.Empty:
            pass
        try:
            self._after_id = self.root.after(60, self._poll)
        except tk.TclError:
            pass

    def post(self, fn, *args):
        self.queue.put((fn, args))


class SetupWizard:
    """Two modes: 'install' (first run) and 'settings' (edit existing config)."""

    def __init__(self, mode: str | None = None):
        self.root = tk.Tk()
        self.root.geometry("760x540")
        self.root.minsize(760, 540)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)

        try:
            i18n.set_lang(cfg.load().get("language", "en"))
        except (OSError, ValueError):
            i18n.set_lang("en")

        self._was_running = service.is_running()
        installed = os.path.isfile(cfg.CONFIG_PATH) or self._was_running
        self.mode = "install"  # settings live in a separate window (SettingsWindow)
        self.root.title(
            tr("Settings") if self.mode == "settings" else tr("Kelam Setup Wizard")
        )

        self._sequence = [
            "welcome", "language", "license", "capture", "action", "tasks", "ready",
            "progress", "finish",
        ]
        self.page = 0
        self.current = self._sequence[0]

        self.capture = CaptureSession()
        self.accepted_license = tk.BooleanVar(value=self.mode == "settings")
        self.create_shortcut = tk.BooleanVar(value=True)
        self.launch_after_install = tk.BooleanVar(value=True)
        self.autostart = tk.BooleanVar(value=True)
        self.beep = tk.BooleanVar(value=False)
        self.action_mode = tk.StringVar(value="winh")
        self.custom_hotkey = tk.StringVar(value="ctrl+alt+d")

        settings = cfg.load()
        saved = settings.get("trigger")
        self.saved_trigger = saved
        self.trigger = saved
        self.captured_label = tk.StringVar(
            value=cfg.describe_trigger(saved) if saved else tr("No key captured yet")
        )

        if self.mode == "settings":
            self.autostart.set(bool(settings.get("autostart", True)))
            self.beep.set(bool(settings.get("beep", False)))
            hotkey_value = (settings.get("action") or {}).get("hotkey", "win+h")
            if hotkey_value and hotkey_value.lower() != "win+h":
                self.action_mode.set("custom")
                self.custom_hotkey.set(hotkey_value)
            desktop_link = service.desktop_shortcut_path()
            self.create_shortcut.set(bool(desktop_link and os.path.isfile(desktop_link)))

        self._installed = False
        self._hotkey_capture = False
        self._hotkey_listener: keyhook.KeyboardListener | None = None
        self._warnings: list[str] = []

        icon_path = os.path.join(paths.RESOURCE_DIR, "assets", "kelam.ico")
        if os.path.isfile(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except tk.TclError:
                pass

        # Keep the bridge from grabbing the key while the wizard is open.
        service.stop()

        self.ui = UiQueue(self.root)
        self._build_layout()
        self._show_page(0)

    # ---------------------------------------------------------------- layout
    def _build_layout(self):
        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True)

        self.brand = tk.Canvas(body, width=190, highlightthickness=0, bg=BRAND_BG)
        self.brand.pack(side="left", fill="y")
        self._paint_brand()

        self.content = ttk.Frame(body, padding=(24, 18))
        self.content.pack(side="left", fill="both", expand=True)

        self.navigation = ttk.Frame(self.root, padding=(12, 10))
        self.navigation.pack(fill="x", side="bottom")
        # Right to left: Cancel | Next | Back
        self.cancel_button = ttk.Button(self.navigation, text=tr("Cancel"), command=self._cancel)
        self.cancel_button.pack(side="right")
        self.next_button = ttk.Button(self.navigation, text=tr("Next"), command=self._next)
        self.next_button.pack(side="right", padx=(8, 0))
        self.back_button = ttk.Button(self.navigation, text=tr("Back"), command=self._back)
        self.back_button.pack(side="right", padx=(8, 0))

        self.root.bind("<Return>", self._on_return)
        self.root.bind("<Escape>", lambda _e: self._cancel())

    def _paint_brand(self):
        self._side_img = paint_brand(self.brand, self.mode)

    def _clear_content(self):
        for child in self.content.winfo_children():
            child.destroy()

    def _heading(self, title: str, description: str):
        ttk.Label(self.content, text=title, font=("Segoe UI", 15, "bold")).pack(
            anchor="w"
        )
        ttk.Label(self.content, text=description, wraplength=500).pack(
            anchor="w", pady=(6, 14)
        )

    # ----------------------------------------------------------------- pages
    def _show_page(self, page: int):
        self.page = page
        self.current = self._sequence[page]
        self._clear_content()
        self.back_button.configure(state="normal" if page else "disabled")
        self.next_button.configure(text=tr("Next"), command=self._next, state="normal")
        pages: dict[str, Callable[[], None]] = {
            "welcome": self._page_welcome,
            "language": self._page_language,
            "license": self._page_license,
            "capture": self._page_capture,
            "action": self._page_action,
            "tasks": self._page_tasks,
            "ready": self._page_ready,
            "progress": self._page_installing,
            "finish": self._page_finish,
        }
        if self.current == "capture":
            self.capture.start()
        else:
            self.capture.stop()
        pages[self.current]()

    def _load_logo(self, size=72):
        """Loads assets/logo.png as a Tk image (None when missing)."""
        path = os.path.join(paths.RESOURCE_DIR, "assets", "logo.png")
        if not os.path.isfile(path):
            return None
        try:
            image = tk.PhotoImage(file=path)
        except tk.TclError:
            return None
        if size < image.width():
            image = image.subsample(max(1, round(image.width() / size)))
        return image

    def _title_with_logo(self, title: str, size: int = 72):
        row = ttk.Frame(self.content)
        row.pack(fill="x")
        logo = self._load_logo(size)
        if logo is not None:
            self._logo_ref = logo  # keep a reference so it is not garbage collected
            ttk.Label(row, image=logo).pack(side="right", padx=(10, 0))
        ttk.Label(row, text=title, font=("Segoe UI", 17, "bold")).pack(
            side="left", anchor="w"
        )
        return row

    def _page_welcome(self):
        if self.mode == "settings":
            self._title_with_logo(tr("Settings"))
            ttk.Label(
                self.content,
                text=(
                    "The installation is running. Use the steps below to change the remote key, "
                    "the action it triggers, and the other options.\n\n"
                    "When you save, the bridge restarts with the new settings."
                ),
                justify="left", wraplength=500,
            ).pack(anchor="w", pady=(12, 10))

            info = ttk.LabelFrame(self.content, text=tr("Current state"), padding=12)
            info.pack(fill="x", pady=(4, 10))
            settings = cfg.load()
            lines = [
                f"Remote key  : {cfg.describe_trigger(settings.get('trigger'))}",
                f"Action      : {cfg.describe_action(settings.get('action'))}",
                f"Bridge      : {tr('running') if self._was_running else tr('stopped')}",
                f"Autostart   : {'on' if settings.get('autostart') else tr('off')}",
            ]
            ttk.Label(info, text="\n".join(lines), justify="left").pack(anchor="nw")

            row = ttk.Frame(self.content)
            row.pack(fill="x", pady=(2, 0))
            ttk.Button(
                row, text=tr("Remove Kelam from this computer"), command=self._uninstall
            ).pack(side="left")
            ttk.Label(
                row,
                text=tr("  Removes the bridge, startup entry, shortcuts and settings."),
                foreground="#666",
            ).pack(side="left")
            return

        self._title_with_logo(tr("Welcome to Kelam"))
        ttk.Label(
            self.content,
            text=(
                "This wizard connects the microphone button on your remote to "
                "Windows voice typing. After setup you can dictate into any text "
                "field where the cursor is.\n\n"
                "Setup makes no system-wide changes: it only adds files in this "
                "folder, one startup entry and one shortcut."
            ),
            justify="left", wraplength=500,
        ).pack(anchor="w", pady=(12, 10))

        frame = ttk.LabelFrame(self.content, text=tr("What you need"), padding=12)
        frame.pack(fill="x", pady=(6, 12))
        ttk.Label(
            frame,
            text=(
                "• A 2.4G or Bluetooth remote with a microphone button\n"
                "• Windows 10/11 and internet (voice typing runs in the cloud)\n"
                "• Python 3.9+ (already installed on this PC)"
            ),
            justify="left",
        ).pack(anchor="w")

        if service.is_running() or os.path.isfile(cfg.CONFIG_PATH):
            row = ttk.Frame(self.content)
            row.pack(fill="x", pady=(6, 0))
            ttk.Button(row, text=tr("Remove installation"), command=self._uninstall).pack(
                side="left"
            )
            ttk.Label(
                row, text=tr("  Removes the existing installation completely."), foreground="#666"
            ).pack(side="left")

        if self.saved_trigger:
            ttk.Label(
                self.content,
                text=(
                    "Existing settings found — key: "
                    f"{cfg.describe_trigger(self.saved_trigger)}\n"
                    "Press Next to change them."
                ),
                foreground="#12506f",
                justify="left",
            ).pack(anchor="w", pady=(12, 0))

    def _page_language(self):
        self._heading(
            tr("Select language"),
            tr("Choose the language for the wizard and for the application."),
        )
        frame = ttk.Frame(self.content)
        frame.pack(fill="x", pady=(6, 0))
        listbox = tk.Listbox(
            frame,
            height=2,
            font=("Segoe UI", 12),
            activestyle="none",
            exportselection=False,
            cursor="hand2",
        )
        for label in i18n.LANGUAGES.values():
            listbox.insert("end", f"   {label}")
        codes = list(i18n.LANGUAGES.keys())
        current = i18n.get_lang()
        listbox.selection_set(codes.index(current) if current in codes else 0)
        listbox.pack(fill="x")
        listbox.bind(
            "<<ListboxSelect>>",
            lambda _event=None: self._set_language(codes[listbox.curselection()[0]])
            if listbox.curselection()
            else None,
        )
        ttk.Label(
            self.content,
            text=tr("You can change this later from Settings."),
            foreground="#4b5563",
        ).pack(anchor="w", pady=(10, 0))

    def _set_language(self, code: str):
        """Apply and remember the language, then redraw the current page."""
        i18n.set_lang(code)
        try:
            data = cfg.load()
            data["language"] = i18n.get_lang()
            cfg.save(data)
        except (OSError, ValueError):
            pass
        self.root.title(tr("Kelam Setup Wizard"))
        self.back_button.configure(text=tr("Back"))
        self.next_button.configure(text=tr("Next"))
        self.cancel_button.configure(text=tr("Cancel"))
        self._show_page(self.page)

    def _page_license(self):
        self._heading(
            tr("License agreement"),
            tr("You must accept the MIT license to continue."),
        )
        text = tk.Text(self.content, height=14, wrap="word", padx=8, pady=8)
        license_path = os.path.join(paths.RESOURCE_DIR, "LICENSE")
        try:
            with open(license_path, "r", encoding="utf-8") as f:
                license_text = f.read()
        except OSError:
            license_text = tr("MIT License (LICENSE file not found)")
        text.insert("1.0", license_text)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)
        ttk.Checkbutton(
            self.content, text=tr("I accept the agreement"),
            variable=self.accepted_license,
        ).pack(anchor="w", pady=(10, 0))

    def _page_capture(self):
        if self.saved_trigger:
            description = (
                f"Current key: {cfg.describe_trigger(self.saved_trigger)}.\n"
                "Press a new key to change it, or press Next to keep it."
            )
        else:
            description = (
                "Press the microphone button on the remote once. When the key "
                "appears, confirm with Enter."
            )
        self._heading(tr("Teach the remote key"), description)
        box = ttk.LabelFrame(self.content, text=tr("Selected key"), padding=12)
        box.pack(fill="x")
        self.captured_label.set(
            cfg.describe_trigger(self.trigger)
            if self.trigger
            else tr("No key captured yet")
        )
        self.captured_value = ttk.Label(
            box, textvariable=self.captured_label,
            font=("Consolas", 11), foreground="#12506f",
        )
        self.captured_value.pack(anchor="w")

        ttk.Label(self.content, text=tr("Recent events:")).pack(anchor="w", pady=(12, 4))
        self.event_list = tk.Listbox(self.content, height=6, activestyle="none")
        self.event_list.pack(fill="both", expand=True)

        row = ttk.Frame(self.content)
        row.pack(fill="x", pady=(10, 0))
        ttk.Button(row, text=tr("Reset"), command=self._reset_capture).pack(side="left")
        ttk.Label(row, text=tr("   Enter = confirm"), foreground="#666").pack(side="left")

        self._poll_capture()

    def _reset_capture(self):
        with self.capture.lock:
            self.capture.events.clear()
        try:
            self.event_list.delete(0, "end")
        except (AttributeError, tk.TclError):
            pass
        self.trigger = self.saved_trigger
        self.captured_label.set(
            cfg.describe_trigger(self.trigger)
            if self.trigger
            else tr("No key captured yet")
        )

    def _poll_capture(self):
        if self.current != "capture":
            return
        events = self.capture.snapshot()
        self.event_list.delete(0, "end")
        for ev in events[-6:]:
            self.event_list.insert("end", self._describe_event(ev))
        candidate = self.capture.last_trigger()
        if candidate:
            self.trigger = candidate
            self.captured_label.set(cfg.describe_trigger(candidate))
        self.root.after(180, self._poll_capture)

    @staticmethod
    def _describe_event(ev):
        if ev["type"] == "key":
            return f"klavye  vk=0x{ev['vk']:02X}  ({cfg.vk_name(ev['vk'])})"
        return (
            f"hid     page=0x{ev['usage_page']:04X} usage=0x{ev['usage']:04X} "
            f"report={ev['report_id']} raw={ev['raw']}"
        )

    def _page_action(self):
        self._heading(
            tr("What should the key do?"),
            tr("Which action should the microphone button trigger?"),
        )
        ttk.Radiobutton(
            self.content, value="winh", variable=self.action_mode,
            text=tr("Windows voice typing (Win+H) — recommended"),
        ).pack(anchor="w", pady=(4, 2))
        ttk.Label(
            self.content,
            text=tr("   Runs in the cloud, free, no load on this PC."),
            foreground="#666",
        ).pack(anchor="w", pady=(0, 12))

        ttk.Radiobutton(
            self.content, value="custom", variable=self.action_mode,
            text=tr("Custom hotkey:"),
        ).pack(anchor="w")
        row = ttk.Frame(self.content)
        row.pack(fill="x", pady=(4, 0), padx=(22, 0))
        ttk.Entry(row, textvariable=self.custom_hotkey, width=24).pack(side="left")
        ttk.Button(row, text=tr("Capture"), command=self._capture_hotkey).pack(
            side="left", padx=(8, 0)
        )
        ttk.Label(
            self.content,
            text=tr("   Example: ctrl+alt+d, f9, win+shift+space"),
            foreground="#666",
        ).pack(anchor="w", pady=(4, 0))

    def _capture_hotkey(self):
        if self._hotkey_capture:
            return
        self._hotkey_capture = True
        self.custom_hotkey.set(tr("… waiting for a key …"))

        def handler(event):
            if keyhook.is_modifier(event["vk"]):
                return False
            mods = keyhook.modifier_state()
            combo = hotkey.build_combo(mods, event["vk"])
            self.ui.post(self._finish_hotkey_capture, combo)
            return True  # swallow the key so it does not reach the app

        self._hotkey_listener = keyhook.KeyboardListener(handler, swallow=True)
        self._hotkey_listener.start()

    def _finish_hotkey_capture(self, combo):
        self._hotkey_capture = False
        self.custom_hotkey.set(combo)
        if self._hotkey_listener:
            self._hotkey_listener.stop()
            self._hotkey_listener = None
        try:
            hotkey.parse_hotkey(combo)
        except ValueError:
            self.custom_hotkey.set("ctrl+alt+d")
            messagebox.showwarning(
                tr("Invalid hotkey"),
                f"'{combo}' cannot be used, reverted to the default.",
                parent=self.root,
            )

    def _page_tasks(self):
        self._heading(
            tr("Extra tasks"),
            tr("Choose the extra tasks to perform during setup."),
        )
        ttk.Checkbutton(
            self.content, text=tr("Start automatically when Windows starts"),
            variable=self.autostart,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(
            self.content, text=tr("Play a short beep when the key is pressed"),
            variable=self.beep,
        ).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(
            self.content, text=tr("Add a Kelam shortcut to the desktop"),
            variable=self.create_shortcut,
        ).pack(anchor="w", pady=(8, 0))

        ttk.Label(
            self.content,
            text=(
                "\nNote: if Windows does not recognize the remote key, the bridge "
                "reads it directly. If it does, the original function is blocked and "
                "only dictation runs."
            ),
            wraplength=500, foreground="#666",
        ).pack(anchor="w", pady=(16, 0))

    def _action_spec(self):
        if self.action_mode.get() == "custom":
            return self.custom_hotkey.get().strip() or "win+h"
        return "win+h"

    def _page_ready(self):
        if self.mode == "settings":
            self._heading(
                tr("Save changes"),
                tr("The settings below will be applied."),
            )
        else:
            self._heading(
                tr("Ready to install"),
                tr("Setup is ready to install Kelam. Review the settings."),
            )
        box = ttk.LabelFrame(self.content, text=tr("Summary"), padding=12)
        box.pack(fill="both", expand=True)
        lines = [
            f"Remote key      : {cfg.describe_trigger(self.trigger)}",
            f"Action          : {cfg.describe_action({'type': 'hotkey', 'hotkey': self._action_spec()})}",
            f"Start with PC   : {tr('yes') if self.autostart.get() else 'no'}",
            f"Beep            : {tr('yes') if self.beep.get() else 'no'}",
            f"Desktop shortcut: {tr('yes') if self.create_shortcut.get() else 'no'}",
            f"Location        : {service.BASE_DIR}",
        ]
        ttk.Label(box, text="\n".join(lines), justify="left").pack(anchor="nw")
        self.next_button.configure(text=tr("Save") if self.mode == "settings" else tr("Install"))

    def _page_installing(self):
        if self.mode == "settings":
            self._heading(tr("Saving"), tr("Please wait, applying your settings."))
        else:
            self._heading(tr("Installing"), tr("Please wait, installing Kelam."))
        self.status = tk.StringVar(value=tr("Preparing…"))
        ttk.Label(self.content, textvariable=self.status).pack(anchor="w", pady=(8, 8))
        self.progress = ttk.Progressbar(self.content, mode="determinate", maximum=100)
        self.progress.pack(fill="x")
        self.back_button.configure(state="disabled")
        self.next_button.configure(state="disabled")
        threading.Thread(target=self._perform_install, daemon=True).start()

    def _page_finish(self):
        if self.mode == "settings":
            self._title_with_logo(tr("Settings saved"), size=64)
            body = (
                "The new settings were applied and the bridge restarted.\n\n"
                "Press the remote key to try it."
            )
        else:
            self._title_with_logo(tr("Setup complete"), size=64)
            body = (
                "Kelam is installed and running.\n\n"
                "Press the remote microphone button and start talking.\n"
                "Text appears wherever the cursor is."
            )
        ttk.Label(
            self.content, text=body, justify="left", wraplength=500,
        ).pack(anchor="w", pady=(12, 8))

        box = ttk.LabelFrame(self.content, text=tr("Assigned key"), padding=12)
        box.pack(fill="x", pady=(6, 0))
        ttk.Label(box, text=cfg.describe_trigger(self.trigger)).pack(anchor="w")

        if self._warnings:
            warn = ttk.LabelFrame(self.content, text=tr("Warnings"), padding=12)
            warn.pack(fill="x", pady=(10, 0))
            ttk.Label(
                warn, text="\n".join(f"• {w}" for w in self._warnings),
                justify="left", wraplength=470, foreground="#8a4b00",
            ).pack(anchor="nw")

        self.back_button.configure(state="disabled")
        self.next_button.configure(text=tr("Close"), command=self._finish)

    # ------------------------------------------------------------ navigation
    def _on_return(self, _event):
        if self.current == "capture":
            if not self.trigger:
                messagebox.showwarning(
                    tr("Waiting for a key"),
                    tr("Press the remote microphone button first."),
                    parent=self.root,
                )
                return "break"
            self._next()
            return "break"
        return None

    def _next(self):
        if self.current == "license" and not self.accepted_license.get():
            messagebox.showwarning(
                tr("License"), tr("Accept the license to continue."), parent=self.root
            )
            return
        if self.current == "capture" and not self.trigger:
            messagebox.showwarning(
                tr("Key not captured"),
                "Could not detect the remote key. Press it again; "
                "if it fails, clear the list with 'Reset'.",
                parent=self.root,
            )
            return
        if self.current == "action" and self.action_mode.get() == "custom":
            try:
                hotkey.parse_hotkey(self._action_spec())
            except ValueError as exc:
                messagebox.showerror(tr("Hotkey"), str(exc), parent=self.root)
                return
        self._show_page(self.page + 1)

    def _back(self):
        if self.page > 0:
            self._show_page(self.page - 1)

    def _cancel(self):
        if self.current == "progress":
            messagebox.showinfo(
                tr("Setup"), tr("Saving is in progress and cannot be cancelled."), parent=self.root
            )
            return
        self.capture.stop()
        if self._hotkey_listener:
            self._hotkey_listener.stop()
        if self._was_running and not self._installed:
            service.start()
        self.root.destroy()

    # ------------------------------------------------------------- installing
    def _set_progress(self, value: int, message: str):
        self.ui.post(self._apply_progress, value, message)

    def _apply_progress(self, value: int, message: str):
        self.progress.configure(value=value)
        self.status.set(message)

    def _perform_install(self):
        self._installed = False
        self._warnings = []
        try:
            self._set_progress(15, tr("Saving settings…"))
            cfg_data = cfg.load()
            cfg_data["bindings"] = [
                cfg.binding(self.trigger, self._action_spec())
            ]
            cfg_data["beep"] = bool(self.beep.get())
            cfg_data["autostart"] = bool(self.autostart.get())
            cfg_data["swallow"] = self.trigger.get("type") == "key"
            cfg.save(cfg_data)

            self._set_progress(45, tr("Updating the startup entry…"))
            service.set_autostart(bool(self.autostart.get()))

            self._set_progress(65, tr("Creating shortcuts…"))
            service.create_shortcuts(desktop=bool(self.create_shortcut.get()))
            if self.create_shortcut.get():
                link = service.desktop_shortcut_path()
                if not link or not os.path.isfile(link):
                    self._warnings.append(
                        "Could not create the desktop shortcut; use the one in the "
                        "Start Menu instead."
                    )

            self._set_progress(
                80,
                tr("Restarting the bridge…")
                if self.mode == "settings"
                else tr("Starting the bridge…"),
            )
            pid = service.restart()
            if not pid:
                self._warnings.append(
                    tr("Could not start the bridge. Remove the installation and try again.")
                )
            service.register_uninstall()

            self._set_progress(
                100,
                tr("Settings saved.")
                if self.mode == "settings"
                else tr("Installation complete."),
            )
            self._installed = True
            finish_index = self._sequence.index("finish")
            self.ui.post(self._show_page, finish_index)
        except Exception as error:  # noqa: BLE001 - show a readable error to the user
            self.ui.post(self._install_failed, error)

    def _install_failed(self, error):
        self.back_button.configure(state="normal")
        self.next_button.configure(state="normal", text=tr("Back"), command=self._back)
        messagebox.showerror(tr("Installation failed"), str(error), parent=self.root)

    def _finish(self):
        self.capture.stop()
        self.root.destroy()

    # ------------------------------------------------------------- uninstall
    def _uninstall(self):
        self.capture.stop()
        dialog = UninstallWizard(self.root)
        dialog.run()
        if dialog.removed and self.root.winfo_exists():
            self.root.destroy()

    def _toggle_language(self):
        """Switch the UI language and reopen the window in it."""
        i18n.toggle_lang()
        self.settings["language"] = i18n.get_lang()
        try:
            cfg.save(self.settings)
        except OSError:
            pass
        self.reopen = True
        self.root.destroy()

    def run(self):
        self.root.mainloop()


class SettingsWindow:
    """Settings menu: key list, one-click actions, Save at bottom right."""

    def __init__(self):
        self.root = tk.Tk()
        self.reopen = False
        try:
            i18n.set_lang(cfg.load().get("language", "en"))
        except (OSError, ValueError):
            i18n.set_lang("en")
        self.root.title(tr("Settings"))
        self.root.geometry("820x600")
        self.root.minsize(820, 600)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)

        icon_path = os.path.join(paths.RESOURCE_DIR, "assets", "kelam.ico")
        if os.path.isfile(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except tk.TclError:
                pass

        self.settings = cfg.load()
        self.bindings = [dict(b) for b in (self.settings.get("bindings") or [])]
        self.selected = 0 if self.bindings else None
        self.capture = CaptureSession()
        self.listening = False
        self._hotkey_listener = None
        self._saved = False

        self._was_running = service.is_running()
        service.stop()  # keep the bridge from reacting while capturing a key

        self.status = tk.StringVar(value="")
        self.action_mode = tk.StringVar(value="winh")
        self.custom_hotkey = tk.StringVar(value="ctrl+alt+d")
        self.autostart = tk.BooleanVar(value=bool(self.settings.get("autostart", True)))
        self.beep = tk.BooleanVar(value=bool(self.settings.get("beep", False)))
        desktop_link = service.desktop_shortcut_path()
        self.create_shortcut = tk.BooleanVar(
            value=bool(desktop_link and os.path.isfile(desktop_link))
        )

        self.ui = UiQueue(self.root)
        self._build()
        self._refresh_table(select=0)
        self._load_action_from_selection()

    # ------------------------------------------------------------------ UI
    def _build(self):
        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True)

        self.brand = tk.Canvas(body, width=190, highlightthickness=0, bg=BRAND_BG)
        self.brand.pack(side="left", fill="y")
        self._brand_img = paint_brand(self.brand, "settings")

        self.content = ttk.Frame(body, padding=(22, 16))
        self.content.pack(side="left", fill="both", expand=True)

        header = ttk.Frame(self.content)
        header.pack(fill="x")
        logo = self._load_logo(56)
        if logo is not None:
            self._logo_ref = logo
            ttk.Label(header, image=logo).pack(side="right")
        ttk.Label(header, text=tr("Settings"), font=("Segoe UI", 17, "bold")).pack(
            side="left", anchor="w"
        )
        ttk.Button(
            header,
            text=("TR" if i18n.get_lang() == "en" else "EN"),
            width=4,
            command=self._toggle_language,
        ).pack(side="right", padx=(0, 8))

        # --- key list
        keys = ttk.LabelFrame(self.content, text=tr("Remote keys"), padding=10)
        keys.pack(fill="both", expand=True, pady=(12, 8))

        table = ttk.Frame(keys)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            table, columns=("key", "action"), show="headings", height=6
        )
        self.tree.heading("key", text=tr("Key"))
        self.tree.heading("action", text=tr("Action"))
        self.tree.column("key", width=330, anchor="w")
        self.tree.column("action", width=180, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)

        buttons = ttk.Frame(keys)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text=tr("Add key"), command=self._add_key).pack(side="left")
        ttk.Button(buttons, text=tr("Remove selected"), command=self._remove_selected).pack(
            side="left", padx=(8, 0)
        )
        self.hint_var = tk.StringVar(value="")
        self.key_hint = ttk.Label(
            buttons, textvariable=self.hint_var, foreground="#12506f"
        )
        self.key_hint.pack(side="left", padx=(12, 0))

        # --- action for the selected key
        action = ttk.LabelFrame(self.content, text=tr("Action for the selected key"), padding=10)
        action.pack(fill="x", pady=(0, 8))
        ttk.Radiobutton(
            action, value="winh", variable=self.action_mode,
            text=tr("Windows voice typing (Win+H) — recommended"),
        ).pack(anchor="w")
        custom = ttk.Frame(action)
        custom.pack(fill="x", pady=(4, 0))
        ttk.Radiobutton(
            custom, value="custom", variable=self.action_mode, text=tr("Custom hotkey:")
        ).pack(side="left")
        self.hotkey_entry = ttk.Entry(custom, textvariable=self.custom_hotkey, width=20)
        self.hotkey_entry.pack(side="left", padx=(8, 0))
        ttk.Button(custom, text=tr("Capture"), command=self._capture_hotkey).pack(
            side="left", padx=(6, 0)
        )

        # --- options
        options = ttk.LabelFrame(self.content, text=tr("Options"), padding=10)
        options.pack(fill="x", pady=(0, 6))
        row = ttk.Frame(options)
        row.pack(fill="x")
        ttk.Checkbutton(
            row, text=tr("Start with Windows"), variable=self.autostart
        ).pack(side="left")
        ttk.Checkbutton(
            row, text="Bip sesi", variable=self.beep
        ).pack(side="left", padx=(16, 0))
        ttk.Checkbutton(
            row, text=tr("Desktop shortcut"), variable=self.create_shortcut
        ).pack(side="left", padx=(16, 0))

        ttk.Label(self.content, textvariable=self.status, foreground="#8a4b00").pack(
            anchor="w"
        )

        # --- alt bar
        footer = ttk.Frame(self.root, padding=(14, 10))
        footer.pack(fill="x", side="bottom")
        ttk.Button(
            footer, text=tr("Remove Kelam from this computer"), command=self._remove
        ).pack(side="left")
        self.save_button = ttk.Button(footer, text=tr("Save"), command=self._save)
        self.save_button.pack(side="right")
        ttk.Button(footer, text=tr("Cancel"), command=self._cancel).pack(
            side="right", padx=(0, 8)
        )

    def _load_logo(self, size=56):
        path = os.path.join(paths.RESOURCE_DIR, "assets", "logo.png")
        if not os.path.isfile(path):
            return None
        try:
            image = tk.PhotoImage(file=path)
        except tk.TclError:
            return None
        if size < image.width():
            image = image.subsample(max(1, round(image.width() / size)))
        return image

    # ------------------------------------------------------------- tablo
    def _refresh_table(self, select=None):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, binding in enumerate(self.bindings):
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    cfg.describe_trigger(binding.get("trigger")),
                    cfg.describe_action(binding.get("action")),
                ),
            )
        if self.bindings:
            target = select if select is not None else self.selected
            if target is None or target >= len(self.bindings):
                target = 0
            self.selected = target
            self.tree.selection_set(str(target))
            self.tree.focus(str(target))
        else:
            self.selected = None
        self._update_hint()

    def _update_hint(self):
        if self.bindings:
            self.hint_var.set("")
        else:
            self.hint_var.set(tr("No keys yet — start with 'Add key'."))

    def _on_select(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        self._commit_action()
        self.selected = int(selection[0])
        self._load_action_from_selection()

    def _load_action_from_selection(self):
        if self.selected is None or self.selected >= len(self.bindings):
            return
        action = (self.bindings[self.selected].get("action") or {})
        hotkey_value = action.get("hotkey", "win+h")
        if hotkey_value and hotkey_value.lower() != "win+h":
            self.action_mode.set("custom")
            self.custom_hotkey.set(hotkey_value)
        else:
            self.action_mode.set("winh")

    def _commit_action(self):
        if self.selected is None or self.selected >= len(self.bindings):
            return
        hotkey_value = (
            self.custom_hotkey.get().strip() or "win+h"
            if self.action_mode.get() == "custom"
            else "win+h"
        )
        self.bindings[self.selected]["action"] = {
            "type": "hotkey",
            "hotkey": hotkey_value,
        }
        self._refresh_row(self.selected)

    def _refresh_row(self, index):
        if index >= len(self.bindings):
            return
        binding = self.bindings[index]
        self.tree.item(
            str(index),
            values=(
                cfg.describe_trigger(binding.get("trigger")),
                cfg.describe_action(binding.get("action")),
            ),
        )

    # --------------------------------------------------------- adding keys
    def _add_key(self):
        if self.listening:
            return
        self.listening = True
        self.capture.start()
        self.hint_var.set(tr("Press the new remote button now…"))
        self.root.after(150, self._poll_capture)

    def _poll_capture(self):
        if not self.listening:
            return
        candidate = self.capture.last_trigger()
        if candidate:
            self.listening = False
            self.capture.stop()
            self._commit_action()
            hotkey_value = (
                self.custom_hotkey.get().strip() or "win+h"
                if self.action_mode.get() == "custom"
                else "win+h"
            )
            self.bindings.append(cfg.binding(candidate, hotkey_value))
            self._refresh_table(select=len(self.bindings) - 1)
            self.hint_var.set(tr("Key added — do not forget to save."))
            return
        self.root.after(150, self._poll_capture)

    def _remove_selected(self):
        if self.selected is None or self.selected >= len(self.bindings):
            return
        del self.bindings[self.selected]
        self.selected = 0 if self.bindings else None
        self._refresh_table(select=0 if self.bindings else None)
        self.hint_var.set(tr("Key removed — do not forget to save."))

    # --------------------------------------------------------- hotkey
    def _capture_hotkey(self):
        self.custom_hotkey.set(tr("… waiting for a key …"))
        self.action_mode.set("custom")

        def handler(event):
            if keyhook.is_modifier(event["vk"]):
                return False
            combo = hotkey.build_combo(keyhook.modifier_state(), event["vk"])
            self.ui.post(self._finish_hotkey, combo)
            return True

        self._hotkey_listener = keyhook.KeyboardListener(handler, swallow=True)
        self._hotkey_listener.start()

    def _finish_hotkey(self, combo):
        if self._hotkey_listener:
            self._hotkey_listener.stop()
            self._hotkey_listener = None
        try:
            hotkey.parse_hotkey(combo)
            self.custom_hotkey.set(combo)
        except ValueError:
            self.custom_hotkey.set("ctrl+alt+d")
            messagebox.showwarning(
                tr("Invalid hotkey"),
                f"'{combo}' cannot be used, reverted to the default.",
                parent=self.root,
            )

    # --------------------------------------------------------------- saving
    def _save(self):
        self._commit_action()
        if not self.bindings:
            messagebox.showwarning(
                tr("No key"), tr("Add at least one remote key."), parent=self.root
            )
            return
        for binding in self.bindings:
            try:
                hotkey.parse_hotkey((binding.get("action") or {}).get("hotkey", "win+h"))
            except ValueError as exc:
                messagebox.showerror(tr("Hotkey"), str(exc), parent=self.root)
                return

        self.save_button.configure(state="disabled")
        self.status.set(tr("Saving…"))

        def work():
            try:
                data = cfg.load()
                data["bindings"] = self.bindings
                data["beep"] = bool(self.beep.get())
                data["autostart"] = bool(self.autostart.get())
                cfg.save(data)

                service.set_autostart(bool(self.autostart.get()))
                service.create_shortcuts(desktop=bool(self.create_shortcut.get()))
                if not self.create_shortcut.get():
                    link = service.desktop_shortcut_path()
                    if link:
                        try:
                            os.remove(link)
                        except OSError:
                            pass
                service.register_uninstall()
                service.restart()
                self._saved = True
                self.ui.post(self._after_save)
            except Exception as error:  # noqa: BLE001
                self.ui.post(self._save_failed, error)

        threading.Thread(target=work, daemon=True).start()

    def _after_save(self):
        self.status.set(tr("Saved."))
        self.root.destroy()

    def _save_failed(self, error):
        self.save_button.configure(state="normal")
        self.status.set("")
        messagebox.showerror(tr("Could not save"), str(error), parent=self.root)

    # --------------------------------------------------------------- remove
    def _remove(self):
        if self.listening:
            self.listening = False
            self.capture.stop()
        dialog = UninstallWizard(self.root)
        dialog.run()
        if dialog.removed and self.root.winfo_exists():
            self.root.destroy()

    def _cancel(self):
        if self.listening:
            self.listening = False
            self.capture.stop()
        if self._hotkey_listener:
            self._hotkey_listener.stop()
        if self._was_running and not self._saved:
            service.start()
        self.root.destroy()

    def _toggle_language(self):
        """Switch the UI language and reopen the window in it."""
        i18n.toggle_lang()
        self.settings["language"] = i18n.get_lang()
        try:
            cfg.save(self.settings)
        except OSError:
            pass
        self.reopen = True
        self.root.destroy()

    def run(self):
        self.root.mainloop()
        while self.reopen:
            self.reopen = False
            fresh = SettingsWindow()
            fresh.root.mainloop()
            self.reopen = fresh.reopen


class UninstallWizard:
    """Uninstall wizard: confirm -> progress -> summary.

    Runs from SetupWizard or standalone via `--uninstall`.
    """

    def __init__(self, parent: tk.Misc):
        self.parent = parent
        self.win = tk.Toplevel(parent)
        self.win.title(tr("Remove Kelam"))
        self.win.geometry("560x420")
        self.win.resizable(False, False)
        self.win.transient(parent)
        self.win.grab_set()
        self.win.protocol("WM_DELETE_WINDOW", self._cancel)

        icon_path = os.path.join(paths.RESOURCE_DIR, "assets", "kelam.ico")
        if os.path.isfile(icon_path):
            try:
                self.win.iconbitmap(icon_path)
            except tk.TclError:
                pass

        self.ui = UiQueue(self.win)
        self.body = ttk.Frame(self.win, padding=(24, 20))
        self.body.pack(fill="both", expand=True)
        self.footer = ttk.Frame(self.win, padding=(12, 10))
        self.footer.pack(fill="x", side="bottom")

        self.removed: list[str] = []
        self._show_confirm()

    # ------------------------------------------------------------- sayfalar
    def _clear(self):
        for panel in (self.body, self.footer):
            for child in panel.winfo_children():
                child.destroy()

    def _show_confirm(self):
        self._clear()
        ttk.Label(
            self.body, text=tr("Remove Kelam?"),
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            self.body,
            text=tr("When removal finishes, the app stops working."),
            wraplength=480,
        ).pack(anchor="w", pady=(6, 10))

        box = ttk.LabelFrame(self.body, text=tr("Will be removed"), padding=12)
        box.pack(fill="both", expand=True)
        items = [
            tr("Running bridge (background process)"),
            tr("Startup entry — no longer starts with Windows"),
            tr("Desktop and Start Menu shortcuts"),
            tr("Apps & features entry"),
            tr("Settings, logs and temporary files"),
        ]
        if service.is_frozen():
            items.append(tr("Program folder (only if it holds Kelam files)"))
        ttk.Label(
            box, text="\n".join(f"• {i}" for i in items), justify="left",
        ).pack(anchor="nw")

        ttk.Button(self.footer, text=tr("Cancel"), command=self._cancel).pack(side="right")
        ttk.Button(self.footer, text=tr("Remove"), command=self._start).pack(
            side="right", padx=(0, 8)
        )

    def _show_progress(self):
        self._clear()
        ttk.Label(
            self.body, text=tr("Removing"),
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")
        self.status = tk.StringVar(value=tr("Preparing…"))
        ttk.Label(self.body, textvariable=self.status).pack(anchor="w", pady=(10, 8))
        self.progress = ttk.Progressbar(self.body, mode="determinate", maximum=100)
        self.progress.pack(fill="x")

    def _show_done(self):
        self._clear()
        ttk.Label(
            self.body, text=tr("Kelam removed"),
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            self.body,
            text=tr("The following were removed:"),
            wraplength=480,
        ).pack(anchor="w", pady=(8, 6))
        box = ttk.LabelFrame(self.body, text=tr("Removed"), padding=12)
        box.pack(fill="both", expand=True)
        ttk.Label(
            box, text="\n".join(f"• {r}" for r in self.removed) or "—",
            justify="left", wraplength=460,
        ).pack(anchor="nw")
        ttk.Button(self.footer, text="Kapat", command=self._close).pack(side="right")

    # --------------------------------------------------------------- eylem
    def _start(self):
        self._show_progress()
        threading.Thread(target=self._work, daemon=True).start()

    def _set_progress(self, value: int, message: str):
        self.ui.post(self._apply_progress, value, message)

    def _apply_progress(self, value: int, message: str):
        self.progress.configure(value=value)
        self.status.set(message)

    def _work(self):
        try:
            self._set_progress(20, tr("Stopping the bridge…"))
            self.removed = uninstall_all()
            if service.can_self_delete() and service.schedule_folder_delete():
                self.removed.append(tr("program folder (deleted on exit)"))
            self._set_progress(100, tr("Removal complete."))
        except Exception as error:  # noqa: BLE001
            self.removed = [f"HATA: {error}"]
        self.ui.post(self._show_done)

    def _cancel(self):
        self.win.grab_release()
        self.win.destroy()

    def _close(self):
        self.win.grab_release()
        self.win.destroy()
        if self.parent is not None and self.parent.winfo_exists():
            self.parent.destroy()

    def run(self):
        self.parent.wait_window(self.win)


def uninstall_all():
    """Removes everything the installer left behind; returns the list."""
    removed = []
    if service.stop():
        removed.append(tr("running bridge stopped"))
    service.set_autostart(False)
    removed.append(tr("startup entry (Run)"))
    service.unregister_uninstall()
    removed.append(tr("Apps & features entry"))
    service.remove_shortcuts()
    removed.append(tr("shortcuts"))

    for name in (
        "config.json",
        "bridge.log",
        "bridge.log.1",
        "bridge.out",
        "bridge.pid",
    ):
        path = os.path.join(service.BASE_DIR, name)
        for _attempt in range(6):
            try:
                os.remove(path)
                removed.append(name)
                break
            except FileNotFoundError:
                break
            except OSError:
                # süreç henüz kapanıyor olabilir
                time.sleep(0.2)

    pycache = os.path.join(service.BASE_DIR, "__pycache__")
    if os.path.isdir(pycache):
        shutil.rmtree(pycache, ignore_errors=True)
        removed.append("__pycache__")
    return removed


def main():
    import main as entry

    entry.main()


if __name__ == "__main__":
    main()
