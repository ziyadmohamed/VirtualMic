import os

import numpy as np
import wx

from _plugin_utils import PluginControlDialog, load_settings, save_settings


PRESETS = {
    "Arena": {"drive": 38, "room": 34, "horn": 58, "mix": 74},
    "Stage": {"drive": 30, "room": 22, "horn": 46, "mix": 62},
    "Halftime": {"drive": 52, "room": 54, "horn": 70, "mix": 82},
}
DEFAULTS = {"preset": "Arena", **PRESETS["Arena"]}


class Plugin:
    def __init__(self):
        self.name = "Stadium PA"
        self.enabled = False
        self.file_name = "stadium_pa.py"
        self.settings_path = os.path.splitext(__file__)[0] + ".json"
        self.delay_buffer = np.zeros(12288, dtype=np.float32)
        self.write_pos = 0
        self.hp_prev_in = 0.0
        self.hp_prev_out = 0.0
        self.lp_state = 0.0

        self.preset = DEFAULTS["preset"]
        self.drive = DEFAULTS["drive"]
        self.room = DEFAULTS["room"]
        self.horn = DEFAULTS["horn"]
        self.mix = DEFAULTS["mix"]
        self.load_settings()

    def apply_preset(self, name):
        values = PRESETS[name]
        self.preset = name
        self.drive = values["drive"]
        self.room = values["room"]
        self.horn = values["horn"]
        self.mix = values["mix"]

    def load_settings(self):
        values = load_settings(self.settings_path, DEFAULTS)
        preset = values.get("preset", DEFAULTS["preset"])
        if preset not in PRESETS:
            preset = DEFAULTS["preset"]
        self.apply_preset(preset)
        self.drive = int(values.get("drive", self.drive))
        self.room = int(values.get("room", self.room))
        self.horn = int(values.get("horn", self.horn))
        self.mix = int(values.get("mix", self.mix))

    def save_settings(self):
        save_settings(
            self.settings_path,
            {
                "preset": self.preset,
                "drive": int(self.drive),
                "room": int(self.room),
                "horn": int(self.horn),
                "mix": int(self.mix),
            },
        )

    def process(self, data):
        source = np.asarray(data, dtype=np.float32)
        if source.size == 0:
            return source

        drive = self.drive / 100.0
        room = self.room / 100.0
        horn = self.horn / 100.0
        mix = self.mix / 100.0

        hp_prev_in = self.hp_prev_in
        hp_prev_out = self.hp_prev_out
        lp_state = self.lp_state
        out = np.empty_like(source, dtype=np.float32)
        pos = self.write_pos
        buf_len = self.delay_buffer.size

        hp_coeff = 0.960
        lp_alpha = 0.16 - (horn * 0.05)
        predrive = 1.4 + (drive * 3.8)
        room_tap_1 = 260 + int(room * 240)
        room_tap_2 = 820 + int(room * 520)
        room_tap_3 = 1680 + int(room * 980)
        room_gain_1 = 0.10 + (room * 0.10)
        room_gain_2 = 0.06 + (room * 0.12)
        room_gain_3 = 0.03 + (room * 0.10)
        horn_delay = 54 + int(horn * 120)
        horn_gain = 0.12 + (horn * 0.20)

        for index, sample in enumerate(source):
            hp = sample - hp_prev_in + (hp_coeff * hp_prev_out)
            hp_prev_in = sample
            hp_prev_out = hp
            lp_state += lp_alpha * (hp - lp_state)
            colored = lp_state

            room_reflections = (
                (self.delay_buffer[(pos - room_tap_1) % buf_len] * room_gain_1)
                + (self.delay_buffer[(pos - room_tap_2) % buf_len] * room_gain_2)
                + (self.delay_buffer[(pos - room_tap_3) % buf_len] * room_gain_3)
            )
            horn_reflect = self.delay_buffer[(pos - horn_delay) % buf_len] * horn_gain
            wet = np.tanh((colored + room_reflections + horn_reflect) * predrive) / np.tanh(predrive)

            out[index] = (sample * (1.0 - mix)) + (wet * mix)
            self.delay_buffer[pos] = np.clip(colored + (room_reflections * 0.18), -1.0, 1.0)
            pos = (pos + 1) % buf_len

        self.hp_prev_in = float(hp_prev_in)
        self.hp_prev_out = float(hp_prev_out)
        self.lp_state = float(lp_state)
        self.write_pos = pos
        return np.clip(out, -0.98, 0.98).astype(np.float32, copy=False)

    def open_settings(self, parent):
        dialog = StadiumPaDialog(parent, self)
        result = dialog.ShowModal()
        if result == wx.ID_OK:
            values = dialog.get_slider_values()
            self.preset = dialog.get_selected_preset() or self.preset
            self.drive = int(values["drive"])
            self.room = int(values["room"])
            self.horn = int(values["horn"])
            self.mix = int(values["mix"])
            self.save_settings()
        dialog.Destroy()


class StadiumPaDialog(PluginControlDialog):
    def __init__(self, parent, plugin):
        super().__init__(
            parent,
            title="Stadium PA Settings",
            preset_names=PRESETS.keys(),
            selected_preset=plugin.preset,
            slider_defs=[
                {"key": "drive", "label": "Drive", "value": plugin.drive},
                {"key": "room", "label": "Room", "value": plugin.room},
                {"key": "horn", "label": "Horn", "value": plugin.horn},
                {"key": "mix", "label": "Mix", "value": plugin.mix},
            ],
            hint="Large PA horn and venue bounce. Arena and Halftime are bigger, Stage is tighter and clearer.",
        )
        if self.preset_choice is not None:
            self.preset_choice.Bind(wx.EVT_CHOICE, self.on_preset_change)

    def on_preset_change(self, event):
        self.set_slider_values(PRESETS[self.get_selected_preset()])
