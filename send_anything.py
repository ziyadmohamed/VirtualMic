"""
Send audio to StMicDriver using the custom device interface and KS property.
Reads driver GUIDs from StMicCommon.h (hardcoded here).

Usage:
  python send_anything.py [--wav path] [--freq 440] [--seconds 2] [--rate 48000]
                         [--device-index N] [--yes]

WAV must be 16-bit mono PCM.
"""
import ctypes
from ctypes import wintypes
import struct
import math
import sys
import time

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
setupapi = ctypes.WinDLL("setupapi", use_last_error=True)

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
kernel32.CreateFileW.restype = wintypes.HANDLE

kernel32.DeviceIoControl.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
kernel32.DeviceIoControl.restype = wintypes.BOOL

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

# GUID structure
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]

# From StMicCommon.h
KSPROPERTY_SET_STMIC = GUID(
    0x12345678, 0x1234, 0x5678,
    (wintypes.BYTE * 8)(0x12, 0x34, 0x56, 0x78, 0x12, 0x34, 0x56, 0x78)
)
KSCATEGORY_STMIC_INTERFACE = GUID(
    0xd58971b1, 0x3ad2, 0x4c90,
    (wintypes.BYTE * 8)(0x9e, 0x11, 0x37, 0x33, 0xa7, 0x4a, 0x36, 0x00)
)
KSCATEGORY_AUDIO = GUID(
    0x6994AD04, 0x93EF, 0x11D0,
    (wintypes.BYTE * 8)(0xA3, 0xCC, 0x00, 0xA0, 0xC9, 0x22, 0x31, 0x96)
)
KSCATEGORY_CAPTURE = GUID(
    0x65E8773D, 0x8F56, 0x11D0,
    (wintypes.BYTE * 8)(0xA3, 0xB9, 0x00, 0xA0, 0xC9, 0x22, 0x31, 0x96)
)
KSCATEGORY_REALTIME = GUID(
    0xEB115FFC, 0x10C8, 0x4964,
    (wintypes.BYTE * 8)(0x83, 0x1D, 0x6D, 0xCB, 0x02, 0xE6, 0xF2, 0x3F)
)

class KSPROPERTY(ctypes.Structure):
    _fields_ = [
        ("Set", GUID),
        ("Id", wintypes.DWORD),
        ("Flags", wintypes.DWORD),
    ]

KSPROPERTY_TYPE_SET = 0x00000001
KSPROPERTY_STMIC_PUSHAUDIO = 1

# IOCTL_KS_PROPERTY (METHOD_NEITHER)
FILE_DEVICE_KS = 0x2F
METHOD_NEITHER = 3
FILE_ANY_ACCESS = 0

def CTL_CODE(DeviceType, Function, Method, Access):
    return (DeviceType << 16) | (Access << 14) | (Function << 2) | Method

IOCTL_KS_PROPERTY = CTL_CODE(FILE_DEVICE_KS, 0x0, METHOD_NEITHER, FILE_ANY_ACCESS)

# SetupAPI constants
DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010

# Direct device paths (usually not created by this driver)
default_device_paths = [
    r"\\.\SimpleAudioSample",
    r"\\.\GLOBAL\SimpleAudioSample",
    r"\\.\SimpleAudioSample0",
]

# SetupAPI prototypes
setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE

class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]

setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.POINTER(GUID),
    wintypes.DWORD,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
]
setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL

setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL

setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL


def generate_tone(freq=440.0, seconds=2.0, sample_rate=48000):
    samples = int(sample_rate * seconds)
    data = bytearray()
    for i in range(samples):
        t = i / sample_rate
        sample = math.sin(2 * math.pi * freq * t)
        pcm = int(sample * 32767)
        data.extend(struct.pack('<h', pcm))
    return bytes(data)


def load_wav(path):
    import wave
    with wave.open(path, 'rb') as wf:
        if wf.getsampwidth() != 2 or wf.getnchannels() != 1:
            raise ValueError("WAV must be 16-bit mono PCM")
        frames = wf.readframes(wf.getnframes())
        return frames, wf.getframerate()


