# 外部服务登记表

仓库里只登记“有什么服务、怎么调用、花多少钱”，**不存任何密钥**。
密钥一律放在云环境的 **Network secrets** 里，由代理在请求时自动注入；代码里的 Authorization 只写占位值（如 `Bearer dummy`）。
（Mem0 规则同样禁止把 API key 写进记忆。）

## 新增服务的流程

1. 用户在服务后台生成 API key（尽量用只读或权限最小的 key）。
2. 用户在云环境 → Edit → Network secrets → 添加秘密：
   - Allowed websites：服务的 API 域名
   - Path prefixes：只放需要的路径（不要整站放开）
   - Header name / Prefix / Value：按服务文档，通常 `Authorization` / `Bearer` / key
3. 在本表加一节，写清：用途、域名与路径、计费、已验证的调用方式、代码位置。
4. 如果 key 曾经出现在聊天里，用完后在服务后台作废并换新 key。

---

## Bright Data（BD）

| 项 | 内容 |
|---|---|
| 用途 | 抓取被封锁的页面（Lowe's、Wayfair 的列表页、商品页、评论页） |
| 账号 | customer `hl_87b86747` |
| Zone | `mcp_unlocker`（Web Unlocker API），IP Allowlist 需包含云端出口 IP（160.79.106.x） |
| 计费 | $1.50 / 1000 次成功请求；每个平台预算上限 $10（`crawler/data/bd_ledger.json` 记账） |
| Network secrets | `api.brightdata.com` 路径 `/request`（同步）、`/unblocker/`（异步）；B1 需再加 `/datasets/` |
| 代码 | `crawler/vanity_crawler/bd.py`（`submit` / `result` / `fetch` / `fetch_many`） |

已验证：
- 异步 `/unblocker/req` + `/unblocker/get_result` 可用；单页 1—7 分钟。同步 `/request` 超过约 30 秒会被云端代理切断，不用。
- POST 请求和自定义 header 可透传（httpbin 验证）。
- Wayfair 的 `/federation/graphql`、`/graphql` 经 BD 一律 400/502，走不通。

## Apify

| 项 | 内容 |
|---|---|
| 用途 | 现成爬虫（Actor）。目前用于 Wayfair 评论翻页（商品页只内嵌前 100 条） |
| 账号 | `kissproof_ghost`，FREE 计划，每月 $5 额度 |
| API | `https://api.apify.com/v2`，认证 `Authorization: Bearer <token>` |
| Network secrets | 建议添加：`api.apify.com`，路径 `/v2/`，Authorization / Bearer / token（之后新会话无需再贴 token） |
| 代码 | `crawler/vanity_crawler/apify.py`（`run_actor`）；token 从 Network secrets 注入，或本会话环境变量 `APIFY_TOKEN` |

已验证的 Actor：

| Actor | 用法 | 结果 | 价格 |
|---|---|---|---|
| `sian.agency/wayfair-data-scraper` | `{"operation":"productReviews","sku":"W100454815","reviewSort":"date_descending","maxPages":N}` | 每页 10 条，按最新排序；字段含 `badge`（Verified Purchase / Wayfair Professional / Incentivized Review）、`date`(MM/DD/YYYY)、`rating`、`body`、`review_id` | 启动 $0.01 + 每条评论 $0.0105（约 $10.5 / 1000 条） |

其他候选（未测）：`scraped/wayfair-reviews-scraper`（只收 productUrl）、`khadinakbar/wayfair-scraper`、`memo23/wayfair-scraper`。
