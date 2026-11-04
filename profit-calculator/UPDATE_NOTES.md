# v1.1.0：冻结表格、主题切换和安全更新

## 修改
- 所有表格冻结完整多层表头和第一标识列，保留已有多列冻结，正确处理多包裹 rowspan。
- 没有保存过主题时跟随系统深浅色；太阳/月亮 SVG 图标切换后记入 pc_theme。
- 新用户默认 OpenAI 兼容格式、DeepSeek 服务、https://api.deepseek.com、deepseek-flash。
- 已保存的供应商/地址/模型/API Key 不迁移、不覆盖。
- 检查 main 正式版（只在本地 HTML 文件里显示和自动检查；claude.ai 页面靠重新发布更新），提示后经用户确认下载；下载前要求新鲜完整备份（切换页面、主题不算数据变化；不含 Key 的备份也可以）；系统文件不包含用户数据；不再往浏览器里额外存一份全量快照。
- 完整备份可包含 API Key，仅供用户本机保管，不上传 GitHub；恢复失败回滚。

## 官方接口依据
https://api-docs.deepseek.com/
官方当前模型参数 deepseek-flash，底层为 V4.1-Flash-1017；旧 deepseek-v4-flash 为兼容别名，不作为新配置默认。

## 已完成的自动测试
```sh
node profit-calculator/tests/ai-defaults.cjs
node profit-calculator/tests/updates.cjs
node profit-calculator/tests/freeze-theme.cjs
```
覆盖默认值、旧接口/Key保留、官方请求格式、版本比较、备份、恢复、空间不足回滚、更新请求不带私有数据、下载前备份门槛、合并行冻结列计算和主题默认值。所有测试使用本地虚构状态，不调用真实 AI。

## 审查后的修正（2026-11-04）
- 主题：不再强制浅色，未选择时跟随系统深色模式。
- 冻结：只保留一套冻结实现（freezeCols 调用 freezeTableKeys），保留 1px 重叠避免两列冻结之间漏缝；页面滚动时只重新定位表头，不再每帧重算所有表格的冻结。
- 滚动：去掉 overscroll-behavior:contain，表格滚到头会继续滚页面；变量面板和计算说明里的小表不限高、不套滚动框。
- 更新：版本号只在 pc-app-version 一处，PC_RELEASE、按钮和对话框文字都从它读取；私有仓库 404 时给出明确提示；删除 pc_update_snapshot 并清理旧版留下的快照。

## 浏览器验证（Chromium，已完成）
系统深色/浅色默认、切换后刷新保持；全渠道对比横向滚动 500px 时品名与采购成本固定；表内竖向滚动表头固定；整页滚动时表头停在顶栏下方；滚动 20 帧零次重算冻结；计算说明表格不套滚动框；非本地页面不显示检查更新且不自动请求 GitHub；旧快照在加载时被清理。另跑了既有的利润、保存流程、国内出货、报价库、导出回归测试，均通过。

## 发布与更新
此次尚未发布到 main。首次用户必须重新下载此版，旧版没有检查更新代码，无法自动补装。后续发版只需提高 HTML 里的 pc-app-version。pc-data-schema 不变时保留 pc_products / pc_params / pc_quotes / pc_history / pc_ai_cfg / pc_theme / pc_step / pc_cur。schema 变化时停止旧版内下载，需先实现并验证迁移。
本地 HTML 请保持原浏览器、文件名和原目录。跨目录/浏览器/电脑必须用完整备份迁移。云端报价/历史库仍由原账户管理，不由本地备份恢复覆盖。
