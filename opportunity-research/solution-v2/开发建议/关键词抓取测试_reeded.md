# 关键词抓取测试：reeded（Home Depot / Lowe's / Wayfair）

> 脚本 `solution-v2/trial/关键词抓取测试_reeded.py`（`python 关键词抓取测试_reeded.py 分析` 打印本页所有数字）；原始缓存 `input/data_v2/渠道关键词/reeded/`（不入库）。采集 2026-11-04。
> 目的：验证 wen 提出的"按关键词抓前 300 条产品"能不能支撑"同尺寸段 × 拆装 × 形态"框内的分析。

## 结论（先看）

| 平台 | 关键词 "reeded bathroom vanity" 抓到什么 | 能否按"尺寸段 × 拆装 × 形态"分析 reeded | 主要原因 |
| :--- | :--- | :--- | :--- |
| Home Depot | 搜索几乎不认 reeded：页面总数 60,851（等于整个浴室柜类目），前 300 条只有 13 条标题含 reeded / fluted | **框能定**（商品页规格补齐后尺寸段 97%、装 98%、形态 98%），**但 reeded 抓不到**；要分析 reeded 得用类目 Top Sellers + 打标，而不是关键词 | 搜索相关度噪声极大；每个尺寸 / 颜色是独立商品页，评论家族共享、每条评论带商品页 ID，可拆到尺寸 |
| Lowe's | 搜索很严格：结果只有 40 条（36 条自然位），翻完即止，远不到 300；36 条里 34 条标题含 reeded / fluted，但 **34 条里 0 条有评论**（31 条是第三方 Marketplace 新品） | **不能**：没有销量信号（评论数 0），样本只有 36 条 | 结果太少 + 几乎全是零评论新品；字段上其实可做：商品页有全部变体（尺寸 / 颜色）和规格（宽、拆装、安装方式），评论页每条评论带 `productId`（变体 ID），可拆到尺寸 |
| Wayfair | 搜索宽松：页面总数 36,000，前 300 条自然位里 107 条标题含 reeded / fluted，且越往后越多（1–50 名 11 条、201–300 名 35 条） | **只能部分**：尺寸段（标题）80%，但拆装只有 8% 能判断，形态 47%；23% 的 listing 一个页面挂多个尺寸，标题尺寸只是当前选项 | 标题不写装；多尺寸 listing 的评论数是整个 listing 合计；**评论条目带 `choices`（如 Overall Width = 48"），可拆到尺寸**，但商品页只内嵌 5 条，完整评论要另走 Apify / GraphQL |

**Bright Data 实际用量：提交 36 次，成功 32 次（3 次目标站 502、1 次 404），费用 ≈ $0.05（按成功计 $0.048；全部计 $0.054），远低于 300 次上限。** Home Depot 直连 HTTP 请求约 300 次（商品页大多复用 HD 回测小试缓存），免费。

## 1. 列表抓取结果

排序都用平台默认（HD = bestmatch，Lowe's = featured，Wayfair = Recommended），排除广告位，按出现顺序去重编排名。

| 指标 | Home Depot | Lowe's | Wayfair |
| :--- | ---: | ---: | :--- |
| 页面显示结果总数 | 60,851 | 40（其中广告 4） | 36,000 |
| 对照词 "fluted bathroom vanity" 结果总数（只抓第 1 页） | 49,058（第 1 页 16 / 24 标题含 reeded/fluted） | 12,172（第 1 页 20 / 24） | 1,920（第 1 页 11 / 33） |
| 抓取页数 / 原始条数 | 15 页 / 360 | 2 页 / 40 | 16 页 / 489 |
| 广告位 | 0（HD 搜索页 `isSponsored` 全空） | 4 | 128（集中在前 10 页，每页 12–15 个） |
| 翻页重复条数 | 46 | 0 | 132（广告位反复出现为主） |
| 自然位去重后（排名用） | 300 | **36（结果用尽）** | 300 |
| 系列（家族）数 | 157（按评论首页相同合并） | 36（`productVariants.parentId`，36 条各自独立；无父体的按自身） | 300 listing；按"品牌 + 去掉尺寸后的标题"粗并为 259 |
| 同系列在结果中出现多次 | 28 个家族占 171 条，最多一个家族 26 条（同款不同尺寸 / 颜色各是一条） | 0（Lowe's 搜索 `rollUpVariants=true`，变体收拢成一条） | listing 不重复；但同系列不同尺寸拆成多个 listing 的情况存在（如 Laval 48/60/72″、Lala 24/30/42/48/60″），粗并后 67 条落在 26 个多 listing 系列里 |
| 标题含 reeded / fluted | 13 / 300（4%） | 34 / 36（94%） | 107 / 300（36%） |
| 价格 / 评分有值 | 300 / 300 | 34 / 3 | 294 / 175 |
| 评论数 > 0 | 205 | **2** | 175 |
| 评论数合计 | 32,163（按商品页，家族共享会重复） | 385（Sandbanks 375 + Kensington 10，都不是标题含 reeded 的那 34 条） | 13,525 |
| 当前选项字段 | `swatches` + `totalNumberOfOptions`（218 条 ≥ 10 个选项） | `activeSwatchColor` / `defaultIden`，只 4 条有变体信息 | 卡片 `displayedOptionIDs` 与链接 `piid`；`choicesText`（如"2 Colors, 7 Sizes"），213 条有 |

