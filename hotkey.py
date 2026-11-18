"""Sending hotkeys and converting to text."""

import ctypes
import time
from i18n import tr

user32 = ctypes.WinDLL("user32.dll")
KEYEVENTF_KEYUP = 0x0002

MODIFIERS = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B}
MODIFIER_ORDER = ["ctrl", "alt", "shift", "win"]

SPECIAL_KEYS = {
    "space": 0x20,
    "enter": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "printscreen": 0x2C,
    "capslock": 0x14,
}

VK_TO_TOKEN = {
    0x08: "backspace",
    0x09: "tab",
    0x0D: "enter",
    0x13: "pause",
    0x14: "capslock",
    0x1B: "esc",
    0x20: "space",
    0x21: "pageup",
    0x22: "pagedown",
    0x23: "end",
    0x24: "home",
    0x25: "left",
    0x26: "up",
    0x27: "right",
    0x28: "down",
    0x2C: "printscreen",
    0x2D: "insert",
    0x2E: "delete",
    0x5B: "win",
    0x5C: "win",
}


def parse_hotkey(spec):
    """'ctrl+alt+d' -> ([0x11, 0x12], 0x44)"""
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError(tr("Hotkey cannot be empty"))
    key_part = parts[-1]
    mods = parts[:-1]
    for mod in mods:
        if mod not in MODIFIERS:
            raise ValueError(f"Unknown modifier: {mod}")
    if key_part in SPECIAL_KEYS:
        vk = SPECIAL_KEYS[key_part]
    elif len(key_part) == 1 and key_part.isalnum():
        vk = ord(key_part.upper())
    elif key_part.startswith("f") and key_part[1:].isdigit():
        num = int(key_part[1:])
        if not 1 <= num <= 24:
            raise ValueError(f"Invalid function key: {key_part}")
        vk = 0x70 + num - 1
    else:
        raise ValueError(f"Unrecognised key: {key_part}")
    mods.sort(key=MODIFIER_ORDER.index)
    return [MODIFIERS[m] for m in mods], vk


def send_hotkey(modifier_vks, vk):
    for mod in modifier_vks:
        user32.keybd_event(mod, 0, 0, 0)
    time.sleep(0.01)
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    for mod in reversed(modifier_vks):
        time.sleep(0.005)
        user32.keybd_event(mod, 0, KEYEVENTF_KEYUP, 0)


def vk_to_token(vk):
    if vk in VK_TO_TOKEN:
        return VK_TO_TOKEN[vk]
    if 0x41 <= vk <= 0x5A:
        return chr(vk).lower()
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x70 <= vk <= 0x87:
        return f"f{vk - 0x6F}"
    if 0x60 <= vk <= 0x69:
        return f"num{vk - 0x60}"
    return f"vk{vk:02X}"


def build_combo(mods, vk):
    """mods: {'ctrl': True, ...} -> 'ctrl+shift+d'"""
    ordered = [m for m in MODIFIER_ORDER if mods.get(m)]
    return "+".join(ordered + [vk_to_token(vk)])


def send_spec(spec):
    mods, vk = parse_hotkey(spec)
    send_hotkey(mods, vk)
