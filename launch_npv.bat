@echo off
setlocal
cd /d "%~dp0"
echo NVP local foundation - developer preview
echo ---------------------------------------
where python >nul 2>nul
if errorlevel 1 (
  echo Python is missing. See docs\FOUNDATION_RUNBOOK.md
  pause
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo Node/npm is missing. See docs\FOUNDATION_RUNBOOK.md
  pause
  exit /b 1
)
if not exist "frontend\node_modules" (
  echo Frontend dependencies are not installed.
  echo Run npm install inside the frontend folder once.
  pause
  exit /b 1
)
start "NVP Local API" /D "%~dp0" cmd /k python -m uvicorn backend.nvp_api:app --host 127.0.0.1 --port 8000
start "NVP UI" /D "%~dp0frontend" cmd /k npm run dev
echo Open http://127.0.0.1:3000 in your browser.
echo This is a local development preview, not a packaged installer.
start "" "http://127.0.0.1:3000"
endlocal
