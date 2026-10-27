"""Single background task queue (DEC-010) and "需重算" state (DEC-016).

Only one computation runs at a time. Work runs inside one database transaction: a failure
rolls everything back, so the previous results stay intact (RULE-09).
"""

from __future__ import annotations

import os
import threading
import traceback
from typing import Any, Callable

from sqlalchemy import select, text
from sqlalchemy.engine import Connection, Engine

from oppo import clock
from oppo import db as D

JOB_LABELS = {"compute": "计算（成败与信号）", "backtest": "回测", "recompute": "全部重算", "export": "导出",
              "import": "导入校验", "model": "变量模型"}

_lock = threading.Lock()
_progress: dict[int, dict[str, Any]] = {}


class JobBusy(Exception):
    pass


class InjectedFailure(RuntimeError):
    pass


def maybe_fail(point: str) -> None:
    """Test hook for RULE-09: OPPO_FAIL_AT=<point> makes the job fail at that step."""
    if os.environ.get("OPPO_FAIL_AT") == point:
        raise InjectedFailure(f"注入的异常：在“{point}”步骤中断")


def running(conn: Connection) -> dict[str, Any] | None:
    row = conn.execute(select(D.job).where(D.job.c.status == "running").order_by(D.job.c.id.desc())).mappings().first()
    return dict(row) if row else None


def latest(conn: Connection, kind: str | None = None) -> dict[str, Any] | None:
    q = select(D.job).order_by(D.job.c.id.desc()).limit(1)
    if kind:
        q = select(D.job).where(D.job.c.kind == kind).order_by(D.job.c.id.desc()).limit(1)
    row = conn.execute(q).mappings().first()
    return dict(row) if row else None


def progress(job_id: int) -> dict[str, Any]:
    return dict(_progress.get(job_id, {}))


def _start(engine: Engine, category_id: int, kind: str, operator: str) -> int:
    with _lock:
        with engine.begin() as conn:
            cur = running(conn)
            if cur:
                raise JobBusy(f"{JOB_LABELS.get(cur['kind'], cur['kind'])}正在运行，完成后再试")
            jid = conn.execute(D.job.insert().values(
                category_id=category_id, kind=kind, status="running", step="排队", progress=0.0,
                started_at=clock.now_iso(), created_by=operator, created_at=clock.now_iso(),
            )).inserted_primary_key[0]
    _progress[jid] = {"step": "开始", "progress": 0.0}
    return int(jid)


def _finish(engine: Engine, jid: int, status: str, error: str | None, result: Any) -> None:
    with engine.begin() as conn:
        conn.execute(D.job.update().where(D.job.c.id == jid).values(
            status=status, error=error, ended_at=clock.now_iso(), progress=1.0 if status == "success" else None,
            step=_progress.get(jid, {}).get("step"), result_json=D.dumps(result) if result is not None else None))
    _progress.pop(jid, None)


def run(engine: Engine, category_id: int, kind: str, operator: str,
        work: Callable[[Connection, Callable[[str, float], None]], Any], background: bool = False,
        after: Callable[[Any], Any] | None = None) -> int:
    """Run work(conn, report) as job `kind`. Raises JobBusy if another job is running.

    `after(result)` runs once the work's transaction has committed (e.g. the backup after an export must
    see the committed export); its return value, if not None, replaces the job result."""
    jid = _start(engine, category_id, kind, operator)

    def report(step: str, frac: float) -> None:
        _progress[jid] = {"step": step, "progress": frac}

    def body() -> None:
        try:
            with engine.begin() as conn:
                result = work(conn, report)
            if after is not None:
                replaced = after(result)
                result = result if replaced is None else replaced
        except Exception as exc:  # noqa: BLE001 - recorded on the job and re-raised for CLI
            msg = str(exc) or exc.__class__.__name__
            _finish(engine, jid, "failed", msg, {"trace": traceback.format_exc(limit=4)})
            if not background:
                raise
            return
        _finish(engine, jid, "success", None, result if isinstance(result, (dict, list, str, int)) else None)

    if background:
        threading.Thread(target=body, name=f"oppo-job-{jid}", daemon=True).start()
    else:
        body()
    return jid


def recover_stale(engine: Engine) -> None:
    """A process restart leaves no live worker: mark orphaned running jobs as failed."""
    with engine.begin() as conn:
        conn.execute(text("UPDATE job SET status='failed', error='程序重启，任务中断', ended_at=:t WHERE status='running'"),
                     {"t": clock.now_iso()})
