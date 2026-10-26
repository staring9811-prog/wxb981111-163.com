# Design System Inspired by 品类机会判定台

> Category: Backend & Data
> 浅色冷静的数据工作台：中性灰白为底，数字旁都带"证据小标签"，命中率用区间条表达不确定性。

本文件是页面原型和后续开发唯一的视觉规范。Token 定义在 `tokens.css`；本文中的全部 CSS 代码块按顺序原样组成共享样式 `pages/assets/app.css`，页面通过 `../tokens.css` 与 `assets/app.css` 引用。依据为《设计决策蓝图》DD-1 至 DD-4（用户确认）。

---

## 视觉主题与氛围

- **视觉方向**：一张整洁的研究工作台。大面积中性灰白，表格是主角；颜色只在三种地方出现：状态、数据标记、唯一的主按钮。
- **用户情绪**：冷静的掌控感和可信——"每个数字都说得出出处"。
  - wen 每月要据此决定 30–40 万元的立项，界面不能催促、不能夸张。
  - 界面要让人一眼看出：哪个数是估算、样本有多少、结论是否经过验证。
- **为什么只做浅色**：
  - 使用场景是白天办公，长时间读表格。
  - 结果要导出成 Excel 和网页报告，网页报告还要打印。
  - 浅色与导出物保持同一观感，深色没有收益（DD-2）。
- **风格定位**：克制的数据产品风格。
  - 借 Linear 的克制与密度。
  - 借 Stripe 后台的数字对齐与表格清晰度。
  - 不用玻璃拟态、渐变、插画。

**色彩速览**

| 角色 | Hex | 用途 |
| :--- | :--- | :--- |
| 页面底色 `--bg` | `#F4F5F7` | 应用背景 |
| 表面 `--surface` | `#FFFFFF` | 表格、面板、抽屉 |
| 次表面 `--paper-2` | `#F7F8FA` | 侧栏、表头、面板页脚 |
| 悬停面 `--paper-hover` | `#EEF1F4` | 行悬停、按钮悬停 |
| 主文字 `--fg` | `#14181D` | 正文、数字 |
| 次文字 `--ink-2` | `#3A424D` | 次级文字、链接 |
| 弱文字 `--muted` | `#5A6370` | 说明、表头、证据小标签 |
| 边框 `--border` | `#D9DEE4` | 面板、表格外框 |
| 控件边框 `--border-control` | `#8A939F` | 输入框、次按钮（非文本对比 3.11:1） |
| 强调 `--accent` | `#1C5A8A` | 唯一主按钮、当前步骤、焦点环 |
| 命中/通过 `--success` | `#1B7343` | 命中、达标、通过 |
| 预警 `--warn` | `#8F5300` | 预警、未验证、需重算、数据不全 |
| 阻断 `--danger` | `#B42318` | 阻断、失败 |
| 截面口径 `--cross` | `#5E45A0` | 一切"截面口径"标注 |
| 数据系列 `--viz-series-1` | `#2A78D6` | 区间点、趋势线、进度 |

**参考先例**
- **Linear**：信息密度高，但留白规整；导航克制。借用侧栏的层级、当前项的处理和整体安静感。
- **Stripe Dashboard**：金额与数字右对齐、等宽数字、表格分隔线极轻。借用表格规则。
- **Datawrapper / 经济学人图表**：图表只画数据本身，在图上直接标注，并注明来源和样本。借用"证据小标签"的写法和区间条的直接标注。

## 色彩美学

- **色彩用途**：
  - 中性色分层级：`bg` 衬底，`surface` 承载内容，`paper-2` 放辅助信息。
  - 唯一的强调色用于"你接下来该点什么"。
  - 语义色只表示状态，并且一律配图标和文字，不单靠颜色。
  - 数据蓝 `--viz-series-1` 只画数据标记，与界面强调色分开，免得把数据误读成可点击。
- **强调色纪律（硬性上限）**：
  - `--accent` 每屏最多 2 处可见使用，典型是工作台的当前步骤加一个主按钮。
  - 链接、表格行内链接、选中的筛选标签、当前导航项都不用 accent，用 `--fg` 加下划线或描边表达。
  - 焦点环可以用 accent，它只在键盘聚焦时出现。
  - 画面占比上限：中性色 ≥ 80%，accent ≤ 5%，语义色 ≤ 5%，数据色 ≤ 10%。

**Surface 色板**

| Token | Hex | 设计理由 |
| :--- | :--- | :--- |
| `--bg` | `#F4F5F7` | 微冷的浅灰，与白色面板形成一级层次，不需要阴影 |
| `--surface` | `#FFFFFF` | 内容承载面，表格读数最清楚 |
| `--surface-warm` → `--paper-2` | `#F7F8FA` | 次要区域：侧栏、表头、面板页脚 |
| `--surface-raised` → `--paper-hover` | `#EEF1F4` | 悬停与选中的底色（色彩响应） |
| `--surface-overlay` → `--surface` | `#FFFFFF` | 抽屉、弹窗、浮层，靠投影与遮罩分层 |
| `--border` | `#D9DEE4` | 面板与表格外框 |
| `--border-soft` → `--line-soft` | `#E9ECF0` | 表格行分隔线，几乎不可见但能引导视线 |
| `--border-control` | `#8A939F` | 输入框、复选框、次按钮的边界，对白底 3.11:1，满足非文本对比 |

**状态与数据色板**

| Token | Hex | 浅底版 | 情感定义 |
| :--- | :--- | :--- | :--- |
| `--accent` | `#1C5A8A` | `--accent-tint` `#E8EEF3` | 深钢蓝：可靠、克制，表示"下一步" |
| `--success` | `#1B7343` | `--success-tint` `#E8F1EC` | 命中、达标、通过：确定的好消息 |
| `--warn` | `#8F5300` | `--warn-tint` `#F4EEE6` | 预警、未验证、需重算、数据不全：需要你看一眼 |
| `--danger` | `#B42318` | `--danger-tint` `#F8E9E8` | 阻断、失败：不处理就不能往下走 |
| `--cross` | `#5E45A0` | `--cross-tint` `#EFECF6` | 截面口径：证据较弱、待历史确认，用低饱和紫与其他状态区分 |
| `--viz-series-1` | `#2A78D6` | `--viz-band` `#9EC5F4` | 数据标记（单系列），dataviz 校验通过 |
| `--viz-deemph` | `#C4CAD1` | — | 图表中的对照项（如 4 个现用指标），配直接数值标注 |

"未命中"不用红色：它是结果，不是错误，用中性灰。

**文字色板与对比度**（WCAG 2.2，实测）

| 文字色 | 白 `#FFFFFF` | 底色 `#F4F5F7` | 次表面 `#F7F8FA` | 悬停 `#EEF1F4` |
| :--- | :--- | :--- | :--- | :--- |
| `--fg` `#14181D` | 17.82 | 16.34 | 16.77 | 15.72 |
| `--fg-2` `#3A424D` | 10.16 | 9.32 | 9.56 | 8.96 |
| `--muted` `#5A6370` | 6.08 | 5.57 | 5.72 | 5.36 |
| `--accent` `#1C5A8A` | 7.29 | 6.69 | 6.86 | 6.43 |
| `--success` `#1B7343` | 5.87 | 5.38 | 5.52 | 5.17 |
| `--warn` `#8F5300` | 6.17 | 5.65 | 5.80 | 5.44 |
| `--danger` `#B42318` | 6.57 | 6.03 | 6.19 | 5.80 |
| `--cross` `#5E45A0` | 7.41 | 6.79 | 6.97 | 6.53 |

- **按钮文字**：主按钮白字 `--accent-on` 在 `--accent` 上为 7.29:1。
- **徽章与横幅**：状态色文字在各自的浅底上分别为 6.24（accent）、5.09（success）、5.35（warn）、5.58（danger）、6.35（cross），均 ≥ 4.5:1。
- **热力格**：浅档（100–400）用 `--fg` 字（≥ 4.9:1），深档（550、650）用白字（≥ 6.6:1）；中间档 `#2A78D6` 两种字色都不到 4.5:1，不用作带字格子。

## 排版与字体

- **字体选择**：本机应用和离线报告都不能加载外部字体，所以全部用系统字体。
  - Windows 上是 Segoe UI 加微软雅黑 UI，macOS 上是苹方。
  - 编号、ASIN、指纹和证据小标签用等宽字体，与正文明显区分，表示"这是一条可核对的记录"。

```
Font labels for catalog extraction:

Display: "Segoe UI Variable Display", "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", "Noto Sans SC", system-ui, sans-serif
Body: "Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", "Noto Sans SC", system-ui, sans-serif
Mono: "Cascadia Mono", "Cascadia Code", Consolas, "SF Mono", Menlo, "Microsoft YaHei UI", monospace
```

