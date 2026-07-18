@echo off
title Tank HUD Overlay - Calibration
cd /d "%~dp0"

echo Get the game showing on screen with the HUD element visible,
echo then click-drag a box around it in the window that opens.
echo.
pause

python calibrate.py

pause
