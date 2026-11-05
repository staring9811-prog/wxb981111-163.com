# 品类机会判定台 Requirements Contract

## Metadata

- work_type: feature
- workflow_mode: standard
- revision: 10
- scope: 第一版
- source_prd: PRD详细版.md
- status: active

> 第二轮（2026-11-03）：承接第二轮《解题方案书》与场景锚点（wen 确认）。第一轮 F01–F14、NFR-001～006 全部 retired（见文末），ID 不复用；第二轮从 F15、NFR-007 起编。第一版 = 浴室柜、在 wen 电脑运行局域网共享、F15–F29 全部交付。revision 7（2026-11-03）：wen 要求把 Home Depot / Lowe's / Wayfair 加入第一版，新增 F28、F29，F18、F26、F27 各增一条 REQ。revision 8（2026-11-03）：小平台回测增量（方案书 §10）——F18、F19、F23、F28、F29 各增一条 REQ，F27 增一条 AC，REQ-F20-01 证据等级语义变更（revision 2），新增 NFR-013。revision 9（2026-11-04）：小平台"单元 × 指标"观察分析（方案书 §11）——新增 F30 渠道调研（REQ-F30-01～04 为第一版；REQ-F30-05 系统内抓取为第二版，planned），新增 NFR-014；已有 ID 语义不变。revision 10（2026-11-05，wen 确认：决策卡改版、页面白话、扫描需求范围、分框调整）——新增 REQ-F18-05（分框打标口径：尺寸段九档含 28″、开放式单独成形态、规则变更后重打标）、REQ-F18-06（调研商品主图）、REQ-F19-04（模型与回测白话）、REQ-F20-03（需求范围与在卖的款数）、REQ-F21-04～07（我们在赌什么白话读法、月销停止线按整款、表格说明与好绿差红、四个渠道段改版）、REQ-F30-06（主图可选列）、REQ-F30-07（小平台框门槛降到月均 100 件、100–200 件标"样本少，只作参考"）、NFR-015（白话用语）；语义变更：REQ-F21-01、REQ-F26-02、REQ-F27-01、REQ-F29-02、REQ-F30-02、REQ-F30-03 升 revision 2。

## External capability configuration

| Capability | Credential owner | Configuration actor | Surface | Scope | Lifecycle | Stage | Requirement IDs |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 卖家精灵接口（Amazon 月度数据、Amazon 评论） | wen（公司账号） | 操作者 | settings | system | 添加、测试、掩码显示后 4 位、更换、删除；失效时相关功能显示未连接 | 第一版 | REQ-F16-01, REQ-F17-01, REQ-F22-01 |
| Bright Data（Lowe's / Wayfair 页面） | wen（公司账号） | 操作者 | settings | system | 添加、测试、掩码显示后 4 位、更换、删除；失效时相关功能显示未连接 | 第一版, 第二版 | REQ-F16-01, REQ-F23-01, REQ-F23-02, REQ-F30-05 |
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
| wen 本机产出的小平台调研数据（三平台_商品表.csv、三平台_月销表.csv，由 solution-v2/trial/大词抓取_三平台整理.py 整理） | ready | wen | 2026-11-04 已产出：商品表 2,615 行、月销表 7,443 行，Home Depot、Wayfair 可按框（solution-v2/开发建议/大词抓取_三平台.md §5；小平台调研_单元×指标_HD_Lowes_Wayfair.md）；Lowe's 评论页补数进行中（wen 2026-11-04 批准，Bright Data 上限 $5.5） | 未导入的渠道显示"尚未导入"；Lowe's 补齐前导入后显示"数据不足"（AC-F30-22、AC-F30-23），其他渠道照常 | 第一版 | REQ-F30-01 |
| 系统内关键词 + 类目节点抓取（Lowe's / Wayfair 经 Bright Data；Wayfair 逐月评论翻页经 Bright Data 返回 400，需另选采集方式） | planned | wen | 第二版启动时核实：Bright Data 已在用（tools/评论月度VP追踪器/services.md）；Wayfair 评论翻页接口经 Bright Data 返回 400（大词抓取_三平台.md §7） | 继续由 wen 本机抓取后导入（REQ-F30-01） | 第二版 | REQ-F30-05 |

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

### REQ-F18-05 · 分框打标口径（revision 10）

- Story: US-F18-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F18-09 · 尺寸段九档

- Parent: REQ-F18-05
- Priority: P0
- EARS:

```text
WHEN 任一渠道商品按宽度（英寸，规则读出的宽度，其他渠道读不出时用商品页规格宽度）打尺寸段
THE SYSTEM SHALL 按 [15, 21) → 18″、[21, 26) → 24″、[26, 29) → 28″、[29, 33) → 30″、[33, 39) → 36″、[39, 45) → 42″、[45, 54) → 48″、[54, 66) → 60″、≥ 66 → 72″+ 归档（下限含、上限不含）；宽度 < 15 或读不出时尺寸段为空，不进任何框
```

### AC-F18-10 · 开放式单独成形态

- Parent: REQ-F18-05
- Priority: P0
- EARS:

