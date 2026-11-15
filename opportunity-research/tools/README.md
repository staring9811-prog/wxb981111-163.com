# 外部工具（wen 2026-11-03 提供）

| 工具 | 位置 | 做什么 | 数据存放 |
| :--- | :--- | :--- | :--- |
| 利润测算台 | `利润测算台/index.html` | 导入工厂报价表 → 确认尺寸、成本、售价 → 测算 Amazon（FBM / CG / FBA）、Lowe's、Home Depot、Wayfair 的利润；历史版本；导出 Excel 或方案 .json | 浏览器本地（localStorage）；方案 .json 可导出 |
| 评论月度 VP 追踪器 | `评论月度VP追踪器/` | 按月统计 Home Depot / Lowe's / Wayfair 评论的 VP / 非 VP 数量；导出 Excel（月度趋势、入口汇总、商品、评论明细） | `data/projects/<项目>/`（不提交） |

- 密钥（Bright Data、Apify）不进仓库，见 `评论月度VP追踪器/services.md`。
- 这两个工具原样放入，接入方式由 PRD 第二轮确定。
