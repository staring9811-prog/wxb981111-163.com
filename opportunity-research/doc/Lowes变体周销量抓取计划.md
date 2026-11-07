# Lowe's 变体级周销量抓取计划（交给 Codex 执行）

> 目的：给 Q3 浴室柜报告补 Lowe's 的「5 月 → 10/11 月」趋势。两期必须**同一批商品、同一颗粒度、同一套换算**，否则趋势是假的。
> 写给：执行抓取的 Codex。读者不需要看过之前的对话。

## 1. 背景与为什么要重抓

- 现有 10 月数据（我们这边）：Lowe's「带台面 Best Sellers」前 100 个链接，**每个链接只读了页面默认那一个变体**的销量标签。
- 5 月数据（wen 的旧表 `四平台…AMZ….xlsx` 的 `Lowes_明细` sheet）：18 个系列链接、127 行，**每行是一个尺寸/颜色变体**，有各自的「一周销量」，月销 = 周销 × 4.33。合计 44,732 件/月。
- 两者对不上：例如 Dover（5001952377）5 月 15 个变体合计约 25,000 件/月，我们 10 月只记了默认变体的「5K+ bought last month」= 5,000。
- 已核实：Lowe's 商品页的销量标签是**按变体（omniItemId）各自显示**的，且一个系列的所有变体都列在页面 JSON 的 `variantUIData` 里。所以可以按变体重抓。

## 2. 用什么接口抓

**Bright Data Web Unlocker**（之前抓 Lowe's 商品页就是用它，已验证能拿到完整 HTML）。

- 端点：`https://api.brightdata.com/request`（同步），或 `https://api.brightdata.com/unblocker`（异步，提交后用 `response_id` 取结果）。
- zone：`mcp_unlocker`（仓库默认值）。
- 密钥：**不要写进代码或文件**。claude.ai 云端由环境 Network secrets 注入；本地用环境变量 `BD_TOKEN`，或者 git 忽略的 `tools/评论月度VP追踪器/crawler/.secrets.json`。
- 可直接复用的现成代码：
  - `tools/评论月度VP追踪器/reviewkit/services.py`（第 54 行起）：Bright Data 调用、异步轮询。
  - `solution-v2/trial/大词抓取_Lowes_Wayfair.py`：`K.bd_cached(url, id, 'lowes_pdp', K.lowes_ok, tries=3)` 带缓存和重试，以及 `lowes_ok` 页面有效性判断。
  - `scratchpad/clean/step1_lowes.py`：6 线程并发抓商品页的写法。
- 额度：这个账号之前设过上限 ledger `BD_CAP`，开抓前先看剩余次数。本计划预计 **150–250 次请求**，失败重试另计。
- 经验：Lowe's 偶尔返回 504 或只有 7 字节。每个 URL 最多重试 3 次，并发 ≤ 6，失败的单独记录，不要无限重试。

**不要用**：Apify 的 Lowe's actor（结果里没有 socialProofing 字段），也不要直接 requests 抓（会被反爬挡）。

## 3. 颗粒度

**一行 = 一个变体（omniItemId）× 一次抓取日期。**

- 变体 = 同一系列里的不同尺寸或颜色，各有自己的 omniItemId 和 pdURL。
- 系列 = 页面 `variantUIData` 里能互相跳转的一组变体。同系列不同 omniItemId 在 Best Sellers 榜单里只出现一次。

## 4. 抓哪些链接

### 4.1 必抓：5 月表里的 18 个系列（为了做同口径趋势）

