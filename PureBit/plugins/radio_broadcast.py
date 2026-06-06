import os
import math
import numpy as np
import wx

from _plugin_utils import PluginControlDialog, load_settings, save_settings


PRESETS = {
    "AM Radio": {"bandwidth": 20, "static": 35, "crackle": 30, "grit": 45, "mix": 100},
    "Old Phonograph": {"bandwidth": 10, "static": 45, "crackle": 65, "grit": 55, "mix": 100},
    "Walkie-Talkie": {"bandwidth": 35, "static": 55, "crackle": 15, "grit": 75, "mix": 100},
    "Vintage FM": {"bandwidth": 75, "static": 12, "crackle": 8, "grit": 20, "mix": 90},
}
DEFAULTS = {"preset": "AM Radio", **PRESETS["AM Radio"]}


class Plugin:
    def __init__(self):
        self.name = "Radio Broadcast"
        self.enabled = False
        self.file_name = "radio_broadcast.py"
        self.settings_path = os.path.splitext(__file__)[0] + ".json"
        
        # Filter states
        self.hp_state = 0.0
        self.lp_state = 0.0
        self.prev_sample = 0.0
        
        # Crackle & Envelope states
        self.crackle_state = 0.0
        self.envelope = 0.0
        
        # RNG for noise and crackles
        self.rng = np.random.default_rng()
        
        self.preset = DEFAULTS["preset"]
        self.bandwidth = DEFAULTS["bandwidth"]
        self.static = DEFAULTS["static"]
        self.crackle = DEFAULTS["crackle"]
        self.grit = DEFAULTS["grit"]
        self.mix = DEFAULTS["mix"]
        self.load_settings()
        
    def apply_preset(self, name):
        values = PRESETS[name]
        self.preset = name
        self.bandwidth = values["bandwidth"]
        self.static = values["static"]
        self.crackle = values["crackle"]
        self.grit = values["grit"]
        self.mix = values["mix"]

    def load_settings(self):
        values = load_settings(self.settings_path, DEFAULTS)
        preset = values.get("preset", DEFAULTS["preset"])
        if preset not in PRESETS:
            preset = DEFAULTS["preset"]
        self.apply_preset(preset)
        self.bandwidth = int(values.get("bandwidth", self.bandwidth))
        self.static = int(values.get("static", self.static))
        self.crackle = int(values.get("crackle", self.crackle))
        self.grit = int(values.get("grit", self.grit))
        self.mix = int(values.get("mix", self.mix))

    def save_settings(self):
        save_settings(
            self.settings_path,
            {
                "preset": self.preset,
                "bandwidth": int(self.bandwidth),
                "static": int(self.static),
                "crackle": int(self.crackle),
                "grit": int(self.grit),
                "mix": int(self.mix),
            },
        )

    def process(self, data):
        source = np.asarray(data, dtype=np.float32)
        if source.size == 0:
            return source

        bandwidth = self.bandwidth / 100.0
        static_gain = (self.static / 100.0) * 0.14
        crackle_gain = (self.crackle / 100.0) * 0.28
        grit = self.grit / 100.0
        mix = self.mix / 100.0

        # Calculate highpass and lowpass coefficients dynamically based on bandwidth
        # AM Radio (Bandwidth=0) cutoffs: HP=400Hz, LP=2200Hz
        # Wide FM (Bandwidth=1) cutoffs: HP=100Hz, LP=9000Hz
        cutoff_hp = 400.0 - (bandwidth * 300.0)
        cutoff_lp = 2200.0 + (bandwidth * 6800.0)
        
        hp_alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff_hp / 48000.0)
        lp_alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff_lp / 48000.0)

        # Clicks probability (crackle density)
        click_prob = 0.0001 + (self.crackle / 100.0) * 0.003
        drive = 1.0 + grit * 4.8

        out = np.empty_like(source)
        hp_state = self.hp_state
        lp_state = self.lp_state
        prev_sample = self.prev_sample
        crackle_state = self.crackle_state
        envelope = self.envelope

        # Generate noise arrays in batches for maximum speed
        noise_samples = self.rng.normal(0.0, 0.05, size=source.size).astype(np.float32)
        click_check = self.rng.random(size=source.size).astype(np.float32)
        click_values = self.rng.uniform(-0.5, 0.5, size=source.size).astype(np.float32)

        for index, sample in enumerate(source):
            # 1. Update vocal envelope tracker (slow decay, fast attack)
            abs_sample = abs(sample)
            env_alpha = 0.15 if abs_sample > envelope else 0.01
            envelope += env_alpha * (abs_sample - envelope)

            # 2. 1-pole Highpass IIR filter (removes low-end rumble)
            hp_state = hp_state * (1.0 - hp_alpha) + (sample - prev_sample)
            prev_sample = sample
            hp_out = hp_state

            # 3. 1-pole Lowpass IIR filter (removes high-end sparkle)
            lp_state = lp_state * (1.0 - lp_alpha) + hp_out * lp_alpha
            filtered = lp_state

            # 4. AM Carrier Noise Hiss (modulated by signal envelope)
            hiss = noise_samples[index] * static_gain * (0.22 + 0.78 * min(1.0, envelope * 8.0))

            # 5. Dust Pop/Crackle (vinyl style)
            if click_check[index] < click_prob:
                crackle_state += click_values[index] * crackle_gain
            
            # exponential decay of crackle pulse
            crackle_state *= 0.86
            
            wet = filtered + hiss + crackle_state

            # 6. Tube saturation distortion
            if grit > 0.05:
                wet = np.tanh(wet * drive) / np.tanh(drive)

            out[index] = (sample * (1.0 - mix)) + (wet * mix)

        self.hp_state = float(hp_state)
        self.lp_state = float(lp_state)
        self.prev_sample = float(prev_sample)
        self.crackle_state = float(crackle_state)
        self.envelope = float(envelope)

        return np.clip(out, -0.98, 0.98).astype(np.float32, copy=False)

    def open_settings(self, parent):
        dialog = RadioBroadcastDialog(parent, self)
        result = dialog.ShowModal()
        if result == wx.ID_OK:
            values = dialog.get_slider_values()
            self.preset = dialog.get_selected_preset() or self.preset
            self.bandwidth = int(values["bandwidth"])
            self.static = int(values["static"])
            self.crackle = int(values["crackle"])
            self.grit = int(values["grit"])
            self.mix = int(values["mix"])
            self.save_settings()
        dialog.Destroy()


class RadioBroadcastDialog(PluginControlDialog):
    def __init__(self, parent, plugin):
        super().__init__(
            parent,
            title="Radio Broadcast Settings",
            preset_names=PRESETS.keys(),
            selected_preset=plugin.preset,
            slider_defs=[
                {"key": "bandwidth", "label": "Bandwidth (AM to FM)", "value": plugin.bandwidth},
                {"key": "static", "label": "Static Hiss", "value": plugin.static},
                {"key": "crackle", "label": "Dust Crackle", "value": plugin.crackle},
                {"key": "grit", "label": "Grit / Warmth", "value": plugin.grit},
                {"key": "mix", "label": "Mix", "value": plugin.mix},
            ],
            hint="Simulates retro AM/FM radios or walkie-talkies. Dust Crackle creates record pops. Static Hiss simulates radio signal hiss which increases when you talk (envelope tracking carrier hiss).",
        )
        if self.preset_choice is not None:
            self.preset_choice.Bind(wx.EVT_CHOICE, self.on_preset_change)

    def on_preset_change(self, event):
        self.set_slider_values(PRESETS[self.get_selected_preset()])
