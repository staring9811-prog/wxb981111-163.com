@echo off
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" (echo 请把报告 HTML 文件拖到这个图标上 & pause & exit /b)
python -c "import pandas,numpy,openpyxl" 2>nul || (echo 首次使用，正在安装所需组件，请稍等…… & python -m pip install pandas numpy openpyxl)
python -X utf8 import_from_html.py "%~1"
if errorlevel 1 (echo. & echo 导入或生成失败，请把上面的内容截图发给 Claude & pause & exit /b)
echo.
echo 完成。双击“打开报告.bat”查看。
pause
