# StMicDriver - Virtual Microphone Driver for Windows

Virtual audio driver that allows pushing audio data from external sources (like Android devices) to appear as a system-wide microphone input on Windows.

## Features

- 🎤 Virtual Microphone Input Device
- 🔊 48kHz, 2-channel, 32-bit PCM audio
- 📡 Network audio streaming support
- 🔧 Custom IOCTL interface for audio injection
- ⚡ Low-latency circular buffer architecture

## Quick Start

### Pre-built Driver

Download the latest pre-built driver from [GitHub Releases](../../releases).

### Build from Source

This repository uses GitHub Actions to automatically build the driver. The workflow runs on every push.

**To build manually**:
1. Install Visual Studio 2022 with C++ workload
2. Install Windows Driver Kit (WDK) 11
3. Run:
   ```cmd
   cd StMicDriver
   msbuild SimpleAudioSample.sln /p:Configuration=Release /p:Platform=x64
   ```

## Installation

### Prerequisites

1. Enable Test Signing (requires Administrator):
   ```cmd
   bcdedit /set TESTSIGNING ON
   ```
   **Reboot required!**

2. Get DevCon tool (from WDK):
   ```
   C:\Program Files (x86)\Windows Kits\10\Tools\x64\devcon.exe
   ```

### Install Driver

```cmd
cd path\to\driver\package
devcon.exe install SimpleAudioSample.inf Root\SimpleAudioSample
```

### Verify Installation

1. Open Device Manager (`devmgmt.msc`)
2. Look for "Virtual Audio Device (WDM) - Simple Audio Sample" under "Sound, video and game controllers"

## Usage

### With Python Receiver

See `receiver.py` for a Python script that:
- Receives audio from Android via network
- Sends audio to driver via IOCTL
- Makes it available as system microphone

### With Android App

See `app/` directory for Android application that:
- Records from device microphone
- Streams audio over WiFi/network
- Connects to Python receiver

## Architecture

```
Android Mic → Network (TCP) → Python Receiver → StMicDriver → Windows Applications
```

### Components

- **StMicDriver**: Windows WDM audio driver (kernel mode)
- **SidebandData**: Circular buffer for audio data
- **KSPROPERTY_STMIC_PUSHAUDIO**: Custom IOCTL for audio injection
- **receiver.py**: User-mode receiver (network → driver)
- **Android App**: Audio capture and network streaming

## Development

### Project Structure

```
├── .github/workflows/     # GitHub Actions CI/CD
├── StMicDriver/          # Driver source code
│   ├── Source/
│   │   ├── Main/        # Core driver logic
│   │   ├── Filters/     # Audio filters
│   │   └── Utilities/   # Helper utilities
│   └── Package/         # Installation package
├── app/                 # Android application
└── receiver.py         # Python receiver script
```

### Building with GitHub Actions

This project automatically builds on every commit using GitHub Actions. The workflow:
1. Sets up Windows build environment
2. Installs WDK
3. Builds both Debug and Release configurations
4. Uploads artifacts (downloadable .sys, .inf, .cat files)

Check the [Actions tab](../../actions) for build status and downloadable artifacts.

## License

Based on Microsoft's SimpleAudioSample driver template.

## Contributing

Pull requests welcome! Please ensure:
- Code builds successfully in GitHub Actions
- Driver installs without errors
- Audio streaming works end-to-end

## Support

For issues, questions, or feature requests, please open a GitHub issue.

---

**Note**: This driver requires Test Signing to be enabled on Windows. For production use, driver signing with a valid certificate is required.
