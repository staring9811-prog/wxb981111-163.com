# 当前项目与来源位置

确认日期：2026-10-24。用户：“ok把他存成下次我一说你就能直接找到的skill，打标吧”，随后确认15列。

- 当前Excel：D:/Codex/Outputs/BathroomVanities_202606-202609_SKU销量预估.xlsx
- 当前规范化原件：D:/Codex/Data/BathroomVanities_202606_09_expansion/sales_payload.json
- 子体详情缓存：同目录collected_details.json；features来源：feature_field_provenance.json。
- 纳入/排除：step1_macro_audit.json.confirmedNonTargetProducts与明细_eligible，分析交接JSON的rowManifest亦可独立读取。以当前真实文件为准，不将路径当永久固定数据。
- 本次原表13,432条，目标月家庭分摊范围10,831条；已知非目标排除后10,816条、唯一子ASIN4,639个。另有1个商品品类待图片复核。
- 历史规则：D:/Desktop/浴室柜/市场调研 code/amz bathroom vanity/TAG_SKILL.md
- 历史脚本：同目录tag_vanity_v3.py、tag_size_lib.py；历史标签库output/tag_database.xlsx。
- 旧Claude记忆：D:/以前的用户/.claude/projects/C--Users-lenovo/memory/amz-vanity-child-sales-estimation.md

旧规则仅为溯源，禁止直接沿用：未知默认MDF/陶瓷、默认单盆/无镜/无龙头、父体五点优先、月销>10/>20过滤、engineered wood无条件当MDF、按价格反推改材料。

准备审查说明：D:/Codex/Outputs/BathroomVanities_旧打标规则审查与准备_20261024.md

## 已完成的2026-10-24文本打标交付

- 打标版：D:/Codex/Outputs/BathroomVanities_202606-202609_SKU销量预估_已打标.xlsx
- 分析交接包：D:/Codex/Outputs/BathroomVanities_202606-202609_打标分析交接包.zip
- 同名analysis.json、tags.json、README.md均位于D:/Codex/Outputs。
- 当前版保留原13,432行与62列，追加15列；目标样本10,816行/4,639唯一子ASIN已执行文本打标。
- 尚未进行独立图片核验：元素7,423行待图片核验，3,393行有文本线索（其中1,315行仅父体候选）。1,197行至少有一个字段冲突。不能称为全量图片核验完成或所有字段均准确。
- 原有657,032个非空单元格和公式与源文件比较一致；新增接口调用0。

## 当前正式v2：台面与台盆拆列及marble业务归类

- 最新Excel：D:/Codex/Outputs/BathroomVanities_202606-202609_SKU销量预估_已打标_v2.xlsx
- 最新交接包：D:/Codex/Outputs/BathroomVanities_202606-202609_打标分析交接包_v2.zip
- 同名analysis.json、tags.json、README.md与Excel绑定使用。旧v1保留，其旧D8不用于确定材料分析。
- 原62列、13,432行保留，新增16列，总78列（BK:BZ）；D8为台面材质、台盆材质两列。
- 标签范围10,816行、4,639唯一子ASIN。非材料维度标签与v1逐值一致；原有非空值/公式逐值一致；新SellerSprite调用0。
- 当前快照台面卡拉拉大理石615条、岗石1,090条（子ASIN×月份，含候选/冲突）；台面信息不足6,776条、台盆信息不足2,565条。不能当历史月末属性或地质鉴定。
- 材料JSON含原词、细分、部件、归类规则与direct_text/business_mapping/business_inference/business_assumption；父体候选、冲突独立标记。少见盆材保留待核验；未开展图片独立核验。
- 审查记录：D:/Codex/Data/BathroomVanities_202606_09_tagging_v2/tagging_export_audit.json；material_change_audit.json。
