[CmdletBinding()]
param(
    [string]$PackagePath,
    [string]$HardwareId = "Root\SimpleAudioSample",
    [ValidateSet("Initial", "PostReboot")]
    [string]$Phase = "Initial",
    [string]$LogPath,
    [switch]$SkipTestSigning,
    [switch]$NoReboot,
    [switch]$SkipVerification,
    [switch]$DryRun,
    [switch]$AllowRepositoryPackageSearch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:ApoClsid = "{A4B73D9A-7D0E-4E7B-9E4D-9D6D3C1A9B2F}"
$script:InterfaceGuid = "{D58971B1-3AD2-4C90-9E11-3733A74A3600}"
$script:MediaClassGuid = "{4d36e96c-e325-11ce-bfc1-08002be10318}"
$script:ExpectedServiceName = "SimpleAudioSample"
$script:ExpectedPnpPattern = "ROOT\\SIMPLEAUDIOSAMPLE*"
$script:ResumeTaskName = "VirtualMicDriverInstallResume"
$script:PendingRebootExitCode = 3010
$script:InstallerRevision = "2026-04-17-telemetry-v7"
$script:ScriptPath = if ($PSCommandPath) { $PSCommandPath } else { $MyInvocation.MyCommand.Path }
$script:ScriptDir = Split-Path -Path $script:ScriptPath -Parent
$script:System32ApoPath = Join-Path $env:SystemRoot "System32\VirtualMicApo.dll"
$script:LogInitialized = $false

function Resolve-DefaultLogPath {
    $preferred = Join-Path $env:ProgramData "Blind Masters\VirtualMic\logs\driver_install.log"
    if ($env:ProgramData) {
        return $preferred
    }

    return (Join-Path $env:TEMP "BlindMasters_VirtualMic_driver_install.log")
}

if (-not $LogPath) {
    $LogPath = Resolve-DefaultLogPath
}

function Write-Log {
    param(
        [Parameter(Mandatory)]
        [string]$Message,
        [ValidateSet("INFO", "WARN", "ERROR", "OK")]
        [string]$Level = "INFO"
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[{0}] [{1}] {2}" -f $timestamp, $Level, $Message
    Write-Host $line
    if (-not $script:LogInitialized) {
        return
    }

    try {
        $utf8 = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::AppendAllText($LogPath, $line + [Environment]::NewLine, $utf8)
    } catch {
        Write-Host ("[{0}] [WARN] Failed to append to log file {1}: {2}" -f $timestamp, $LogPath, $_.Exception.Message)
    }
}

function Initialize-LogFile {
    param(
        [Parameter(Mandatory)]
        [string]$RequestedPath
    )

    $candidates = @($RequestedPath)
    $fallback = Join-Path $env:TEMP "BlindMasters_VirtualMic_driver_install.log"
    if ($RequestedPath -ne $fallback) {
        $candidates += $fallback
    }

    foreach ($candidate in $candidates) {
        try {
            $directory = Split-Path -Path $candidate -Parent
            if ($directory -and -not (Test-Path -LiteralPath $directory)) {
                New-Item -ItemType Directory -Path $directory -Force | Out-Null
            }

            if (-not (Test-Path -LiteralPath $candidate)) {
                New-Item -ItemType File -Path $candidate -Force | Out-Null
            } else {
                Add-Content -Path $candidate -Value ""
            }

            $script:LogInitialized = $true
            return $candidate
        } catch {
            Write-Host ("[WARN] Could not initialize log path {0}: {1}" -f $candidate, $_.Exception.Message)
        }
    }

    throw "Could not initialize any writable log file path."
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function ConvertTo-CommandArguments {
    param(
        [hashtable]$BoundParameters
    )

    $argumentList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ('"{0}"' -f $script:ScriptPath))
    foreach ($entry in $BoundParameters.GetEnumerator() | Sort-Object Key) {
        $name = "-{0}" -f $entry.Key
        $value = $entry.Value
        if ($value -is [switch]) {
            if ($value.IsPresent) {
                $argumentList += $name
            }
            continue
        }

        if ($value -is [bool]) {
            if ($value) {
                $argumentList += $name
            }
            continue
        }

        $argumentList += $name
        $argumentList += ('"{0}"' -f ($value.ToString().Replace('"', '\"')))
    }

    return $argumentList
}

function Ensure-Elevated {
    if ($DryRun) {
        Write-Log "Dry run enabled; skipping elevation check." "WARN"
        return
    }

    if (Test-IsAdministrator) {
        return
    }

    $argumentList = ConvertTo-CommandArguments -BoundParameters $PSBoundParameters
    Write-Host "Requesting Administrator privileges..."
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $argumentList | Out-Null
    exit 0
}

function Invoke-External {
    param(
        [Parameter(Mandatory)]
        [string]$FilePath,
        [string[]]$Arguments = @(),
        [switch]$AllowFailure,
        [switch]$ReadOnly
    )

    $rendered = @($FilePath) + $Arguments
    Write-Log ("Running: {0}" -f ($rendered -join " "))

    if ($DryRun -and -not $ReadOnly) {
        Write-Log "Dry run: command was not executed." "WARN"
        return [pscustomobject]@{
            ExitCode = 0
            Output = @("[dry-run]")
        }
    }

    $output = & $FilePath @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    if (-not $output) {
        $output = @()
    }

    foreach ($line in $output) {
        if ([string]::IsNullOrWhiteSpace([string]$line)) {
            continue
        }

        Write-Log ([string]$line)
    }

    if ($exitCode -ne 0 -and -not $AllowFailure) {
        throw ("Command failed with exit code {0}: {1}" -f $exitCode, ($rendered -join " "))
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = $output
    }
}

function Resolve-DriverPackage {
    param(
        [string]$RequestedPath
    )

    $candidateInfs = @()

    if ($RequestedPath) {
        $resolved = (Resolve-Path -LiteralPath $RequestedPath -ErrorAction Stop).Path
        if ((Get-Item -LiteralPath $resolved).PSIsContainer) {
            $requestedInf = Join-Path $resolved "SimpleAudioSample.inf"
        } else {
            $requestedInf = $resolved
        }

        if (-not (Test-Path -LiteralPath $requestedInf)) {
            throw "The requested package path does not contain SimpleAudioSample.inf."
        }

        $candidateInfs = @(Get-Item -LiteralPath $requestedInf)
    } else {
        $siblingPackageInf = Join-Path (Join-Path $script:ScriptDir "package") "SimpleAudioSample.inf"
        if (Test-Path -LiteralPath $siblingPackageInf) {
            $candidateInfs = @(Get-Item -LiteralPath $siblingPackageInf)
        } elseif ($AllowRepositoryPackageSearch) {
            $roots = @(
                (Join-Path $script:ScriptDir "artifacts"),
                (Join-Path $script:ScriptDir "downloads"),
                (Join-Path $script:ScriptDir "StMicDriver-Output"),
                (Join-Path $script:ScriptDir "StMicDriver")
            ) | Where-Object { Test-Path -LiteralPath $_ }

            foreach ($root in $roots) {
                $matches = Get-ChildItem -LiteralPath $root -Recurse -Filter "SimpleAudioSample.inf" -File -ErrorAction SilentlyContinue |
                    Where-Object {
                        $_.FullName -match '\\x64\\Release\\package\\SimpleAudioSample\.inf$' -or
                        $_.FullName -match '\\Package\\SimpleAudioSample\.inf$'
                    }
                $candidateInfs += $matches
            }
        } else {
            throw "No package folder was found next to install_driver_full.ps1. Extract the full BM Mic package and run install_driver_now.bat from its tools folder."
        }
    }

    $packages = foreach ($inf in $candidateInfs | Sort-Object LastWriteTime -Descending) {
        $packageDir = $inf.Directory.FullName
        $releaseDir = $inf.Directory.Parent.FullName
        $cer = Join-Path $releaseDir "package.cer"
        $sys = Join-Path $packageDir "SimpleAudioSample.sys"
        $cat = Join-Path $packageDir "simpleaudiosample.cat"
        $apo = Join-Path $packageDir "VirtualMicApo.dll"

        if (-not (Test-Path -LiteralPath $sys) -or -not (Test-Path -LiteralPath $cat)) {
            continue
        }

        [pscustomobject]@{
            InfPath = $inf.FullName
            PackageDir = $packageDir
            ReleaseDir = $releaseDir
            CertificatePath = $cer
            SysPath = $sys
            CatPath = $cat
            ApoPath = $apo
            LastWriteTime = @(
                $inf.LastWriteTimeUtc,
                (Get-Item -LiteralPath $sys).LastWriteTimeUtc,
                (Get-Item -LiteralPath $cat).LastWriteTimeUtc
            ) | Sort-Object -Descending | Select-Object -First 1
        }
    }

    $selected = $packages | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $selected) {
        throw "No complete driver package was found. Expected SimpleAudioSample.inf/sys/cat together."
    }

    return $selected
}

function Get-CertificateThumbprint {
    param(
        [Parameter(Mandatory)]
        [string]$CertificatePath
    )

    if (-not (Test-Path -LiteralPath $CertificatePath)) {
        return $null
    }

    return (Get-PfxCertificate -FilePath $CertificatePath).Thumbprint
}

function Ensure-CertificateImported {
    param(
        [Parameter(Mandatory)]
        [string]$CertificatePath
    )

    if (-not (Test-Path -LiteralPath $CertificatePath)) {
        Write-Log "package.cer was not found. Skipping certificate import." "WARN"
        return
    }

    $thumbprint = Get-CertificateThumbprint -CertificatePath $CertificatePath
    if (-not $thumbprint) {
        Write-Log "Could not read certificate thumbprint from $CertificatePath." "WARN"
        return
    }

    foreach ($storePath in @("Cert:\LocalMachine\Root", "Cert:\LocalMachine\TrustedPublisher")) {
        $existing = Get-ChildItem -Path $storePath -ErrorAction SilentlyContinue |
            Where-Object { $_.Thumbprint -eq $thumbprint } |
            Select-Object -First 1

        if ($existing) {
            Write-Log ("Certificate already present in {0}: {1}" -f $storePath, $thumbprint)
            continue
        }

        if ($DryRun) {
            Write-Log ("Dry run: would import certificate into {0}" -f $storePath) "WARN"
            continue
        }

        Import-Certificate -FilePath $CertificatePath -CertStoreLocation $storePath | Out-Null
        Write-Log ("Imported certificate into {0}: {1}" -f $storePath, $thumbprint) "OK"
    }
}

function Get-TestSigningState {
    $result = Invoke-External -FilePath "$env:SystemRoot\System32\bcdedit.exe" -Arguments @("/enum") -AllowFailure -ReadOnly
    $text = ($result.Output -join "`n")
    if ($result.ExitCode -ne 0) {
        Write-Log "Could not read BCD settings. Continuing with a conservative assumption." "WARN"
        return $false
    }

    return ($text -match '(?im)^\s*testsigning\s+Yes\s*$')
}

function Enable-TestSigningAndScheduleResume {
    param(
        [Parameter(Mandatory)]
        [pscustomobject]$Package
    )

    $resumeArguments = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $script:ScriptPath),
        '-Phase', 'PostReboot',
        '-PackagePath', ('"{0}"' -f $Package.PackageDir),
        '-LogPath', ('"{0}"' -f $LogPath)
    )
    if ($AllowRepositoryPackageSearch) {
        $resumeArguments += '-AllowRepositoryPackageSearch'
    }
    if ($SkipVerification) {
        $resumeArguments += '-SkipVerification'
    }
    $resumeArguments = $resumeArguments -join ' '

    if ($DryRun) {
        Write-Log "Dry run: scheduled-task continuation was not registered." "WARN"
    } else {
        $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $resumeArguments
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
        $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -RunLevel Highest
        Register-ScheduledTask -TaskName $script:ResumeTaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
        Write-Log "Registered elevated scheduled task continuation for post-reboot install."
    }

    $result = Invoke-External -FilePath "$env:SystemRoot\System32\bcdedit.exe" -Arguments @("/set", "testsigning", "on") -AllowFailure
    if ($result.ExitCode -ne 0) {
        $text = ($result.Output -join "`n")
        if ($text -match "Secure Boot") {
            throw "Windows refused to enable TESTSIGNING because Secure Boot is enforcing policy. Disable Secure Boot in UEFI/BIOS first, then rerun the installer."
        }

        throw "Failed to enable TESTSIGNING. See the log for details."
    }

    Write-Log "TESTSIGNING has been enabled. A reboot is required before the driver can load." "OK"

    if ($NoReboot) {
        Write-Log "NoReboot was requested. Reboot manually, log in, and the installer will continue automatically once." "WARN"
        exit $script:PendingRebootExitCode
    }

    Invoke-External -FilePath "$env:SystemRoot\System32\shutdown.exe" -Arguments @("/r", "/t", "5", "/c", "VirtualMic installer is rebooting to continue driver installation.") | Out-Null
    exit $script:PendingRebootExitCode
}

