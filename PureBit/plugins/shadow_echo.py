import os

import numpy as np
import wx

from _plugin_utils import PluginControlDialog, load_settings, save_settings


SAMPLE_RATE = 48000
PRESETS = {
    "Slap": {"time": 8, "feedback": 16, "tone": 68, "mix": 20},
    "Tunnel": {"time": 34, "feedback": 42, "tone": 46, "mix": 38},
    "Ghost": {"time": 54, "feedback": 60, "tone": 32, "mix": 54},
}
DEFAULTS = {"preset": "Slap", **PRESETS["Slap"]}


class Plugin:
    def __init__(self):
        self.name = "Shadow Echo"
        self.enabled = False
        self.file_name = "shadow_echo.py"
        self.settings_path = os.path.splitext(__file__)[0] + ".json"
        self.buffer = np.zeros(SAMPLE_RATE * 2, dtype=np.float32)
        self.write_pos = 0
        self.tone_state = 0.0

        self.preset = DEFAULTS["preset"]
        self.time = DEFAULTS["time"]
        self.feedback = DEFAULTS["feedback"]
        self.tone = DEFAULTS["tone"]
        self.mix = DEFAULTS["mix"]
        self.load_settings()

    def apply_preset(self, name):
        values = PRESETS[name]
        self.preset = name
        self.time = values["time"]
        self.feedback = values["feedback"]
        self.tone = values["tone"]
        self.mix = values["mix"]

    def load_settings(self):
        values = load_settings(self.settings_path, DEFAULTS)
        preset = values.get("preset", DEFAULTS["preset"])
        if preset not in PRESETS:
            preset = DEFAULTS["preset"]
        self.apply_preset(preset)
        self.time = int(values.get("time", self.time))
        self.feedback = int(values.get("feedback", self.feedback))
        self.tone = int(values.get("tone", self.tone))
        self.mix = int(values.get("mix", self.mix))

    def save_settings(self):
        save_settings(
            self.settings_path,
            {
                "preset": self.preset,
                "time": int(self.time),
                "feedback": int(self.feedback),
                "tone": int(self.tone),
                "mix": int(self.mix),
            },
        )

    def process(self, data):
        source = np.asarray(data, dtype=np.float32)
        if source.size == 0:
            return source

        delay_ms = 65.0 + ((self.time / 100.0) * 560.0)
        delay_samples = min(int((delay_ms / 1000.0) * SAMPLE_RATE), self.buffer.size - 1)
        feedback = 0.08 + ((self.feedback / 100.0) * 0.62)
        tone_alpha = 0.03 + ((self.tone / 100.0) * 0.22)
        mix = self.mix / 100.0
        out = np.empty_like(source, dtype=np.float32)
        pos = self.write_pos
        tone_state = self.tone_state
        buffer_len = self.buffer.size

        for index, sample in enumerate(source):
            delayed = self.buffer[(pos - delay_samples) % buffer_len]
            tone_state += tone_alpha * (delayed - tone_state)
            wet = tone_state
            out[index] = sample + (wet * mix)
            self.buffer[pos] = np.clip(sample + (wet * feedback), -1.0, 1.0)
            pos = (pos + 1) % buffer_len

        self.write_pos = pos
        self.tone_state = float(tone_state)
        return np.clip(out, -0.98, 0.98).astype(np.float32, copy=False)

    def open_settings(self, parent):
        dialog = ShadowEchoDialog(parent, self)
        result = dialog.ShowModal()
        if result == wx.ID_OK:
            values = dialog.get_slider_values()
            self.preset = dialog.get_selected_preset() or self.preset
            self.time = int(values["time"])
            self.feedback = int(values["feedback"])
            self.tone = int(values["tone"])
            self.mix = int(values["mix"])
            self.save_settings()
        dialog.Destroy()


class ShadowEchoDialog(PluginControlDialog):
    def __init__(self, parent, plugin):
        self.plugin = plugin
        super().__init__(
            parent,
            title="Shadow Echo Settings",
            preset_names=PRESETS.keys(),
            selected_preset=plugin.preset,
            slider_defs=[
                {"key": "time", "label": "Time", "value": plugin.time},
                {"key": "feedback", "label": "Feedback", "value": plugin.feedback},
                {"key": "tone", "label": "Tone", "value": plugin.tone},
                {"key": "mix", "label": "Mix", "value": plugin.mix},
            ],
            hint="Short slap for swagger or longer ghost trails for dramatic speech.",
        )
        if self.preset_choice is not None:
            self.preset_choice.Bind(wx.EVT_CHOICE, self.on_preset_change)

    def on_preset_change(self, event):
        self.set_slider_values(PRESETS[self.get_selected_preset()])

