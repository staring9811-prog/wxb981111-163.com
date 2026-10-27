"""Workbench renders on an empty and a prepared database; writes need the start token."""

from __future__ import annotations

import urllib.error
import urllib.request

from tests.conftest import Live


def _post(live: Live, path: str, headers: dict[str, str]) -> int:
    req = urllib.request.Request(live.u(path), data=b"", method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_workbench_empty(live_server, data_dir, page):  # type: ignore[no-untyped-def]
    live = live_server(data_dir)
    page.goto(live.u("/"))
    assert page.locator("h1").inner_text() == "本月工作台"
    assert page.get_by_text("导入第一个数据包").first.is_visible()
    assert not page.js_errors


def test_workbench_done(live_server, clone, h1a_done, page):  # type: ignore[no-untyped-def]
    live = live_server(clone(h1a_done))
    page.goto(live.u("/"))
    assert "2026-03 月更" in page.locator(".page-head__sub").inner_text()
    assert page.locator(".step").count() == 8
    assert page.locator("table.table tbody tr").count() == 5
    assert not page.js_errors


def test_write_requires_token(live_server, data_dir):  # type: ignore[no-untyped-def]
    live = live_server(data_dir)
    assert _post(live, "/jobs/compute", {}) == 403
    assert _post(live, "/jobs/compute", {"X-Oppo-Token": live.token, "Origin": "http://evil.example"}) == 403


def test_data_dir_with_percent_and_chinese(tmp_path):  # type: ignore[no-untyped-def]
    """Windows URLs carry %5C; a data path with % or Chinese must still migrate (found on the Windows runner)."""
    from tests.conftest import open_dir

    app = open_dir(tmp_path / "机会判定台 100%" / "data")
    assert app.category_id() > 0


def test_workbench_lists_health_warning_with_evidence(live_server, clone, h1a_done, page):  # type: ignore[no-untyped-def]
    """FLOW-03 on the workbench itself: a warning with value, threshold and an evidence tag (n=)."""
    from oppo.core import categories as CAT

    live = live_server(clone(h1a_done))
    with live.app.engine.begin() as conn:
        cid = live.app.category_id()
        cfg = CAT.current_version(conn, cid)["config"]
        cfg["health_thresholds"]["first_review_early"] = 0.1
        CAT.save_version(conn, cid, cfg, "wen", "测试：降低首评阈值")
    page.goto(live.u("/"))
    item = page.locator('li[data-todo="health"]').filter(has_text="首次评分早于上架")
    assert item.count() == 1
    text = item.inner_text()
    assert "0.3%" in text and "阈值 0.1%" in text and "n=986" in text
    item.locator("button.etag").click()
    from playwright.sync_api import expect

    expect(page.locator(".popover.is-open")).to_contain_text("分母")
    assert not page.js_errors
