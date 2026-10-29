---
name: bathroom-vanity-tagger
description: 浴室柜整柜商品属性打标，并回答“哪些字段现有数据能打、哪些现阶段不行”。用户说浴室柜打标、给浴室柜贴标签、浴室柜打标可行性、之前的浴室柜打标skill时使用。基于子ASIN的SKU、标题、子体详情、卖家精灵导出详细参数、五点处理11维度16列，保留字段证据、父体候选和逐字段可行性代码，不用销量门槛或未知默认值。关键词词库打标另用keyword-taxonomy-skill。
---

# 浴室柜商品打标

下次说“浴室柜打标”直接从本技能开始。输入位置与项目历史见[references/current-project.md](references/current-project.md)；输出16列见[references/output-schema.md](references/output-schema.md)；可行性代码与尺寸规则见[references/feasibility-and-dimension-rules.md](references/feasibility-and-dimension-rules.md)；全部字段规则现状见[references/all-field-rules.md](references/all-field-rules.md)。同一已确认结构直接复用，不重复询问。

**台面/台盆：** D8拆为台面材质、台盆材质。执行前读[references/surface-basin-rules.md](references/surface-basin-rules.md)。大理石分支Carrara/Calacatta统一卡拉拉大理石，其余未明确细分marble归岗石；明确石英石、岩板、树脂、Cultured Marble优先。业务归类与推导须记JSON方法和来源，不作为天然材质鉴定。

## 关键规则

- 粒度为子ASIN×目标月份；属性是证据快照，不是历史月末属性。可复用同一子ASIN相同文本快照，但保留原月份行、证据指纹、冲突和父体来源。不得对多月记录取最后一条覆盖。
- 不设月销10/20门槛。保留输入全部行；已核验目标浴室柜填标签，范围外或目标月归属未核验行只标状态，不删除、不挪用销量。
- 子体标题/SKU/子体详情/卖家精灵导出详细参数（同ASIN）/子体五点优先。子体没有的信息用父体的（用户2026-10-27确认，默认开启）：父体五点与父体详情overviews的值直接填入，不加后缀，JSON状态parent_fill、打标说明写“父体信息补充”；父体overviews不取颜色；父体尺寸只在父体代表变体与子体同宽度时补深/高。--no-parent-fill 恢复“（父体候选）”口径。JSON逐字段记来源ASIN、范围，导出来源另记导出月份与行号。
- 柜体颜色优先SKU单色和明确柜体描述；组合色未区分柜/盆/五金不硬填。标题与SKU不一致保留SKU值并标冲突。
- 柜体、台面、盆材质按部件判断。实木/实木框架只凭文本不信：整装且价格≥同宽MDF中位1.5倍才算实木，否则实木框架+MDF（用户2026-10-27，CAB-SOLIDWOOD-PRICE）；solid wood legs/feet不算柜体。柜体多种材料：含实木写实木框架+MDF等，其余用+连接（用户2026-10-27）；一体盆归台上盆。台面：solid wood单独出现是柜体不是台面，wood/marble texture直接接top才是木板台面；未细分stone top归岗石；一体盆台（<材质> sink top、integrated sink、D4一体盆）台面=盆材。engineered/composite wood归MDF（用户2026-10-27）；solid wood frame不自动补成实木框架+MDF；SMC/亚克力归树脂业务组并保留细分。纹理/仿色不证明天然石材；图片不能证明内部板材。
- 元素先文本；无可靠文本线索标待图片核验。用户2026-10-27：看图先不做。实际看过对应子体图片才可写图片核验，链接存在不等于看过图。
- 否定、排除与部件范围先于关键词。镜子/龙头：用户2026-10-27确认，文本未明确with/included的默认“无”（status=business_default，--no-accessory-default关闭）；明确含/单卖/不含的文本仍优先；无盆不推出无龙头；“faucets and mirror are not included”“excluding faucets”这类列表排除要识别；pre-drilled faucet hole、Single Hole Faucet不代表含龙头。
- 盆数先认明确数量词（single/double/dual/two + 可带修饰 + sink）；single/double vanity行业用语次之；都没有时按用户2026-10-27规则默认单盆，写双盆但宽度<48in标冲突。产品形态没写floating/corner/pedestal等默认落地式；标题或SKU写明pedestal sink/basin/under sink（含立柱盆储物柜）的一律柱状盆，优先于floating/freestanding等形态词（用户2026-10-28，FORM-PEDESTAL-PRIORITY），Standing Pedestal Cabinet配台上盆的是落地柜，不算；安装方式没写assembled/pre-assembled默认拆装。默认值JSON记business_default。
- 尺寸：优先SKU宽度，再用带方向标记的子体尺寸/标题。宽度基本是标准尺寸（用户2026-10-27）：实际值与24/28/30/31/32/36/42/48/60/72等标准宽度相差≤0.8in且唯一最近时归到标准值，原值存JSON rawValue；居中（31.5）或不在列表（37、43）的保留原值。无单位的“3H”不在a×b×c尺寸串里时是3孔龙头位，不是高度。同一来源D/W标签互换（标D≈已选宽度、标W与宽度不符）时深度留空标冲突。
- 无方向三维数“a x b x c inches”按D×W×H读取（DIM-DWH-ORDER，中间值须与已选宽度相差≤1in）；D/W标反来源取其标W值作深度（DIM-DW-SWAP）。两条规则用户2026-10-27已确认，默认开启，--no-dim-rules 关闭。
- 文字来源不保证正确。每个标签记录原文片段、来源字段/ASIN、范围、方法、冲突、规则版本。数字空值不转0；自动文本证据可用不等于独立验证准确。

