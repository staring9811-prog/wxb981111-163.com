"""生成 output/设计追溯矩阵.md（第二轮，revision 10）。"""
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
 "F30": ("PAGE-F30-01, PAGE-F30-02", "API-F30-02, DATA-F30-02", "附录 A.1、A.2"),
}
# 个别条目落点细化（页面, 其他 ID）
OVR = {
 "REQ-F18-04": ("PAGE-F18-01", "API-F18-01, DATA-F18-01, DATA-F28-02"),
 "AC-F18-08": ("PAGE-F18-01", "API-F18-01, DATA-F18-01, DATA-F28-02"),
 "REQ-F19-03": ("PAGE-F19-01, PAGE-F21-02", "API-F19-02, DATA-F19-02, SEQ-F23-01"),
 "AC-F19-05": ("PAGE-F19-01", "API-F19-02, DATA-F19-02, SEQ-F23-01"),
 "AC-F19-06": ("PAGE-F19-01, PAGE-F20-01", "API-F19-02, DATA-F19-02"),
 "AC-F20-03": ("PAGE-F20-01", "API-F20-01, API-F19-02, DATA-F20-01, DATA-F19-02"),
 "REQ-F23-02": ("PAGE-F23-01, CMP-F16-01", "API-F23-02, API-F16-03, DATA-F28-02, SEQ-F23-01"),
 "AC-F23-03": ("PAGE-F23-01, CMP-F16-01", "API-F23-02, API-F16-03, DATA-F28-02, SEQ-F23-01"),
 "AC-F23-04": ("PAGE-F23-01", "API-F23-02, DATA-F28-02"),
 "REQ-F28-03": ("PAGE-F28-01", "API-F28-02, DATA-F28-02, SEQ-F23-01"),
 "AC-F28-06": ("PAGE-F28-01", "API-F28-02, DATA-F28-02, SEQ-F23-01"),
 "AC-F28-07": ("PAGE-F28-01", "API-F28-02, DATA-F28-02"),
 "AC-F28-08": ("PAGE-F28-01", "API-F28-02, DATA-F28-02"),
 "REQ-F29-03": ("PAGE-F20-01, PAGE-F21-02", "API-F29-02, DATA-F20-01, DATA-F28-02"),
 "AC-F29-05": ("PAGE-F20-01, PAGE-F21-02", "API-F29-02, DATA-F20-01, DATA-F28-02"),
 "AC-F29-06": ("PAGE-F20-01", "API-F29-02, DATA-F20-01"),
 "AC-F27-04": ("PAGE-F27-01", "API-F27-01, DATA-F27-01"),
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
 # v9 渠道调研
 "REQ-F30-01": ("PAGE-F30-03", "API-F30-01, DATA-F30-01, DATA-F30-02, SEQ-F30-01"),
 **{f"AC-F30-0{i}": ("PAGE-F30-03", "API-F30-01, DATA-F30-01, DATA-F30-02, SEQ-F30-01") for i in range(1, 9)},
 "AC-F30-06": ("PAGE-F30-03", "API-F30-01, DATA-F30-01, DATA-F28-01, SEQ-F30-01"),
 "AC-F30-08": ("PAGE-F30-03", "API-F30-01, DATA-F30-02, DATA-F28-01, DATA-F20-01"),
 "AC-F30-09": ("PAGE-F30-03, PAGE-F30-01", "API-F30-01, API-F15-01"),
 "AC-F30-10": ("PAGE-F30-01", "API-F30-02, DATA-F30-02, DATA-F18-01"),
 "AC-F30-16": ("PAGE-F30-02", "API-F30-02, DATA-F30-02, DATA-F17-02"),
 "AC-F30-22": ("PAGE-F30-01, PAGE-F15-02", "API-F30-02, DATA-F30-01, DEC-105"),
 "AC-F30-23": ("PAGE-F30-01, PAGE-F15-02", "API-F30-02, DATA-F30-02, DEC-105"),
 "AC-F30-25": ("PAGE-F30-02", "API-F30-02, API-F19-02, API-F20-01, DATA-F19-02"),
 "REQ-F30-04": ("PAGE-F18-01, PAGE-F30-01", "API-F30-01, API-F30-02, API-F18-02, DATA-F18-01, SEQ-F30-01"),
 "AC-F30-26": ("PAGE-F18-01", "API-F30-01, API-F18-02, DATA-F18-01, SEQ-F30-01"),
 "AC-F30-27": ("PAGE-F30-01, PAGE-F18-01", "API-F30-02, API-F18-02"),
 "AC-F30-28": ("PAGE-F18-01", "API-F18-02, DATA-F18-01"),
 "AC-F30-29": ("PAGE-F18-01, PAGE-F30-01", "API-F18-02, API-F30-02, DATA-F30-02, SEQ-F30-01, DEC-106"),
 "AC-F30-30": ("PAGE-F30-03, PAGE-F18-01", "API-F30-01, DATA-F18-01"),
}
# 第二版（planned）：只有骨架落点
PLANNED = {
 "REQ-F30-05": ("PAGE-F30-01, API-F16-03, DATA-F30-01", "页面清单.md（PAGE-F30-01 planned 能力）; 设计决策蓝图.md §12.1; 技术方案.md §8.3", "第二版启动时补抓取入口、费用闸门与核对衔接的详细设计；抓取产出须与导入同字段、走 API-F30-01 同一核对"),
}
PLANNED["AC-F30-31"] = PLANNED["REQ-F30-05"]
PLANNED["AC-F30-32"] = ("PAGE-F30-01, API-F16-03, DATA-F30-01", PLANNED["REQ-F30-05"][1], "第二版启动时设计月度续更的断点与不重复计费（沿用 NFR-011 机制）")
# 本期 F30 中落在 PAGE-F30-02 的条目
for _k in ("AC-F30-13", "AC-F30-14", "AC-F30-15", "AC-F30-17"):
    OVR[_k] = ("PAGE-F30-02", "API-F30-02, DATA-F30-02")
