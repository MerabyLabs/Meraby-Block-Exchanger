@echo off
setlocal
title Meraby Block Exchanger
cd /d "%~dp0"

echo ========================================
echo Meraby Block Exchanger
echo Offline blueprint toolkit
echo ========================================
echo.

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    python gui_standalone.py
    goto :AFTER
)

py -3.12 -c "import sys" >nul 2>nul
if not errorlevel 1 goto :PY312
py -3.11 -c "import sys" >nul 2>nul
if not errorlevel 1 goto :PY311
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 goto :PY3
python -c "import sys" >nul 2>nul
if not errorlevel 1 goto :PYTHON

echo Python 3.11 or 3.12 was not found.
echo Install Python from https://www.python.org/downloads/ and enable the py launcher.
echo This toolkit is tested on Python 3.11 and 3.12. The Windows Store "python" stub is not used.
pause
exit /b 1

:PY312
py -3.12 gui_standalone.py
goto :AFTER
:PY311
py -3.11 gui_standalone.py
goto :AFTER
:PY3
py -3 gui_standalone.py
goto :AFTER
:PYTHON
python gui_standalone.py

:AFTER
if errorlevel 1 (
    echo.
    echo Meraby Block Exchanger exited with an error.
    pause
    exit /b 1
)
