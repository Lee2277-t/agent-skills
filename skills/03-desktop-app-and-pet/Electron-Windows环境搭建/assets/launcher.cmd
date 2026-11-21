@echo off
setlocal
cd /d "%~dp0"

if not exist "node_modules\electron\dist\electron.exe" (
  echo [launcher] Electron runtime is missing.
  echo [launcher] Run the bootstrap steps and ensure-electron before launching.
  pause
  exit /b 1
)

start "" "node_modules\electron\dist\electron.exe" .
