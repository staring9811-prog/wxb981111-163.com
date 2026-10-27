"""Time-split backtest (F07: REQ-F07-01..03, AC-F07-01..14, DEC-023/028/029/036).

Ranking inside each test batch uses the signal values visible at that batch's launch month (T = batch).
Achievement tests use integer cross-multiplication so 2.00× and equal hit rates are decided exactly.
"""

from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from oppo import clock
from oppo import db as D
from oppo.core import categories as CAT
from oppo.core import compute as CMP
from oppo.core import contract as CT
from oppo.core import jobs
from oppo.core import judge as J
from oppo.core import rules as RULES
from oppo.core import segments as SEG
from oppo.core import signals as SIG
from oppo.core import stats as ST
from oppo.core.packages import add_months, month_range

MIN_SAMPLE = 20
MIN_EFFECTIVE = 5  # DEC-036
TOP_SHARE = 0.20
LIMITATION = "广告投入、站外引流未纳入"
CONFOUNDERS = ("品牌上架前已有命中 SPU", "上架月份", "价格位置（相对细分销量加权均价）", "变体数", "配送方式", "疑似重新上架")
# Source fields each signal needs; a snapshot field among them excludes the signal (AC-F02-05).
SIGNAL_FIELDS = {
    "demand": [("C5", "月搜索量"), ("C5", "关键词属性标签")],
    "entry": [("C3", "子体月销量"), ("C3", "小类BSR")],
    "pain": [("C6", "是否结构类痛点"), ("C6", "评论日期")],
    "hslr": [("C1", "子体月销量"), ("C6", "星级")],
    "unit_asin": [("C1", "子体月销量")],
    "premium": [("C1", "子体月销售额"), ("C1", "子体月销量")],
    "trend": [("C1", "子体月销量")],
    "low_score": [("C1", "子体月销量"), ("C6", "星级")],
}

Scorer = Callable[[str, str], float | None]


def holdout_size(n_batches: int, split: dict[str, Any]) -> int:
    """Batches in the test group: ⌊n × test / (rule + test)⌋, at least 1 (AC-F07-01; 4 → 1, 10 → 3 at 2:1)."""
    return max(1, math.floor(n_batches * split["test"] / (split["rule"] + split["test"])))


def top_k(n_effective: int) -> int:
    """Segments in the top 20 %: ⌈n × 0.2⌉, at least 1 (11 → 3)."""
    return max(1, math.ceil(n_effective * TOP_SHARE))


class BacktestError(Exception):
    pass


def _next_code(conn: Connection) -> str:
    n = conn.execute(select(func.count()).select_from(D.backtest_run)).scalar() or 0
    return f"BT-{n + 1:04d}"


def _sig_lookup(sig: pd.DataFrame) -> dict[tuple[str, str, str], float | None]:
    out = {}
    for T, seg, s, v in sig[["t_month", "segment_key", "signal", "value"]].itertuples(index=False):
        out[(T, seg, s)] = None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)
    return out


def _reasons(sig: pd.DataFrame) -> dict[str, str]:
    """Reason per signal when it has no value, taken from the latest month T that has one."""
    out: dict[str, str] = {}
    empty = sig[sig["value"].isna()].sort_values("t_month", ascending=False, kind="stable")
    for s, extra in empty[["signal", "extra_json"]].itertuples(index=False):
        if s not in out and extra:
            r = (D.loads(extra, {}) or {}).get("reason")
            if r:
                out[s] = r
    return out


