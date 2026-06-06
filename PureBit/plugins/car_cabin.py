import ctypes
import math
import os
import struct
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

try:
    from pydub import AudioSegment
except Exception:
    AudioSegment = None

try:
    import audioread
except Exception:
    audioread = None

from _plugin_utils import PluginControlDialog, load_settings, save_settings
from _steam_audio_support import STEAMAUDIO_VERSION, resolve_steam_audio_paths


SAMPLE_RATE = 48000
SOUND_SPEED_MPS = 343.0
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
NOISE_LOOP_PATH = os.path.join(ASSETS_DIR, "car_noise_loop.wav")
NOISE_BEDS_DIR = os.path.join(ASSETS_DIR, "car_noise_beds")
IR_ROOT = os.path.join(ASSETS_DIR, "v_class_impulse_responses", "impulse_responses")
STEAMAUDIO_INFO = resolve_steam_audio_paths()
STEAMAUDIO_ROOT = STEAMAUDIO_INFO["root"]
STEAMAUDIO_DLL_PATH = STEAMAUDIO_INFO["dll"]

NOISE_BED_FILES = {
    "legacy": NOISE_LOOP_PATH,
    "midsize_80": os.path.join(NOISE_BEDS_DIR, "midsize_80.wav"),
    "midsize_100": os.path.join(NOISE_BEDS_DIR, "midsize_100.wav"),
    "midsize_130": os.path.join(NOISE_BEDS_DIR, "midsize_130.wav"),
    "fullsize_100": os.path.join(NOISE_BEDS_DIR, "fullsize_100.wav"),
    "fullsize_130": os.path.join(NOISE_BEDS_DIR, "fullsize_130.wav"),
    "crossroad": os.path.join(NOISE_BEDS_DIR, "crossroad.wav"),
}
AMBIENT_BED_ROOT = os.path.join(ASSETS_DIR, "ambient_space_beds")
AMBIENT_BED_FILES = {
    "airport": os.path.join(AMBIENT_BED_ROOT, "airport.wav"),
    "const": os.path.join(AMBIENT_BED_ROOT, "const.wav"),
    "crowd": os.path.join(AMBIENT_BED_ROOT, "crowd.wav"),
    "rain": os.path.join(AMBIENT_BED_ROOT, "rain.wav"),
    "water": os.path.join(AMBIENT_BED_ROOT, "water.wav"),
    "wind": os.path.join(AMBIENT_BED_ROOT, "wind.wav"),
}

SOURCE_IDS = {
    "driver": 12,
    "passenger": 13,
    "second_left": 14,
    "second_right": 15,
    "rear_left": 16,
    "rear_right": 17,
}

LISTENER_POSITIONS = {
    "driver": np.array([-0.34, 0.72, 0.14], dtype=np.float32),
    "passenger": np.array([0.34, 0.72, 0.14], dtype=np.float32),
    "second_left": np.array([-0.30, 0.72, -0.46], dtype=np.float32),
    "second_right": np.array([0.30, 0.72, -0.46], dtype=np.float32),
    "rear_left": np.array([-0.20, 0.72, -0.84], dtype=np.float32),
    "rear_right": np.array([0.20, 0.72, -0.84], dtype=np.float32),
    "back_center": np.array([0.00, 0.72, -0.84], dtype=np.float32),
}

CAR_MUSIC_SPEAKERS = (
    {"name": "dash_left", "position": np.array([-0.48, 0.86, 0.92], dtype=np.float32), "channel": "left", "weight": 0.32, "crossfeed": 0.04, "band": "presence"},
    {"name": "dash_right", "position": np.array([0.48, 0.86, 0.92], dtype=np.float32), "channel": "right", "weight": 0.32, "crossfeed": 0.04, "band": "presence"},
    {"name": "lower_left", "position": np.array([-0.62, 0.18, 0.68], dtype=np.float32), "channel": "left", "weight": 0.52, "crossfeed": 0.02, "band": "body"},
    {"name": "lower_right", "position": np.array([0.62, 0.18, 0.68], dtype=np.float32), "channel": "right", "weight": 0.52, "crossfeed": 0.02, "band": "body"},
)

MIC_IDS = {
    "bpillar": 0,
    "roof_front": 1,
    "array_l": 2,
    "array_ml": 3,
    "array_mr": 4,
    "array_r": 5,
    "roof_pass": 6,
    "roof_mid_left": 7,
    "mid_l": 8,
    "mid_ml": 9,
    "mid_mr": 10,
    "mid_r": 11,
    "roof_mid_right": 12,
    "roof_rear_left": 13,
    "rear_l": 14,
    "rear_ml": 15,
    "rear_mr": 16,
    "rear_r": 17,
    "roof_rear_right": 18,
    "driver_ear_left": 19,
    "driver_ear_right": 20,
}

IR_SOURCES = {
    f"{source}_{mic}": (source_id, mic_id)
    for source, source_id in SOURCE_IDS.items()
    for mic, mic_id in MIC_IDS.items()
}

PRESETS = {
    "Driver Seat": {"space": 38, "speaker": 50, "road": 18, "tight": 68, "mix": 86, "width": 28, "presence": 60, "seat": 20, "window": 6, "hrtf": 62, "balance": 50, "engine": 24, "rain": 0, "air": 18, "traffic": 10, "motion": 16},
    "Handsfree": {"space": 46, "speaker": 52, "road": 24, "tight": 62, "mix": 88, "width": 34, "presence": 52, "seat": 24, "window": 10, "hrtf": 74, "balance": 50, "engine": 28, "rain": 0, "air": 28, "traffic": 16, "motion": 22},
    "Roof Console": {"space": 40, "speaker": 56, "road": 18, "tight": 70, "mix": 88, "width": 24, "presence": 60, "seat": 30, "window": 6, "hrtf": 84, "balance": 50, "engine": 22, "rain": 0, "air": 20, "traffic": 10, "motion": 14},
    "Phone On Dash": {"space": 34, "speaker": 64, "road": 20, "tight": 82, "mix": 90, "width": 16, "presence": 76, "seat": 28, "window": 4, "hrtf": 82, "balance": 50, "engine": 16, "rain": 0, "air": 14, "traffic": 8, "motion": 10},
    "Mirror Mic": {"space": 42, "speaker": 60, "road": 22, "tight": 74, "mix": 90, "width": 22, "presence": 70, "seat": 24, "window": 6, "hrtf": 78, "balance": 50, "engine": 18, "rain": 0, "air": 16, "traffic": 10, "motion": 14},
    "Passenger Seat": {"space": 52, "speaker": 50, "road": 24, "tight": 56, "mix": 88, "width": 38, "presence": 50, "seat": 80, "window": 8, "hrtf": 60, "balance": 50, "engine": 24, "rain": 0, "air": 24, "traffic": 18, "motion": 20},
    "Passenger Window": {"space": 56, "speaker": 50, "road": 30, "tight": 52, "mix": 92, "width": 38, "presence": 46, "seat": 84, "window": 30, "hrtf": 64, "balance": 50, "engine": 28, "rain": 0, "air": 30, "traffic": 36, "motion": 24},
    "Second Row Left": {"space": 60, "speaker": 46, "road": 26, "tight": 52, "mix": 92, "width": 36, "presence": 42, "seat": 22, "window": 8, "hrtf": 56, "balance": 50, "engine": 26, "rain": 0, "air": 20, "traffic": 24, "motion": 22},
    "Second Row Right": {"space": 60, "speaker": 46, "road": 26, "tight": 52, "mix": 92, "width": 36, "presence": 42, "seat": 78, "window": 8, "hrtf": 56, "balance": 50, "engine": 26, "rain": 0, "air": 20, "traffic": 24, "motion": 22},
    "Back Seat": {"space": 68, "speaker": 44, "road": 28, "tight": 48, "mix": 94, "width": 34, "presence": 34, "seat": 50, "window": 10, "hrtf": 48, "balance": 50, "engine": 30, "rain": 0, "air": 18, "traffic": 20, "motion": 28},
    "Taxi Idle": {"space": 44, "speaker": 54, "road": 12, "tight": 64, "mix": 88, "width": 24, "presence": 58, "seat": 26, "window": 4, "hrtf": 72, "balance": 50, "engine": 56, "rain": 0, "air": 40, "traffic": 18, "motion": 10},
    "Highway": {"space": 54, "speaker": 48, "road": 52, "tight": 58, "mix": 92, "width": 32, "presence": 44, "seat": 24, "window": 18, "hrtf": 66, "balance": 50, "engine": 44, "rain": 0, "air": 28, "traffic": 20, "motion": 36},
    "Rainy Commute": {"space": 54, "speaker": 48, "road": 34, "tight": 58, "mix": 92, "width": 30, "presence": 46, "seat": 24, "window": 22, "hrtf": 68, "balance": 50, "engine": 34, "rain": 62, "air": 28, "traffic": 28, "motion": 26},
    "Window Cracked": {"space": 50, "speaker": 50, "road": 40, "tight": 60, "mix": 92, "width": 30, "presence": 48, "seat": 24, "window": 54, "hrtf": 70, "balance": 50, "engine": 34, "rain": 0, "air": 32, "traffic": 34, "motion": 28},
    "Tunnel Cruise": {"space": 72, "speaker": 46, "road": 46, "tight": 44, "mix": 94, "width": 40, "presence": 38, "seat": 24, "window": 10, "hrtf": 62, "balance": 50, "engine": 40, "rain": 0, "air": 24, "traffic": 16, "motion": 42},
    "Drive-Thru": {"space": 30, "speaker": 70, "road": 10, "tight": 84, "mix": 88, "width": 14, "presence": 78, "seat": 28, "window": 4, "hrtf": 84, "balance": 50, "engine": 12, "rain": 0, "air": 18, "traffic": 14, "motion": 8},
    "Parking Garage": {"space": 58, "speaker": 46, "road": 8, "tight": 44, "mix": 92, "width": 32, "presence": 36, "seat": 32, "window": 4, "hrtf": 52, "balance": 50, "engine": 16, "rain": 0, "air": 14, "traffic": 10, "motion": 14},
    "SUV Highway": {"space": 56, "speaker": 48, "road": 58, "tight": 56, "mix": 94, "width": 34, "presence": 42, "seat": 24, "window": 16, "hrtf": 64, "balance": 50, "engine": 50, "rain": 0, "air": 34, "traffic": 22, "motion": 40},
    "City Night": {"space": 52, "speaker": 50, "road": 32, "tight": 56, "mix": 92, "width": 34, "presence": 46, "seat": 24, "window": 26, "hrtf": 72, "balance": 50, "engine": 28, "rain": 0, "air": 24, "traffic": 54, "motion": 24},
    "Traffic Jam": {"space": 48, "speaker": 52, "road": 18, "tight": 60, "mix": 90, "width": 28, "presence": 50, "seat": 24, "window": 14, "hrtf": 74, "balance": 50, "engine": 20, "rain": 0, "air": 44, "traffic": 62, "motion": 10},
    "Ride Share Rear Right": {"space": 64, "speaker": 46, "road": 24, "tight": 50, "mix": 94, "width": 36, "presence": 40, "seat": 82, "window": 10, "hrtf": 58, "balance": 50, "engine": 24, "rain": 0, "air": 24, "traffic": 32, "motion": 24},
    "Luxury SUV Night": {"space": 58, "speaker": 54, "road": 48, "tight": 60, "mix": 94, "width": 36, "presence": 46, "seat": 26, "window": 12, "hrtf": 72, "balance": 50, "engine": 44, "rain": 0, "air": 34, "traffic": 20, "motion": 42},
    "Storm Run": {"space": 58, "speaker": 46, "road": 36, "tight": 56, "mix": 94, "width": 32, "presence": 42, "seat": 24, "window": 28, "hrtf": 70, "balance": 50, "engine": 32, "rain": 82, "air": 28, "traffic": 30, "motion": 30},
}

