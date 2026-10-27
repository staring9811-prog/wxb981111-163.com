"""Browser E2E for 台账、策略库与备份恢复 (FLOW-13/14/15/16, RULE-08 page part; DESIGN-15..22 behaviour).

Expected values come from the sample-package documents (H1-A / H1-B 说明) and the acceptance contract, not from the
code under test: 2026-03 reconciliation 4/9 vs 6/28 = 2.07×, R-A ≥ 2 upgrades, R-B 0.78 recorded, R-C 0.58 unchanged.
"""

from __future__ import annotations

import copy
import re
import sqlite3
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from oppo import service as SV
from oppo.core import backup as BK
from oppo.core import categories as CAT
from oppo.core import ledger as LG
from oppo.core import ranking as RK
from oppo.core import segments as SEG
from tests.conftest import clone_dir, fixture_pkg, open_dir


def _close(app: SV.App) -> None:
    app.engine.dispose()
    SV._apps.pop(str(app.settings.data_dir.resolve()), None)


def _rows(d: Path, sql: str) -> list[tuple]:
    c = sqlite3.connect(str(d / "oppo.sqlite3"))
    try:
        return c.execute(sql).fetchall()
    finally:
        c.close()


def _months(rows: list[tuple]) -> list[dict]:
    return [dict(zip(("units", "sales", "bsr"), r)) for r in rows]


