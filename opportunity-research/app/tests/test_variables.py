"""变量关系 page and the bins pick-list / control-variable settings on 品类配置."""

from __future__ import annotations

from sqlalchemy import text

from oppo.core import backtest as BT
from oppo.core import categories as CAT
from oppo.core import variables as VARS
from tests.conftest import open_dir


def test_variables_analysis_on_prepared_data(clone, h1a_done):  # type: ignore[no-untyped-def]
    app = open_dir(clone(h1a_done))
    with app.engine.begin() as conn:
        cid = app.category_id()
        va = VARS.analysis(conn, cid, "history")
    assert va["run"] is not None and va["n_pool"] >= 10 and 0 < va["n_hit"] < va["n_pool"]
    assert [p["key"] for p in va["process"]] == list(BT.SIG.SIGNALS + BT.SIG.CURRENT)
    assert {e["signal"] for e in va["process_effects"]} == set(BT.SIG.SIGNALS)
    assert any(e["after"] is not None for e in va["process_effects"])
    dims = {a["dim"]: a for a in va["attribute_effects"]}
    assert "形态" in dims and dims["形态"]["is_segment_dim"]
    form = dims["形态"]["values"]
    assert sum(r["n"] for r in form) == va["n_pool"]
    big = [r for r in form if r["n"] >= VARS.MIN_VALUE_N and not r["unknown"]]
    assert big and all(r["or_after"] is not None and r["lo"] is not None for r in big)
    assert va["selected_controls"] == list(CAT.CONTROL_VARS)


def test_controls_setting_changes_effects(clone, h1a_done):  # type: ignore[no-untyped-def]
    app = open_dir(clone(h1a_done))
    with app.engine.begin() as conn:
        cid = app.category_id()
        cfg = CAT.current_version(conn, cid)["config"]
        full = VARS.analysis(conn, cid, "history")
        CAT.set_path(cfg, "controls", "brand_prior_hit、fba")
        assert cfg["controls"] == ["brand_prior_hit", "fba"] and CAT.get_path(cfg, "controls") == "brand_prior_hit、fba"
        CAT.save_version(conn, cid, cfg, "wen", "少控制")
        fewer = VARS.analysis(conn, cid, "history")
    assert fewer["selected_controls"] == ["brand_prior_hit", "fba"]
    a = {e["signal"]: e["after"] for e in full["process_effects"] if e["after"] is not None}
    b = {e["signal"]: e["after"] for e in fewer["process_effects"] if e["after"] is not None}
    assert a and any(abs(a[k] - b[k]) > 1e-9 for k in a if k in b)
    import pytest

    with pytest.raises(ValueError):
        CAT.set_path(cfg, "controls", "weather")
    # configs saved before the field existed read as the full set
    assert CAT.controls_of({k: v for k, v in cfg.items() if k != "controls"}) == list(CAT.CONTROL_VARS)


def test_variables_page_and_bins_picklist(live_server, clone, h1a_done, page):  # type: ignore[no-untyped-def]
    live = live_server(clone(h1a_done))
    page.goto(live.u("/variables"))
    assert page.locator("h1").inner_text() == "变量关系"
    assert page.locator("table").count() >= 2
    assert "BSR" in page.locator("section[aria-labelledby=out-title] dl").inner_text()
    assert not page.js_errors
    # 品类配置: category dimensions pick bins from the package's values; width stays a text range
    page.goto(live.u("/settings/category"))
    row = page.locator("tr[data-dim-row]").filter(has_text="形态")
    assert row.locator("[data-bins-pick] input[data-pick-value]").count() >= 2
    assert row.locator("[data-bins-pick] input[data-pick-value]:checked").count() == 2  # 落地式 / 悬浮式
    width = page.locator("tr[data-dim-row]").filter(has_text="宽度档")
    assert width.locator('input.input[name="bins.width"]').count() == 1
    # pick every value of 颜色 as a segment dimension; the hidden bins field follows the ticks
    basin = page.locator("tr[data-dim-row]").filter(has_text="颜色")
    basin.locator("input[data-segdim]").check()
    basin.locator("[data-pick-all]").check()
    picked = basin.locator("[data-bins-pick] input[data-pick-value]:checked").count()
    assert picked >= 2 and basin.locator('input[name="bins.颜色"]').input_value().count(" / ") == picked - 1
    page.locator('input[name="ctrl"][value="month_idx"]').uncheck()
    page.wait_for_timeout(800)  # draft autosave
    with live.app.engine.begin() as conn:
        cid = live.app.category_id()
        draft = conn.execute(text("SELECT config_json FROM category_draft WHERE category_id=:c"), {"c": cid}).scalar()
    assert draft and "海军蓝" in draft and '"controls":["brand_prior_hit","price_pos","variant_count","fba","relaunch"]' in draft
    assert not page.js_errors
