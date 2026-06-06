import os

import numpy as np
import wx

from _plugin_utils import PluginControlDialog, load_settings, save_settings


PRESETS = {
    "Street": {"horn": 56, "grit": 48, "slap": 20, "mix": 84},
    "Protest": {"horn": 70, "grit": 62, "slap": 28, "mix": 92},
    "Stadium": {"horn": 82, "grit": 42, "slap": 42, "mix": 88},
}
DEFAULTS = {"preset": "Street", **PRESETS["Street"]}


class Plugin:
    def __init__(self):
        self.name = "Megaphone"
        self.enabled = False
        self.file_name = "megaphone.py"
        self.settings_path = os.path.splitext(__file__)[0] + ".json"
        self.delay_buffer = np.zeros(4096, dtype=np.float32)
        self.write_pos = 0
        self.hp_prev_in = 0.0
        self.hp_prev_out = 0.0
        self.lp_state = 0.0

        self.preset = DEFAULTS["preset"]
        self.horn = DEFAULTS["horn"]
        self.grit = DEFAULTS["grit"]
        self.slap = DEFAULTS["slap"]
        self.mix = DEFAULTS["mix"]
        self.load_settings()

    def apply_preset(self, name):
        values = PRESETS[name]
        self.preset = name
        self.horn = values["horn"]
        self.grit = values["grit"]
        self.slap = values["slap"]
        self.mix = values["mix"]

    def load_settings(self):
        values = load_settings(self.settings_path, DEFAULTS)
        preset = values.get("preset", DEFAULTS["preset"])
        if preset not in PRESETS:
            preset = DEFAULTS["preset"]
        self.apply_preset(preset)
        self.horn = int(values.get("horn", self.horn))
        self.grit = int(values.get("grit", self.grit))
        self.slap = int(values.get("slap", self.slap))
        self.mix = int(values.get("mix", self.mix))

    def save_settings(self):
        save_settings(
            self.settings_path,
            {
                "preset": self.preset,
                "horn": int(self.horn),
                "grit": int(self.grit),
                "slap": int(self.slap),
                "mix": int(self.mix),
            },
        )

    def process(self, data):
        source = np.asarray(data, dtype=np.float32)
        if source.size == 0:
            return source

        horn = self.horn / 100.0
        grit = self.grit / 100.0
        slap = self.slap / 100.0
        mix = self.mix / 100.0

        hp_prev_in = self.hp_prev_in
        hp_prev_out = self.hp_prev_out
        lp_state = self.lp_state
        out = np.empty_like(source, dtype=np.float32)
        pos = self.write_pos

        hp_coeff = 0.950
        lp_alpha = 0.14 - (horn * 0.04)
        horn_delay = 38 + int(horn * 110)
        slap_delay = 220 + int(slap * 520)
        horn_gain = 0.18 + (horn * 0.26)
        slap_gain = 0.05 + (slap * 0.22)
        drive = 1.8 + (grit * 5.6)
        buf_len = self.delay_buffer.size

        for index, sample in enumerate(source):
            hp = sample - hp_prev_in + (hp_coeff * hp_prev_out)
            hp_prev_in = sample
            hp_prev_out = hp

            lp_state += lp_alpha * (hp - lp_state)
            band = lp_state

            horn_reflect = self.delay_buffer[(pos - horn_delay) % buf_len] * horn_gain
            slap_reflect = self.delay_buffer[(pos - slap_delay) % buf_len] * slap_gain
            wet = np.tanh((band + horn_reflect + slap_reflect) * drive) / np.tanh(drive)

            out[index] = (sample * (1.0 - mix)) + (wet * mix)
            self.delay_buffer[pos] = np.clip(band + (horn_reflect * 0.18), -1.0, 1.0)
            pos = (pos + 1) % buf_len

        self.hp_prev_in = float(hp_prev_in)
        self.hp_prev_out = float(hp_prev_out)
        self.lp_state = float(lp_state)
        self.write_pos = pos
        return np.clip(out, -0.98, 0.98).astype(np.float32, copy=False)

    def open_settings(self, parent):
        dialog = MegaphoneDialog(parent, self)
        result = dialog.ShowModal()
        if result == wx.ID_OK:
            values = dialog.get_slider_values()
            self.preset = dialog.get_selected_preset() or self.preset
            self.horn = int(values["horn"])
            self.grit = int(values["grit"])
            self.slap = int(values["slap"])
            self.mix = int(values["mix"])
            self.save_settings()
        dialog.Destroy()


class MegaphoneDialog(PluginControlDialog):
    def __init__(self, parent, plugin):
        super().__init__(
            parent,
            title="Megaphone Settings",
            preset_names=PRESETS.keys(),
            selected_preset=plugin.preset,
            slider_defs=[
                {"key": "horn", "label": "Horn", "value": plugin.horn},
                {"key": "grit", "label": "Grit", "value": plugin.grit},
                {"key": "slap", "label": "Slap", "value": plugin.slap},
                {"key": "mix", "label": "Mix", "value": plugin.mix},
            ],
            hint="Horn-loaded shout box sound. Slap adds the hard bounce you hear from cheap megaphones and PA horns.",
        )
        if self.preset_choice is not None:
            self.preset_choice.Bind(wx.EVT_CHOICE, self.on_preset_change)

    def on_preset_change(self, event):
        self.set_slider_values(PRESETS[self.get_selected_preset()])
