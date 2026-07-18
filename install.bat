@echo off
setlocal enabledelayedexpansion
title Tank HUD Overlay - Installer
cd /d "%~dp0"

echo ============================================
echo   Tank HUD Overlay - Installer
echo ============================================
echo.

REM --- Check Python is installed and on PATH ---
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found on your PATH.
    echo.
    echo 1. Install Python from https://www.python.org/downloads/
    echo 2. On the FIRST install screen, check the box that says
    echo    "Add python.exe to PATH" before clicking Install.
    echo 3. Close this window and double-click install.bat again.
    echo.
    pause
    exit /b 1
)

echo [OK] Python found:
python --version
echo.

REM --- Upgrade pip quietly, then install requirements ---
echo Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1

echo Installing required packages, this can take a minute...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Package install failed - scroll up to see the error above.
    echo Common fixes:
    echo   - Right-click install.bat and choose "Run as administrator"
    echo   - Make sure you're connected to the internet
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] Python packages installed.
echo.

REM --- Check for Tesseract OCR engine ---
set TESS_FOUND=0
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set TESS_FOUND=1
if exist "%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe" set TESS_FOUND=1
where tesseract >nul 2>&1
if not errorlevel 1 set TESS_FOUND=1

if "%TESS_FOUND%"=="0" (
    echo [ACTION NEEDED] Tesseract-OCR was not found on this PC.
    echo This is a separate program the overlay needs to read in-game text.
    echo.
    echo Opening the download page in your browser now...
    start https://github.com/UB-Mannheim/tesseract/wiki
    echo.
    echo Install it with the default options ^(default install folder is
    echo fine, the overlay finds it automatically^), then run install.bat
    echo again to confirm everything's set up.
    echo.
    pause
    exit /b 1
) else (
    echo [OK] Tesseract-OCR found.
)

echo.
echo ============================================
echo   Setup complete!
echo   Next: run calibrate.py once to set up your screen regions
echo   ^(see README.md^), then double-click run.bat to start.
echo ============================================
pause