def try_direct_ioctl(audio_data):
    ioctl = CTL_CODE(0x22, 0x800 + 1, 0, 0)

    for path in default_device_paths:
        handle = kernel32.CreateFileW(
            path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if handle != INVALID_HANDLE_VALUE:
            buffer = struct.pack('I', len(audio_data)) + audio_data
            bytes_returned = wintypes.DWORD()
            ok = kernel32.DeviceIoControl(
                handle,
                ioctl,
                buffer,
                len(buffer),
                None,
                0,
                ctypes.byref(bytes_returned),
                None,
            )
            kernel32.CloseHandle(handle)
            if ok:
                print("Direct IOCTL send succeeded on", path)
                return True
            print("Direct IOCTL failed on", path, "error", ctypes.get_last_error())
        else:
            err = ctypes.get_last_error()
            if err != 2:
                print("CreateFile failed on", path, "error", err)
    return False


def enumerate_device_interfaces(interface_guid):
    hDevInfo = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(interface_guid),
        None,
        None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE,
    )
    if hDevInfo == INVALID_HANDLE_VALUE:
        print("SetupDiGetClassDevsW failed, error", ctypes.get_last_error())
        return []

    dev_data = SP_DEVICE_INTERFACE_DATA()
    dev_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)

    paths = []
    index = 0
    while True:
        ok = setupapi.SetupDiEnumDeviceInterfaces(
            hDevInfo,
            None,
            ctypes.byref(interface_guid),
            index,
            ctypes.byref(dev_data),
        )
        if not ok:
            err = ctypes.get_last_error()
            if err != 259:  # ERROR_NO_MORE_ITEMS
                print("SetupDiEnumDeviceInterfaces error", err)
            break

        required_size = wintypes.DWORD(0)
        setupapi.SetupDiGetDeviceInterfaceDetailW(
            hDevInfo,
            ctypes.byref(dev_data),
            None,
            0,
            ctypes.byref(required_size),
            None,
        )
        if required_size.value == 0:
            index += 1
            continue

        buffer = ctypes.create_string_buffer(required_size.value)
        cbsize = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
        ctypes.memmove(buffer, ctypes.byref(wintypes.DWORD(cbsize)), 4)

        ok = setupapi.SetupDiGetDeviceInterfaceDetailW(
            hDevInfo,
            ctypes.byref(dev_data),
            buffer,
            required_size,
            None,
            None,
        )
        if not ok:
            print("SetupDiGetDeviceInterfaceDetailW error", ctypes.get_last_error())
            index += 1
            continue

        offset = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 4
        device_path = ctypes.wstring_at(ctypes.addressof(buffer) + offset)
        if device_path and not device_path.startswith("\\\\?\\"):
            # Some buffers show missing prefix; fix it if needed
            if device_path.startswith("?\\"):
                device_path = "\\\\" + device_path
            elif device_path.startswith("\\"):
                device_path = "\\?" + device_path
        if device_path:
            paths.append(device_path)

        index += 1

    setupapi.SetupDiDestroyDeviceInfoList(hDevInfo)
    return paths


def _pick_from_list(paths):
    for i, p in enumerate(paths):
        print("  [" + str(i) + "]", p[:160])
    try:
        choice = input("Select device index: ").strip()
        idx = int(choice)
        if 0 <= idx < len(paths):
            return paths[idx]
    except Exception:
        return None
    return None


def _path_score(path):
    p = path.lower()
    score = 0
    if "root#media#0001" in p:
        score += 100
    if "wavemicarray1" in p:
        score += 80
    elif "wave" in p:
        score += 40
    if "{d58971b1-3ad2-4c90-9e11-3733a74a3600}" in p:
        score += 60
    if "simpleaudiosample" in p or "bm mic" in p:
        score += 30
    return score


def find_stmic_interface(non_interactive=False, selected_index=None):
    print("Searching for StMic interfaces...")
    all_paths = []
    for category_name, category_guid in (
        ("custom", KSCATEGORY_STMIC_INTERFACE),
        ("audio", KSCATEGORY_AUDIO),
        ("capture", KSCATEGORY_CAPTURE),
        ("realtime", KSCATEGORY_REALTIME),
    ):
        paths = enumerate_device_interfaces(category_guid)
        if paths:
            print(f"  {category_name}: {len(paths)} interface(s)")
            all_paths.extend(paths)

    if not all_paths:
        return None

    unique_paths = []
    seen = set()
    for p in all_paths:
        if p not in seen:
            seen.add(p)
            unique_paths.append(p)

    unique_paths.sort(key=_path_score, reverse=True)
    root_media_paths = [p for p in unique_paths if "root#media#0001" in p.lower()]
    if root_media_paths:
        unique_paths = root_media_paths

    if selected_index is not None:
        if 0 <= selected_index < len(unique_paths):
            chosen = unique_paths[selected_index]
            print("Selected by --device-index:", chosen[:160])
            return [chosen]
        print("Invalid --device-index value:", selected_index)
        return []

    if non_interactive or (not sys.stdin.isatty()):
        print("Auto-selected first candidate:", unique_paths[0][:160])
        return unique_paths

    print("Candidate interfaces:")
    selected = _pick_from_list(unique_paths)
    return [selected] if selected else []


