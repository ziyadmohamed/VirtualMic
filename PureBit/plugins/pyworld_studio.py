import os
import numpy as np
import soundfile as sf
import sounddevice as sd
import wx

from _plugin_utils import PluginControlDialog, load_settings, save_settings


DEFAULTS = {
    "shift": 0,
    "formant": 0,
    "robotize": 0,
}


class Plugin:
    def __init__(self):
        self.name = "PyWorld Studio"
        self.enabled = False
        self.file_name = "pyworld_studio.py"
        self.settings_path = os.path.splitext(__file__)[0] + ".json"
        
        self.shift = DEFAULTS["shift"]
        self.formant = DEFAULTS["formant"]
        self.robotize = DEFAULTS["robotize"]
        self.load_settings()

    def load_settings(self):
        values = load_settings(self.settings_path, DEFAULTS)
        self.shift = int(values.get("shift", 0))
        self.formant = int(values.get("formant", 0))
        self.robotize = int(values.get("robotize", 0))

    def save_settings(self):
        save_settings(
            self.settings_path,
            {
                "shift": int(self.shift),
                "formant": int(self.formant),
                "robotize": int(self.robotize),
            },
        )

    def process(self, data):
        # PyWorld is designed for offline/batch processing of recorded files.
        # This plugin passes real-time audio through untouched,
        # but provides the PyWorld Studio interface to process your recordings.
        return data

    def open_settings(self, parent):
        dialog = PyWorldStudioDialog(parent, self)
        dialog.ShowModal()
        dialog.Destroy()


