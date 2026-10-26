# 品类机会判定台 Requirements Contract

## Metadata

- work_type: feature
- workflow_mode: standard
- revision: 2
- scope: 第一期
- source_prd: PRD详细版.md
- status: active

> 本次范围为第一期（用户确认 D-8）：亚马逊美国 · 浴室柜，本机小网页。revision 2 新增截面模式（用户确认 D-23）：REQ-F01-03、REQ-F03-02、REQ-F05-02、REQ-F06-08、REQ-F07-03。第二期（迁服务器、多人与权限、第二个品类）与第三期（HDP、Lowe's、Wayfair）不在本契约内。数据接口约定 v1 见 `PRD详细版.md` §10.4。

## External capability configuration

| Capability | Credential owner | Configuration actor | Surface | Scope | Lifecycle | Stage | Requirement IDs |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| none | - | - | - | - | - | - | - |

## Capability prerequisites

| Prerequisite | Status | Owner | Evidence or deadline | Fallback | Stage | Requirement IDs |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| wen 的 Windows 电脑可运行本机小网页 | ready | wen | 旧技能包脚本（allocate_sales.py、tag_cached.py 等）曾在该机 D:/Codex 下运行，见 input/predecessor | 换一台可运行 Python 的电脑 | 第一期 | REQ-F01-01 |
| 截面数据包（同期上架的全部新品含低销量 + 观察月份月度数据，约定 v1.1） | committed | wen | 截止日期待 wen 确认（RA-020） | 先用已提供的 2026.06–09 头部数据跑通流程，截面回测在补齐失败样本前被阻断（AC-F03-04） | 第一期 | REQ-F01-03, REQ-F07-03 |
| 符合数据接口约定 v1 的第一期真实数据包 | committed | wen | wen 承诺下周提供，截止 2026-11-06（用户原话"数据包下周给"，2026-10-26） | 在此之前先用已提供的 2026.06–09 SKU 表与关键词表转换成约定格式跑通流程（用户确认）；缺评论痛点时先用另两类信号回测 | 第一期 | REQ-F01-01, REQ-F06-05 |

## Feature F01 · 数据导入与约定校验

### US-F01-01 · 导入数据包并知道能不能用于计算

- Role: 产品经理
- Goal: 把按约定准备的数据包导入系统，并立刻知道哪里不合格
- Value: 不合格的数据不会悄悄进入计算，避免得出错误结论
- Stage: 第一期
- Status: active

### REQ-F01-01 · 按数据接口约定 v1 校验导入的数据包

数据包为一个文件夹或 zip，内含约定 v1（PRD §10.4）规定的文件。系统逐文件、逐字段校验：必需文件是否存在、必需字段是否存在、主键是否唯一、日期与数值能否解析、月份覆盖是否满足约定。无法解析的行占该文件总行数 1% 及以下时记为警告并在计算中排除这些行，超过 1% 时记为阻断。

- Story: US-F01-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F01-01 · 生成逐项校验报告

- Parent: REQ-F01-01
- Priority: P0
- EARS:

```text
WHEN 产品经理导入一个数据包
THE SYSTEM SHALL 生成校验报告，逐个列出约定 v1 中每个文件和每个必需字段的检查结果（通过、警告或阻断）及受影响行数
```

### AC-F01-02 · 存在阻断项时禁止计算

- Parent: REQ-F01-01
- Priority: P0
- EARS:

```text
WHEN 校验报告中存在至少一个阻断项
THE SYSTEM SHALL 禁止对该数据包启动任何计算步骤，并显示每个阻断项的文件名、字段名和不超过 5 个示例行号
```

### AC-F01-03 · 警告行被排除并列出

- Parent: REQ-F01-01
- Priority: P1
- EARS:

```text
WHEN 某文件无法解析的行数大于 0 且不超过该文件总行数的 1%
THE SYSTEM SHALL 将该文件标为警告，在后续计算中排除这些行，并在校验报告中列出被排除的行号
```

### REQ-F01-02 · 只读保存数据包并识别重复导入

通过校验的数据包以只读副本保存，并计算文件指纹（SHA-256）；后续计算只读取该副本。每次导入生成数据包版本号。

- Story: US-F01-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F01-04 · 保存只读副本与指纹

- Parent: REQ-F01-02
- Priority: P0
- EARS:

```text
WHEN 数据包校验完成且没有阻断项
THE SYSTEM SHALL 保存该数据包的只读副本、每个文件的 SHA-256 指纹和新的数据包版本号
```

### AC-F01-05 · 重复导入不新建版本

- Parent: REQ-F01-02
- Priority: P1
- EARS:

```text
WHEN 产品经理导入的数据包与某个已有版本的全部文件指纹相同
THE SYSTEM SHALL 提示"该数据包已导入"并显示已有版本号，不创建新的数据包版本
```

### REQ-F01-03 · 识别数据包类型

数据包分两类：历史数据包（约定 v1，PRD §10.4 C1–C7）与截面数据包（约定 v1.1，PRD §10.4 S1–S3 加 C4、可选 C5–C7）。数据包根目录的清单文件声明类型，系统按对应约定校验。

- Story: US-F01-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F01-06 · 按类型校验

- Parent: REQ-F01-03
- Priority: P0
- EARS:

```text
WHEN 产品经理导入数据包
THE SYSTEM SHALL 按清单文件声明的类型（历史数据包或截面数据包）选择对应约定校验，清单缺失或类型无法识别时记为阻断
```

## Feature F02 · 字段约定确认

### US-F02-01 · 确认每个字段的含义和用法

- Role: 产品经理
- Goal: 逐个确认数据里每个字段代表什么、能不能用、怎么用
- Value: 解决"字段含义理解错"这一最大风险，确认后的口径每次都按同样规则执行
- Stage: 第一期
- Status: active

