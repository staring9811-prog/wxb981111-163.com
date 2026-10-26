"""PAGE-F03-01 本月工作台 and the background-job endpoints every page uses (DEC-010)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from oppo import service as SV
from oppo.core import backtest as BT
from oppo.core import jobs
from oppo.web import common as C
from oppo.web import viewmodels as VM

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def workbench(request: Request) -> HTMLResponse:
    app = C.svc(request)
    with app.engine.begin() as conn:
        cid = app.category_id()
        mode = C.mode_of(request, conn, cid)
        vm = VM.workbench_summary(conn, app, mode)
        foot = VM.footer(conn, cid, mode)
    return C.render(request, "pages/F03-01.html", "PAGE-F03-01", {"vm": vm, "foot": foot})


def _start(request: Request, fn, **kw) -> JSONResponse:  # type: ignore[no-untyped-def]
    app = C.svc(request)
    try:
        jid = fn(app, background=True, **kw)
    except jobs.JobBusy as exc:
        return C.fail(str(exc), status=409)
    except (PermissionError, ValueError, BT.BacktestError) as exc:
        return C.fail(str(exc))
    return C.ok(job=jid, redirect=request.headers.get("x-oppo-next"))


@router.post("/jobs/compute")
def job_compute(request: Request) -> JSONResponse:
    return _start(request, SV.compute)


@router.post("/jobs/backtest")
async def job_backtest(request: Request) -> JSONResponse:
    form = await request.form()
    mode = str(form.get("mode") or request.query_params.get("mode") or "history")
    return _start(request, SV.backtest, mode=mode if mode in ("history", "cross") else "history")


@router.post("/jobs/recompute")
def job_recompute(request: Request) -> JSONResponse:
    return _start(request, SV.recompute)
