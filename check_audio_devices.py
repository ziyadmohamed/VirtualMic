import pyaudio

def print_device_info():
    p = pyaudio.PyAudio()
    print("Scanning Audio Devices...\n")
    
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')

    for i in range(0, numdevices):
        dev = p.get_device_info_by_host_api_device_index(0, i)
        name = dev.get('name')
        max_in = dev.get('maxInputChannels')
        max_out = dev.get('maxOutputChannels')
        sr = dev.get('defaultSampleRate')
        
        print(f"Device [{i}]: {name}")
        print(f"  - Max Inputs: {max_in}")
        print(f"  - Max Outputs: {max_out}")
        print(f"  - Sample Rate: {sr} Hz")
        print("-" * 30)

    p.terminate()
    print("\nIf 'Virtual Audio Cable' shows 0 Inputs/Outputs, it might be disabled in Windows.")

if __name__ == "__main__":
    print_device_info()