### REQ-F02-01 · 为每个字段生成约定草稿

草稿包含：含义、粒度（子体 / 父体 / SPU / 关键词 / 评论）、时点（当月值 / 快照及快照日期）、性质（平台实测 / 第三方估算 / 推导 / 人工标注）、建议用法（直接用 / 按规则用 / 回测不用）、来自本数据包的体检证据。

- Story: US-F02-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F02-01 · 显示字段约定草稿

- Parent: REQ-F02-01
- Priority: P0
- EARS:

```text
WHEN 数据包通过校验
THE SYSTEM SHALL 为数据包中的每个字段显示含义、粒度、时点、性质、建议用法和来自本数据包的体检证据
```

### REQ-F02-02 · 确认后形成带版本的字段约定

产品经理逐项或按建议批量确认、修改字段约定；保存后生成新的约定版本。未确认的字段不参与任何计算；标为"快照"的字段不得进入回测信号计算。

- Story: US-F02-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F02-02 · 保存生成新版本并留痕

- Parent: REQ-F02-02
- Priority: P0
- EARS:

```text
WHEN 产品经理确认或修改字段约定并保存
THE SYSTEM SHALL 生成新的字段约定版本号，并记录每个变动字段的修改前后值、操作人和时间
```

### AC-F02-03 · 按建议批量确认

- Parent: REQ-F02-02
- Priority: P1
- EARS:

```text
WHEN 产品经理选中一组字段并选择"按建议批量确认"
THE SYSTEM SHALL 一次确认所选字段，并把这些字段的确认来源记录为"批量确认"
```

### AC-F02-04 · 未确认字段不参与计算

- Parent: REQ-F02-02
- Priority: P0
- EARS:

```text
WHEN 存在尚未确认的字段时运行任一计算步骤
THE SYSTEM SHALL 不使用这些字段，并在该次计算结果中列出被排除的字段名
```

### AC-F02-05 · 快照字段不进入回测

- Parent: REQ-F02-02
- Priority: P0
- EARS:

```text
WHEN 某字段在当前字段约定中被标为"快照"
THE SYSTEM SHALL 拒绝把该字段用于回测信号计算，并在回测报告中列出被拒绝的字段名
```

### AC-F02-07 · 约定变更后标记需重算

- Parent: REQ-F02-02
- Priority: P1
- EARS:

```text
WHEN 产品经理保存新的字段约定版本
THE SYSTEM SHALL 把依赖旧约定版本的成败判定、信号、回测和排序结果标为"需重算"
```

### REQ-F02-03 · 新数据包只确认变化的字段

- Story: US-F02-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F02-06 · 只列出变化字段待确认

- Parent: REQ-F02-03
- Priority: P1
- EARS:

```text
WHEN 新导入的数据包与当前字段约定版本相比新增字段、缺少字段或字段类型改变
THE SYSTEM SHALL 只把这些变化的字段列为待确认，其余字段沿用当前约定版本
```

## Feature F03 · 自动体检与异常提示

### US-F03-01 · 知道数据哪里可疑

- Role: 产品经理
- Goal: 每次导入后看到一份固定的数据体检结果
- Value: 及早发现父子体口径混用、重新上架等问题，不让它们悄悄影响结论
- Stage: 第一期
- Status: active

### REQ-F03-01 · 运行固定体检项且不修改数据

体检项：首次评分日期早于上架日期超过 7 天的子体占比；同一父体内子体上架日期跨度超过 180 天的家族数；子体月销量估算低于"过去一个月购买"标签下界的比例（有标签时）；各属性维度"未知"占比；跨月父 ASIN 发生变化的子体数；主键重复数。预警阈值在品类配置中设置。

- Story: US-F03-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F03-01 · 输出体检结果

- Parent: REQ-F03-01
- Priority: P0
- EARS:

```text
WHEN 数据包通过校验
THE SYSTEM SHALL 运行 REQ-F03-01 列出的全部体检项，每项给出数值、分母和不超过 5 条样例记录
```

### AC-F03-02 · 超阈值预警需确认

- Parent: REQ-F03-01
- Priority: P1
- EARS:

```text
WHEN 任一体检项超过品类配置中的预警阈值
THE SYSTEM SHALL 在首页显示该预警，直到产品经理将其标为"已知晓"并填写说明
```

### AC-F03-03 · 体检不改源数据

- Parent: REQ-F03-01
- Priority: P0
- EARS:

```text
WHEN 体检运行完成
THE SYSTEM SHALL 保持数据包只读副本的每个文件指纹与导入时完全一致
```

### REQ-F03-02 · 截面数据包必须包含失败样本

截面模型要回答"新品命中概率"，新品清单必须包含没卖起来的商品；只含头部商品时回归会高估成功率（小试⑥）。

- Story: US-F03-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F03-04 · 疑似只含头部时阻断截面回测

- Parent: REQ-F03-02
- Priority: P0
- EARS:

```text
WHEN 截面数据包中观察月份月销量低于品类配置头部门槛（浴室柜 60 件）的新品占比为 0
THE SYSTEM SHALL 阻断截面回测，并提示"新品清单疑似只含头部商品，缺少失败样本"
```

## Feature F04 · 新品判定与 SPU 归并

### US-F04-01 · 准确知道哪些是真正的新品

- Role: 产品经理
- Goal: 把子体正确归并成 SPU，并区分真正的新品、新变体和疑似重新上架
- Value: 避免把老爆款的新颜色、新尺寸当成"新品成功"，命中率不虚高
- Stage: 第一期
- Status: active

### REQ-F04-01 · SPU 归并：优先用编号，否则规则建议加人工确认

