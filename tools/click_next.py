"""Click the wizard's Next button (for verifying the packaged exe)."""

import ctypes
import sys
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
user32.FindWindowW.restype = wintypes.HWND
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]

title = sys.argv[1] if len(sys.argv) > 1 else "Kelam Setup Wizard"
hwnd = user32.FindWindowW(None, title)
if not hwnd:
    print("window not found")
    raise SystemExit(1)

rect = wintypes.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
user32.ShowWindow(hwnd, 9)
user32.SetForegroundWindow(hwnd)
time.sleep(0.6)

# Next is the middle button of the bottom-right navigation bar
x = rect.left + 657
y = rect.top + 557
user32.SetCursorPos(x, y)
time.sleep(0.2)
user32.mouse_event(0x0002, 0, 0, 0, 0)  # left down
user32.mouse_event(0x0004, 0, 0, 0, 0)  # left up
print(f"clicked ({x}, {y})")
