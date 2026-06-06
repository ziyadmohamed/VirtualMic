import math
import os
import threading
import wave

import numpy as np
import wx

try:
    import soundfile as sf
except Exception:
    sf = None

try:
    from scipy.signal import lfilter
except Exception:
    lfilter = None

from _plugin_utils import PluginControlDialog, load_settings, save_settings
from _steam_audio import SteamAudioBinaural, pan_mono


SAMPLE_RATE = 48000
MAX_IR_SAMPLES = 1000
ASSET_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets"))
AMBIENT_BED_ROOT = os.path.join(ASSET_ROOT, "ambient_space_beds")
AMBIENT_BED_FILES = {
    "airplane": os.path.join(AMBIENT_BED_ROOT, "airplane.wav"),
    "airport": os.path.join(AMBIENT_BED_ROOT, "airport.wav"),
    "airport_terminal_interior": os.path.join(AMBIENT_BED_ROOT, "airport_terminal_interior.wav"),
    "clock": os.path.join(AMBIENT_BED_ROOT, "clock.wav"),
    "const": os.path.join(AMBIENT_BED_ROOT, "const.wav"),
    "crowd": os.path.join(AMBIENT_BED_ROOT, "crowd.wav"),
    "jet": os.path.join(AMBIENT_BED_ROOT, "jet.wav"),
    "mall_interior": os.path.join(AMBIENT_BED_ROOT, "mall_interior.wav"),
    "ocean": os.path.join(AMBIENT_BED_ROOT, "ocean.wav"),
    "plane_cabin_interior": os.path.join(AMBIENT_BED_ROOT, "plane_cabin_interior.wav"),
    "plane_inflight_interior": os.path.join(AMBIENT_BED_ROOT, "plane_inflight_interior.wav"),
    "rain": os.path.join(AMBIENT_BED_ROOT, "rain.wav"),
    "water": os.path.join(AMBIENT_BED_ROOT, "water.wav"),
    "wind": os.path.join(AMBIENT_BED_ROOT, "wind.wav"),
}
_REAL_BED_CACHE = {}
_SHAPED_BED_CACHE = {}


PRESETS = {
    "Jet Cabin": {"size": 34, "surface": 44, "tail": 28, "focus": 74, "air": 38, "ambience": 72, "width": 12, "position": 50, "mix": 74},
    "Airport Gate": {"size": 58, "surface": 52, "tail": 42, "focus": 64, "air": 54, "ambience": 58, "width": 32, "position": 50, "mix": 74},
    "Mall Atrium": {"size": 78, "surface": 70, "tail": 72, "focus": 52, "air": 60, "ambience": 54, "width": 62, "position": 50, "mix": 82},
    "Food Court": {"size": 66, "surface": 56, "tail": 58, "focus": 48, "air": 52, "ambience": 66, "width": 54, "position": 50, "mix": 78},
    "Living Room": {"size": 34, "surface": 32, "tail": 24, "focus": 64, "air": 44, "ambience": 12, "width": 28, "position": 48, "mix": 56},
    "Bedroom": {"size": 24, "surface": 20, "tail": 14, "focus": 72, "air": 38, "ambience": 6, "width": 18, "position": 48, "mix": 42},
    "Kitchen": {"size": 28, "surface": 52, "tail": 26, "focus": 60, "air": 50, "ambience": 18, "width": 24, "position": 50, "mix": 60},
    "Bathroom Tile": {"size": 22, "surface": 86, "tail": 44, "focus": 54, "air": 74, "ambience": 8, "width": 26, "position": 50, "mix": 68},
    "Hallway": {"size": 58, "surface": 60, "tail": 54, "focus": 56, "air": 50, "ambience": 16, "width": 34, "position": 48, "mix": 74},
    "Stairwell": {"size": 72, "surface": 72, "tail": 70, "focus": 46, "air": 56, "ambience": 20, "width": 48, "position": 50, "mix": 84},
    "Classroom": {"size": 46, "surface": 42, "tail": 32, "focus": 60, "air": 46, "ambience": 14, "width": 30, "position": 50, "mix": 62},
    "Open Office": {"size": 64, "surface": 34, "tail": 28, "focus": 58, "air": 42, "ambience": 28, "width": 46, "position": 50, "mix": 58},
    "Basement": {"size": 52, "surface": 58, "tail": 48, "focus": 44, "air": 30, "ambience": 10, "width": 22, "position": 48, "mix": 72},
    "Studio Booth": {"size": 12, "surface": 10, "tail": 6, "focus": 82, "air": 36, "ambience": 0, "width": 10, "position": 50, "mix": 26},
}


