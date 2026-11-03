"""费用闸门的任务接口（API-F16-03）。所有花钱任务都经此：估算 → 弹窗确认 → 执行；可查进度、暂停、续跑。"""
import json

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse

from .. import costgate
from ..auth import any_user, operator_only
from ..config import SERVICES
from ..db import session
from ..models import Job

router = APIRouter()


def _job_json(j: Job) -> dict:
    est = dict(j.estimate or {})
    usage = []
    for svc in (est.get("services") or {est.get("service"): est}):
        if not svc:
            continue
        cap, unit = costgate.budget(svc)
        amt, qty = costgate.spent(svc)
        usage.append(dict(service=svc, name=SERVICES.get(svc, svc), cap=cap, unit=unit, spent_usd=amt, spent_qty=qty))
    return dict(id=j.id, kind=j.kind, label=costgate.KINDS[j.kind].label if j.kind in costgate.KINDS else j.kind,
                month=j.month, target=j.target, status=j.status, estimate=est, progress=j.progress or {},
                error=j.error, usage=usage)


@router.post("/jobs/estimate")
def estimate(request: Request, kind: str = Form(...), month: str = Form(""), target: str = Form(""),
             params: str = Form("{}"), user=operator_only):
    if kind not in costgate.KINDS:
        raise HTTPException(404, "未知任务类型")
    try:
        j = costgate.estimate(kind, json.loads(params or "{}"), user.id, month=month, target=target)
    except Exception as e:  # 估算本身失败（如未连接）要让页面看到原因
        return JSONResponse({"error": str(e)}, status_code=400)
    return _job_json(j)


@router.post("/jobs/{job_id}/confirm")
def confirm(job_id: int, user=operator_only):
    costgate.confirm(job_id, user.id)
    return get(job_id)


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: int, user=operator_only):
    costgate.cancel(job_id)
    return get(job_id)


@router.post("/jobs/{job_id}/pause")
def pause(job_id: int, user=operator_only):
    costgate.pause(job_id)
    return get(job_id)


@router.get("/jobs/{job_id}")
def get(job_id: int, user=any_user):
    with session() as s:
        j = s.get(Job, job_id)
        if not j:
            raise HTTPException(404, "任务不存在")
        return _job_json(j)