SPU 定义为同一设计（含各尺寸、各颜色）。数据包提供已确认的 SPU 编号时直接使用；未提供时按"同品牌 + 同款式"规则生成合并建议，进入待审清单，确认后生效。

- Story: US-F04-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F04-01 · 有编号时直接归并

- Parent: REQ-F04-01
- Priority: P0
- EARS:

```text
WHEN 数据包提供 SPU 编号字段且该字段已在字段约定中确认
THE SYSTEM SHALL 按该编号把子体归并为 SPU
```

### AC-F04-02 · 无编号时生成合并建议

- Parent: REQ-F04-01
- Priority: P0
- EARS:

```text
WHEN 数据包未提供已确认的 SPU 编号
THE SYSTEM SHALL 按"同品牌 + 同款式"规则生成 SPU 合并建议，每条建议显示涉及的父 ASIN、子 ASIN 数量和匹配依据，并放入待审清单
```

### AC-F04-03 · 未确认建议不生效

- Parent: REQ-F04-01
- Priority: P0
- EARS:

```text
WHEN 某条合并建议尚未被产品经理确认
THE SYSTEM SHALL 在成败判定和回测中不使用该建议，涉及的子体按各自父 ASIN 分别计为 SPU
```

### AC-F04-04 · 批量确认合并建议

- Parent: REQ-F04-01
- Priority: P1
- EARS:

```text
WHEN 产品经理按匹配依据筛选合并建议并选择批量确认
THE SYSTEM SHALL 一次确认所选建议，并把确认来源记录为"批量确认"
```

### AC-F04-05 · 修改归并后标记需重算

- Parent: REQ-F04-01
- Priority: P1
- EARS:

```text
WHEN 产品经理拆分或修改一条已生效的 SPU 归并
THE SYSTEM SHALL 记录修改前后、操作人和时间，并把受影响的成败判定、信号和回测结果标为"需重算"
```

### REQ-F04-02 · 判定新 SPU、新变体与疑似重新上架

SPU 上架日取其全部子体上架日期的最早值；上架日期晚于所属 SPU 上架日的子体为"新变体"；SPU 的最早首次评分日期早于 SPU 上架日超过 7 天的为"疑似重新上架"。新 SPU 按上架日所在自然月划入批次。

- Story: US-F04-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F04-06 · SPU 上架日取最早子体

- Parent: REQ-F04-02
- Priority: P0
- EARS:

```text
WHEN 计算某 SPU 的上架日
THE SYSTEM SHALL 取该 SPU 内全部子体上架日期的最早值，并在 SPU 详情中显示该日期来自哪个子 ASIN
```

### AC-F04-07 · 新变体不计为新品

- Parent: REQ-F04-02
- Priority: P0
- EARS:

```text
WHEN 某子体的上架日期晚于其所属 SPU 的上架日
THE SYSTEM SHALL 将该子体标为"新变体"，不把它计为新 SPU
```

### AC-F04-08 · 标记疑似重新上架

- Parent: REQ-F04-02
- Priority: P0
- EARS:

```text
WHEN 某 SPU 的最早首次评分日期早于该 SPU 上架日超过 7 天
THE SYSTEM SHALL 将该 SPU 标为"疑似重新上架"
```

### AC-F04-09 · 按上架月份划分批次

- Parent: REQ-F04-02
- Priority: P0
- EARS:

```text
WHEN 生成新品批次
THE SYSTEM SHALL 把每个新 SPU 归入其上架日所在自然月的批次
```

## Feature F05 · 6 个月成败判定

### US-F05-01 · 按公司的成功线判定每个新品成没成

- Role: 产品经理
- Goal: 对每个新 SPU 按"上架 6 个月内 BSR 前 50 或累计 GMV 达 $20 万"判定成败
- Value: 用同一条成功线衡量竞品新品和自家立项，命中率可以比较
- Stage: 第一期
- Status: active

### REQ-F05-01 · 按品类配置的成功线判定

判定窗口为上架当月起的连续 6 个自然月（上架当月为第 1 个月）。满足其一即为"命中"：任一子 ASIN 在窗口内任一月的小类 BSR ≤ 品类配置阈值（浴室柜默认 50，BSR 取法按字段约定）；或 SPU 内各子体在窗口内的月销售额累计 ≥ 品类配置阈值（浴室柜默认 200,000 美元）。

- Story: US-F05-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F05-01 · BSR 达标判为命中

- Parent: REQ-F05-01
- Priority: P0
- EARS:

```text
WHEN 某新 SPU 的任一子 ASIN 在判定窗口内任一月的小类 BSR 小于或等于品类配置的 BSR 阈值
THE SYSTEM SHALL 将该 SPU 判为"命中"，并记录首次达成的月份和对应子 ASIN
```

### AC-F05-02 · 累计 GMV 达标判为命中

- Parent: REQ-F05-01
- Priority: P0
- EARS:

```text
WHEN 某新 SPU 各子体在判定窗口内的月销售额累计大于或等于品类配置的 GMV 阈值
THE SYSTEM SHALL 将该 SPU 判为"命中"，并记录累计金额和首次达成的月份
```

### AC-F05-03 · 不满 6 个月标为观察中

- Parent: REQ-F05-01
- Priority: P0
- EARS:

```text
WHEN 某新 SPU 从上架当月到数据最新月份不足 6 个自然月且尚未命中
THE SYSTEM SHALL 将其标为"观察中"，不计入任何命中率的分母
```

### AC-F05-04 · 满 6 个月未达标判为未命中

- Parent: REQ-F05-01
- Priority: P0
- EARS:

```text
WHEN 某新 SPU 的 6 个月判定窗口已结束、窗口内每月都有销量与 BSR 数据且两项都未达标
THE SYSTEM SHALL 将其判为"未命中"
```

### AC-F05-05 · 缺月份时标数据不全

