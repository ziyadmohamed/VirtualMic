import ctypes
import os
import sys
import webbrowser

import keyboard
import numpy as np
import sounddevice as sd
import soundfile as sf
import wx

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PluginNG import PluginManager

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    from receiver import BmMicDrain, convert_float32_to_bmmic, open_bmmic_client
except Exception as exc:
    BmMicDrain = None
    convert_float32_to_bmmic = None
    open_bmmic_client = None
    BM_MIC_IMPORT_ERROR = exc
else:
    BM_MIC_IMPORT_ERROR = None


def is_bm_mic_device(name):
    lowered = name.lower()
    return "bm mic" in lowered or "virtual microphone" in lowered


def build_input_device_list():
    devices = sd.query_devices()
    preferred = []
    fallback = []

    for index, device in enumerate(devices):
        if device.get("max_input_channels", 0) <= 0:
            continue
        input_channels = max(1, min(2, int(device.get("max_input_channels", 1))))
        entry = (index, device.get("name", f"Input {index}"), input_channels)
        if is_bm_mic_device(entry[1]):
            fallback.append(entry)
        else:
            preferred.append(entry)

    return preferred or fallback


def find_bm_mic_label():
    devices = sd.query_devices()
    candidates = []

    for device in devices:
        name = device.get("name", "")
        if not is_bm_mic_device(name):
            continue
        score = 0
        if "bm mic audio" in name.lower():
            score += 30
        if device.get("default_samplerate") == 48000.0:
            score += 10
        candidates.append((score, name))

    if not candidates:
        return "BM Mic driver"

    candidates.sort(reverse=True)
    return candidates[0][1]


def normalize_audio_frames(audio_data):
    array = np.asarray(audio_data, dtype=np.float32)
    if array.ndim == 1:
        return array.astype(np.float32, copy=False)
    if array.ndim == 2 and array.shape[1] in (1, 2):
        return array.astype(np.float32, copy=False)
    raise ValueError(f"Unsupported audio buffer shape: {array.shape}")


def ensure_stereo_frames(audio_data):
    array = normalize_audio_frames(audio_data)
    if array.ndim == 1:
        return np.column_stack((array, array)).astype(np.float32, copy=False)
    if array.shape[1] == 1:
        return np.repeat(array, 2, axis=1).astype(np.float32, copy=False)
    return array[:, :2].astype(np.float32, copy=False)