```text
WHEN 一个商品按现行形态规则为落地式（含原规则的 console 开放式），且标题或 SKU 属性（其他渠道另含商品页规格的类型字段）写明不带门的开放层板（open shelf / open storage / open cubes / side shelves / two-tier shelf / console vanity 等；镜柜或药柜上的层板、放水管的柜内层板、门背置物架、前面带 no / not / without 的不算）
THE SYSTEM SHALL 形态打为"开放式"，与落地式、悬浮式并列单独成框（框 = 尺寸段 × 拆装 × 形态，形态取落地式 / 悬浮式 / 开放式）；悬浮式带开放层板仍为悬浮式；柱状盆、转角式、两用照旧不进框；只靠泛指词（open storage、open space 等，可能指柜内空间）判出的开放式置信度低于阈值，进入确认队列
```

### AC-F18-11 · 规则变更后重打标

- Parent: REQ-F18-05
- Priority: P0
- EARS:

```text
WHEN 分框规则（尺寸段档位或形态规则）变更后系统首次启动，或 wen 在品类配置页点"按当前规则重打分框标签"
THE SYSTEM SHALL 只对未人工确认的尺寸段、形态标签按新规则重算（已确认的标签不变），重算后置信度低于阈值的进入确认队列；完成后各渠道机会扫描按新框重算，模型与回测页提示"分框规则已变更，需重算"直到 wen 重算完成；页面显示本次改变的标签数（尺寸段、形态各多少条）
```

### REQ-F18-06 · 调研商品主图

- Story: US-F18-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F18-12 · 有主图就显示

- Parent: REQ-F18-06
- Priority: P1
- EARS:

```text
WHEN 打标确认队列里"分框未知（渠道调研）"的条目对应商品在调研导入时带主图
THE SYSTEM SHALL 显示主图缩略图，点击后放大查看；"商品链接"在新窗口打开该商品页
```

### AC-F18-13 · 无主图提示

- Parent: REQ-F18-06
- Priority: P1
- EARS:

```text
WHEN 该商品没有主图
THE SYSTEM SHALL 显示提示"没有主图，点商品链接去商品页看"，并保留可点开的商品链接
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

### REQ-F19-04 · 模型与回测页白话说明（revision 10）

- Story: US-F19-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F19-07 · 系数表白话列

- Parent: REQ-F19-04
- Priority: P1
- EARS:

```text
WHEN 用户打开模型与回测页（Amazon）的市场层信号系数表
THE SYSTEM SHALL 在"意思"列后显示"白话"列，b6、x5、x3、x4、x2、截距每行一句说明这个信号代表什么、对"之后份额变大"的影响方向和大小（截距写"所有单元共同的起点，不用单独看"）；b、c、k = 6 合计、k = 8 合计四个列头悬停给白话说明（k = 立项后第几个月）
```

### AC-F19-08 · 本月偏差卡读法

- Parent: REQ-F19-04
- Priority: P1
- EARS:

```text
WHEN 用户查看"本月模型偏差"卡
THE SYSTEM SHALL 说明"每 10 个"的意思（照这类条件做 10 个新品，有几个能做到成功线），并在卡底用一句结论写出近批模型估计每 10 个成几个、实际成几个、模型偏乐观或偏保守，以及决策卡上把模型估计往下（或往上）调多少
```

### AC-F19-09 · 校准方式白话

- Parent: REQ-F19-04
- Priority: P1
- EARS:

```text
WHEN 用户查看"校准方式选择"
THE SYSTEM SHALL 用一句话说明三种办法（只看最近半年 / 看全部历史 / 按趋势往后推）都是在估模型平时多估了多少，平均差得最少的被选中、用来调整决策卡上的估计；误差列名为"平均每 10 个差多少个"
```

### AC-F19-10 · 回测时点表说明与标红

- Parent: REQ-F19-04
- Priority: P1
- EARS:

```text
WHEN 用户查看新品层回测时点表
THE SYSTEM SHALL 每个列头悬停有白话说明（训练新家族 = 模型用来学习的新品款数；检验新家族 = 用来考模型、模型没见过的新品款数；实际每 10 个做到；能不能分出好坏；打分前 30% / 后 30% = 模型打分最高三成 / 最低三成的新品实际每 10 个做成几个；模型平均 (a)/(b)/(c)；用途：选择 = 用来挑办法，检验 = 用来考），表下有白话注释；AUC 列名为"能不能分出好坏（0.5 = 瞎猜，越近 1 越准）"，AUC < 0.5 的数字标红并配文字"比瞎猜还差"，打分前 30% 不高于后 30% 时同样标红并配文字
```

### AC-F19-11 · 把握分档与分级白话

- Parent: REQ-F19-04
- Priority: P1
- EARS:

```text
WHEN 用户查看"把握分档：之后实际份额变大的比例"和"分级：之后实际份额变大的比例"两块
THE SYSTEM SHALL 各自顶部一句白话写出用途和本次结果（例："系统给每个机会打了“把握”；回头检验，把握 ≥ 70% 的那批之后真有 x% 份额变大"），列头悬停说明，表下说明 A / B / C / D 的含义与"实际多卖合计 / 中位"（立项后这些单元实际比之前每月多卖多少件）；底部相关性改成白话结论（把握和实际变化方向基本一致 / 不太一致，月销 ≥ 300 件的大单元更一致或更不一致），相关系数数值只放悬停说明
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

