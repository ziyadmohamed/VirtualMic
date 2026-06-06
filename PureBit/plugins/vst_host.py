import os
import numpy as np
import wx
import base64
import json

from _plugin_utils import PluginControlDialog, load_settings, save_settings

DEFAULTS = {
    "vst_path": "",
    "mix": 100,
    "vst_state_b64": "",
}

def scan_system_vst3s():
    # Standard VST3 directories on Windows
    dirs = [
        r"C:\Program Files\Common Files\VST3",
        r"C:\Program Files (x86)\Common Files\VST3",
    ]
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        dirs.append(os.path.join(user_profile, r"AppData\Local\Programs\Common\VST3"))
    
    # Waves specific folders (V11 to V15)
    dirs.extend([
        r"C:\Program Files\Waves\Plug-Ins V15",
        r"C:\Program Files\Waves\Plug-Ins V14",
        r"C:\Program Files\Waves\Plug-Ins V13",
        r"C:\Program Files\Waves\Plug-Ins V12",
        r"C:\Program Files\Waves\Plug-Ins V11",
    ])
    
    found_plugins = {}
    for d in dirs:
        if not os.path.exists(d):
            continue
        for root, subdirs, files in os.walk(d):
            # Scan files ending in .vst3
            for name in files:
                if name.lower().endswith(".vst3"):
                    full_path = os.path.join(root, name)
                    base_name = os.path.splitext(name)[0]
                    if base_name not in found_plugins:
                        found_plugins[base_name] = os.path.abspath(full_path)
            # Scan directories ending in .vst3 (bundle-style VST3)
            for name in subdirs:
                if name.lower().endswith(".vst3"):
                    full_path = os.path.join(root, name)
                    base_name = os.path.splitext(name)[0]
                    if base_name not in found_plugins:
                        found_plugins[base_name] = os.path.abspath(full_path)
                        
            # Skip traversing inside .vst3 directories to avoid duplicate scans
            subdirs[:] = [s for s in subdirs if not s.lower().endswith(".vst3")]
            
    return found_plugins

def scan_presets_for_vst(manufacturer, plugin_name):
    presets = {}
    
    # 1. Local user presets directory (PureBit/presets/<plugin_name>/)
    local_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "presets", plugin_name)
    if os.path.exists(local_dir):
        try:
            for f in os.listdir(local_dir):
                if f.lower().endswith(".json"):
                    name = os.path.splitext(f)[0]
                    presets[f"[User] {name}"] = {"type": "json", "path": os.path.join(local_dir, f)}
        except Exception as e:
            print(f"Error scanning local presets: {e}")
            
    # 2. System VST3 preset folders
    user_docs = os.path.expanduser("~/Documents")
    appdata_roaming = os.path.expanduser("~/AppData/Roaming")
    
    preset_paths = []
    if manufacturer:
        preset_paths.extend([
            os.path.join(user_docs, "VST3 Presets", manufacturer, plugin_name),
            os.path.join(appdata_roaming, "VST3 Presets", manufacturer, plugin_name),
        ])
    preset_paths.extend([
        os.path.join(user_docs, "VST3 Presets", plugin_name),
        os.path.join(appdata_roaming, "VST3 Presets", plugin_name),
    ])
    
    for folder in preset_paths:
        if os.path.exists(folder):
            try:
                for root, _, files in os.walk(folder):
                    for f in files:
                        if f.lower().endswith(".vstpreset"):
                            name = os.path.splitext(f)[0]
                            rel_path = os.path.relpath(os.path.join(root, f), folder)
                            display_name = rel_path.replace("\\", " > ")
                            presets[f"[System] {display_name}"] = {"type": "vstpreset", "path": os.path.join(root, f)}
            except Exception as e:
                print(f"Error scanning system presets in {folder}: {e}")
                
    return presets