**字号梯度**：以 14px 为正文基准（Windows 中文界面的常用阅读尺寸），表格用 13px 以容纳更多列。

| Token | 值 | 用途 |
| :--- | :--- | :--- |
| `--text-2xs` | 11px | 证据小标签、图表刻度 |
| `--text-xs` | 12px | 表头、说明、徽章 |
| `--text-sm` | 13px | 表格正文、按钮、导航 |
| `--text-base` | 14px | 正文 |
| `--text-lg` | 16px | 区块标题 |
| `--text-xl` | 18px | 抽屉、弹窗标题 |
| `--text-2xl` | 22px | 页面标题 |
| `--text-3xl` | 28px | 统计卡数值 |
| `--text-4xl` | 36px | 网页报告首屏标题 |
| `--text-hero` | 48px | 每屏唯一的主数字（回测倍数、报告结论） |

**Letter-spacing 精确规则**

| 场景 | 值 | Token |
| :--- | :--- | :--- |
| 全大写文本（仅英文缩写，如 ASIN、FBM） | 0.06em | 直接写 `0.06em` |
| Display 大字（48px） | -0.02em | `--tracking-hero` |
| 标题（28–36px） | -0.01em | `--tracking-display` |
| 小文本（11–13px） | 0.01em | `--tracking-small` |
| UI 标签、按钮、徽章、证据小标签 | 0.02em | `--tracking-ui` |
| 正文（14–22px） | 0 | 默认 |

**行高**：
- 正文 1.6（`--leading-body`），中文段落不拥挤。
- 标题和统计数字 1.3（`--leading-tight`），营造"仪表感"。
- 表格单元格 1.45，兼顾密度和中英混排。
- **数字字形**：表格里需要上下对齐的数字用等宽数字（`.num`、`.t-num`）；单独出现的大数字用比例数字。

## 间距体系

- **间距依据**：以 4px 为基准。8 和 12 用于组件内部，16 和 24 用于区块之间，32 和 48 用于大段落；同一组信息靠近，不同组信息用更大的空隙分开，替代边框。
- **间距值**：`--space-1` 4 · `--space-2` 8 · `--space-3` 12 · `--space-4` 16 · `--space-5` 20 · `--space-6` 24 · `--space-8` 32 · `--space-12` 48。
- **区块垂直节奏**：
  - 桌面 32px：信息多，靠节奏分组。
  - 平板 24px。
  - 手机 16px：网页报告在小屏上的降级。

## 布局与空间构成

- **应用骨架（DD-1）**：
  - 左侧固定侧栏 224px，可收起为 64px 图标栏。
  - 顶栏 56px，吸顶。
  - 内容区最大宽 1440px，左右留白 32px。
- **页面结构**：
  - 页头：面包屑、标题、副标题、右侧操作。
  - 内容区块：区块间距 32px。
  - 工作台和回测用"主栏 + 侧栏"两列（约 1.6 : 1）；列表页用整宽表格。
- **深度与层级**：
  - 第一层：底色和白色面板。
  - 第二层：悬停时底色变化，不抬升，不加阴影。
  - 第三层：抽屉、弹窗、浮层用 `--elev-float` 投影加遮罩。
  - 只有真正"浮"在页面上的东西才有投影，表格和卡片保持平面，靠层次而不是边框堆叠。
- **响应式（DD-3）**：
  - ≥ 1600：显示全部列。
  - 1366–1599：收起表格中标为次要的列（`.col-2`），可从"列"菜单调出。
  - 1280–1439：内容留白收为 24px。
  - < 1280：侧栏自动收为图标栏，两列布局变为单列，8 步进度条折为两行。
  - < 768：仅作降级显示，侧栏变为顶部横向导航，主要服务网页报告在手机上的阅读。

```css
/* ── 基础 ── */
*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: var(--font-body);
  font-size: var(--text-base);
  line-height: var(--leading-body);
  -webkit-font-smoothing: antialiased;
}
h1, h2, h3, h4 { margin: 0; font-family: var(--font-display); line-height: var(--leading-tight); color: var(--fg); }
h1 { font-size: var(--text-2xl); font-weight: 600; }
h2 { font-size: var(--text-lg); font-weight: 600; }
h3 { font-size: var(--text-base); font-weight: 600; }
p { margin: 0; }
ul, ol { margin: 0; padding-left: 1.2em; }
a {
  color: var(--fg-2);
  text-decoration: underline;
  text-decoration-color: var(--border-control);
  text-underline-offset: 3px;
  transition: color var(--motion-fast) var(--ease-standard), text-decoration-color var(--motion-fast) var(--ease-standard);
}
a:hover { color: var(--fg); text-decoration-color: var(--fg); }
a:active { color: var(--fg); }
a:focus-visible { outline: none; box-shadow: var(--focus-ring); border-radius: var(--radius-sm); }
.num { font-variant-numeric: tabular-nums; }
.mono { font-family: var(--font-mono); font-size: var(--text-xs); letter-spacing: var(--tracking-ui); }
.muted { color: var(--muted); }
.small { font-size: var(--text-xs); letter-spacing: var(--tracking-small); }
.strong { font-weight: 600; color: var(--fg); }
.icon { width: 16px; height: 16px; flex: none; fill: currentColor; vertical-align: -3px; }
.icon--lg { width: 20px; height: 20px; }
[hidden] { display: none !important; }
.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.stack > * + * { margin-top: var(--space-3); }
.stack-lg > * + * { margin-top: var(--space-6); }
.page-foot { margin-top: var(--space-8); font-size: var(--text-xs); color: var(--muted); letter-spacing: var(--tracking-small); }
.row { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
.spacer { flex: 1; }

/* ── 应用骨架 ── */
.app { display: grid; grid-template-columns: var(--sidebar-w) minmax(0, 1fr); min-height: 100vh; }
.app.is-collapsed { grid-template-columns: var(--sidebar-w-collapsed) minmax(0, 1fr); }
.sidebar {
  position: sticky; top: 0; height: 100vh;
  display: flex; flex-direction: column;
  background: var(--surface-warm);
  border-right: 1px solid var(--border);
  overflow-y: auto;
}
.sidebar__brand {
  display: flex; align-items: center; gap: var(--space-2);
  height: var(--topbar-h); padding: 0 var(--space-4);
  font-family: var(--font-display); font-size: var(--text-base); font-weight: 700;
  color: var(--fg); white-space: nowrap;
  border-bottom: 1px solid var(--border-soft);
}
.brand-mark { width: 24px; height: 24px; flex: none; }
.brand-mark .bm-bg { fill: var(--fg); }
.brand-mark .bm-band { fill: var(--surface); opacity: 0.55; }
.brand-mark .bm-dot { fill: var(--surface); }
.nav { display: flex; flex-direction: column; gap: 2px; padding: var(--space-2) var(--space-2) var(--space-4); }
.nav__group {
  margin: var(--space-4) var(--space-3) var(--space-1);
  font-size: var(--text-xs); color: var(--muted); letter-spacing: var(--tracking-ui);
}
.nav__item {
  position: relative;
  display: flex; align-items: center; gap: var(--space-3);
  min-height: 34px; padding: 0 var(--space-3);
  border-radius: var(--radius-md);
  color: var(--fg-2); text-decoration: none;
  font-size: var(--text-sm); letter-spacing: var(--tracking-small);
  transition: background-color var(--motion-fast) var(--ease-standard), color var(--motion-fast) var(--ease-standard);
}
.nav__item:hover { background: var(--surface-raised); color: var(--fg); }
.nav__item:active { background: var(--border-soft); }
.nav__item:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.nav__item[aria-current="page"] { background: var(--surface); color: var(--fg); font-weight: 600; box-shadow: var(--elev-ring); }
.nav__item[aria-current="page"]::before {
  content: ""; position: absolute; left: calc(-1 * var(--space-2)); top: 8px; bottom: 8px;
  width: 2px; border-radius: 2px; background: var(--fg);
}
.nav__count {
  margin-left: auto; min-width: 20px; padding: 0 6px;
  border-radius: var(--radius-pill);
  background: var(--warn-tint); color: var(--warn);
  font-size: var(--text-xs); text-align: center; font-variant-numeric: tabular-nums;
}
.sidebar__foot { margin-top: auto; padding: var(--space-2); border-top: 1px solid var(--border-soft); }
.app.is-collapsed .nav__item span,
.app.is-collapsed .nav__group,
.app.is-collapsed .sidebar__brand span,
.app.is-collapsed .nav__count { display: none; }
.app.is-collapsed .nav__item { justify-content: center; padding: 0; }
.app.is-collapsed .sidebar__brand { justify-content: center; padding: 0; }

.main { min-width: 0; display: flex; flex-direction: column; }
.topbar {
  position: sticky; top: 0; z-index: 20;
  display: flex; align-items: center; gap: var(--space-4);
  height: var(--topbar-h); padding: 0 var(--container-gutter-desktop);
  background: var(--surface); border-bottom: 1px solid var(--border);
}
.topbar__category { font-size: var(--text-sm); font-weight: 600; white-space: nowrap; }
.versions { display: flex; gap: var(--space-2); flex-wrap: nowrap; }
.version {
  padding: 2px var(--space-2);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--surface-warm); color: var(--muted);
  font-family: var(--font-mono); font-size: var(--text-xs); letter-spacing: var(--tracking-ui);
  white-space: nowrap; text-decoration: none;
  transition: background-color var(--motion-fast) var(--ease-standard), color var(--motion-fast) var(--ease-standard);
}
a.version:hover { background: var(--surface-raised); color: var(--fg); }
a.version:active { background: var(--border-soft); }
a.version:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.operator { display: inline-flex; align-items: center; gap: var(--space-1); font-size: var(--text-sm); color: var(--fg-2); white-space: nowrap; }

.content {
  width: 100%; max-width: var(--container-max); margin: 0 auto;
  padding: var(--space-6) var(--container-gutter-desktop) var(--space-12);
}
.page-head { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--space-4); margin-bottom: var(--space-6); }
.crumbs { display: flex; align-items: center; gap: var(--space-1); margin-bottom: var(--space-1); font-size: var(--text-xs); color: var(--muted); letter-spacing: var(--tracking-small); }
.crumbs a { color: var(--muted); text-decoration: none; }
.crumbs a:hover { color: var(--fg); text-decoration: underline; }
.page-head__sub { margin-top: var(--space-1); font-size: var(--text-sm); color: var(--muted); }
.page-head__actions { display: flex; gap: var(--space-2); flex-wrap: wrap; justify-content: flex-end; }
.section { margin-top: var(--section-y-desktop); }
.section__head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--space-3); margin-bottom: var(--space-3); }
.section__title { font-size: var(--text-lg); font-weight: 600; }
.section__note { font-size: var(--text-xs); color: var(--muted); letter-spacing: var(--tracking-small); }
.grid-2 { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: var(--space-6); }
.grid-main-side { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(320px, 1fr); gap: var(--space-6); align-items: start; }
```

