import os

import numpy as np
import wx

from _plugin_utils import PluginControlDialog, load_settings, save_settings


PRESETS = {
    "Pager": {"crush": 42, "hold": 20, "tone": 56, "mix": 58},
    "Rust": {"crush": 72, "hold": 52, "tone": 34, "mix": 82},
    "Arcade": {"crush": 58, "hold": 38, "tone": 66, "mix": 74},
}
DEFAULTS = {"preset": "Pager", **PRESETS["Pager"]}


class Plugin:
    def __init__(self):
        self.name = "Bitgrid Crusher"
        self.enabled = False
        self.file_name = "bitgrid_crusher.py"
        self.settings_path = os.path.splitext(__file__)[0] + ".json"
        self.hp_prev_in = 0.0
        self.hp_prev_out = 0.0
        self.lp_state = 0.0

        self.preset = DEFAULTS["preset"]
        self.crush = DEFAULTS["crush"]
        self.hold = DEFAULTS["hold"]
        self.tone = DEFAULTS["tone"]
        self.mix = DEFAULTS["mix"]
        self.load_settings()

    def apply_preset(self, name):
        values = PRESETS[name]
        self.preset = name
        self.crush = values["crush"]
        self.hold = values["hold"]
        self.tone = values["tone"]
        self.mix = values["mix"]

    def load_settings(self):
        values = load_settings(self.settings_path, DEFAULTS)
        preset = values.get("preset", DEFAULTS["preset"])
        if preset not in PRESETS:
            preset = DEFAULTS["preset"]
        self.apply_preset(preset)
        self.crush = int(values.get("crush", self.crush))
        self.hold = int(values.get("hold", self.hold))
        self.tone = int(values.get("tone", self.tone))
        self.mix = int(values.get("mix", self.mix))

    def save_settings(self):
        save_settings(
            self.settings_path,
            {
                "preset": self.preset,
                "crush": int(self.crush),
                "hold": int(self.hold),
                "tone": int(self.tone),
                "mix": int(self.mix),
            },
        )

    def _shape_band(self, data):
        output = np.empty_like(data, dtype=np.float32)
        hp_prev_in = self.hp_prev_in
        hp_prev_out = self.hp_prev_out
        lp_state = self.lp_state
        hp_coeff = 0.86 + ((self.tone / 100.0) * 0.08)
        lp_alpha = 0.08 + ((self.tone / 100.0) * 0.20)

        for index, sample in enumerate(data):
            high = sample - hp_prev_in + (hp_coeff * hp_prev_out)
            hp_prev_in = sample
            hp_prev_out = high
            lp_state += lp_alpha * (high - lp_state)
            output[index] = lp_state

        self.hp_prev_in = float(hp_prev_in)
        self.hp_prev_out = float(hp_prev_out)
        self.lp_state = float(lp_state)
        return output

    def process(self, data):
        source = np.asarray(data, dtype=np.float32)
        if source.size == 0:
            return source

        hold_step = 1 + int((self.hold / 100.0) * 14)
        held = np.repeat(source[::hold_step], hold_step)[:source.size]
        bits = 12 - int((self.crush / 100.0) * 8)
        quantizer = float(2 ** (bits - 1))
        crushed = np.clip(np.round(held * quantizer) / quantizer, -1.0, 1.0)
        filtered = self._shape_band(crushed) * 1.18
        mix = self.mix / 100.0
        out = (source * (1.0 - mix)) + (filtered * mix)
        return np.clip(out, -0.98, 0.98).astype(np.float32, copy=False)

    def open_settings(self, parent):
        dialog = BitgridCrusherDialog(parent, self)
        result = dialog.ShowModal()
        if result == wx.ID_OK:
            values = dialog.get_slider_values()
            self.preset = dialog.get_selected_preset() or self.preset
            self.crush = int(values["crush"])
            self.hold = int(values["hold"])
            self.tone = int(values["tone"])
            self.mix = int(values["mix"])
            self.save_settings()
        dialog.Destroy()


class BitgridCrusherDialog(PluginControlDialog):
    def __init__(self, parent, plugin):
        self.plugin = plugin
        super().__init__(
            parent,
            title="Bitgrid Crusher Settings",
            preset_names=PRESETS.keys(),
            selected_preset=plugin.preset,
            slider_defs=[
                {"key": "crush", "label": "Crush", "value": plugin.crush},
                {"key": "hold", "label": "Hold", "value": plugin.hold},
                {"key": "tone", "label": "Tone", "value": plugin.tone},
                {"key": "mix", "label": "Mix", "value": plugin.mix},
            ],
            hint="Lo-fi, pager, arcade and broken-comms textures. Higher hold values sound more digital.",
        )
        if self.preset_choice is not None:
            self.preset_choice.Bind(wx.EVT_CHOICE, self.on_preset_change)

    def on_preset_change(self, event):
        self.set_slider_values(PRESETS[self.get_selected_preset()])

