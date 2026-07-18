@echo off
title Tank HUD Overlay
cd /d "%~dp0"

python overlay.py

if errorlevel 1 (
    echo.
    echo ============================================
    echo   The overlay closed with an error - see above.
    echo ============================================
)
pause