def send_via_ksproperty(device_path, audio_data):
    handle = kernel32.CreateFileW(
        device_path,
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        0,
        None,
    )
    if handle == INVALID_HANDLE_VALUE:
        print("CreateFile failed", ctypes.get_last_error())
        return False

    ksProp = KSPROPERTY()
    ksProp.Set = KSPROPERTY_SET_STMIC
    ksProp.Id = KSPROPERTY_STMIC_PUSHAUDIO
    ksProp.Flags = KSPROPERTY_TYPE_SET

    # Method 1: KSPROPERTY in input, data in output buffer
    data_size = len(audio_data)
    payload = struct.pack('<I', data_size) + audio_data
    bytes_returned = wintypes.DWORD()
    out_buffer = ctypes.create_string_buffer(payload)
    ok = kernel32.DeviceIoControl(
        handle,
        IOCTL_KS_PROPERTY,
        ctypes.byref(ksProp),
        ctypes.sizeof(ksProp),
        out_buffer,
        len(payload),
        ctypes.byref(bytes_returned),
        None,
    )
    if ok:
        kernel32.CloseHandle(handle)
        return True

    err1 = ctypes.get_last_error()

    # Method 2: KSPROPERTY + data in input buffer
    in_payload = bytes(ksProp) + payload
    in_buffer = ctypes.create_string_buffer(in_payload)
    ok2 = kernel32.DeviceIoControl(
        handle,
        IOCTL_KS_PROPERTY,
        in_buffer,
        len(in_payload),
        None,
        0,
        ctypes.byref(bytes_returned),
        None,
    )
    if ok2:
        kernel32.CloseHandle(handle)
        return True

    err2 = ctypes.get_last_error()

    # Method 3: KSPROPERTY + data in input, writable output buffer too
    in_buffer2 = ctypes.create_string_buffer(in_payload)
    out_buffer2 = ctypes.create_string_buffer(payload)
    ok3 = kernel32.DeviceIoControl(
        handle,
        IOCTL_KS_PROPERTY,
        in_buffer2,
        len(in_payload),
        out_buffer2,
        len(payload),
        ctypes.byref(bytes_returned),
        None,
    )
    kernel32.CloseHandle(handle)

    if ok3:
        return True

    err3 = ctypes.get_last_error()
    print("KSPROPERTY send failed", err1, "/", err2, "/", err3)
    return False


def main():
    wav_path = None
    freq = 440.0
    seconds = 2.0
    sample_rate = 48000
    selected_index = None
    non_interactive = False

    args = sys.argv[1:]
    if "--wav" in args:
        i = args.index("--wav")
        if i + 1 < len(args):
            wav_path = args[i + 1]
    if "--freq" in args:
        i = args.index("--freq")
        if i + 1 < len(args):
            freq = float(args[i + 1])
    if "--seconds" in args:
        i = args.index("--seconds")
        if i + 1 < len(args):
            seconds = float(args[i + 1])
    if "--rate" in args:
        i = args.index("--rate")
        if i + 1 < len(args):
            sample_rate = int(args[i + 1])
    if "--device-index" in args:
        i = args.index("--device-index")
        if i + 1 < len(args):
            selected_index = int(args[i + 1])
    if "--yes" in args:
        non_interactive = True

    if wav_path:
        audio_data, rate = load_wav(wav_path)
        sample_rate = rate
        print("Loaded WAV:", wav_path, "rate", sample_rate, "bytes", len(audio_data))
    else:
        audio_data = generate_tone(freq, seconds, sample_rate)
        print("Generated tone:", freq, "Hz", seconds, "sec", "rate", sample_rate, "bytes", len(audio_data))

    print("Trying direct IOCTL...")
    if try_direct_ioctl(audio_data):
        print("Direct IOCTL success")
        return

    print("Trying KS property on StMic interface...")
    device_paths = find_stmic_interface(
        non_interactive=non_interactive,
        selected_index=selected_index,
    )
    if not device_paths:
        print("No device interface found")
        return

    chunk_size = int(sample_rate * 0.1) * 2  # 100ms * 16-bit mono
    for device_path in device_paths:
        print("Using device path:", repr(device_path))
        total = 0
        ok_all = True
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i + chunk_size]
            if not send_via_ksproperty(device_path, chunk):
                ok_all = False
                print("Failed at", total, "on", device_path)
                break
            total += len(chunk)
            time.sleep(0.1)

        if ok_all:
            print("Done, sent", total, "bytes on", device_path)
            return

    print("All candidate interfaces failed.")


if __name__ == "__main__":
    main()
