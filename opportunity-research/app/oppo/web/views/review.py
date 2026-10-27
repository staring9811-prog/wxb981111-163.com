"""PAGE-F15-01 数据审核: proposals from Codex (local API) or typed in by hand wait here; a person confirms them as
proposed, edits the value before confirming, or rejects them. Confirmed adjustments can be revoked. The imported
package never changes."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from oppo import service as SV
from oppo.core import adjust as ADJ
from oppo.core import jobs
from oppo.core import packages as PK
from oppo.web import common as C

router = APIRouter()
PAGE = 100
TABS = {"pending": [ADJ.PENDING], "confirmed": [ADJ.CONFIRMED],
        "other": [ADJ.REJECTED, ADJ.WITHDRAWN, ADJ.REVOKED]}
FILTERS = ("package", "file", "field", "source", "batch", "child")


def _filters(request: Request) -> dict[str, str]:
    return {k: (request.query_params.get(k) or "").strip() for k in FILTERS}


def _select(conn: Any, cid: int, f: dict[str, str], statuses: list[str]) -> list[dict[str, Any]]:
    pid = None
    if f["package"]:
        pkg = PK.by_label(conn, f["package"])
        pid = pkg["id"] if pkg else -1
    out: list[dict[str, Any]] = []
    for st in statuses:
        out += ADJ.listing(conn, cid, package_id=pid, status=st, file_code=f["file"] or None,
                           field=f["field"] or None, source=f["source"] or None, batch=f["batch"] or None,
                           child=f["child"] or None)
    return sorted(out, key=lambda r: r["id"], reverse=True)


@router.get("/review", response_class=HTMLResponse)
def review(request: Request) -> HTMLResponse:
    app = C.svc(request)
    tab = request.query_params.get("tab") or "pending"
    if tab not in TABS:
        tab = "pending"
    f = _filters(request)
    try:
        page = max(1, int(request.query_params.get("page") or 1))
    except ValueError:
        page = 1
    with app.engine.begin() as conn:
        cid = app.category_id()
        pkgs = PK.list_packages(conn, cid)
        labels = {p["id"]: p["label"] for p in pkgs}
        counts = ADJ.counts(conn, cid)
        rows = _select(conn, cid, f, TABS[tab])
        everything = ADJ.listing(conn, cid)
        cur = [p for p in (PK.current_package(conn, cid, m) for m in ("cross", "history")) if p]
        fields_by_pkg = {p["label"]: ADJ.files_of(conn, p["id"]) for p in cur}
        busy = jobs.running(conn)
        stale = C.stale_reasons(conn, cid)
    total = len(rows)
    pages = max(1, (total + PAGE - 1) // PAGE)
    page = min(page, pages)
    shown = rows[(page - 1) * PAGE: page * PAGE]
    for r in shown:
        r["package"] = labels.get(r["package_id"], "")
    opts = {k: sorted({str(r[k2]) for r in everything if r.get(k2)})
            for k, k2 in (("file", "file_code"), ("field", "field"), ("source", "source"), ("batch", "batch"))}
    opts["package"] = sorted({labels[r["package_id"]] for r in everything if r["package_id"] in labels})

    def link(**kw: Any) -> str:
        q = {**{k: v for k, v in f.items() if v}, "tab": tab, **kw}
        return "/review?" + urlencode({k: v for k, v in q.items() if v not in (None, "")})

    return C.render(request, "pages/F15-01.html", "PAGE-F15-01", {
        "tab": tab, "rows": shown, "total": total, "page": page, "pages": pages, "link": link, "f": f,
        "opts": opts, "counts": counts, "stale": stale, "busy": "有计算任务正在运行" if busy else None,
        "fields_by_pkg": fields_by_pkg, "current_pkgs": [p["label"] for p in cur],
        "api_base": f"http://127.0.0.1:{app.settings.port}/api/v1", "api_token": request.app.state.api_token,
        "token_path": str(app.settings.api_token_path), "filtered": any(f.values()),
        "evidence_states": ADJ.S.EVIDENCE_STATES,
    })


def _codes(form: Any) -> list[str]:
    out: list[str] = []
    for v in form.getlist("codes"):
        out += [x.strip() for x in str(v).replace(",", " ").split() if x.strip()]
    return list(dict.fromkeys(out))


def _refused(exc: Exception) -> JSONResponse:
    return C.fail(str(exc), status=409 if isinstance(exc, jobs.JobBusy) else 200)


@router.post("/review/decide")
async def decide(request: Request) -> JSONResponse:
    app = C.svc(request)
    form = await request.form()
    decision = str(form.get("decision") or "")
    note = str(form.get("note") or "").strip()
    if form.get("scope") == "filtered":
        f = {k: str(form.get(k) or "").strip() for k in FILTERS}
        with app.engine.begin() as conn:
            codes = [r["code"] for r in _select(conn, app.category_id(), f, [ADJ.PENDING])]
    else:
        codes = _codes(form)
    if not codes:
        return C.fail("请先勾选要处理的调整")
    values = None
    if form.get("value_edit") is not None and len(codes) == 1:
        values = {codes[0]: str(form.get("value_edit") or "")}
    try:
        res = SV.adjust_decide(app, codes, decision, values=values, note=note)
    except (ADJ.AdjustError, jobs.JobBusy) as exc:
        if values and isinstance(exc, ADJ.AdjustError):
            return C.fail(str(exc), fields={"value_edit": str(exc)})
        return _refused(exc)
    if not res["done"]:
        return C.fail("所选调整已处理过，没有新的变动", status=409)
    verb = "确认" if decision == "confirm" else "驳回"
    toast = f"已{verb} {len(res['done'])} 条" + ("（按改后的值）" if values else "")
    if decision == "confirm":
        toast += " · 数据体检已按新值刷新，成败、信号和回测已标为需重算"
    if res["skipped"]:
        toast += f"（{len(res['skipped'])} 条已处理过，跳过）"
    return C.ok(redirect=str(form.get("next") or "/review"), toast=toast)


@router.post("/review/revoke")
async def revoke(request: Request) -> JSONResponse:
    app = C.svc(request)
    form = await request.form()
    codes = _codes(form)
    if not codes:
        return C.fail("请先选择要撤销的调整")
    try:
        res = SV.adjust_revoke(app, codes, note=str(form.get("note") or "").strip())
    except (ADJ.AdjustError, jobs.JobBusy) as exc:
        return _refused(exc)
    if not res["done"]:
        return C.fail("所选调整不是已确认状态，没有撤销", status=409)
    return C.ok(redirect=str(form.get("next") or "/review?tab=confirmed"),
                toast=f"已撤销 {len(res['done'])} 条 · 这些值恢复为数据包原值，结果已标为需重算")


@router.post("/review/propose")
async def propose(request: Request) -> JSONResponse:
    app = C.svc(request)
    form = await request.form()
    item = {k: str(form.get(k) or "").strip() for k in ("file", "child", "month", "field", "value", "reason")}
    try:
        pkg = SV.resolve_package(app, str(form.get("package") or "") or None)
        res = SV.adjust_propose(app, pkg["id"], [item], "手工")
    except ADJ.AdjustError as exc:
        return C.fail(str(exc))
    if res["errors"]:
        err = res["errors"][0]["error"]
        key = "child" if "子 ASIN" in err else "field" if "字段" in err else "month" if "月" in err else "value"
        return C.fail(err, fields={key: err})
    return C.ok(redirect="/review", toast=f"已记录 {res['created'][0]}，待审核")