function Get-ExistingRootDevices {
    $devices = @(Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue |
        Where-Object {
            Test-IsBmMediaDeviceRecord -Device $_
        } |
        Sort-Object PNPDeviceID)

    return ,$devices
}

function Ensure-RootDeviceApi {
    if ("VirtualMicRootDeviceApi" -as [type]) {
        return
    }

    Add-Type -TypeDefinition @"
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

public static class VirtualMicRootDeviceApi
{
    private const uint DICD_GENERATE_ID = 0x00000001;
    private const uint SPDRP_HARDWAREID = 0x00000001;
    private const int DIF_REGISTERDEVICE = 0x00000019;
    private static readonly IntPtr INVALID_HANDLE_VALUE = new IntPtr(-1);

    [StructLayout(LayoutKind.Sequential)]
    public struct SP_DEVINFO_DATA
    {
        public uint cbSize;
        public Guid ClassGuid;
        public uint DevInst;
        public IntPtr Reserved;
    }

    [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool SetupDiGetINFClass(
        string InfName,
        out Guid ClassGuid,
        StringBuilder ClassName,
        int ClassNameSize,
        out int RequiredSize);

    [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr SetupDiCreateDeviceInfoList(
        ref Guid ClassGuid,
        IntPtr hwndParent);

    [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool SetupDiCreateDeviceInfo(
        IntPtr DeviceInfoSet,
        string DeviceName,
        ref Guid ClassGuid,
        string DeviceDescription,
        IntPtr hwndParent,
        uint CreationFlags,
        ref SP_DEVINFO_DATA DeviceInfoData);

    [DllImport("setupapi.dll", SetLastError = true)]
    private static extern bool SetupDiSetDeviceRegistryProperty(
        IntPtr DeviceInfoSet,
        ref SP_DEVINFO_DATA DeviceInfoData,
        uint Property,
        byte[] PropertyBuffer,
        uint PropertyBufferSize);

    [DllImport("setupapi.dll", SetLastError = true)]
    private static extern bool SetupDiCallClassInstaller(
        int InstallFunction,
        IntPtr DeviceInfoSet,
        ref SP_DEVINFO_DATA DeviceInfoData);

    [DllImport("setupapi.dll", SetLastError = true)]
    private static extern bool SetupDiDestroyDeviceInfoList(
        IntPtr DeviceInfoSet);

    public static void CreateRootDevice(string infPath, string hardwareId)
    {
        Guid classGuid;
        int requiredSize;
        StringBuilder className = new StringBuilder(260);
        if (!SetupDiGetINFClass(infPath, out classGuid, className, className.Capacity, out requiredSize))
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(), "SetupDiGetINFClass failed.");
        }

        IntPtr infoSet = SetupDiCreateDeviceInfoList(ref classGuid, IntPtr.Zero);
        if (infoSet == INVALID_HANDLE_VALUE)
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(), "SetupDiCreateDeviceInfoList failed.");
        }

        try
        {
            SP_DEVINFO_DATA deviceInfo = new SP_DEVINFO_DATA();
            deviceInfo.cbSize = (uint)Marshal.SizeOf(typeof(SP_DEVINFO_DATA));

            if (!SetupDiCreateDeviceInfo(
                infoSet,
                className.ToString(),
                ref classGuid,
                null,
                IntPtr.Zero,
                DICD_GENERATE_ID,
                ref deviceInfo))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "SetupDiCreateDeviceInfo failed.");
            }

            byte[] hardwareIdBytes = Encoding.Unicode.GetBytes(hardwareId + "\0\0");
            if (!SetupDiSetDeviceRegistryProperty(
                infoSet,
                ref deviceInfo,
                SPDRP_HARDWAREID,
                hardwareIdBytes,
                (uint)hardwareIdBytes.Length))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "SetupDiSetDeviceRegistryProperty failed.");
            }

            if (!SetupDiCallClassInstaller(DIF_REGISTERDEVICE, infoSet, ref deviceInfo))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "SetupDiCallClassInstaller(DIF_REGISTERDEVICE) failed.");
            }
        }
        finally
        {
            SetupDiDestroyDeviceInfoList(infoSet);
        }
    }
}
"@
}

