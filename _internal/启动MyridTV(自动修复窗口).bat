@echo off
set "PYTHON_EXE=C:\Users\<user>\AppData\Local\Programs\Python\Python313\python.exe"
set "SCRIPT=%~dp0启动MyridTV_自动修复版.py"
start "" "%PYTHON_EXE%" -B "%SCRIPT%"