### REQ-F20-03 · 需求范围与在卖的款数（revision 10）

- Story: US-F20-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F20-06 · 需求范围列

- Parent: REQ-F20-03
- Priority: P1
- EARS:

```text
WHEN 用户打开机会扫描结果表
THE SYSTEM SHALL 每个单元行显示"需求范围"：先列该单元的尺寸段、拆装、形态和属性取值，再给判定"可拓展到 X″、Y″…"或"细分需求"；悬停显示依据：同渠道、同拆装、同形态下各尺寸段该取值的份额（前 → 近）与走势
```

### AC-F20-07 · 需求范围判定

- Parent: REQ-F20-03
- Priority: P1
- EARS:

```text
WHEN 计算某单元的需求范围
THE SYSTEM SHALL 在同渠道、同拆装、同形态、同属性取值的其他尺寸段框中（只看本次扫描里有该单元的框），份额 ln(近 6 个月 ÷ 前 6 个月) ≥ 0.2（在涨）或份额 ≥ 该取值在这些尺寸段（含本框）的平均份额的尺寸段计为可拓展；至少一个时显示"可拓展到"并按尺寸从小到大列出；一个都没有（含其他尺寸段都没有该单元）时显示"细分需求"
```

### AC-F20-08 · 在卖的款数

- Parent: REQ-F20-03
- Priority: P1
- EARS:

```text
WHEN 用户查看扫描结果的月销悬停卡
THE SYSTEM SHALL 原"在榜家族"显示为"在卖的款数"，并说明"这几个月里，这个框里带该属性、进入销量榜的不同款数（同一款不同颜色尺寸算一个）"
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
- Revision: 2
- Status: active

### AC-F21-01 · 十项齐全

- Parent: REQ-F21-01
- Priority: P0
- EARS:

```text
WHEN 一张决策卡生成
THE SYSTEM SHALL 包含：分框决策、我们在赌什么（市场评分、新品做到概率（模型估计与扣掉它过去多估部分后的值）、框内历史做到率、打算定的价位实际卖得怎么样）、看到什么就停、被放弃的选项、大数据层时间线、SKU 层、差评归类、钱、上架后跟踪、数据限制
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

### REQ-F21-04 · "我们在赌什么"白话读法（revision 10）

- Story: US-F21-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F21-07 · 新品做到读法

- Parent: REQ-F21-04
- Priority: P1
- EARS:

```text
WHEN 决策卡显示新品做到概率
THE SYSTEM SHALL 读法写成白话结论："照这个方向开发新品，估计每 10 个约有 N 个能做到成功线"（N = 扣偏差后的每 10 个值四舍五入），括号里写模型原始算出的值、它过去在同类新品上平均多估（或少估）多少、扣掉（或加上）后是多少
```

### AC-F21-08 · 框内历史做到率结论

- Parent: REQ-F21-04
- Priority: P1
- EARS:

```text
WHEN 决策卡显示框内历史做到率
THE SYSTEM SHALL 写"同框里带{取值}的新品 a 个做到 b 个（百分比），同框其他{属性}做到率 c%"，并给结论：两组合计少于 20 个或带该取值的少于 5 个 →"样本太少，看不出{取值}占优势"；否则检验 p < 0.05 →"差别明显，{取值}更容易做到"或"更难做到"；否则"差别不明显，看不出{取值}占优势"；p 值只放悬停说明并配白话（这么大的差别纯靠运气出现的可能）
```

### AC-F21-09 · 打算定的价位卖得怎么样

- Parent: REQ-F21-04
- Priority: P1
- EARS:

```text
WHEN 决策卡显示拟定价位所在价格带的实测成交
THE SYSTEM SHALL 项目名为"打算定的价位，实际卖得怎么样"，每个价格带写"$X–Y 这档单个链接（子体）每月一般卖 m 件、最多 M 件"（m = 子体 × 月销量中位，M = 最高），并给结论：m ≥ 20 →"这个价位走量稳"；m < 10 且 M ≥ 100 →"这个价位能卖，但单个链接量小，要靠多款或爆款"；M < 50 →"这个价位卖得少，要慎重"；其余 →"这个价位能卖，量中等"
```

### REQ-F21-05 · 月销停止线按整款（revision 10）

- Story: US-F21-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F21-10 · 月销停止线

- Parent: REQ-F21-05
- Priority: P0
- EARS:

```text
WHEN 生成决策卡的"看到什么就停"
THE SYSTEM SHALL 月销停止线 X = 同框（同渠道、同尺寸段 × 拆装 × 形态）过去做成的新品款（上架 6 个月内做到该渠道成功线、且数据里有上架第 2、3 个月）各自上架第 2–3 个月整款月销（两月平均，整款 = 同款各颜色尺寸合计）的第 10 百分位（从低到高排、最低一成处），四舍五入到个位；文案为"上架第 2–3 个月整款月销低于 X 件就停（过去同框做成的新品里，九成这时都已超过 X 件）"
```

