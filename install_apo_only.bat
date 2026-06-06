@echo on
setlocal

set "LOG=%~dp0install_apo_only.log"
set "NO_PAUSE="
if /i "%~1"=="--no-pause" set "NO_PAUSE=1"

echo ===== APO INSTALL START %date% %time% ===== > "%LOG%"
call :log "Log file: %LOG%"

REM Must run as Administrator
net session >nul 2>&1
if errorlevel 1 (
  call :log "Please run this script as Administrator."
  set "EXITCODE=1"
  goto :done
)

set "ARTIFACTS_ROOT=%~dp0artifacts"
call :log "Artifacts root: %ARTIFACTS_ROOT%"

REM Pick latest artifact folder that contains the driver package
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$root = '%ARTIFACTS_ROOT%'; if(!(Test-Path $root)){exit 1}; $dir = Get-ChildItem -Path $root -Directory | Sort-Object LastWriteTime -Descending | ForEach-Object { $inf = Join-Path $_.FullName 'StMicDriver-Output\\StMicDriver\\x64\\Release\\package\\SimpleAudioSample.inf'; if(Test-Path $inf){ $_.FullName; break } }; if(!$dir){exit 1}; $dir"`) do set "ARTIFACT_DIR=%%I"

if "%ARTIFACT_DIR%"=="" (
  call :log "No artifact with driver package found under %ARTIFACTS_ROOT%"
  set "EXITCODE=1"
  goto :done
)

set "PKG_DIR=%ARTIFACT_DIR%\StMicDriver-Output\StMicDriver\x64\Release\package"
set "INF=%PKG_DIR%\SimpleAudioSample.inf"
set "APO=%PKG_DIR%\VirtualMicApo.dll"
set "DEST_DLL=%SystemRoot%\System32\VirtualMicApo.dll"
call :log "Package dir: %PKG_DIR%"
call :log "INF: %INF%"
call :log "APO: %APO%"
call :log "Destination DLL: %DEST_DLL%"

if not exist "%INF%" (
  call :log "INF not found: %INF%"
  set "EXITCODE=1"
  goto :done
)
if not exist "%APO%" (
  call :log "APO DLL not found: %APO%"
  set "EXITCODE=1"
  goto :done
)

REM Extract CLSID and friendly name from INF (fallback to defaults)
set "CLSID="
set "FRIENDLY="
for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b /i "VirtualMicApo.CLSID" "%INF%"`) do set "CLSID=%%B"
for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b /i "VirtualMicApo.FriendlyName" "%INF%"`) do set "FRIENDLY=%%B"
for /f "tokens=* delims= " %%A in ("%CLSID%") do set "CLSID=%%A"
for /f "tokens=* delims= " %%A in ("%FRIENDLY%") do set "FRIENDLY=%%A"
set "CLSID=%CLSID:"=%"
set "FRIENDLY=%FRIENDLY:"=%"
if "%CLSID%"=="" set "CLSID={A4B73D9A-7D0E-4E7B-9E4D-9D6D3C1A9B2F}"
if "%FRIENDLY%"=="" set "FRIENDLY=VirtualMic APO"

if "%CLSID%"=="" (
  call :log "Failed to read CLSID from INF."
  set "EXITCODE=1"
  goto :done
)

call :log "Using artifact: %ARTIFACT_DIR%"
call :log "APO DLL: %APO%"
call :log "CLSID: %CLSID%"
call :log "Friendly name: %FRIENDLY%"

copy /y "%APO%" "%DEST_DLL%"
if errorlevel 1 (
  call :log "Failed to copy APO DLL to %DEST_DLL%"
  set "EXITCODE=1"
  goto :done
)

reg add "HKCR\CLSID\%CLSID%" /ve /d "%FRIENDLY%" /f
if errorlevel 1 (
  call :log "Failed to write CLSID key."
  set "EXITCODE=1"
  goto :done
)
reg add "HKCR\CLSID\%CLSID%\InprocServer32" /ve /d "%DEST_DLL%" /f
if errorlevel 1 (
  call :log "Failed to write InprocServer32 default value."
  set "EXITCODE=1"
  goto :done
)
reg add "HKCR\CLSID\%CLSID%\InprocServer32" /v ThreadingModel /t REG_SZ /d Both /f
if errorlevel 1 (
  call :log "Failed to write ThreadingModel."
  set "EXITCODE=1"
  goto :done
)

REM Basic verification
set "REG_DLL="
for /f "tokens=2,*" %%A in ('reg query "HKCR\CLSID\%CLSID%\InprocServer32" /ve ^| findstr /i "REG_SZ"') do set "REG_DLL=%%B"
set "REG_TM="
for /f "tokens=2,*" %%A in ('reg query "HKCR\CLSID\%CLSID%\InprocServer32" /v ThreadingModel ^| findstr /i "REG_SZ"') do set "REG_TM=%%B"
call :log "Registry InprocServer32: %REG_DLL%"
call :log "Registry ThreadingModel: %REG_TM%"

if exist "%DEST_DLL%" if /i "%REG_DLL%"=="%DEST_DLL%" if /i "%REG_TM%"=="Both" (
  call :log "APO install looks OK."
  set "EXITCODE=0"
  goto :done
)

call :log "APO install verification failed."
call :log "DLL exists: %DEST_DLL%"
call :log "Registry InprocServer32: %REG_DLL%"
call :log "Registry ThreadingModel: %REG_TM%"
set "EXITCODE=1"
goto :done

:log
echo %~1
echo %~1>>"%LOG%"
goto :eof

:done
call :log "Exit code: %EXITCODE%"
call :log "===== APO INSTALL END %date% %time% ====="
if not defined NO_PAUSE pause
exit /b %EXITCODE%
