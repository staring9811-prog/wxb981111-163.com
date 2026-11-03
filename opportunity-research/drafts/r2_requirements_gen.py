import sys
sys.path.insert(0,'.')
exec(open('spec.py',encoding='utf-8').read())
role=lambda r: '审批者' if '老板' in r else '操作者'
L=['# 品类机会判定台 Requirements Contract','','## Metadata','','- work_type: feature','- workflow_mode: standard','- revision: 7','- scope: 第一版','- source_prd: PRD详细版.md','- status: active','',
'> 第二轮（2026-11-03）：承接第二轮《解题方案书》与场景锚点（wen 确认）。第一轮 F01–F14、NFR-001～006 全部 retired（见文末），ID 不复用；第二轮从 F15、NFR-007 起编。第一版 = 浴室柜、在 wen 电脑运行局域网共享、F15–F29 全部交付。revision 7（2026-11-03）：wen 要求把 Home Depot / Lowe\'s / Wayfair 加入第一版，新增 F28、F29，F18、F26、F27 各增一条 REQ。','',
'## External capability configuration','','| Capability | Credential owner | Configuration actor | Surface | Scope | Lifecycle | Stage | Requirement IDs |','| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |']
for cap,ids in (('卖家精灵接口（Amazon 月度数据、Amazon 评论）','REQ-F16-01, REQ-F17-01, REQ-F22-01'),('Bright Data（Lowe\'s / Wayfair 页面）','REQ-F16-01, REQ-F23-01'),('Apify（Lowe\'s / Wayfair 评论）','REQ-F16-01, REQ-F23-01'),('大模型（Claude / OpenAI 等，看图打元素、差评归类、叙述草稿）','REQ-F16-01, REQ-F18-01, REQ-F21-03, REQ-F22-02')):
    L.append(f'| {cap} | wen（公司账号） | 操作者 | settings | system | 添加、测试、掩码显示后 4 位、更换、删除；失效时相关功能显示未连接 | 第一版 | {ids} |')
L+=['','## Capability prerequisites','','| Prerequisite | Status | Owner | Evidence or deadline | Fallback | Stage | Requirement IDs |','| :--- | :--- | :--- | :--- | :--- | :--- | :--- |',
'| 卖家精灵接口可用、能按月拉浴室柜类目全量 | ready | wen | 2024-10 至 2025-12 月度数据与评论已用卖家精灵 MCP 拉取（solution-v2/数据准备/卖家精灵导出_2025-03至12_核对.md；evidence/差评_*.md） | 拉取失败时 wen 手动导出上传同格式文件（F17 导入核对照常） | 第一版 | REQ-F17-01, REQ-F22-01 |',
'| Bright Data、Apify 账号与 IP 白名单 | ready | wen | 评论月度 VP 追踪器已在用（tools/评论月度VP追踪器/services.md） | 只采 Home Depot（直连免费），Lowe\'s / Wayfair 跳过 | 第一版 | REQ-F23-01 |',
'| 大模型密钥（至少一家） | committed | wen | wen 2026-11-03 确认由其在设置页填写；截止：第一版联调开始前 | 元素全部进入人工确认；差评只显示原文、不归类；不起草叙述 | 第一版 | REQ-F18-01, REQ-F22-02, REQ-F21-03 |',
'| wen 电脑作为运行机、局域网可访问 | ready | wen | wen 2026-11-03 选择"你的电脑上运行，局域网共享" | 只在 wen 本机使用，决策卡导出分享 | 第一版 | REQ-F15-01 |','']
for fid,name,us,reqs in F:
    n=fid[1:]; L+=[f'## Feature {fid} · {name}','',f'### US-{fid}-01 · {us[1]}','',f'- Role: {role(us[0])}',f'- Goal: {us[1]}',f'- Value: {us[2]}','- Stage: 第一版','- Status: active','']
    ac=0
    for i,(rt,acs) in enumerate(reqs,1):
        L+=[f'### REQ-{fid}-{i:02d} · {rt}','',f'- Story: US-{fid}-01','- Stage: 第一版','- Revision: 1','- Status: active','']
        for at,w,s,p in acs:
            ac+=1; L+=[f'### AC-{fid}-{ac:02d} · {at}','',f'- Parent: REQ-{fid}-{i:02d}',f'- Priority: {p}','- EARS:','','```text',f'WHEN {w}',f'THE SYSTEM SHALL {s}','```','']
L+=['## Non-functional requirements','']
for i,(t,a,m) in enumerate(NFR,7):
    L+=[f'### NFR-{i:03d} · {t}','',f'- Applies-to: {a}','- Revision: 1','- Status: active',f'- Measure: {m}','']
L+=['## Retired（第一轮，revision 5 及以前）','','第一轮需求契约（F01–F14，及其 US / REQ / AC；NFR-001～006）于 revision 6 整体 retired：第一轮 PRD v5 于 2026-10-27 被 wen 判定未达预期，第二轮以新《解题方案书》为准重写。原文见 git 历史（本文件 revision 5 版本）。这些 ID 永不复用。','']
open(sys.argv[1],'w',encoding='utf-8').write('\n'.join(L)+'\n'); print(len(L))