### AC-F21-11 · 停止线样本不足

- Parent: REQ-F21-05
- Priority: P0
- EARS:

```text
WHEN 同框做成的新品少于 10 款
THE SYSTEM SHALL 退到同渠道同尺寸段（不分拆装与形态）做成的新品计算，并在停止线旁注明"同框只有 n 款，按同尺寸段 m 款算"；仍少于 10 款时用起量线 60 件，并注明"样本不足，用起量线 60 件兜底"
```

### REQ-F21-06 · 表格说明与好绿差红（revision 10）

- Story: US-F21-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F21-12 · 表头说明

- Parent: REQ-F21-06
- Priority: P1
- EARS:

```text
WHEN 决策卡任一数据表格显示（四个渠道并排、Amazon 侧丰富度、同取值的其他框、被放弃的选项、大数据层时间线、框内各取值、SKU 层、钱、上架后跟踪）
THE SYSTEM SHALL 每个列头悬停有白话说明，表下有一行白话注释说明缩写或合写的列（例："评分 绿 / 框" = 带该属性产品的平均评分 / 整框平均评分）
```

### AC-F21-13 · 好绿差红

- Parent: REQ-F21-06
- Priority: P1
- EARS:

```text
WHEN 表中重点数字与比较对象（同框、上一期、门槛或停止线）相比更好或更差
THE SYSTEM SHALL 更好（比同框好、在涨、高于门槛）用绿色，更差（比同框差、在跌、低于停止线）用红色，持平不着色；着色的数字旁同时有文字或箭头（↑ / ↓ / 比同框高 / 比同框低），不只靠颜色
```

### REQ-F21-07 · 四个渠道段改版（revision 10）

- Story: US-F21-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F21-14 · 按月柱状图

- Parent: REQ-F21-07
- Priority: P1
- EARS:

```text
WHEN 决策卡显示"同一机会在四个渠道"的趋势
THE SYSTEM SHALL 每个渠道画按月柱状图（每月一根，标月份和该月框内份额），没有数据的月份留空、不画 0
```

### AC-F21-15 · Lowe's、Wayfair 用渠道调研

- Parent: REQ-F21-07
- Priority: P0
- EARS:

```text
WHEN 决策卡显示 Lowe's、Wayfair 行
THE SYSTEM SHALL 用渠道调研（F30）当前导入版本里同框同属性取值的数据：份额前 3 月 → 近 3 月、逐月柱状图、样本量（款数、月均件数）；证据等级标"历史观察"，与 Home Depot 的"经回测（打折）"分开显示，不给把握、分级与"上 / 不上"；不写入其他渠道分析库（F28）
```

### AC-F21-16 · 调研不可用如实说明

- Parent: REQ-F21-07
- Priority: P0
- EARS:

```text
WHEN Lowe's 或 Wayfair 没有调研导入，或该框未达调研门槛、不下结论、趋势不下结论，或该取值不在框内单元表里
THE SYSTEM SHALL 该行显示对应原因（尚未导入渠道调研 / 该框月均不到门槛（默认 100 件）/ 样本少，只作参考（框月均 100–200 件，照常显示数字）/ 不下结论（分框覆盖 x%）/ 趋势不下结论（有月度 x%）/ 该取值月均不到 20 件），不显示该原因下不允许显示的数字
```

### AC-F21-17 · 前 5 款代表产品

- Parent: REQ-F21-07
- Priority: P1
- EARS:

```text
WHEN 决策卡显示四个渠道段
THE SYSTEM SHALL 每个渠道（含 Amazon）列出同框同属性取值按窗口月销从高到低的前 5 款（Amazon、Home Depot 窗口为近 6 个月，Lowe's、Wayfair 为调研窗口）：主图（没有则显示"没有主图"）、标题、品牌、价格、评分、评论数、月销、上架时间（有则显示）、商品页链接（新窗口），每款一张逐月柱状图
```

### AC-F21-18 · 近 6 个月新品单列

- Parent: REQ-F21-07
- Priority: P1
- EARS:

```text
WHEN 该渠道同框同属性有近 6 个月内上架（调研渠道：首评或进入月在窗口最后 6 个月内）的新款
THE SYSTEM SHALL 单独列一组（按月销前 5），每款标"卖起来了"（上架以来月均 ≥ 同框每款月均）或"还没卖起来"
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
- Revision: 2
- Status: active

### AC-F26-02 · 自动对账

- Parent: REQ-F26-02
- Priority: P0
- EARS:

```text
WHEN 某条台账预计上架后满 6 个月且对应月份数据已并入
THE SYSTEM SHALL 自动判定是否做到（6 个月内任一月小类 BSR ≤ 50 或 SPU 月销售额 ≥ $10 万）、是否触发停止条件（月销停止条件按自家整款上架第 2–3 个月月销的两月平均判定），并写回台账
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
- Revision: 2
- Status: active

### AC-F27-01 · 分框与属性

