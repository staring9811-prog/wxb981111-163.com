"""审批（PAGE-F25-01）与策略库（PAGE-F25-02）。API-F25-01 / API-F25-02。"""
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from ..auth import any_user, approver_only, operator_only, roles
from ..config import CHANNEL_NAMES
from ..db import session
from ..models import Card, Strategy
from ..core import approval as apcore
from ..core import card as cardcore
from .ui import redirect, render

router = APIRouter()
operator_or_approver = roles("operator", "approver")


def _json(request: Request) -> bool:
    return request.headers.get("accept", "").startswith("application/json")


def _summary(c: Card) -> dict:
    n = c.numbers or {}
    sc = (n.get("bet") or {}).get("score") or {}
    pr = (n.get("bet") or {}).get("prob") or {}
    verdicts = " · ".join(f"{ch['name']} {ch['verdict']}" for ch in n.get("channels", []) if ch["verdict"] in ("上", "观察"))
    return dict(verdicts=verdicts or "—", grade=sc.get("grade"), lo=sc.get("lo"), hi=sc.get("hi"),
                raw=(pr.get("raw") or [None])[0], adj=(pr.get("adj") or [None])[0], stops=c.narrative.get("stop", []), stop_defs={x["kind"]: x for x in n.get("stop", [])})


@router.get("/approvals")
def approvals(request: Request, user=operator_or_approver):
    with session() as s:
        todo = [apcore.describe(s, a) for a in apcore.pending(s)]
        done = [apcore.describe(s, a) for a in apcore.done(s)]
        for d in todo:
            if d["type"] == "card":
                d["sum"] = _summary(d["card"])
                pv = cardcore.profit_view(s, d["card"])
                d["am_profit"] = next((r for r in (pv or {}).get("rows", []) if r["channel"].startswith("Amazon") and r.get("profit") is not None), None)
                d["launch"] = (d["card"].narrative or {}).get("launch_month")
    return render(request, "approvals.html", "PAGE-F25-01", "审批", todo=todo, done=done,
                  is_approver=user.role == "approver", now_txt=datetime.now().strftime("%Y-%m-%d %H:%M"))


@router.post("/approvals/{approval_id}/decide")
async def approvals_decide(request: Request, approval_id: int, user=approver_only):
    f = await request.form()
    try:
        res = apcore.decide(approval_id, f.get("decision", ""), f.get("comment", ""), user.id, request.client.host if request.client else "")
    except (apcore.ApprovalError, cardcore.IllegalTransition) as e:
        if _json(request):
            return JSONResponse({"detail": str(e)}, status_code=400)
        return redirect("/approvals", str(e), "error")
    msg = "已记录：" + apcore.DECISIONS[f["decision"]] + (f"，已登记台账 {res['ledger_code']}" if res.get("ledger_code") else "")
    return {"ok": True, **res} if _json(request) else redirect("/approvals", msg)


# ---------------------------------------------------------------- 策略库
@router.get("/strategies")
def strategies(request: Request, user=any_user):
    apcore.seed_strategies()
    with session() as s:
        items = []
        for st in s.scalars(select(Strategy).order_by(Strategy.updated_at.desc(), Strategy.id.desc())):
            pend = apcore.pending_request(s, st.id)
            items.append(dict(st=st, pending=pend, versions=apcore.versions(s, st.id)))
        counts = {k: sum(1 for i in items if i["st"].status == k) for k in apcore.STRAT_STATUS}
    return render(request, "strategies.html", "PAGE-F25-02", "策略库", items=items, counts=counts, kinds=apcore.STRAT_KINDS,
                  statuses=apcore.STRAT_STATUS, is_op=user.role == "operator", channel_names=CHANNEL_NAMES)


@router.post("/strategies")
async def strategies_create(request: Request, user=operator_only):
    f = await request.form()
    try:
        apcore.create_strategy(f.get("title", ""), f.get("kind", ""), f.get("status", ""), f.get("basis", ""), f.get("body", ""), user.id)
    except apcore.ApprovalError as e:
        return JSONResponse({"detail": str(e)}, status_code=400) if _json(request) else redirect("/strategies", str(e), "error")
    return {"ok": True} if _json(request) else redirect("/strategies", "已新增结论（v1）")


@router.post("/strategies/{sid}")
async def strategies_update(request: Request, sid: int, user=operator_only):
    f = await request.form()
    try:
        v = apcore.update_strategy(sid, f.get("title"), f.get("status", ""), f.get("basis"), f.get("body"), f.get("note", ""), user.id)
    except apcore.ApprovalError as e:
        return JSONResponse({"detail": str(e)}, status_code=400) if _json(request) else redirect("/strategies", str(e), "error")
    return {"ok": True, "version": v} if _json(request) else redirect("/strategies", f"已保存为新版本 v{v}，旧版本保留在版本历史")


@router.post("/strategies/{sid}/apply-verified")
async def strategies_apply(request: Request, sid: int, user=operator_only):
    f = await request.form()
    try:
        aid = apcore.apply_verified(sid, f.get("basis", ""), user.id)
    except apcore.ApprovalError as e:
        return JSONResponse({"detail": str(e)}, status_code=400) if _json(request) else redirect("/strategies", str(e), "error")
    return {"ok": True, "approval_id": aid} if _json(request) else redirect("/strategies", "已提交申请，待老板审批；批准前状态不变")


@router.get("/strategies/{sid}/versions")
def strategies_versions(sid: int, user=any_user):
    with session() as s:
        if not s.get(Strategy, sid):
            raise HTTPException(404, "条目不存在")
        return {"versions": [dict(v, at=v["at"].strftime("%Y-%m-%d %H:%M")) for v in apcore.versions(s, sid)]}
