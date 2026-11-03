# 品类机会判定台 Requirements Correctness Analysis

## Scope

- contract: requirements.md
- revision: 6
- analyzed_at: 2026-11-03T12:00:00Z

## Findings

| ID | Severity | Involved IDs | Category | Failure Mode | Resolution | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| RA-101 | P1 | AC-F16-07, AC-F17-01, AC-F22-01, AC-F23-01 | 约束冲突 | "先评估再确认"与"每月自动拉"可能冲突：自动任务没人点确认 | 第一版不做定时自动运行，所有花钱任务由 wen 发起并确认；"每月"指 wen 每月发起一次（AC-F17-01 写明由 wen 选择月份并确认费用） | resolved |
| RA-102 | P1 | AC-F17-03 | 含糊量词 | "与上一月小类排名相同的比例"未说明分母 | 已回写 AC-F17-03：分母为两个月都出现的 ASIN；阈值 10%（第二轮核对：正常相邻月 0–3%，误标月 95%） | resolved |
| RA-103 | P1 | AC-F18-03, AC-F27-01 | 未声明假设 | "低于阈值"没有默认值 | 阈值在品类配置里设置（AC-F27-01）；浴室柜默认按第二轮打标技能的置信度分档"低"进入队列 | resolved |
| RA-104 | P1 | AC-F19-01, AC-F20-01 | 未声明假设 | 第九版规则和机会扫描规则引用的是文件，实现可能分叉 | 以 `solution-v2/trial/回归预测.py`、`回归预测_第九版.py`、`机会扫描.py` 的现有实现为规则来源；Design 阶段转成算法规格 | resolved |
| RA-105 | P1 | AC-F25-01, AC-F21-02 | 逻辑不一致 | 批准后锁定，但数据更新后卡上的数字会变 | 已回写 AC-F25-02：批准时保存数字快照，之后数据更新只提示"有新数据"、可另存新草稿 | resolved |
| RA-106 | P1 | AC-F26-02 | 缺失路径 | 自家产品没有关联 ASIN 时无法对账 | 由 AC-F26-04"待关联"覆盖；wen 关联 ASIN 后再对账 | resolved |
| RA-107 | P2 | NFR-007 | 约束冲突 | wen 电脑关机时其他角色不可访问 | 已作为关键决策的代价被接受（PRD 10.3），第一版不处理 | resolved |
| RA-108 | P1 | AC-F24-02 | 缺失路径 | 原利润测算台的数据存在浏览器里，迁移时可能丢 | 提供"导入已保存方案 .json"（原工具已有），首次使用时由 wen 导入 | resolved |

## Summary

P0 unresolved: 0
P1 unresolved: 0
