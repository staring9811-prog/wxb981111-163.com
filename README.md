# wxb981111-163.com

## 浴室柜打标 skill

- `.claude/skills/bathroom-vanity-tagger/`：浴室柜整柜属性打标（11维度16列）与“现有数据能否打标”的可行性判定。在本仓库里对 Claude Code 说“浴室柜打标”即可调用。
  - `scripts/tag_cached.py`：无网络打标，输出标签矩阵、逐字段证据、可行性代码与工作队列。
  - `scripts/write_workbook.py` / `verify_workbook.py`：只改16个标签列写入 Excel，并逐单元格证明其余内容未变。
  - `scripts/feasibility_report.py`：生成字段可行性评估表与 Markdown。
  - `scripts/update_handoff.py`：把 analysis.json 交接文件更新到新版工作簿。
  - `scripts/selftest.py`：规则回归用例。
- `reports/浴室柜各字段打标分布_v9.md`（各字段每个值的行数与来源）、`reports/浴室柜打标可行性评估_20261027_v9.md`（最新）、v8、`reports/浴室柜打标可行性评估_20261027_v7.md`、`reports/浴室柜打标可行性评估_20261027_v6.md`、`reports/浴室柜打标可行性评估_20261027_v5.md`、`reports/浴室柜打标可行性评估_20261027_v4.md`、`reports/浴室柜打标可行性评估_20261027.md`（v3）：2026年6–9月项目（10,816行/4,639个子ASIN）各字段现阶段能否打标的汇总。

项目数据（卖家精灵导出、详情缓存、打标后的 Excel/JSON）不入库，随交接包单独保存。
