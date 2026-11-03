"""费用闸门（技术方案 §4，AC-F16-06～08，NFR-011）。

所有外部按量调用都必须：
1. 先 `estimate()` 建任务并给出预计调用量 / 费用区间 / 耗时；
2. wen 在 CMP-F16-01 弹窗确认后 `confirm()` 才执行；
3. 执行中每笔调用前 `ctx.allow()` 检查当月上限，调用后 `ctx.charge()` 记账；到上限即停（CapReached），已采数据保留。

模块用 `register(kind, estimator, runner)` 注册任务类型：
- estimator(params: dict) -> dict(service=..., calls=int, usd_lo=float, usd_hi=float, minutes=float, note=str, services={...可选多服务})
- runner(job_ctx: JobCtx) -> None
"""
import os
import threading
import traceback
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import func, select

from .db import session
from .models import Audit, Budget, CostRecord, Job, Shard, now


class CapReached(Exception):
    def __init__(self, service, spent, cap, unit):
        self.service, self.spent, self.cap, self.unit = service, spent, cap, unit
        super().__init__(f"{service} 本月已达上限（{spent:g} / {cap:g} {unit}）")


class Paused(Exception):
    pass


@dataclass
class Kind:
    estimator: Callable
    runner: Callable
    label: str


KINDS: dict[str, Kind] = {}


def register(kind: str, label: str, estimator: Callable, runner: Callable):
    KINDS[kind] = Kind(estimator, runner, label)


def month_key(dt=None) -> str:
    return (dt or now()).strftime("%Y-%m")


def spent(service: str, month: str | None = None) -> tuple[float, float]:
    """当月 (金额美元, 数量)。"""
    month = month or month_key()
    with session() as s:
        amt, qty = s.execute(select(func.coalesce(func.sum(CostRecord.amount), 0), func.coalesce(func.sum(CostRecord.qty), 0))
                             .where(CostRecord.service == service, CostRecord.month == month)).one()
        return float(amt), float(qty)


def budget(service: str):
    with session() as s:
        b = s.get(Budget, service)
        return (b.cap, b.unit) if b else (None, None)


def would_exceed(service: str, amount: float = 0.0, qty: float = 0.0) -> bool:
    cap, unit = budget(service)
    if cap is None:
        return False
    amt, q = spent(service)
    used, add = (amt, amount) if unit == "usd" else (q, qty)
    return used + add > cap + 1e-9


def check(service: str, amount: float = 0.0, qty: float = 0.0):
    if would_exceed(service, amount, qty):
        cap, unit = budget(service)
        amt, q = spent(service)
        raise CapReached(service, amt if unit == "usd" else q, cap, unit)


def estimate(kind: str, params: dict, user_id: int | None, month: str = "", target: str = "") -> Job:
    """建任务并估算。同一类型同一月份同一对象已有进行中任务时返回该任务（互斥）。"""
    k = KINDS[kind]
    with session() as s:
        busy = s.scalar(select(Job).where(Job.kind == kind, Job.month == month, Job.target == target,
                                          Job.status.in_(["running", "queued"])))
        if busy:
            return busy
        est = k.estimator(dict(params, month=month, target=target))
        # 叠加上限预警：预计费用上沿超过剩余额度
        warn = []
        for svc, e in (est.get("services") or {est.get("service"): est}).items():
            if not svc:
                continue
            cap, unit = budget(svc)
            if cap is not None:
                amt, q = spent(svc)
                need = e.get("usd_hi", 0) if unit == "usd" else e.get("calls", 0)
                used = amt if unit == "usd" else q
                if used + need > cap:
                    warn.append(f"{svc}：预计超过本月上限（已用 {used:g} / {cap:g} {unit}），到上限会自动停止，已采数据保留")
        est["warnings"] = warn
        j = Job(kind=kind, month=month, target=target, status="estimated", estimate=est, params=params, created_by=user_id)
        s.add(j)
        s.flush()
        s.expunge(j)
        return j


