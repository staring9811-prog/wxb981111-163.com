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
