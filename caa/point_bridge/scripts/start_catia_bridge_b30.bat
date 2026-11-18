@echo off
setlocal
if not defined CATIA_MCP_PYTHON set "CATIA_MCP_PYTHON=python"
"%CATIA_MCP_PYTHON%" "%~dp0start_catia_bridge_b30.py" %*
exit /b %errorlevel%