**标题含 reeded / fluted 的商品有没有销量信号**：HD 13 条里 3 条有评论（合计 153 条评论）；Lowe's 34 条全部 0 评论；Wayfair 107 条里 26 条有评论（合计 178 条，占前 300 评论 1.3%）。三个平台的关键词结果里，reeded 本身都是"新、少、评论薄"。

## 2. 尺寸段 / 拆装 / 形态能定的比例

规则：v12.2 Tagger（`app/pdt/core/tagging_rules.py`，关默认值）读标题；Tagger 没认出宽时补一条标题正则（"数字 + in/inch/\"" 且后面不是 H/D，15–100 寸；"24\"/30\"" 这类多尺寸写法不认）。装看 "(Assembled) / Fully Assembled / RTA / Unassembled"；形态看 "floating / wall mount / freestanding"。尺寸段按 `families.band`（±3 寸归段）。

| 项 | HD 标题 | HD 标题 + 商品页规格 | Lowe's 标题（36 条） | Wayfair 标题 |
| :--- | ---: | ---: | ---: | ---: |
| 尺寸段能定 | 270 / 300（90%） | 291（97%） | 31（86%） | 241（80%） |
| 装能定 | 137（46%） | 295（98%） | 4（11%） | 23（8%） |
| 形态能定 | 266（89%） | 295（98%） | 20（56%） | 141（47%） |

尺寸段分布（能定的部分）：
- HD（规格补齐后）：60″ 55、30″ 54、72″+ 44、24″ 38、36″ 34、48″ 30、42″ 21、18″ 15。
- Lowe's：30″ 13、24″ 5、18″ 4、48″ 3、36″ / 60″ / 72″+ 各 2。
- Wayfair：30″ 86、36″ 48、60″ 35、48″ 29、24″ 19、72″+ 14、42″ 9、18″ 1。

注意 Wayfair 的"尺寸段能定"是**标题上的当前选项**：69 个 listing（23%）一页挂多个尺寸（"N Sizes"），标题只写其中一个，评论数（合计 819 条）是整个 listing 所有尺寸的合计。Lowe's 同理：父体下有多个尺寸时，搜索条目的标题可能根本不写尺寸（Sandbanks、Kensington）。

## 3. 变体与评论字段核实（抽样）

### Lowe's（经 Bright Data 抓商品页 3 个 + 评论页 2 页）

抽样：Sandbanks 5014516369（父体 6003477634，multipleOptions，375 评论）、Kensington 5017482105（父体 6003377066，按尺寸，10 评论）、Vanityfus 5019332077（父体 6003482753，按颜色，0 评论）。原计划的 5022709982（列表无价格）商品页两次 502，换成 5019332077。

- (a) **商品页有全部选项**：`productDetails[id].product.productVariantsV3.variantUIData`，每个维度一组值，每个值带对应变体 `omniItemId` 和 URL。例：Sandbanks `Manufacturer Color/Finish` = Flaxen Greige / White / White Oak，`Top Width/Sink Count` = 30-in / 36-in / 48-in single sink、60-in double sink；Kensington `Common Width` = 36 / 42 / 48 / 54 / 60 / 72.25（其中 60、72.25、42、48 指向另一个品牌 Wavecrest 的商品——Lowe's 的"父体"可以跨品牌拼组）。**各选项价格没有**，页面只有当前选中变体的价格（`mfePrice.price.additionalData.sellingPrice`）。规格里有 `Common Width (Inches)`、`Actual Width (Inches)`、`Installation Type`（Freestanding 等）、`Assembly Required` / `Ready to Assemble (RTA)`。
- (b) **评论带变体 ID**：评论页 `https://www.lowes.com/reviews/<slug>/<omniItemId>`（`window.__PRELOADED_STATE__.ratingList[id].results`，每页 20 条，`?offset=20` 翻页已验证）。每条评论有 `productId`（写评论时的变体 omniItemId）和 `pdPageURL`，例：`"productId": "5014516375"` → `/pd/allen-roth-Sandbanks-30-in-Greige-...`。首页 20 条分布在 9 个变体上。没有单独的 Size / Color 字段，但 `productId` 对上商品页的 `variantUIData` 就能得到尺寸 / 颜色。旧的 `/rnr/r/get-by-product/...` 接口 404。
- (c) **评论数是父体合计**：列表 `reviewCount` 375 = 评论页 `reviewStatistics.totalReviewCount` 375，评论来自同父体的不同尺寸 / 颜色。Kensington 商品页没有"查看全部评论"链接（10 条评论），Vanityfus 无评论。

