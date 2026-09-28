@echo off
REM Meraby Block Exchanger (MBX) - Standalone GUI Launcher
REM Double-click this file to launch the app

echo ========================================
echo Meraby Block Exchanger
echo Offline blueprint toolkit
echo ========================================
echo.
echo Launching standalone application...
echo.

REM Try virtual environment first, fall back to system Python
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

python gui_standalone.py

pause
