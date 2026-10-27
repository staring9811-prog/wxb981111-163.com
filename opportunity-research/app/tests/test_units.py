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
