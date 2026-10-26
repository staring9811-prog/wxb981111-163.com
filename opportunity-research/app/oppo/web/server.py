"""Start the local web server (127.0.0.1 only, NFR-006) and open the browser."""

from __future__ import annotations

import os
import threading
import webbrowser

import uvicorn

from oppo import service as SV
from oppo.web.app import create_app


def serve(app: SV.App | None = None, port: int | None = None, open_browser: bool = True) -> None:
    svc = app or SV.open_app()
    port = int(port or svc.settings.port)
    web = create_app(svc)
    url = f"http://127.0.0.1:{port}/"
    if open_browser and not os.environ.get("OPPO_NO_BROWSER"):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"品类机会判定台已启动：{url}（只在本机访问；关闭此窗口即停止）", flush=True)
    uvicorn.run(web, host="127.0.0.1", port=port, log_level="warning", access_log=False)
