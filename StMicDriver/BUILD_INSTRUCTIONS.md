# Building the StMic Virtual Audio Driver

## Prerequisites
1.  **Visual Studio 2022** (Free Community Edition is fine).
    - Workload: "Desktop development with C++".
2.  **Windows Driver Kit (WDK)**.
    - Install WDK for Windows 11/10.
    - Install the "WDK Visual Studio Extension".

## Build Steps
1.  Open `d:\VirtualMic\StMicDriver\SimpleAudioSample.sln` in Visual Studio.
2.  Visual Studio might ask to "Retarget Projects" to your installed SDK/WDK version. Click OK.
3.  Select Configuration: **Debug** or **Release**.
4.  Select Configuration: **x64**.
5.  Right-click Solution -> **Build**.

## Installation (Test Mode)
Since this is a self-signed driver, Windows will block it by default.
1.  Open Admin Command Prompt.
2.  Enable Test Signing:
    ```cmd
    bcdedit /set testsigning on
    ```
3.  **Restart your Computer**.
4.  Locate the built driver (e.g., `x64\Debug\SimpleAudioSample\SimpleAudioSample.inf`).
5.  Install using `devcon` (tool included in WDK) or Device Manager:
    - Device Manager: Action -> Add Legacy Hardware -> Install from Disk -> Point to `.inf`.

## Usage
- The driver should appear as "Microphone (Simple Audio Sample)".
- Run `receiver.py`. (Note: currently `receiver.py` logic defaults to VB-Cable for simplicity, but the driver source is ready for custom IOCTL development if you wish to go deeper).

## Why VB-Cable is better?
- VB-Cable is a signed, production-ready driver.
- It is exactly what WO Mic uses (WO Mic usually installs its own signed driver, but VB-Cable is the same concept).
- Writing and signing your own driver costs money (EV Certificate) and time.
