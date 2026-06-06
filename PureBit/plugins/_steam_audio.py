import ctypes
import math
import os

import numpy as np

from _steam_audio_support import STEAMAUDIO_VERSION, resolve_steam_audio_paths


STEAMAUDIO_INFO = resolve_steam_audio_paths()
STEAMAUDIO_ROOT = STEAMAUDIO_INFO["root"]
STEAMAUDIO_DLL_PATH = STEAMAUDIO_INFO["dll"]


class IPLContextSettings(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("logCallback", ctypes.c_void_p),
        ("allocateCallback", ctypes.c_void_p),
        ("freeCallback", ctypes.c_void_p),
        ("simdLevel", ctypes.c_int),
        ("flags", ctypes.c_int),
    ]


class IPLAudioSettings(ctypes.Structure):
    _fields_ = [("samplingRate", ctypes.c_int32), ("frameSize", ctypes.c_int32)]


class IPLHRTFSettings(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("sofaFileName", ctypes.c_char_p),
        ("sofaData", ctypes.POINTER(ctypes.c_uint8)),
        ("sofaDataSize", ctypes.c_int),
        ("volume", ctypes.c_float),
        ("normType", ctypes.c_int),
    ]


class IPLBinauralEffectSettings(ctypes.Structure):
    _fields_ = [("hrtf", ctypes.c_void_p)]


class IPLVector3(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float), ("z", ctypes.c_float)]


class IPLBinauralEffectParams(ctypes.Structure):
    _fields_ = [
        ("direction", IPLVector3),
        ("interpolation", ctypes.c_int),
        ("spatialBlend", ctypes.c_float),
        ("hrtf", ctypes.c_void_p),
        ("peakDelays", ctypes.POINTER(ctypes.c_float)),
    ]


class IPLAudioBuffer(ctypes.Structure):
    _fields_ = [
        ("numChannels", ctypes.c_int32),
        ("numSamples", ctypes.c_int32),
        ("data", ctypes.POINTER(ctypes.POINTER(ctypes.c_float))),
    ]


IPL_SIMDLEVEL_AVX2 = 3
IPL_HRTFTYPE_DEFAULT = 0
IPL_HRTFNORMTYPE_RMS = 1
IPL_HRTFINTERPOLATION_NEAREST = 0


def direction_from_angles(azimuth_deg, elevation_deg):
    azimuth = math.radians(float(azimuth_deg))
    elevation = math.radians(float(elevation_deg))
    cos_elevation = math.cos(elevation)
    x = math.sin(azimuth) * cos_elevation
    y = math.sin(elevation)
    z = -math.cos(azimuth) * cos_elevation
    norm = max(1e-6, math.sqrt((x * x) + (y * y) + (z * z)))
    return IPLVector3(x / norm, y / norm, z / norm)


def pan_mono(mono_block, pan):
    mono = np.asarray(mono_block, dtype=np.float32)
    pan = float(np.clip(pan, -1.0, 1.0))
    angle = (pan + 1.0) * (math.pi * 0.25)
    left = mono * math.cos(angle)
    right = mono * math.sin(angle)
    return np.column_stack((left, right)).astype(np.float32, copy=False)


