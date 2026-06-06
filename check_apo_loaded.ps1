param(
    [string]$ApoDllName = "VirtualMicApo.dll",
    [switch]$RestartAudio
)

$ErrorActionPreference = "Stop"

if ($RestartAudio) {
    Write-Host "Restarting audio services..."
    Restart-Service audiosrv,AudioEndpointBuilder -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

Write-Host "Checking APO DLL load status: $ApoDllName"

# 1) Verify DLL exists in System32
$systemDll = Join-Path $env:SystemRoot "System32\$ApoDllName"
if (Test-Path $systemDll) {
    Write-Host "DLL exists: $systemDll"
} else {
    Write-Host "DLL missing: $systemDll"
}

# 2) Check registry registration (best-effort)
try {
    $clsidKey = Get-ChildItem "Registry::HKEY_CLASSES_ROOT\CLSID" -ErrorAction Stop |
        Where-Object {
            $_.PSChildName -match '^\{[0-9A-Fa-f-]+\}$' -and
            (Get-ItemProperty -Path $_.PsPath -Name "(default)" -ErrorAction SilentlyContinue)."(default)" -eq "VirtualMic APO"
        } | Select-Object -First 1

    if ($clsidKey) {
        $inproc = Get-ItemProperty -Path "$($clsidKey.PsPath)\InprocServer32" -ErrorAction SilentlyContinue
        if ($inproc) {
            Write-Host "Registry InprocServer32: $($inproc.'(default)')"
        }
    } else {
        Write-Host "Registry CLSID for 'VirtualMic APO' not found (friendly-name scan)."
    }
} catch {
    Write-Host "Registry check skipped: $($_.Exception.Message)"
}

# 3) Check audiodg module list
$loaded = $false
try {
    $audiodg = Get-Process audiodg -ErrorAction Stop
    $mod = $audiodg.Modules | Where-Object { $_.ModuleName -ieq $ApoDllName } | Select-Object -First 1
    if ($mod) {
        Write-Host "APO loaded in audiodg: $($mod.FileName)"
        $loaded = $true
    } else {
        Write-Host "APO not listed in audiodg modules."
    }
} catch {
    Write-Host "Module enumeration failed: $($_.Exception.Message)"
}

# 4) Fallback: tasklist /m
if (-not $loaded) {
    try {
        $tasklist = tasklist /m $ApoDllName 2>$null
        if ($tasklist -match "audiodg.exe") {
            Write-Host "tasklist reports audiodg.exe has $ApoDllName loaded."
            $loaded = $true
        } else {
            Write-Host "tasklist does not show $ApoDllName loaded."
        }
    } catch {
        Write-Host "tasklist check skipped: $($_.Exception.Message)"
    }
}

if ($loaded) {
    Write-Host "APO appears to be loaded and active."
    exit 0
}

Write-Host "APO does not appear to be loaded. Ensure the device is active and retry."
exit 1
