@echo off
setlocal

set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"
set "CAA_WORKSPACE=%REPO_ROOT%\caa_workspace"
set "INSTALL_CONFIG=%CAA_WORKSPACE%\Install_config_win_b64"

if not defined CATIA_B30_INSTALL (
  if exist "%INSTALL_CONFIG%" (
    for /f "usebackq skip=1 delims=" %%I in ("%INSTALL_CONFIG%") do (
      if not defined CATIA_B30_INSTALL set "CATIA_B30_INSTALL=%%I"
    )
  )
)

if not defined CATIA_B30_INSTALL (
  echo CATIA_B30_INSTALL is not set and %INSTALL_CONFIG% was not usable.
  exit /b 1
)

set "MKMK_SETENV=%CATIA_B30_INSTALL%\win_b64\code\command\MkmkSetenv.bat"
set "MKMK_CMD=%CATIA_B30_INSTALL%\win_b64\code\command\mkmk.bat"

if not exist "%MKMK_SETENV%" (
  echo MkmkSetenv.bat not found: %MKMK_SETENV%
  exit /b 1
)

if not exist "%MKMK_CMD%" (
  echo mkmk.bat not found: %MKMK_CMD%
  exit /b 1
)

if not defined RADECATSettingPath (
  if exist "%APPDATA%\DassaultSystemes\CATSettings\RADE\RADELicensing.xml" (
    set "RADECATSettingPath=%APPDATA%\DassaultSystemes\CATSettings\RADE"
  )
)

if not defined RADECATSettingPath (
  echo RADECATSettingPath is not set. Configure RADE licensing with CATVBTLicenser first.
  exit /b 1
)

set "MkmkINSTALL_PATH=%CATIA_B30_INSTALL%"
call "%MKMK_SETENV%"
if errorlevel 1 exit /b %errorlevel%

rem mkmk does not reliably track every nested CAA header or restored source
rem timestamp. Remove only the generated Bridge objects so both the add-in UI
rem registration and the branded command module are rebuilt.
set "BRIDGE_ADDIN_OBJECT_DIR=%CAA_WORKSPACE%\CatiaPyBridgeFramework\CatiaPyBridgeAddin.m\Objects\win_b64"
if exist "%BRIDGE_ADDIN_OBJECT_DIR%" del /q "%BRIDGE_ADDIN_OBJECT_DIR%\CatiaPyBridge*.obj" >nul 2>&1

set "BRIDGE_OBJECT_DIR=%CAA_WORKSPACE%\CatiaPyBridgeFramework\CatiaPyBridgeCmdModule.m\Objects\win_b64"
if exist "%BRIDGE_OBJECT_DIR%" del /q "%BRIDGE_OBJECT_DIR%\CatiaPyBridge*.obj" >nul 2>&1

pushd "%CAA_WORKSPACE%"
if errorlevel 1 exit /b 1
set "BUILD_LOG=%TEMP%\CatiaPyBridge_mkmk_%RANDOM%_%RANDOM%.log"
call "%MKMK_CMD%" -a > "%BUILD_LOG%" 2>&1
set "BUILD_RC=%errorlevel%"
type "%BUILD_LOG%"
findstr /C:"-ERROR:" /C:"fatal error" "%BUILD_LOG%" >nul
if not errorlevel 1 set "BUILD_RC=1"
echo Build log retained: %BUILD_LOG%
popd

if "%BUILD_RC%"=="0" (
  call "%REPO_ROOT%\scripts\sync_caa_runtime.bat"
  if errorlevel 1 set "BUILD_RC=1"
)

exit /b %BUILD_RC%
