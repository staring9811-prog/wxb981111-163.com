"""Ledger: decisions, own launch data and due reconciliation (F10: REQ-F10-02/03, AC-F10-02..05;
F11: AC-F11-03/06, D-27, DEC-006/007/012/027/029)."""

from __future__ import annotations

import re
from datetime import datetime
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
    """`fields` maps form field names to messages shown next to the field."""

    def __init__(self, message: str, fields: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.fields = fields or {}


MSG_SEGMENT = "请选择关联细分"
MSG_DECISION = "请选择立项或不立项"
MSG_REASON = "请写下理由，日后对账要看当时为什么这样决定"
MSG_DATE = "请按 2027-05-08 的格式填写，且不晚于今天"
MSG_REQUIRED = "必填"


def _next_code(conn: Connection) -> str:
    n = conn.execute(select(func.count()).select_from(D.decision_record)).scalar() or 0
    return f"D-{n + 1:04d}"


def _date_ok(s: str | None) -> bool:
    """A real YYYY-MM-DD date that is not later than today."""
    if not (s and re.match(r"^\d{4}-\d{2}-\d{2}$", s)):
        return False
    try:
        d = datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return False
    return d <= clock.now().date()


def _raise(fields: dict[str, str]) -> None:
    if fields:
        raise LedgerError("；".join(dict.fromkeys(fields.values())), fields)


def record_decision(conn: Connection, category_id: int, operator: str, decision: str, segment_key: str,
                    segment_name: str, reason: str, snapshot_id: int | None, project_date: str | None = None,
                    project_name: str | None = None) -> str:
    fields: dict[str, str] = {}
    if not (segment_key or "").strip():
        fields["segment_key"] = MSG_SEGMENT
    if decision not in ("立项", "不立项"):
        fields["decision"] = MSG_DECISION
    if decision == "立项" and project_date and not _date_ok(project_date):
        fields["project_date"] = MSG_DATE
    if not (reason or "").strip():
        fields["reason"] = MSG_REASON
    _raise(fields)
    code = _next_code(conn)
    conn.execute(D.decision_record.insert().values(
        category_id=category_id, code=code, kind="记录", decision=decision, segment_key=segment_key,
        segment_name=segment_name, reason=reason.strip(), snapshot_id=snapshot_id,
        project_name=(project_name or "").strip() or None,
        project_date=(project_date or None) if decision == "立项" else None, source="手工", created_by=operator,
        created_at=clock.now_iso()))
    return code


def record_backfill(conn: Connection, category_id: int, operator: str, project_name: str, project_date: str,
                    segment_key: str, segment_name: str, basis_note: str = "") -> str:
    fields: dict[str, str] = {}
    if not (project_name or "").strip():
        fields["project_name"] = MSG_REQUIRED
    if not (project_date or "").strip():
        fields["project_date"] = MSG_REQUIRED
    elif not _date_ok(project_date):
        fields["project_date"] = MSG_DATE
    if not (segment_key or "").strip():
        fields["segment_key"] = MSG_REQUIRED
    _raise(fields)
    code = _next_code(conn)
    conn.execute(D.decision_record.insert().values(
        category_id=category_id, code=code, kind="补录", decision="立项", segment_key=segment_key,
        segment_name=segment_name, reason=None, snapshot_id=None, project_name=project_name.strip(),
        project_date=project_date, basis_note=(basis_note or "").strip() or None, source="手工",
        created_by=operator, created_at=clock.now_iso()))
    return code


def correct(conn: Connection, category_id: int, operator: str, original_code: str, **fields: Any) -> str:
    """Append a correction; the original is shown as 已更正 (DEC-007). Unspecified fields keep the original's."""
    orig = conn.execute(select(D.decision_record).where(D.decision_record.c.code == original_code)).mappings().first()
    if orig is None:
        raise LedgerError("原记录不存在")
    if conn.execute(select(D.decision_record.c.id).where(D.decision_record.c.corrects_id == orig["id"])).first():
        raise LedgerError("该记录已有更正，请对更正记录再追加更正")
    vals = {k: (fields[k] if fields.get(k) not in (None, "") else orig[k])
            for k in ("decision", "segment_key", "segment_name", "project_name", "project_date", "basis_note")}
    errs: dict[str, str] = {}
    reason = (fields.get("reason") or "").strip()
    if not reason:
        errs["reason"] = "请填写更正理由"
    if vals["decision"] not in ("立项", "不立项"):
        errs["decision"] = MSG_DECISION
    if not (vals["segment_key"] or "").strip():
        errs["segment_key"] = MSG_SEGMENT
    if vals["decision"] == "立项" and vals["project_date"] and not _date_ok(vals["project_date"]):
        errs["project_date"] = MSG_DATE
    if orig["kind"] == "补录" or (orig["kind"] == "更正" and orig["snapshot_id"] is None):
        if not (vals["project_name"] or "").strip():
            errs["project_name"] = MSG_REQUIRED
    _raise(errs)
    if vals["decision"] == "不立项":
        vals["project_date"] = None
    code = _next_code(conn)
    conn.execute(D.decision_record.insert().values(
        category_id=category_id, code=code, kind="更正", reason=reason, snapshot_id=orig["snapshot_id"],
        corrects_id=orig["id"], source="手工", created_by=operator, created_at=clock.now_iso(), **vals))
    return code


def segment_key_of(text_value: str | None) -> str:
    """C7 writes segments the way people read them ("30–48″ · 落地式 · $500–900"); keys use "|"."""
    return " ".join((text_value or "").split()).replace(" · ", "|").strip()


def c7_preview(conn: Connection, category_id: int) -> dict[str, Any]:
    """What 从数据包导入自家立项 would add (DEC-012): new 补录 records and launch data."""
    pkg = PK.current_package(conn, category_id, "history")
    if not pkg:
        return {"package": None, "rows": [], "new": [], "launch": []}
    rows = [dict(r) for r in conn.execute(select(D.raw_c7).where(D.raw_c7.c.package_id == pkg["id"])).mappings()]
    recs = [r for r in records(conn, category_id, with_status=False) if r["decision"] == "立项"]
    by_key = {}
    for r in recs:
        if not r["corrected_by"]:
            by_key[(r["project_name"], r["project_date"])] = r
    new, launch = [], []
    for r in rows:
        key = (r["name"], r["project_date"])
        rec = by_key.get(key)
        lm = (r.get("launch_date") or "")[:7] or None
        if rec is None:
            new.append(r)
            if lm:
                launch.append({"name": r["name"], "launch_month": lm, "asin": r.get("asin"), "decision": None})
        elif lm and not launch_status(conn, category_id, rec["id"]):
            launch.append({"name": r["name"], "launch_month": lm, "asin": r.get("asin"), "decision": rec["code"]})
    return {"package": pkg, "rows": rows, "new": new, "launch": launch}


def import_c7(conn: Connection, category_id: int, operator: str) -> int:
    """New C7 projects become 补录 records; C7 launch dates become their launch data. Returns rows written."""
    pkg = PK.current_package(conn, category_id, "history")
    if not pkg:
        raise LedgerError("当前没有历史数据包")
    pv = c7_preview(conn, category_id)
    if not pv["rows"]:
        raise LedgerError("当前数据包不含 C7 自家立项")
    n = 0
    cfg_ver = CAT.current_version(conn, category_id)
    codes = {}
    for r in pv["new"]:
        code = _next_code(conn)
        key = segment_key_of(r["segment_or_attr"])
        conn.execute(D.decision_record.insert().values(
            category_id=category_id, code=code, kind="补录", decision="立项", segment_key=key,
            segment_name=key.replace("|", " · "), project_name=r["name"], project_date=r["project_date"],
            basis_note=f"从数据包 {pkg['label']} 的 C7 导入", source="数据包", created_by=operator,
            created_at=clock.now_iso()))
        codes[r["name"]] = code
        n += 1
    for item in pv["launch"]:
        code = item["decision"] or codes.get(item["name"])
        rec = conn.execute(select(D.decision_record).where(D.decision_record.c.code == code)).mappings().first()
        if rec is None:
            continue
        conn.execute(D.launch_data.insert().values(
            decision_id=rec["id"], launch_month=item["launch_month"], asin=item["asin"] or None,
            months_json=D.dumps({"months": [{"units": None, "sales": None, "bsr": None} for _ in range(6)],
                                 "source": f"C7 导入（{pkg['label']}）"}),
            config_version_id=cfg_ver["id"], created_by=operator, created_at=clock.now_iso()))
        n += 1
    return n


def records(conn: Connection, category_id: int, with_status: bool = True) -> list[dict[str, Any]]:
    rows = conn.execute(select(D.decision_record).where(D.decision_record.c.category_id == category_id)
                        .order_by(D.decision_record.c.id.desc())).mappings().all()
    out = [dict(r) for r in rows]
    by_id = {r["id"]: r for r in out}
    corrected_by = {r["corrects_id"]: r for r in out if r["corrects_id"]}
    snaps: dict[int, Any] = {}
    for r in out:
        r["corrected_by"] = corrected_by.get(r["id"])
        r["corrects"] = by_id.get(r["corrects_id"]) if r["corrects_id"] else None
        if not with_status:
            continue
        r["launch"] = launch_status(conn, category_id, r["id"])
        sid = r["snapshot_id"]
        if sid and sid not in snaps:
            snaps[sid] = RK.get_snapshot(conn, sid)
        r["snapshot"] = snaps.get(sid) if sid else None
    return out


# ---- own launch data (AC-F10-05, DEC-012) ----------------------------------------------------


def _parse_cell(v: Any, kind: str) -> tuple[float | None, str | None]:
    """Blank = missing (not 0). Units: non-negative integer; sales: non-negative number with optional
    thousands separators; BSR: positive integer."""
    s = "" if v is None else str(v).strip().replace(",", "").replace("，", "")
    if kind == "sales":
        s = s.replace("$", "")
    if s == "":
        return None, None
    try:
        x = float(s)
    except ValueError:
        x = None
    msgs = {"units": "请填写整数；没有数据就留空", "sales": "请填写金额数字；没有数据就留空",
            "bsr": "小类 BSR 应为正整数；没有数据就留空"}
    if x is None or x != x or x < 0 or (kind != "sales" and x != int(x)) or (kind == "bsr" and x < 1):
        return None, msgs[kind]
    return (int(x) if kind != "sales" else x), None


ASIN_RE = re.compile(r"^(B0[0-9A-Z]{8}|[A-Za-z0-9][A-Za-z0-9_\-]{1,31})$")


def save_launch_data(conn: Connection, category_id: int, operator: str, decision_code: str, launch_month: str,
                     months: list[dict[str, Any]], asin: str = "") -> dict[str, Any]:
    """Validate and append launch data (latest row wins). Field errors use names asin, launch_month,
    units_1..6, sales_1..6, bsr_1..6."""
    rec = conn.execute(select(D.decision_record).where(D.decision_record.c.code == decision_code)).mappings().first()
    if rec is None:
        raise LedgerError("立项记录不存在")
    if rec["decision"] != "立项":
        raise LedgerError("不立项的决定不参与自家对账")
    if conn.execute(select(D.decision_record.c.id).where(D.decision_record.c.corrects_id == rec["id"])).first():
        raise LedgerError("该记录已被更正，请在更正记录上录入")
    errors: dict[str, str] = {}
    asin = (asin or "").strip()
    if not asin or not ASIN_RE.match(asin):
        errors["asin"] = "请填写父 ASIN 或自家 SPU 编号"
    lm = (launch_month or "").strip()
    now_month = clock.now().strftime("%Y-%m")
    proj_month = (rec["project_date"] or "")[:7]
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", lm) or lm > now_month or (proj_month and lm < proj_month):
        errors["launch_month"] = "请按 2026-09 的格式填写上架月" + ("（不早于立项月份，不晚于本月）" if
                                                             re.match(r"^\d{4}-\d{2}$", lm) else "")
    clean = []
    for i, m in enumerate((months + [{}] * 6)[:6], start=1):
        row: dict[str, Any] = {}
        for key in ("units", "sales", "bsr"):
            v, msg = _parse_cell(m.get(key), key)
            if msg:
                errors[f"{key}_{i}"] = msg
            row[key] = v
        clean.append(row)
    if errors:
        raise LedgerError("有需要修改的格子", errors)
    prev = launch_status(conn, category_id, rec["id"])
    cfg_ver = CAT.current_version(conn, category_id)
    conn.execute(D.launch_data.insert().values(
        decision_id=rec["id"], launch_month=lm, asin=asin, months_json=D.dumps({"months": clean, "source": "手工录入"}),
        config_version_id=cfg_ver["id"], created_by=operator, created_at=clock.now_iso()))
    if prev:
        conn.execute(D.change_log.insert().values(
            category_id=category_id, object="自家上架数据", object_id=decision_code, action="修改上架数据",
            item=None, before=D.dumps({"launch_month": prev["launch_month"], "asin": prev["asin"],
                                       "months": prev["months"]}),
            after=D.dumps({"launch_month": lm, "asin": asin, "months": clean}), created_by=operator,
            created_at=clock.now_iso()))
    return launch_status(conn, category_id, rec["id"]) or {}


def current_month(conn: Connection, category_id: int) -> str:
    pkg = PK.current_package(conn, category_id, "history")
    if pkg and pkg["months_to"]:
        return pkg["months_to"]
    return clock.now().strftime("%Y-%m")


def judge_own(launch_month: str, months: list[dict[str, Any]], current: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Own launch against the category success line (AC-F10-05): first month reaching BSR ≤ line or sales ≥ line
    is a hit; a month missing units, sales or BSR inside the elapsed window makes an unhit result 数据不全."""
    succ = cfg["success"]
    window = int(succ["window_months"])
    bsr_max, gmv_min = float(succ["bsr_max"]), float(succ["gmv_min"])
    elapsed = len(month_range(launch_month, current)) if current >= launch_month else 0
    elapsed = min(elapsed, window)
    best_bsr = max_sales = best_bsr_age = max_sales_age = None
    missing = []
    base = {"window": window, "elapsed": elapsed, "window_end": add_months(launch_month, window - 1)}
    for age, m in enumerate(months[:window], start=1):
        if age > elapsed:
            break
        bsr, sales, units = m.get("bsr"), m.get("sales"), m.get("units")
        if bsr is not None and (best_bsr is None or bsr < best_bsr):
            best_bsr, best_bsr_age = bsr, age
        if sales is not None and (max_sales is None or sales > max_sales):
            max_sales, max_sales_age = sales, age
        best = {"best_bsr": best_bsr, "max_sales": max_sales, "best_bsr_age": best_bsr_age,
                "max_sales_age": max_sales_age}
        if (bsr is not None and bsr <= bsr_max) or (sales is not None and sales >= gmv_min):
            return {**base, "status": J.HIT, "hit_age": age, "hit_month": add_months(launch_month, age - 1),
                    **best, "basis": "BSR" if bsr is not None and bsr <= bsr_max else "GMV"}
        if bsr is None or sales is None or units is None:
            missing.append(add_months(launch_month, age - 1))
    best = {"best_bsr": best_bsr, "max_sales": max_sales, "best_bsr_age": best_bsr_age,
            "max_sales_age": max_sales_age}
    if missing and elapsed >= window:
        return {**base, "status": J.INCOMPLETE, "missing": missing, **best}
    if elapsed < window:
        return {**base, "status": J.WATCH, "remaining": window - elapsed, "missing": missing, **best}
    return {**base, "status": J.MISS, **best}


def launch_status(conn: Connection, category_id: int, decision_id: int) -> dict[str, Any] | None:
    row = conn.execute(select(D.launch_data).where(D.launch_data.c.decision_id == decision_id)
                       .order_by(D.launch_data.c.id.desc()).limit(1)).mappings().first()
    if not row:
        return None
    cfg = CAT.current_version(conn, category_id)
    raw = D.loads(row["months_json"], [])
    months, source = (raw.get("months", []), raw.get("source", "手工录入")) if isinstance(raw, dict) else (raw, "手工录入")
    res = judge_own(row["launch_month"], months, current_month(conn, category_id), cfg["config"])
    return {**dict(row), "months": months, "source": source, **res, "config_version_no": cfg["version_no"],
            "current_month": current_month(conn, category_id)}


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
