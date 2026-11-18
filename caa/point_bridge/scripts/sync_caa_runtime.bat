@echo off
setlocal

set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"
set "CAA_WORKSPACE=%REPO_ROOT%\caa_workspace"
set "BRIDGE_RUNTIME=%CAA_WORKSPACE%\CatiaPyBridgeRuntime"
set "BRIDGE_BIN=%BRIDGE_RUNTIME%\code\bin"
set "BRIDGE_PRODUCT_IC=%BRIDGE_RUNTIME%\code\productIC"
set "BRIDGE_MSGCATALOG=%BRIDGE_RUNTIME%\resources\msgcatalog"
set "BUILD_BIN=%CAA_WORKSPACE%\win_b64\code\bin"
set "SOURCE_PRODUCT_IC=%CAA_WORKSPACE%\win_b64\code\productIC"
set "SOURCE_MSGCATALOG=%CAA_WORKSPACE%\CatiaPyBridgeFramework\CNext\resources\msgcatalog"

call :require "%BUILD_BIN%\CatiaPyBridgeCmdModule.dll"
if errorlevel 1 exit /b 1
call :require "%BUILD_BIN%\CatiaPyBridgeAddin.dll"
if errorlevel 1 exit /b 1
call :require "%SOURCE_PRODUCT_IC%\CatiaPyBridgeFrameworkIC.xml"
if errorlevel 1 exit /b 1
call :require "%SOURCE_MSGCATALOG%\CatiaPyBridgeAddin.CATNls"
if errorlevel 1 exit /b 1
call :require "%SOURCE_MSGCATALOG%\CatiaPyBridgeCommandHeader.CATNls"
if errorlevel 1 exit /b 1

if not exist "%BRIDGE_BIN%" mkdir "%BRIDGE_BIN%"
if not exist "%BRIDGE_PRODUCT_IC%" mkdir "%BRIDGE_PRODUCT_IC%"
if not exist "%BRIDGE_MSGCATALOG%" mkdir "%BRIDGE_MSGCATALOG%"

copy /y "%BUILD_BIN%\CatiaPyBridgeCmdModule.dll" "%BRIDGE_BIN%\CatiaPyBridgeCmdModule.dll" >nul
if errorlevel 1 exit /b 1
copy /y "%BUILD_BIN%\CatiaPyBridgeAddin.dll" "%BRIDGE_BIN%\CatiaPyBridgeAddin.dll" >nul
if errorlevel 1 exit /b 1
copy /y "%SOURCE_PRODUCT_IC%\CatiaPyBridgeFrameworkIC.xml" "%BRIDGE_PRODUCT_IC%\CatiaPyBridgeFrameworkIC.xml" >nul
if errorlevel 1 exit /b 1
copy /y "%SOURCE_MSGCATALOG%\CatiaPyBridgeAddin.CATNls" "%BRIDGE_MSGCATALOG%\CatiaPyBridgeAddin.CATNls" >nul
if errorlevel 1 exit /b 1
copy /y "%SOURCE_MSGCATALOG%\CatiaPyBridgeCommandHeader.CATNls" "%BRIDGE_MSGCATALOG%\CatiaPyBridgeCommandHeader.CATNls" >nul
if errorlevel 1 exit /b 1

if not defined CATIA_MCP_PYTHON set "CATIA_MCP_PYTHON=python"
"%CATIA_MCP_PYTHON%" -m catia_mcp.caa.runtime_manifest --workspace "%CAA_WORKSPACE%"
if errorlevel 1 exit /b 1

echo Synchronized isolated CatiaPyBridge runtime: %BRIDGE_RUNTIME%
exit /b 0

:require
if exist "%~1" exit /b 0
echo Required CAA runtime input not found: %~1
exit /b 1
