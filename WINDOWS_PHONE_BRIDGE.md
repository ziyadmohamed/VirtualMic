# Windows Phone Bridge

This repository now has a native Windows app path in `WindowsPhoneBridge/`.

Current scope:

- Native C++ control tool: `phone_bridge_ctl`
- Uses the public Core Audio MMDevice API to enumerate audio endpoints
- Reports the current default `communications` and `multimedia` render/capture devices
- Establishes the Windows-side control surface we need before attempting Phone Link-style audio routing

Build locally:

```powershell
& "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\MSBuild\Current\Bin\MSBuild.exe" `
  WindowsPhoneBridge\PhoneBridgeCtl.vcxproj `
  /p:Configuration=Release `
  /p:Platform=x64
```

Run:

```powershell
.\WindowsPhoneBridge\build\PhoneBridgeCtl\Release\phone_bridge_ctl.exe list
.\WindowsPhoneBridge\build\PhoneBridgeCtl\Release\phone_bridge_ctl.exe defaults
```

Architecture notes:

1. The Android app in this repo can already place calls, answer/hang up, mute, and switch Android call routes.
2. A true Phone Link-style PC call experience needs the Windows side to participate in the system communications audio path.
3. Public Core Audio APIs let us inspect and follow the active communications endpoints. That is what `phone_bridge_ctl` starts with.
4. Full telephony-style Bluetooth audio on Windows is tied to system Bluetooth profile handling and, in some cases, lower-level driver work rather than an ordinary desktop app socket.

Planned next steps:

1. Add endpoint change notifications with `IMMNotificationClient`.
2. Add Bluetooth device and service discovery relevant to hands-free endpoints.
3. Add a desktop UI/service layer around the existing Android remote protocol.
4. Evaluate whether the remaining routing gap can be solved with public Windows APIs alone or requires a driver/plugin layer.
