import os

import numpy as np
import wx

from _plugin_utils import PluginControlDialog, load_settings, save_settings


PRESETS = {
    "Patrol": {"crunch": 44, "static": 22, "squelch": 46, "mix": 86},
    "Dispatch": {"crunch": 34, "static": 16, "squelch": 30, "mix": 78},
    "Scramble": {"crunch": 68, "static": 42, "squelch": 64, "mix": 94},
}
DEFAULTS = {"preset": "Patrol", **PRESETS["Patrol"]}


class Plugin:
    def __init__(self):
        self.name = "Walkie Talkie"
        self.enabled = False
        self.file_name = "walkie_talkie.py"
        self.settings_path = os.path.splitext(__file__)[0] + ".json"
        self.hp_prev_in = 0.0
        self.hp_prev_out = 0.0
        self.lp_state = 0.0
        self.env_state = 0.0
        self.noise_low = 0.0
        self.rng = np.random.default_rng()

        self.preset = DEFAULTS["preset"]
        self.crunch = DEFAULTS["crunch"]
        self.static = DEFAULTS["static"]
        self.squelch = DEFAULTS["squelch"]
        self.mix = DEFAULTS["mix"]
        self.load_settings()

    def apply_preset(self, name):
        values = PRESETS[name]
        self.preset = name
        self.crunch = values["crunch"]
        self.static = values["static"]
        self.squelch = values["squelch"]
        self.mix = values["mix"]

    def load_settings(self):
        values = load_settings(self.settings_path, DEFAULTS)
        preset = values.get("preset", DEFAULTS["preset"])
        if preset not in PRESETS:
            preset = DEFAULTS["preset"]
        self.apply_preset(preset)
        self.crunch = int(values.get("crunch", self.crunch))
        self.static = int(values.get("static", self.static))
        self.squelch = int(values.get("squelch", self.squelch))
        self.mix = int(values.get("mix", self.mix))

    def save_settings(self):
        save_settings(
            self.settings_path,
            {
                "preset": self.preset,
                "crunch": int(self.crunch),
                "static": int(self.static),
                "squelch": int(self.squelch),
                "mix": int(self.mix),
            },
        )

    def process(self, data):
        source = np.asarray(data, dtype=np.float32)
        if source.size == 0:
            return source

        crunch = self.crunch / 100.0
        static = self.static / 100.0
        squelch = self.squelch / 100.0
        mix = self.mix / 100.0

        hp_prev_in = self.hp_prev_in
        hp_prev_out = self.hp_prev_out
        lp_state = self.lp_state
        env_state = self.env_state
        noise_low = self.noise_low
        out = np.empty_like(source, dtype=np.float32)

        hp_coeff = 0.955
        lp_alpha = 0.17 - (crunch * 0.05)
        threshold = 0.012 + (squelch * 0.050)
        drive = 1.5 + (crunch * 4.2)

        for index, sample in enumerate(source):
            hp = sample - hp_prev_in + (hp_coeff * hp_prev_out)
            hp_prev_in = sample
            hp_prev_out = hp

            lp_state += lp_alpha * (hp - lp_state)
            band = lp_state
            env_state += 0.08 * ((abs(band)) - env_state)

            radio = np.tanh(band * drive) / np.tanh(drive)
            gate = np.clip((env_state - threshold) / max(0.001, 0.08 - threshold), 0.0, 1.0)
            radio *= 0.18 + (gate * 0.82)

            noise = float(self.rng.normal(0.0, 1.0))
            noise_low += 0.20 * (noise - noise_low)
            hiss = (noise - noise_low) * (0.014 + (static * 0.085))
            hiss *= 1.0 - (gate * 0.72)

            wet = radio + hiss
            out[index] = (sample * (1.0 - mix)) + (wet * mix)

        self.hp_prev_in = float(hp_prev_in)
        self.hp_prev_out = float(hp_prev_out)
        self.lp_state = float(lp_state)
        self.env_state = float(env_state)
        self.noise_low = float(noise_low)
        return np.clip(out, -0.98, 0.98).astype(np.float32, copy=False)

    def open_settings(self, parent):
        dialog = WalkieTalkieDialog(parent, self)
        result = dialog.ShowModal()
        if result == wx.ID_OK:
            values = dialog.get_slider_values()
            self.preset = dialog.get_selected_preset() or self.preset
            self.crunch = int(values["crunch"])
            self.static = int(values["static"])
            self.squelch = int(values["squelch"])
            self.mix = int(values["mix"])
            self.save_settings()
        dialog.Destroy()


class WalkieTalkieDialog(PluginControlDialog):
    def __init__(self, parent, plugin):
        super().__init__(
            parent,
            title="Walkie Talkie Settings",
            preset_names=PRESETS.keys(),
            selected_preset=plugin.preset,
            slider_defs=[
                {"key": "crunch", "label": "Crunch", "value": plugin.crunch},
                {"key": "static", "label": "Static", "value": plugin.static},
                {"key": "squelch", "label": "Squelch", "value": plugin.squelch},
                {"key": "mix", "label": "Mix", "value": plugin.mix},
            ],
            hint="Patrol and dispatch radio tones. Higher squelch makes starts and stops choppier.",
        )
        if self.preset_choice is not None:
            self.preset_choice.Bind(wx.EVT_CHOICE, self.on_preset_change)

    def on_preset_change(self, event):
        self.set_slider_values(PRESETS[self.get_selected_preset()])
