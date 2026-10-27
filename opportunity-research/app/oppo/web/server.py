"""Start the local web server (127.0.0.1 only, NFR-006) and open the browser.

Starting again while the service is already running only opens the browser (技术方案 §7.1); a port taken by
another program is reported with the way to choose another one.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import urllib.request
import webbrowser

import uvicorn

from oppo import service as SV
from oppo.web.app import create_app


def _ours(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/jobs/current", timeout=2) as r:
            return "running" in json.loads(r.read())
    except (OSError, ValueError):
        return False


def _busy(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _open(url: str, open_browser: bool, delay: float = 0.0) -> None:
    if not open_browser or os.environ.get("OPPO_NO_BROWSER"):
        return
    if delay:
        threading.Timer(delay, lambda: webbrowser.open(url)).start()
    else:
        webbrowser.open(url)


def serve(app: SV.App | None = None, port: int | None = None, open_browser: bool = True) -> int:
    svc = app or SV.open_app()
    port = int(port or svc.settings.port)
    url = f"http://127.0.0.1:{port}/"
    if _busy(port):
        if _ours(port):
            print(f"品类机会判定台已在运行：{url}（已打开浏览器）", flush=True)
            _open(url, open_browser)
            return 0
        print(f"端口 {port} 已被其他程序占用。请设置环境变量 OPPO_PORT 为其他端口（如 8766）后重新启动。", flush=True)
        return 1
    web = create_app(svc)
    _open(url, open_browser, delay=1.0)
    print(f"品类机会判定台已启动：{url}（只在本机访问；关闭此窗口即停止）", flush=True)
    uvicorn.run(web, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    return 0
