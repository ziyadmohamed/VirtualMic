"""
Check driver installation status and diagnose issues
"""
import subprocess
import os

def run_command(cmd):
    """Run PowerShell command and return output"""
    try:
        result = subprocess.run(
            ["powershell", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as e:
        return "", str(e), -1

print("="*70)
print("StMicDriver Installation Diagnostics")
print("="*70)

print("\n1. Checking if driver files are in System32...")
stdout, stderr, code = run_command('Test-Path "C:\\Windows\\System32\\drivers\\SimpleAudioSample.sys"')
if stdout == "True":
    print("   ✅ SimpleAudioSample.sys found in System32\\drivers")
else:
    print("   ❌ SimpleAudioSample.sys NOT found in System32\\drivers")
    print("   ℹ️  This means driver wasn't copied during installation")

print("\n2. Checking installed drivers...")
stdout, stderr, code = run_command('pnputil /enum-drivers | Select-String "SimpleAudio" -Context 2,2')
if stdout:
    print(f"   ✅ Found in driver store:\n{stdout}")
else:
    print("   ❌ Driver NOT in driver store")

print("\n3. Checking for driver devices...")
stdout, stderr, code = run_command("Get-PnpDevice | Where-Object {$_.FriendlyName -like '*Simple*' -or $_.FriendlyName -like '*Virtual Audio*'} | Format-Table Status, FriendlyName, InstanceId")
if stdout:
    print(f"   Devices found:\n{stdout}")
else:
    print("   ❌ No matching devices found")

print("\n4. Checking Windows Setup API logs...")
stdout, stderr, code = run_command("Get-Content 'C:\\Windows\\INF\\setupapi.dev.log' -Tail 200 | Select-String 'SimpleAudio' -Context 3")
if stdout:
    print(f"   Setup log entries:\n{stdout[:500]}...")
else:
    print("   ℹ️  No recent entries in setup log")

print("\n5. Checking Event Logs for driver errors...")
stdout, stderr, code = run_command("Get-EventLog -LogName System -Newest 50 -EntryType Error,Warning | Where-Object {$_.Message -like '*driver*' -or $_.Message -like '*audio*'} | Select-Object -First 5 | Format-List TimeGenerated, Source, Message")
if stdout:
    print(f"   Recent errors:\n{stdout[:500]}...")
else:
    print("   ℹ️  No recent driver errors")

print("\n" + "="*70)
print("DIAGNOSIS:")
print("="*70)

# Check setupapi.dev.log for actual errors
stdout, stderr, code = run_command("Get-Content 'C:\\Windows\\INF\\setupapi.dev.log' -Tail 500 | Select-String 'error|fail' -Context 1")
if "SimpleAudio" in stdout or "sysvad" in stdout.lower():
    print("⚠️  Found errors in setup log!")
    print("   The driver installation likely failed.")
    print("\n   Most common causes:")
    print("   1. INF file has errors or is incompatible")
    print("   2. Driver binary (.sys) has errors")
    print("   3. Missing dependencies")
    print("   4. Architecture mismatch (ARM64 vs x64)")
else:
    print("ℹ️  Driver may have installed but didn't create a device")
    print("   This is actually EXPECTED for this driver!")
    print("\n   Reason: StMicDriver is a 'Software Device' driver.")
    print("   It won't appear until we manually create the device instance.")
    print("\n   📝 NEXT STEP: We need to manually create the device using devcon")

print("="*70)