### Wayfair（经 Bright Data 抓商品页 3 个）

抽样：Kennedy GCNE1307（"2 Colors, 7 Sizes"，104 评论）、Kendal Reeded GCNE1351（"2 Colors, 4 Sizes"，46 评论）、Bilroy W111053305（8 色单尺寸，332 评论）。

- (a) **商品页有全部选项名**：RSC 数据里 `choiceCategories[].variantChoices.edges[].node.choice.name`，例 Kennedy `Overall Width` = 36″ / 42″ / 48″ / 54″ / 60″ / 72″ / 84″，`Base Finish` = Enhanced Brown Oak / Enhanced Natural Oak；每个选项带自己的 `listingUrl?piid=...`。**各选项价格没有**，只有当前 piid 的价格（`allPrices`，Kennedy 36″ $1,690 / 原价 $1,936）；要每个尺寸的价格需逐个 piid 再抓一次商品页。
- (b) **评论带选项字段**：`MarketplaceListingReview.choices`，形如 `[{"name": "Base Color", "value": "Enhanced Brown Oak"}, {"name": "Overall Width", "value": "48\""}]`。Kennedy 内嵌 5 条：48″ ×3、36″、72″；Bilroy 5 条都带 `Base Color`；**Kendal 5 条 `choices` 为空**（同为 Verified Purchase）——不是每个 listing 都有。商品页只内嵌 5 条（`hasNextPage: true`）；翻页走 `/federation/graphql`（services.md 记录经 BD 一律 400/502），或 Apify `abotapi/wayfair-scraper`（字段 `purchasedOptions`，本次不可用、未调用）。
- (c) **评论数是 listing 合计**：`reviews.totalCount` 104 = 列表卡片 `totalReviewCount` 104，跨 7 个尺寸 × 2 色。

### Home Depot（直连，3 个）

Arcott 327193858、Bannister 319735856、Laval 333485322：评论首页 30 条的 `ProductId` 分别落在 5 / 16 / 17 个不同商品页上，`OriginalProductName` 带尺寸（如 "Arcott 49 in. …"、"Laval 24 in. W …"）——已知结论成立：家族共享评论、每条评论带写评论时的商品页 ID，可直接拆到尺寸 / 颜色。搜索结果**把尺寸 / 颜色展开成多条**：同家族最多 26 条（Laval 系列），28 个多条家族占前 300 的 171 条。

## 4. 覆盖估计（前 300 是否已覆盖大部分销量）

做法同 HD 回测小试 §3.1：家族按最靠前的排名计一次，看各排名段的评论数（销量代理）和"价格 × 评论数"（销售额代理）占前 300 合计的比例；再用 51–300 名有评论的家族拟合 ln(值) = a + b·ln(家族名次)，乘上"有评论"的比例，外推到前 1,000 / 3,000 个家族。假设：评论数与销量成正比（各平台没有校准）；评论数是累计值，不是近期月销；关键词结果的"全集"不知道多大（HD / Wayfair 的页面总数基本是整个类目），所以给两个 N 做敏感性。

| 平台 | 值 | 家族数 | 1–50 | 51–100 | 101–200 | 201–300 | 斜率 b | 外推覆盖（N=1,000 / 3,000） |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| HD | 评论数 | 157 | 83% | 11% | 3% | 3% | −1.98 | 99% / 98% |
| HD | 价 × 评 | 157 | 73% | 16% | 6% | 5% | −1.96 | 98% / 98% |
| Lowe's | 评论数 | 36 | 100%（只有 2 个有评论） | — | — | — | 拟合不了 | — |
| Wayfair | 评论数 | 300 | 18% | 30% | 30% | 23% | −0.29 | 86% / 67% |
| Wayfair | 价 × 评 | 300 | 27% | 7% | 37% | 29% | +0.08 | 82% / 53% |

