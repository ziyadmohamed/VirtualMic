"""
Send audio data to StMicDriver using IOCTL
This script demonstrates how to communicate with the virtual microphone driver
"""
import ctypes
from ctypes import wintypes
import struct
import wave
import numpy as np
import time

# Windows API constants
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
INVALID_HANDLE_VALUE = -1

# Kernel32 and SetupAPI
kernel32 = ctypes.windll.kernel32
setupapi = ctypes.windll.setupapi

# IOCTL code calculation
def CTL_CODE(DeviceType, Function, Method, Access):
    """Calculate Windows IOCTL code"""
    return (DeviceType << 16) | (Access << 14) | (Function << 2) | Method

# KSPROPERTY_STMIC_PUSHAUDIO IOCTL
# From StMicCommon.h:
# FILE_DEVICE_UNKNOWN = 0x22
# METHOD_BUFFERED = 0
# FILE_ANY_ACCESS = 0
# Function code needs to be calculated from KSPROPERTY
IOCTL_KSPROPERTY = CTL_CODE(0x22, 0x800 + 1, 0, 0)  # Approximation

class StMicDriver:
    """Interface to communicate with StMicDriver"""
    
    def __init__(self):
        self.handle = None
        self.device_paths = [
            r"\\.\SimpleAudioSample",
            r"\\.\GLOBAL\SimpleAudioSample", 
            r"\\.\SimpleAudioSample0",
        ]
    
    def find_and_open_device(self):
        """Find and open the driver device"""
        print("Searching for StMicDriver device...")
        
        for path in self.device_paths:
            print(f"  Trying: {path}")
            handle = kernel32.CreateFileW(
                path,
                GENERIC_READ | GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                0,
                None
            )
            
            if handle != INVALID_HANDLE_VALUE:
                print(f"  ✅ Opened device: {path}")
                self.handle = handle
                return True
            else:
                error = kernel32.GetLastError()
                if error != 2:  # ERROR_FILE_NOT_FOUND
                    print(f"  ⚠️  Error {error}")
        
        print("\n⚠️  Could not open device with standard paths")
        print("   Driver may not expose a device interface")
        print("   Will try alternative method using KS API...")
        return False
    
    def send_audio_data(self, audio_data):
        """Send audio data to driver via IOCTL"""
        if not self.handle:
            print("❌ Device not opened")
            return False
        
        # Prepare STMIC_AUDIO_DATA structure
        # typedef struct {
        #     ULONG Size;
        #     BYTE Data[1];
        # } STMIC_AUDIO_DATA;
        
        data_size = len(audio_data)
        buffer = struct.pack('I', data_size) + audio_data
        
        bytes_returned = wintypes.DWORD()
        
        result = kernel32.DeviceIoControl(
            self.handle,
            IOCTL_KSPROPERTY,
            buffer,
            len(buffer),
            None,
            0,
            ctypes.byref(bytes_returned),
            None
        )
        
        if result:
            return True
        else:
            error = kernel32.GetLastError()
            print(f"⚠️  DeviceIoControl failed: Error {error}")
            return False
    
    def close(self):
        """Close device handle"""
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None

def generate_test_tone(frequency=440, duration=1.0, sample_rate=48000):
    """Generate a sine wave test tone"""
    samples = int(sample_rate * duration)
    t = np.linspace(0, duration, samples, False)
    tone = np.sin(2 * np.pi * frequency * t)
    
    # Convert to 16-bit PCM
    tone = (tone * 32767).astype(np.int16)
    return tone.tobytes()

def test_driver_communication():
    """Test sending audio to driver"""
    print("="*70)
    print("StMicDriver Audio Test")
    print("="*70)
    
    driver = StMicDriver()
    
    # Try to open device
    if not driver.find_and_open_device():
        print("\n❌ Could not open driver device")
        print("\nℹ️  This is expected - WDM audio drivers use KS API")
        print("   We need to use Kernel Streaming API instead")
        print("\n📝 Next step: Implement KS-based communication")
        return False
    
    print("\n✅ Driver device opened successfully!")
    print("\n📤 Generating test audio (440 Hz sine wave)...")
    
    # Generate 1 second of 440Hz tone
    test_audio = generate_test_tone(440, 1.0, 48000)
    
    print(f"   Generated {len(test_audio)} bytes of audio data")
    
    # Send audio in chunks
    chunk_size = 4800  # 100ms at 48kHz, 16-bit mono
    total_sent = 0
    
    print("\n📡 Sending audio to driver...")
    for i in range(0, len(test_audio), chunk_size):
        chunk = test_audio[i:i+chunk_size]
        if driver.send_audio_data(chunk):
            total_sent += len(chunk)
            print(f"  Sent {total_sent}/{len(test_audio)} bytes", end='\r')
            time.sleep(0.1)  # 100ms delay between chunks
        else:
            print(f"\n❌ Failed to send chunk at offset {i}")
            break
    
    print(f"\n✅ Sent {total_sent} bytes total")
    
    driver.close()
    
    print("\n" + "="*70)
    print("✅ Test completed!")
    print("   Check Windows Sound Recorder or Audacity")
    print("   to see if virtual microphone is receiving audio")
    print("="*70)
    
    return True

if __name__ == "__main__":
    try:
        test_driver_communication()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    input("\nPress Enter to exit...")
