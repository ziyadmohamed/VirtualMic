import os
import importlib.util
import sys
import wx
import numpy as np
import json


def load_module_from_path(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def normalize_audio_buffer(audio_data):
    array = np.asarray(audio_data, dtype=np.float32)
    if array.ndim == 1:
        return array.astype(np.float32, copy=False)
    if array.ndim == 2 and array.shape[1] in (1, 2):
        return array.astype(np.float32, copy=False)
    raise ValueError(f"Unsupported audio buffer shape: {array.shape}")


def expand_channels(audio_data, target_channels):
    array = normalize_audio_buffer(audio_data)
    if array.ndim == 1:
        array = array[:, None]

    if array.shape[1] == target_channels:
        return array

    if array.shape[1] == 1 and target_channels == 2:
        return np.repeat(array, 2, axis=1)

    raise ValueError(f"Cannot expand {array.shape[1]} channel(s) to {target_channels}")

class PluginManager:
    def __init__(self):
        self.plugins_folder = os.path.join(os.path.dirname(__file__), "plugins")
        self.settings_file = os.path.join(os.path.dirname(__file__), "settings.json")
        
        if not os.path.exists(self.plugins_folder):
            os.makedirs(self.plugins_folder)
        
        self.loaded_plugins = []
        self.refresh_plugins()

    def load_saved_states(self):

        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    return json.load(f).get("plugin_states", {})
            except:
                return {}
        return {}

    def save_current_states(self):

        states = {p.file_name: p.enabled for p in self.loaded_plugins}
        data = {"plugin_states": states}
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def refresh_plugins(self):
        saved_states = self.load_saved_states()
        self.loaded_plugins = []
        if self.plugins_folder not in sys.path:
            sys.path.insert(0, self.plugins_folder)
        importlib.invalidate_caches()

        helper_path = os.path.join(self.plugins_folder, "_plugin_utils.py")
        if os.path.exists(helper_path):
            try:
                load_module_from_path("_plugin_utils", helper_path)
            except Exception as e:
                print(f"Error loading _plugin_utils.py: {e}")
                return
        
        for filename in sorted(os.listdir(self.plugins_folder)):
            if filename.endswith(".py") and filename != "__init__.py" and not filename.startswith("_"):
                try:
                    path = os.path.join(self.plugins_folder, filename)
                    module = load_module_from_path(filename[:-3], path)
                    
                    if hasattr(module, "Plugin"):
                        instance = module.Plugin()
                        instance.file_name = filename

                        instance.enabled = saved_states.get(filename, instance.enabled)
                        self.loaded_plugins.append(instance)
                except Exception as e:
                    print(f"Error loading {filename}: {e}")

        self.loaded_plugins.sort(key=lambda plugin: (int(getattr(plugin, "process_stage", 0)), plugin.file_name.lower()))

    def run_plugins(self, audio_data):
        audio_data = normalize_audio_buffer(audio_data)
        for plugin in self.loaded_plugins:
            if plugin.enabled:
                try:
                    if audio_data.ndim == 2 and audio_data.shape[1] > 1 and not getattr(plugin, "supports_stereo", False):
                        mono_input = np.mean(audio_data, axis=1, dtype=np.float32)
                        processed = plugin.process(mono_input.copy())
                        processed = normalize_audio_buffer(processed)
                        if processed.shape[0] != audio_data.shape[0]:
                            raise ValueError(
                                f"{plugin.file_name} returned {processed.shape[0]} frames for {audio_data.shape[0]} input frames"
                            )
                        audio_data = expand_channels(processed, audio_data.shape[1])
                    else:
                        processed = plugin.process(audio_data.copy())
                        processed = normalize_audio_buffer(processed)
                        if processed.shape[0] != audio_data.shape[0]:
                            raise ValueError(
                                f"{plugin.file_name} returned {processed.shape[0]} frames for {audio_data.shape[0]} input frames"
                            )
                        if audio_data.ndim == 2 and processed.ndim == 1:
                            audio_data = expand_channels(processed, audio_data.shape[1])
                        else:
                            audio_data = processed
                except Exception as e:
                    print(f"Plugin {plugin.file_name} crashed: {e}")
        return audio_data

class PluginManagerDialog(wx.Dialog):
    def __init__(self, parent, manager):
        super().__init__(parent, title="Plugins Manager", size=(450, 400))
        self.manager = manager
        
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.list.InsertColumn(0, "Plugin Name", width=200)
        self.list.InsertColumn(1, "Status", width=100)
        
        self.update_list()
        
        vbox.Add(self.list, 1, wx.EXPAND | wx.ALL, 10)
        
        btn_hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        self.toggle_btn = wx.Button(panel, label="Enable/Disable")
        self.toggle_btn.Bind(wx.EVT_BUTTON, self.on_toggle)

        self.settings_btn = wx.Button(panel, label="Settings")
        self.settings_btn.Bind(wx.EVT_BUTTON, self.on_settings)
        
        self.refresh_btn = wx.Button(panel, label="Refresh Folder")
        self.refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        
        self.close_btn = wx.Button(panel, label="Close")
        self.close_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_OK))
        
        btn_hbox.Add(self.toggle_btn, 1, wx.ALL, 5)
        btn_hbox.Add(self.settings_btn, 1, wx.ALL, 5)
        btn_hbox.Add(self.refresh_btn, 1, wx.ALL, 5)
        btn_hbox.Add(self.close_btn, 1, wx.ALL, 5)
        
        vbox.Add(btn_hbox, 0, wx.EXPAND | wx.BOTTOM, 10)
        
        panel.SetSizer(vbox)

    def update_list(self):
        self.list.DeleteAllItems()
        for idx, p in enumerate(self.manager.loaded_plugins):
            self.list.InsertItem(idx, p.name)
            status = "Active" if p.enabled else "Disabled"
            self.list.SetItem(idx, 1, status)

    def on_toggle(self, e):
        idx = self.list.GetFirstSelected()
        if idx != -1:
            plugin = self.manager.loaded_plugins[idx]
            plugin.enabled = not plugin.enabled
            self.update_list()

            self.manager.save_current_states()

    def on_settings(self, e):
        idx = self.list.GetFirstSelected()
        if idx == -1:
            return
        plugin = self.manager.loaded_plugins[idx]
        if hasattr(plugin, "open_settings"):
            plugin.open_settings(self.GetParent())

    def on_refresh(self, e):
        self.manager.refresh_plugins()
        self.update_list()
