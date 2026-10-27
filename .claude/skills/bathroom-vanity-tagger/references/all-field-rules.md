# 各字段打标规则现状（v10，2026-10-27）

通用顺序：SKU属性 → 子体标题 → 子体详情 overviews → 卖家精灵导出详细参数/亮点 → 子体五点 → 商品尺寸 → 父体五点/父体详情（子体没有时直接用，JSON status=parent_fill）→ 用户默认规则（status=business_default）。否定词（no/without/not）先于关键词；SKU 与标题不一致时 SKU 优先并标冲突。

## D1 产品形态
| 原文 | 标签 |
|---|---|
| floating / wall-mounted / wall-hung | 悬浮式 |
| freestanding / free-standing / floor-mounted | 落地式 |
| console vanity / sink / table | 开放式 |
| corner vanity / cabinet / sink | 转角式 |
| pedestal sink / basin（后面不是 storage/cabinet） | 柱状盆 |
| 以上都没有 | **默认落地式**（FORM-DEFAULT-FREESTANDING） |

注：vessel 是台面形态（D4 台上盆），不是 D1。商品尺寸列不参与。

## D2 安装方式
| 原文 | 标签 |
|---|---|
| partially / partly assembled、some components pre-assembled | 部分预装 |
| no assembly (required)、fully / pre-assembled、comes / arrives assembled | 整装 |
| assembly required、ready-to-assemble、RTA、easy / quick assembly | 拆装 |

父体五点可代表全部子体（用户2026-10-27：一个链接里基本只有整装或拆装一种）。
| 以上都没有 | **默认拆装**（ASSEMBLY-DEFAULT-RTA） |

## D3 盆数
| 原文 | 标签 |
|---|---|
| without / no sink、sink not included / sold separately、cabinet / vanity base only | 无盆 |
| double / dual / two / 2 + (修饰词≤3) + sink/basin/bowl；SKU Size 含 Dual | 双盆 |
| single / one / 1 + (修饰词≤3) + sink/basin/bowl；SKU Size 含 Single | 单盆 |
| 只有 single / double vanity 行业用语 | 单盆 / 双盆（弱证据） |
| 以上都没有 | **默认单盆**（BASIN-DEFAULT-SINGLE） |

SKU 的盆数优先于标题；写了双盆但宽度 < 48in 的行标冲突待核验。同一文本同时写单盆和双盆（多选描述）不归一。

## D4 台面形态
| 原文 | 标签 |
|---|---|
| vessel sink、above-counter sink | 台上盆 |
| undermount / undercounter | 台下盆 |
| integrated / integration sink、one-piece sink/countertop | 台上盆（用户2026-10-27：一体盆归台上盆；原文保留在JSON，用于一体盆台同材推导） |
| drop-in、top-mount sink | 嵌入盆 |
| D3 为无盆 | 不适用（无盆） |
| 以上都没有 | **默认台下盆**（TOPFORM-DEFAULT-UNDERMOUNT） |

## D5 元素（多标签，“；”分隔）
Fluted、Reeded、Shaker（含 recessed panel）、Barn Door、Farmhouse（含 X-design）、Slatted（含 louvered）、Glass Door（glass/glazed door）、Rattan（含 wicker/cane）。只看标题、SKU、五点、导出亮点和 style 类字段。都没有 → 待图片核验（用户要求看图暂不做）。

## D6 柜体颜色
1. SKU `Color:` 单一颜色 → 直接用（规范化：white/cream/ivory→白色，oak/natural→原木色，walnut→胡桃木色，espresso/dark brown/coffee→深咖啡色，gray/driftwood→灰色，navy→藏青色，blue-gray→灰蓝色，gray-green→灰绿色，sage/mint→绿色 等）。
2. SKU 是组合色（Black White）→ 不按词序取，只接受标题/详情里明确绑定 cabinet 的颜色，且必须在 SKU 组合色之内。
3. 无 SKU 颜色时：标题末尾颜色、详情 Color 字段、"xxx cabinet" 上下文。
4. SKU 与标题明确柜体颜色不一致 → 保留 SKU 值并标冲突。
5. 都没有 → 信息不足（待看图）。

