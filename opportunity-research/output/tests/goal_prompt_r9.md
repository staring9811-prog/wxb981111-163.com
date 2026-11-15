# /goal 提示 · revision 9（渠道调研）

> 用法：在本项目的 Claude Code（Code 模式）会话里，把下面"命令正文"整段原样发送；开头的 `/goal` 必须保留。这是按 tdd-master 规范写的等价版：原命令页 200w.liurun.vip/skill/goal.html 已下线，按 wen 2026-11-03 的决定在对话里直接用这一版（见 `doc/项目纪要-wen.md`"/goal 执行方式"）。
>
> 本轮范围：requirements revision 9，scope = 第一版；新增 F30 渠道调研（REQ-F30-01～04）、NFR-014，以及受影响的打标确认、工作台。REQ-F30-05（系统内抓取）属第二版，不做。

## 命令正文

```text
/goal 在 opportunity-research 项目里完成 revision 9（渠道调研：小平台"单元 × 指标"观察）的开发与验收，直到 output/tests/TDD验收契约.md 的全部验收行在 output/tests/TDD验收结果.md 中为 pass，并用 tdd-master 校验器 --result 模式机械核对通过。

一、开工前（改任何代码之前）
1. 读取同一 output/ 下的上游：requirements.md（revision 9）、PRD详细版.md v9 §3.3.17、设计决策蓝图.md §12、页面清单.md、设计追溯矩阵.md、技术方案.md 附录 A（API-F30-01/02、DATA-F30-01/02、SEQ-F30-01、A.4 NFR-014）、pages/PAGE-F30-01/02/03 与 PAGE-F18-01、PAGE-F15-02 的 MD 与 HTML、change-impact.md 最后一节；读取 app/开发约定.md。
2. 提取 TDD验收契约.md 的全部验收 ID，沿用已有 TDD验收结果.md：contract_sha256 已按 revision 9 契约更新；新增行（FLOW-33～40、DESIGN-19～21、RULE-10～11）和失效行（DESIGN-02、DESIGN-08、RULE-01）为 pending；其余 pass 行在本轮实现、依赖或环境改动影响到它们时才重验（例如侧栏新增两个入口会改变所有页面的导航截图：若独立视觉复核发现差异，按实际影响重截重审）。原有 pending（SMOKE-01、RULE-08、DESIGN-03 等需 wen 本人或真实密钥的项）保持如实 pending，不为清空而倒填。

二、实现要点（以上游为准，这里只提示容易做错的口径）
1. 新路由与权限：/research、/research/{channel}/frame/{key}（三类角色可看）；/data/research（导入，仅操作者；只读、审批者的写请求一律拒绝）。在 pdt/web/ui.py 的 NAV 里加"渠道调研导入"（数据组，PAGE-F30-03）和"渠道调研"（分析组，PAGE-F30-01）。原型里的 PAGE-*.html 互链换成真实路径。
2. 导入（AC-F30-01～09）：只认 三平台_商品表.csv / 三平台_月销表.csv 的列名（见 PAGE-F30-03.md §4.2），渠道只认 Home Depot / Lowe's / Wayfair；任何检查失败整次拒绝且当前版本不变；核对摘要确认后才生效；按渠道替换并保留旧版本；冲突 = 类目节点 / 两者商品当月 VP + 非VP 与已并入去重评论数差异 > 5%（已并入为 0 而导入 > 0 也算），勾选才导入。调研数据写新表（DATA-F30-01/02），不写 F28 的 Batch / Snapshot，机会扫描、回测、决策卡、台账数字不得变化。
3. 计算（AC-F30-10～25）：框 = 尺寸段 × 装 × 形态，已确认 Tag 优先于导入值；门槛 框月均 ≥ 200、单元 ≥ 20（窗口 = 导入数据的完整月）；份额分母 = 整框销量（含该属性未知）；无月度商品按同来源、同评论数档估算中估计 / 低估计，体量、份额、家族、价格、评分用中估计，趋势与新品只用有月度销量；可读性：分框覆盖（期望）< 95% 不下结论只显示体量份额，有月度 < 60% 趋势不下结论；渠道没有框达门槛显示"数据不足"；证据等级只有"历史观察"，回测标记单列。期望值以 solution-v2/trial/小平台调研_单元指标.py 的口径与 solution-v2/开发建议/小平台调研_单元×指标_HD_Lowes_Wayfair.md 的结果为准，不由被测代码生成期望。
4. 分框待确认（AC-F30-26～30）：尺寸段 / 装 / 形态任一未知（含"多尺寸未拆"）的调研商品进现有打标确认队列，原因"分框未知（渠道调研）"（新 reason 值），可按渠道筛选；多尺寸未拆候选 = 选项段里的尺寸段 + "不进框"；确认后该渠道调研重算（≤ 30 秒），重算出错保留上次结果并显示原因（DEC-106）；再次导入保留已确认值。分框确认同时作用于该商品在机会扫描中的标签（RA-120）。
5. 不新增外部服务和依赖（CSV 与计算用已在用的 pandas / numpy）；不调用 Bright Data / Apify；系统内抓取不做。

三、开发与验证节奏
1. 按最小可独立验证的闭环推进：导入核对 → 计算与框列表 → 框详情 → 打标确认联动 → 工作台行。每个闭环先跑最短冒烟；有可操作版本就给 wen 本机入口（app/启动.command 或 python run.py）试用，并说明仍在测试。
2. 测试数据：input/data_v2/渠道关键词/大词/三平台_商品表.csv、三平台_月销表.csv 与 input/data_v2/渠道调研/ 全量表（本机，不入库，不得提交）；错误输入用删改副本构造；pytest 放 app/tests/，可在测试中读取本机样本，样本不存在时跳过并在结果里如实标注。
3. 功能行 pass 需真实命令与退出码 / 测试汇总；DESIGN-19～21、DESIGN-02、DESIGN-08 用真实运行成品截图（存 output/tests/visual/）+ 独立视觉验收官（另一个子 Agent，只看截图与契约锚点，不看实现）复核，记录 actual=…; reviewer=independent-visual; review=pass; blocking=0。RULE-10 按 NFR-014 用实际规模样本计时，各测 3 次取最大值。
4. 每完成一个环节：运行 cd app && python -m pytest -q 全量（不得退化原有 143 个测试），更新 TDD验收结果.md，然后按项目规则用简体中文提交并推送 GitHub（不推送 input/ 数据）。

四、完成判定
1. 运行 python3 /root/.claude/skills/tdd-master/validators/check_delivery_contract.py --result opportunity-research/output，要求契约哈希一致、ID 集合相等、pending = 0、fail = 0。需 wen 本人或真实密钥才能执行的项（SMOKE-01 局域网另一设备与 Windows、RULE-08 真实密钥、DESIGN-03 账号页）如仍受阻，如实保留 pending 并说明停点，不得宣称整体验收完成。
2. 更新 doc/项目纪要-wen.md（当前状态与必要的决策），汇报：可用入口、通过 / 未通过行、真实证据位置、遗留问题。用户叫停立即停止。
```

## 要点速览

- 新增与失效的验收行：FLOW-33～40（导入拒绝、摘要与版本、冲突、指标数值回归、估算与可读性、尚未导入 / 数据不足、历史观察与回测标记、打标确认联动）、DESIGN-19～21（三张新页面）、RULE-10（NFR-014 计时）、RULE-11（不改分析库 + 权限）；DESIGN-02、DESIGN-08、RULE-01 因通过标准或路由集合变化重新验证。
- 数值基准：Home Depot 15 / 25 框、216 单元、覆盖 99.3%、全部可读、待确认 36；Wayfair 23 / 28 框、可读 2 框、24″ · 拆装 · 落地式 5,456 / 低估计 4,010、待确认 83。
- 不做：系统内抓取（第二版）、跨渠道绝对销量比较、把调研并入机会扫描。
