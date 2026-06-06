param(
    [string]$Version = "4.8.1",
    [string]$DownloadUrl = "https://github.com/ValveSoftware/steam-audio/releases/download/v4.8.1/steamaudio_4.8.1.zip",
    [string]$InstallParent = ""
)

$ErrorActionPreference = "Stop"

function Find-SteamAudioRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SearchRoot
    )

    $directCandidate = Join-Path $SearchRoot "steamaudio"
    $directDll = Join-Path $directCandidate "lib\windows-x64\phonon.dll"
    if (Test-Path -LiteralPath $directDll) {
        return $directCandidate
    }

    $directories = Get-ChildItem -LiteralPath $SearchRoot -Directory -Recurse -ErrorAction SilentlyContinue
    foreach ($directory in $directories) {
        $dllPath = Join-Path $directory.FullName "lib\windows-x64\phonon.dll"
        if (Test-Path -LiteralPath $dllPath) {
            return $directory.FullName
        }
    }

    return $null
}

$packageRoot = if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) {
    Split-Path -Parent $MyInvocation.MyCommand.Path
} else {
    $PSScriptRoot
}
if ([string]::IsNullOrWhiteSpace($InstallParent)) {
    $InstallParent = Join-Path $packageRoot "third_party"
}

$InstallParent = [System.IO.Path]::GetFullPath($InstallParent)
$targetRoot = Join-Path $InstallParent "steamaudio"
$targetDll = Join-Path $targetRoot "lib\windows-x64\phonon.dll"

if (Test-Path -LiteralPath $targetDll) {
    Write-Host "Steam Audio is already installed at: $targetRoot"
    Write-Host "PureBit will auto-detect it from this package."
    exit 0
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("PureBitSteamAudio_" + [guid]::NewGuid().ToString("N"))
$zipPath = Join-Path $tempRoot ("steamaudio_{0}.zip" -f $Version)
$extractRoot = Join-Path $tempRoot "extract"

try {
    New-Item -ItemType Directory -Force -Path $InstallParent | Out-Null
    New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null

    Write-Host "Downloading Steam Audio $Version..."
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $zipPath -UseBasicParsing

    Write-Host "Extracting Steam Audio package..."
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force

    $sourceRoot = Find-SteamAudioRoot -SearchRoot $extractRoot
    if (-not $sourceRoot) {
        throw "Could not find a Steam Audio SDK folder containing lib\windows-x64\phonon.dll."
    }

    if (Test-Path -LiteralPath $targetRoot) {
        Remove-Item -LiteralPath $targetRoot -Recurse -Force
    }

    Move-Item -LiteralPath $sourceRoot -Destination $targetRoot

    if (-not (Test-Path -LiteralPath $targetDll)) {
        throw "Steam Audio install completed, but phonon.dll was not found at $targetDll."
    }

    Write-Host "Steam Audio installed successfully."
    Write-Host "Install path: $targetRoot"
    Write-Host "PureBit will auto-detect Steam Audio from this package."
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