class SteamAudioBinaural:
    def __init__(self, sample_rate=48000):
        self.sample_rate = int(sample_rate)
        self.available = False
        self.error = None
        self.dll = None
        self.context = ctypes.c_void_p()
        self.hrtf = ctypes.c_void_p()
        self.effect = ctypes.c_void_p()
        self.frame_size = 0

        self._peak_delays = (ctypes.c_float * 2)()
        self._params = IPLBinauralEffectParams()
        self._mono = None
        self._left = None
        self._right = None
        self._input_ptrs = None
        self._output_ptrs = None
        self._input_buffer = IPLAudioBuffer()
        self._output_buffer = IPLAudioBuffer()

    def _bind_shared(self, dll):
        dll.iplContextCreate.argtypes = [ctypes.POINTER(IPLContextSettings), ctypes.POINTER(ctypes.c_void_p)]
        dll.iplContextCreate.restype = ctypes.c_int
        dll.iplContextRelease.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        dll.iplContextRelease.restype = None
        dll.iplHRTFCreate.argtypes = [ctypes.c_void_p, ctypes.POINTER(IPLAudioSettings), ctypes.POINTER(IPLHRTFSettings), ctypes.POINTER(ctypes.c_void_p)]
        dll.iplHRTFCreate.restype = ctypes.c_int
        dll.iplHRTFRelease.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        dll.iplHRTFRelease.restype = None
        dll.iplBinauralEffectCreate.argtypes = [ctypes.c_void_p, ctypes.POINTER(IPLAudioSettings), ctypes.POINTER(IPLBinauralEffectSettings), ctypes.POINTER(ctypes.c_void_p)]
        dll.iplBinauralEffectCreate.restype = ctypes.c_int
        dll.iplBinauralEffectApply.argtypes = [ctypes.c_void_p, ctypes.POINTER(IPLBinauralEffectParams), ctypes.POINTER(IPLAudioBuffer), ctypes.POINTER(IPLAudioBuffer)]
        dll.iplBinauralEffectApply.restype = ctypes.c_int
        dll.iplBinauralEffectReset.argtypes = [ctypes.c_void_p]
        dll.iplBinauralEffectReset.restype = None
        dll.iplBinauralEffectRelease.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        dll.iplBinauralEffectRelease.restype = None

    def _lazy_load(self):
        import _steam_audio_support
        if _steam_audio_support._SHARED_DLL is None:
            if os.name != "nt" or not os.path.exists(STEAMAUDIO_DLL_PATH):
                self.error = f"Steam Audio DLL not found at {STEAMAUDIO_DLL_PATH}"
                return False
            try:
                _steam_audio_support._SHARED_DLL = ctypes.WinDLL(STEAMAUDIO_DLL_PATH)
                self._bind_shared(_steam_audio_support._SHARED_DLL)
            except Exception as exc:
                self.error = f"DLL load failed: {exc}"
                return False

        self.dll = _steam_audio_support._SHARED_DLL

        if _steam_audio_support._SHARED_CONTEXT is None:
            try:
                settings = IPLContextSettings(STEAMAUDIO_VERSION, None, None, None, IPL_SIMDLEVEL_AVX2, 0)
                ctx = ctypes.c_void_p()
                status = self.dll.iplContextCreate(ctypes.byref(settings), ctypes.byref(ctx))
                if status != 0 or not ctx.value:
                    self.error = f"Steam Audio context failed: {status}"
                    return False
                _steam_audio_support._SHARED_CONTEXT = ctx
            except Exception as exc:
                self.error = f"Context creation failed: {exc}"
                return False

        self.context = _steam_audio_support._SHARED_CONTEXT
        self.available = True
        return True

    def _release_pipeline(self):
        if self.effect.value and self.dll is not None:
            self.dll.iplBinauralEffectRelease(ctypes.byref(self.effect))
        if self.hrtf.value and self.dll is not None:
            self.dll.iplHRTFRelease(ctypes.byref(self.hrtf))
        self.effect = ctypes.c_void_p()
        self.hrtf = ctypes.c_void_p()
        self.frame_size = 0

    def close(self):
        self._release_pipeline()
        self.context = ctypes.c_void_p()
        self.dll = None
        self.available = False

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _ensure_buffers(self, frame_size):
        if self._mono is not None and self.frame_size == frame_size:
            return

        self._mono = np.zeros(frame_size, dtype=np.float32)
        self._left = np.zeros(frame_size, dtype=np.float32)
        self._right = np.zeros(frame_size, dtype=np.float32)
        mono_ptr = self._mono.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        left_ptr = self._left.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        right_ptr = self._right.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        self._input_ptrs = (ctypes.POINTER(ctypes.c_float) * 1)(mono_ptr)
        self._output_ptrs = (ctypes.POINTER(ctypes.c_float) * 2)(left_ptr, right_ptr)
        self._input_buffer = IPLAudioBuffer(1, frame_size, self._input_ptrs)
        self._output_buffer = IPLAudioBuffer(2, frame_size, self._output_ptrs)

    def _ensure_pipeline(self, frame_size):
        if not self.available or not self.context.value:
            if not self._lazy_load():
                return False
        if self.effect.value and self.frame_size == frame_size:
            return True

        self._release_pipeline()
        self._ensure_buffers(frame_size)

        audio_settings = IPLAudioSettings(self.sample_rate, frame_size)
        hrtf_settings = IPLHRTFSettings(IPL_HRTFTYPE_DEFAULT, None, None, 0, 1.0, IPL_HRTFNORMTYPE_RMS)
        if self.dll.iplHRTFCreate(self.context, ctypes.byref(audio_settings), ctypes.byref(hrtf_settings), ctypes.byref(self.hrtf)) != 0:
            self.error = "Steam Audio HRTF create failed"
            return False

        effect_settings = IPLBinauralEffectSettings(self.hrtf)
        if self.dll.iplBinauralEffectCreate(self.context, ctypes.byref(audio_settings), ctypes.byref(effect_settings), ctypes.byref(self.effect)) != 0:
            self.error = "Steam Audio binaural effect create failed"
            self._release_pipeline()
            return False

        self.frame_size = frame_size
        return True

    def process(self, mono_block, azimuth_deg, elevation_deg, spatial_blend):
        mono = np.asarray(mono_block, dtype=np.float32)
        if mono.ndim != 1 or mono.size == 0:
            return np.zeros((0, 2), dtype=np.float32)
        if not self._ensure_pipeline(int(mono.shape[0])):
            pan = float(np.clip(azimuth_deg / 55.0, -1.0, 1.0))
            return pan_mono(mono, pan)

        self._mono[:] = mono
        self._left.fill(0.0)
        self._right.fill(0.0)
        self._params.direction = direction_from_angles(azimuth_deg, elevation_deg)
        self._params.interpolation = IPL_HRTFINTERPOLATION_NEAREST
        self._params.spatialBlend = float(np.clip(spatial_blend, 0.0, 1.0))
        self._params.hrtf = self.hrtf
        self._params.peakDelays = self._peak_delays

        self.dll.iplBinauralEffectApply(
            self.effect,
            ctypes.byref(self._params),
            ctypes.byref(self._input_buffer),
            ctypes.byref(self._output_buffer),
        )

        output = np.empty((mono.shape[0], 2), dtype=np.float32)
        output[:, 0] = self._left
        output[:, 1] = self._right
        return output