PRESET_SCENES = {
    "Jet Cabin": {
        "seed": 101,
        "tail_ms": 118,
        "early_ms": [4, 9, 15, 22, 31, 43],
        "early_gains": [0.34, 0.27, 0.21, 0.15, 0.10, 0.06],
        "early_pan": [-0.22, 0.12, -0.10, 0.16, -0.06, 0.18],
        "late_ms": [57, 83, 111, 146],
        "late_gains": [0.14, 0.11, 0.08, 0.05],
        "late_pan": [-0.12, 0.18, -0.08, 0.20],
        "ambience": "jet",
        "ambience_gain": 0.22,
        "direct": 0.84,
        "width_base": 0.04,
        "hrtf_azimuth": 0.0,
        "hrtf_elevation": 5.0,
        "hrtf_blend": 0.72,
        "target_peak": 0.42,
    },
    "Airport Gate": {
        "seed": 149,
        "tail_ms": 168,
        "early_ms": [9, 19, 32, 47, 65, 84],
        "early_gains": [0.28, 0.23, 0.18, 0.13, 0.09, 0.06],
        "early_pan": [-0.16, 0.10, -0.10, 0.16, -0.05, 0.18],
        "late_ms": [71, 109, 151, 203],
        "late_gains": [0.18, 0.14, 0.10, 0.07],
        "late_pan": [-0.14, 0.16, -0.10, 0.22],
        "ambience": "terminal",
        "ambience_gain": 0.18,
        "direct": 0.76,
        "width_base": 0.12,
        "hrtf_azimuth": 0.0,
        "hrtf_elevation": 9.0,
        "hrtf_blend": 0.62,
        "target_peak": 0.38,
    },
    "Mall Atrium": {
        "seed": 211,
        "tail_ms": 250,
        "early_ms": [12, 24, 40, 59, 82, 108],
        "early_gains": [0.32, 0.27, 0.21, 0.16, 0.11, 0.08],
        "early_pan": [-0.18, 0.18, -0.14, 0.22, -0.06, 0.24],
        "late_ms": [93, 141, 201, 273],
        "late_gains": [0.20, 0.16, 0.13, 0.10],
        "late_pan": [-0.18, 0.22, -0.10, 0.26],
        "ambience": "mall",
        "ambience_gain": 0.13,
        "direct": 0.66,
        "width_base": 0.28,
        "hrtf_azimuth": -2.0,
        "hrtf_elevation": 12.0,
        "hrtf_blend": 0.56,
        "target_peak": 0.36,
    },
    "Food Court": {
        "seed": 257,
        "tail_ms": 220,
        "early_ms": [10, 20, 33, 49, 69, 94],
        "early_gains": [0.30, 0.24, 0.19, 0.14, 0.10, 0.07],
        "early_pan": [-0.16, 0.14, -0.12, 0.18, -0.06, 0.20],
        "late_ms": [81, 119, 169, 227],
        "late_gains": [0.19, 0.15, 0.11, 0.08],
        "late_pan": [-0.14, 0.18, -0.08, 0.22],
        "ambience": "crowd",
        "ambience_gain": 0.17,
        "direct": 0.62,
        "width_base": 0.24,
        "hrtf_azimuth": 0.0,
        "hrtf_elevation": 8.0,
        "hrtf_blend": 0.52,
        "target_peak": 0.36,
    },
    "Living Room": {
        "seed": 307,
        "tail_ms": 95,
        "early_ms": [6, 13, 21, 30, 44, 60],
        "early_gains": [0.24, 0.18, 0.13, 0.09, 0.06, 0.04],
        "early_pan": [-0.10, 0.08, -0.06, 0.10, -0.03, 0.12],
        "late_ms": [46, 67, 91, 121],
        "late_gains": [0.09, 0.07, 0.05, 0.04],
        "late_pan": [-0.08, 0.10, -0.04, 0.12],
        "ambience": "home",
        "ambience_gain": 0.05,
        "direct": 0.78,
        "width_base": 0.10,
        "hrtf_azimuth": -4.0,
        "hrtf_elevation": 3.0,
        "hrtf_blend": 0.52,
        "target_peak": 0.33,
    },
    "Bedroom": {
        "seed": 353,
        "tail_ms": 70,
        "early_ms": [5, 10, 17, 25, 35, 48],
        "early_gains": [0.18, 0.13, 0.09, 0.06, 0.04, 0.03],
        "early_pan": [-0.08, 0.06, -0.04, 0.07, -0.03, 0.08],
        "late_ms": [39, 57, 79, 101],
        "late_gains": [0.06, 0.05, 0.04, 0.03],
        "late_pan": [-0.06, 0.08, -0.03, 0.10],
        "ambience": "quiet",
        "ambience_gain": 0.02,
        "direct": 0.88,
        "width_base": 0.06,
        "hrtf_azimuth": -3.0,
        "hrtf_elevation": 2.0,
        "hrtf_blend": 0.46,
        "target_peak": 0.29,
    },
    "Kitchen": {
        "seed": 401,
        "tail_ms": 105,
        "early_ms": [5, 10, 16, 24, 34, 48],
        "early_gains": [0.26, 0.20, 0.15, 0.10, 0.07, 0.05],
        "early_pan": [-0.10, 0.08, -0.06, 0.10, -0.04, 0.12],
        "late_ms": [49, 71, 97, 129],
        "late_gains": [0.10, 0.08, 0.06, 0.04],
        "late_pan": [-0.08, 0.10, -0.04, 0.12],
        "ambience": "home",
        "ambience_gain": 0.06,
        "direct": 0.74,
        "width_base": 0.10,
        "hrtf_azimuth": -2.0,
        "hrtf_elevation": 4.0,
        "hrtf_blend": 0.54,
        "target_peak": 0.35,
    },
    "Bathroom Tile": {
        "seed": 449,
        "tail_ms": 120,
        "early_ms": [4, 8, 13, 19, 27, 39],
        "early_gains": [0.36, 0.30, 0.24, 0.17, 0.12, 0.09],
        "early_pan": [-0.08, 0.08, -0.05, 0.09, -0.03, 0.10],
        "late_ms": [37, 53, 71, 97],
        "late_gains": [0.14, 0.11, 0.08, 0.05],
        "late_pan": [-0.06, 0.08, -0.02, 0.10],
        "ambience": "tile",
        "ambience_gain": 0.03,
        "direct": 0.70,
        "width_base": 0.08,
        "hrtf_azimuth": 0.0,
        "hrtf_elevation": 6.0,
        "hrtf_blend": 0.48,
        "target_peak": 0.40,
    },
    "Hallway": {
        "seed": 503,
        "tail_ms": 190,
        "early_ms": [8, 17, 29, 43, 62, 88],
        "early_gains": [0.28, 0.22, 0.17, 0.12, 0.08, 0.06],
        "early_pan": [-0.14, 0.12, -0.10, 0.16, -0.05, 0.18],
        "late_ms": [77, 111, 157, 213],
        "late_gains": [0.18, 0.13, 0.09, 0.06],
        "late_pan": [-0.12, 0.14, -0.06, 0.18],
        "ambience": "hall",
        "ambience_gain": 0.08,
        "direct": 0.70,
        "width_base": 0.16,
        "hrtf_azimuth": -6.0,
        "hrtf_elevation": 5.0,
        "hrtf_blend": 0.56,
        "target_peak": 0.36,
    },
    "Stairwell": {
        "seed": 557,
        "tail_ms": 260,
        "early_ms": [11, 23, 39, 58, 84, 122],
        "early_gains": [0.31, 0.25, 0.20, 0.15, 0.11, 0.08],
        "early_pan": [-0.18, 0.18, -0.10, 0.20, -0.05, 0.22],
        "late_ms": [101, 149, 211, 287],
        "late_gains": [0.22, 0.18, 0.14, 0.10],
        "late_pan": [-0.18, 0.20, -0.08, 0.24],
        "ambience": "hall",
        "ambience_gain": 0.09,
        "direct": 0.60,
        "width_base": 0.24,
        "hrtf_azimuth": 0.0,
        "hrtf_elevation": 14.0,
        "hrtf_blend": 0.54,
        "target_peak": 0.38,
    },
    "Classroom": {
        "seed": 601,
        "tail_ms": 110,
        "early_ms": [7, 14, 24, 36, 52, 71],
        "early_gains": [0.24, 0.18, 0.13, 0.10, 0.06, 0.04],
        "early_pan": [-0.12, 0.08, -0.08, 0.12, -0.04, 0.14],
        "late_ms": [53, 77, 109, 143],
        "late_gains": [0.10, 0.08, 0.06, 0.04],
        "late_pan": [-0.08, 0.10, -0.04, 0.12],
        "ambience": "office",
        "ambience_gain": 0.06,
        "direct": 0.76,
        "width_base": 0.12,
        "hrtf_azimuth": -4.0,
        "hrtf_elevation": 8.0,
        "hrtf_blend": 0.56,
        "target_peak": 0.34,
    },
    "Open Office": {
        "seed": 653,
        "tail_ms": 120,
        "early_ms": [8, 17, 29, 45, 67, 93],
        "early_gains": [0.22, 0.17, 0.13, 0.10, 0.07, 0.05],
        "early_pan": [-0.12, 0.10, -0.08, 0.12, -0.04, 0.14],
        "late_ms": [59, 83, 117, 157],
        "late_gains": [0.10, 0.08, 0.06, 0.04],
        "late_pan": [-0.10, 0.12, -0.04, 0.16],
        "ambience": "office",
        "ambience_gain": 0.10,
        "direct": 0.78,
        "width_base": 0.18,
        "hrtf_azimuth": -2.0,
        "hrtf_elevation": 10.0,
        "hrtf_blend": 0.48,
        "target_peak": 0.32,
    },
    "Basement": {
        "seed": 701,
        "tail_ms": 160,
        "early_ms": [9, 20, 33, 49, 70, 97],
        "early_gains": [0.26, 0.20, 0.15, 0.11, 0.08, 0.05],
        "early_pan": [-0.10, 0.08, -0.06, 0.10, -0.03, 0.12],
        "late_ms": [69, 101, 141, 191],
        "late_gains": [0.15, 0.11, 0.08, 0.05],
        "late_pan": [-0.08, 0.10, -0.03, 0.12],
        "ambience": "quiet",
        "ambience_gain": 0.04,
        "direct": 0.64,
        "width_base": 0.08,
        "hrtf_azimuth": -5.0,
        "hrtf_elevation": 2.0,
        "hrtf_blend": 0.44,
        "target_peak": 0.35,
    },
    "Studio Booth": {
        "seed": 751,
        "tail_ms": 55,
        "early_ms": [3, 6, 10, 16, 23, 31],
        "early_gains": [0.10, 0.08, 0.06, 0.04, 0.02, 0.01],
        "early_pan": [-0.04, 0.04, -0.02, 0.04, -0.01, 0.05],
        "late_ms": [27, 39, 51, 67],
        "late_gains": [0.03, 0.02, 0.015, 0.01],
        "late_pan": [-0.03, 0.04, -0.01, 0.05],
        "ambience": "quiet",
        "ambience_gain": 0.0,
        "direct": 0.96,
        "width_base": 0.04,
        "hrtf_azimuth": 0.0,
        "hrtf_elevation": 1.0,
        "hrtf_blend": 0.32,
        "target_peak": 0.24,
    },
}