for _k in ("AC-F30-11", "AC-F30-12", "AC-F30-18", "AC-F30-19", "AC-F30-20", "AC-F30-21", "AC-F30-24"):
    OVR[_k] = ("PAGE-F30-01, PAGE-F30-02", "API-F30-02, DATA-F30-02")
NFR = {
 "NFR-007": ("PAGE-F15-01", "API-F15-01", "§7.1；附录 A.4", "integration（监听地址检查）"),
 "NFR-008": ("PAGE-F16-01", "API-F16-01, DATA-F16-01", "§7.2、§7.3；附录 A.4", "integration + 仓库/日志扫描"),
 "NFR-009": ("PAGE-F20-01", "API-F20-01, DATA-F20-01", "§5.2；附录 A.4", "性能计时（24 个月数据）"),
 "NFR-010": ("PAGE-F21-02", "API-F21-01, DATA-F21-01", "附录 A.4", "性能计时"),
 "NFR-011": ("PAGE-F17-01, PAGE-F23-01", "API-F16-03, DATA-F16-03, SEQ-F17-01", "§4 后台任务；附录 A.4", "integration（中断重跑计数）"),
 "NFR-013": ("PAGE-F23-01", "API-F23-02, DATA-F28-02, SEQ-F23-01", "§4 后台任务；附录 A.3、A.4", "integration（假站点记录请求时间戳与重试）"),
 "NFR-012": ("PAGE-F17-01, PAGE-F19-01", "API-F17-03, DATA-F17-01", "§5.1；附录 A.4", "integration（历史月份重放）"),
 "NFR-014": ("PAGE-F30-01, PAGE-F30-02, PAGE-F30-03", "API-F30-01, API-F30-02, DATA-F30-02", "附录 A.4", "性能计时（三平台实际规模 CSV）"),
}

# v10 决策卡改版、白话、需求范围、分框调整、调研主图与门槛
for _k in ("REQ-F18-05", "AC-F18-09", "AC-F18-10", "AC-F18-11"):
    OVR[_k] = ("PAGE-F18-01, PAGE-F27-01", "API-F18-03, DATA-F18-01, DATA-F27-02")
for _k in ("REQ-F18-06", "AC-F18-12", "AC-F18-13"):
    OVR[_k] = ("PAGE-F18-01", "API-F18-02, DATA-F30-03")
for _k in ("REQ-F19-04", "AC-F19-07", "AC-F19-08", "AC-F19-09", "AC-F19-10", "AC-F19-11"):
    OVR[_k] = ("PAGE-F19-01", "API-F19-01, DATA-F19-01, CMP-F21-01, CMP-F21-02")
for _k in ("REQ-F20-03", "AC-F20-06", "AC-F20-07", "AC-F20-08"):
    OVR[_k] = ("PAGE-F20-01", "API-F20-02, DATA-F20-01, CMP-F21-01")
for _k in ("REQ-F21-04", "AC-F21-07", "AC-F21-08", "AC-F21-09"):
    OVR[_k] = ("PAGE-F21-02", "API-F21-03, DATA-F21-01, CMP-F21-01")
for _k in ("REQ-F21-05", "AC-F21-10", "AC-F21-11"):
    OVR[_k] = ("PAGE-F21-02, PAGE-F26-01", "API-F21-03, API-F26-01, DATA-F21-01, DATA-F26-01")
for _k in ("REQ-F21-06", "AC-F21-12", "AC-F21-13"):
    OVR[_k] = ("PAGE-F21-02", "API-F21-03, CMP-F21-01, CMP-F21-02")
for _k in ("REQ-F21-07", "AC-F21-14", "AC-F21-15", "AC-F21-16", "AC-F21-17", "AC-F21-18"):
    OVR[_k] = ("PAGE-F21-02", "API-F21-03, API-F30-02, DATA-F21-01, DATA-F30-02, DATA-F30-03, CMP-F21-03")
