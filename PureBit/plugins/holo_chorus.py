import os

import numpy as np
import wx

from _plugin_utils import PluginControlDialog, load_settings, save_settings


SAMPLE_RATE = 48000
PRESETS = {
    "Wide": {"depth": 48, "rate": 28, "feedback": 18, "mix": 38},
    "Liquid": {"depth": 66, "rate": 40, "feedback": 28, "mix": 50},
    "Dream": {"depth": 82, "rate": 22, "feedback": 34, "mix": 62},
}
DEFAULTS = {"preset": "Wide", **PRESETS["Wide"]}


class Plugin:
    def __init__(self):
        self.name = "Holo Chorus"
        self.enabled = False
        self.file_name = "holo_chorus.py"
        self.settings_path = os.path.splitext(__file__)[0] + ".json"
        self.buffer = np.zeros(12288, dtype=np.float32)
        self.write_pos = 0
        self.lfo_phase = 0.0

        self.preset = DEFAULTS["preset"]
        self.depth = DEFAULTS["depth"]
        self.rate = DEFAULTS["rate"]
        self.feedback = DEFAULTS["feedback"]
        self.mix = DEFAULTS["mix"]
        self.load_settings()

    def apply_preset(self, name):
        values = PRESETS[name]
        self.preset = name
        self.depth = values["depth"]
        self.rate = values["rate"]
        self.feedback = values["feedback"]
        self.mix = values["mix"]

    def load_settings(self):
        values = load_settings(self.settings_path, DEFAULTS)
        preset = values.get("preset", DEFAULTS["preset"])
        if preset not in PRESETS:
            preset = DEFAULTS["preset"]
        self.apply_preset(preset)
        self.depth = int(values.get("depth", self.depth))
        self.rate = int(values.get("rate", self.rate))
        self.feedback = int(values.get("feedback", self.feedback))
        self.mix = int(values.get("mix", self.mix))

    def save_settings(self):
        save_settings(
            self.settings_path,
            {
                "preset": self.preset,
                "depth": int(self.depth),
                "rate": int(self.rate),
                "feedback": int(self.feedback),
                "mix": int(self.mix),
            },
        )

    def process(self, data):
        source = np.asarray(data, dtype=np.float32)
        if source.size == 0:
            return source

        mix = self.mix / 100.0
        feedback = 0.04 + ((self.feedback / 100.0) * 0.30)
        rate_hz = 0.10 + ((self.rate / 100.0) * 2.6)
        depth_samples = 36.0 + ((self.depth / 100.0) * 420.0)
        base_delay = 72.0
        phase_step = (2.0 * np.pi * rate_hz) / SAMPLE_RATE
        out = np.empty_like(source, dtype=np.float32)
        buffer_len = self.buffer.size
        pos = self.write_pos

        for index, sample in enumerate(source):
            mod = 0.5 * (1.0 + np.sin(self.lfo_phase + (phase_step * index)))
            delay = base_delay + (depth_samples * mod)
            read_pos = (pos - delay) % buffer_len
            i0 = int(read_pos)
            i1 = (i0 + 1) % buffer_len
            frac = read_pos - i0
            delayed = (self.buffer[i0] * (1.0 - frac)) + (self.buffer[i1] * frac)
            wet = sample + (delayed * 0.68)
            out[index] = (sample * (1.0 - mix)) + (wet * mix)
            self.buffer[pos] = np.clip(sample + (delayed * feedback), -1.0, 1.0)
            pos = (pos + 1) % buffer_len

        self.write_pos = pos
        self.lfo_phase = (self.lfo_phase + (phase_step * source.size)) % (2.0 * np.pi)
        return np.clip(out, -0.98, 0.98).astype(np.float32, copy=False)

    def open_settings(self, parent):
        dialog = HoloChorusDialog(parent, self)
        result = dialog.ShowModal()
        if result == wx.ID_OK:
            values = dialog.get_slider_values()
            self.preset = dialog.get_selected_preset() or self.preset
            self.depth = int(values["depth"])
            self.rate = int(values["rate"])
            self.feedback = int(values["feedback"])
            self.mix = int(values["mix"])
            self.save_settings()
        dialog.Destroy()


class HoloChorusDialog(PluginControlDialog):
    def __init__(self, parent, plugin):
        self.plugin = plugin
        super().__init__(
            parent,
            title="Holo Chorus Settings",
            preset_names=PRESETS.keys(),
            selected_preset=plugin.preset,
            slider_defs=[
                {"key": "depth", "label": "Depth", "value": plugin.depth},
                {"key": "rate", "label": "Rate", "value": plugin.rate},
                {"key": "feedback", "label": "Feedback", "value": plugin.feedback},
                {"key": "mix", "label": "Mix", "value": plugin.mix},
            ],
            hint="Animated width and shimmer. Keep mix moderate if you still want clear speech.",
        )
        if self.preset_choice is not None:
            self.preset_choice.Bind(wx.EVT_CHOICE, self.on_preset_change)

    def on_preset_change(self, event):
        self.set_slider_values(PRESETS[self.get_selected_preset()])
