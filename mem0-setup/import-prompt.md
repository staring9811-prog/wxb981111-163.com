# 给 Codex 的指令：导入云端会话记忆

把下面整段复制给本地 Codex 执行。

---

请把仓库 staring9811-prog/wxb981111-163.com（分支 claude/brave-galileo-sw5mud）里的 `mem0-setup/cloud-memories-20261028.json` 导入我的 mem0。这是从我的云端 Claude Code 会话整理出的 38 条工作记忆。

要求：
1. 先拉取该分支，读取 JSON。每条有 `text`、`project`、`type` 三个字段。
2. 用 mem0 官方 SDK 或 MCP 写入，参数名以当前官方文档为准：
   - user_id = "wxb"，agent_id = "claude-code-cloud"
   - metadata = {"project": ..., "type": ..., "source": "cloud-claude-code", "imported_at": "2026-10-28"}
   - 这些文本已经提炼好，写入时关闭自动提取（例如 `infer=False`），保持原文；如果当前版本没有这个选项，正常写入后核对结果有没有被改写或拆散
   - type 为“进度”的记忆，如果支持过期时间，设为 30 天后过期
3. 写入前先按 text 搜索一次，已有相同或几乎相同的记忆就跳过，避免重复。
4. API key 只从环境变量 `MEM0_API_KEY` 读取，不打印、不写进文件。
5. 导入后验收：搜索“广告花费怎么拆”“实木怎么判断”“命中率怎么算”各一次，确认能查到对应记忆。
6. 最后给我一张表：成功写入几条、跳过几条（重复）、失败几条及原因，以及第 5 步三次搜索的结果。
