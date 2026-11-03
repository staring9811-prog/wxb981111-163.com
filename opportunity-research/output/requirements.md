# 品类机会判定台 Requirements Contract

## Metadata

- work_type: feature
- workflow_mode: standard
- revision: 8
- scope: 第一版
- source_prd: PRD详细版.md
- status: active

> 第二轮（2026-11-03）：承接第二轮《解题方案书》与场景锚点（wen 确认）。第一轮 F01–F14、NFR-001～006 全部 retired（见文末），ID 不复用；第二轮从 F15、NFR-007 起编。第一版 = 浴室柜、在 wen 电脑运行局域网共享、F15–F29 全部交付。revision 7（2026-11-03）：wen 要求把 Home Depot / Lowe's / Wayfair 加入第一版，新增 F28、F29，F18、F26、F27 各增一条 REQ。revision 8（2026-11-03）：小平台回测增量（方案书 §10）——F18、F19、F23、F28、F29 各增一条 REQ，F27 增一条 AC，REQ-F20-01 证据等级语义变更（revision 2），新增 NFR-013。

## External capability configuration

| Capability | Credential owner | Configuration actor | Surface | Scope | Lifecycle | Stage | Requirement IDs |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 卖家精灵接口（Amazon 月度数据、Amazon 评论） | wen（公司账号） | 操作者 | settings | system | 添加、测试、掩码显示后 4 位、更换、删除；失效时相关功能显示未连接 | 第一版 | REQ-F16-01, REQ-F17-01, REQ-F22-01 |
| Bright Data（Lowe's / Wayfair 页面） | wen（公司账号） | 操作者 | settings | system | 添加、测试、掩码显示后 4 位、更换、删除；失效时相关功能显示未连接 | 第一版 | REQ-F16-01, REQ-F23-01, REQ-F23-02 |
| Apify（Lowe's / Wayfair 评论） | wen（公司账号） | 操作者 | settings | system | 添加、测试、掩码显示后 4 位、更换、删除；失效时相关功能显示未连接 | 第一版 | REQ-F16-01, REQ-F23-01, REQ-F23-02 |
| 大模型（Claude / OpenAI 等，看图打元素、差评归类、叙述草稿） | wen（公司账号） | 操作者 | settings | system | 添加、测试、掩码显示后 4 位、更换、删除；失效时相关功能显示未连接 | 第一版 | REQ-F16-01, REQ-F18-01, REQ-F21-03, REQ-F22-02 |

## Capability prerequisites

| Prerequisite | Status | Owner | Evidence or deadline | Fallback | Stage | Requirement IDs |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 卖家精灵接口可用、能按月拉浴室柜类目全量 | ready | wen | 2024-10 至 2025-12 月度数据与评论已用卖家精灵 MCP 拉取（solution-v2/数据准备/卖家精灵导出_2025-03至12_核对.md；evidence/差评_*.md） | 拉取失败时 wen 手动导出上传同格式文件（F17 导入核对照常） | 第一版 | REQ-F17-01, REQ-F22-01 |
| Bright Data、Apify 账号与 IP 白名单 | ready | wen | 评论月度 VP 追踪器已在用（tools/评论月度VP追踪器/services.md） | 只采 Home Depot（直连免费），Lowe's / Wayfair 跳过 | 第一版 | REQ-F23-01 |
| 大模型密钥（至少一家） | committed | wen | wen 2026-11-03 确认由其在设置页填写；截止：第一版联调开始前 | 元素全部进入人工确认；差评只显示原文、不归类；不起草叙述 | 第一版 | REQ-F18-01, REQ-F22-02, REQ-F21-03 |
| Home Depot 公开页面直连（列表、商品页规格、评论接口） | ready | wen | 2026-11-03 小试：两个类目各前 300 个商品页、约 2,900 次请求无 403 / 429（solution-v2/开发建议/小平台_HD回测小试.md） | 降速重试；仍失败时该渠道回补暂停并提示，已采部分保留 | 第一版 | REQ-F23-02 |
| wen 电脑作为运行机、局域网可访问 | ready | wen | wen 2026-11-03 选择"你的电脑上运行，局域网共享" | 只在 wen 本机使用，决策卡导出分享 | 第一版 | REQ-F15-01 |

## Feature F15 · 账号与角色

### US-F15-01 · 建账号、按角色控制可见和可操作的范围

- Role: 操作者
- Goal: 建账号、按角色控制可见和可操作的范围
- Value: 老板审批留痕，未登录者看不到数据
- Stage: 第一版
- Status: active

### REQ-F15-01 · 三类角色与登录

- Story: US-F15-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F15-01 · 未登录不可见

- Parent: REQ-F15-01
- Priority: P0
- EARS:

```text
WHEN 未登录的人在局域网打开系统任一页面
THE SYSTEM SHALL 重定向到登录页，不返回任何业务数据
```

### AC-F15-02 · 角色操作边界

- Parent: REQ-F15-01
- Priority: P0
- EARS:

```text
WHEN 只读角色（运营 / 采购 / 研发）对决策卡、机会扫描、台账发起修改或审批操作
THE SYSTEM SHALL 拒绝该操作并提示"无权限"，数据不变
```

### AC-F15-03 · 审批者不能改内容

- Parent: REQ-F15-01
- Priority: P0
- EARS:

```text
WHEN 审批者（老板）编辑决策卡正文或数据
THE SYSTEM SHALL 拒绝编辑，只允许审批与留意见
```