- Parent: REQ-F05-01
- Priority: P1
- EARS:

```text
WHEN 某新 SPU 尚未命中且判定窗口内有任一月缺少销量或 BSR 数据
THE SYSTEM SHALL 将其标为"数据不全"，不计入命中率分母，并列出缺失的月份
```

### REQ-F05-02 · 截面口径成败判定

截面数据包中，上架于回看窗口内（默认最新观察月往前 12 个月）的新 SPU，在任一观察月满足以下任一条即为"截面命中"：任一子 ASIN 小类 BSR ≤ 品类配置 BSR 阈值；或 SPU 当月销售额 ≥ GMV 阈值 ÷ 判定窗口月数（浴室柜默认 200,000 ÷ 6 ≈ 33,333 美元）。否则为"截面未命中"。每个观察月记录 SPU 当时的上架月龄（上架当月为第 1 个月）。

- Story: US-F05-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F05-06 · 判为截面命中

- Parent: REQ-F05-02
- Priority: P0
- EARS:

```text
WHEN 截面数据包中某新 SPU 在任一观察月满足 REQ-F05-02 的任一条件
THE SYSTEM SHALL 将其判为"截面命中"，并记录达成月份与当时的上架月龄
```

### AC-F05-07 · 判为截面未命中

- Parent: REQ-F05-02
- Priority: P0
- EARS:

```text
WHEN 截面数据包中某新 SPU 在全部观察月都有数据且均不满足 REQ-F05-02 的条件
THE SYSTEM SHALL 将其判为"截面未命中"，并记录最后一个观察月的上架月龄
```

### AC-F05-08 · 截面口径单独标注

- Parent: REQ-F05-02
- Priority: P0
- EARS:

```text
WHEN 展示或导出截面口径的成败结果
THE SYSTEM SHALL 标注"截面口径（近似成功线）"，与 6 个月窗口口径区分
```

## Feature F06 · 信号计算

### US-F06-01 · 看到每个细分在每个月"当时"的信号

- Role: 产品经理
- Goal: 按细分看到需求在涨、新品进得去、现有产品没做好三类信号，以及现在常看的指标
- Value: 信号只用当时能看到的数据计算，回测才可信
- Stage: 第一期
- Status: active

### REQ-F06-01 · 按品类配置划分细分

每个子体按品类配置的维度与分档归入唯一细分；属性为"未知"的子体归入该维度的"未知"档。属性值来自父体回填的，信号表显示回填占比。

- Story: US-F06-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F06-01 · 每个子体归入唯一细分

- Parent: REQ-F06-01
- Priority: P0
- EARS:

```text
WHEN 计算细分
THE SYSTEM SHALL 按品类配置的维度与分档把每个子体归入唯一细分，属性为"未知"的子体归入该维度的"未知"档且不被丢弃
```

### AC-F06-02 · 显示父体回填占比

- Parent: REQ-F06-01
- Priority: P1
- EARS:

```text
WHEN 某细分内有子体使用了"父体回填"的属性值
THE SYSTEM SHALL 在该细分的信号表中显示使用回填值的子体占比
```

### REQ-F06-02 · 只用当时可见的数据

计算第 T 月的任一信号，只使用日期早于第 T 月第一天的记录：评论按评论日期，关键词按统计月份，月度商品数据按所属月份。

- Story: US-F06-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F06-03 · 按时点截断数据

- Parent: REQ-F06-02
- Priority: P0
- EARS:

```text
WHEN 计算第 T 月的任一信号
THE SYSTEM SHALL 只使用日期早于第 T 月第一天的评论、关键词月度数据和月度商品数据
```

### REQ-F06-03 · 需求在涨

信号值 = 按映射规则归入该细分的关键词，在第 T−4 至 T−1 月的搜索量合计，相对上一年同期 4 个月合计的同比变化。窗口月数在品类配置中可改。没有映射到任何细分维度的关键词（如泛词）不计入细分信号。所需月份的关键词数据缺失时，该细分该月信号为"无数据"。

- Story: US-F06-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F06-04 · 计算需求动量

- Parent: REQ-F06-03
- Priority: P0
- EARS:

```text
WHEN 计算第 T 月某细分的"需求在涨"
THE SYSTEM SHALL 按 REQ-F06-03 的口径计算同比变化，并显示参与计算的关键词数量
```

### REQ-F06-04 · 新品进得去

信号值 = 上架月份在第 T−12 至 T−7 月（判定窗口已在第 T 月之前结束，回看月数在品类配置中可改）的该细分新 SPU 中，命中数除以已判定数（不含观察中与数据不全）。

- Story: US-F06-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F06-05 · 计算细分新品命中率

- Parent: REQ-F06-04
- Priority: P0
- EARS:

```text
WHEN 计算第 T 月某细分的"新品进得去"
THE SYSTEM SHALL 按 REQ-F06-04 的口径计算命中率，并同时显示分子和分母
```

### REQ-F06-05 · 现有产品没做好

用评论日期早于第 T 月的评论计算两项：被标为结构类痛点的评论占比；"高销低评"商品销量占比——高销指第 T−1 月销量处于该细分前 25%，低评指其评论日期早于第 T 月的评论平均星级低于 4.0。子体级评论计入该子体所在细分；父体级评论计入该父体第 T−1 月销量占比最大的子体所在细分，不重复计入其他细分。

- Story: US-F06-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F06-06 · 计算结构类痛点占比

- Parent: REQ-F06-05
- Priority: P0
- EARS:

```text
WHEN 计算第 T 月某细分的结构类痛点占比
THE SYSTEM SHALL 以该细分评论日期早于第 T 月的评论为分母、其中标为结构类痛点的评论为分子计算占比，并显示分子和分母
```

### AC-F06-07 · 计算高销低评销量占比

