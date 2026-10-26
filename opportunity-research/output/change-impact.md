# 变更影响 · 需求 revision 4 → 5

- 触发：用户确认 3 处需求歧义（D-27 规则按动作验证、D-28 回测只与可计算的现用指标比较、D-29 约定增加可选字段"五点描述"），见 `requirements.md` revision 5、`requirements-analysis.md` RA-028–030。
- 范围：只重做下表直接映射及依赖的设计项；其他页面、设计系统、已确认的设计决定不动。
- 示意数据口径：R-012 在 2026-11 快照中适用的就是前 2 名细分，所以它的规则倍数与快照前 20% 倍数相同，都是 2.07×；新增 R-015（观察）与 R-009（放弃）的规则对账示例，均不改变状态。

| Changed Source | Old→New Revision | Affected Design IDs | Artifacts | Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| REQ-F07-01 | 1→2 | PAGE-F07-01, API-F07-01, DATA-F07-01, SEQ-F07-01 | pages/PAGE-F07-01.md/.html; 技术方案.md §4.3 §4.4 §5.6; 设计决策蓝图.md | 改达标条件为"高于每个可计算的现用指标"，列出无法计算的指标与原因；删除页面中的"待确认" | covered |
| AC-F07-03 | 1→2 | PAGE-F07-01, DATA-F07-01 | pages/PAGE-F07-01.md/.html | 同上，达标条件逐项打勾写"全部 4 个可计算的现用指标" | covered |
| AC-F07-14 | 新增（随 REQ-F07-01 为 2） | PAGE-F07-01, PAGE-F08-01, PAGE-F12-01, DATA-F07-01, SEQ-F07-01 | pages/PAGE-F07-01.md/.html; PAGE-F08-01.md/.html; PAGE-F12-01.md; 技术方案.md | 新增：评估表对无法计算的指标显示"无数据"和原因；可比较的少于 1 个时结论为"未达标：数据不足"；导出中同样列出 | covered |
| REQ-F07-03 | 1→2 | PAGE-F07-01, PAGE-F08-01, DATA-F07-01, SEQ-F07-01 | pages/PAGE-F07-01.md/.html; PAGE-F08-01.md | 截面基线改为"只用老品、且在该截面数据包上可计算的现用指标" | covered |
| AC-F07-10 | 1→2 | PAGE-F07-01, DATA-F07-01, CMP-F09-01 | pages/PAGE-F07-01.md/.html | 同上 | covered |
| AC-F07-11 | 1→2 | PAGE-F07-01, PAGE-F08-01, PAGE-F08-02, PAGE-F09-01, PAGE-F12-02, CMP-F08-01 | pages/PAGE-F07-01.md/.html; PAGE-F08-01.md | "优于四个现用指标"改为"优于每个可计算的现用指标（至少 1 个）"；其他页面只显示结论，无需改 | covered |
| REQ-F11-01 | 1→2 | PAGE-F11-01, PAGE-F11-02, PAGE-F10-05, API-F11-01, DATA-F11-01, DATA-F11-02, DEC-013 | pages/PAGE-F11-01.md/.html; PAGE-F11-02.md/.html; PAGE-F10-05.md/.html; 技术方案.md §4.4 §4.5 §5.6 | 状态说明改为按动作验证；新增"规则倍数"定义与规则对账记录（DATA-F11-02） | covered |
| AC-F11-03 | 1→2 | PAGE-F10-05, PAGE-F11-01, DATA-F11-02, SEQ-F10-01 | pages/PAGE-F10-05.md/.html; PAGE-F11-01.md/.html; PAGE-F08-02、PAGE-F06-02、PAGE-F10-01、PAGE-F10-02、PAGE-F12-02 的"倍数"措辞 | 对账页新增"规则对账"表（规则、动作、适用细分、实际命中率、规则倍数、验证条件、结果）；R-012 依据改为规则倍数 | covered |
| AC-F11-06 | 新增（随 REQ-F11-01 为 2） | PAGE-F10-05, PAGE-F11-01, DATA-F11-02, SEQ-F10-01 | pages/PAGE-F10-05.md/.html; PAGE-F11-01.md/.html; 技术方案.md | 新增：观察规则对账只记录规则倍数和对账月份，状态不变 | covered |
| PRD §10.4（D-29，无需求 ID 变化） | — | PAGE-F04-02, DEC-009 | pages/PAGE-F04-02.md/.html; 设计决策蓝图.md | 依据 3"五点描述相同"注明来自 C1/C2 可选字段；未提供时不生成建议、对照显示"无数据"；删除页面中的"待确认" | covered |

## 顺带清理

页面中残留的"待确认"标注改为蓝图中已定的设计决定编号，行为不变：PAGE-F01-02（DEC-019）、PAGE-F03-02（DEC-022）、PAGE-F05-01（DEC-037）。

## 未受影响

设计系统（DESIGN.md、tokens.css、app.css、app.js、icons.js）、其余 17 个页面、技术选型与部署方案。