### REQ-F15-02 · 账号管理

- Story: US-F15-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F15-04 · 建与停用账号

- Parent: REQ-F15-02
- Priority: P0
- EARS:

```text
WHEN wen 在账号页新建账号并指定角色（操作者 / 审批者 / 只读）
THE SYSTEM SHALL 保存账号，该账号用设定密码登录后只获得所选角色的权限
```

### AC-F15-05 · 停用后立即失效

- Parent: REQ-F15-02
- Priority: P1
- EARS:

```text
WHEN wen 停用一个账号
THE SYSTEM SHALL 该账号的已登录会话在下一次请求时失效并回到登录页
```

## Feature F16 · 设置：密钥、预算与费用

### US-F16-01 · 在设置页配置外部服务密钥、选择大模型、设置每月预算

- Role: 操作者
- Goal: 在设置页配置外部服务密钥、选择大模型、设置每月预算
- Value: 花钱前心里有数，到上限自动停
- Stage: 第一版
- Status: active

### REQ-F16-01 · 密钥配置

- Story: US-F16-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F16-01 · 填写与掩码

- Parent: REQ-F16-01
- Priority: P0
- EARS:

```text
WHEN wen 在设置页为卖家精灵、Bright Data、Apify、大模型任一服务保存密钥
THE SYSTEM SHALL 只在本机保存密钥，页面此后只显示后 4 位
```

### AC-F16-02 · 测试连接

- Parent: REQ-F16-01
- Priority: P0
- EARS:

```text
WHEN wen 对某个已保存密钥点击"测试"
THE SYSTEM SHALL 调用该服务的最小只读请求，并显示"可用"或失败原因（认证失败 / 网络 / 额度）
```

### AC-F16-03 · 更换与删除

- Parent: REQ-F16-01
- Priority: P1
- EARS:

```text
WHEN wen 更换或删除某个密钥
THE SYSTEM SHALL 后续调用使用新密钥；删除后依赖该服务的功能显示"未连接"并不发起调用
```

### AC-F16-04 · 多家大模型

- Parent: REQ-F16-01
- Priority: P1
- EARS:

```text
WHEN wen 在设置页选择大模型提供方（至少 Claude、OpenAI 两家）并填对应密钥
THE SYSTEM SHALL 看图打标、差评归类、叙述草稿都使用所选提供方
```

### AC-F16-05 · 密钥不外泄

- Parent: REQ-F16-01
- Priority: P0
- EARS:

```text
WHEN 任何页面、导出文件、日志或代码仓库
THE SYSTEM SHALL 不出现完整密钥
```

### REQ-F16-02 · 预算与记账

- Story: US-F16-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F16-06 · 月度上限

- Parent: REQ-F16-02
- Priority: P0
- EARS:

```text
WHEN wen 为每个按量计费服务设置月度上限（美元或调用次数）
THE SYSTEM SHALL 当月累计花费达到上限时停止该服务的新调用，已采数据保留，并提示已达上限
```

### AC-F16-07 · 先评估再确认

- Parent: REQ-F16-02
- Priority: P0
- EARS:

```text
WHEN wen 发起任一会花钱的任务（拉数据、采评论、打标、归类）
THE SYSTEM SHALL 先显示预计调用量、预计费用区间和预计耗时，wen 点确认后才开始
```

### AC-F16-08 · 记账可查

- Parent: REQ-F16-02
- Priority: P1
- EARS:

```text
WHEN 任一按量计费调用完成
THE SYSTEM SHALL 在费用记录里新增一条（时间、服务、任务、数量、金额），并可按月汇总查看
```

## Feature F17 · Amazon 月度数据拉取与导入核对

### US-F17-01 · 每月让系统用卖家精灵接口拉上月浴室柜小类数据，并自动核对

- Role: 操作者
- Goal: 每月让系统用卖家精灵接口拉上月浴室柜小类数据，并自动核对
- Value: 不再手动导出，也不会把 9 月数据当成 10 月
- Stage: 第一版
- Status: active

### REQ-F17-01 · 按月拉取

- Story: US-F17-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F17-01 · 拉取上月

- Parent: REQ-F17-01
- Priority: P0
- EARS:

```text
WHEN wen 选择月份（默认上一个自然月）并确认费用后发起拉取
THE SYSTEM SHALL 用卖家精灵接口拉取该月浴室柜类目全部商品的月度字段（ASIN、父体、品牌、价格、月销、小类排名、评分、评分数、上架日期、变体、图片、链接），可断点续拉
```

### AC-F17-02 · 拉取失败可续

- Parent: REQ-F17-01
- Priority: P1
- EARS:

```text
WHEN 拉取中途失败或中断
THE SYSTEM SHALL 保留已拉部分，再次发起时只拉缺的部分
```

### REQ-F17-02 · 导入核对

- Story: US-F17-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F17-03 · 月份误标检测

- Parent: REQ-F17-02
- Priority: P0
- EARS:

```text
WHEN 一批数据的"上月购买标"日期不在所标月份，或在两个月都出现的 ASIN 中小类排名与上一月完全相同的比例超过 10%
THE SYSTEM SHALL 把该批标为"疑似月份错误"，不并入分析，并提示 wen
```

### AC-F17-04 · 来源与覆盖核对

- Parent: REQ-F17-02
- Priority: P0
- EARS:

