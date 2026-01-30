"""
Test and verify StMicDriver installation and accessibility
"""
import ctypes
from ctypes import wintypes
import struct

# Windows API constants
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002

# IOCTL definition from StMicCommon.h
# METHOD_BUFFERED = 0
# FILE_ANY_ACCESS = 0
# FILE_DEVICE_UNKNOWN = 0x00000022
# KSPROPERTY_STMIC_PUSHAUDIO = 1

def CTL_CODE(DeviceType, Function, Method, Access):
    return (DeviceType << 16) | (Access << 14) | (Function << 2) | Method

# Define IOCTL for KSPROPERTY_STMIC_PUSHAUDIO
# This needs to match the driver's IOCTL code
IOCTL_STMIC_PUSHAUDIO = CTL_CODE(0x00000022, 0x800 + 1, 0, 0)

def find_driver_device():
    """
    Find the StMicDriver device path
    """
    print("Searching for StMicDriver device...")
    
    # Common device interface GUIDs for audio devices
    # We'll need to enumerate devices to find ours
    
    # For now, try common patterns
    possible_paths = [
        r"\\.\SimpleAudioSample",
        r"\\.\StMic",
        r"\\.\VirtualMic",
    ]
    
    for path in possible_paths:
        print(f"Trying: {path}")
        handle = ctypes.windll.kernel32.CreateFileW(
            path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None
        )
        if handle != -1:
            print(f"✅ Found device at: {path}")
            ctypes.windll.kernel32.CloseHandle(handle)
            return path
    
    print("❌ Device not found with common paths")
    print("\nℹ️ The driver may not have a device interface enabled")
    print("   This is normal for audio drivers - they work through KSPROPERTY")
    return None

def test_driver_communication():
    """
    Test basic communication with driver
    """
    print("="*60)
    print("StMicDriver Communication Test")
    print("="*60)
    
    device_path = find_driver_device()
    
    if not device_path:
        print("\n⚠️ Direct device access not available")
        print("This is expected for WDM audio drivers")
        print("\nℹ️ Next step: Use KS (Kernel Streaming) API to access driver")
        return False
    
    # Try to open and test
    try:
        handle = ctypes.windll.kernel32.CreateFileW(
            device_path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None
        )
        
        if handle == -1:
            print(f"❌ Failed to open device: {ctypes.get_last_error()}")
            return False
        
        print(f"✅ Opened device successfully")
        
        # Test sending dummy audio data
        test_audio = b'\x00' * 1024  # 1KB of silence
        
        # Prepare IOCTL buffer (STMIC_AUDIO_DATA structure)
        # typedef struct {
        #     ULONG Size;
        #     BYTE Data[1];
        # } STMIC_AUDIO_DATA;
        
        buffer = struct.pack('I', len(test_audio)) + test_audio
        bytes_returned = wintypes.DWORD()
        
        result = ctypes.windll.kernel32.DeviceIoControl(
            handle,
            IOCTL_STMIC_PUSHAUDIO,
            buffer,
            len(buffer),
            None,
            0,
            ctypes.byref(bytes_returned),
            None
        )
        
        if result:
            print(f"✅ Successfully sent {len(test_audio)} bytes to driver")
            print(f"✅ Driver is working correctly!")
        else:
            error = ctypes.get_last_error()
            print(f"⚠️ DeviceIoControl failed: Error {error}")
        
        ctypes.windll.kernel32.CloseHandle(handle)
        return result
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    test_driver_communication()
    
    print("\n" + "="*60)
    print("Next Steps:")
    print("="*60)
    print("1. Check Device Manager for 'Virtual Audio Device (WDM)'")
    print("2. Check Sound Settings for virtual microphone")
    print("3. If driver is visible, we'll implement full KS API access")
    print("="*60)
