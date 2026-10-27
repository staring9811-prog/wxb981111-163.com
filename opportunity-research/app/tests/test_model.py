"""变量关系模型: finds the relationships planted in M1-真相, keeps the ladder honest, and only people adopt rules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oppo import service as SV
from oppo.core import model as M
from oppo.core import rules as RULES
from tests.conftest import fixture_pkg, open_dir


@pytest.fixture(scope="session")
def mock_done(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """M1-真相 imported, confirmed, computed, backtested and modelled."""
    d = tmp_path_factory.mktemp("mock_done")
    app = open_dir(d)
    SV.import_package(app, fixture_pkg("M1-真相"))
    SV.contract_confirm(app)
    SV.compute(app)
    SV.backtest(app)
    SV.model_run(app)
    app.engine.dispose()
    SV._apps.pop(str(d.resolve()), None)
    return d


def _result(app: SV.App) -> dict:
    with app.engine.begin() as conn:
        return M.latest(conn, app.category_id(), "history")["result"]


def test_model_recovers_planted_truths(clone, mock_done):  # type: ignore[no-untyped-def]
    app = open_dir(clone(mock_done))
    r = _result(app)
    truth = json.loads((fixture_pkg("M1-真相") / "真相.json").read_text(encoding="utf-8"))
    assert r["simulated"] and r["n_pool"] >= truth["样本"]["已判定新 SPU"] - 5
    assert r["verdict"] == "effective" and r["splits"]["test"] and r["splits"]["calib"]
    eff = {(e["var"], e["value"]): e for e in r["effects"]}
    # 1. the strongest segment: width 30–48″ carries a stable positive effect
    assert eff[("seg:width", "30–48″")]["stable"] and eff[("seg:width", "30–48″")]["or_lo"] > 1
    # 2. direct attribute effect: 一体盆 OR well above 1, interval excludes 1, consistent across windows
    top = eff[("attr:台面形态", "一体盆")]
    assert top["or"] > 1.8 and top["or_lo"] > 1 and top["stable"]
    # 3. spurious via FBA: 实木 is not stable once 配送方式 is controlled (interval covers 1)
    wood = eff[("attr:柜体材质", "实木")]
    assert wood["or_lo"] <= 1 <= wood["or_hi"] and not wood["stable"]
    # 4. colour carries nothing: no colour is stable
    assert not any(e["stable"] for (v, _), e in eff.items() if v == "attr:颜色")
    imp = {i["var"]: i["importance"] for i in r["importance"]}
    assert imp["attr:台面形态"] > imp.get("attr:颜色", 0)
    # rules: the top rule names 一体盆 and is graded 高 with its interval above the test base
    best = r["rules"][0]
    assert best["tier"] == "高" and "一体盆" in best["text"] and best["test"]["lo"] > best["test"]["base"]
    assert all(len(x["conds"]) <= M.MAX_RULE_CONDS for x in r["rules"])
    assert not any(x["tier"] == "高" and all(c["key"] == "颜色" for c in x["conds"]) for x in r["rules"])
    # paths: segment-level signals are functions of the segment dims (R² ≈ 1), early trajectory is 事后
    paths = {p["key"]: p for p in r["paths"]}
    assert paths["demand"]["r2_x"] > 0.9 and paths["units_m1"]["timing"] == "事后"
    # strategy-library rules are scored on the same rows
    assert r["library"] and all("test" in x and "fit" in x for x in r["library"])
    # combinations point at products: the planted 一体盆 shows up in the best combos, not a colour-only combo
    combo = r["combos"]
    assert combo and combo["good"] and r["combo_vars"]
    assert any("一体盆" in c["text"] for c in combo["good"][:5])
    assert not any(c["tier"] == "高" and all(v == "attr:颜色" for v in c["vars"]) for c in combo["good"])
    assert all(c["test"]["lift"] > 1 and c["fit"]["lift"] > 1 for c in combo["good"])
    with open_dir(clone(mock_done)).engine.begin() as conn2:
        picked = M.combos_for(conn2, app.category_id(), "history", ["attr:台面形态", "seg:width", "seg:price"])
    assert picked["variables"] == ["attr:台面形态", "seg:width", "seg:price"] and picked["n_combos"] > 0
    # logic tree: Y → M (|log OR|) → X (single-variable R² share); importance per model for the picker
    tree = r["tree"]
    assert tree["process"] and tree["process"][0]["strength"] >= tree["process"][-1]["strength"]
    demand = next(p for p in tree["process"] if p["key"] == "demand")
    assert demand["children"] and demand["children"][0]["strength"] > 0.5  # a segment-level signal: segment dims explain it
    assert set(r["importance_by"]) == set(r["model1"]["models"]) and set(tree["direct"]) == set(r["importance_by"])


def test_adopt_is_person_only_and_recorded(clone, mock_done):  # type: ignore[no-untyped-def]
    app = open_dir(clone(mock_done))
    with app.engine.begin() as conn:
        cid = app.category_id()
        mr = M.latest(conn, cid, "history")
        before = len(RULES.list_current(conn, cid))
    rid = SV.model_adopt(app, mr["id"], 0)
    with app.engine.begin() as conn:
        rule = RULES.current(conn, rid)
        assert rule["origin"] == "模型发现" and rule["status"] == "历史观察" and rule["basis"]["model_run"] == mr["id"]
        assert rule["conds"] == [{k: v for k, v in c.items() if k != "label"} for c in mr["result"]["rules"][0]["conds"]]
        assert len(RULES.list_current(conn, cid)) == before + 1
        with pytest.raises(M.ModelError):
            M.adopt(conn, cid, mr["id"], 99, "wen")
    # a second model run on unchanged data is not stale; a new compute run makes it stale
    with app.engine.begin() as conn:
        assert M.stale_reasons(conn, cid, M.latest(conn, cid, "history")) == []
    SV.compute(app)
    with app.engine.begin() as conn:
        assert "成败与信号已重算" in M.stale_reasons(conn, cid, M.latest(conn, cid, "history"))


def test_variables_page_v2_and_adopt_button(live_server, clone, mock_done, page):  # type: ignore[no-untyped-def]
    live = live_server(clone(mock_done))
    page.goto(live.u("/variables"))
    assert page.locator("h1").inner_text() == "变量关系"
    assert "找到稳定关系" in page.locator(".stats").inner_text()
    assert page.locator("#m1-title").is_visible() and page.locator("#m2-title").is_visible()
    assert page.locator("#rule-table tbody tr").count() >= 2
    assert "模拟数据" in page.locator(".banner--warn").first.inner_text()
    # X | M | Y side by side, the logic tree, and the model picker switching the importance panel
    cols = page.locator(".vr-flow .panel__title").all_inner_texts()
    assert cols == ["可控变量 X", "过程指标 M", "结果变量 Y"]
    assert page.locator("svg.vr-tree path.edge").count() >= 5
    widths = [float(w) for w in page.locator("svg.vr-tree path.edge").evaluate_all("els => els.map(e => e.getAttribute('stroke-width'))")]
    assert max(widths) > min(widths)
    # combination section, left TOC highlighting, 简明/详细 switch
    assert page.locator("#combo-table tbody tr").count() >= 3 and "★" in page.locator("#combo-table").inner_text()
    assert page.locator(".vr-toc a.is-active").count() == 1
    assert page.locator("#cmp-title").is_hidden()  # statistics panel hidden in 简明
    page.locator('[data-vr-view] [data-view="detail"]').click()
    assert page.locator("#cmp-title").is_visible()
    page.locator('[data-vr-view] [data-view="simple"]').click()
    page.evaluate("document.getElementById('combo-title').scrollIntoView({block: 'start'})")
    page.wait_for_timeout(500)
    assert "组合" in page.locator(".vr-toc a.is-active").inner_text()
    page.locator('input[name="combo"][value="attr:颜色"]').uncheck()
    page.locator('input[name="combo"][value="seg:price"]').check()
    page.locator("[data-combo-submit]").click()
    page.wait_for_url("**combo=*")
    assert "价格带" in page.locator("#combo-table").inner_text() or "$" in page.locator("#combo-table").inner_text()
    page.locator('[data-model-picker] [data-model="tree"]').click()
    assert page.locator('[data-model-panel="tree"]:not([hidden])').count() >= 1
    assert page.locator('[data-model-panel="logit"]:not([hidden])').count() == 0
    page.locator('#rule-table [data-post="/variables/adopt"]').first.click()
    page.wait_for_url("**toast=*")
    assert "已采纳" in page.locator("#rule-table").inner_text()
    page.goto(live.u("/rules"))
    assert "模型发现" in page.locator(".filters").inner_text()
    assert not page.js_errors


def test_model_without_compute_is_refused(clone, h1a_imported):  # type: ignore[no-untyped-def]
    app = open_dir(clone(h1a_imported))
    with pytest.raises(M.ModelError):
        SV.model_run(app)


def test_cli_model(clone, mock_done, capsys):  # type: ignore[no-untyped-def]
    from oppo import cli

    d = clone(mock_done)
    argv = ["--data-dir", str(d)]
    assert cli.main(argv + ["model", "show"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "找到稳定关系" and out["rules"]
    assert cli.main(argv + ["model", "adopt", "--index", "0", "--note", "测试采纳"]) == 0
    assert "已采纳" in capsys.readouterr().out
    assert cli.main(argv + ["model", "run"]) == 0
    assert "模型完成" in capsys.readouterr().out