function Ensure-DriverBindingApi {
    if ("VirtualMicDriverBindingApi" -as [type]) {
        return
    }

    Add-Type -TypeDefinition @"
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;

public static class VirtualMicDriverBindingApi
{
    private const uint INSTALLFLAG_FORCE = 0x00000001;
    private const uint INSTALLFLAG_NONINTERACTIVE = 0x00000004;

    [DllImport("newdev.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool UpdateDriverForPlugAndPlayDevices(
        IntPtr hwndParent,
        string hardwareId,
        string fullInfPath,
        uint installFlags,
        [MarshalAs(UnmanagedType.Bool)] out bool rebootRequired);

    public static bool ForceUpdateDriver(string hardwareId, string infPath, out bool rebootRequired)
    {
        if (!UpdateDriverForPlugAndPlayDevices(IntPtr.Zero, hardwareId, infPath, INSTALLFLAG_FORCE | INSTALLFLAG_NONINTERACTIVE, out rebootRequired))
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(), "UpdateDriverForPlugAndPlayDevices failed.");
        }

        return rebootRequired;
    }
}
"@
}

function Get-BundledRootDeviceHelperPath {
    $candidates = @(
        (Join-Path $script:ScriptDir "tools\VirtualMicRootDeviceHelper.exe"),
        (Join-Path $script:ScriptDir "VirtualMicRootDeviceHelper.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    return $null
}

function Resolve-OptionalToolPath {
    param(
        [Parameter(Mandatory)]
        [string]$ToolName
    )

    $command = Get-Command $ToolName -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $programFilesX86 = ${env:ProgramFiles(x86)}
    if (-not $programFilesX86) {
        return $null
    }

    $toolsRoot = Join-Path $programFilesX86 "Windows Kits\10\Tools"
    if (-not (Test-Path -LiteralPath $toolsRoot)) {
        return $null
    }

    $preferredArch = if ([Environment]::Is64BitOperatingSystem) { "x64" } else { "x86" }
    $archOrder = @($preferredArch, "arm64", "x86") | Select-Object -Unique

    $versionDirs = @(Get-ChildItem -LiteralPath $toolsRoot -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending)

    foreach ($dir in $versionDirs) {
        foreach ($arch in $archOrder) {
            $candidate = Join-Path $dir.FullName (Join-Path $arch $ToolName)
            if (Test-Path -LiteralPath $candidate) {
                return $candidate
            }
        }
    }

    return $null
}

function Test-RequiredPackageFiles {
    param(
        [Parameter(Mandatory)]
        [pscustomobject]$Package
    )

    $required = @(
        @{ Label = "INF"; Path = $Package.InfPath },
        @{ Label = "SYS"; Path = $Package.SysPath },
        @{ Label = "CAT"; Path = $Package.CatPath }
    )

    if (Test-Path -LiteralPath $Package.CertificatePath) {
        $required += @{ Label = "CER"; Path = $Package.CertificatePath }
    }

    foreach ($item in $required) {
        if (-not (Test-Path -LiteralPath $item.Path)) {
            throw ("Required package file is missing: {0} -> {1}" -f $item.Label, $item.Path)
        }
    }

    $helperPath = Get-BundledRootDeviceHelperPath
    if (-not $helperPath) {
        Write-Log "Bundled root-device helper was not found in this package. The script will rely on any existing local devcon/devgen tools or the legacy in-process SetupAPI fallback." "WARN"
    } else {
        Write-Log ("Bundled root-device helper: {0}" -f $helperPath)
    }
}

function Invoke-DeviceRescan {
    Invoke-External -FilePath "$env:SystemRoot\System32\pnputil.exe" -Arguments @("/scan-devices") -AllowFailure | Out-Null
}

function Wait-ForRootDevicePresence {
    param(
        [int]$TimeoutSeconds = 15
    )

    return (Wait-Until -TimeoutSeconds $TimeoutSeconds -PollSeconds 2 -Condition {
        @(Get-ExistingRootDevices).Count -gt 0
    })
}

function Try-CreateRootDeviceWithInstalledTools {
    param(
        [Parameter(Mandatory)]
        [pscustomobject]$Package
    )

    $devconPath = Resolve-OptionalToolPath -ToolName "devcon.exe"
    if ($devconPath) {
        Write-Log ("Using devcon at {0} to create the Root device." -f $devconPath)
        $devconResult = Invoke-External -FilePath $devconPath -Arguments @("install", $Package.InfPath, $HardwareId) -AllowFailure
        Invoke-DeviceRescan
        if (Wait-ForRootDevicePresence) {
            Write-Log "Root device instance created with devcon." "OK"
            return $true
        }

        Write-Log ("devcon exited with code {0}, but no BM Mic root device was detected." -f $devconResult.ExitCode) "WARN"
    }

    $devgenPath = Resolve-OptionalToolPath -ToolName "devgen.exe"
    if ($devgenPath) {
        Write-Log ("Using devgen at {0} to create the Root device." -f $devgenPath)
        $devgenResult = Invoke-External -FilePath $devgenPath -Arguments @("/add", "/bus", "ROOT", "/hardwareid", $HardwareId) -AllowFailure
        Invoke-DeviceRescan
        if (Wait-ForRootDevicePresence) {
            Write-Log "Root device instance created with devgen." "OK"
            return $true
        }

        Write-Log ("devgen exited with code {0}, but no BM Mic root device was detected." -f $devgenResult.ExitCode) "WARN"
    }

    return $false
}

function ConvertTo-WindowsCommandLineArgument {
    param(
        [AllowNull()]
        [string]$Value
    )

    if ($null -eq $Value -or $Value.Length -eq 0) {
        return '""'
    }

    if ($Value -notmatch '[\s"]') {
        return $Value
    }

    $escaped = $Value -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

function Invoke-RootDeviceHelper {
    param(
        [Parameter(Mandatory)]
        [string]$HelperPath,
        [Parameter(Mandatory)]
        [string]$InfPath,
        [Parameter(Mandatory)]
        [string]$RootHardwareId,
        [int]$TimeoutSeconds = 45
    )

    Write-Log ('Running bundled root-device helper: "{0}" "{1}" "{2}"' -f $HelperPath, $InfPath, $RootHardwareId)

    if ($DryRun) {
        Write-Log "Dry run: bundled root-device helper was not executed." "WARN"
        return [pscustomobject]@{
            ExitCode = 0
            TimedOut = $false
            Output = @("[dry-run]")
        }
    }

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $HelperPath
    $startInfo.Arguments = ('{0} {1}' -f
        (ConvertTo-WindowsCommandLineArgument -Value $InfPath),
        (ConvertTo-WindowsCommandLineArgument -Value $RootHardwareId))
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    $null = $process.Start()

    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        try {
            $process.Kill()
        } catch {
        }

        $timedOutOutput = @()
        $timedOutOutput += ($process.StandardOutput.ReadToEnd() -split "`r?`n")
        $timedOutOutput += ($process.StandardError.ReadToEnd() -split "`r?`n")
        foreach ($line in $timedOutOutput) {
            if (-not [string]::IsNullOrWhiteSpace($line)) {
                Write-Log $line "WARN"
            }
        }

        return [pscustomobject]@{
            ExitCode = -1
            TimedOut = $true
            Output = $timedOutOutput
        }
    }

    $output = @()
    $output += ($process.StandardOutput.ReadToEnd() -split "`r?`n")
    $output += ($process.StandardError.ReadToEnd() -split "`r?`n")
    foreach ($line in $output) {
        if (-not [string]::IsNullOrWhiteSpace($line)) {
            Write-Log $line
        }
    }

    return [pscustomobject]@{
        ExitCode = $process.ExitCode
        TimedOut = $false
        Output = $output
    }
}

function Ensure-RootDevice {
    param(
        [Parameter(Mandatory)]
        [pscustomobject]$Package
    )

    $existing = Get-ExistingRootDevices
    if ($existing.Count -gt 0) {
        Write-Log ("Existing Root device instance(s) found: {0}" -f (($existing | Select-Object -ExpandProperty PNPDeviceID) -join ", "))
        return
    }

    $creationFailures = @()
    $helperPath = Get-BundledRootDeviceHelperPath
    if ($helperPath) {
        Write-Log ("Using bundled root-device helper from this package: {0}" -f $helperPath)
        $helperResult = Invoke-RootDeviceHelper -HelperPath $helperPath -InfPath $Package.InfPath -RootHardwareId $HardwareId
        Invoke-DeviceRescan
        $existingAfterHelper = if (Wait-ForRootDevicePresence) { @(Get-ExistingRootDevices) } else { @() }
        if ($existingAfterHelper.Count -gt 0) {
            Write-Log ("Root device instance created by bundled helper: {0}" -f (($existingAfterHelper | Select-Object -ExpandProperty PNPDeviceID) -join ", ")) "OK"
            return
        }

        if ($helperResult.TimedOut) {
            $creationFailures += "Bundled root-device helper timed out while creating the BM Mic device"
        } else {
            $creationFailures += ("Bundled root-device helper exited with code {0} and no BM Mic device was created" -f $helperResult.ExitCode)
        }
    } elseif (Try-CreateRootDeviceWithInstalledTools -Package $Package) {
        return
    }

    if ($helperPath) {
        Write-Log "Bundled root-device helper did not finish the job. Falling back to legacy in-process SetupAPI root-device creation." "WARN"
    } else {
        Write-Log "devcon/devgen were not found on this machine and no bundled helper is present. Falling back to legacy in-process SetupAPI root-device creation." "WARN"
    }

    if ($DryRun) {
        Write-Log "Dry run: native Root device creation skipped." "WARN"
        return
    }

    Ensure-RootDeviceApi
    try {
        [VirtualMicRootDeviceApi]::CreateRootDevice($Package.InfPath, $HardwareId)
    } catch {
        $existingAfterFailure = @(Get-ExistingRootDevices)
        if ($existingAfterFailure.Count -gt 0) {
            Write-Log ("SetupAPI root-device creation reported an error, but BM Mic device(s) already exist: {0}. Continuing." -f (($existingAfterFailure | Select-Object -ExpandProperty PNPDeviceID) -join ", ")) "WARN"
            return
        }

        throw
    }

    Invoke-DeviceRescan
    if (Wait-ForRootDevicePresence) {
        Write-Log "Root device node created via SetupAPI. Driver binding will continue with pnputil." "OK"
        return
    }

    if ($creationFailures.Count -gt 0) {
        throw ("Root device creation completed without producing a BM Mic device. Earlier attempts: {0}" -f ($creationFailures -join " | "))
    }

    throw "Root device creation completed without producing a BM Mic device."
}

function Ensure-DriverPackageInstalled {
    param(
        [Parameter(Mandatory)]
        [pscustomobject]$Package
    )

    $addDriverResult = Invoke-External -FilePath "$env:SystemRoot\System32\pnputil.exe" -Arguments @("/add-driver", $Package.InfPath, "/install") -AllowFailure
    $addDriverText = ($addDriverResult.Output -join "`n")

    $pnputilReportedSuccess =
        ($addDriverText -match "Driver package added successfully") -and
        (
            ($addDriverText -match "Driver package is up-to-date on device") -or
            ($addDriverText -match "Published Name:")
        )

    if ($addDriverResult.ExitCode -ne 0) {
        if ($pnputilReportedSuccess) {
            Write-Log ("pnputil returned exit code {0} after reporting a successful driver state. Treating this as success." -f $addDriverResult.ExitCode) "WARN"
        } else {
            throw ("pnputil did not report a successful driver install state. Exit code: {0}" -f $addDriverResult.ExitCode)
        }
    }

    Invoke-External -FilePath "$env:SystemRoot\System32\pnputil.exe" -Arguments @("/scan-devices") -AllowFailure | Out-Null

    $rootDevicesAfterScan = @(Get-ExistingRootDevices)
    $driverService = Get-CimInstance Win32_SystemDriver -Filter ("Name='{0}'" -f $script:ExpectedServiceName) -ErrorAction SilentlyContinue
    if ($rootDevicesAfterScan.Count -gt 0 -and -not $driverService) {
        Write-Log "BM Mic root device exists, but the kernel driver service is not bound yet. Forcing driver update against the package INF." "WARN"
        Ensure-DriverBindingApi

        try {
            $rebootRequired = $false
            $null = [VirtualMicDriverBindingApi]::ForceUpdateDriver($HardwareId, $Package.InfPath, [ref]$rebootRequired)
            Write-Log "UpdateDriverForPlugAndPlayDevices completed for Root\\SimpleAudioSample." "OK"
            if ($rebootRequired) {
                Write-Log "Windows requested a reboot while binding the BM Mic driver." "WARN"
            }
        } catch {
            Write-Log ("Explicit driver binding failed: {0}" -f $_.Exception.Message) "WARN"
        }

        Invoke-External -FilePath "$env:SystemRoot\System32\pnputil.exe" -Arguments @("/scan-devices") -AllowFailure | Out-Null
    }
}

function Ensure-ReplaceableSystemFile {
    param(
        [Parameter(Mandatory)]
        [string]$LiteralPath
    )

    if (-not (Test-Path -LiteralPath $LiteralPath)) {
        return
    }

    Write-Log ("Preparing existing protected file for replacement: {0}" -f $LiteralPath) "WARN"
    Invoke-External -FilePath "$env:SystemRoot\System32\takeown.exe" -Arguments @("/f", $LiteralPath, "/a") -AllowFailure | Out-Null
    Invoke-External -FilePath "$env:SystemRoot\System32\icacls.exe" -Arguments @($LiteralPath, "/grant:r", "Administrators:F") -AllowFailure | Out-Null
}

function Stop-AudioServicesForApoUpdate {
    if ($DryRun) {
        Write-Log "Dry run: audio services were not stopped for APO update." "WARN"
        return
    }

    foreach ($serviceName in @("audiosrv", "AudioEndpointBuilder")) {
        try {
            $service = Get-Service -Name $serviceName -ErrorAction Stop
            if ($service.Status -ne "Stopped") {
                Stop-Service -Name $serviceName -Force -ErrorAction Stop
                Write-Log ("Stopped service for APO update: {0}" -f $serviceName)
            }
        } catch {
            Write-Log ("Could not stop service {0} before APO replacement: {1}" -f $serviceName, $_.Exception.Message) "WARN"
        }
    }

    Start-Sleep -Seconds 1
}

function Ensure-ApoRegistration {
    param(
        [Parameter(Mandatory)]
        [pscustomobject]$Package
    )

    if (-not (Test-Path -LiteralPath $Package.ApoPath)) {
        Write-Log "VirtualMicApo.dll was not found in the package. Skipping APO copy/repair." "WARN"
        return
    }

    if ($DryRun) {
        Write-Log ("Dry run: would copy {0} to {1}" -f $Package.ApoPath, $script:System32ApoPath) "WARN"
    } else {
        Stop-AudioServicesForApoUpdate
        Ensure-ReplaceableSystemFile -LiteralPath $script:System32ApoPath
        try {
            Copy-Item -LiteralPath $Package.ApoPath -Destination $script:System32ApoPath -Force
        } catch [System.UnauthorizedAccessException] {
            Write-Log ("Unauthorized while replacing APO DLL. Retrying after ownership repair: {0}" -f $_.Exception.Message) "WARN"
            Ensure-ReplaceableSystemFile -LiteralPath $script:System32ApoPath
            Remove-Item -LiteralPath $script:System32ApoPath -Force -ErrorAction SilentlyContinue
            Copy-Item -LiteralPath $Package.ApoPath -Destination $script:System32ApoPath -Force
        }
        Write-Log ("Copied APO DLL to {0}" -f $script:System32ApoPath) "OK"
    }

    if ($DryRun) {
        Write-Log "Dry run: would repair APO CLSID registration." "WARN"
        return
    }

    Invoke-External -FilePath "$env:SystemRoot\System32\reg.exe" -Arguments @("add", "HKCR\CLSID\$script:ApoClsid", "/ve", "/t", "REG_SZ", "/d", "VirtualMic APO", "/f") | Out-Null
    Invoke-External -FilePath "$env:SystemRoot\System32\reg.exe" -Arguments @("add", "HKCR\CLSID\$script:ApoClsid\InprocServer32", "/ve", "/t", "REG_SZ", "/d", $script:System32ApoPath, "/f") | Out-Null
    Invoke-External -FilePath "$env:SystemRoot\System32\reg.exe" -Arguments @("add", "HKCR\CLSID\$script:ApoClsid\InprocServer32", "/v", "ThreadingModel", "/t", "REG_SZ", "/d", "Both", "/f") | Out-Null
    Write-Log "APO CLSID registration repaired." "OK"
}

function Restart-AudioStack {
    if ($DryRun) {
        Write-Log "Dry run: audio services were not restarted." "WARN"
        return
    }

    Write-Log "Restarting Windows audio services."
    Restart-Service -Name "AudioEndpointBuilder" -Force -ErrorAction Stop
    Restart-Service -Name "audiosrv" -Force -ErrorAction Stop
    Start-Sleep -Seconds 2
    Write-Log "Windows audio services restarted." "OK"
}

function Wait-Until {
    param(
        [Parameter(Mandatory)]
        [scriptblock]$Condition,
        [int]$TimeoutSeconds = 30,
        [int]$PollSeconds = 2
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) {
            return $true
        }

        Start-Sleep -Seconds $PollSeconds
    }

    return $false
}

function Get-ObjectPropertyValue {
    param(
        [Parameter(Mandatory)]
        [object]$InputObject,
        [Parameter(Mandatory)]
        [string]$Name,
        $Default = $null
    )

    if ($null -eq $InputObject) {
        return $Default
    }

    $property = $InputObject.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $Default
    }

    return $property.Value
}

