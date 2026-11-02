# 三平台浴室柜评论采集 —— 需求整理与对齐清单（v0，2026-11-02）

来源：`三平台浴室柜_爬取Skills与任务交接包_20261101.zip`（01_本次爬取目标与接手说明.md、retail-product-review-research Skill、本次核验记录、历史代码）。
状态：**对齐阶段，未正式抓取**。下面“待确认”项确认后再定表头、跑小样、做软件。

## 1. 已确认的范围（不再重复问）

| 平台 | 入口 | 数量 / 排名口径 | 变体 |
|---|---|---|---|
| Lowe's 带台面 | Best Sellers 榜 4294684460 | 官方 BSR 1—100（offset 0/24/48/72/96，每页滚动补齐 24 条） | 已上榜颜色/尺寸各自保留，不展开榜外变体 |
| Lowe's 无台面 | Best Sellers 榜 4294684459 | 官方 BSR 1—100 | 同上；两榜分开交付、不跨榜去重 |
| Wayfair 主类目 | bathroom-vanities-c527058 | Recommended 排序前 200 个有效自然商品主链接（去广告、去非目标、按主链接去重后顺延补足） | 不展开，保留列表选中配置和 piid |
| Wayfair 无台面 | vanity-bases-c527056 | 前 50 个有效自然商品主链接 | 同上 |
| HDP 带台面 / 无台面 | N-5yc1vZcfw5 / N-5yc1vZcfv9 | Top Sellers 自然顺序（不称 BSR）——**数量待定** | **展开规则待定** |

- 品类：浴室柜整柜，有盆/无盆都要；独立台面、台盆、镜柜、侧柜、配件排除并留排除原因。
- 采什么：2026 年原始评论（日期原值、原文、单条评分、VP 原始证据、激励/Pro、转载/来源、原评论 ID、商品映射、覆盖状态），按 VP / non_VP / unknown 计数。
- 不做：销量预估、属性打标、痛点分析。
- 页面累计 Reviews 数只做辅助校验，不能代替 2026 年 VP/非VP 计数。

## 2. 技术链路（基于交接包判断）

| 平台 | 列表 | 评论 | 关键依赖 |
|---|---|---|---|
| Lowe's | 榜单页（需渲染/滚动，或抓页面内 JSON） | Bazaarvoice API（公开站点 passkey，可从页面取） | 列表页大概率需 BD Web Unlocker/代理 |
| HDP | 类目页 Top Sellers（Nao 分页，带台面深页曾报错） | Bazaarvoice API | 同上 |
| Wayfair | 类目页 curpage 分页 | GraphQL `reviewsListPossibleMPLDataByNodeIdQuery`（需现抓当前 hash/headers，旧 hash 不可直接用） | 直连 PDP 曾 429，**必须走 BD** |

云端环境探测（2026-11-02，仅首页）：三站首页均返回 200；类目页、评论接口未测，不代表可直连批量抓取。

## 3. 待你确认的口径

1. **时间截止**：建议 2026-01-01 至 2026-10-31（10 个完整月）为正式口径；11 月 1 日至抓取日单列“未完整月”。
2. **HDP 数量**：建议两入口各取 Top Sellers 自然前 100（去 Sponsored、去非目标后顺延），与 Lowe's 对齐。
3. **HDP 变体**：建议不展开“+N more”，只保留卡片当前展示的规格（排名不复制给展开变体）。
4. **地区 / 邮编**：建议三平台统一固定一个美国邮编并记录（如 90013 洛杉矶），否则按平台各自自动地区记录。
5. **Wayfair 只有 Pro、无 VP 标签**：在拿到当前 GraphQL 原始返回前记 unknown；若原始结构证明“badge 字段存在但不是 VP”即为未验证，再改判 non_VP（会先给你看证据）。
6. **软件形态**：见第 5 节。

## 4. 需要你提供的东西

