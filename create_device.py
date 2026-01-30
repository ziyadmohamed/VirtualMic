"""
Create Virtual Audio Device Instance using Windows Setup API
"""
import ctypes
from ctypes import wintypes
import sys

# setupapi.dll functions
setupapi = ctypes.windll.setupapi
kernel32 = ctypes.windll.kernel32

# Constants
DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010
SPDRP_DEVICEDESC = 0x00000000
ERROR_NO_MORE_ITEMS = 259
INVALID_HANDLE_VALUE = -1

# GUID for Media class {4d36e96c-e325-11ce-bfc1-08002be10318}
MEDIA_CLASS_GUID = "{4d36e96c-e325-11ce-bfc1-08002be10318}"

def is_admin():
    """Check if running as administrator"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def create_virtual_device():
    """Create virtual audio device instance"""
    
    if not is_admin():
        print("❌ Error: This script must run as Administrator!")
        print("\nRight-click Python and select 'Run as administrator'")
        return False
    
    print("="*70)
    print("Creating Virtual Audio Device Instance")
    print("="*70)
    
    # Hardware ID for our driver
    hardware_id = "Root\\SimpleAudioSample"
    inf_path = r"C:\Users\MU\Downloads\StMicDriver-Output\Release\package\SimpleAudioSample.inf"
    
    print(f"\n1. Hardware ID: {hardware_id}")
    print(f"2. INF Path: {inf_path}")
    
    # Method 1: Try using UpdateDriverForPlugAndPlayDevices
    print("\n3. Attempting to install driver...")
    
    # Load newdev.dll for UpdateDriverForPlugAndPlayDevices
    try:
        newdev = ctypes.windll.newdev
        
        # BOOL UpdateDriverForPlugAndPlayDevicesW(
        #   HWND hwndParent,
        #   LPCWSTR HardwareId,
        #   LPCWSTR FullInfPath,
        #   DWORD InstallFlags,
        #   PBOOL bRebootRequired
        # )
        
        reboot_required = wintypes.BOOL()
        INSTALLFLAG_FORCE = 0x00000001
        INSTALLFLAG_READONLY = 0x00000002
        INSTALLFLAG_NONINTERACTIVE = 0x00000004
        
        result = newdev.UpdateDriverForPlugAndPlayDevicesW(
            None,  # No parent window
            hardware_id,
            inf_path,
            INSTALLFLAG_FORCE | INSTALLFLAG_NONINTERACTIVE,
            ctypes.byref(reboot_required)
        )
        
        if result:
            print("✅ Device created successfully!")
            if reboot_required.value:
                print("⚠️  Reboot required to complete installation")
            else:
                print("✅ No reboot required")
            return True
        else:
            error = kernel32.GetLastError()
            print(f"⚠️  UpdateDriverForPlugAndPlayDevices failed: Error {error}")
            
            # Common errors:
            # 0xE0000235 (3758096949) = Device not started
            # 0xE0000247 (3758096967) = No such device
            
            if error == 0xE0000235:
                print("\n   This error is OK - it means driver is installed")
                print("   but device needs to be created manually.")
            
    except Exception as e:
        print(f"❌ Failed: {e}")
    
    print("\n" + "="*70)
    print("ALTERNATIVE METHOD:")
    print("="*70)
    print("\nSince automatic device creation failed, you need DevCon:")
    print("\n1. Download DevCon from:")
    print("   https://github.com/microsoft/Windows-driver-samples/tree/main/tools/devcon")
    print("\n2. Or from WDK at:")
    print("   C:\\Program Files (x86)\\Windows Kits\\10\\Tools\\x64\\devcon.exe")
    print("\n3. Run:")
    print(f'   devcon.exe install "{inf_path}" Root\\SimpleAudioSample')
    
    return False

if __name__ == "__main__":
    success = create_virtual_device()
    
    if not success:
        print("\n" + "="*70)
        print("MANUAL STEPS:")
        print("="*70)
        print("\n1. Download devcon.exe")
        print("2. Place it in Downloads folder")
        print("3. Run (PowerShell as Admin):")
        print('   .\\devcon.exe install "C:\\Users\\MU\\Downloads\\StMicDriver-Output\\Release\\package\\SimpleAudioSample.inf" Root\\SimpleAudioSample')
        print("="*70)
    
    input("\nPress Enter to exit...")