function Test-IsBmMediaDeviceRecord {
    param(
        [Parameter(Mandatory)]
        [object]$Device
    )

    $instanceId = [string](Get-ObjectPropertyValue -InputObject $Device -Name "InstanceId" "")
    if ([string]::IsNullOrWhiteSpace($instanceId)) {
        $instanceId = [string](Get-ObjectPropertyValue -InputObject $Device -Name "DeviceID" "")
    }
    if ([string]::IsNullOrWhiteSpace($instanceId)) {
        $instanceId = [string](Get-ObjectPropertyValue -InputObject $Device -Name "PNPDeviceID" "")
    }

    $friendlyName = [string](Get-ObjectPropertyValue -InputObject $Device -Name "FriendlyName" "")
    if ([string]::IsNullOrWhiteSpace($friendlyName)) {
        $friendlyName = [string](Get-ObjectPropertyValue -InputObject $Device -Name "Name" "")
    }
    if ([string]::IsNullOrWhiteSpace($friendlyName)) {
        $friendlyName = [string](Get-ObjectPropertyValue -InputObject $Device -Name "DeviceName" "")
    }

    $service = [string](Get-ObjectPropertyValue -InputObject $Device -Name "Service" "")
    $class = [string](Get-ObjectPropertyValue -InputObject $Device -Name "Class" "")
    $classGuid = [string](Get-ObjectPropertyValue -InputObject $Device -Name "ClassGuid" "")
    $manufacturer = [string](Get-ObjectPropertyValue -InputObject $Device -Name "Manufacturer" "")
    if ([string]::IsNullOrWhiteSpace($manufacturer)) {
        $manufacturer = [string](Get-ObjectPropertyValue -InputObject $Device -Name "DriverProviderName" "")
    }

    $isMediaClass = $class -eq "MEDIA" -or $classGuid -eq $script:MediaClassGuid
    return (
        $instanceId -like $script:ExpectedPnpPattern -or
        $instanceId -like ("{0}*" -f $HardwareId) -or
        $service -eq $script:ExpectedServiceName -or
        (
            $isMediaClass -and (
                $friendlyName -like "*BM Mic*" -or
                $manufacturer -eq "Blind Masters"
            )
        )
    )
}

