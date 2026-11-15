"""Trigger layer: raw HID buttons plus Windows keyboard keys."""

import threading
import time

import hidbtn

CONSUMER_PAGE = 0x000C
VENDOR_PAGE_MIN = 0xFF00


def is_candidate(info):
    """Interfaces that may belong to a remote: Consumer Control or vendor-defined."""
    page = info.get("usage_page")
    if page is None:
        return False
    return page == CONSUMER_PAGE or page >= VENDOR_PAGE_MIN


def parse_report(data):
    """Consumer raporu: [report_id, usage_lo, usage_hi] -> (report_id, usage)"""
    if len(data) < 2:
        return None
    report_id = data[0]
    usage = data[1] | ((data[2] << 8) if len(data) > 2 else 0)
    return report_id, usage


def make_hid_event(info, report_id, usage, data):
    return {
        "type": "hid",
        "vid": info.get("vid"),
        "pid": info.get("pid"),
        "usage_page": info.get("usage_page"),
        "usage": usage,
        "report_id": report_id,
        "report_len": info.get("input_report_len"),
        "path": info.get("path"),
        "raw": data.hex(),
        "time": time.time(),
    }


class HidSupervisor(threading.Thread):
    """Listens to the matching HID interface and reconnects when it drops."""

    def __init__(self, on_event, stop_flag, selector=None, fixed_path=None, log=None):
        super().__init__(daemon=True)
        self.on_event = on_event
        self.stop_flag = stop_flag
        self.selector = selector
        self.fixed_path = fixed_path
        self.log = log
        self.last_error = None

    def _resolve(self):
        if self.fixed_path:
            info = hidbtn.describe(self.fixed_path)
            return (self.fixed_path, info) if info else (None, None)
        for path in hidbtn.enumerate_paths():
            info = hidbtn.describe(path)
            if info and self.selector and self.selector(info):
                return path, info
        return None, None

    def _on_usage(self, info, usage, ts, data):
        parsed = parse_report(data)
        report_id = parsed[0] if parsed else None
        self.on_event(make_hid_event(info, report_id, usage, data))

    def _on_error(self, msg):
        self.last_error = msg

    def run(self):
        state = None
        while not self.stop_flag.is_set():
            path, info = self._resolve()
            if not path:
                if state != "yok" and self.log:
                    self.log("device not found (asleep or out of range), retrying")
                state = "yok"
                self._wait(3.0)
                continue
            if state != "var" and self.log:
                self.log(f"listening: {info}")
            state = "var"
            hidbtn.listen(
                path,
                lambda usage, ts, data, i=info: self._on_usage(i, usage, ts, data),
                on_error=self._on_error,
                stop_flag=self.stop_flag,
                report_len=info.get("input_report_len", 3),
            )
            if self.stop_flag.is_set():
                break
            if self.log:
                self.log(f"connection lost: {self.last_error or 'read finished'}")
            state = "koptu"
            self._wait(2.0)

    def _wait(self, seconds):
        end = time.time() + seconds
        while time.time() < end and not self.stop_flag.is_set():
            time.sleep(0.15)


def capture_listeners(on_event, stop_flag, log=None):
    """Starts listening to every candidate interface (for the setup wizard)."""
    threads = []
    for path in hidbtn.enumerate_paths():
        info = hidbtn.describe(path)
        if not info or not is_candidate(info):
            continue
        worker = HidSupervisor(
            on_event, stop_flag, fixed_path=path, log=log
        )
        worker.start()
        threads.append(worker)
    return threads
