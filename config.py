"""Loading and saving settings.

Settings now hold a `bindings` list: each entry is a key plus its action.
The legacy single-key `trigger`/`action` layout is migrated on load.
"""

import copy
import json
import os

import paths
from i18n import tr

BASE_DIR = paths.BASE_DIR
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG = {
    "language": "en",
    "bindings": [],
    "beep": False,
    "debounce_ms": 400,
    "autostart": True,
    "swallow": True,
}

DEFAULT_ACTION = {"type": "hotkey", "hotkey": "win+h"}

SPECIAL_VK = {
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
    0x5D: "apps",
    0x90: "numlock",
    0x91: "scrolllock",
}

CONSUMER_NAMES = {
    0x00CF: tr("Voice Command (mic button)"),
    0x0221: "AC Search",
    0x0223: "AC Home",
    0x0224: "AC Back",
    0x0225: "AC Forward",
    0x00CD: "Play/Pause",
    0x00E2: "Mute",
    0x00E9: tr("Volume up"),
    0x00EA: tr("Volume down"),
    0x00B5: tr("Next track"),
    0x00B6: tr("Previous track"),
}


def _migrate(data):
    """Migrates the old single-key layout into the bindings list."""
    if not data.get("bindings"):
        trigger = data.get("trigger")
        action = data.get("action") or copy.deepcopy(DEFAULT_ACTION)
        data["bindings"] = (
            [{"trigger": trigger, "action": action}] if trigger else []
        )
    data.pop("trigger", None)
    data.pop("action", None)
    # fill in missing fields
    for binding in data["bindings"]:
        if not isinstance(binding.get("action"), dict):
            binding["action"] = copy.deepcopy(DEFAULT_ACTION)
    return data


def load(path=CONFIG_PATH):
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                    cfg[key].update(value)
                else:
                    cfg[key] = value
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError):
        pass
    return _migrate(cfg)


def save(cfg, path=CONFIG_PATH):
    data = copy.deepcopy(cfg)
    data.pop("trigger", None)
    data.pop("action", None)
    data.setdefault("bindings", [])
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def binding(trigger, hotkey="win+h"):
    """Builds a new key binding."""
    return {"trigger": trigger, "action": {"type": "hotkey", "hotkey": hotkey}}


def vk_name(vk):
    if vk in SPECIAL_VK:
        return SPECIAL_VK[vk]
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x41 <= vk <= 0x5A:
        return chr(vk).lower()
    if 0x60 <= vk <= 0x69:
        return f"num{vk - 0x60}"
    if 0x70 <= vk <= 0x87:
        return f"f{vk - 0x6F}"
    return f"vk{vk:02X}"


def describe_trigger(trigger):
    if not trigger:
        return tr("not configured")
    if trigger.get("type") == "hid":
        name = CONSUMER_NAMES.get(trigger.get("usage"))
        base = (
            f"HID {trigger.get('vid', 0):04X}:{trigger.get('pid', 0):04X} "
            f"usage 0x{trigger.get('usage', 0):04X}"
        )
        return f"{base} ({name})" if name else base
    if trigger.get("type") == "key":
        return f"Keyboard key: {trigger.get('name') or vk_name(trigger.get('vk', 0))}"
    return str(trigger)


def describe_action(action):
    if not action:
        return "yok"
    if action.get("type") == "hotkey":
        hk = action.get("hotkey", "")
        if hk.lower() == "win+h":
            return "Win+H (Windows sesle yazma)"
        return hk
    return str(action)


def describe_binding(binding_item):
    return (
        f"{describe_trigger(binding_item.get('trigger'))} → "
        f"{describe_action(binding_item.get('action'))}"
    )