AMBIENCE_PROFILES = {
    "jet": {"low": 0.84, "high": 0.32, "hum": 0.05, "mod": 0.06, "stereo": 0.12, "hum_hz": 93.0},
    "terminal": {"low": 0.28, "high": 0.18, "hum": 0.05, "mod": 0.16, "stereo": 0.20, "hum_hz": 120.0},
    "mall": {"low": 0.32, "high": 0.22, "hum": 0.06, "mod": 0.22, "stereo": 0.24, "hum_hz": 90.0},
    "crowd": {"low": 0.24, "high": 0.28, "hum": 0.04, "mod": 0.28, "stereo": 0.28, "hum_hz": 110.0},
    "home": {"low": 0.12, "high": 0.05, "hum": 0.03, "mod": 0.04, "stereo": 0.08, "hum_hz": 60.0},
    "tile": {"low": 0.02, "high": 0.08, "hum": 0.01, "mod": 0.03, "stereo": 0.05, "hum_hz": 0.0},
    "hall": {"low": 0.10, "high": 0.10, "hum": 0.05, "mod": 0.06, "stereo": 0.14, "hum_hz": 72.0},
    "office": {"low": 0.18, "high": 0.08, "hum": 0.06, "mod": 0.10, "stereo": 0.16, "hum_hz": 120.0},
    "quiet": {"low": 0.01, "high": 0.01, "hum": 0.0, "mod": 0.01, "stereo": 0.02, "hum_hz": 0.0},
}


PRESET_REAL_BEDS = {
    "Jet Cabin": "jet_cabin",
    "Airport Gate": "airport_gate",
    "Mall Atrium": "mall_atrium",
    "Food Court": "food_court",
    "Living Room": "living_room",
    "Bedroom": "bedroom",
    "Kitchen": "kitchen",
    "Bathroom Tile": "bathroom_tile",
    "Hallway": "hallway",
    "Stairwell": "stairwell",
    "Classroom": "classroom",
    "Open Office": "open_office",
    "Basement": "basement",
    "Studio Booth": "studio_booth",
}


