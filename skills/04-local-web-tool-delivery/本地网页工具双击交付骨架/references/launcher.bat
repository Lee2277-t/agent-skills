@echo off
rem Save as UTF-8 WITHOUT BOM, CRLF line endings. Verified original: <project-root>\watermark-remover\启动去水印工具.bat
setlocal EnableExtensions
chcp 65001 >nul
title <工具标题>
cd /d "%~dp0"

set "PYW=%~dp0.venv\Scripts\pythonw.exe"
set "SRV=%~dp0server.py"
if not exist "%PYW%" (
  echo [启动失败] 找不到运行环境 .venv\Scripts\pythonw.exe
  echo 请先在工具目录里执行：python -m venv .venv  然后  .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%PYW%' -ArgumentList '%SRV%' -WorkingDirectory '%~dp0' -WindowStyle Hidden"

ping -n 5 127.0.0.1 >nul

if not exist "%~dp0work\runtime.json" (
  echo [启动失败] 本地服务没有起来，请把 work\tool.log 的最后几行发给开发者。
  pause
  exit /b 1
)

echo 已在浏览器打开工具，这个窗口可以关闭。
ping -n 3 127.0.0.1 >nul
exit /b 0
