"""Shared page plumbing: Jinja environment, layout context (sidebar counts, top bar versions, mode),
form/JSON helpers and job state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.engine import Connection

from oppo import clock, fmt
from oppo import db as D
from oppo.core import adjust as ADJ
from oppo.core import cards as CARD
from oppo.core import categories as CAT
from oppo.core import compute as CMP
from oppo.core import contract as CT
from oppo.core import health as H
from oppo.core import jobs
from oppo.core import packages as PK
from oppo.core import spu as SPU

HERE = Path(__file__).resolve().parent
env = Environment(loader=FileSystemLoader(str(HERE / "templates")), autoescape=select_autoescape(["html"]),
                  trim_blocks=True, lstrip_blocks=True)
env.globals.update(fmt=fmt, ibar=fmt.ibar, etag=fmt.etag, badge=fmt.badge, icon=fmt.icon, segname=fmt.segname,
                   pct=fmt.pct, pct0=fmt.pct0, num=fmt.num, money=fmt.money, mult=fmt.mult, ci_text=fmt.ci_text,
                   is_none=fmt.is_none, NO_DATA=fmt.NO_DATA, CARD=CARD, loads=D.loads)
env.filters["pct"] = fmt.pct
env.filters["num"] = fmt.num
env.filters["money"] = fmt.money
env.filters["mult"] = fmt.mult
env.filters["dt"] = lambda s: (s or "")[:16]

NAV = [
    ("PAGE-F03-01", "/", "house", "本月工作台", None),
    ("group", "数据准备"),
    ("PAGE-F01-01", "/packages", "package", "数据包", None),
    ("PAGE-F02-01", "/fields", "list-checks", "字段约定", "fields"),
    ("PAGE-F03-02", "/health", "heartbeat", "数据体检", "health"),
    ("PAGE-F15-01", "/review", "note-pencil", "数据审核", "review"),
    ("group", "新品"),
    ("PAGE-F04-01", "/spu", "cube", "新品与 SPU", None),
    ("PAGE-F04-02", "/spu/merge", "git-merge", "合并建议", "merges"),
    ("group", "分析"),
    ("PAGE-F06-01", "/signals", "chart-line-up", "信号", None),
    ("PAGE-F07-01", "/backtest", "flask", "回测", None),
    ("PAGE-F08-01", "/card", "cards", "判定卡", None),
    ("PAGE-F08-02", "/kits", "lightbulb", "立项锦囊", None),
    ("PAGE-F09-01", "/ranking", "list-numbers", "本月排序", None),
    ("group", "沉淀"),
    ("PAGE-F10-01", "/ledger/snapshots", "book-open-text", "台账", None),
    ("PAGE-F11-01", "/rules", "stack", "策略库", None),
    ("group", "设置"),
    ("PAGE-F13-01", "/settings/category", "sliders-horizontal", "品类配置", None),
    ("PAGE-F10-03", "/settings/backup", "database", "备份与恢复", None),
    ("PAGE-F14-01", "/settings/runs", "timer", "运行记录", None),
]
NAV_PARENT = {"PAGE-F01-02": "PAGE-F01-01", "PAGE-F05-01": "PAGE-F04-01", "PAGE-F10-04": "PAGE-F10-01",
              "PAGE-F10-05": "PAGE-F10-01"}


def svc(request: Request) -> Any:
    return request.app.state.svc


def mode_of(request: Request, conn: Connection, cid: int) -> str:
    m = request.query_params.get("mode") or request.cookies.get("oppo_mode")
    if m in ("history", "cross"):
        return m
    if PK.current_package(conn, cid, "history") is None and PK.current_package(conn, cid, "cross") is not None:
        return "cross"
    return "history"


def layout(request: Request, conn: Connection, page_id: str) -> dict[str, Any]:
    app = svc(request)
    cid = CAT.current_category_id(conn)
    cfg_ver = CAT.current_version(conn, cid)
    mode = mode_of(request, conn, cid)
    hist = PK.current_package(conn, cid, "history")
    cross = PK.current_package(conn, cid, "cross")
    cv = CT.current_version(conn, cid)
    pending_fields = CT.pending_count(conn, cid)
    pending_merges = len(SPU.suggestions(conn, cid, "pending"))
    pending_adjust = ADJ.counts(conn, cid)[ADJ.PENDING]
    warns = len(H.open_warnings(conn, cid))
    eff = CARD.effective(conn, cid)
    card_h = CARD.current_card(conn, cid, "history")
    card_x = CARD.current_card(conn, cid, "cross")
    job = jobs.running(conn)
    category = conn.execute(D.category.select().where(D.category.c.id == cid)).mappings().first()
    return {
        "request": request, "page_id": page_id, "nav": NAV, "nav_active": NAV_PARENT.get(page_id, page_id),
        "nav_counts": {"fields": pending_fields, "health": warns, "merges": pending_merges,
                       "review": pending_adjust},
        "token": request.app.state.token, "operator": app.operator, "cid": cid, "cfg": cfg_ver["config"],
        "cfg_ver": cfg_ver, "category_name": f"亚马逊美国 · {category['name']}" if category else "",
        "mode": mode, "both_modes": hist is not None and cross is not None, "has_cross": cross is not None,
        "pkg_history": hist, "pkg_cross": cross, "pkg": cross if mode == "cross" else hist,
        "contract_ver": cv, "card_effective": eff, "card_history": card_h, "card_cross": card_x,
        "card_mode": card_x if mode == "cross" else card_h, "job": job,
        "job_label": jobs.JOB_LABELS.get(job["kind"], job["kind"]) if job else None,
        "toast": request.query_params.get("toast"), "path": request.url.path,
        "full_path": str(request.url.path) + (("?" + str(request.url.query)) if request.url.query else ""),
        "now": clock.now(),
    }


def render(request: Request, template: str, page_id: str, ctx: dict[str, Any], status: int = 200) -> HTMLResponse:
    app = svc(request)
    with app.engine.begin() as conn:
        base = layout(request, conn, page_id)
    base.update(ctx)
    html = env.get_template(template).render(**base)
    return HTMLResponse(html, status_code=status)


def ok(redirect: str | None = None, toast: str | None = None, **extra: Any) -> JSONResponse:
    if redirect and toast:
        from urllib.parse import quote

        redirect += ("&" if "?" in redirect else "?") + "toast=" + quote(toast)
    return JSONResponse({"ok": True, "redirect": redirect, **extra})


def fail(error: str, fields: dict[str, str] | None = None, status: int = 200) -> JSONResponse:
    """A refused write. Validation answers with 200 + ok:false so the browser console stays clean; callers pass
    409 for a running job when the status code matters."""
    return JSONResponse({"ok": False, "error": error, "fields": fields or {}}, status_code=status)


def job_state(request: Request) -> dict[str, Any]:
    app = svc(request)
    with app.engine.begin() as conn:
        cur = jobs.running(conn)
        last = jobs.latest(conn)
    if cur:
        p = jobs.progress(cur["id"])
        return {"running": True, "id": cur["id"], "kind": cur["kind"], "label": jobs.JOB_LABELS.get(cur["kind"]),
                "step": p.get("step"), "progress": p.get("progress")}
    out: dict[str, Any] = {"running": False}
    if last:
        out.update(id=last["id"], kind=last["kind"], status=last["status"], error=last["error"],
                   label=jobs.JOB_LABELS.get(last["kind"]), started_at=last["started_at"], ended_at=last["ended_at"],
                   result=D.loads(last.get("result_json")))
    return out


def error_page(request: Request, status: int, message: str) -> str:
    return env.get_template("error.html").render(status=status, message=message)


def stale_reasons(conn: Connection, cid: int) -> list[str]:
    out: list[str] = []
    for mode in ("history", "cross"):
        for r in CMP.stale_reasons(conn, cid, CMP.latest_run(conn, cid, mode)):
            if r not in out:
                out.append(r)
    return out
