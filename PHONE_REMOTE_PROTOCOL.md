# Phone Remote Protocol

The Android app exposes a Bluetooth RFCOMM service named `StMic Phone Remote` with UUID `bb807b4d-aea5-4f11-a8b1-47d12ae2f4c2`.

Commands are newline-delimited JSON objects. Each response is also a single JSON line.

Examples:

```json
{"id":"1","action":"status"}
{"id":"2","action":"dial","number":"+15551234567"}
{"id":"3","action":"dial","number":"+15551234567","speakerphone":true}
{"id":"4","action":"send_sms","number":"+15551234567","message":"Testing from Bluetooth"}
{"id":"5","action":"answer"}
{"id":"6","action":"hang_up"}
{"id":"7","action":"mute","enabled":true}
{"id":"8","action":"speaker","enabled":true}
{"id":"9","action":"route","route":"BLUETOOTH"}
```

Notes:

- `answer`, `hang_up`, `mute`, and `speaker` only work while the app is the default dialer and a live call is routed through its `InCallService`.
- `route` can switch between currently supported Android call routes such as `EARPIECE`, `WIRED_HEADSET`, `BLUETOOTH`, and `SPEAKER`.
- `dial` requires the Android runtime permission `CALL_PHONE`.
- `send_sms` requires the Android runtime permission `SEND_SMS`.
- This app does not inject arbitrary audio into carrier calls or stream SIM call audio over RFCOMM. Android does not expose that through normal public APIs for third-party apps.

Windows client:

```powershell
python phone_remote_client.py --mac AA:BB:CC:DD:EE:FF shell
python phone_remote_client.py --mac AA:BB:CC:DD:EE:FF status
python phone_remote_client.py --mac AA:BB:CC:DD:EE:FF dial +15551234567
python phone_remote_client.py --mac AA:BB:CC:DD:EE:FF sms +15551234567 "test from pc"
python phone_remote_client.py --mac AA:BB:CC:DD:EE:FF route BLUETOOTH
```
