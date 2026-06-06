import os
import sys
import subprocess
import ctypes

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def find_inf():
    search_dirs = [
        r"C:\Users\MU\Downloads\VirtualMic",
        r"C:\Users\MU\Downloads"
    ]
    for d in search_dirs:
        if not os.path.exists(d):
            continue
        for root, dirs, files in os.walk(d):
            if "SimpleAudioSample.inf" in files:
                # Prioritize paths that are in a Release or package directory
                full_path = os.path.join(root, "SimpleAudioSample.inf")
                if "Release" in full_path or "package" in full_path:
                    return full_path
    
    # Fallback to any found
    for d in search_dirs:
        if not os.path.exists(d):
            continue
        for root, dirs, files in os.walk(d):
            if "SimpleAudioSample.inf" in files:
                return os.path.join(root, "SimpleAudioSample.inf")
    return None

def count_existing_devices():
    # Search in WMI/CIM for ROOT\MEDIA devices that match Simple Audio Sample
    ps_cmd = (
        "Get-CimInstance Win32_PnPEntity | "
        "Where-Object { $_.DeviceID -like 'ROOT\\MEDIA*' -and ($_.Name -like '*BM Mic*' -or $_.Name -like '*Simple Audio*') } | "
        "Measure-Object | Select-Object -ExpandProperty Count"
    )
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd]
    try:
        output = subprocess.check_output(cmd).decode('utf-8').strip()
        return int(output) if output else 0
    except Exception as e:
        print("Error counting devices:", e)
        return 0

def add_device(inf_path, hardware_id="Root\\SimpleAudioSample"):
    ps_script = f"""
$infPath = "{inf_path}"
$hardwareId = "{hardware_id}"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;
using System.ComponentModel;

public static class VirtualMicRootDeviceApi
{{
    private const uint DICD_GENERATE_ID = 0x00000001;
    private const uint SPDRP_HARDWAREID = 0x00000001;
    private const int DIF_REGISTERDEVICE = 0x00000019;
    private static readonly IntPtr INVALID_HANDLE_VALUE = new IntPtr(-1);

    [StructLayout(LayoutKind.Sequential)]
    public struct SP_DEVINFO_DATA
    {{
        public uint cbSize;
        public Guid ClassGuid;
        public uint DevInst;
        public IntPtr Reserved;
    }}

    [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool SetupDiGetINFClass(string InfName, out Guid ClassGuid, StringBuilder ClassName, int ClassNameSize, out int RequiredSize);

    [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr SetupDiCreateDeviceInfoList(ref Guid ClassGuid, IntPtr hwndParent);

    [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool SetupDiCreateDeviceInfo(IntPtr DeviceInfoSet, string DeviceName, ref Guid ClassGuid, string DeviceDescription, IntPtr hwndParent, uint CreationFlags, ref SP_DEVINFO_DATA DeviceInfoData);

    [DllImport("setupapi.dll", SetLastError = true)]
    private static extern bool SetupDiSetDeviceRegistryProperty(IntPtr DeviceInfoSet, ref SP_DEVINFO_DATA DeviceInfoData, uint Property, byte[] PropertyBuffer, uint PropertyBufferSize);

    [DllImport("setupapi.dll", SetLastError = true)]
    private static extern bool SetupDiCallClassInstaller(int InstallFunction, IntPtr DeviceInfoSet, ref SP_DEVINFO_DATA DeviceInfoData);

    public static void CreateRootDevice(string infPath, string hardwareId)
    {{
        Guid classGuid;
        int requiredSize;
        StringBuilder className = new StringBuilder(260);
        if (!SetupDiGetINFClass(infPath, out classGuid, className, className.Capacity, out requiredSize))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "SetupDiGetINFClass failed.");

        IntPtr infoSet = SetupDiCreateDeviceInfoList(ref classGuid, IntPtr.Zero);
        if (infoSet == INVALID_HANDLE_VALUE)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "SetupDiCreateDeviceInfoList failed.");

        try {{
            SP_DEVINFO_DATA deviceInfo = new SP_DEVINFO_DATA();
            deviceInfo.cbSize = (uint)Marshal.SizeOf(typeof(SP_DEVINFO_DATA));

            if (!SetupDiCreateDeviceInfo(infoSet, className.ToString(), ref classGuid, null, IntPtr.Zero, DICD_GENERATE_ID, ref deviceInfo))
                throw new Win32Exception(Marshal.GetLastWin32Error(), "SetupDiCreateDeviceInfo failed.");

            byte[] hardwareIdBytes = Encoding.Unicode.GetBytes(hardwareId + "\\0\\0");
            if (!SetupDiSetDeviceRegistryProperty(infoSet, ref deviceInfo, SPDRP_HARDWAREID, hardwareIdBytes, (uint)hardwareIdBytes.Length))
                throw new Win32Exception(Marshal.GetLastWin32Error(), "SetupDiSetDeviceRegistryProperty failed.");

            if (!SetupDiCallClassInstaller(DIF_REGISTERDEVICE, infoSet, ref deviceInfo))
                throw new Win32Exception(Marshal.GetLastWin32Error(), "SetupDiCallClassInstaller(DIF_REGISTERDEVICE) failed.");
        }} finally {{
        }}
    }}
}}
"@

[VirtualMicRootDeviceApi]::CreateRootDevice($infPath, $hardwareId)
write-output "Device added successfully"
"""
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script]
    try:
        subprocess.check_call(cmd)
        return True
    except subprocess.CalledProcessError as e:
        print("Failed to add device:", e)
        return False