解读：
- HD：排名靠前的家族评论极集中（前 50 名占 83%），前 300 对"相关度排序下的浴室柜"已基本饱和——但这批结果几乎不是 reeded（13 / 300），所以这个覆盖说的是"类目头部"，不是 reeded。
- Lowe's：关键词结果 36 条就用尽，评论只集中在 2 个不含 reeded 字样的老款上；无从谈覆盖。
- Wayfair：评论数随排名几乎不降（b = −0.29，201–300 名仍占 23%），**前 300 远未饱和**；Recommended 排序不按销量排，reeded 商品还在往后堆（201–300 名 35 条）。外推覆盖对 N 很敏感，只能说"前 300 最多覆盖一半到八成多"。

## 5. 结论与建议

1. **Home Depot**：框（尺寸段 × 装 × 形态）能定，但"关键词抓 300"抓不到 reeded——HD 搜索把 reeded 当噪声，返回的是整个类目。分析 reeded 应沿用"类目 Top Sellers 前 300 × 2 + 评论家族 + 打标"（HD 回测小试已做），评论按商品页 ID 拆到尺寸。
2. **Lowe's**：关键词结果只有 36 条，34 条 reeded 全是零评论（多为 Marketplace 新品），**没有可分析的销量**。字段层面可行：商品页给全部变体和规格（宽 / 拆装 / 安装方式），评论页每条带 `productId`，按"评论 → 变体 → 尺寸"可以把父体评论拆到尺寸。要做 Lowe's，入口应是类目 Best Sellers 榜（或更宽的词），不是 reeded 关键词。
3. **Wayfair**：关键词有相关度（36% 标题含 reeded / fluted），但排序不按销量、前 300 未饱和；标题拆装只有 8%、形态 47%。拆到尺寸的办法：评论 `choices` 里的 `Overall Width`（Kennedy 5/5 有，Kendal 0/5 有），按评论的尺寸分布把 listing 评论拆到尺寸段；拿不到 `choices` 的 listing 只能按标题尺寸或均分。完整评论需要 Apify（`purchasedOptions`）或 GraphQL（BD 不通），BD 只能拿到商品页内嵌的 5 条。
4. **Bright Data 稳定性**：Lowe's 502 共 3 次——搜索第 2 页 `offset=24` 第一次 502、重试成功（偶发）；商品页 5022709982 两次 502（单个商品页的问题，列表里它也没有价格）。另一个"限制"是参数：Lowe's 搜索页的 `adjustedNextOffset=20` 不能用作翻页参数（服务端仍返回第 1 页），要用 `offset = 页码 × 24`。Wayfair 列表 16 页中有 3 页第一次只渲染出少量卡片（约 0.94 MB），重试即正常。单次请求 10 秒–7 分钟。

### 做成正式流程时每个平台的预计请求数（按本次实测的每页条数与重试率）

| 平台 | 列表 | 商品页（规格 / 变体） | 评论（拆到尺寸用） | 预计请求 / 费用 |
| :--- | :--- | :--- | :--- | :--- |
| Home Depot | 直连，24 条 / 页，300 条 ≈ 15 页 | 直连，每商品页 1 次（≈ 300） | 直连，每家族约 评论数 ÷ 30 页（已有 GraphQL 接口） | 免费，≈ 1.3 秒 / 次 |
| Lowe's | BD，24 条 / 页（20 自然位），300 条 ≈ 15–18 页 | BD，每父体 1 次（变体名单 + 规格；各变体价格要逐个变体页再抓） | BD 评论页，每页 20 条：家族评论数 ÷ 20（如 375 条 = 19 页） | 300 个父体、平均 100 条评论：≈ 18 + 300 + 1,500 ≈ 1,800 次 ≈ $2.7；只要列表 + 商品页 ≈ 320 次 ≈ $0.5 |
| Wayfair | BD，30 条 / 页（约 18 个新的自然位），300 条 ≈ 17 页 + 约 20% 重试 ≈ 20 次 | BD，每 listing 1 次（选项名单 + 当前价 + 5 条内嵌评论）≈ 300；各尺寸价格另需每选项 1 次 | BD 拿不到完整评论；需 Apify（本次不可用）或 GraphQL | 列表 + 商品页 ≈ 320 次 ≈ $0.5；若各选项价格都要，按平均 3–4 个选项 ≈ +1,000 次 ≈ +$1.5 |

## 局限

- 评论数是累计值，不是近期销量；覆盖估计只给量级。
- Wayfair 粗并系列（品牌 + 去尺寸标题）只是启发式，没有逐个核对。
- 抽样每平台 3 个，`choices` 是否普遍存在（Kendal 为空）需要更大样本确认。
- HD 搜索的 `isSponsored` 全空，广告位可能没识别出来。
