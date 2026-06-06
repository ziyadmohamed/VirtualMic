param(
    [string]$ArtifactsRoot = "$(Split-Path -Parent $MyInvocation.MyCommand.Path)\artifacts",
    [switch]$ForceOwnership
)

$ErrorActionPreference = "Stop"

function Get-LatestArtifactDir {
    param([string]$Root)
    if (-not (Test-Path $Root)) { return $null }
    $dirs = Get-ChildItem -Path $Root -Directory | Sort-Object LastWriteTime -Descending
    foreach ($d in $dirs) {
        $inf = Join-Path $d.FullName "StMicDriver-Output\StMicDriver\x64\Release\package\SimpleAudioSample.inf"
        if (Test-Path $inf) { return $d.FullName }
    }
    return $null
}

function Get-ApoInfoFromInf {
    param([string]$InfPath)
    $content = Get-Content -Path $InfPath -ErrorAction Stop
    $clsid = ($content | Where-Object { $_ -match '^VirtualMicApo\.CLSID\s*=\s*"' } | Select-Object -First 1)
    $friendly = ($content | Where-Object { $_ -match '^VirtualMicApo\.FriendlyName\s*=\s*"' } | Select-Object -First 1)
    $clsidValue = $null
    $friendlyValue = $null
    if ($clsid) {
        $clsidValue = ($clsid -replace '.*=\s*"', '') -replace '"\s*$', ''
    }
    if ($friendly) {
        $friendlyValue = ($friendly -replace '.*=\s*"', '') -replace '"\s*$', ''
    }
    if (-not $clsidValue) {
        $clsidValue = "{A4B73D9A-7D0E-4E7B-9E4D-9D6D3C1A9B2F}"
    }
    if (-not $friendlyValue) {
        $friendlyValue = "VirtualMic APO"
    }
    return @{ CLSID = $clsidValue; FriendlyName = $friendlyValue }
}

function Assert-Admin {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "This script must be run as Administrator."
    }
}

Assert-Admin

$artifactDir = Get-LatestArtifactDir -Root $ArtifactsRoot
if (-not $artifactDir) {
    throw "No artifact with driver package found under $ArtifactsRoot"
}

$pkgDir = Join-Path $artifactDir "StMicDriver-Output\StMicDriver\x64\Release\package"
$infPath = Join-Path $pkgDir "SimpleAudioSample.inf"
$apoPath = Join-Path $pkgDir "VirtualMicApo.dll"

if (-not (Test-Path $apoPath)) {
    throw "APO DLL not found: $apoPath"
}
if (-not (Test-Path $infPath)) {
    throw "INF not found: $infPath"
}

$apoInfo = Get-ApoInfoFromInf -InfPath $infPath
$clsid = $apoInfo.CLSID
$friendly = $apoInfo.FriendlyName

Write-Host "Using artifact: $artifactDir"
Write-Host "APO DLL: $apoPath"
Write-Host "CLSID: $clsid"

$destDll = Join-Path $env:SystemRoot "System32\VirtualMicApo.dll"
$copyOk = $false
try {
    Copy-Item -Path $apoPath -Destination $destDll -Force
    $copyOk = $true
} catch {
    if (-not $ForceOwnership) {
        throw
    }
}

if (-not $copyOk -and $ForceOwnership) {
    Write-Host "Copy failed; attempting to take ownership of $destDll"
    if (Test-Path $destDll) {
        & takeown.exe /f $destDll /a | Out-Null
        & icacls.exe $destDll /grant:r "Administrators:F" | Out-Null
    }
    Copy-Item -Path $apoPath -Destination $destDll -Force
}

$clsidKey = "Registry::HKEY_CLASSES_ROOT\CLSID\$clsid"
$inprocKey = "$clsidKey\\InprocServer32"

New-Item -Path $clsidKey -Force | Out-Null
New-ItemProperty -Path $clsidKey -Name "(default)" -Value $friendly -Force | Out-Null
New-Item -Path $inprocKey -Force | Out-Null
New-ItemProperty -Path $inprocKey -Name "(default)" -Value $destDll -Force | Out-Null
New-ItemProperty -Path $inprocKey -Name "ThreadingModel" -Value "Both" -Force | Out-Null

Write-Host "APO registry entries written."

# Basic verification
$dllOk = Test-Path $destDll
$regDll = (Get-ItemProperty -Path $inprocKey -Name "(default)" -ErrorAction SilentlyContinue)."(default)"
$regThreading = (Get-ItemProperty -Path $inprocKey -Name "ThreadingModel" -ErrorAction SilentlyContinue)."ThreadingModel"

if ($dllOk -and $regDll -eq $destDll -and $regThreading -eq "Both") {
    Write-Host "APO install looks OK."
    exit 0
}

Write-Host "APO install verification failed."
Write-Host "DLL exists: $dllOk"
Write-Host "Registry InprocServer32: $regDll"
Write-Host "Registry ThreadingModel: $regThreading"
exit 1
