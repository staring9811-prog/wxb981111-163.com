# Codex 接入：读数据、提调整、人来审核

程序启动后在本机开一个 JSON 接口 `http://127.0.0.1:8765/api/v1`，给 Codex 之类的工具用。原则只有一条：

> **数据源不动。** 工具只能读数据和提交“调整提议”；提议在「数据审核」页由人确认、改值或驳回后才生效。导入的数据包行一个字都不改，已确认的调整随时可以撤销，撤销后回到原值。

## 令牌

- 第一次启动时在数据目录生成 `data\api_token.txt`，重启不变。删掉这个文件再启动会换新令牌。
- 查看：命令行 `oppo api-token`，或「数据审核」页顶部的「Codex 接入」折叠块。
- 每个请求都要带请求头：`Authorization: Bearer <令牌>`。网页用的启动令牌对接口无效，接口令牌也打不开网页写操作，两者分开。
- 接口只在本机监听，不接受跨站请求。

## 接口

| 方法 | 地址 | 作用 |
|---|---|---|
| GET | `/api/v1/info` | 品类、数据包列表、每个当前数据包可调整的文件和字段、证据状态取值、调整计数 |
| GET | `/api/v1/packages/{数据包}/rows?file=C4&child=…&month=…&filter=字段:值&limit=100&offset=0` | 读一个文件的行：`values` 是审核后的值，`imported_if_changed` 列出与原值不同的字段及原值，`pending` 是这一行待审核的提议 |
| POST | `/api/v1/packages/{数据包}/adjustments` | 提交调整提议（见下） |
| GET | `/api/v1/adjustments?package=&status=&file=&field=&source=&batch=&child=&limit=&offset=` | 查看提议及审核结果 |
| POST | `/api/v1/adjustments/withdraw` | 撤回自己还没被审核的提议：`{"codes": ["A-00001"]}` |

`{数据包}` 填编号（`P-0001`）；省略或填 `current` 以外的值都按编号找。`file` 是数据包里的文件代号：历史包 C1–C4，截面包 S1、S2、S3、C4。

**没有确认接口。** 确认只能在「数据审核」页或 `oppo adjust confirm` 由人完成。

## 提交调整

```json
POST /api/v1/packages/P-0001/adjustments
{
  "source": "Codex",
  "items": [
    {"file": "C4", "child": "B0XXXXXXXX", "field": "形态", "value": "悬浮式",
     "reason": "主图为壁挂安装，标题含 wall mounted"},
    {"file": "C4", "child": "B0XXXXXXXX", "field": "形态证据状态", "value": "子体确认"},
    {"file": "S1", "child": "B0XXXXXXXX", "field": "上架日期", "value": "2026-03-04",
     "reason": "子体详情页 Date First Available"},
    {"file": "S1", "child": "B0XXXXXXXX", "month": "202607", "field": "子体月销量", "value": "35"}
  ]
}
```

- `field` 用字段约定里的中文名。C4 的字段是属性维度名（如 `形态`）或 `维度 + 证据状态`（如 `形态证据状态`）；证据状态只能是 `子体确认 / 父体回填 / 父体候选 / 信息不足 / 冲突`。
- C1/S1、C3/S3 可带 `month`（`202607` 或 `2026-07`）；不带则作用于该子体的所有月份。
- `value` 传 `""` 表示清空。日期 `YYYY-MM-DD`，数值直接写数字。
- 一次最多 5000 条。返回里 `created` 是新编号（`A-00001`），`errors` 逐条列出没收下的项和原因（子 ASIN 不在数据包里、字段不存在、值类型不对等）；收下的部分照常记录。
- 同一个位置（文件 + 子 ASIN + 月份 + 字段）再提一次，旧的待审核提议自动变为“已撤回”，以新的为准。
- 每次提交记为一个批次 `B-0001`，审核页可按批次筛选、全部确认或全部驳回。

## 审核（人做）

- 网页：左侧「数据审核」。待审核里逐条「确认 / 改值 / 驳回」，或勾选后批量，或按筛选「全部确认」。已确认里可「撤销」。
- 命令行：
  ```
  oppo adjust list --status 待审核
  oppo adjust confirm --codes A-00001 A-00002
  oppo adjust confirm --codes A-00003 --value 落地式     # 改值后确认
  oppo adjust confirm --all-pending --batch B-0001
  oppo adjust reject --codes A-00004 --note 证据不足
  oppo adjust revoke --codes A-00001
  oppo adjust propose --file items.json --source Codex   # 不走接口，直接读 JSON 文件
  ```
- 确认或撤销后：数据体检立即按新值刷新；成败判定、信号、回测标为“需重算”，在工作台点「全部重算」后更新。每一步都记入变更日志（谁、何时、原值、提议值、生效值）。

## 建议 Codex 的工作方式

1. `GET /info` 拿到当前数据包和可调整字段。
2. 用 `rows` 加 `filter=形态证据状态:信息不足` 之类的条件分页拉出要判断的行，`limit` 最大 1000。
3. 判断后分批提交，`reason` 写清依据（标题、五点、图片），审核的人靠它决定。
4. 提交后告诉人去「数据审核」页。不要试图绕过审核，接口里没有这条路。