- Parent: REQ-F27-01
- Priority: P1
- EARS:

```text
WHEN wen 打开品类配置
THE SYSTEM SHALL 可查看和修改该品类的分框维度（浴室柜默认：尺寸段 18″、24″、28″、30″、36″、42″、48″、60″、72″+ × 拆装、整装 × 落地式、悬浮式、开放式，与打标取值一致）、扫描属性列表、打标规则、低置信度阈值
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
- Revision: 2
- Status: active

### AC-F29-03 · 并排显示

- Parent: REQ-F29-02
- Priority: P0
- EARS:

```text
WHEN 一张决策卡生成
THE SYSTEM SHALL 在"分框决策"里并排显示同一机会（同框、同属性取值）在 Amazon、Home Depot、Lowe's、Wayfair 的份额、趋势、分级与样本量；Amazon、Home Depot 给出"上 / 不上 / 观察"，Lowe's、Wayfair 来自渠道调研、标"历史观察"、不给分级与"上 / 不上"（AC-F21-15）
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

## Feature F30 · 渠道调研（单元 × 指标观察）

### US-F30-01 · 导入本机抓好的 Home Depot / Lowe's / Wayfair 商品与逐月评论数据，按渠道 × 框看"单元 × 指标"

- Role: 操作者
- Goal: 导入本机抓好的 Home Depot / Lowe's / Wayfair 商品与逐月评论数据，按渠道 × 框看"单元 × 指标"
- Value: 在小平台还不能回测时，也能按同框观察各属性取值的体量、份额、趋势和供给，并知道哪些框的数据够下结论
- Stage: 第一版
- Status: active

### REQ-F30-01 · 导入与核对

- Story: US-F30-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F30-01 · 格式不对拒绝

- Parent: REQ-F30-01
- Priority: P0
- EARS:

```text
WHEN wen 在渠道调研页上传商品表与月销表（CSV），任一文件缺少必需列（商品表：渠道、fam、pid、title、来源、尺寸段、装、形态、台面材质、主色、柜体材质、元素、价格、评分、页面评论数；月销表：渠道、fam、pid、尺寸段、装、形态、月、VP、非VP、销量），或"月"不是 YYYY-MM、VP / 非VP / 销量不是非负数
THE SYSTEM SHALL 拒绝整次导入，列出缺少的列名或出错的行号与列，当前调研数据不变
```

### AC-F30-02 · 渠道不认识拒绝

- Parent: REQ-F30-01
- Priority: P0
- EARS:

```text
WHEN 任一行的"渠道"不是 Home Depot、Lowe's、Wayfair 之一（含 Amazon 或空值）
THE SYSTEM SHALL 拒绝整次导入，列出不认识的渠道值及其行数，当前调研数据不变
```

### AC-F30-03 · 重复与对不上拒绝

- Parent: REQ-F30-01
- Priority: P0
- EARS:

```text
WHEN 商品表中同一渠道 + pid 出现多行，或月销表中同一渠道 + pid + 尺寸段 + 月出现多行，或月销表的渠道 + pid 在商品表中不存在
THE SYSTEM SHALL 拒绝整次导入，按问题类型列出行数和前 20 条示例，当前调研数据不变
```

### AC-F30-04 · 未完整月只作参考

- Parent: REQ-F30-01
- Priority: P1
- EARS:

```text
WHEN 月销表含晚于最近一个完整自然月的月份
THE SYSTEM SHALL 这些行不计入任何指标，核对摘要中显示为"只作参考"及其行数
```

### AC-F30-05 · 核对摘要与确认

- Parent: REQ-F30-01
- Priority: P0
- EARS:

```text
WHEN 一次上传通过格式、渠道、重复检查
THE SYSTEM SHALL 先按渠道显示核对摘要（商品数、家族数、完整月范围、窗口销量合计、有月度销量占比、能落框销量占比、分框待确认商品数），wen 点"确认导入"后才生效；未确认或放弃时当前调研数据不变
```

### AC-F30-06 · 与已有渠道数据冲突

- Parent: REQ-F30-01
- Priority: P0
- EARS:

```text
WHEN 导入的某渠道在某月已有并入的评论 VP 数据（F28），且导入数据中来源为"类目节点"或"两者"的商品当月 VP + 非VP 评论数合计与已并入数据该月按评论 ID 去重的评论数相差超过 5%（差异 = |导入 − 已并入| ÷ 已并入；已并入为 0 而导入 > 0 也算不一致）
THE SYSTEM SHALL 在核对摘要中把该渠道标"与已有数据不一致"，逐月显示两边条数与差异百分比；wen 勾选确认该渠道后才能导入它，未勾选的渠道不导入
```

### AC-F30-07 · 按渠道替换并留版本

- Parent: REQ-F30-01
- Priority: P1
- EARS:

```text
WHEN wen 确认导入某渠道
THE SYSTEM SHALL 该渠道的调研数据替换为本次导入，上一版本保留并可在导入记录里查看（导入时间、文件名、商品数、月份范围、操作人）；本次未导入的渠道数据不变
```

### AC-F30-08 · 导入不改分析库

