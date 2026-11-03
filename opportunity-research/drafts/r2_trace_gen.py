"""生成 output/设计追溯矩阵.md（第二轮，revision 7）。"""
import re, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent / "output"
req = (ROOT / "requirements.md").read_text(encoding="utf-8").split("## Retired")[0]

# 解析条目：ID、标题、Parent、Revision、SHALL 文本
items = {}
for m in re.finditer(r"^### ((?:REQ|AC|NFR)-[A-Z0-9-]+) · (.+?)\n(.*?)(?=^### |^## |\Z)", req, re.S | re.M):
    sid, title, body = m.group(1), m.group(2).strip(), m.group(3)
    par = re.search(r"- Parent: (\S+)", body)
    rev = re.search(r"- Revision: (\d+)", body)
    shall = re.findall(r"SHALL (.+)", body)
    meas = re.search(r"- Measure: (.+)", body)
    items[sid] = dict(title=title, parent=par.group(1) if par else None,
                      rev=rev.group(1) if rev else None,
                      inv="；".join(s.strip() for s in shall) or (meas.group(1) if meas else title))
for sid, it in items.items():
    if sid.startswith("REQ"):
        kids = [k for k, v in items.items() if v["parent"] == sid]
        it["inv"] = "子条目全部成立：" + "、".join(f"{k}（{items[k]['title']}）" for k in kids)
    if it["rev"] is None and it["parent"]:
        it["rev"] = items[it["parent"]]["rev"]

# 每个 Feature 的默认设计落点
F = {
 "F15": ("PAGE-F15-01, PAGE-F15-02, PAGE-F15-03", "API-F15-01, API-F15-02, API-F15-03, DATA-F15-01, DATA-F15-02", "§7.2"),
 "F16": ("PAGE-F16-01, PAGE-F16-02, CMP-F16-01", "API-F16-01, API-F16-02, API-F16-03, API-F16-04, DATA-F16-01, DATA-F16-02, DATA-F16-03", "§4 费用闸门"),
 "F17": ("PAGE-F17-01, CMP-F16-01", "API-F17-01, API-F17-02, API-F17-03, API-F16-03, DATA-F16-03, DATA-F17-01, DATA-F17-02, SEQ-F17-01", "§4 时序 1"),
 "F18": ("PAGE-F18-01", "API-F18-01, API-F18-02, DATA-F18-01", "§6.1"),
 "F19": ("PAGE-F19-01", "API-F19-01, DATA-F19-01", "§4 模块边界"),
 "F20": ("PAGE-F20-01", "API-F20-01, DATA-F20-01", "§5.2"),
 "F21": ("PAGE-F21-01, PAGE-F21-02", "API-F21-01, API-F21-02, DATA-F21-01, SEQ-F21-01", "§5.1 状态机"),
 "F22": ("PAGE-F21-02, CMP-F16-01", "API-F22-01, API-F16-03, DATA-F22-01", "§6.1"),
 "F23": ("PAGE-F23-01, CMP-F16-01", "API-F23-01, API-F16-03, DATA-F16-02", "§4 费用闸门"),
 "F24": ("PAGE-F24-01, PAGE-F21-02", "API-F24-01, API-F24-02, DATA-F24-01", "§8.2"),
 "F25": ("PAGE-F25-01, PAGE-F25-02, PAGE-F21-02", "API-F25-01, API-F25-02, DATA-F25-01, DATA-F25-02, DATA-F21-01, SEQ-F25-01", "§4 时序 2"),
 "F26": ("PAGE-F26-01", "API-F26-01, DATA-F26-01, SEQ-F26-01", "附录 A.3"),
 "F27": ("PAGE-F27-01", "API-F27-01, DATA-F27-01", "§5.1"),
 "F28": ("PAGE-F28-01", "API-F28-01, DATA-F28-01", "§5.1"),
 "F29": ("PAGE-F20-01, PAGE-F21-02", "API-F20-01, API-F29-01, DATA-F20-01, DATA-F28-01", "§5.1"),
}
# 个别条目落点细化（页面, 其他 ID）
OVR = {
 "AC-F15-01": ("PAGE-F15-01", "API-F15-01, DATA-F15-01"),
 "AC-F15-02": ("PAGE-F15-02, PAGE-F15-03, PAGE-F21-02", "API-F15-01, DEC-101"),
 "AC-F15-03": ("PAGE-F21-02, PAGE-F25-01", "API-F15-01, API-F25-01"),
 "AC-F15-04": ("PAGE-F15-03", "API-F15-02, API-F15-03, DATA-F15-01, DATA-F15-02"),
 "AC-F15-05": ("PAGE-F15-03, PAGE-F15-01", "API-F15-01, API-F15-02, DATA-F15-01"),
 "REQ-F16-01": ("PAGE-F16-01", "API-F16-01, DATA-F16-01"),
 "REQ-F16-02": ("PAGE-F16-02, CMP-F16-01", "API-F16-02, API-F16-03, API-F16-04, DATA-F16-02"),
 "AC-F16-06": ("PAGE-F16-02, CMP-F16-01", "API-F16-02, API-F16-03, DATA-F16-02"),
 "AC-F16-07": ("PAGE-F16-02, CMP-F16-01, PAGE-F17-01", "API-F16-03, API-F16-04, DATA-F16-02, SEQ-F17-01"),
 "AC-F16-08": ("PAGE-F16-02", "API-F16-04, DATA-F16-02"),
 "AC-F19-04": ("PAGE-F19-01, PAGE-F15-02", "API-F19-01, API-F15-04, DATA-F19-01"),
 "AC-F20-05": ("PAGE-F20-01, PAGE-F21-02", "API-F21-01, DATA-F21-01"),
 "AC-F21-01": ("PAGE-F21-01, PAGE-F21-02", "API-F21-01, API-F21-02, DATA-F21-01"),
 "AC-F21-06": ("PAGE-F21-02", "API-F21-02, API-F16-03, DATA-F21-01"),
 "AC-F24-01": ("PAGE-F24-01", "API-F24-01, DATA-F24-01"),
 "AC-F24-02": ("PAGE-F24-01", "API-F24-01, DATA-F24-01"),
 "AC-F25-02": ("PAGE-F21-02", "API-F21-02, API-F25-01, DATA-F21-01, SEQ-F21-01"),
 "AC-F25-03": ("PAGE-F25-01, PAGE-F26-01", "API-F25-01, DATA-F26-01, SEQ-F25-01"),
 "AC-F26-02": ("PAGE-F26-01, PAGE-F15-02", "API-F26-01, DATA-F26-01, SEQ-F26-01"),
 "AC-F29-01": ("PAGE-F20-01", "API-F20-01, DATA-F20-01, DATA-F28-01"),
 "AC-F29-02": ("PAGE-F20-01", "API-F20-01, DATA-F20-01"),
 "AC-F29-03": ("PAGE-F21-02", "API-F29-01, DATA-F21-01"),
 "AC-F29-04": ("PAGE-F21-02", "API-F29-01, DATA-F21-01"),
}
NFR = {
 "NFR-007": ("PAGE-F15-01", "API-F15-01", "§7.1；附录 A.4", "integration（监听地址检查）"),
 "NFR-008": ("PAGE-F16-01", "API-F16-01, DATA-F16-01", "§7.2、§7.3；附录 A.4", "integration + 仓库/日志扫描"),
 "NFR-009": ("PAGE-F20-01", "API-F20-01, DATA-F20-01", "§5.2；附录 A.4", "性能计时（24 个月数据）"),
 "NFR-010": ("PAGE-F21-02", "API-F21-01, DATA-F21-01", "附录 A.4", "性能计时"),
 "NFR-011": ("PAGE-F17-01, PAGE-F23-01", "API-F16-03, DATA-F16-03, SEQ-F17-01", "§4 后台任务；附录 A.4", "integration（中断重跑计数）"),
 "NFR-012": ("PAGE-F17-01, PAGE-F19-01", "API-F17-03, DATA-F17-01", "§5.1；附录 A.4", "integration（历史月份重放）"),
}

