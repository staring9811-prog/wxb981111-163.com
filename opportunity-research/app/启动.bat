@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto :nopython

rem ---- auto update: git pull (system git, or the git bundled with GitHub Desktop) ----
set "GITEXE="
where git >nul 2>nul && set "GITEXE=git"
if not defined GITEXE for /d %%D in ("%LOCALAPPDATA%\GitHubDesktop\app-*") do if exist "%%D\resources\app\git\cmd\git.exe" set "GITEXE=%%D\resources\app\git\cmd\git.exe"
if defined GITEXE (
  echo Checking for updates...
  set GIT_TERMINAL_PROMPT=0
  "%GITEXE%" pull --ff-only
  if errorlevel 1 echo Update skipped ^(offline, not signed in, or local changes^). Starting the current version.
) else (
  echo Git not found, skipping auto update.
)

rem ---- (re)install packages when missing or when requirements.txt changed ----
if not exist ".venv\installed.ok" goto :install
fc /b requirements.txt ".venv\installed.ok" >nul 2>nul
if errorlevel 1 goto :install
goto :run

:install
echo Installing packages, this takes a few minutes the first time...
if not exist ".venv\Scripts\python.exe" (
  if exist ".venv" rmdir /s /q ".venv"
  python -m venv .venv
  if errorlevel 1 goto :err
)
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 goto :err
copy /y requirements.txt ".venv\installed.ok" >nul

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
