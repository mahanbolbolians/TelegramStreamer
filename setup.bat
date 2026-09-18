@echo off
title TelegramStreamer Setup
cd /d "%~dp0"

echo ===================================================
echo     TelegramStreamer - Automated Setup
echo ===================================================
echo.

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set PY_CMD=py -3.12
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set PY_CMD=python
    ) else (
        echo [ERROR] Python was not found on your system!
        echo Please install Python 3.10+ from python.org and add it to PATH.
        echo.
        pause
        exit /b 1
    )
)

echo [*] Checking virtual environment...
if not exist "venv\Scripts\python.exe" (
    echo [*] Creating virtual environment (venv)...
    %PY_CMD% -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo [!] Trying generic python...
        python -m venv venv
    )
)

echo [*] Installing dependencies from requirements.txt...
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\pip.exe install -r requirements.txt

echo.
echo ===================================================
echo   [SUCCESS] Setup Completed!
echo   Double-click "start.bat" to start TelegramStreamer.
echo ===================================================
echo.
pause