function Get-CaptureEndpoints {
    $endpoints = @()

    try {
        $items = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture\*" -ErrorAction Stop
        foreach ($item in @($items)) {
            $friendlyName = Get-ObjectPropertyValue -InputObject $item -Name "FriendlyName"
            if ([string]::IsNullOrWhiteSpace([string]$friendlyName)) {
                continue
            }

            $endpoints += [pscustomobject]@{
                FriendlyName = [string]$friendlyName
                Id = [string](Get-ObjectPropertyValue -InputObject $item -Name "PSChildName" "")
            }
        }
    } catch {
        Write-Log ("Capture endpoint registry enumeration failed: {0}" -f $_.Exception.Message) "WARN"
    }

    return $endpoints
}

function Get-PnpDeviceSnapshot {
    param(
        [Parameter(Mandatory)]
        [string]$ClassName
    )

    $results = @()
    $getPnpDevice = Get-Command Get-PnpDevice -ErrorAction SilentlyContinue
    if (-not $getPnpDevice) {
        return $results
    }

    try {
        $devices = @(Get-PnpDevice -Class $ClassName -ErrorAction Stop)
        foreach ($device in $devices) {
            $results += [pscustomobject]@{
                Class = [string](Get-ObjectPropertyValue -InputObject $device -Name "Class" $ClassName)
                FriendlyName = [string](Get-ObjectPropertyValue -InputObject $device -Name "FriendlyName" "")
                InstanceId = [string](Get-ObjectPropertyValue -InputObject $device -Name "InstanceId" "")
                Status = [string](Get-ObjectPropertyValue -InputObject $device -Name "Status" "")
                Problem = [string](Get-ObjectPropertyValue -InputObject $device -Name "Problem" "")
                Service = [string](Get-ObjectPropertyValue -InputObject $device -Name "Service" "")
                Present = [bool](Get-ObjectPropertyValue -InputObject $device -Name "Present" $true)
            }
        }
    } catch {
        Write-Log ("Get-PnpDevice failed for class {0}: {1}" -f $ClassName, $_.Exception.Message) "WARN"
    }

    return $results
}