| 项 | 用途 | 怎么给 |
|---|---|---|
| Bright Data API Token | Web Unlocker 调用（历史代码读 `BD_TOKEN`） | 在云环境设置里加环境变量，**不要贴到聊天里** |
| BD Zone 名称 | 历史用 `mcp_unlocker`（读 `BD_ZONE`） | 同上，或直接告诉我名字（不是密钥） |
| （可选）BD 代理账号 | 历史代码也用过 `brd.superproxy.io:44445`（`BD_PROXY_USER` / `BD_PROXY_PASS`） | 同上 |
| BD 预算上限 | 控制请求量，先小样计费再全量 | 告诉我金额或请求数上限 |
| 软件运行位置 | 云端 / 你的 Windows 电脑 | 告诉我 |

Bazaarvoice passkey 是站点公开参数，我可以自己从页面取，不需要你提供。

## 5. 软件方案（建议）

Python 单一项目，一份任务配置驱动，可断点续采：

```
crawler/
  config/task.yaml          # 平台、入口、数量、时间窗、邮编、预算
  vanity_crawler/
    transport.py            # 直连 / BD Unlocker / BD 代理，统一限速、重试、计费账本
    lists/{lowes,hdp,wayfair}.py     # 列表/榜单采集 → 商品表
    reviews/{bazaarvoice,wayfair}.py # 评论分页采集，raw 原始响应落盘
    normalize.py            # VP/non_VP/unknown、转载、去重、指纹
    coverage.py             # 覆盖/缺页/日期边界校验
    export.py               # Excel（带下拉）+ CSV/JSON
  app.py                    # 网页界面：填配置 → 一键运行 → 看进度 → 下载 Excel
```

交付表（表头在小样后按 table-schema-confirmation 逐列给你确认）：商品表、评论明细、商品-评论映射、按月 VP/non_VP/unknown 计数、覆盖与异常。

## 6. 下一步

1. 你回复第 3、4 节 → 2. 配好 BD 后我做每平台 1 个商品的小样（列表 + 评论原始返回） → 3. 给你逐列表头确认 → 4. 正式采集并做成软件。

## 7. 对齐进展（2026-11-02 更新，新会话从这里接着做）

- 运行位置：**云端**。
- BD：已在云环境 Network secrets 配置 `api.brightdata.com` + 路径 `/request`，Authorization: Bearer（代理自动注入，代码不读 BD_TOKEN）。Zone=`mcp_unlocker`（Web Unlocker API，Active，免费额度 5000）。本会话测试返回 401 “Auth method is not supported”，需新会话复测；仍 401 则核对 Token 是否为 Account settings 里的 API key。
- 云端探测：api.brightdata.com 可达；brd.superproxy.io 代理端口不可达（只走 Unlocker API）；HDP 类目页直连 200、含完整商品 JSON，列表页可能无需 BD。
- 预算：**每平台上限 10 美元**，分平台记账，接近上限即停并标“预算上限”。
- HDP：无公开逐商品 BSR，用类目页 `sortby=topsellers`（降序）自然顺序；卡片有 Best Seller 徽章（只有是/否）。建议加“平台徽章”列，待确认。
- 表头：见 SCHEMA.md v2（2 个 sheet，含打标用的标题/型号/卖点/描述/规格参数/图片），**待用户最终确认**。
- 仍待确认：时间窗（建议 1—10 月完整月 + 11 月单列）、HDP 各前 100 且不展开、邮编 90013。

## 8. 新会话复测（2026-11-02，分支 claude/sharp-feynman-6kkqf3）

- BD 复测仍 401 “Auth method is not supported”（带/不带 Authorization 头结果相同），说明新会话已生效、问题在密钥本身或 Header 格式。
- 直连探测（无 BD）：HDP 带台面类目页 200（约 1.5MB，可直连）；Lowe's 榜单页 403；Wayfair 类目页 429。**Lowe's、Wayfair 必须等 BD 打通**。
- 待用户核对 Network secrets：Value 只填 Account settings → API keys 里的 API key；认证方式选 Bearer 时 Value 不要再写 “Bearer ” 前缀（避免变成 “Bearer Bearer …”）；不要填 zone 密码或 Proxies 页的用户名/密码。改完开新会话复测。
- 第 7 节 4 项口径仍待确认。
