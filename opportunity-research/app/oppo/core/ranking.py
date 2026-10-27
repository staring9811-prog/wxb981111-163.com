"""Segment ranking and monthly snapshots (F09: REQ-F09-01, AC-F09-01/02; F10: AC-F10-01, DEC-006)."""

from __future__ import annotations

import hashlib
import math
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from oppo import clock
from oppo import db as D
from oppo.core import backtest as BT
from oppo.core import cards as CARD
from oppo.core import categories as CAT
from oppo.core import compute as CMP
from oppo.core import contract as CT
from oppo.core import judge as J
from oppo.core import packages as PK
from oppo.core import rules as RULES
from oppo.core import segments as SEG
from oppo.core import stats as ST

MIN_SAMPLE = BT.MIN_SAMPLE


def reference_text(cfg: dict[str, Any]) -> str:
    return f"起量新品（任一月父体月销 ≥ {cfg['rising_min_parent_units']:g} 件）"


def build_rows(conn: Connection, category_id: int, mode: str) -> dict[str, Any] | None:
    card = CARD.current_card(conn, category_id, mode)
    run_ = CMP.latest_run(conn, category_id, mode)
    if card is None or run_ is None:
        return None
    cfg = CAT.current_version(conn, category_id)["config"]
    T = run_["t_month"]
    spus = CMP.spus_frame(conn, run_["id"])
    sig = CMP.signals_frame(conn, run_["id"], T)
    look = {(row.segment_key, row.signal): (None if row.value != row.value else row.value)
            for row in sig.itertuples()}
    new = spus[(spus["is_new"] == 1) & (spus["rising"] == 1)]
    if mode == "history":
        dec = new[new["status"].isin([J.HIT, J.MISS])]
        sample = dec.groupby("segment_key").size().to_dict()
        hits = dec[dec["status"] == J.HIT].groupby("segment_key").size().to_dict()
    else:
        dec = new
        sample = dec.groupby("segment_key").size().to_dict()
        hits = dec[dec["status"] == J.X_HIT].groupby("segment_key").size().to_dict()
    universe = sorted(s for s, n in sample.items() if n >= 1)
    card_signals = D.loads(card["signals_json"], [])
    bt = BT.get(conn, card["backtest_id"]) if card["backtest_id"] else None
    probs = (bt["result"].get("probs") or {}) if bt and mode == "cross" else {}
    if mode == "history":
        scorer = BT.card_scorer(card_signals, {(T, s, k): v for (s, k), v in look.items()}, universe)
        score = {s: scorer(s, T) for s in universe}
    else:
        score = {s: probs.get(s) for s in universe}
    rules = [r for r in RULES.list_current(conn, category_id)
             if (mode == "cross") == bool(r["cross_tag"]) or r["origin"] == "人工"]
    sig_by_seg: dict[str, dict[str, float | None]] = {}
    for (s, k), v in look.items():
        sig_by_seg.setdefault(s, {})[k] = v
    for s, p in probs.items():
        sig_by_seg.setdefault(s, {})["xprob"] = p
    rows = []
    for s in universe:
        n = int(sample.get(s, 0))
        h = int(hits.get(s, 0))
        if mode == "history":
            point = h / n if n else None
            lo, hi = ST.wilson(h, n)
        else:
            point = probs.get(s)
            lo, hi = ST.wilson(int(round((point or 0) * n)), n) if n and point is not None else (None, None)
        tips = []
        for r in rules:
            if RULES.matches(r["conds"], s, sig_by_seg.get(s, {}), cfg):
                b = r["basis"] or {}
                tips.append({"rule": r["code"], "rule_id": r["rule_id"], "version": r["version_no"],
                             "action": r["action"], "status": r["status"], "cond": r["cond_text"],
                             "attr_note": r["attr_note"], "origin": r["origin"], "ci": b.get("ci"),
                             "n": b.get("n"), "batches": b.get("batches"), "backtest": b.get("backtest")})
        tips.sort(key=lambda t: (0 if t["origin"] == "回测" else 1, t["rule"]))
        rows.append({"segment_key": s, "segment": SEG.seg_name(s), "score": score.get(s), "sample": n, "hits": h,
                     "point": point, "ci": [lo, hi], "effective": n >= MIN_SAMPLE, "tips": tips,
                     "has_unknown": SEG.UNKNOWN in s.split("|")})

    def key(r: dict[str, Any]) -> tuple[Any, ...]:
        sc = r["score"] if r["score"] is not None else -math.inf
        return (-sc, -r["sample"], r["segment"])

    eff = sorted([r for r in rows if r["effective"]], key=key)
    short = sorted([r for r in rows if not r["effective"]], key=key)
    ordered = eff + short
    for i, r in enumerate(ordered, start=1):
        r["rank"] = i
    k = max(1, math.ceil(len(eff) * BT.TOP_SHARE)) if eff else 0
    top = eff[:k]
    th, tn = sum(r["hits"] for r in top), sum(r["sample"] for r in top)
    if mode == "history":
        top_ci = ST.wilson(th, tn)
        top_point = th / tn if tn else None
    else:
        pts = [r["point"] for r in top if r["point"] is not None]
        top_point = sum(pts) / len(pts) if pts else None
        top_ci = ST.wilson(int(round((top_point or 0) * tn)), tn) if tn and top_point is not None else (None, None)
    baseline = (bt["result"].get("baseline") if bt else None) or {}
    cv = CT.current_version(conn, category_id)
    cfg_ver = CAT.current_version(conn, category_id)
    pkg = PK.get(conn, run_["package_id"])
    return {
        "month": T, "mode": mode, "data_to": run_["latest_month"],
        "card": {"id": card["id"], "label": card["label"], "status": card["status"], "signals": card_signals,
                 "backtest": bt["code"] if bt else None, "reason": (D.loads(card["basis_json"], {}) or {})
                 .get("reason_text"), "reason_class": (D.loads(card["basis_json"], {}) or {}).get("reason_class")},
        "versions": {"package": pkg["label"] if pkg else None, "contract": f"v{cv['version_no']}" if cv else None,
                     "config": f"v{cfg_ver['version_no']}", "compute_run": run_["id"]},
        "rows": ordered, "effective": len(eff), "insufficient": len(short),
        "top20": {"segments": [r["segment_key"] for r in top], "hits": th, "n": tn, "point": top_point,
                  "ci": list(top_ci)},
        "average": {"rate": baseline.get("rate"), "hits": baseline.get("hits"), "n": baseline.get("n")},
        "reference": reference_text(cfg), "cross": mode == "cross",
    }