## D7 柜体材质（多标签）
材料词：MDF / medium-density fiberboard / engineered wood / composite wood→MDF（用户2026-10-27：engineered/composite wood 就是 MDF）、plywood→胶合板、particle board / chipboard→刨花板、solid wood/oak/pine/rubberwood/birch/poplar→实木、bamboo→竹材；另识别 ceramic/resin/glass/stainless 等但只在明确 "cabinet made of X" 时算柜体。
- 按子句绑定最近的部件锚点（cabinet / vanity base / body / frame / doors；top；sink；hardware），距离 ≤48 字符。
- 板材/木材词默认属于柜体；靠近 top/sink/hardware 时丢弃（除非写成 "X countertop"）。
- solid wood frame → 实木框架（其余未说明）；与 MDF 同时出现写 实木框架；MDF。
- 多种材料同时出现保留全部；输出格式（用户2026-10-27）：含实木的写 实木框架+MDF / 实木框架+MDF+胶合板+刨花板，其余用 + 连接，顺序 MDF、胶合板、刨花板、竹材；单独 solid wood frame 写 实木框架。
- 子体没有 → 父体 Material / 五点补充。都没有 → 信息不足。
- solid wood legs / feet / handles / knobs 只描述部件，不作柜体实木证据。
- **实木复核（CAB-SOLIDWOOD-PRICE，v10）**：文本只给出 实木 或 实木框架 时，结合 D2 与同宽度价格：整装且价格 ≥ 同宽度 MDF 中位数 × 1.5 → 实木 / 实木框架+实木；拆装或价格不足 → 实木框架+MDF；整装但该宽度无 ≥10 个 MDF 参照 → 保留文本标签。逐行执行（价格按行），依据写入 JSON（assembly、price、width、sameWidthMDFMedian、priceRatio、decision）。--no-price-rules 关闭。
- 不做默认值（用户尚未定）。

## D8 台面材质
见 surface-basin-rules.md 第 1–4 层及 v6 追加：直接词（石英石/岩板/陶瓷/Cultured Marble/树脂组/花岗岩/玻璃/不锈钢）→ marble 系归卡拉拉大理石或岗石 → wood/oak 直接接 top 为木板，solid wood 单独不算台面 → marble texture top 无石材词为木板 → 未细分 stone top 为岗石（兜底）→ 一体盆台取盆材 → no top / base only 为不适用。都没有 → 信息不足。

## D8 台盆材质
| 原文（绑定 sink/basin/bowl） | 标签 |
|---|---|
| ceramic / porcelain / vitreous china | 陶瓷盆 |
| resin / SMC / acrylic | 树脂盆 |
| cultured marble | Cultured Marble盆 |
| glass / tempered glass | 玻璃盆 |
| marble 系 | 岗石盆 / 卡拉拉大理石盆 |
| stainless steel 等 | 保留原词 + 盆，标待核验 |
| D3 无盆 | 不适用（不含盆） |
| 石英石/岗石台面 + 明确配盆 + 盆材未知 | 陶瓷盆（business_assumption） |
| 同材一体结构（one-piece/molded）且台面为 SMC/树脂/Cultured Marble | 同材盆（business_inference） |

## D9 宽 / 深 / 高（英寸）
1. 宽：SKU Size（去掉 "-3H" 孔位码）> 标题 "30 Inch Vanity" > 带 W 标签的详情尺寸。
2. 深/高：带 D/H 标签的详情尺寸；同一来源 D/W 标反时取其 W 值作深（DIM-DW-SWAP）；无标签 a×b×c 按 深×宽×高（DIM-DWH-ORDER，中间值须与宽度相差 ≤1in）；父体代表变体同宽度时补父体尺寸。
3. 宽度与标准尺寸（12…84，含 24/28/30/31/32/36/42/48/60/72）相差 ≤0.8in 且唯一最近 → 归标准值，原值存 JSON；31.5/37/43/49/55/61/73 等保留原值，不合并（用户2026-10-27确认）。
4. 无单位 "3H" 不是高度；cm 自动换算；来源差异 >2.5in 标冲突。
5. 无默认值。

## D10 镜子 / D11 龙头
| 原文 | 标签 |
|---|---|
| X sold / purchased separately | 单卖 |
| no / without X、X not included、excluding X、does not include X、列表式 "faucets and mirror are not included" | 无 |
| X included、with (matte black) X、includes / comes with / package includes … X、子体标题列出 Faucet / Mirror | 含 |
| faucet hole、3-hole faucet、widespread faucet、pre-drilled、mirror finish | 不算 |
| 以上都没有 | **默认无**（ACC-DEFAULT-NONE） |

## 默认值与可行性代码
所有默认值在 Excel 里与文本证据同形，JSON 的 status=business_default、可行性 A2；文本证据为 A，父体补充为 A3，冲突为 C。关闭开关：--no-accessory-default（同时关闭 D1/D2/D3/D10/D11 默认）、--no-parent-fill、--no-dim-rules、--no-std-width。
