"""Shared fixtures: isolated data directories, prepared H1-A state, a live local server and a browser.

Every test gets its own data directory (a copy of a prepared one), so tests never share a database.
"""

from __future__ import annotations

import shutil
import socket
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
import uvicorn

from oppo import service as SV
from oppo import settings as S

APP_ROOT = Path(__file__).resolve().parents[1]
FIX = APP_ROOT / "fixtures" / "packages"
TOKEN = "test-token"


def fixture_pkg(name: str) -> Path:
    p = FIX / name
    if not p.exists():
        pytest.skip(f"样例数据 {name} 未生成（运行 python -m fixtures.build_samples）")
    return p


def open_dir(d: Path) -> SV.App:
    return SV.open_app(S.Settings(data_dir=d, operator="wen", port=0))


def clone_dir(src: Path, dst: Path) -> Path:
    """Copy a data directory; the database is copied with SQLite's backup API (consistent under WAL)."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name.startswith("oppo.sqlite3"):
            continue
        if item.is_dir():
            shutil.copytree(item, dst / item.name, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dst / item.name)
    s = sqlite3.connect(str(src / "oppo.sqlite3"))
    t = sqlite3.connect(str(dst / "oppo.sqlite3"))
    s.backup(t)
    t.close()
    s.close()
    return dst


def _prepared(tmp_path_factory: pytest.TempPathFactory, name: str, steps: tuple[str, ...]) -> Path:
    d = tmp_path_factory.mktemp(name)
    app = open_dir(d)
    for st in steps:
        if st.startswith("import:"):
            SV.import_package(app, fixture_pkg(st.split(":", 1)[1]))
        elif st == "confirm":
            SV.contract_confirm(app)
        elif st == "compute":
            SV.compute(app)
        elif st.startswith("backtest"):
            SV.backtest(app, mode=st.split(":", 1)[1] if ":" in st else "history")
    app.engine.dispose()
    SV._apps.pop(str(d.resolve()), None)
    return d


@pytest.fixture(scope="session")
def h1a_imported(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """H1-A imported, nothing confirmed."""
    return _prepared(tmp_path_factory, "h1a_imported", ("import:H1-A",))


@pytest.fixture(scope="session")
def h1a_done(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """H1-A imported, contract v1 confirmed, computed and backtested (snapshot 2026-03 第 1 版)."""
    return _prepared(tmp_path_factory, "h1a_done", ("import:H1-A", "confirm", "compute", "backtest"))


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture
def clone(tmp_path: Path):  # type: ignore[no-untyped-def]
    n = {"i": 0}

    def make(src: Path) -> Path:
        n["i"] += 1
        return clone_dir(src, tmp_path / f"data{n['i']}")

    return make


@dataclass
class Live:
    url: str
    app: SV.App
    token: str = TOKEN

    def u(self, path: str) -> str:
        return self.url.rstrip("/") + path


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def live_server():  # type: ignore[no-untyped-def]
    """live_server(data_dir) -> Live: the real FastAPI app on 127.0.0.1:<free port>."""
    from oppo.web.app import create_app

    servers: list[tuple[uvicorn.Server, threading.Thread, SV.App]] = []

    def start(d: Path) -> Live:
        app = open_dir(d)
        web = create_app(app, token=TOKEN)
        port = _free_port()
        server = uvicorn.Server(uvicorn.Config(web, host="127.0.0.1", port=port, log_level="warning"))
        t = threading.Thread(target=server.run, daemon=True)
        t.start()
        for _ in range(200):
            if server.started:
                break
            time.sleep(0.05)
        servers.append((server, t, app))
        return Live(f"http://127.0.0.1:{port}", app)

    yield start
    for server, t, app in servers:
        server.should_exit = True
        t.join(timeout=10)
        app.engine.dispose()
        SV._apps.pop(str(app.settings.data_dir.resolve()), None)


@pytest.fixture(scope="session")
def browser():  # type: ignore[no-untyped-def]
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        exe = Path("/opt/pw-browsers/chromium")
        b = pw.chromium.launch(executable_path=str(exe) if exe.exists() else None)
        yield b
        b.close()


@pytest.fixture
def page(browser):  # type: ignore[no-untyped-def]
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    p = ctx.new_page()
    errors: list[str] = []
    p.on("pageerror", lambda e: errors.append(str(e)))
    p.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    p.js_errors = errors  # type: ignore[attr-defined]
    yield p
    ctx.close()


def wait_job(live: Live, timeout: float = 300) -> dict:
    """Block until no job is running; return the last job state."""
    import json
    import urllib.request

    end = time.time() + timeout
    while time.time() < end:
        with urllib.request.urlopen(live.u("/jobs/current")) as r:
            st = json.loads(r.read())
        if not st.get("running"):
            return st
        time.sleep(0.5)
    raise TimeoutError("job did not finish")