def surface(sid):
    if sid.startswith("REQ"): return "unit + integration + e2e"
    return "integration + e2e"

def arts(pages, sec):
    out = []
    for p in [x.strip() for x in pages.split(",")]:
        if p.startswith("PAGE-"):
            out.append(f"pages/{p}.md; pages/{p}.html")
    out.append(f"技术方案.md {sec}；附录 A")
    return "; ".join(out)

rows = []
for sid, it in items.items():
    if sid.startswith("NFR"):
        if sid not in NFR: continue
        pages, other, sec, ver = NFR[sid]
        rows.append((sid, it["rev"], f"{pages}, {other}", arts(pages, sec), it["inv"], ver))
        continue
    f = re.search(r"-(F\d\d)-", sid).group(1)
    pages, other, sec = F[f]
    if sid in OVR: pages, other = OVR[sid]
    rows.append((sid, it["rev"], f"{pages}, {other}", arts(pages, sec), it["inv"].replace("|", "/"), surface(sid)))

head = """# 设计追溯矩阵（第二轮）

> 来源：`requirements.md` revision 7（scope = 第一版）。全部 active REQ / AC / NFR 都属于本期，状态均为 covered。
>
> 第一轮（revision 5）的条目和设计 ID 已 retired，见 `change-impact.md`。
>
> 设计 ID 定义：PAGE 见 `页面清单.md` 与 `pages/`；CMP-F16-01 = 费用评估确认弹窗（见 PAGE-F16-02）；API / DATA / SEQ 见 `技术方案.md` 附录 A；DEC-101 = 工作台（design-derived，见 `设计决策蓝图.md`）。
>
> 本文件由 `drafts/r2_trace_gen.py` 从需求契约生成；Error/Invariant 列取自各条目的 SHALL / Measure 原文。

| Source ID | Source Revision | Design IDs | Artifact | Error/Invariant | Verification Surface | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""
body = "\n".join(f"| {a} | {b} | {c} | {d} | {e} | {f} | covered |" for a, b, c, d, e, f in rows)
tail = """

## Design-derived 对象

| Design ID | 必要性 | 关联 |
| :--- | :--- | :--- |
| DEC-101 / PAGE-F15-02 / API-F15-04 | 登录后需要一处汇总各角色待办（待确认标签、待审批、到期对账、费用），否则入口分散；wen 已在蓝图确认 | AC-F15-02, AC-F19-04, AC-F26-02 |
"""
(ROOT / "设计追溯矩阵.md").write_text(head + body + tail, encoding="utf-8")
print(len(rows), "rows")
