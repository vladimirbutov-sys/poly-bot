@echo off
title Polymarket Dashboard
echo Starting Polymarket Dashboard...
echo.
cd /d "%~dp0"
py -3.12 app.py
pause
