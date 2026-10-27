"""台账（月度快照、立项记录、到期对账）、策略库与备份恢复：PAGE-F10-01..06、PAGE-F11-01/02。

Ledger tables are append-only (DEC-007/014): every write here appends a record or a version.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from markupsafe import Markup
from sqlalchemy import func, select, text
from sqlalchemy.engine import Connection

from oppo import clock, fmt
from oppo import db as D
from oppo.core import backup as BK
from oppo.core import cards as CARD
from oppo.core import categories as CAT
from oppo.core import compute as CMP
from oppo.core import jobs
from oppo.core import judge as J
from oppo.core import ledger as LG
from oppo.core import packages as PK
from oppo.core import ranking as RK
from oppo.core import rules as RULES
from oppo.core import segments as SEG
from oppo.core import signals as SIG
from oppo.web import common as C

router = APIRouter()

OWN_BADGE = {J.HIT: "hit", J.MISS: "miss", J.WATCH: "watch", J.INCOMPLETE: "incomplete"}


# ---- shared helpers --------------------------------------------------------------------------


def _next(form: Any, default: str) -> str:
    """Only same-site relative paths are accepted as the page to return to (fragment and modal-opening
    parameters dropped, so the page reloads with the modal closed)."""
    nxt = str(form.get("next") or "").split("#", 1)[0]
    if nxt.startswith("/ledger/decisions") or nxt.startswith("/ledger/reconcile"):
        nxt = nxt.split("?", 1)[0]
    p = urlparse(nxt)
    if nxt.startswith("/") and not nxt.startswith("//") and not p.netloc:
        return nxt
    return default


def _size(n: int | None) -> str:
    if n is None:
        return "无数据"
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    return f"{max(1, round(n / 1024))} KB"


def recon_bar(rate: float | None, lo: float | None, hi: float | None, avg: float | None, top_txt: str,
              avg_txt: str, cross: bool = False) -> Markup:
    """Reconciliation interval bar: band = expected interval saved with the snapshot, dot = actual,
    line = category actual (same 0–60 % geometry as fmt.ibar)."""
    if rate is None or lo is None or hi is None:
        return fmt.etag(fmt.NO_DATA, "nodata")
    x = fmt._x  # noqa: SLF001 - shared geometry
    band_x, band_w = x(lo), max(1.0, round(x(hi) - x(lo), 1))
    parts = ['<line class="ibar__track" x1="0" y1="10" x2="160" y2="10"/>',
             f'<rect class="ibar__band" x="{band_x}" y="7" width="{band_w}" height="6" rx="3"/>']
    if avg is not None:
        parts.append(f'<line class="ibar__avg" x1="{x(avg)}" y1="3" x2="{x(avg)}" y2="17"/>')
    parts.append(f'<circle class="ibar__dot" cx="{x(rate)}" cy="10" r="4"/>')
    kind = "截面预期区间" if cross else "回测预期区间"
    exp = fmt.ci_text([lo, hi])
    label = f"实际命中率 {top_txt}，{kind} {exp}，全类目实际 {avg_txt}"
    tip = f"实际 {top_txt}|{kind} {exp}|竖线：全类目实际 {avg_txt}"
    from html import escape

    return Markup(f'<span class="ibar" tabindex="0" aria-label="{escape(label)}" data-tip="{escape(tip)}">'
                  f'<svg width="160" height="20" viewBox="0 0 160 20" aria-hidden="true">{"".join(parts)}</svg>'
                  f'</span>')


def own_pop(st: dict[str, Any]) -> dict[str, str]:
    return {"来源": st.get("source") or "手工录入", "录入人": st.get("created_by") or "—",
            "性质": "自家实际数据", "上架月": st["launch_month"],
            "窗口": f"{st['launch_month']} 至 {st['window_end']}", "上次保存": (st.get("created_at") or "")[:16]}


C.env.globals.update(recon_bar=recon_bar, own_pop=own_pop, size_text=_size, OWN_BADGE=OWN_BADGE,
                     add_months=PK.add_months, seg_name=SEG.seg_name, RULES_cond=RULES.cond_text,
                     CANDIDATE_SIGNALS=SIG.CURRENT)


def _tab_counts(conn: Connection, cid: int) -> dict[str, int]:
    def n(table: Any) -> int:
        return int(conn.execute(select(func.count()).select_from(table).where(table.c.category_id == cid)).scalar()
                   or 0)
    return {"snapshots": n(D.snapshot), "decisions": n(D.decision_record), "reconcile": n(D.reconciliation)}


def _window(conn: Connection, cid: int) -> int:
    return int(CAT.current_version(conn, cid)["config"]["success"]["window_months"])


def _latest_months(conn: Connection, cid: int) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for m in ("history", "cross"):
        r = CMP.latest_run(conn, cid, m)
        out[m] = r["latest_month"] if r else None
    return out


def _recon_by_snapshot(conn: Connection, cid: int) -> dict[int, dict[str, Any]]:
    rows = conn.execute(select(D.reconciliation).where(D.reconciliation.c.category_id == cid)
                        .order_by(D.reconciliation.c.id)).mappings().all()
    return {r["snapshot_id"]: dict(r) for r in rows}


def snapshot_states(conn: Connection, cid: int) -> list[dict[str, Any]]:
    """Every snapshot with its reconciliation state (DEC-006: the version last exported in the month, else the
    last version, is the one reconciled; other versions of the month are 不用于对账)."""
    snaps = RK.snapshot_rows(conn, cid)
    window = _window(conn, cid)
    latest = _latest_months(conn, cid)
    recons = _recon_by_snapshot(conn, cid)
    chosen: dict[tuple[str, str], dict[str, Any]] = {}
    for s in snaps:
        k = (s["month"], s["mode"])
        if k not in chosen:
            chosen[k] = RK.reconcile_version(conn, cid, s["month"], s["mode"]) or s
    newest = {}
    for s in snaps:
        newest.setdefault(s["mode"], s["month"])
    out = []
    for s in snaps:
        d = dict(s)
        pick = chosen[(s["month"], s["mode"])]
        same_month = [x for x in snaps if x["month"] == s["month"] and x["mode"] == s["mode"]]
        d["expected"] = PK.add_months(s["month"], window)
        d["window_end"] = PK.add_months(s["month"], window - 1)
        rec = recons.get(s["id"])
        notes = []
        if s["month"] == newest.get(s["mode"]) and s["id"] == max(x["id"] for x in same_month):
            notes.append("本月 · 当前最后一版")
        elif len(same_month) > 1 and s["id"] == pick["id"] and s["exported_at"]:
            notes.append("同月最后导出的版本")
        if s["mode"] == "cross":
            notes.append("截面口径")
        d["note"] = " · ".join(notes)
        if rec:
            d["recon"] = "done"
            d["recon_rec"] = rec
        elif s["id"] != pick["id"]:
            d["recon"] = "unused"
            d["unused_reason"] = (f"同月第 {pick['seq']} 版已导出" if pick.get("exported_at")
                                  else "同月有更晚的版本")
        else:
            lm = latest.get(s["mode"])
            d["recon"] = "pending"
            d["due_now"] = bool(lm and d["window_end"] <= lm)
            d["export_hint"] = not s["exported_at"]
        out.append(d)
    return out


def _card_text(snap: dict[str, Any]) -> str:
    lab = snap.get("card_label") or "—"
    return lab


def _tips_of(content: dict[str, Any]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for r in content.get("rows") or []:
        for t in r.get("tips") or []:
            e = seen.setdefault(t["rule"], {**t, "segments": []})
            e["segments"].append(r["segment"])
    order = {a: i for i, a in enumerate(RULES.ACTIONS)}
    return sorted(seen.values(), key=lambda t: (order.get(t["action"], 9), t["rule"]))


# ---- PAGE-F10-02: record decision modal (also included on /ranking) ---------------------------


def decision_ctx(conn: Connection, cid: int, mode: str = "history") -> dict[str, Any]:
    """Context for templates/partials/F10-02.html."""
    snap = RK.latest_snapshot(conn, cid, mode)
    cfg_ver = CAT.current_version(conn, cid)
    cfg = cfg_ver["config"]
    content = (snap or {}).get("content") or {}
    rows = content.get("rows") or []
    by_key = {r["segment_key"]: r for r in rows}
    segs: list[tuple[str, str]] = [(r["segment_key"], r["segment"]) for r in rows]
    for k in SEG.all_segment_keys(cfg):
        if k not in by_key:
            segs.append((k, SEG.seg_name(k)))
    card = CARD.get(conn, snap["card_id"]) if snap and snap.get("card_id") else None
    pkg = PK.current_package(conn, cid, mode)
    month = snap["month"] if snap else (PK.add_months(pkg["months_to"], 1) if pkg and pkg.get("months_to") else None)
    return {
        "snapshot": snap, "rows": rows, "by_key": by_key, "segments": segs, "mode": mode,
        "average": content.get("average") or {}, "effective": content.get("effective"),
        "month": month, "today": clock.now().date().isoformat(), "card": card,
        "card_status": snap["card_status"] if snap else None, "cfg_no": cfg_ver["version_no"],
    }


def _records_ctx(conn: Connection, cid: int) -> list[dict[str, Any]]:
    return LG.records(conn, cid)


async def _form(request: Request) -> Any:
    return await request.form()


@router.post("/ledger/decisions")
async def post_decision(request: Request) -> JSONResponse:
    app = C.svc(request)
    form = await _form(request)
    mode = str(form.get("mode") or "history")
    key = str(form.get("segment_key") or "")
    with app.engine.begin() as conn:
        cid = app.category_id()
        snap = RK.latest_snapshot(conn, cid, mode if mode in ("history", "cross") else "history")
        if snap is None:
            return C.fail("还没有快照，请先生成本月排序；系统启用前的立项请用补录")
        try:
            code = LG.record_decision(conn, cid, app.operator, str(form.get("decision") or ""), key,
                                      SEG.seg_name(key), str(form.get("reason") or ""), snap["id"],
                                      str(form.get("project_date") or "") or None,
                                      str(form.get("project_name") or "") or None)
        except LG.LedgerError as exc:
            return C.fail(str(exc), exc.fields)
    return C.ok(redirect=_next(form, "/ledger/decisions"), toast=f"已记录 {code}")


@router.post("/ledger/backfill")
async def post_backfill(request: Request) -> JSONResponse:
    app = C.svc(request)
    form = await _form(request)
    key = str(form.get("segment_key") or "")
    with app.engine.begin() as conn:
        cid = app.category_id()
        try:
            code = LG.record_backfill(conn, cid, app.operator, str(form.get("project_name") or ""),
                                      str(form.get("project_date") or ""), key, SEG.seg_name(key),
                                      str(form.get("basis_note") or ""))
        except LG.LedgerError as exc:
            return C.fail(str(exc), exc.fields)
    return C.ok(redirect=_next(form, "/ledger/decisions"), toast=f"已补录 {code}")


@router.post("/ledger/decisions/{code}/correct")
async def post_correct(request: Request, code: str) -> JSONResponse:
    app = C.svc(request)
    form = await _form(request)
    key = str(form.get("segment_key") or "")
    vals = {"reason": str(form.get("reason") or ""), "decision": str(form.get("decision") or "") or None,
            "segment_key": key or None, "segment_name": SEG.seg_name(key) if key else None,
            "project_name": str(form.get("project_name") or "") or None,
            "project_date": str(form.get("project_date") or "") or None,
            "basis_note": str(form.get("basis_note") or "") or None}
    with app.engine.begin() as conn:
        cid = app.category_id()
        try:
            new = LG.correct(conn, cid, app.operator, code, **vals)
        except LG.LedgerError as exc:
            return C.fail(str(exc), exc.fields)
    return C.ok(redirect=_next(form, "/ledger/decisions"), toast=f"已追加更正 {new}，{code} 标为已更正")


@router.post("/ledger/import-c7")
def post_import_c7(request: Request) -> JSONResponse:
    app = C.svc(request)
    with app.engine.begin() as conn:
        cid = app.category_id()
        pv = LG.c7_preview(conn, cid)
        if not pv["package"]:
            return C.fail("当前没有历史数据包")
        if not pv["rows"]:
            return C.fail("当前数据包没有 C7 自家立项")
        label = pv["package"]["label"]
        if not pv["new"] and not pv["launch"]:
            return C.ok(redirect="/ledger/decisions",
                        toast=f"已读取 {label} 的 C7 自家立项 {len(pv['rows'])} 行：都已在台账中，没有新的立项或上架数据")
        try:
            LG.import_c7(conn, cid, app.operator)
        except LG.LedgerError as exc:
            return C.fail(str(exc))
    return C.ok(redirect="/ledger/decisions",
                toast=f"已从 {label} 的 C7 导入：新增补录 {len(pv['new'])} 条，上架数据 {len(pv['launch'])} 条")


@router.post("/ledger/launch/{code}")
async def post_launch(request: Request, code: str) -> JSONResponse:
    app = C.svc(request)
    form = await _form(request)
    months = [{k: form.get(f"{k}_{i}") for k in ("units", "sales", "bsr")} for i in range(1, 7)]
    with app.engine.begin() as conn:
        cid = app.category_id()
        try:
            st = LG.save_launch_data(conn, cid, app.operator, code, str(form.get("launch_month") or ""), months,
                                     str(form.get("asin") or ""))
        except LG.LedgerError as exc:
            return C.fail(str(exc), exc.fields)
    extra = f" · 还剩 {st['remaining']} 个月" if st.get("status") == J.WATCH else ""
    return C.ok(redirect=_next(form, "/ledger/decisions"), toast=f"已保存 {code} 上架数据：{st.get('status')}{extra}")


# ---- PAGE-F10-01 月度快照 ---------------------------------------------------------------------


@router.get("/ledger")
def ledger_root() -> RedirectResponse:
    return RedirectResponse("/ledger/snapshots", status_code=303)


@router.get("/ledger/snapshots", response_class=HTMLResponse)
def snapshots_page(request: Request) -> HTMLResponse:
    app = C.svc(request)
    with app.engine.begin() as conn:
        cid = app.category_id()
        page = max(1, int(request.query_params.get("page") or 1)) if (request.query_params.get("page") or "1").isdigit() else 1
        states = snapshot_states(conn, cid)
        total = len(states)
        shown = states[(page - 1) * 50: page * 50]
        decisions = LG.records(conn, cid, with_status=False)
        for s in shown:
            s["tips"] = _tips_of(s["content"])
            s["decisions"] = [r for r in decisions if r["snapshot_id"] == s["id"]]
            s["card"] = CARD.get(conn, s["card_id"]) if s.get("card_id") else None
        bk_set = BK.setting(conn)
        bk_ok = BK.last_success(conn)
        cur_snap = RK.latest_snapshot(conn, cid, C.mode_of(request, conn, cid))
        ctx = {
            "tabs": _tab_counts(conn, cid), "snaps": shown, "total": total, "page": page,
            "pages": max(1, (total + 49) // 50),
            "counts": {k: sum(1 for s in states if s["recon"] == k) for k in ("pending", "done", "unused")},
            "mode_counts": {m: sum(1 for s in states if s["mode"] == m) for m in ("history", "cross")},
            "month_span": (states[-1]["month"], states[0]["month"]) if states else None,
            "open_id": request.query_params.get("snap"), "data_dir": str(app.settings.data_dir),
            "bk_set": bk_set, "bk_ok": bk_ok, "cur_snap": cur_snap, "window": _window(conn, cid),
            "cfg_dims": " × ".join(d["label"] for d in CAT.current_version(conn, cid)["config"]["segment_dims"]),
        }
    return C.render(request, "pages/F10-01.html", "PAGE-F10-01", ctx)


# ---- PAGE-F10-04 立项记录 ---------------------------------------------------------------------


@router.get("/ledger/decisions", response_class=HTMLResponse)
def decisions_page(request: Request) -> HTMLResponse:
    app = C.svc(request)
    q = request.query_params
    with app.engine.begin() as conn:
        cid = app.category_id()
        mode = C.mode_of(request, conn, cid)
        recs = LG.records(conn, cid)
        recon_ids = {r["snapshot_id"]: r["id"] for r in LG.reconciliations(conn, cid)}
        for r in recs:
            r["recon_id"] = recon_ids.get(r["snapshot_id"]) if r["snapshot_id"] else None
        pv = LG.c7_preview(conn, cid)
        correct = None
        if q.get("correct"):
            correct = next((r for r in recs if r["code"] == q.get("correct") and not r["corrected_by"]), None)
        launch = None
        if q.get("launch"):
            launch = next((r for r in recs if r["code"] == q.get("launch") and r["decision"] == "立项"
                           and not r["corrected_by"]), None)
        cfg_ver = CAT.current_version(conn, cid)
        ctx = {
            "tabs": _tab_counts(conn, cid), "recs": recs, "c7": pv, "decision_ctx": decision_ctx(conn, cid, mode),
            "correct": correct, "launch": launch, "launch_ctx": _launch_ctx(conn, cid, launch) if launch else None,
            "open_modal": q.get("new") or ("backfill" if q.get("backfill") else None),
            "cfg_no": cfg_ver["version_no"], "cfg": cfg_ver["config"],
            "counts": {
                "go": sum(1 for r in recs if r["decision"] == "立项"),
                "nogo": sum(1 for r in recs if r["decision"] == "不立项"),
                "record": sum(1 for r in recs if r["kind"] == "记录"),
                "backfill": sum(1 for r in recs if r["kind"] == "补录"),
                "correction": sum(1 for r in recs if r["kind"] == "更正"),
            },
        }
    return C.render(request, "pages/F10-04.html", "PAGE-F10-04", ctx)


def _launch_ctx(conn: Connection, cid: int, rec: dict[str, Any]) -> dict[str, Any]:
    st = rec.get("launch")
    cfg_ver = CAT.current_version(conn, cid)
    cur = LG.current_month(conn, cid)
    lm = st["launch_month"] if st else None
    months = (st or {}).get("months") or [{} for _ in range(6)]
    return {"status": st, "current": cur, "launch_month": lm, "months": months, "cfg": cfg_ver["config"],
            "cfg_no": cfg_ver["version_no"], "window": int(cfg_ver["config"]["success"]["window_months"])}


# ---- PAGE-F10-05 到期对账 ---------------------------------------------------------------------


def _batch_progress(spus: Any, month: str) -> dict[str, int] | None:
    if spus is None or spus.empty:
        return None
    b = spus[(spus["is_new"] == 1) & (spus["rising"] == 1) & (spus["batch"] == month)]
    st = b["status"].value_counts().to_dict()
    hit, miss = int(st.get(J.HIT, 0)), int(st.get(J.MISS, 0))
    return {"total": int(len(b)), "decided": hit + miss, "hit": hit, "miss": miss,
            "watch": int(st.get(J.WATCH, 0)), "incomplete": int(st.get(J.INCOMPLETE, 0))}


def _own_rows(conn: Connection, cid: int, recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Effective 立项 records (corrections replace originals) in project-date order (AC-F10-05)."""
    rows = []
    for r in recs:
        if r["decision"] != "立项" or r["corrected_by"]:
            continue
        d = dict(r)
        snap = r.get("snapshot")
        d["snap_row"] = None
        d["snap_avg"] = None
        if snap:
            content = snap["content"]
            d["snap_row"] = next((x for x in content.get("rows") or [] if x["segment_key"] == r["segment_key"]), None)
            d["snap_avg"] = (content.get("average") or {}).get("rate")
            d["snap_eff"] = content.get("effective")
        rows.append(d)
    rows.sort(key=lambda x: (x["project_date"] or "", x["code"]))
    return rows