## 组件设计

**交互哲学：色彩响应**。全部组件统一：悬停只改底色或边框，按下再深一级，键盘焦点显示 3px 焦点环；不用阴影抬升，也不用位移。只有抽屉、弹窗、浮层有投影，因为它们确实浮在页面之上。

### 按钮

- **样式**：
  - 圆角 6px，高 34px，足够点击但不抢表格的空间。
  - 主按钮每页最多 1 个（强调色纪律）。
  - 危险操作（拆分归并、恢复备份）用红色描边按钮，提醒后果，但不像主按钮那样诱导点击。
- **禁用态**：保留鼠标事件，可以用提示说明为什么不能点（例："存在阻断项，不能计算"）。

```css
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2);
  height: 34px; padding: 0 var(--space-4);
  border: 1px solid var(--border-control); border-radius: var(--radius-md);
  background: var(--surface); color: var(--fg);
  font: inherit; font-size: var(--text-sm); font-weight: 500; letter-spacing: var(--tracking-ui);
  white-space: nowrap; text-decoration: none; cursor: pointer;
  transition: background-color var(--motion-fast) var(--ease-standard), border-color var(--motion-fast) var(--ease-standard), color var(--motion-fast) var(--ease-standard);
}
.btn:hover { background: var(--surface-raised); border-color: var(--fg-2); color: var(--fg); }
.btn:active { background: var(--border-soft); }
.btn:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.btn--primary { background: var(--accent); border-color: var(--accent); color: var(--accent-on); }
.btn--primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); color: var(--accent-on); }
.btn--primary:active { background: var(--accent-active); border-color: var(--accent-active); }
.btn--ghost { border-color: transparent; background: transparent; color: var(--fg-2); }
.btn--ghost:hover { background: var(--surface-raised); border-color: transparent; }
.btn--ghost:active { background: var(--border-soft); }
.btn--danger { color: var(--danger); border-color: color-mix(in oklab, var(--danger), white 50%); }
.btn--danger:hover { background: var(--danger-tint); border-color: var(--danger); color: var(--danger); }
.btn--danger:active { background: color-mix(in oklab, var(--danger-tint), var(--danger) 8%); }
.btn--sm { height: 28px; padding: 0 var(--space-3); font-size: var(--text-xs); }
.btn--icon { width: 34px; padding: 0; }
.btn--sm.btn--icon { width: 28px; }
.btn[disabled], .btn[aria-disabled="true"] { opacity: 0.45; cursor: not-allowed; }
.btn[disabled]:hover, .btn[aria-disabled="true"]:hover { background: var(--surface); border-color: var(--border-control); }
.btn--primary[disabled]:hover, .btn--primary[aria-disabled="true"]:hover { background: var(--accent); border-color: var(--accent); }
```

### 表单控件

- **控件边界**：输入框边框用 `--border-control`，满足非文本 3:1 对比。
- **必填**：必填项在标签后加红色"*"。
- **错误**：错误文案放在字段下方，并带图标。
- **复选框与单选**：用 `--fg` 着色，不消耗强调色。

```css
.field { display: flex; flex-direction: column; gap: var(--space-1); min-width: 0; }
.field__label { font-size: var(--text-sm); font-weight: 500; color: var(--fg); letter-spacing: var(--tracking-small); }
.field__label .req { margin-left: 2px; color: var(--danger); }
.field__hint { font-size: var(--text-xs); color: var(--muted); letter-spacing: var(--tracking-small); }
.field__error { display: flex; align-items: center; gap: var(--space-1); font-size: var(--text-xs); color: var(--danger); }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-4) var(--space-5); }
.form-grid .span-2 { grid-column: span 2; }
.input, .select, .textarea {
  width: 100%; min-height: 34px; padding: 6px var(--space-3);
  border: 1px solid var(--border-control); border-radius: var(--radius-md);
  background: var(--surface); color: var(--fg);
  font: inherit; font-size: var(--text-sm);
  transition: border-color var(--motion-fast) var(--ease-standard), box-shadow var(--motion-fast) var(--ease-standard);
}
.input:hover, .select:hover, .textarea:hover { border-color: var(--fg-2); }
.input:active, .select:active, .textarea:active { border-color: var(--fg); }
.input:focus-visible, .select:focus-visible, .textarea:focus-visible { outline: none; border-color: var(--accent); box-shadow: var(--focus-ring); }
.input[aria-invalid="true"], .textarea[aria-invalid="true"] { border-color: var(--danger); }
.input[readonly] { background: var(--surface-warm); color: var(--fg-2); }
.input--num { text-align: right; font-variant-numeric: tabular-nums; }
.textarea { min-height: 84px; resize: vertical; line-height: var(--leading-body); }
.select { cursor: pointer; }
.check { display: inline-flex; align-items: center; gap: var(--space-2); font-size: var(--text-sm); cursor: pointer; }
.check input { width: 16px; height: 16px; margin: 0; accent-color: var(--fg); cursor: pointer; }
.check input:hover { outline: 1px solid var(--fg-2); outline-offset: 1px; }
.check input:active { outline: 1px solid var(--fg); outline-offset: 1px; }
.check input:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.choice-group { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.choice {
  display: inline-flex; align-items: center; gap: var(--space-2);
  padding: 6px var(--space-3);
  border: 1px solid var(--border-control); border-radius: var(--radius-md);
  background: var(--surface); font-size: var(--text-sm); cursor: pointer;
  transition: background-color var(--motion-fast) var(--ease-standard), border-color var(--motion-fast) var(--ease-standard);
}
.choice:hover { background: var(--surface-raised); }
.choice:active { background: var(--border-soft); }
.choice:has(input:focus-visible) { box-shadow: var(--focus-ring); }
.choice:has(input:checked) { border-color: var(--fg); box-shadow: inset 0 0 0 1px var(--fg); font-weight: 600; }
.choice input { margin: 0; accent-color: var(--fg); }
.dropzone {
  display: flex; align-items: center; gap: var(--space-4);
  padding: var(--space-5); border: 1px dashed var(--border-control); border-radius: var(--radius-lg);
  background: var(--surface); cursor: pointer;
  transition: background-color var(--motion-fast) var(--ease-standard), border-color var(--motion-fast) var(--ease-standard);
}
.dropzone:hover, .dropzone.is-over { background: var(--surface-raised); border-color: var(--fg-2); }
.dropzone:active { background: var(--border-soft); }
.dropzone:focus-within { box-shadow: var(--focus-ring); }
.dropzone > .icon { width: 28px; height: 28px; color: var(--muted); }
```

