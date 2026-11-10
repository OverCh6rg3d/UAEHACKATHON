@echo off
REM Start the DABAB demo: copies demo data if needed, starts the server, opens the browser.
cd /d "%~dp0\.."
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.9+ is required: https://www.python.org/downloads/
  pause
  exit /b 1
)
python final\start.py
pause
