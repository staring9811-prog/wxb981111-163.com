@echo off
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" (echo 请把报告 HTML 文件拖到这个图标上 & pause & exit /b)
python -X utf8 import_from_html.py "%~1"
echo.
echo 完成。报告在 data 文件夹里，可以运行 python serve.py 打开。
pause
