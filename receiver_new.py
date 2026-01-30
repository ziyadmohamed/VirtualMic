"""
VirtualMic Receiver - New Network-based version
Receives audio from Android via WiFi and injects into Virtual Microphone
Uses PyAudio to route audio to the virtual device
"""
import socket
import struct
import sys
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try to import pyaudio
try:
    import pyaudio
except ImportError:
    logger.error("PyAudio not installed! Run: pip install pyaudio")
    sys.exit(1)

class VirtualMicReceiver:
    def __init__(self, host='0.0.0.0', port=8888):
        self.host = host
        self.port = port
        self.socket = None
        self.audio = None
        self.stream = None
        
        # Audio format (must match Android app)
        self.SAMPLE_RATE = 48000
        self.CHANNELS = 1  # Mono
        self.FORMAT = pyaudio.paInt16
        self.CHUNK_SIZE = 4800  # 100ms at 48kHz
        
    def find_virtual_mic(self):
        """Find the Virtual Audio Device (WDM) microphone"""
        logger.info("Searching for Virtual Audio Device...")
        
        self.audio = pyaudio.PyAudio()
        
        # List all audio devices
        for i in range(self.audio.get_device_count()):
            info = self.audio.get_device_info_by_index(i)
            name = info.get('name', '')
            
            # Look for our virtual device
            if ('Virtual' in name or 'Simple' in name) and info['maxInputChannels'] > 0:
                logger.info(f"Found virtual mic: {name} (index {i})")
                logger.info(f"  Max channels: {info['maxInputChannels']}")
                logger.info(f"  Sample rate: {int(info['defaultSampleRate'])} Hz")
                return i, info
        
        logger.error("Virtual Audio Device not found!")
        logger.info("\nAvailable input devices:")
        for i in range(self.audio.get_device_count()):
            info = self.audio.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                logger.info(f"  [{i}] {info['name']}")
        
        return None, None
    
    def open_audio_stream(self, device_index, device_info):
        """Open PyAudio output stream to virtual mic"""
        logger.info(f"Opening audio stream to device index {device_index}...")
        
        # Use device's actual channel count
        channels = min(self.CHANNELS, device_info['maxOutputChannels'])
        if channels == 0:
            channels = device_info['maxInputChannels']  # Fallback to input channels
        
        logger.info(f"  Using {channels} channel(s)")
        
        try:
            # Open OUTPUT stream (we're writing TO the virtual mic)
            self.stream = self.audio.open(
                format=self.FORMAT,
                channels=channels,
                rate=int(device_info['defaultSampleRate']),
                output=True,
                output_device_index=device_index,
                frames_per_buffer=self.CHUNK_SIZE
            )
            logger.info("✅ Audio stream opened successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to open audio stream: {e}")
            return False
    
    def start_server(self):
        """Start TCP server to receive audio from Android"""
        logger.info(f"Starting server on {self.host}:{self.port}...")
        
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.socket.bind((self.host, self.port))
            self.socket.listen(1)
            logger.info(f"✅ Server listening on {self.host}:{self.port}")
            
            while True:
                logger.info("\nWaiting for Android connection...")
                client, addr = self.socket.accept()
                logger.info(f"✅ Connected from {addr}")
                
                try:
                    self.handle_client(client)
                except Exception as e:
                    logger.error(f"Error handling client: {e}")
                finally:
                    client.close()
                    logger.info("Client disconnected")
                    
        except KeyboardInterrupt:
            logger.info("\nShutting down...")
        finally:
            self.cleanup()
    
    def handle_client(self, client):
        """Handle audio streaming from connected Android client"""
        logger.info("Streaming audio...")
        
        bytes_received = 0
        
        while True:
            # Read audio chunk from network
            data = client.recv(self.CHUNK_SIZE)
            
            if not data:
                break
            
            # Write audio to virtual microphone
            if self.stream:
                try:
                    self.stream.write(data)
                    bytes_received += len(data)
                    
                    # Log progress every 1MB
                    if bytes_received % (1024 * 1024) == 0:
                        logger.info(f"Received {bytes_received / (1024*1024):.1f} MB")
                        
                except Exception as e:
                    logger.error(f"Error writing audio: {e}")
                    break
    
    def cleanup(self):
        """Clean up resources"""
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.audio:
            self.audio.terminate()
        if self.socket:
            self.socket.close()
        logger.info("Cleanup completed")

def main():
    print("="*70)
    print("VirtualMic Receiver - Network Edition")
    print("="*70)
    
    receiver = VirtualMicReceiver(host='0.0.0.0', port=8888)
    
    # Find virtual microphone
    device_index, device_info = receiver.find_virtual_mic()
    
    if device_index is None:
        print("\n❌ Virtual Audio Device not found!")
        print("\nMake sure:")
        print("  1. StMicDriver is installed")
        print("  2. Device appears in Device Manager")
        print("  3. Device is enabled in Sound Settings")
        input("\nPress Enter to exit...")
        return
    
    # Open audio stream
    if not receiver.open_audio_stream(device_index, device_info):
        print("\n❌ Failed to open audio stream")
        input("\nPress Enter to exit...")
        return
    
    print("\n✅ Ready to receive audio!")
    print(f"\n📱 Connect Android app to:")
    print(f"   IP: <Your PC IP Address>")
    print(f"   Port: 8888")
    print("\nPress Ctrl+C to stop")
    print("="*70)
    
    # Start server
    receiver.start_server()

if __name__ == "__main__":
    main()
