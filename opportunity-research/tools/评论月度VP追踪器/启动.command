#!/bin/bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "没找到 python3，请先安装 Python 3.10+：https://www.python.org/downloads/"; read -n 1; exit 1
fi
python3 -c "import openpyxl" 2>/dev/null || python3 -m pip install -q --user openpyxl
python3 app.py
