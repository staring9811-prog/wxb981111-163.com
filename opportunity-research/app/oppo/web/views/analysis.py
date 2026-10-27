"""分析组页面：PAGE-F07-01 回测、PAGE-F08-01 判定卡、PAGE-F08-02 立项锦囊、PAGE-F09-01 本月排序，
以及 PAGE-F12-01 导出报告弹窗（导出任务、打开导出的文件）。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.engine import Connection

from oppo import db as D
from oppo import fmt
from oppo import service as SV
from oppo.core import backtest as BT
from oppo.core import backup as BK
from oppo.core import cards as CARD
from oppo.core import categories as CAT
from oppo.core import compute as CMP
from oppo.core import jobs
from oppo.core import packages as PK
from oppo.core import ranking as RK
from oppo.core import rules as RULES
from oppo.core import signals as SIG
from oppo.web import common as C
from oppo.web.report import present as P

router = APIRouter()

C.env.globals.update(P=P, SIG_LABELS=SIG.LABELS, fmt_rule_value=RULES.fmt_value, BT_CONFOUNDERS=BT.CONFOUNDERS)

EXCEL_SHEETS = ("首页", "细分排序", "锦囊", "判定卡版本", "回测摘要", "台账-快照", "台账-立项记录", "台账-对账", "版本信息")


def _job_ctx(conn: Connection) -> dict[str, Any]:
    cur = jobs.running(conn)
    return {"running_job": cur, "running_label": jobs.JOB_LABELS.get(cur["kind"], cur["kind"]) if cur else None,
            "running_step": jobs.progress(cur["id"]).get("step") if cur else None}


def _month_T(conn: Connection, cid: int, mode: str) -> str | None:
    pkg = PK.current_package(conn, cid, mode)
    return PK.add_months(pkg["months_to"], 1) if pkg and pkg.get("months_to") else None


# ---- PAGE-F07-01 回测 ------------------------------------------------------------------------------


@router.get("/backtest", response_class=HTMLResponse)
def backtest_page(request: Request) -> HTMLResponse:
    app = C.svc(request)
    with app.engine.begin() as conn:
        cid = app.category_id()
        mode = C.mode_of(request, conn, cid)
        cfg = CAT.current_version(conn, cid)["config"]
        hist = P.backtest_view(conn, BT.latest(conn, cid, "history"))
        cross = P.backtest_view(conn, BT.latest(conn, cid, "cross"))
        run_ = CMP.latest_run(conn, cid, mode)
        last = jobs.latest(conn, "backtest")
        cur_bt = hist if mode == "history" else cross
        failed = None
        if last and last["status"] == "failed" and (cur_bt is None or (last["started_at"] or "") >=
                                                     (cur_bt["bt"]["started_at"] or "")):
            failed = last
        ctx = {
            "hist": hist, "cross": cross, "report": cur_bt, "cfg": cfg, "run": run_, "failed": failed,
            "stale": [r for r in CMP.stale_reasons(conn, cid, run_)] if run_ else [],
            "reference": RK.reference_text(cfg), "card_now": CARD.current_card(conn, cid, mode)
            or CARD.effective(conn, cid)["card"], "vers": P.versions(conn, cid, mode), **_job_ctx(conn),
            "cross_pkg": P.package_info(conn, cross["bt"]["package_id"]) if cross else None,
        }
    return C.render(request, "pages/F07-01.html", "PAGE-F07-01", ctx)


# ---- PAGE-F08-01 判定卡 -----------------------------------------------------------------------------


@router.get("/card", response_class=HTMLResponse)
def card_page(request: Request) -> HTMLResponse:
    app = C.svc(request)
    with app.engine.begin() as conn:
        cid = app.category_id()
        mode = C.mode_of(request, conn, cid)
        cfg = CAT.current_version(conn, cid)["config"]
        eff = CARD.effective(conn, cid)
        card = CARD.current_card(conn, cid, mode) or (eff["card"] if mode == "history" else None)
        bt = P.backtest_view(conn, BT.get(conn, card["backtest_id"])) if card and card.get("backtest_id") else None
        snap = RK.latest_snapshot(conn, cid, card["mode"]) if card else None
        kits = P.kits(conn, cid, card["mode"], snap) if card else []
        hist_card = CARD.current_card(conn, cid, "history")
        ctx = {
            "card": card, "bt": bt, "eff": eff, "cfg": cfg, "defs": P.signal_defs(cfg), "kits": kits,
            "versions": P.card_versions(conn, cid), "reference": RK.reference_text(cfg),
            "superseded": bool(card and card["mode"] == "cross" and hist_card),
            "hist_card": hist_card, "snapshot": snap, "stale": C.stale_reasons(conn, cid),
            "vers": P.versions(conn, cid, card["mode"] if card else mode), **_job_ctx(conn),
            "card_pkg": P.package_info(conn, bt["bt"]["package_id"]) if bt else None,
        }
    return C.render(request, "pages/F08-01.html", "PAGE-F08-01", ctx)


# ---- PAGE-F08-02 立项锦囊 ---------------------------------------------------------------------------


@router.get("/kits", response_class=HTMLResponse)
def kits_page(request: Request) -> HTMLResponse:
    app = C.svc(request)
    with app.engine.begin() as conn:
        cid = app.category_id()
        mode = C.mode_of(request, conn, cid)
        cfg = CAT.current_version(conn, cid)["config"]
        eff = CARD.effective(conn, cid)
        card = CARD.current_card(conn, cid, mode) or (eff["card"] if mode == "history" else None)
        snap = RK.latest_snapshot(conn, cid, card["mode"]) if card else None
        items = P.kits(conn, cid, card["mode"], snap) if card else []
        bt = P.backtest_view(conn, BT.get(conn, card["backtest_id"])) if card and card.get("backtest_id") else None
        ctx = {"card": card, "bt": bt, "items": items, "counts": P.kit_counts(items), "cfg": cfg,
               "reference": RK.reference_text(cfg), "snapshot": snap, "stale": C.stale_reasons(conn, cid),
               "avg": (snap["content"]["average"] if snap else {}) or {},
               "vers": P.versions(conn, cid, card["mode"] if card else mode)}
    return C.render(request, "pages/F08-02.html", "PAGE-F08-02", ctx)


# ---- PAGE-F09-01 本月排序 + PAGE-F12-01 导出弹窗 ------------------------------------------------------


def _export_result(conn: Connection, eid: int) -> dict[str, Any] | None:
    row = conn.execute(select(D.export_record).where(D.export_record.c.id == eid)).mappings().first()
    if not row:
        return None
    out = dict(row)
    bk = None
    if row["backup_id"]:
        bk = conn.execute(select(D.backup_record).where(D.backup_record.c.id == row["backup_id"])).mappings().first()
    out["backup"] = dict(bk) if bk else None
    out["last_success"] = BK.last_success(conn)
    out["snapshot"] = RK.get_snapshot(conn, row["snapshot_id"])
    out["xlsx_name"] = Path(row["xlsx_path"]).name if row["xlsx_path"] else None
    out["html_name"] = Path(row["html_path"]).name if row["html_path"] else None
    out["folder"] = str(Path(row["xlsx_path"]).parent) if row["xlsx_path"] else None
    return out


@router.get("/ranking", response_class=HTMLResponse)
def ranking_page(request: Request) -> HTMLResponse:
    app = C.svc(request)
    with app.engine.begin() as conn:
        cid = app.category_id()
        mode = C.mode_of(request, conn, cid)
        cfg = CAT.current_version(conn, cid)["config"]
        T = _month_T(conn, cid, mode)
        snaps = [s for s in RK.snapshot_rows(conn, cid, mode) if s["month"] == T] if T else []
        snap = snaps[0] if snaps else None
        older = RK.latest_snapshot(conn, cid, mode)
        bt = BT.get(conn, snap["backtest_id"]) if snap and snap.get("backtest_id") else None
        card = CARD.get(conn, snap["card_id"]) if snap else None
        content = snap["content"] if snap else None
        pkg = PK.current_package(conn, cid, mode)
        bk_set = BK.setting(conn)
        stale = C.stale_reasons(conn, cid)
        want_export = request.query_params.get("export") == "1"
        done = request.query_params.get("done")
        export_done = _export_result(conn, int(done)) if done and done.isdigit() else None
        from oppo.web.views import ledger as LV

        decision_ctx = None
        if snap and hasattr(LV, "decision_ctx"):
            try:
                decision_ctx = LV.decision_ctx(conn, cid, mode)
            except Exception:  # noqa: BLE001 - the ledger group owns this helper; the page still renders
                decision_ctx = None
        ctx = {
            "T": T, "snap": snap, "older": older, "content": content, "bt": bt, "card": card, "cfg": cfg,
            "reference": RK.reference_text(cfg), "stale": stale, "pkg": pkg, "backup_setting": bk_set,
            "want_export": want_export, "export_done": export_done, "sheets": EXCEL_SHEETS,
            "exports_dir": str(app.settings.exports_dir / (T or "")), "decision_ctx": decision_ctx,
            "category": conn.execute(select(D.category).where(D.category.c.id == cid)).mappings().first(),
            "vers": P.versions(conn, cid, mode), "bt_view": P.backtest_view(conn, bt) if bt else None,
            "card_banner": CARD.banner(card["status"]) if card else None, **_job_ctx(conn),
        }
    return C.render(request, "pages/F09-01.html", "PAGE-F09-01", ctx)


@router.post("/jobs/export")
async def job_export(request: Request) -> JSONResponse:
    app = C.svc(request)
    form = await request.form()
    month = str(form.get("month") or "") or None
    mode = str(form.get("mode") or "history")
    with app.engine.begin() as conn:
        cid = app.category_id()
        if not [s for s in RK.snapshot_rows(conn, cid, mode) if month is None or s["month"] == month]:
            return C.fail("还没有可导出的排序快照")
    try:
        jid = SV.export(app, month, mode if mode in ("history", "cross") else "history", background=True)
    except jobs.JobBusy as exc:
        return C.fail(str(exc), status=409)
    return C.ok(job=jid)


@router.get("/exports/{eid}/html")
def export_html(request: Request, eid: int) -> FileResponse:
    app = C.svc(request)
    with app.engine.begin() as conn:
        res = _export_result(conn, eid)
    if not res or not res["html_path"] or not Path(res["html_path"]).is_file():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="网页报告文件不存在")
    return FileResponse(res["html_path"], media_type="text/html; charset=utf-8")


def _reveal(path: Path) -> bool:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])  # noqa: S603, S607
        else:
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603,S607
        return True
    except OSError:
        return False


@router.post("/exports/{eid}/open")
def export_open(request: Request, eid: int) -> JSONResponse:
    app = C.svc(request)
    with app.engine.begin() as conn:
        res = _export_result(conn, eid)
    if not res or not res["folder"] or not Path(res["folder"]).is_dir():
        return C.fail("导出目录不存在")
    if _reveal(Path(res["folder"])):
        return JSONResponse({"ok": True, "toast": f"已在资源管理器中打开 {res['folder']}"})
    return C.fail(f"本机无法直接打开文件夹，请手动打开：{res['folder']}")


def ranking_tip_text(r: dict[str, Any]) -> str:
    return fmt.pct0(r.get("point"))
