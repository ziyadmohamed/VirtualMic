import os

import numpy as np
import wx

from _plugin_utils import PluginControlDialog, load_settings, save_settings


SAMPLE_RATE = 48000
PRESETS = {
    "Hover": {"rate": 18, "depth": 36, "shape": 34, "mix": 42},
    "Trance": {"rate": 46, "depth": 78, "shape": 72, "mix": 100},
    "Chop": {"rate": 78, "depth": 92, "shape": 86, "mix": 100},
}
DEFAULTS = {"preset": "Hover", **PRESETS["Hover"]}


class Plugin:
    def __init__(self):
        self.name = "Pulse Gate"
        self.enabled = False
        self.file_name = "pulse_gate.py"
        self.settings_path = os.path.splitext(__file__)[0] + ".json"
        self.phase = 0.0

        self.preset = DEFAULTS["preset"]
        self.rate = DEFAULTS["rate"]
        self.depth = DEFAULTS["depth"]
        self.shape = DEFAULTS["shape"]
        self.mix = DEFAULTS["mix"]
        self.load_settings()

    def apply_preset(self, name):
        values = PRESETS[name]
        self.preset = name
        self.rate = values["rate"]
        self.depth = values["depth"]
        self.shape = values["shape"]
        self.mix = values["mix"]

    def load_settings(self):
        values = load_settings(self.settings_path, DEFAULTS)
        preset = values.get("preset", DEFAULTS["preset"])
        if preset not in PRESETS:
            preset = DEFAULTS["preset"]
        self.apply_preset(preset)
        self.rate = int(values.get("rate", self.rate))
        self.depth = int(values.get("depth", self.depth))
        self.shape = int(values.get("shape", self.shape))
        self.mix = int(values.get("mix", self.mix))

    def save_settings(self):
        save_settings(
            self.settings_path,
            {
                "preset": self.preset,
                "rate": int(self.rate),
                "depth": int(self.depth),
                "shape": int(self.shape),
                "mix": int(self.mix),
            },
        )

    def process(self, data):
        source = np.asarray(data, dtype=np.float32)
        if source.size == 0:
            return source

        rate_hz = 0.35 + ((self.rate / 100.0) * 14.5)
        depth = self.depth / 100.0
        curve = 1.0 + ((self.shape / 100.0) * 7.0)
        mix = self.mix / 100.0

        phase_step = (2.0 * np.pi * rate_hz) / SAMPLE_RATE
        phases = self.phase + (phase_step * np.arange(source.size, dtype=np.float32))
        lfo = 0.5 * (1.0 + np.sin(phases))
        gate = np.power(lfo, curve)
        wet = source * ((1.0 - depth) + (depth * gate))
        self.phase = float((self.phase + (phase_step * source.size)) % (2.0 * np.pi))
        out = (source * (1.0 - mix)) + (wet * mix)
        return np.clip(out, -0.98, 0.98).astype(np.float32, copy=False)

    def open_settings(self, parent):
        dialog = PulseGateDialog(parent, self)
        result = dialog.ShowModal()
        if result == wx.ID_OK:
            values = dialog.get_slider_values()
            self.preset = dialog.get_selected_preset() or self.preset
            self.rate = int(values["rate"])
            self.depth = int(values["depth"])
            self.shape = int(values["shape"])
            self.mix = int(values["mix"])
            self.save_settings()
        dialog.Destroy()


class PulseGateDialog(PluginControlDialog):
    def __init__(self, parent, plugin):
        self.plugin = plugin
        super().__init__(
            parent,
            title="Pulse Gate Settings",
            preset_names=PRESETS.keys(),
            selected_preset=plugin.preset,
            slider_defs=[
                {"key": "rate", "label": "Rate", "value": plugin.rate},
                {"key": "depth", "label": "Depth", "value": plugin.depth},
                {"key": "shape", "label": "Shape", "value": plugin.shape},
                {"key": "mix", "label": "Mix", "value": plugin.mix},
            ],
            hint="Rhythmic chopping and tremolo. Higher shape values make the gate harder and sharper.",
        )
        if self.preset_choice is not None:
            self.preset_choice.Bind(wx.EVT_CHOICE, self.on_preset_change)

    def on_preset_change(self, event):
        self.set_slider_values(PRESETS[self.get_selected_preset()])