## v12.2（2026-10-29，四路审计后，用户逐条确认）

以下覆盖上文对应条目；规则用例见 references/v12.2_cases.jsonl，`python3 -I scripts/case_tests.py` 全部通过才算改完。

- 形态：标题/SKU 写 corner 一律转角式（FORM-CORNER-PRIORITY）；写可壁挂也可落地的单列"两用"（FORM-DUAL）；标题写 under sink 储物柜、不含盆也不是 bathroom vanity，或写 U 形的，算柱状盆（FORM-PEDESTAL-STORAGE）；"pedestal sink"只作卖点词（柜子自带盆、厨房底柜）不算柱状盆；镜柜/防倾倒五金/对比句里的 wall mount 不算悬浮；floor standing 算落地。
- 安装方式：认 fully-assembled 等写法和"部分组件预装"；文字没写的仍默认拆装，但同一子体其他月份、同家族文字写了的照用（FAMILY-ASSEMBLY-FILL）；不用包装尺寸、品牌推断。
- 盆数/台盆位置：台盆位置只有无盆 / 台上盆 / 台下盆三种，drop-in 归台上盆；without sink、vanity only、base cabinet、without top、sink not included 等认作无盆；sink top、boat、countertop sink、integrated / one-piece / all-in-one 写法认作台上盆；文字完全没写的仍默认台下盆。
- 台面/台盆：盆材已知（陶瓷/树脂/Cultured Marble）、子体文字没有台面材质词、不是 vessel 类台上盆的，推断一体盆台，台面 = 盆材、台盆位置 = 台上盆（M-INTEGRATED-INFER / TOPFORM-INTEGRATED-INFER）；vessel 类台上盆且没写台面材质的算木板（M-VESSEL-TOP-WOOD）；台面→盆同材反推；读 SKU 里的台面/盆材料。
- 元素：Farmhouse 只认看得见的饰条（X 形、cross、barn door），只写风格词的待图片核验；Barn Doors 复数、barn-style doors 认作 Barn Door；风格列表里的 farmhouse 不算。
- 颜色：颜色和柜体名词之间可隔几个词；盆/台面/五金的颜色不算柜体色；Size 里写的柜体色要读；White Oak 归原木色；近义色（Walnut 与 Brown）不算冲突。
- 柜体材质：对比/否定句（than、unlike、avoid using、no、-free、where X warps）里的材料不算；认 solid hardwood / solid wooden / solid American oak；"vanities"复数也算柜体上下文；多层实木板 → 胶合板，实木颗粒板 → 刨花板，manufactured wood / density board → MDF；泛称 engineered wood 与具体板材同时出现时只留具体板材；腿、抽屉、门板、台面板的材料不算柜体；实木框架 + 实木写成实木。实木价格复核前的文字标签另存 tagging_d7_text_labels.json，分析"能贵多少"时用它，避免用价格解释价格。
- 尺寸：认 ''、”、“、28-inch、36in、48 in. 等写法和复数 vanities；文字没写宽度时用商品尺寸前两维中较大且 ≤84 的值（DIM-WIDTH-FROM-DIMENSION）；商品尺寸首值等于宽度、次值 ≤26 时按宽×深×高补深高（DIM-WDH-ORDER）；带侧柜的按总宽（DIM-SIDE-CABINET-TOTAL）；D/W 标反的判定放宽；别的变体的导出尺寸只作最后的深高来源。

