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
set "APO_CLSID={A4B73D9A-7D0E-4E7B-9E4D-9D6D3C1A9B2F}"

REM Pick latest artifact folder that contains the driver package.
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$root = '%ARTIFACTS_ROOT%'; if(!(Test-Path $root)){ exit 1 }; $inf = Get-ChildItem -Path $root -Recurse -Filter SimpleAudioSample.inf -File | Where-Object { $_.FullName -match '\\package\\SimpleAudioSample\.inf$' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if(!$inf){ exit 1 }; $pkg = $inf.Directory.FullName; $relative = $inf.FullName.Substring($root.Length).TrimStart('\'); $artifactName = $relative.Split('\')[0]; $base = Join-Path $root $artifactName; $cer = Get-ChildItem -Path $base -Recurse -Filter package.cer -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1; Write-Output $base; Write-Output $pkg; Write-Output $inf.FullName; if($cer){ Write-Output $cer.FullName }"`) do (
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
  echo Registering APO CLSID...
  reg add "HKCR\CLSID\%APO_CLSID%" /ve /t REG_SZ /d "VirtualMic APO" /f >nul
  if errorlevel 1 (
    if not defined NO_PAUSE pause
    exit /b 1
  )
  reg add "HKCR\CLSID\%APO_CLSID%\InprocServer32" /ve /t REG_SZ /d "%SystemRoot%\System32\VirtualMicApo.dll" /f >nul
  if errorlevel 1 (
    if not defined NO_PAUSE pause
    exit /b 1
  )
  reg add "HKCR\CLSID\%APO_CLSID%\InprocServer32" /v ThreadingModel /t REG_SZ /d "Both" /f >nul
  if errorlevel 1 (
    if not defined NO_PAUSE pause
    exit /b 1
  )
) else (
  echo APO DLL not found in package, skipping APO copy.
)

echo Restarting audio services...
powershell -NoProfile -Command "Restart-Service -Name audiosrv,AudioEndpointBuilder -Force"
if errorlevel 1 (
  if not defined NO_PAUSE pause
  exit /b 1
)

echo Done.
if not defined NO_PAUSE pause
endlocal
