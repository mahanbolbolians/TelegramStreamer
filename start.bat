@echo off
title TelegramStreamer
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [!] Virtual environment not found. Running setup first...
    call setup.bat
)

echo ===================================================
echo     TelegramStreamer - ADM Streaming Server
echo ===================================================
echo.

.\venv\Scripts\python.exe bot.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo [!] TelegramStreamer stopped with error code %ERRORLEVEL%.
    pause
)
