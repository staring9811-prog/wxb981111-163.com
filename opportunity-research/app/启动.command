#!/bin/bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "没找到 python3，请先安装 Python 3.12+：https://www.python.org/downloads/"; read -n 1; exit 1
fi
if [ ! -d .venv ]; then
  echo "首次运行：正在建立运行环境并安装依赖，需要几分钟……"
  python3 -m venv .venv && .venv/bin/python -m pip install -q -r requirements.txt || { echo "安装失败，请把上面的报错截图发给开发者。"; read -n 1; exit 1; }
fi
.venv/bin/python run.py
