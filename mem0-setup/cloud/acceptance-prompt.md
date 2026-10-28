# 新云端会话里的 Mem0 验收指令

在连接好 Mem0 连接器并在环境里加好 Setup script 之后，新开一个云端会话，把下面整段发给它。

---

请做 Mem0 云端接入的真实验收，只用本会话实际加载的 Mem0 连接器工具，不要用 REST，也不要读取任何密钥。

0. 先确认：本会话工具列表里是否有 Mem0 工具（search_memories、add_memory、get_memory、update_memory、delete_memory）；`~/.claude/CLAUDE.md` 里是否有 `BEGIN mem0-shared-memory` 段落。任一项没有就停下报告，不要继续。
1. search_memories：query="Mem0共享记忆配置进度"，filters={"user_id": "wxb"}。报告是否找到本机 Codex 保存的那条（给出 memory_id 前 8 位和创建日期，不贴全文以外的敏感信息）。
2. add_memory：文本“云端验收测试记忆，可删除”，user_id="wxb"，agent_id="claude-code"，metadata={"project": "通用", "type": "进度", "test_run": "cloud-accept-<当前UTC时间到秒>"}；如果工具支持关闭自动提取（infer=false），就关闭。
3. 用 test_run 值搜索或 get_memories 读回这条，记录 memory_id。如果写入是异步的，等待后重试，最多 5 次。
4. update_memory：同一个 memory_id，文本改为“云端验收测试记忆（已更新），可删除”。再按 test_run 回查，确认只有 1 条且内容已更新。
5. delete_memory：只删除第 3 步记录的那个 memory_id（用户已授权删除本次测试新建的记忆）。再按 test_run 回查，确认残留为 0。不要调用 delete_all_memories 或 delete_entities。
6. 最后给一张表：检索 / 保存 / 更新 / 删除 各自是否通过；CLAUDE.md 规则是否已由 Setup script 加载；本会话有没有 UserPromptSubmit 钩子做自动检索（没有就写“依赖模型遵守指令”）。
