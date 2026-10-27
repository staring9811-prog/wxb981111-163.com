# 品类机会判定台（第一期）

本机运行的网页应用 + 命令行，网页与命令行调用同一套服务函数。技术栈与版本见 `pyproject.toml` 和 `../output/技术方案.md`。

## Windows 离线安装包（给使用者）

1. 构建（需联网，任意装有 Python 3.14 的电脑均可）：`python packaging/build_offline.py --out dist`，得到 `dist/机会判定台-1.0.0-win64.zip`；把它解压到使用者电脑的任意目录。
2. 双击 `启动.bat`：在 `http://127.0.0.1:8765/` 启动并自动打开浏览器；再次双击只打开浏览器。
3. 双击 `命令行.bat` 使用 `oppo` 命令（`oppo --help`）。数据在 `data\`，升级时保留。运行时不联网。

## 开发环境

```bash
cd app
uv venv --python 3.14 && uv pip install -e ".[dev]"
.venv/bin/python -m fixtures.build_samples          # 生成样例包（H1-A、H1-B、X1 与各变体）到 fixtures/packages
.venv/bin/oppo serve                                  # 本机服务 127.0.0.1:8765
.venv/bin/oppo --help                                 # 命令行
```

试用：在“数据包”页粘贴 `fixtures/packages/H1-A` 的路径导入，然后按工作台的 8 步走完一个月。

## 更新到最新版本

关闭运行窗口后，在 `app` 目录双击 `更新.bat`（或运行 `.venv\Scripts\python -m oppo.cli update`）：从 GitHub 下载分支最新代码，替换 `oppo/`、`docs/`、`tests/`、`packaging/`、`fixtures/`（生成的样例包不动）、`pyproject.toml`；`data/` 和 `.venv/` 不动，被替换的旧文件先备份到 `data/update_backup/<时间>/`。依赖有变化时自动重装。更新后双击 `启动.bat` 即可，数据库在启动时自动升级。没有网络时先在浏览器下载分支 zip，再运行 `oppo update --zip <文件>`。

## Codex 接入（数据审核）

程序启动后在本机提供 `http://127.0.0.1:8765/api/v1`，Codex 等工具可以读数据包、提交调整提议；提议在「数据审核」页由人确认、改值或驳回后才参与体检和计算，导入的数据包本身不变。令牌在 `data/api_token.txt`（`oppo api-token` 查看），接口与命令行 `oppo adjust` 的说明见 `docs/Codex接入.md`。

## 测试与验收

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest            # 单元、服务层、浏览器端到端（Playwright + 本机 Chromium）
.venv/bin/python -m fixtures.build_scale              # S-规模样例包（约 66.8 万行，不入库）
python -m devtools.visual_states <目录>                # 视觉验收用的数据状态
python -m devtools.capture_visual <目录>               # 真实页面截图 → ../output/tests/visual/
```

- `packaging/build_offline.py`：构建 Windows 离线安装包（嵌入式 Python + 预装依赖）。
- `packaging/win_acceptance.py`：在一台 Windows x64 电脑上执行 SMOKE-03、RULE-05 与 FLOW-17 的浏览器部分（`python packaging/win_acceptance.py --zip <安装包> --fixtures fixtures/packages --out results`）；本期结果与运行环境记录在 `../output/tests/windows/`。
- 验收结果：`../output/tests/TDD验收结果.md`，校验：`python3 ../tools/check_contract.py --result ../output`。
