#!/usr/bin/env python3
"""Equivalent checker for output/tests/TDD验收契约.md and TDD验收结果.md.

Used because the installed tdd-master validator could not be executed in this
environment. It mechanically checks the same things the TDD spec (§3, §5.3, §7)
requires: contract structure, scope/revision vs requirements.md, design trace
matrix coverage, page list coverage, and (with --result) the execution ledger.

Usage: python3 tools/check_contract.py [--result] <project>/output
Standard library only.
"""

from __future__ import annotations

import hashlib
import re
import struct
import sys
from pathlib import Path

SRC = r"(?:REQ-F\d{2,3}-\d{2,3}|AC-F\d{2,3}-\d{2,3}|NFR-\d{3}|REPRO-\d{3}|CUR-\d{3}|EXP-\d{3}|UNCH-\d{3}|CON-\d{3})"
SRC_RE = re.compile(SRC)
SRC_HEAD_RE = re.compile(r"^###\s+(" + SRC + r")\b", re.M)
DESIGN_RE = re.compile(
    r"(?:PAGE-F\d{2,3}-\d{2,3}|CMP-F\d{2,3}-\d{2,3}|API-F\d{2,3}-\d{2,3}|DATA-F\d{2,3}-\d{2,3}"
    r"|SEQ-F\d{2,3}-\d{2,3}|DEC-\d{3}|FIX-BUG-\d{3})"
)
PAGE_RE = re.compile(r"PAGE-F\d{2,3}-\d{2,3}")
PAGE_PATH_RE = re.compile(r"(?:output/)?pages/[^\s;|`]+?\.(?:md|html)", re.I)
TEST_ID_RE = re.compile(r"(?:SMOKE|FLOW|RULE|DESIGN)-\d{2,3}|BUG-(?:REPRO|FIX|REG|RULE)-\d{2,3}")
PLACEHOLDER_RE = re.compile(r"\{\{|\b(?:TBD|TODO)\b|待定|占位", re.I)
ANCHORS = ("结构", "组件", "内容", "交互", "视觉", "原生适配")
SECTIONS = ("## 0. 契约元信息", "## 1. 完成定义", "## 2. 冒烟门禁", "## 3. 功能与流程验收",
            "## 4. 设计落地验收", "## 5. 风险触发验收", "## 6. 本期不阻塞项")


def meta(text: str, name: str) -> str | None:
    m = re.search(rf"^- {re.escape(name)}:[^\S\n]*(.*?)[^\S\n]*$", text, re.M | re.I)
    return m.group(1).strip().strip("`") if m else None


def empty(value: str, allow_dash: bool = False) -> bool:
    v = value.strip().strip("`")
    if not v or PLACEHOLDER_RE.search(v) or re.fullmatch(r"(?:missing|缺失)", v, re.I):
        return True
    return v == "-" and not allow_dash


def cells_of(line: str) -> list[str]:
    out, start, bs, s = [], 0, 0, line.strip()
    for i, ch in enumerate(s):
        if ch == "|" and bs % 2 == 0:
            out.append(s[start:i].strip())
            start = i + 1
        bs = bs + 1 if ch == "\\" else 0
    out.append(s[start:].strip())
    if s.startswith("|"):
        out.pop(0)
    if out and not out[-1] and s.endswith("|"):
        out.pop()
    return out


def id_rows(text: str, pattern: re.Pattern, ncols: int, label: str, errs: list[str], strict=False) -> list[list[str]]:
    rows, in_table = [], False
    for no, line in enumerate(text.splitlines(), 1):
        if not line.lstrip().startswith("|"):
            in_table = False
            continue
        c = cells_of(line)
        if c and c[0].strip("`").lower() in {"id", "tdd id"}:
            in_table = True
            continue
        if c and all(re.fullmatch(r":?-+:?", x.strip()) for x in c):
            continue
        rid = c[0].strip("`") if c else ""
        if not pattern.fullmatch(rid):
            if strict and c and (in_table or re.match(r"(?:SMOKE|FLOW|RULE|DESIGN|BUG)(?:[-_\s]|$)", rid, re.I)):
                errs.append(f"{label}第 {no} 行验收 ID 非法: {rid or '(空)'}")
            continue
        if len(c) != ncols:
            errs.append(f"{label}第 {no} 行 {rid} 列数 {len(c)} != {ncols}")
            continue
        c[0] = rid
        rows.append(c)
    return rows