class Plugin:
    def __init__(self):
        self.name = "VST3 Host"
        self.enabled = False
        self.file_name = "vst_host.py"
        self.settings_path = os.path.splitext(__file__)[0] + ".json"
        
        self.vst_path = DEFAULTS["vst_path"]
        self.mix = DEFAULTS["mix"]
        self.vst_state_b64 = DEFAULTS["vst_state_b64"]
        self.vst_instance = None
        self.load_error = None
        self.is_loading = False
        
        self.load_settings()
        if self.vst_path:
            self.load_vst(self.vst_path)

    def load_settings(self):
        values = load_settings(self.settings_path, DEFAULTS)
        self.vst_path = values.get("vst_path", "")
        self.mix = int(values.get("mix", 100))
        self.vst_state_b64 = values.get("vst_state_b64", "")

    def save_settings(self):
        state_b64 = ""
        if self.vst_instance is not None:
            try:
                state_b64 = base64.b64encode(self.vst_instance.raw_state).decode("utf-8")
            except Exception as e:
                print(f"Failed to serialize VST state: {e}")
                
        save_settings(
            self.settings_path,
            {
                "vst_path": self.vst_path,
                "mix": int(self.mix),
                "vst_state_b64": state_b64 or self.vst_state_b64,
            },
        )

    def load_vst(self, path):
        if not path or not os.path.exists(path):
            self.vst_instance = None
            self.load_error = "File does not exist"
            return False
            
        self.is_loading = True
        try:
            from pedalboard import load_plugin
            new_instance = load_plugin(path)
            self.vst_instance = new_instance
            self.vst_path = path
            self.load_error = None
            
            # Try to restore the VST state if it was saved
            if hasattr(self, "vst_state_b64") and self.vst_state_b64:
                try:
                    new_instance.raw_state = base64.b64decode(self.vst_state_b64)
                except Exception as state_err:
                    print(f"Failed to restore VST state: {state_err}")
                    
            return True
        except Exception as e:
            self.vst_instance = None
            self.load_error = str(e)
            return False
        finally:
            self.is_loading = False

    def process(self, data):
        source = np.asarray(data, dtype=np.float32)
        if source.size == 0 or self.vst_instance is None or getattr(self, "is_loading", False):
            return source

        mix = self.mix / 100.0
        try:
            wet = self.vst_instance.process(source, 48000)
            
            if wet.shape[0] != source.shape[0]:
                return source
                
            if source.ndim == 2 and wet.ndim == 1:
                wet = np.column_stack((wet, wet))
            elif source.ndim == 1 and wet.ndim == 2:
                wet = np.mean(wet, axis=1)
                
            return (source * (1.0 - mix)) + (wet * mix)
        except Exception as e:
            print(f"VST execution error: {e}")
            return source

    def open_settings(self, parent):
        dialog = VstHostDialog(parent, self)
        result = dialog.ShowModal()
        if result == wx.ID_OK:
            values = dialog.get_slider_values()
            self.mix = int(values["mix"])
            self.save_settings()
        dialog.Destroy()

