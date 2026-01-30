"""
Send audio to StMicDriver using Kernel Streaming Properties
This bypasses the need for device interface by using KS filter directly
"""
import ctypes
from ctypes import wintypes
import struct
import math
import time
import sys

# Windows API
kernel32 = ctypes.windll.kernel32
setupapi = ctypes.windll.setupapi

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
INVALID_HANDLE_VALUE = -1

# GUID definitions
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8)
    ]

# KSPROPERTY_SET_STMIC: {12345678-1234-5678-1234-567812345678}
KSPROPERTY_SET_STMIC = GUID(
    0x12345678, 0x1234, 0x5678,
    (wintypes.BYTE * 8)(0x12, 0x34, 0x56, 0x78, 0x12, 0x34, 0x56, 0x78)
)

# KSCATEGORY_AUDIO: {6994AD04-93EF-11D0-A3CC-00A0C9223196}
KSCATEGORY_AUDIO = GUID(
    0x6994AD04, 0x93EF, 0x11D0,
    (wintypes.BYTE * 8)(0xA3, 0xCC, 0x00, 0xA0, 0xC9, 0x22, 0x31, 0x96)
)

# KSPROPERTY structure
class KSPROPERTY(ctypes.Structure):
    _fields_ = [
        ("Set", GUID),
        ("Id", wintypes.DWORD),
        ("Flags", wintypes.DWORD)
    ]

# Constants
KSPROPERTY_TYPE_SET = 0x00000001
KSPROPERTY_TYPE_GET = 0x00000002
KSPROPERTY_STMIC_PUSHAUDIO = 1

# IOCTL for KSPROPERTY
IOCTL_KS_PROPERTY = 0x00070000 | (0 << 14) | (0 << 2) | 0

def find_audio_filter():
    """Find the StMic audio filter using setupapi"""
    print("Searching for StMic audio filter...")
    
    # Get device info set for audio devices
    DIGCF_PRESENT = 0x00000002
    DIGCF_DEVICEINTERFACE = 0x00000010
    
    hDevInfo = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(KSCATEGORY_AUDIO),
        None,
        None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )
    
    if hDevInfo == INVALID_HANDLE_VALUE:
        print(f"❌ SetupDiGetClassDevs failed: {kernel32.GetLastError()}")
        return None
    
    # SP_DEVICE_INTERFACE_DATA structure
    class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("InterfaceClassGuid", GUID),
            ("Flags", wintypes.DWORD),
            ("Reserved", ctypes.POINTER(wintypes.ULONG))
        ]
    
    devInterfaceData = SP_DEVICE_INTERFACE_DATA()
    devInterfaceData.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
    
    # Collect all devices
    all_devices = []
    virtual_device = None
    
    # Enumerate devices
    index = 0
    while True:
        result = setupapi.SetupDiEnumDeviceInterfaces(
            hDevInfo,
            None,
            ctypes.byref(KSCATEGORY_AUDIO),
            index,
            ctypes.byref(devInterfaceData)
        )
        
        if not result:
            break
        
        # Get device path
        requiredSize = wintypes.DWORD()
        setupapi.SetupDiGetDeviceInterfaceDetailW(
            hDevInfo,
            ctypes.byref(devInterfaceData),
            None,
            0,
            ctypes.byref(requiredSize),
            None
        )
        
        if requiredSize.value == 0:
            index += 1
            continue
        
        # Allocate buffer for device path
        class SP_DEVICE_INTERFACE_DETAIL_DATA(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("DevicePath", wintypes.WCHAR * (requiredSize.value - 4))
            ]
        
        detailData = SP_DEVICE_INTERFACE_DETAIL_DATA()
        detailData.cbSize = 6 if ctypes.sizeof(ctypes.c_void_p) == 8 else 5
        
        result = setupapi.SetupDiGetDeviceInterfaceDetailW(
            hDevInfo,
            ctypes.byref(devInterfaceData),
            ctypes.byref(detailData),
            requiredSize,
            None,
            None
        )
        
        if result:
            devicePath = detailData.DevicePath
            all_devices.append(devicePath)
            
            # Check if it's our virtual device
            if 'simple' in devicePath.lower() or 'virtual' in devicePath.lower():
                virtual_device = devicePath
        
        index += 1
    
    setupapi.SetupDiDestroyDeviceInfoList(hDevInfo)
    
    # If found automatically, return it
    if virtual_device:
        print(f"✅ Auto-detected: {virtual_device[:80]}...")
        return virtual_device
    
    # Otherwise, show list and let user choose
    print(f"\n⚠️  Could not auto-detect StMic filter")
    print(f"Found {len(all_devices)} audio device(s):\n")
    
    for i, dev in enumerate(all_devices):
        # Show shortened path
        short_path = dev.split('\\')[-1] if '\\' in dev else dev
        print(f"  [{i}] ...{short_path[:70]}")
    
    if not all_devices:
        print("  (No audio devices found)")
        return None
    
    print(f"\nWhich device is the Virtual Audio Device?")
    print(f"Enter number (0-{len(all_devices)-1}), or 'q' to quit: ", end='')
    
    choice = input().strip()
    
    if choice.lower() == 'q':
        return None
    
    try:
        idx = int(choice)
        if 0 <= idx < len(all_devices):
            selected = all_devices[idx]
            print(f"\n✅ Selected: {selected[:80]}...")
            return selected
        else:
            print(f"❌ Invalid index: {idx}")
            return None
    except ValueError:
        print(f"❌ Invalid input: {choice}")
        return None

