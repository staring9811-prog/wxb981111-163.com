"""Data states for the visual acceptance screenshots (TDD 验收契约 DESIGN-01..26).

Each state is a data directory produced only through the service / core functions the app itself uses, starting
from the hand-built sample packages. Nothing is written into result tables directly.

    python -m devtools.visual_states <base_dir> [state ...]
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path

from oppo import service as SV
from oppo import settings as S
from oppo.core import backup as BK
from oppo.core import categories as CAT
from oppo.core import ledger as LG
from oppo.core import ranking as RK

APP = Path(__file__).resolve().parents[1]
FIX = APP / "fixtures" / "packages"


def open_dir(d: Path) -> SV.App:
    return SV.open_app(S.Settings(data_dir=d, operator="wen", port=0))


def close(app: SV.App) -> None:
    app.engine.dispose()
    SV._apps.pop(str(app.settings.data_dir.resolve()), None)


def clone(src: Path, dst: Path) -> Path:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for item in src.iterdir():
        if item.name.startswith("oppo.sqlite3"):
            continue
        if item.is_dir():
            shutil.copytree(item, dst / item.name)
        else:
            shutil.copy2(item, dst / item.name)
    s, t = sqlite3.connect(str(src / "oppo.sqlite3")), sqlite3.connect(str(dst / "oppo.sqlite3"))
    s.backup(t)
    s.close()
    t.close()
    # backup records point at the source's backup directory; give the clone its own copy
    if (src / "backups").exists():
        from sqlalchemy import text

        app = open_dir(dst)
        with app.engine.begin() as conn:
            BK.set_directory(conn, str(dst / "backups"), "wen")
            # backup records are not append-only; point them at the copied files so list and records agree
            conn.execute(text("UPDATE backup_record SET path = REPLACE(path, :a, :b) WHERE path IS NOT NULL"),
                         {"a": str(src / "backups"), "b": str(dst / "backups")})
        close(app)
    return dst


def fresh(d: Path) -> SV.App:
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return open_dir(d)


def backup_dir(app: SV.App, d: Path) -> None:
    with app.engine.begin() as conn:
        ok, msg = BK.set_directory(conn, str(d / "backups"), "wen")
        assert ok, msg


def s1(base: Path) -> Path:
    """H1-A month done in the order of SMOKE-02, exported with an automatic backup."""
    d = base / "s1"
    app = fresh(d)
    backup_dir(app, d)
    SV.import_package(app, FIX / "H1-A")
    SV.contract_confirm(app)
    SV.merge_confirm_basis(app, "标题主干相同")
    SV.compute(app)
    SV.backtest(app)
    SV.export(app)
    close(app)
    return d


def s1x(base: Path) -> Path:
    """s1 plus the cross package X1 computed and backtested: both conclusions exist."""
    d = clone(base / "s1", base / "s1x")
    app = open_dir(d)
    SV.import_package(app, FIX / "X1")
    SV.contract_confirm(app)
    SV.compute(app)
    SV.backtest(app, mode="cross")
    close(app)
    return d


def s_cross_only(base: Path) -> Path:
    d = base / "s_cross_only"
    app = fresh(d)
    backup_dir(app, d)
    SV.import_package(app, FIX / "X1")
    SV.contract_confirm(app)
    SV.compute(app)
    SV.backtest(app, mode="cross")
    SV.export(app, mode="cross")
    close(app)
    return d


def s_unverified(base: Path) -> Path:
    d = base / "s_unverified"
    app = fresh(d)
    backup_dir(app, d)
    SV.import_package(app, FIX / "H1-无区分度")
    SV.contract_confirm(app)
    SV.merge_confirm_basis(app, "标题主干相同")
    SV.compute(app)
    SV.backtest(app)
    SV.export(app)
    close(app)
    return d


def s_block(base: Path) -> Path:
    d = base / "s_block"
    app = fresh(d)
    SV.import_package(app, FIX / "H1-坏行11")
    close(app)
    return d


def s_ledger(base: Path) -> Path:
    """FLOW-13/14/15: two exported snapshot versions of 2026-03, decisions (incl. 补录 and 更正), H1-B reconciled,
    own-project launch data."""
    d = clone(base / "s1", base / "s_ledger")
    app = open_dir(d)
    cid = app.category_id()
    with app.engine.begin() as conn:
        cfg = CAT.current_version(conn, cid)["config"]
        cfg["health_thresholds"]["dup_key"] = 5
        CAT.save_version(conn, cid, cfg, "wen", "主键重复预警阈值放宽到 5 条")
    SV.recompute(app)
    SV.export(app)
    with app.engine.begin() as conn:
        snap = RK.latest_snapshot(conn, cid, "history")
        rows = snap["content"]["rows"]
        a = LG.record_decision(conn, cid, "wen", "立项", rows[0]["segment_key"], rows[0]["segment"],
                               "需求在涨 +20%，前 20% 细分，样本 44", snap["id"], project_name="甲 · 36 寸落地浴室柜")
        b = LG.record_decision(conn, cid, "wen", "立项", rows[1]["segment_key"], rows[1]["segment"],
                               "需求在涨 +20%，与第 1 名同宽度档", snap["id"], project_name="乙 · 42 寸低价落地款")
        c = LG.record_decision(conn, cid, "wen", "不立项", rows[4]["segment_key"], rows[4]["segment"],
                               "需求在跌，锦囊为放弃", snap["id"])
        LG.correct(conn, cid, "wen", c, reason="需求在跌 −6%，锦囊为放弃；补充：头部品牌集中")
        e = LG.record_backfill(conn, cid, "wen", "丙 · 30 寸悬浮款", "2025-12-10", rows[3]["segment_key"],
                               rows[3]["segment"], "补录系统上线前已立项的在研项目")
        f = LG.record_decision(conn, cid, "wen", "立项", rows[2]["segment_key"], rows[2]["segment"],
                               "观察类细分里样本最多", snap["id"], project_name="丁 · 24 寸落地款")
    SV.import_package(app, FIX / "H1-B")
    SV.contract_confirm(app)
    SV.compute(app)
    with app.engine.begin() as conn:
        full = [{"units": u, "sales": s, "bsr": r} for u, s, r in
                [(80, 31200, 260), (95, 37100, 180), (110, 42900, 140), (120, 46800, 112), (118, 46000, 130),
                 (105, 41000, 150)]]
        LG.save_launch_data(conn, cid, "wen", a, "2026-03", full, asin="B0JIA00001")
        yi = [dict(m) for m in full]
        yi[3]["bsr"] = 50
        LG.save_launch_data(conn, cid, "wen", b, "2026-03", yi, asin="B0YI000001")
        bing = [dict(m) for m in full]
        bing[2] = {"units": None, "sales": None, "bsr": None}
        LG.save_launch_data(conn, cid, "wen", e, "2026-03", bing, asin="B0BING0001")
        ding = [dict(m) for m in full[:4]] + [{"units": None, "sales": None, "bsr": None}] * 2
        LG.save_launch_data(conn, cid, "wen", f, "2026-05", ding, asin="B0DING0001")
    close(app)
    return d


def s_timing(base: Path) -> Path:
    """FLOW-19 with a controllable clock: first run Fri 10:40 → Tue 16:52, a monthly update 09:00 → 12:10."""
    d = base / "s_timing"
    clock = base / "s_timing.clock"
    old = os.environ.get("OPPO_CLOCK_FILE")
    os.environ["OPPO_CLOCK_FILE"] = str(clock)

    def at(s: str) -> None:
        clock.write_text(s, encoding="utf-8")

    try:
        app = fresh(d)
        backup_dir(app, d)
        at("2026-11-06 10:40:00")
        SV.import_package(app, FIX / "H1-A")
        at("2026-11-06 14:10:00")
        SV.contract_confirm(app)
        at("2026-11-09 09:30:00")
        SV.merge_confirm_basis(app, "标题主干相同")
        at("2026-11-09 10:05:00")
        SV.compute(app)
        at("2026-11-10 16:52:00")
        SV.backtest(app)
        at("2026-11-10 17:05:00")
        SV.export(app)
        at("2026-12-07 09:00:00")
        SV.import_package(app, FIX / "H1-B")
        at("2026-12-07 09:25:00")
        SV.contract_confirm(app)
        at("2026-12-07 09:50:00")
        SV.compute(app)
        at("2026-12-07 11:20:00")
        SV.backtest(app)
        at("2026-12-07 12:10:00")
        SV.export(app)
        close(app)
    finally:
        if old is None:
            os.environ.pop("OPPO_CLOCK_FILE", None)
        else:
            os.environ["OPPO_CLOCK_FILE"] = old
    return d


STATES = {"s1": s1, "s1x": s1x, "s_cross_only": s_cross_only, "s_unverified": s_unverified, "s_block": s_block,
          "s_ledger": s_ledger, "s_timing": s_timing}


def main() -> None:
    base = Path(sys.argv[1])
    names = sys.argv[2:] or list(STATES)
    base.mkdir(parents=True, exist_ok=True)
    for n in names:
        print("building", n, flush=True)
        STATES[n](base)
    print("done", flush=True)


if __name__ == "__main__":
    main()