for _k in ("REQ-F30-06", "AC-F30-33"):
    OVR[_k] = ("PAGE-F30-03, PAGE-F18-01, PAGE-F21-02", "API-F30-01, DATA-F30-03")
for _k in ("REQ-F30-07", "AC-F30-34", "AC-F30-35"):
    OVR[_k] = ("PAGE-F30-01, PAGE-F30-02, PAGE-F27-01, PAGE-F21-02", "API-F30-02, DATA-F27-02")
OVR["REQ-F26-02"] = ("PAGE-F26-01", "API-F26-01, DATA-F26-01, SEQ-F26-01")
OVR["REQ-F27-01"] = ("PAGE-F27-01", "API-F27-01, DATA-F27-01, DATA-F27-02")
OVR["AC-F27-01"] = ("PAGE-F27-01", "API-F27-01, DATA-F27-01, DATA-F27-02")
NFR["NFR-015"] = ("PAGE-F18-01, PAGE-F19-01, PAGE-F20-01, PAGE-F21-02", "CMP-F21-01, CMP-F21-02", "附录 A.4、A.5；DESIGN.md 表头说明", "视觉复核 + 页面文本扫描")

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
        rows.append((sid, it["rev"], f"{pages}, {other}", arts(pages, sec), it["inv"], ver, "covered"))
        continue
    f = re.search(r"-(F\d\d)-", sid).group(1)
    pages, other, sec = F[f]
    if sid in OVR: pages, other = OVR[sid]
    if sid in PLANNED:
        d, a, note = PLANNED[sid]
        rows.append((sid, it["rev"], d, a, note, "第二版启动时深设计与验收", "planned"))
        continue
    rows.append((sid, it["rev"], f"{pages}, {other}", arts(pages, sec), it["inv"].replace("|", "/"), surface(sid), "covered"))

head = """# 设计追溯矩阵（第二轮）

> 来源：`requirements.md` revision 10（scope = 第一版）。第一版的 active REQ / AC / NFR 状态为 covered；REQ-F30-05、AC-F30-31、AC-F30-32 属第二版（未启动），状态为 planned。
>
> 第一轮（revision 5）的条目和设计 ID 已 retired，见 `change-impact.md`。
>
> 设计 ID 定义：PAGE 见 `页面清单.md` 与 `pages/`；CMP-F16-01 = 费用评估确认弹窗（见 PAGE-F16-02）；CMP-F21-01～03 = 表头说明、好坏着色、按月柱状图（见 DESIGN.md）；API / DATA / SEQ 见 `技术方案.md` 附录 A；DEC-101 = 工作台、DEC-105 = 工作台渠道调研行、DEC-106 = 重算出错保留上次结果（design-derived，见 `设计决策蓝图.md`）。
>
> 本文件由 `drafts/r2_trace_gen.py` 从需求契约生成；Error/Invariant 列取自各条目的 SHALL / Measure 原文。

| Source ID | Source Revision | Design IDs | Artifact | Error/Invariant | Verification Surface | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""
body = "\n".join(f"| {a} | {b} | {c} | {d} | {e} | {f} | {g} |" for a, b, c, d, e, f, g in rows)
tail = """

## Design-derived 对象

| Design ID | 必要性 | 关联 |
| :--- | :--- | :--- |
| DEC-101 / PAGE-F15-02 / API-F15-04 | 登录后需要一处汇总各角色待办（待确认标签、待审批、到期对账、费用），否则入口分散；wen 已在蓝图确认 | AC-F15-02, AC-F19-04, AC-F26-02 |
| DEC-102 / PAGE-F17-01 | AC-F17-04 只说"超出设定阈值"，没给默认值。设计默认：品类总月销环比 ±30% 内、家族键月间一致率 ≥ 90%、每个标签覆盖率 ≥ 95%；wen 2026-11-03 确认 | AC-F17-04 |
| DEC-103 / PAGE-F15-03 | 最后一个正常状态的操作者不能停用，防止没人能管账号；wen 2026-11-03 确认 | AC-F15-04 |
| DEC-105 / PAGE-F15-02 | 渠道调研不在"其他渠道数据"里，工作台本月数据状态需要一行汇总各渠道调研状态与分框待确认数，否则入口只在侧栏；wen 2026-11-04 蓝图 §12 确认 | AC-F30-22, AC-F30-23 |
| DEC-106 / PAGE-F30-01 / API-F30-02 | AC-F30-29 只规定确认后重算，没规定重算出错时显示什么；设计默认保留上次结果并显示出错原因与结果时间，避免空白页；wen 2026-11-04 蓝图 §12 确认 | AC-F30-29 |
| DEC-104 / PAGE-F16-02 | 用到月度上限 80% 时显示"接近上限"，只提示，不改变到上限即停（AC-F16-06）；wen 2026-11-03 确认 | AC-F16-06 |
"""
(ROOT / "设计追溯矩阵.md").write_text(head + body + tail, encoding="utf-8")
print(len(rows), "rows")
