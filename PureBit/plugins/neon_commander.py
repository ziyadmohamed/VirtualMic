import json
import os

import numpy as np
import wx


PRESETS = {
    "Broadcast": {
        "drive": 28,
        "presence": 34,
        "thickness": 18,
        "mix": 82,
        "delay_samples": 156,
        "output_gain": 0.95,
    },
    "Radio": {
        "drive": 40,
        "presence": 60,
        "thickness": 8,
        "mix": 90,
        "delay_samples": 96,
        "output_gain": 0.88,
    },
    "Titan": {
        "drive": 52,
        "presence": 20,
        "thickness": 34,
        "mix": 86,
        "delay_samples": 228,
        "output_gain": 0.84,
    },
}


class Plugin:
    def __init__(self):
        self.name = "Neon Commander"
        self.enabled = True
        self.file_name = "neon_commander.py"

        self.settings_path = os.path.splitext(__file__)[0] + ".json"
        self.delay_buffer = np.zeros(4096, dtype=np.float32)
        self.delay_pos = 0
        self.hp_prev_in = 0.0
        self.hp_prev_out = 0.0
        self.low_state = 0.0
        self.air_state = 0.0

        self.preset = "Broadcast"
        self.drive = 28
        self.presence = 34
        self.thickness = 18
        self.mix = 82
        self.delay_samples = 156
        self.output_gain = 0.95

        self.load_settings()

    def apply_preset(self, name):
        values = PRESETS[name]
        self.preset = name
        self.drive = values["drive"]
        self.presence = values["presence"]
        self.thickness = values["thickness"]
        self.mix = values["mix"]
        self.delay_samples = values["delay_samples"]
        self.output_gain = values["output_gain"]

    def load_settings(self):
        if not os.path.exists(self.settings_path):
            self.apply_preset(self.preset)
            return

        try:
            with open(self.settings_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            self.apply_preset(self.preset)
            return

        preset = data.get("preset", self.preset)
        if preset not in PRESETS:
            preset = "Broadcast"
        self.apply_preset(preset)

        self.drive = int(data.get("drive", self.drive))
        self.presence = int(data.get("presence", self.presence))
        self.thickness = int(data.get("thickness", self.thickness))
        self.mix = int(data.get("mix", self.mix))
        self.delay_samples = int(data.get("delay_samples", self.delay_samples))
        self.output_gain = float(data.get("output_gain", self.output_gain))

    def save_settings(self):
        data = {
            "preset": self.preset,
            "drive": int(self.drive),
            "presence": int(self.presence),
            "thickness": int(self.thickness),
            "mix": int(self.mix),
            "delay_samples": int(self.delay_samples),
            "output_gain": float(self.output_gain),
        }
        try:
            with open(self.settings_path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
        except Exception as exc:
            print(f"Neon Commander settings save failed: {exc}")

    def _highpass_block(self, data):
        output = np.empty_like(data, dtype=np.float32)
        prev_in = self.hp_prev_in
        prev_out = self.hp_prev_out
        coeff = 0.995

        for index, sample in enumerate(data):
            current = sample - prev_in + (coeff * prev_out)
            output[index] = current
            prev_in = sample
            prev_out = current

        self.hp_prev_in = float(prev_in)
        self.hp_prev_out = float(prev_out)
        return output

    def _lowpass_block(self, data, state_name, alpha):
        output = np.empty_like(data, dtype=np.float32)
        state = getattr(self, state_name)

        for index, sample in enumerate(data):
            state += alpha * (sample - state)
            output[index] = state

        setattr(self, state_name, float(state))
        return output

    def _thicken(self, data, amount):
        if amount <= 0.001:
            return data

        output = np.empty_like(data, dtype=np.float32)
        delay_length = self.delay_buffer.shape[0]
        delay_samples = max(32, min(self.delay_samples, delay_length - 1))
        pos = self.delay_pos
        feedback = 0.05 + (amount * 0.16)
        blend = amount * 0.38

        for index, sample in enumerate(data):
            read_index = (pos - delay_samples) % delay_length
            delayed = self.delay_buffer[read_index]
            output[index] = sample + (delayed * blend)
            self.delay_buffer[pos] = np.clip(sample + (delayed * feedback), -1.0, 1.0)
            pos = (pos + 1) % delay_length

        self.delay_pos = pos
        return output

    def process(self, data):
        try:
            source = np.asarray(data, dtype=np.float32)
            if source.size == 0:
                return source

            drive = self.drive / 100.0
            presence = self.presence / 100.0
            thickness = self.thickness / 100.0
            mix = self.mix / 100.0

            highpassed = self._highpass_block(source)
            body = self._lowpass_block(highpassed, "low_state", 0.075 + (thickness * 0.045))
            air_base = self._lowpass_block(highpassed, "air_state", 0.018 + (presence * 0.015))
            air = highpassed - air_base

            if self.preset == "Radio":
                shaped = (highpassed * 0.72) + (air * (0.55 + (presence * 0.95))) + (body * 0.08)
            elif self.preset == "Titan":
                shaped = (highpassed * 0.92) + (air * (0.20 + (presence * 0.45))) + (body * (0.32 + (thickness * 0.35)))
            else:
                shaped = (highpassed * 0.86) + (air * (0.42 + (presence * 0.72))) + (body * (0.18 + (thickness * 0.18)))

            drive_amount = 1.0 + (drive * 4.5)
            saturated = np.tanh(shaped * drive_amount) / np.tanh(drive_amount)
            thickened = self._thicken(saturated, thickness)

            wet = np.clip(thickened * self.output_gain, -1.0, 1.0)
            final = (source * (1.0 - mix)) + (wet * mix)
            return np.clip(final, -0.98, 0.98).astype(np.float32, copy=False)
        except Exception as exc:
            print(f"Neon Commander crashed: {exc}")
            return data

    def open_settings(self, parent):
        dialog = NeonCommanderDialog(parent, self)
        if dialog.ShowModal() == wx.ID_OK:
            dialog.apply_changes()
            self.save_settings()
        dialog.Destroy()


class NeonCommanderDialog(wx.Dialog):
    def __init__(self, parent, plugin):
        super().__init__(parent, title="Neon Commander Settings", size=(430, 420))
        self.plugin = plugin
        self.controls = {}

        panel = wx.Panel(self)
        panel_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer = wx.BoxSizer(wx.VERTICAL)

        panel_sizer.Add(wx.StaticText(panel, label="Preset"), 0, wx.LEFT | wx.TOP, 12)
        self.preset_choice = wx.Choice(panel, choices=list(PRESETS.keys()))
        self.preset_choice.SetStringSelection(plugin.preset)
        self.preset_choice.Bind(wx.EVT_CHOICE, self.on_preset_change)
        panel_sizer.Add(self.preset_choice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.controls["drive"] = self._add_slider(panel, panel_sizer, "Drive", plugin.drive)
        self.controls["presence"] = self._add_slider(panel, panel_sizer, "Presence", plugin.presence)
        self.controls["thickness"] = self._add_slider(panel, panel_sizer, "Thickness", plugin.thickness)
        self.controls["mix"] = self._add_slider(panel, panel_sizer, "Mix", plugin.mix)

        hint = wx.StaticText(
            panel,
            label="Broadcast = polished voice, Radio = comms style, Titan = heavier and thicker.",
        )
        hint.Wrap(360)
        panel_sizer.Add(hint, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, 12)

        button_row = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
        panel.SetSizer(panel_sizer)
        dialog_sizer.Add(panel, 1, wx.EXPAND | wx.ALL, 0)
        if button_row is not None:
            dialog_sizer.Add(button_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        self.SetSizerAndFit(dialog_sizer)

    def _add_slider(self, panel, root, label, value):
        text = wx.StaticText(panel, label=f"{label}: {value}")
        slider = wx.Slider(panel, value=value, minValue=0, maxValue=100)
        slider.Bind(wx.EVT_SLIDER, lambda event, t=text, name=label: t.SetLabel(f"{name}: {event.GetInt()}"))
        root.Add(text, 0, wx.LEFT | wx.TOP, 12)
        root.Add(slider, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)
        return {"label": label, "text": text, "slider": slider}

    def on_preset_change(self, event):
        values = PRESETS[self.preset_choice.GetStringSelection()]
        for key in ("drive", "presence", "thickness", "mix"):
            control = self.controls[key]
            value = values[key]
            control["slider"].SetValue(value)
            control["text"].SetLabel(f"{control['label']}: {value}")

    def apply_changes(self):
        preset = self.preset_choice.GetStringSelection() or "Broadcast"
        self.plugin.preset = preset
        self.plugin.drive = int(self.controls["drive"]["slider"].GetValue())
        self.plugin.presence = int(self.controls["presence"]["slider"].GetValue())
        self.plugin.thickness = int(self.controls["thickness"]["slider"].GetValue())
        self.plugin.mix = int(self.controls["mix"]["slider"].GetValue())
        self.plugin.delay_samples = PRESETS[preset]["delay_samples"]
        self.plugin.output_gain = PRESETS[preset]["output_gain"]