PRESET_SCENES = {
    "Driver Seat": {"source": "driver", "mode": "driver", "noise": "midsize_100", "tail_ms": 56, "target_peak": 0.52, "direct_mix": 0.008, "crossfeed": 0.020, "cabin_bias": 0.28, "noise_gain": 0.12, "width_base": 0.001, "box_cut": 0.24, "soft_drive": 0.028, "left_noise_bias": 1.03, "right_noise_bias": 0.99, "hrtf_azimuth": -18.0, "hrtf_elevation": 4.0, "hrtf_blend": 0.68, "engine_bias": 0.92, "engine_side": -0.14},
    "Handsfree": {"source": "driver", "mode": "handsfree", "noise": "midsize_100", "tail_ms": 60, "target_peak": 0.50, "direct_mix": 0.010, "crossfeed": 0.024, "cabin_bias": 0.34, "noise_gain": 0.14, "width_base": 0.002, "box_cut": 0.22, "soft_drive": 0.030, "left_noise_bias": 1.02, "right_noise_bias": 1.00, "hrtf_azimuth": -8.0, "hrtf_elevation": 8.0, "hrtf_blend": 0.74, "engine_bias": 1.00, "engine_side": -0.10},
    "Roof Console": {"source": "driver", "mode": "roof_console", "noise": "midsize_100", "tail_ms": 54, "target_peak": 0.50, "direct_mix": 0.010, "crossfeed": 0.022, "cabin_bias": 0.30, "noise_gain": 0.12, "width_base": 0.001, "box_cut": 0.23, "soft_drive": 0.026, "left_noise_bias": 1.01, "right_noise_bias": 1.00, "hrtf_azimuth": -2.0, "hrtf_elevation": 20.0, "hrtf_blend": 0.84, "engine_bias": 0.78, "engine_side": -0.08},
    "Phone On Dash": {"source": "driver", "mode": "dash", "noise": "midsize_100", "tail_ms": 46, "target_peak": 0.48, "direct_mix": 0.012, "crossfeed": 0.012, "cabin_bias": 0.22, "noise_gain": 0.12, "width_base": 0.000, "box_cut": 0.30, "soft_drive": 0.020, "left_noise_bias": 1.01, "right_noise_bias": 0.99, "hrtf_azimuth": -4.0, "hrtf_elevation": 2.0, "hrtf_blend": 0.82, "engine_bias": 0.68, "engine_side": -0.10},
    "Mirror Mic": {"source": "driver", "mode": "mirror", "noise": "midsize_100", "tail_ms": 50, "target_peak": 0.50, "direct_mix": 0.010, "crossfeed": 0.018, "cabin_bias": 0.26, "noise_gain": 0.13, "width_base": 0.001, "box_cut": 0.26, "soft_drive": 0.024, "left_noise_bias": 1.02, "right_noise_bias": 0.99, "hrtf_azimuth": -6.0, "hrtf_elevation": 16.0, "hrtf_blend": 0.78, "engine_bias": 0.80, "engine_side": -0.10},
    "Passenger Seat": {"source": "passenger", "mode": "passenger", "noise": "midsize_100", "tail_ms": 64, "target_peak": 0.50, "direct_mix": 0.010, "crossfeed": 0.026, "cabin_bias": 0.36, "noise_gain": 0.14, "width_base": 0.003, "box_cut": 0.22, "soft_drive": 0.028, "left_noise_bias": 0.99, "right_noise_bias": 1.03, "hrtf_azimuth": 18.0, "hrtf_elevation": 4.0, "hrtf_blend": 0.60, "engine_bias": 0.96, "engine_side": -0.20},
    "Passenger Window": {"source": "passenger", "mode": "passenger", "noise": "midsize_100", "tail_ms": 66, "target_peak": 0.48, "direct_mix": 0.008, "crossfeed": 0.026, "cabin_bias": 0.38, "noise_gain": 0.16, "width_base": 0.003, "box_cut": 0.22, "soft_drive": 0.030, "left_noise_bias": 0.98, "right_noise_bias": 1.06, "hrtf_azimuth": 22.0, "hrtf_elevation": 6.0, "hrtf_blend": 0.66, "engine_bias": 1.02, "engine_side": -0.26},
    "Second Row Left": {"source": "second_left", "mode": "second_left", "noise": "midsize_80", "tail_ms": 70, "target_peak": 0.48, "direct_mix": 0.006, "crossfeed": 0.030, "cabin_bias": 0.42, "noise_gain": 0.15, "width_base": 0.004, "box_cut": 0.20, "soft_drive": 0.032, "left_noise_bias": 1.04, "right_noise_bias": 0.99, "hrtf_azimuth": -34.0, "hrtf_elevation": 0.0, "hrtf_blend": 0.56, "engine_bias": 1.08, "engine_side": -0.12},
    "Second Row Right": {"source": "second_right", "mode": "second_right", "noise": "midsize_80", "tail_ms": 70, "target_peak": 0.48, "direct_mix": 0.006, "crossfeed": 0.030, "cabin_bias": 0.42, "noise_gain": 0.15, "width_base": 0.004, "box_cut": 0.20, "soft_drive": 0.032, "left_noise_bias": 0.99, "right_noise_bias": 1.04, "hrtf_azimuth": 34.0, "hrtf_elevation": 0.0, "hrtf_blend": 0.56, "engine_bias": 1.08, "engine_side": -0.18},
    "Back Seat": {"source": "rear_left", "mode": "back", "noise": "midsize_80", "tail_ms": 76, "target_peak": 0.46, "direct_mix": 0.004, "crossfeed": 0.034, "cabin_bias": 0.48, "noise_gain": 0.16, "width_base": 0.005, "box_cut": 0.18, "soft_drive": 0.034, "left_noise_bias": 1.01, "right_noise_bias": 1.01, "hrtf_azimuth": 0.0, "hrtf_elevation": -4.0, "hrtf_blend": 0.48, "engine_bias": 1.12, "engine_side": -0.16},
    "Taxi Idle": {"source": "driver", "mode": "handsfree", "noise": "midsize_80", "tail_ms": 58, "target_peak": 0.50, "direct_mix": 0.010, "crossfeed": 0.022, "cabin_bias": 0.32, "noise_gain": 0.10, "width_base": 0.001, "box_cut": 0.22, "soft_drive": 0.030, "left_noise_bias": 1.02, "right_noise_bias": 1.00, "hrtf_azimuth": -6.0, "hrtf_elevation": 8.0, "hrtf_blend": 0.72, "engine_bias": 1.34, "engine_side": -0.12},
    "Highway": {"source": "driver", "mode": "highway", "noise": "midsize_130", "tail_ms": 62, "target_peak": 0.48, "direct_mix": 0.008, "crossfeed": 0.026, "cabin_bias": 0.34, "noise_gain": 0.20, "width_base": 0.002, "box_cut": 0.24, "soft_drive": 0.032, "left_noise_bias": 1.03, "right_noise_bias": 0.99, "hrtf_azimuth": -10.0, "hrtf_elevation": 6.0, "hrtf_blend": 0.70, "engine_bias": 1.16, "engine_side": -0.14},
    "Rainy Commute": {"source": "driver", "mode": "window", "noise": "crossroad", "tail_ms": 64, "target_peak": 0.48, "direct_mix": 0.008, "crossfeed": 0.026, "cabin_bias": 0.36, "noise_gain": 0.18, "width_base": 0.002, "box_cut": 0.24, "soft_drive": 0.032, "left_noise_bias": 1.04, "right_noise_bias": 0.99, "hrtf_azimuth": -12.0, "hrtf_elevation": 10.0, "hrtf_blend": 0.74, "engine_bias": 1.02, "engine_side": -0.14, "rain_bias": 1.34},
    "Window Cracked": {"source": "driver", "mode": "window", "noise": "crossroad", "tail_ms": 58, "target_peak": 0.48, "direct_mix": 0.008, "crossfeed": 0.022, "cabin_bias": 0.32, "noise_gain": 0.18, "width_base": 0.002, "box_cut": 0.24, "soft_drive": 0.030, "left_noise_bias": 1.05, "right_noise_bias": 0.98, "hrtf_azimuth": -14.0, "hrtf_elevation": 8.0, "hrtf_blend": 0.74, "engine_bias": 1.08, "engine_side": -0.12},
    "Tunnel Cruise": {"source": "driver", "mode": "highway", "noise": "fullsize_100", "tail_ms": 88, "target_peak": 0.46, "direct_mix": 0.006, "crossfeed": 0.036, "cabin_bias": 0.54, "noise_gain": 0.20, "width_base": 0.005, "box_cut": 0.18, "soft_drive": 0.036, "left_noise_bias": 1.03, "right_noise_bias": 0.99, "hrtf_azimuth": -8.0, "hrtf_elevation": 8.0, "hrtf_blend": 0.62, "engine_bias": 1.10, "engine_side": -0.12},
    "Drive-Thru": {"source": "driver", "mode": "drive_thru", "noise": "legacy", "tail_ms": 42, "target_peak": 0.50, "direct_mix": 0.012, "crossfeed": 0.010, "cabin_bias": 0.20, "noise_gain": 0.10, "width_base": 0.000, "box_cut": 0.30, "soft_drive": 0.018, "left_noise_bias": 1.00, "right_noise_bias": 1.00, "hrtf_azimuth": -2.0, "hrtf_elevation": 2.0, "hrtf_blend": 0.86, "engine_bias": 0.60, "engine_side": -0.10},
    "Parking Garage": {"source": "driver", "mode": "garage", "noise": "midsize_80", "tail_ms": 74, "target_peak": 0.46, "direct_mix": 0.006, "crossfeed": 0.030, "cabin_bias": 0.46, "noise_gain": 0.08, "width_base": 0.003, "box_cut": 0.18, "soft_drive": 0.026, "left_noise_bias": 1.01, "right_noise_bias": 1.00, "hrtf_azimuth": -6.0, "hrtf_elevation": 10.0, "hrtf_blend": 0.52, "engine_bias": 0.72, "engine_side": -0.12},
    "SUV Highway": {"source": "driver", "mode": "suv_highway", "noise": "fullsize_130", "tail_ms": 66, "target_peak": 0.48, "direct_mix": 0.008, "crossfeed": 0.028, "cabin_bias": 0.38, "noise_gain": 0.22, "width_base": 0.003, "box_cut": 0.22, "soft_drive": 0.034, "left_noise_bias": 1.03, "right_noise_bias": 0.99, "hrtf_azimuth": -8.0, "hrtf_elevation": 8.0, "hrtf_blend": 0.72, "engine_bias": 1.22, "engine_side": -0.14},
    "City Night": {"source": "driver", "mode": "window", "noise": "crossroad", "tail_ms": 62, "target_peak": 0.48, "direct_mix": 0.008, "crossfeed": 0.026, "cabin_bias": 0.34, "noise_gain": 0.18, "width_base": 0.003, "box_cut": 0.24, "soft_drive": 0.030, "left_noise_bias": 1.05, "right_noise_bias": 0.98, "hrtf_azimuth": -12.0, "hrtf_elevation": 9.0, "hrtf_blend": 0.74, "engine_bias": 0.94, "engine_side": -0.12, "traffic_bed": "crossroad", "traffic_bias": 1.26, "air_bias": 0.92, "motion_bias": 0.82},
    "Traffic Jam": {"source": "driver", "mode": "handsfree", "noise": "crossroad", "tail_ms": 60, "target_peak": 0.48, "direct_mix": 0.010, "crossfeed": 0.028, "cabin_bias": 0.34, "noise_gain": 0.14, "width_base": 0.003, "box_cut": 0.24, "soft_drive": 0.028, "left_noise_bias": 1.04, "right_noise_bias": 0.99, "hrtf_azimuth": -8.0, "hrtf_elevation": 8.0, "hrtf_blend": 0.72, "engine_bias": 0.82, "engine_side": -0.12, "traffic_bed": "crossroad", "traffic_bias": 1.38, "air_bias": 1.18, "motion_bias": 0.42},
    "Ride Share Rear Right": {"source": "second_right", "mode": "second_right", "noise": "midsize_80", "tail_ms": 74, "target_peak": 0.48, "direct_mix": 0.006, "crossfeed": 0.032, "cabin_bias": 0.44, "noise_gain": 0.16, "width_base": 0.004, "box_cut": 0.20, "soft_drive": 0.032, "left_noise_bias": 0.99, "right_noise_bias": 1.05, "hrtf_azimuth": 32.0, "hrtf_elevation": 2.0, "hrtf_blend": 0.58, "engine_bias": 1.04, "engine_side": -0.18, "traffic_bed": "crossroad", "traffic_bias": 1.10, "air_bias": 0.90, "motion_bias": 0.84},
    "Luxury SUV Night": {"source": "driver", "mode": "suv_highway", "noise": "fullsize_130", "tail_ms": 74, "target_peak": 0.46, "direct_mix": 0.008, "crossfeed": 0.030, "cabin_bias": 0.42, "noise_gain": 0.18, "width_base": 0.004, "box_cut": 0.20, "soft_drive": 0.032, "left_noise_bias": 1.02, "right_noise_bias": 0.99, "hrtf_azimuth": -8.0, "hrtf_elevation": 10.0, "hrtf_blend": 0.74, "engine_bias": 1.10, "engine_side": -0.12, "traffic_bed": "midsize_130", "traffic_bias": 0.86, "air_bias": 1.04, "motion_bias": 0.98},
    "Storm Run": {"source": "driver", "mode": "window", "noise": "crossroad", "tail_ms": 70, "target_peak": 0.46, "direct_mix": 0.008, "crossfeed": 0.028, "cabin_bias": 0.38, "noise_gain": 0.18, "width_base": 0.003, "box_cut": 0.22, "soft_drive": 0.034, "left_noise_bias": 1.05, "right_noise_bias": 0.98, "hrtf_azimuth": -12.0, "hrtf_elevation": 10.0, "hrtf_blend": 0.72, "engine_bias": 0.98, "engine_side": -0.12, "rain_bias": 1.60, "traffic_bed": "crossroad", "traffic_bias": 1.12, "air_bias": 0.96, "motion_bias": 0.88},
}

DEFAULTS = {
    "preset": "Handsfree",
    "song_path": "",
    "song_enabled": False,
    "song_loop": True,
    "song_level": 36,
    **PRESETS["Handsfree"],
}

_RAW_IR_CACHE = None
_NOISE_LOOP_CACHE = {}
_REAL_BED_CACHE = {}
_SHAPED_BED_CACHE = {}


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
    if frame_rate == SAMPLE_RATE or frame_rate <= 0:
        return data.astype(np.float32, copy=False)

    target_length = int(round((data.shape[0] * SAMPLE_RATE) / frame_rate))
    if target_length <= 1:
        return data[:1].astype(np.float32, copy=False)

    source_positions = np.arange(data.shape[0], dtype=np.float32)
    target_positions = np.linspace(0.0, max(0.0, data.shape[0] - 1), target_length, dtype=np.float32)
    if data.ndim == 1:
        return np.interp(target_positions, source_positions, data).astype(np.float32)

    channels = [np.interp(target_positions, source_positions, data[:, channel]) for channel in range(data.shape[1])]
    return np.column_stack(channels).astype(np.float32, copy=False)


def _normalize_noise_bed(stereo_data, target_rms=0.16):
    if stereo_data is None or stereo_data.size == 0:
        return None

    data = stereo_data.astype(np.float32, copy=True)
    peak_99 = float(np.percentile(np.abs(data), 99.8))
    if peak_99 > 0.95:
        data *= 0.95 / peak_99

    rms = float(np.sqrt(np.mean(data * data)))
    if rms > 1e-6:
        data *= target_rms / rms

    return np.clip(data, -1.25, 1.25).astype(np.float32, copy=False)


def load_noise_loop(bed_name="legacy"):
    global _NOISE_LOOP_CACHE
    if bed_name in _NOISE_LOOP_CACHE:
        return _NOISE_LOOP_CACHE[bed_name]

    path = NOISE_BED_FILES.get(bed_name, NOISE_LOOP_PATH)
    if not os.path.exists(path):
        if bed_name != "legacy":
            return load_noise_loop("legacy")
        _NOISE_LOOP_CACHE[bed_name] = None
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
            print(f"Car Cabin noise loop load failed: {exc}")
            _NOISE_LOOP_CACHE[bed_name] = None
            return None

        if width != 2:
            print(f"Car Cabin noise bed could not be decoded: {os.path.basename(path)}")
            _NOISE_LOOP_CACHE[bed_name] = None
            return None

        data = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
        data = data.reshape(-1, channels)

    data = data.astype(np.float32, copy=False)
    if data.shape[1] == 1:
        stereo = np.repeat(data, 2, axis=1)
    elif data.shape[1] == 2:
        stereo = data[:, :2]
    else:
        left = np.mean(data[:, 0::2], axis=1)
        right = np.mean(data[:, 1::2], axis=1)
        stereo = np.column_stack((left, right))

    stereo = resample_audio(stereo, frame_rate)
    stereo -= np.mean(stereo, axis=0, keepdims=True)
    stereo = _normalize_noise_bed(stereo)
    _NOISE_LOOP_CACHE[bed_name] = stereo
    return stereo


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
            print(f"Car Cabin ambient bed load failed for {os.path.basename(path)}: {exc}")
            _REAL_BED_CACHE[bed_name] = None
            return None

        if width != 2:
            print(f"Car Cabin ambient bed decode unsupported for {os.path.basename(path)}")
            _REAL_BED_CACHE[bed_name] = None
            return None

        data = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
        data = data.reshape(-1, channels)

    stereo = ensure_stereo_frames(data)
    stereo = resample_audio(stereo, frame_rate)
    stereo -= np.mean(stereo, axis=0, keepdims=True)
    stereo = _normalize_noise_bed(stereo, target_rms=0.18)
    _REAL_BED_CACHE[bed_name] = stereo
    return stereo


def _one_pole_lowpass(audio_data, cutoff_hz):
    if cutoff_hz is None or cutoff_hz <= 0.0:
        return np.asarray(audio_data, dtype=np.float32)

    alpha = float(1.0 - math.exp((-2.0 * math.pi * cutoff_hz) / SAMPLE_RATE))
    if alpha >= 0.9999:
        return np.asarray(audio_data, dtype=np.float32)

    array = np.asarray(audio_data, dtype=np.float32)
    b = np.array([alpha], dtype=np.float32)
    a = np.array([1.0, -(1.0 - alpha)], dtype=np.float32)

    if array.ndim == 1:
        if lfilter is not None:
            return lfilter(b, a, array).astype(np.float32, copy=False)
        output = np.empty_like(array, dtype=np.float32)
        state = 0.0
        for index, sample in enumerate(array):
            state += alpha * (float(sample) - state)
            output[index] = state
        return output

    output = np.empty_like(array, dtype=np.float32)
    if lfilter is not None:
        for channel in range(array.shape[1]):
            output[:, channel] = lfilter(b, a, array[:, channel]).astype(np.float32, copy=False)
        return output

    for channel in range(array.shape[1]):
        state = 0.0
        for index, sample in enumerate(array[:, channel]):
            state += alpha * (float(sample) - state)
            output[index, channel] = state
    return output


def shape_real_bed(bed_name, lowpass_hz=None, highpass_hz=None, width=1.0, target_rms=0.18):
    global _SHAPED_BED_CACHE
    cache_key = (bed_name, float(lowpass_hz or 0.0), float(highpass_hz or 0.0), float(width), float(target_rms))
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
    shaped = _normalize_noise_bed(shaped, target_rms=target_rms)
    _SHAPED_BED_CACHE[cache_key] = shaped
    return shaped


