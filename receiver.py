"""
Bluetooth RFCOMM receiver for StMic.

This script connects from Windows to the Android phone over Bluetooth and
pushes the incoming PCM stream into the BM Mic driver.

Android side defaults:
- 48 kHz
- PCM 16-bit
- mono unless the "Stereo" option is enabled

BM Mic expects 48 kHz, 32-bit, stereo PCM, so the receiver converts the
incoming stream before injecting it into the driver.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import socket
import struct
import sys
import time

try:
    import numpy as np
except ImportError:
    np = None

try:
    import sounddevice as sd
except ImportError:
    sd = None


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


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


KSPROPERTY_SET_STMIC = GUID(
    0x12345678, 0x1234, 0x5678,
    (wintypes.BYTE * 8)(0x12, 0x34, 0x56, 0x78, 0x12, 0x34, 0x56, 0x78),
)
KSCATEGORY_STMIC_INTERFACE = GUID(
    0xD58971B1, 0x3AD2, 0x4C90,
    (wintypes.BYTE * 8)(0x9E, 0x11, 0x37, 0x33, 0xA7, 0x4A, 0x36, 0x00),
)
KSCATEGORY_AUDIO = GUID(
    0x6994AD04, 0x93EF, 0x11D0,
    (wintypes.BYTE * 8)(0xA3, 0xCC, 0x00, 0xA0, 0xC9, 0x22, 0x31, 0x96),
)
KSCATEGORY_CAPTURE = GUID(
    0x65E8773D, 0x8F56, 0x11D0,
    (wintypes.BYTE * 8)(0xA3, 0xB9, 0x00, 0xA0, 0xC9, 0x22, 0x31, 0x96),
)

KSPROPERTY_STMIC_PUSHAUDIO = 1
KSPROPERTY_TYPE_SET = 0x00000002
DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010

DEFAULT_DEVICE_PATHS = [
    r"\\.\SimpleAudioSample",
    r"\\.\GLOBAL\SimpleAudioSample",
    r"\\.\SimpleAudioSample0",
]
STREAM_HEADER_MAGIC = b"STM1"
STREAM_HEADER_SIZE = 12
PCM16_FORMAT_CODE = 1
PCM_FLOAT32_FORMAT_CODE = 3


def ctl_code(device_type: int, function: int, method: int, access: int) -> int:
    return (device_type << 16) | (access << 14) | (function << 2) | method


IOCTL_KS_PROPERTY = ctl_code(0x2F, 0x0, 3, 0)


class KSPROPERTY(ctypes.Structure):
    _fields_ = [
        ("Set", GUID),
        ("Id", wintypes.DWORD),
        ("Flags", wintypes.DWORD),
    ]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


setupapi.SetupDiGetClassDevsW.argtypes = [
    ctypes.POINTER(GUID),
    wintypes.LPCWSTR,
    wintypes.HWND,
    wintypes.DWORD,
]
setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE

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


def enumerate_device_interfaces(interface_guid: GUID) -> list[str]:
    info_set = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(interface_guid),
        None,
        None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE,
    )
    if info_set == INVALID_HANDLE_VALUE:
        return []

    results: list[str] = []
    index = 0
    interface_data = SP_DEVICE_INTERFACE_DATA()
    interface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)

    while True:
        ok = setupapi.SetupDiEnumDeviceInterfaces(
            info_set,
            None,
            ctypes.byref(interface_guid),
            index,
            ctypes.byref(interface_data),
        )
        if not ok:
            break

        required = wintypes.DWORD(0)
        setupapi.SetupDiGetDeviceInterfaceDetailW(
            info_set,
            ctypes.byref(interface_data),
            None,
            0,
            ctypes.byref(required),
            None,
        )
        if required.value == 0:
            index += 1
            continue

        buffer = ctypes.create_string_buffer(required.value)
        cbsize = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
        ctypes.memmove(buffer, ctypes.byref(wintypes.DWORD(cbsize)), 4)

        ok = setupapi.SetupDiGetDeviceInterfaceDetailW(
            info_set,
            ctypes.byref(interface_data),
            buffer,
            required,
            None,
            None,
        )
        if ok:
            offset = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 4
            path = ctypes.wstring_at(ctypes.addressof(buffer) + offset)
            if path:
                if not path.startswith("\\\\?\\"):
                    if path.startswith("?\\"):
                        path = "\\\\" + path
                    elif path.startswith("\\"):
                        path = "\\?" + path
                results.append(path)

        index += 1

    setupapi.SetupDiDestroyDeviceInfoList(info_set)
    return results


def _path_score(path: str) -> int:
    value = path.lower()
    score = 0
    if "root#media#0001" in value:
        score += 100
    if "wavemicarray1" in value:
        score += 80
    elif "wave" in value:
        score += 40
    if "{d58971b1-3ad2-4c90-9e11-3733a74a3600}" in value:
        score += 60
    if "simpleaudiosample" in value or "bm mic" in value:
        score += 30
    return score


def find_stmic_interfaces(selected_index: int | None = None) -> list[str]:
    all_paths: list[str] = []
    for guid in (KSCATEGORY_STMIC_INTERFACE, KSCATEGORY_AUDIO, KSCATEGORY_CAPTURE):
        all_paths.extend(enumerate_device_interfaces(guid))

    unique_paths = sorted(set(all_paths), key=_path_score, reverse=True)
    root_media_paths = [path for path in unique_paths if "root#media#0001" in path.lower()]
    if root_media_paths:
        unique_paths = root_media_paths

    if selected_index is None:
        return unique_paths

    if 0 <= selected_index < len(unique_paths):
        return [unique_paths[selected_index]]
    return []


class StMicKsClient:
    def __init__(self, device_path: str):
        self.device_path = device_path
        self.handle = None
        self.send_mode = None

    def open(self) -> None:
        self.handle = kernel32.CreateFileW(
            self.device_path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if self.handle == INVALID_HANDLE_VALUE:
            error = ctypes.get_last_error()
            raise OSError(error, f"CreateFile failed for {self.device_path}")

    def close(self) -> None:
        if self.handle and self.handle != INVALID_HANDLE_VALUE:
            kernel32.CloseHandle(self.handle)
        self.handle = None
        self.send_mode = None

    def push_audio(self, audio_data: bytes) -> bool:
        if not audio_data:
            return True
        if not self.handle or self.handle == INVALID_HANDLE_VALUE:
            raise RuntimeError("BM Mic driver handle is not open")

        if self.send_mode is not None:
            return self._send_with_mode(self.send_mode, audio_data)

        for mode in (1, 2, 3):
            if self._send_with_mode(mode, audio_data):
                self.send_mode = mode
                return True

        return False

    def _send_with_mode(self, mode: int, audio_data: bytes) -> bool:
        property_header = KSPROPERTY()
        property_header.Set = KSPROPERTY_SET_STMIC
        property_header.Id = KSPROPERTY_STMIC_PUSHAUDIO
        property_header.Flags = KSPROPERTY_TYPE_SET

        payload = struct.pack("<I", len(audio_data)) + audio_data
        bytes_returned = wintypes.DWORD()

        if mode == 1:
            out_buffer = ctypes.create_string_buffer(payload)
            ok = kernel32.DeviceIoControl(
                self.handle,
                IOCTL_KS_PROPERTY,
                ctypes.byref(property_header),
                ctypes.sizeof(property_header),
                out_buffer,
                len(payload),
                ctypes.byref(bytes_returned),
                None,
            )
            return bool(ok)

        in_payload = bytes(property_header) + payload
        in_buffer = ctypes.create_string_buffer(in_payload)

        if mode == 2:
            ok = kernel32.DeviceIoControl(
                self.handle,
                IOCTL_KS_PROPERTY,
                in_buffer,
                len(in_payload),
                None,
                0,
                ctypes.byref(bytes_returned),
                None,
            )
            return bool(ok)

        if mode == 3:
            out_buffer = ctypes.create_string_buffer(payload)
            ok = kernel32.DeviceIoControl(
                self.handle,
                IOCTL_KS_PROPERTY,
                in_buffer,
                len(in_payload),
                out_buffer,
                len(payload),
                ctypes.byref(bytes_returned),
                None,
            )
            return bool(ok)

        return False


class BmMicDrain:
    def __init__(self, device_name_hint: str = "bm mic"):
        self.device_name_hint = device_name_hint.lower()
        self.stream = None

    def start(self) -> None:
        if sd is None:
            return

        device_index = self._find_preferred_device()
        if device_index is None:
            return

        self.stream = sd.RawInputStream(
            samplerate=48000,
            blocksize=480,
            channels=1,
            dtype="int16",
            device=device_index,
            callback=self._callback,
            latency="low",
        )
        self.stream.start()
        print(f"Opened BM Mic drain stream on device index {device_index}")

    def close(self) -> None:
        if self.stream is None:
            return
        try:
            self.stream.stop()
        finally:
            self.stream.close()
            self.stream = None

    def _callback(self, indata, frames, time_info, status):
        _ = (indata, frames, time_info, status)

    def _find_preferred_device(self) -> int | None:
        devices = sd.query_devices()
        candidates = []
        for idx, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) <= 0:
                continue
            name = dev.get("name", "").lower()
            if self.device_name_hint not in name:
                continue
            score = 0
            if dev.get("hostapi") == 2:
                score += 100
            if "virtual microphone" in name:
                score += 20
            if dev.get("default_samplerate") == 48000.0:
                score += 10
            candidates.append((score, idx))

        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][1]


def open_bmmic_client(selected_index: int | None = None) -> StMicKsClient:
    last_error = None
    candidate_paths = find_stmic_interfaces(selected_index)
    candidate_paths.extend(path for path in DEFAULT_DEVICE_PATHS if path not in candidate_paths)

    for path in candidate_paths:
        try:
            client = StMicKsClient(path)
            client.open()
            print(f"Using BM Mic device path: {path}")
            return client
        except OSError as exc:
            last_error = exc

    if last_error:
        raise last_error
    raise RuntimeError("No BM Mic device interface was found")


def normalize_mac_address(value: str) -> str:
    cleaned = value.strip().replace("-", ":").upper()
    if len(cleaned) != 17:
        raise ValueError("Bluetooth MAC address must look like AA:BB:CC:DD:EE:FF")
    return cleaned


def _format_bt_exception(exc: BaseException) -> str:
    code = getattr(exc, "winerror", None)
    if code is None:
        code = getattr(exc, "errno", None)
    if code is not None:
        return str(code)
    if getattr(exc, "args", None):
        return "/".join(str(part) for part in exc.args if part not in (None, ""))
    return repr(exc)


def connect_rfcomm(
    mac_address: str,
    channel: int | None,
    scan_max_channel: int,
    timeout_seconds: float,
    attempts: int,
    retry_delay: float,
):
    if not hasattr(socket, "AF_BLUETOOTH"):
        raise RuntimeError("This Python build does not expose Bluetooth sockets")

    channels = [channel] if channel is not None else list(range(1, scan_max_channel + 1))
    failures = []

    for candidate in channels:
        for attempt in range(1, attempts + 1):
            sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            sock.settimeout(timeout_seconds)
            try:
                print(
                    f"Trying RFCOMM channel {candidate} "
                    f"(attempt {attempt}/{attempts}, timeout {timeout_seconds:.1f}s)..."
                )
                sock.connect((mac_address, candidate))
                sock.settimeout(None)
                return sock, candidate
            except OSError as exc:
                failures.append((candidate, exc))
                sock.close()
                if attempt < attempts and retry_delay > 0:
                    time.sleep(retry_delay)

    details = ", ".join(
        f"{candidate}:{_format_bt_exception(exc)}"
        for candidate, exc in failures[:8]
    )
    raise ConnectionError(f"Bluetooth connection failed. Tried channels: {details}")


def bytes_per_sample_for_format(format_code: int) -> int:
    if format_code == PCM16_FORMAT_CODE:
        return 2
    if format_code == PCM_FLOAT32_FORMAT_CODE:
        return 4
    raise ValueError(f"Unsupported Bluetooth audio format code: {format_code}")


def format_name(format_code: int) -> str:
    if format_code == PCM16_FORMAT_CODE:
        return "pcm16"
    if format_code == PCM_FLOAT32_FORMAT_CODE:
        return "float32"
    return f"unknown({format_code})"


def convert_input_to_bmmic(
    data: bytes,
    input_channels: int,
    input_sample_rate: int,
    format_code: int,
    gain: float,
) -> bytes:
    if format_code == PCM16_FORMAT_CODE:
        return convert_pcm16_to_bmmic(data, input_channels, input_sample_rate, gain)
    if format_code == PCM_FLOAT32_FORMAT_CODE:
        return convert_float32_to_bmmic(data, input_channels, input_sample_rate, gain)
    raise ValueError(f"Unsupported Bluetooth audio format code: {format_code}")


def convert_pcm16_to_bmmic(data: bytes, input_channels: int, input_sample_rate: int, gain: float) -> bytes:
    if input_channels not in (1, 2):
        raise ValueError("Only mono or stereo PCM16 input is supported")
    if 48000 % input_sample_rate != 0:
        raise ValueError("Input sample rate must divide 48000 for BM Mic conversion")

    if np is not None:
        return convert_pcm16_to_bmmic_numpy(data, input_channels, input_sample_rate, gain)
    return convert_pcm16_to_bmmic_python(data, input_channels, input_sample_rate, gain)


def _resample_factor(input_sample_rate: int) -> int:
    return 48000 // input_sample_rate


def _downmix_numpy(frames):
    if frames.shape[1] == 1:
        return frames[:, 0].astype(np.float32)
    left = frames[:, 0].astype(np.float32)
    right = frames[:, 1].astype(np.float32)
    return ((left * 0.75) + (right * 0.25))


def _upsample_linear_numpy(samples: np.ndarray, factor: int) -> np.ndarray:
    if factor == 1 or samples.size == 0:
        return samples
    x_old = np.arange(samples.shape[0], dtype=np.float32)
    x_new = np.arange(samples.shape[0] * factor, dtype=np.float32) / factor
    if samples.shape[0] == 1:
        return np.repeat(samples, factor)
    return np.interp(x_new, x_old, samples).astype(np.float32)


def convert_pcm16_to_bmmic_numpy(data: bytes, input_channels: int, input_sample_rate: int, gain: float) -> bytes:
    samples = np.frombuffer(data, dtype="<i2")
    if samples.size == 0:
        return b""
    frames = samples.reshape(-1, input_channels)
    factor = _resample_factor(input_sample_rate)

    if input_channels == 1:
        mono = _downmix_numpy(frames)
        mono = _upsample_linear_numpy(mono, factor)
        if gain != 1.0:
            mono = np.clip(mono * gain, -32768, 32767)
        wide = mono.astype("<i4") << 16
        stereo = np.empty((wide.size, 2), dtype="<i4")
        stereo[:, 0] = wide
        stereo[:, 1] = wide
        return stereo.tobytes()

    left = _upsample_linear_numpy(frames[:, 0].astype(np.float32), factor)
    right = _upsample_linear_numpy(frames[:, 1].astype(np.float32), factor)
    if gain != 1.0:
        left = np.clip(left * gain, -32768, 32767)
        right = np.clip(right * gain, -32768, 32767)
    stereo = np.empty((left.size, 2), dtype="<i4")
    stereo[:, 0] = left.astype("<i4") << 16
    stereo[:, 1] = right.astype("<i4") << 16
    return stereo.tobytes()


def _downmix_python(data: bytes, input_channels: int) -> list[float]:
    if input_channels == 1:
        return [float(sample) for (sample,) in struct.iter_unpack("<h", data)]
    mixed = []
    for left, right in struct.iter_unpack("<hh", data):
        mixed.append((left * 0.75) + (right * 0.25))
    return mixed


def _upsample_linear_python(samples: list[float], factor: int) -> list[float]:
    if factor == 1 or len(samples) <= 1:
        if len(samples) == 1 and factor > 1:
            return samples * factor
        return samples
    out: list[float] = []
    for i in range(len(samples) - 1):
        start = samples[i]
        end = samples[i + 1]
        for step in range(factor):
            t = step / factor
            out.append(start + (end - start) * t)
    out.extend([samples[-1]] * factor)
    return out


def _split_stereo_python(data: bytes) -> tuple[list[float], list[float]]:
    left: list[float] = []
    right: list[float] = []
    for lval, rval in struct.iter_unpack("<hh", data):
        left.append(float(lval))
        right.append(float(rval))
    return left, right


def convert_pcm16_to_bmmic_python(data: bytes, input_channels: int, input_sample_rate: int, gain: float) -> bytes:
    factor = _resample_factor(input_sample_rate)
    if input_channels == 1:
        mono = _downmix_python(data, input_channels)
        mono = _upsample_linear_python(mono, factor)
        output = bytearray(len(mono) * 8)
        offset = 0
        for sample in mono:
            scaled = int(sample * gain)
            if scaled > 32767:
                scaled = 32767
            elif scaled < -32768:
                scaled = -32768
            wide = scaled << 16
            struct.pack_into("<ii", output, offset, wide, wide)
            offset += 8
        return bytes(output)

    left, right = _split_stereo_python(data)
    left = _upsample_linear_python(left, factor)
    right = _upsample_linear_python(right, factor)
    output = bytearray(len(left) * 8)
    offset = 0
    for lval, rval in zip(left, right):
        scaled_left = int(lval * gain)
        scaled_right = int(rval * gain)
        if scaled_left > 32767:
            scaled_left = 32767
        elif scaled_left < -32768:
            scaled_left = -32768
        if scaled_right > 32767:
            scaled_right = 32767
        elif scaled_right < -32768:
            scaled_right = -32768
        struct.pack_into("<ii", output, offset, scaled_left << 16, scaled_right << 16)
        offset += 8
    return bytes(output)


def convert_float32_to_bmmic(data: bytes, input_channels: int, input_sample_rate: int, gain: float) -> bytes:
    if input_channels not in (1, 2):
        raise ValueError("Only mono or stereo float32 input is supported")
    if 48000 % input_sample_rate != 0:
        raise ValueError("Input sample rate must divide 48000 for BM Mic conversion")

    if np is not None:
        return convert_float32_to_bmmic_numpy(data, input_channels, input_sample_rate, gain)
    return convert_float32_to_bmmic_python(data, input_channels, input_sample_rate, gain)


def convert_float32_to_bmmic_numpy(data: bytes, input_channels: int, input_sample_rate: int, gain: float) -> bytes:
    samples = np.frombuffer(data, dtype="<f4")
    if samples.size == 0:
        return b""
    frames = samples.reshape(-1, input_channels)
    factor = _resample_factor(input_sample_rate)

    if input_channels == 1:
        mono = _downmix_numpy(frames)
        mono = _upsample_linear_numpy(mono, factor)
        if gain != 1.0:
            mono = mono * gain
        mono = np.clip(mono, -1.0, 1.0)
        wide = (mono * 2147483647.0).astype("<i4")
        stereo = np.empty((wide.size, 2), dtype="<i4")
        stereo[:, 0] = wide
        stereo[:, 1] = wide
        return stereo.tobytes()

    left = _upsample_linear_numpy(frames[:, 0].astype(np.float32), factor)
    right = _upsample_linear_numpy(frames[:, 1].astype(np.float32), factor)
    if gain != 1.0:
        left = left * gain
        right = right * gain
    left = np.clip(left, -1.0, 1.0)
    right = np.clip(right, -1.0, 1.0)
    stereo = np.empty((left.size, 2), dtype="<i4")
    stereo[:, 0] = (left * 2147483647.0).astype("<i4")
    stereo[:, 1] = (right * 2147483647.0).astype("<i4")
    return stereo.tobytes()


def _downmix_float_python(data: bytes, input_channels: int) -> list[float]:
    if input_channels == 1:
        return [sample for (sample,) in struct.iter_unpack("<f", data)]
    mixed = []
    for left, right in struct.iter_unpack("<ff", data):
        mixed.append((left * 0.75) + (right * 0.25))
    return mixed


def _split_stereo_float_python(data: bytes) -> tuple[list[float], list[float]]:
    left: list[float] = []
    right: list[float] = []
    for lval, rval in struct.iter_unpack("<ff", data):
        left.append(lval)
        right.append(rval)
    return left, right


def convert_float32_to_bmmic_python(data: bytes, input_channels: int, input_sample_rate: int, gain: float) -> bytes:
    factor = _resample_factor(input_sample_rate)
    if input_channels == 1:
        mono = _downmix_float_python(data, input_channels)
        mono = _upsample_linear_python(mono, factor)
        output = bytearray(len(mono) * 8)
        offset = 0
        for sample in mono:
            scaled = int(max(-1.0, min(1.0, sample * gain)) * 2147483647.0)
            struct.pack_into("<ii", output, offset, scaled, scaled)
            offset += 8
        return bytes(output)

    left, right = _split_stereo_float_python(data)
    left = _upsample_linear_python(left, factor)
    right = _upsample_linear_python(right, factor)
    output = bytearray(len(left) * 8)
    offset = 0
    for lval, rval in zip(left, right):
        scaled_left = int(max(-1.0, min(1.0, lval * gain)) * 2147483647.0)
        scaled_right = int(max(-1.0, min(1.0, rval * gain)) * 2147483647.0)
        struct.pack_into("<ii", output, offset, scaled_left, scaled_right)
        offset += 8
    return bytes(output)


def read_stream_header(
    sock,
    fallback_sample_rate: int,
    fallback_channels: int,
    fallback_format_code: int,
) -> tuple[int, int, int, bytes]:
    initial = bytearray()
    while len(initial) < STREAM_HEADER_SIZE:
        chunk = sock.recv(STREAM_HEADER_SIZE - len(initial))
        if not chunk:
            break
        initial.extend(chunk)

    if len(initial) >= STREAM_HEADER_SIZE and bytes(initial[:4]) == STREAM_HEADER_MAGIC:
        _, sample_rate, channels, format_code = struct.unpack("<4sIHH", bytes(initial[:STREAM_HEADER_SIZE]))
        if format_code not in (PCM16_FORMAT_CODE, PCM_FLOAT32_FORMAT_CODE):
            raise RuntimeError(f"Unsupported Bluetooth audio format code: {format_code}")
        if channels not in (1, 2):
            raise RuntimeError(f"Unsupported Bluetooth channel count: {channels}")
        print(
            f"Detected Bluetooth stream header: {sample_rate} Hz, "
            f"{channels} channel(s), {format_name(format_code)}"
        )
        return sample_rate, channels, format_code, bytes(initial[STREAM_HEADER_SIZE:])

    print(
        "Bluetooth stream header missing or invalid; "
        f"using fallback {fallback_sample_rate} Hz, {fallback_channels} channel(s), "
        f"{format_name(fallback_format_code)}"
    )
    return fallback_sample_rate, fallback_channels, fallback_format_code, bytes(initial)


def stream_bluetooth_to_bmmic(args: argparse.Namespace) -> None:
    mac_address = normalize_mac_address(args.mac)

    driver = open_bmmic_client(args.device_index)
    drain = BmMicDrain()
    total_in = 0
    total_out = 0
    started_at = time.time()

    try:
        if not args.no_bmmic_drain:
            try:
                drain.start()
            except Exception as exc:
                print(f"Warning: could not open BM Mic drain stream: {exc}")
        sock, connected_channel = connect_rfcomm(
            mac_address,
            args.channel,
            args.scan_max_channel,
            args.connect_timeout,
            args.connect_attempts,
            args.retry_delay,
        )
        print(f"Connected to {mac_address} on RFCOMM channel {connected_channel}")
        fallback_sample_rate = args.sample_rate
        if fallback_sample_rate <= 0:
            fallback_sample_rate = 24000
        if args.input_format == "auto":
            fallback_format_code = PCM_FLOAT32_FORMAT_CODE if args.input_channels == 2 else PCM16_FORMAT_CODE
        elif args.input_format == "float32":
            fallback_format_code = PCM_FLOAT32_FORMAT_CODE
        else:
            fallback_format_code = PCM16_FORMAT_CODE
        stream_sample_rate, stream_channels, stream_format_code, initial_data = read_stream_header(
            sock,
            fallback_sample_rate,
            args.input_channels,
            fallback_format_code,
        )
        input_frame_bytes = stream_channels * bytes_per_sample_for_format(stream_format_code)
        frames_per_chunk = max(1, int(stream_sample_rate * (args.chunk_ms / 1000.0)))
        input_chunk_bytes = frames_per_chunk * input_frame_bytes
        recv_size = max(args.recv_size, input_chunk_bytes)
        print("Streaming Bluetooth audio into BM Mic...")

        pending = bytearray(initial_data)
        next_report = time.time() + 5.0
        last_flush = time.perf_counter()

        try:
            while True:
                data = sock.recv(recv_size)
                if not data:
                    print("Bluetooth connection closed by remote device.")
                    break

                total_in += len(data)
                pending.extend(data)

                while len(pending) >= input_chunk_bytes:
                    raw_chunk = bytes(pending[:input_chunk_bytes])
                    del pending[:input_chunk_bytes]

                    converted = convert_input_to_bmmic(
                        raw_chunk,
                        stream_channels,
                        stream_sample_rate,
                        stream_format_code,
                        args.gain,
                    )
                    if not driver.push_audio(converted):
                        raise RuntimeError("Failed to inject audio into BM Mic")
                    total_out += len(converted)
                    last_flush = time.perf_counter()

                partial_bytes = len(pending) - (len(pending) % input_frame_bytes)
                if partial_bytes > 0 and (time.perf_counter() - last_flush) * 1000.0 >= args.flush_ms:
                    raw_chunk = bytes(pending[:partial_bytes])
                    del pending[:partial_bytes]
                    converted = convert_input_to_bmmic(
                        raw_chunk,
                        stream_channels,
                        stream_sample_rate,
                        stream_format_code,
                        args.gain,
                    )
                    if not driver.push_audio(converted):
                        raise RuntimeError("Failed to inject audio into BM Mic")
                    total_out += len(converted)
                    last_flush = time.perf_counter()

                now = time.time()
                if now >= next_report:
                    seconds = total_in / float(stream_sample_rate * input_frame_bytes)
                    print(
                        f"Received {total_in} bytes ({seconds:.1f}s input), "
                        f"injected {total_out} bytes into BM Mic."
                    )
                    next_report = now + 5.0
        finally:
            usable = len(pending) - (len(pending) % input_frame_bytes)
            if usable > 0:
                converted = convert_input_to_bmmic(
                    bytes(pending[:usable]),
                    stream_channels,
                    stream_sample_rate,
                    stream_format_code,
                    args.gain,
                )
                if driver.push_audio(converted):
                    total_out += len(converted)
            sock.close()
    finally:
        drain.close()
        driver.close()

    elapsed = max(time.time() - started_at, 0.001)
    print(
        f"Finished. Received {total_in} bytes and injected {total_out} bytes "
        f"in {elapsed:.1f}s."
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Connect to the Android StMic Bluetooth server and inject audio into BM Mic."
    )
    parser.add_argument("--mac", required=True, help="Android Bluetooth MAC address, for example AA:BB:CC:DD:EE:FF")
    parser.add_argument("--channel", type=int, help="RFCOMM channel if you already know it")
    parser.add_argument("--scan-max-channel", type=int, default=30, help="Highest RFCOMM channel to probe when --channel is omitted")
    parser.add_argument("--connect-timeout", type=float, default=5.0, help="Per-channel Bluetooth connect timeout in seconds")
    parser.add_argument("--connect-attempts", type=int, default=2, help="How many times to try each RFCOMM channel before failing")
    parser.add_argument("--retry-delay", type=float, default=0.5, help="Delay between failed RFCOMM connect attempts in seconds")
    parser.add_argument("--sample-rate", type=int, default=0, help="Fallback input sample rate when the Bluetooth stream header is missing. Default: 24000")
    parser.add_argument("--input-channels", type=int, choices=(1, 2), default=1, help="Android stream channel count. Use 2 only if the app runs in Stereo mode")
    parser.add_argument("--input-format", choices=("auto", "pcm16", "float32"), default="auto", help="Fallback Bluetooth sample format when the stream header is missing")
    parser.add_argument("--chunk-ms", type=int, default=5, help="How much Bluetooth audio to batch before injecting into BM Mic")
    parser.add_argument("--flush-ms", type=float, default=3.0, help="Maximum time to wait before flushing a partial chunk into BM Mic")
    parser.add_argument("--recv-size", type=int, default=1024, help="Socket recv size in bytes")
    parser.add_argument("--gain", type=float, default=1.0, help="Digital gain applied before injecting into BM Mic")
    parser.add_argument("--no-bmmic-drain", action="store_true", help="Do not open a background BM Mic capture stream to keep latency down")
    parser.add_argument("--device-index", type=int, help="Optional BM Mic interface index from the internal candidate list")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    try:
        stream_bluetooth_to_bmmic(args)
        return 0
    except KeyboardInterrupt:
        print("Stopped by user.")
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