def evaluate(batches: list[str], pool: pd.DataFrame, eff: list[str], n_seg: dict[str, int], scorer: Scorer,
             seed: int, boot: bool = True) -> dict[str, Any]:
    """Top-20% hit rate of `scorer` over `batches` (pool: one row per decided SPU with hit ∈ {0,1})."""
    k = top_k(len(eff))
    per_batch = {b: pool[pool["batch"] == b] for b in batches}
    by_seg_batch = {(b, s): (int(g["hit"].sum()), int(len(g)))
                    for b, pb in per_batch.items() for s, g in pb.groupby("segment_key")}
    computable = False
    top_hits = top_n = 0
    tops: dict[str, list[str]] = {}
    for b in batches:
        vals = {s: scorer(s, b) for s in eff}
        have = [s for s in eff if vals[s] is not None]
        if have:
            computable = True
        ranked = sorted(have, key=lambda s: (-vals[s], -n_seg.get(s, 0), s))[:k]
        tops[b] = ranked
        for s in ranked:
            h, n = by_seg_batch.get((b, s), (0, 0))
            top_hits += h
            top_n += n
    all_hits, all_n = int(pool["hit"].sum()), int(len(pool))
    res: dict[str, Any] = {"computable": computable, "k": k, "top_hits": top_hits, "top_n": top_n,
                           "all_hits": all_hits, "all_n": all_n, "tops": tops}
    if not computable or top_n == 0 or all_n == 0:
        res.update(rate=None, avg=all_hits / all_n if all_n else None, multiple=None, ci=(None, None),
                   mult_ci=(None, None))
        return res
    rate, avg = top_hits / top_n, all_hits / all_n
    mult = (top_hits * all_n) / (top_n * all_hits) if all_hits else None  # exact ratio of integers
    res.update(rate=rate, avg=avg, multiple=mult, ci=ST.wilson(top_hits, top_n))
    if boot and avg:
        units = list(eff)

        def stat(sample: list[str]) -> float | None:
            th = tn = ah = an = 0
            for b in batches:
                entries = [(s, i) for i, s in enumerate(sample)]
                vals = {e: scorer(e[0], b) for e in entries}
                have = [e for e in entries if vals[e] is not None]
                ranked = sorted(have, key=lambda e: (-vals[e], -n_seg.get(e[0], 0), e[0], e[1]))[:k]
                for e in ranked:
                    h, n = by_seg_batch.get((b, e[0]), (0, 0))
                    th += h
                    tn += n
                for s in sample:
                    h, n = by_seg_batch.get((b, s), (0, 0))
                    ah += h
                    an += n
            if not tn or not an or not ah:
                return None
            return (th / tn) / (ah / an)

        res["mult_ci"] = ST.bootstrap_ratio(units, stat, seed=seed)
    else:
        res["mult_ci"] = (None, None)
    return res


def _round_step(v: float, step: float = 0.05) -> float:
    return round(round(v / step) * step, 10)


def thresholds(values: dict[str, float]) -> tuple[float | None, float | None]:
    vals = sorted(values.values(), reverse=True)
    n = len(vals)
    if n < 2:
        return None, None
    k = max(1, math.ceil(n * TOP_SHARE))
    upper = _round_step((vals[k - 1] + vals[min(k, n - 1)]) / 2)
    lower = _round_step((vals[max(n - k, 0)] + vals[max(n - k - 1, 0)]) / 2) if n >= 2 * k + 1 else None
    return upper, lower


def weights(mults: dict[str, float]) -> dict[str, float]:
    total = sum(mults.values())
    raw = {k: v / total for k, v in mults.items()}
    out = {k: round(v, 2) for k, v in raw.items()}
    diff = round(1.0 - sum(out.values()), 2)
    if out and diff:
        top = max(out, key=lambda k: (raw[k], k))
        out[top] = round(out[top] + diff, 2)
    return out


def card_scorer(card_signals: list[dict[str, Any]], look: dict[tuple[str, str, str], float | None],
                universe: list[str]) -> Scorer:
    cache: dict[str, dict[str, float]] = {}

    def score(seg: str, T: str) -> float | None:
        if not card_signals:
            return None
        if T not in cache:
            tot = {s: 0.0 for s in universe}
            any_val = {s: False for s in universe}
            for cs in card_signals:
                vals = {s: look.get((T, s, cs["signal"])) for s in universe}
                pr = ST.pct_rank(vals)
                for s in universe:
                    tot[s] += cs["weight"] * pr[s]
                    any_val[s] = any_val[s] or vals[s] is not None
            cache[T] = {s: (tot[s] if any_val[s] else None) for s in universe}
        return cache[T].get(seg)

    return score


