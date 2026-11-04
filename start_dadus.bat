@echo off
setlocal
title DADUS - Personal AI Operating Assistant

echo ==============================================================================
echo                      DADUS - Personal AI Operating Assistant
echo                      Autonomous Windows OS Voice ^& Web Controller
echo ==============================================================================
echo.

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found in your system PATH.
    echo Please install Python 3.10 or higher from https://www.python.org/
    pause
    exit /b 1
)

if exist ".venv\Scripts\activate.bat" (
    echo [*] Activating virtual environment .venv
    call .venv\Scripts\activate.bat
)
if exist "venv\Scripts\activate.bat" (
    echo [*] Activating virtual environment venv
    call venv\Scripts\activate.bat
)

python -c "import fastapi, uvicorn, sqlalchemy, pydantic" >nul 2>nul
if errorlevel 1 (
    echo [WARNING] Installing dependencies from requirements.txt...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install required packages.
        pause
        exit /b 1
    )
)

echo [*] DADUS environment verified successfully.
echo.
echo Choose launch mode:
echo   [1] Start Web Dashboard and Voice Assistant [Default - Browser]
echo   [2] Start Background System Tray Daemon [Silent in Taskbar]
echo   [3] Start Interactive Voice CLI [Terminal mode]
echo   [4] Run Full Automated Test Suite
echo   [5] Exit
echo.

set MODE=1
set /p MODE="Select mode [1-5] (default=1): "

if "%MODE%"=="1" goto launch_web
if "%MODE%"=="2" goto launch_tray
if "%MODE%"=="3" goto launch_cli
if "%MODE%"=="4" goto launch_tests
if "%MODE%"=="5" goto exit_script

:launch_web
echo [*] Starting DADUS Web Dashboard on http://127.0.0.1:8000
start "" "http://127.0.0.1:8000"
python run.py
goto end_script

:launch_tray
echo [*] Starting DADUS silently in Windows System Tray...
python run.py --tray
goto end_script

:launch_cli
echo [*] Starting DADUS Interactive Terminal...
python run.py --cli
goto end_script

:launch_tests
echo [*] Running full test suite...
python -m pytest -v
pause
goto end_script

:exit_script
echo Exiting.
exit /b 0

:end_script
if errorlevel 1 (
    echo.
    echo [!] DADUS exited with an error code: %errorlevel%
    pause
)
