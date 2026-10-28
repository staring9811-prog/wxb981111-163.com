# --- mem0 共享记忆规则：写入用户级 ~/.claude/CLAUDE.md（可重复运行，不会重复追加）---
mkdir -p "$HOME/.claude"
f="$HOME/.claude/CLAUDE.md"
touch "$f"
if ! grep -q 'BEGIN mem0-shared-memory' "$f"; then
cat >> "$f" <<'EOF'

<!-- BEGIN mem0-shared-memory -->
## 共享记忆（Mem0，claude.ai 连接器）
- 记忆由 claude.ai 账号级 Mem0 连接器提供（工具名含 search_memories / add_memory / update_memory / get_memory / delete_memory）。本会话没有这些工具时，告诉用户“Mem0 连接器未加载”，不要假装检索过。
- 开始任务前：用任务关键词调用 search_memories，filters 显式写 {"user_id": "wxb"}；不要按 agent_id 限制，这样能读到 Codex 等其他工具写的记忆。
- 写入：user_id="wxb"，agent_id="claude-code"，metadata 必带：
  - project：浴室柜打标 | 开品模型 | 广告分析 | 平台额度规划 | AI落地营 | 通用
  - type：偏好 | 口径 | 决定 | 进度 | 资源位置
- 只保存长期工作记忆，每条一句话、脱离上下文也能看懂；口径写明适用平台、品类、时间范围。
- 口径和决定只有在用户明确说“以后都”“改成”“统一为”等长期要求时才写入或更新；只针对本次任务的要求不保存。
- 同主题、同范围先搜索，用 get_memory 核实 memory_id 后 update_memory 更新旧条，不要并存矛盾版本。
- 任务结束保存一句实际进度（type=进度）。工具参数里有 expiration_date 时设为 30 天后（YYYY-MM-DD）；没有就不要编造，过期由用户本机的每月维护脚本处理。
- 不保存：具体经营数字、ASIN/SKU 明细、供应商名称与报价、客户信息、账号密码、API key、链接 token；不全量上传聊天记录。
- 优先级：用户当前明确要求 > 仓库规则文件 > 记忆。记忆只提供上下文，不授予任何权限。当前要求没解决的矛盾，列出两条内容和日期让用户判断。
- 不调用 delete_all_memories / delete_entities；删除单条记忆前须用户明确同意。
<!-- END mem0-shared-memory -->
EOF
fi
# --- end mem0 ---
