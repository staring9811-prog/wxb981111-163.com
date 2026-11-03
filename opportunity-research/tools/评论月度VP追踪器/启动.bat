@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo 没找到 Python。请先安装 Python 3.10 或更新版本：https://www.python.org/downloads/
  echo 安装时勾选 "Add python.exe to PATH"，装好后再双击本文件。
  pause
  exit /b 1
)
python -c "import openpyxl" 2>nul || python -m pip install -q openpyxl
python app.py
pause
