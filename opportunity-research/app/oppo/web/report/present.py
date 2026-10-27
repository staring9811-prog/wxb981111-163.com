"""Display models shared by the analysis pages (回测、判定卡、锦囊、排序) and the exported report, so the
page and the offline report show the same numbers in the same words (AC-F12-03)."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Connection

from oppo import db as D
from oppo import fmt
from oppo.core import backtest as BT
from oppo.core import cards as CARD
from oppo.core import categories as CAT
from oppo.core import compute as CMP
from oppo.core import contract as CT
from oppo.core import packages as PK
from oppo.core import ranking as RK
from oppo.core import rules as RULES
from oppo.core import signals as SIG

NO = fmt.NO_DATA


def pct1(v: Any) -> str:
    return fmt.pct(v, 1)


def frac(h: Any, n: Any) -> str:
    return f"{h} / {n}" if n else NO


def ci1(ci: Any) -> str:
    return fmt.ci_text(ci, 1)


def mult_ci(ci: Any) -> str:
    if not ci or ci[0] is None or ci[1] is None:
        return NO
    return f"{ci[0]:.2f}–{ci[1]:.2f}"


def span(batches: list[str] | None, sep: str = "–") -> str:
    if not batches:
        return NO
    return batches[0] if len(batches) == 1 else f"{batches[0]}{sep}{batches[-1]}"


def size_text(n: Any) -> str:
    if n is None:
        return NO
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    return f"{max(1, round(n / 1024))} KB"


def duration(a: str | None, b: str | None) -> str:
    if not a or not b:
        return NO
    s = int((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds())
    m, s = divmod(max(0, s), 60)
    return f"{m} 分 {s} 秒" if m else f"{s} 秒"


def signal_defs(cfg: dict[str, Any]) -> dict[str, str]:
    n = int(cfg["signal_windows"]["demand_months"])
    w = int(cfg["success"]["window_months"])
    look = int(cfg["signal_windows"]["entry_lookback_months"])
    return {
        "demand": f"映射到细分的关键词，T−{n} 至 T−1 月搜索量合计的同比变化",
        "entry": f"T−{w + look} 至 T−{w + 1} 月上架的新 SPU 中，命中数 ÷ 已判定数",
        "pain": "评论日期早于 T 月的评论中，被标为结构类痛点的评论占比",
        "hslr": "T−1 月销量前 25% 的子体中，平均星级低于 4.0 的子体销量 ÷ 细分总销量",
        "xprob": "截面模型：上架月龄、细分属性与 6 项干扰因素合成的上架 6 个月内命中概率",
    }


def threshold_text(sig: str, v: Any) -> str:
    return NO if v is None else f"≥ {RULES.fmt_value(sig, v)}"


def package_info(conn: Connection, package_id: int | None) -> dict[str, Any] | None:
    pkg = PK.get(conn, package_id) if package_id else None
    if not pkg:
        return None
    return {**pkg, "fp_short": (pkg.get("fingerprint") or "")[:8],
            "months": f"{pkg['months_from']}–{pkg['months_to']}" if pkg.get("months_from") else NO}


def version_no(conn: Connection, table: Any, vid: int | None) -> int | None:
    if not vid:
        return None
    return conn.execute(select(table.c.version_no).where(table.c.id == vid)).scalar()


# ---- backtest ---------------------------------------------------------------------------------


def _hbars(entries: list[dict[str, Any]], avg: float | None) -> dict[str, Any]:
    rates = [e["rate"] for e in entries if e["rate"] is not None] + ([2 * avg] if avg else [])
    top = max(rates) if rates else 0.5
    scale = max(0.5, math.ceil(top * 1.1 * 10) / 10)

    def w(v: float | None) -> float:
        return 0.0 if v is None else round(min(1.0, v / scale) * 100, 1)

    return {"scale": scale, "scale_text": f"0–{scale * 100:.0f}%", "rows": [dict(e, width=w(e["rate"])) for e in entries],
            "avg": avg, "avg_left": w(avg) if avg else None, "two_left": w(2 * avg) if avg else None}


def _eval_row(label: str, e: dict[str, Any] | None, kind: str, key: str | None = None) -> dict[str, Any]:
    e = e or {}
    ok = bool(e.get("computable")) and e.get("rate") is not None
    return {"label": label, "kind": kind, "key": key, "ok": ok, "rate": e.get("rate"), "hits": e.get("top_hits"),
            "n": e.get("top_n"), "ci": e.get("ci"), "multiple": e.get("multiple"), "mult_ci": e.get("mult_ci"),
            "reason": e.get("reason") or (None if ok else "数据包缺少所需数据")}


def conditions(res: dict[str, Any], cross: bool = False) -> list[dict[str, Any]]:
    card = res.get("card") or {}
    cond = res.get("conditions") or {}
    rate, avg = card.get("rate"), card.get("avg")
    cur = res.get("current") or {}
    comp = [k for k, v in cur.items() if v.get("computable") and v.get("top_n")]
    nodata = [k for k in cur if k not in comp]
    out = []
    if rate is not None and avg is not None:
        ok1 = bool(cond.get("cond1"))
        txt = f"{pct1(rate)} {'≥' if ok1 else '<'} 2 × {pct1(avg)} = {pct1(2 * avg)}"
        if not ok1:
            txt += f"，差 {(2 * avg - rate) * 100:.1f} 个百分点"
        out.append({"ok": ok1, "title": f"前 20% 细分{'截面' if cross else ''}命中率 ≥ 全类目平均的 2 倍", "text": txt,
                    "short": txt})
    best = cond.get("best_current")
    if comp:
        beats = cond.get("beats") or {}
        losers = [k for k in comp if not beats.get(k)]
        ok2 = bool(cond.get("cond2"))
        tail = f"（另 {len(nodata)} 个无数据，未参与比较）" if nodata else ""
        if ok2:
            txt = (f"高于{'全部' if not nodata else ''} {len(comp)} 个可计算的现用指标"
                   f"（最高 {SIG.LABELS[best[0]]} {pct1(best[1])}）" if best else "")
            desc = f"最高的现用指标为{SIG.LABELS[best[0]]} {pct1(best[1])}" if best else ""
        else:
            txt = "不高于" + "、".join(f"{SIG.LABELS[k]} {pct1(cur[k]['rate'])}" for k in losers)
            desc = txt
        title = (f"高于每个可计算的现用指标各自排序的前 20% 命中率（本次 {len(comp)} 个可计算"
                 f"{'' if not nodata else f'，{len(nodata)} 个无数据'}）")
        out.append({"ok": ok2, "title": title, "text": desc + tail, "short": txt + tail, "nodata": nodata})
    else:
        out.append({"ok": False, "title": "高于每个可计算的现用指标各自排序的前 20% 命中率",
                    "text": "现用指标都无法计算：" + "；".join(f"{SIG.LABELS[k]}：{cur[k].get('reason') or NO}"
                                                     for k in cur), "short": "现用指标都无法计算", "nodata": list(cur)})
    return out


def backtest_view(conn: Connection, bt: dict[str, Any] | None) -> dict[str, Any] | None:
    """Everything the 回测 page, the 判定卡 page and the report show about one backtest run."""
    if not bt:
        return None
    res = bt["result"] or {}
    cross = bt["mode"] == "cross"
    card = res.get("card") or {}
    split = res.get("split") or {}
    base = res.get("baseline") or {}
    avg = base.get("rate") if base else card.get("avg")
    pkg = package_info(conn, bt["package_id"])
    card_row = CARD.get(conn, bt["card_id"]) if bt.get("card_id") else None
    rules = []
    if card_row:
        for r in RULES.list_current(conn, bt["category_id"]):
            b = r.get("basis") or {}
            if r["origin"] == "回测" and b.get("backtest") == bt["code"]:
                rules.append(r["code"])
    rows: list[dict[str, Any]] = []
    weights = " · ".join(f"{s['label']} {s['weight']:.2f}" for s in res.get("card_signals") or [] if s.get("weight"))
    if cross:
        rows.append({"group": "截面模型（按上架 6 个月内命中概率排序）"})
        rows.append(dict(_eval_row("截面模型", card, "card"), sub=None))
        rows.append({"group": "现用指标（只用老品计算）"})
    else:
        rows.append({"group": "判定卡（组合规则）"})
        rows.append(dict(_eval_row(f"判定卡 {card_row['label']}" if card_row else "判定卡", card, "card"), sub=weights))
        rows.append({"group": "单个信号"})
        for s in SIG.SIGNALS:
            rows.append(_eval_row(SIG.LABELS[s], (res.get("signals") or {}).get(s), "signal", s))
        rows.append({"group": "现用指标（对照）"})
    old_n = _old_count(conn, bt) if cross else None
    for s in SIG.CURRENT:
        r = _eval_row(SIG.LABELS[s], (res.get("current") or {}).get(s), "current", s)
        r["cand"] = True
        if cross and old_n is not None and r["ok"]:
            r["sub"] = f"老品 n={old_n:,}"
        rows.append(r)
    rows.append({"group": "基准"})
    rows.append({"label": "全类目平均", "kind": "base", "ok": avg is not None, "rate": avg, "hits": base.get("hits"),
                 "n": base.get("n"), "ci": base.get("ci"), "sub": f"检验组 {base.get('n', 0)} 个起量新 SPU"
                 if cross else "检验组全部起量新 SPU"})
    computable = [r for r in rows if r.get("kind") == "current" and r["ok"]]
    bar_entries = []
    if card.get("rate") is not None:
        bar_entries.append({"label": f"判定卡 {card_row['label']}" if card_row and not cross else
                            ("截面模型" if cross else "判定卡"), "rate": card.get("rate"), "hits": card.get("top_hits"),
                            "n": card.get("top_n"), "ci": card.get("ci"), "focus": True})
    for r in sorted(computable, key=lambda r: -(r["rate"] or 0)):
        bar_entries.append({"label": r["label"], "rate": r["rate"], "hits": r["hits"], "n": r["n"], "ci": r["ci"],
                            "focus": False, "cand": True})
    nodata_current = [r for r in rows if r.get("kind") == "current" and not r["ok"]]
    decided = res.get("decided_batches") or []
    excluded = res.get("excluded_batches") or []
    started = bt.get("started_at")
    view = {
        "bt": bt, "code": bt["code"], "mode": bt["mode"], "cross": cross, "res": res,
        "conclusion": res.get("conclusion") or bt.get("conclusion"), "reason_class": res.get("reason_class"),
        "reason_text": res.get("reason_text"), "achieved": (res.get("conclusion") or "").startswith("达标"),
        "card": card, "card_row": card_row, "card_label": card_row["label"] if card_row else None,
        "multiple": card.get("multiple"), "mult_ci": card.get("mult_ci"), "rate": card.get("rate"),
        "top_hits": card.get("top_hits"), "top_n": card.get("top_n"), "top_ci": card.get("ci"),
        "avg": avg, "all_hits": base.get("hits", card.get("all_hits")), "all_n": base.get("n", card.get("all_n")),
        "base_ci": base.get("ci"), "conditions": conditions(res, cross) if card else [],
        "decided": decided, "excluded": excluded, "rule_batches": split.get("rule") or [],
        "test_batches": split.get("test") or [], "rule_counts": res.get("rule_counts") or {},
        "test_counts": res.get("test_counts") or {}, "effective": res.get("effective") or [], "k": res.get("k"),
        "insufficient": [dict(h, name=fmt.segname(h["segment"].replace("|", " · ")),
                              merge_name=h["merge_with"].replace("|", " · ") if h.get("merge_with") else None)
                         for h in res.get("insufficient") or []],
        "confounders": res.get("confounders") or [], "confounder_n": res.get("confounder_n"),
        "rejected": res.get("rejected_fields") or [], "limitation": res.get("limitation") or BT.LIMITATION,
        "seed": bt.get("seed"), "started": (started or "")[:16], "duration": duration(started, bt.get("ended_at")),
        "package": pkg, "contract_no": version_no(conn, D.contract_version, bt.get("contract_version_id")),
        "config_no": version_no(conn, D.category_version, bt.get("config_version_id")),
        "rows": rows, "bars": _hbars(bar_entries, avg), "nodata_current": nodata_current,
        "computable_current": len(computable), "rules": rules, "card_signals": res.get("card_signals") or [],
        "model_rows": (res.get("rows") or {}) if cross else {}, "operator": bt.get("created_by"),
    }
    if cross:
        view["heat"] = heat_table(res)
    return view


def _old_count(conn: Connection, bt: dict[str, Any]) -> int | None:
    run_ = conn.execute(select(D.compute_run).where(D.compute_run.c.id == bt["compute_run_id"])).mappings().first()
    if not run_:
        return None
    sig = CMP.signals_frame(conn, run_["id"], run_["t_month"])
    sig = sig[sig["signal"] == "unit_asin"]
    total = 0
    for extra in sig["extra_json"]:
        total += int((D.loads(extra, {}) or {}).get("old") or 0)
    return total or None


def heat_class(h: int, n: int) -> str:
    if n < 5:
        return "hx"
    if h == 0:
        return "h0"
    return f"h{min(6, int((h / n) * 10) + 1)}"


def heat_table(res: dict[str, Any]) -> dict[str, Any]:
    table = res.get("age_table") or {}
    probs = res.get("probs") or {}
    eff = res.get("effective") or []
    k = res.get("k") or 0
    top = set(sorted([s for s in eff if probs.get(s) is not None], key=lambda s: (-probs[s], s))[:k])
    rows = []
    for seg, ages in table.items():
        cells = []
        for a in range(1, 7):
            c = ages.get(a) or ages.get(str(a))
            if not c:
                cells.append({"cls": "hx", "text": NO, "sub": "",
                              "tip": f"{NO}|{seg.replace('|', ' · ')} · 第 {a} 个月|没有被观察到的新 SPU"})
                continue
            h, n = int(c["hits"]), int(c["n"])
            cls = heat_class(h, n)
            rate = h / n if n else 0.0
            if cls == "hx":
                cells.append({"cls": cls, "text": f"{h}/{n}", "sub": "样本过少",
                              "tip": f"样本过少|第 {a} 个月：达标 {h} / 观察 {n}|观察少于 5 个，不着色"})
            else:
                cells.append({"cls": cls, "text": f"{h}/{n}", "sub": pct1(rate),
                              "tip": f"{pct1(rate)}|第 {a} 个月：达标 {h} / 观察 {n}"})
        all_few = all(c["cls"] == "hx" for c in cells)
        maxn = max((int((ages.get(a) or ages.get(str(a)) or {}).get("n", 0)) for a in range(1, 7)), default=0)
        rows.append({"segment": seg.replace("|", " · "), "key": seg, "cells": cells, "top": seg in top,
                     "prob": None if all_few else probs.get(seg), "all_few": all_few, "maxn": maxn})
    rows.sort(key=lambda r: (0 if r["top"] else 1, r["all_few"], -(r["prob"] or 0), -r["maxn"], r["segment"]))
    return {"rows": rows, "batches": res.get("decided_batches") or []}


# ---- decision card --------------------------------------------------------------------------------


def card_diff(card: dict[str, Any], prev: dict[str, Any] | None) -> str:
    if prev is None:
        return "首次生成" if card["mode"] == "history" else "截面回测首次生成"
    a = {s["signal"]: s for s in prev.get("signals") or []}
    b = {s["signal"]: s for s in card.get("signals") or []}
    parts = []
    added = [s for s in b if s not in a]
    removed = [s for s in a if s not in b]
    if added:
        parts.append("新增入选信号：" + "、".join(b[s]["label"] for s in added))
    if removed:
        parts.append("移出：" + "、".join(a[s]["label"] for s in removed))
    for s in b:
        if s in a:
            if a[s].get("threshold") != b[s].get("threshold"):
                parts.append(f"{b[s]['label']}阈值 {threshold_text(s, a[s].get('threshold'))} → "
                             f"{threshold_text(s, b[s].get('threshold'))}")
            if a[s].get("weight") != b[s].get("weight"):
                parts.append(f"{b[s]['label']}权重 {a[s].get('weight', 0):.2f} → {b[s].get('weight', 0):.2f}")
    if prev.get("status") != card.get("status"):
        parts.append(f"状态 {prev.get('status')} → {card.get('status')}")
    return "；".join(parts) or "入选信号、阈值与权重不变"


def card_versions(conn: Connection, cid: int) -> list[dict[str, Any]]:
    cards = list(reversed(CARD.all_cards(conn, cid)))  # oldest first
    eff = CARD.effective(conn, cid)
    cur_ids = {c["id"] for c in (CARD.current_card(conn, cid, "history"), CARD.current_card(conn, cid, "cross")) if c}
    prev_by_mode: dict[str, dict[str, Any]] = {}
    out = []
    for c in cards:
        bt = BT.get(conn, c["backtest_id"]) if c.get("backtest_id") else None
        res = (bt or {}).get("result") or {}
        b = c.get("basis") or {}
        test = b.get("test_batches") or []
        out.append({
            "card": c, "label": c["label"], "date": (c["created_at"] or "")[:10], "mode": c["mode"],
            "status": c["status"], "bt": bt["code"] if bt else NO, "test": span(test),
            "test_n": b.get("test_spus"), "model_rows": (res.get("rows") or {}).get("test"),
            "multiple": b.get("multiple"), "mult_ci": b.get("mult_ci"),
            "diff": card_diff(c, prev_by_mode.get(c["mode"])), "current": c["id"] in cur_ids,
            "superseded": c["mode"] == "cross" and eff.get("mode") == "history",
            "reason_text": b.get("reason_text"), "reason_class": b.get("reason_class"),
        })
        prev_by_mode[c["mode"]] = c
    return list(reversed(out))


# ---- kits (锦囊) -----------------------------------------------------------------------------------


def kits(conn: Connection, cid: int, mode: str, snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Rules that apply under the current card of `mode`, with the segments they apply to in the snapshot."""
    cfg = CAT.current_version(conn, cid)["config"]
    applies: dict[str, list[str]] = {}
    if snapshot:
        for r in snapshot["content"].get("rows") or []:
            for t in r.get("tips") or []:
                applies.setdefault(t["rule"], []).append({"key": r["segment_key"], "name": r["segment"]})
    order = {a: i for i, a in enumerate(RULES.ACTIONS)}
    out = []
    for r in RULES.list_current(conn, cid):
        if not ((mode == "cross") == bool(r["cross_tag"]) or r["origin"] == "人工"):
            continue
        b = r.get("basis") or {}
        ci = b.get("ci")
        n, h = b.get("n"), b.get("hits")
        point = (h / n) if n and h is not None else None
        manual = r["origin"] == "人工" and not b
        if r["status"] == "已验证":
            note = (f"{b.get('recon_month', '')} 对账 {b.get('recon_snapshot', '')}："
                    f"规则倍数 {fmt.mult(b.get('rule_multiple'))}"
                    f"（{'立项候选 ≥ 2' if r['action'] == '立项候选' else '放弃 ≤ 0.5'}）")
        elif r["status"] == "历史观察":
            note = "由达标回测生成，尚未经到期对账检验"
        else:
            note = "人工新增，未经回测检验。理由：" + (r.get("reason") or "") if r["origin"] == "人工" else \
                "条件或动作已修改，未经回测检验。理由：" + (r.get("reason") or "")
        segs = applies.get(r["code"], [])
        out.append({
            "rule": r, "code": r["code"], "version": r["version_no"], "origin": r["origin"],
            "origin_text": "回测" if r["origin"] == "回测" else f"人工 · {r.get('created_by') or ''} · "
                           f"{(r.get('created_at') or '')[:10]}",
            "action": r["action"], "status": r["status"], "cond": r["cond_text"], "attr_note": r.get("attr_note"),
            "advice": r.get("reason") if r["origin"] == "人工" else None, "ci": ci if ci and ci[0] is not None else None,
            "point": point, "n": n, "hits": h, "batches": b.get("batches"), "backtest": b.get("backtest"),
            "note": note, "segments": segs, "manual": manual, "cross": bool(r["cross_tag"]),
            "updated_by": r.get("updated_by"), "updated_at": r.get("updated_at"),
            "_order": (order.get(r["action"], 9), 0 if r["origin"] == "回测" else 1, r["code"]),
        })
    out.sort(key=lambda k: k["_order"])
    _ = cfg
    return out


