@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0\.."

set VENV=.venv

if not exist "%VENV%" (
    echo Virtual environment not found. Run: scripts\setup.bat
    exit /b 1
)

echo Building preschool_map_2026.html...
"%VENV%\Scripts\python" build_map.py

echo Done. Open preschool_map_2026.html in your browser.