- Parent: REQ-F06-05
- Priority: P1
- EARS:

```text
WHEN 计算第 T 月某细分的"高销低评"
THE SYSTEM SHALL 按 REQ-F06-05 的口径计算高销低评商品的销量占该细分第 T−1 月销量的比例，并显示涉及的商品数
```

### REQ-F06-06 · 产品经理现用指标作为候选信号

单位 ASIN 贡献 = 细分第 T−1 月销量 ÷ 该细分当月有销量的子 ASIN 数；属性溢价 = 细分第 T−1 月销量加权均价（月销售额 ÷ 月销量）÷ 同宽度档销量加权均价 − 1；属性趋势 = 细分第 T−3 至 T−1 月销量份额相对第 T−6 至 T−4 月的变化；低分高销 = REQ-F06-05 的高销低评销量占比。

- Story: US-F06-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F06-08 · 计算四个现用指标

- Parent: REQ-F06-06
- Priority: P1
- EARS:

```text
WHEN 计算第 T 月的信号
THE SYSTEM SHALL 按 REQ-F06-06 的口径同时计算单位 ASIN 贡献、属性溢价、属性趋势和低分高销，并在信号表中标为"候选信号"
```

### REQ-F06-07 · 类型属性按父体回填

品类配置中列为"类型属性"的维度（浴室柜：形态、安装方式、元素、台面形态、柜体材质、台面材质、台盆材质），子体没有确认值、但有父体候选值时，使用父体候选值并标为"父体回填"（D-10）。颜色、尺寸、盆数等随变体变化的维度不回填。

- Story: US-F06-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F06-09 · 类型属性使用父体值并标记

- Parent: REQ-F06-07
- Priority: P0
- EARS:

```text
WHEN 某子体的类型属性没有子体确认值且有父体候选值
THE SYSTEM SHALL 在细分划分中使用该父体候选值，并把该属性标为"父体回填"
```

### AC-F06-10 · 随变体变化的维度不回填

- Parent: REQ-F06-07
- Priority: P0
- EARS:

```text
WHEN 某子体的颜色、尺寸或盆数没有子体确认值
THE SYSTEM SHALL 不使用父体值回填，并把该子体归入该维度的"未知"档
```

### REQ-F06-08 · 截面模式下的信号口径

截面模式中，新品批次与结果在同一观察期内，"新品进得去"会用到同期结果，因此不计算；"需求在涨"与"现有产品没做好"仍按批次上架月之前的数据计算，缺数据时为"无数据"；四个现用指标只用上架早于新品回看窗口的老品在观察月份的数据计算。

- Story: US-F06-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F06-11 · 截面模式不算新品进得去

- Parent: REQ-F06-08
- Priority: P0
- EARS:

```text
WHEN 在截面数据包上计算信号
THE SYSTEM SHALL 不计算"新品进得去"，并在信号表中标注"截面模式不适用"
```

### AC-F06-12 · 现用指标只用老品

- Parent: REQ-F06-08
- Priority: P0
- EARS:

```text
WHEN 在截面数据包上计算四个现用指标
THE SYSTEM SHALL 只使用上架日期早于新品回看窗口的商品数据，并在信号表中显示参与计算的老品数量
```

## Feature F07 · 时间切分回测

### US-F07-01 · 用之前先知道信号到底准不准

- Role: 产品经理
- Goal: 用历史新品批次检验信号和规则能不能挑出更容易成功的细分
- Value: 只有经过检验的判定卡才拿去指导立项，避免凭感觉定指标
- Stage: 第一期
- Status: active

### REQ-F07-01 · 时间切分与达标判定

按上架月份排序已判定的批次，默认前 2/3 批次定规则、后 1/3 批次检验（品类配置可改，批次数不能整除时检验组向下取整、至少 1 个批次）。在检验批次中，按信号或规则排序的前 20% 细分（细分数 × 20% 向上取整，至少 1 个）新品命中率 ≥ 全类目平均命中率的 2 倍，且高于 REQ-F06-06 四个现用指标各自排序的同口径命中率，结论为"达标"，否则为"未达标"。检验批次新 SPU 少于 20 个的细分为"样本不足"，不参与达标评估。区间口径：命中率用 Wilson 90% 区间；倍数用对细分有放回重抽样 1000 次的 90% 区间，随机种子固定，保证可复现。

- Story: US-F07-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F07-01 · 列出定规则与检验批次

- Parent: REQ-F07-01
- Priority: P0
- EARS:

```text
WHEN 产品经理启动回测
THE SYSTEM SHALL 按上架月份把已判定批次分为定规则组和检验组，并在回测报告中列出两组的批次月份范围
```

### AC-F07-02 · 计算命中率倍数与区间

- Parent: REQ-F07-01
- Priority: P0
- EARS:

```text
WHEN 回测完成
THE SYSTEM SHALL 对每个信号和每条组合规则，给出检验组中排名前 20% 细分的命中率、全类目平均命中率、两者倍数、样本量和 90% 区间
```

### AC-F07-03 · 判定达标

- Parent: REQ-F07-01
- Priority: P0
- EARS:

```text
WHEN 检验组中判定卡排名前 20% 细分的命中率大于或等于全类目平均命中率的 2 倍，且高于任一现有单指标排序的前 20% 细分命中率
THE SYSTEM SHALL 将回测结论标为"达标"
```

### AC-F07-04 · 未达标给出原因

- Parent: REQ-F07-01
- Priority: P0
- EARS:

```text
WHEN 达标条件中任一项不满足
THE SYSTEM SHALL 将回测结论标为"未达标"，并按"数据不足""细分样本不足""信号无区分度"分类给出原因及对应数值
```

### AC-F07-05 · 样本不足的细分不参与评估