def cancel(job_id: int):
    with session() as s:
        j = s.get(Job, job_id)
        if j and j.status == "estimated":
            j.status = "cancelled"


_lock = threading.Lock()


def confirm(job_id: int, user_id: int | None):
    with session() as s:
        j = s.get(Job, job_id)
        if not j or j.status not in ("estimated", "paused", "stopped_cap", "failed"):
            return j
        j.status = "queued"
        j.confirmed_at = now()
        j.error = ""
        s.add(Audit(kind="spend", content=f"确认花钱任务：{KINDS[j.kind].label}（{j.month or j.target}），预计 ${j.estimate.get('usd_lo', 0):g}–{j.estimate.get('usd_hi', 0):g}", user_id=user_id))
    _dispatch(job_id)
    return j


def resume(job_id: int, user_id: int | None):
    """断点续跑：重新估算剩余部分后需再次确认（由页面走 estimate→confirm）；这里直接续跑已确认任务。"""
    return confirm(job_id, user_id)


def pause(job_id: int):
    with session() as s:
        j = s.get(Job, job_id)
        if j and j.status in ("running", "queued"):
            j.progress = dict(j.progress or {}, pause_requested=True)


def _dispatch(job_id: int):
    if os.environ.get("PDT_SYNC_JOBS") == "1":
        _run(job_id)
    else:
        threading.Thread(target=_run, args=(job_id,), daemon=True).start()


class JobCtx:
    def __init__(self, job: Job):
        self.job = job
        self.id = job.id
        self.kind = job.kind
        self.month = job.month
        self.params = job.params or {}
        self.target = job.target

    # 记账
    def allow(self, service: str, amount: float = 0.0, qty: float = 0.0):
        check(service, amount, qty)
        self._check_pause()

    def charge(self, service: str, qty: float, amount: float, task: str = "", source: str = ""):
        with session() as s:
            s.add(CostRecord(month=month_key(), service=service, job_id=self.id,
                             task=task or KINDS[self.kind].label, qty=qty, amount=amount, source=source))

    # 分片
    def shard_done(self, key: str) -> bool:
        with session() as s:
            return s.scalar(select(Shard.id).where(Shard.kind == self.kind, Shard.month == self.month, Shard.key == key)) is not None

    def mark_shard(self, key: str, payload_path: str = ""):
        with session() as s:
            s.add(Shard(kind=self.kind, month=self.month, key=key, job_id=self.id, payload_path=payload_path))

    # 进度
    def progress(self, **kw):
        with session() as s:
            j = s.get(Job, self.id)
            j.progress = dict(j.progress or {}, **kw)

    def _check_pause(self):
        with session() as s:
            j = s.get(Job, self.id)
            if (j.progress or {}).get("pause_requested"):
                raise Paused()


def _run(job_id: int):
    with _lock:  # 单 worker：同一时间只跑一个重任务
        with session() as s:
            j = s.get(Job, job_id)
            if j.status != "queued":
                return
            j.status = "running"
            j.progress = {k: v for k, v in (j.progress or {}).items() if k != "pause_requested"}
            s.flush()
            s.expunge(j)
        ctx = JobCtx(j)
        status, err = "done", ""
        try:
            KINDS[j.kind].runner(ctx)
        except CapReached as e:
            status, err = "stopped_cap", str(e)
        except Paused:
            status, err = "paused", "已暂停，已完成部分保留"
        except Exception as e:  # 任务失败要可见，不吞掉
            status, err = "failed", f"{type(e).__name__}: {e}"
            traceback.print_exc()
        with session() as s:
            jj = s.get(Job, job_id)
            if status == "paused" and (jj.progress or {}).get("abandoned"):  # 运行中点“放弃本批”：停下后记为已取消（见 ingest.abandon_pull）
                status, err = "cancelled", (jj.progress or {}).get("abandon_note") or "已放弃本批"
            jj.status = status
            jj.error = err
            jj.finished_at = now()
