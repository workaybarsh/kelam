"""hidbtn.py - Kucuk HID tus dinleyicisi (harici paket gerektirmez).

Windows hid.dll + setupapi.dll uzerinden dogrudan calisir. Amac: Windows'un
tanimadigi 'Voice Command' (Consumer Page 0x0C, usage 0x00CF) gibi tuslari
capture it and hand it to a callback.

Kullanim:
    from hidbtn import find_interface, listen
    path, label = find_interface(0x1915, 0x1025, usage_page=0x000C)
    listen(path, lambda usage, t: print(hex(usage)))
"""

import ctypes
from ctypes import wintypes as w

hid = ctypes.WinDLL("hid.dll")
setupapi = ctypes.WinDLL("setupapi.dll")
kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)

DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10
GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x01
FILE_SHARE_WRITE = 0x02
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", w.DWORD),
        ("Data2", w.WORD),
        ("Data3", w.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", w.DWORD),
        ("Reserved", ctypes.c_size_t),
    ]


class SP_DEVICE_INTERFACE_DETAIL_DATA(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("DevicePath", w.WCHAR * 1)]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Size", w.ULONG),
        ("VendorID", w.USHORT),
        ("ProductID", w.USHORT),
        ("VersionNumber", w.USHORT),
    ]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", w.USHORT),
        ("UsagePage", w.USHORT),
        ("InputReportByteLength", w.USHORT),
        ("OutputReportByteLength", w.USHORT),
        ("FeatureReportByteLength", w.USHORT),
        ("Reserved", w.USHORT * 17),
        ("NumberLinkCollectionNodes", w.USHORT),
        ("NumberInputButtonCaps", w.USHORT),
        ("NumberInputValueCaps", w.USHORT),
        ("NumberInputDataIndices", w.USHORT),
        ("NumberOutputButtonCaps", w.USHORT),
        ("NumberOutputValueCaps", w.USHORT),
        ("NumberOutputDataIndices", w.USHORT),
        ("NumberFeatureButtonCaps", w.USHORT),
        ("NumberFeatureValueCaps", w.USHORT),
        ("NumberFeatureDataIndices", w.USHORT),
    ]


hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
hid.HidD_GetAttributes.argtypes = [w.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
hid.HidD_GetPreparsedData.argtypes = [w.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]

setupapi.SetupDiGetClassDevsW.restype = w.HANDLE
setupapi.SetupDiGetClassDevsW.argtypes = [
    ctypes.POINTER(GUID),
    w.LPCWSTR,
    w.HWND,
    w.DWORD,
]
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    w.HANDLE,
    ctypes.c_void_p,
    ctypes.POINTER(GUID),
    w.DWORD,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
]
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    w.HANDLE,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
    ctypes.POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA),
    w.DWORD,
    ctypes.POINTER(w.DWORD),
    ctypes.c_void_p,
]
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [w.HANDLE]

kernel32.CreateFileW.restype = w.HANDLE
kernel32.CreateFileW.argtypes = [
    w.LPCWSTR,
    w.DWORD,
    w.DWORD,
    ctypes.c_void_p,
    w.DWORD,
    w.DWORD,
    w.HANDLE,
]
kernel32.CloseHandle.argtypes = [w.HANDLE]
kernel32.ReadFile.argtypes = [
    w.HANDLE,
    ctypes.c_void_p,
    w.DWORD,
    ctypes.POINTER(w.DWORD),
    ctypes.c_void_p,
]