@pytest.fixture(scope="module")
def rich(h1a_done: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """H1-A → export 第 1 版 → config change + 全部重算 → 第 2 版 → export; decisions; H1-B + compute (reconcile);
    own launch data for 甲 乙 丙 丁 (FLOW-15)."""
    d = clone_dir(h1a_done, tmp_path_factory.mktemp("ledger_rich") / "data")
    bk = d.parent / "backups"
    app = open_dir(d)
    cid = app.category_id()
    with app.engine.begin() as conn:
        assert BK.set_directory(conn, str(bk), "wen")[0]
    SV.export(app)
    with app.engine.begin() as conn:
        cfg = copy.deepcopy(CAT.current_version(conn, cid)["config"])
        cfg["health_thresholds"]["first_review_early"] = 25
        CAT.save_version(conn, cid, cfg, "wen", "改预警阈值")
    SV.recompute(app)
    SV.export(app)
    with app.engine.begin() as conn:
        snap = RK.latest_snapshot(conn, cid, "history")
        rows = snap["content"]["rows"]
        k1, k2, k3 = rows[0]["segment_key"], rows[1]["segment_key"], rows[2]["segment_key"]
        LG.record_decision(conn, cid, "wen", "立项", k1, SEG.seg_name(k1), "第 1 名，立项候选", snap["id"], "2026-03-15", "甲")
        LG.record_backfill(conn, cid, "wen", "乙", "2025-12-10", k3, SEG.seg_name(k3), "2025 年底人工研究")
        LG.record_decision(conn, cid, "wen", "立项", k2, SEG.seg_name(k2), "第 2 名", snap["id"], "2026-02-01", "丙")
        LG.record_backfill(conn, cid, "wen", "丁", "2026-04-20", k2, SEG.seg_name(k2), "")
        LG.record_decision(conn, cid, "wen", "不立项", k3, SEG.seg_name(k3), "锦囊为观察", snap["id"])
    SV.import_package(app, fixture_pkg("H1-B"))
    SV.compute(app)
    with app.engine.begin() as conn:
        LG.save_launch_data(conn, cid, "wen", "D-0001", "2026-03", _months(
            [(38, "19,000", 312), (96, "46,800", 164), (141, "44,100", 112), (122, "38,900", 131),
             (104, "33,500", 158), (97, "31,200", 170)]), "B0DGX4M7QK")
        LG.save_launch_data(conn, cid, "wen", "D-0002", "2026-01", _months(
            [(20, "9,000", 210), (40, "18,000", 120), (70, "30,000", 80), (90, "41,000", 50), ("", "", ""),
             ("", "", "")]), "B0DGX4M7QA")
        LG.save_launch_data(conn, cid, "wen", "D-0003", "2026-02", _months(
            [(20, "9,000", 210), (40, "18,000", 120), ("", "", ""), (90, "41,000", 90), (80, "36,000", 95),
             (70, "33,000", 99)]), "B0DGX4M7QB")
        LG.save_launch_data(conn, cid, "wen", "D-0004", "2026-05", _months(
            [(20, "9,000", 210), (40, "18,000", 120), (50, "20,000", 110), (60, "26,000", 100)]), "B0DGX4M7QC")
    _close(app)
    return d


def _ok(page: Page) -> None:
    """No script errors; 400 responses are the expected answers to rejected forms."""
    errs = [e for e in page.js_errors if "status of 400" not in e]  # type: ignore[attr-defined]
    assert not errs, errs


# ---- PAGE-F10-01 ------------------------------------------------------------------------------


def test_snapshots_versions_drawer_and_filters(live_server, clone, rich, page: Page) -> None:  # type: ignore[no-untyped-def]
    live = live_server(clone(rich))
    page.goto(live.u("/ledger/snapshots"))
    rows = page.locator("#snap-table tbody tr")
    expect(rows).to_have_count(2)
    v2 = page.locator("#snap-table tbody tr", has_text="2026-03 · 第 2 版")
    v1 = page.locator("#snap-table tbody tr", has_text="2026-03 · 第 1 版")
    expect(v2).to_contain_text("已对账")
    expect(v2).to_contain_text("倍数 2.07×")
    expect(v2).to_contain_text("已导出")
    expect(v1).to_contain_text("不用于对账")
    expect(v1).to_contain_text("同月第 2 版已导出")
    # no edit / delete entry anywhere on the page
    assert page.get_by_role("button", name=re.compile("删除|修改|编辑")).count() == 0
    page.get_by_role("button", name="不用于对账").click()
    expect(page.locator("#snap-table tbody tr:visible")).to_have_count(1)
    expect(page.locator("[data-filter-count]").first).to_have_text("1")
    page.locator(".chip[data-filter='recon:all']").click()
    v2.get_by_role("button", name="查看快照").click()
    drawer = page.locator("aside.drawer.is-open")
    expect(drawer).to_contain_text("快照保存后不可修改")
    expect(drawer).to_contain_text("前 20% 4/9，全类目 6/28，倍数 2.07×")
    drawer.get_by_role("button", name="SHA-256").click()
    sha = _rows(live.app.settings.data_dir, "SELECT sha256 FROM snapshot WHERE seq=2")[0][0]
    expect(page.locator(".popover.is-open")).to_contain_text(sha)
    expect(drawer.get_by_role("link", name="在到期对账中查看")).to_be_visible()
    _ok(page)


# ---- PAGE-F10-02 / F10-04 (FLOW-13) ------------------------------------------------------------


def test_record_decision_requires_reason_then_saves_with_snapshot(live_server, clone, h1a_done, page: Page) -> None:  # type: ignore[no-untyped-def]
    live = live_server(clone(h1a_done))
    page.goto(live.u("/ledger/decisions"))
    expect(page.get_by_text("还没有立项记录", exact=True)).to_be_visible()
    page.get_by_role("button", name="记录决定").first.click()
    modal = page.locator("#decision-modal")
    expect(modal).to_have_class(re.compile("is-open"))
    seg = "30–48″|落地式|$500–900"
    modal.locator("#d-seg").select_option(seg)
    expect(modal.locator(f"[data-ctx-for='{seg}']")).to_contain_text("本月排第 1 名")
    expect(modal.locator("#d-snap")).to_have_value(re.compile("2026-03 · 第 1 版"))
    modal.locator("[data-submit-for='decide']").click()
    expect(modal.locator("[data-error-for='reason']")).to_have_text("请写下理由，日后对账要看当时为什么这样决定")
    assert _rows(live.app.settings.data_dir, "SELECT count(*) FROM decision_record")[0][0] == 0
    modal.locator("#d-reason").fill("第 1 名，锦囊立项候选")
    modal.locator("[data-submit-for='decide']").click()
    page.wait_for_url(re.compile("/ledger/decisions"))
    row = page.locator("#d-0001")
    expect(row).to_contain_text("第 1 名，锦囊立项候选")
    expect(row).to_contain_text("快照 2026-03 · 第 1 版")
    rec = _rows(live.app.settings.data_dir, "SELECT decision, segment_key, snapshot_id, created_by, kind FROM decision_record")
    assert rec[0][0] == "立项" and rec[0][1] == seg and rec[0][2] is not None and rec[0][3] == "wen" and rec[0][4] == "记录"
    _ok(page)


def test_backfill_then_correction_keeps_original(live_server, clone, h1a_done, page: Page) -> None:  # type: ignore[no-untyped-def]
    live = live_server(clone(h1a_done))
    page.goto(live.u("/ledger/decisions"))
    page.get_by_role("button", name="补录在研立项").first.click()
    modal = page.locator("#decision-modal")
    expect(modal.locator("#panel-backfill")).to_be_visible()
    modal.locator("[data-submit-for='backfill']").click()
    for f in ("project_name", "project_date", "segment_key"):
        expect(modal.locator(f"#panel-backfill [data-error-for='{f}']")).to_have_text("必填")
    modal.locator("#b-name").fill("30″ 悬浮式双抽柜（ZR-2025-12）")
    modal.locator("#b-date").fill("2025-12-10")
    modal.locator("#b-seg").select_option("≤30″|悬浮式|<$500")
    modal.locator("[data-submit-for='backfill']").click()
    page.wait_for_url(re.compile("/ledger/decisions"))
    orig = page.locator("#d-0001")
    expect(orig).to_contain_text("补录")
    expect(orig).to_contain_text("无对应快照（补录）")
    expect(orig).to_contain_text("2025-12-10")
    orig.get_by_role("link", name="更正").click()
    modal = page.locator("#decision-modal")
    expect(modal).to_contain_text("更正立项记录")
    modal.locator("#b-seg").select_option("≤30″|悬浮式|$500–900")
    modal.locator("[data-submit-for='backfill']").click()
    expect(modal.locator("[data-error-for='reason']")).to_have_text("请填写更正理由")
    modal.locator("#b-reason").fill("关联细分误填")
    modal.locator("[data-submit-for='backfill']").click()
    page.wait_for_url(re.compile("/ledger/decisions"))
    expect(page.locator("#d-0001")).to_contain_text("已更正")
    expect(page.locator("#d-0001")).to_contain_text("见更正记录 D-0002")
    expect(page.locator("#d-0002")).to_contain_text("更正 D-0001")
    assert page.locator("#d-0001").get_by_role("link", name="更正").count() == 0
    rows = _rows(live.app.settings.data_dir, "SELECT code, kind, segment_key, corrects_id FROM decision_record ORDER BY id")
    assert rows[0] == ("D-0001", "补录", "≤30″|悬浮式|<$500", None)
    assert rows[1][1] == "更正" and rows[1][2] == "≤30″|悬浮式|$500–900" and rows[1][3] == 1
    _ok(page)


# ---- PAGE-F10-06 (FLOW-15) ---------------------------------------------------------------------


def test_launch_data_rejects_non_numbers_and_keeps_blanks_missing(live_server, clone, h1a_done, page: Page) -> None:  # type: ignore[no-untyped-def]
    d = clone(h1a_done)
    app = open_dir(d)
    with app.engine.begin() as conn:
        cid = app.category_id()
        snap = RK.latest_snapshot(conn, cid, "history")
        k = snap["content"]["rows"][0]["segment_key"]
        LG.record_decision(conn, cid, "wen", "立项", k, SEG.seg_name(k), "第 1 名", snap["id"], "2025-08-20", "丙")
    _close(app)
    live = live_server(d)
    page.goto(live.u("/ledger/decisions"))
    page.locator("#d-0001").get_by_role("link", name="录入上架数据").click()
    modal = page.locator("#launch-modal")
    expect(modal).to_contain_text("填写上架月和月度数据后")
    modal.locator("#l-month").fill("2026-01")  # data runs to 2026-02: months 3–6 are in the future
    expect(modal.locator("input[name='units_3']")).to_be_disabled()
    expect(modal.locator("input[name='units_2']")).to_be_enabled()
    modal.locator("#l-month").fill("2025-09")
    expect(modal.locator("[data-month-label='6']")).to_have_text("2026-02")
    modal.locator("#l-asin").fill("B0DGX4M7QK")
    vals = {1: (38, "19,000", 312), 2: ("abc", "46,800", 164), 4: (122, "38,900", 131), 5: (104, "33,500", 158),
            6: (97, "31,200", 170)}
    for i, (u, s, b) in vals.items():
        modal.locator(f"input[name='units_{i}']").fill(str(u))
        modal.locator(f"input[name='sales_{i}']").fill(s)
        modal.locator(f"input[name='bsr_{i}']").fill(str(b))
    page.get_by_role("button", name="保存并判定").click()
    expect(modal.locator("[data-error-for='units_2']")).to_have_text("请填写整数；没有数据就留空")
    assert _rows(d, "SELECT count(*) FROM launch_data")[0][0] == 0
    modal.locator("input[name='units_2']").fill("96")
    page.get_by_role("button", name="保存并判定").click()
    page.wait_for_url(re.compile("toast="))
    expect(page.locator("#d-0001")).to_contain_text("数据不全")
    expect(page.locator("#d-0001")).to_contain_text("缺 2025-11")
    import json

    months = json.loads(_rows(d, "SELECT months_json FROM launch_data")[0][0])["months"]
    assert months[2] == {"units": None, "sales": None, "bsr": None}  # blank stays missing, not 0
    assert months[0] == {"units": 38, "sales": 19000.0, "bsr": 312}
    _ok(page)


# ---- PAGE-F10-05 (FLOW-14 / FLOW-15) -----------------------------------------------------------


def test_reconcile_page_numbers_rules_and_own_results(live_server, clone, rich, page: Page) -> None:  # type: ignore[no-untyped-def]
    live = live_server(clone(rich))
    page.goto(live.u("/ledger/reconcile"))
    row = page.locator("#recon-table tbody tr").first
    expect(row).to_contain_text("2026-03 · 第 2 版")
    expect(row).to_contain_text("44.4%")
    expect(row).to_contain_text("命中 4 / 9")
    expect(row).to_contain_text("21.4%")
    expect(row).to_contain_text("命中 6 / 28")
    expect(row).to_contain_text("2.07×")
    expect(row).to_contain_text("对账月份 2026-09")
    expect(row.locator(".badge")).to_contain_text(re.compile("区间"))
    rules = page.locator("#rule-recon-table tbody tr")
    expect(rules).to_have_count(3)
    expect(rules.nth(0)).to_contain_text("升为已验证")
    expect(rules.nth(0)).to_contain_text("2.07×")
    expect(rules.nth(0)).to_contain_text("2 个")
    expect(rules.nth(1)).to_contain_text("0.78×")
    expect(rules.nth(1)).to_contain_text("已记录")
    expect(rules.nth(1)).to_contain_text("2 个")
    expect(rules.nth(2)).to_contain_text("0.58×")
    expect(rules.nth(2)).to_contain_text("未达条件")
    expect(rules.nth(2)).to_contain_text("3 个")
    own = page.locator("#own-table")
    expect(own.locator("[data-own='D-0001']")).to_contain_text("未命中")
    expect(own.locator("[data-own='D-0001']")).to_contain_text("2026-03 · 第 2 版 · 第 1 名")
    expect(own.locator("[data-own='D-0001']")).to_contain_text('当时为"历史观察"')
    expect(own.locator("[data-own='D-0002']")).to_contain_text("命中")
    expect(own.locator("[data-own='D-0002']")).to_contain_text("无对应快照（补录）")
    expect(own.locator("[data-own='D-0003']")).to_contain_text("数据不全")
    expect(own.locator("[data-own='D-0003']")).to_contain_text("缺 2026-04")
    expect(own.locator("[data-own='D-0004']")).to_contain_text("观察中 · 还剩 2 个月")
    assert own.locator("[data-own='D-0005']").count() == 0  # 不立项 does not take part
    page.get_by_role("link", name="查看策略库").click()
    expect(page.locator("#rule-table tr[data-rule='R-001']")).to_contain_text("已验证")
    _ok(page)


# ---- PAGE-F11-01 / F11-02 (FLOW-16) ------------------------------------------------------------


def test_rules_add_validation_and_versions(live_server, clone, h1a_done, page: Page) -> None:  # type: ignore[no-untyped-def]
    live = live_server(clone(h1a_done))
    page.goto(live.u("/rules"))
    page.get_by_role("link", name="新增经验规则").click()
    drawer = page.locator("#rule-drawer")
    expect(drawer).to_contain_text("保存后为新规则 v1，状态为未验证经验")
    drawer.get_by_role("button", name="保存").click()
    expect(drawer.locator("[data-error-for='cond']")).to_have_text("至少需要一条条件")
    expect(drawer.locator("[data-error-for='action']")).to_have_text("请选择动作")
    expect(drawer.locator("[data-error-for='reason']")).to_have_text("请写明理由")
    row1 = drawer.locator("[data-cond]").nth(0)
    row1.locator("[data-cond-field]").select_option("attr:台面材质")
    row1.locator("[name='cond_value']").select_option("岩板")
    drawer.get_by_role("button", name="添加条件").click()
    row2 = drawer.locator("[data-cond]").nth(1)
    row2.locator("[data-cond-field]").select_option("dim:width")
    row2.locator("[name='cond_value']").select_option("≥48″")
    drawer.get_by_label("观察").check()
    drawer.get_by_role("button", name="保存").click()
    expect(drawer.locator("[data-error-for='reason']")).to_have_text("请写明理由")
    drawer.locator("#rule-reason").fill("立项评审时的供应链判断")
    drawer.get_by_role("button", name="保存").click()
    page.wait_for_url(re.compile(r"/rules\?toast="))
    new = page.locator("#rule-table tr[data-rule='R-004']")
    expect(new).to_contain_text("台面材质 = 岩板 且 宽度档 = ≥48″")
    expect(new).to_contain_text("未验证经验")
    expect(new).to_contain_text("人工新增")
    expect(new).to_contain_text("R-004 · v1")
    # only the reason changes → new version, status unchanged
    new.click()
    drawer = page.locator("#rule-drawer")
    expect(drawer.locator("#reset-hint")).to_be_hidden()
    drawer.locator("#rule-reason").fill("补充：来自 2026-03 评审")
    drawer.get_by_role("button", name="保存为 v2").click()
    page.wait_for_url(re.compile(r"/rules\?toast="))
    expect(page.locator("#rule-table tr[data-rule='R-004']")).to_contain_text("R-004 · v2")
    expect(page.locator("#rule-table tr[data-rule='R-004']")).to_contain_text("未验证经验")
    # a 历史观察 rule: threshold +15% → +20% resets to 未验证经验, old version keeps its status
    page.goto(live.u("/rules?rule=R-001"))
    drawer = page.locator("#rule-drawer")
    expect(drawer).to_contain_text("历史观察")
    val = drawer.locator("[data-cond]").nth(0).locator("[name='cond_value']")
    expect(val).to_have_value("+15%")
    val.fill("+20%")
    expect(drawer.locator("#reset-hint")).to_be_visible()
    expect(drawer.locator("#reset-hint")).to_contain_text("保存后状态将变为未验证经验")
    drawer.locator("#rule-reason").fill("旺季前后容易误报")
    drawer.get_by_role("button", name="保存为 v2").click()
    page.wait_for_url(re.compile(r"/rules\?toast="))
    expect(page.locator("#rule-table tr[data-rule='R-001']")).to_contain_text("未验证经验")
    page.goto(live.u("/rules?rule=R-001"))
    hist = page.locator("[data-versions]")
    expect(hist.locator("[data-version='2']")).to_contain_text("需求在涨 ≥ +15%")
    expect(hist.locator("[data-version='2']")).to_contain_text("需求在涨 ≥ +20%")
    expect(hist.locator("[data-version='2']")).to_contain_text("旺季前后容易误报")
    expect(hist.locator("[data-version='1']")).to_contain_text("历史观察")
    vers = _rows(live.app.settings.data_dir, "SELECT version_no, status, condition_json FROM rule_version v JOIN rule r "
                 "ON r.id = v.rule_id WHERE r.code='R-001' ORDER BY version_no")
    assert [v[1] for v in vers] == ["历史观察", "未验证经验"]
    assert '"value": 0.2' in vers[1][2] and '"kind": "signal"' in vers[1][2]
    _ok(page)


# ---- PAGE-F10-03 (RULE-08 page part, AC-F10-08) ------------------------------------------------


def test_backup_directory_check_and_restore(live_server, clone, h1a_done, tmp_path: Path, page: Page) -> None:  # type: ignore[no-untyped-def]
    d = clone(h1a_done)
    live = live_server(d)
    page.goto(live.u("/settings/backup"))
    expect(page.get_by_text("还没有设置备份目录").first).to_be_visible()
    blocker = tmp_path / "a-file"
    blocker.write_text("x")
    page.locator("#bk-dir").fill(str(blocker / "sub"))
    page.get_by_role("button", name="检测能否写入").click()
    expect(page.locator("[data-error-for='directory']")).to_contain_text("不能写入")
    page.get_by_role("button", name="保存目录").click()
    expect(page.locator("[data-error-for='directory']")).to_contain_text("不能写入")
    assert _rows(d, "SELECT count(*) FROM backup_setting")[0][0] == 0
    good = tmp_path / "备份"
    page.locator("#bk-dir").fill(str(good))
    page.get_by_role("button", name="检测能否写入").click()
    expect(page.locator("[data-dir-result]")).to_contain_text("可以写入")
    page.get_by_role("button", name="保存目录").click()
    page.wait_for_url(re.compile("toast="))
    app = live.app
    with app.engine.begin() as conn:
        first = BK.run_backup(app.settings.db_path, conn, "导出后自动", "wen", app.category_id())
    with app.engine.begin() as conn:
        snap = RK.latest_snapshot(conn, app.category_id(), "history")
        k = snap["content"]["rows"][0]["segment_key"]
        LG.record_decision(conn, app.category_id(), "wen", "不立项", k, SEG.seg_name(k), "先不做", snap["id"])
    page.goto(live.u("/settings/backup"))
    rows = page.locator("#backup-table tbody tr")
    expect(rows).to_have_count(1)
    rows.first.get_by_role("button", name="恢复").click()
    modal = page.locator(".modal.is-open")
    expect(modal).to_contain_text("将覆盖当前的台账、策略库、字段约定、品类配置和确认记录")
    expect(modal.locator(".diff")).to_contain_text("立项记录 1")
    expect(modal.locator(".diff")).to_contain_text("立项记录 0")
    modal.get_by_role("button", name="确认恢复").click()
    page.wait_for_url(re.compile("restored=1"))
    expect(page.locator("#restore-done")).to_contain_text(f"已恢复到 {first['time'][:16]} 的备份")
    expect(page.locator("#backup-table tbody tr")).to_have_count(2)
    expect(page.locator("#backup-table tbody tr").first).to_contain_text("恢复前自动备份")
    assert _rows(d, "SELECT count(*) FROM decision_record")[0][0] == 0
    assert _rows(d, "SELECT count(*) FROM restore_record")[0][0] == 1
    _ok(page)