- Parent: REQ-F30-01
- Priority: P0
- EARS:

```text
WHEN 任一调研导入生效
THE SYSTEM SHALL 不写入其他渠道分析库（F28）；机会扫描、模型与回测、决策卡和预测台账的数字与导入前相同
```

### AC-F30-09 · 非操作者只能看

- Parent: REQ-F30-01
- Priority: P1
- EARS:

```text
WHEN 审批者或只读打开渠道调研页
THE SYSTEM SHALL 可查看全部调研结果；不显示上传、确认导入和分框确认入口，直接调用这些操作被拒绝并提示"无权限"
```

### REQ-F30-02 · 框与单元指标

- Story: US-F30-01
- Stage: 第一版
- Revision: 2
- Status: active

### AC-F30-10 · 分框

- Parent: REQ-F30-02
- Priority: P0
- EARS:

```text
WHEN 计算某渠道调研结果
THE SYSTEM SHALL 按商品的尺寸段、装、形态把月销表销量放进框（框 = 尺寸段 × 拆装 × 形态）；打标确认中已确认的分框标签优先于导入值；任一项为空、"未知"或尺寸段为"多尺寸未拆"的销量不进任何框，计入该渠道"待确认"销量
```

### AC-F30-11 · 门槛

- Parent: REQ-F30-02
- Priority: P0
- EARS:

```text
WHEN 显示框列表与单元表
THE SYSTEM SHALL 只列月均 ≥ 该渠道调研框门槛（品类配置分渠道设置，Home Depot / Lowe's / Wayfair 默认 100 件，AC-F30-35）的框和框内月均 ≥ 20 件的单元（单元 = 框 × 属性取值；月均 = 窗口销量 ÷ 窗口完整月数，窗口 = 导入数据中的完整月，本期为 2026-01 至 2026-10）；未达门槛的框只在列表底部显示个数与合计月均
```

### AC-F30-12 · 体量与份额

- Parent: REQ-F30-02
- Priority: P0
- EARS:

```text
WHEN 显示任一框或单元
THE SYSTEM SHALL 框显示月均与渠道内份额（框销量 ÷ 该渠道已落框销量），单元显示月均与框内份额（单元销量 ÷ 整框销量，分母含该属性未知的销量），并显示该框台面材质、元素、主色、柜体材质各自的已知占比
```

### AC-F30-13 · 趋势

- Parent: REQ-F30-02
- Priority: P0
- EARS:

```text
WHEN 显示可读框（AC-F30-20、AC-F30-21 之外）里的单元
THE SYSTEM SHALL 只用有月度的销量显示：逐月份额；近 3 月对前 3 月（窗口最后 3 个月与最前 3 个月的份额差，百分点）与走势（ln(近 3 份额 ÷ 前 3 份额) ≥ 0.3 为"抢份额"、≤ −0.3 为"丢份额"、其余"随框"，前 3 月份额为 0 而近 3 月 > 0 为"新出现"），并附框本身近 3 ÷ 前 3（≥ 1.15 框涨、≤ 0.87 框跌）；斜率（逐月份额的线性斜率，百分点 / 月）；波动（单元月销的变异系数）；窗口少于 6 个完整月时近 3 对前 3 与走势显示"—（月份不足）"
```

### AC-F30-14 · 新品

- Parent: REQ-F30-02
- Priority: P1
- EARS:

```text
WHEN 显示可读框里的单元
THE SYSTEM SHALL 显示新家族数（首评月在窗口内的家族；商品表没有"首评月"列时，以页面累计评论数 ≤ 窗口内评论数判定；没有月度的商品记非新）、其中"卖起来"的个数（进入月至窗口末在该单元的月均 ≥ 同框每家族月均）、各新家族进入的月份、新家族销量占比与同框新家族销量占比，并注明本次所用的新家族判定方式
```

### AC-F30-15 · 供给、价格、评分

- Parent: REQ-F30-02
- Priority: P0
- EARS:

```text
WHEN 显示单元
THE SYSTEM SHALL 显示家族数（窗口内有销量的家族）、价位段数（与 F29 相同的 7 段绝对价位）、单款 ÷ 同框（单元每家族月均 ÷ 同框每家族月均）、价格带（按销量加权 P25–P75）与溢价（单元加权中位价 ÷ 同框加权中位价）、评分（按页面评论数加权）与同框评分差；没有价格或评分时显示"无"，不按 0 计算
```

### AC-F30-16 · Amazon 同框对照

- Parent: REQ-F30-02
- Priority: P1
- EARS:

```text
WHEN 显示单元
THE SYSTEM SHALL 同时显示 Amazon 同尺寸段 × 形态 × 取值（不分拆装，元素按 F29 的 6 类对齐）最近 6 个完整月的家族数、价位段数、份额前 3 月 → 近 3 月及方向（ln 变化 ≥ 0.2 上升、≤ −0.2 下降、其余持平）；Amazon 没有该单元时显示"Amazon 无"
```

### AC-F30-17 · 无月度商品估算

- Parent: REQ-F30-02
- Priority: P0
- EARS:

