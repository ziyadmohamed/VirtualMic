"""
Check and list all audio recording devices
"""
import subprocess

def run_ps(cmd):
    result = subprocess.run(
        ["powershell", "-Command", cmd],
        capture_output=True,
        text=True
    )
    return result.stdout.strip()

print("="*70)
print("Audio Recording Devices Check")
print("="*70)

# Check all audio devices
print("\n1. All Audio Devices (from Device Manager):")
output = run_ps("Get-PnpDevice -Class 'MEDIA','AudioEndpoint' | Select-Object Status, FriendlyName")
print(output if output else "   No devices found")

# Check recording devices using Windows Audio
print("\n2. Checking Windows Audio Endpoints...")
script = """
[void][System.Reflection.Assembly]::LoadWithPartialName('System.Speech')
Add-Type -AssemblyName System.Core

$mmde = [System.Runtime.InteropServices.Marshal]::GetTypeFromCLSID([Guid]'BCDE0395-E52F-467C-8E3D-C4579291692E')
$mmd = [System.Activator]::CreateInstance($mmde)
$devices = $mmd.EnumerateAudioEndPoints(1, 1)  # 1 = Capture, 1 = Active

Write-Host "Recording Devices:"
for ($i = 0; $i -lt $devices.Count; $i++) {
    $device = $devices.Item($i)
    Write-Host "  - $($device.FriendlyName)"
}
"""

try:
    output = run_ps(script)
    print(output if output else "   Error checking endpoints")
except:
    print("   Could not enumerate audio endpoints")

# Alternative: Check via registry
print("\n3. Checking Audio Devices in Registry...")
reg_cmd = "Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio\\Capture\\*' -ErrorAction SilentlyContinue | Select-Object FriendlyName"
output = run_ps(reg_cmd)
print(output if output else "   No registry entries found")

print("\n" + "="*70)
print("INSTRUCTIONS:")
print("="*70)
print("\n1. افتح Sound Control Panel:")
print("   control mmsys.cpl")
print("\n2. روح لتاب 'Recording'")
print("\n3. كليك يمين في المساحة الفاضية")
print("\n4. اختر 'Show Disabled Devices' و 'Show Disconnected Devices'")
print("\n5. شوف 'Virtual Audio Device' موجود؟")
print("\n6. لو موجود بس disabled، كليك يمين → Enable")
print("="*70)