## 执行

1. 读用户当前文件及同名analysis.json/README，先复用缓存，核对范围、字段和文件版本。新结构按table-schema-confirmation确认；已确认16列见输出规范。不要为了打标调用在线采集接口。
一键本地运行（依赖 Python 3.10+ 与 openpyxl）：`python3 -I scripts/run_pipeline.py --data-root <数据目录> --base-xlsx <上一版或未打标xlsx> --out-dir <输出目录> [--base-analysis 上一版analysis.json] [--base-evidence 上一版tags.json] [--name 文件名]`，依次执行下面 2–6 步并校验。分步：

2. 打标（无网络）：
   `python3 -I scripts/tag_cached.py --data-root <规范化数据目录> --out-dir <输出目录>`（默认开启尺寸规则、标准宽度、父体补充；对应关闭开关 --no-dim-rules / --no-std-width / --no-parent-fill / --no-accessory-default / --no-price-rules）
   数据目录需含sales_payload.json、collected_details.json、step1_macro_audit.json、feature_field_provenance.json，可选input_rows.json（卖家精灵导出逐行）。输出tagging_matrix/evidence/summary/work_queues四个JSON。其他项目须先明确映射字段和纳入标记，不能把缺少_eligible当作全量范围。不要运行旧tag_vanity_v3.py。
3. 写Excel（只改16个标签列，其余单元格原样）：
   `python3 -I scripts/write_workbook.py --base <源或上一版xlsx> --matrix <输出目录>/tagging_matrix.json --out <新xlsx>`
   表头已有16列时原位替换；没有时追加到末列并扩展表格范围。然后必须跑
   `python3 -I scripts/verify_workbook.py --base ... --out ... --matrix ...`，ok不为true不得交付。
4. 可行性报告：`python3 -I scripts/feasibility_report.py --tag-dir <输出目录> --data-root <数据目录> --out-xlsx ... --out-md ... [--base-evidence 上一版evidence] [--dim-rules-dir 启用尺寸规则的输出目录]`。
5. 交接文件：`python3 -I scripts/update_handoff.py` 在上一版analysis.json上替换工作簿绑定、taggingStatus和tagging块，销量口径不动。交付Excel、tags.json（=tagging_evidence.json）、analysis.json、README与可行性报告。
6. `python3 -I scripts/distribution.py --tag-dir <输出目录> --out-md ... --out-xlsx ...` 输出各字段每个值的行数/唯一ASIN/证据来源分布。
7. 按table-macro-check在对话给关键覆盖和异常：每字段可打标/父体候选/冲突/需补采/需看图/待确认规则的行数，待图片、父体候选、缺失数量必须明示，不能宣称全量已准确核验。

原始历史TAG_SKILL及脚本保留不改，不把其中不一致的默认值继续作为新规则。