def kit_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    c = {a: 0 for a in RULES.ACTIONS}
    for k in items:
        c[k["action"]] = c.get(k["action"], 0) + 1
    return c


# ---- versions footer --------------------------------------------------------------------------------


def versions(conn: Connection, cid: int, mode: str) -> dict[str, Any]:
    pkg = PK.current_package(conn, cid, mode)
    cv = CT.current_version(conn, cid)
    cfg = CAT.current_version(conn, cid)
    card = CARD.current_card(conn, cid, mode)
    bt = BT.latest(conn, cid, mode)
    snap = RK.latest_snapshot(conn, cid, mode)
    return {"package": pkg, "contract": cv, "config": cfg, "card": card, "bt": bt, "snapshot": snap}


def footer(v: dict[str, Any], with_snapshot: bool = True) -> str:
    parts = [f"数据包 {v['package']['label']}" if v["package"] else "数据包 —",
             f"字段约定 v{v['contract']['version_no']}" if v["contract"] else "字段约定 —",
             f"品类配置 v{v['config']['version_no']}"]
    if v["card"]:
        parts.append(f"判定卡 {v['card']['label']}")
    if v["bt"]:
        parts.append(f"回测 {v['bt']['code']}")
    if with_snapshot and v["snapshot"]:
        parts.append(f"快照 {v['snapshot']['month']} 第 {v['snapshot']['seq']} 版")
    return " · ".join(parts)
