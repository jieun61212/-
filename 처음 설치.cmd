@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title 법률 원고 스튜디오 - 처음 설치
py -3.12 -c "import sys,struct;sys.exit(0 if sys.version_info[:2]==(3,12) and struct.calcsize('P')==8 else 1)" >nul 2>&1
if not errorlevel 1 goto use_py
python -c "import sys,struct;sys.exit(0 if sys.version_info[:2]==(3,12) and struct.calcsize('P')==8 else 1)" >nul 2>&1
if not errorlevel 1 goto use_python
echo Python 3.12 (64비트) 설치가 먼저 필요합니다.
echo 열린 공식 페이지에서 Windows installer (64-bit)를 받으세요.
echo 설치 창 아래 Add python.exe to PATH 체크 후 Install Now를 누르세요.
echo 설치가 끝나면 이 창을 닫고 처음 설치.cmd를 다시 실행하세요.
start "" "https://www.python.org/downloads/release/python-31210/"
pause
exit /b 1
:use_py
py -3.12 scripts\windows_setup.py
goto done
:use_python
python scripts\windows_setup.py
:done
if errorlevel 1 echo 설치에 실패했습니다. 이 창의 오류 내용을 확인해 주세요.
pause