def reconcile_ctx(conn: Connection, cid: int) -> dict[str, Any]:
    recs_all = LG.reconciliations(conn, cid)
    states = snapshot_states(conn, cid)
    run_ = CMP.latest_run(conn, cid, "history")
    spus = CMP.spus_frame(conn, run_["id"]) if run_ else None
    pending = [s for s in reversed(states) if s["recon"] == "pending"]
    for s in pending:
        s["progress"] = None if s["month"] == (run_ or {}).get("t_month") else _batch_progress(
            spus if s["mode"] == "history" else None, s["month"])
        s["this_month"] = run_ is not None and s["month"] >= run_["t_month"]
    unused = [s for s in states if s["recon"] == "unused"]
    hist_recs = [r for r in recs_all if r["mode"] == "history"]
    latest_hist = hist_recs[0] if hist_recs else None
    upgrades = [x for x in (latest_hist or {}).get("rules", []) if x["result"] == "升为已验证"]
    rules_map = {r["rule_id"]: r for r in RULES.list_current(conn, cid)}
    records = LG.records(conn, cid)
    own = _own_rows(conn, cid, records)
    launched = [r for r in own if r.get("launch")]
    cfg = CAT.current_version(conn, cid)
    top_rows = []
    for r in recs_all:
        for sg in (r["detail"] or {}).get("segments", []):
            if sg.get("top"):
                top_rows.append({"rec": r, **sg})
    return {
        "recs": recs_all, "latest": recs_all[0] if recs_all else None, "latest_hist": latest_hist,
        "upgrades": upgrades, "rules_map": rules_map, "pending": pending, "unused": unused,
        "next_due": pending[0] if pending else None, "own": own, "launched": launched,
        "corrected": [r for r in records if r["corrected_by"]],
        "nogo": [r for r in records if r["decision"] == "不立项" and not r["corrected_by"]],
        "cfg": cfg["config"], "cfg_no": cfg["version_no"], "top_rows": top_rows,
        "counts": {m: sum(1 for r in recs_all if r["mode"] == m) for m in ("history", "cross")},
        "reference": RK.reference_text(cfg["config"]),
        "pkg": PK.current_package(conn, cid, "history"),
    }