```text
WHEN 一批数据并入前
THE SYSTEM SHALL 显示与上月相比的品类总月销变化、家族键月间一致比例、各标签覆盖率；任一项超出设定阈值时标"异常"，需 wen 确认后才并入
```

### AC-F17-05 · 并入后标注

- Parent: REQ-F17-02
- Priority: P1
- EARS:

```text
WHEN wen 确认并入一批被标"异常"的数据
THE SYSTEM SHALL 该月在所有图表和决策卡中带 * 标记，并注明异常原因
```

## Feature F18 · 自动打标与人工确认

### US-F18-01 · 新数据自动打上尺寸、拆装、形态、台面、台面材质、元素、主色、柜体材质等标签，只确认元素和低置信度标签

- Role: 操作者
- Goal: 新数据自动打上尺寸、拆装、形态、台面、台面材质、元素、主色、柜体材质等标签，只确认元素和低置信度标签
- Value: 人工只看少数需要判断的产品
- Stage: 第一版
- Status: active

### REQ-F18-01 · 自动打标

- Story: US-F18-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F18-01 · 规则打标

- Parent: REQ-F18-01
- Priority: P0
- EARS:

```text
WHEN 新并入的一批商品
THE SYSTEM SHALL 按当前品类配置的打标规则给每个子体打全部标签，并给每个标签一个置信度
```

### AC-F18-02 · 看图打元素

- Parent: REQ-F18-01
- Priority: P0
- EARS:

```text
WHEN 规则判断不了元素的商品
THE SYSTEM SHALL 用所选大模型看主图给出元素和置信度；未配置大模型时把这些商品放进人工确认
```

### REQ-F18-02 · 人工确认

- Story: US-F18-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F18-03 · 确认队列

- Parent: REQ-F18-02
- Priority: P0
- EARS:

```text
WHEN 打标完成
THE SYSTEM SHALL 把"元素"标签和置信度低于阈值的标签放进确认队列，每条显示主图、标题、候选值
```

### AC-F18-04 · 同图一致

- Parent: REQ-F18-02
- Priority: P1
- EARS:

```text
WHEN 确认队列里有主图相同的多个商品
THE SYSTEM SHALL 把它们分在一组，wen 选一次即应用到整组，也可在组内单独改
```

### AC-F18-05 · 确认后生效

- Parent: REQ-F18-02
- Priority: P0
- EARS:

```text
WHEN wen 确认或修改一条标签
THE SYSTEM SHALL 该标签状态变为"已确认"，下一次扫描和评分使用确认后的值
```

### AC-F18-06 · 看不出 = 非本品类

- Parent: REQ-F18-02
- Priority: P1
- EARS:

```text
WHEN wen 把某商品标为"看不出 / 不是本品类"
THE SYSTEM SHALL 该商品不进入本品类的任何分析
```

### REQ-F18-03 · 其他渠道商品打标

- Story: US-F18-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F18-07 · 同一套规则

- Parent: REQ-F18-03
- Priority: P0
- EARS:

```text
WHEN Home Depot / Lowe's / Wayfair 的一批商品（标题、规格、图片）入库
THE SYSTEM SHALL 用同一套打标规则和看图打元素给它们打全部标签，元素与低置信度标签进入同一个确认队列，并标明渠道
```

### REQ-F18-04 · 其他渠道按商品页规格打标

- Story: US-F18-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F18-08 · 规格优先

- Parent: REQ-F18-04
- Priority: P0
- EARS:

```text
WHEN Home Depot / Lowe's / Wayfair 商品带有商品页规格（宽度、是否需要组装、安装方式、台面材质、柜体材质、颜色）
THE SYSTEM SHALL 优先按规格字段给尺寸段、装、形态、台面材质、柜体材质、主色打标，规格缺失时才用标题规则；没有依据时"装"标为未知并进入确认队列，不默认为拆装
```

## Feature F19 · 模型更新与回测

### US-F19-01 · 新数据并入后重算市场评分和新品打分，并看到回测是否仍然有效

- Role: 操作者
- Goal: 新数据并入后重算市场评分和新品打分，并看到回测是否仍然有效
- Value: 知道这个月的评分还能不能信
- Stage: 第一版
- Status: active

### REQ-F19-01 · 重算评分

- Story: US-F19-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F19-01 · 市场层评分

- Parent: REQ-F19-01
- Priority: P0
- EARS:

```text
WHEN 一个新月份并入并确认标签后
THE SYSTEM SHALL 按第九版规则（份额斜率、新品占比、搜索同比、体量；按体量档 × 预测窗口校准）为所有分框单元重算把握、分级、立项后 6–10 个月份额预测与 80% 区间
```

### AC-F19-02 · 新品层打分

- Parent: REQ-F19-01
- Priority: P0
- EARS:

```text
WHEN 同上
THE SYSTEM SHALL 重训新品做到概率模型（只用开发能定的属性），按最近半年做到率校准，并显示"模型偏差"（近批预测平均 − 实际）
```

### REQ-F19-02 · 回测与样本外检验

- Story: US-F19-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F19-03 · 滚动回测

- Parent: REQ-F19-02
- Priority: P0
- EARS:

```text
WHEN 重算完成
THE SYSTEM SHALL 用结果已知的时点重跑回测，显示把握分档后实际变大比例、D 档变大比例、秩相关，并和上一版并排
```

### AC-F19-04 · 有效性告警