| 5 月链接 ID | 5 月表品牌 | 5 月行数 | 5 月合计月销 | 链接 |
|---|---|---|---|---|
| 5001952377 | Project Source | 15 | 25,028 | https://www.lowes.com/pd/Project-Source-White-24-in-White-Undermount-Single-Sink-Bathroom-Vanity-with-White-Cultured-Marble-Top/5001952377 |
| 5015209375 | allen + roth | 5 | 627 | https://www.lowes.com/pd/allen-roth-Roveland-36-in-Dark-Walnut-Undermount-Single-Sink-Bathroom-Vanity-with-Carrara-Natural-Marble-Top/5015209375 |
| 5015186533 | Style Selections | 10 | 2,447 | https://www.lowes.com/pd/Style-Selections-Cauley-24-in-White-Single-Sink-Bathroom-Vanity-with-White-Cultured-Marble-Top/5015186533 |
| 5014722199 | allen + roth | 6 | 369 | https://www.lowes.com/pd/allen-roth-AR-Austin-24-white-vanity/5014722199 |
| 5015828323 | Project Source | 4 | 88 | https://www.lowes.com/pd/Project-Source-Davies-24-in-White-Single-Sink-Bathroom-Vanity-with-White-Cultured-Marble-Top/5015828323 |
| 5015828324 | Project Source | 4 | 1,321 | https://www.lowes.com/pd/Project-Source-Davies-24-in-White-Single-Sink-Bathroom-Vanity-with-White-Cultured-Marble-Top/5015828324 |
| 5015828325 | Project Source | 5 | 801 | https://www.lowes.com/pd/Project-Source-Davies-24-in-White-Single-Sink-Bathroom-Vanity-with-White-Cultured-Marble-Top/5015828325 |
| 5014610455 | allen + roth | 8 | 176 | https://www.lowes.com/pd/allen-roth-36-in-Light-Oak-Undermount-Single-Sink-Bathroom-Vanity-with-White-Engineered-Stone-Top/5014610455 |
| 5001874195 | Project Source | 6 | 2,447 | https://www.lowes.com/pd/Style-Selections-Euro-24-5-in-White-Bathroom-Vanity-with-Cultured-Marble-Top/5001874195 |
| 5014113023 | Style Selections | 14 | 2,133 | https://www.lowes.com/pd/Style-Selections-Kirkman-48-in-White-Vanity-Combo-with-Cultured-Marble-Top/5014113023 |
| 5014610473 | Style Selections | 17 | 2,882 | https://www.lowes.com/pd/Style-Selections-24-in-Brown-Undermount-Single-Sink-Bathroom-Vanity-with-White-Engineered-Stone-Top/5014610473 |
| 5017604283 | Style Selections | 2 | 866 | https://www.lowes.com/pd/Diamond-NOW-30-in-White-Single-Sink-Bathroom-Vanity-with-White-Cultured-Marble-Top/5017604283 |
| 5013492375 | Style Selections | 4 | 499 | https://www.lowes.com/pd/allen-roth-Rigsby-30-in-White-Undermount-Single-Sink-Bathroom-Vanity-with-White-Engineered-Marble-Top/5013492375 |
| 5015328137 | Style Selections | 11 | 1,300 | https://www.lowes.com/pd/Style-Selections-Dolton-24-in-White-Undermount-Single-Sink-Bathroom-Vanity-with-White-Engineered-Marble-Top/5015328137 |
| 5015350431 | Style Selections | 6 | 1,062 | https://www.lowes.com/pd/Style-Selections-Esterbrook-24-in-Dark-Gray-Single-Sink-Bathroom-Vanity-with-White-Cultured-Marble-Top/5015350431 |
| 5015737813 | Style Selections | 3 | 888 | https://www.lowes.com/pd/Style-Selections-36IN-VANITY/5015737813 |
| 5014516375 | allen + roth | 4 | 499 | https://www.lowes.com/pd/allen-roth-Sandbanks-30-in-Greige-Undermount-Single-Sink-Bathroom-Vanity-with-White-Engineered-Stone-Top/5014516375 |
| 5014520375 | allen + roth | 3 | 1,299 | https://www.lowes.com/pd/allen-roth-Canterbury-30-in-White-Undermount-Single-Sink-Bathroom-Vanity-with-Carrara-Engineered-Marble-Top/5014520375 |

注意：
- 5015828323、5015828324、5015828325 是**同一个 Davies 系列**的不同变体，展开后会重复，按 omniItemId 去重。
- 5 月表的「品牌」列有几处和链接对不上（5001874195 的链接是 Style Selections Euro；5017604283 是 Diamond NOW；5013492375 是 allen + roth Rigsby）。**品牌以本次抓到的页面为准**，5 月表的品牌只用来参考。

### 4.2 建议一起抓：10 月 Best Sellers 前 100 的系列

- 来源：`input/data_v2/渠道VP/浴室柜_2026_渠道VP_20261103.xlsx`，sheet `商品月度明细`。筛选条件：`渠道 == "Lowe's"` 且 `入口 == "Lowes带台面榜"`，取 `商品ID`（共 100 个）。
- 目的：把 10 月口径也改成「系列 = 所有变体之和」，修正多尺寸系列被少算的问题。
- 先跑 4.1，确认方法可行，再跑这一批。和 4.1 重叠的系列不要重复抓。

## 5. 抓取步骤

### 步骤 0：试点，只跑 Dover（5001952377），约 10 分钟

1. 抓系列页，展开所有变体，再逐个抓变体页。
2. 把各变体的周销量标签和 5 月表里 Dover 的 15 行对照（5 月表 LOW-001 至 LOW-015：尺寸 24/30/36/48/60，价格 159/219/259/499/599）。
3. 回答两个问题，写进试点报告：
   - 页面标签是否按变体各不相同？
   - 5 月表里的 1200、15、2 这类数，能否对应到页面标签？例如 "1.2K+ bought last week"、"15 bought last week"。如果都对应不上，说明 5 月数字来自别的工具，**停下，报告给 wen，不要继续全量抓**。

