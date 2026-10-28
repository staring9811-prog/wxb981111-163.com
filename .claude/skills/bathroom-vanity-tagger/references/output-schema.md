# 2026-10-24已确认字段

用户已确认台面台盆两列分开，并确认最新marble归类。v2、v3按以下16列执行（v3未改列结构）。

表：SKU估算明细；子ASIN×目标月份一行。现有62列原样保留，末尾追加以下16列，无下拉。其余Sheet不改。

| 表头 | 填写方式 |
|---|---|
| D1产品形态 | 自动文本：悬浮式/落地式/开放式/柱状盆/转角式，未知信息不足；父体独有线索加（父体候选）；v12起柱状盆含立柱盆储物柜，标题/SKU写明时优先 |
| D2安装方式 | 自动文本：整装/拆装/部分预装，未知信息不足；不凭默认值判断 |
| D3盆数 | 自动文本：单盆/双盆/无盆/多盆，未知信息不足，不凭宽度强推 |
| D4台面形态 | 自动文本：台上盆/台下盆/嵌入盆/不适用（无盆）；一体盆归台上盆（v9）；未知默认台下盆（JSON status=business_default） |
| D5元素 | 自动文本，可用；分隔多标签：Fluted/Reeded/Shaker/Barn Door/Farmhouse/Slatted/Glass Door/Rattan；未识别待图片核验 |
| D6柜体颜色 | 自动文本，规范化颜色名；组合色未分部件时信息不足，不硬取首词 |
| D7柜体材质 | 自动文本：MDF（含engineered/composite wood）/胶合板/刨花板/实木/竹材；组合用+连接，含实木的写实木框架+MDF等（v9）；未知信息不足 |
| D8台面材质 | 自动文本：卡拉拉大理石/岗石/石英石/岩板/陶瓷/树脂/Cultured Marble/玻璃/木板等；未知信息不足，无台面不适用；v6起仿大理石纹无石材词→木板、stone top→岗石、一体盆台→盆材；业务归类见JSON |
| D8台盆材质 | 自动文本：陶瓷盆/树脂盆/Cultured Marble盆/玻璃盆等明确例外；未知信息不足，无盆不适用；配套推导单独记JSON状态 |
| D9宽(in) | 数值，英寸；未知留空；v4起≤0.8in内归标准宽度（24/30/36/48/60/72等），原值在JSON |
| D9深(in) | 数值，英寸；未知留空；无方向三维数按D×W×H（宽度交叉核对）；D/W标反来源取标W值；父体同宽度可补 |
| D9高(in) | 数值，英寸；未知留空；无单位“3H”是龙头孔位不是高度；无方向三维数按D×W×H；悬浮柜高度常为14–19in属正常 |
| D10镜子 | 自动文本：含/无/单卖；v5起未明确提及默认无（JSON status=business_default） |
| D11龙头 | 自动文本：含/无/单卖；v5起未明确提及默认无（JSON status=business_default） |
| 打标状态 | 自动文本：文本证据可用／部分信息不足／存在冲突待核验／目标月归属待核验／不纳入浴室柜分析；v4起父体补充的值不带“（父体候选）”后缀，来源看JSON status=parent_fill |
| 打标说明 | 自动文本；来源、父体候选、部件/变体冲突、图片未核验等 |

以上是开放文本字段，不是穷尽材料/颜色的下拉枚举，不把新原词吞成其他材料。完整逐字段证据另附JSON；缺失、父体候选、明确否定与冲突分别保存。D8两列独立判断可用性；不能把business_assumption当接口直接返回。

## JSON附加字段（v3）

tagging_evidence.json每行另有：
- feasibility：14个字段各一个代码A/A2/B/C/D/E/F/G，定义见feasibility-and-dimension-rules.md。可行性不是新列，不写进Excel。
- textSources：childDetail、sellerSpriteExport、parentFeatures三个布尔值。
- fields[D9深/高]可能有orderInferenceCandidate、swapCorrectedCandidate、rejectedCandidates、rejectedValue。
- 证据来源为卖家精灵导出时另记exportMonth、exportFile、exportRow。

tagging_work_queues.json：recollectChildDetailASINs（需补采）、imageReviewQueue（需看图）。
