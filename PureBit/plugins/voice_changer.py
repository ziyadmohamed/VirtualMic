import os
import math
import numpy as np
import wx

from _plugin_utils import PluginControlDialog, load_settings, save_settings


PRESETS = {
    "Demon": {"shift": -7, "grit": 40, "mix": 100},
    "Chipmunk": {"shift": 8, "grit": 0, "mix": 100},
    "Giant": {"shift": -12, "grit": 50, "mix": 90},
    "Robot Voice": {"shift": -4, "grit": 20, "mix": 80},
}
DEFAULTS = {"preset": "Demon", **PRESETS["Demon"]}


class Plugin:
    def __init__(self):
        self.name = "Voice Changer"
        self.enabled = False
        self.file_name = "voice_changer.py"
        self.settings_path = os.path.splitext(__file__)[0] + ".json"
        
        # Ring buffer for pitch shifting: 8192 samples is enough for 100ms at 48kHz
        self.buffer_size = 8192
        self.delay_buffer = np.zeros(self.buffer_size, dtype=np.float32)
        self.write_pos = 0
        self.phase = 0.0
        
        self.preset = DEFAULTS["preset"]
        self.shift = DEFAULTS["shift"]
        self.grit = DEFAULTS["grit"]
        self.mix = DEFAULTS["mix"]
        self.load_settings()
        
    def apply_preset(self, name):
        values = PRESETS[name]
        self.preset = name
        self.shift = values["shift"]
        self.grit = values["grit"]
        self.mix = values["mix"]

    def load_settings(self):
        values = load_settings(self.settings_path, DEFAULTS)
        preset = values.get("preset", DEFAULTS["preset"])
        if preset not in PRESETS:
            preset = DEFAULTS["preset"]
        self.apply_preset(preset)
        self.shift = int(values.get("shift", self.shift))
        self.grit = int(values.get("grit", self.grit))
        self.mix = int(values.get("mix", self.mix))

    def save_settings(self):
        save_settings(
            self.settings_path,
            {
                "preset": self.preset,
                "shift": int(self.shift),
                "grit": int(self.grit),
                "mix": int(self.mix),
            },
        )

    def process(self, data):
        source = np.asarray(data, dtype=np.float32)
        if source.size == 0:
            return source

        semitones = float(self.shift)
        S = 2.0 ** (semitones / 12.0)
        grit = self.grit / 100.0
        mix = self.mix / 100.0

        if abs(semitones) < 0.1:
            if grit > 0.05:
                drive = 1.0 + grit * 4.0
                wet = np.tanh(source * drive) / np.tanh(drive)
                return (source * (1.0 - mix)) + (wet * mix)
            return source

        # Max delay size is 30ms (1440 samples at 48kHz)
        D = 1440.0
        freq = abs(1.0 - S) * 48000.0 / D
        phase_step = freq / 48000.0

        out = np.empty_like(source)
        pos = self.write_pos
        phase = self.phase
        buf_len = self.buffer_size

        for index, sample in enumerate(source):
            self.delay_buffer[pos] = sample

            # Calculate delay times
            d1 = phase * D
            d2 = ((phase + 0.5) % 1.0) * D

            # Read indices (fractional delay with linear interpolation)
            idx1_f = (pos - d1) % buf_len
            idx1_i = int(idx1_f)
            frac1 = idx1_f - idx1_i
            idx1_next = (idx1_i + 1) % buf_len
            val1 = self.delay_buffer[idx1_i] + (self.delay_buffer[idx1_next] - self.delay_buffer[idx1_i]) * frac1

            idx2_f = (pos - d2) % buf_len
            idx2_i = int(idx2_f)
            frac2 = idx2_f - idx2_i
            idx2_next = (idx2_i + 1) % buf_len
            val2 = self.delay_buffer[idx2_i] + (self.delay_buffer[idx2_next] - self.delay_buffer[idx2_i]) * frac2

            # Triangle window crossfade
            w1 = 1.0 - abs(2.0 * phase - 1.0)
            w2 = 1.0 - w1

            wet = val1 * w1 + val2 * w2

            # Saturation
            if grit > 0.05:
                drive = 1.0 + grit * 4.0
                wet = np.tanh(wet * drive) / np.tanh(drive)

            out[index] = (sample * (1.0 - mix)) + (wet * mix)

            phase = (phase + phase_step) % 1.0
            pos = (pos + 1) % buf_len

        self.write_pos = pos
        self.phase = phase
        return np.clip(out, -0.98, 0.98).astype(np.float32, copy=False)

    def open_settings(self, parent):
        dialog = VoiceChangerDialog(parent, self)
        result = dialog.ShowModal()
        if result == wx.ID_OK:
            values = dialog.get_slider_values()
            self.preset = dialog.get_selected_preset() or self.preset
            self.shift = int(values["shift"])
            self.grit = int(values["grit"])
            self.mix = int(values["mix"])
            self.save_settings()
        dialog.Destroy()


class VoiceChangerDialog(PluginControlDialog):
    def __init__(self, parent, plugin):
        super().__init__(
            parent,
            title="Voice Changer Settings",
            preset_names=PRESETS.keys(),
            selected_preset=plugin.preset,
            slider_defs=[
                {"key": "shift", "label": "Pitch Shift (Semitones)", "value": plugin.shift, "min": -12, "max": 12},
                {"key": "grit", "label": "Grit / Distortion", "value": plugin.grit},
                {"key": "mix", "label": "Mix", "value": plugin.mix},
            ],
            hint="Pitch Shift semitones to sound like a Demon (-7), Chipmunk (+8), or Giant (-12). Grit adds harmonic transistor/tube drive distortion.",
        )
        if self.preset_choice is not None:
            self.preset_choice.Bind(wx.EVT_CHOICE, self.on_preset_change)

    def on_preset_change(self, event):
        self.set_slider_values(PRESETS[self.get_selected_preset()])