- Parent: REQ-F19-02
- Priority: P0
- EARS:

```text
WHEN 回测显示 D 档之后变大比例 > 30%，或把握分档不再逐档上升
THE SYSTEM SHALL 在首页和每张决策卡顶部显示"市场评分本月未通过有效性检验"
```

### REQ-F19-03 · 分渠道模型与回测

- Story: US-F19-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F19-05 · 渠道回测

- Parent: REQ-F19-03
- Priority: P0
- EARS:

```text
WHEN 某个其他渠道的重建历史达到 20 个月以上，wen 发起该渠道重算
THE SYSTEM SHALL 只用该渠道数据，按"尺寸 × 拆装 × 形态"框 × 属性取值重算评分（信号：份额斜率、新品占比、Amazon 侧丰富度）并滚动回测，显示把握分档后之后变大比例、D 档之后变大比例、秩相关（全部 / 大单元），并按打折规则（秩相关减 0.1、把握 ≥ 70% 档减 15 个百分点、方向对按 ≤ 60% 看）同时显示打折后的读法
```

### AC-F19-06 · 渠道证据等级

- Parent: REQ-F19-03
- Priority: P0
- EARS:

```text
WHEN 某渠道最近一次回测的把握分档逐档上升且 D 档之后变大比例 ≤ 30%
THE SYSTEM SHALL 该渠道机会的证据等级为"经回测（打折）"；不满足或尚未回测时为"未验证"，且不显示把握与分级
```

## Feature F20 · 机会扫描

### US-F20-01 · 在"尺寸 × 拆装 × 形态"框里看各属性取值的四类机会

- Role: 操作者
- Goal: 在"尺寸 × 拆装 × 形态"框里看各属性取值的四类机会
- Value: 先知道机会在哪里，再选去做决策卡
- Stage: 第一版
- Status: active

### REQ-F20-01 · 分框扫描

- Story: US-F20-01
- Stage: 第一版
- Revision: 2
- Status: active

### AC-F20-01 · 四类机会

- Parent: REQ-F20-01
- Priority: P0
- EARS:

```text
WHEN wen 打开机会扫描
THE SYSTEM SHALL 对近 6 个月月销 ≥ 200 件的每个框，按当前配置的属性（台面材质、元素、主色、柜体材质）列出每个取值，并标出增长型、评分缺口型、价格缺口型、坑（规则同 开发建议/机会扫描_202610.md）
```

### AC-F20-02 · 只在框内比

- Parent: REQ-F20-01
- Priority: P0
- EARS:

```text
WHEN 任一指标（份额、溢价、评分差、新品占比）
THE SYSTEM SHALL 只和同一个"尺寸 × 拆装 × 形态"框里的其他取值比，不跨框合并
```

### AC-F20-03 · 证据等级

- Parent: REQ-F20-01
- Priority: P1
- EARS:

```text
WHEN 列出任一机会
THE SYSTEM SHALL 同时显示它的证据等级（经回测 / 经回测（打折） / 历史观察 / 未验证）；其他渠道按该渠道最近一次回测结果给出（F19）
```

### REQ-F20-02 · 筛选

- Story: US-F20-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F20-04 · 勾选关注变量

- Parent: REQ-F20-02
- Priority: P1
- EARS:

```text
WHEN wen 勾选关注的属性、框或机会类型
THE SYSTEM SHALL 只显示符合条件的单元，系统自动保持分框控制变量不变
```

### AC-F20-05 · 从扫描生成决策卡

- Parent: REQ-F20-02
- Priority: P0
- EARS:

```text
WHEN wen 在某个单元上点"做决策卡"
THE SYSTEM SHALL 以该单元为目标创建一张决策卡草稿（F21）
```

## Feature F21 · 决策卡

### US-F21-01 · 对选中的机会生成决策卡并编辑叙述

- Role: 操作者
- Goal: 对选中的机会生成决策卡并编辑叙述
- Value: 评审会上能直接拍板，并能展开看实证
- Stage: 第一版
- Status: active

### REQ-F21-01 · 卡片内容

- Story: US-F21-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F21-01 · 十项齐全

- Parent: REQ-F21-01
- Priority: P0
- EARS:

```text
WHEN 一张决策卡生成
THE SYSTEM SHALL 包含：分框决策、我们在赌什么（市场评分、扣偏差后的新品打分、框内历史做到率与 p 值、拟定价位实测成交）、看到什么就停、被放弃的选项、大数据层时间线、SKU 层、差评归类、钱、上架后跟踪、数据限制
```

### AC-F21-02 · 数字来自数据

- Parent: REQ-F21-01
- Priority: P0
- EARS:

```text
WHEN 卡片中任一数字
THE SYSTEM SHALL 可点开看到计算来源（框、月份、样本数）；wen 不能直接改数字，只能改叙述文字
```

### AC-F21-03 · 偏差后打分

- Parent: REQ-F21-01
- Priority: P1
- EARS:

```text
WHEN 显示新品做到概率
THE SYSTEM SHALL 同时显示模型原值和扣掉当月"模型偏差"后的值
```

### REQ-F21-02 · 展开项

- Story: US-F21-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F21-04 · SKU 展开

- Parent: REQ-F21-02
- Priority: P0
- EARS:

```text
WHEN 用户在卡片 SKU 层点开任一 SKU
THE SYSTEM SHALL 显示子 ASIN 链接、主图、逐月价格 / 价比 / 评分 / 月销 / 小类排名、首次进前 50 的月份
```

