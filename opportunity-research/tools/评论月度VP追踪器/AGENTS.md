# AGENTS.md — 给 Codex / Claude 等编码助手的仓库说明

## 评论月度 VP 追踪器（）

用户说类似下面的话时，就是要用这个工具：
- “用评论追踪器跑一下 <品类> <年份>”、“拉 Lowe's / HDP / Wayfair 的 VP 非VP 月度数据”
- “<品类> 三个平台关键词 <词> 各前 100”、“Lowe's BSR 榜单前 50 + Wayfair 类目页前 200”

详细说明见 `README.md`，服务与价格见 `services.md`。

### 标准流程（必须按顺序）

1. **新建项目 + 采列表 + 评估**（只花很少的钱，不采评论）：
   ```bash
   python3 app.py new <项目名> --category "<品类>" --keyword "<关键词>" --top 100
   ```
   - 某个平台用网址（类目页 / Lowe's BSR 榜单）时用 `--lowes URL --hdp URL --wayfair URL`，也可以填关键词；只跑部分平台就只给对应参数。
   - 常用选项：`--start 2026-01-01`、`--full-end 2026-10-31`、`--dedupe-parent`（父体去重）、`--dedupe-across`（跨入口去重）、
     `--keep-sponsored`（不排除广告位）、`--include/--exclude/--keep "词1,词2"`（品类筛选）、`--preset bathroom_vanity`、
     `--low-threshold 20 --low-mode total_only|skip|split`（评论少的商品）、`--budget 10`（每平台每项服务上限美元）、
     `--from <已有项目>`（以已有项目为模板）。
   - 用户没说的项用默认值，并在回复里写明用了哪些默认值。
2. **把评估结果告诉用户**（各平台商品数、预计评论数、费用、耗时），**等用户确认后**再进行第 3 步。
   例外：用户事先明确说了“直接跑”“预算 X 以内直接跑”且评估总费用不超过该预算。
3. **采集 + 导出**：
   ```bash
   python3 app.py run <项目名> collect
   python3 app.py run <项目名> export
   ```
   采集可能要 1—数小时（Lowe's/Wayfair 经 BD 和 Apify），放后台运行；每一步可断点续跑，中断后重跑同一命令即可。
4. **交付**：Excel 在 `data/projects/<项目名>/exports/`，每个平台一个文件。
   回复里给出：每个入口完整月的 VP / 非VP 合计和 VP 占比、状态为「部分/失败/未采集」的商品数和原因、实际花费（`ledger.json`）。

想用网页界面时：`python3 app.py`，浏览器打开 http://localhost:8765。

### 规则

- **密钥不进仓库、不写进聊天回复、不写进记忆。** 云端由 Network secrets 注入；本机用环境变量 `BD_TOKEN`、`APIFY_TOKEN`
  或 `.secrets.json`（已 gitignore）。缺密钥时告诉用户去配置，不要编造结果。
- 不要提交 `data/`（采集数据和 Excel）。项目设置 `projects/*.json` 可以提交。
- Wayfair VP 口径：只有 “Verified Purchase” 徽章计 VP，其余徽章计非VP（2026-11-03 用户确认）。
- 不要调用各网站的内部数据接口去绕过访问限制；只用公开页面 + 已登记的服务（Bright Data、Apify）。
- 新增外部服务时登记到 `services.md`（用途、域名路径、价格、调用方式），密钥让用户放到 Network secrets 或本机环境变量。
