import json
import os

import wx


def load_settings(settings_path, defaults):
    values = dict(defaults)
    if not os.path.exists(settings_path):
        return values

    try:
        with open(settings_path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except Exception:
        return values

    if isinstance(loaded, dict):
        values.update(loaded)
    return values


def save_settings(settings_path, values):
    with open(settings_path, "w", encoding="utf-8") as handle:
        json.dump(values, handle, indent=2)


class PluginControlDialog(wx.Dialog):
    def __init__(
        self,
        parent,
        title,
        slider_defs,
        preset_names=None,
        selected_preset=None,
        hint=None,
        size=(430, 420),
    ):
        super().__init__(parent, title=title, size=size)
        self.controls = {}

        panel = wx.Panel(self)
        panel_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer = wx.BoxSizer(wx.VERTICAL)

        self.preset_choice = None
        if preset_names:
            panel_sizer.Add(wx.StaticText(panel, label="Preset"), 0, wx.LEFT | wx.TOP, 12)
            self.preset_choice = wx.Choice(panel, choices=list(preset_names))
            if selected_preset:
                self.preset_choice.SetStringSelection(selected_preset)
            panel_sizer.Add(self.preset_choice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        for slider_def in slider_defs:
            self._add_slider(panel, panel_sizer, slider_def)

        if hint:
            help_text = wx.StaticText(panel, label=hint)
            help_text.Wrap(360)
            panel_sizer.Add(help_text, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, 12)

        panel.SetSizer(panel_sizer)
        dialog_sizer.Add(panel, 1, wx.EXPAND, 0)

        button_row = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
        if button_row is not None:
            dialog_sizer.Add(button_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.SetSizerAndFit(dialog_sizer)

    def _add_slider(self, panel, sizer, slider_def):
        key = slider_def["key"]
        label = slider_def["label"]
        value = int(slider_def["value"])
        minimum = int(slider_def.get("min", 0))
        maximum = int(slider_def.get("max", 100))

        text = wx.StaticText(panel, label=f"{label}: {value}")
        slider = wx.Slider(panel, value=value, minValue=minimum, maxValue=maximum)
        slider.Bind(wx.EVT_SLIDER, lambda event, t=text, name=label: t.SetLabel(f"{name}: {event.GetInt()}"))

        sizer.Add(text, 0, wx.LEFT | wx.TOP, 12)
        sizer.Add(slider, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        self.controls[key] = {"label": label, "text": text, "slider": slider}

    def set_slider_values(self, values):
        for key, value in values.items():
            if key not in self.controls:
                continue
            control = self.controls[key]
            control["slider"].SetValue(int(value))
            control["text"].SetLabel(f"{control['label']}: {int(value)}")

    def get_slider_values(self):
        return {key: control["slider"].GetValue() for key, control in self.controls.items()}

    def get_selected_preset(self):
        if self.preset_choice is None:
            return None
        return self.preset_choice.GetStringSelection()
