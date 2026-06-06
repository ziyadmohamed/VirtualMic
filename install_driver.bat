@echo off
setlocal EnableDelayedExpansion

set "NO_PAUSE="
set "SCRIPT_ARGS="
set "HAS_PACKAGE_PATH="
for %%I in ("%~dp0.") do set "ROOT_DIR=%%~fI"
set "REPORTER=%ROOT_DIR%\report_installer_event.ps1"

:collect_args
if "%~1"=="" goto args_done
if /i "%~1"=="--no-pause" (
  set "NO_PAUSE=1"
) else if /i "%~1"=="-PackagePath" (
  set "HAS_PACKAGE_PATH=1"
  set "SCRIPT_ARGS=!SCRIPT_ARGS! ""%~1"""
) else (
  set "SCRIPT_ARGS=!SCRIPT_ARGS! ""%~1"""
)
shift
goto collect_args

:args_done

set "SCRIPT=%ROOT_DIR%\install_driver_full.ps1"
set "PACKAGE_DIR=%ROOT_DIR%\package"

if not exist "%SCRIPT%" (
  echo Missing installer script: %SCRIPT%
  call :report_launcher_error "Missing installer script" "%SCRIPT%"
  if not defined NO_PAUSE pause
  exit /b 1
)

if not defined HAS_PACKAGE_PATH if exist "%PACKAGE_DIR%\SimpleAudioSample.inf" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -PackagePath "%PACKAGE_DIR%" %SCRIPT_ARGS%
) else (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %SCRIPT_ARGS%
)
set "EXITCODE=%ERRORLEVEL%"

if %EXITCODE%==3010 (
  echo Reboot scheduled or required. The installer will continue after sign-in.
  if not defined NO_PAUSE pause
  exit /b 0
)

if not %EXITCODE%==0 (
  echo Installation failed. See install_driver_full.log for details.
  if not defined NO_PAUSE pause
  exit /b %EXITCODE%
)

echo Installation completed successfully.
if not defined NO_PAUSE pause
exit /b 0

:report_launcher_error
if not exist "%REPORTER%" exit /b 0
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%REPORTER%" -Kind "LauncherError" -Summary "%~1" -Details "%~2" -Revision "batch-launcher" -PackagePath "%ROOT_DIR%" >nul 2>nul
exit /b 0