def enumerate_paths():
    """Returns the device paths of every HID interface on the system."""
    guid = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(guid))
    hdev = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )
    if hdev == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())

    paths = []
    try:
        index = 0
        while True:
            did = SP_DEVICE_INTERFACE_DATA()
            did.cbSize = ctypes.sizeof(did)
            if not setupapi.SetupDiEnumDeviceInterfaces(
                hdev, None, ctypes.byref(guid), index, ctypes.byref(did)
            ):
                break
            index += 1

            required = w.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                hdev, ctypes.byref(did), None, 0, ctypes.byref(required), None
            )
            if required.value <= 0:
                continue

            buf = ctypes.create_string_buffer(required.value)
            ctypes.cast(buf, ctypes.POINTER(w.DWORD))[0] = ctypes.sizeof(
                SP_DEVICE_INTERFACE_DETAIL_DATA
            )
            if not setupapi.SetupDiGetDeviceInterfaceDetailW(
                hdev,
                ctypes.byref(did),
                ctypes.cast(buf, ctypes.POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA)),
                required.value,
                ctypes.byref(required),
                None,
            ):
                continue
            paths.append(
                ctypes.wstring_at(ctypes.addressof(buf) + ctypes.sizeof(w.DWORD))
            )
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(hdev)
    return paths


def open_path(path, access=GENERIC_READ):
    return kernel32.CreateFileW(
        path,
        access,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        0,
        None,
    )


def describe(path):
    """Returns VID/PID and usage of the interface (None if it cannot be opened)."""
    handle = open_path(path, 0)
    if handle is None or handle == INVALID_HANDLE_VALUE:
        return None
    try:
        attrs = HIDD_ATTRIBUTES()
        attrs.Size = ctypes.sizeof(attrs)
        if not hid.HidD_GetAttributes(handle, ctypes.byref(attrs)):
            return None
        info = {
            "path": path,
            "vid": attrs.VendorID,
            "pid": attrs.ProductID,
        }
        pp = ctypes.c_void_p()
        if hid.HidD_GetPreparsedData(handle, ctypes.byref(pp)) and pp:
            try:
                caps = HIDP_CAPS()
                if hid.HidP_GetCaps(pp, ctypes.byref(caps)):
                    info["usage_page"] = caps.UsagePage
                    info["usage"] = caps.Usage
                    info["input_report_len"] = caps.InputReportByteLength
            finally:
                hid.HidD_FreePreparsedData(pp)
        return info
    finally:
        kernel32.CloseHandle(handle)


def find_interface(vid, pid, usage_page=None, usage=None):
    """Finds the first interface matching VID/PID (and optional usage)."""
    for path in enumerate_paths():
        info = describe(path)
        if not info or info.get("vid") != vid or info.get("pid") != pid:
            continue
        if usage_page is not None and info.get("usage_page") != usage_page:
            continue
        if usage is not None and info.get("usage") != usage:
            continue
        return path, info
    return None, None


def listen(path, on_usage, on_error=None, stop_flag=None, report_len=3):
    """Listens to the interface; calls on_usage(usage, timestamp) on each press.

    Consumer Control raporu: [report_id, usage_lo, usage_hi]
    Tus birakildiginda usage 0 gelir, bu yuzden sadece 0 olmayanlar bildirilir.
    """
    handle = open_path(path, GENERIC_READ)
    if handle is None or handle == INVALID_HANDLE_VALUE:
        msg = f"Cannot open device (err={ctypes.get_last_error()})"
        if on_error:
            on_error(msg)
        return

    import time as _time

    buf = ctypes.create_string_buffer(max(report_len, 2) + 64)
    read = w.DWORD()
    try:
        while True:
            if stop_flag is not None and stop_flag.is_set():
                break
            ok = kernel32.ReadFile(
                handle,
                ctypes.cast(buf, ctypes.c_void_p),
                len(buf),
                ctypes.byref(read),
                None,
            )
            if not ok:
                err = ctypes.get_last_error()
                if stop_flag is not None and stop_flag.is_set():
                    break
                if on_error:
                    on_error(f"Read error (err={err})")
                break
            data = buf.raw[: read.value]
            if len(data) < 2:
                continue
            usage = data[1] | (data[2] << 8 if len(data) > 2 else 0)
            if usage:
                on_usage(usage, _time.time(), data)
    finally:
        kernel32.CloseHandle(handle)