class VstHostDialog(PluginControlDialog):
    def __init__(self, parent, plugin):
        self.plugin = plugin
        super().__init__(
            parent,
            title="VST3 Host Settings",
            slider_defs=[
                {"key": "mix", "label": "Mix", "value": plugin.mix},
            ],
            hint="Loads a VST3 audio plugin (like Waves, FabFilter, etc.) and runs it inside the mic stream. You can search for plugins below, or browse manually.",
            size=(480, 750),
        )
        
        panel = next((child for child in self.GetChildren() if isinstance(child, wx.Panel)), None)
        if panel is not None:
            panel_sizer = panel.GetSizer()
            
            # Current Loaded VST Path
            self.path_label = wx.StaticText(panel, label=self._get_path_label())
            self.path_label.Wrap(440)
            panel_sizer.Add(self.path_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
            
            # Load status
            self.status_label = wx.StaticText(panel, label=self._get_status_label())
            self.status_label.Wrap(440)
            panel_sizer.Add(self.status_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
            
            # Control Buttons row
            btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
            self.btn_editor = wx.Button(panel, label="Open VST Editor")
            self.btn_browse = wx.Button(panel, label="Browse File...")
            self.btn_clear = wx.Button(panel, label="Clear VST")
            
            btn_sizer.Add(self.btn_editor, 1, wx.RIGHT, 6)
            btn_sizer.Add(self.btn_browse, 1, wx.LEFT | wx.RIGHT, 6)
            btn_sizer.Add(self.btn_clear, 1, wx.LEFT, 6)
            panel_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, 12)
            
            # VST Presets row
            panel_sizer.Add(wx.StaticText(panel, label="Presets & Custom Settings:"), 0, wx.LEFT | wx.TOP, 6)
            preset_sizer = wx.BoxSizer(wx.HORIZONTAL)
            self.preset_choice = wx.Choice(panel)
            self.btn_save_preset = wx.Button(panel, label="Save Preset...")
            self.btn_load_preset = wx.Button(panel, label="Load Preset File...")
            
            preset_sizer.Add(self.preset_choice, 2, wx.EXPAND | wx.RIGHT, 6)
            preset_sizer.Add(self.btn_save_preset, 1, wx.RIGHT, 6)
            preset_sizer.Add(self.btn_load_preset, 1, 0)
            panel_sizer.Add(preset_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
            
            # divider line
            panel_sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 6)
            
            # Search Box
            panel_sizer.Add(wx.StaticText(panel, label="Search System VSTs:"), 0, wx.LEFT | wx.TOP, 6)
            self.search_ctrl = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
            panel_sizer.Add(self.search_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
            
            # Listbox of VSTs
            self.listbox = wx.ListBox(panel, size=(-1, 180), style=wx.LB_SINGLE | wx.LB_NEEDED_SB)
            panel_sizer.Add(self.listbox, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
            
            # Scan system VSTs
            self.vst_map = scan_system_vst3s()
            self._update_list()
            
            # Bind events
            self.btn_editor.Bind(wx.EVT_BUTTON, self.on_editor)
            self.btn_browse.Bind(wx.EVT_BUTTON, self.on_browse)
            self.btn_clear.Bind(wx.EVT_BUTTON, self.on_clear)
            self.search_ctrl.Bind(wx.EVT_TEXT, self.on_search)
            self.search_ctrl.Bind(wx.EVT_TEXT_ENTER, self.on_search_enter)
            self.listbox.Bind(wx.EVT_LISTBOX_DCLICK, self.on_list_double_click)
            self.listbox.Bind(wx.EVT_LISTBOX, self.on_list_select)
            
            self.preset_choice.Bind(wx.EVT_CHOICE, self.on_preset_select)
            self.btn_save_preset.Bind(wx.EVT_BUTTON, self.on_save_preset)
            self.btn_load_preset.Bind(wx.EVT_BUTTON, self.on_load_preset)
            
            # Prevent enter from confirming dialog on specific controls
            self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
            
            # Enable/disable controls
            self.btn_editor.Enable(plugin.vst_instance is not None)
            self._update_presets()
            
            self.SetSizerAndFit(self.GetSizer())
            
    def _get_path_label(self):
        if not self.plugin.vst_path:
            return "VST3 File: None loaded"
        return f"VST3 File: {os.path.basename(self.plugin.vst_path)}"
        
    def _get_status_label(self):
        if not self.plugin.vst_path:
            return ""
        if self.plugin.vst_instance is not None:
            return "Status: Loaded successfully!"
        return f"Status Error: {self.plugin.load_error}"

    def _update_list(self, filter_text=""):
        self.listbox.Clear()
        filter_text = filter_text.lower()
        sorted_names = sorted(self.vst_map.keys())
        for name in sorted_names:
            if not filter_text or filter_text in name.lower():
                self.listbox.Append(name)

    def _update_presets(self):
        self.preset_choice.Clear()
        self.presets_map = {}
        
        if self.plugin.vst_instance is None:
            self.preset_choice.Append("No VST Loaded")
            self.preset_choice.SetSelection(0)
            self.preset_choice.Disable()
            self.btn_save_preset.Disable()
            self.btn_load_preset.Disable()
            return
            
        self.preset_choice.Enable()
        self.btn_save_preset.Enable()
        self.btn_load_preset.Enable()
        
        vst_name = getattr(self.plugin.vst_instance, "name", "")
        manufacturer = getattr(self.plugin.vst_instance, "manufacturer_name", "")
        
        if not vst_name:
            vst_name = os.path.splitext(os.path.basename(self.plugin.vst_path))[0]
            
        self.presets_map = scan_presets_for_vst(manufacturer, vst_name)
        
        self.preset_choice.Append("-- Select Preset --")
        sorted_keys = sorted(self.presets_map.keys())
        for k in sorted_keys:
            self.preset_choice.Append(k)
            
        self.preset_choice.SetSelection(0)

    def on_char_hook(self, event):
        key = event.GetKeyCode()
        if key == wx.WXK_RETURN:
            focus = wx.Window.FindFocus()
            # Intercept enter key in textctrl, listbox, or choice to prevent dialog closure
            if focus in (self.search_ctrl, self.listbox, self.preset_choice):
                if focus == self.listbox:
                    self.on_list_double_click(None)
                return  # Do not Skip(), consume it!
        event.Skip()

    def on_search_enter(self, event):
        # Do not propagate
        pass

    def on_search(self, event):
        self._update_list(self.search_ctrl.GetValue())

    def on_list_select(self, event):
        pass

    def on_list_double_click(self, event):
        selection = self.listbox.GetStringSelection()
        if selection and selection in self.vst_map:
            path = self.vst_map[selection]
            self._load_and_update(path)

    def _load_and_update(self, path):
        if self.plugin.load_vst(path):
            self.plugin.save_settings()
            self.path_label.SetLabel(self._get_path_label())
            self.status_label.SetLabel(self._get_status_label())
            self.btn_editor.Enable(True)
        else:
            self.path_label.SetLabel(self._get_path_label())
            self.status_label.SetLabel(self._get_status_label())
            self.btn_editor.Enable(False)
        self._update_presets()
        self.Layout()

    def on_preset_select(self, event):
        selection = self.preset_choice.GetStringSelection()
        if selection in self.presets_map:
            preset_info = self.presets_map[selection]
            path = preset_info["path"]
            p_type = preset_info["type"]
            
            try:
                if p_type == "json":
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    state_b64 = data.get("raw_state_b64", "")
                    if state_b64:
                        self.plugin.vst_instance.raw_state = base64.b64decode(state_b64)
                        self.plugin.save_settings()
                        self.status_label.SetLabel("Status: Loaded JSON preset successfully!")
                elif p_type == "vstpreset":
                    self.plugin.vst_instance.load_preset(path)
                    self.plugin.save_settings()
                    self.status_label.SetLabel("Status: Loaded .vstpreset successfully!")
            except Exception as e:
                wx.MessageBox(f"Failed to load preset:\n{e}", "Preset Error", wx.ICON_ERROR)

    def on_save_preset(self, event):
        if self.plugin.vst_instance is None:
            return
            
        vst_name = getattr(self.plugin.vst_instance, "name", "")
        if not vst_name:
            vst_name = os.path.splitext(os.path.basename(self.plugin.vst_path))[0]
            
        with wx.TextEntryDialog(self, "Enter preset name:", "Save Preset") as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                name = dlg.GetValue().strip()
                if not name:
                    return
                
                # Sanitize filename
                safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).strip()
                if not safe_name:
                    return
                    
                local_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "presets", vst_name)
                if not os.path.exists(local_dir):
                    os.makedirs(local_dir)
                    
                path = os.path.join(local_dir, f"{safe_name}.json")
                try:
                    state_b64 = base64.b64encode(self.plugin.vst_instance.raw_state).decode("utf-8")
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump({"name": name, "raw_state_b64": state_b64}, f, indent=2)
                        
                    self._update_presets()
                    # Select the newly saved preset
                    idx = self.preset_choice.FindString(f"[User] {safe_name}")
                    if idx != wx.NOT_FOUND:
                        self.preset_choice.SetSelection(idx)
                        
                    self.status_label.SetLabel(f"Status: Saved preset '{name}' successfully!")
                except Exception as e:
                    wx.MessageBox(f"Failed to save preset:\n{e}", "Preset Error", wx.ICON_ERROR)

    def on_load_preset(self, event):
        if self.plugin.vst_instance is None:
            return
            
        with wx.FileDialog(
            self,
            "Select VST3 Preset File",
            wildcard="VST3 Preset files (*.vstpreset)|*.vstpreset",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as file_dialog:
            if file_dialog.ShowModal() == wx.ID_CANCEL:
                return
            path = file_dialog.GetPath()
            try:
                self.plugin.vst_instance.load_preset(path)
                self.plugin.save_settings()
                self.status_label.SetLabel("Status: Loaded preset file successfully!")
            except Exception as e:
                wx.MessageBox(f"Failed to load preset file:\n{e}", "Preset Error", wx.ICON_ERROR)

    def on_browse(self, event):
        with wx.FileDialog(
            self,
            "Select VST3 Plugin",
            wildcard="VST3 plugins (*.vst3)|*.vst3",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as file_dialog:
            if file_dialog.ShowModal() == wx.ID_CANCEL:
                return
            path = file_dialog.GetPath()
            self._load_and_update(path)

    def on_editor(self, event):
        if self.plugin.vst_instance is not None:
            try:
                self.plugin.vst_instance.show_editor()
            except Exception as e:
                wx.MessageBox(f"Could not open VST editor:\n{e}", "VST Editor Error", wx.ICON_ERROR)

    def on_clear(self, event):
        self.plugin.vst_path = ""
        self.plugin.vst_instance = None
        self.plugin.load_error = None
        self.plugin.save_settings()
        self.path_label.SetLabel(self._get_path_label())
        self.status_label.SetLabel(self._get_status_label())
        self.btn_editor.Enable(False)
        self._update_presets()
        self.Layout()
