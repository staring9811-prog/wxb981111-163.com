"""Browser E2E for the 新品与信号 pages (PAGE-F04-01, F04-02, F05-01, F06-01, F06-02).

Covers FLOW-04 (merge suggestions, batch confirm by basis, split, 需重算), FLOW-05 (history judgments and the
batch overview), FLOW-06 (cross judgments), FLOW-07 (signal values and the segment drawer) and FLOW-08
(cross signal columns), all through the real pages on a live local server.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

import pytest

from oppo import service as SV
from tests.conftest import Live, _prepared, open_dir, wait_job

X_SEG = "30–48″|落地式|$500–900"
EDGE_SEG = "≤30″|落地式|≥$900"  # FLOW-05 boundary products A–F


@pytest.fixture(scope="session")
def x1_done(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """X1 (cross package) imported, contract confirmed, computed and cross-backtested."""
    return _prepared(tmp_path_factory, "x1_done", ("import:X1", "confirm", "compute", "backtest:cross"))


def _cross(page, live: Live, path: str) -> None:  # type: ignore[no-untyped-def]
    page.goto(live.u("/mode/cross?next=" + quote(path)))


def _row_text(page, sel: str) -> str:  # type: ignore[no-untyped-def]
    return page.locator(sel).inner_text()


# ---- PAGE-F04-01 / PAGE-F05-01 history (FLOW-05, FLOW-04 SPU facts) --------------------------------


def test_spu_list_history_overview_and_filters(live_server, clone, h1a_done, page):  # type: ignore[no-untyped-def]
    live = live_server(clone(h1a_done))
    page.goto(live.u("/spu"))
    assert page.locator("h1").inner_text().startswith("新品与 SPU")
    assert "参照人群：起量新品（任一月父体月销 ≥ 60 件）" in page.locator(".page-head__sub").inner_text()
    # unconfirmed suggestions are announced (AC-F04-03)
    assert "3 条合并建议未确认" in page.locator("[data-banner=pending]").inner_text()
    # batch overview: 2025-09 fully judged; F (not rising) excluded in the earlier batches summary
    row = page.locator("#batch-table tr[data-batch='2025-09']")
    assert "已全部判定" in row.inner_text()
    older = page.locator("#batch-table tbody tr").last.inner_text()
    assert older.startswith("更早 8 个批次")
    assert older.split()[-1] == "1"  # 未起量（已排除）: F in 2025-06
    # F's own batch, shown when filtering on it
    page.goto(live.u("/spu?batch=2025-06"))
    assert page.locator("select[name=batch]").input_value() == "2025-06"
    # result filter: only 命中 rows
    page.goto(live.u("/spu?result=hit"))
    badges = page.locator("#spu-table tbody tr td:nth-child(5)").all_inner_texts()
    assert badges and all("命中" in b and "未命中" not in b for b in badges)
    # search by child ASIN of A, then open its detail by clicking the row
    page.goto(live.u("/spu?q=B05QSTPZ02"))
    rows = page.locator("#spu-table tbody tr")
    assert rows.count() == 1
    with page.expect_navigation():
        rows.first.locator("td").nth(2).click()
    assert "/spu/P:B05QSTPZ02" in page.url
    assert not page.js_errors


def test_spu_detail_flow05_judgments(live_server, clone, h1a_done, page):  # type: ignore[no-untyped-def]
    live = live_server(clone(h1a_done))
    # A: BSR 50 in month 6 (2025-08) by child B0C3HX7Y2L → 命中 (AC-F05-01); a child ASIN resolves to its SPU
    page.goto(live.u("/spu/B0C3HX7Y2L"))
    verdict = page.locator("[data-verdict]")
    assert verdict.get_attribute("data-verdict") == "命中"
    text = verdict.inner_text()
    assert "第 6 个月（2025-08）" in text and "B0C3HX7Y2L" in text and "≤ 50" in text
    assert page.locator("#age-grid td.b-hitcell").count() == 1
    assert "参照人群：起量新品" in page.locator(".page-foot").inner_text()
    # the boundary segment lists B (未命中), C (命中 $100,000), D (观察中), E (数据不全); F is excluded
    page.goto(live.u("/spu?segment=" + quote(EDGE_SEG)))
    statuses = page.locator("#spu-table tbody tr").evaluate_all("rs => rs.map(r => r.dataset.status)")
    assert sorted(statuses) == sorted(["命中", "未命中", "命中", "观察中", "数据不全"])
    keys = dict(zip(statuses, page.locator("#spu-table tbody tr").evaluate_all("rs => rs.map(r => r.dataset.spu)"),
                    strict=False))
    page.goto(live.u("/spu/" + quote(keys["未命中"], safe=":")))
    t = page.locator("[data-verdict]").inner_text()
    assert "未命中" in t and "51" in t and "$99,999" in t
    page.goto(live.u("/spu/" + quote(keys["观察中"], safe=":")))
    assert "还剩 1 个月" in page.locator("[data-verdict]").inner_text()
    assert page.locator("#age-grid").get_by_text("未到").count() >= 3  # month 6 not reached
    page.goto(live.u("/spu/" + quote(keys["数据不全"], safe=":")))
    t = page.locator("[data-verdict]").inner_text()
    assert "数据不全" in t and "2025-07" in t
    # C: two children $60,000 + $40,000 in month 2 → 命中 with amount $100,000 (AC-F05-02)
    page.goto(live.u("/spu?segment=" + quote(EDGE_SEG) + "&result=hit&sort=launch&dir=desc"))
    c_key = page.locator("#spu-table tbody tr").first.get_attribute("data-spu")  # C (2025-04) is newer than A
    page.goto(live.u("/spu/" + quote(c_key or "", safe=":")))
    t = page.locator("[data-verdict]").inner_text()
    assert "第 2 个月（2025-05）" in t and "$100,000" in t
    assert "$100,000" in page.locator("#kids-table tr[data-total]").inner_text()
    assert not page.js_errors


def test_spu_detail_launch_variant_relaunch(live_server, clone, h1a_done, page):  # type: ignore[no-untyped-def]
    live = live_server(clone(h1a_done))
    page.goto(live.u("/spu/B0A1VNT3QZ"))
    assert page.locator("[data-fact=launch]").inner_text() == "2025-05-03"
    assert page.locator("[data-fact=launch-child]").inner_text() == "B0A1VNT3QZ"
    assert page.locator("[data-fact=batch]").inner_text() == "2025-05"
    assert "疑似重新上架" in page.locator("h1").inner_text()
    assert "早于 SPU 上架日 2025-05-03 共 8 天" in page.locator("[data-fact=relaunch]").inner_text()
    variant_row = page.locator("#kids-table tr[data-child='B0A2VNT3QZ']")
    assert variant_row.locator("[data-new-variant]").count() == 1
    assert not page.js_errors


# ---- PAGE-F04-02 合并建议 (FLOW-04) ------------------------------------------------------------------


def test_merge_batch_confirm_reject_split_and_stale(live_server, clone, h1a_done, page):  # type: ignore[no-untyped-def]
    live = live_server(clone(h1a_done))
    page.goto(live.u("/spu/merge"))
    assert page.locator("[data-stat=pending]").inner_text().startswith("3")
    pending = page.locator("#pending-table > tbody > tr[data-sid]:not(.b-detail-row)")
    assert pending.count() == 3
    # each suggestion lists parents, child count and basis; the first comparison is expanded
    assert page.locator("#pending-table details[open]").count() == 1
    bases = page.locator("#pending-table > tbody > tr:not(.b-detail-row) td:nth-child(5)").all_inner_texts()
    assert any("五点描述相同" in b for b in bases) and any("标题主干相同" in b for b in bases)
    assert any("标题主干高度相似" in b and "且类型属性一致" in b for b in bases)
    # filter "标题主干相同", select all (only the filtered rows) and batch-confirm in the modal
    page.locator("button.chip[data-filter='basis:stem']").click()
    page.locator("input[data-select-all='#pending-table']").click()  # selects the visible (filtered) rows only
    assert page.locator(".batchbar [data-batch-count]").inner_text() == "1"
    page.locator(".batchbar button[data-open='#batch-modal']").click()
    with page.expect_navigation():
        page.locator("#batch-modal button[type=submit]").click()
    assert "tab=active" in page.url
    active = page.locator("#active-table tbody tr")
    assert active.count() == 1
    assert "批量确认" in active.first.inner_text()
    assert page.locator("[data-stat=confirmed]").inner_text().startswith("1")
    # reject one suggestion individually
    page.goto(live.u("/spu/merge"))
    first = page.locator("#pending-table > tbody > tr[data-sid]:not(.b-detail-row)").first
    with page.expect_navigation():
        first.get_by_role("button", name="拒绝").click()
    assert "已拒绝" in page.locator(".toast").first.inner_text()
    assert page.locator("[data-stat=rejected]").inner_text().startswith("1")
    # confirm the last one individually (来源 逐条确认)
    with page.expect_navigation():
        page.locator("#pending-table > tbody > tr[data-sid]:not(.b-detail-row)").first.get_by_role(
            "button", name="确认").click()
    assert "逐条确认" in page.locator(".toast").first.inner_text()
    page.goto(live.u("/spu/merge?tab=active"))
    assert page.locator("#active-table tbody tr").count() == 2
    # adding another brand's parent is refused with an inline message
    row = page.locator("#active-table tbody tr").first
    row.get_by_role("button", name="修改").click()
    page.locator("#edit-modal.is-open").wait_for()
    other_parent = page.locator("#active-table tbody tr").nth(1).locator("td").nth(1).inner_text().split()[0]
    page.locator("#edit-modal input[name=add]").fill(other_parent)
    page.locator("#edit-modal button[type=submit]").click()
    err = page.locator("#edit-modal [data-error-for=add]")
    err.wait_for(state="visible")
    assert "同品牌" in err.inner_text() or "已在归并" in err.inner_text()
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.querySelector('#edit-modal.is-open')")
    # split the first active merge: recorded, and the workbench shows 需重算 (AC-F04-05)
    code = page.locator("#active-table tbody tr").first.get_attribute("data-merge")
    page.locator("#active-table tbody tr").first.get_by_role("button", name="拆分").click()
    page.locator("#split-modal.is-open").wait_for()
    assert code in (page.locator("#split-modal .modal__title").text_content() or "")
    with page.expect_navigation():
        page.locator("#split-modal button[type=submit]").click()
    assert page.locator("#active-table tbody tr").count() == 1
    page.goto(live.u("/"))
    assert "SPU 归并已修改" in page.locator(".banner--stale").inner_text()
    page.goto(live.u("/spu"))
    assert "需重算" in page.locator("h1").inner_text()
    # the only console error is the deliberate 400 from the refused cross-brand edit
    assert [e for e in page.js_errors if "status of 400" not in e] == []


def test_merge_writes_need_token(live_server, clone, h1a_done):  # type: ignore[no-untyped-def]
    import urllib.error
    import urllib.request

    live = live_server(clone(h1a_done))
    req = urllib.request.Request(live.u("/spu/merge/decide"), data=b"ids=1&decision=confirm", method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 403


# ---- cross mode (FLOW-06, FLOW-08) ------------------------------------------------------------------


def test_spu_cross_mode(live_server, clone, x1_done, page):  # type: ignore[no-untyped-def]
    live = live_server(clone(x1_done))
    _cross(page, live, "/spu")
    assert "截面口径（近似成功线）" in page.locator(".banner--cross").inner_text()
    assert page.locator("#cross-batch-table").count() == 1 and page.locator("#batch-table").count() == 0
    note = page.locator("#cross-batch-title").locator("xpath=..").inner_text()
    assert "老品 40 个" in note
    # P: 截面命中 2026-07 at age 5 ($100,000); Q: 截面未命中, unobserved ages 1–5; old products are labelled
    page.goto(live.u("/spu?result=xhit&batch=2026-03"))
    hits = page.locator("#cross-table tbody tr").all_inner_texts()
    assert any("2026-07 · 第 5 个月" in h and "$100,000" in h for h in hits)
    page.goto(live.u("/spu?result=xmiss&batch=2026-01"))
    assert any("未观察到第 1–5 个月" in t for t in page.locator("#cross-table tbody tr").all_inner_texts())
    page.goto(live.u("/spu?result=old"))
    first = page.locator("#cross-table tbody tr").first
    assert "老品" in first.inner_text() and "不做截面判定" in first.inner_text()
    # a 截面未命中 detail page lists the unobserved ages and marks them 未观察 in the grid
    page.goto(live.u("/spu?result=xmiss&batch=2026-01"))
    with page.expect_navigation():
        page.locator("#cross-table tbody tr").first.locator("td").nth(1).click()
    t = page.locator("[data-verdict]").inner_text()
    assert "截面未命中" in t and "第 1–5 个月" in t
    assert page.locator("#age-grid").get_by_text("未观察").count() >= 10  # ages 1–5 × every metric row
    assert not page.js_errors


def test_signals_cross_mode(live_server, clone, x1_done, page):  # type: ignore[no-untyped-def]
    live = live_server(clone(x1_done))
    _cross(page, live, "/signals")
    assert page.locator("select[aria-label='月份 T']").input_value() == "2026-10"
    banner = page.locator(".banner--cross").inner_text()
    assert "截面模式不适用" in banner and "老品共 40 个" in banner and "不含评论痛点（C6）" in banner
    entry = page.locator("#sig-table tbody td[data-sig=entry]").all_inner_texts()
    assert entry and all(e == "截面模式不适用" for e in entry)
    heads = page.locator("#sig-table thead").inner_text()
    assert "单位 ASIN 贡献 · 老品" in heads or "单位 ASIN 贡献 · 老品" in page.locator("#sig-table thead").text_content()
    old_total = sum(int(m) for m in re.findall(r"老品 n=(\d+)",
                                                " ".join(page.locator("#sig-table tbody tr td:nth-child(2)").all_inner_texts())))
    assert old_total == 40
    pain = page.locator("#sig-table tbody td[data-sig=pain]").all_inner_texts()
    assert all(p == "无数据" for p in pain)
    assert not page.js_errors


# ---- PAGE-F06-01 / F06-02 history (FLOW-07) ---------------------------------------------------------


def test_signals_history_values_and_drawer(live_server, clone, h1a_done, page):  # type: ignore[no-untyped-def]
    live = live_server(clone(h1a_done))
    page.goto(live.u("/signals"))
    assert "T = 2026-03：只用 2026-03-01 之前的数据" in page.locator("[data-banner=asof]").inner_text()
    x = page.locator(f"#sig-table tbody tr[data-segment='{X_SEG}']")
    assert "+20.0%" in x.locator("td[data-sig=demand]").inner_text()
    assert "关键词 3 个" in x.locator("td[data-sig=demand]").inner_text()
    assert "37.5%" in x.locator("td[data-sig=entry]").inner_text()
    assert "命中 9 / 已判定 24" in x.locator("td[data-sig=entry]").inner_text()
    assert "12.5%" in x.locator("td[data-sig=pain]").inner_text() and "25 / 200" in x.locator("td[data-sig=pain]").inner_text()
    assert "8.0%" in x.locator("td[data-sig=hslr]").inner_text() and "2 个商品" in x.locator("td[data-sig=hslr]").inner_text()
    cand = {k: x.locator(f"td[data-sig={k}]").text_content() for k in ("unit_asin", "premium", "trend", "low_score")}
    assert cand["unit_asin"].startswith("40.0 件") and "候选" in cand["unit_asin"]
    assert cand["premium"].startswith("+10.0%") and cand["trend"].startswith("+2.0 个百分点")
    assert cand["low_score"].startswith("8.0%")
    assert "回填 1%" in x.inner_text()
    # a segment missing a keyword month shows 无数据, never 0
    missing = page.locator("#sig-table tbody tr[data-segment^='≥48″|悬浮式'] td[data-sig=demand]").first
    assert missing.inner_text() == "无数据"
    # evidence tag popover shows field, file, version and record counts (RULE-03)
    x.locator("td[data-sig=demand] button.etag").click()
    page.locator(".popover.is-open").wait_for()
    pop = page.locator(".popover.is-open").text_content() or ""
    assert "C5 关键词月度" in pop and "P-0001" in pop and "1,200 / 1,000" in pop
    page.keyboard.press("Escape")
    # click the row → drawer opens in place, URL carries the segment; Esc closes and restores the URL
    page.evaluate("window.scrollTo(0, 200)")
    x.locator("td").nth(1).click()
    drawer = page.locator("#seg-drawer.is-open")
    drawer.wait_for()
    assert "30–48″" in drawer.locator(".drawer__title").inner_text()
    assert "segment=" in page.url
    assert "+20.0%" in drawer.locator("tr[data-sig=demand]").inner_text()
    assert "命中 9 / 已判定 24" in drawer.locator("tr[data-sig=entry]").inner_text()
    assert "柜体材质" in drawer.inner_text() and "颜色、尺寸、盆数" in drawer.inner_text()
    assert drawer.locator("svg.spark").count() >= 1
    assert "S0" in drawer.locator(".hbars").inner_text()  # structural pain codes breakdown
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.querySelector('#seg-drawer.is-open')")
    assert "segment=" not in page.url
    assert page.evaluate("window.scrollY") >= 150
    # opening by URL renders the drawer on load
    page.goto(live.u("/signals?month=2026-03&segment=" + quote(X_SEG)))
    page.locator("#seg-drawer.is-open").wait_for()
    assert not page.js_errors


def test_signals_empty_then_compute(live_server, clone, h1a_imported, page):  # type: ignore[no-untyped-def]
    d = clone(h1a_imported)
    app = open_dir(d)
    SV.contract_confirm(app)
    live = live_server(d)
    page.goto(live.u("/signals"))
    assert "还没有信号结果" in page.locator(".empty__title").inner_text()
    page.get_by_role("button", name="运行计算").click()
    wait_job(live, timeout=600)
    page.wait_for_url(re.compile(r"toast="), timeout=60000)
    assert page.locator("#sig-table tbody tr").count() > 5
    assert not page.js_errors