### 面板与可点卡片

- **面板**：用 8px 圆角加 1px 边框，不加投影——表面是平的，层次来自底色差。
- **可点卡片**（如锦囊卡片）：悬停时底色加深一级。
- **事项列表**（`.list`）：用于工作台"待处理"等逐条事项，每条为"状态图标 + 标题 + 一行说明 + 去处理"。
- **面板内表格**：表格放进面板时加 `.table-wrap--flush` 去掉外框，避免双层边框。
- **展开依据**：用原生 `<details>` / `<summary>`；摘要行为次级文字色，悬停变深，键盘可聚焦。

```css
.panel { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); }
.panel__head {
  display: flex; align-items: center; justify-content: space-between; gap: var(--space-3);
  padding: var(--space-4) var(--space-5); border-bottom: 1px solid var(--border-soft);
}
.panel__title { font-size: var(--text-base); font-weight: 600; }
.panel__body { padding: var(--space-4) var(--space-5); }
.panel__foot {
  padding: var(--space-3) var(--space-5); border-top: 1px solid var(--border-soft);
  background: var(--surface-warm); border-radius: 0 0 var(--radius-lg) var(--radius-lg);
  font-size: var(--text-xs); color: var(--muted);
}
.card-link {
  display: block; padding: var(--space-4);
  border: 1px solid var(--border); border-radius: var(--radius-lg);
  background: var(--surface); color: inherit; text-decoration: none;
  transition: background-color var(--motion-fast) var(--ease-standard), border-color var(--motion-fast) var(--ease-standard);
}
.card-link:hover { background: var(--surface-raised); border-color: var(--border-control); color: inherit; }
.card-link:active { background: var(--border-soft); }
.card-link:focus-visible { outline: none; box-shadow: var(--focus-ring); }
:where(.kv) { margin: 0; }
.kv { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: var(--space-2) var(--space-5); font-size: var(--text-sm); }
.kv dt { color: var(--muted); }
.kv dd { margin: 0; color: var(--fg); min-width: 0; }
summary { color: var(--fg-2); cursor: pointer; border-radius: var(--radius-sm); transition: color var(--motion-fast) var(--ease-standard); }
summary:hover { color: var(--fg); }
summary:active { color: var(--fg); }
summary:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.list { margin: 0; padding: 0; list-style: none; }
.list__item { display: flex; align-items: flex-start; gap: var(--space-3); padding: var(--space-3) var(--space-5); border-bottom: 1px solid var(--border-soft); }
.list__item:last-child { border-bottom: 0; }
.list__icon { margin-top: 2px; color: var(--muted); }
.list__icon--warn { color: var(--warn); }
.list__icon--danger { color: var(--danger); }
.list__icon--ok { color: var(--success); }
.list__body { flex: 1; min-width: 0; }
.list__title { font-size: var(--text-sm); font-weight: 600; color: var(--fg); }
.list__desc { margin-top: 2px; font-size: var(--text-xs); color: var(--muted); letter-spacing: var(--tracking-small); }
.list__action { flex: none; align-self: center; }
```

### 数据表格

- **用途**：表格是主角。
- **表头**：次表面底色，12px 弱文字。
- **分隔**：行分隔线极轻，用 `--border-soft`。
- **数字列**：右对齐，用等宽数字。
- **整行可点**：悬停换底色，键盘可聚焦。
- **次要列**：标 `.col-2`，窄屏收起。
- **样本不足**：样本不足的细分放在分隔行 `.table__divider` 之后。

```css
.table-wrap { width: 100%; overflow-x: auto; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); }
.table-wrap--flush { border: 0; border-radius: 0 0 var(--radius-lg) var(--radius-lg); }
.table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: var(--text-sm); }
.table th {
  position: sticky; top: 0; z-index: 1;
  padding: var(--space-2) var(--space-3);
  background: var(--surface-warm); color: var(--muted);
  font-size: var(--text-xs); font-weight: 500; letter-spacing: var(--tracking-small);
  text-align: left; white-space: nowrap;
  border-bottom: 1px solid var(--border);
}
.table td { padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--border-soft); vertical-align: middle; line-height: 1.45; }
.table tbody tr:last-child td { border-bottom: 0; }
.table tbody tr { transition: background-color var(--motion-fast) var(--ease-standard); }
.table tbody tr:hover { background: var(--surface-raised); }
.table tbody tr.is-selected { background: var(--surface-raised); box-shadow: inset 2px 0 0 var(--fg); }
.table tr[data-href] { cursor: pointer; }
.table tr[data-href]:active { background: var(--border-soft); }
.table tr[data-href]:focus-visible { outline: none; box-shadow: inset 0 0 0 2px var(--accent); }
.table .t-num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.table .t-center { text-align: center; }
.table .t-nowrap { white-space: nowrap; }
.table .t-check { width: 36px; }
.table__divider td {
  padding: var(--space-2) var(--space-3);
  background: var(--surface-warm); color: var(--muted);
  font-size: var(--text-xs); border-top: 1px solid var(--border);
}
.cell-title { font-weight: 500; color: var(--fg); }
.cell-sub { font-size: var(--text-xs); color: var(--muted); letter-spacing: var(--tracking-small); }
.tlink { color: var(--fg); text-decoration: none; font-weight: 500; }
.tlink:hover { text-decoration: underline; text-decoration-color: var(--fg); }
.tlink:active { color: var(--fg-2); }
.tlink:focus-visible { outline: none; box-shadow: var(--focus-ring); border-radius: var(--radius-sm); }
.th-sort {
  display: inline-flex; align-items: center; gap: 2px; padding: 0;
  border: 0; border-radius: var(--radius-sm); background: transparent;
  color: inherit; font: inherit; cursor: pointer;
}
.th-sort:hover { color: var(--fg); }
.th-sort:active { color: var(--fg-2); }
.th-sort:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.th-sort[aria-sort] { color: var(--fg); }
.segname { display: inline; }
.segname > span + span::before { content: "·"; margin: 0 5px; color: var(--muted); }
.pager { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-3) var(--space-1) 0; font-size: var(--text-xs); color: var(--muted); }
.pager__pages { display: flex; gap: var(--space-1); }
.pager__btn {
  min-width: 28px; height: 28px; padding: 0 var(--space-2);
  border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--surface); color: var(--fg-2);
  font: inherit; font-size: var(--text-xs); font-variant-numeric: tabular-nums; cursor: pointer;
  transition: background-color var(--motion-fast) var(--ease-standard);
}
.pager__btn:hover { background: var(--surface-raised); }
.pager__btn:active { background: var(--border-soft); }
.pager__btn:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.pager__btn[aria-current="page"] { border-color: var(--fg); color: var(--fg); font-weight: 600; }
```

### 状态徽章

- **配对规则**：每个状态都由"图标 + 文字"组成，从不只靠颜色。
- **全站统一状态词**：
  - 成败：命中、未命中、观察中、数据不全；截面口径为截面命中、截面未命中、观察中、老品。
  - 回测结论：达标、达标（截面）、未达标；判定卡多一个"未验证"。
  - 其他：需重算、样本不足、无数据。

**状态词与徽章对照**（全站统一，页面不得另选图标或样式）

| 类别 | 状态词 | 类名 | 图标 |
| :--- | :--- | :--- | :--- |
| 成败 | 命中 / 截面命中 | `badge--hit` / `badge--cross` | `check-circle` |
| 成败 | 未命中 / 截面未命中 | `badge--miss` | `minus` |
| 成败 | 观察中 | `badge--watch` | `hourglass` |
| 成败 | 数据不全 | `badge--incomplete` | `warning` |
| 成败 | 老品 | `badge--old` | `archive` |
| 回测与判定卡 | 达标 / 已达标 | `badge--pass` | `seal-check` |
| 回测与判定卡 | 达标（截面） | `badge--cross` | `seal-check` |
| 回测与判定卡 | 未达标 | `badge--fail` | `x-circle` |
| 回测与判定卡 | 未验证 | `badge--unverified` | `seal-question` |
| 锦囊动作 | 立项候选 | `badge--hit` | `flag` |
| 锦囊动作 | 观察 | `badge--watch` | `eye` |
| 锦囊动作 | 放弃 | `badge--miss` | `prohibit` |
| 规则状态 | 已验证 | `badge--pass` | `seal-check` |
| 规则状态 | 历史观察 | `.badge`（默认） | `clock-counter-clockwise` |
| 规则状态 | 未验证经验 | `badge--unverified` | `seal-question` |
| 标记 | 疑似重新上架 | `badge--warn` | `clock-counter-clockwise` |
| 标记 | 需重算 | `badge--stale` | `arrows-clockwise` |
| 标记 | 样本不足 | `badge--insufficient` | `info` |
| 标记 | 阻断 / 警告 / 通过 | `badge--block` / `badge--warn` / `badge--ok` | `warning-octagon` / `warning` / `check-circle` |
| 标记 | 已知晓 | `badge--ack` | `check` |