def source_blocks(text: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    seen: set[str] = set()
    for m in SRC_HEAD_RE.finditer(text):
        nxt = re.search(r"^#{1,3}\s+", text[m.end():], re.M)
        block = text[m.start(): m.end() + (nxt.start() if nxt else len(text))]
        sid = m.group(1)
        if sid in seen:
            raise ValueError(f"上游重复定义 Source ID: {sid}")
        seen.add(sid)
        if (meta(block, "Status") or "").lower() != "retired":
            blocks[sid] = block
    return blocks


def metadata_section(text: str) -> str:
    m = re.search(r"^## Metadata[^\S\n]*\n(.*?)(?=^#{2,3} |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def norm_stage(v: str) -> str | None:
    v = v.strip().strip("`")
    if not v or re.search(r"\{\{|\}\}|[,，]|^(?:TBD|TODO|unknown|missing|待定|待确认|未知|缺失|-)$", v, re.I):
        return None
    if v.upper() == "MVP":
        return "阶段1"
    m = re.fullmatch(r"阶段\s*([0-9]+|[一二三四五六七八九十])\s*(?:[（(]\s*MVP\s*[）)]|MVP)?", v, re.I)
    if not m:
        return v
    n = m.group(1)
    k = int(n) if n.isascii() and n.isdecimal() else "一二三四五六七八九十".index(n) + 1
    if k < 1 or ("MVP" in v.upper() and k != 1):
        return None
    return f"阶段{k}"


def parse_scope(value: str | None, label: str, errs: list[str]) -> set[str]:
    out = set()
    for item in re.split(r"[,，]", value or ""):
        s = norm_stage(item)
        if s is None:
            errs.append(f"{label} 含空白或未知 Stage: {item.strip() or '(空)'}")
        else:
            out.add(s)
    return out


def scoped_reqs(blocks, stages):
    return {k for k, b in blocks.items() if k.startswith("REQ-") and norm_stage(meta(b, "Stage") or "") in stages}


def scoped_sources(blocks, stages, required_only=False):
    reqs = scoped_reqs(blocks, stages)
    sel = set(reqs)
    for k, b in blocks.items():
        if k.startswith("AC-") and meta(b, "Parent") in reqs:
            if not required_only or (meta(b, "Priority") or "").upper() in {"P0", "P1"}:
                sel.add(k)
        elif k.startswith("NFR-"):
            ap = set(SRC_RE.findall(meta(b, "Applies-to") or ""))
            if not ap or ap & reqs:
                sel.add(k)
    return sel


def check_trace(src_text, trace_text, contract, work_type, stages, out: Path) -> list[str]:
    errs: list[str] = []
    blocks = source_blocks(src_text)
    rev = meta(metadata_section(src_text), "revision")
    if empty(rev or ""):
        errs.append("上游 Metadata 缺少有效 revision")
    if meta(contract, "source_revision") != rev or not rev:
        errs.append("TDD source_revision 与上游 Metadata revision 不一致")
    if work_type == "feature":
        for k, b in blocks.items():
            if k.startswith("REQ-") and norm_stage(meta(b, "Stage") or "") is None:
                errs.append(f"{k} Stage 缺失或无法识别")
            if k.startswith("AC-") and (meta(b, "Parent") or "") not in blocks:
                errs.append(f"{k} 的 Parent 缺失或不是 active REQ")
    selected = scoped_sources(blocks, stages) if work_type == "feature" else set(blocks)
    traced = set()
    for c in id_rows(trace_text, SRC_RE, 7, "设计追溯矩阵", errs):
        sid = c[0]
        if sid not in blocks:
            errs.append(f"设计矩阵包含未定义或 retired Source: {sid}")
            continue
        traced.add(sid)
        b = blocks[sid]
        exp = meta(b, "Revision")
        if not exp and sid.startswith("AC-"):
            exp = meta(blocks.get(meta(b, "Parent") or "", ""), "Revision")
        exp = exp or rev
        if c[1].strip("`") != exp:
            errs.append(f"设计矩阵 {sid} Source Revision {c[1]} != {exp}")
        status = c[6].strip("`").lower()
        allowed = {"covered", "preserved"} if sid in selected else {"covered", "preserved", "planned"}
        if status not in allowed:
            errs.append(f"设计矩阵 {sid} 状态不可交付: {status}")
        if not DESIGN_RE.search(c[2]):
            errs.append(f"设计矩阵 {sid} 缺少合法 Design ID")
        for i, lab in ((3, "Artifact"), (4, "Error/Invariant"), (5, "Verification Surface")):
            if empty(c[i]):
                errs.append(f"设计矩阵 {sid} 的 {lab} 未完成")
        art = re.sub(r"\[[^\]\n]*\](?=\()", "", c[3])
        for raw in re.findall(r"[^\s;；|`<>]+?\.(?:md|html|css)\b", art, re.I):
            raw = raw.rsplit("](", 1)[-1].lstrip("(").removeprefix("./")
            if "://" in raw:
                continue
            rel = Path(raw.replace("\\", "/").removeprefix("output/"))
            if rel.parts and rel.parts[0] == "pages":
                continue
            if rel.is_absolute() or ".." in rel.parts or not (out / rel).is_file():
                errs.append(f"设计矩阵 {sid} 的 Artifact 不存在: {raw}")
    for sid in sorted(set(blocks) - traced):
        errs.append(f"设计矩阵缺少 active Source 行: {sid}")
    return errs


def page_identity(path: Path, page_id: str, name: str) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    if path.suffix.lower() == ".html":
        ids = set()
        for tag in re.findall(r"<meta\b[^>]*>", text, re.I):
            n = re.search(r'name=["\']([^"\']+)', tag, re.I)
            v = re.search(r'content=["\']([^"\']+)', tag, re.I)
            if n and v and n.group(1).strip().lower() == "page-id":
                ids.add(v.group(1).strip())
        if ids:
            return 100 if ids == {page_id} else 0
        t = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        if t and name and name in re.sub(r"<[^>]+>", "", t.group(1)):
            return 60
    else:
        ids = {v.strip().strip("`") for v in re.findall(r"^\|\s*页面\s*ID\s*\|\s*([^|]+)\|", text, re.M | re.I)}
        if ids:
            return 100 if ids == {page_id} else 0
        h = re.search(r"^#\s+.*$", text, re.M)
        if h and name and name in h.group(0):
            return 60
    if name and name in path.stem:
        return 40
    return 10 if name and name in text else 0


def pick_artifact(out: Path, suffix: str, page_id: str, name: str):
    cands = [p for p in (out / "pages").rglob(f"*{suffix}") if p.is_file()] if (out / "pages").is_dir() else []
    scored = [(page_identity(p, page_id, name), p) for p in cands]
    scored = [s for s in scored if s[0] > 0]
    if not scored:
        return None, f"{page_id} 找不到内容可确认的 {suffix} 产物"
    best = max(s for s, _ in scored)
    top = sorted(p for s, p in scored if s == best)
    if len(top) != 1:
        return None, f"{page_id} 的 {suffix} 内容匹配不唯一"
    return top[0], None


def fields(value: str) -> dict[str, str]:
    d = {}
    for part in re.split(r"[;；]", value.strip().strip("`")):
        k, sep, v = part.partition("=")
        if sep:
            d[k.strip()] = v.strip().strip("`")
    return d


def png_size(path: Path):
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 45 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR" \
            or not data.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82"):
        return None
    w, h = struct.unpack(">II", data[16:24])
    return (w, h) if w > 0 and h > 0 else None


def check_design_result(out: Path, tid: str, need_pair: bool, action: str, evidence: str) -> list[str]:
    errs = []
    targets = "actual|成品|截图" + ("|baseline|原型" if need_pair else "")
    if re.search(rf"(?:未|没有|尚未|并未|无法|不能)(?:实际)?(?:查看|看图)(?:\s*(?:{targets})|(?=[，；。]|$))", action, re.I) \
            or re.fullmatch(r"(?:只做代码审查|仅运行\s*UI\s*自动化)[。.]?", action.strip(" `"), re.I):
        errs.append(f"{tid} 的实际验证动作没有证明查看了截图")
    f = fields(evidence)
    keys = ("actual", "reviewer", "review", "blocking") + (("baseline",) if need_pair else ())
    missing = [k for k in keys if empty(f.get(k, ""))]
    if missing:
        return errs + [f"{tid} 缺少视觉证据字段: {', '.join(missing)}"]
    if f["reviewer"].lower() != "independent-visual":
        errs.append(f"{tid} reviewer 必须为 independent-visual")
    if f["review"].lower() != "pass":
        errs.append(f"{tid} 独立视觉复核未通过: {f['review']}")
    if f["blocking"] != "0":
        errs.append(f"{tid} 仍有阻塞视觉差异: {f['blocking']}")
    sizes = {}
    for k in ("actual", "baseline"):
        if k not in f:
            continue
        rel = Path(f[k].strip("`\"'").removeprefix("output/"))
        if rel.is_absolute() or ".." in rel.parts or len(rel.parts) < 3 or rel.parts[:2] != ("tests", "visual") \
                or rel.suffix.lower() != ".png":
            errs.append(f"{tid}: 视觉证据必须是 output/tests/visual/ 下的 PNG: {f[k]}")
            continue
        p = out / rel
        sz = png_size(p) if p.is_file() else None
        if sz is None:
            errs.append(f"{tid} 的 {k} 截图不存在或不是有效 PNG: {rel}")
            continue
        sizes[k] = (p, sz)
    if "actual" in sizes and "baseline" in sizes:
        if sizes["actual"][0] == sizes["baseline"][0]:
            errs.append(f"{tid} baseline 与 actual 不能是同一文件")
        if need_pair and sizes["actual"][1] != sizes["baseline"][1]:
            errs.append(f"{tid} 原型/成品截图尺寸不同")
    return errs


def check_exec_evidence(tid: str, action: str, evidence: str) -> list[str]:
    errs = []
    if re.search(r"^(?:只做代码审查|仅做代码审查)(?:[，,；;。]|$)", action.strip(" `")) or re.search(
            r"(?:^|[，,；;。])\s*(?:尚未|没有|未)(?:实际|真实)?执行(?:测试|验收|验证|命令|E2E)?\s*(?:[，,；;。]|$)", action) \
            or re.match(r"(?:应该通过|预计通过|功能已实现|代码已完成)(?:[，,；;。]|$)", evidence.strip(" `")):
        errs.append(f"{tid} 标为 pass，但动作或证据表示未执行或仅推测通过")
    text = evidence.strip()
    if text.startswith("`") and text.endswith("`"):
        text = text[1:-1]
    text = re.sub(r'''(?:^|(?<=[;；]))\s*command\s*=\s*(?:[^;；'"`\\]|\\.|'[^']*'|"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`)*(?=[;；]|$)''',
                  "", text, flags=re.I)
    codes = [int(v) for v in re.findall(r"(?:\bexit_code\b|\bexit\b|退出码)\s*(?:[=:：]\s*)?(-?\d+)\b", text, re.I)]
    failed = [int(v) for m in re.findall(r"\bfailed\s*[=:]\s*(\d+)\b|\b(\d+)\s+failed\b", text, re.I) for v in m if v]
    f = {k.lower(): v.upper() for k, v in fields(text).items()}
    expected_ok = False
    if "expected_exit_code" in f or "actual_exit_code" in f:
        e, a = f.get("expected_exit_code", ""), f.get("actual_exit_code", "")
        if not re.fullmatch(r"-?\d+", e) or not re.fullmatch(r"-?\d+", a):
            errs.append(f"{tid} expected_exit_code / actual_exit_code 必须成对填写整数")
        elif int(e) != int(a):
            errs.append(f"{tid} 实际退出码与预期不一致")
        else:
            expected_ok = all(c == int(a) for c in codes)
    red = tid.startswith("BUG-REPRO-") and f.get("expected") == "RED" and f.get("observed") == "RED"
    if ((any(c != 0 for c in codes) and not expected_ok) or any(n > 0 for n in failed)) and not red:
        errs.append(f"{tid} 标为 pass，但证据包含失败退出码或失败测试")
    return errs


def check_ledger(out: Path, ledger: Path, contract_path: Path, rows: list[list[str]]) -> list[str]:
    text = ledger.read_text(encoding="utf-8")
    errs: list[str] = []
    want = "sha256:" + hashlib.sha256(contract_path.read_bytes()).hexdigest()
    if meta(text, "contract_sha256") != want:
        errs.append("TDD验收结果 contract_sha256 与当前契约不一致")
    if empty(meta(text, "run_started_at") or ""):
        errs.append("TDD验收结果缺少有效 run_started_at")
    lrows = id_rows(text, TEST_ID_RE, 4, "验收结果", errs, strict=True)
    if not lrows:
        return errs + ["TDD验收结果没有合法结果行"]
    cids = [r[0] for r in rows]
    by_id = {r[0]: r for r in rows}
    lids = [r[0] for r in lrows]
    dup = sorted({i for i in lids if lids.count(i) > 1})
    if dup:
        errs.append("TDD验收结果 ID 重复: " + ", ".join(dup))
    if set(cids) - set(lids):
        errs.append("TDD验收结果漏项: " + ", ".join(sorted(set(cids) - set(lids))))
    if set(lids) - set(cids):
        errs.append("TDD验收结果包含契约外 ID: " + ", ".join(sorted(set(lids) - set(cids))))
    counts = {"pass": 0, "pending": 0, "fail": 0}
    for tid, st, action, evidence in lrows:
        s = st.strip().strip("`").lower()
        if s not in counts:
            errs.append(f"{tid} 状态非法: {st}")
            continue
        counts[s] += 1
        if s != "pass":
            errs.append(f"{tid} 尚未通过: {s}")
        if empty(action):
            errs.append(f"{tid} 缺少实际验证动作")
        if empty(evidence):
            errs.append(f"{tid} 缺少验证证据")
        if s == "pass" and not tid.startswith("DESIGN-"):
            errs.extend(check_exec_evidence(tid, action, evidence))
        if tid.startswith("DESIGN-") and tid in by_id:
            pair = any(m in cell for cell in by_id[tid][3:] for m in ("截图对", "严格对照"))
            errs.extend(check_design_result(out, tid, pair, action, evidence))
    print(f"   ledger: total={len(lrows)} pass={counts['pass']} pending={counts['pending']} fail={counts['fail']}")
    return errs


def main() -> int:
    args = sys.argv[1:]
    with_result = bool(args and args[0] == "--result")
    args = args[1:] if with_result else args
    if len(args) != 1:
        print("用法: python3 tools/check_contract.py [--result] <项目/output>")
        return 2
    out = Path(args[0])
    cpath = out / "tests" / "TDD验收契约.md"
    if not cpath.is_file():
        print(f"❌ 文件不存在: {cpath}")
        return 2
    contract = cpath.read_text(encoding="utf-8")
    errs: list[str] = []
    warns: list[str] = []
    for s in SECTIONS:
        if s not in contract:
            errs.append(f"契约缺少章节: {s}")
    sc, wt = meta(contract, "source_contract"), meta(contract, "work_type")
    if sc not in {"requirements.md", "bugfix.md"} or wt not in {"feature", "bugfix"} \
            or (sc == "requirements.md") != (wt == "feature"):
        errs.append("work_type / source_contract 非法或不一致")
    spath, tpath = out / (sc or "requirements.md"), out / "设计追溯矩阵.md"
    for p in (spath, tpath):
        if not p.is_file():
            errs.append(f"文件不存在: {p}")
    if errs:
        print(f"❌ 校验失败（{len(errs)}）")
        for e in errs:
            print("  -", e)
        return 2
    stext = spath.read_text(encoding="utf-8")
    try:
        blocks = source_blocks(stext)
    except ValueError as exc:
        print("❌", exc)
        return 2
    stages: set[str] = set()
    if wt == "feature":
        stages = parse_scope(meta(contract, "scope"), "TDD scope", errs)
        up = meta(metadata_section(stext), "scope")
        if stages != parse_scope("MVP" if up is None else up, "上游 scope", errs):
            errs.append("TDD scope 与上游 Metadata scope 不一致")
        for st in sorted(stages):
            if not scoped_reqs(blocks, {st}):
                errs.append(f"scope {st} 没有匹配的 active REQ")
        required = scoped_sources(blocks, stages, required_only=True)
    else:
        required = set(blocks)
    trace = tpath.read_text(encoding="utf-8")
    errs.extend(check_trace(stext, trace, contract, wt, stages, out))
    known = set(DESIGN_RE.findall(trace))
    rows = id_rows(contract, TEST_ID_RE, 6, "验收契约", errs, strict=True)
    if not rows:
        errs.append("契约没有合法验收行")

    all_pages: dict[str, tuple[set[str], str]] = {}
    scope_pages: set[str] = set()
    if wt == "feature":
        sel = scoped_sources(blocks, stages)
        referenced = {p for r in id_rows(trace, SRC_RE, 7, "", []) if r[0] in sel for p in PAGE_RE.findall(r[2])}
        referenced |= {p for r in rows for p in PAGE_RE.findall(r[2])}
        plist = out / "页面清单.md"
        if plist.is_file():
            for c in id_rows(plist.read_text(encoding="utf-8"), PAGE_RE, 6, "页面清单", errs):
                if c[0] in all_pages:
                    errs.append(f"页面清单重复定义 PAGE ID: {c[0]}")
                    continue
                pst = parse_scope(c[2].strip("`"), f"页面清单 {c[0]}", errs)
                all_pages[c[0]] = (pst, c[4])
                if pst & stages:
                    scope_pages.add(c[0])
            known |= set(all_pages)
            for p in sorted(referenced - set(all_pages)):
                errs.append(f"页面清单遗漏引用的页面: {p}")
        elif referenced:
            errs.append(f"文件不存在: {plist}")

    ids = [r[0] for r in rows]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        errs.append("验收 ID 重复: " + ", ".join(dup))
    covered, covered_pages, owners = set(), set(), {}
    for tid, scell, dcell, scen, expect, method in rows:
        rs = set(SRC_RE.findall(scell))
        covered |= rs
        if tid.startswith("DESIGN-"):
            pages = set(PAGE_RE.findall(dcell))
            covered_pages |= pages
            if len(pages) != 1:
                errs.append(f"{tid} 必须且只能对应一个 PAGE ID")
            af = fields(expect)
            miss = [a for a in ANCHORS if empty(af.get(a, ""))]
            if miss:
                errs.append(f"{tid} 缺少视觉锚点: {', '.join(miss)}")
            if "截图" not in method or "独立" not in method:
                errs.append(f"{tid} 验证方式必须包含真实成品截图和独立视觉复核")
            explicit = [Path(x.removeprefix("output/")) for x in PAGE_PATH_RE.findall(dcell)]
            for pid in pages:
                name = all_pages.get(pid, (set(), ""))[1]
                for suf in (".md", ".html"):
                    path, e = pick_artifact(out, suf, pid, name)
                    if e:
                        errs.append(f"{tid}: {e}")
                        continue
                    real = path.resolve()
                    if owners.get(real, pid) != pid:
                        errs.append(f"{pid} 与 {owners[real]} 共用页面产物 {path.name}")
                    owners[real] = pid
                    rel = path.relative_to(out)
                    if rel not in explicit:
                        warns.append(f"{tid} 未准确记录 {pid} 的实际路径，按内容匹配为 {rel}")
        for s in rs - set(blocks):
            errs.append(f"{tid} 引用未知 Source ID: {s}")
        for d in set(DESIGN_RE.findall(dcell)) - known:
            errs.append(f"{tid} 引用未出现在设计产物中的 Design ID: {d}")
        if not tid.startswith("SMOKE-") and not rs and "design-derived" not in scell:
            errs.append(f"{tid} 缺少 Source ID")
        for lab, v in (("场景与操作", scen), ("可观察通过标准", expect), ("验证方式", method)):
            if empty(v):
                errs.append(f"{tid} 的{lab}为空或占位")
        if empty(dcell, allow_dash=tid.startswith("SMOKE-")):
            errs.append(f"{tid} 的 Design IDs/产物为空或占位")
    if not any(i.startswith("SMOKE-") for i in ids):
        errs.append("缺少 SMOKE 冒烟门禁")
    if wt == "feature" and not any(i.startswith("FLOW-") for i in ids):
        errs.append("Feature 缺少 FLOW")
    for s in sorted(required - covered):
        errs.append(f"required Source 未被验收覆盖: {s}")
    for p in sorted(scope_pages - covered_pages):
        errs.append(f"当前 scope 页面未进入 DESIGN 验收: {p}")

    if with_result:
        ledger = out / "tests" / "TDD验收结果.md"
        if not ledger.is_file():
            errs.append(f"文件不存在: {ledger}")
        else:
            errs.extend(check_ledger(out, ledger, cpath, rows))

    for w in warns:
        print("⚠️", w)
    if errs:
        print(f"❌ 校验失败（{len(errs)}）")
        for e in errs:
            print("  -", e)
        return 2
    print(f"✅ 校验通过：{len(required)} required source / {len(scope_pages)} scope pages / {len(rows)} acceptance rows"
          + (" / execution ledger all pass" if with_result else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
