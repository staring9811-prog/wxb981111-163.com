# 2026-06..09 浴室柜项目实际使用的销量脚本（原件，未改）

来自交接包 `02_数据源/BathroomVanities_202606_09_expansion`。基础 `allocate_sales.py` 未实现全部项目规则；本项目实际链路为
`prepare.py`（读卖家精灵导出）→ `normalize.py`（父子关系、详情、五点规范化）→ `reuse_merge.py`（6月复用7月词数、8月复用9月词数）→ `estimate_sales.py`（分摊 + 单子体回填 + 旧版4.5/1.5倍对照列）。
脚本内 D:/Codex、C:/Users 路径需按本机交接包目录映射。复算须同时读 `../../references/accuracy-and-legacy-rules.md`。
