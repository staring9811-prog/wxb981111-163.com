# v1.1.0：冻结表格、主题切换和安全更新

## 修改
- 所有表格冻结完整多层表头和第一标识列，保留已有多列冻结，正确处理多包裹 rowspan。
- 默认浅色，太阳/月亮 SVG 图标切换，选择记入 pc_theme。
- 新用户默认 OpenAI 兼容格式、DeepSeek 服务、https://api.deepseek.com、deepseek-flash。
- 已保存的供应商/地址/模型/API Key 不迁移、不覆盖。
- 检查 main 正式版，提示后经用户确认下载；下载前要求新鲜完整备份；系统文件不包含用户数据。
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

## 浏览器验证未完成
本地环境没有 Chromium；官方浏览器组件下载失败。独立浏览器不允许 data: 测试页面，故无法声称实际滚动验证通过。
待审查时在正常 HTTP 服务或本地 HTML 实测：确认表水平滚动；双包裹产品名；长表竖向滚动；全渠道对比的两层表头；整页滚动；小窗口；深浅主题切换及刷新。

## 发布与更新
此次尚未发布到 main。首次用户必须重新下载此版，旧版没有检查更新代码，无法自动补装。后续发版应同步提高 HTML pc-app-version、PC_RELEASE.version 和界面版本标签。pc-data-schema 不变时保留 pc_products / pc_params / pc_quotes / pc_history / pc_ai_cfg / pc_theme / pc_step / pc_cur。schema 变化时停止旧版内下载，需先实现并验证迁移。
本地 HTML 请保持原浏览器、文件名和原目录。跨目录/浏览器/电脑必须用完整备份迁移。云端报价/历史库仍由原账户管理，不由本地备份恢复覆盖。
