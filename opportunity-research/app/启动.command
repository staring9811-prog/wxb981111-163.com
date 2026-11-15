#!/bin/bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python not found. Install Python 3.12+ from https://www.python.org/downloads/"; read -n 1; exit 1
fi
if command -v git >/dev/null 2>&1; then
  echo "Checking for updates..."
  GIT_TERMINAL_PROMPT=0 git pull --ff-only || echo "Update skipped (offline, not signed in, or local changes). Starting the current version."
fi
if [ ! -x .venv/bin/python ] || ! cmp -s requirements.txt .venv/installed.ok; then
  echo "Installing packages, this takes a few minutes the first time..."
  [ -x .venv/bin/python ] || python3 -m venv .venv || { echo "Install failed. Please send a screenshot to the developer."; read -n 1; exit 1; }
  .venv/bin/python -m pip install -q -r requirements.txt || { echo "Install failed. Please send a screenshot to the developer."; read -n 1; exit 1; }
  cp requirements.txt .venv/installed.ok
fi
.venv/bin/python run.py
