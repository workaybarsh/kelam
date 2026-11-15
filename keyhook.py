"""Low-level keyboard hook (WH_KEYBOARD_LL).

Used to capture keys Windows knows about, and optionally swallow them.
If the remote's mic button never reaches Windows, this layer is not used;
o durumda hidbtn kullanilir.
"""

import ctypes
import threading
import time
from ctypes import wintypes as w

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
LLKHF_EXTENDED = 0x01
LLKHF_INJECTED = 0x10
STILL_ACTIVE = 259

MODIFIER_VKS = {0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", w.DWORD),
        ("scanCode", w.DWORD),
        ("flags", w.DWORD),
        ("time", w.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, w.WPARAM, w.LPARAM)

user32.SetWindowsHookExW.restype = w.HHOOK
user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    HOOKPROC,
    w.HINSTANCE,
    w.DWORD,
]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.CallNextHookEx.argtypes = [w.HHOOK, ctypes.c_int, w.WPARAM, w.LPARAM]
user32.UnhookWindowsHookEx.argtypes = [w.HHOOK]
user32.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(w.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(w.MSG)]
user32.PostThreadMessageW.argtypes = [w.DWORD, w.UINT, w.WPARAM, w.LPARAM]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short


def modifier_state():
    """Returns the modifiers currently held down."""
    keys = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B}
    return {
        name: bool(user32.GetAsyncKeyState(vk) & 0x8000) for name, vk in keys.items()
    }


class KeyboardListener(threading.Thread):
    """Klavye kancasini kendi thread'inde calistirir.

    on_event(event) -> returning True swallows the key when enabled
    (it never reaches the app).
    """

    def __init__(self, on_event, swallow=False, on_ready=None):
        super().__init__(daemon=True)
        self.on_event = on_event
        self.swallow = swallow
        self.on_ready = on_ready
        self.last_error = None
        self.ready = threading.Event()
        self._thread_id = None
        self._hook = None
        self._proc = HOOKPROC(self._handler)

    def _handler(self, n_code, w_param, l_param):
        try:
            if n_code == 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                event = {
                    "type": "key",
                    "vk": int(kb.vkCode),
                    "scan": int(kb.scanCode),
                    "extended": bool(kb.flags & LLKHF_EXTENDED),
                    "injected": bool(kb.flags & LLKHF_INJECTED),
                    "time": time.time(),
                }
                if self.on_event and self.on_event(event):
                    if self.swallow:
                        return 1
        except Exception as exc:  # kanca icinde patlamak sistemi kilitler
            self.last_error = repr(exc)
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        self._hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0
        )
        if not self._hook:
            self.last_error = (
                f"SetWindowsHookExW basarisiz (err={ctypes.get_last_error()})"
            )
            self.ready.set()
            return
        self.ready.set()
        msg = w.MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

    def stop(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)


def is_modifier(vk):
    return vk in MODIFIER_VKS