def achieved(card: dict[str, Any], current: dict[str, dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
    """AC-F07-03 using integers: top_hits/top_n ≥ 2·all_hits/all_n and > every computable indicator."""
    th, tn, ah, an = card["top_hits"], card["top_n"], card["all_hits"], card["all_n"]
    cond1 = tn > 0 and an > 0 and th * an >= 2 * ah * tn
    comparable = {k: v for k, v in current.items() if v.get("computable") and v.get("top_n")}
    beats = {k: th * v["top_n"] > v["top_hits"] * tn for k, v in comparable.items()}
    cond2 = bool(comparable) and all(beats.values())
    best = max(comparable.items(), key=lambda kv: kv[1]["rate"]) if comparable else None
    return cond1 and cond2, {"cond1": cond1, "cond2": cond2, "beats": beats,
                             "best_current": (best[0], best[1]["rate"]) if best else None}


def run(conn: Connection, category_id: int, operator: str, mode: str = "history",
        report: Callable[[str, float], None] = lambda s, f: None) -> int:
    started = clock.now_iso()
    run_ = CMP.latest_run(conn, category_id, mode)
    if run_ is None:
        raise BacktestError("还没有成败与信号结果，请先运行计算")
    cfg_ver = CAT.current_version(conn, category_id)
    cfg = cfg_ver["config"]
    seed = ST.SEED
    code = _next_code(conn)
    report("读取成败与信号", 0.05)
    spus = CMP.spus_frame(conn, run_["id"])
    sig = CMP.signals_frame(conn, run_["id"])
    uf = CT.usable_fields(conn, category_id, run_["package_id"])
    snap_fields = uf["snapshot"]
    snap_keys = {(CT.contract_code(f["file"]), f["field"]) for f in snap_fields}
    blocked = {s for s, fs in SIGNAL_FIELDS.items() if any(f in snap_keys for f in fs)}
    if mode == "history":
        result = _history(conn, cfg, spus, sig, run_, seed, blocked, report)
    else:
        result = _cross(conn, cfg, spus, sig, run_, seed, blocked, report)
    result["rejected_fields"] = snap_fields
    result["limitation"] = LIMITATION
    result["seed"] = seed
    result["versions"] = {"package_id": run_["package_id"], "contract_version_id": run_["contract_version_id"],
                          "config_version_id": run_["config_version_id"]}
    jobs.maybe_fail("backtest:after-evaluate")
    conclusion = result["conclusion"]
    now = clock.now_iso()
    bt_id = conn.execute(D.backtest_run.insert().values(
        code=code, category_id=category_id, mode=mode, compute_run_id=run_["id"], package_id=run_["package_id"],
        contract_version_id=run_["contract_version_id"], config_version_id=run_["config_version_id"],
        merge_hash=run_["merge_hash"], seed=seed, status="success", conclusion=conclusion,
        reason_class=result.get("reason_class"), result_json=D.dumps(result), started_at=started, ended_at=now,
        created_by=operator, created_at=now)).inserted_primary_key[0]
    report("生成判定卡与锦囊", 0.9)
    card_id = _make_card(conn, category_id, mode, bt_id, code, result, operator)
    conn.execute(D.backtest_run.update().where(D.backtest_run.c.id == bt_id).values(card_id=card_id))
    from oppo.core import ranking, runs

    report("排序与快照", 0.95)
    ranking.generate(conn, category_id, mode, operator)
    runs.record_step(conn, category_id, "回测", started, clock.now_iso(), operator,
                     result=f"{code} · {conclusion}", link="/backtest", package_id=run_["package_id"])
    return int(bt_id)


def _pool_history(spus: pd.DataFrame) -> pd.DataFrame:
    p = spus[(spus["is_new"] == 1) & (spus["rising"] == 1) & spus["status"].isin([J.HIT, J.MISS])].copy()
    p["hit"] = (p["status"] == J.HIT).astype(int)
    return p


def _history(conn: Connection, cfg: dict[str, Any], spus: pd.DataFrame, sig: pd.DataFrame, run_: dict[str, Any],
             seed: int, blocked: set[str], report: Callable[[str, float], None]) -> dict[str, Any]:
    window = int(cfg["success"]["window_months"])
    latest = run_["latest_month"]
    pool = _pool_history(spus)
    new = spus[(spus["is_new"] == 1)]
    all_batches = sorted(new["batch"].unique())
    decided = [b for b in all_batches if add_months(b, window - 1) <= latest and (pool["batch"] == b).any()]
    res: dict[str, Any] = {"mode": "history", "decided_batches": decided,
                           "excluded_batches": [b for b in all_batches if b not in decided]}
    if len(decided) < 3:
        res.update(conclusion="未达标", reason_class="数据不足",
                   reason_text=f"已判定批次 {len(decided)} 个（至少需要 3 个）")
        res["card_signals"] = []
        return res
    split = cfg["backtest_split"]
    n_test = holdout_size(len(decided), split)
    rule_b, test_b = decided[:-n_test], decided[-n_test:]
    res["split"] = {"rule": rule_b, "test": test_b}
    look = _sig_lookup(sig)
    reasons = _reasons(sig)
    rule_pool = pool[pool["batch"].isin(rule_b)]
    test_pool = pool[pool["batch"].isin(test_b)]
    res["rule_counts"] = {"spus": int(len(rule_pool)), "batches": len(rule_b)}
    res["test_counts"] = {"spus": int(len(test_pool)), "batches": len(test_b)}

    def seg_counts(p: pd.DataFrame) -> dict[str, int]:
        return p.groupby("segment_key").size().astype(int).to_dict()

    n_rule, n_test_seg = seg_counts(rule_pool), seg_counts(test_pool)
    eff_rule = sorted(s for s, n in n_rule.items() if n >= MIN_SAMPLE)
    if len(eff_rule) < 2:
        eff_rule = sorted(s for s, n in n_rule.items() if n >= 5)
    eff_test = sorted(s for s, n in n_test_seg.items() if n >= MIN_SAMPLE)
    insufficient = sorted(s for s, n in n_test_seg.items() if n < MIN_SAMPLE)
    res["effective"] = eff_test
    res["k"] = top_k(len(eff_test))
    res["insufficient"] = [_merge_hint(s, n_test_seg, cfg) for s in insufficient]

    def sig_scorer(name: str) -> Scorer:
        return lambda s, T: None if name in blocked else look.get((T, s, name))

    # ---- choose the card on the rule group
    report("定规则组：挑选信号", 0.2)
    rule_eval = {}
    for s in SIG.SIGNALS:
        rule_eval[s] = evaluate(rule_b, rule_pool, eff_rule, n_rule, sig_scorer(s), seed, boot=False)
    candidates = {s: e["multiple"] for s, e in rule_eval.items() if e["computable"] and e["multiple"] is not None}
    chosen = {s: m for s, m in candidates.items() if m >= 2.0}
    if not chosen and candidates:
        best = max(candidates, key=lambda s: (candidates[s], s))
        chosen = {best: candidates[best]}
    w = weights(chosen) if chosen else {}
    card_signals = []
    for s in sorted(w, key=lambda s: (-w[s], s)):
        means = {}
        for seg in eff_rule:
            vals = [look.get((b, seg, s)) for b in rule_b]
            vals = [v for v in vals if v is not None]
            if vals:
                means[seg] = float(np.mean(vals))
        upper, lower = thresholds(means)
        card_signals.append({"signal": s, "label": SIG.LABELS[s], "weight": w[s], "threshold": upper,
                             "lower": lower, "rule_multiple": chosen[s]})
    res["card_signals"] = card_signals
    res["rule_eval"] = {s: _slim(e) for s, e in rule_eval.items()}

    # ---- evaluate on the test group
    report("检验组：评估", 0.45)
    jobs.maybe_fail("backtest:evaluate")
    card_eval = evaluate(test_b, test_pool, eff_test, n_test_seg, card_scorer(card_signals, look, eff_test), seed)
    single = {s: evaluate(test_b, test_pool, eff_test, n_test_seg, sig_scorer(s), seed) for s in SIG.SIGNALS}
    current = {}
    for s in SIG.CURRENT:
        e = evaluate(test_b, test_pool, eff_test, n_test_seg, sig_scorer(s), seed)
        if not e["computable"]:
            e["reason"] = "回测不用快照字段" if s in blocked else reasons.get(s, "数据包缺少所需数据")
        current[s] = e
    base_ci = ST.wilson(int(test_pool["hit"].sum()), int(len(test_pool)))
    res["card"] = _slim(card_eval)
    res["signals"] = {s: _slim(e) for s, e in single.items()}
    for s, e in single.items():
        if not e["computable"]:
            res["signals"][s]["reason"] = reasons.get(s, "数据包缺少所需数据")
    res["current"] = {s: {**_slim(e), "reason": e.get("reason")} for s, e in current.items()}
    res["baseline"] = {"hits": int(test_pool["hit"].sum()), "n": int(len(test_pool)), "ci": base_ci,
                       "rate": float(test_pool["hit"].mean()) if len(test_pool) else None}
    computable_current = [s for s, e in current.items() if e["computable"]]
    ok, detail = achieved(card_eval, current)
    res["conditions"] = detail
    if not computable_current:
        res.update(conclusion="未达标", reason_class="数据不足", reason_text="现用指标都无法计算")
    elif len(eff_test) < MIN_EFFECTIVE:
        res.update(conclusion="未达标", reason_class="细分样本不足",
                   reason_text=f"有效细分 {len(eff_test)} 个（少于 {MIN_EFFECTIVE} 个），样本不足细分 {len(insufficient)} 个")
    elif ok:
        res.update(conclusion="达标", reason_class=None, reason_text=None)
    else:
        best = detail["best_current"]
        res.update(conclusion="未达标", reason_class="信号无区分度",
                   reason_text=(f"前 20% 命中率 {_pct(card_eval['rate'])}，全类目平均 {_pct(card_eval['avg'])}，"
                                f"倍数 {_mult(card_eval['multiple'])}；最强现用指标"
                                f"{SIG.LABELS[best[0]] if best else '无'} {_pct(best[1]) if best else ''}"))
    # ---- confounders on the rule group (AC-F07-06)
    report("控制干扰因素", 0.75)
    res["confounders"] = _confounders(rule_pool, look, sig, blocked)
    res["confounder_n"] = int(len(rule_pool))
    # ---- rule basis for tips
    res["rules"] = _rule_specs(card_signals, pool, decided, look, cfg) if res["conclusion"] == "达标" else []
    return res


def _slim(e: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in e.items() if k != "tops"} | {"tops": e.get("tops", {})}


def _pct(v: float | None) -> str:
    return "无数据" if v is None else f"{v * 100:.1f}%"


def _mult(v: float | None) -> str:
    return "无数据" if v is None else f"{v:.2f}×"


def _merge_hint(seg: str, counts: dict[str, int], cfg: dict[str, Any]) -> dict[str, Any]:
    adj = SEG.adjacent_bins(seg, cfg)
    best = max(adj, key=lambda a: (counts.get(a, 0), a)) if adj else None
    merged = counts.get(seg, 0) + (counts.get(best, 0) if best else 0)
    return {"segment": seg, "n": counts.get(seg, 0), "merge_with": best, "merged_n": merged,
            "still_short": merged < MIN_SAMPLE}


def _confounders(pool: pd.DataFrame, look: dict[tuple[str, str, str], float | None], sig: pd.DataFrame,
                 blocked: set[str]) -> list[dict[str, Any]]:
    out = []
    if not len(pool):
        return out
    price = {(T, s): v for T, s, sg, v in sig[sig["signal"] == "premium"][["t_month", "segment_key", "signal", "num"]]
             .itertuples(index=False)}
    p = pool.copy()
    p["seg_price"] = [price.get((b, s)) for b, s in zip(p["batch"], p["segment_key"])]
    p["price_pos"] = p["launch_price"] / p["seg_price"]
    months = sorted(p["batch"].unique())
    p["month_idx"] = p["batch"].map({m: i for i, m in enumerate(months)})
    p["fba"] = (p["fulfillment"].fillna("").str.upper() == "FBA").astype(int)
    ctrl_cols = ["brand_prior_hit", "month_idx", "price_pos", "variant_count", "fba", "relaunch"]
    for s in SIG.SIGNALS:
        if s in blocked:
            out.append({"signal": s, "label": SIG.LABELS[s], "before": None, "after": None, "reason": "回测不用快照字段"})
            continue
        x = np.array([look.get((b, seg, s)) for b, seg in zip(p["batch"], p["segment_key"])], dtype=float)
        mask = ~np.isnan(x)
        ctrl = p[ctrl_cols].astype(float).to_numpy()
        mask &= ~np.isnan(ctrl).any(axis=1)
        y = p["hit"].to_numpy()[mask]
        before = ST.odds_ratio(y, x[mask], None)
        after = ST.odds_ratio(y, x[mask], ctrl[mask])
        out.append({"signal": s, "label": SIG.LABELS[s], "before": before, "after": after, "n": int(mask.sum()),
                    "reason": None if before is not None else "无数据"})
    return out


def _rule_specs(card_signals: list[dict[str, Any]], pool: pd.DataFrame, decided: list[str],
                look: dict[tuple[str, str, str], float | None], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    if not card_signals:
        return []
    p = card_signals[0]
    s, up, lo = p["signal"], p["threshold"], p["lower"]
    specs = []
    if up is not None:
        specs.append(([{"kind": "signal", "key": s, "op": ">=", "value": up}], "立项候选"))
    if up is not None and lo is not None and lo < up:
        specs.append(([{"kind": "signal", "key": s, "op": ">=", "value": lo},
                       {"kind": "signal", "key": s, "op": "<", "value": up}], "观察"))
    if lo is not None:
        specs.append(([{"kind": "signal", "key": s, "op": "<", "value": lo}], "放弃"))
    out = []
    for conds, action in specs:
        hits = n = 0
        for b in decided:
            pb = pool[pool["batch"] == b]
            for seg, g in pb.groupby("segment_key"):
                v = {s: look.get((b, seg, s))}
                if RULES.matches(conds, seg, v, cfg):
                    hits += int(g["hit"].sum())
                    n += int(len(g))
        out.append({"conds": conds, "action": action, "hits": hits, "n": n, "ci": ST.wilson(hits, n),
                    "batches": f"{decided[0]}–{decided[-1]}"})
    return out


def _make_card(conn: Connection, category_id: int, mode: str, bt_id: int, code: str, result: dict[str, Any],
               operator: str) -> int:
    n = conn.execute(select(func.count()).select_from(D.decision_card).where(
        D.decision_card.c.category_id == category_id, D.decision_card.c.mode == mode)).scalar() or 0
    no = n + 1
    label = f"v{no}" if mode == "history" else f"截面 v{no}"
    conclusion = result["conclusion"]
    status = {"达标": "已达标", "达标（截面）": "达标（截面）"}.get(conclusion, "未验证")
    split = result.get("split") or {}
    card = result.get("card") or {}
    basis = {
        "backtest": code, "rule_batches": split.get("rule", []), "test_batches": split.get("test", []),
        "rule_spus": (result.get("rule_counts") or {}).get("spus"),
        "test_spus": (result.get("test_counts") or {}).get("spus"),
        "top_hits": card.get("top_hits"), "top_n": card.get("top_n"), "all_hits": card.get("all_hits"),
        "all_n": card.get("all_n"), "rate": card.get("rate"), "avg": card.get("avg"),
        "multiple": card.get("multiple"), "ci": card.get("ci"), "mult_ci": card.get("mult_ci"),
        "reason_class": result.get("reason_class"), "reason_text": result.get("reason_text"),
        "rows": result.get("rows"),
    }
    now = clock.now_iso()
    cid = conn.execute(D.decision_card.insert().values(
        category_id=category_id, mode=mode, version_no=no, label=label, status=status, backtest_id=bt_id,
        signals_json=D.dumps(result.get("card_signals", [])), basis_json=D.dumps(basis), created_by=operator,
        created_at=now)).inserted_primary_key[0]
    if status in ("已达标", "达标（截面）"):
        for spec in result.get("rules", []):
            RULES.generated_or_reuse(
                conn, category_id, spec["conds"], spec["action"],
                f"由回测 {code} 生成（{'截面' if mode == 'cross' else '历史'}口径）",
                {"backtest": code, "batches": spec["batches"], "hits": spec["hits"], "n": spec["n"],
                 "ci": spec["ci"], "card": label}, operator, cross=(mode == "cross"))
    return int(cid)


# ---- cross-section mode (REQ-F07-03) --------------------------------------------------------


def _cross(conn: Connection, cfg: dict[str, Any], spus: pd.DataFrame, sig: pd.DataFrame, run_: dict[str, Any],
           seed: int, blocked: set[str], report: Callable[[str, float], None]) -> dict[str, Any]:
    window = int(cfg["success"]["window_months"])
    first_obs = conn.execute(select(D.package.c.months_from).where(D.package.c.id == run_["package_id"])).scalar()
    new = spus[(spus["is_new"] == 1) & (spus["rising"] == 1)].copy()
    batches = sorted(new["batch"].unique())
    res: dict[str, Any] = {"mode": "cross", "decided_batches": batches, "excluded_batches": []}
    rows = []
    for r in new.itertuples():
        for m in D.loads(r.months_json, []) or []:
            age = m.get("age") or 0
            if 1 <= age <= window and not m.get("missing"):
                rows.append({"spu_key": r.spu_key, "segment_key": r.segment_key, "batch": r.batch, "age": age,
                             "y": int(bool(m.get("achieved")))})
    rows_df = pd.DataFrame(rows, columns=["spu_key", "segment_key", "batch", "age", "y"])
    # segment × age table over all batches (AC-F07-13)
    table = {}
    for (s, a), g in rows_df.groupby(["segment_key", "age"]):
        table.setdefault(s, {})[int(a)] = {"hits": int(g["y"].sum()), "n": int(g["spu_key"].nunique())}
    res["age_table"] = table
    if len(batches) < 3:
        res.update(conclusion="未达标", reason_class="数据不足", reason_text=f"已判定批次 {len(batches)} 个（至少需要 3 个）")
        res["card_signals"] = []
        return res
    split = cfg["backtest_split"]
    n_test = holdout_size(len(batches), split)
    model_b, test_b = batches[:-n_test], batches[-n_test:]
    res["split"] = {"rule": model_b, "test": test_b}
    res["rows"] = {"model": int(rows_df["batch"].isin(model_b).sum()), "test": int(rows_df["batch"].isin(test_b).sum())}
    report("截面模型：新品-月逻辑回归", 0.3)
    jobs.maybe_fail("backtest:evaluate")
    probs = _cross_model(rows_df[rows_df["batch"].isin(model_b)], new, window)
    res["probs"] = probs
    pool = new[new["batch"].isin(test_b)].copy()
    pool["hit"] = (pool["status"] == J.X_HIT).astype(int)
    n_seg = pool.groupby("segment_key").size().astype(int).to_dict()
    eff = sorted(s for s, n in n_seg.items() if n >= MIN_SAMPLE)
    insufficient = sorted(s for s, n in n_seg.items() if n < MIN_SAMPLE)
    res["effective"] = eff
    res["k"] = top_k(len(eff))
    res["insufficient"] = [_merge_hint(s, n_seg, cfg) for s in insufficient]
    res["test_counts"] = {"spus": int(len(pool)), "batches": len(test_b)}
    res["rule_counts"] = {"spus": int(len(new[new["batch"].isin(model_b)])), "batches": len(model_b)}
    look = _sig_lookup(sig)
    reasons = _reasons(sig)
    model_eval = evaluate(test_b, pool, eff, n_seg, lambda s, T: probs.get(s), seed)
    current = {}
    for s in SIG.CURRENT:
        e = evaluate(test_b, pool, eff, n_seg, (lambda name: (lambda seg, T: None if name in blocked
                                                               else look.get((T, seg, name))))(s), seed)
        if not e["computable"]:
            e["reason"] = "回测不用快照字段" if s in blocked else reasons.get(s, "数据包缺少所需数据")
        current[s] = e
    res["card"] = _slim(model_eval)
    res["current"] = {s: {**_slim(e), "reason": e.get("reason")} for s, e in current.items()}
    res["baseline"] = {"hits": int(pool["hit"].sum()), "n": int(len(pool)),
                       "ci": ST.wilson(int(pool["hit"].sum()), int(len(pool))),
                       "rate": float(pool["hit"].mean()) if len(pool) else None}
    ok, detail = achieved(model_eval, current)
    res["conditions"] = detail
    computable_current = [s for s, e in current.items() if e["computable"]]
    if not computable_current:
        res.update(conclusion="未达标", reason_class="数据不足", reason_text="现用指标都无法计算")
    elif len(eff) < MIN_EFFECTIVE:
        res.update(conclusion="未达标", reason_class="细分样本不足",
                   reason_text=f"有效细分 {len(eff)} 个（少于 {MIN_EFFECTIVE} 个），样本不足细分 {len(insufficient)} 个")
    elif ok:
        res.update(conclusion="达标（截面）", reason_class=None, reason_text=None)
    else:
        best = detail["best_current"]
        res.update(conclusion="未达标", reason_class="信号无区分度",
                   reason_text=(f"前 20% 截面命中率 {_pct(model_eval['rate'])}，全类目平均 {_pct(model_eval['avg'])}，"
                                f"倍数 {_mult(model_eval['multiple'])}；最强现用指标"
                                f"{SIG.LABELS[best[0]] if best else '无'} {_pct(best[1]) if best else ''}"))
    res["card_signals"] = [{"signal": "xprob", "label": "上架 6 个月内命中概率（截面）", "weight": 1.0,
                            "threshold": None, "lower": None}]
    vals = {s: p for s, p in probs.items() if s in eff}
    up, lo = thresholds(vals) if len(vals) >= 2 else (None, None)
    res["card_signals"][0].update(threshold=up, lower=lo)
    res["rules"] = []
    if res["conclusion"] == "达标（截面）" and up is not None:
        specs = [([{"kind": "signal", "key": "xprob", "op": ">=", "value": up}], "立项候选")]
        if lo is not None and lo < up:
            specs.append(([{"kind": "signal", "key": "xprob", "op": ">=", "value": lo},
                           {"kind": "signal", "key": "xprob", "op": "<", "value": up}], "观察"))
            specs.append(([{"kind": "signal", "key": "xprob", "op": "<", "value": lo}], "放弃"))
        for conds, action in specs:
            segs = [s for s in probs if RULES.matches(conds, s, {"xprob": probs[s]}, cfg)]
            g = pool[pool["segment_key"].isin(segs)]
            hits, n = int(g["hit"].sum()), int(len(g))
            res["rules"].append({"conds": conds, "action": action, "hits": hits, "n": n, "ci": ST.wilson(hits, n),
                                 "batches": f"{test_b[0]}–{test_b[-1]}"})
    res["confounders"] = []
    res["confounder_n"] = res["rows"]["model"]
    return res


def _cross_model(rows: pd.DataFrame, new: pd.DataFrame, window: int) -> dict[str, float]:
    """Logit on new-product-months: age dummies + segment dummies + confounders (ridge), then
    P(hit within 6 months) = 1 − Π(1 − p_age) at mean confounders — an approximation (independent months)."""
    import statsmodels.api as sm

    if rows.empty:
        return {}
    info = new.set_index("spu_key")
    df = rows.join(info[["brand_prior_hit", "variant_count", "relaunch", "fulfillment"]], on="spu_key")
    df["fba"] = (df["fulfillment"].fillna("").str.upper() == "FBA").astype(float)
    segs = sorted(df["segment_key"].unique())
    ages = list(range(1, window + 1))
    X = pd.DataFrame(index=df.index)
    for a in ages[1:]:
        X[f"age{a}"] = (df["age"] == a).astype(float)
    for s in segs[1:]:
        X[f"seg::{s}"] = (df["segment_key"] == s).astype(float)
    conf = df[["brand_prior_hit", "variant_count", "relaunch", "fba"]].astype(float).fillna(0.0)
    means = conf.mean()
    sds = conf.std().replace(0, 1.0).fillna(1.0)
    for c in conf.columns:
        X[c] = (conf[c] - means[c]) / sds[c]
    X = sm.add_constant(X, has_constant="add")
    y = df["y"].astype(float).to_numpy()
    try:
        fit = sm.GLM(y, X.to_numpy(), family=sm.families.Binomial()).fit_regularized(alpha=0.01, L1_wt=0.0,
                                                                                         maxiter=300)
        params = pd.Series(np.asarray(fit.params), index=X.columns)
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for s in segs:
        logit_base = params["const"] + (params.get(f"seg::{s}", 0.0) if s != segs[0] else 0.0)
        miss = 1.0
        for a in ages:
            lo = logit_base + (params.get(f"age{a}", 0.0) if a != 1 else 0.0)
            p = 1 / (1 + math.exp(-lo))
            miss *= (1 - p)
        out[s] = float(1 - miss)
    return out


# ---- reading -----------------------------------------------------------------------------


def latest(conn: Connection, category_id: int, mode: str) -> dict[str, Any] | None:
    row = conn.execute(select(D.backtest_run).where(
        D.backtest_run.c.category_id == category_id, D.backtest_run.c.mode == mode,
        D.backtest_run.c.status == "success").order_by(D.backtest_run.c.id.desc()).limit(1)).mappings().first()
    if not row:
        return None
    d = dict(row)
    d["result"] = D.loads(row["result_json"], {})
    return d


def get(conn: Connection, bt_id: int) -> dict[str, Any] | None:
    row = conn.execute(select(D.backtest_run).where(D.backtest_run.c.id == bt_id)).mappings().first()
    if not row:
        return None
    d = dict(row)
    d["result"] = D.loads(row["result_json"], {})
    return d