def send_audio_via_ksproperty(device_path, audio_data):
    """Send audio data using KSPROPERTY"""
    print(f"\nOpening filter: {device_path[:60]}...")
    
    # Open device
    handle = kernel32.CreateFileW(
        device_path,
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        0,
        None
    )
    
    if handle == INVALID_HANDLE_VALUE:
        error = kernel32.GetLastError()
        print(f"❌ CreateFile failed: Error {error}")
        return False
    
    print("✅ Filter opened!")
    
    # Prepare KSPROPERTY structure
    ksProp = KSPROPERTY()
    ksProp.Set = KSPROPERTY_SET_STMIC
    ksProp.Id = KSPROPERTY_STMIC_PUSHAUDIO
    ksProp.Flags = KSPROPERTY_TYPE_SET
    
    # Prepare data: ULONG Size + BYTE Data[]
    data_size = len(audio_data)
    prop_data = struct.pack('I', data_size) + audio_data
    
    # Combine KSPROPERTY + data
    input_buffer = bytes(ksProp) + prop_data
    
    bytes_returned = wintypes.DWORD()
    
    print(f"📤 Sending {len(audio_data)} bytes via KSPROPERTY...")
    
    result = kernel32.DeviceIoControl(
        handle,
        IOCTL_KS_PROPERTY,
        input_buffer,
        len(input_buffer),
        None,
        0,
        ctypes.byref(bytes_returned),
        None
    )
    
    if result:
        print(f"✅ Successfully sent {len(audio_data)} bytes!")
        kernel32.CloseHandle(handle)
        return True
    else:
        error = kernel32.GetLastError()
        print(f"❌ DeviceIoControl failed: Error {error}")
        kernel32.CloseHandle(handle)
        return False

def generate_test_tone(freq=440, duration=2.0, sample_rate=48000):
    """Generate sine wave test tone"""
    samples = int(sample_rate * duration)
    audio_data = bytearray()
    
    for i in range(samples):
        t = i / sample_rate
        sample = math.sin(2 * math.pi * freq * t)
        pcm_sample = int(sample * 32767)
        pcm_sample = max(-32768, min(32767, pcm_sample))
        audio_data.extend(struct.pack('<h', pcm_sample))
    
    return bytes(audio_data)

def main():
    print("="*70)
    print("StMicDriver KS Property Audio Injection")
    print("="*70)
    
    # Find filter
    device_path = find_audio_filter()
    
    if not device_path:
        print("\n❌ Could not find StMic audio filter")
        print("\nMake sure:")
        print("  1. Driver is installed")
        print("  2. Device is enabled in Device Manager")
        input("\nPress Enter to exit...")
        return
    
    # Generate test audio
    print("\n🎵 Generating 440 Hz test tone (2 seconds)...")
    audio_data = generate_test_tone(440, 2.0, 48000)
    print(f"   Generated {len(audio_data)} bytes")
    
    # Send in chunks
    chunk_size = 9600  # 100ms at 48kHz, 16-bit
    total_sent = 0
    
    print("\n📡 Sending audio to driver...")
    for i in range(0, len(audio_data), chunk_size):
        chunk = audio_data[i:i+chunk_size]
        
        if send_audio_via_ksproperty(device_path, chunk):
            total_sent += len(chunk)
            progress = (total_sent / len(audio_data)) * 100
            print(f"   Progress: {progress:.1f}% ({total_sent}/{len(audio_data)} bytes)", end='\r')
            time.sleep(0.1)  # 100ms delay
        else:
            print(f"\n❌ Failed at {total_sent} bytes")
            break
    
    print(f"\n\n✅ Sent {total_sent} bytes total!")
    
    print("\n" + "="*70)
    print("Testing complete!")
    print("\n📊 Check:")
    print("  1. Open Sound Recorder or Audacity")
    print("  2. Select 'Virtual Audio Device' as input")
    print("  3. You should see/hear the 440 Hz tone!")
    print("="*70)
    
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
