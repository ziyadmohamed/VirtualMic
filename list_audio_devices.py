"""
List all audio devices and their capabilities
"""
import pyaudio

audio = pyaudio.PyAudio()

print("="*70)
print("All Audio Devices")
print("="*70)

for i in range(audio.get_device_count()):
    info = audio.get_device_info_by_index(i)
    
    print(f"\n[{i}] {info['name']}")
    print(f"    Max Input Channels: {info['maxInputChannels']}")
    print(f"    Max Output Channels: {info['maxOutputChannels']}")
    print(f"    Default Sample Rate: {int(info['defaultSampleRate'])} Hz")
    print(f"    Host API: {audio.get_host_api_info_by_index(info['hostApi'])['name']}")
    
    if 'Virtual' in info['name'] or 'Simple' in info['name']:
        print("    >>> THIS IS OUR VIRTUAL DEVICE <<<")

audio.terminate()

print("\n" + "="*70)
print("Diagnosis:")
print("="*70)
print("\nIf Virtual Device has:")
print("  maxOutputChannels = 0 → It's INPUT only (microphone)")
print("  maxOutputChannels > 0 → We can write to it")
print("\nIf it's INPUT only, we need a different approach!")
print("="*70)