### 步骤 1：系列页 → 变体清单

- 抓每个系列链接的 HTML，在页面 JSON 里解析 `"variantUIData":[...]`：
  - 每个维度（`name`，如 `Manufacturer Color/Finish`、`Width` 等）下有 `values[]`。
  - 每个 value 有 `value`（如 "Light Gray"）、`omniItemId`、`pdURL`，以及 `ids[]`。`ids[]` 里是该取值和其他维度组合出的 omniItemId/pdURL。
  - **把所有出现过的 omniItemId 和对应 pdURL 去重收集**，这些就是该系列的全部变体。
- 当前页本身的 omniItemId（URL 末尾数字）也算一个变体。
- 输出 `variants.csv`，字段：family_id（输入链接 ID）、omni_item_id、pd_url、color（value 文本，能取到就填）。

### 步骤 2：变体页 → 销量标签和属性

逐个抓 `https://www.lowes.com` + pdURL，解析：

| 字段 | 从页面哪里取 |
|---|---|
| week_msg | `"socialProofingMessages":{ ... "socialProofingMessage":"…" }` |
| month_msg | 同一对象里的 `"socialProofingMessageLastMonth"` |
| pro_week_msg / pro_month_msg | `socialProofingMessageProLastWeek` / `ProLastMonth`（只记录，不计入销量） |
| price | `"sellingPrice": 数字` |
| width_in | 规格里的宽度，或标题/URL 里的 "24-in" |
| color | 规格 `Manufacturer Color/Finish`，或步骤 1 的 value |
| rating、review_count | 页面评分和评论数 |
| title、brand | 页面标题和品牌 |

页面上没有 `socialProofingMessages` 的变体，记为「无标签」，不要猜。

### 步骤 3：标签换算成月销（和 10 月现有口径一致）

- 标签示例：`"1K+ bought last week"`、`"90+ bought last week"`、`"40 bought last week"`、`"5K+ bought last month"`、`"1K+ views last week"`、`"In 100+ carts last week"`。
- 数值：取数字，`K` ×1000，去掉 `+`，**取下限**。
- **主口径（和 5 月表对齐）**：月销 = 上周购买 × 4.33。
- **辅助口径（和我们 10 月对齐）**：max(上周购买 × 4.3, 上月购买下限)。两列都输出。
- `Pros bought` 不计入。`views`、`carts` 不当销量：只记原文，月销留空，单独标「仅浏览/加购」。
- 不要用 BSR 曲线给变体补数。曲线只在系列层面、且整个系列都没有标签时才用，而且要另外标注。

### 步骤 4：输出

1. `lowes_variant_<抓取日期>.csv`：每行一个变体，含步骤 1、2、3 的全部字段，加 fetch_date、http_status、原始标签文本。
2. `lowes_family_<抓取日期>.csv`：按 family 汇总，字段：变体数、有标签变体数、周销合计、月销合计（两种口径各一列）、仅浏览变体数。
3. `lowes_may_vs_now.csv`：5 月与本次对照，规则见第 6 节。
4. 原始 HTML 缓存到 `input/data_v2/渠道关键词/大词/raw/lowes_pdp/`，文件名用 omniItemId，复跑时直接读缓存。

**这些数据文件不要提交进 git**（仓库规定业务数据不入库），只提交脚本。

## 6. 和 5 月怎么对

5 月表没有变体 ID，按以下顺序匹配：

1. 同系列内按 **尺寸 + 颜色** 匹配。
2. 颜色缺失时按 **尺寸 + 价格** 匹配，允许 ±10%。
3. 一对多或多对一的，在该尺寸内合并成一个对照单元。
4. 对不上的单列出来，不强配。

趋势只用「两期都对上的变体」算：同口径月销合计的变化率，再按系列汇总。每个系列都写上「对上 x / 5 月 y 行 / 本次 z 个变体」。

## 7. 验收检查（交付前自查）

- [ ] Dover 试点结论已写明，并附 3 个变体的原始标签截图或原文。
- [ ] 18 个系列全部有结果，失败的单列并写原因（504、页面无变体数据等）。
- [ ] 变体按 omniItemId 去重后的数量；Davies 三个 ID 只算一个系列。
- [ ] 每个变体都有原始标签原文。随机抽 5 个变体，打开页面人工核对。
- [ ] 月销合计按两种口径分别给出，和 5 月合计 44,732 并列。
- [ ] 消耗了多少次 Bright Data 请求，剩余额度多少。

## 8. 交回给 Claude 时带上

`lowes_variant_*.csv`、`lowes_family_*.csv`、`lowes_may_vs_now.csv`、试点结论（一段话）、请求消耗数。拿到后由 Claude 并入报告的 Lowe's 趋势（5 月、本次两个点），并修正 10 月多尺寸系列被少算的问题。