REAL_BED_MIXES = {
    "jet_cabin": (
        {"bed": "plane_cabin_interior", "gain": 0.92, "lowpass": 3200.0, "highpass": 85.0, "width": 0.08},
        {"bed": "plane_inflight_interior", "gain": 0.62, "lowpass": 2500.0, "highpass": 70.0, "width": 0.05},
        {"bed": "const", "gain": 0.18, "lowpass": 1250.0, "highpass": 40.0, "width": 0.01},
    ),
    "airport_gate": (
        {"bed": "airport_terminal_interior", "gain": 1.00, "lowpass": 5400.0, "highpass": 95.0, "width": 0.26},
        {"bed": "airport", "gain": 0.14, "lowpass": 3000.0, "highpass": 130.0, "width": 0.12},
        {"bed": "crowd", "gain": 0.10, "lowpass": 2400.0, "highpass": 180.0, "width": 0.18},
    ),
    "mall_atrium": (
        {"bed": "mall_interior", "gain": 0.96, "lowpass": 6100.0, "highpass": 120.0, "width": 0.34},
        {"bed": "crowd", "gain": 0.18, "lowpass": 3200.0, "highpass": 150.0, "width": 0.22},
    ),
    "food_court": (
        {"bed": "mall_interior", "gain": 0.84, "lowpass": 5200.0, "highpass": 130.0, "width": 0.26},
        {"bed": "crowd", "gain": 0.26, "lowpass": 3000.0, "highpass": 180.0, "width": 0.18},
        {"bed": "const", "gain": 0.06, "lowpass": 1000.0, "highpass": 50.0, "width": 0.02},
    ),
    "living_room": (("wind", 0.10), ("clock", 0.15)),
    "bedroom": (("wind", 0.07), ("clock", 0.08)),
    "kitchen": (("const", 0.18), ("clock", 0.07)),
    "bathroom_tile": (("water", 0.40), ("const", 0.09)),
    "hallway": (("wind", 0.18), ("const", 0.12)),
    "stairwell": (("wind", 0.22), ("water", 0.12)),
    "classroom": (("crowd", 0.14), ("const", 0.12)),
    "open_office": (("const", 0.22), ("crowd", 0.13)),
    "basement": (("const", 0.24), ("water", 0.08)),
    "studio_booth": (("clock", 0.05),),
}


DEFAULTS = {"preset": "Jet Cabin", **PRESETS["Jet Cabin"]}


def normalize_audio_frames(audio_data):
    array = np.asarray(audio_data, dtype=np.float32)
    if array.ndim == 1:
        return array.astype(np.float32, copy=False)
    if array.ndim == 2 and array.shape[1] in (1, 2):
        return array.astype(np.float32, copy=False)
    raise ValueError(f"Unsupported audio buffer shape: {array.shape}")


def ensure_stereo_frames(audio_data):
    array = normalize_audio_frames(audio_data)
    if array.ndim == 1:
        return np.column_stack((array, array)).astype(np.float32, copy=False)
    if array.shape[1] == 1:
        return np.repeat(array, 2, axis=1).astype(np.float32, copy=False)
    return array[:, :2].astype(np.float32, copy=False)


def resample_audio(data, frame_rate):
    array = np.asarray(data, dtype=np.float32)
    if frame_rate <= 0 or frame_rate == SAMPLE_RATE or array.shape[0] <= 1:
        return array.astype(np.float32, copy=False)

    target_length = max(1, int(round((array.shape[0] * SAMPLE_RATE) / float(frame_rate))))
    if target_length == array.shape[0]:
        return array.astype(np.float32, copy=False)

    source_positions = np.arange(array.shape[0], dtype=np.float32)
    target_positions = np.linspace(0.0, float(array.shape[0] - 1), target_length, dtype=np.float32)
    if array.ndim == 1:
        return np.interp(target_positions, source_positions, array).astype(np.float32)

    channels = [np.interp(target_positions, source_positions, array[:, channel]) for channel in range(array.shape[1])]
    return np.column_stack(channels).astype(np.float32, copy=False)


def normalize_bed_audio(stereo_data, target_rms=0.18):
    if stereo_data is None or stereo_data.size == 0:
        return None

    data = stereo_data.astype(np.float32, copy=True)
    peak_99 = float(np.percentile(np.abs(data), 99.5))
    if peak_99 > 0.96:
        data *= 0.96 / peak_99

    rms = float(np.sqrt(np.mean(data * data)))
    if rms > 1e-6:
        data *= target_rms / rms

    return np.clip(data, -1.0, 1.0).astype(np.float32, copy=False)


def load_real_bed(bed_name):
    global _REAL_BED_CACHE
    if bed_name in _REAL_BED_CACHE:
        return _REAL_BED_CACHE[bed_name]

    path = AMBIENT_BED_FILES.get(bed_name)
    if not path or not os.path.exists(path):
        _REAL_BED_CACHE[bed_name] = None
        return None

    data = None
    frame_rate = 0
    if sf is not None:
        try:
            data, frame_rate = sf.read(path, dtype="float32", always_2d=True)
        except Exception:
            data = None
            frame_rate = 0

    if data is None:
        try:
            with wave.open(path, "rb") as handle:
                channels = handle.getnchannels()
                width = handle.getsampwidth()
                frame_rate = handle.getframerate()
                frames = handle.readframes(handle.getnframes())
        except Exception as exc:
            print(f"Ambient Spaces bed load failed for {os.path.basename(path)}: {exc}")
            _REAL_BED_CACHE[bed_name] = None
            return None

        if width != 2:
            print(f"Ambient Spaces bed decode unsupported for {os.path.basename(path)}")
            _REAL_BED_CACHE[bed_name] = None
            return None

        data = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
        data = data.reshape(-1, channels)

    stereo = ensure_stereo_frames(data)
    stereo = resample_audio(stereo, frame_rate)
    stereo -= np.mean(stereo, axis=0, keepdims=True)
    stereo = normalize_bed_audio(stereo)
    _REAL_BED_CACHE[bed_name] = stereo
    return stereo