```css
.badge {
  display: inline-flex; align-items: center; gap: 4px;
  height: 22px; padding: 0 8px;
  border: 1px solid transparent; border-radius: var(--radius-pill);
  background: var(--surface-warm); color: var(--fg-2);
  font-size: var(--text-xs); font-weight: 500; letter-spacing: var(--tracking-ui);
  white-space: nowrap; vertical-align: middle;
}
.badge .icon { width: 13px; height: 13px; vertical-align: 0; }
.badge--hit, .badge--pass, .badge--ok { background: var(--success-tint); color: var(--success); }
.badge--miss, .badge--fail { background: var(--surface-warm); color: var(--fg-2); border-color: var(--border); }
.badge--watch { background: var(--surface); color: var(--fg-2); border-color: var(--border-control); }
.badge--incomplete, .badge--warn, .badge--stale, .badge--unverified { background: var(--warn-tint); color: var(--warn); }
.badge--block { background: var(--danger-tint); color: var(--danger); }
.badge--cross { background: var(--cross-tint); color: var(--cross); }
.badge--old, .badge--insufficient, .badge--ack, .badge--nodata { background: transparent; color: var(--muted); border-color: var(--border-control); border-style: dashed; }
.badge--accent { background: var(--accent-tint); color: var(--accent); }
```

### 证据小标签（设计签名）

关键数字后面紧跟一个 11px 的等宽小标签，回答三个问题：样本多少、数据什么性质、是不是截面口径。

- **六种写法**：
  - 样本量：`n=128`
  - 数据性质：`估算`、`实测`、`推导`、`人工`
  - 快照：`快照`，带预警色
  - 父体回填：`回填 23%`，虚线框
  - 截面口径：`截面`，带截面紫
  - 候选信号：`候选`，点线框
- **缺失值**：一律写成 `无数据` 标签，从不显示 0 或横杠。
- **可点开**：小标签做成按钮时，点击后弹出浮层，显示字段、来源文件、字段约定版本和来源记录主键（NFR-003）。

```css
.etag {
  display: inline-flex; align-items: center; gap: 3px;
  height: 18px; padding: 0 5px; margin-left: 4px;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--surface-warm); color: var(--muted);
  font-family: var(--font-mono); font-size: var(--text-2xs); font-weight: 400; letter-spacing: var(--tracking-ui);
  line-height: 1; white-space: nowrap; vertical-align: 1px;
}
button.etag { appearance: none; cursor: pointer; transition: background-color var(--motion-fast) var(--ease-standard), border-color var(--motion-fast) var(--ease-standard), color var(--motion-fast) var(--ease-standard); }
button.etag:hover { background: var(--surface); border-color: var(--border-control); color: var(--fg); }
button.etag:active { background: var(--surface-raised); }
button.etag:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.etag--n { color: var(--fg-2); }
.etag--snap { background: var(--warn-tint); color: var(--warn); border-color: color-mix(in oklab, var(--warn), white 55%); }
.etag--fill { border-style: dashed; border-color: var(--border-control); }
.etag--cross { background: var(--cross-tint); color: var(--cross); border-color: color-mix(in oklab, var(--cross), white 60%); }
.etag--cand { border-style: dotted; border-color: var(--border-control); }
.etag--nodata { background: transparent; border-style: dashed; margin-left: 0; }
.popover {
  position: absolute; z-index: 40; min-width: 240px; max-width: 360px;
  padding: var(--space-3) var(--space-4);
  background: var(--surface-overlay); border: 1px solid var(--border); border-radius: var(--radius-md);
  box-shadow: var(--elev-float);
  font-size: var(--text-xs); color: var(--fg-2); line-height: 1.5;
  opacity: 0; visibility: hidden;
  transition: opacity var(--motion-fast) var(--ease-standard), visibility var(--motion-fast) var(--ease-standard);
}
.popover.is-open { opacity: 1; visibility: visible; }
.popover__title { margin-bottom: var(--space-2); font-size: var(--text-sm); font-weight: 600; color: var(--fg); }
.popover dl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 2px var(--space-3); margin: 0; }
.popover dt { color: var(--muted); }
.popover dd { margin: 0; color: var(--fg); font-family: var(--font-mono); font-size: var(--text-2xs); word-break: break-all; }
```

### 区间条（设计签名之二）

- **用途**：预期命中率一律画成区间条，不只写一个点估计。
- **画法**：
  - 浅蓝带表示 90% 区间。
  - 实心点（8px，带 2px 白环）表示点估计。
  - 细竖线表示全类目平均；平均值写在表头说明里，不在每行重复。
  - 样本不足的细分改用灰色。
- **数值与提示**：区间数值始终以文字写在旁边，悬停提示只是补充。

```css
.ibar { display: inline-block; vertical-align: middle; }
.ibar svg { display: block; overflow: visible; }
.ibar__track { stroke: var(--viz-grid); stroke-width: 1; }
.ibar__band { fill: var(--viz-band); transition: fill var(--motion-fast) var(--ease-standard); }
.ibar__avg { stroke: var(--viz-ref); stroke-width: 1; }
.ibar__dot { fill: var(--viz-series-1); stroke: var(--surface); stroke-width: 2; }
.ibar__hit { fill: transparent; cursor: default; }
.ibar__hit:hover { fill: color-mix(in oklab, var(--fg), transparent 95%); }
.ibar__hit:active { fill: color-mix(in oklab, var(--fg), transparent 92%); }
.ibar__hit:focus-visible { outline: none; fill: color-mix(in oklab, var(--fg), transparent 95%); stroke: var(--fg-2); stroke-width: 1; }
.ibar:hover .ibar__band, .ibar:focus-visible .ibar__band { fill: var(--viz-seq-300); }
.ibar:focus-visible { outline: none; box-shadow: var(--focus-ring); border-radius: var(--radius-sm); }
.ibar:active .ibar__band { fill: var(--viz-seq-300); }
.ibar--muted .ibar__band { fill: var(--viz-deemph); }
.ibar--muted .ibar__dot { fill: var(--muted); }
.ibar-text { margin-left: var(--space-2); font-size: var(--text-xs); color: var(--fg-2); font-variant-numeric: tabular-nums; white-space: nowrap; }
```

### 图表部件

图表只用单系列数据蓝与对照灰。

- **规则**：
  - 不用双轴，不用彩虹色，不用渐变块。
  - 网格线是实线细线。
  - 柱子最粗 16px，数据端 4px 圆角，基线端是直角。
  - 线宽 2px，端点 8px 圆点带白环。
  - 数值直接标在柱端或线端；表格视图始终可用。
- **热力表**：使用同一蓝色顺序阶，浅档配深字、深档配白字，并带色阶图例。

