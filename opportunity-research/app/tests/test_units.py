"""Unit tests for the rounding and boundary rules named in FLOW-09, FLOW-10 and FLOW-12."""

from __future__ import annotations

import pytest

from oppo.core import backtest as BT
from oppo.core import stats as ST

SPLIT = {"rule": 2, "test": 1}


@pytest.mark.parametrize("n,test", [(4, 1), (9, 3), (10, 3), (3, 1)])
def test_split_rounding(n: int, test: int) -> None:
    assert BT.holdout_size(n, SPLIT) == test


@pytest.mark.parametrize("n,k", [(10, 2), (11, 3), (5, 1), (1, 1)])
def test_top_20_percent_rounding(n: int, k: int) -> None:
    assert BT.top_k(n) == k


def test_wilson_90() -> None:
    lo, hi = ST.wilson(24, 40)
    assert round(lo, 3) == 0.470 and round(hi, 3) == 0.717


def _card(th: int, tn: int, ah: int, an: int) -> dict:
    return {"top_hits": th, "top_n": tn, "all_hits": ah, "all_n": an}


def _cur(th: int, tn: int) -> dict:
    return {"computable": True, "top_hits": th, "top_n": tn, "rate": th / tn}


def test_achieved_exactly_two_times() -> None:
    ok, d = BT.achieved(_card(40, 100, 20, 100), {"unit_asin": _cur(30, 100)})  # 40% / 20% = 2.00
    assert ok and d["cond1"] and d["cond2"]


def test_not_achieved_at_1_99() -> None:
    ok, d = BT.achieved(_card(199, 1000, 100, 1000), {"unit_asin": _cur(10, 100)})  # 1.99
    assert not ok and not d["cond1"]


def test_not_achieved_when_equal_to_an_indicator() -> None:
    ok, d = BT.achieved(_card(40, 100, 20, 100), {"unit_asin": _cur(40, 100), "premium": _cur(10, 100)})
    assert not ok and d["cond1"] and not d["cond2"]


def test_uncomputable_indicators_are_not_compared() -> None:
    cur = {"unit_asin": _cur(10, 100), "low_score": {"computable": False, "top_hits": 0, "top_n": 0, "rate": None}}
    ok, _ = BT.achieved(_card(40, 100, 20, 100), cur)
    assert ok


@pytest.mark.parametrize("word, cls, icon", [("未达标", "badge--fail", "x-circle"), ("截面命中", "badge--cross", "check-circle"),
                                             ("达标（截面）", "badge--cross", "seal-check"),
                                             ("未验证", "badge--unverified", "seal-question")])
def test_status_badges_follow_design_md(word: str, cls: str, icon: str) -> None:
    """DESIGN.md 状态词与徽章对照: pages may not pick another icon or style."""
    from oppo import fmt

    html = str(fmt.badge(word))
    assert cls in html and f"#ph-{icon}" in html and html.endswith(f"{word}</span>")


def test_heat_cell_without_observations_says_no_data_once() -> None:
    from oppo.web.report import present as P

    t = P.heat_table({"age_table": {"a|b": {"1": {"hits": 1, "n": 6}}}, "probs": {}, "effective": [], "k": 0})
    empty = t["rows"][0]["cells"][1]
    assert empty["text"] == "无数据" and empty["sub"] == "" and "没有被观察到的新 SPU" in empty["tip"]


def test_reconcile_bar_marks_an_interval_past_the_scale() -> None:
    from oppo.web.views import ledger as LV

    assert "ibar__over" in str(LV.recon_bar(0.444, 0.46, 0.63, 0.214, "44.4%", "21.4%"))
    assert "ibar__over" not in str(LV.recon_bar(0.30, 0.20, 0.40, 0.214, "30%", "21.4%"))


def test_width_bins_accept_exact_values_or_ranges():
    """品类配置: width picks concrete 尺寸 values (each its own bin) or, optionally, ranges."""
    from oppo.core import categories as CAT
    from oppo.core import segments as SEG

    exact = CAT._parse_bins("width", "24 / 30 / 36")
    assert [b["eq"] for b in exact] == [24, 30, 36]
    assert SEG.bin_numeric(30, exact) == "30" and SEG.bin_numeric(42, exact) == "未知"
    ranges = CAT._parse_bins("width", "≤30″ / 30–48″ / ≥48″")
    assert "max" in ranges[0] and SEG.bin_numeric(42, ranges) == "30–48″"
    import pytest

    with pytest.raises(ValueError):
        CAT._parse_bins("width", "24 / 24")