def read_loop_block(audio_data, cursor, length):
    if audio_data is None or audio_data.size == 0 or length <= 0:
        return np.zeros((max(0, length), 2), dtype=np.float32), 0

    total = int(audio_data.shape[0])
    if total <= 0:
        return np.zeros((length, 2), dtype=np.float32), 0

    start = int(cursor) % total
    end = start + int(length)
    if end <= total:
        return audio_data[start:end].astype(np.float32, copy=False), end % total

    first = audio_data[start:]
    remaining = end - total
    repeats = remaining // total
    tail = remaining % total
    chunks = [first]
    if repeats > 0:
        chunks.extend([audio_data] * repeats)
    if tail > 0:
        chunks.append(audio_data[:tail])
    return np.vstack(chunks).astype(np.float32, copy=False), tail


def _one_pole_lowpass(audio_data, cutoff_hz):
    if cutoff_hz is None or cutoff_hz <= 0.0:
        return audio_data.astype(np.float32, copy=False)

    alpha = float(1.0 - math.exp((-2.0 * math.pi * cutoff_hz) / SAMPLE_RATE))
    if alpha >= 0.9999:
        return audio_data.astype(np.float32, copy=False)

    b = np.array([alpha], dtype=np.float32)
    a = np.array([1.0, -(1.0 - alpha)], dtype=np.float32)
    output = np.empty_like(audio_data, dtype=np.float32)
    if audio_data.ndim == 1:
        return lfilter(b, a, audio_data).astype(np.float32, copy=False) if lfilter is not None else audio_data.astype(np.float32, copy=False)

    if lfilter is not None:
        for channel in range(audio_data.shape[1]):
            output[:, channel] = lfilter(b, a, audio_data[:, channel]).astype(np.float32, copy=False)
        return output

    for channel in range(audio_data.shape[1]):
        state = 0.0
        for index, sample in enumerate(audio_data[:, channel]):
            state += alpha * (float(sample) - state)
            output[index, channel] = state
    return output


def shape_real_bed(bed_name, lowpass_hz=None, highpass_hz=None, width=1.0):
    global _SHAPED_BED_CACHE
    cache_key = (bed_name, float(lowpass_hz or 0.0), float(highpass_hz or 0.0), float(width))
    if cache_key in _SHAPED_BED_CACHE:
        return _SHAPED_BED_CACHE[cache_key]

    stereo = load_real_bed(bed_name)
    if stereo is None or stereo.size == 0:
        _SHAPED_BED_CACHE[cache_key] = None
        return None

    shaped = stereo.astype(np.float32, copy=True)
    if lowpass_hz:
        shaped = _one_pole_lowpass(shaped, lowpass_hz)
    if highpass_hz:
        shaped = shaped - _one_pole_lowpass(shaped, highpass_hz)

    center = np.mean(shaped, axis=1, keepdims=True)
    shaped = center + ((shaped - center) * float(np.clip(width, 0.0, 1.25)))
    shaped -= np.mean(shaped, axis=0, keepdims=True)
    shaped = normalize_bed_audio(shaped, target_rms=0.18)
    _SHAPED_BED_CACHE[cache_key] = shaped
    return shaped


def constant_power_pan(pan):
    clipped = np.clip(pan, -1.0, 1.0)
    angle = (clipped + 1.0) * (math.pi * 0.25)
    return np.cos(angle), np.sin(angle)