### AC-F21-05 · 趋势与价格带

- Parent: REQ-F21-02
- Priority: P1
- EARS:

```text
WHEN 用户展开"大数据层"
THE SYSTEM SHALL 显示该取值在框内的份额、新品占比、溢价率、价格带构成的逐月或逐季图
```

### REQ-F21-03 · 叙述草稿

- Story: US-F21-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F21-06 · 大模型起草

- Parent: REQ-F21-03
- Priority: P1
- EARS:

```text
WHEN wen 点"起草叙述"并确认费用
THE SYSTEM SHALL 用所选大模型起草"为消费者解决了什么问题"，标"AI 草稿"，wen 编辑后才去掉该标记
```

## Feature F22 · 差评拉取与归类

### US-F22-01 · 对决策卡里的 SKU 拉 1–3 星评论并归类

- Role: 操作者
- Goal: 对决策卡里的 SKU 拉 1–3 星评论并归类
- Value: 知道低评分是能改的问题还是材料本身
- Stage: 第一版
- Status: active

### REQ-F22-01 · 拉取

- Story: US-F22-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F22-01 · Amazon 评论

- Parent: REQ-F22-01
- Priority: P0
- EARS:

```text
WHEN wen 在决策卡上点"拉差评"并确认费用
THE SYSTEM SHALL 用卖家精灵接口拉卡片中 SKU 的 1–3 星评论（每个最多 30 条），存入该卡
```

### AC-F22-02 · 其他平台评论

- Parent: REQ-F22-01
- Priority: P1
- EARS:

```text
WHEN 卡片关联了 Lowe's / Home Depot / Wayfair 商品
THE SYSTEM SHALL 从 F23 已采集的评论明细中取 1–3 星评论并入同一张卡
```

### REQ-F22-02 · 归类

- Story: US-F22-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F22-03 · 六类

- Parent: REQ-F22-02
- Priority: P0
- EARS:

```text
WHEN 评论入卡
THE SYSTEM SHALL 用所选大模型把每条评论归入一个主要原因：装配 / 做工、本品类关键部件（如树脂盆）、柜体材料、结构 / 设计、运输、服务、不明，并统计占比
```

### AC-F22-04 · 可改判

- Parent: REQ-F22-02
- Priority: P1
- EARS:

```text
WHEN wen 修改某条评论的归类
THE SYSTEM SHALL 占比随之重算，并记录为人工修改
```

## Feature F23 · 评论月度 VP 追踪（并入）

### US-F23-01 · 在同一系统里按月统计 Home Depot / Lowe's / Wayfair 评论的 VP / 非 VP

- Role: 操作者
- Goal: 在同一系统里按月统计 Home Depot / Lowe's / Wayfair 评论的 VP / 非 VP
- Value: 不用另开工具
- Stage: 第一版
- Status: active

### REQ-F23-01 · 保留现有功能

- Story: US-F23-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F23-01 · 四步流程

- Parent: REQ-F23-01
- Priority: P0
- EARS:

```text
WHEN wen 在系统内打开评论 VP 追踪
THE SYSTEM SHALL 提供与原工具相同的项目设置和"采集列表 → 评估费用 → 采集评论 → 导出 Excel"四步，可断点续跑，结果与原工具口径一致（Wayfair 只有 Verified Purchase 计 VP）
```

### AC-F23-02 · 共用设置

- Parent: REQ-F23-01
- Priority: P0
- EARS:

```text
WHEN 评论 VP 追踪调用 Bright Data / Apify
THE SYSTEM SHALL 使用 F16 设置页的密钥与月度上限，费用计入同一记账
```

### REQ-F23-02 · 历史回补

- Story: US-F23-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F23-03 · 回补采集

- Parent: REQ-F23-02
- Priority: P0
- EARS:

```text
WHEN wen 为某渠道发起"历史回补"（起始月份默认 2024-01，商品页数 N 默认 300）并确认费用
THE SYSTEM SHALL 按类目榜单排序取前 N 个商品页（排除广告位），采集每个商品页的全部历史评论（日期、星级、是否 Verified Purchase）与商品页规格，可断点续采；Home Depot 直连，Lowe's / Wayfair 经 Bright Data / Apify
```

### AC-F23-04 · 翻页上限

- Parent: REQ-F23-02
- Priority: P1
- EARS:

```text
WHEN 某商品页的评论数超过站点单一排序可翻到的上限
THE SYSTEM SHALL 按星级（再按是否 Verified Purchase）分片补采，并报告仍被截断的商品页数
```

## Feature F24 · 利润测算（并入）

### US-F24-01 · 在同一系统里做全渠道利润测算，并把结果带回决策卡

- Role: 操作者
- Goal: 在同一系统里做全渠道利润测算，并把结果带回决策卡
- Value: 决策卡"钱"一节有毛利，不只是销售额
- Stage: 第一版
- Status: active

### REQ-F24-01 · 保留现有功能

- Story: US-F24-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F24-01 · 全部功能

- Parent: REQ-F24-01
- Priority: P0
- EARS:

```text
WHEN wen 在系统内打开利润测算
THE SYSTEM SHALL 提供与原利润测算台相同的功能：导入报价表、确认尺寸与价格、参数设置、Amazon（FBM / CG / FBA）与 Lowe's / Home Depot / Wayfair 利润表、历史版本、导出 Excel 与方案 .json
```