def generate(conn: Connection, category_id: int, mode: str, operator: str) -> int | None:
    content = build_rows(conn, category_id, mode)
    if content is None:
        return None
    blob = D.dumps(content)
    sha = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    T = content["month"]
    seq = (conn.execute(select(func.count()).select_from(D.snapshot).where(
        D.snapshot.c.category_id == category_id, D.snapshot.c.month == T, D.snapshot.c.mode == mode)).scalar() or 0) + 1
    sid = conn.execute(D.snapshot.insert().values(
        category_id=category_id, month=T, seq=seq, mode=mode, card_id=content["card"]["id"],
        card_label=content["card"]["label"], card_status=content["card"]["status"],
        backtest_id=(BT.latest(conn, category_id, mode) or {}).get("id"), compute_run_id=content["versions"]["compute_run"],
        content_json=blob, sha256=sha, created_by=operator, created_at=clock.now_iso())).inserted_primary_key[0]
    return int(sid)


def snapshot_rows(conn: Connection, category_id: int, mode: str | None = None) -> list[dict[str, Any]]:
    q = select(D.snapshot).where(D.snapshot.c.category_id == category_id)
    if mode:
        q = q.where(D.snapshot.c.mode == mode)
    rows = conn.execute(q.order_by(D.snapshot.c.month.desc(), D.snapshot.c.seq.desc())).mappings().all()
    out = []
    exports = {r[0]: r[1] for r in conn.execute(select(D.snapshot_export.c.snapshot_id,
                                                       func.max(D.snapshot_export.c.created_at))
                                                .group_by(D.snapshot_export.c.snapshot_id))}
    for r in rows:
        d = dict(r)
        d["content"] = D.loads(r["content_json"], {})
        d["exported_at"] = exports.get(r["id"])
        d["label"] = f"{r['month']} · 第 {r['seq']} 版"
        out.append(d)
    return out


def latest_snapshot(conn: Connection, category_id: int, mode: str) -> dict[str, Any] | None:
    rows = snapshot_rows(conn, category_id, mode)
    return rows[0] if rows else None


def get_snapshot(conn: Connection, sid: int) -> dict[str, Any] | None:
    r = conn.execute(select(D.snapshot).where(D.snapshot.c.id == sid)).mappings().first()
    if not r:
        return None
    d = dict(r)
    d["content"] = D.loads(r["content_json"], {})
    d["label"] = f"{r['month']} · 第 {r['seq']} 版"
    ex = conn.execute(select(func.max(D.snapshot_export.c.created_at)).where(
        D.snapshot_export.c.snapshot_id == sid)).scalar()
    d["exported_at"] = ex
    return d


def reconcile_version(conn: Connection, category_id: int, month: str, mode: str) -> dict[str, Any] | None:
    """DEC-006: the version last exported in that month, else the last one."""
    rows = [r for r in snapshot_rows(conn, category_id, mode) if r["month"] == month]
    if not rows:
        return None
    exported = [r for r in rows if r["exported_at"]]
    if exported:
        return max(exported, key=lambda r: (r["exported_at"], r["seq"]))
    return max(rows, key=lambda r: r["seq"])
