@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo 没找到 Python。请先安装 Python 3.12 或更新版本：https://www.python.org/downloads/
  echo 安装时勾选 "Add python.exe to PATH"，装好后再双击本文件。
  pause
  exit /b 1
)
if not exist .venv (
  echo 首次运行：正在建立运行环境并安装依赖，需要几分钟……
  python -m venv .venv || goto :err
  .venv\Scripts\python -m pip install -q -r requirements.txt || goto :err
)
.venv\Scripts\python run.py
pause
exit /b 0
:err
echo 安装失败，请把上面的报错截图发给开发者。
pause
exit /b 1