- Parent: REQ-F07-01
- Priority: P0
- EARS:

```text
WHEN 某细分在检验组中的新 SPU 少于 20 个
THE SYSTEM SHALL 将该细分标为"样本不足"，不纳入达标评估，并提示可合并的相邻分档
```

### AC-F07-08 · 批次太少时不切分

- Parent: REQ-F07-01
- Priority: P0
- EARS:

```text
WHEN 已判定（命中或未命中）的新 SPU 批次少于 3 个
THE SYSTEM SHALL 不进行切分，直接给出"未达标：数据不足"，并显示已判定批次数
```

### REQ-F07-02 · 控制可观察的干扰因素

回测同时纳入六项干扰因素：品牌在上架前是否已有命中 SPU、上架月份、相对细分销量加权均价的价格位置、变体数、配送方式、疑似重新上架；不可观察的广告投入、站外引流写为局限。

- Story: US-F07-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F07-06 · 报告控制前后对比

- Parent: REQ-F07-02
- Priority: P0
- EARS:

```text
WHEN 回测计算信号与命中的关系
THE SYSTEM SHALL 纳入 REQ-F07-02 的六项干扰因素，并在回测报告中列出控制前后每个信号的效果对比
```

### AC-F07-07 · 固定列出局限

- Parent: REQ-F07-02
- Priority: P1
- EARS:

```text
WHEN 生成回测报告
THE SYSTEM SHALL 在结论旁列出"广告投入、站外引流未纳入"的局限说明
```

### REQ-F07-03 · 截面模式回测

在截面数据包上：按上架月份排序新 SPU 批次，前 2/3 批次建模、后 1/3 检验；模型以"截面命中"为结果，纳入细分属性、上架月龄和 REQ-F07-02 的干扰因素；按模型给出的"标准月龄（默认 6 个月）命中概率"对细分排序，用与 REQ-F07-01 相同的 2 倍与前 20% 口径评估，基线为只用老品计算的四个现用指标。同一品类同时有历史模式结论时，以历史模式为准。

- Story: US-F07-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F07-09 · 截面回测划分批次并控制月龄

- Parent: REQ-F07-03
- Priority: P0
- EARS:

```text
WHEN 产品经理在截面数据包上启动回测
THE SYSTEM SHALL 按上架月份把新 SPU 批次分为建模组和检验组，模型纳入上架月龄与六项干扰因素，并在报告中列出两组批次范围
```

### AC-F07-10 · 截面回测评估口径

- Parent: REQ-F07-03
- Priority: P0
- EARS:

```text
WHEN 截面回测完成
THE SYSTEM SHALL 按标准月龄命中概率对细分排序，给出检验组前 20% 细分的截面命中率、全类目平均、倍数、样本量和 90% 区间，并与只用老品计算的四个现用指标排序比较
```

### AC-F07-11 · 截面达标单独标注

- Parent: REQ-F07-03
- Priority: P0
- EARS:

```text
WHEN 截面回测满足 2 倍且优于四个现用指标
THE SYSTEM SHALL 将结论标为"达标（截面）"，并在判定卡、排序、锦囊和导出文件上显示"截面口径，待历史回测确认"
```

### AC-F07-12 · 历史模式优先

- Parent: REQ-F07-03
- Priority: P1
- EARS:

```text
WHEN 同一品类同时存在历史模式与截面模式的回测结论
THE SYSTEM SHALL 以历史模式结论决定判定卡状态，并在回测页并列显示两种结论
```

## Feature F08 · 判定卡与立项锦囊

### US-F08-01 · 拿到能直接用的立项规则

- Role: 产品经理
- Goal: 得到"在什么条件下立项、观察或放弃"的规则，并知道每条规则的依据
- Value: 指标、阈值和动作被固定下来，换人、换品类都能按同样标准判断
- Stage: 第一期
- Status: active

### REQ-F08-01 · 由回测生成判定卡与锦囊

- Story: US-F08-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F08-01 · 达标时生成判定卡新版本

- Parent: REQ-F08-01
- Priority: P0
- EARS:

```text
WHEN 回测结论为"达标"
THE SYSTEM SHALL 生成判定卡新版本，列出入选信号、阈值、权重及回测依据（批次范围、样本量、命中率倍数）
```

### AC-F08-02 · 锦囊内容完整

- Parent: REQ-F08-01
- Priority: P0
- EARS:

```text
WHEN 生成锦囊
THE SYSTEM SHALL 使每条锦囊包含触发条件、建议动作（立项候选、观察或放弃）、预期命中率区间、依据批次、样本量和状态
```

### AC-F08-03 · 未达标时标为未验证

- Parent: REQ-F08-01
- Priority: P0
- EARS:

```text
WHEN 回测结论为"未达标"
THE SYSTEM SHALL 将判定卡标为"未验证"，并在所有展示判定卡、排序或锦囊的页面显示"未验证，不可作为立项结论"
```

## Feature F09 · 细分排序与区间

### US-F09-01 · 每月看到先做哪些细分

- Role: 产品经理
- Goal: 每月得到全部细分的排序、区间和对应锦囊
- Value: 立项评审时有一份按同一标准排好的候选清单
- Stage: 第一期
- Status: active

### REQ-F09-01 · 按当前判定卡排序

得分相同的细分，按样本量从大到小、再按细分名称排序，保证同一输入排序结果一致。

- Story: US-F09-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F09-01 · 显示排序与区间

- Parent: REQ-F09-01
- Priority: P0
- EARS:

```text
WHEN 产品经理对某月运行更新
THE SYSTEM SHALL 按当前判定卡对全部细分排序，每个细分显示排名、得分、预期命中率区间、样本量和适用的锦囊
```

### AC-F09-02 · 样本不足的细分排在后面

