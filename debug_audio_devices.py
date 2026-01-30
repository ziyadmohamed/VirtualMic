"""
Debug: List all audio devices using different methods
"""
import subprocess

print("="*70)
print("Audio Devices Debug")
print("="*70)

# Method 1: PowerShell Get-PnpDevice
print("\n1. Using Get-PnpDevice (MEDIA class):")
try:
    result = subprocess.run(
        ["powershell", "-Command", 
         "Get-PnpDevice -Class 'MEDIA' | Select-Object Status, FriendlyName, InstanceId | Format-Table -AutoSize"],
        capture_output=True,
        text=True,
        timeout=10
    )
    print(result.stdout if result.stdout else "  (No output)")
except Exception as e:
    print(f"  Error: {e}")

# Method 2: Check AudioEndpoint class
print("\n2. Using Get-PnpDevice (AudioEndpoint class):")
try:
    result = subprocess.run(
        ["powershell", "-Command",
         "Get-PnpDevice -Class 'AudioEndpoint' | Select-Object Status, FriendlyName | Format-Table -AutoSize"],
        capture_output=True,
        text=True,
        timeout=10
    )
    print(result.stdout if result.stdout else "  (No output)")
except Exception as e:
    print(f"  Error: {e}")

# Method 3: PyAudio
print("\n3. Using PyAudio:")
try:
    import pyaudio
    audio = pyaudio.PyAudio()
    
    for i in range(audio.get_device_count()):
        info = audio.get_device_info_by_index(i)
        if 'Virtual' in info['name'] or 'Simple' in info['name']:
            print(f"  ✅ [{i}] {info['name']}")
            print(f"      Input channels: {info['maxInputChannels']}")
            print(f"      Output channels: {info['maxOutputChannels']}")
    
    audio.terminate()
except ImportError:
    print("  PyAudio not installed")
except Exception as e:
    print(f"  Error: {e}")

# Method 4: Registry check
print("\n4. Checking Registry (MMDEVICES):")
try:
    result = subprocess.run(
        ["powershell", "-Command",
         "Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio\\Capture\\*' -ErrorAction SilentlyContinue | Select-Object FriendlyName"],
        capture_output=True,
        text=True,
        timeout=10
    )
    if result.stdout and result.stdout.strip():
        print(result.stdout)
    else:
        print("  (No capture devices in registry)")
except Exception as e:
    print(f"  Error: {e}")

print("\n" + "="*70)
print("Diagnosis:")
print("="*70)
print("\nIf Virtual Audio Device appears in:")
print("  ✅ Method 1 or 2 → Driver is installed")
print("  ✅ Method 3 (PyAudio) → We can use PyAudio approach")
print("  ✅ Method 4 (Registry) → Device is registered")
print("\nIf it doesn't appear anywhere → Driver issue or not installed correctly")
print("="*70)

input("\nPress Enter to exit...")