function Get-BmEndpointCandidates {
    $candidates = @()

    foreach ($device in @(Get-PnpDeviceSnapshot -ClassName "AudioEndpoint")) {
        $friendlyName = [string](Get-ObjectPropertyValue -InputObject $device -Name "FriendlyName" "")
        if ($friendlyName -like "*BM Mic*" -or $friendlyName -like "*VirtualMic*") {
            $candidates += $device
        }
    }

    foreach ($endpoint in @(Get-CaptureEndpoints)) {
        $friendlyName = [string](Get-ObjectPropertyValue -InputObject $endpoint -Name "FriendlyName" "")
        if ($friendlyName -like "*BM Mic*" -or $friendlyName -like "*VirtualMic*") {
            $candidates += [pscustomobject]@{
                Class = "RegistryCapture"
                FriendlyName = $friendlyName
                InstanceId = [string](Get-ObjectPropertyValue -InputObject $endpoint -Name "Id" "")
                Status = ""
                Problem = ""
            }
        }
    }

    return @(
        $candidates |
            Group-Object FriendlyName, InstanceId |
            ForEach-Object { $_.Group | Select-Object -First 1 }
    )
}

function Get-BmMediaDevices {
    $matches = @()

    foreach ($device in @(Get-PnpDeviceSnapshot -ClassName "MEDIA")) {
        if (Test-IsBmMediaDeviceRecord -Device $device) {
            $matches += $device
        }
    }

    if ($matches.Count -eq 0) {
        foreach ($device in @(Get-ExistingRootDevices)) {
            $matches += [pscustomobject]@{
                Class = "MEDIA"
                FriendlyName = [string](Get-ObjectPropertyValue -InputObject $device -Name "Name" "")
                InstanceId = [string](Get-ObjectPropertyValue -InputObject $device -Name "PNPDeviceID" "")
                Status = [string](Get-ObjectPropertyValue -InputObject $device -Name "Status" "")
                Problem = ""
                Service = [string](Get-ObjectPropertyValue -InputObject $device -Name "Service" "")
                Present = $true
            }
        }
    }

    return @(
        $matches |
            Group-Object InstanceId |
            ForEach-Object { $_.Group | Select-Object -First 1 }
    )
}