```css
.hbars { display: grid; grid-template-columns: max-content minmax(0, 1fr) max-content; gap: var(--space-2) var(--space-3); align-items: center; font-size: var(--text-sm); }
.hbar__label { color: var(--fg-2); white-space: nowrap; }
.hbar__track { position: relative; height: 16px; border-left: 1px solid var(--viz-axis); }
.hbar__bar {
  position: absolute; left: 0; top: 0; bottom: 0;
  border-radius: 0 4px 4px 0; background: var(--viz-deemph);
  transition: box-shadow var(--motion-fast) var(--ease-standard);
}
.hbar__bar--focus { background: var(--viz-series-1); }
.hbar__bar:hover, .hbar__bar:focus-visible { outline: none; box-shadow: 0 0 0 2px var(--surface), 0 0 0 3px var(--fg-2); }
.hbar__bar:active { box-shadow: 0 0 0 2px var(--surface), 0 0 0 3px var(--fg); }
.hbar__ref { position: absolute; top: -6px; bottom: -6px; width: 0; border-left: 1px solid var(--viz-ref); }
.hbar__ref-label { position: absolute; top: -22px; transform: translateX(-50%); font-size: var(--text-2xs); color: var(--muted); white-space: nowrap; }
.hbar__value { color: var(--fg); font-variant-numeric: tabular-nums; white-space: nowrap; }
.spark { display: block; overflow: visible; }
.spark__grid { stroke: var(--viz-grid); stroke-width: 1; }
.spark__line { fill: none; stroke: var(--viz-series-1); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.spark__area { fill: var(--viz-series-1); opacity: 0.1; }
.spark__dot { fill: var(--viz-series-1); stroke: var(--surface); stroke-width: 2; }
.spark__cross { stroke: var(--fg-2); stroke-width: 1; opacity: 0; transition: opacity var(--motion-fast) var(--ease-standard); }
.spark:hover .spark__cross, .spark:focus-visible .spark__cross { opacity: 1; }
.spark:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.spark__label { font-family: var(--font-body); font-size: var(--text-2xs); fill: var(--muted); }
.spark__value { font-family: var(--font-body); font-size: var(--text-2xs); fill: var(--fg); font-weight: 600; }
.heat { border-collapse: separate; border-spacing: 2px; font-size: var(--text-xs); }
.heat th { padding: var(--space-1) var(--space-2); color: var(--muted); font-weight: 500; text-align: left; white-space: nowrap; }
.heat td {
  min-width: 68px; height: 38px; padding: 2px var(--space-2);
  border-radius: var(--radius-sm); text-align: center; line-height: 1.25;
  font-variant-numeric: tabular-nums;
  transition: box-shadow var(--motion-fast) var(--ease-standard);
}
.heat td:hover, .heat td:focus-visible { outline: none; box-shadow: inset 0 0 0 2px var(--fg); }
.heat td:active { box-shadow: inset 0 0 0 3px var(--fg); }
.heat td span { display: block; font-size: var(--text-2xs); }
.heat .h0 { background: var(--surface-warm); color: var(--fg-2); }
.heat .h1 { background: var(--viz-seq-100); color: var(--fg); }
.heat .h2 { background: var(--viz-seq-200); color: var(--fg); }
.heat .h3 { background: var(--viz-seq-300); color: var(--fg); }
.heat .h4 { background: var(--viz-seq-400); color: var(--fg); }
.heat .h5 { background: var(--viz-seq-550); color: var(--surface); }
.heat .h6 { background: var(--viz-seq-650); color: var(--surface); }
.heat .hx { background: transparent; color: var(--muted); box-shadow: inset 0 0 0 1px var(--border); }
.scale-legend { display: inline-flex; align-items: center; gap: 2px; font-size: var(--text-xs); color: var(--muted); }
.scale-legend i { display: inline-block; width: 26px; height: 10px; border-radius: 2px; }
.scale-legend .l1 { background: var(--viz-seq-100); }
.scale-legend .l2 { background: var(--viz-seq-200); }
.scale-legend .l3 { background: var(--viz-seq-300); }
.scale-legend .l4 { background: var(--viz-seq-400); }
.scale-legend .l5 { background: var(--viz-seq-550); }
.scale-legend .l6 { background: var(--viz-seq-650); }
.tip {
  position: fixed; z-index: 60; pointer-events: none;
  padding: var(--space-2) var(--space-3);
  background: var(--surface-overlay); border: 1px solid var(--border); border-radius: var(--radius-md);
  box-shadow: var(--elev-float);
  font-size: var(--text-xs); color: var(--fg-2); line-height: 1.5;
  opacity: 0; transition: opacity var(--motion-fast) var(--ease-standard);
}
.tip.is-on { opacity: 1; }
.tip strong { display: block; font-size: var(--text-sm); color: var(--fg); font-variant-numeric: tabular-nums; }
.tip .key { display: inline-block; width: 12px; height: 2px; margin-right: 4px; vertical-align: middle; background: var(--viz-series-1); }
```

### 统计卡与进度

- **统计卡**：数值用比例数字和 28px，单位和目标写在下方。
- **进度轨**：用同一色阶的浅档。用时超过目标的 80% 时转预警色，超过目标转阻断色。
- **主数字**：每屏最多一个 48px 的主数字（`.hero-figure`）。

```css
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: var(--space-4); }
.stat { padding: var(--space-4) var(--space-5); background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); }
.stat__label { font-size: var(--text-xs); color: var(--muted); letter-spacing: var(--tracking-small); }
.stat__value {
  margin-top: var(--space-1);
  font-family: var(--font-display); font-size: var(--text-3xl); font-weight: 600;
  line-height: var(--leading-tight); letter-spacing: var(--tracking-display); color: var(--fg);
}
.stat__unit { margin-left: 2px; font-size: var(--text-base); font-weight: 500; letter-spacing: 0; color: var(--fg-2); }
.stat__meta { margin-top: var(--space-1); font-size: var(--text-xs); color: var(--muted); }
.meter { height: 6px; margin-top: var(--space-3); border-radius: 3px; background: var(--viz-track); overflow: hidden; }
.meter > i { display: block; height: 100%; border-radius: 3px; background: var(--viz-series-1); }
.meter--warn { background: var(--warn-tint); }
.meter--warn > i { background: var(--warn); }
.meter--danger { background: var(--danger-tint); }
.meter--danger > i { background: var(--danger); }
.hero-figure {
  font-family: var(--font-display); font-size: var(--text-hero); font-weight: 600;
  line-height: 1; letter-spacing: var(--tracking-hero); color: var(--fg);
}
```

### 横幅

- **适用**：口径与状态横幅常驻，不可关闭——"未验证""截面口径""需重算""阻断"是你必须一直看得见的事实。
- **文字颜色**：正文用 `--fg`，只有图标带状态色。

```css
.banner {
  display: flex; align-items: flex-start; gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--surface-warm); color: var(--fg); font-size: var(--text-sm);
}
.banner > .icon { margin-top: 3px; }
.banner__body { flex: 1; min-width: 0; }
.banner__title { font-weight: 600; }
.banner__actions { display: flex; gap: var(--space-2); align-self: center; }
.banner + .banner { margin-top: var(--space-2); }
.banner--unverified, .banner--stale, .banner--warn { background: var(--warn-tint); border-color: color-mix(in oklab, var(--warn), white 70%); }
.banner--unverified > .icon, .banner--stale > .icon, .banner--warn > .icon { color: var(--warn); }
.banner--cross { background: var(--cross-tint); border-color: color-mix(in oklab, var(--cross), white 70%); }
.banner--cross > .icon { color: var(--cross); }
.banner--block { background: var(--danger-tint); border-color: color-mix(in oklab, var(--danger), white 70%); }
.banner--block > .icon { color: var(--danger); }
.banner--ok { background: var(--success-tint); border-color: color-mix(in oklab, var(--success), white 70%); }
.banner--ok > .icon { color: var(--success); }
```

### 8 步进度条（工作台）

- **用途**：整页最重要的导航。每一步都可点，点击后进入对应页面。
- **当前步骤**：用强调色描边，是工作台的第 1 处强调色。
- **状态样式**：
  - 已完成：绿色勾。
  - 需处理：预警色。
  - 阻断：红色。
  - 未开始：弱文字。
- **连接线**：连接线在已完成的步骤之间加深。

```css
.steps {
  display: grid; grid-template-columns: repeat(8, minmax(0, 1fr));
  margin: 0; padding: var(--space-2);
  list-style: none;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
}
.step { position: relative; min-width: 0; }
.step:not(:last-child)::after {
  content: ""; position: absolute; top: 25px; left: calc(var(--space-3) + 34px); right: -4px;
  height: 1px; background: var(--border);
}
.step--done:not(:last-child)::after { background: var(--fg-2); }
.step__link {
  position: relative; z-index: 1;
  display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
  padding: var(--space-3); border-radius: var(--radius-md);
  color: inherit; text-decoration: none;
  transition: background-color var(--motion-fast) var(--ease-standard);
}
.step__link:hover { background: var(--surface-raised); color: inherit; }
.step__link:active { background: var(--border-soft); }
.step__link:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.step__dot {
  display: inline-flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; margin-bottom: var(--space-1);
  border: 1px solid var(--border-control); border-radius: 50%;
  background: var(--surface); color: var(--muted);
  font-size: var(--text-xs); font-weight: 600; font-variant-numeric: tabular-nums;
}
.step__dot .icon { width: 14px; height: 14px; }
.step__name { font-size: var(--text-sm); font-weight: 600; color: var(--fg); white-space: nowrap; }
.step__meta { font-size: var(--text-xs); color: var(--muted); white-space: nowrap; }
.step--done .step__dot { border-color: var(--success); background: var(--success-tint); color: var(--success); }
.step--current .step__dot { border: 2px solid var(--accent); color: var(--accent); }
.step--attention .step__dot { border-color: var(--warn); background: var(--warn-tint); color: var(--warn); }
.step--blocked .step__dot { border-color: var(--danger); background: var(--danger-tint); color: var(--danger); }
.step--todo .step__name { font-weight: 500; color: var(--fg-2); }
```

