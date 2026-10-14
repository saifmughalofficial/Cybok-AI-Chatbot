@echo off
title Cybok - Your AI. Your Workspace.
cd /d "%~dp0"
echo.
echo   ==========================================
echo     CYBOK  -  Your AI. Your Workspace.
echo   ==========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo   Python was not found. Install Python 3.10+ from https://www.python.org/downloads/
  echo   and tick "Add Python to PATH" during installation.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo   [1/3] Creating virtual environment ^(first run only^)...
  python -m venv .venv
  if errorlevel 1 ( echo   Could not create the virtual environment. & pause & exit /b 1 )
)

echo   [2/3] Checking packages...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 ( echo   Package installation failed. Check your internet connection. & pause & exit /b 1 )

echo   [3/3] Starting Cybok...
".venv\Scripts\python.exe" run.py %*
pause
