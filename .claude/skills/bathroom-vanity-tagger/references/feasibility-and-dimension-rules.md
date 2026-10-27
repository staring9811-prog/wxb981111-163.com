# 可行性代码与尺寸规则（2026-10-27，v3）

用户要求：打标同时回答“哪些用现有数据源就可打标，哪些现阶段不行”。tag_cached.py对每个目标行的14个字段给一个代码，写在tagging_evidence.json的rows[].feasibility。

## 可行性代码

| 代码 | 含义 | 判定 |
|---|---|---|
| A | 可打标：子体文本证据 | status为text_supported或derived |
| A2 | 可打标：按已确认业务规则归类/推导 | business_mapping、business_inference、business_assumption、order_inference |
| B | 仅父体候选：需子体证据确认 | parent_candidate |
| C | 有冲突：需人工核验 | conflict（D/W互换且有纠正候选的归D） |
| D | 现有数据可补：需确认新规则后启用 | 缺失但有orderInferenceCandidate，或D/W互换有swapCorrectedCandidate |
| E | 现阶段不行：缺子体详情，需补采asin_detail | 非外观字段缺失，且该子ASIN既无子体详情也无卖家精灵导出 |
| F | 现阶段不行：文本无线索，需看图核验 | 外观字段（D1、D3、D4、D5、D6）缺失 |
| G | 现阶段不行：子体文本未写，需说明书/厂家/人工 | 非外观字段缺失，但已有子体详情或导出参数 |

字段级结论（feasibility_report.py）：A+A2≥75%为“可打标”；A+A2+D≥75%为“确认规则后可打标”；A+A2≥35%为“部分可打标”；其余“现阶段不行（大部分）”。阈值只用于概括，报告必须同时给出各代码行数。

外观字段文本缺失时直接归F，不归E。原因：主图链接对全部行可访问，看图比补采更直接；但图片只能支持外观，不能证明内部板材、台面真材或是否随附镜子/龙头。

工作队列（tagging_work_queues.json）：
- recollectChildDetailASINs：既无子体详情也无导出参数的子ASIN，补采约每个一次asin_detail调用。补采前须用户同意接口消耗。
- imageReviewQueue：存在F字段的子ASIN、主图链接与需看字段。看图后才可把对应字段写为图片核验。

## 尺寸规则

默认行为（无需确认，已启用）：
- DIM-HOLE-CODE：无单位、且不在“a x b x c”尺寸串里的“nH”（n≤8）是龙头孔位（如'Size: 48" -3H'），不取作高度，记入D9高rejectedCandidates并在打标说明写明。
- 字母在前的尺寸（W36Inch、H 34in）须带单位；'24"W 18"D'这种字母属于前一个数字，不按字母在前解析。
- D/W互换保护：同一来源标W与已选宽度相差>2.5in、而标D与已选宽度相差≤1in时，判为该来源D/W标反。其标W不再算宽度冲突；深度优先取标签一致的来源；若只有该来源，深度留空并标冲突，候选写swapCorrectedCandidate。

需用户确认后用 --enable-dim-rules 启用：
- DIM-DWH-ORDER：“商品尺寸”列无方向“a x b x c inches/cm”按D×W×H读取，仅当b与已选宽度相差≤1in。2026-10-27在本项目已有带标签深/高的行上交叉核对：深度1,937/1,959一致，高度1,923/1,942一致（约99%）。不一致多为不同快照或W×D×H顺序。
- DIM-DW-SWAP：上面判为D/W标反的来源，取其标W值作深度。

两条规则的结果status为order_inference，归A2，并在打标说明写明“按顺序推断/标签互换纠正”。未启用时Excel不填，候选只在JSON与可行性表中给出。

## 镜子/龙头列表式表述（v3）

在v2的“X included / not included / sold separately / with X”之外：
- 排除：名词后在同一子句、只隔配件清单（and、mirror、drain、backsplash、hardware等）出现not included / excluded / sold separately；名词前出现excluding、does not include、without（≤2词）。
- 包含：名词前出现includes、including、comes with、package includes、complete with，且之间无否定、名词前不是for/fits/compatible with/drilled for。
- 两者都触达时取距离近的一方。
- 子体标题直接列出Faucet/Mirror视为含；名词后接hole/holes/mount holes/finish/compatible/ready，或前面是Single Hole、3-Hole、widespread、centerset时不算。
