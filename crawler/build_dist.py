"""Build a self-contained zip for local use (Windows / Mac). No secrets, no collected data.

  python3 build_dist.py            → data/dist/评论月度VP追踪器_<date>.zip
"""
import os, re, time, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "评论月度VP追踪器"
OUT = os.path.join(HERE, "data", "dist", f"{NAME}_{time.strftime('%Y%m%d')}.zip")

START_BAT = r"""@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo 没找到 Python。请先安装 Python 3.10 或更新版本：https://www.python.org/downloads/
  echo 安装时勾选 "Add python.exe to PATH"，装好后再双击本文件。
  pause
  exit /b 1
)
python -c "import openpyxl" 2>nul || python -m pip install -q openpyxl
python app.py
pause
"""

START_MAC = """#!/bin/bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "没找到 python3，请先安装 Python 3.10+：https://www.python.org/downloads/"; read -n 1; exit 1
fi
python3 -c "import openpyxl" 2>/dev/null || python3 -m pip install -q --user openpyxl
python3 app.py
"""

QUICK = """评论月度 VP 追踪器 — 快速上手
====================================

一、第一次使用（只做一次）
1. 安装 Python 3.10 或更新版本（https://www.python.org/downloads/ ，Windows 安装时勾选 "Add python.exe to PATH"）。
2. 配置密钥：把 secrets.example.json 复制一份，改名为 .secrets.json，填入
     BD_TOKEN    = Bright Data 后台 Account settings → API keys 里的 API key
     APIFY_TOKEN = Apify 后台 Settings → API & Integrations 里的 API token
   （.secrets.json 只存在你电脑上，不要发给别人、不要传到网上。）
3. Bright Data：在 zone（默认 mcp_unlocker）的 IP Allowlist 里加上你电脑的公网 IP，
   或者设为允许所有 IP。不加的话 Lowe's / Wayfair 会失败（Home Depot 不受影响）。
   如果你的 zone 名或账号 ID 不同，在项目设置文件 projects/<项目>.json 的 services.brightdata 里改。

二、每次使用
- Windows：双击「启动.bat」；Mac：双击「启动.command」（第一次如被拦截：右键 → 打开）。
- 浏览器会自动打开 http://localhost:8765 。
- 选项目或「复制为新项目」→ 勾选设置 → 依次点
    ① 采集列表 → ② 评估时间和费用 → ③ 开始采集评论 → ④ 导出 Excel
- Excel 在「导出文件」里点击下载，也保存在 data/projects/<项目名>/exports/ 。
- 关闭黑色命令行窗口即停止。采集中途关掉也没关系，下次再点同一步会接着跑，已采过的不重复花钱。

三、费用（以实际为准）
- Home Depot：免费（直连）。
- Lowe's / Wayfair 列表页：Bright Data，约 $1.5 / 1000 次请求。
- 评论：Apify，Lowe's 约 $0.1 / 1000 条，Wayfair 约 $0.5 / 1000 条。
- 每个平台都有预算上限（页面第 5 项），到了自动停。

四、让 Codex / Claude 帮你跑
把整个文件夹放进它的工作目录，对它说：
  “按 AGENTS.md 用评论追踪器跑 <品类>，三个平台关键词 <词> 各前 100”
它会先给你时间和费用评估，你确认后再采集。

详细说明见 README.md。
"""

SECRETS_EXAMPLE = '{\n  "BD_TOKEN": "在这里填 Bright Data API key",\n  "APIFY_TOKEN": "在这里填 Apify API token"\n}\n'


def agents_md():
    s = open(os.path.join(HERE, "..", "AGENTS.md"), encoding="utf-8").read()
    s = s.replace("   cd crawler\n", "").replace("`crawler/README.md`", "`README.md`")
    s = s.replace("服务与价格见 `services/README.md`。", "服务与价格见 `services.md`。")
    s = s.replace("crawler/", "").replace("`services/README.md`", "`services.md`")
    return s


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    files = ["app.py", "app_page.html"] + \
        [os.path.join("reviewkit", f) for f in sorted(os.listdir(os.path.join(HERE, "reviewkit"))) if f.endswith(".py")] + \
        [os.path.join("projects", f) for f in sorted(os.listdir(os.path.join(HERE, "projects"))) if f.endswith(".json") and not f.startswith("_")]
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(os.path.join(HERE, f), f"{NAME}/{f}")
        z.write(os.path.join(HERE, "..", "services", "README.md"), f"{NAME}/services.md")
        z.writestr(f"{NAME}/AGENTS.md", agents_md())
        readme = open(os.path.join(HERE, "README.md"), encoding="utf-8").read()
        readme = readme.replace("cd crawler\n", "").replace("`../services/README.md`", "`services.md`").replace("crawler/", "")
        z.writestr(f"{NAME}/README.md", readme)
        z.writestr(f"{NAME}/快速上手.txt", QUICK.replace("\n", "\r\n"))
        z.writestr(f"{NAME}/secrets.example.json", SECRETS_EXAMPLE)
        z.writestr(f"{NAME}/requirements.txt", "openpyxl>=3.1\n")
        z.writestr(f"{NAME}/启动.bat", START_BAT.replace("\n", "\r\n").encode("utf-8"))
        info = zipfile.ZipInfo(f"{NAME}/启动.command")
        info.external_attr = 0o755 << 16
        z.writestr(info, START_MAC)
    # guard: never ship a key
    with zipfile.ZipFile(OUT) as z:
        for n in z.namelist():
            body = z.read(n).decode("utf-8", "ignore")
            assert not re.search(r"apify_api_[A-Za-z0-9]{10,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", body), n
    print(OUT, os.path.getsize(OUT), "bytes,", len(files) + 7, "files")


if __name__ == "__main__":
    main()