def remove_devices():
    # Disable and uninstall ROOT\MEDIA devices matching hardware ID or name
    # Using pnputil and/or powershell command
    ps_cmd = (
        "Get-PnpDevice -HardwareID 'Root\\SimpleAudioSample' -ErrorAction SilentlyContinue | "
        "ForEach-Object { $_ | Disable-PnpDevice -Confirm:$false; $_ | Uninstall-PnpDevice -Confirm:$false }; "
        "Get-CimInstance Win32_PnPEntity | "
        "Where-Object { $_.DeviceID -like 'ROOT\\MEDIA*' -and ($_.Name -like '*BM Mic*' -or $_.Name -like '*Simple Audio*') } | "
        "ForEach-Object { powershell -Command \"Disable-PnpDevice -InstanceId '$($_.DeviceID)' -Confirm:\\$false; Uninstall-PnpDevice -InstanceId '$($_.DeviceID)' -Confirm:\\$false\" }"
    )
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd]
    try:
        subprocess.check_call(cmd)
        print("Successfully removed all virtual devices.")
        return True
    except subprocess.CalledProcessError as e:
        print("Failed to remove devices:", e)
        return False

def main():
    if not is_admin():
        print("This script must be run as Administrator.")
        # Re-run with admin
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "--remove":
        remove_devices()
        return

    target_count = 1
    if len(sys.argv) > 1:
        try:
            target_count = int(sys.argv[1])
        except ValueError:
            pass

    inf_path = find_inf()
    if not inf_path:
        print("Error: Could not locate SimpleAudioSample.inf in the workspace.")
        sys.exit(1)
    
    print(f"Found INF at: {inf_path}")
    
    current_count = count_existing_devices()
    print(f"Currently installed virtual devices: {current_count}")
    
    if current_count >= target_count:
        print(f"Already have {current_count} devices, which is >= target of {target_count}.")
        return

    to_add = target_count - current_count
    print(f"Adding {to_add} more virtual device instances to reach {target_count}...")
    
    success_count = 0
    for i in range(to_add):
        print(f"Creating device instance {current_count + i + 1}/{target_count}...")
        if add_device(inf_path):
            success_count += 1
            
    print(f"Finished! Successfully added {success_count} device instances.")

if __name__ == "__main__":
    main()