@router.get("/ledger/reconcile", response_class=HTMLResponse)
def reconcile_page(request: Request) -> HTMLResponse:
    return _reconcile(request, None)


@router.get("/ledger/reconcile/{rid}", response_class=HTMLResponse)
def reconcile_one(request: Request, rid: int) -> HTMLResponse:
    return _reconcile(request, rid)


def _reconcile(request: Request, rid: int | None) -> HTMLResponse:
    app = C.svc(request)
    with app.engine.begin() as conn:
        cid = app.category_id()
        ctx = reconcile_ctx(conn, cid)
        ctx["tabs"] = _tab_counts(conn, cid)
        ctx["focus"] = rid
        q = request.query_params
        ctx["launch"] = None
        if q.get("launch"):
            rec = next((r for r in LG.records(conn, cid) if r["code"] == q.get("launch")), None)
            if rec and rec["decision"] == "立项" and not rec["corrected_by"]:
                ctx["launch"] = rec
                ctx["launch_ctx"] = _launch_ctx(conn, cid, rec)
    return C.render(request, "pages/F10-05.html", "PAGE-F10-05", ctx)


# ---- PAGE-F11-01 / F11-02 策略库 --------------------------------------------------------------


def _attr_values(conn: Connection, cid: int) -> dict[str, list[str]]:
    pkg = PK.current_package(conn, cid, "history") or PK.current_package(conn, cid, "cross")
    cfg = CAT.current_version(conn, cid)["config"]
    seg_attrs = {d.get("attr") for d in cfg["segment_dims"]}
    names = [a for a in cfg.get("attribute_dims") or [] if a not in seg_attrs]
    out: dict[str, list[str]] = {a: [] for a in names}
    if pkg:
        rows = conn.execute(text("SELECT dim, value, count(*) AS n FROM raw_c4 WHERE package_id=:p AND value IS NOT NULL "
                                 "AND value != '' GROUP BY dim, value ORDER BY dim, n DESC"), {"p": pkg["id"]}).all()
        for dim, value, _n in rows:
            if dim in out and value not in (SEG.UNKNOWN,) and value not in out[dim]:
                out[dim].append(value)
    return out


