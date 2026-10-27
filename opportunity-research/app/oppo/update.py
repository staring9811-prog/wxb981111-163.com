"""`oppo update`: replace the program files with the latest code from GitHub (or a zip already downloaded).

What changes: app/oppo, app/docs, app/tests, app/packaging, app/fixtures (except the generated packages),
pyproject.toml and README.md. What never changes: the data directory (database, packages, exports, tokens)
and the virtual environment. The files being replaced are copied to data/update_backup/<time>/ first, so an
update can be undone by copying them back. Dependencies are re-installed only when pyproject.toml changed.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from oppo import settings as S

REPO = "staring9811-prog/wxb981111-163.com"
BRANCH = "claude/tdd-delivery-contract-fia58p"
APP_SUBDIR = "opportunity-research/app"
# what an update replaces, relative to the app directory
PARTS = ("oppo", "docs", "tests", "packaging", "fixtures", "pyproject.toml", "README.md", "启动.bat", "更新.bat")
SKIP_DIRS = {"__pycache__", "packages", ".venv", "data"}  # fixtures/packages are generated locally

APP_DIR = Path(__file__).resolve().parents[1]


class UpdateError(Exception):
    pass


def zip_url(branch: str = BRANCH) -> str:
    return f"https://github.com/{REPO}/archive/refs/heads/{branch}.zip"


def _log(msg: str) -> None:
    print(msg, flush=True)


def _server_running(port: int) -> bool:
    from oppo.web.server import _busy, _ours

    return _busy(port) and _ours(port)


def _download(url: str, dest: Path) -> None:
    _log(f"下载 {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "oppo-update"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
    except Exception as exc:  # noqa: BLE001 - user-facing
        raise UpdateError(f"下载失败：{exc}。检查网络，或先在浏览器下载 zip 后用 --zip 指定") from exc


def _find_app(root: Path) -> Path:
    for p in root.rglob("pyproject.toml"):
        if (p.parent / "oppo" / "cli.py").exists():
            return p.parent
    raise UpdateError("压缩包里没有找到程序目录（应含 pyproject.toml 和 oppo/cli.py）")


def _hashes(base: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in PARTS:
        p = base / part
        if p.is_file():
            out[part] = hashlib.sha256(p.read_bytes()).hexdigest()
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file() and not (set(f.relative_to(base).parts) & SKIP_DIRS) and f.suffix != ".pyc":
                    out[str(f.relative_to(base)).replace("\\", "/")] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def _copy_part(src: Path, dst: Path) -> None:
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.pyc"))


def run(settings: S.Settings, url: str | None = None, zip_path: Path | None = None, branch: str = BRANCH,
        reinstall: bool | None = None) -> dict[str, Any]:
    if _server_running(settings.port):
        raise UpdateError(f"程序正在运行（端口 {settings.port}），请先关闭运行窗口再更新")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    work = Path(tempfile.mkdtemp(prefix="oppo-update-", dir=str(settings.data_dir / "tmp")
                                 if (settings.data_dir / "tmp").exists() else None))
    try:
        if zip_path is None:
            zip_path = work / "latest.zip"
            _download(url or zip_url(branch), zip_path)
        _log("解压")
        try:
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(work / "src")
        except zipfile.BadZipFile as exc:
            raise UpdateError("下载的不是有效的 zip（私有仓库需要先登录浏览器下载，再用 --zip 指定）") from exc
        new_app = _find_app(work / "src")
        before, after = _hashes(APP_DIR), _hashes(new_app)
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        if not changed:
            _log("已经是最新，没有文件需要更新")
            return {"changed": [], "backup": None, "reinstalled": False}
        backup = settings.data_dir / "update_backup" / stamp
        backup.mkdir(parents=True, exist_ok=True)
        _log(f"备份当前程序文件到 {backup}")
        for part in PARTS:
            if (APP_DIR / part).exists():
                _copy_part(APP_DIR / part, backup / part)
        # fixtures/packages are generated locally and kept in place; everything else in PARTS is replaced
        _log(f"替换 {len(changed)} 个文件")
        for part in PARTS:
            if (new_app / part).exists():
                if part == "fixtures" and (APP_DIR / part).exists():
                    for f in (new_app / part).rglob("*"):
                        if f.is_file() and not (set(f.relative_to(new_app).parts) & SKIP_DIRS):
                            _copy_part(f, APP_DIR / f.relative_to(new_app))
                else:
                    _copy_part(new_app / part, APP_DIR / part)
        deps_changed = before.get("pyproject.toml") != after.get("pyproject.toml")
        reinstalled = False
        if reinstall if reinstall is not None else deps_changed:
            _log("依赖有变化，重新安装（需要联网）")
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-e", str(APP_DIR)], check=True)
            reinstalled = True
        return {"changed": changed, "backup": str(backup), "reinstalled": reinstalled}
    finally:
        shutil.rmtree(work, ignore_errors=True)
