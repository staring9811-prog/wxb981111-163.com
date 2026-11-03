# 评论月度 VP 追踪器（reviewkit）

任意品类，按月统计 Home Depot / Lowe's / Wayfair 商品评论的 **VP（Verified Purchase）/ 非VP** 数量，出 Excel。

## 怎么用

```bash
cd crawler
python3 app.py            # 浏览器打开 http://localhost:8765
```

页面上：选项目（或「复制为新项目」改品类）→ 勾选设置 → 依次点 **① 采集列表 → ② 评估时间和费用 → ③ 开始采集评论 → ④ 导出 Excel**。
每一步都能断点续跑，已采过的不会重复花钱。也可以命令行：`python3 app.py run <项目名> lists|estimate|collect|export|all`。

依赖：Python 3.10+、`pip install openpyxl`。

## 设置项（全部可勾选）

| 需求 | 设置 | 说明 |
|---|---|---|
| 有 BSR 的渠道取前 N | 入口「落地页类型 = BSR/热销榜」+「前N」 | Lowe's 用 Best Sellers 排序 |
| 没有 BSR 的渠道 | 「类目落地页」填类目网址，或「关键词落地页」填关键词 | Home Depot 用 Top Sellers 排序；Wayfair 用 Recommended 默认排序 |
| 排除广告位 | 每个入口「排除广告」 | 跳过 Sponsored 并顺延补足 N |
| 父体去重 | 每个入口「父体去重」 | 同一款不同颜色/尺寸只算一个：Lowe's 按父体 ID，HDP 按共享评论判断，Wayfair 列表本身按款 |
| 跨入口去重 | 「跨入口去重」 | 同一商品/父体已被前面的入口选中时，后面的入口跳过并顺延 |
| 只留目标品类 | 内置规则（如浴室柜）+ 必含词 / 排除词 / 保留词 | 被排除的商品在 Excel「商品」表里留排除原因 |
| 评论少的商品 | 阈值 + 三选一：照常区分 VP / 只计月度合计 / 不采集 | 按商品页「累计评论数」判断 |
| 时间窗 | 起始日期、最后一个完整月月底、是否单列当月未完整数据 | |
| 预算 | 每个平台 BD、Apify 上限（美元） | 达到即停，已采数据保留 |
| 时间与费用评估 | ② 按钮 | 用列表里的真实商品数和评论数估算，给出区间 |

## Excel（每个平台一个文件）

1. **月度趋势**：一行一个商品，每月 VP / 非VP / 合计 + 完整月 VP 占比
2. **入口月度汇总**：每个入口每月合计，按评论 ID 去重（同系列共享评论不重复算）
3. **商品**：排名、徽章、标题、卖点、描述、规格、图片、价格、评分、纳入/排除原因、采集状态
4. **评论明细**（可关）：每条评论的日期、VP 状态和证据（徽章原文）

VP 口径：HDP、Lowe's 用评论自带的 verifiedPurchaser 标记；Wayfair 每条评论只有一个徽章，**只有 "Verified Purchase" 计 VP**，其余（Incentivized / Wayfair Professional 等）计非VP。

## 数据从哪来、花多少钱

| 平台 | 列表/详情 | 评论 | 费用 |
|---|---|---|---|
| Home Depot | 直连 | 直连评论页（照片评论在前，最多约 17 页） | 免费 |
| Lowe's | Bright Data Web Unlocker（云端 IP 被封） | Apify `automation-lab/lowes-product-reviews-scraper` | BD $1.5/千次；评论约 $0.1/千条 |
| Wayfair | Bright Data（列表） | Apify `abotapi/wayfair-scraper`（含详情），按 100→300→1000 条分轮取 | 评论约 $0.5/千条 |

服务登记见 `../services/README.md`。

## 密钥

- claude.ai 云端：在环境 Network secrets 里配置 `api.brightdata.com`（路径 `/unblocker/`）和 `api.apify.com`（路径 `/v2/`），代码不需要密钥。
- 本机运行：设环境变量 `BD_TOKEN`、`APIFY_TOKEN`，或建 `crawler/.secrets.json`：`{"BD_TOKEN": "...", "APIFY_TOKEN": "..."}`（已在 .gitignore，不会提交）。
- Bright Data 的 zone（默认 `mcp_unlocker`）需要在 IP Allowlist 放行运行机器的出口 IP。

## 已知限制

- HDP 评论页最多翻约 17 页；时间窗内评论特别多的商品会标「部分」。
- Lowe's Apify 每个商品最多取 1000 条（新、旧各 500）；超过的标「部分」。
- Wayfair Apify 每个商品最多 1000 条；超过的标「部分」。
- 通过 BD 的页面每页 1—7 分钟；BD 对 Lowe's 有限速，列表/详情页并发不宜超过 6。
- 评估用经验系数（每月约 2% 的累计评论落在时间窗内），实际以采集结果为准；跑完后可按真实数据调整 `reviewkit/estimate.py` 的 `CAL`。

## 目录

```
crawler/
  app.py, app_page.html      网页界面 + 命令行入口
  reviewkit/                 采集核心：hdp.py lowes.py wayfair.py（三个平台）, pipeline.py, estimate.py, export.py, classify.py, services.py
  projects/<项目>.json        项目设置（不含密钥，可提交）
  data/projects/<项目>/       采集缓存、日志、导出 Excel（不提交）
  vanity_crawler/, run_*.py  浴室柜项目最初的脚本（已被 reviewkit 取代，保留作参考）
```