class PyWorldStudioDialog(PluginControlDialog):
    def __init__(self, parent, plugin):
        self.plugin = plugin
        super().__init__(
            parent,
            title="PyWorld Vocal Studio",
            slider_defs=[
                {"key": "shift", "label": "Pitch Shift (Semitones)", "value": plugin.shift, "min": -12, "max": 12},
                {"key": "formant", "label": "Formant Shift (%)", "value": plugin.formant, "min": -50, "max": 50},
            ],
            hint="PyWorld uses high-quality vocoder analysis (WORLD model) for natural voice modifications. Select Pitch Shift or Formant Shift (stretching the vocal tract envelope to sound older/younger/different gender) and click process.",
            size=(480, 620),
        )
        
        panel = next((child for child in self.GetChildren() if isinstance(child, wx.Panel)), None)
        if panel is not None:
            panel_sizer = panel.GetSizer()
            
            # Robotize Checkbox
            self.chk_robot = wx.CheckBox(panel, label="Robotize Voice (Flat pitch)")
            self.chk_robot.SetValue(bool(plugin.robotize))
            panel_sizer.Add(self.chk_robot, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
            
            # Latest file info
            self.file_label = wx.StaticText(panel, label=self._get_latest_file_label())
            self.file_label.Wrap(420)
            panel_sizer.Add(self.file_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 15)
            
            # Buttons sizer
            btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
            self.btn_process = wx.Button(panel, label="Process Latest")
            self.btn_play_original = wx.Button(panel, label="Play Original")
            self.btn_play_processed = wx.Button(panel, label="Play Processed")
            
            btn_sizer.Add(self.btn_process, 1, wx.RIGHT, 6)
            btn_sizer.Add(self.btn_play_original, 1, wx.LEFT | wx.RIGHT, 6)
            btn_sizer.Add(self.btn_play_processed, 1, wx.LEFT, 6)
            
            panel_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, 12)
            
            # Bind events
            self.btn_process.Bind(wx.EVT_BUTTON, self.on_process)
            self.btn_play_original.Bind(wx.EVT_BUTTON, self.on_play_original)
            self.btn_play_processed.Bind(wx.EVT_BUTTON, self.on_play_processed)
            
            self.chk_robot.Bind(wx.EVT_CHECKBOX, self.on_robot_toggle)
            
            # Disable play processed until a file is processed
            self.processed_path = None
            self.btn_play_processed.Enable(False)
            
            # Find latest file
            self.latest_filepath = self._find_latest_recording()
            if not self.latest_filepath:
                self.btn_process.Enable(False)
                self.btn_play_original.Enable(False)
                
            self.SetSizerAndFit(self.GetSizer())
            
    def _find_latest_recording(self):
        # BASE_DIR is PureBit folder
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        recording_dir = os.path.join(base_dir, "recording")
        if not os.path.exists(recording_dir):
            return None
            
        files = [os.path.join(recording_dir, f) for f in os.listdir(recording_dir) if f.endswith(".wav") and not f.endswith("_processed.wav")]
        if not files:
            return None
            
        files.sort(key=os.path.getmtime)
        return files[-1]

    def _get_latest_file_label(self):
        path = self._find_latest_recording()
        if not path:
            return "No recordings found yet in recording/ folder."
        return f"Target File: {os.path.basename(path)}"

    def on_robot_toggle(self, event):
        self.plugin.robotize = int(self.chk_robot.GetValue())
        self.plugin.save_settings()

    def on_process(self, event):
        if not self.latest_filepath:
            return
            
        self.plugin.shift = self.controls["shift"]["slider"].GetValue()
        self.plugin.formant = self.controls["formant"]["slider"].GetValue()
        self.plugin.robotize = int(self.chk_robot.GetValue())
        self.plugin.save_settings()
        
        # Open ProgressDialog
        progress = wx.ProgressDialog(
            "Vocoding Vocal...",
            "Running PyWorld Analysis (Dio + CheapTrick + D4C)... Please wait.",
            parent=self,
            style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE
        )
        
        try:
            import pyworld as pw
            
            # 1. Load Audio
            data, fs = sf.read(self.latest_filepath, always_2d=True)
            mono = np.mean(data, axis=1).astype(np.float64)
            
            progress.Update(30, "Analyzing fundamental frequency (F0)...")
            
            # 2. F0 estimation
            # Use dio + stoneMask or harvest. harvest is higher quality but a bit slower.
            # Since it's a short recording, harvest is perfect.
            f0, t = pw.harvest(mono, fs)
            
            progress.Update(60, "Extracting spectral envelope & aperiodicity...")
            
            # 3. Cheaptrick and D4C analysis
            sp = pw.cheaptrick(mono, f0, t, fs)
            ap = pw.d4c(mono, f0, t, fs)
            
            progress.Update(80, "Applying pitch & formant shifts...")
            
            # 4. Apply Pitch Shift
            semitones = float(self.plugin.shift)
            pitch_ratio = 2.0 ** (semitones / 12.0)
            
            if self.plugin.robotize:
                # Flat voiced pitch at 110Hz for robotic effect
                f0_new = np.where(f0 > 0.0, 110.0, 0.0)
            else:
                f0_new = f0 * pitch_ratio
                
            # 5. Apply Formant Shift
            formant_shift_pct = float(self.plugin.formant)
            if abs(formant_shift_pct) > 0.05:
                # Scale factor e.g., +20% -> 1.20, -20% -> 0.80
                formant_scale = 1.0 + (formant_shift_pct / 100.0)
                f_scale = 1.0 / formant_scale
                
                num_freqs = sp.shape[1]
                freqs = np.arange(num_freqs, dtype=np.float64)
                new_freqs = freqs * f_scale
                
                # Resample spectral envelope along the frequency axis
                for i in range(sp.shape[0]):
                    sp[i] = np.interp(new_freqs, freqs, sp[i], right=0.0)
            
            progress.Update(90, "Synthesizing vocal waveform...")
            
            # 6. Synthesize
            synthesized = pw.synthesize(f0_new, sp, ap, fs)
            synthesized = np.clip(synthesized, -0.98, 0.98).astype(np.float32)
            
            # Convert back to stereo (just duplicate mono channels)
            out_stereo = np.column_stack((synthesized, synthesized))
            
            # Save processed file
            base, ext = os.path.splitext(self.latest_filepath)
            self.processed_path = base + "_processed.wav"
            sf.write(self.processed_path, out_stereo, fs)
            
            progress.Update(100, "Done!")
            progress.Destroy()
            
            self.btn_play_processed.Enable(True)
            wx.MessageBox(f"Processed file saved to:\n{self.processed_path}", "Vocoding Complete", wx.OK | wx.ICON_INFORMATION)
            
        except Exception as e:
            if progress:
                progress.Destroy()
            wx.MessageBox(f"Vocoding failed:\n{e}", "Error", wx.ICON_ERROR)

    def on_play_original(self, event):
        if self.latest_filepath and os.path.exists(self.latest_filepath):
            try:
                sd.stop()
                data, fs = sf.read(self.latest_filepath)
                sd.play(data, fs)
            except Exception as e:
                wx.MessageBox(f"Could not play audio:\n{e}", "Error", wx.ICON_ERROR)

    def on_play_processed(self, event):
        if self.processed_path and os.path.exists(self.processed_path):
            try:
                sd.stop()
                data, fs = sf.read(self.processed_path)
                sd.play(data, fs)
            except Exception as e:
                wx.MessageBox(f"Could not play audio:\n{e}", "Error", wx.ICON_ERROR)
