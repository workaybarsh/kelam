"""Kelam bridge: listens to every configured key and runs its action."""

import ctypes
import os
import threading
import time

import config as cfg
import hotkey
import keyhook
import paths
import trigger
from i18n import tr

BASE_DIR = paths.BASE_DIR
LOG_PATH = os.path.join(BASE_DIR, "bridge.log")
PID_PATH = os.path.join(BASE_DIR, "bridge.pid")
MUTEX_NAME = "KelamBridge"
ERROR_ALREADY_EXISTS = 183


class Bridge:
    def __init__(self, settings):
        self.settings = settings
        self.bindings = settings.get("bindings") or []
        self.debounce = max(0.05, settings.get("debounce_ms", 400) / 1000.0)
        self.stop_flag = threading.Event()
        self.last_fire: dict[int, float] = {}
        self.count = 0
        self.workers = []

    # -------------------------------------------------------------- helpers
    def log(self, message):
        line = f"{time.strftime('%H:%M:%S')} {message}"
        try:
            print(line, flush=True)
        except Exception:
            pass
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def rotate_log(self):
        try:
            if os.path.getsize(LOG_PATH) > 1_000_000:
                os.replace(LOG_PATH, LOG_PATH + ".1")
        except OSError:
            pass

    def beep(self, frequency=880):
        if not self.settings.get("beep", True):
            return
        try:
            threading.Thread(
                target=ctypes.windll.kernel32.Beep,
                args=(frequency, 60),
                daemon=True,
            ).start()
        except Exception:
            pass

    def fire(self, index):
        now = time.time()
        if now - self.last_fire.get(index, 0.0) < self.debounce:
            return
        self.last_fire[index] = now
        self.count += 1
        self.beep(880)

        action = (self.bindings[index].get("action") or {})
        spec = action.get("hotkey", "win+h")
        try:
            hotkey.send_spec(spec)
        except (ValueError, OSError) as exc:
            self.log(f"could not send hotkey ({spec}): {exc}")

    # ------------------------------------------------------------ dinleyici
    def _hid_handler(self, index, event):
        want = (self.bindings[index].get("trigger") or {}).get("usage")
        if want is not None and event["usage"] != want:
            return
        self.fire(index)

    def _key_handler(self, index, event):
        if keyhook.is_modifier(event["vk"]):
            return False
        if event["vk"] != (self.bindings[index].get("trigger") or {}).get("vk"):
            return False
        self.fire(index)
        return True  # swallow the key (when enabled)

    def _start_hid(self, index):
        item = self.bindings[index].get("trigger") or {}
        selector = lambda info: (  # noqa: E731
            info.get("vid") == item.get("vid")
            and info.get("pid") == item.get("pid")
            and info.get("usage_page") == item.get("usage_page")
        )
        worker = trigger.HidSupervisor(
            lambda event, i=index: self._hid_handler(i, event),
            self.stop_flag,
            selector=selector,
            log=lambda msg, i=index: self.log(f"[{i + 1}] {msg}"),
        )
        worker.start()
        self.workers.append(worker)

    def _start_key(self, index):
        worker = keyhook.KeyboardListener(
            lambda event, i=index: self._key_handler(i, event),
            swallow=bool(self.settings.get("swallow", True)),
        )
        worker.start()
        worker.ready.wait(2)
        if worker.last_error:
            self.log(f"[{index + 1}] keyboard hook error: {worker.last_error}")
        self.workers.append(worker)

    def run(self):
        self.rotate_log()
        self.log(f"started | {len(self.bindings)} key(s)")
        if not self.bindings:
            self.log(tr("no keys configured; open settings and add one"))
            return 1

        for index, item in enumerate(self.bindings):
            trigger_cfg = item.get("trigger") or {}
            self.log(
                f"[{index + 1}] {cfg.describe_trigger(trigger_cfg)} → "
                f"{cfg.describe_action(item.get('action'))}"
            )
            if trigger_cfg.get("type") == "hid":
                self._start_hid(index)
            elif trigger_cfg.get("type") == "key":
                self._start_key(index)
            else:
                self.log(f"[{index + 1}] unknown key type: {trigger_cfg.get('type')}")

        try:
            while not self.stop_flag.is_set():
                time.sleep(0.3)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop_flag.set()
            for worker in self.workers:
                if hasattr(worker, "stop"):
                    worker.stop()
            self.log(f"stopped (total {self.count} triggers)")
        return 0


def single_instance():
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    already = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
    return handle, already


def main():
    mutex, already = single_instance()
    if already:
        print(tr("Bridge is already running."), flush=True)
        return 0

    settings = cfg.load()
    bridge = Bridge(settings)
    try:
        with open(PID_PATH, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass

    try:
        return bridge.run()
    finally:
        try:
            os.remove(PID_PATH)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