### AC-F24-02 · 数据存服务端

- Parent: REQ-F24-01
- Priority: P1
- EARS:

```text
WHEN 保存一个利润方案
THE SYSTEM SHALL 存在系统（wen 电脑）上而不是单个浏览器里，局域网内有权限的人都能看到同一份
```

### REQ-F24-02 · 与决策卡打通

- Story: US-F24-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F24-03 · 从卡片带入

- Parent: REQ-F24-02
- Priority: P1
- EARS:

```text
WHEN wen 在决策卡"钱"一节点"测算利润"
THE SYSTEM SHALL 打开利润测算并预填该卡的尺寸、拟定售价
```

### AC-F24-04 · 结果回写

- Parent: REQ-F24-02
- Priority: P0
- EARS:

```text
WHEN wen 在利润测算里把一个方案关联到决策卡并保存
THE SYSTEM SHALL 该卡"钱"一节显示各渠道单件利润、利润率、保本价，并随方案更新
```

## Feature F25 · 审批：立项与策略库

### US-F25-01 · 在系统里审批决策卡立项和策略库条目

- Role: 审批者
- Goal: 在系统里审批决策卡立项和策略库条目
- Value: 拍板有记录，结论状态清楚
- Stage: 第一版
- Status: active

### REQ-F25-01 · 立项审批

- Story: US-F25-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F25-01 · 提交与审批

- Parent: REQ-F25-01
- Priority: P0
- EARS:

```text
WHEN wen 把一张决策卡提交审批，老板选择"批准 / 驳回 / 退回修改"并可留意见
THE SYSTEM SHALL 记录审批人、时间、结论和意见；批准后该卡锁定为只读版本
```

### AC-F25-02 · 批准后数字快照

- Parent: REQ-F25-01
- Priority: P0
- EARS:

```text
WHEN 一张已批准的决策卡所依据的数据在之后被更新
THE SYSTEM SHALL 保持批准时的数字快照不变，只在卡片上提示"有新数据"并可另存为新草稿
```

### AC-F25-03 · 批准即登记台账

- Parent: REQ-F25-01
- Priority: P0
- EARS:

```text
WHEN 一张决策卡被批准立项
THE SYSTEM SHALL 自动在预测台账（F26）登记该卡的预测
```

### REQ-F25-02 · 策略库

- Story: US-F25-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F25-04 · 三种状态

- Parent: REQ-F25-02
- Priority: P0
- EARS:

```text
WHEN wen 新增或修改一条策略库结论（如分框信号、条件表、"评分做好就起量"）
THE SYSTEM SHALL 条目带状态"未验证经验 / 历史观察 / 已验证"之一，修改产生新版本，旧版本保留
```

### AC-F25-05 · 改状态需审批

- Parent: REQ-F25-02
- Priority: P1
- EARS:

```text
WHEN 任何人把条目状态改为"已验证"
THE SYSTEM SHALL 必须经老板批准后才生效
```

## Feature F26 · 预测台账与对账

### US-F26-01 · 立项时登记预测，6 个月后自动对账

- Role: 操作者
- Goal: 立项时登记预测，6 个月后自动对账
- Value: 知道系统和决策卡说得准不准
- Stage: 第一版
- Status: active

### REQ-F26-01 · 登记

- Story: US-F26-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F26-01 · 登记内容

- Parent: REQ-F26-01
- Priority: P0
- EARS:

```text
WHEN 一张卡登记入台账
THE SYSTEM SHALL 保存登记时间、版本、分框、市场把握与份额区间、做到概率（原值与扣偏差值）、停止条件、预计上架月份
```

### REQ-F26-02 · 对账

- Story: US-F26-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F26-02 · 自动对账

- Parent: REQ-F26-02
- Priority: P0
- EARS:

```text
WHEN 某条台账预计上架后满 6 个月且对应月份数据已并入
THE SYSTEM SHALL 自动判定是否做到（6 个月内任一月小类 BSR ≤ 50 或 SPU 月销售额 ≥ $10 万）、是否触发停止条件，并写回台账
```

### AC-F26-03 · 汇总准确率

- Parent: REQ-F26-02
- Priority: P1
- EARS:

```text
WHEN 用户打开台账汇总
THE SYSTEM SHALL 按分级和做到概率分档显示实际做到比例，并标出是否达到方案书的有效标准
```

### AC-F26-04 · 未上架

- Parent: REQ-F26-02
- Priority: P1
- EARS:

```text
WHEN 台账条目超过预计上架月份 3 个月仍未关联到自家 ASIN
THE SYSTEM SHALL 标"待关联"并提示 wen
```

### REQ-F26-03 · 分渠道成功线

- Story: US-F26-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F26-05 · 各渠道判定

- Parent: REQ-F26-03
- Priority: P0
- EARS:

```text
WHEN 一条台账登记的上架渠道包含 Home Depot / Lowe's / Wayfair
THE SYSTEM SHALL 按该渠道的成功线判定是否做到：上架 6 个月内任一月进入该渠道类目榜前 50，或估算月销达到该渠道阈值（默认 Home Depot 250 件、Lowe's 150 件、Wayfair 120 件，可在品类配置里改）；同系列商品合并计算
```

### AC-F26-06 · 分渠道显示

- Parent: REQ-F26-03
- Priority: P1
- EARS:

