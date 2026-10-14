@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title 법률 원고 스튜디오
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" scripts\windows_launch.py
if errorlevel 1 pause
exit /b
:missing
echo 먼저 처음 설치.cmd를 더블클릭해 설치를 완료하세요.
pause
exit /b 1
