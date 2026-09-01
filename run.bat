@echo off
setlocal
cd /d "%~dp0"

if not defined CIVIT_API_KEY (
  echo [ERROR] Environment variable CIVIT_API_KEY is not set.
  echo Set the API key and run this file again.
  pause
  exit /b 1
)

if not "%~1"=="" set "PORT=%~1"
if not defined PORT set "PORT=5055"

if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  python -m venv .venv
  if errorlevel 1 goto :failed
)

".venv\Scripts\python.exe" -c "import flask, requests" >nul 2>&1
if errorlevel 1 (
  echo Installing dependencies...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :failed
)

echo.
echo Civitai Collection Lens: http://127.0.0.1:%PORT%
echo Press Ctrl+C to stop.
echo.
".venv\Scripts\python.exe" app.py
exit /b %errorlevel%

:failed
echo.
echo [ERROR] Setup failed.
pause
exit /b 1