def _rule_field_options(conn: Connection, cid: int, extra_keys: set[str] | None = None) -> dict[str, Any]:
    cfg_ver = CAT.current_version(conn, cid)
    cfg = cfg_ver["config"]
    signals = [(k, SIG.LABELS[k]) for k in SIG.SIGNALS]
    cand = [(k, SIG.LABELS[k]) for k in SIG.CURRENT]
    if extra_keys and "xprob" in extra_keys:
        signals.append(("xprob", RULES.SIGNAL_LABELS["xprob"]))
    dims = [(d["key"], d["label"], [b["label"] for b in d["bins"]]) for d in cfg["segment_dims"]]
    attrs = _attr_values(conn, cid)
    return {"signals": signals, "candidates": cand, "dims": dims, "attrs": attrs, "cfg_no": cfg_ver["version_no"],
            "values": {**{f"dim:{k}": v for k, _l, v in dims}, **{f"attr:{k}": v for k, v in attrs.items()}},
            "pct": sorted(RULES.PCT_SIGNALS), "signed": sorted(RULES.SIGNED)}


def _rule_rows(conn: Connection, cid: int) -> list[dict[str, Any]]:
    bt_codes = {r[0]: r[1] for r in conn.execute(select(D.backtest_run.c.code, D.backtest_run.c.id))}
    rows = []
    for r in RULES.list_current(conn, cid):
        d = dict(r)
        hist = RULES.history(conn, r["rule_id"])
        d["versions"] = hist
        manual_later = sorted((v for v in hist if not _is_system(v, r) and v["version_no"] > 1),
                              key=lambda v: v["version_no"])
        if r["origin"] == "回测":
            d["source_text"] = "回测生成" + (f"，v{manual_later[0]['version_no']} 人工修改" if manual_later else "")
        else:
            d["source_text"] = "人工新增"
        d["actor"] = _actor(hist[0], r)
        recon = LG.rule_recon_history(conn, r["rule_id"])
        d["recon"] = None
        if recon:
            x = recon[0]
            rec = conn.execute(select(D.reconciliation).where(D.reconciliation.c.id == x["reconciliation_id"])
                               ).mappings().first()
            snap = RK.get_snapshot(conn, x["snapshot_id"])
            d["recon"] = {**x, "rec": dict(rec) if rec else None, "snapshot": snap,
                          "segments": D.loads(x["segments_json"], {})}
        b = r["basis"] or {}
        d["bt_id"] = bt_codes.get(b.get("backtest"))
        d["cross"] = bool(r["cross_tag"])
        d["status_key"] = {"已验证": "verified", "历史观察": "observed"}.get(r["status"], "unverified")
        d["search"] = " ".join([r["code"], r["cond_text"], r["reason"] or "", r["action"]])
        rows.append(d)
    rows.sort(key=lambda x: x["updated_at"] or "", reverse=True)
    return rows


