import os

import numpy as np
import wx

from _plugin_utils import PluginControlDialog, load_settings, save_settings


SAMPLE_RATE = 48000
PRESETS = {
    "Droid": {"carrier": 24, "metallic": 36, "tone": 52, "mix": 72},
    "Scanner": {"carrier": 48, "metallic": 58, "tone": 44, "mix": 82},
    "Overlord": {"carrier": 62, "metallic": 74, "tone": 34, "mix": 92},
}
DEFAULTS = {"preset": "Droid", **PRESETS["Droid"]}


class Plugin:
    def __init__(self):
        self.name = "Robot Matrix"
        self.enabled = False
        self.file_name = "robot_matrix.py"
        self.settings_path = os.path.splitext(__file__)[0] + ".json"
        self.phase = 0.0
        self.buffer = np.zeros(4096, dtype=np.float32)
        self.write_pos = 0
        self.low_state = 0.0

        self.preset = DEFAULTS["preset"]
        self.carrier = DEFAULTS["carrier"]
        self.metallic = DEFAULTS["metallic"]
        self.tone = DEFAULTS["tone"]
        self.mix = DEFAULTS["mix"]
        self.load_settings()

    def apply_preset(self, name):
        values = PRESETS[name]
        self.preset = name
        self.carrier = values["carrier"]
        self.metallic = values["metallic"]
        self.tone = values["tone"]
        self.mix = values["mix"]

    def load_settings(self):
        values = load_settings(self.settings_path, DEFAULTS)
        preset = values.get("preset", DEFAULTS["preset"])
        if preset not in PRESETS:
            preset = DEFAULTS["preset"]
        self.apply_preset(preset)
        self.carrier = int(values.get("carrier", self.carrier))
        self.metallic = int(values.get("metallic", self.metallic))
        self.tone = int(values.get("tone", self.tone))
        self.mix = int(values.get("mix", self.mix))

    def save_settings(self):
        save_settings(
            self.settings_path,
            {
                "preset": self.preset,
                "carrier": int(self.carrier),
                "metallic": int(self.metallic),
                "tone": int(self.tone),
                "mix": int(self.mix),
            },
        )

    def process(self, data):
        source = np.asarray(data, dtype=np.float32)
        if source.size == 0:
            return source

        carrier_hz = 26.0 + ((self.carrier / 100.0) * 210.0)
        metallic = self.metallic / 100.0
        mix = self.mix / 100.0
        phase_step = (2.0 * np.pi * carrier_hz) / SAMPLE_RATE
        phases = self.phase + (phase_step * np.arange(source.size, dtype=np.float32))
        oscillator = np.sin(phases).astype(np.float32)
        ring = source * oscillator

        delay_samples = 26 + int(metallic * 180.0)
        feedback = 0.10 + (metallic * 0.42)
        tone_alpha = 0.06 + ((self.tone / 100.0) * 0.24)

        out = np.empty_like(source, dtype=np.float32)
        pos = self.write_pos
        low_state = self.low_state
        buffer_len = self.buffer.size

        for index, sample in enumerate(ring):
            delayed = self.buffer[(pos - delay_samples) % buffer_len]
            comb = sample + (delayed * feedback)
            low_state += tone_alpha * (comb - low_state)
            wet = (comb * (0.72 + (metallic * 0.18))) + (low_state * 0.28)
            out[index] = (source[index] * (1.0 - mix)) + (wet * mix)
            self.buffer[pos] = np.clip(sample, -1.0, 1.0)
            pos = (pos + 1) % buffer_len

        self.phase = float((self.phase + (phase_step * source.size)) % (2.0 * np.pi))
        self.write_pos = pos
        self.low_state = float(low_state)
        return np.clip(out, -0.98, 0.98).astype(np.float32, copy=False)

    def open_settings(self, parent):
        dialog = RobotMatrixDialog(parent, self)
        result = dialog.ShowModal()
        if result == wx.ID_OK:
            values = dialog.get_slider_values()
            self.preset = dialog.get_selected_preset() or self.preset
            self.carrier = int(values["carrier"])
            self.metallic = int(values["metallic"])
            self.tone = int(values["tone"])
            self.mix = int(values["mix"])
            self.save_settings()
        dialog.Destroy()


class RobotMatrixDialog(PluginControlDialog):
    def __init__(self, parent, plugin):
        self.plugin = plugin
        super().__init__(
            parent,
            title="Robot Matrix Settings",
            preset_names=PRESETS.keys(),
            selected_preset=plugin.preset,
            slider_defs=[
                {"key": "carrier", "label": "Carrier", "value": plugin.carrier},
                {"key": "metallic", "label": "Metallic", "value": plugin.metallic},
                {"key": "tone", "label": "Tone", "value": plugin.tone},
                {"key": "mix", "label": "Mix", "value": plugin.mix},
            ],
            hint="Robot voice and scanner-metal textures. Higher carrier values sound more synthetic.",
        )
        if self.preset_choice is not None:
            self.preset_choice.Bind(wx.EVT_CHOICE, self.on_preset_change)

    def on_preset_change(self, event):
        self.set_slider_values(PRESETS[self.get_selected_preset()])