```text
WHEN 一条台账涉及多个渠道
THE SYSTEM SHALL 分别显示每个渠道的判定结果，不合并成一个结论
```

## Feature F27 · 品类配置

### US-F27-01 · 第一版只跑浴室柜，但分框维度、属性和打标规则可配置

- Role: 操作者
- Goal: 第一版只跑浴室柜，但分框维度、属性和打标规则可配置
- Value: 以后加品类只改配置
- Stage: 第一版
- Status: active

### REQ-F27-01 · 配置项

- Story: US-F27-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F27-01 · 分框与属性

- Parent: REQ-F27-01
- Priority: P1
- EARS:

```text
WHEN wen 打开品类配置
THE SYSTEM SHALL 可查看和修改该品类的分框维度（浴室柜默认：尺寸段 × 拆装 × 形态）、扫描属性列表、打标规则、低置信度阈值
```

### AC-F27-02 · 第一版只开浴室柜

- Parent: REQ-F27-01
- Priority: P0
- EARS:

```text
WHEN 第一版
THE SYSTEM SHALL 只提供浴室柜一个品类可运行；新建其他品类的入口不出现
```

### REQ-F27-02 · 渠道参数

- Story: US-F27-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F27-03 · 换算与成功线可改

- Parent: REQ-F27-02
- Priority: P1
- EARS:

```text
WHEN wen 在品类配置里修改某渠道的评论换算系数（默认 1 条 VP = 50 件、1 条非 VP = 20 件）或成功线
THE SYSTEM SHALL 之后的销量估算、机会扫描和台账判定使用新值，并在页面上注明所用参数版本
```

### AC-F27-04 · 回补与打折参数可改

- Parent: REQ-F27-02
- Priority: P1
- EARS:

```text
WHEN wen 在品类配置里修改某渠道的历史回补起始月份、商品页数 N 或打折规则（秩相关减值、高档减值、方向对上限）
THE SYSTEM SHALL 之后的回补、回测与打折后读法使用新值，并在页面注明参数版本
```

## Feature F28 · 其他渠道数据与销量估算

### US-F28-01 · 把 Home Depot / Lowe's / Wayfair 的月度评论数据变成可比较的月度销量估算

- Role: 操作者
- Goal: 把 Home Depot / Lowe's / Wayfair 的月度评论数据变成可比较的月度销量估算
- Value: 其他渠道也能和 Amazon 一样分框看份额和趋势
- Stage: 第一版
- Status: active

### REQ-F28-01 · 数据进入

- Story: US-F28-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F28-01 · 从评论追踪进入

- Parent: REQ-F28-01
- Priority: P0
- EARS:

```text
WHEN 评论 VP 追踪（F23）完成一个月份的采集
THE SYSTEM SHALL 把各渠道商品、排名、月度 VP / 非 VP 评论数并入分析库，按商品 ID 与渠道关联打标结果
```

### AC-F28-02 · 上传已有导出

- Parent: REQ-F28-01
- Priority: P1
- EARS:

```text
WHEN wen 上传评论 VP 追踪器导出的 Excel（含"商品月度明细"表）
THE SYSTEM SHALL 按同一口径并入，并核对月份为完整月（未完整月份只作参考，不计入）
```

### REQ-F28-02 · 销量估算

- Story: US-F28-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F28-03 · 评论换算法

- Parent: REQ-F28-02
- Priority: P0
- EARS:

```text
WHEN 用户查看任一其他渠道商品或单元的月销
THE SYSTEM SHALL 按"VP 条数 × VP 系数 + 非 VP 条数 × 非 VP 系数"（默认 50 / 20）给出估算月销，并注明方法与系数
```

### AC-F28-04 · 排名平滑法

- Parent: REQ-F28-02
- Priority: P1
- EARS:

```text
WHEN wen 在品类配置里把某渠道的估算方法切换为"榜单排名平滑"
THE SYSTEM SHALL 按该渠道榜单排名的平滑趋势换算月销（排名—销量曲线用同时有排名和评论换算销量的商品拟合；这类商品少于 10 个时不提供该方法并提示），并注明方法；两种方法可在同一页面对照
```

### AC-F28-05 · 系列去重

- Parent: REQ-F28-02
- Priority: P0
- EARS:

```text
WHEN 同一系列的多个商品共享同一批评论
THE SYSTEM SHALL 计算渠道或单元合计时按评论 ID 去重，不重复计入同系列商品
```

### REQ-F28-03 · 历史重建

- Story: US-F28-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F28-06 · 按评论日期重建

- Parent: REQ-F28-03
- Priority: P0
- EARS:

```text
WHEN 某渠道历史回补（F23）完成
THE SYSTEM SHALL 按评论日期把每个商品页 2024-01 起的逐月 VP / 非 VP 评论数换算成估算月销（同 AC-F28-03 口径），以首条评论月作为上架月，并入该渠道分析库
```

### AC-F28-07 · 评论家族合并

- Parent: REQ-F28-03
- Priority: P0
- EARS:

```text
WHEN 多个商品页（同系列不同尺寸 / 颜色）共享同一批评论
THE SYSTEM SHALL 按评论重叠把它们合并为一个评论家族，家族作为该渠道的分析与份额计算单位，评论只计一次
```

### AC-F28-08 · 覆盖与换手

- Parent: REQ-F28-03
- Priority: P1
- EARS:

