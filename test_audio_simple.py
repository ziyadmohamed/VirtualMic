"""
Simplified audio test without numpy - sends pure sine wave to driver
"""
import ctypes
from ctypes import wintypes
import struct
import math
import time

# Windows API
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_SHARE_READ = 0x00000001  
FILE_SHARE_WRITE = 0x00000002
INVALID_HANDLE_VALUE = -1

kernel32 = ctypes.windll.kernel32

def generate_sine_wave(frequency=440, duration=1.0, sample_rate=48000):
    """Generate sine wave without numpy"""
    samples = int(sample_rate * duration)
    audio_data = bytearray()
    
    for i in range(samples):
        # Generate sine wave sample
        t = i / sample_rate
        sample = math.sin(2 * math.pi * frequency * t)
        
        # Convert to 16-bit PCM
        pcm_sample = int(sample * 32767)
        # Clamp to int16 range
        pcm_sample = max(-32768, min(32767, pcm_sample))
        
        # Pack as little-endian 16-bit integer
        audio_data.extend(struct.pack('<h', pcm_sample))
    
    return bytes(audio_data)

print("="*70)
print("StMicDriver Simple Audio Test (No Dependencies)")
print("="*70)

print("\n1. Generating test tone (440 Hz sine wave)...")
test_audio = generate_sine_wave(440, 2.0, 48000)  # 2 seconds
print(f"   ✅ Generated {len(test_audio)} bytes ({len(test_audio)//2} samples)")

print("\n2. Attempting to open driver device...")

device_paths = [
    r"\\.\SimpleAudioSample",
    r"\\.\GLOBAL\SimpleAudioSample",
]

handle = None
for path in device_paths:
    print(f"   Trying: {path}")
    h = kernel32.CreateFileW(
        path,
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        0,
        None
    )
    
    if h != INVALID_HANDLE_VALUE:
        print(f"   ✅ Opened: {path}")
        handle = h
        break
    else:
        error = kernel32.GetLastError()
        print(f"   ❌ Error: {error}")

if not handle:
    print("\n⚠️  Could not open device directly")
    print("   This is NORMAL for WDM audio drivers!")
    print("\n📝 Why:")
    print("   - WDM drivers don't expose device handles like \\.\DeviceName")
    print("   - They use Kernel Streaming (KS) API")
    print("   - We need to access via audio endpoint")
    print("\n🔧 Solution:")
    print("   We'll modify the driver to create a device interface")
    print("   OR use Windows Core Audio API to inject audio")
    print("\n" + "="*70)
    input("Press Enter to continue...")
    exit(0)

print("\n3. Sending audio data to driver...")

# Calculate IOCTL code
def CTL_CODE(DeviceType, Function, Method, Access):
    return (DeviceType << 16) | (Access << 14) | (Function << 2) | Method

IOCTL_PUSH_AUDIO = CTL_CODE(0x22, 0x801, 0, 0)

# Send in chunks
chunk_size = 9600  # 100ms at 48kHz, 16-bit
total_sent = 0

for i in range(0, len(test_audio), chunk_size):
    chunk = test_audio[i:i+chunk_size]
    
    # Prepare buffer: ULONG size + data
    buffer = struct.pack('I', len(chunk)) + chunk
    bytes_returned = wintypes.DWORD()
    
    result = kernel32.DeviceIoControl(
        handle,
        IOCTL_PUSH_AUDIO,
        buffer,
        len(buffer),
        None,
        0,
        ctypes.byref(bytes_returned),
        None
    )
    
    if result:
        total_sent += len(chunk)
        progress = (total_sent / len(test_audio)) * 100
        print(f"   Progress: {progress:.1f}% ({total_sent}/{len(test_audio)} bytes)", end='\r')
        time.sleep(0.1)
    else:
        error = kernel32.GetLastError()
        print(f"\n   ❌ IOCTL failed: Error {error}")
        break

print(f"\n   ✅ Sent {total_sent} bytes")

kernel32.CloseHandle(handle)

print("\n" + "="*70)
print("✅ Test completed!")
print("\n📊 What to check:")
print("   1. Open Windows Sound Recorder")
print("   2. Select 'Virtual Audio Device' as microphone")
print("   3. You should see audio levels responding")
print("="*70)

input("\nPress Enter to exit...")