def build_scene_ir(scene, size_ratio, surface_ratio, tail_ratio, width_ratio, position_pan):
    tail_ms = scene["tail_ms"] + (size_ratio * 70.0) + (tail_ratio * 120.0)
    length = int(max(384, min(MAX_IR_SAMPLES, round((tail_ms / 1000.0) * SAMPLE_RATE))))
    ir_left = np.zeros(length, dtype=np.float32)
    ir_right = np.zeros(length, dtype=np.float32)

    time_scale = 0.68 + (size_ratio * 0.95)
    reflect_gain = 0.46 + (surface_ratio * 0.92)
    width_shape = (width_ratio - 0.5) * 0.34

    for delay_ms, gain, base_pan in zip(scene["early_ms"], scene["early_gains"], scene["early_pan"]):
        index = min(length - 1, max(0, int((delay_ms * 0.001 * SAMPLE_RATE) * time_scale)))
        left_weight, right_weight = constant_power_pan(base_pan + (position_pan * 0.42) + width_shape)
        ir_left[index] += gain * reflect_gain * left_weight
        ir_right[index] += gain * reflect_gain * right_weight

    for delay_ms, gain, base_pan in zip(scene["late_ms"], scene["late_gains"], scene["late_pan"]):
        index = min(length - 1, max(0, int((delay_ms * 0.001 * SAMPLE_RATE) * (0.74 + (size_ratio * 1.12)))))
        left_weight, right_weight = constant_power_pan(base_pan + (position_pan * 0.28) + (width_shape * 1.2))
        late_gain = gain * (0.36 + (tail_ratio * 0.86))
        ir_left[index] += late_gain * left_weight
        ir_right[index] += late_gain * right_weight

    seed = int(scene["seed"] + round(size_ratio * 97) + round(surface_ratio * 131) + round(tail_ratio * 173) + round(width_ratio * 211))
    rng = np.random.default_rng(seed)
    diffuse_count = int(72 + (size_ratio * 96) + (tail_ratio * 164))
    diffuse_start = min(length - 1, max(32, int((scene["late_ms"][0] * 0.001 * SAMPLE_RATE) * 0.84)))
    if diffuse_start < length - 1 and diffuse_count > 0:
        positions = rng.integers(diffuse_start, length, size=diffuse_count)
        amplitudes = rng.normal(0.0, 1.0, size=diffuse_count).astype(np.float32)
        pans = np.clip(
            rng.uniform(-0.75, 0.75, size=diffuse_count).astype(np.float32) * (0.36 + (width_ratio * 0.92))
            + (position_pan * 0.20),
            -1.0,
            1.0,
        )
        decay = np.exp(-(positions - diffuse_start) / max(1.0, length * (0.14 + (tail_ratio * 0.62)))).astype(np.float32)
        gains = amplitudes * decay * (0.012 + (surface_ratio * 0.022) + (tail_ratio * 0.032))
        left_weight, right_weight = constant_power_pan(pans)
        np.add.at(ir_left, positions, gains * left_weight)
        np.add.at(ir_right, positions, gains * right_weight)

    fade_len = min(max(64, length // 6), 768)
    if fade_len > 1:
        fade = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
        ir_left[-fade_len:] *= fade
        ir_right[-fade_len:] *= fade

    peak = max(float(np.max(np.abs(ir_left))), float(np.max(np.abs(ir_right))))
    if peak > 1e-6:
        scale = float(scene["target_peak"]) / peak
        ir_left *= scale
        ir_right *= scale

    return ir_left.astype(np.float32, copy=False), ir_right.astype(np.float32, copy=False)


class Plugin:
    def __init__(self):
        self.name = "Ambient Spaces"
        self.enabled = False
        self.supports_stereo = True
        self.process_stage = 105
        self.file_name = "ambient_spaces.py"
        self.settings_path = os.path.splitext(__file__)[0] + ".json"

        self.steam_audio = SteamAudioBinaural(SAMPLE_RATE)
        self.rng = np.random.default_rng()
        self._scene_lock = threading.RLock()

        self.active_left_ir = np.array([1.0], dtype=np.float32)
        self.active_right_ir = np.array([1.0], dtype=np.float32)
        self.left_ir_state = np.zeros(0, dtype=np.float32)
        self.right_ir_state = np.zeros(0, dtype=np.float32)

        self.amb_low_state = np.zeros(2, dtype=np.float32)
        self.amb_high_state = np.zeros(2, dtype=np.float32)
        self.amb_mod_state = np.zeros(2, dtype=np.float32)
        self.amb_hum_phase = np.zeros(2, dtype=np.float32)
        self.amb_profile = AMBIENCE_PROFILES["quiet"]
        self.ambience_gain = 0.0
        self.amb_low_alpha = 0.05
        self.amb_high_alpha = 0.22
        self.amb_mod_alpha = 0.04
        self.amb_hum_rates = np.zeros(2, dtype=np.float32)
        self.bed_layers = []

        self.room_gain = 0.3
        self.width_gain = 0.12
        self.direct_gain = 0.8
        self.direct_spatial = 0.5
        self.hrtf_azimuth = 0.0
        self.hrtf_elevation = 4.0
        self.soft_drive = 0.12
        self.mix_ratio = 0.5

        self.preset = DEFAULTS["preset"]
        self.size = DEFAULTS["size"]
        self.surface = DEFAULTS["surface"]
        self.tail = DEFAULTS["tail"]
        self.focus = DEFAULTS["focus"]
        self.air = DEFAULTS["air"]
        self.ambience = DEFAULTS["ambience"]
        self.width = DEFAULTS["width"]
        self.position = DEFAULTS["position"]
        self.mix = DEFAULTS["mix"]
        self.load_settings()

    def apply_preset(self, name):
        values = PRESETS[name]
        self.preset = name
        self.size = values["size"]
        self.surface = values["surface"]
        self.tail = values["tail"]
        self.focus = values["focus"]
        self.air = values["air"]
        self.ambience = values["ambience"]
        self.width = values["width"]
        self.position = values["position"]
        self.mix = values["mix"]

    def set_live_values(self, preset_name, values):
        preset_changed = preset_name in PRESETS and preset_name != self.preset
        if preset_name in PRESETS:
            self.preset = preset_name
        self.size = int(values["size"])
        self.surface = int(values["surface"])
        self.tail = int(values["tail"])
        self.focus = int(values["focus"])
        self.air = int(values["air"])
        self.ambience = int(values["ambience"])
        self.width = int(values["width"])
        self.position = int(values["position"])
        self.mix = int(values["mix"])
        self._refresh_scene(reset_state=preset_changed)

    def load_settings(self):
        values = load_settings(self.settings_path, DEFAULTS)
        preset = values.get("preset", DEFAULTS["preset"])
        if preset not in PRESETS:
            preset = DEFAULTS["preset"]
        self.apply_preset(preset)
        self.size = int(values.get("size", self.size))
        self.surface = int(values.get("surface", self.surface))
        self.tail = int(values.get("tail", self.tail))
        self.focus = int(values.get("focus", self.focus))
        self.air = int(values.get("air", self.air))
        self.ambience = int(values.get("ambience", self.ambience))
        self.width = int(values.get("width", self.width))
        self.position = int(values.get("position", self.position))
        self.mix = int(values.get("mix", self.mix))
        self._refresh_scene(reset_state=True)

    def save_settings(self):
        save_settings(
            self.settings_path,
            {
                "preset": self.preset,
                "size": int(self.size),
                "surface": int(self.surface),
                "tail": int(self.tail),
                "focus": int(self.focus),
                "air": int(self.air),
                "ambience": int(self.ambience),
                "width": int(self.width),
                "position": int(self.position),
                "mix": int(self.mix),
            },
        )

    def _refresh_scene(self, reset_state):
        with self._scene_lock:
            scene = PRESET_SCENES.get(self.preset, PRESET_SCENES[DEFAULTS["preset"]])
            size_ratio = np.clip(self.size / 100.0, 0.0, 1.0)
            surface_ratio = np.clip(self.surface / 100.0, 0.0, 1.0)
            tail_ratio = np.clip(self.tail / 100.0, 0.0, 1.0)
            focus_ratio = np.clip(self.focus / 100.0, 0.0, 1.0)
            air_ratio = np.clip(self.air / 100.0, 0.0, 1.0)
            ambience_ratio = np.clip(self.ambience / 100.0, 0.0, 1.0)
            width_ratio = np.clip(self.width / 100.0, 0.0, 1.0)
            position_pan = np.clip((self.position - 50.0) / 50.0, -1.0, 1.0)

            self.active_left_ir, self.active_right_ir = build_scene_ir(
                scene,
                size_ratio,
                surface_ratio,
                tail_ratio,
                width_ratio,
                position_pan,
            )
            self.left_ir_state = np.zeros(max(0, self.active_left_ir.shape[0] - 1), dtype=np.float32)
            self.right_ir_state = np.zeros(max(0, self.active_right_ir.shape[0] - 1), dtype=np.float32)

            self.room_gain = float(0.26 + (surface_ratio * 0.34) + (tail_ratio * 0.22))
            self.width_gain = float(scene["width_base"] + (width_ratio * 0.26))
            self.direct_gain = float(scene["direct"] * (0.50 + (focus_ratio * 0.64)))
            self.direct_spatial = float(np.clip(scene["hrtf_blend"] * (0.24 + (focus_ratio * 0.76)), 0.0, 1.0))
            self.hrtf_azimuth = float(scene["hrtf_azimuth"] + (position_pan * 34.0))
            self.hrtf_elevation = float(scene["hrtf_elevation"])
            self.soft_drive = float(0.08 + (surface_ratio * 0.10) + (tail_ratio * 0.08))
            self.mix_ratio = float(np.clip(self.mix / 100.0, 0.0, 1.0))

            self.amb_profile = AMBIENCE_PROFILES[scene["ambience"]]
            self.ambience_gain = float(scene["ambience_gain"] * (0.10 + (ambience_ratio * 1.24)))
            self.amb_low_alpha = float(0.025 + ((1.0 - air_ratio) * 0.045))
            self.amb_high_alpha = float(0.16 + (air_ratio * 0.24))
            self.amb_mod_alpha = float(0.020 + (self.amb_profile["mod"] * 0.06))
            hum_rate = float(self.amb_profile["hum_hz"]) * (2.0 * math.pi / SAMPLE_RATE)
            self.amb_hum_rates[0] = hum_rate
            self.amb_hum_rates[1] = hum_rate * 1.013 if hum_rate > 0.0 else 0.0

            previous_cursors = {}
            if not reset_state:
                previous_cursors = {layer["name"]: layer["cursor"] for layer in self.bed_layers}

            self.bed_layers = []
            bed_mix = REAL_BED_MIXES.get(PRESET_REAL_BEDS.get(self.preset, ""), ())
            for layer_index, layer_spec in enumerate(bed_mix):
                if isinstance(layer_spec, dict):
                    bed_name = layer_spec.get("bed", "")
                    layer_gain = float(layer_spec.get("gain", 1.0))
                    lowpass_hz = layer_spec.get("lowpass")
                    highpass_hz = layer_spec.get("highpass")
                    stereo_width = layer_spec.get("width", 1.0)
                else:
                    bed_name, layer_gain = layer_spec
                    lowpass_hz = None
                    highpass_hz = None
                    stereo_width = 1.0

                audio = shape_real_bed(bed_name, lowpass_hz=lowpass_hz, highpass_hz=highpass_hz, width=stereo_width)
                if audio is None or audio.size == 0:
                    continue
                if bed_name in previous_cursors:
                    cursor = int(previous_cursors[bed_name] % audio.shape[0])
                else:
                    cursor = int((scene["seed"] * (layer_index + 1) * 977) % audio.shape[0])
                self.bed_layers.append({"name": bed_name, "audio": audio, "gain": float(layer_gain), "cursor": cursor})

            if reset_state:
                self.amb_low_state.fill(0.0)
                self.amb_high_state.fill(0.0)
                self.amb_mod_state.fill(0.0)
                self.amb_hum_phase.fill(0.0)

    def _convolve_room(self, source_mono):
        expected_left = max(0, self.active_left_ir.shape[0] - 1)
        expected_right = max(0, self.active_right_ir.shape[0] - 1)
        if self.left_ir_state.shape[0] != expected_left:
            self.left_ir_state = np.zeros(expected_left, dtype=np.float32)
        if self.right_ir_state.shape[0] != expected_right:
            self.right_ir_state = np.zeros(expected_right, dtype=np.float32)
        if lfilter is not None:
            left, self.left_ir_state = lfilter(self.active_left_ir, np.array([1.0], dtype=np.float32), source_mono, zi=self.left_ir_state)
            right, self.right_ir_state = lfilter(self.active_right_ir, np.array([1.0], dtype=np.float32), source_mono, zi=self.right_ir_state)
            return np.column_stack((left, right)).astype(np.float32, copy=False)

        left = np.convolve(source_mono, self.active_left_ir, mode="full")[: source_mono.shape[0]]
        right = np.convolve(source_mono, self.active_right_ir, mode="full")[: source_mono.shape[0]]
        return np.column_stack((left, right)).astype(np.float32, copy=False)

    def _real_ambience_block(self, length):
        if self.ambience_gain <= 0.0 or not self.bed_layers:
            return None

        output = np.zeros((length, 2), dtype=np.float32)
        for layer in self.bed_layers:
            block, next_cursor = read_loop_block(layer["audio"], layer["cursor"], length)
            layer["cursor"] = next_cursor
            output += block * layer["gain"]

        center = np.mean(output, axis=1, keepdims=True)
        side = output - center
        stereo = center + (side * (0.35 + self.amb_profile["stereo"] + (self.width_gain * 0.28)))
        return (stereo * self.ambience_gain).astype(np.float32, copy=False)

    def _synthetic_ambience_block(self, length):
        if self.ambience_gain <= 0.0:
            return np.zeros((length, 2), dtype=np.float32)

        white = self.rng.normal(0.0, 1.0, size=(length, 2)).astype(np.float32)
        abs_white = np.abs(white)
        output = np.empty((length, 2), dtype=np.float32)

        if lfilter is not None:
            low_b = np.array([self.amb_low_alpha], dtype=np.float32)
            low_a = np.array([1.0, -(1.0 - self.amb_low_alpha)], dtype=np.float32)
            high_b = np.array([self.amb_high_alpha], dtype=np.float32)
            high_a = np.array([1.0, -(1.0 - self.amb_high_alpha)], dtype=np.float32)
            mod_b = np.array([self.amb_mod_alpha], dtype=np.float32)
            mod_a = np.array([1.0, -(1.0 - self.amb_mod_alpha)], dtype=np.float32)

            for channel in range(2):
                low, low_state = lfilter(low_b, low_a, white[:, channel], zi=np.array([self.amb_low_state[channel]], dtype=np.float32))
                high, high_state = lfilter(high_b, high_a, white[:, channel], zi=np.array([self.amb_high_state[channel]], dtype=np.float32))
                mod, mod_state = lfilter(mod_b, mod_a, abs_white[:, channel], zi=np.array([self.amb_mod_state[channel]], dtype=np.float32))
                self.amb_low_state[channel] = low_state[0]
                self.amb_high_state[channel] = high_state[0]
                self.amb_mod_state[channel] = mod_state[0]
                airy = high - low
                hum = 0.0
                if self.amb_profile["hum"] > 0.0:
                    phase = self.amb_hum_phase[channel] + (self.amb_hum_rates[channel] * np.arange(length, dtype=np.float32))
                    hum = np.sin(phase).astype(np.float32, copy=False)
                    self.amb_hum_phase[channel] = float((phase[-1] + self.amb_hum_rates[channel]) % (2.0 * math.pi))
                motion = 0.65 + (mod * 0.55)
                output[:, channel] = (
                    (low * self.amb_profile["low"])
                    + (airy * self.amb_profile["high"] * motion)
                    + (hum * self.amb_profile["hum"])
                ).astype(np.float32, copy=False)
        else:
            for channel in range(2):
                low_state = float(self.amb_low_state[channel])
                high_state = float(self.amb_high_state[channel])
                mod_state = float(self.amb_mod_state[channel])
                hum_phase = float(self.amb_hum_phase[channel])
                for index in range(length):
                    sample = float(white[index, channel])
                    low_state += self.amb_low_alpha * (sample - low_state)
                    high_state += self.amb_high_alpha * (sample - high_state)
                    mod_state += self.amb_mod_alpha * (abs(sample) - mod_state)
                    airy = high_state - low_state
                    hum = math.sin(hum_phase) if self.amb_profile["hum"] > 0.0 else 0.0
                    hum_phase = (hum_phase + self.amb_hum_rates[channel]) % (2.0 * math.pi)
                    motion = 0.65 + (mod_state * 0.55)
                    output[index, channel] = (
                        (low_state * self.amb_profile["low"])
                        + (airy * self.amb_profile["high"] * motion)
                        + (hum * self.amb_profile["hum"])
                    )
                self.amb_low_state[channel] = low_state
                self.amb_high_state[channel] = high_state
                self.amb_mod_state[channel] = mod_state
                self.amb_hum_phase[channel] = hum_phase

        center = np.mean(output, axis=1, keepdims=True)
        side = np.column_stack((-1.0 * (output[:, 1] - output[:, 0]), output[:, 1] - output[:, 0])).astype(np.float32, copy=False)
        stereo = center + (side * (0.22 + self.amb_profile["stereo"]))
        return stereo * self.ambience_gain

    def _ambience_block(self, length):
        real_block = self._real_ambience_block(length)
        if real_block is not None:
            return real_block
        return self._synthetic_ambience_block(length)

    def process(self, data):
        source = normalize_audio_frames(data)
        if source.size == 0:
            return source

        with self._scene_lock:
            dry_stereo = ensure_stereo_frames(source)
            source_mono = source if source.ndim == 1 else np.mean(dry_stereo, axis=1, dtype=np.float32)
            room = self._convolve_room(source_mono) * self.room_gain
            direct = self.steam_audio.process(source_mono * self.direct_gain, self.hrtf_azimuth, self.hrtf_elevation, self.direct_spatial)
            if direct.shape[0] == 0:
                direct = pan_mono(source_mono * self.direct_gain, self.hrtf_azimuth / 60.0)
            ambience = self._ambience_block(source_mono.shape[0])

            room_center = np.mean(room, axis=1, keepdims=True)
            room_side = np.column_stack((room[:, 0] - room[:, 1], room[:, 1] - room[:, 0])).astype(np.float32, copy=False)
            room = room_center + (room_side * (0.42 + self.width_gain))

            wet = room + direct + ambience
            wet = wet / (1.0 + (np.abs(wet) * self.soft_drive))
            mixed = (dry_stereo * (1.0 - self.mix_ratio)) + (wet * self.mix_ratio)
            return np.clip(mixed, -0.98, 0.98).astype(np.float32, copy=False)

    def open_settings(self, parent):
        dialog = AmbientSpacesDialog(parent, self)
        dialog.ShowModal()
        self.save_settings()
        dialog.Destroy()


class AmbientSpacesDialog(PluginControlDialog):
    def __init__(self, parent, plugin):
        self.plugin = plugin
        super().__init__(
            parent,
            title="Ambient Spaces Settings",
            preset_names=PRESETS.keys(),
            selected_preset=plugin.preset,
            slider_defs=[
                {"key": "size", "label": "Size", "value": plugin.size},
                {"key": "surface", "label": "Surface", "value": plugin.surface},
                {"key": "tail", "label": "Tail", "value": plugin.tail},
                {"key": "focus", "label": "Focus", "value": plugin.focus},
                {"key": "air", "label": "Air", "value": plugin.air},
                {"key": "ambience", "label": "Ambience", "value": plugin.ambience},
                {"key": "width", "label": "Width", "value": plugin.width},
                {"key": "position", "label": "Position", "value": plugin.position},
                {"key": "mix", "label": "Mix", "value": plugin.mix},
            ],
            hint="Environment sim with live preview. Presets apply immediately, so you do not need to press OK for the new preset to be heard. Ambience now uses real local environment beds when available. Size changes distance, Surface changes reflections, Tail changes decay, Focus pushes the source forward, and Ambience adds the place noise layer.",
            size=(500, 720),
        )
        if self.preset_choice is not None:
            self.preset_choice.Bind(wx.EVT_CHOICE, self.on_preset_change)
        for control in self.controls.values():
            control["slider"].Bind(wx.EVT_SLIDER, self.on_live_change)

    def apply_live(self):
        self.plugin.set_live_values(self.get_selected_preset() or self.plugin.preset, self.get_slider_values())

    def on_preset_change(self, event):
        selected = self.get_selected_preset()
        if selected in PRESETS:
            self.set_slider_values(PRESETS[selected])
        self.apply_live()

    def on_live_change(self, event):
        event.Skip()
        self.apply_live()
