@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto :nopython
if exist ".venv\installed.ok" goto :run
echo First run: creating environment and installing packages, this takes a few minutes...
if exist ".venv" rmdir /s /q ".venv"
python -m venv .venv
if errorlevel 1 goto :err
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 goto :err
echo ok> ".venv\installed.ok"
:run
".venv\Scripts\python.exe" run.py
pause
exit /b 0
:nopython
echo Python not found. Install Python 3.12+ from https://www.python.org/downloads/
echo During install, tick "Add python.exe to PATH", then double-click this file again.
pause
exit /b 1
:err
echo Install failed. Please send a screenshot of the messages above to the developer.
pause
exit /b 1