class AudioEngine:
    def __init__(self):
        self.model = None
        self.lib = None
        self.stream = None
        self.driver = None
        self.bm_mic_drain = None
        self.is_running = False
        self.callback_error = None
        self.error_handler = None
        self.stream_channels = 1

        self.reduction_level = 1.0
        self.noise_reduction_enabled = True
        self.gain_db = 0.0
        self.reverb_on = False
        self.reverb_level = 0.4
        self.reverb_buffer = np.zeros((4800, 1), dtype=np.float32)
        self.is_recording = False
        self.recorded_frames = []
        self.current_gain = 1.0
        self.gate_threshold = 0.004
        self.fade_speed = 0.12

        self.plugin_manager = PluginManager()

        dll_path = os.path.join(BASE_DIR, "rnnoise.dll")
        try:
            self.lib = ctypes.CDLL(dll_path, winmode=0)
            self.lib.rnnoise_create.restype = ctypes.c_void_p
            self.lib.rnnoise_process_frame.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_float),
                ctypes.POINTER(ctypes.c_float),
            ]
            self.model = self.lib.rnnoise_create(None)
        except OSError:
            print("RNNoise DLL missing, continuing without AI denoise.")

    def set_error_handler(self, handler):
        self.error_handler = handler

    def apply_reverb(self, data):
        input_data = normalize_audio_frames(data)
        original_was_mono = input_data.ndim == 1
        frame_data = input_data[:, None] if original_was_mono else input_data

        decay = 0.35
        if self.reverb_buffer.shape[1] != frame_data.shape[1]:
            self.reverb_buffer = np.zeros((4800, frame_data.shape[1]), dtype=np.float32)

        self.reverb_buffer = np.roll(self.reverb_buffer, -len(frame_data), axis=0)
        self.reverb_buffer[-len(frame_data):] = frame_data + (self.reverb_buffer[:len(frame_data)] * decay)
        wet = frame_data + (self.reverb_buffer[-len(frame_data):] * self.reverb_level)
        return wet[:, 0] if original_was_mono else wet

    def process_noise_reduction(self, raw_input):
        if self.lib is None or self.model is None:
            return raw_input

        input_mono = (raw_input * 32768.0).astype(np.float32)
        in_ptr = input_mono.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        out_ptr = (ctypes.c_float * 480)()
        self.lib.rnnoise_process_frame(self.model, out_ptr, in_ptr)
        return np.array(out_ptr, dtype=np.float32) / 32768.0

    def audio_callback(self, indata, frames, time_info, status):
        _ = (frames, time_info, status)
        if not self.is_running:
            return

        try:
            capture = np.asarray(indata[:, : self.stream_channels], dtype=np.float32)
            raw_input = np.mean(capture, axis=1, dtype=np.float32)
            if self.noise_reduction_enabled:
                denoised = self.process_noise_reduction(raw_input)
                mixed = (denoised * self.reduction_level) + (raw_input * (1.0 - self.reduction_level))
                rms = np.sqrt(np.mean(mixed ** 2))
                target_gate = 1.0 if rms > self.gate_threshold else 0.0
                self.current_gain += (target_gate - self.current_gain) * self.fade_speed
                processed = mixed * self.current_gain
            else:
                processed = raw_input
            processed = self.plugin_manager.run_plugins(processed)
            processed = normalize_audio_frames(processed)

            if self.reverb_on:
                processed = self.apply_reverb(processed)

            gain_factor = 10 ** (self.gain_db / 20)
            final_output = np.clip(processed * gain_factor, -0.99, 0.99).astype(np.float32, copy=False)
            driver_frames = ensure_stereo_frames(final_output)

            if self.is_recording:
                self.recorded_frames.append(driver_frames.copy())

            if self.driver is None:
                raise RuntimeError("BM Mic driver is not open")

            converted = convert_float32_to_bmmic(
                driver_frames.tobytes(),
                input_channels=2,
                input_sample_rate=48000,
                gain=1.0,
            )
            if not self.driver.push_audio(converted):
                raise RuntimeError("Failed to inject audio into BM Mic")
        except Exception as exc:
            self.callback_error = str(exc)
            self.is_running = False
            if self.error_handler is not None:
                self.error_handler(self.callback_error)
            raise sd.CallbackAbort

    def start(self, in_id, input_channels=1):
        if BM_MIC_IMPORT_ERROR is not None:
            raise RuntimeError(f"BM Mic integration could not be loaded: {BM_MIC_IMPORT_ERROR}")

        self.stop()
        self.callback_error = None
        self.current_gain = 1.0
        self.stream_channels = max(1, min(2, int(input_channels)))
        self.reverb_buffer = np.zeros((4800, 1), dtype=np.float32)

        self.driver = open_bmmic_client()

        if BmMicDrain is not None:
            self.bm_mic_drain = BmMicDrain()
            try:
                self.bm_mic_drain.start()
            except Exception as exc:
                print(f"Warning: could not open BM Mic drain stream: {exc}")
                self.bm_mic_drain = None

        try:
            self.stream = sd.InputStream(
                device=in_id,
                samplerate=48000,
                blocksize=480,
                dtype="float32",
                channels=self.stream_channels,
                callback=self.audio_callback,
                latency="low",
            )
            self.stream.start()
            self.is_running = True
        except Exception:
            self.stop()
            raise

    def stop(self):
        self.is_running = False

        if self.stream:
            try:
                self.stream.stop()
            except Exception:
                pass
            try:
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        if self.bm_mic_drain:
            try:
                self.bm_mic_drain.close()
            except Exception:
                pass
            self.bm_mic_drain = None

        if self.driver:
            try:
                self.driver.close()
            except Exception:
                pass
            self.driver = None


