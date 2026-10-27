"""变量关系 (PAGE-F16-01): the three kinds of variables behind a judgment and how they relate.

- 结果变量: hit within the success window (BSR ≤ bsr_max or monthly GMV ≥ gmv_min).
- 过程变量: the three signals and the four current metrics, measured as of each batch month.
- 控制变量: the factors held fixed when a signal's or an attribute's effect is estimated (CAT.CONTROL_VARS).

Everything here is read from the latest compute run and the current package: nothing is written. Effects are
odds ratios from the same ridge-penalised logit the backtest uses (ST.odds_ratio), with sample sizes and
Wilson intervals, so a thin sample shows as a wide interval rather than a confident number.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.engine import Connection

from oppo.core import backtest as BT
from oppo.core import categories as CAT
from oppo.core import compute as CMP
from oppo.core import contract as CT
from oppo.core import data as DATA
from oppo.core import judge as J
from oppo.core import packages as PK
from oppo.core import segments as SEG
from oppo.core import signals as SIG
from oppo.core import stats as ST

MIN_VALUE_N = 5  # attribute values seen on fewer judged SPUs are listed without an effect
SIGNAL_DESC = {
    "demand": "细分关键词搜索量近几个月的同比变化",
    "entry": "回看期内进入该细分的新品中起量的比例",
    "pain": "该细分老品评论里结构类痛点的占比",
    "hslr": "该细分老品中高销量、低评分商品的占比",
    "unit_asin": "细分老品月销量 ÷ 老品子体数",
    "premium": "细分老品均价相对同宽度档均价的溢价",
    "trend": "细分属性在老品中的份额趋势",
    "low_score": "细分老品中评分低于 4 分却高销的商品数",
}


def _pool(spus: pd.DataFrame, mode: str) -> pd.DataFrame:
    hit, miss = (J.HIT, J.MISS) if mode == "history" else (J.X_HIT, J.X_MISS)
    p = spus[(spus["is_new"] == 1) & (spus["rising"] == 1) & spus["status"].isin([hit, miss])].copy()
    p["hit"] = (p["status"] == hit).astype(int)
    return p


def catalogue(conn: Connection, category_id: int, mode: str) -> dict[str, Any]:
    """Variable lists with availability on the latest run; `effects` are filled by analysis()."""
    cfg = CAT.current_version(conn, category_id)["config"]
    run_ = CMP.latest_run(conn, category_id, mode)
    pkg = PK.current_package(conn, category_id, mode)
    succ = cfg.get("success") or {}
    out: dict[str, Any] = {
        "run": run_, "pkg": pkg, "mode": mode,
        "outcome": {
            "label": "命中",
            "definition": (f"上架 {succ.get('window_months')} 个月内小类 BSR ≤ {succ.get('bsr_max')}，"
                           f"或 SPU 任一月销售额 ≥ ${float(succ.get('gmv_min')):,.0f}") if succ.get("gmv_min") else "成功线未配置",
            "source": "C1/S1 子体月销量、子体月销售额、小类BSR；C3/S3 新品轨迹",
            "reference": f"分母只含起量新品（任一月父体月销 ≥ {cfg.get('rising_min_parent_units')} 件）",
        },
        "process": [], "controls": [], "selected_controls": CAT.controls_of(cfg),
    }
    sig = CMP.signals_frame(conn, run_["id"]) if run_ else pd.DataFrame()
    for key in SIG.SIGNALS + SIG.CURRENT:
        row = {"key": key, "label": SIG.LABELS[key], "kind": "信号" if key in SIG.SIGNALS else "现用指标",
               "definition": SIGNAL_DESC.get(key, ""), "available": None, "cells": 0, "reason": None}
        if len(sig):
            part = sig[sig["signal"] == key]
            n_val = int(part["value"].notna().sum())
            row.update(available=n_val > 0, cells=n_val)
            if n_val == 0 and len(part):
                flags = part["flag"].dropna()
                row["reason"] = str(flags.iloc[0]) if len(flags) else "无数据"
        out["process"].append(row)
    for key, label in CAT.CONTROL_VARS.items():
        out["controls"].append({"key": key, "label": label, "on": key in out["selected_controls"]})
    return out


def _attrs_of_pool(conn: Connection, category_id: int, run_: dict[str, Any], cfg: dict[str, Any],
                   pool: pd.DataFrame) -> pd.DataFrame:
    uf = CT.usable_fields(conn, category_id, run_["package_id"])
    b = DATA.load(conn, run_["package_id"], uf["confirmed"])
    if not len(b.c4):
        return pd.DataFrame(index=pool.index)
    attrs = SEG.effective_attrs(b.c4, cfg).set_index("child")
    dims = [d for d in (cfg.get("attribute_dims") or []) if d in attrs.columns]
    rows = attrs.reindex(pool["launch_child"].tolist())[dims]
    rows.index = pool.index
    return rows


def analysis(conn: Connection, category_id: int, mode: str) -> dict[str, Any]:
    """catalogue() plus: process-variable effects before/after controls, attribute-value effects, sample notes."""
    out = catalogue(conn, category_id, mode)
    run_ = out["run"]
    out.update(process_effects=[], attribute_effects=[], n_pool=0, n_hit=0, notes=[])
    if run_ is None:
        out["notes"].append("还没有成败与信号结果，请先运行计算")
        return out
    cfg = CAT.current_version(conn, category_id)["config"]
    controls = CAT.controls_of(cfg)
    spus = CMP.spus_frame(conn, run_["id"])
    sig = CMP.signals_frame(conn, run_["id"])
    pool = _pool(spus, mode)
    out["n_pool"], out["n_hit"] = int(len(pool)), int(pool["hit"].sum()) if len(pool) else 0
    if len(pool) < 10 or pool["hit"].nunique() < 2:
        out["notes"].append(f"已判定的起量新品 {len(pool)} 个，命中 {out['n_hit']} 个；少于 10 个或全部同一结果时不估计效应")
        return out
    # process variables: the backtest's confounder table, on every judged SPU rather than the rule group only
    uf = CT.usable_fields(conn, category_id, run_["package_id"])
    snap_keys = {(CT.contract_code(f["file"]), f["field"]) for f in uf["snapshot"]}
    blocked = {s for s, fs in BT.SIGNAL_FIELDS.items() if any(f in snap_keys for f in fs)}
    look = BT._sig_lookup(sig)
    out["process_effects"] = BT._confounders(pool, look, sig, blocked, controls)
    # attribute values: indicator of "this SPU's lead child has value v" against hit, with the same controls
    ctrl = BT.control_frame(pool, sig)
    ctrl_mat = ctrl[controls].astype(float).to_numpy() if controls else np.zeros((len(pool), 0))
    attrs = _attrs_of_pool(conn, category_id, run_, cfg, pool)
    y_all = pool["hit"].to_numpy()
    base_rate = float(y_all.mean())
    out["base_rate"] = base_rate
    for dim in attrs.columns:
        col = attrs[dim].fillna(SEG.UNKNOWN).astype(str)
        values = []
        for v, n in col.value_counts().items():
            m = (col == v).to_numpy()
            hits = int(y_all[m].sum())
            lo, hi = ST.wilson(hits, int(n))
            row = {"value": v, "n": int(n), "hits": hits, "rate": hits / n, "lo": lo, "hi": hi,
                   "or_before": None, "or_after": None, "unknown": v == SEG.UNKNOWN}
            if n >= MIN_VALUE_N and n < len(pool) and v != SEG.UNKNOWN:
                x = m.astype(float)
                mask = np.ones(len(pool), dtype=bool)
                if ctrl_mat.shape[1]:
                    mask &= ~np.isnan(ctrl_mat).any(axis=1)
                row["or_before"] = ST.odds_ratio(y_all[mask], x[mask], None)
                row["or_after"] = ST.odds_ratio(y_all[mask], x[mask], ctrl_mat[mask] if ctrl_mat.shape[1] else None)
            values.append(row)
        values.sort(key=lambda r: (r["unknown"], -r["n"]))
        out["attribute_effects"].append({"dim": dim, "values": values,
                                         "is_segment_dim": dim in {d["attr"] for d in cfg.get("segment_dims") or []},
                                         "unknown_share": float((col == SEG.UNKNOWN).mean())})
    if len(pool) < BT.MIN_SAMPLE * 2:
        out["notes"].append(f"已判定的起量新品只有 {len(pool)} 个，区间很宽；控制变量越多估计越不稳，结论只作方向参考")
    return out
