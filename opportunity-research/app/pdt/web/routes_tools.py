"""工具：评论 VP 追踪（PAGE-F23-01，API-F23-01）与利润测算（PAGE-F24-01，API-F24-01 / 02）。"""
import json
from datetime import timezone
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select

from .. import costgate
from ..auth import any_user, operator_only
from ..db import session
from ..models import Card, Job, ProfitPlan, Secret, User, now
from ..core import card as cardcore
from ..core import vp as vpcore
from .ui import redirect, render

router = APIRouter()


def _json(request: Request) -> bool:
    return request.headers.get("accept", "").startswith("application/json")


# ================================================================ 评论 VP 追踪
def _svc(slot):
    with session() as s:
        r = s.get(Secret, slot)
        return dict(ok=r is not None, last4=r.last4 if r else "")


@router.get("/tools/vp")
def vp_page(request: Request, name: str = "", user=operator_only):
    names = vpcore.projects()
    if not names:
        return render(request, "tools_vp.html", "PAGE-F23-01", "评论 VP 追踪", names=[], name="", cfg=None)
    name = name if name in names else names[0]
    cfg = vpcore.load(name)
    st = vpcore.state(name)
    with session() as s:
        jobs = {k: s.scalar(select(Job).where(Job.kind == k, Job.target == f"vp:{name}").order_by(Job.id.desc()).limit(1))
                for k in ("vp_lists", "vp_collect")}
        jobs = {k: (dict(id=j.id, status=j.status, error=j.error) if j else None) for k, j in jobs.items()}
    usage = {}
    for svc in ("brightdata", "apify"):
        cap, unit = costgate.budget(svc)
        amt, qty = costgate.spent(svc)
        usage[svc] = dict(cap=cap, unit=unit, spent=amt if unit != "calls" else qty)
    return render(request, "tools_vp.html", "PAGE-F23-01", "评论 VP 追踪", names=names, name=name, cfg=cfg, st=st, jobs=jobs,
                  usage=usage, bd=_svc("brightdata"), ap=_svc("apify"), monthly=vpcore.monthly(name),
                  month_short=vpcore.month_short, plats=vpcore.PLATS, cfg_json=json.dumps(cfg, ensure_ascii=False))


@router.post("/tools/vp/project")
async def vp_save(request: Request, user=operator_only):
    f = await request.form()
    try:
        name = vpcore.save(json.loads(f.get("cfg", "{}")))
    except (vpcore.VpError, ValueError) as e:
        return JSONResponse({"detail": str(e)}, status_code=400) if _json(request) else redirect("/tools/vp", str(e), "error")
    return {"ok": True, "name": name} if _json(request) else redirect(f"/tools/vp?name={quote(name)}", f"设置已保存：{name}")


@router.post("/tools/vp/copy")
async def vp_copy(request: Request, user=operator_only):
    f = await request.form()
    try:
        name = vpcore.copy_as(f.get("src", ""), f.get("new", ""))
    except vpcore.VpError as e:
        return JSONResponse({"detail": str(e)}, status_code=400) if _json(request) else redirect("/tools/vp", str(e), "error")
    return {"ok": True, "name": name} if _json(request) else redirect(f"/tools/vp?name={quote(name)}", f"已复制为新项目：{name}")


@router.post("/tools/vp/estimate")
def vp_estimate(request: Request, name: str, user=operator_only):
    est = vpcore.run_estimate(name)
    return est if _json(request) else redirect(f"/tools/vp?name={quote(name)}", f"评估完成：约 ${est['合计']['总费用']}，约 {est['合计']['预计耗时分钟']} 分钟")


@router.post("/tools/vp/export")
def vp_export(request: Request, name: str, user=operator_only):
    files = vpcore.run_export(name)
    return {"files": files} if _json(request) else redirect(f"/tools/vp?name={quote(name)}", "已导出：" + "、".join(files))


@router.get("/tools/vp/download")
def vp_download(name: str, file: str, user=operator_only):
    rc = vpcore.rk_ctx(name)
    import os
    p = rc.path("exports", os.path.basename(file))
    if not os.path.exists(p):
        raise HTTPException(404, "文件不存在")
    return FileResponse(p, filename=os.path.basename(p))


@router.get("/tools/vp/state")
def vp_state(name: str, user=operator_only):
    return vpcore.state(name)