def load_media_audio(path):
    if not path or not os.path.exists(path):
        raise FileNotFoundError(path or "No file selected")

    data = None
    frame_rate = 0
    if sf is not None:
        try:
            data, frame_rate = sf.read(path, dtype="float32", always_2d=True)
        except Exception:
            data = None
            frame_rate = 0

    if data is None and AudioSegment is not None:
        try:
            segment = AudioSegment.from_file(path)
            if segment.channels != 2:
                segment = segment.set_channels(2)
            if segment.frame_rate != SAMPLE_RATE:
                segment = segment.set_frame_rate(SAMPLE_RATE)

            sample_width = max(1, int(segment.sample_width))
            pcm = np.array(segment.get_array_of_samples())
            data = pcm.reshape(-1, segment.channels).astype(np.float32)
            data /= float(1 << ((sample_width * 8) - 1))
            frame_rate = int(segment.frame_rate)
        except Exception:
            data = None
            frame_rate = 0

    if data is None and audioread is not None:
        try:
            with audioread.audio_open(path) as media:
                frame_rate = int(getattr(media, "samplerate", 0) or 0)
                channels = max(1, int(getattr(media, "channels", 2) or 2))
                chunks = [np.frombuffer(chunk, dtype="<i2") for chunk in media]
            if chunks:
                decoded = np.concatenate(chunks).astype(np.float32) / 32768.0
                data = decoded.reshape(-1, channels)
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
            raise ValueError(f"Could not decode audio file: {os.path.basename(path)}") from exc

        if width != 2:
            raise ValueError(f"Unsupported sample format in {os.path.basename(path)}")

        data = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
        data = data.reshape(-1, channels)

    stereo = ensure_stereo_frames(data)
    stereo = resample_audio(stereo, frame_rate)
    stereo -= np.mean(stereo, axis=0, keepdims=True)
    stereo = stereo - _one_pole_lowpass(stereo, 28.0)

    peak = float(np.max(np.abs(stereo))) if stereo.size else 0.0
    if peak > 0.92:
        stereo *= 0.92 / peak
    rms = float(np.sqrt(np.mean(stereo * stereo))) if stereo.size else 0.0
    if rms > 0.16:
        stereo *= 0.16 / max(rms, 1e-6)
    return np.clip(stereo, -1.0, 1.0).astype(np.float32, copy=False)


def load_fir_response(lsp_id, mic_id):
    path = os.path.join(IR_ROOT, f"lsp_{lsp_id:02d}_mic_{mic_id:02d}_enh.fir")
    if not os.path.exists(path):
        return None

    try:
        with open(path, "rb") as handle:
            sample_count = struct.unpack("<i", handle.read(4))[0]
            data = np.fromfile(handle, dtype="<f4", count=sample_count)
    except Exception as exc:
        print(f"Car Cabin IR load failed for {os.path.basename(path)}: {exc}")
        return None

    if data.size == 0:
        return None
    return data.astype(np.float32, copy=False)


def load_raw_ir_bank():
    global _RAW_IR_CACHE
    if _RAW_IR_CACHE is not None:
        return _RAW_IR_CACHE

    bank = {}
    for name, (lsp_id, mic_id) in IR_SOURCES.items():
        response = load_fir_response(lsp_id, mic_id)
        if response is not None:
            bank[name] = response

    _RAW_IR_CACHE = bank
    return _RAW_IR_CACHE


def pad_to_length(data, length):
    if data.shape[0] >= length:
        return data
    output = np.zeros(length, dtype=np.float32)
    output[: data.shape[0]] = data
    return output


def mix_weighted_responses(bank, weights):
    available = [(bank[name], float(weight)) for name, weight in weights.items() if name in bank and weight > 0.0]
    if not available:
        return None

    length = max(response.shape[0] for response, _ in available)
    output = np.zeros(length, dtype=np.float32)
    for response, weight in available:
        output[: response.shape[0]] += response * weight
    return output


def _key(source_name, mic_name):
    return f"{source_name}_{mic_name}"


def _scene_weights(source_name, mode):
    k = lambda mic: _key(source_name, mic)

    if mode == "driver":
        return {
            "close_left": {k("roof_front"): 0.30, k("array_l"): 0.24, k("array_ml"): 0.20, k("bpillar"): 0.18, k("driver_ear_left"): 0.08},
            "close_right": {k("roof_front"): 0.26, k("array_mr"): 0.20, k("array_r"): 0.14, k("roof_pass"): 0.18, k("driver_ear_right"): 0.08},
            "cabin_left": {k("driver_ear_left"): 0.34, k("roof_front"): 0.20, k("bpillar"): 0.18, k("roof_mid_left"): 0.12, k("mid_l"): 0.08, k("rear_ml"): 0.08},
            "cabin_right": {k("driver_ear_right"): 0.34, k("roof_front"): 0.18, k("roof_pass"): 0.18, k("roof_mid_right"): 0.10, k("mid_r"): 0.08, k("rear_mr"): 0.08, k("array_r"): 0.04},
        }

    if mode == "handsfree":
        return {
            "close_left": {k("roof_front"): 0.26, k("array_l"): 0.22, k("array_ml"): 0.24, k("bpillar"): 0.16, k("driver_ear_left"): 0.06},
            "close_right": {k("roof_front"): 0.24, k("array_mr"): 0.24, k("array_r"): 0.18, k("roof_pass"): 0.18, k("driver_ear_right"): 0.06},
            "cabin_left": {k("driver_ear_left"): 0.28, k("roof_front"): 0.20, k("bpillar"): 0.16, k("roof_mid_left"): 0.10, k("mid_l"): 0.10, k("rear_ml"): 0.06, k("array_l"): 0.10},
            "cabin_right": {k("driver_ear_right"): 0.28, k("roof_front"): 0.16, k("roof_pass"): 0.20, k("roof_mid_right"): 0.10, k("mid_r"): 0.10, k("rear_mr"): 0.06, k("array_r"): 0.10},
        }

    if mode == "dash":
        return {
            "close_left": {k("roof_front"): 0.26, k("array_ml"): 0.30, k("array_mr"): 0.18, k("array_l"): 0.16, k("bpillar"): 0.10},
            "close_right": {k("roof_front"): 0.24, k("array_mr"): 0.30, k("array_ml"): 0.18, k("array_r"): 0.18, k("roof_pass"): 0.10},
            "cabin_left": {k("driver_ear_left"): 0.18, k("roof_front"): 0.22, k("array_ml"): 0.20, k("array_l"): 0.14, k("roof_mid_left"): 0.12, k("bpillar"): 0.14},
            "cabin_right": {k("driver_ear_right"): 0.18, k("roof_front"): 0.22, k("array_mr"): 0.22, k("array_r"): 0.12, k("roof_mid_right"): 0.12, k("roof_pass"): 0.14},
        }

    if mode == "mirror":
        return {
            "close_left": {k("bpillar"): 0.28, k("roof_front"): 0.26, k("array_l"): 0.18, k("array_ml"): 0.18, k("driver_ear_left"): 0.10},
            "close_right": {k("roof_front"): 0.26, k("array_mr"): 0.22, k("roof_pass"): 0.20, k("array_r"): 0.14, k("driver_ear_right"): 0.08, k("bpillar"): 0.10},
            "cabin_left": {k("driver_ear_left"): 0.24, k("bpillar"): 0.20, k("roof_front"): 0.20, k("roof_mid_left"): 0.14, k("mid_l"): 0.10, k("rear_ml"): 0.06, k("array_l"): 0.06},
            "cabin_right": {k("driver_ear_right"): 0.24, k("roof_front"): 0.18, k("roof_pass"): 0.18, k("roof_mid_right"): 0.14, k("mid_r"): 0.10, k("rear_mr"): 0.06, k("array_r"): 0.10},
        }

    if mode == "roof_console":
        return {
            "close_left": {k("roof_front"): 0.30, k("array_ml"): 0.24, k("array_l"): 0.16, k("bpillar"): 0.14, k("roof_mid_left"): 0.10, k("driver_ear_left"): 0.06},
            "close_right": {k("roof_pass"): 0.28, k("array_mr"): 0.24, k("roof_front"): 0.18, k("array_r"): 0.14, k("roof_mid_right"): 0.10, k("driver_ear_right"): 0.06},
            "cabin_left": {k("roof_front"): 0.24, k("driver_ear_left"): 0.18, k("roof_mid_left"): 0.16, k("bpillar"): 0.16, k("array_ml"): 0.12, k("mid_l"): 0.08, k("rear_ml"): 0.06},
            "cabin_right": {k("roof_pass"): 0.24, k("driver_ear_right"): 0.18, k("roof_mid_right"): 0.16, k("roof_front"): 0.14, k("array_mr"): 0.12, k("mid_r"): 0.08, k("rear_mr"): 0.08},
        }

    if mode == "passenger":
        return {
            "close_left": {k("roof_front"): 0.18, k("array_l"): 0.14, k("array_ml"): 0.22, k("array_mr"): 0.22, k("roof_pass"): 0.24},
            "close_right": {k("roof_front"): 0.16, k("array_mr"): 0.22, k("array_r"): 0.20, k("roof_pass"): 0.28, k("driver_ear_right"): 0.08, k("array_ml"): 0.06},
            "cabin_left": {k("driver_ear_left"): 0.30, k("roof_front"): 0.18, k("array_ml"): 0.16, k("roof_mid_left"): 0.12, k("mid_l"): 0.10, k("rear_ml"): 0.08, k("roof_pass"): 0.06},
            "cabin_right": {k("driver_ear_right"): 0.34, k("roof_pass"): 0.20, k("array_r"): 0.14, k("roof_mid_right"): 0.12, k("mid_r"): 0.10, k("rear_mr"): 0.08, k("roof_front"): 0.02},
        }

    if mode == "second_left":
        return {
            "close_left": {k("roof_mid_left"): 0.26, k("mid_l"): 0.22, k("mid_ml"): 0.18, k("roof_front"): 0.14, k("driver_ear_left"): 0.10, k("bpillar"): 0.10},
            "close_right": {k("mid_ml"): 0.24, k("mid_mr"): 0.14, k("roof_mid_right"): 0.16, k("roof_front"): 0.18, k("driver_ear_right"): 0.12, k("roof_pass"): 0.10},
            "cabin_left": {k("driver_ear_left"): 0.34, k("roof_mid_left"): 0.18, k("mid_l"): 0.14, k("roof_front"): 0.12, k("rear_ml"): 0.08, k("rear_l"): 0.08, k("bpillar"): 0.06},
            "cabin_right": {k("driver_ear_right"): 0.34, k("roof_mid_right"): 0.18, k("mid_mr"): 0.12, k("roof_pass"): 0.12, k("rear_mr"): 0.08, k("rear_r"): 0.08, k("roof_front"): 0.08},
        }

    if mode == "second_right":
        return {
            "close_left": {k("mid_ml"): 0.18, k("mid_mr"): 0.22, k("roof_mid_left"): 0.16, k("roof_front"): 0.18, k("driver_ear_left"): 0.12, k("bpillar"): 0.08, k("roof_pass"): 0.06},
            "close_right": {k("roof_mid_right"): 0.24, k("mid_r"): 0.22, k("mid_mr"): 0.18, k("roof_pass"): 0.14, k("driver_ear_right"): 0.12, k("roof_front"): 0.10},
            "cabin_left": {k("driver_ear_left"): 0.34, k("roof_mid_left"): 0.18, k("mid_ml"): 0.12, k("roof_front"): 0.12, k("rear_ml"): 0.08, k("rear_l"): 0.06, k("bpillar"): 0.10},
            "cabin_right": {k("driver_ear_right"): 0.34, k("roof_mid_right"): 0.18, k("mid_r"): 0.14, k("roof_pass"): 0.12, k("rear_mr"): 0.08, k("rear_r"): 0.08, k("roof_front"): 0.06},
        }

    if mode == "back":
        return {
            "close_left": {k("roof_rear_left"): 0.22, k("rear_l"): 0.18, k("rear_ml"): 0.14, _key("rear_right", "rear_ml"): 0.10, k("roof_mid_left"): 0.10, k("driver_ear_left"): 0.10, _key("rear_right", "driver_ear_left"): 0.06, k("roof_front"): 0.10},
            "close_right": {_key("rear_right", "roof_rear_right"): 0.22, _key("rear_right", "rear_r"): 0.18, _key("rear_right", "rear_mr"): 0.14, k("rear_mr"): 0.10, _key("rear_right", "roof_mid_right"): 0.10, _key("rear_right", "driver_ear_right"): 0.10, k("driver_ear_right"): 0.06, _key("rear_right", "roof_pass"): 0.10},
            "cabin_left": {k("driver_ear_left"): 0.22, _key("rear_right", "driver_ear_left"): 0.18, k("roof_mid_left"): 0.12, _key("rear_right", "roof_mid_right"): 0.10, k("roof_front"): 0.10, k("mid_l"): 0.08, _key("rear_right", "mid_ml"): 0.08, k("rear_l"): 0.06, _key("rear_right", "rear_ml"): 0.06},
            "cabin_right": {_key("rear_right", "driver_ear_right"): 0.22, k("driver_ear_right"): 0.18, _key("rear_right", "roof_mid_right"): 0.12, k("roof_mid_left"): 0.10, _key("rear_right", "roof_pass"): 0.10, _key("rear_right", "mid_r"): 0.08, k("mid_mr"): 0.08, _key("rear_right", "rear_r"): 0.06, k("rear_mr"): 0.06},
        }

    if mode == "highway":
        return {
            "close_left": {k("roof_front"): 0.24, k("array_l"): 0.20, k("array_ml"): 0.20, k("bpillar"): 0.20, k("driver_ear_left"): 0.08, k("roof_mid_left"): 0.08},
            "close_right": {k("roof_front"): 0.20, k("array_mr"): 0.20, k("array_r"): 0.14, k("roof_pass"): 0.22, k("driver_ear_right"): 0.08, k("roof_mid_right"): 0.08, k("bpillar"): 0.08},
            "cabin_left": {k("driver_ear_left"): 0.28, k("bpillar"): 0.22, k("roof_front"): 0.18, k("roof_mid_left"): 0.12, k("mid_l"): 0.08, k("rear_ml"): 0.08, k("rear_l"): 0.04},
            "cabin_right": {k("driver_ear_right"): 0.28, k("roof_pass"): 0.20, k("roof_front"): 0.14, k("roof_mid_right"): 0.12, k("mid_r"): 0.08, k("rear_mr"): 0.08, k("rear_r"): 0.04, k("array_r"): 0.06},
        }

    if mode == "window":
        return {
            "close_left": {k("roof_front"): 0.24, k("array_l"): 0.22, k("array_ml"): 0.20, k("bpillar"): 0.22, k("driver_ear_left"): 0.08, k("roof_mid_left"): 0.04},
            "close_right": {k("roof_front"): 0.20, k("array_mr"): 0.20, k("array_r"): 0.14, k("roof_pass"): 0.24, k("driver_ear_right"): 0.08, k("roof_mid_right"): 0.06, k("bpillar"): 0.08},
            "cabin_left": {k("driver_ear_left"): 0.28, k("bpillar"): 0.22, k("roof_front"): 0.18, k("roof_mid_left"): 0.12, k("mid_l"): 0.08, k("rear_ml"): 0.08, k("array_l"): 0.04},
            "cabin_right": {k("driver_ear_right"): 0.28, k("roof_pass"): 0.20, k("roof_front"): 0.14, k("roof_mid_right"): 0.12, k("mid_r"): 0.08, k("rear_mr"): 0.08, k("array_r"): 0.10},
        }

    if mode == "drive_thru":
        return {
            "close_left": {k("roof_front"): 0.24, k("array_ml"): 0.26, k("array_l"): 0.20, k("bpillar"): 0.20, k("driver_ear_left"): 0.10},
            "close_right": {k("roof_front"): 0.22, k("array_mr"): 0.28, k("array_r"): 0.18, k("roof_pass"): 0.18, k("driver_ear_right"): 0.10, k("array_ml"): 0.04},
            "cabin_left": {k("driver_ear_left"): 0.20, k("bpillar"): 0.24, k("roof_front"): 0.22, k("array_l"): 0.18, k("roof_mid_left"): 0.10, k("mid_l"): 0.06},
            "cabin_right": {k("driver_ear_right"): 0.20, k("roof_front"): 0.22, k("roof_pass"): 0.18, k("array_r"): 0.18, k("roof_mid_right"): 0.10, k("mid_r"): 0.06, k("array_mr"): 0.06},
        }

    if mode == "garage":
        return {
            "close_left": {k("roof_front"): 0.22, k("array_l"): 0.18, k("array_ml"): 0.18, k("bpillar"): 0.18, k("driver_ear_left"): 0.12, k("roof_mid_left"): 0.12},
            "close_right": {k("roof_front"): 0.20, k("array_mr"): 0.18, k("array_r"): 0.14, k("roof_pass"): 0.18, k("driver_ear_right"): 0.12, k("roof_mid_right"): 0.12, k("array_ml"): 0.06},
            "cabin_left": {k("driver_ear_left"): 0.28, k("bpillar"): 0.16, k("roof_front"): 0.18, k("roof_mid_left"): 0.14, k("mid_l"): 0.12, k("rear_ml"): 0.08, k("rear_l"): 0.04},
            "cabin_right": {k("driver_ear_right"): 0.28, k("roof_pass"): 0.16, k("roof_front"): 0.18, k("roof_mid_right"): 0.14, k("mid_r"): 0.12, k("rear_mr"): 0.08, k("rear_r"): 0.04},
        }

    if mode == "suv_highway":
        return {
            "close_left": {k("roof_front"): 0.22, k("array_l"): 0.18, k("array_ml"): 0.20, k("bpillar"): 0.18, k("driver_ear_left"): 0.08, k("roof_mid_left"): 0.14},
            "close_right": {k("roof_front"): 0.18, k("array_mr"): 0.20, k("array_r"): 0.16, k("roof_pass"): 0.22, k("driver_ear_right"): 0.08, k("roof_mid_right"): 0.14, k("array_ml"): 0.02},
            "cabin_left": {k("driver_ear_left"): 0.24, k("bpillar"): 0.18, k("roof_front"): 0.16, k("roof_mid_left"): 0.16, k("mid_l"): 0.12, k("rear_ml"): 0.08, k("rear_l"): 0.06},
            "cabin_right": {k("driver_ear_right"): 0.24, k("roof_pass"): 0.18, k("roof_front"): 0.12, k("roof_mid_right"): 0.16, k("mid_r"): 0.12, k("rear_mr"): 0.08, k("rear_r"): 0.06, k("array_r"): 0.04},
        }

    return {
        "close_left": {k("roof_front"): 0.22, k("array_l"): 0.18, k("array_ml"): 0.20, k("bpillar"): 0.18, k("driver_ear_left"): 0.10, k("roof_mid_left"): 0.12},
        "close_right": {k("roof_front"): 0.20, k("array_mr"): 0.18, k("array_r"): 0.14, k("roof_pass"): 0.22, k("driver_ear_right"): 0.10, k("roof_mid_right"): 0.12, k("array_ml"): 0.04},
        "cabin_left": {k("driver_ear_left"): 0.28, k("bpillar"): 0.18, k("roof_front"): 0.16, k("roof_mid_left"): 0.14, k("mid_l"): 0.10, k("rear_ml"): 0.08, k("rear_l"): 0.06},
        "cabin_right": {k("driver_ear_right"): 0.28, k("roof_pass"): 0.18, k("roof_front"): 0.14, k("roof_mid_right"): 0.14, k("mid_r"): 0.10, k("rear_mr"): 0.08, k("rear_r"): 0.06, k("array_r"): 0.02},
    }


