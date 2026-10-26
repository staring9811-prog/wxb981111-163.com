"""Step timing (F14: REQ-F14-01, AC-F14-01, AC-F14-02, DEC-031)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Connection

from oppo import db as D

STEPS = ("导入校验", "字段确认", "数据体检", "SPU 审核", "计算", "回测", "导出")
MONTHLY_TARGET_MIN = 240
FIRST_RUN_TARGET_DAYS = 5


def _update_month(conn: Connection, package_id: int | None, category_id: int) -> str | None:
    from oppo.core import packages as PK

    pkg = PK.get(conn, package_id) if package_id else None
    if pkg is None:
        pkg = PK.current_package(conn, category_id, "history") or PK.current_package(conn, category_id, "cross")
    if pkg and pkg.get("months_to"):
        return PK.add_months(pkg["months_to"], 1)
    return None


def record_step(conn: Connection, category_id: int, step: str, started: str, ended: str | None, operator: str,
                result: str = "", link: str = "", package_id: int | None = None, month: str | None = None) -> None:
    conn.execute(D.run_step.insert().values(
        category_id=category_id, step=step, month=month or _update_month(conn, package_id, category_id),
        started_at=started, ended_at=ended, result=result, link=link, created_by=operator,
        created_at=ended or started))


def workdays_between(a: date, b: date) -> int:
    """Working days (Mon–Fri) from a to b inclusive."""
    if b < a:
        return 0
    n, d = 0, a
    while d <= b:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def steps(conn: Connection, category_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(select(D.run_step).where(D.run_step.c.category_id == category_id)
                        .order_by(D.run_step.c.started_at, D.run_step.c.id)).mappings().all()
    return [dict(r) for r in rows]


def summary(conn: Connection, category_id: int) -> dict[str, Any]:
    all_steps = steps(conn, category_id)
    imports = [s for s in all_steps if s["step"] == "导入校验"]
    backtests = [s for s in all_steps if s["step"] == "回测" and s["ended_at"]]
    first: dict[str, Any] | None = None
    if imports:
        a = _dt(imports[0]["started_at"])
        done = [b for b in backtests if _dt(b["ended_at"]) >= a]
        if done:
            b = _dt(done[0]["ended_at"])
            days = workdays_between(a.date(), b.date())
            first = {"start": a, "end": b, "days": days, "ok": days <= FIRST_RUN_TARGET_DAYS, "in_progress": False}
        else:
            first = {"start": a, "end": None, "days": None, "ok": None, "in_progress": True}
    months: dict[str, dict[str, Any]] = {}
    for s in all_steps:
        m = s["month"]
        if not m:
            continue
        rec = months.setdefault(m, {"month": m, "import": None, "export": None, "steps": []})
        rec["steps"].append(s)
        if s["step"] == "导入校验" and rec["import"] is None:
            rec["import"] = _dt(s["started_at"])
        if s["step"] == "导出" and s["ended_at"]:
            rec["export"] = _dt(s["ended_at"])  # last export wins (DEC-031)
    monthly = []
    for m in sorted(months):
        rec = months[m]
        if rec["import"] and rec["export"] and rec["export"] >= rec["import"]:
            mins = int((rec["export"] - rec["import"]).total_seconds() // 60)
            rec.update(minutes=mins, ok=mins <= MONTHLY_TARGET_MIN, in_progress=False,
                       over=max(0, mins - MONTHLY_TARGET_MIN))
        else:
            rec.update(minutes=None, ok=None, in_progress=True, over=0)
        monthly.append(rec)
    return {"first_run": first, "monthly": monthly}


def fmt_minutes(mins: int | None) -> str:
    if mins is None:
        return "无数据"
    h, m = divmod(mins, 60)
    return f"{h} 小时 {m} 分" if h else f"{m} 分钟"