### 标签页、筛选与批量操作

- **标签页**：用下划线标出，当前标签为 `--fg` 加 2px 下划线，不消耗强调色。
- **筛选**：筛选标签放在表格上方一行，选中时描边加粗并打勾。
- **批量操作条**：勾选后从底部出现，深底白字。它是一个临时的"操作层"，要和页面内容明显区分。

```css
.tabs { display: flex; gap: var(--space-1); margin-bottom: var(--space-5); border-bottom: 1px solid var(--border); }
.tab {
  position: relative;
  display: inline-flex; align-items: center; gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md) var(--radius-md) 0 0;
  color: var(--muted); text-decoration: none;
  font-size: var(--text-sm); font-weight: 500;
  transition: color var(--motion-fast) var(--ease-standard), background-color var(--motion-fast) var(--ease-standard);
}
button.tab { border: 0; background: transparent; font: inherit; cursor: pointer; }
.tab:hover { color: var(--fg); background: var(--surface-raised); }
.tab:active { background: var(--border-soft); }
.tab:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.tab[aria-selected="true"], .tab[aria-current="page"] { color: var(--fg); font-weight: 600; }
.tab[aria-selected="true"]::after, .tab[aria-current="page"]::after {
  content: ""; position: absolute; left: var(--space-3); right: var(--space-3); bottom: -1px;
  height: 2px; border-radius: 2px; background: var(--fg);
}
.tab .count { color: var(--muted); font-size: var(--text-xs); font-variant-numeric: tabular-nums; }
.filters { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); margin-bottom: var(--space-3); }
.filters__label { margin-right: var(--space-1); font-size: var(--text-xs); color: var(--muted); }
.filters__sep { width: 1px; height: 20px; margin: 0 var(--space-2); background: var(--border); }
.chip {
  display: inline-flex; align-items: center; gap: var(--space-1);
  height: 28px; padding: 0 var(--space-3);
  border: 1px solid var(--border); border-radius: var(--radius-pill);
  background: var(--surface); color: var(--fg-2);
  font: inherit; font-size: var(--text-xs); letter-spacing: var(--tracking-ui);
  cursor: pointer; white-space: nowrap;
  transition: background-color var(--motion-fast) var(--ease-standard), border-color var(--motion-fast) var(--ease-standard), color var(--motion-fast) var(--ease-standard);
}
.chip:hover { background: var(--surface-raised); color: var(--fg); }
.chip:active { background: var(--border-soft); }
.chip:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.chip[aria-pressed="true"] { border-color: var(--fg); color: var(--fg); font-weight: 600; box-shadow: inset 0 0 0 1px var(--fg); }
.chip .count { color: var(--muted); font-weight: 400; font-variant-numeric: tabular-nums; }
.search { position: relative; display: inline-block; }
.search > .icon { position: absolute; left: 10px; top: 9px; color: var(--muted); pointer-events: none; }
.search .input { width: 240px; padding-left: 32px; }
.batchbar {
  position: sticky; bottom: var(--space-4); z-index: 15;
  display: flex; align-items: center; gap: var(--space-3);
  margin-top: var(--space-3); padding: var(--space-2) var(--space-2) var(--space-2) var(--space-4);
  background: var(--fg); color: var(--surface);
  border-radius: var(--radius-lg); box-shadow: var(--elev-float);
  font-size: var(--text-sm);
}
.batchbar[hidden] { display: none; }
.batchbar .btn { background: transparent; color: var(--surface); border-color: color-mix(in oklab, var(--surface), transparent 60%); }
.batchbar .btn:hover { background: color-mix(in oklab, var(--surface), transparent 88%); color: var(--surface); border-color: var(--surface); }
.batchbar .btn:active { background: color-mix(in oklab, var(--surface), transparent 80%); }
.batchbar .btn--primary { background: var(--accent); border-color: var(--accent); }
.batchbar .btn--primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
```

### 顶栏口径切换与任务指示

- **口径切换**：历史 / 截面是一个分段开关，两种结果都有时才出现；默认选中历史（历史模式优先，AC-F07-12）。
- **任务指示**：显示正在运行的计算任务、进度和步骤名；同时只运行一个任务。

```css
.seg { display: inline-flex; padding: 2px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-warm); }
.seg__opt {
  padding: 3px var(--space-3);
  border: 0; border-radius: var(--radius-sm);
  background: transparent; color: var(--muted);
  font: inherit; font-size: var(--text-xs); letter-spacing: var(--tracking-ui);
  cursor: pointer; white-space: nowrap;
  transition: background-color var(--motion-fast) var(--ease-standard), color var(--motion-fast) var(--ease-standard);
}
.seg__opt:hover { background: var(--surface-raised); color: var(--fg); }
.seg__opt:active { background: var(--border-soft); }
.seg__opt:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.seg__opt[aria-pressed="true"] { background: var(--surface); color: var(--fg); font-weight: 600; box-shadow: var(--elev-ring); }
.job {
  display: inline-flex; align-items: center; gap: var(--space-2);
  padding: 4px var(--space-3);
  border: 1px solid var(--border); border-radius: var(--radius-pill);
  background: var(--surface-warm); color: var(--fg-2);
  font-size: var(--text-xs); white-space: nowrap;
}
.job__bar { width: 72px; height: 4px; border-radius: 2px; background: var(--viz-track); overflow: hidden; }
.job__bar > i { display: block; height: 100%; background: var(--viz-series-1); }
.lock { display: inline-flex; align-items: center; gap: var(--space-1); font-size: var(--text-xs); color: var(--muted); }
.fp { font-family: var(--font-mono); font-size: var(--text-xs); letter-spacing: var(--tracking-ui); color: var(--fg-2); }
.diff { display: grid; grid-template-columns: max-content minmax(0, 1fr) minmax(0, 1fr); gap: var(--space-1) var(--space-3); font-size: var(--text-sm); }
.diff__key { color: var(--muted); }
.diff__old { color: var(--muted); text-decoration: line-through; text-decoration-color: var(--border-control); }
.diff__new { padding: 0 var(--space-1); border-radius: var(--radius-sm); background: var(--success-tint); color: var(--fg); }
```

### 抽屉、弹窗、轻提示、空状态

- **抽屉**：宽 600px，从右侧推入，用于"看一个对象的细节"，例如细分详情、规则编辑。
- **弹窗**：居中，宽 640–760px，用于"一次提交"，例如记录立项决定、录入上架数据、导出报告。
- **轻提示**：深底白字，3 秒后消失；只用于"已完成"类反馈，不承载需要决定的事。

```css
.scrim {
  position: fixed; inset: 0; z-index: 50;
  background: var(--scrim);
  opacity: 0; visibility: hidden;
  transition: opacity var(--motion-base) var(--ease-standard), visibility var(--motion-base) var(--ease-standard);
}
.scrim.is-open { opacity: 1; visibility: visible; }
.drawer {
  position: fixed; top: 0; right: 0; bottom: 0; z-index: 51;
  width: min(var(--drawer-w), 92vw);
  display: flex; flex-direction: column;
  background: var(--surface-overlay); border-left: 1px solid var(--border); box-shadow: var(--elev-float);
  transform: translateX(100%); visibility: hidden;
  transition: transform var(--motion-base) var(--ease-standard), visibility var(--motion-base) var(--ease-standard);
}
.drawer.is-open { transform: none; visibility: visible; }
.drawer__head, .modal__head {
  display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-3);
  padding: var(--space-5) var(--space-6) var(--space-4); border-bottom: 1px solid var(--border-soft);
}
.drawer__title, .modal__title { font-size: var(--text-xl); font-weight: 600; }
.drawer__sub, .modal__sub { margin-top: 2px; font-size: var(--text-xs); color: var(--muted); }
.drawer__body, .modal__body { flex: 1; overflow-y: auto; padding: var(--space-5) var(--space-6); }
.drawer__foot, .modal__foot {
  display: flex; align-items: center; justify-content: flex-end; gap: var(--space-2);
  padding: var(--space-3) var(--space-6);
  border-top: 1px solid var(--border-soft); background: var(--surface-warm);
}
.modal {
  position: fixed; inset: 0; z-index: 52;
  display: grid; place-items: center; padding: var(--space-6);
  opacity: 0; visibility: hidden;
  transition: opacity var(--motion-base) var(--ease-standard), visibility var(--motion-base) var(--ease-standard);
}
.modal.is-open { opacity: 1; visibility: visible; }
.modal__dialog {
  width: min(640px, 100%); max-height: calc(100vh - 48px);
  display: flex; flex-direction: column;
  background: var(--surface-overlay); border: 1px solid var(--border); border-radius: var(--radius-lg);
  box-shadow: var(--elev-float);
}
.modal__dialog--wide { width: min(760px, 100%); }
.modal__foot { border-radius: 0 0 var(--radius-lg) var(--radius-lg); }
.toast-host { position: fixed; right: var(--space-6); bottom: var(--space-6); z-index: 70; display: flex; flex-direction: column; gap: var(--space-2); }
.toast {
  display: flex; align-items: center; gap: var(--space-2);
  min-width: 240px; padding: var(--space-3) var(--space-4);
  background: var(--fg); color: var(--surface);
  border-radius: var(--radius-md); box-shadow: var(--elev-float);
  font-size: var(--text-sm);
  opacity: 0; transition: opacity var(--motion-base) var(--ease-standard);
}
.toast.is-on { opacity: 1; }
.empty { display: flex; flex-direction: column; align-items: center; gap: var(--space-2); padding: var(--space-12) var(--space-6); text-align: center; color: var(--muted); }
.empty > .icon { width: 32px; height: 32px; color: var(--border-control); }
.empty__title { font-size: var(--text-base); font-weight: 600; color: var(--fg); }
.empty__desc { max-width: 440px; font-size: var(--text-sm); }
.skeleton { display: block; height: 12px; border-radius: var(--radius-sm); background: var(--surface-raised); animation: pulse calc(var(--motion-base) * 7) var(--ease-standard) infinite alternate; }
```

