"""Service layer shared by the web app and the command line (NFR-004: same functions, same results)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.engine import Engine

from oppo import clock
from oppo import db as D
from oppo import settings as S
from oppo.core import backtest as BT
from oppo.core import categories as CAT
from oppo.core import compute as CMP
from oppo.core import contract as CT
from oppo.core import jobs, runs
from oppo.core import packages as PK
from oppo.core import ranking as RK
from oppo.core import spu as SPU


@dataclass
class App:
    settings: S.Settings
    engine: Engine

    @property
    def operator(self) -> str:
        return self.settings.operator

    def category_id(self) -> int:
        with self.engine.begin() as conn:
            return CAT.current_category_id(conn)


_apps: dict[str, App] = {}


def open_app(settings: S.Settings | None = None) -> App:
    settings = settings or S.load()
    key = str(settings.data_dir.resolve())
    if key in _apps:
        return _apps[key]
    for d in (settings.data_dir, settings.packages_dir, settings.exports_dir, settings.logs_dir):
        d.mkdir(parents=True, exist_ok=True)
    engine = D.get_engine(settings.db_path)
    D.init_db(engine)
    with engine.begin() as conn:
        CAT.ensure_default(conn, settings.operator)
    jobs.recover_stale(engine)
    app = App(settings, engine)
    _apps[key] = app
    return app


def reset_cache() -> None:
    _apps.clear()
    D.dispose_all()


# ---- operations -----------------------------------------------------------------------------


def import_package(app: App, path: Path) -> PK.ImportResult:
    cid = app.category_id()
    with app.engine.begin() as conn:
        if jobs.running(conn):
            raise jobs.JobBusy("有计算任务正在运行，完成后再导入")
        return PK.import_package(conn, app.settings, cid, Path(path), app.operator)


def contract_confirm(app: App, keys: list[tuple[str, str]] | None = None, suggested_only: bool = False,
                     save: bool = True, note: str = "") -> dict[str, Any]:
    cid = app.category_id()
    started = clock.now_iso()
    with app.engine.begin() as conn:
        n = CT.batch_confirm(conn, cid, keys, suggested_only=suggested_only)
        no = None
        if save:
            cur = CT.current_version(conn, cid)
            pkg = PK.current_package(conn, cid, "history") or PK.current_package(conn, cid, "cross")
            if cur is not None and not CT.draft_changes(conn, cid):
                # nothing changed in this month's package: keep the current version, still record the step (F14)
                no = cur["version_no"]
                result = f"无变化，沿用 v{no}"
            else:
                no = CT.save_version(conn, cid, app.operator, note)
                result = f"保存为 v{no}"
                if pkg:
                    SPU.refresh_suggestions(conn, cid, pkg["id"], app.operator)
            runs.record_step(conn, cid, "字段确认", started, clock.now_iso(), app.operator,
                             result=result, link="/fields", package_id=pkg["id"] if pkg else None)
        return {"confirmed": n, "version": no}


def contract_save(app: App, note: str = "") -> int:
    cid = app.category_id()
    started = clock.now_iso()
    with app.engine.begin() as conn:
        no = CT.save_version(conn, cid, app.operator, note)
        for kind in ("history", "cross"):
            pkg = PK.current_package(conn, cid, kind)
            if pkg:
                SPU.refresh_suggestions(conn, cid, pkg["id"], app.operator)
        pkg = PK.current_package(conn, cid, "history") or PK.current_package(conn, cid, "cross")
        runs.record_step(conn, cid, "字段确认", started, clock.now_iso(), app.operator, result=f"保存为 v{no}",
                         link="/fields", package_id=pkg["id"] if pkg else None)
        return no


def merge_confirm_basis(app: App, basis: str) -> dict[str, int]:
    cid = app.category_id()
    started = clock.now_iso()
    with app.engine.begin() as conn:
        res = SPU.confirm_by_basis(conn, cid, basis, app.operator)
        runs.record_step(conn, cid, "SPU 审核", started, clock.now_iso(), app.operator,
                         result=f"按“{basis}”批量确认 {res['done']} 条", link="/spu/merge")
        return res


def merge_decide(app: App, ids: list[int], decision: str, source: str = "逐条") -> dict[str, int]:
    cid = app.category_id()
    started = clock.now_iso()
    with app.engine.begin() as conn:
        res = SPU.decide(conn, cid, ids, decision, app.operator, source=source)
        runs.record_step(conn, cid, "SPU 审核", started, clock.now_iso(), app.operator,
                         result=f"{'确认' if decision == 'confirm' else '拒绝'} {res['done']} 条", link="/spu/merge")
        return res


def compute(app: App, background: bool = False, then: Callable[[Any, Callable], Any] | None = None) -> int:
    cid = app.category_id()

    def work(conn: Any, report: Callable[[str, float], None]) -> Any:
        ids = CMP.run(conn, cid, app.operator, report)
        if then:
            then(conn, report)
        return {"runs": ids}

    with app.engine.begin() as conn:
        current = [PK.current_package(conn, cid, kind) for kind in ("history", "cross")]
        for pkg in current:
            if pkg and pkg["conclusion"] == "block":
                raise PermissionError(f"数据包 {pkg['label']} 存在阻断项，不能计算")
        if not any(current):  # refuse before a job is created (AC-F01-02: API and CLI are refused)
            last = (PK.list_packages(conn, cid) or [None])[0]
            if last and last["conclusion"] == "block":
                raise PermissionError(f"数据包 {last['label']} 存在阻断项，不能计算；请修正后重新导入")
            raise ValueError("还没有可计算的数据包，请先导入")
    return jobs.run(app.engine, cid, "compute", app.operator, work, background=background)


def backtest(app: App, mode: str = "history", background: bool = False) -> int:
    cid = app.category_id()

    def work(conn: Any, report: Callable[[str, float], None]) -> Any:
        bid = BT.run(conn, cid, app.operator, mode, report)
        return {"backtest": bid}

    with app.engine.begin() as conn:
        if CMP.latest_run(conn, cid, mode) is None:
            raise BT.BacktestError("还没有成败与信号结果，请先运行计算")
        pkg = PK.current_package(conn, cid, mode)
        if pkg and pkg["conclusion"] == "block":
            raise PermissionError(f"数据包 {pkg['label']} 存在阻断项，不能回测")

    return jobs.run(app.engine, cid, "backtest", app.operator, work, background=background)


def recompute(app: App, background: bool = False) -> int:
    """全部重算 (API-F05-02): compute, then re-rank with the current card (DEC-023) → new snapshot."""
    cid = app.category_id()
    with app.engine.begin() as conn:
        reasons = []
        for mode in ("history", "cross"):
            reasons += CMP.stale_reasons(conn, cid, CMP.latest_run(conn, cid, mode))
        if not reasons and CMP.latest_run(conn, cid, "history") is not None:
            raise ValueError("当前没有需要重算的结果")

    def work(conn: Any, report: Callable[[str, float], None]) -> Any:
        ids = CMP.run(conn, cid, app.operator, report)
        out = []
        for mode in ("history", "cross"):
            if CMP.latest_run(conn, cid, mode) and RK.CARD.current_card(conn, cid, mode):
                out.append(RK.generate(conn, cid, mode, app.operator))
        return {"runs": ids, "snapshots": out}

    return jobs.run(app.engine, cid, "recompute", app.operator, work, background=background)


def export(app: App, month: str | None = None, mode: str = "history", background: bool = False) -> int:
    from oppo.core import export as EX

    cid = app.category_id()

    def work(conn: Any, report: Callable[[str, float], None]) -> Any:
        return EX.export_month(conn, app.settings, cid, app.operator, month, mode, report)

    def after(result: Any) -> Any:
        """AC-F10-06: back up automatically after every export; a failed backup never undoes the export."""
        from oppo.core import backup as BK

        with app.engine.begin() as conn:
            bk = BK.run_backup(app.settings.db_path, conn, "导出后自动", app.operator, cid)
            if isinstance(result, dict) and result.get("export_id"):
                conn.execute(D.export_record.update().where(D.export_record.c.id == result["export_id"])
                             .values(backup_id=bk["id"]))
        out = dict(result) if isinstance(result, dict) else {"result": result}
        out["backup"] = bk
        return out

    return jobs.run(app.engine, cid, "export", app.operator, work, background=background, after=after)


def job_result(app: App, jid: int) -> dict[str, Any]:
    with app.engine.begin() as conn:
        row = conn.execute(D.job.select().where(D.job.c.id == jid)).mappings().first()
        d = dict(row) if row else {}
        d["result"] = D.loads(d.get("result_json"), None)
        return d
