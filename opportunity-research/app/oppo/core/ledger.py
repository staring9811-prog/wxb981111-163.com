"""Ledger: decisions, own launch data and due reconciliation (F10: REQ-F10-02/03, AC-F10-02..05;
F11: AC-F11-03/06, D-27, DEC-006/007/012/027/029)."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from oppo import clock
from oppo import db as D
from oppo.core import categories as CAT
from oppo.core import compute as CMP
from oppo.core import judge as J
from oppo.core import packages as PK
from oppo.core import ranking as RK
from oppo.core import rules as RULES
from oppo.core.packages import add_months, month_range


class LedgerError(Exception):
    pass


def _next_code(conn: Connection) -> str:
    n = conn.execute(select(func.count()).select_from(D.decision_record)).scalar() or 0
    return f"D-{n + 1:04d}"


def _date_ok(s: str | None) -> bool:
    return bool(s and re.match(r"^\d{4}-\d{2}-\d{2}$", s))


def record_decision(conn: Connection, category_id: int, operator: str, decision: str, segment_key: str,
                    segment_name: str, reason: str, snapshot_id: int | None, project_date: str | None = None,
                    project_name: str | None = None) -> str:
    errors = []
    if decision not in ("立项", "不立项"):
        errors.append("请选择决定")
    if not (segment_key or "").strip():
        errors.append("请选择关联细分")
    if not (reason or "").strip():
        errors.append("请填写理由")
    if decision == "立项" and project_date and not _date_ok(project_date):
        errors.append("立项日期格式应为 YYYY-MM-DD")
    if errors:
        raise LedgerError("；".join(errors))
    code = _next_code(conn)
    conn.execute(D.decision_record.insert().values(
        category_id=category_id, code=code, kind="记录", decision=decision, segment_key=segment_key,
        segment_name=segment_name, reason=reason.strip(), snapshot_id=snapshot_id, project_name=project_name or None,
        project_date=project_date or None, source="手工", created_by=operator, created_at=clock.now_iso()))
    return code


def record_backfill(conn: Connection, category_id: int, operator: str, project_name: str, project_date: str,
                    segment_key: str, segment_name: str, basis_note: str = "") -> str:
    errors = []
    if not (project_name or "").strip():
        errors.append("请填写立项名称")
    if not _date_ok(project_date):
        errors.append("请填写立项日期（YYYY-MM-DD）")
    if not (segment_key or "").strip():
        errors.append("请选择关联细分")
    if errors:
        raise LedgerError("；".join(errors))
    code = _next_code(conn)
    conn.execute(D.decision_record.insert().values(
        category_id=category_id, code=code, kind="补录", decision="立项", segment_key=segment_key,
        segment_name=segment_name, reason=None, snapshot_id=None, project_name=project_name.strip(),
        project_date=project_date, basis_note=basis_note or None, source="手工", created_by=operator,
        created_at=clock.now_iso()))
    return code


def correct(conn: Connection, category_id: int, operator: str, original_code: str, **fields: Any) -> str:
    """Append a correction; the original is shown as 已更正 (DEC-007)."""
    orig = conn.execute(select(D.decision_record).where(D.decision_record.c.code == original_code)).mappings().first()
    if orig is None:
        raise LedgerError("原记录不存在")
    if conn.execute(select(D.decision_record.c.id).where(D.decision_record.c.corrects_id == orig["id"])).first():
        raise LedgerError("该记录已有更正，请对更正记录再追加更正")
    reason = (fields.get("reason") or "").strip()
    if not reason:
        raise LedgerError("请填写更正理由")
    vals = {k: fields.get(k, orig[k]) for k in ("decision", "segment_key", "segment_name", "project_name",
                                                "project_date", "basis_note")}
    code = _next_code(conn)
    conn.execute(D.decision_record.insert().values(
        category_id=category_id, code=code, kind="更正", reason=reason, snapshot_id=orig["snapshot_id"],
        corrects_id=orig["id"], source="手工", created_by=operator, created_at=clock.now_iso(), **vals))
    return code


def import_c7(conn: Connection, category_id: int, operator: str) -> int:
    pkg = PK.current_package(conn, category_id, "history")
    if not pkg:
        raise LedgerError("当前没有历史数据包")
    rows = conn.execute(select(D.raw_c7).where(D.raw_c7.c.package_id == pkg["id"])).mappings().all()
    if not rows:
        raise LedgerError("当前数据包不含 C7 自家立项")
    n = 0
    existing = {(r["project_name"], r["project_date"]) for r in records(conn, category_id)}
    for r in rows:
        if (r["name"], r["project_date"]) in existing:
            continue
        code = _next_code(conn)
        conn.execute(D.decision_record.insert().values(
            category_id=category_id, code=code, kind="补录", decision="立项", segment_key=r["segment_or_attr"],
            segment_name=r["segment_or_attr"], project_name=r["name"], project_date=r["project_date"],
            basis_note=f"从数据包 {pkg['label']} 的 C7 导入", source="数据包", created_by=operator,
            created_at=clock.now_iso()))
        n += 1
    return n


def records(conn: Connection, category_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(select(D.decision_record).where(D.decision_record.c.category_id == category_id)
                        .order_by(D.decision_record.c.id.desc())).mappings().all()
    out = [dict(r) for r in rows]
    by_id = {r["id"]: r for r in out}
    corrected_by = {r["corrects_id"]: r for r in out if r["corrects_id"]}
    for r in out:
        r["corrected_by"] = corrected_by.get(r["id"])
        r["corrects"] = by_id.get(r["corrects_id"]) if r["corrects_id"] else None
        r["launch"] = launch_status(conn, category_id, r["id"])
        r["snapshot"] = RK.get_snapshot(conn, r["snapshot_id"]) if r["snapshot_id"] else None
    return out


# ---- own launch data (AC-F10-05, DEC-012) ----------------------------------------------------


def _parse_cell(v: Any) -> tuple[float | None, bool]:
    s = "" if v is None else str(v).strip().replace(",", "").replace("$", "")
    if s == "":
        return None, True
    try:
        return float(s), True
    except ValueError:
        return None, False


def save_launch_data(conn: Connection, category_id: int, operator: str, decision_code: str, launch_month: str,
                     months: list[dict[str, Any]], asin: str = "") -> dict[str, Any]:
    rec = conn.execute(select(D.decision_record).where(D.decision_record.c.code == decision_code)).mappings().first()
    if rec is None:
        raise LedgerError("立项记录不存在")
    if not re.match(r"^\d{4}-\d{2}$", launch_month or ""):
        raise LedgerError("请填写上架月（YYYY-MM）")
    errors: dict[str, str] = {}
    clean = []
    for i, m in enumerate(months[:6], start=1):
        row = {}
        for key in ("units", "sales", "bsr"):
            v, ok = _parse_cell(m.get(key))
            if not ok:
                errors[f"{i}:{key}"] = "请填数字"
            row[key] = v
        clean.append(row)
    while len(clean) < 6:
        clean.append({"units": None, "sales": None, "bsr": None})
    if errors:
        e = LedgerError("有非数字的值")
        e.fields = errors  # type: ignore[attr-defined]
        raise e
    cfg_ver = CAT.current_version(conn, category_id)
    conn.execute(D.launch_data.insert().values(
        decision_id=rec["id"], launch_month=launch_month, asin=asin or None, months_json=D.dumps(clean),
        config_version_id=cfg_ver["id"], created_by=operator, created_at=clock.now_iso()))
    return launch_status(conn, category_id, rec["id"]) or {}


def current_month(conn: Connection, category_id: int) -> str:
    pkg = PK.current_package(conn, category_id, "history")
    if pkg and pkg["months_to"]:
        return pkg["months_to"]
    return clock.now().strftime("%Y-%m")


def judge_own(launch_month: str, months: list[dict[str, Any]], current: str, cfg: dict[str, Any]) -> dict[str, Any]:
    succ = cfg["success"]
    window = int(succ["window_months"])
    bsr_max, gmv_min = float(succ["bsr_max"]), float(succ["gmv_min"])
    elapsed = len(month_range(launch_month, current)) if current >= launch_month else 0
    elapsed = min(elapsed, window)
    best_bsr = max_sales = None
    missing = []
    for age, m in enumerate(months[:window], start=1):
        if age > elapsed:
            break
        bsr, sales = m.get("bsr"), m.get("sales")
        if bsr is not None and (best_bsr is None or bsr < best_bsr):
            best_bsr = bsr
        if sales is not None and (max_sales is None or sales > max_sales):
            max_sales = sales
        if (bsr is not None and bsr <= bsr_max) or (sales is not None and sales >= gmv_min):
            return {"status": J.HIT, "hit_age": age, "hit_month": add_months(launch_month, age - 1),
                    "best_bsr": best_bsr, "max_sales": max_sales,
                    "basis": "BSR" if bsr is not None and bsr <= bsr_max else "GMV"}
        if bsr is None or sales is None:
            missing.append(add_months(launch_month, age - 1))
    if elapsed < window:
        return {"status": J.WATCH, "remaining": window - elapsed, "best_bsr": best_bsr, "max_sales": max_sales}
    if missing:
        return {"status": J.INCOMPLETE, "missing": missing, "best_bsr": best_bsr, "max_sales": max_sales}
    return {"status": J.MISS, "best_bsr": best_bsr, "max_sales": max_sales}


def launch_status(conn: Connection, category_id: int, decision_id: int) -> dict[str, Any] | None:
    row = conn.execute(select(D.launch_data).where(D.launch_data.c.decision_id == decision_id)
                       .order_by(D.launch_data.c.id.desc()).limit(1)).mappings().first()
    if not row:
        return None
    cfg = CAT.current_version(conn, category_id)
    months = D.loads(row["months_json"], [])
    res = judge_own(row["launch_month"], months, current_month(conn, category_id), cfg["config"])
    return {**dict(row), "months": months, **res, "config_version_no": cfg["version_no"]}


# ---- reconciliation (AC-F10-04, AC-F11-03, AC-F11-06, SEQ-F10-01) ---------------------------------


def reconcile_all(conn: Connection, category_id: int, operator: str) -> list[int]:
    out = []
    cfg = CAT.current_version(conn, category_id)["config"]
    window = int(cfg["success"]["window_months"])
    for mode in ("history", "cross"):
        run_ = CMP.latest_run(conn, category_id, mode)
        if run_ is None:
            continue
        latest = run_["latest_month"]
        done_months = {r[0] for r in conn.execute(select(D.reconciliation.c.batch).where(
            D.reconciliation.c.category_id == category_id, D.reconciliation.c.mode == mode))}
        months = sorted({s["month"] for s in RK.snapshot_rows(conn, category_id, mode)})
        spus = None
        for M in months:
            if M in done_months or add_months(M, window - 1) > latest:
                continue
            snap = RK.reconcile_version(conn, category_id, M, mode)
            if snap is None:
                continue
            if spus is None:
                spus = CMP.spus_frame(conn, run_["id"])
            out.append(_reconcile(conn, category_id, snap, spus, run_, mode, operator))
    return out


def _reconcile(conn: Connection, category_id: int, snap: dict[str, Any], spus: Any, run_: dict[str, Any],
               mode: str, operator: str) -> int:
    M = snap["month"]
    content = snap["content"]
    hit_status = J.HIT if mode == "history" else J.X_HIT
    decided_status = [J.HIT, J.MISS] if mode == "history" else [J.X_HIT, J.X_MISS]
    batch = spus[(spus["is_new"] == 1) & (spus["rising"] == 1) & (spus["batch"] == M)]
    dec = batch[batch["status"].isin(decided_status)]
    incomplete = int(len(batch) - len(dec))
    ah, an = int((dec["status"] == hit_status).sum()), int(len(dec))
    top_segs = content["top20"]["segments"]
    top = dec[dec["segment_key"].isin(top_segs)]
    th, tn = int((top["status"] == hit_status).sum()), int(len(top))
    rate = th / tn if tn else None
    avg = ah / an if an else None
    mult = (rate / avg) if rate is not None and avg else None
    lo, hi = content["top20"]["ci"]
    within = None
    if rate is not None and lo is not None:
        within = "落在区间内" if lo - 1e-12 <= rate <= hi + 1e-12 else ("高于区间" if rate > hi else "低于区间")
    recon_month = run_["t_month"]
    per_seg = []
    for r in content["rows"]:
        g = dec[dec["segment_key"] == r["segment_key"]]
        per_seg.append({"segment_key": r["segment_key"], "segment": r["segment"], "rank": r["rank"],
                        "tips": [t["action"] + " " + t["rule"] for t in r["tips"]], "n": int(len(g)),
                        "hits": int((g["status"] == hit_status).sum()), "top": r["segment_key"] in top_segs})
    rid = conn.execute(D.reconciliation.insert().values(
        category_id=category_id, snapshot_id=snap["id"], recon_month=recon_month, batch=M, mode=mode,
        detail_json=D.dumps({"segments": per_seg, "snapshot_label": snap["label"]}), top_hits=th, top_n=tn,
        all_hits=ah, all_n=an, incomplete=incomplete, multiple=mult, exp_lo=lo, exp_hi=hi, within=within,
        created_by=operator, created_at=clock.now_iso())).inserted_primary_key[0]
    # rule reconciliation: each 历史观察 rule referenced by the snapshot's tips
    referenced: dict[int, dict[str, Any]] = {}
    for r in content["rows"]:
        for t in r["tips"]:
            if t["status"] != "历史观察":
                continue
            ent = referenced.setdefault(t["rule_id"], {"tip": t, "segments": []})
            ent["segments"].append(r["segment_key"])
    for rule_id, ent in sorted(referenced.items()):
        segs = ent["segments"]
        g = dec[dec["segment_key"].isin(segs)]
        h, n = int((g["status"] == hit_status).sum()), int(len(g))
        with_batch = sorted({s for s in g["segment_key"]})
        multiple = (h / n) / avg if n and avg else None
        action = ent["tip"]["action"]
        cur = RULES.current(conn, rule_id)
        result, new_no = "未达条件，状态不变", None
        if n == 0 or not an:
            result = "无对应批次新 SPU，状态不变"
        elif mode == "cross":
            result = "截面对账仅作参考，不改变规则状态"
        elif action == "观察":
            result = "已记录，状态不变"
        else:
            meets = (h * an >= 2 * ah * n) if action == "立项候选" else (2 * h * an <= ah * n)
            if meets and cur and cur["status"] == "历史观察" and cur["version_no"] == ent["tip"]["version"]:
                new_no = RULES.upgrade(conn, rule_id, recon_month, multiple or 0.0, snap["label"], operator)
                result = "升为已验证"
        conn.execute(D.rule_reconciliation.insert().values(
            reconciliation_id=rid, rule_id=rule_id, rule_version_no=ent["tip"]["version"], snapshot_id=snap["id"],
            recon_month=recon_month, action=action,
            segments_json=D.dumps({"referenced": segs, "with_batch": with_batch}), hits=h, n=n, batch_avg=avg,
            multiple=multiple, condition_text=ent["tip"]["cond"], result=result, new_version_no=new_no,
            created_by=operator, created_at=clock.now_iso()))
    return int(rid)


def reconciliations(conn: Connection, category_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(select(D.reconciliation).where(D.reconciliation.c.category_id == category_id)
                        .order_by(D.reconciliation.c.id.desc())).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["detail"] = D.loads(r["detail_json"], {})
        d["snapshot"] = RK.get_snapshot(conn, r["snapshot_id"])
        d["rules"] = [dict(x) | {"segments": D.loads(x["segments_json"], {})} for x in conn.execute(
            select(D.rule_reconciliation).where(D.rule_reconciliation.c.reconciliation_id == r["id"])
            .order_by(D.rule_reconciliation.c.id)).mappings().all()]
        for x in d["rules"]:
            rule = conn.execute(select(D.rule.c.code).where(D.rule.c.id == x["rule_id"])).scalar()
            x["code"] = rule
        out.append(d)
    return out


def rule_recon_history(conn: Connection, rule_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(select(D.rule_reconciliation).where(D.rule_reconciliation.c.rule_id == rule_id)
                        .order_by(D.rule_reconciliation.c.id.desc())).mappings().all()
    return [dict(r) for r in rows]