# ================================================================ 利润测算
def _ms(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _item(s, p: ProfitPlan) -> dict:
    d = p.data or {}
    prods = d.get("products") or []
    u = s.get(User, p.updated_by) if p.updated_by else None
    c = s.get(Card, p.card_id) if p.card_id else None
    return dict(id=p.id, name=p.name, savedAtMs=_ms(p.updated_at), savedAt=p.updated_at.replace(tzinfo=timezone.utc).isoformat(),
                renamedAtMs=d.get("renamedAtMs"), count=len(prods), names=[x.get("name", "") for x in prods][:20], products=prods,
                params=d.get("params") or {}, by=u.name if u else "", card_id=p.card_id, card_name=cardcore.card_name(c) if c else "",
                result=p.result or {})


def _check_result(res):
    if res in (None, {}):
        return None
    if not isinstance(res, dict) or not isinstance(res.get("rows"), list):
        raise HTTPException(400, "回写结果格式不对")
    return res


def _link(s, p: ProfitPlan, card_id: int, result: dict | None, user_id):
    c = s.get(Card, card_id)
    if not c:
        raise HTTPException(404, "决策卡不存在")
    p.card_id = card_id
    if result:
        p.result = result
    c.profit_plan_id = p.id
    cardcore.log(s, c.id, "profit", f"利润方案“{p.name}”回写“钱”一节" + ("（卡片已批准，快照不变）" if c.status in cardcore.LOCKED else ""), user_id)


@router.get("/tools/profit")
def profit_page(request: Request, card: int | None = None, plan: int | None = None, user=any_user):
    with session() as s:
        cobj = s.get(Card, card) if card else None
        p = None
        if plan:
            p = s.get(ProfitPlan, plan)
        elif cobj and cobj.profit_plan_id:
            p = s.get(ProfitPlan, cobj.profit_plan_id)
        elif not cobj:
            p = s.scalar(select(ProfitPlan).order_by(ProfitPlan.updated_at.desc()).limit(1))
        if p and p.card_id and not cobj:
            cobj = s.get(Card, p.card_id)
        item = _item(s, p) if p else None
        cinfo = None
        if cobj:
            narr = cobj.narrative or {}
            cinfo = dict(id=cobj.id, name=cardcore.card_name(cobj), size=cobj.frame.split(" · ")[0], value=cobj.value, price=narr.get("price"),
                         status=cobj.status, status_name=cardcore.STATUS_NAMES.get(cobj.status, ""), locked=cobj.status in cardcore.LOCKED)
    init = dict(params=item["params"], products=item["products"]) if item else None
    step = 4 if item else (2 if cinfo else None)
    pdt = dict(init=init, planId=item["id"] if item else None, planName=item["name"] if item else "", step=step,
               readonly=user.role != "operator", card=cinfo, linkProduct=(item or {}).get("result", {}).get("product") if item else None,
               savedAt=item["savedAt"] if item else None)
    return render(request, "tools_profit.html", "PAGE-F24-01", "利润测算", pdt=pdt, card=cinfo, plan=item, is_op=user.role == "operator")


@router.get("/tools/profit/plans")
def profit_plans(user=any_user):
    with session() as s:
        return {"items": [_item(s, p) for p in s.scalars(select(ProfitPlan).order_by(ProfitPlan.updated_at.desc(), ProfitPlan.id.desc()))]}


@router.get("/tools/profit/plans/{pid}")
def profit_plan(pid: int, user=any_user):
    with session() as s:
        p = s.get(ProfitPlan, pid)
        if not p:
            raise HTTPException(404, "方案不存在")
        return _item(s, p)


@router.post("/tools/profit/plans")
async def profit_create(request: Request, user=operator_only):
    b = await request.json()
    if not b.get("products"):
        raise HTTPException(400, "没有产品可以保存")
    with session() as s:
        p = ProfitPlan(name=(b.get("name") or "利润测算").strip()[:128], data=dict(version=1, params=b.get("params") or {}, products=b["products"]),
                       updated_by=user.id)
        s.add(p)
        s.flush()
        if b.get("card_id"):
            _link(s, p, int(b["card_id"]), _check_result(b.get("result")), user.id)
        return _item(s, p)


@router.post("/tools/profit/plans/{pid}")
async def profit_update(request: Request, pid: int, user=operator_only):
    b = await request.json()
    with session() as s:
        p = s.get(ProfitPlan, pid)
        if not p:
            raise HTTPException(404, "方案不存在")
        d = dict(p.data or {})
        if b.get("name") and b["name"] != p.name:
            p.name = b["name"].strip()[:128]
            d["renamedAtMs"] = _ms(now())
        if "products" in b:
            d["products"] = b["products"]
            p.updated_at = now()
        if "params" in b:
            d["params"] = b["params"]
            p.updated_at = now()
        p.data = d
        p.updated_by = user.id
        cid = b.get("card_id") or p.card_id
        if cid and (b.get("result") or b.get("card_id")):
            _link(s, p, int(cid), _check_result(b.get("result")), user.id)
        return _item(s, p)


@router.post("/tools/profit/plans/{pid}/delete")
def profit_delete(pid: int, user=operator_only):
    with session() as s:
        p = s.get(ProfitPlan, pid)
        if p:
            for c in s.scalars(select(Card).where(Card.profit_plan_id == pid)):
                if c.status not in cardcore.LOCKED:
                    c.profit_plan_id = None
            s.delete(p)
    return {"ok": True}


@router.post("/tools/profit/import")
async def profit_import(request: Request, file: UploadFile, user=operator_only):
    """导入原利润测算台导出的方案 .json（RA-108）：{version, name?, savedAt?, params, products}。"""
    try:
        d = json.loads((await file.read()).decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "文件格式不对：不是方案 .json") from None
    if not isinstance(d, dict) or not isinstance(d.get("products"), list):
        raise HTTPException(400, "文件格式不对：缺少 products")
    name = d.get("name") or (file.filename or "导入的方案").rsplit(".", 1)[0]
    with session() as s:
        p = ProfitPlan(name=name[:128], data=dict(version=d.get("version", 1), params=d.get("params") or {}, products=d["products"]), updated_by=user.id)
        s.add(p)
        s.flush()
        return _item(s, p)


@router.post("/tools/profit/{pid}/link/{card_id}")
async def profit_link(request: Request, pid: int, card_id: int, user=operator_only):
    """API-F24-02：方案关联决策卡并回写"钱"一节（各渠道售价、单件利润、利润率、保本价）。"""
    b = await request.json()
    with session() as s:
        p = s.get(ProfitPlan, pid)
        if not p:
            raise HTTPException(404, "方案不存在")
        _link(s, p, card_id, _check_result(b.get("result")), user.id)
        p.updated_at = now()
        return _item(s, p)