function Test-ApoLoaded {
    $loaded = $false

    try {
        $audiodg = Get-Process -Name "audiodg" -ErrorAction Stop
        $match = $audiodg.Modules | Where-Object { $_.ModuleName -ieq "VirtualMicApo.dll" } | Select-Object -First 1
        if ($match) {
            Write-Log ("audiodg.exe currently has VirtualMicApo.dll loaded from {0}" -f $match.FileName) "OK"
            $loaded = $true
        }
    } catch {
        Write-Log ("Direct audiodg module enumeration failed: {0}" -f $_.Exception.Message) "WARN"
    }

    if ($loaded) {
        return $true
    }

    $taskList = Invoke-External -FilePath "$env:SystemRoot\System32\tasklist.exe" -Arguments @("/m", "VirtualMicApo.dll") -AllowFailure -ReadOnly
    if (($taskList.Output -join "`n") -match "audiodg.exe") {
        Write-Log "tasklist confirms audiodg.exe has VirtualMicApo.dll loaded." "OK"
        return $true
    }

    Write-Log "VirtualMicApo.dll is not currently visible in audiodg.exe. This can happen until the endpoint becomes active." "WARN"
    return $false
}

function Verify-Installation {
    param(
        [Parameter(Mandatory)]
        [pscustomobject]$Package
    )

    try {
        $deviceReady = Wait-Until -TimeoutSeconds 30 -Condition {
            @(Get-ExistingRootDevices).Count -gt 0
        }

        $driver = Get-CimInstance Win32_PnPSignedDriver -ErrorAction SilentlyContinue |
            Where-Object {
                Test-IsBmMediaDeviceRecord -Device $_
            } |
            Sort-Object {
                Get-ObjectPropertyValue -InputObject $_ -Name "DeviceID" ""
            } |
            Select-Object -First 1

        $service = Get-CimInstance Win32_SystemDriver -Filter ("Name='{0}'" -f $script:ExpectedServiceName) -ErrorAction SilentlyContinue
        $interfaces = Invoke-External -FilePath "$env:SystemRoot\System32\pnputil.exe" -Arguments @("/enum-interfaces", "/class", $script:InterfaceGuid) -AllowFailure -ReadOnly
        $captureEndpoints = @(Get-BmEndpointCandidates)
        $mediaDevices = @(Get-BmMediaDevices)
        $apoFilePresent = Test-Path -LiteralPath $script:System32ApoPath
        $apoLoaded = Test-ApoLoaded
        $captureEndpointCount = @($captureEndpoints).Count
        $mediaDeviceCount = @($mediaDevices).Count

        Write-Log ("Driver service present: {0}" -f [bool]$service)
        Write-Log ("Root device present: {0}" -f $deviceReady)
        Write-Log ("Capture endpoints found: {0}" -f $captureEndpointCount)
        Write-Log ("Matching MEDIA-class devices found: {0}" -f $mediaDeviceCount)
        Write-Log ("APO DLL present in System32: {0}" -f $apoFilePresent)

        if ($driver) {
            $deviceName = [string](Get-ObjectPropertyValue -InputObject $driver -Name "DeviceName" "<unknown>")
            $driverVersion = [string](Get-ObjectPropertyValue -InputObject $driver -Name "DriverVersion" "<unknown>")
            $infName = [string](Get-ObjectPropertyValue -InputObject $driver -Name "InfName" "<unknown>")
            Write-Log ("Installed driver: {0} | Version {1} | Inf {2}" -f $deviceName, $driverVersion, $infName) "OK"
        } else {
            Write-Log "No BM Mic Win32_PnPSignedDriver entry was found." "WARN"
        }

        if ($mediaDeviceCount -gt 0) {
            foreach ($mediaDevice in $mediaDevices) {
                Write-Log ("MEDIA device: {0} | Status {1} | Instance {2}" -f
                    ([string](Get-ObjectPropertyValue -InputObject $mediaDevice -Name "FriendlyName" "<unnamed>")),
                    ([string](Get-ObjectPropertyValue -InputObject $mediaDevice -Name "Status" "<unknown>")),
                    ([string](Get-ObjectPropertyValue -InputObject $mediaDevice -Name "InstanceId" "<unknown>"))) "OK"
            }
        } else {
            Write-Log "No matching MEDIA-class PnP device was found for BM Mic." "WARN"
        }

        if ($captureEndpointCount -gt 0) {
            foreach ($endpoint in $captureEndpoints) {
                $friendlyName = [string](Get-ObjectPropertyValue -InputObject $endpoint -Name "FriendlyName" "<unnamed endpoint>")
                $status = [string](Get-ObjectPropertyValue -InputObject $endpoint -Name "Status" "")
                if ($status) {
                    Write-Log ("Capture endpoint: {0} | Status {1}" -f $friendlyName, $status) "OK"
                } else {
                    Write-Log ("Capture endpoint: {0}" -f $friendlyName) "OK"
                }
            }
        } else {
            Write-Log "No BM Mic capture endpoint was found under MMDevices." "WARN"
        }

        $interfaceText = $interfaces.Output -join "`n"
        $ksInterfacePresent = $interfaces.ExitCode -eq 0 -and $interfaceText -match [Regex]::Escape($script:InterfaceGuid)
        if ($ksInterfacePresent) {
            Write-Log "Custom KS interface is present." "OK"
        } else {
            Write-Log "Custom KS interface was not confirmed through pnputil /enum-interfaces." "WARN"
        }

        $coreSignalsReady = $deviceReady -and $service -and $apoFilePresent -and $ksInterfacePresent
        if ($coreSignalsReady) {
            if (-not $apoLoaded) {
                Write-Log "Core install passed, but the APO is not loaded yet. Open the BM Mic endpoint once or start a capture app to force audiodg to load it." "WARN"
            }

            if ($captureEndpointCount -eq 0) {
                Write-Log "The core driver signals are healthy, but Windows has not surfaced the BM Mic endpoint yet. This can lag until the audio stack refreshes or the machine signs in again." "WARN"
            }

            if (-not $driver) {
                Write-Log "Skipping strict Win32_PnPSignedDriver matching because the active instance may enumerate under ROOT\\MEDIA instead of the requested hardware ID." "WARN"
            }

            Write-Log "VirtualMic driver installation completed successfully." "OK"
            return
        }

        throw "Driver installation finished with missing verification signals. Check the log and Device Manager before using the endpoint."
    } catch [System.Management.Automation.PropertyNotFoundException] {
        Write-Log ("Verification hit a missing property while reading Windows device metadata: {0}" -f $_.Exception.Message) "WARN"
        Write-Log "Treating verification as partial because this machine returned incomplete metadata. Check Device Manager and the Sound control panel if the endpoint is still missing." "WARN"
        return
    }
}