def blend_responses(close_response, cabin_response, amount):
    if close_response is None and cabin_response is None:
        return None
    if close_response is None:
        return cabin_response.astype(np.float32, copy=True)
    if cabin_response is None:
        return close_response.astype(np.float32, copy=True)

    length = max(close_response.shape[0], cabin_response.shape[0])
    close_data = pad_to_length(close_response, length)
    cabin_data = pad_to_length(cabin_response, length)
    return ((close_data * (1.0 - amount)) + (cabin_data * amount)).astype(np.float32, copy=False)


def shape_stereo_pair(left_response, right_response, tail_ms, target_peak):
    if left_response is None and right_response is None:
        unit = np.array([1.0], dtype=np.float32)
        return unit, unit
    if left_response is None:
        left_response = right_response.copy()
    if right_response is None:
        right_response = left_response.copy()

    left_peak = int(np.argmax(np.abs(left_response)))
    right_peak = int(np.argmax(np.abs(right_response)))
    pre_roll = 24
    start = max(0, min(left_peak, right_peak) - pre_roll)

    tail_samples = int((tail_ms / 1000.0) * SAMPLE_RATE)
    end = max(left_peak + tail_samples, right_peak + tail_samples)
    end = min(end, max(left_response.shape[0], right_response.shape[0]))

    left_full = pad_to_length(left_response, end)
    right_full = pad_to_length(right_response, end)
    left_crop = left_full[start:end].astype(np.float32, copy=True)
    right_crop = right_full[start:end].astype(np.float32, copy=True)

    max_len = 400
    if left_crop.shape[0] > max_len:
        left_crop = left_crop[:max_len]
        right_crop = right_crop[:max_len]

    fade_len = min(int(0.020 * SAMPLE_RATE), left_crop.shape[0] // 3, right_crop.shape[0] // 3)
    if fade_len > 8:
        fade = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
        left_crop[-fade_len:] *= fade
        right_crop[-fade_len:] *= fade

    peak = max(float(np.max(np.abs(left_crop))), float(np.max(np.abs(right_crop))))
    if peak > 1e-6:
        scale = float(target_peak) / peak
        left_crop *= scale
        right_crop *= scale

    return left_crop.astype(np.float32, copy=False), right_crop.astype(np.float32, copy=False)


def constant_power_pan(pan):
    pan_array = np.clip(np.asarray(pan, dtype=np.float32), -1.0, 1.0)
    angle = (pan_array + 1.0) * (math.pi * 0.25)
    return np.cos(angle).astype(np.float32, copy=False), np.sin(angle).astype(np.float32, copy=False)


def pan_mono_block(mono_block, pan):
    mono = np.asarray(mono_block, dtype=np.float32)
    left_weight, right_weight = constant_power_pan(float(np.clip(pan, -1.0, 1.0)))
    return np.column_stack((mono * left_weight, mono * right_weight)).astype(np.float32, copy=False)


def vector_to_angles(vector):
    rel = np.asarray(vector, dtype=np.float32)
    distance = float(np.sqrt(np.sum(rel * rel)))
    lateral = float(rel[0])
    vertical = float(rel[1])
    forward = float(rel[2])
    azimuth = math.degrees(math.atan2(lateral, max(1e-6, forward)))
    elevation = math.degrees(math.atan2(vertical, max(1e-6, math.sqrt((lateral * lateral) + (forward * forward)))))
    return azimuth, elevation, max(1e-6, distance)


def _scene_hrtf_settings(scene, seat_pan, hrtf_ratio):
    azimuth = (float(scene.get("hrtf_azimuth", 0.0)) * (0.52 + (hrtf_ratio * 0.18))) + (seat_pan * 6.0)
    elevation = float(scene.get("hrtf_elevation", 0.0))
    blend = np.clip(float(scene.get("hrtf_blend", 0.6)) * (0.22 + (hrtf_ratio * 0.48)), 0.0, 1.0)
    return azimuth, elevation, blend


from _steam_audio import SteamAudioBinaural


class Plugin:
    def __init__(self):
        self.name = "Car Cabin"
        self.enabled = False
        self.supports_stereo = True
        self.process_stage = 100
        self.file_name = "car_cabin.py"
        self.settings_path = os.path.splitext(__file__)[0] + ".json"

        self.noise_loop = load_noise_loop("legacy")
        self.noise_bed_name = "legacy"
        self.noise_pos = 0
        self.engine_pos = 0
        self.noise_duck = 1.0
        self.raw_ir_bank = load_raw_ir_bank()
        self._scene_lock = threading.RLock()

        self.active_left_ir = np.array([1.0], dtype=np.float32)
        self.active_right_ir = np.array([1.0], dtype=np.float32)
        self.ir_history = np.zeros(0, dtype=np.float32)
        self.left_ir_state = np.zeros(0, dtype=np.float32)
        self.right_ir_state = np.zeros(0, dtype=np.float32)
        self.song_ir_history = np.zeros(0, dtype=np.float32)
        self.song_left_ir_state = np.zeros(0, dtype=np.float32)
        self.song_right_ir_state = np.zeros(0, dtype=np.float32)
        self.rng = np.random.default_rng()
        self.window_low_state = np.zeros(2, dtype=np.float32)
        self.window_high_state = np.zeros(2, dtype=np.float32)
        self.rain_low_state = np.zeros(2, dtype=np.float32)
        self.rain_high_state = np.zeros(2, dtype=np.float32)
        self.window_bed = shape_real_bed("wind", lowpass_hz=7600.0, highpass_hz=140.0, width=0.92, target_rms=0.16)
        self.window_pos = 0
        self.air_bed = shape_real_bed("wind", lowpass_hz=4200.0, highpass_hz=180.0, width=0.20, target_rms=0.14)
        self.air_pos = 0
        self.air_detail_bed = shape_real_bed("const", lowpass_hz=1400.0, highpass_hz=35.0, width=0.04, target_rms=0.12)
        self.air_detail_pos = 0
        self.rain_bed = shape_real_bed("rain", lowpass_hz=7600.0, highpass_hz=220.0, width=0.58, target_rms=0.15)
        self.rain_pos = 0
        self.rain_detail_bed = shape_real_bed("water", lowpass_hz=3600.0, highpass_hz=260.0, width=0.22, target_rms=0.14)
        self.rain_detail_pos = 0
        self.air_low_state = np.zeros(2, dtype=np.float32)
        self.air_high_state = np.zeros(2, dtype=np.float32)
        self.air_swirl_phase = math.pi * 0.18
        self.traffic_loop = load_noise_loop("crossroad")
        self.traffic_bed_name = "crossroad"
        self.traffic_pos = 0
        self.traffic_event_remaining = 0
        self.traffic_event_duration = 0
        self.traffic_event_pan_start = 0.0
        self.traffic_event_pan_end = 0.0
        self.traffic_event_gain = 0.0
        self.traffic_low_state = 0.0
        self.traffic_high_state = 0.0
        self.motion_phase = 0.0
        self.motion_secondary_phase = math.pi * 0.37

        self.hp_state = np.zeros(2, dtype=np.float32)
        self.hp_prev_in = np.zeros(2, dtype=np.float32)
        self.hp_prev_out = np.zeros(2, dtype=np.float32)
        self.low_state = np.zeros(2, dtype=np.float32)
        self.air_state = np.zeros(2, dtype=np.float32)
        self.box_state = np.zeros(2, dtype=np.float32)
        self.engine_body_state = 0.0
        self.engine_growl_state = 0.0
        self.engine_wobble_phase = 0.0
        self.steam_audio = SteamAudioBinaural()

        self.direct_mix = 0.02
        self.crossfeed = 0.05
        self.left_noise_bias = 1.0
        self.right_noise_bias = 1.0
        self.width_gain = 0.01
        self.window_gain = 0.0
        self.presence_gain = 0.05
        self.seat_pan = -0.4
        self.noise_gain = 0.12
        self.box_cut = 0.22
        self.soft_drive = 0.03
        self.hrtf_amount = 0
        self.balance = 50
        self.hrtf_scene_blend = 0.0
        self.hrtf_azimuth = 0.0
        self.hrtf_elevation = 0.0
        self.output_balance = 0.0
        self.engine_gain = 0.0
        self.engine_side = -0.10
        self.rain_gain = 0.0
        self.air_gain = 0.0
        self.air_side = -0.04
        self.traffic_gain = 0.0
        self.traffic_density = 0.0
        self.traffic_side_bias = -0.08
        self.motion_depth = 0.0
        self.motion_pan_depth = 0.0
        self.motion_rate = 0.0
        self.motion_width = 0.0
        self.song_path = ""
        self.song_enabled = False
        self.song_loop = True
        self.song_level = 36
        self.song_audio = None
        self.song_pos = 0
        self.listener_position = LISTENER_POSITIONS["driver"].copy()
        self.song_speakers = []
        self.song_speaker_histories = {}
        self.song_aux_histories = {}
        self.song_body_state = np.zeros(2, dtype=np.float32)
        self.song_tone_low_state = np.zeros(2, dtype=np.float32)
        self.song_tone_air_state = np.zeros(2, dtype=np.float32)
        self.song_tone_hp_prev_in = np.zeros(2, dtype=np.float32)
        self.song_tone_hp_prev_out = np.zeros(2, dtype=np.float32)
        self.song_fill_state = 0.0
        self.song_direct_gain = 1.0
        self.song_cabin_gain = 0.0
        self.song_fill_gain = 0.0
        self.song_duck_strength = 0.08
        self.song_motion_follow = 0.0
        self.song_soft_drive = 0.02
        self.song_body_alpha = 0.18
        self.song_stage_level = 0.38
        self.song_tone_low_alpha = 0.24
        self.song_tone_air_alpha = 0.10
        self.song_tone_hp_coeff = 0.988
        self.song_core_gain = 0.52
        self.song_body_gain = 0.22
        self.song_presence_gain = 0.10
        self.song_shell_gain = 0.10
        self.song_dash_gain = 0.08
        self.song_cross_gain = 0.05
        self.song_fill_alpha = 0.12
        self.song_dash_delay = 96
        self.song_glass_delay = 168
        self.song_cross_delay = 312

        self.preset = DEFAULTS["preset"]
        self.space = DEFAULTS["space"]
        self.speaker = DEFAULTS["speaker"]
        self.road = DEFAULTS["road"]
        self.tight = DEFAULTS["tight"]
        self.mix = DEFAULTS["mix"]
        self.width = DEFAULTS["width"]
        self.presence = DEFAULTS["presence"]
        self.seat = DEFAULTS["seat"]
        self.window = DEFAULTS["window"]
        self.hrtf_amount = DEFAULTS["hrtf"]
        self.balance = DEFAULTS["balance"]
        self.engine = DEFAULTS["engine"]
        self.rain = DEFAULTS["rain"]
        self.air = DEFAULTS["air"]
        self.traffic = DEFAULTS["traffic"]
        self.motion = DEFAULTS["motion"]
        self.song_path = DEFAULTS["song_path"]
        self.song_enabled = bool(DEFAULTS["song_enabled"])
        self.song_loop = bool(DEFAULTS["song_loop"])
        self.song_level = int(DEFAULTS["song_level"])
        self.load_settings()

    def apply_preset(self, name):
        values = PRESETS[name]
        self.preset = name
        self.space = values["space"]
        self.speaker = values["speaker"]
        self.road = values["road"]
        self.tight = values["tight"]
        self.mix = values["mix"]
        self.width = values["width"]
        self.presence = values["presence"]
        self.seat = values["seat"]
        self.window = values["window"]
        self.hrtf_amount = values["hrtf"]
        self.balance = values["balance"]
        self.engine = values["engine"]
        self.rain = values["rain"]
        self.air = values["air"]
        self.traffic = values["traffic"]
        self.motion = values["motion"]

    def set_song_source(self, path=None, enabled=None, loop=None, reset_position=False):
        if path is not None:
            normalized_path = os.path.abspath(path) if path else ""
            if normalized_path != self.song_path:
                if normalized_path:
                    self.song_audio = load_media_audio(normalized_path)
                    self.song_path = normalized_path
                else:
                    self.song_audio = None
                    self.song_path = ""
                self.song_pos = 0
                self.song_ir_history = np.zeros(0, dtype=np.float32)
                self.song_left_ir_state = np.zeros(max(0, self.active_left_ir.shape[0] - 1), dtype=np.float32)
                self.song_right_ir_state = np.zeros(max(0, self.active_right_ir.shape[0] - 1), dtype=np.float32)
                self.song_speaker_histories = {}
                self.song_aux_histories = {}
                self.song_body_state.fill(0.0)
                self.song_tone_low_state.fill(0.0)
                self.song_tone_air_state.fill(0.0)
                self.song_tone_hp_prev_in.fill(0.0)
                self.song_tone_hp_prev_out.fill(0.0)
                self.song_fill_state = 0.0
            elif reset_position:
                self.song_pos = 0
        elif reset_position:
            self.song_pos = 0

        if enabled is not None:
            self.song_enabled = bool(enabled)
        if loop is not None:
            self.song_loop = bool(loop)

    def set_live_values(self, preset_name, values):
        preset_changed = preset_name in PRESETS and preset_name != self.preset
        if preset_name in PRESETS:
            self.preset = preset_name
        self.space = int(values["space"])
        self.speaker = int(values["speaker"])
        self.road = int(values["road"])
        self.tight = int(values["tight"])
        self.mix = int(values["mix"])
        self.width = int(values["width"])
        self.presence = int(values["presence"])
        self.seat = int(values["seat"])
        self.window = int(values["window"])
        self.hrtf_amount = int(values["hrtf"])
        self.balance = int(values["balance"])
        self.engine = int(values["engine"])
        self.rain = int(values["rain"])
        self.air = int(values["air"])
        self.traffic = int(values["traffic"])
        self.motion = int(values["motion"])
        if "song_level" in values:
            self.song_level = int(values["song_level"])
        self._refresh_scene(reset_history=preset_changed)

    def load_settings(self):
        values = load_settings(self.settings_path, DEFAULTS)
        if "space" not in values and "cabin" in values:
            values["space"] = values["cabin"]
        if "road" not in values and "dash" in values:
            values["road"] = values["dash"]

        preset = values.get("preset", DEFAULTS["preset"])
        if preset not in PRESETS:
            preset = DEFAULTS["preset"]

        self.apply_preset(preset)
        self.space = int(values.get("space", self.space))
        self.speaker = int(values.get("speaker", self.speaker))
        self.road = int(values.get("road", self.road))
        self.tight = int(values.get("tight", self.tight))
        self.mix = int(values.get("mix", self.mix))
        self.width = int(values.get("width", self.width))
        self.presence = int(values.get("presence", self.presence))
        self.seat = int(values.get("seat", self.seat))
        self.window = int(values.get("window", self.window))
        self.hrtf_amount = int(values.get("hrtf", self.hrtf_amount))
        self.balance = int(values.get("balance", self.balance))
        self.engine = int(values.get("engine", self.engine))
        self.rain = int(values.get("rain", self.rain))
        self.air = int(values.get("air", self.air))
        self.traffic = int(values.get("traffic", self.traffic))
        self.motion = int(values.get("motion", self.motion))
        self.song_level = int(values.get("song_level", self.song_level))
        self.song_enabled = bool(values.get("song_enabled", self.song_enabled))
        self.song_loop = bool(values.get("song_loop", self.song_loop))
        requested_song_path = values.get("song_path", self.song_path)
        try:
            self.set_song_source(requested_song_path, enabled=self.song_enabled, loop=self.song_loop, reset_position=False)
        except Exception as exc:
            print(f"Car Cabin song load failed: {exc}")
            self.song_enabled = False
            self.song_path = ""
            self.song_audio = None
        self._refresh_scene(reset_history=True)

    def save_settings(self):
        save_settings(
            self.settings_path,
            {
                "preset": self.preset,
                "space": int(self.space),
                "speaker": int(self.speaker),
                "road": int(self.road),
                "tight": int(self.tight),
                "mix": int(self.mix),
                "width": int(self.width),
                "presence": int(self.presence),
                "seat": int(self.seat),
                "window": int(self.window),
                "hrtf": int(self.hrtf_amount),
                "balance": int(self.balance),
                "engine": int(self.engine),
                "rain": int(self.rain),
                "air": int(self.air),
                "traffic": int(self.traffic),
                "motion": int(self.motion),
                "song_path": self.song_path,
                "song_enabled": bool(self.song_enabled),
                "song_loop": bool(self.song_loop),
                "song_level": int(self.song_level),
            },
        )

    def _refresh_scene(self, reset_history):
        with self._scene_lock:
            scene = PRESET_SCENES.get(self.preset, PRESET_SCENES[DEFAULTS["preset"]])
            weights = _scene_weights(scene["source"], scene["mode"])
            space_ratio = np.clip(self.space / 100.0, 0.0, 1.0)
            width_ratio = np.clip(self.width / 100.0, 0.0, 1.0)
            tight_ratio = np.clip(self.tight / 100.0, 0.0, 1.0)
            presence_ratio = np.clip(self.presence / 100.0, 0.0, 1.0)
            window_ratio = np.clip(self.window / 100.0, 0.0, 1.0)
            engine_ratio = np.clip(self.engine / 100.0, 0.0, 1.0)
            rain_ratio = np.clip(self.rain / 100.0, 0.0, 1.0)
            air_ratio = np.clip(self.air / 100.0, 0.0, 1.0)
            traffic_ratio = np.clip(self.traffic / 100.0, 0.0, 1.0)
            motion_ratio = np.clip(self.motion / 100.0, 0.0, 1.0)
            road_ratio = np.clip(self.road / 100.0, 0.0, 1.0)
            raw_seat_pan = np.clip((self.seat - 50.0) / 50.0, -1.0, 1.0)
            seat_pan = raw_seat_pan * 0.68
            blend_amount = np.clip(scene["cabin_bias"] + (space_ratio * 0.30) - (tight_ratio * 0.16), 0.12, 0.82)

            left_response = blend_responses(
                mix_weighted_responses(self.raw_ir_bank, weights["close_left"]),
                mix_weighted_responses(self.raw_ir_bank, weights["cabin_left"]),
                blend_amount,
            )
            right_response = blend_responses(
                mix_weighted_responses(self.raw_ir_bank, weights["close_right"]),
                mix_weighted_responses(self.raw_ir_bank, weights["cabin_right"]),
                blend_amount,
            )

            tail_ms = max(36, int(scene["tail_ms"] + (space_ratio * 10.0) - (tight_ratio * 16.0)))
            target_peak = max(0.34, scene["target_peak"] - (space_ratio * 0.02) - (tight_ratio * 0.03))
            self.active_left_ir, self.active_right_ir = shape_stereo_pair(left_response, right_response, tail_ms, target_peak)

            left_ir_gain = 1.0 + max(0.0, -seat_pan) * 0.12 - max(0.0, seat_pan) * 0.04
            right_ir_gain = 1.0 + max(0.0, seat_pan) * 0.12 - max(0.0, -seat_pan) * 0.04
            self.active_left_ir *= left_ir_gain
            self.active_right_ir *= right_ir_gain

            stereo_peak = max(float(np.max(np.abs(self.active_left_ir))), float(np.max(np.abs(self.active_right_ir))))
            if stereo_peak > 1e-6:
                stereo_scale = target_peak / stereo_peak
                self.active_left_ir *= stereo_scale
                self.active_right_ir *= stereo_scale

            self.direct_mix = scene["direct_mix"] + ((1.0 - space_ratio) * 0.008) + (presence_ratio * 0.014)
            self.crossfeed = max(0.0, scene["crossfeed"] + (space_ratio * 0.016) - (width_ratio * 0.020) - (tight_ratio * 0.012))
            self.left_noise_bias = scene["left_noise_bias"] + max(0.0, -seat_pan) * 0.08
            self.right_noise_bias = scene["right_noise_bias"] + max(0.0, seat_pan) * 0.08
            noise_norm = 2.0 / max(1e-6, self.left_noise_bias + self.right_noise_bias)
            self.left_noise_bias *= noise_norm
            self.right_noise_bias *= noise_norm
            self.width_gain = max(0.0, scene["width_base"] + (width_ratio * 0.012) - (tight_ratio * 0.007))
            self.window_gain = window_ratio * (0.001 + (0.010 * (0.35 + space_ratio)))
            self.presence_gain = 0.006 + (presence_ratio * 0.030) + (tight_ratio * 0.010)
            self.seat_pan = seat_pan
            self.noise_gain = scene["noise_gain"] * (0.84 + (space_ratio * 0.12))
            self.box_cut = scene["box_cut"] + (tight_ratio * 0.10)
            self.soft_drive = scene["soft_drive"] + max(0.0, (self.speaker / 100.0) - 0.55) * 0.02
            self.engine_gain = float(scene.get("engine_bias", 1.0)) * (0.003 + (engine_ratio * 0.038))
            self.engine_side = float(scene.get("engine_side", -0.12)) - (seat_pan * 0.18)
            self.rain_gain = float(scene.get("rain_bias", 1.0)) * (0.002 + (rain_ratio * 0.030))
            self.air_gain = float(scene.get("air_bias", 1.0)) * (0.002 + (air_ratio * 0.024))
            self.air_side = float(scene.get("air_side", -0.04)) - (seat_pan * 0.10)
            self.traffic_gain = float(scene.get("traffic_bias", 1.0)) * (0.002 + (traffic_ratio * 0.026))
            self.traffic_density = np.clip(
                float(scene.get("traffic_density", 1.0)) * (0.16 + (traffic_ratio * 1.08) + (window_ratio * 0.28) + (road_ratio * 0.24)),
                0.0,
                1.8,
            )
            self.traffic_side_bias = float(scene.get("traffic_side", -0.10)) - (seat_pan * 0.18) - (window_ratio * 0.22)
            self.motion_depth = float(scene.get("motion_bias", 1.0)) * (0.04 + (motion_ratio * 0.36))
            self.motion_pan_depth = 0.010 + (motion_ratio * 0.070)
            self.motion_rate = float(scene.get("motion_rate", 1.0)) * (0.30 + (road_ratio * 1.70) + (motion_ratio * 0.55))
            self.motion_width = 0.002 + (motion_ratio * 0.010)
            listener_depth = 0.0
            if scene["source"] in ("second_left", "second_right"):
                listener_depth = 0.42
            elif scene["source"] in ("rear_left", "rear_right") or scene.get("mode") == "back":
                listener_depth = 0.72
            if scene.get("mode") == "back":
                self.listener_position = LISTENER_POSITIONS["back_center"].copy()
            else:
                self.listener_position = LISTENER_POSITIONS.get(scene["source"], LISTENER_POSITIONS["driver"]).copy()
            self.listener_position[0] += raw_seat_pan * 0.12
            self.listener_position[2] += (space_ratio - 0.5) * 0.04

            self.song_speakers = []
            for speaker in CAR_MUSIC_SPEAKERS:
                relative = speaker["position"] - self.listener_position
                vertical = float(relative[1])
                azimuth, _, distance = vector_to_angles(relative)
                pan = float(np.clip(azimuth / 60.0, -1.0, 1.0))
                delay_samples = int(round((distance / SOUND_SPEED_MPS) * SAMPLE_RATE))
                distance_gain = (0.52 / max(0.52, distance)) ** 0.92
                vertical_shadow = 1.0 - min(0.18, abs(vertical) * 0.10)
                render_gain = speaker["weight"] * distance_gain * vertical_shadow
                self.song_speakers.append(
                    {
                        "name": speaker["name"],
                        "channel": speaker["channel"],
                        "gain": render_gain,
                        "crossfeed": float(speaker["crossfeed"]),
                        "band": speaker.get("band", "full"),
                        "pan": pan,
                        "delay": max(0, delay_samples),
                    }
                )

            self.song_direct_gain = 1.0
            self.song_cabin_gain = 0.0
            self.song_fill_gain = 0.040 + (space_ratio * 0.030) + (listener_depth * 0.028)
            self.song_duck_strength = 0.04 + (presence_ratio * 0.05)
            self.song_motion_follow = 0.0
            self.song_soft_drive = 0.016 + (space_ratio * 0.004)
            body_cutoff_hz = 1650.0 + (presence_ratio * 850.0) - (listener_depth * 260.0)
            self.song_body_alpha = float(np.clip(1.0 - math.exp((-2.0 * math.pi * body_cutoff_hz) / SAMPLE_RATE), 0.02, 0.60))
            self.song_stage_level = float(np.clip(0.34 + (presence_ratio * 0.05) - (listener_depth * 0.04), 0.28, 0.42))
            tone_ratio = np.clip(self.speaker / 100.0, 0.0, 1.0)
            tone_body_hz = 1180.0 + (presence_ratio * 1100.0) + ((1.0 - tone_ratio) * 320.0)
            tone_air_hz = 3000.0 + (tone_ratio * 1900.0) - (space_ratio * 650.0)
            fill_hz = 420.0 + (space_ratio * 260.0) + (listener_depth * 180.0)
            self.song_tone_low_alpha = float(np.clip(1.0 - math.exp((-2.0 * math.pi * tone_body_hz) / SAMPLE_RATE), 0.02, 0.45))
            self.song_tone_air_alpha = float(np.clip(1.0 - math.exp((-2.0 * math.pi * tone_air_hz) / SAMPLE_RATE), 0.02, 0.30))
            self.song_fill_alpha = float(np.clip(1.0 - math.exp((-2.0 * math.pi * fill_hz) / SAMPLE_RATE), 0.01, 0.25))
            self.song_tone_hp_coeff = float(np.clip(0.986 + ((1.0 - tone_ratio) * 0.006) + (space_ratio * 0.002), 0.974, 0.996))
            self.song_core_gain = 0.46 - (space_ratio * 0.04)
            self.song_body_gain = 0.24 + ((1.0 - tone_ratio) * 0.08) + (listener_depth * 0.05)
            self.song_presence_gain = 0.04 + (presence_ratio * 0.04) - (listener_depth * 0.015)
            self.song_shell_gain = 0.110 + (space_ratio * 0.055) + (listener_depth * 0.040)
            self.song_dash_gain = 0.075 + (presence_ratio * 0.040)
            self.song_cross_gain = 0.040 + (listener_depth * 0.045) + (space_ratio * 0.020)
            self.song_dash_delay = max(1, int(round((0.0018 + ((1.0 - tight_ratio) * 0.0010)) * SAMPLE_RATE)))
            self.song_glass_delay = max(1, int(round((0.0038 + (space_ratio * 0.0014) + (listener_depth * 0.0012)) * SAMPLE_RATE)))
            self.song_cross_delay = max(1, int(round((0.0065 + (space_ratio * 0.0015) + (listener_depth * 0.0020)) * SAMPLE_RATE)))
            hrtf_ratio = np.clip(self.hrtf_amount / 100.0, 0.0, 1.0)
            self.hrtf_azimuth, self.hrtf_elevation, self.hrtf_scene_blend = _scene_hrtf_settings(scene, seat_pan, hrtf_ratio)
            self.output_balance = ((self.balance - 50.0) / 50.0) * 0.32
            self.noise_bed_name = scene["noise"]
            self.noise_loop = load_noise_loop(self.noise_bed_name)
            self.traffic_bed_name = scene.get(
                "traffic_bed",
                "crossroad" if scene.get("noise") == "crossroad" else scene.get("noise", "crossroad"),
            )
            self.traffic_loop = load_noise_loop(self.traffic_bed_name)
            if self.traffic_loop is None:
                self.traffic_bed_name = "crossroad"
                self.traffic_loop = load_noise_loop("crossroad")
            self.window_bed = shape_real_bed(
                scene.get("window_bed", "wind"),
                lowpass_hz=scene.get("window_lowpass", 7600.0),
                highpass_hz=scene.get("window_highpass", 140.0),
                width=scene.get("window_width", 0.92),
                target_rms=0.16,
            )
            self.air_bed = shape_real_bed(
                scene.get("air_bed", "wind"),
                lowpass_hz=scene.get("air_lowpass", 4200.0),
                highpass_hz=scene.get("air_highpass", 180.0),
                width=scene.get("air_width", 0.20),
                target_rms=0.14,
            )
            self.air_detail_bed = shape_real_bed(
                scene.get("air_detail_bed", "const"),
                lowpass_hz=scene.get("air_detail_lowpass", 1400.0),
                highpass_hz=scene.get("air_detail_highpass", 35.0),
                width=scene.get("air_detail_width", 0.04),
                target_rms=0.12,
            )
            self.rain_bed = shape_real_bed(
                scene.get("rain_bed", "rain"),
                lowpass_hz=scene.get("rain_lowpass", 7600.0),
                highpass_hz=scene.get("rain_highpass", 220.0),
                width=scene.get("rain_width", 0.58),
                target_rms=0.15,
            )
            self.rain_detail_bed = shape_real_bed(
                scene.get("rain_detail_bed", "water"),
                lowpass_hz=scene.get("rain_detail_lowpass", 3600.0),
                highpass_hz=scene.get("rain_detail_highpass", 260.0),
                width=scene.get("rain_detail_width", 0.22),
                target_rms=0.14,
            )

            history_size = max(0, max(self.active_left_ir.shape[0], self.active_right_ir.shape[0]) - 1)
            if reset_history or self.ir_history.shape[0] != history_size:
                self.ir_history = np.zeros(history_size, dtype=np.float32)
                self.left_ir_state = np.zeros(max(0, self.active_left_ir.shape[0] - 1), dtype=np.float32)
                self.right_ir_state = np.zeros(max(0, self.active_right_ir.shape[0] - 1), dtype=np.float32)
                self.song_ir_history = np.zeros(history_size, dtype=np.float32)
                self.song_left_ir_state = np.zeros(max(0, self.active_left_ir.shape[0] - 1), dtype=np.float32)
                self.song_right_ir_state = np.zeros(max(0, self.active_right_ir.shape[0] - 1), dtype=np.float32)
                self.song_aux_histories = {}
                self.song_body_state.fill(0.0)
                self.song_tone_low_state.fill(0.0)
                self.song_tone_air_state.fill(0.0)
                self.song_tone_hp_prev_in.fill(0.0)
                self.song_tone_hp_prev_out.fill(0.0)
                self.song_fill_state = 0.0
                self.hp_state.fill(0.0)
                self.hp_prev_in.fill(0.0)
                self.hp_prev_out.fill(0.0)
                self.low_state.fill(0.0)
                self.air_state.fill(0.0)
                self.box_state.fill(0.0)
                self.window_low_state.fill(0.0)
                self.window_high_state.fill(0.0)
                self.rain_low_state.fill(0.0)
                self.rain_high_state.fill(0.0)
                self.air_low_state.fill(0.0)
                self.air_high_state.fill(0.0)
                self.air_swirl_phase = math.pi * 0.18
                self.engine_body_state = 0.0
                self.engine_growl_state = 0.0
                self.engine_wobble_phase = 0.0
                self.noise_duck = 1.0
                self.noise_pos = 0
                self.engine_pos = 0
                self.window_pos = 0
                self.air_pos = 0
                self.air_detail_pos = 0
                self.rain_pos = 0
                self.rain_detail_pos = 0
                self.traffic_pos = 0
                self.traffic_event_remaining = 0
                self.traffic_event_duration = 0
                self.traffic_event_pan_start = 0.0
                self.traffic_event_pan_end = 0.0
                self.traffic_event_gain = 0.0
                self.traffic_low_state = 0.0
                self.traffic_high_state = 0.0
                self.motion_phase = 0.0
                self.motion_secondary_phase = math.pi * 0.37

    def _convolve_block(self, source_mono):
        source_mono = np.asarray(source_mono, dtype=np.float32)
        block_len = source_mono.shape[0]
        max_history_len = self.ir_history.shape[0]

        if lfilter is not None:
            if not hasattr(self, "_a_one"):
                self._a_one = np.array([1.0], dtype=np.float32)
            def convolve_channel(ir, state):
                state_len = max(0, ir.shape[0] - 1)
                if state_len <= 0:
                    return (source_mono * float(ir[0])).astype(np.float32, copy=False), np.zeros(0, dtype=np.float32)
                if state.shape[0] != state_len:
                    state = np.zeros(state_len, dtype=np.float32)
                channel, new_state = lfilter(ir, self._a_one, source_mono, zi=state)
                return channel.astype(np.float32, copy=False), new_state.astype(np.float32, copy=False)

            left, self.left_ir_state = convolve_channel(self.active_left_ir, self.left_ir_state)
            right, self.right_ir_state = convolve_channel(self.active_right_ir, self.right_ir_state)

            if max_history_len > 0:
                if block_len >= max_history_len:
                    self.ir_history = source_mono[-max_history_len:].copy()
                else:
                    keep = max_history_len - block_len
                    self.ir_history = np.concatenate((self.ir_history[-keep:], source_mono)).astype(np.float32, copy=False)

            return np.column_stack((left, right)).astype(np.float32, copy=False)

        def convolve_channel(ir):
            channel_history_len = max(0, ir.shape[0] - 1)
            if channel_history_len > 0:
                history = self.ir_history[-channel_history_len:]
                window = np.empty(channel_history_len + block_len, dtype=np.float32)
                window[:channel_history_len] = history
                window[channel_history_len:] = source_mono
            else:
                window = source_mono

            channel = np.convolve(window, ir, mode="valid").astype(np.float32, copy=False)
            if channel.shape[0] != block_len:
                channel = channel[-block_len:]
            return channel

        left = convolve_channel(self.active_left_ir)
        right = convolve_channel(self.active_right_ir)

        if max_history_len > 0:
            if block_len >= max_history_len:
                self.ir_history = source_mono[-max_history_len:].copy()
            else:
                keep = max_history_len - block_len
                self.ir_history = np.concatenate((self.ir_history[-keep:], source_mono)).astype(np.float32, copy=False)

        return np.column_stack((left, right)).astype(np.float32, copy=False)

    def _convolve_song_block(self, source_mono):
        source_mono = np.asarray(source_mono, dtype=np.float32)
        block_len = source_mono.shape[0]
        max_history_len = self.song_ir_history.shape[0]

        if lfilter is not None:
            if not hasattr(self, "_a_one"):
                self._a_one = np.array([1.0], dtype=np.float32)
            def convolve_channel(ir, state):
                state_len = max(0, ir.shape[0] - 1)
                if state_len <= 0:
                    return (source_mono * float(ir[0])).astype(np.float32, copy=False), np.zeros(0, dtype=np.float32)
                if state.shape[0] != state_len:
                    state = np.zeros(state_len, dtype=np.float32)
                channel, new_state = lfilter(ir, self._a_one, source_mono, zi=state)
                return channel.astype(np.float32, copy=False), new_state.astype(np.float32, copy=False)

            left, self.song_left_ir_state = convolve_channel(self.active_left_ir, self.song_left_ir_state)
            right, self.song_right_ir_state = convolve_channel(self.active_right_ir, self.song_right_ir_state)

            if max_history_len > 0:
                if block_len >= max_history_len:
                    self.song_ir_history = source_mono[-max_history_len:].copy()
                else:
                    keep = max_history_len - block_len
                    self.song_ir_history = np.concatenate((self.song_ir_history[-keep:], source_mono)).astype(np.float32, copy=False)

            return np.column_stack((left, right)).astype(np.float32, copy=False)

        def convolve_channel(ir):
            channel_history_len = max(0, ir.shape[0] - 1)
            if channel_history_len > 0:
                history = self.song_ir_history[-channel_history_len:]
                window = np.empty(channel_history_len + block_len, dtype=np.float32)
                window[:channel_history_len] = history
                window[channel_history_len:] = source_mono
            else:
                window = source_mono

            channel = np.convolve(window, ir, mode="valid").astype(np.float32, copy=False)
            if channel.shape[0] != block_len:
                channel = channel[-block_len:]
            return channel

        left = convolve_channel(self.active_left_ir)
        right = convolve_channel(self.active_right_ir)

        if max_history_len > 0:
            if block_len >= max_history_len:
                self.song_ir_history = source_mono[-max_history_len:].copy()
            else:
                keep = max_history_len - block_len
                self.song_ir_history = np.concatenate((self.song_ir_history[-keep:], source_mono)).astype(np.float32, copy=False)

        return np.column_stack((left, right)).astype(np.float32, copy=False)

    def _song_segment(self, length):
        if self.song_audio is None or self.song_audio.size == 0 or length <= 0:
            return np.zeros((max(0, length), 2), dtype=np.float32)

        total = int(self.song_audio.shape[0])
        start = int(self.song_pos)
        if self.song_loop:
            block = self._loop_segment(start, length, self.song_audio)
            self.song_pos = (start + length) % total
            return block

        if start >= total:
            return np.zeros((length, 2), dtype=np.float32)

        end = min(total, start + length)
        block = np.zeros((length, 2), dtype=np.float32)
        block[: end - start] = self.song_audio[start:end]
        self.song_pos = end
        return block

    def _split_song_program(self, signal, channel_index):
        program = np.asarray(signal, dtype=np.float32)
        alpha = float(np.clip(self.song_body_alpha, 0.01, 0.95))

        if lfilter is not None:
            body, state = lfilter(
                np.array([alpha], dtype=np.float32),
                np.array([1.0, -(1.0 - alpha)], dtype=np.float32),
                program,
                zi=np.array([self.song_body_state[channel_index]], dtype=np.float32),
            )
            self.song_body_state[channel_index] = float(state[0])
            body = body.astype(np.float32, copy=False)
        else:
            body = np.empty_like(program, dtype=np.float32)
            state = float(self.song_body_state[channel_index])
            for index, sample in enumerate(program):
                state += alpha * (float(sample) - state)
                body[index] = state
            self.song_body_state[channel_index] = state

        presence = (program - body).astype(np.float32, copy=False)
        return body, presence

    def _delay_song_speaker(self, speaker_name, signal, delay_samples):
        source = np.asarray(signal, dtype=np.float32)
        if delay_samples <= 0:
            return source.astype(np.float32, copy=False)

        history = self.song_speaker_histories.get(speaker_name)
        if history is None or history.shape[0] != delay_samples:
            history = np.zeros(delay_samples, dtype=np.float32)

        window = np.concatenate((history, source)).astype(np.float32, copy=False)
        delayed = window[: source.shape[0]].astype(np.float32, copy=False)
        self.song_speaker_histories[speaker_name] = window[-delay_samples:].astype(np.float32, copy=False)
        return delayed

    def _delay_song_aux(self, name, signal, delay_samples):
        source = np.asarray(signal, dtype=np.float32)
        if delay_samples <= 0:
            return source.astype(np.float32, copy=False)

        history = self.song_aux_histories.get(name)
        if history is None or history.shape[0] != delay_samples:
            history = np.zeros(delay_samples, dtype=np.float32)

        window = np.concatenate((history, source)).astype(np.float32, copy=False)
        delayed = window[: source.shape[0]].astype(np.float32, copy=False)
        self.song_aux_histories[name] = window[-delay_samples:].astype(np.float32, copy=False)
        return delayed

    def _song_stage_chain(self, stereo_data):
        stage = np.asarray(stereo_data, dtype=np.float32)
        output = np.empty_like(stage, dtype=np.float32)
        hp_coeff = float(np.clip(self.song_tone_hp_coeff, 0.90, 0.999))
        low_alpha = float(np.clip(self.song_tone_low_alpha, 0.01, 0.60))
        air_alpha = float(np.clip(self.song_tone_air_alpha, 0.01, 0.40))

        for channel in range(2):
            prev_in = float(self.song_tone_hp_prev_in[channel])
            prev_out = float(self.song_tone_hp_prev_out[channel])
            low_state = float(self.song_tone_low_state[channel])
            air_state = float(self.song_tone_air_state[channel])

            for index, sample in enumerate(stage[:, channel]):
                hp = float(sample) - prev_in + (hp_coeff * prev_out)
                prev_in = float(sample)
                prev_out = hp
                low_state += low_alpha * (hp - low_state)
                air_state += air_alpha * (hp - air_state)
                bright = hp - air_state
                output[index, channel] = (
                    (hp * self.song_core_gain)
                    + (low_state * self.song_body_gain)
                    + (bright * self.song_presence_gain)
                )

            self.song_tone_hp_prev_in[channel] = prev_in
            self.song_tone_hp_prev_out[channel] = prev_out
            self.song_tone_low_state[channel] = low_state
            self.song_tone_air_state[channel] = air_state

        return output

    def _song_cabin_fill(self, stereo_data):
        center = np.mean(np.asarray(stereo_data, dtype=np.float32), axis=1, dtype=np.float32)
        alpha = float(np.clip(self.song_fill_alpha, 0.01, 0.50))

        if lfilter is not None:
            filled, state = lfilter(
                np.array([alpha], dtype=np.float32),
                np.array([1.0, -(1.0 - alpha)], dtype=np.float32),
                center,
                zi=np.array([self.song_fill_state], dtype=np.float32),
            )
            self.song_fill_state = float(state[0])
            mono_fill = filled.astype(np.float32, copy=False)
        else:
            mono_fill = np.empty_like(center, dtype=np.float32)
            state = float(self.song_fill_state)
            for index, sample in enumerate(center):
                state += alpha * (float(sample) - state)
                mono_fill[index] = state
            self.song_fill_state = state

        return np.column_stack((mono_fill, mono_fill)).astype(np.float32, copy=False) * self.song_fill_gain

    def _song_cabin_shell(self, stereo_data):
        stage = np.asarray(stereo_data, dtype=np.float32)
        left = stage[:, 0]
        right = stage[:, 1]
        center = np.mean(stage, axis=1, dtype=np.float32)

        glass_left = self._delay_song_aux("glass_left", left, self.song_glass_delay)
        glass_right = self._delay_song_aux("glass_right", right, self.song_glass_delay)
        dash_center = self._delay_song_aux("dash_center", center, self.song_dash_delay)
        cross_left = self._delay_song_aux("cross_left", right, self.song_cross_delay)
        cross_right = self._delay_song_aux("cross_right", left, self.song_cross_delay)

        shell = np.column_stack(
            (
                (glass_left * self.song_shell_gain) + (dash_center * self.song_dash_gain) + (cross_left * self.song_cross_gain),
                (glass_right * self.song_shell_gain) + (dash_center * self.song_dash_gain) + (cross_right * self.song_cross_gain),
            )
        ).astype(np.float32, copy=False)
        return shell

    def _music_block(self, length, voice_level, motion_azimuth=0.0, motion_elevation=0.0):
        if (
            not self.song_enabled
            or self.song_audio is None
            or self.song_audio.size == 0
            or self.song_level <= 0
            or not self.song_speakers
        ):
            return np.zeros((length, 2), dtype=np.float32)

        song = self._song_segment(length)
        if song.size == 0:
            return np.zeros((length, 2), dtype=np.float32)

        song = song.astype(np.float32, copy=False)
        level = np.clip(self.song_level / 100.0, 0.0, 1.0) * self.song_stage_level
        duck = max(0.76, 1.0 - (voice_level * self.song_duck_strength))
        left_input = (song[:, 0] * 0.92) + (song[:, 1] * 0.08)
        right_input = (song[:, 1] * 0.92) + (song[:, 0] * 0.08)
        left_body, left_presence = self._split_song_program(left_input, 0)
        right_body, right_presence = self._split_song_program(right_input, 1)
        direct = np.zeros((length, 2), dtype=np.float32)

        for speaker in self.song_speakers:
            if speaker["channel"] == "left":
                main_body, main_presence = left_body, left_presence
                side_body, side_presence = right_body, right_presence
            else:
                main_body, main_presence = right_body, right_presence
                side_body, side_presence = left_body, left_presence

            if speaker["band"] == "body":
                main_source = main_body
                side_source = side_body
            elif speaker["band"] == "presence":
                main_source = main_presence
                side_source = side_presence
            else:
                main_source = left_input if speaker["channel"] == "left" else right_input
                side_source = right_input if speaker["channel"] == "left" else left_input

            speaker_source = (main_source * (1.0 - speaker["crossfeed"])) + (side_source * speaker["crossfeed"])
            delayed = self._delay_song_speaker(speaker["name"], speaker_source, speaker["delay"])
            rendered = pan_mono_block(delayed, speaker["pan"] - ((motion_azimuth / 120.0) * self.song_motion_follow))
            direct += rendered * speaker["gain"]

        direct = self._song_stage_chain(direct)
        shell = self._song_cabin_shell(direct)
        fill = self._song_cabin_fill(direct)
        music = (direct * self.song_direct_gain) + shell + fill
        music = music * level * duck
        drive = 1.0 + (self.song_soft_drive * 18.0)
        return (np.tanh(music * drive) / drive).astype(np.float32, copy=False)

    def _speaker_chain(self, stereo_data):
        tone = self.speaker / 100.0
        hp_coeff = 0.960 + ((1.0 - tone) * 0.010)
        low_alpha = 0.11 - (tone * 0.018)
        air_alpha = 0.028 - (tone * 0.006)
        box_alpha = 0.040 + ((1.0 - tone) * 0.014)
        body_gain = 0.54 - (tone * 0.08)
        air_gain = 0.22 + (tone * 0.18)

        if lfilter is not None:
            hp_b = np.array([1.0, -1.0], dtype=np.float32)
            hp_a = np.array([1.0, -hp_coeff], dtype=np.float32)
            low_b = np.array([low_alpha], dtype=np.float32)
            low_a = np.array([1.0, -(1.0 - low_alpha)], dtype=np.float32)
            air_b = np.array([air_alpha], dtype=np.float32)
            air_a = np.array([1.0, -(1.0 - air_alpha)], dtype=np.float32)
            box_b = np.array([box_alpha], dtype=np.float32)
            box_a = np.array([1.0, -(1.0 - box_alpha)], dtype=np.float32)
            output = np.empty_like(stereo_data, dtype=np.float32)

            for channel in range(2):
                hp, hp_state = lfilter(hp_b, hp_a, stereo_data[:, channel], zi=np.array([self.hp_state[channel]], dtype=np.float32))
                low, low_state = lfilter(low_b, low_a, hp, zi=np.array([self.low_state[channel]], dtype=np.float32))
                air, air_state = lfilter(air_b, air_a, hp, zi=np.array([self.air_state[channel]], dtype=np.float32))
                box, box_state = lfilter(box_b, box_a, hp, zi=np.array([self.box_state[channel]], dtype=np.float32))
                self.hp_state[channel] = hp_state[0]
                self.low_state[channel] = low_state[0]
                self.air_state[channel] = air_state[0]
                self.box_state[channel] = box_state[0]
                bright = hp - air
                output[:, channel] = ((low * body_gain) + (bright * air_gain) - (box * self.box_cut)).astype(np.float32, copy=False)

            return output

        output = np.empty_like(stereo_data, dtype=np.float32)
        for channel in range(2):
            prev_in = float(self.hp_prev_in[channel])
            prev_out = float(self.hp_prev_out[channel])
            low_state = float(self.low_state[channel])
            air_state = float(self.air_state[channel])
            box_state = float(self.box_state[channel])

            for index, sample in enumerate(stereo_data[:, channel]):
                hp = sample - prev_in + (hp_coeff * prev_out)
                prev_in = sample
                prev_out = hp

                low_state += low_alpha * (hp - low_state)
                air_state += air_alpha * (hp - air_state)
                box_state += box_alpha * (hp - box_state)
                bright = hp - air_state
                output[index, channel] = (low_state * body_gain) + (bright * air_gain) - (box_state * self.box_cut)

            self.hp_prev_in[channel] = prev_in
            self.hp_prev_out[channel] = prev_out
            self.low_state[channel] = low_state
            self.air_state[channel] = air_state
            self.box_state[channel] = box_state

        return output

    def _loop_segment(self, base_offset, length, audio_data=None):
        loop = self.noise_loop if audio_data is None else audio_data
        if loop is None or loop.size == 0:
            return np.zeros((length, 2), dtype=np.float32)

        loop_len = loop.shape[0]
        raw_indices = base_offset + np.arange(length)
        indices = raw_indices % loop_len
        block = loop[indices].astype(np.float32, copy=True)

        fade_len = min(2048, loop_len // 8)
        if fade_len > 0:
            wrap_mask = indices >= (loop_len - fade_len)
            if np.any(wrap_mask):
                fade = (indices[wrap_mask] - (loop_len - fade_len)).astype(np.float32) / float(fade_len)
                block[wrap_mask] = (block[wrap_mask] * (1.0 - fade[:, None])) + (loop[: fade.size] * fade[:, None])
        return block

    def _loop_segment_resampled(self, start_pos, length, speed_ratio, audio_data=None):
        loop = self.noise_loop if audio_data is None else audio_data
        if loop is None or loop.size == 0:
            return np.zeros((length, 2), dtype=np.float32), start_pos

        loop_len = loop.shape[0]
        if not hasattr(self, "_arange_cache"):
            self._arange_cache = {}
        if length not in self._arange_cache:
            self._arange_cache[length] = np.arange(length, dtype=np.float32)

        steps = self._arange_cache[length] * speed_ratio
        raw_indices = start_pos + steps
        indices_f = raw_indices % loop_len
        indices_i = indices_f.astype(np.int32)
        frac = (indices_f - indices_i)[:, None]
        indices_next = (indices_i + 1) % loop_len

        a = loop[indices_i]
        b = loop[indices_next]
        block = a + (b - a) * frac
        block = block.astype(np.float32, copy=True)

        fade_len = min(2048, loop_len // 8)
        if fade_len > 0:
            end_limit = loop_len - fade_len
            if indices_i[-1] >= end_limit or indices_i[0] >= end_limit:
                wrap_mask = indices_i >= end_limit
                fade = (indices_f[wrap_mask] - end_limit).astype(np.float32) / float(fade_len)
                block[wrap_mask] = (block[wrap_mask] * (1.0 - fade[:, None])) + (loop[: fade.size] * fade[:, None])

        next_pos = (start_pos + length * speed_ratio) % loop_len
        return block, next_pos

    def _noise_block(self, length, road_amount, voice_level):
        if self.noise_loop is None or self.noise_loop.size == 0 or road_amount <= 0.0:
            return np.zeros((length, 2), dtype=np.float32)

        road_ratio = getattr(self, "road_ratio", 1.0)
        block, self.noise_pos = self._loop_segment_resampled(self.noise_pos, length, road_ratio)

        base_gain = self.noise_gain * (0.34 + (road_amount * 0.96))
        target_duck = max(0.50, 1.0 - (voice_level * (2.4 - (road_amount * 0.3))))
        self.noise_duck += 0.10 * (target_duck - self.noise_duck)

        if not hasattr(self, "_noise_bias_arr"):
            self._noise_bias_arr = np.array([self.left_noise_bias, self.right_noise_bias], dtype=np.float32)
        stereo_noise = block * self._noise_bias_arr
        return stereo_noise * base_gain * self.noise_duck

    def _engine_block(self, length, road_amount, voice_level):
        if self.noise_loop is None or self.noise_loop.size == 0 or self.engine_gain <= 0.0:
            return np.zeros((length, 2), dtype=np.float32)

        engine_ratio = getattr(self, "engine_ratio", 1.0)
        offset = 2111 + int((0.18 + road_amount) * 960.0)
        block, self.engine_pos = self._loop_segment_resampled(self.engine_pos + offset, length, engine_ratio)
        mono = np.mean(block, axis=1, dtype=np.float32)

        if lfilter is not None:
            body_b = np.array([0.040], dtype=np.float32)
            body_a = np.array([1.0, -0.960], dtype=np.float32)
            growl_b = np.array([0.120], dtype=np.float32)
            growl_a = np.array([1.0, -0.880], dtype=np.float32)
            body, body_state = lfilter(body_b, body_a, mono, zi=np.array([self.engine_body_state], dtype=np.float32))
            growl, growl_state = lfilter(growl_b, growl_a, mono, zi=np.array([self.engine_growl_state], dtype=np.float32))
            self.engine_body_state = float(body_state[0])
            self.engine_growl_state = float(growl_state[0])
        else:
            body = np.empty(length, dtype=np.float32)
            growl = np.empty(length, dtype=np.float32)
            body_state = float(self.engine_body_state)
            growl_state = float(self.engine_growl_state)
            for index, sample in enumerate(mono):
                body_state += 0.040 * (sample - body_state)
                growl_state += 0.120 * (sample - growl_state)
                body[index] = body_state
                growl[index] = growl_state
            self.engine_body_state = body_state
            self.engine_growl_state = growl_state

        texture = np.tanh((growl - (body * 0.92)) * 2.8)
        harmonic = np.tanh(growl * 3.0) * 0.22
        rumble = ((body * 0.74) + (texture * 0.18) + harmonic).astype(np.float32, copy=False)

        wobble_rate = 1.3 + (road_amount * 2.2)
        phase_step = (wobble_rate * (2.0 * math.pi)) / SAMPLE_RATE
        phases = self.engine_wobble_phase + (np.arange(length, dtype=np.float32) * phase_step)
        wobble = 0.92 + (0.08 * np.sin(phases))
        self.engine_wobble_phase = float((phases[-1] + phase_step) % (2.0 * math.pi))
        rumble *= wobble.astype(np.float32, copy=False)

        duck = max(0.64, 1.0 - (voice_level * (1.2 - (road_amount * 0.25))))
        engine_side = self.engine_side
        stereo = np.column_stack(
            (
                rumble * (1.0 + max(0.0, -engine_side) * 0.38),
                rumble * (1.0 + max(0.0, engine_side) * 0.38),
            )
        )
        return stereo * self.engine_gain * duck

    def _window_block(self, length, road_amount):
        if self.window_gain <= 0.0 or self.window_bed is None or self.window_bed.size == 0:
            return np.zeros((length, 2), dtype=np.float32)

        road_ratio = getattr(self, "road_ratio", 1.0)
        wind_ratio = max(0.3, road_ratio * 0.9)
        block, self.window_pos = self._loop_segment_resampled(self.window_pos, length, wind_ratio, self.window_bed)

        side = np.array(
            [
                1.0 + max(0.0, -self.seat_pan) * 0.55 - max(0.0, self.seat_pan) * 0.20,
                1.0 + max(0.0, self.seat_pan) * 0.55 - max(0.0, -self.seat_pan) * 0.20,
            ],
            dtype=np.float32,
        )
        center = np.mean(block, axis=1, keepdims=True)
        side_image = block - center
        output = center + (side_image * (0.42 + (road_amount * 0.36) + (self.window_gain * 20.0)))
        gain = self.window_gain * (0.16 + (road_amount * 0.42))
        return output * gain * side

    def _rain_block(self, length, road_amount):
        if self.rain_gain <= 0.0 or self.rain_bed is None or self.rain_bed.size == 0:
            return np.zeros((length, 2), dtype=np.float32)

        base = self._loop_segment(self.rain_pos, length, self.rain_bed)
        offset = self._loop_segment(self.rain_pos + 733, length, self.rain_bed)
        self.rain_pos = (self.rain_pos + length) % self.rain_bed.shape[0]
        output = (base * 0.78) + (offset[:, ::-1] * 0.22)

        if self.rain_detail_bed is not None and self.rain_detail_bed.size > 0:
            detail = self._loop_segment(self.rain_detail_pos + 317, length, self.rain_detail_bed)
            self.rain_detail_pos = (self.rain_detail_pos + length) % self.rain_detail_bed.shape[0]
            output += detail * 0.34

        roof_side = np.array(
            [
                1.04 + max(0.0, -self.seat_pan) * 0.10,
                1.04 + max(0.0, self.seat_pan) * 0.10,
            ],
            dtype=np.float32,
        )
        gain = self.rain_gain * (0.18 + (road_amount * 0.06) + (self.window_gain * 8.0))
        return output * gain * roof_side

    def _motion_offsets(self, length, road_amount):
        if self.motion_depth <= 0.0:
            return 0.0, 0.0, 0.0, 1.0, 0.0

        primary_rate = self.motion_rate * (0.55 + (road_amount * 0.95))
        secondary_rate = primary_rate * 1.73
        primary_step = (primary_rate * (2.0 * math.pi)) / SAMPLE_RATE
        secondary_step = (secondary_rate * (2.0 * math.pi)) / SAMPLE_RATE

        primary_center = self.motion_phase + (primary_step * (length * 0.5))
        secondary_center = self.motion_secondary_phase + (secondary_step * (length * 0.5))
        sway = (math.sin(primary_center) * 0.72) + (math.sin(secondary_center) * 0.28)
        roll = (math.sin((primary_center * 0.61) + 0.7) * 0.60) + (math.sin((secondary_center * 0.47) + 1.1) * 0.40)
        bump = max(0.0, math.sin((primary_center * 0.43) + 0.5)) ** 3

        self.motion_phase = float((self.motion_phase + (primary_step * length)) % (2.0 * math.pi))
        self.motion_secondary_phase = float((self.motion_secondary_phase + (secondary_step * length)) % (2.0 * math.pi))

        azimuth_offset = sway * (2.5 + (road_amount * 4.8)) * self.motion_depth
        elevation_offset = roll * (0.8 + (road_amount * 1.8)) * self.motion_depth
        seat_offset = sway * self.motion_pan_depth
        width_scale = 1.0 + (abs(roll) * self.motion_width) + (bump * self.motion_width * 0.8)
        presence_push = bump * (0.02 + (self.motion_depth * 0.04))
        return azimuth_offset, elevation_offset, seat_offset, width_scale, presence_push

    def _air_block(self, length, road_amount, voice_level):
        if self.air_gain <= 0.0 or self.air_bed is None or self.air_bed.size == 0:
            return np.zeros((length, 2), dtype=np.float32)

        vent = self._loop_segment(self.air_pos, length, self.air_bed)
        offset_vent = self._loop_segment(self.air_pos + 701, length, self.air_bed)
        self.air_pos = (self.air_pos + length) % self.air_bed.shape[0]
        output = (vent * 0.78) + (offset_vent[:, ::-1] * 0.22)

        detail = np.zeros((length, 2), dtype=np.float32)
        if self.air_detail_bed is not None and self.air_detail_bed.size > 0:
            detail = self._loop_segment(self.air_detail_pos + 173, length, self.air_detail_bed)
            self.air_detail_pos = (self.air_detail_pos + length) % self.air_detail_bed.shape[0]
            detail_center = np.mean(detail, axis=1, keepdims=True)
            detail = detail_center + ((detail - detail_center) * 0.04)

        swirl_rate = 0.18 + (road_amount * 0.24)
        swirl_step = (swirl_rate * (2.0 * math.pi)) / SAMPLE_RATE
        swirl_phases = self.air_swirl_phase + (np.arange(length, dtype=np.float32) * swirl_step)
        swirl = 0.82 + (0.18 * np.sin(swirl_phases))
        self.air_swirl_phase = float((swirl_phases[-1] + swirl_step) % (2.0 * math.pi))

        side = np.array(
            [
                1.0 + max(0.0, -self.air_side) * 0.30 - max(0.0, self.air_side) * 0.12,
                1.0 + max(0.0, self.air_side) * 0.30 - max(0.0, -self.air_side) * 0.12,
            ],
            dtype=np.float32,
        )
        duck = max(0.74, 1.0 - (voice_level * 0.60))
        gain = self.air_gain * (0.16 + (road_amount * 0.04))
        return ((output * swirl[:, None]) + (detail * 0.42)) * gain * duck * side

    def _traffic_block(self, length, road_amount, voice_level):
        if self.traffic_gain <= 0.0 or self.traffic_loop is None or self.traffic_loop.size == 0:
            return np.zeros((length, 2), dtype=np.float32)

        output = np.zeros((length, 2), dtype=np.float32)
        base_block = self._loop_segment(self.traffic_pos + 377, length, self.traffic_loop)
        offset_block = self._loop_segment(self.traffic_pos + 2111, length, self.traffic_loop)
        self.traffic_pos = (self.traffic_pos + length) % self.traffic_loop.shape[0]

        duck = max(0.72, 1.0 - (voice_level * (0.85 - (road_amount * 0.12))))
        distant = (base_block * 0.64) + (offset_block * 0.36)
        distant_center = np.mean(distant, axis=1, keepdims=True)
        distant_side = distant - distant_center
        distant = distant_center + (distant_side * (0.22 + (self.width_gain * 0.60)))
        side_push = self.traffic_side_bias * (0.10 + (self.window_gain * 8.0))
        if abs(side_push) > 1e-4:
            distant[:, 0] *= 1.0 + max(0.0, -side_push) * 0.30 - max(0.0, side_push) * 0.12
            distant[:, 1] *= 1.0 + max(0.0, side_push) * 0.30 - max(0.0, -side_push) * 0.12
        output += distant * self.traffic_gain * (0.06 + (road_amount * 0.10)) * duck

        processed = 0
        while processed < length:
            if self.traffic_event_remaining <= 0:
                chance = min(0.24, (length / SAMPLE_RATE) * self.traffic_density * (0.25 + (road_amount * 0.85) + (self.window_gain * 14.0)))
                if self.rng.random() >= chance:
                    break
                duration = max(480, int(self.rng.uniform(0.24, 0.62) * SAMPLE_RATE))
                direction = -1.0 if self.rng.random() < 0.55 else 1.0
                lead = 0.72 + self.rng.uniform(0.08, 0.22)
                tail = 0.10 + self.rng.uniform(0.10, 0.28)
                side_bias = self.traffic_side_bias * 0.55
                self.traffic_event_duration = duration
                self.traffic_event_remaining = duration
                self.traffic_event_pan_start = float(np.clip((direction * lead) + side_bias, -1.0, 1.0))
                self.traffic_event_pan_end = float(np.clip((-direction * tail) + (side_bias * 0.20), -1.0, 1.0))
                self.traffic_event_gain = self.traffic_gain * self.rng.uniform(0.80, 1.35) * (1.0 + (self.window_gain * 18.0))

            segment_len = min(length - processed, self.traffic_event_remaining)
            start_progress = (self.traffic_event_duration - self.traffic_event_remaining) / max(1.0, float(self.traffic_event_duration))
            end_progress = (self.traffic_event_duration - self.traffic_event_remaining + segment_len) / max(1.0, float(self.traffic_event_duration))
            phase = np.linspace(start_progress, end_progress, segment_len, endpoint=False, dtype=np.float32)
            source_block = self._loop_segment(self.traffic_pos + 5000 + int(self.traffic_event_gain * 3000.0), segment_len, self.traffic_loop)
            mono = np.mean(source_block, axis=1, dtype=np.float32)

            if lfilter is not None:
                low_b = np.array([0.045], dtype=np.float32)
                low_a = np.array([1.0, -0.955], dtype=np.float32)
                high_b = np.array([0.240], dtype=np.float32)
                high_a = np.array([1.0, -0.760], dtype=np.float32)
                low, low_state = lfilter(low_b, low_a, mono, zi=np.array([self.traffic_low_state], dtype=np.float32))
                high, high_state = lfilter(high_b, high_a, mono, zi=np.array([self.traffic_high_state], dtype=np.float32))
                self.traffic_low_state = float(low_state[0])
                self.traffic_high_state = float(high_state[0])
                whoosh = np.tanh((high - low) * 2.2).astype(np.float32, copy=False)
            else:
                low_state = float(self.traffic_low_state)
                high_state = float(self.traffic_high_state)
                whoosh = np.empty(segment_len, dtype=np.float32)
                for index, sample in enumerate(mono):
                    low_state += 0.045 * (sample - low_state)
                    high_state += 0.240 * (sample - high_state)
                    whoosh[index] = math.tanh((high_state - low_state) * 2.2)
                self.traffic_low_state = low_state
                self.traffic_high_state = high_state

            pan_curve = self.traffic_event_pan_start + ((self.traffic_event_pan_end - self.traffic_event_pan_start) * phase)
            left_weight, right_weight = constant_power_pan(pan_curve)
            envelope = np.square(np.sin(np.pi * np.clip(phase, 0.0, 1.0))).astype(np.float32, copy=False)
            near_gain = 0.40 + (np.sin(phase * math.pi).astype(np.float32, copy=False) * 0.85)
            stereo = np.column_stack((whoosh * left_weight, whoosh * right_weight)).astype(np.float32, copy=False)
            output[processed : processed + segment_len] += stereo * (self.traffic_event_gain * near_gain[:, None] * envelope[:, None] * duck)

            processed += segment_len
            self.traffic_event_remaining -= segment_len
            if self.traffic_event_remaining <= 0:
                self.traffic_event_duration = 0

        return output

    def process(self, data):
        source = normalize_audio_frames(data)
        if source.size == 0:
            return source

        dry_stereo = ensure_stereo_frames(source)
        source_mono = source if source.ndim == 1 else np.mean(dry_stereo, axis=1, dtype=np.float32)

        with self._scene_lock:
            # Simulation update
            length = source_mono.shape[0]
            dt = length / SAMPLE_RATE
            
            if not hasattr(self, "sim_speed"):
                self.sim_speed = 0.0
                self.sim_target_speed = 0.0
                self.sim_rpm = 850.0
                self.sim_gear = 1
                self.sim_timer = 0.0
                self.shift_timer = 0.0
            
            preset_lower = self.preset.lower() if hasattr(self, "preset") and self.preset else ""
            self.sim_timer += dt
            
            if "idle" in preset_lower or "jam" in preset_lower:
                if preset_lower == "taxi idle":
                    self.sim_target_speed = 0.0
                else:
                    if int(self.sim_timer / 10) % 2 == 0:
                        self.sim_target_speed = 12.0
                    else:
                        self.sim_target_speed = 2.0
            elif "highway" in preset_lower or "tunnel" in preset_lower or "cruise" in preset_lower:
                self.sim_target_speed = 100.0 + 3.0 * math.sin(self.sim_timer * 0.1)
            else:
                cycle_time = self.sim_timer % 70.0
                if cycle_time < 20.0:
                    self.sim_target_speed = 55.0
                elif cycle_time < 45.0:
                    self.sim_target_speed = 55.0 + 2.0 * math.sin(self.sim_timer * 0.5)
                elif cycle_time < 58.0:
                    self.sim_target_speed = 0.0
                else:
                    self.sim_target_speed = 0.0

            speed_diff = self.sim_target_speed - self.sim_speed
            if abs(speed_diff) > 0.1:
                accel_rate = 6.0 if speed_diff > 0 else 12.0
                self.sim_speed += np.sign(speed_diff) * min(accel_rate * dt, abs(speed_diff))
            else:
                self.sim_speed = self.sim_target_speed

            target_gear = 1
            if self.sim_speed < 1.0:
                target_gear = 0
            elif self.sim_speed < 20.0:
                target_gear = 1
            elif self.sim_speed < 40.0:
                target_gear = 2
            elif self.sim_speed < 65.0:
                target_gear = 3
            elif self.sim_speed < 90.0:
                target_gear = 4
            else:
                target_gear = 5

            if target_gear != self.sim_gear and self.sim_speed > 5.0:
                if self.shift_timer <= 0.0:
                    self.shift_timer = 0.35
                    self.sim_gear = target_gear
            
            if self.shift_timer > 0.0:
                self.shift_timer -= dt
                target_rpm = 1100.0
            else:
                if target_gear == 0:
                    target_rpm = 850.0 + 40.0 * math.sin(self.sim_timer * 2.0)
                else:
                    gear_min_speeds = [0.0, 0.0, 20.0, 40.0, 65.0, 90.0]
                    gear_min_rpms = [850.0, 1000.0, 1500.0, 1600.0, 1700.0, 1800.0]
                    gear_scales = [0.0, 120.0, 75.0, 55.0, 40.0, 30.0]
                    
                    g = self.sim_gear
                    speed_in_gear = self.sim_speed - gear_min_speeds[g]
                    target_rpm = gear_min_rpms[g] + speed_in_gear * gear_scales[g]
                    if speed_diff > 5.0:
                        target_rpm += 300.0
            
            rpm_inertia = 8.0 if self.shift_timer > 0.0 else 4.0
            self.sim_rpm += (target_rpm - self.sim_rpm) * rpm_inertia * dt
            
            self.road_ratio = max(0.1, self.sim_speed / 80.0)
            self.engine_ratio = max(0.4, self.sim_rpm / 1800.0)

            convolved = self._convolve_block(source_mono)
            speaker_filtered = self._speaker_chain(convolved)
            tone = self.speaker / 100.0
            space_ratio = self.space / 100.0
            mix = self.mix / 100.0
            road = self.road / 100.0
            hrtf_ratio = self.hrtf_amount / 100.0

            cabin_voice = (convolved * (0.44 - (tone * 0.06))) + (speaker_filtered * (0.56 + (tone * 0.10)))
            cabin_voice += convolved[:, ::-1] * self.crossfeed

            voice_level = float(np.sqrt(np.mean(cabin_voice * cabin_voice)))
            motion_azimuth, motion_elevation, motion_pan, motion_width_scale, motion_presence = self._motion_offsets(source_mono.shape[0], road)
            effective_pan = self.seat_pan + motion_pan
            road_noise = self._noise_block(source_mono.shape[0], road, voice_level)
            traffic_noise = self._traffic_block(source_mono.shape[0], road, voice_level)
            engine_noise = self._engine_block(source_mono.shape[0], road, voice_level)
            air_noise = self._air_block(source_mono.shape[0], road, voice_level)
            window_noise = self._window_block(source_mono.shape[0], road)
            rain_noise = self._rain_block(source_mono.shape[0], road)
            music_bed = self._music_block(source_mono.shape[0], voice_level, motion_azimuth, motion_elevation)
            hrtf_focus = np.zeros_like(cabin_voice, dtype=np.float32)
            if hrtf_ratio > 0.001:
                focus_source = (
                    (source_mono * (0.48 + ((self.presence / 100.0) * 0.28)))
                    + (np.mean(speaker_filtered, axis=1, dtype=np.float32) * (0.16 + (space_ratio * 0.10)))
                ).astype(np.float32, copy=False)
                hrtf_focus = self.steam_audio.process(
                    focus_source,
                    self.hrtf_azimuth + motion_azimuth,
                    self.hrtf_elevation + motion_elevation,
                    self.hrtf_scene_blend,
                )
                hrtf_focus = (hrtf_focus * 0.76) + (np.mean(hrtf_focus, axis=1, keepdims=True) * 0.24)
                hrtf_focus *= 0.10 + (hrtf_ratio * 0.24)
            direct_center = np.column_stack((source_mono, source_mono)) * self.direct_mix
            direct_side = np.column_stack(
                (
                    source_mono * (0.94 + max(0.0, -effective_pan) * 0.18),
                    source_mono * (0.94 + max(0.0, effective_pan) * 0.18),
                )
            ) * (self.presence_gain + motion_presence)

            width_push = np.column_stack((-source_mono, source_mono)) * ((self.width_gain + (space_ratio * 0.002)) * motion_width_scale)
            wet = cabin_voice + hrtf_focus + road_noise + traffic_noise + engine_noise + air_noise + window_noise + rain_noise + direct_center + direct_side + width_push
            wet *= 0.94 - (road * 0.03)
            wet = wet / (1.0 + (np.abs(wet) * self.soft_drive))

            left_level = float(np.sqrt(np.mean(wet[:, 0] * wet[:, 0])))
            right_level = float(np.sqrt(np.mean(wet[:, 1] * wet[:, 1])))
            auto_balance = np.clip(math.log((left_level + 1e-6) / (right_level + 1e-6)) * 0.30, -0.22, 0.22)
            total_balance = auto_balance + self.output_balance
            if abs(total_balance) > 1e-4:
                wet[:, 0] *= math.exp(-total_balance)
                wet[:, 1] *= math.exp(total_balance)

            output = (dry_stereo * (1.0 - mix)) + (wet * mix) + music_bed
            return np.clip(output, -0.98, 0.98).astype(np.float32, copy=False)

    def open_settings(self, parent):
        snapshot = {
            "preset": self.preset,
            "space": int(self.space),
            "speaker": int(self.speaker),
            "road": int(self.road),
            "tight": int(self.tight),
            "mix": int(self.mix),
            "width": int(self.width),
            "presence": int(self.presence),
            "seat": int(self.seat),
            "window": int(self.window),
            "hrtf": int(self.hrtf_amount),
            "balance": int(self.balance),
            "engine": int(self.engine),
            "rain": int(self.rain),
            "air": int(self.air),
            "traffic": int(self.traffic),
            "motion": int(self.motion),
            "song_level": int(self.song_level),
            "song_path": self.song_path,
            "song_enabled": bool(self.song_enabled),
            "song_loop": bool(self.song_loop),
        }
        dialog = CarCabinDialog(parent, self)
        result = dialog.ShowModal()
        if result == wx.ID_OK:
            self.save_settings()
        else:
            self.set_live_values(snapshot["preset"], snapshot)
            try:
                self.set_song_source(snapshot["song_path"], enabled=snapshot["song_enabled"], loop=snapshot["song_loop"], reset_position=False)
            except Exception:
                self.song_enabled = False
                self.song_path = ""
                self.song_audio = None
        dialog.Destroy()


class CarCabinDialog(PluginControlDialog):
    def __init__(self, parent, plugin):
        self.plugin = plugin
        super().__init__(
            parent,
            title="Car Cabin Settings",
            preset_names=PRESETS.keys(),
            selected_preset=plugin.preset,
            slider_defs=[
                {"key": "space", "label": "Cabin", "value": plugin.space},
                {"key": "speaker", "label": "Tone", "value": plugin.speaker},
                {"key": "road", "label": "Road", "value": plugin.road},
                {"key": "engine", "label": "Engine", "value": plugin.engine},
                {"key": "air", "label": "Air", "value": plugin.air},
                {"key": "traffic", "label": "Traffic", "value": plugin.traffic},
                {"key": "rain", "label": "Rain", "value": plugin.rain},
                {"key": "tight", "label": "Tightness", "value": plugin.tight},
                {"key": "hrtf", "label": "HRTF", "value": plugin.hrtf_amount},
                {"key": "motion", "label": "Motion", "value": plugin.motion},
                {"key": "song_level", "label": "Song", "value": plugin.song_level},
                {"key": "width", "label": "Width", "value": plugin.width},
                {"key": "presence", "label": "Presence", "value": plugin.presence},
                {"key": "seat", "label": "Seat Bias", "value": plugin.seat},
                {"key": "balance", "label": "Balance", "value": plugin.balance},
                {"key": "window", "label": "Window", "value": plugin.window},
                {"key": "mix", "label": "Mix", "value": plugin.mix},
            ],
            hint="Hybrid measured car capture with live preview. Presets apply immediately, so you do not need to press OK to hear the change. Air, Window, Rain, and Traffic use recorded local beds where available. Song is rendered through fixed front car speakers, with body coming from the lower front pair and presence from the dashboard pair, so changing presets moves the listener inside the same cabin instead of moving the speakers.",
            size=(540, 980),
        )
        self.song_path = plugin.song_path
        panel = next((child for child in self.GetChildren() if isinstance(child, wx.Panel)), None)
        if panel is not None:
            panel_sizer = panel.GetSizer()
            self.song_enable = wx.CheckBox(panel, label="Play Song Inside Cabin")
            self.song_enable.SetValue(bool(plugin.song_enabled))
            panel_sizer.Add(self.song_enable, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)

            self.song_loop = wx.CheckBox(panel, label="Loop Song")
            self.song_loop.SetValue(bool(plugin.song_loop))
            panel_sizer.Add(self.song_loop, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)

            self.song_label = wx.StaticText(panel, label=self._song_label_text(self.song_path))
            self.song_label.Wrap(440)
            panel_sizer.Add(self.song_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)

            button_row = wx.BoxSizer(wx.HORIZONTAL)
            self.song_browse = wx.Button(panel, label="Choose Song")
            self.song_clear = wx.Button(panel, label="Clear Song")
            button_row.Add(self.song_browse, 1, wx.RIGHT, 6)
            button_row.Add(self.song_clear, 1, wx.LEFT, 6)
            panel_sizer.Add(button_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 12)

        if self.preset_choice is not None:
            self.preset_choice.Bind(wx.EVT_CHOICE, self.on_preset_change)
        for control in self.controls.values():
            control["slider"].Bind(wx.EVT_SLIDER, self.on_live_change)
        if panel is not None:
            self.song_enable.Bind(wx.EVT_CHECKBOX, self.on_song_toggle)
            self.song_loop.Bind(wx.EVT_CHECKBOX, self.on_song_loop)
            self.song_browse.Bind(wx.EVT_BUTTON, self.on_browse_song)
            self.song_clear.Bind(wx.EVT_BUTTON, self.on_clear_song)

    def apply_live(self):
        self.plugin.set_live_values(self.get_selected_preset() or self.plugin.preset, self.get_slider_values())
        self.plugin.set_song_source(self.song_path, enabled=self.song_enable.GetValue(), loop=self.song_loop.GetValue(), reset_position=False)

    def _song_label_text(self, path):
        if not path:
            return "Song File: none"
        return f"Song File: {path}"

    def on_preset_change(self, event):
        selected = self.get_selected_preset()
        if selected in PRESETS:
            self.set_slider_values(PRESETS[selected])
        self.apply_live()

    def on_live_change(self, event):
        event.Skip()
        self.apply_live()

    def on_song_toggle(self, event):
        event.Skip()
        self.apply_live()

    def on_song_loop(self, event):
        event.Skip()
        self.apply_live()

    def on_browse_song(self, event):
        with wx.FileDialog(
            self,
            "Choose Song",
            wildcard="Audio files (*.wav;*.flac;*.ogg;*.mp3)|*.wav;*.flac;*.ogg;*.mp3|All files (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dialog:
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            selected_path = dialog.GetPath()

        previous_path = self.song_path
        self.song_path = selected_path
        try:
            self.song_enable.SetValue(True)
            self.apply_live()
        except Exception as exc:
            self.song_path = previous_path
            wx.MessageBox(f"Could not load song:\n{exc}", "Car Cabin", wx.ICON_ERROR)
        self.song_label.SetLabel(self._song_label_text(self.song_path))
        self.Layout()

    def on_clear_song(self, event):
        self.song_path = ""
        self.song_enable.SetValue(False)
        self.apply_live()
        self.song_label.SetLabel(self._song_label_text(self.song_path))
        self.Layout()
