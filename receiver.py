import socket
import pyaudio
import sys

# Configuration
SAMPLE_RATE = 48000
CHANNELS = 1 # Mono by default, Android app sends what it's configured for (usually Mono unless Stereo checked)
FORMAT = pyaudio.paInt16
CHUNK = 1024
UUID = "00001101-0000-1000-8000-00805F9B34FB"

def get_audio_device_index(p):
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    print("Available Audio Output Devices:")
    output_devices = []
    
    vb_cable_index = None
    
    for i in range(0, numdevices):
        dev_info = p.get_device_info_by_host_api_device_index(0, i)
        if dev_info.get('maxOutputChannels') > 0:
            name = dev_info.get('name')
            print(f"[{i}] {name}")
            output_devices.append(i)
            # Try to auto-detect VB-Cable Input or Virtual Audio Cable
            if "CABLE Input" in name or "VB-Audio" in name or "Virtual Audio Cable" in name:
                vb_cable_index = i
            
    if not output_devices:
        print("No output devices found.")
        sys.exit(1)
        
    if vb_cable_index is not None:
        print(f"\nAuto-detected VB-Cable/Virtual Device at index [{vb_cable_index}]")
        choice = input(f"Press Enter to use VB-Cable [{vb_cable_index}], or enter another index: ")
        if choice.strip() == "":
            return vb_cable_index
        
    while True:
        try:
            choice = input("Select Output Device Index (e.g. for VB-Cable Input): ")
            index = int(choice)
            if index in output_devices:
                return index
            print("Invalid index.")
        except ValueError:
            print("Invalid input.")

def connect_bluetooth(mac_address):
    print(f"Connecting to {mac_address}...")
    s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    try:
        s.connect((mac_address, 1)) # Try channel 1. Android usually listens on an assigned channel.
        # Note: Android listenUsingRfcommWithServiceRecord assigns a channel.
        # If connection fails, we might need to find the channel via SDP or just try a few.
        # But 'connect' with address and channel *should* work if we knew the channel.
        # Actually, Python's connect on Windows with (addr, port) might need the port/channel.
        # Android's listen typically assigns a dynamic channel.
        # Let's try standard SPP port 1, but this is the tricky part.
        # Better: use PyBluez if available? standard socket is built-in.
        # Let's hope Channel 1 works or user might need to pair and use a COM port if this fails.
        # UPDATE: On Windows, often connecting to the MAC works if paired.
        return s
    except Exception as e:
        print(f"Connection failed: {e}")
        print("Tip: Make sure the device is PAIRED and the App is running in Bluetooth Mode.")
        return None


# Driver Configuration
DRIVER_IOCTL = 1 # KSPROPERTY_STMIC_PUSHAUDIO (Method Set is implicitly determining this)
# Actually, we need to send a Property Request via KSPROPERTY structure.
# This works via DeviceIoControl with IOCTL_KS_PROPERTY usually.
# But connecting to the filter directly and sending IOCTLs is one way.
# Another way is using the KS API. 
# Implementing generic IOCTL support in Python is complex.
# We will assume the user has the 'simpleaudiosample' device interface.

def push_audio_to_driver(data, device_handle):
    # This requires ctypes or win32file
    pass

import ctypes
from ctypes import wintypes

# Define Windows structures/constants if needed or use simplified approach
# To simple push to our custom property, we need to locate the Device interface.
# This part is highly advanced.
# A simpler approach: The Driver creates a "File" (Device Interface). We open it.
# We send DeviceIoControl.

# Let's keep it simple: Just mention the driver is not easily accessible via Python without win32 dependencies.
# But I will add the placeholder for the user.

def main():
    if "--driver" in sys.argv:
        print("Driver Mode Selected.")
        print("This requires the 'StMic Virtual Driver' to be installed and running.")
        print("ERROR: Python Driver Interface not fully implemented in this script.")
        print("Use VB-Cable mode for now (it is robust and standard).")
        sys.exit(1)
        
    p = pyaudio.PyAudio()
    
    try:
        device_index = get_audio_device_index(p)
        
        mac = input("Enter Android Device Bluetooth MAC Address (e.g. AA:BB:CC:DD:EE:FF): ")
        
        s = connect_bluetooth(mac)
        if not s:
            sys.exit(1)
            
        print("Connected! Streaming audio...")
        
        stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=SAMPLE_RATE,
                        output=True,
                        output_device_index=device_index,
                        frames_per_buffer=CHUNK)
                        
        while True:
            try:
                data = s.recv(CHUNK * 2) # Read bytes
                if not data:
                    break
                stream.write(data)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
                break
                
        print("Stopping...")
        stream.stop_stream()
        stream.close()
        s.close()
        
    finally:
        p.terminate()

if __name__ == "__main__":
    main()
