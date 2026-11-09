@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 浴室柜报告（关掉这个窗口报告就停止）
python -c "import pandas,numpy,openpyxl" 2>nul || (echo 首次使用，正在安装所需组件，请稍等…… & python -m pip install pandas numpy openpyxl)
echo 正在打开报告，浏览器会自动弹出：http://127.0.0.1:8765
echo 看报告期间不要关这个窗口。
echo.
python -X utf8 serve.py
if errorlevel 1 (echo. & echo 打开失败，请把上面的报错截图发给 Claude & pause)
