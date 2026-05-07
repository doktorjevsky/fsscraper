@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0\.."

set VENV=.venv

if not exist "%VENV%" (
    echo Creating virtual environment...
    python -m venv "%VENV%"
)

echo Installing dependencies...
"%VENV%\Scripts\pip" install --upgrade pip
"%VENV%\Scripts\pip" install -r requirements.txt

echo Done. Virtual environment ready at %VENV%\
