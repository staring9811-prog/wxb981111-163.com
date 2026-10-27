@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在从 GitHub 获取最新程序文件……
.venv\Scripts\python -m oppo.cli update %*
pause
