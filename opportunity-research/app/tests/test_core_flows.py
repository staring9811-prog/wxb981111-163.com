"""Service-level acceptance of the computations (FLOW-04/05/06/07/08/09/10/11/12). Expected values come from the
sample-package documents (fixtures/packages/*.说明.md), which were worked out by hand from the confirmed rules."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from oppo import db as D
from oppo import service as SV
from oppo.core import backtest as BT
from oppo.core import compute as CMP
from oppo.core import judge as J
from oppo.core import ranking as RK
from oppo.core import spu as SPU
from tests.conftest import _prepared, open_dir

X = "30–48″|落地式|$500–900"
Y = "30–48″|落地式|<$500"


def _close(app: SV.App) -> None:
    app.engine.dispose()
    SV._apps.pop(str(app.settings.data_dir.resolve()), None)


@pytest.fixture(scope="module")
def h1(h1a_done: Path):  # type: ignore[no-untyped-def]
    app = open_dir(h1a_done)
    with app.engine.begin() as conn:
        cid = app.category_id()
        run_ = CMP.latest_run(conn, cid, "history")
        spus = CMP.spus_frame(conn, run_["id"])
        sig = CMP.signals_frame(conn, run_["id"], "2026-03")
        seg = CMP.segments_frame(conn, run_["id"], "2026-03")
        bt = BT.latest(conn, cid, "history")
        snap = RK.latest_snapshot(conn, cid, "history")
        sugg = SPU.suggestions(conn, cid)
    yield {"app": app, "spus": spus, "sig": sig, "seg": seg, "bt": bt, "snap": snap, "sugg": sugg, "run": run_}
    _close(app)


def _one(spus: pd.DataFrame, brand: str) -> pd.Series:
    rows = spus[spus["brand"] == brand]
    assert len(rows) == 1, f"{brand}: {len(rows)} SPU"
    return rows.iloc[0]


def _sig(sig: pd.DataFrame, seg: str, name: str) -> pd.Series:
    rows = sig[(sig["segment_key"] == seg) & (sig["signal"] == name)]
    assert len(rows) == 1
    return rows.iloc[0]


# ---- FLOW-05 -------------------------------------------------------------------------------------


def test_flow05_success_line(h1) -> None:  # type: ignore[no-untyped-def]
    s = h1["spus"]
    a = _one(s, "Kingsman")
    assert (a["status"], a["hit_month"], a["hit_child"]) == (J.HIT, "2025-08", "B0C3HX7Y2L")
    b = _one(s, "Belvedere")
    assert b["status"] == J.MISS and b["best_bsr"] == 51 and b["max_sales"] == 99999
    c = _one(s, "Mirabelle")
    assert (c["status"], c["hit_month"], c["hit_amount"]) == (J.HIT, "2025-05", 100000)
    d = _one(s, "Monterey")
    assert d["status"] == J.WATCH and d["remaining"] == 1
    e = _one(s, "Aquadom")
    assert e["status"] == J.INCOMPLETE and json.loads(e["missing_months_json"]) == ["2025-07"]
    f = _one(s, "Blossom")
    assert f["rising"] == 0
    batch06 = s[(s["batch"] == "2025-06") & (s["is_new"] == 1)]
    assert int((batch06["rising"] == 0).sum()) == 1


# ---- FLOW-04 -------------------------------------------------------------------------------------


def test_flow04_launch_variant_relaunch(h1) -> None:  # type: ignore[no-untyped-def]
    s = h1["spus"]
    p = _one(s, "Puluomis")
    assert (p["launch_date"], p["launch_child"], p["batch"]) == ("2025-05-03", "B0A1VNT3QZ", "2025-05")
    assert p["new_variant_count"] == 1 and p["relaunch"] == 1
    hx = _one(s, "HOMLUX")
    assert hx["relaunch"] == 0
    # 未确认任何建议：SOLIDEE 两个父体各算一个 SPU
    assert len(s[s["brand"] == "SOLIDEE"]) == 2


def test_flow04_suggestion_bases(h1) -> None:  # type: ignore[no-untyped-def]
    by_brand = {x["brand"]: x["basis"] for x in h1["sugg"]}
    assert by_brand["SOLIDEE"] == "标题主干相同"
    assert by_brand["Eclife"] == "五点描述相同"
    assert by_brand["Woodbridge"] == "标题主干高度相似且类型属性一致"
    for x in h1["sugg"]:
        assert len(x["parents"]) >= 2 and x["child_count"] >= 2


def test_flow04_variants_spu_numbers_and_no_bullets(tmp_path_factory) -> None:  # type: ignore[no-untyped-def]
    d1 = _prepared(tmp_path_factory, "spu_no", ("import:H1-SPU编号", "confirm"))
    d2 = _prepared(tmp_path_factory, "no_bullets", ("import:H1-无五点", "confirm"))
    for d, check in ((d1, "spu_no"), (d2, "no_bullets")):
        app = open_dir(d)
        with app.engine.begin() as conn:
            sugg = SPU.suggestions(conn, app.category_id())
        _close(app)
        if check == "spu_no":
            assert sugg == []
        else:
            assert sugg and all(x["basis"] != "五点描述相同" for x in sugg)


# ---- FLOW-07 -------------------------------------------------------------------------------------


def test_flow07_signals_x(h1) -> None:  # type: ignore[no-untyped-def]
    sig = h1["sig"]
    dm = _sig(sig, X, "demand")
    assert dm["value"] == pytest.approx(0.20) and (dm["num"], dm["den"], dm["cnt"]) == (1200, 1000, 3)
    assert pd.isna(_sig(sig, "≥48″|悬浮式|$500–900", "demand")["value"])
    en = _sig(sig, X, "entry")
    assert en["value"] == pytest.approx(0.375) and (en["num"], en["den"]) == (9, 24)
    pn = _sig(sig, X, "pain")
    assert pn["value"] == pytest.approx(0.125) and (pn["num"], pn["den"]) == (25, 200)
    hs = _sig(sig, X, "hslr")
    assert hs["value"] == pytest.approx(0.08) and (hs["num"], hs["den"], hs["cnt"]) == (320, 4000, 2)
    assert _sig(sig, X, "unit_asin")["value"] == pytest.approx(40.0)
    assert _sig(sig, X, "premium")["value"] == pytest.approx(0.10)
    assert _sig(sig, X, "trend")["value"] == pytest.approx(2.0)  # stored in percentage points
    assert _sig(sig, X, "low_score")["value"] == pytest.approx(0.08)
    seg = h1["seg"].set_index("segment_key")
    assert seg.loc[X, "backfill_share"] == pytest.approx(0.01)
    assert "30–48″|未知|$500–900" in seg.index


# ---- FLOW-09 -------------------------------------------------------------------------------------


def test_flow09_history_backtest(h1) -> None:  # type: ignore[no-untyped-def]
    bt = h1["bt"]
    r = bt["result"]
    assert r["split"] == {"rule": ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06"],
                          "test": ["2025-07", "2025-08", "2025-09"]}
    assert len(r["effective"]) == 10 and r["k"] == 2
    card = r["card"]
    assert (card["top_hits"], card["top_n"], card["all_hits"], card["all_n"]) == (24, 40, 60, 300)
    assert round(card["ci"][0], 3) == 0.470 and round(card["ci"][1], 3) == 0.717
    assert round(card["multiple"], 2) == 3.00
    assert card["mult_ci"][0] <= 3.0 <= card["mult_ci"][1]
    for name, cur in r["current"].items():
        assert cur["top_hits"] <= 10 and cur["top_n"] == 40, name
    assert bt["conclusion"] == "达标"
    assert r["limitation"] == "广告投入、站外引流未纳入"
    assert {f["field"] for f in r["rejected_fields"]} >= {"当月价格"}
    assert len(BT.CONFOUNDERS) == 6
    assert {c["signal"] for c in r["confounders"]} >= {"demand", "pain", "hslr"}
    acts = sorted((x["action"], json.dumps(x["conds"], sort_keys=True)) for x in r["rules"])
    assert [a for a, _ in acts] == sorted(["立项候选", "观察", "放弃"])
    cand = next(x for x in r["rules"] if x["action"] == "立项候选")
    assert cand["conds"] == [{"key": "demand", "kind": "signal", "op": ">=", "value": 0.15}]


def test_flow09_rules_are_history_observation(h1) -> None:  # type: ignore[no-untyped-def]
    from oppo.core import rules as RULES

    app = h1["app"]
    with app.engine.begin() as conn:
        rs = RULES.list_current(conn, app.category_id())
    gen = [r for r in rs if r["origin"] == "回测"]
    assert len(gen) == 3 and all(r["status"] == "历史观察" for r in gen)


# ---- FLOW-12 -------------------------------------------------------------------------------------

# 合并建议都未确认时 30–48″·悬浮式·<$500 为 8 个（说明文档：只确认“标题主干相同”后为 7）
EXPECTED_ORDER = [
    ("30–48″|落地式|$500–900", 44), ("30–48″|落地式|<$500", 42), ("≤30″|落地式|<$500", 70),
    ("30–48″|悬浮式|$500–900", 67), ("≥48″|落地式|$500–900", 66), ("≥48″|落地式|<$500", 30),
    ("≥48″|落地式|≥$900", 25), ("≤30″|悬浮式|$500–900", 65), ("≤30″|悬浮式|<$500", 22),
    ("≤30″|悬浮式|≥$900", 22), ("≤30″|落地式|$500–900", 19), ("≤30″|落地式|≥$900", 3), ("30–48″|悬浮式|<$500", 8),
]


def test_flow12_ranking_order_and_repeatability(h1) -> None:  # type: ignore[no-untyped-def]
    rows = h1["snap"]["content"]["rows"]
    assert [(r["segment_key"], r["sample"]) for r in rows] == EXPECTED_ORDER
    assert [r["effective"] for r in rows] == [True] * 10 + [False] * 3
    app = h1["app"]
    with app.engine.begin() as conn:
        again = RK.build_rows(conn, app.category_id(), "history")
    assert D.dumps(again["rows"]) == D.dumps(rows)
    assert h1["snap"]["content"]["top20"]["segments"] == [X, Y]
    assert h1["snap"]["label"] == "2026-03 · 第 1 版"


# ---- FLOW-06 / FLOW-08 / FLOW-11 (截面) -----------------------------------------------------------


@pytest.fixture(scope="module")
def x1(tmp_path_factory):  # type: ignore[no-untyped-def]
    from fixtures.build_samples import X1

    d = _prepared(tmp_path_factory, "x1", ("import:X1", "confirm", "compute", "backtest:cross"))
    spec = X1()
    spec.assemble("X1")
    app = open_dir(d)
    with app.engine.begin() as conn:
        cid = app.category_id()
        run_ = CMP.latest_run(conn, cid, "cross")
        out = {"spus": CMP.spus_frame(conn, run_["id"]), "sig": CMP.signals_frame(conn, run_["id"], run_["t_month"]),
               "run": run_, "bt": BT.latest(conn, cid, "cross"), "special": spec.special}
    yield out
    _close(app)


def _by_child(spus: pd.DataFrame, child: str) -> pd.Series:
    rows = spus[spus["launch_child"] == child]
    assert len(rows) == 1
    return rows.iloc[0]


def test_flow06_cross_judgment(x1) -> None:  # type: ignore[no-untyped-def]
    s, sp = x1["spus"], x1["special"]
    p = _by_child(s, sp["P"][0].asin)
    assert (p["status"], p["hit_month"], p["hit_age"]) == (J.X_HIT, "2026-07", 5)
    q = _by_child(s, sp["Q"][0].asin)
    assert q["status"] == J.X_MISS and json.loads(q["unobserved_ages_json"]) == [1, 2, 3, 4, 5]
    r = _by_child(s, sp["R"][0].asin)
    assert r["status"] == J.WATCH
    old = s[s["launch_child"] == sp["S"].asin]
    assert len(old) == 1 and old.iloc[0]["status"] == J.OLD


def test_flow08_cross_signals(x1) -> None:  # type: ignore[no-untyped-def]
    sig, run_ = x1["sig"], x1["run"]
    assert run_["t_month"] == "2026-10"
    entry = sig[sig["signal"] == "entry"]
    assert len(entry) and entry["value"].isna().all() and (entry["flag"] == "截面模式不适用").all()
    ua = sig[sig["signal"] == "unit_asin"]
    assert int(ua["extra_json"].map(lambda e: (json.loads(e) or {}).get("old") or 0).sum()) == 40
    for name in ("pain", "hslr", "low_score", "trend"):
        assert sig[sig["signal"] == name]["value"].isna().all(), name
    dm = sig[sig["signal"] == "demand"].set_index("segment_key")["value"]
    assert dm[[k for k in dm.index if k.startswith("30–48″|落地式")]].notna().all()
    assert dm[[k for k in dm.index if k.startswith("≥48″|悬浮式")]].isna().all()


def test_flow11_cross_backtest(x1) -> None:  # type: ignore[no-untyped-def]
    bt = x1["bt"]
    r = bt["result"]
    assert r["split"] == {"rule": ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"],
                          "test": ["2026-07", "2026-08", "2026-09"]}
    assert (r["rows"]["model"], r["rows"]["test"]) == (431, 213)
    assert len(r["effective"]) == 5 and r["k"] == 1
    card = r["card"]
    assert (card["top_hits"], card["top_n"]) == (10, 22)
    assert (card["all_hits"], card["all_n"]) == (16, 106)
    assert round(card["multiple"], 2) == 3.01
    assert bt["conclusion"] == "达标（截面）"
    cells = r["age_table"]["≥48″|悬浮式|$500–900"]
    assert cells and all(c["n"] < 5 for c in cells.values())  # shown as 样本过少


# ---- FLOW-10 -------------------------------------------------------------------------------------


@pytest.mark.parametrize("pkg,mode,conclusion,reason", [
    ("H1-两批次", "history", "未达标", "数据不足"),
    ("H1-有效4", "history", "未达标", "细分样本不足"),
    ("H1-无区分度", "history", "未达标", "信号无区分度"),
    ("X1-无老品", "cross", "未达标", "数据不足"),
])
def test_flow10_unverified_reasons(tmp_path_factory, pkg, mode, conclusion, reason) -> None:  # type: ignore[no-untyped-def]
    d = _prepared(tmp_path_factory, "f10", (f"import:{pkg}", "confirm", "compute", f"backtest:{mode}"))
    app = open_dir(d)
    with app.engine.begin() as conn:
        bt = BT.latest(conn, app.category_id(), mode)
        from oppo.core import cards as CARD

        card = CARD.current_card(conn, app.category_id(), mode)
    _close(app)
    assert bt["conclusion"] == conclusion and bt["reason_class"] == reason
    assert card["status"] == "未验证"
    if pkg == "H1-两批次":
        assert "已判定批次 2 个" in bt["result"]["reason_text"]
        assert not bt["result"].get("split", {}).get("test")


def test_flow10_sample_19_vs_20(tmp_path_factory) -> None:  # type: ignore[no-untyped-def]
    """H1-样本19: ≤30″·悬浮式·≥$900 has 19 test-group SPUs, ≤30″·悬浮式·<$500 exactly 20."""
    d = _prepared(tmp_path_factory, "s19", ("import:H1-样本19", "confirm", "compute", "backtest"))
    app = open_dir(d)
    with app.engine.begin() as conn:
        bt = BT.latest(conn, app.category_id(), "history")
    _close(app)
    r = bt["result"]
    ins = {x["segment"]: x for x in r["insufficient"]}
    assert ins["≤30″|悬浮式|≥$900"]["n"] == 19 and ins["≤30″|悬浮式|≥$900"]["merge_with"]
    assert "≤30″|悬浮式|≥$900" not in r["effective"]
    assert "≤30″|悬浮式|<$500" in r["effective"]