```text
WHEN 用户打开其他渠道数据页
THE SYSTEM SHALL 显示该渠道重建历史的月份范围、商品页数、家族数、评论数、前 N 覆盖估计（按排名分段的评论量递减外推）与前 50 名半年重合率，并注明幸存者偏差（只含当前仍在榜的商品）
```

## Feature F29 · 分渠道机会与跨渠道印证

### US-F29-01 · 每个渠道单独按框扫机会，在决策卡里并排看同一机会在各渠道的方向

- Role: 操作者
- Goal: 每个渠道单独按框扫机会，在决策卡里并排看同一机会在各渠道的方向
- Value: 能得出"只上 Wayfair"这类分渠道结论，并用多渠道信号互相印证
- Stage: 第一版
- Status: active

### REQ-F29-01 · 分渠道扫描

- Story: US-F29-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F29-01 · 每渠道单独扫

- Parent: REQ-F29-01
- Priority: P0
- EARS:

```text
WHEN wen 在机会扫描里选择渠道（Amazon / Home Depot / Lowe's / Wayfair）
THE SYSTEM SHALL 用同样的"尺寸 × 拆装 × 形态"框和四类机会规则，只用该渠道的数据扫描
```

### AC-F29-02 · 渠道内比较

- Parent: REQ-F29-01
- Priority: P0
- EARS:

```text
WHEN 任一其他渠道指标
THE SYSTEM SHALL 只在该渠道内比较，不跨渠道比较绝对销量（Wayfair 的 VP 口径不同）
```

### REQ-F29-02 · 决策卡分渠道

- Story: US-F29-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F29-03 · 并排显示

- Parent: REQ-F29-02
- Priority: P0
- EARS:

```text
WHEN 一张决策卡生成
THE SYSTEM SHALL 在"分框决策"里并排显示同一机会（同框、同属性取值）在 Amazon、Home Depot、Lowe's、Wayfair 的份额、趋势、分级与样本量，并给出每个渠道"上 / 不上 / 观察"
```

### AC-F29-04 · 跨渠道印证

- Parent: REQ-F29-02
- Priority: P1
- EARS:

```text
WHEN 同一机会在两个及以上渠道方向一致（都在涨或都在跌）
THE SYSTEM SHALL 在卡片上标"多渠道印证"并列出一致的渠道；方向相反时标"渠道分歧"
```

### REQ-F29-03 · 跨渠道供给丰富度

- Story: US-F29-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F29-05 · Amazon 侧丰富度信号

- Parent: REQ-F29-03
- Priority: P0
- EARS:

```text
WHEN 扫描或决策卡显示某个其他渠道的单元
THE SYSTEM SHALL 同时显示 Amazon 同尺寸段 × 形态 × 属性取值（不分拆装）近 6 个月的家族数、价位段数、份额走势，以及该渠道对应的家族数、价位段数和差距值 ln((Amazon 家族数 + 1) / (该渠道家族数 + 1))；Amazon 侧丰富度作为该渠道评分的信号之一，证据等级随该渠道（F19）
```

### AC-F29-06 · 样本外单元

- Parent: REQ-F29-03
- Priority: P1
- EARS:

```text
WHEN 某单元在该渠道前 N 个商品页里没有任何家族
THE SYSTEM SHALL 标"该渠道样本外，仅参考"，只显示 Amazon 侧事实，不给该渠道的把握与分级
```

## Non-functional requirements

### NFR-007 · 局域网访问

- Applies-to: REQ-F15-01
- Revision: 1
- Status: active
- Measure: 在 wen 电脑运行时，同一局域网内的浏览器可访问；系统不监听公网地址

### NFR-008 · 密钥本机存储

- Applies-to: REQ-F16-01
- Revision: 1
- Status: active
- Measure: 密钥只保存在 wen 电脑本地加密存储中；代码仓库、导出文件、日志中出现完整密钥的次数为 0

### NFR-009 · 扫描响应

- Applies-to: REQ-F20-01
- Revision: 1
- Status: active
- Measure: 24 个月数据量下（约 5 万行子体 × 月），打开机会扫描页在 10 秒内显示结果

### NFR-010 · 决策卡生成

- Applies-to: REQ-F21-01
- Revision: 1
- Status: active
- Measure: 不含外部调用时，生成一张决策卡在 30 秒内完成

### NFR-011 · 断点续跑

- Applies-to: REQ-F17-01
- Revision: 1
- Status: active
- Measure: 任何拉取 / 采集任务中断后重跑，已成功的部分不重复调用、不重复计费

### NFR-012 · 数据保留

- Applies-to: REQ-F17-01
- Revision: 1
- Status: active
- Measure: 原始拉取数据与每月并入版本保留至少 36 个月，可回看任一历史月份的扫描与评分

### NFR-013 · 回补礼貌限速

- Applies-to: REQ-F23-02
- Revision: 1
- Status: active
- Measure: 直连采集同一站点的相邻请求间隔 ≥ 1 秒，单个请求失败重试 ≤ 3 次；遇 403 / 429 自动降速并记录次数；中断后续采不重复请求已完成的商品页

## Retired（第一轮，revision 5 及以前）

第一轮需求契约（F01–F14，及其 US / REQ / AC；NFR-001～006）于 revision 6 整体 retired：第一轮 PRD v5 于 2026-10-27 被 wen 判定未达预期，第二轮以新《解题方案书》为准重写。原文见 git 历史（本文件 revision 5 版本）。这些 ID 永不复用。