## 动效与交互物理

- **动效用途**：
  - 只表达两件事：你的操作被接收了（悬停、按下、焦点）；界面状态变了（抽屉打开、任务完成）。
  - 不做装饰性动画。
  - 页面进场只淡入，不位移。
- **时长**：微反馈 150ms（`--motion-fast`），状态切换 200ms（`--motion-base`），曲线统一为 `--ease-standard`。

```css
/* 进场：区块依次淡入，--i 为区块序号（0–5），间隔 50ms */
.enter { animation: enter var(--motion-base) var(--ease-standard) both; animation-delay: calc(var(--i, 0) * var(--motion-fast) / 3); }
@keyframes enter { from { opacity: 0; } to { opacity: 1; } }
@keyframes pulse { from { opacity: 1; } to { opacity: 0.55; } }
@keyframes spin { to { transform: rotate(360deg); } }
.spin { animation: spin calc(var(--motion-base) * 4) var(--ease-linear) infinite; }
.btn.is-loading .icon { animation: spin calc(var(--motion-base) * 4) var(--ease-linear) infinite; }

/* 减少动效：逐类关闭，不用全局选择器 */
@media (prefers-reduced-motion: reduce) {
  .enter, .spin, .skeleton, .btn.is-loading .icon { animation: none; }
  .drawer, .modal, .scrim, .toast, .popover, .tip { transition: none; }
}

/* 响应式 */
@media (max-width: 1599px) {
  .table .col-2 { display: none; }
  .table-wrap.show-all .table .col-2 { display: table-cell; }
}
@media (max-width: 1439px) {
  .content { padding-left: var(--container-gutter-tablet); padding-right: var(--container-gutter-tablet); }
  .topbar { padding: 0 var(--container-gutter-tablet); }
  .version--optional { display: none; }
}
@media (max-width: 1279px) {
  .app { grid-template-columns: var(--sidebar-w-collapsed) minmax(0, 1fr); }
  .app .nav__item span, .app .nav__group, .app .sidebar__brand span, .app .nav__count { display: none; }
  .app .nav__item { justify-content: center; padding: 0; }
  .app .sidebar__brand { justify-content: center; padding: 0; }
  .grid-2, .grid-main-side { grid-template-columns: minmax(0, 1fr); }
  .steps { grid-template-columns: repeat(4, minmax(0, 1fr)); row-gap: var(--space-2); }
  .step:nth-child(4)::after { display: none; }
}
@media (max-width: 767px) {
  .app, .app.is-collapsed { display: block; }
  .sidebar { position: static; height: auto; flex-direction: row; align-items: center; overflow-x: auto; border-right: 0; border-bottom: 1px solid var(--border); }
  .nav { flex-direction: row; padding: var(--space-2); }
  .nav__group, .sidebar__foot { display: none; }
  .topbar { height: auto; flex-wrap: wrap; padding: var(--space-2) var(--container-gutter-phone); }
  .versions { display: none; }
  .content { padding: var(--space-4) var(--container-gutter-phone) var(--space-8); }
  .page-head { flex-direction: column; align-items: flex-start; }
  .section { margin-top: var(--section-y-phone); }
  .steps { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .step::after { display: none; }
  .form-grid { grid-template-columns: minmax(0, 1fr); }
  .form-grid .span-2 { grid-column: auto; }
  .search .input { width: 100%; }
  .drawer { width: 100vw; }
}
```

**状态切换**：
- 标签页：下划线和文字颜色在 150ms 内变化。
- 抽屉：200ms 从右侧推入，遮罩同步淡入。
- 弹窗：只淡入。
- 下拉和浮层：150ms 淡入。
- 长任务完成：顶栏任务指示消失，同时出现一条轻提示，例如"回测完成，用时 18 分钟"。

## 品牌情感与声音

- **品牌灵魂**：一位严谨、可靠的研究同事。它不吹嘘，只说出数字、样本和出处，也承认不确定。依据是这个产品要替代"每次跑出来都不一样"的研究过程，可信度就是它的全部价值。
- **说话方式**：
  - 简体中文、短句、主动语态。
  - 数字带单位和样本量。
  - 不用感叹号和"恭喜""太棒了"之类的词。
  - 说清原因和下一步，不指责使用者。例："有 2 个阻断项，修好数据包后重新导入"，不说"导入失败"。
- **边缘时刻**：
  - **空状态**：一个弱色线性图标，一句话说明"这里会出现什么"，一个去下一步的按钮。例："还没有回测结果。完成成败与信号计算后，在这里运行回测。"
  - **加载**：表格保留上一次的结果并降低不透明度，不闪白；首次加载用骨架条。
  - **长任务**：显示步骤名和百分比，不显示无意义的转圈。
  - **错误**：说清哪个文件、哪个字段、哪几行，给出可执行的修复方式。
- **插画**：不用插画、3D 或 emoji；图标统一用 Phosphor Regular（MIT 许可），线性、16/20px。
- **页面生成准则**（给生成 HTML 的实现者）：
  - 引用 `../tokens.css` 与 `assets/app.css`，`<body>` 第一行加载 `assets/icons.js`。
  - 只用本文件定义的类名和 Token，不写十六进制颜色。
  - 每个比例、命中率和金额都加证据小标签；缺失值用"无数据"标签。
  - 每页最多 1 个主按钮；口径和状态横幅常驻不可关闭。
  - 区间一律用区间条加文字数值；图表遵守"图表部件"一节的规则。

## 设计禁忌

1. 禁止用红色表示"未命中"——未命中是成败结果，不是错误；红色只留给阻断和失败，否则会让你误以为数据出了问题。
2. 禁止显示不带样本量的比例或命中率——口径纪律要求每个统计值都附样本量，没有 n 的百分比会误导立项。
3. 禁止把缺失值显示成 0 或"-"——缺失统一显示"无数据"标签，避免把"不知道"读成"没有"。
4. 禁止把"未验证""截面口径""需重算""阻断"横幅做成可关闭——这些是结论能否使用的前提，关掉就可能被当成正式结论发出去。
5. 禁止用阴影抬升或位移作为悬停反馈——全站统一为色彩响应，混用会让界面显得浮躁、不稳定。
6. 禁止每屏使用超过 2 处强调色，禁止把链接、选中筛选、当前导航做成强调色——强调色只告诉你"下一步点哪里"。
7. 禁止一个页面出现两个主按钮——同一时刻只有一个最重要的动作。
8. 禁止圆角大于 8px（胶囊徽章与筛选标签除外）——大圆角会让高密度表格显得松散，削弱精确感。
9. 禁止数字列左对齐或使用比例数字——上下对比数字是这个工具最常见的动作。
10. 禁止双轴图、彩虹色、渐变填充和 3D 图表——它们会制造不存在的相关性，或夸大差异。
11. 禁止加载外部字体、图标或脚本——本机离线运行，网页报告要离线可读（NFR-006、AC-F12-03）。
12. 禁止使用 emoji 或装饰插画——它们与"严谨研究同事"的性格相悖。
13. 禁止把估算值和实测值写在一起而不加区分——必须用"估算 / 实测"标签标明。