- Parent: REQ-F09-01
- Priority: P1
- EARS:

```text
WHEN 某细分的样本量少于 20 个新 SPU
THE SYSTEM SHALL 在排序中把该细分标为"样本不足"并排在全部有效细分之后
```

## Feature F10 · 预测台账与对账

### US-F10-01 · 记录预测和决定，6 个月后对账

- Role: 产品经理
- Goal: 保存每月的排序与自己的立项决定，到期自动对账
- Value: 逐步积累自家结果，检验判定卡在真实决策中是否有效
- Stage: 第一期
- Status: active

### REQ-F10-01 · 每月快照不可改

- Story: US-F10-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F10-01 · 自动保存月度快照

- Parent: REQ-F10-01
- Priority: P0
- EARS:

```text
WHEN 某月排序生成
THE SYSTEM SHALL 自动保存当月排序、锦囊和判定卡版本号的快照，且快照保存后不允许修改
```

### REQ-F10-02 · 记录立项决定与补录在研立项

- Story: US-F10-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F10-02 · 记录立项决定

- Parent: REQ-F10-02
- Priority: P0
- EARS:

```text
WHEN 产品经理记录一项立项决定
THE SYSTEM SHALL 保存决定（立项或不立项）、关联细分、理由、对应快照月份、操作人和时间
```

### AC-F10-03 · 补录在研立项

- Parent: REQ-F10-02
- Priority: P1
- EARS:

```text
WHEN 产品经理补录一项在研立项
THE SYSTEM SHALL 保存其立项日期和关联细分，并将该记录标为"补录"
```

### REQ-F10-03 · 到期对账

- Story: US-F10-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F10-04 · 竞品新品对账

- Parent: REQ-F10-03
- Priority: P0
- EARS:

```text
WHEN 某快照月份之后对应批次的新 SPU 已全部完成 6 个月成败判定
THE SYSTEM SHALL 生成对账结果，列出快照中排名前 20% 细分的实际新品命中率、全类目平均命中率、两者倍数及回测时的预期区间
```

### AC-F10-05 · 自家立项对账

- Parent: REQ-F10-03
- Priority: P1
- EARS:

```text
WHEN 产品经理录入某项自家立项上架后的月度销量、销售额与 BSR
THE SYSTEM SHALL 按品类配置的成功线判定其命中与否，并与当时的排序和锦囊并列展示
```

### REQ-F10-04 · 自动备份与恢复

每次导出当月结果后，把台账、策略库、字段约定、品类配置和全部确认记录备份到产品经理指定的目录；可从任一备份恢复。

- Story: US-F10-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F10-06 · 导出后自动备份

- Parent: REQ-F10-04
- Priority: P0
- EARS:

```text
WHEN 产品经理导出当月结果完成
THE SYSTEM SHALL 自动在指定目录生成一份带时间戳的备份，并显示备份完成时间
```

### AC-F10-07 · 备份失败不删旧备份

- Parent: REQ-F10-04
- Priority: P0
- EARS:

```text
WHEN 自动备份执行时备份目录不可写或备份过程失败
THE SYSTEM SHALL 显示失败原因和上次成功备份的时间，且不删除或改动任何已有备份
```

### AC-F10-08 · 从备份恢复

- Parent: REQ-F10-04
- Priority: P0
- EARS:

```text
WHEN 产品经理选择一个备份并确认恢复
THE SYSTEM SHALL 把台账、策略库、字段约定、品类配置和确认记录恢复为该备份时的内容，并显示所恢复备份的时间
```

## Feature F11 · 策略库

### US-F11-01 · 规则有版本、有状态

- Role: 产品经理
- Goal: 维护判定规则和经验规则，知道每条规则验证到哪一步
- Value: 经验和数据结论被沉淀下来，换品类时可以复用
- Stage: 第一期
- Status: active

### REQ-F11-01 · 规则版本与三种状态

规则状态：未验证经验（人工新增）、历史观察（由达标回测生成）、已验证（在台账对账中命中率倍数 ≥ 2）。任何修改生成新版本并保留历史；修改条件或动作的新版本状态重置为"未验证经验"。

- Story: US-F11-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F11-01 · 新增经验规则

- Parent: REQ-F11-01
- Priority: P0
- EARS:

```text
WHEN 产品经理新增一条经验规则
THE SYSTEM SHALL 要求填写条件、动作和理由，并将其状态设为"未验证经验"
```

### AC-F11-02 · 回测生成的规则为历史观察

- Parent: REQ-F11-01
- Priority: P0
- EARS:

```text
WHEN 一条规则由结论为"达标"的回测生成
THE SYSTEM SHALL 将其状态设为"历史观察"
```

### AC-F11-03 · 对账达标升为已验证

- Parent: REQ-F11-01
- Priority: P1
- EARS:

```text
WHEN 某条"历史观察"规则在一次台账对账中的命中率倍数大于或等于 2
THE SYSTEM SHALL 将其状态设为"已验证"，并记录依据的对账月份
```

### AC-F11-04 · 修改生成新版本

- Parent: REQ-F11-01
- Priority: P0
- EARS:

```text
WHEN 产品经理修改任一规则
THE SYSTEM SHALL 生成该规则的新版本，并保留历史版本、修改理由、操作人和时间
```

### AC-F11-05 · 改条件或动作后状态重置

- Parent: REQ-F11-01
- Priority: P1
- EARS:

```text
WHEN 产品经理修改某规则的条件或动作并保存
THE SYSTEM SHALL 将该规则新版本的状态设为"未验证经验"，旧版本保留原状态
```

## Feature F12 · 报告导出

### US-F12-01 · 把结果发给老板和下游

- Role: 产品经理
- Goal: 一键导出当月结果
- Value: 第一期没有服务器，也能把结论发给老板和开发、采购、运营
- Stage: 第一期
- Status: active