class PureBit(wx.Frame):
    def __init__(self):
        super().__init__(None, title="PureBit", size=(500, 720))
        self.engine = AudioEngine()
        self.engine.set_error_handler(lambda message: wx.CallAfter(self.on_engine_error, message))
        self.auto_started_stream = False

        self.undo_stack = []
        self.redo_stack = []

        self.in_list = build_input_device_list()
        self.bm_mic_label = find_bm_mic_label()

        self.init_ui()
        self.create_menubar()
        self.setup_hotkeys()
        self.Bind(wx.EVT_CLOSE, self.on_close)

    def create_menubar(self):
        menubar = wx.MenuBar()

        edit_menu = wx.Menu()
        undo_item = edit_menu.Append(wx.ID_UNDO, "Undo (Toggle Filter)\tCtrl+Z")
        redo_item = edit_menu.Append(wx.ID_REDO, "Redo\tCtrl+Y")
        edit_menu.AppendSeparator()
        edit_menu.Append(wx.ID_ANY, "Clear Recording History").Enable(False)

        self.Bind(wx.EVT_MENU, self.on_undo, undo_item)
        self.Bind(wx.EVT_MENU, self.on_redo, redo_item)
        menubar.Append(edit_menu, "&Edit")

        self.effects_menu = wx.Menu()
        self.update_effects_menu()
        menubar.Append(self.effects_menu, "&Effects")

        driver_menu = wx.Menu()
        create_mics_item = driver_menu.Append(wx.ID_ANY, "Install Virtual Devices (Admin)")
        check_mics_item = driver_menu.Append(wx.ID_ANY, "Check Virtual Devices")
        remove_mics_item = driver_menu.Append(wx.ID_ANY, "Remove Virtual Devices (Admin)")

        self.Bind(wx.EVT_MENU, self.on_create_mics, create_mics_item)
        self.Bind(wx.EVT_MENU, self.on_check_mics, check_mics_item)
        self.Bind(wx.EVT_MENU, self.on_remove_mics, remove_mics_item)
        menubar.Append(driver_menu, "&Driver")

        about_menu = wx.Menu()
        about_app = about_menu.Append(wx.ID_ANY, "About App")
        user_guide = about_menu.Append(wx.ID_ANY, "User Guide")
        addons_guide = about_menu.Append(wx.ID_ANY, "Addons Guide")
        app_repo = about_menu.Append(wx.ID_ANY, "App Repository")

        about_menu.AppendSeparator()

        dev_menu = wx.Menu()
        jf_web = dev_menu.Append(wx.ID_ANY, "Jumping Fridge Website")
        tg_chan = dev_menu.Append(wx.ID_ANY, "Telegram Channel")
        about_menu.AppendSubMenu(dev_menu, "Developer")

        self.Bind(wx.EVT_MENU, lambda e: self.open_local_html("AboutApp.html"), about_app)
        self.Bind(wx.EVT_MENU, lambda e: self.open_local_html("Userguide.html"), user_guide)
        self.Bind(wx.EVT_MENU, lambda e: self.open_local_html("AddonsGuide.html"), addons_guide)
        self.Bind(wx.EVT_MENU, lambda e: webbrowser.open("https://github.com/DRCode22/PureBit/"), app_repo)
        self.Bind(wx.EVT_MENU, lambda e: webbrowser.open("https://jumpingfridge.gt.tc/"), jf_web)
        self.Bind(wx.EVT_MENU, lambda e: webbrowser.open("https://t.me/ultech_ar"), tg_chan)

        menubar.Append(about_menu, "&About")
        self.SetMenuBar(menubar)

    def update_effects_menu(self):
        for item in self.effects_menu.GetMenuItems():
            self.effects_menu.Remove(item)

        active_plugins = self.engine.plugin_manager.loaded_plugins
        if not active_plugins:
            self.effects_menu.Append(wx.ID_ANY, "No Plugins Found").Enable(False)
        else:
            for plugin in active_plugins:
                label = f"Toggle: {plugin.name}"
                item = self.effects_menu.AppendCheckItem(wx.ID_ANY, label)
                item.Check(plugin.enabled)
                self.Bind(wx.EVT_MENU, lambda evt, p=plugin: self.on_toggle_plugin_state(p), item)

                set_item = self.effects_menu.Append(wx.ID_ANY, f"  Settings: {plugin.name}")
                self.Bind(wx.EVT_MENU, lambda evt, p=plugin: p.open_settings(self), set_item)
                self.effects_menu.AppendSeparator()

    def on_toggle_plugin_state(self, plugin):
        self.undo_stack.append((plugin, plugin.enabled))
        self.redo_stack.clear()

        plugin.enabled = not plugin.enabled
        self.update_effects_menu()
        self.engine.plugin_manager.save_current_states()
        print(f"Filter '{plugin.name}' is now {'Enabled' if plugin.enabled else 'Disabled'}")

    def on_undo(self, e):
        if self.undo_stack:
            plugin, prev_state = self.undo_stack.pop()
            self.redo_stack.append((plugin, plugin.enabled))
            plugin.enabled = prev_state
            self.update_effects_menu()
            self.engine.plugin_manager.save_current_states()

    def on_redo(self, e):
        if self.redo_stack:
            plugin, next_state = self.redo_stack.pop()
            self.undo_stack.append((plugin, plugin.enabled))
            plugin.enabled = next_state
            self.update_effects_menu()
            self.engine.plugin_manager.save_current_states()

    def open_local_html(self, filename):
        path = os.path.join(BASE_DIR, filename)
        if os.path.exists(path):
            webbrowser.open(f"file:///{path}")
        else:
            wx.MessageBox(f"File not found: {filename}", "Error", wx.ICON_ERROR)

    def init_ui(self):
        panel = wx.Panel(self)
        self.main_vbox = wx.BoxSizer(wx.VERTICAL)
        panel.SetBackgroundColour("#F0F4F8")

        header = wx.StaticText(panel, label="PUREBIT")
        header.SetFont(wx.Font(22, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.main_vbox.Add(header, 0, wx.ALL | wx.CENTER, 20)

        self.create_section_label(panel, "Source Microphone:")
        self.in_cb = wx.ComboBox(
            panel,
            choices=[device[1] for device in self.in_list],
            style=wx.CB_READONLY,
            name="Source Microphone",
        )
        if self.in_list:
            self.in_cb.SetSelection(self.find_default_input_selection())
        self.main_vbox.Add(self.in_cb, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)

        self.create_section_label(panel, "Output Target:")
        self.output_target = wx.StaticText(panel, label=self.bm_mic_label)
        self.output_target.SetForegroundColour("#1E8449")
        self.output_target.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.main_vbox.Add(self.output_target, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)

        output_hint = wx.StaticText(panel, label="Processed audio is injected directly into the BM Mic driver. Stereo effects can widen the final stream.")
        output_hint.SetForegroundColour("#546E7A")
        output_hint.Wrap(450)
        self.main_vbox.Add(output_hint, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)

        self.sld_red = self.create_slider(panel, "AI Noise Reduction Strength", 100)

        self.noise_check = wx.CheckBox(panel, label="Enable AI Noise Removal")
        self.noise_check.SetValue(True)
        self.noise_check.Bind(wx.EVT_CHECKBOX, self.on_noise_check)
        self.main_vbox.Add(self.noise_check, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)

        self.sld_gain = self.create_slider(panel, "Output Volume Gain", 0, -10, 20)

        self.main_vbox.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 10)

        rev_h_box = wx.BoxSizer(wx.HORIZONTAL)
        self.rev_check = wx.CheckBox(panel, label="Enable Echo (F1)")
        self.rev_check.Bind(wx.EVT_CHECKBOX, self.on_reverb_check)
        rev_h_box.Add(self.rev_check, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 15)

        self.rev_toggle_btn = wx.Button(panel, label="Echo settings", size=(120, 30))
        self.rev_toggle_btn.Bind(wx.EVT_BUTTON, self.on_toggle_rev_panel)
        rev_h_box.AddStretchSpacer()
        rev_h_box.Add(self.rev_toggle_btn, 0, wx.RIGHT, 15)
        self.main_vbox.Add(rev_h_box, 0, wx.EXPAND | wx.BOTTOM, 10)

        self.rev_panel = wx.Panel(panel)
        self.rev_panel.SetBackgroundColour("#E1E8ED")
        rev_p_vbox = wx.BoxSizer(wx.VERTICAL)
        self.sld_rev_lvl = wx.Slider(self.rev_panel, value=40, minValue=0, maxValue=100, name="Echo Intensity Slider")
        self.sld_rev_lvl.Bind(wx.EVT_SLIDER, self.on_rev_lvl_change)
        rev_p_vbox.Add(wx.StaticText(self.rev_panel, label="Echo intensity:"), 0, wx.LEFT | wx.TOP, 5)
        rev_p_vbox.Add(self.sld_rev_lvl, 0, wx.EXPAND | wx.ALL, 5)
        self.rev_panel.SetSizer(rev_p_vbox)
        self.rev_panel.Hide()
        self.main_vbox.Add(self.rev_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)

        self.main_vbox.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 10)

        rec_box = wx.BoxSizer(wx.HORIZONTAL)
        self.rec_btn = wx.Button(panel, label="Start recording", size=(-1, 45))
        self.rec_btn.Bind(wx.EVT_BUTTON, self.on_record_click)

        rec_box.Add(self.rec_btn, 1, wx.LEFT | wx.RIGHT, 10)
        self.main_vbox.Add(rec_box, 0, wx.EXPAND | wx.BOTTOM, 15)

        effects_btn_box = wx.BoxSizer(wx.HORIZONTAL)

        self.plug_btn = wx.Button(panel, label="Plugins Manager", size=(-1, 45))
        self.plug_btn.SetBackgroundColour("#34495E")
        self.plug_btn.SetForegroundColour("white")
        self.plug_btn.Bind(wx.EVT_BUTTON, self.on_open_plugins)

        effects_btn_box.Add(self.plug_btn, 1, wx.EXPAND, 0)
        self.main_vbox.Add(effects_btn_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)

        self.btn_main = wx.Button(panel, label="START BM MIC STREAM", size=(-1, 65))
        self.btn_main.SetBackgroundColour("#2ECC71")
        self.btn_main.SetForegroundColour("white")
        self.btn_main.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.btn_main.Bind(wx.EVT_BUTTON, self.on_main_toggle)
        self.main_vbox.Add(self.btn_main, 0, wx.EXPAND | wx.ALL, 15)

        if not self.in_list:
            self.in_cb.Disable()
            self.btn_main.Disable()

        panel.SetSizer(self.main_vbox)
        self.Layout()

    def create_section_label(self, panel, text):
        label = wx.StaticText(panel, label=text)
        label.SetForegroundColour("#546E7A")
        self.main_vbox.Add(label, 0, wx.LEFT | wx.TOP, 10)

    def create_slider(self, panel, label, default_value, min_v=0, max_v=100):
        value_label = wx.StaticText(panel, label=f"{label}: {default_value}")
        self.main_vbox.Add(value_label, 0, wx.LEFT | wx.TOP, 10)
        slider = wx.Slider(panel, value=default_value, minValue=min_v, maxValue=max_v, name=label)
        slider.Bind(wx.EVT_SLIDER, lambda e: self.on_slider_move(e, value_label, label))
        self.main_vbox.Add(slider, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 15)
        return slider

    def find_default_input_selection(self):
        try:
            default_input = sd.default.device[0]
        except Exception:
            default_input = None

        for choice_index, (device_index, _, _) in enumerate(self.in_list):
            if device_index == default_input:
                return choice_index
        return 0

    def on_slider_move(self, event, label, name):
        value = event.GetEventObject().GetValue()
        label.SetLabel(f"{name}: {value}")
        if "Reduction" in name:
            self.engine.reduction_level = value / 100.0
        else:
            self.engine.gain_db = float(value)

    def on_reverb_check(self, e):
        self.engine.reverb_on = self.rev_check.IsChecked()

    def on_noise_check(self, e):
        self.engine.noise_reduction_enabled = self.noise_check.IsChecked()
        if self.engine.noise_reduction_enabled:
            self.sld_red.Enable()
        else:
            self.sld_red.Disable()

    def on_toggle_rev_panel(self, e):
        if self.rev_panel.IsShown():
            self.rev_panel.Hide()
            self.rev_toggle_btn.SetLabel("Echo settings")
        else:
            self.rev_panel.Show()
            self.rev_toggle_btn.SetLabel("Hide settings")
        self.Layout()

    def on_rev_lvl_change(self, e):
        self.engine.reverb_level = self.sld_rev_lvl.GetValue() / 100.0

    def on_open_plugins(self, e):
        from PluginNG import PluginManagerDialog

        dlg = PluginManagerDialog(self, self.engine.plugin_manager)
        dlg.ShowModal()
        dlg.Destroy()
        self.update_effects_menu()

    def on_record_click(self, e):
        self.toggle_record_logic()

    def save_recording_automatically(self):
        if not self.engine.recorded_frames:
            return
        
        recording_dir = os.path.join(BASE_DIR, "recording")
        if not os.path.exists(recording_dir):
            try:
                os.makedirs(recording_dir)
            except Exception as e:
                wx.MessageBox(f"Failed to create recording directory:\n{e}", "Error", wx.ICON_ERROR)
                return
            
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"recording_{timestamp}.wav"
        path = os.path.join(recording_dir, filename)
        
        try:
            full_data = np.concatenate(self.engine.recorded_frames, axis=0)
            sf.write(path, full_data, 48000)
            wx.MessageBox(f"Recording saved automatically to:\n{path}", "Recording Saved", wx.OK | wx.ICON_INFORMATION)
        except Exception as e:
            wx.MessageBox(f"Failed to save recording:\n{e}", "Error", wx.ICON_ERROR)
        
        self.engine.recorded_frames = []

    def toggle_record_logic(self):
        if not self.engine.is_recording:
            self.engine.recorded_frames = []
            self.auto_started_stream = False
            
            # If the engine is not running, start it automatically!
            if not self.engine.is_running:
                selected = self.in_cb.GetSelection()
                if selected == -1:
                    selected = self.find_default_input_selection()
                    self.in_cb.SetSelection(selected)
                
                try:
                    device_index, _, input_channels = self.in_list[selected]
                    self.engine.start(device_index, input_channels)
                    self.auto_started_stream = True
                    self.btn_main.SetLabel("STOP BM MIC STREAM")
                    self.btn_main.SetBackgroundColour("#E74C3C")
                except Exception as exc:
                    self.engine.stop()
                    wx.MessageBox(f"Unable to start stream for recording:\n{exc}", "PureBit", wx.ICON_ERROR)
                    return
            
            self.engine.is_recording = True
            self.rec_btn.SetLabel("Stop recording")
            self.rec_btn.SetBackgroundColour("#FFEB3B")
        else:
            self.engine.is_recording = False
            self.rec_btn.SetLabel("Start recording")
            self.rec_btn.SetBackgroundColour("#FFFFFF")
            
            # Save the recording automatically
            self.save_recording_automatically()
            
            # If we auto-started the stream, stop it now
            if self.auto_started_stream:
                self.engine.stop()
                self.btn_main.SetLabel("START BM MIC STREAM")
                self.btn_main.SetBackgroundColour("#2ECC71")
                self.auto_started_stream = False
                
        self.Layout()

    def setup_hotkeys(self):
        keyboard.add_hotkey("f1", self.global_reverb_toggle)
        keyboard.add_hotkey("ctrl+r", self.global_record_toggle)

    def global_reverb_toggle(self):
        wx.CallAfter(self.rev_check.SetValue, not self.rev_check.IsChecked())
        self.engine.reverb_on = not self.engine.reverb_on

    def global_record_toggle(self):
        wx.CallAfter(self.toggle_record_logic)

    def on_engine_error(self, message):
        self.engine.stop()
        self.btn_main.SetLabel("START BM MIC STREAM")
        self.btn_main.SetBackgroundColour("#2ECC71")
        wx.MessageBox(f"BM Mic streaming stopped:\n{message}", "PureBit", wx.ICON_ERROR)

    def on_main_toggle(self, e):
        if not self.engine.is_running:
            if not self.in_list:
                wx.MessageBox("No usable input microphone was found.", "PureBit", wx.ICON_ERROR)
                return

            selected = self.in_cb.GetSelection()
            if selected == -1:
                selected = self.find_default_input_selection()
                self.in_cb.SetSelection(selected)

            try:
                device_index, _, input_channels = self.in_list[selected]
                self.engine.start(device_index, input_channels)
            except Exception as exc:
                self.engine.stop()
                wx.MessageBox(f"Unable to start BM Mic stream:\n{exc}", "PureBit", wx.ICON_ERROR)
                return

            self.btn_main.SetLabel("STOP BM MIC STREAM")
            self.btn_main.SetBackgroundColour("#E74C3C")
        else:
            self.engine.stop()
            self.btn_main.SetLabel("START BM MIC STREAM")
            self.btn_main.SetBackgroundColour("#2ECC71")

    def on_close(self, event):
        self.engine.stop()
        keyboard.unhook_all_hotkeys()
        event.Skip()

    def on_create_mics(self, event):
        script_path = os.path.join(REPO_ROOT, "add_virtual_mics.py")
        if not os.path.exists(script_path):
            wx.MessageBox(f"Script not found: {script_path}", "Error", wx.ICON_ERROR)
            return
            
        try:
            import subprocess
            cmd = f'Start-Process python -ArgumentList \\"{script_path} 1\\" -Verb RunAs'
            subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd], shell=True)
            wx.MessageBox("Elevated device creator started. Please click 'Yes' on the UAC prompt to allow device creation.", "Virtual Device Creator", wx.ICON_INFORMATION)
        except Exception as e:
            wx.MessageBox(f"Failed to launch device creator:\n{e}", "Error", wx.ICON_ERROR)

    def on_remove_mics(self, event):
        script_path = os.path.join(REPO_ROOT, "add_virtual_mics.py")
        if not os.path.exists(script_path):
            wx.MessageBox(f"Script not found: {script_path}", "Error", wx.ICON_ERROR)
            return
            
        try:
            import subprocess
            cmd = f'Start-Process python -ArgumentList \\"{script_path} --remove\\" -Verb RunAs'
            subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd], shell=True)
            wx.MessageBox("Elevated device cleaner started. Please click 'Yes' on the UAC prompt to allow device removal.", "Virtual Device Cleaner", wx.ICON_INFORMATION)
        except Exception as e:
            wx.MessageBox(f"Failed to launch device cleaner:\n{e}", "Error", wx.ICON_ERROR)

    def on_check_mics(self, event):
        try:
            import subprocess
            ps_cmd = (
                "Get-CimInstance Win32_PnPEntity | "
                "Where-Object { $_.DeviceID -like 'ROOT\\\\MEDIA*' -and ($_.Name -like '*BM Mic*' -or $_.Name -like '*Simple Audio*') } | "
                "Select-Object Name, DeviceID, Status | Format-Table"
            )
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd]
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8', errors='ignore').strip()
            
            if not output:
                output = "No BM virtual microphone devices found."
                
            wx.MessageBox(f"Currently installed devices:\n\n{output}", "Virtual Mic Status", wx.ICON_INFORMATION)
        except Exception as e:
            wx.MessageBox(f"Failed to query devices:\n{e}", "Error", wx.ICON_ERROR)


if __name__ == "__main__":
    app = wx.App()
    PureBit().Show()
    app.MainLoop()
