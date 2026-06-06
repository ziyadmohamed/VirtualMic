import os

import numpy as np
import wx

from _plugin_utils import PluginControlDialog, load_settings, save_settings


SAMPLE_RATE = 48000
PRESETS = {
    "Underpass": {"length": 28, "walls": 40, "feedback": 34, "mix": 44},
    "Subway": {"length": 58, "walls": 62, "feedback": 56, "mix": 62},
    "Drain": {"length": 82, "walls": 76, "feedback": 70, "mix": 78},
}
DEFAULTS = {"preset": "Underpass", **PRESETS["Underpass"]}


class Plugin:
    def __init__(self):
        self.name = "Tunnel Space"
        self.enabled = False
        self.file_name = "tunnel_space.py"
        self.settings_path = os.path.splitext(__file__)[0] + ".json"
        self.delay_buffer = np.zeros(SAMPLE_RATE * 3, dtype=np.float32)
        self.write_pos = 0
        self.feedback_state = 0.0

        self.preset = DEFAULTS["preset"]
        self.length = DEFAULTS["length"]
        self.walls = DEFAULTS["walls"]
        self.feedback = DEFAULTS["feedback"]
        self.mix = DEFAULTS["mix"]
        self.load_settings()

    def apply_preset(self, name):
        values = PRESETS[name]
        self.preset = name
        self.length = values["length"]
        self.walls = values["walls"]
        self.feedback = values["feedback"]
        self.mix = values["mix"]

    def load_settings(self):
        values = load_settings(self.settings_path, DEFAULTS)
        preset = values.get("preset", DEFAULTS["preset"])
        if preset not in PRESETS:
            preset = DEFAULTS["preset"]
        self.apply_preset(preset)
        self.length = int(values.get("length", self.length))
        self.walls = int(values.get("walls", self.walls))
        self.feedback = int(values.get("feedback", self.feedback))
        self.mix = int(values.get("mix", self.mix))

    def save_settings(self):
        save_settings(
            self.settings_path,
            {
                "preset": self.preset,
                "length": int(self.length),
                "walls": int(self.walls),
                "feedback": int(self.feedback),
                "mix": int(self.mix),
            },
        )

    def process(self, data):
        source = np.asarray(data, dtype=np.float32)
        if source.size == 0:
            return source

        length = self.length / 100.0
        walls = self.walls / 100.0
        feedback = 0.14 + ((self.feedback / 100.0) * 0.72)
        mix = self.mix / 100.0

        tap_1 = 1200 + int(length * 3600)
        tap_2 = 3000 + int(length * 7200)
        tap_3 = 6200 + int(length * 12000)
        wall_gain_1 = 0.20 + (walls * 0.18)
        wall_gain_2 = 0.14 + (walls * 0.16)
        wall_gain_3 = 0.08 + (walls * 0.14)

        out = np.empty_like(source, dtype=np.float32)
        pos = self.write_pos
        fb_state = self.feedback_state
        buf_len = self.delay_buffer.size
        damping = 0.06 + ((1.0 - walls) * 0.12)

        for index, sample in enumerate(source):
            d1 = self.delay_buffer[(pos - tap_1) % buf_len]
            d2 = self.delay_buffer[(pos - tap_2) % buf_len]
            d3 = self.delay_buffer[(pos - tap_3) % buf_len]
            wet = (d1 * wall_gain_1) + (d2 * wall_gain_2) + (d3 * wall_gain_3)
            fb_state += damping * (wet - fb_state)
            tunnel = sample + wet + (fb_state * 0.24)
            out[index] = (sample * (1.0 - mix)) + (tunnel * mix)
            self.delay_buffer[pos] = np.clip(sample + (wet * feedback), -1.0, 1.0)
            pos = (pos + 1) % buf_len

        self.write_pos = pos
        self.feedback_state = float(fb_state)
        return np.clip(out, -0.98, 0.98).astype(np.float32, copy=False)

    def open_settings(self, parent):
        dialog = TunnelSpaceDialog(parent, self)
        result = dialog.ShowModal()
        if result == wx.ID_OK:
            values = dialog.get_slider_values()
            self.preset = dialog.get_selected_preset() or self.preset
            self.length = int(values["length"])
            self.walls = int(values["walls"])
            self.feedback = int(values["feedback"])
            self.mix = int(values["mix"])
            self.save_settings()
        dialog.Destroy()


class TunnelSpaceDialog(PluginControlDialog):
    def __init__(self, parent, plugin):
        super().__init__(
            parent,
            title="Tunnel Space Settings",
            preset_names=PRESETS.keys(),
            selected_preset=plugin.preset,
            slider_defs=[
                {"key": "length", "label": "Length", "value": plugin.length},
                {"key": "walls", "label": "Walls", "value": plugin.walls},
                {"key": "feedback", "label": "Feedback", "value": plugin.feedback},
                {"key": "mix", "label": "Mix", "value": plugin.mix},
            ],
            hint="Big concrete tunnel reflections. Longer length and feedback make the voice trail harder.",
        )
        if self.preset_choice is not None:
            self.preset_choice.Bind(wx.EVT_CHOICE, self.on_preset_change)

    def on_preset_change(self, event):
        self.set_slider_values(PRESETS[self.get_selected_preset()])
