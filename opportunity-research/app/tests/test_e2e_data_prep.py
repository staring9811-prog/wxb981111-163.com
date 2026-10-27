"""Browser E2E for the 数据准备 pages: 数据包、校验报告、字段约定、数据体检、品类配置、运行记录
(FLOW-01/02/03/18/19 through the real pages; DESIGN-02..05/25/26 behaviour)."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
from pathlib import Path

import pytest
from sqlalchemy import select, text

from oppo import db as D
from oppo import service as SV
from oppo.core import categories as CAT
from oppo.core import compute as CMP
from oppo.core import contract as CT
from oppo.core import packages as PK
from oppo.core import runs
from oppo.web import viewmodels as VM
from tests.conftest import FIX, _prepared, fixture_pkg, open_dir

LONG = 180_000


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _toast(page, contains: str) -> str:  # type: ignore[no-untyped-def]
    """Wait for a toast containing `contains` (earlier toasts may still be fading out)."""
    loc = page.locator(".toast", has_text=contains)
    loc.last.wait_for(timeout=30_000)
    return loc.last.inner_text()


@pytest.fixture(scope="session")
def variants(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """坏行 8 / 10 / 11 (C1 1,000 rows), 无清单 and the cross-section X1, imported in that order."""
    return _prepared(tmp_path_factory, "variants", ("import:H1-坏行8", "import:H1-坏行10", "import:H1-坏行11",
                                                     "import:H1-无清单", "import:X1"))


# ---- PAGE-F01-01 数据包 -------------------------------------------------------------------------


def test_import_by_path_then_duplicate_zip(live_server, data_dir, page, tmp_path):  # type: ignore[no-untyped-def]
    live = live_server(data_dir)
    src = fixture_pkg("H1-A")
    page.goto(live.u("/packages?import=1"))
    assert page.get_by_text("还没有数据包").first.is_visible()
    page.fill("#pkg-path", str(src))
    page.click("[data-stage-path]")
    page.wait_for_selector("#preview-table")
    assert page.locator("#preview-table tbody tr").count() == 7
    assert "历史数据包 · 按约定 v1 校验" in page.locator(".kv").first.inner_text()
    page.click("[data-import-submit]")
    page.wait_for_url(re.compile(r"/packages/\d+/report"), timeout=LONG)
    assert page.locator("h1").inner_text() == "校验报告 · P-0001"
    assert "有警告 · 可以计算" in page.locator(".banner").first.inner_text()
    assert page.locator("#matrix-table tbody tr").count() == 7
    with live.app.engine.begin() as conn:
        pkg = PK.by_label(conn, "P-0001")
        files = PK.files(conn, pkg["id"])
        n_steps = conn.execute(text("SELECT COUNT(*) FROM run_step WHERE step='导入校验'")).scalar()
    assert n_steps == 1
    copy = Path(pkg["readonly_path"])
    for f in files:
        target = copy / f["filename"]
        assert stat.S_IMODE(target.stat().st_mode) & 0o222 == 0, "只读副本应带只读属性"
        assert f["sha256"] == _sha(target) == _sha(src / f["filename"])
    # the same package again, this time as a zip upload → duplicate notice, no new version
    z = shutil.make_archive(str(tmp_path / "H1-A"), "zip", root_dir=src)
    page.goto(live.u("/packages"))
    page.set_input_files("[data-stage-zip]", z)
    page.wait_for_selector("[data-dup]")
    dup = page.locator("[data-dup]").inner_text()
    assert "该数据包已导入" in dup and "P-0001" in dup
    assert page.locator("#import-form .btn--primary").get_attribute("aria-disabled") == "true"
    assert page.locator("#pkg-table tbody tr").count() == 1
    with live.app.engine.begin() as conn:
        assert len(PK.list_packages(conn, live.app.category_id())) == 1
    assert not page.js_errors


def test_stage_errors_and_missing_manifest_preview(live_server, data_dir, page):  # type: ignore[no-untyped-def]
    live = live_server(data_dir)
    page.goto(live.u("/packages"))
    page.fill("#pkg-path", "/no/such/place.zip")
    page.click("[data-stage-path]")
    page.wait_for_selector("[data-error-for=path]:not(:empty)")
    assert "找不到" in page.locator("[data-error-for=path]").inner_text()
    page.fill("#pkg-path", str(fixture_pkg("H1-无清单")))
    page.click("[data-stage-path]")
    page.wait_for_selector(".banner--block")
    assert "未找到清单文件" in page.locator(".banner--block").inner_text()
    assert page.locator("#import-form .btn--primary").get_attribute("aria-disabled") == "true"
    assert not page.js_errors


def test_package_list_and_reports(live_server, clone, variants, page):  # type: ignore[no-untyped-def]
    live = live_server(clone(variants))
    page.goto(live.u("/packages"))
    rows = page.locator("#pkg-table tbody tr")
    assert rows.count() == 5
    text_all = page.locator("#pkg-table").inner_text()
    assert "P-0005" in text_all and "截面" in text_all and "阻断" in text_all
    page.click(".chip[data-filter='type:cross']")
    assert page.locator("#pkg-table tbody tr:not([hidden])").count() == 1
    # 8 bad rows → warning, all excluded line numbers listed
    page.goto(live.u("/packages/P-0001/report"))
    assert "有警告 · 可以计算" in page.locator(".banner").first.inner_text()
    page.click("#tab-warn")
    item = page.locator("[data-issue=warn]").first
    assert "上架日期" in item.inner_text() and "8 行无法解析" in item.inner_text()
    item.locator("summary").click()
    assert "102、139、176、213、250、287、324、361" in item.inner_text()
    # 10 bad rows (= 1.0%) is still a warning
    page.goto(live.u("/packages/P-0002/report"))
    assert "有警告 · 可以计算" in page.locator(".banner").first.inner_text()
    # 11 bad rows (1.1%) → block, at most 5 sample rows, compute actions disabled
    page.goto(live.u("/packages/P-0003/report"))
    banner = page.locator(".banner--block").first.inner_text()
    assert "阻断 · 不能计算" in banner
    blk = page.locator("[data-issue=block]").first.inner_text()
    assert "C1 月度类目商品" in blk and "上架日期" in blk and "102、139、176、213、250" in blk and "287" not in blk
    assert page.get_by_role("link", name="重新导入").is_visible()
    assert page.locator(".page-head__actions .btn[aria-disabled=true]").count() == 2
    # no manifest → one manifest block, nothing copied
    page.goto(live.u("/packages/P-0004/report"))
    assert "清单文件缺失" in page.locator("[data-issue=block]").first.inner_text()
    assert "未保存只读副本" in page.locator(".page-foot").inner_text()
    # X1: cross contract v1.1, missing optional C6/C7 does not block
    page.goto(live.u("/packages/P-0005/report"))
    assert "按约定 v1.1 校验" in page.locator(".page-head__sub").inner_text()
    assert "可以计算" in page.locator(".banner").first.inner_text()
    assert "缺少痛点信号" in page.locator(".banner").first.inner_text()
    assert "未提供（可选）" in page.locator("#matrix-table tr[data-file=C6]").inner_text()
    assert not page.js_errors


# ---- PAGE-F02-01 字段约定 -----------------------------------------------------------------------


def test_fields_batch_item_and_save(live_server, clone, h1a_imported, page):  # type: ignore[no-untyped-def]
    live = live_server(clone(h1a_imported))
    page.goto(live.u("/fields"))
    assert "未确认的字段不参与计算" in page.locator("[data-pending-banner]").inner_text()
    # every field shows the six contract attributes; evidence is never blank
    first = page.locator("tr[data-field-row]").first
    assert first.locator("td").count() == 10
    for cell in page.locator("tr[data-field-row] td:nth-child(8)").all_inner_texts():
        assert cell.strip()
    # select all, keep 优惠券 out, batch-confirm the 直接用 suggestions
    page.locator("[data-select-all='#field-table']").check()
    page.locator("tr[data-field='C1|优惠券'] input[data-row-check]").uncheck()
    page.click("[data-batchbar] button[data-open='#batch-modal']")
    page.click("#batch-modal button[type=submit]")
    assert "来源：批量确认" in _toast(page, "来源：批量确认")
    # after reading them, the 按规则用 fields are confirmed as suggested too (the rule fields feed 成败与信号)
    page.click(".chip[data-filter='view:rule']")
    page.locator("[data-select-all='#field-table']").click()  # selects the rows the filter shows
    page.click("[data-batchbar] button[data-open='#batch-modal']")
    page.locator("#batch-modal input[name=suggested_only]").uncheck()
    page.click("#batch-modal button[type=submit]")
    _toast(page, "来源：批量确认")
    page.wait_for_load_state("networkidle")
    # one field individually: 直接用 → 按规则用
    row = page.locator("tr[data-field='C1|品牌']")
    rid = row.get_attribute("id")
    row.locator("[data-expand]").click()
    form = page.locator(f"#edit-{rid} form")
    form.locator("input[name=usage][value='按规则用']").check()
    form.locator("input[name=rule_text]").fill("合并建议只在同品牌内提出")
    form.locator("button[value=edit]").click()
    assert "逐项" in _toast(page, "逐项")
    page.click("button[data-open='#save-modal']")
    page.wait_for_selector("#save-modal.is-open .diff", state="visible")
    diff = page.locator("#save-modal .diff").inner_text()
    assert "C1 品牌" in diff and "已确认（逐项）" in diff
    page.click("#save-modal button[type=submit]")
    assert "已保存为字段约定 v1" in _toast(page, "已保存为字段约定 v1")
    with live.app.engine.begin() as conn:
        cid = live.app.category_id()
        cv = CT.current_version(conn, cid)
        items = {(i["file_code"], i["field"]): i for i in CT.version_items(conn, cv["id"])}
        logs = conn.execute(select(D.change_log).where(D.change_log.c.object == "字段约定")).mappings().all()
    assert cv["version_no"] == 1
    assert items[("C1", "品牌")]["source"] == "逐项" and items[("C1", "品牌")]["usage"] == "按规则用"
    assert items[("C1", "月份")]["source"] == "批量确认"
    assert items[("C1", "优惠券")]["status"] == "pending"
    assert all(lg["created_by"] == "wen" and lg["created_at"] for lg in logs) and len(logs) >= 2
    page.goto(live.u("/fields"))
    assert "pending" in page.locator("tr[data-field='C1|优惠券']").get_attribute("data-view")
    assert "未确认的字段不参与计算" in page.locator("[data-pending-banner]").inner_text()
    page.click("button[data-open='#history-drawer']")
    page.wait_for_selector("#history-drawer.is-open .drawer__body", state="visible")
    assert "v1" in page.locator("#history-drawer").inner_text()
    # the excluded field never enters the computation
    SV.compute(live.app)
    with live.app.engine.begin() as conn:
        run_ = CMP.latest_run(conn, live.app.category_id(), "history")
    assert any(f["field"] == "优惠券" for f in CMP.excluded_fields(run_))
    assert not page.js_errors


def test_fields_changed_package_and_stale(live_server, clone, h1a_done, page):  # type: ignore[no-untyped-def]
    live = live_server(clone(h1a_done))
    SV.import_package(live.app, fixture_pkg("H1-字段变化"))
    page.goto(live.u("/fields"))
    pending = page.locator("tr[data-field-row][data-view*=pending]")
    names = sorted(r.get_attribute("data-field") for r in pending.all())
    assert names == ["C1|Prime价格", "C1|优惠券", "C1|促销标记"]
    page.click(".chip[data-filter='view:changed']")
    assert page.locator("tr[data-field-row]:not([hidden])").count() == 3
    # confirm the three one by one, save → results depending on the old version need recomputing
    for key in names:
        row = page.locator(f"tr[data-field='{key}']")
        rid = row.get_attribute("id")
        if page.locator(f"#edit-{rid}").get_attribute("data-collapsed") is not None:
            row.locator("[data-expand]").click()
        page.locator(f"#edit-{rid} button[value=confirm]").click()
        _toast(page, "逐项")
        page.goto(live.u("/fields"))
    page.click("button[data-open='#save-modal']")
    page.wait_for_selector("#save-modal.is-open .modal__body", state="visible")
    assert "将标为“需重算”" in page.locator("#save-modal").inner_text()
    page.click("#save-modal button[type=submit]")
    assert "需重算" in _toast(page, "需重算")
    page.goto(live.u("/"))
    assert "字段约定已保存为 v2" in page.locator(".banner--stale").inner_text()
    assert not page.js_errors


# ---- PAGE-F03-02 数据体检 -----------------------------------------------------------------------


def test_health_threshold_ack_and_fingerprints(live_server, clone, h1a_done, page):  # type: ignore[no-untyped-def]
    d = clone(h1a_done)
    live = live_server(d)
    page.goto(live.u("/settings/category"))
    page.fill("input[name='health_thresholds.first_review_early']", "0.2")
    page.click("[data-cfg-review]")
    page.wait_for_selector("#save-modal.is-open")
    page.click("#save-confirm")
    assert "品类配置 v2" in _toast(page, "品类配置 v2")
    page.goto(live.u("/health"))
    item = page.locator("li[data-check=first_review_early]")
    assert item.get_attribute("data-status") == "warn"
    assert "3 个子体" in item.inner_text() and "986" in item.inner_text()
    assert item.locator("tbody tr").count() == 3  # 8 天 counted, 7 天 not
    fam = page.locator("li[data-check=family_span]").inner_text()
    assert "1 个家族" in fam
    assert page.locator("#warn-banner").inner_text().startswith("2 项预警待知晓")
    # sample columns follow PAGE-F03-02 §5 (brand included; duplicate keys show the key value and line number)
    def heads(check: str) -> list[str]:
        return [h.strip() for h in page.locator(f"li[data-check={check}] thead th").all_text_contents()]
    assert heads("first_review_early") == ["子ASIN", "父ASIN", "品牌", "上架日期", "首次评分日期", "早于上架"]
    assert heads("family_span") == ["父ASIN", "品牌", "子体数", "最早上架", "最晚上架", "跨度"]
    assert heads("dup_key") == ["文件", "主键值", "行号"]
    dup = [c.strip() for c in page.locator("li[data-check=dup_key] tbody tr").first.locator("td").all_text_contents()]
    assert dup[0].startswith("C") and "·" in dup[1] and dup[2].isdigit()
    assert all(c.strip() not in ("", "—", "无数据") for c in
               page.locator("li[data-check=first_review_early] tbody td:nth-child(3)").all_text_contents())
    with live.app.engine.begin() as conn:  # the workbench's 待处理 list (PAGE-F03-01 reads the same function)
        todo = [t for t in VM.todo_items(conn, live.app.category_id(), "history") if t["kind"] == "health"]
    assert len(todo) == 2
    page.goto(live.u("/health"))
    page.click("button[data-open='#ack-modal-first_review_early']")
    modal = page.locator("#ack-modal-first_review_early")
    modal.locator("button[type=submit]").click()
    page.wait_for_selector("#ack-modal-first_review_early [data-error-for=note]:not(:empty)")
    assert "请填写说明" in modal.locator("[data-error-for=note]").inner_text()
    modal.locator("textarea").fill("首评日期按父体共享口径处理，只用于疑似重新上架提示")
    modal.locator("button[type=submit]").click()
    assert "已标为已知晓" in _toast(page, "已标为已知晓")
    item = page.locator("li[data-check=first_review_early]")
    assert item.get_attribute("data-status") == "acked"
    assert "说明：首评日期按父体共享口径处理" in item.inner_text()
    with live.app.engine.begin() as conn:
        ack = conn.execute(select(D.health_ack)).mappings().first()
        pkg = PK.current_package(conn, live.app.category_id(), "history")
        files = PK.files(conn, pkg["id"])
    assert ack["created_by"] == "wen" and ack["created_at"]
    with live.app.engine.begin() as conn:
        todo = [t for t in VM.todo_items(conn, live.app.category_id(), "history") if t["kind"] == "health"]
    assert len(todo) == 1 and "主键重复数" in todo[0]["title"]
    assert "指纹全部一致" in page.locator(".banner--ok").last.inner_text()
    for f in files:
        assert f["sha256"] == _sha(Path(pkg["readonly_path"]) / f["filename"])
    assert not page.js_errors


# ---- PAGE-F13-01 品类配置 -----------------------------------------------------------------------


def test_config_required_bins_and_new_version(live_server, clone, h1a_done, page):  # type: ignore[no-untyped-def]
    live = live_server(clone(h1a_done))
    page.goto(live.u("/settings/category"))
    v1_price = page.locator("input[name='bins.price']").input_value()
    # an edited field is marked 已修改 with the current version's value beneath it; undoing the edit removes both
    win = page.locator(".field:has(> input[name='success.window_months'])")
    page.fill("input[name='success.window_months']", "5")
    assert "已修改" in win.locator(".field__label .was-badge").inner_text()
    assert win.locator(".was-note").inner_text() == "v1 为 6 个月。"
    page.fill("input[name='success.window_months']", "6")
    assert win.locator(".was-badge").count() == 0 and win.locator(".was-note").count() == 0
    for name, value in (("success.bsr_max", "50"), ("success.gmv_min", "100,000"), ("success.window_months", "6"),
                        ("rising_min_parent_units", "60"), ("node", "6810202011")):
        assert page.locator(f"#cfg-form [name='{name}']").input_value() == value
    page.fill("input[name='success.gmv_min']", "")
    page.click("[data-cfg-review]")
    page.wait_for_selector("[data-error-for='success.gmv_min']:not(:empty)")
    assert page.locator("[data-error-for='success.gmv_min']").inner_text() == "必填"
    assert not page.locator("#save-modal.is-open").count()
    page.fill("input[name='success.gmv_min']", "100,000")
    page.fill("input[name='bins.price']", "<$500 / $600–900 / ≥$900")
    page.click("[data-cfg-review]")
    page.wait_for_selector("[data-error-for='bins.price']:not(:empty)")
    assert "分档有重叠或空档" in page.locator("[data-error-for='bins.price']").inner_text()
    page.fill("input[name='bins.price']", "<$400 / $400–900 / ≥$900")
    page.wait_for_timeout(800)
    page.reload()
    assert page.locator("input[name='bins.price']").input_value() == "<$400 / $400–900 / ≥$900"
    assert page.locator("#draft-banner").is_visible()
    cell = page.locator("td:has(> input[name='bins.price'])")  # table cells carry the mark too, after a reload
    assert cell.locator(".was-note").inner_text() == f"已修改v1 为 {v1_price}"
    page.click("[data-cfg-review]")
    page.wait_for_selector("#save-modal.is-open")
    diff = page.locator("#save-diff").inner_text()
    assert "价格带" in diff and "<$400" in diff
    page.fill("#save-note", "价格带下沿改为 400")
    page.click("#save-confirm")
    assert "已保存为品类配置 v2" in _toast(page, "已保存为品类配置 v2")
    with live.app.engine.begin() as conn:
        cur = CAT.current_version(conn, live.app.category_id())
        assert cur["version_no"] == 2 and cur["note"] == "价格带下沿改为 400"
        stale = CMP.stale_reasons(conn, live.app.category_id(), CMP.latest_run(conn, live.app.category_id(), "history"))
    assert "品类配置已保存为 v2" in stale
    assert "需重算" in page.locator("#stale-banner").inner_text()
    page.goto(live.u("/"))
    assert "品类配置已保存为 v2" in page.locator(".banner--stale").inner_text()
    assert not page.js_errors


def test_config_segment_dimensions_are_editable(live_server, clone, h1a_done, page):  # type: ignore[no-untyped-def]
    """PAGE-F13-01 F-02 / REQ-F13-01: the segment dimensions themselves can be changed, not only their bins."""
    live = live_server(clone(h1a_done))
    page.goto(live.u("/settings/category"))
    row = page.locator("tr[data-dim-row]").filter(has_text="柜体材质")
    picks = row.locator("[data-bins-pick] input[data-pick-value]")  # the package's values, not a free text box
    assert picks.count() >= 4 and picks.first.is_disabled()
    page.check("input[name=segdim][value='柜体材质']")
    assert picks.first.is_enabled()
    page.click("[data-cfg-review]")  # a newly selected dimension needs its bins
    page.wait_for_selector("[data-error-for='bins.柜体材质']:not(:empty)")
    for v in ("橡胶木", "MDF", "竹", "实木"):
        row.locator(f"[data-bins-pick] input[value='{v}']").check()
    page.uncheck("input[name=segdim][value='form']")
    assert page.locator("input[name='bins.form']").is_disabled()
    page.wait_for_timeout(800)
    page.click("[data-cfg-review]")
    page.wait_for_selector("#save-modal.is-open")
    diff = page.locator("#save-diff").inner_text()
    assert "宽度档 × 价格带 × 柜体材质" in diff and all(v in diff for v in ("橡胶木", "MDF", "竹", "实木"))
    page.fill("#save-note", "细分加柜体材质、去掉形态")
    page.click("#save-confirm")
    assert "已保存为品类配置 v2" in _toast(page, "已保存为品类配置 v2")
    app = live.app
    with app.engine.begin() as conn:
        dims = CAT.current_version(conn, app.category_id())["config"]["segment_dims"]
    assert [d["key"] for d in dims] == ["width", "price", "柜体材质"]
    assert SV.job_result(app, SV.compute(app))["status"] == "success"
    with app.engine.begin() as conn:
        run_ = CMP.latest_run(conn, app.category_id(), "history")
        keys = [r[0] for r in conn.execute(text("SELECT DISTINCT segment_key FROM signal_value WHERE run_id=:r"),
                                           {"r": run_["id"]})]
        demand = conn.execute(text("SELECT COUNT(*) FROM signal_value WHERE run_id=:r AND signal='demand' "
                                   "AND value IS NOT NULL"), {"r": run_["id"]}).scalar()
    assert keys and all(len(k.split("|")) == 3 for k in keys)
    assert {k.split("|")[2] for k in keys} <= {"橡胶木", "MDF", "竹", "实木", "未知"}
    assert demand > 0  # keywords still map through 宽度档; 价格带 and 柜体材质 count every bin
    assert SV.job_result(app, SV.backtest(app))["status"] == "success"
    page.goto(live.u("/signals"))
    assert "柜体材质" in page.locator("main").inner_text() or "橡胶木" in page.locator("main").inner_text()
    assert not page.js_errors


def test_new_category_from_template_and_blank(live_server, data_dir, page):  # type: ignore[no-untyped-def]
    live = live_server(data_dir)
    page.goto(live.u("/settings/category"))
    page.click("button[data-open='#new-cat-modal']")
    page.click("#new-cat-modal button[type=submit]")
    page.wait_for_selector("#new-cat-modal [data-error-for=name]:not(:empty)")
    page.fill("#nc-name", "浴室镜柜")
    page.fill("#nc-node", "1234567")
    page.click("#new-cat-modal button[type=submit]")
    page.wait_for_url(re.compile(r"category=\d+"))
    assert "浴室镜柜" in page.locator(".page-head__sub").inner_text()
    for name, value in (("site", "US"), ("success.bsr_max", "50"), ("success.gmv_min", "100,000"),
                        ("success.window_months", "6"), ("rising_min_parent_units", "60")):
        assert page.locator(f"#cfg-form [name='{name}']").input_value() == value
    page.click("[data-cfg-review]")
    page.wait_for_selector("#save-modal.is-open")
    page.click("#save-confirm")
    assert "已保存为品类配置 v1" in _toast(page, "已保存为品类配置 v1")
    # blank start: every value must be filled before v1 can be saved
    page.click("button[data-open='#new-cat-modal']")
    page.fill("#nc-name", "淋浴房")
    page.fill("#nc-node", "7654321")
    page.check("#new-cat-modal input[value=blank]")
    page.click("#new-cat-modal button[type=submit]")
    page.wait_for_selector(".page-head__sub:has-text('淋浴房')")
    assert page.locator("input[name='success.gmv_min']").input_value() == ""
    page.click("[data-cfg-review]")
    page.wait_for_selector("[data-error-for='success.gmv_min']:not(:empty)")
    assert not page.locator("#save-modal.is-open").count()
    with live.app.engine.begin() as conn:
        names = [r[0] for r in conn.execute(select(D.category.c.name).order_by(D.category.c.id))]
        assert names == ["浴室柜", "浴室镜柜", "淋浴房"]
        assert CAT.current_category_id(conn) == 1
    assert not page.js_errors


# ---- PAGE-F14-01 运行记录 -----------------------------------------------------------------------


def test_runs_first_run_and_monthly(live_server, data_dir, page):  # type: ignore[no-untyped-def]
    """FLOW-19 timing rules on recorded steps: Fri→Tue = 3 working days; 09:00→12:10 = 3 h 10 min."""
    live = live_server(data_dir)
    with live.app.engine.begin() as conn:
        cid = live.app.category_id()
        rec = lambda step, a, b, month: runs.record_step(conn, cid, step, a, b, "wen", result="完成", link="",  # noqa: E731
                                                         month=month)
        rec("导入校验", "2026-11-06 10:40:00", "2026-11-06 10:44:00", "2026-11")
        rec("回测", "2026-11-10 16:30:00", "2026-11-10 16:52:00", "2026-11")
        rec("导入校验", "2026-12-04 09:00:00", "2026-12-04 09:05:00", "2026-12")
        rec("字段确认", "2026-12-04 09:10:00", "2026-12-04 09:30:00", "2026-12")
        rec("导出", "2026-12-04 12:00:00", "2026-12-04 12:10:00", "2026-12")
    page.goto(live.u("/settings/runs"))
    first = page.locator("[data-stat=first]").inner_text()
    assert "3" in first and "个工作日" in first and "2026-11-06 → 2026-11-10" in first
    row = page.locator("#monthly-table tr[data-month='2026-12']").inner_text()
    assert "3 小时 10 分" in row and "达标" in row
    assert "达标（≤ 5 个工作日）" in page.locator("tr[data-first-run]").inner_text()
    last = page.locator("[data-stat=last]").inner_text()
    assert "2026-12" in last and "10" in last
    page.select_option("select[data-nav-select]", label="2026-12")
    page.wait_for_url(re.compile(r"month=2026-12"))
    assert page.locator("#steps-table tbody tr").count() == 3
    assert "20 分钟" in page.locator("#steps-table tr[data-step='字段确认']").inner_text()
    assert not page.js_errors


def test_runs_match_workbench(live_server, clone, h1a_done, page, tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    live = live_server(clone(h1a_done))
    with live.app.engine.begin() as conn:
        last = conn.execute(text("SELECT MAX(ended_at) FROM run_step")).scalar()
    clock_file = tmp_path / "clock.txt"  # freeze "now" so both pages measure the same elapsed time
    clock_file.write_text(last[:11] + "23:59:00", encoding="utf-8")
    monkeypatch.setenv("OPPO_CLOCK_FILE", str(clock_file))
    page.goto(live.u("/"))
    wb = page.locator("#time-title").locator("xpath=../..").locator(".stat__value").first.inner_text()
    page.goto(live.u("/settings/runs"))
    rr = page.locator("[data-stat=current] .stat__value").inner_text()
    norm = lambda s: re.sub(r"\s+", "", s)  # noqa: E731
    assert norm(wb) == norm(rr)
    steps = page.locator("#steps-table tbody tr[data-step]").all_inner_texts()
    assert any("导入" in s for s in steps) and any("回测" in s for s in steps)
    assert not page.js_errors


def test_cli_and_page_share_import_records(data_dir):  # type: ignore[no-untyped-def]
    """The service/CLI import and the page read the same records (NFR-004)."""
    app = open_dir(data_dir)
    r = SV.import_package(app, FIX / "X1")
    assert r.kind == "cross" and r.conclusion in ("pass", "warn")
    with app.engine.begin() as conn:
        pv = PK.preview(conn, app.settings, app.category_id(), FIX / "X1")
    assert pv["duplicate"]["label"] == r.label and not pv["can_import"]
    assert os.path.isdir(app.settings.packages_dir / r.label)