### US-F12-02 · 不装系统也能看报告

- Role: 结果接收方
- Goal: 在自己的电脑上直接打开报告，看到结论和依据
- Value: 不需要安装或登录本系统
- Stage: 第一期
- Status: active

### REQ-F12-01 · 导出 Excel 与单文件网页报告

- Story: US-F12-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F12-01 · 导出 Excel

- Parent: REQ-F12-01
- Priority: P0
- EARS:

```text
WHEN 产品经理导出当月结果
THE SYSTEM SHALL 生成一个 Excel 文件，包含细分排序、锦囊、判定卡版本、回测摘要、台账以及数据包、字段约定和品类配置的版本号
```

### AC-F12-02 · 未验证标记出现在导出物首页

- Parent: REQ-F12-01
- Priority: P0
- EARS:

```text
WHEN 判定卡为"未验证"时导出 Excel 或网页报告
THE SYSTEM SHALL 在导出文件的首页显示"未验证，不可作为立项结论"
```

### REQ-F12-02 · 网页报告离线可读

- Story: US-F12-02
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F12-03 · 单个 HTML 文件离线打开

- Parent: REQ-F12-02
- Priority: P0
- EARS:

```text
WHEN 结果接收方在未安装本系统且没有网络的 Windows 或 macOS 电脑上用 Chrome、Edge 或 Safari 打开导出的网页报告
THE SYSTEM SHALL 使该单个 HTML 文件显示与导出时一致的排序、锦囊、回测摘要和版本信息
```

## Feature F13 · 品类配置

### US-F13-01 · 换品类只加配置

- Role: 产品经理
- Goal: 用配置描述一个品类，而不是改程序
- Value: 第二期接第二个品类时直接复用
- Stage: 第一期
- Status: active

### REQ-F13-01 · 品类配置项与版本

配置项：站点、类目节点、细分维度与分档、成功线参数（BSR 阈值、GMV 阈值、判定窗口月数）、关键词映射规则、信号窗口与回看期、回测切分比例、体检预警阈值。浴室柜默认：美国站、节点 6810202011、BSR 阈值 50、GMV 阈值 200,000 美元、判定窗口 6 个月。

- Story: US-F13-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F13-01 · 新建品类配置

- Parent: REQ-F13-01
- Priority: P0
- EARS:

```text
WHEN 产品经理新建品类配置
THE SYSTEM SHALL 要求填写 REQ-F13-01 列出的全部配置项，并提供浴室柜配置作为可复制的模板
```

### AC-F13-02 · 修改配置标记需重算

- Parent: REQ-F13-01
- Priority: P0
- EARS:

```text
WHEN 产品经理修改某品类配置并保存
THE SYSTEM SHALL 生成新的配置版本，并把依赖旧版本的成败判定、信号和回测结果标为"需重算"
```

## Feature F14 · 运行记录与用时统计

### US-F14-01 · 知道每一步花了多久

- Role: 产品经理
- Goal: 看到首跑和每次月更在系统内花了多少时间
- Value: 检验"首跑 ≤ 5 个工作日、月更 ≤ 半天"的效率目标
- Stage: 第一期
- Status: active

### REQ-F14-01 · 记录步骤用时并汇总

首跑用时 = 某品类首次导入到首次生成回测报告之间的工作日数（周一至周五）；月更用时 = 某月导入到该月导出之间的时长。

- Story: US-F14-01
- Stage: 第一期
- Revision: 1
- Status: active

### AC-F14-01 · 记录每步起止

- Parent: REQ-F14-01
- Priority: P1
- EARS:

```text
WHEN 导入、字段确认、体检、SPU 审核、计算、回测或导出中任一步骤开始或结束
THE SYSTEM SHALL 记录该步骤的开始时间、结束时间和操作人
```

### AC-F14-02 · 汇总首跑与月更用时

- Parent: REQ-F14-01
- Priority: P1
- EARS:

```text
WHEN 产品经理查看用时统计
THE SYSTEM SHALL 按 REQ-F14-01 的口径显示每个品类的首跑用时和每次月更用时
```

## Non-functional requirements

### NFR-001 · 同样输入得到同样结果

- Revision: 1
- Status: active
- Measure: 同一数据包版本、同一字段约定版本、同一品类配置版本连续运行两次，成败判定、信号、回测、排序和锦囊的全部数值与文本 100% 一致

### NFR-002 · 本机数据可备份与恢复

- Applies-to: REQ-F10-04
- Revision: 1
- Status: active
- Measure: 每次导出当月结果后自动备份到产品经理指定的目录；从任一备份恢复后，台账、策略库、字段约定与确认记录与备份时逐条一致（100%）

### NFR-003 · 每个结论可追溯

- Revision: 1
- Status: active
- Measure: 100% 的成败判定、排序行和锦囊都能查到所用的数据包版本、字段约定版本、品类配置版本和来源记录主键

### NFR-004 · 第二期可迁服务器不重做业务逻辑

- Revision: 1
- Status: active
- Measure: 每条记录都带操作人与时间；不经网页界面、只用命令行对同一输入运行全部计算，结果与网页运行 100% 一致

### NFR-005 · 本机计算时长

- Applies-to: REQ-F07-01
- Revision: 1
- Status: active
- Measure: 在 8 GB 内存的 Windows 电脑上，浴室柜规模数据（24 个月月度商品数据、12 个新品批次及其轨迹、对应评论）完成一次从计算到回测报告的全流程不超过 30 分钟

### NFR-006 · 仅本机访问

- Revision: 1
- Status: active
- Measure: 第一期网页服务只在本机地址监听，同一局域网内其他电脑访问失败；第一期不调用任何外部服务，数据不离开本机
