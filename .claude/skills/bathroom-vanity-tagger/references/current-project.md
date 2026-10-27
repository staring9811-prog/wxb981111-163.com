# 当前项目与来源位置

## 交接包（2026-10-27）

数据随“浴室柜_数据源与全部打标Skills_20261027”包交接，不入本仓库。解压后目录：

- 01_原始导出：卖家精灵6/7/8/9月导出Excel及原ZIP。
- 02_数据源/BathroomVanities_202606_09_expansion：打标用的规范化数据目录，即 `--data-root`。含sales_payload.json（13,432行明细）、collected_details.json（1,318个ASIN详情，其中907个目标子ASIN的精确子体详情，其余为父体）、step1_macro_audit.json（已知非目标）、feature_field_provenance.json（五点来源）、input_rows.json（卖家精灵导出逐行，含详细参数attributes/亮点features）。
- 03_打标结果与基础表：未打标源表、v2打标表及同名analysis/tags/README。
- 04_打标证据与核查：v2逐字段证据与大数核查（tagging_macro_readout_20261027.json记录了3H高度问题，v3已修复）。

旧D:/Codex、C:/Users等路径只在原机器有效，按包内相应目录映射。

## 项目范围

- 原表13,432行；已知非目标排除后10,816条子ASIN×月份、4,639个唯一子ASIN纳入打标；目标月归属待核验2,002行、不纳入614行只标状态。
- 文本来源覆盖（目标行）：子体详情2,000行/907个子ASIN；卖家精灵导出详细参数1,504行/668个；五点为父体填充8,808行/3,729个；既无子体详情也无导出参数7,955行/3,353个。
- 用户确认：2026-10-24“ok把他存成下次我一说你就能直接找到的skill，打标吧”，确认16列（D8拆两列）与marble归类。2026-10-27要求“把数据打标好，哪些用现有数据源就可打标，哪些现阶段不行”。

## 版本

- v1（2026-10-24）：15列，旧合并D8仅溯源。
- v2（2026-10-24）：16列，台面/台盆拆列。已知问题：137行高度=3in（3H龙头孔位）；152行深度实为宽度（D/W标签互换）。
- v3（2026-10-27）：修复上述两项；接入导出详细参数与父体overviews材质；镜子/龙头列表式表述；逐字段可行性代码与工作队列。列结构与v2相同，Excel由write_workbook.py在v2上原位替换BK:BZ，verify_workbook.py核对其余832,846个单元格不变。
- v4（2026-10-27）：用户确认启用DIM-DWH-ORDER、DIM-DW-SWAP；新增标准宽度归档、父体信息补充（不再标父体候选）；看图暂不做。Excel在v3上原位替换，verify通过。
- v5（2026-10-27）：镜子/龙头未明确with的默认无（ACC-DEFAULT-NONE）。Excel在v4上原位替换。
- v6（2026-10-27）：台面规则：solid wood不作台面、wood top→木板、仿大理石纹无石材词→木板、stone top→岗石、一体盆台同材、no top/base only→不适用。Excel在v5上原位替换。

## 历史规则（仅溯源，禁止直接沿用）

原机器上的TAG_SKILL.md、tag_vanity_v3.py、tag_size_lib.py及旧标签库。禁止沿用：未知默认MDF/陶瓷、默认单盆/无镜/无龙头、父体五点优先、月销>10/>20过滤、engineered wood无条件当MDF、按价格反推材料。
