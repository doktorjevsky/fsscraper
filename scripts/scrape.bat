@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0\.."

set VENV=.venv
set YEAR=%1
if "%~1"=="" set YEAR=2026

if not exist "%VENV%" (
    echo Virtual environment not found. Run: scripts\setup.bat
    exit /b 1
)

echo Scraping preschool surveys for year %YEAR%...
"%VENV%\Scripts\python" -m fsscraper.cli scrape --year %YEAR%
