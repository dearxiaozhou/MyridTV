@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "PY=python"
if exist "%~dp0python\python.exe" set "PY=%~dp0python\python.exe"
if exist "%~dp0_internal\python\python.exe" set "PY=%~dp0_internal\python\python.exe"

"%PY%" -B "%~dp0测试画布MCP.py"
echo.
pause