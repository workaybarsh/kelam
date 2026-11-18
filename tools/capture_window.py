"""Capture a window by title (helper for screenshots and promo art)."""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

from PIL import ImageGrab

user32 = ctypes.windll.user32

user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_uint,
]
user32.SetWindowPos.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]

HWND_TOPMOST = wintypes.HWND(-1)
HWND_NOTOPMOST = wintypes.HWND(-2)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_SHOWWINDOW = 0x0040


def capture(title: str, output: str) -> int:
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        print(f"window not found: {title}")
        return 1

    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
    time.sleep(1.0)

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    image = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)
    image.save(output)
    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)

    print(f"{output}  {image.size[0]}x{image.size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(capture(sys.argv[1], sys.argv[2]))