def _is_system(ver: dict[str, Any], rule: dict[str, Any]) -> bool:
    """Versions written by a backtest or a reconciliation (older databases stored the operator's name)."""
    note = ver.get("change_note") or ""
    return (ver["created_by"] == RULES.SYSTEM or note.startswith("由回测") or ("对账" in note and "升为已验证" in note)
            or (rule["origin"] == "回测" and ver["version_no"] == 1))


def _actor(ver: dict[str, Any], rule: dict[str, Any]) -> str:
    if not _is_system(ver, rule):
        return ver["created_by"]
    note = ver.get("change_note") or ""
    if "对账" in note:
        return "系统 · 到期对账"
    b = ver.get("basis") if isinstance(ver.get("basis"), dict) else D.loads(ver.get("basis_json"), {}) or {}
    return f"系统 · 回测 {b.get('backtest')}" if b.get("backtest") else "系统"


def _diff(new: dict[str, Any], old: dict[str, Any]) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Changed items between two rule versions, and the names of unchanged ones."""
    changes, same = [], []
    nc, oc = new["conds"], old["conds"]
    for i in range(max(len(nc), len(oc))):
        a = RULES.cond_text([oc[i]]) if i < len(oc) else "—"
        b = RULES.cond_text([nc[i]]) if i < len(nc) else "—"
        if a != b:
            changes.append((f"条件 {i + 1}", a, b))
        else:
            same.append(f"条件 {i + 1}")
    if new["action"] != old["action"]:
        changes.append(("动作", old["action"], new["action"]))
    else:
        same.append("动作")
    if new["status"] != old["status"]:
        changes.append(("状态", old["status"], new["status"]))
    return changes, same


def _rule_editor(conn: Connection, cid: int, code: str) -> dict[str, Any] | None:
    if code == "new":
        return {"new": True, "rule": None, "versions": [], "opts": _rule_field_options(conn, cid),
                "conds": [{"kind": "", "key": "", "op": "", "value": ""}]}
    rule = RULES.by_code(conn, code)
    if rule is None or rule["category_id"] != cid:
        return None
    hist = RULES.history(conn, rule["rule_id"])
    vers = []
    for i, v in enumerate(hist):
        older = hist[i + 1] if i + 1 < len(hist) else None
        ch, same = _diff(v, older) if older else ([], [])
        vers.append({**v, "actor": _actor(v, rule), "system": _is_system(v, rule), "changes": ch, "same": same,
                     "current": i == 0})
    keys = {c["key"] for c in rule["conds"]}
    conds = []
    for c in rule["conds"]:
        conds.append({"kind": c["kind"], "key": c["key"], "op": c.get("op") or "=",
                      "value": RULES.fmt_value(c["key"], c["value"]) if c["kind"] == "signal" else c["value"]})
    return {"new": False, "rule": rule, "versions": vers, "opts": _rule_field_options(conn, cid, keys),
            "conds": conds}


@router.get("/rules", response_class=HTMLResponse)
def rules_page(request: Request) -> HTMLResponse:
    app = C.svc(request)
    with app.engine.begin() as conn:
        cid = app.category_id()
        mode = C.mode_of(request, conn, cid)
        rows = _rule_rows(conn, cid)
        code = request.query_params.get("rule")
        editor = _rule_editor(conn, cid, code) if code else None
        card = CARD.current_card(conn, cid, mode)
        snap = RK.latest_snapshot(conn, cid, mode)
        used = [t["rule"] for t in _tips_of(snap["content"])] if snap else []
        ctx = {"rows": rows, "editor": editor, "missing_rule": code if code and editor is None else None,
               "counts": {s: sum(1 for r in rows if r["status"] == s) for s in RULES.STATUSES},
               "origin_counts": {o: sum(1 for r in rows if r["origin"] == o) for o in ("人工", "回测")},
               "card": card, "used": used, "focus_code": code}
    return C.render(request, "pages/F11-01.html", "PAGE-F11-01", ctx)


def _cond_rows(form: Any) -> list[dict[str, Any]]:
    fields = form.getlist("cond_field")
    ops = form.getlist("cond_op")
    vals = form.getlist("cond_value")
    rows = []
    for i, f in enumerate(fields):
        kind, _, key = str(f or "").partition(":")
        rows.append({"kind": kind or None, "key": key, "op": ops[i] if i < len(ops) else "",
                     "value": vals[i] if i < len(vals) else ""})
    return rows


@router.post("/rules")
async def post_rule_new(request: Request) -> JSONResponse:
    return await _save_rule(request, None)


@router.post("/rules/{code}")
async def post_rule_edit(request: Request, code: str) -> JSONResponse:
    return await _save_rule(request, code)


async def _save_rule(request: Request, code: str | None) -> JSONResponse:
    app = C.svc(request)
    form = await _form(request)
    action = str(form.get("action") or "")
    reason = str(form.get("reason") or "")
    with app.engine.begin() as conn:
        cid = app.category_id()
        cfg_ver = CAT.current_version(conn, cid)
        conds, errs = RULES.check_conds(_cond_rows(form), cfg_ver["config"], cfg_ver["version_no"],
                                        _attr_values(conn, cid))
        if action not in RULES.ACTIONS:
            errs["action"] = "请选择动作"
        if not reason.strip():
            errs["reason"] = "请写明理由"
        if errs:
            return C.fail("还有需要补充或修改的内容", errs)
        try:
            if code is None:
                rid = RULES.add(conn, cid, conds, action, reason, app.operator)
                rule = RULES.current(conn, rid)
            else:
                rule = RULES.by_code(conn, code)
                if rule is None:
                    return C.fail("规则不存在")
                exp = str(form.get("expected_version") or "")
                RULES.edit(conn, rule["rule_id"], conds, action, reason, app.operator,
                           int(exp) if exp.isdigit() else None)
                rule = RULES.current(conn, rule["rule_id"])
        except RULES.RuleError as exc:
            return C.fail(str(exc), exc.fields)
    assert rule is not None
    return C.ok(redirect="/rules", toast=f"已保存 {rule['code']} v{rule['version_no']} · {rule['status']}")


# ---- PAGE-F10-03 备份与恢复 -------------------------------------------------------------------


def _fmt_stats(st: dict[str, Any] | None) -> dict[str, str]:
    if not st:
        return {k: "无数据" for k in ("ledger", "rules", "conv", "cfg", "conf")}
    return {"ledger": f"快照 {st['snapshots']} · 立项记录 {st['decisions']}",
            "rules": f"{st['rules']} 条" + (f" · 最近修改 {st['rule_updated']}" if st["rule_updated"] else ""),
            "conv": f"v{st['contract']}" if st["contract"] else "—", "cfg": f"v{st['config']}" if st["config"] else "—",
            "conf": f"{st['confirmations']:,} 条"}


def _trigger_text(conn: Connection, rec: dict[str, Any] | None) -> str:
    if not rec:
        return "—"
    if rec["trigger"] == "导出后自动":
        ex = conn.execute(select(D.export_record).where(D.export_record.c.backup_id == rec["id"])).mappings().first()
        if ex:
            snap = RK.get_snapshot(conn, ex["snapshot_id"])
            return f"导出 {snap['label'].replace(' · ', ' ')}" if snap else f"导出 {ex['month']}"
        return "导出后自动备份"
    return {"恢复前": "恢复前自动备份", "手动重试": "手动重试备份"}.get(rec["trigger"], rec["trigger"])


@router.get("/settings/backup", response_class=HTMLResponse)
def backup_page(request: Request) -> HTMLResponse:
    app = C.svc(request)
    with app.engine.begin() as conn:
        cid = app.category_id()
        st = BK.setting(conn)
        recs = BK.records(conn)
        by_path = {r["path"]: r for r in recs if r["path"]}
        files = BK.list_files(conn)
        cur = _fmt_stats(BK.current_stats(conn))
        for f in files:
            rec = by_path.get(f["path"])
            f["record"] = rec
            f["trigger_text"] = _trigger_text(conn, rec)
            f["stats"] = _fmt_stats(BK.file_stats(f["path"]))
            f["folder"] = Path(f["path"]).name
        last = BK.last_attempt(conn)
        ok = BK.last_success(conn)
        restore = BK.last_restore(conn)
        show_restore = request.query_params.get("restored") and restore
        pre = None
        if show_restore and restore["pre_backup_id"]:
            pre = conn.execute(select(D.backup_record).where(D.backup_record.c.id == restore["pre_backup_id"])
                               ).mappings().first()
        cur_snap = RK.latest_snapshot(conn, cid, "history")
        job = jobs.running(conn)
        ctx = {"setting": st, "files": files, "last": last, "last_ok": ok, "current": cur,
               "last_trigger": _trigger_text(conn, last), "restore": restore if show_restore else None,
               "pre_backup": pre, "cur_snap": cur_snap, "data_dir": str(app.settings.data_dir), "running": job,
               "free": BK.free_space(st["directory"]) if st and st["directory"] else None,
               "failed_records": [r for r in recs if r["status"] == "failed"][:5]}
    return C.render(request, "pages/F10-03.html", "PAGE-F10-03", ctx)


@router.post("/settings/backup/check")
async def backup_check(request: Request) -> JSONResponse:
    form = await _form(request)
    path = str(form.get("directory") or "").strip()
    if not path:
        return C.fail("请填写备份目录", {"directory": "请填写备份目录"})
    ok, msg = BK.check_writable(path)
    if not ok:
        return C.fail(msg, {"directory": msg})
    free = BK.free_space(path)
    return JSONResponse({"ok": True, "message": msg, "free": _gb(free), "checked_at": clock.now_iso()[:16]})


def _gb(n: int | None) -> str:
    return "无数据" if n is None else f"{n / 1024 ** 3:.1f} GB"


C.env.globals.update(size_gb=_gb)


@router.post("/settings/backup/dir")
async def backup_dir(request: Request) -> JSONResponse:
    app = C.svc(request)
    form = await _form(request)
    path = str(form.get("directory") or "")
    with app.engine.begin() as conn:
        ok, msg = BK.set_directory(conn, path, app.operator)
    if not ok:
        return C.fail(msg, {"directory": msg})
    return C.ok(redirect="/settings/backup", toast=f"备份目录已保存：{path.strip()}")


@router.post("/settings/backup/run")
def backup_run(request: Request) -> JSONResponse:
    app = C.svc(request)
    with app.engine.begin() as conn:
        if jobs.running(conn):
            return C.fail("有计算任务正在运行，完成后再试")
        res = BK.run_backup(app.settings.db_path, conn, "手动重试", app.operator, app.category_id())
    if res["status"] != "success":
        return C.ok(redirect="/settings/backup", toast=f"备份失败：{res['error']}")
    return C.ok(redirect="/settings/backup", toast=f"备份完成：{res['time'][:16]}")


@router.post("/settings/backup/restore")
async def backup_restore(request: Request) -> JSONResponse:
    app = C.svc(request)
    form = await _form(request)
    path = str(form.get("path") or "")
    with app.engine.begin() as conn:
        known = {f["path"] for f in BK.list_files(conn)}
    if path not in known:
        return C.fail("只能从备份目录中由本系统生成的备份恢复")
    if str(form.get("confirm") or "") != "yes":
        return C.fail("恢复需要二次确认")
    try:
        res = BK.restore(app, Path(path), confirm=True)
    except BK.RestoreError as exc:
        return C.fail(str(exc))
    return C.ok(redirect="/settings/backup?restored=1", toast=f"已恢复到 {(res['backup_time'] or '')[:16]} 的备份")
