"""Service-level acceptance for step timing (FLOW-19) and maturity reconciliation (FLOW-14).
Expected numbers come from the contract and fixtures/packages/H1-B.说明.md."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from oppo import service as SV
from oppo.core import categories as CAT
from oppo.core import ledger as LG
from oppo.core import ranking as RK
from oppo.core import rules as RULES
from oppo.core import runs
from tests.conftest import fixture_pkg, open_dir

pytest.importorskip("oppo.core.export")


def _close(app: SV.App) -> None:
    app.engine.dispose()
    SV._apps.pop(str(app.settings.data_dir.resolve()), None)


def test_flow19_first_run_and_monthly_timing(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    clock = tmp_path / "clock.txt"
    monkeypatch.setenv("OPPO_CLOCK_FILE", str(clock))

    def at(s: str) -> None:
        clock.write_text(s, encoding="utf-8")

    app = open_dir(tmp_path / "data")
    at("2026-11-06 10:40:00")  # Friday
    SV.import_package(app, fixture_pkg("H1-A"))
    at("2026-11-06 14:00:00")
    SV.contract_confirm(app)
    at("2026-11-09 09:30:00")
    SV.merge_confirm_basis(app, "标题主干相同")
    at("2026-11-09 10:00:00")
    SV.compute(app)
    at("2026-11-10 16:52:00")  # Tuesday
    SV.backtest(app)
    with app.engine.begin() as conn:
        cid = app.category_id()
        first = runs.summary(conn, cid)["first_run"]
    assert first["start"] == datetime(2026, 11, 6, 10, 40) and first["end"] == datetime(2026, 11, 10, 16, 52)
    assert first["days"] == 3 and first["ok"] is True

    at("2026-12-07 09:00:00")
    SV.import_package(app, fixture_pkg("H1-B"))
    at("2026-12-07 09:20:00")
    SV.contract_confirm(app)
    at("2026-12-07 09:40:00")
    SV.compute(app)
    at("2026-12-07 11:00:00")
    SV.backtest(app)
    at("2026-12-07 11:30:00")
    SV.export(app)
    at("2026-12-07 12:10:00")
    SV.export(app)  # the last export of the month counts
    with app.engine.begin() as conn:
        summ = runs.summary(conn, cid)
        steps = runs.steps(conn, cid)
    month = next(m for m in summ["monthly"] if m["month"] == "2026-09")
    assert month["minutes"] == 190 and month["ok"] is True
    assert runs.fmt_minutes(month["minutes"]) == "3 小时 10 分"
    names = {s["step"] for s in steps}
    assert names >= {"导入校验", "字段确认", "数据体检", "SPU 审核", "计算", "回测", "导出"}
    for s in steps:
        assert s["started_at"] and s["ended_at"] and s["created_by"] == "wen", s
    _close(app)


def test_flow14_reconciliation_uses_last_exported_version(tmp_path: Path) -> None:
    app = open_dir(tmp_path / "data")
    SV.import_package(app, fixture_pkg("H1-A"))
    SV.contract_confirm(app)
    SV.compute(app)
    SV.backtest(app)
    SV.export(app)  # 2026-03 第 1 版 exported
    with app.engine.begin() as conn:
        cid = app.category_id()
        cfg = CAT.current_version(conn, cid)["config"]
        cfg["health_thresholds"]["dup_key"] = 5
        CAT.save_version(conn, cid, cfg, "wen", "调整体检阈值")
    SV.recompute(app)  # → 第 2 版
    SV.export(app)  # 第 2 版 exported last
    with app.engine.begin() as conn:
        v = RK.reconcile_version(conn, cid, "2026-03", "history")
        assert v["seq"] == 2
        tips = {t["rule"]: t for r in v["content"]["rows"] for t in r["tips"]}
    SV.import_package(app, fixture_pkg("H1-B"))
    SV.compute(app)
    with app.engine.begin() as conn:
        recs = LG.reconciliations(conn, cid)
        r = next(x for x in recs if x["batch"] == "2026-03" and x["mode"] == "history")
        assert r["snapshot"]["seq"] == 2 and r["recon_month"] == "2026-09"
        assert (r["top_hits"], r["top_n"], r["all_hits"], r["all_n"]) == (4, 9, 6, 28)
        assert round(r["multiple"], 2) == 2.07 and r["incomplete"] == 3
        assert r["within"] is not None
        by_action = {x["action"]: x for x in r["rules"]}
        ra, rb, rc = by_action["立项候选"], by_action["观察"], by_action["放弃"]
        assert round(ra["multiple"], 2) == 2.07 and ra["result"] == "升为已验证" and ra["new_version_no"] == 2
        assert round(rb["multiple"], 2) == 0.78 and rb["result"] != "升为已验证"
        assert round(rc["multiple"], 2) == 0.58 and rc["result"] != "升为已验证"
        cur_a = RULES.current(conn, ra["rule_id"])
        assert cur_a["status"] == "已验证" and cur_a["version_no"] == 2
        assert RULES.current(conn, rb["rule_id"])["status"] == "历史观察"
        assert RULES.current(conn, rc["rule_id"])["status"] == "历史观察"
        old = RULES.history(conn, ra["rule_id"])
        assert [h["status"] for h in sorted(old, key=lambda h: h["version_no"])] == ["历史观察", "已验证"]
    assert set(tips) >= {ra["code"], rb["code"], rc["code"]}
    _close(app)


@pytest.mark.parametrize("h,n,ah,an,action,upgrade", [
    (2, 10, 1, 10, "立项候选", True),  # 2.00 → 升级
    (199, 1000, 1, 10, "立项候选", False),  # 1.99 → 不升级
    (1, 20, 1, 10, "放弃", True),  # 0.50 → 升级
    (51, 1000, 1, 10, "放弃", False),  # 0.51 → 不升级
])
def test_flow14_upgrade_boundaries(h, n, ah, an, action, upgrade) -> None:  # type: ignore[no-untyped-def]
    assert LG.upgrade_met(action, h, n, ah, an) is upgrade
