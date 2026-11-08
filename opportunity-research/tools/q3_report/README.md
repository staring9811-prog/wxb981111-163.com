# Q3 浴室柜 · 市场与渠道数据报告（生成脚本）

一条命令重新生成报告：

```bash
cd opportunity-research/tools/q3_report
python run.py            # 需要 Python 3.10+，依赖 openpyxl、numpy、pandas
```

输出：`data/Q3浴室柜_市场与渠道数据报告.html`（单文件，可直接发同事）。

## 数据放哪

数据不入库。把 wen 保管的数据包 `q3_report_data.zip` 解压到本目录，得到 `data/`：

```
data/
├── pdt.sqlite3                 Amazon 月度快照、打标、小平台研究表（约 100MB）
├── kw.json                     卖家精灵 339 个浴室柜词的月度搜索量
├── amz_width.pkl               Amazon 子体柜宽（尺寸段用）
├── tag.xlsx                    wen 的小平台打标
├── tag_override.csv            ★ 人工改标（最高优先级）
├── clean/hd.pkl wf.pkl lw.pkl lw_fix.pkl   小平台干净父体数据
└── input_data_v2/渠道关键词/大词/三平台_商品表.csv
```

也可以放别处，用环境变量指过去：`Q3_DATA=/path/to/data python run.py`。

## 在报告里直接改标签（推荐）

```bash
python serve.py          # 浏览器自动打开 http://127.0.0.1:8765
```

点热力表或交叉筛选的任一格子 → 弹出商品清单 → 拆装 / 形态 / 尺寸 / 台面 / 柜体 / 元素 都是下拉框 → 改完点“保存改标并重算”。
保存时同时写三处，然后整份报告重算、页面自动刷新（侧边备注、格子备注、改过的结论文字会带过去）：

| 写到哪 | 内容 |
|---|---|
| `data/tag_override.csv` | 改标记录（报告里最高优先级，带时间） |
| `data/pdt.sqlite3` 的 `tag` 表 | Amazon 原始打标：值改成新值，`source=manual`、`status=confirmed`、记确认时间 |
| `data/tag.xlsx` 的“确认：xx”列 | 小平台原始打标（第一次写之前自动备份成 `tag.xlsx.原始备份.xlsx`） |

尺寸、价格带（以及小平台的主色）原始库里没有对应列，只记在 `tag_override.csv`。服务只监听本机，关掉命令行窗口就停止。直接双击打开 HTML 时弹窗里只显示提示，不能保存。

商品明细可按 Esc 关闭并回到原筛选。侧边备注和格子备注独立保存在同一浏览器的报告地址下，刷新和重算会继续读取。交叉筛选中，展开格子备注后，将鼠标移到备注框上，点右上角的「×」，确认后只清除当前格子的备注。

## 手工改标（不用浏览器时）

在 `data/tag_override.csv` 里加一行，再跑 `python run.py`，全报告（总览、对照、明细、趋势、交叉筛选、弹窗）都会按新标签重算：

| 列 | 说明 |
|---|---|
| 渠道 | `amazon` / `homedepot` / `lowes` / `wayfair` |
| 商品ID | Amazon 填子体 ASIN；小平台填父体 ID（报告弹窗里标题下面那串） |
| 属性 | `拆装` `形态` `尺寸` `价格带` `台面` `柜体` `主色` `元素` 之一 |
| 改成 | 新取值，写法和报告里一致，如 `拆装`、`开放式`、`36″` |
| 备注 | 为什么改，随便写 |

例：`amazon,B0GG9TYLD9,拆装,拆装,标题写 Pre-Assembled 但实际拆装`

优先级：人工改标 > 价格线 > 原始打标。

## 规则在哪改

| 规则 | 位置 |
|---|---|
| 整装价格线（售价 ≥ 线价一律整装，四个渠道） | `calc3.py` 的 `ASM_LINE`，`calc.py` 同名字典（两处要一致） |
| 拆装价格线（售价 < 线价一律拆装，只用于 Amazon） | `calc3.py` 的 `KD_LINE`，`calc.py` 同名字典 |
| 自营品牌名单 | `gen3.py` 的 `SELF` |
| 尺寸档 | `sizeband.py` |

每次运行会生成 `data/asm_flips.csv`：被价格线改动的商品清单，用来核对。

## 运行顺序（run.py 已串好）

`calc.py`（Amazon 大盘、份额）→ `calc2.py`（同比、关键词）→ `calc3.py`（各渠道商品记录与指标表）→ `gen.py`（Amazon 旧版板块）→ `gen3.py`（最终报告，模板 `tpl3.html`）。