```text
WHEN 某商品在月销表中没有行，但页面评论数 > 0
THE SYSTEM SHALL 按同渠道、来源为"两词"或"两者"、同评论数档（1–20、21–100、101–300、> 300 条）且有月度商品的"合计窗口销量 ÷ 合计页面评论数"换算出中估计；只用来源为"两词"的有月度商品同档系数换算出低估计；该档没有参照商品时不估算，计入"无法估算"商品数
```

### AC-F30-18 · 估算的使用与标注

- Parent: REQ-F30-02
- Priority: P0
- EARS:

```text
WHEN 框或单元含估算销量
THE SYSTEM SHALL 体量、份额、家族数、价格、评分用中估计，趋势与新品只用有月度的销量；在月均与份额旁标"估算"，同时显示低估计的月均与份额，以及有月度销量占比；框是否达门槛按中估计判断，低估计下框月均 < 该渠道框门槛时另标"低估计未达门槛"
```

### REQ-F30-03 · 可读性与证据等级

- Story: US-F30-01
- Stage: 第一版
- Revision: 2
- Status: active

### AC-F30-19 · 分框覆盖

- Parent: REQ-F30-03
- Priority: P0
- EARS:

```text
WHEN 计算框的可读性
THE SYSTEM SHALL 按分框覆盖（期望）= 本框已落框销量 ÷（本框已落框销量 + 待确认销量中按已知的尺寸段 / 装 / 形态可能落到本框、并按各候选框已落框销量比例分摊给本框的部分）计算；多尺寸未拆只分摊到其选项段里出现的尺寸段
```

### AC-F30-20 · 不下结论

- Parent: REQ-F30-03
- Priority: P0
- EARS:

```text
WHEN 某框分框覆盖 < 95%
THE SYSTEM SHALL 该框标"不下结论（分框覆盖 x%）"，框和框内单元只显示体量与份额，其他指标不显示
```

### AC-F30-21 · 趋势不下结论

- Parent: REQ-F30-03
- Priority: P0
- EARS:

```text
WHEN 某框分框覆盖 ≥ 95%，但有月度销量占比 < 60%
THE SYSTEM SHALL 该框标"趋势不下结论（有月度 x%）"，趋势与新品指标显示"—"，体量、份额、供给、价格、评分、Amazon 对照照常显示
```

### AC-F30-22 · 尚未导入

- Parent: REQ-F30-03
- Priority: P1
- EARS:

```text
WHEN 用户在渠道调研页选择一个还没有调研导入的渠道
THE SYSTEM SHALL 显示"尚未导入"；操作者另显示导入入口；不显示框列表
```

### AC-F30-23 · 数据不足

- Parent: REQ-F30-03
- Priority: P0
- EARS:

```text
WHEN 某渠道已导入，但没有任何框达到该渠道框门槛（默认月均 100 件）
THE SYSTEM SHALL 该渠道显示"数据不足"，给出已落框销量占比、未落框原因构成（尺寸段未知、多尺寸未拆、装未知、形态未知各占渠道销量的比例）和待确认商品数，不显示框列表
```

### AC-F30-24 · 历史观察

- Parent: REQ-F30-03
- Priority: P0
- EARS:

```text
WHEN 显示渠道调研结果
THE SYSTEM SHALL 页面和每个框标证据等级"历史观察"，不显示把握、分级或"上 / 不上"结论；注明商品范围（两词自然位前 300 + 类目节点商品）、换算系数、价格与评分口径、幸存者偏差，并说明只在同渠道、同框内比较
```

### AC-F30-25 · 与回测结论分开标

- Parent: REQ-F30-03
- Priority: P1
- EARS:

```text
WHEN 该渠道最近一次回测为"经回测（打折）"（AC-F19-06），且同一框 × 属性取值在该渠道机会扫描中有分级
THE SYSTEM SHALL 在单元行另列"回测"标记（证据等级与分级，可跳到机会扫描对应单元），与"历史观察"分开显示，不合并成一个等级
```

### REQ-F30-04 · 分框待确认与重算

- Story: US-F30-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F30-26 · 进确认队列

- Parent: REQ-F30-04
- Priority: P0
- EARS:

```text
WHEN 一次调研导入生效
THE SYSTEM SHALL 尺寸段、装、形态任一未知（含多尺寸未拆）的商品进入打标确认队列，原因为"分框未知（渠道调研）"，带渠道、窗口销量、标题、链接与原值（宽、选项段、颜色 / 台面 / 柜体原值），按窗口销量从大到小排；已有确认值的商品不进队列
```

### AC-F30-27 · 从调研页进队列

- Parent: REQ-F30-04
- Priority: P1
- EARS:

```text
WHEN wen 在渠道调研页点某渠道的"待确认 N 个"
THE SYSTEM SHALL 打开打标确认页，并已按该渠道和"分框未知（渠道调研）"筛选
```

### AC-F30-28 · 多尺寸未拆的确认

- Parent: REQ-F30-04
- Priority: P1
- EARS:

