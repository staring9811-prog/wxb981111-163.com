"""Local JSON API for Codex and other tools (bearer token from the data folder's api_token.txt).

Tools read package rows and propose adjustments; a proposal waits as 待审核 until a person confirms, edits or
rejects it on the 数据审核 page or with `oppo adjust`. There is deliberately no endpoint that confirms.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from oppo import service as SV
from oppo.core import adjust as ADJ
from oppo.core import categories as CAT
from oppo.core import packages as PK
from oppo.web import common as C

router = APIRouter(prefix="/api/v1")


def _err(msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": msg}, status_code=status)


def _pkg_out(p: dict[str, Any], current: set[int]) -> dict[str, Any]:
    return {"package": p["label"], "id": p["id"], "kind": "截面" if p["kind"] == "cross" else "历史",
            "months": [p.get("months_from"), p.get("months_to")], "conclusion": p.get("conclusion"),
            "current": p["id"] in current}


async def _json(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError as exc:
        raise ADJ.AdjustError("请求体不是有效的 JSON") from exc
    if not isinstance(body, dict):
        raise ADJ.AdjustError("请求体应是 JSON 对象")
    return body


@router.get("/info")
def info(request: Request) -> JSONResponse:
    app = C.svc(request)
    cid = app.category_id()
    with app.engine.begin() as conn:
        cur = {p["id"] for p in (PK.current_package(conn, cid, m) for m in ("history", "cross")) if p}
        pkgs = PK.list_packages(conn, cid)
        cfg = CAT.current_version(conn, cid)["config"]
        files = {p["label"]: ADJ.files_of(conn, p["id"]) for p in pkgs if p["id"] in cur}
        counts = ADJ.counts(conn, cid)
    return JSONResponse({
        "ok": True, "category": cfg.get("name"), "operator": app.operator,
        "packages": [_pkg_out(p, cur) for p in pkgs],
        "adjustable_fields": files, "evidence_states": list(ADJ.S.EVIDENCE_STATES),
        "adjustments": counts,
        "notes": ["导入的数据包本身不会被修改；提交的调整为“待审核”，由人在“数据审核”页确认、改值或驳回后才生效。",
                  "C1/S1、C3/S3 的调整可带 month（YYYYMM）；不带 month 时作用于该子体的所有月份。",
                  "C4 的字段是属性维度名（如 形态）或“维度+证据状态”（如 形态证据状态）。",
                  "value 传空字符串表示把该值清空。"],
    })


@router.get("/packages/{ref}/rows")
def rows(request: Request, ref: str, file: str, child: str | None = None, month: str | None = None,
         limit: int = 100, offset: int = 0) -> JSONResponse:
    app = C.svc(request)
    filters: dict[str, str] = {}
    for f in request.query_params.getlist("filter"):
        if ":" not in f:
            return _err("filter 的格式是 字段:值，例如 filter=形态证据状态:信息不足")
        k, v = f.split(":", 1)
        filters[k.strip()] = v.strip()
    try:
        pkg = SV.resolve_package(app, ref)
        with app.engine.begin() as conn:
            out = ADJ.effective_rows(conn, pkg["id"], file.strip().upper(), child=child, month=month,
                                     filters=filters, limit=limit, offset=max(0, offset))
    except ADJ.AdjustError as exc:
        return _err(str(exc))
    return JSONResponse({"ok": True, "package": pkg["label"], **out})


@router.post("/packages/{ref}/adjustments")
async def propose(request: Request, ref: str) -> JSONResponse:
    app = C.svc(request)
    try:
        body = await _json(request)
        items = body.get("items")
        if not isinstance(items, list):
            return _err("items 应是数组：[{file, child, month?, field, value, reason?}]")
        pkg = SV.resolve_package(app, ref)
        res = SV.adjust_propose(app, pkg["id"], [i if isinstance(i, dict) else {} for i in items],
                                str(body.get("source") or "Codex"))
    except ADJ.AdjustError as exc:
        return _err(str(exc))
    return JSONResponse({"ok": True, "package": pkg["label"], "status": ADJ.PENDING, **res,
                         "review_url": "http://127.0.0.1:%d/review" % app.settings.port})


@router.get("/adjustments")
def adjustments(request: Request, package: str | None = None, status: str | None = None, file: str | None = None,
                field: str | None = None, source: str | None = None, child: str | None = None,
                batch: str | None = None, limit: int = 200, offset: int = 0) -> JSONResponse:
    app = C.svc(request)
    if status and status not in ADJ.STATUSES:
        return _err(f"status 只能是 {' / '.join(ADJ.STATUSES)}")
    try:
        pid = SV.resolve_package(app, package)["id"] if package else None
    except ADJ.AdjustError as exc:
        return _err(str(exc))
    cid = app.category_id()
    limit = max(1, min(limit, 2000))
    with app.engine.begin() as conn:
        labels = {p["id"]: p["label"] for p in PK.list_packages(conn, cid)}
        got = ADJ.listing(conn, cid, package_id=pid, status=status, file_code=(file or "").upper() or None,
                          field=field, source=source, child=child, batch=batch, limit=limit, offset=max(0, offset))
    keys = ("code", "batch", "file_code", "child", "month", "field", "old_value", "proposed_value", "final_value",
            "reason", "source", "status", "decided_by", "decided_at", "decision_note", "created_at")
    return JSONResponse({"ok": True, "items": [{"package": labels.get(r["package_id"]), **{k: r[k] for k in keys}}
                                               for r in got]})


@router.post("/adjustments/withdraw")
async def withdraw(request: Request) -> JSONResponse:
    app = C.svc(request)
    try:
        body = await _json(request)
    except ADJ.AdjustError as exc:
        return _err(str(exc))
    codes = [str(c) for c in body.get("codes") or []]
    if not codes:
        return _err("codes 应是要撤回的调整编号数组，如 [\"A-00001\"]")
    return JSONResponse({"ok": True, **SV.adjust_withdraw(app, codes)})
