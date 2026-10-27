"""Build the Windows offline package (技术方案 §7.1): embedded Python + pre-installed dependencies + program.

    python packaging/build_offline.py --out dist [--python-version 3.14.x] [--embed-zip path]

Layout of the package (one zip):
    机会判定台/python/         embedded CPython (python.org "embed-amd64" distribution)
    机会判定台/site-packages/  locked dependencies (win_amd64 wheels only)
    机会判定台/app/oppo/       the program
    机会判定台/data/           data directory, kept across upgrades (program and data are separate)
    机会判定台/启动.bat         start the local service and open the browser; a second start only opens the browser
    机会判定台/命令行.bat       a console where `oppo --help` works
    机会判定台/oppo.bat        the `oppo` command
    机会判定台/依赖锁定清单.txt  exact versions inside site-packages

Building needs network access (python.org and PyPI); running the package does not.
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
import tomllib
import urllib.request
import zipfile
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
NAME = "机会判定台"

START_BAT = r"""@echo off
setlocal
chcp 65001 >nul
set "ROOT=%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "OPPO_DATA_DIR=%ROOT%data"
"%ROOT%python\python.exe" -m oppo.cli serve %*
if errorlevel 1 pause
"""

OPPO_BAT = r"""@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if not defined OPPO_DATA_DIR set "OPPO_DATA_DIR=%ROOT%data"
"%ROOT%python\python.exe" -m oppo.cli %*
exit /b %errorlevel%
"""

CONSOLE_BAT = r"""@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PATH=%~dp0;%PATH%"
cmd /k "echo oppo --help"
"""

README = """品类机会判定台 · 离线安装包

1. 解压到任意目录（路径可以有中文）。
2. 双击“启动.bat”：在本机 127.0.0.1:8765 启动服务并自动打开浏览器；再次双击只打开浏览器。
   端口被占用时，在“启动.bat”所在目录打开命令行，执行 set OPPO_PORT=8766 后再运行 启动.bat。
3. 双击“命令行.bat”可使用 oppo 命令（oppo --help 查看全部命令）。
4. 数据保存在 data 目录。升级时只替换 python、site-packages、app 三个目录，data 目录保留。
5. 运行时不访问网络。
"""


def requirements() -> list[str]:
    data = tomllib.loads((APP / "pyproject.toml").read_text(encoding="utf-8"))
    return list(data["project"]["dependencies"])


def fetch_embed(version: str, dest: Path, local: Path | None) -> Path:
    if local:
        return local
    url = f"https://www.python.org/ftp/python/{version}/python-{version}-embed-amd64.zip"
    target = dest / f"python-{version}-embed-amd64.zip"
    print("下载", url, flush=True)
    with urllib.request.urlopen(url, timeout=120) as r, target.open("wb") as f:
        shutil.copyfileobj(r, f)
    return target


def build(out: Path, version: str, embed_zip: Path | None) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    root = out / NAME
    if root.exists():
        shutil.rmtree(root)
    (root / "data").mkdir(parents=True)
    work = out / "_work"
    work.mkdir(exist_ok=True)
    z = fetch_embed(version, work, embed_zip)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(root / "python")
    pth = next((root / "python").glob("python3*._pth"))
    stdlib_zip = next((root / "python").glob("python3*.zip")).name
    pth.write_text("\n".join([stdlib_zip, ".", r"..\site-packages", r"..\app", "import site", ""]), encoding="utf-8")
    reqs = work / "requirements.txt"
    reqs.write_text("\n".join(requirements()) + "\n", encoding="utf-8")
    major_minor = ".".join(version.split(".")[:2])
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-compile", "--target", str(root / "site-packages"),
                    "--platform", "win_amd64", "--python-version", major_minor, "--implementation", "cp",
                    "--only-binary=:all:", "-r", str(reqs)], check=True)
    shutil.copytree(APP / "oppo", root / "app" / "oppo",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"))
    (root / "启动.bat").write_text(START_BAT.replace("\n", "\r\n"), encoding="utf-8")
    (root / "oppo.bat").write_text(OPPO_BAT.replace("\n", "\r\n"), encoding="utf-8")
    (root / "命令行.bat").write_text(CONSOLE_BAT.replace("\n", "\r\n"), encoding="utf-8")
    (root / "使用说明.txt").write_text(README.replace("\n", "\r\n"), encoding="utf-8-sig")
    lock = sorted(p.name[: -len(".dist-info")] for p in (root / "site-packages").glob("*.dist-info"))
    (root / "依赖锁定清单.txt").write_text(f"python=={version}\r\n" + "\r\n".join(
        n.replace("-", "==", 1) if n.count("-") == 1 else n for n in lock) + "\r\n", encoding="utf-8")
    app_version = tomllib.loads((APP / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    target = out / f"{NAME}-{app_version}-win64.zip"
    if target.exists():
        target.unlink()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(root.rglob("*")):
            zf.write(p, p.relative_to(out).as_posix())
    shutil.rmtree(work, ignore_errors=True)
    print("已生成", target, f"{target.stat().st_size / 1e6:.1f} MB", flush=True)
    return target


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(APP / "dist"))
    ap.add_argument("--python-version", default=platform.python_version())
    ap.add_argument("--embed-zip", default=None)
    a = ap.parse_args()
    build(Path(a.out), a.python_version, Path(a.embed_zip) if a.embed_zip else None)


if __name__ == "__main__":
    main()
