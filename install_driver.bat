@echo off
setlocal

set "NO_PAUSE="
if /i "%~1"=="--no-pause" set "NO_PAUSE=1"
if /i "%~1"=="--elevated" shift

REM Must run as Administrator
net session >nul 2>&1
if errorlevel 1 (
  echo Requesting Administrator privileges...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '--elevated --no-pause' -Verb RunAs"
  if not defined NO_PAUSE pause
  exit /b 0
)

set "ARTIFACTS_ROOT=%~dp0artifacts"

REM Pick latest artifact folder that contains the driver package.
REM Supports both old: StMicDriver-Output\... and new: StMicDriver\...
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$root = '%ARTIFACTS_ROOT%'; if(!(Test-Path $root)){exit 1}; $rels = @('StMicDriver\\x64\\Release\\package\\SimpleAudioSample.inf','StMicDriver-Output\\StMicDriver\\x64\\Release\\package\\SimpleAudioSample.inf'); $match = $null; Get-ChildItem -Path $root -Directory | Sort-Object LastWriteTime -Descending | ForEach-Object { $base = $_.FullName; foreach($rel in $rels){ $inf = Join-Path $base $rel; if(Test-Path $inf){ $pkg = Split-Path $inf -Parent; $cer = @((Join-Path $base 'StMicDriver\\x64\\Release\\package.cer'), (Join-Path $base 'StMicDriver-Output\\StMicDriver\\x64\\Release\\package.cer')) | Where-Object { Test-Path $_ } | Select-Object -First 1; $match = [PSCustomObject]@{ Base=$base; Package=$pkg; Inf=$inf; Cer=$cer }; break } }; if($match){ break } }; if(!$match){ exit 1 }; Write-Output $match.Base; Write-Output $match.Package; Write-Output $match.Inf; Write-Output $match.Cer"`) do (
  if not defined ARTIFACT_DIR (
    set "ARTIFACT_DIR=%%I"
  ) else if not defined PKG_DIR (
    set "PKG_DIR=%%I"
  ) else if not defined INF (
    set "INF=%%I"
  ) else if not defined CER (
    set "CER=%%I"
  )
)

if "%ARTIFACT_DIR%"=="" (
  echo No artifact with driver package found under %ARTIFACTS_ROOT%
  if not defined NO_PAUSE pause
  exit /b 1
)

set "APO=%PKG_DIR%\VirtualMicApo.dll"

if not exist "%INF%" (
  echo INF not found: %INF%
  if not defined NO_PAUSE pause
  exit /b 1
)

echo Using artifact: %ARTIFACT_DIR%
echo Using package: %PKG_DIR%
echo Using INF: %INF%
if exist "%CER%" (
  echo Installing certificate: %CER%
  certutil -addstore -f TrustedPublisher "%CER%"
  if errorlevel 1 (
    if not defined NO_PAUSE pause
    exit /b 1
  )
  certutil -addstore -f Root "%CER%"
  if errorlevel 1 (
    if not defined NO_PAUSE pause
    exit /b 1
  )
) else (
  echo Certificate not found under artifacts, skipping cert install.
)

echo Installing/updating driver...
pnputil /add-driver "%INF%" /install
if errorlevel 1 (
  if not defined NO_PAUSE pause
  exit /b 1
)

if exist "%APO%" (
  echo Installing APO DLL: %APO%
  copy /y "%APO%" "%SystemRoot%\System32\VirtualMicApo.dll" >nul
  if errorlevel 1 (
    if not defined NO_PAUSE pause
    exit /b 1
  )
) else (
  echo APO DLL not found in package, skipping APO copy.
)

echo Done.
if not defined NO_PAUSE pause
endlocal
