"""
Aggressive Audio Interface Enumerator
Lists ALL interfaces in KSCATEGORY_AUDIO and KSCATEGORY_RENDER
to find the hidden StMicDriver
"""
import ctypes
from ctypes import wintypes

setupapi = ctypes.windll.setupapi
kernel32 = ctypes.windll.kernel32

class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", wintypes.BYTE * 8)]

# KSCATEGORY_AUDIO
KSCATEGORY_AUDIO = GUID(0x6994AD04, 0x93EF, 0x11D0, (wintypes.BYTE*8)(0xA3, 0xCC, 0x00, 0xA0, 0xC9, 0x22, 0x31, 0x96))
# KSCATEGORY_RENDER
KSCATEGORY_RENDER = GUID(0x65E8773E, 0x8F56, 0x11D0, (wintypes.BYTE*8)(0xA3, 0xB9, 0x00, 0xA0, 0xC9, 0x22, 0x31, 0x96))
# KSCATEGORY_CAPTURE
KSCATEGORY_CAPTURE = GUID(0x65E8773D, 0x8F56, 0x11D0, (wintypes.BYTE*8)(0xA3, 0xB9, 0x00, 0xA0, 0xC9, 0x22, 0x31, 0x96))

def list_interfaces(category_guid, category_name):
    print(f"\n--- Scanning {category_name} ---")
    
    hDevInfo = setupapi.SetupDiGetClassDevsW(ctypes.byref(category_guid), None, None, 0x12) # PRESENT | DEVICEINTERFACE
    if hDevInfo == -1: return

    class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("InterfaceClassGuid", GUID), ("Flags", wintypes.DWORD), ("Reserved", ctypes.POINTER(wintypes.ULONG))]
    
    did = SP_DEVICE_INTERFACE_DATA()
    did.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
    
    idx = 0
    while setupapi.SetupDiEnumDeviceInterfaces(hDevInfo, None, ctypes.byref(category_guid), idx, ctypes.byref(did)):
        req_size = wintypes.DWORD()
        setupapi.SetupDiGetDeviceInterfaceDetailW(hDevInfo, ctypes.byref(did), None, 0, ctypes.byref(req_size), None)
        
        class SP_DEVICE_INTERFACE_DETAIL_DATA(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("DevicePath", wintypes.WCHAR * req_size.value)]
            
        didd = SP_DEVICE_INTERFACE_DETAIL_DATA()
        didd.cbSize = 6 if ctypes.sizeof(ctypes.c_void_p) == 8 else 5
        
        if setupapi.SetupDiGetDeviceInterfaceDetailW(hDevInfo, ctypes.byref(did), ctypes.byref(didd), req_size, None, None):
            path = didd.DevicePath
            print(f"[{idx}] {path}")
            if "simple" in path.lower() or "virtual" in path.lower() or "root" in path.lower():
                print(f"    *** POTENTIAL MATCH ***")
        idx += 1
    
    setupapi.SetupDiDestroyDeviceInfoList(hDevInfo)

list_interfaces(KSCATEGORY_AUDIO, "KSCATEGORY_AUDIO")
list_interfaces(KSCATEGORY_RENDER, "KSCATEGORY_RENDER")
list_interfaces(KSCATEGORY_CAPTURE, "KSCATEGORY_CAPTURE")
input("\nPress Enter...")