```text
WHEN wen 确认一个"多尺寸未拆"商品
THE SYSTEM SHALL 可选一个尺寸段（该商品全部销量计入该段）或"不进框"；选"不进框"的商品不再进入队列，其销量单列为"不进框"，不计入待确认
```

### AC-F30-29 · 确认后重算

- Parent: REQ-F30-04
- Priority: P0
- EARS:

```text
WHEN wen 在打标确认页确认或修改一个调研商品的尺寸段、装或形态
THE SYSTEM SHALL 该渠道调研结果重算，受影响框的指标、可读性和待确认数更新，页面显示重算时间
```

### AC-F30-30 · 再导入保留确认

- Parent: REQ-F30-04
- Priority: P1
- EARS:

```text
WHEN 同一渠道再次导入
THE SYSTEM SHALL 已确认的分框标签按渠道 + pid 保留并优先于新导入值，只有新的未知商品进入队列
```

### REQ-F30-05 · 系统内抓取（第二版）

- Story: US-F30-01
- Stage: 第二版
- Revision: 1
- Status: active

### AC-F30-31 · 关键词与类目节点抓取

- Parent: REQ-F30-05
- Priority: P1
- EARS:

```text
WHEN wen 在渠道调研页为某渠道发起抓取（关键词默认 "bathroom vanity"、"bathroom vanity with sink" 各取自然位前 300，加品类配置里的类目节点）并在费用评估后确认
THE SYSTEM SHALL Home Depot 直连、Lowe's / Wayfair 经 Bright Data 采集列表、商品页规格与评论，产出与导入相同字段的商品表和月销表，并按导入核对（REQ-F30-01）后生效
```

### AC-F30-32 · 每月续更

- Parent: REQ-F30-05
- Priority: P1
- EARS:

```text
WHEN 一个新的完整月结束后 wen 发起该渠道月度更新
THE SYSTEM SHALL 只补抓新月份评论与新进入范围的商品，已抓部分不重复请求、不重复计费
```

### REQ-F30-06 · 商品主图（可选列，revision 10）

- Story: US-F30-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F30-33 · 主图可选列

- Parent: REQ-F30-06
- Priority: P1
- EARS:

```text
WHEN wen 上传的渠道调研商品表带可选列"主图"（图片网址）
THE SYSTEM SHALL 按渠道 + pid 保存主图网址，打标确认（AC-F18-12）与决策卡渠道段代表产品（AC-F21-17）使用它；没有该列、或某行为空时照常导入、不报错，显示无图提示
```

### REQ-F30-07 · 小平台框门槛与样本少（revision 10）

- Story: US-F30-01
- Stage: 第一版
- Revision: 1
- Status: active

### AC-F30-34 · 样本少只作参考

- Parent: REQ-F30-07
- Priority: P0
- EARS:

```text
WHEN 某小平台框月均 ≥ 该渠道框门槛（默认 100 件）但 < 200 件
THE SYSTEM SHALL 该框和框内单元照常显示全部数据，可读性一栏统一显示"样本少，只作参考"（不显示"可读"、"不下结论"或"趋势不下结论"，不出走势结论文字）；月均 ≥ 200 件的框沿用 AC-F30-19～21 的可读性规则；决策卡渠道段（AC-F21-15）对这类框同样标"样本少，只作参考"
```

### AC-F30-35 · 框门槛分渠道可配

- Parent: REQ-F30-07
- Priority: P1
- EARS:

```text
WHEN wen 在品类配置里修改某小平台的调研框门槛
THE SYSTEM SHALL 该渠道调研结果按新门槛重算，页面注明所用门槛；Amazon 机会扫描框门槛仍为月均 200 件（AC-F20-01），不受影响
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

### NFR-014 · 渠道调研响应

- Applies-to: REQ-F30-01, REQ-F30-02, REQ-F30-04
- Revision: 1
- Status: active
- Measure: 三个渠道合计 ≤ 3,000 行商品、≤ 10,000 行月销的数据量下：上传到显示核对摘要 ≤ 60 秒；打开某渠道框列表 ≤ 5 秒；打开框内单元表 ≤ 3 秒；确认一个分框标签后该渠道重算完成 ≤ 30 秒

### NFR-015 · 白话用语

- Applies-to: REQ-F19-04, REQ-F20-03, REQ-F21-04, REQ-F21-06
- Revision: 1
- Status: active
- Measure: 给 wen 看的页面表头、指标名和提示里出现统计术语或自造词（b6、x5、AUC、p 值、扣偏差、k、T0、家族等）时，100% 带白话悬停说明（必要时另有白话列或结论句），术语保留在说明里；页面可见文案里的"家族"改称"款"（必要时括注"款（家族）"）；抽查模型与回测、机会扫描、决策卡、打标确认四页，不合格处为 0

## Retired（第一轮，revision 5 及以前）

第一轮需求契约（F01–F14，及其 US / REQ / AC；NFR-001～006）于 revision 6 整体 retired：第一轮 PRD v5 于 2026-10-27 被 wen 判定未达预期，第二轮以新《解题方案书》为准重写。原文见 git 历史（本文件 revision 5 版本）。这些 ID 永不复用。

