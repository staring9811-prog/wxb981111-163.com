# 变更影响（需求契约 revision 5 → 7，第二轮）

| Changed Source | Old→New Revision | Affected Design IDs | Artifacts | Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| F01–F14 及其 US / REQ / AC，NFR-001～006 | 5 → retired | 第一轮全部 PAGE-F01～F14、CMP / API / DATA / SEQ、DEC-001～ | pages/PAGE-F01～F14-*.md / .html；页面清单.md；设计决策蓝图.md；技术方案.md；设计追溯矩阵.md | 按第二轮重做。第一轮视觉风格（DESIGN.md / tokens.css）和技术栈经 wen 确认后沿用；第一轮页面文件留在 git 历史，新页面使用新的 PAGE ID | stale |
| F15–F29、NFR-007～012（新增） | — → 7 | 第二轮新 PAGE / CMP / API / DATA / SEQ | 新蓝图、页面清单、pages/PAGE-F15～F29-*、技术方案、追溯矩阵 | 新建 | stale |

## 需求契约 revision 7 → 8（2026-11-03，小平台回测增量，方案书 §10）

| Changed Source | Old→New Revision | Affected Design IDs | Artifacts | Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| REQ-F20-01（AC-F20-03 证据等级增加"经回测（打折）"） | 1 → 2 | PAGE-F20-01, API-F20-01, DATA-F20-01 | pages/PAGE-F20-01.md / .html；技术方案.md 附录 A | 更新页面证据等级徽标与说明 | covered |
| REQ-F18-04、AC-F18-08（新增） | — → 1 | PAGE-F18-01, API-F18-01, DATA-F18-01, DATA-F28-02 | pages/PAGE-F18-01.md / .html；技术方案.md | 标签来源与规格优先打标 | covered |
| REQ-F19-03、AC-F19-05～06（新增） | — → 1 | PAGE-F19-01, API-F19-02, DATA-F19-02, SEQ-F23-01 | pages/PAGE-F19-01.md / .html；技术方案.md | 渠道切换、分渠道回测与证据等级 | covered |
| REQ-F23-02、AC-F23-03～04、NFR-013（新增） | — → 1 | PAGE-F23-01, CMP-F16-01, API-F23-02, DATA-F28-02, SEQ-F23-01 | pages/PAGE-F23-01.md / .html；技术方案.md | 历史回补区与限速 | covered |
| REQ-F28-03、AC-F28-06～08（新增） | — → 1 | PAGE-F28-01, API-F28-02, DATA-F28-02, SEQ-F23-01 | pages/PAGE-F28-01.md / .html；技术方案.md | 历史重建、评论家族、覆盖与换手 | covered |
| REQ-F29-03、AC-F29-05～06（新增） | — → 1 | PAGE-F20-01, PAGE-F21-02, API-F29-02 | pages/PAGE-F20-01、PAGE-F21-02 .md / .html；技术方案.md | Amazon 侧丰富度列、样本外标记、决策卡对照 | covered |
| AC-F27-04（新增，Parent REQ-F27-02 未改语义） | — → 1 | PAGE-F27-01, API-F27-01, DATA-F27-01 | pages/PAGE-F27-01.md / .html | 回补与打折参数 | covered |

未受影响的页面（F15、F16、F17、F21-01、F22、F24、F25、F26 相关）与技术方案其余章节保持不变。

## 需求契约 revision 8 → 9（2026-11-04，渠道调研：小平台"单元 × 指标"观察，方案书 §11；蓝图 §12 wen 确认）

| Changed Source | Old→New Revision | Affected Design IDs | Artifacts | Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| REQ-F30-01、AC-F30-01～09（新增） | — → 1 | PAGE-F30-03, API-F30-01, DATA-F30-01, DATA-F30-02, SEQ-F30-01 | pages/PAGE-F30-03.md / .html；技术方案.md 附录 A | 新建导入页（数据分区） | covered |
| REQ-F30-02、AC-F30-10～18（新增） | — → 1 | PAGE-F30-01, PAGE-F30-02, API-F30-02, DATA-F30-02 | pages/PAGE-F30-01、PAGE-F30-02 .md / .html；技术方案.md 附录 A | 新建框列表与框详情 | covered |
| REQ-F30-03、AC-F30-19～25（新增） | — → 1 | PAGE-F30-01, PAGE-F30-02, API-F30-02, DEC-106 | pages/PAGE-F30-01、PAGE-F30-02 .md / .html | 可读性、尚未导入、数据不足、历史观察、回测标记 | covered |
| REQ-F30-04、AC-F30-26～30（新增） | — → 1 | PAGE-F18-01, PAGE-F30-01, API-F30-01, API-F30-02, API-F18-02, DATA-F18-01, SEQ-F30-01 | pages/PAGE-F18-01.md / .html（局部：原因"分框未知（渠道调研）"、预筛与返回、多尺寸候选）；PAGE-F30-01 | 打标确认增量 | covered |
| REQ-F30-05、AC-F30-31～32（新增，Stage 第二版） | — → 1 | PAGE-F30-01（planned 入口）, API-F16-03, DATA-F30-01 | 页面清单.md；设计决策蓝图.md §12；技术方案.md §8.3 | 只登记骨架与扩展预留，不出详细设计 | planned |
| NFR-014（新增） | — → 1 | PAGE-F30-01, PAGE-F30-02, PAGE-F30-03, API-F30-01, API-F30-02 | 技术方案.md 附录 A.4 | 测量点 | covered |
| DEC-105（design-derived，新增） | — | PAGE-F15-02 | pages/PAGE-F15-02.md / .html（本月数据状态加"渠道调研"行） | 局部更新 | covered |

已有来源 ID 的 revision 都没变，无 stale 项。全部页面 HTML 的侧栏加"渠道调研导入"（数据）与"渠道调研"（分析）两项，打标确认角标随原型数据改为 268；其余页面内容、视觉规则（DESIGN.md / tokens.css）与技术方案其余章节不变。
