"""Produces the wizard promo image (docs/screenshot-welcome.png).

    python tools/capture_screens.py

Opens the wizard in install mode, captures the first page and closes it.
The app does not need to be installed.
"""

import ctypes
import os
import sys
import time
from ctypes import wintypes as w

from PIL import ImageGrab

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import wizard as wizard_mod  # noqa: E402

DOCS = os.path.join(BASE, "docs")


class RECT(ctypes.Structure):
    _fields_ = [("left", w.LONG), ("top", w.LONG), ("right", w.LONG), ("bottom", w.LONG)]


def window_handle(root):
    hwnd = root.winfo_id()
    parent = ctypes.windll.user32.GetParent(hwnd)
    return parent or hwnd


def frame_rect(hwnd):
    """Real window frame without shadow/transparent border (DWM)."""
    rect = RECT()
    try:
        dwm = ctypes.WinDLL("dwmapi")
        # DWMWA_EXTENDED_FRAME_BOUNDS = 9
        status = dwm.DwmGetWindowAttribute(
            w.HWND(hwnd), ctypes.c_uint(9), ctypes.byref(rect), ctypes.sizeof(rect)
        )
        if status == 0 and rect.right > rect.left and rect.bottom > rect.top:
            return rect
    except Exception:
        pass
    ctypes.windll.user32.GetWindowRect(w.HWND(hwnd), ctypes.byref(rect))
    return rect


def capture(root, name):
    root.attributes("-topmost", True)
    root.lift()
    root.update()
    time.sleep(0.6)

    rect = frame_rect(window_handle(root))
    image = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))
    path = os.path.join(DOCS, f"{name}.png")
    image.save(path)
    root.attributes("-topmost", False)
    print(f"{name}.png  {image.width}x{image.height}")


def main():
    os.makedirs(DOCS, exist_ok=True)
    app = wizard_mod.SetupWizard(mode="install")
    app.root.update()
    capture(app.root, "screenshot-welcome")
    app.capture.stop()
    app.root.destroy()


if __name__ == "__main__":
    main()