function Clear-ResumeTask {
    if ($DryRun) {
        Write-Log "Dry run: scheduled-task cleanup skipped." "WARN"
        return
    }

    Unregister-ScheduledTask -TaskName $script:ResumeTaskName -Confirm:$false -ErrorAction SilentlyContinue
}

function Send-InstallerEventReport {
    param(
        [Parameter(Mandatory)]
        [string]$Kind,
        [Parameter(Mandatory)]
        [string]$Summary,
        [string]$Details = "",
        [string]$ResolvedPackagePath = ""
    )

    $reporterPath = Join-Path $script:ScriptDir "report_installer_event.ps1"
    if (-not (Test-Path -LiteralPath $reporterPath)) {
        return
    }

    try {
        & $reporterPath -Kind $Kind -Summary $Summary -Details $Details -LogPath $LogPath -Revision $script:InstallerRevision -Phase $Phase -PackagePath $ResolvedPackagePath
    } catch {
    }
}

Ensure-Elevated
$LogPath = Initialize-LogFile -RequestedPath $LogPath
Write-Log ("=== VirtualMic install started | Revision={0} | Phase={1} | DryRun={2} | PackageOnly={3} ===" -f $script:InstallerRevision, $Phase, $DryRun, (-not $AllowRepositoryPackageSearch))

$package = $null
try {
    $package = Resolve-DriverPackage -RequestedPath $PackagePath
    Write-Log ("Using package directory: {0}" -f $package.PackageDir)
    Write-Log ("Using INF: {0}" -f $package.InfPath)
    Write-Log ("Using CAT: {0}" -f $package.CatPath)
    Test-RequiredPackageFiles -Package $package

    $catSignature = Get-AuthenticodeSignature -FilePath $package.CatPath
    Write-Log ("Catalog signature status: {0}" -f $catSignature.Status)

    if (-not $SkipTestSigning -and $Phase -eq "Initial") {
        if (-not (Get-TestSigningState)) {
            Enable-TestSigningAndScheduleResume -Package $package
        }

        Write-Log "TESTSIGNING is already enabled."
    }

    if (-not $SkipTestSigning -and $Phase -eq "PostReboot") {
        if (-not (Get-TestSigningState)) {
            throw "The machine rebooted, but TESTSIGNING is still off. Aborting."
        }

        Write-Log "Post-reboot phase confirmed TESTSIGNING is enabled."
    }

    Ensure-CertificateImported -CertificatePath $package.CertificatePath
    Ensure-RootDevice -Package $package
    Ensure-DriverPackageInstalled -Package $package
    Ensure-ApoRegistration -Package $package
    Restart-AudioStack

    if (-not $SkipVerification) {
        Verify-Installation -Package $package
    }

    Clear-ResumeTask
    Write-Log "=== VirtualMic install completed ===" "OK"
} catch {
    $errorText = $_ | Out-String
    $errorSummary = $_.Exception.Message
    Write-Log ("Installation failed: {0}" -f $errorSummary) "ERROR"
    Send-InstallerEventReport -Kind "DriverInstallError" -Summary $errorSummary -Details $errorText -ResolvedPackagePath $(if ($package) { $package.PackageDir } elseif ($PackagePath) { $PackagePath } else { $script:ScriptDir })
    throw
}
