"""变量关系 · 模型 (PAGE-F16-01 v2): 变量 → 过程指标 → 结果指标, with the mathematics in between.

Three layers of variables on every judged rising new SPU (solution-master 三层变量), each tagged 事前可知 or
事后才知; only 事前可知 variables may predict. Then the solution ladder, level by level:

- 模型 1 总效应 Y ~ X: a ridge logit and a gradient-boosted tree fitted on the same rows, compared on the same
  windows (训练 → 校准 → 验证, split by launch batch; the last window never picks the model). Outputs permutation
  importance per variable and the marginal odds ratio of every attribute value with a bootstrap interval.
- 模型 2 路径 X → M → Y: for each process indicator, how much of it the controllable variables explain and how
  much it still tells about hitting once they are held fixed.
- 模型 3 规则: paths of a shallow tree over the controllable variables, re-scored on the 验证 window and graded
  高 / 中 / 低; the rules people wrote in the strategy library are scored on the same rows, in the same table.

Every statistic carries n; intervals, not point claims; an ineffective model says so (题型库 §三). Nothing here
writes to the package or the strategy library: adopting a rule is a separate, person-only step.
"""

from __future__ import annotations

import math
import warnings
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.engine import Connection

from oppo import clock
from oppo import db as D
from oppo.core import adjust as ADJ
from oppo.core import backtest as BT
from oppo.core import categories as CAT
from oppo.core import compute as CMP
from oppo.core import rules as RULES
from oppo.core import signals as SIG
from oppo.core import stats as ST
from oppo.core import variables as VARS

MIN_VALUE_N = 8      # an attribute value needs this many judged SPUs to become a model feature
MIN_LEAF = 10        # smallest tree leaf / rule support on the fitting rows
MAX_RULE_CONDS = 3
BOOT = 150
PERM_REPEATS = 20
RIDGE = 0.01
TIERS = ("高", "中", "低")
VERDICTS = {"effective": "找到稳定关系", "weak": "关系较弱", "none": "未找到稳定关系", "nodata": "数据不足"}
LAYERS = {"x": "可控变量", "m": "过程指标", "z": "控制变量", "y": "结果变量"}
EARLY = {"units_m1": "首月 SPU 销量", "bsr_m1": "首月最好 BSR", "units_m2": "次月 SPU 销量"}


class ModelError(Exception):
    pass


# ---- the analysis table ---------------------------------------------------------------------


def table(conn: Connection, category_id: int, mode: str) -> dict[str, Any]:
    """One row per judged rising new SPU with Y, X (attributes, segment dims, launch price position …),
    M (segment signals at the launch batch, early trajectory) and Z (controls); plus the variable catalogue."""
    cfg = CAT.current_version(conn, category_id)["config"]
    run_ = CMP.latest_run(conn, category_id, mode)
    if run_ is None:
        raise ModelError("还没有成败与信号结果，请先运行计算")
    spus = CMP.spus_frame(conn, run_["id"])
    sig = CMP.signals_frame(conn, run_["id"])
    pool = VARS._pool(spus, mode).reset_index(drop=True)
    controls = CAT.controls_of(cfg)
    ctrl = BT.control_frame(pool, sig) if len(pool) else pool.copy()
    attrs = VARS._attrs_of_pool(conn, category_id, run_, cfg, pool) if len(pool) else pd.DataFrame()
    look = BT._sig_lookup(sig)
    dim_keys = [d["key"] for d in cfg["segment_dims"]]
    dim_labels = {d["key"]: d["label"] for d in cfg["segment_dims"]}
    df = pd.DataFrame({"spu_key": pool["spu_key"], "y": pool["hit"].astype(int), "batch": pool["batch"],
                       "segment_key": pool["segment_key"]})
    for i, k in enumerate(dim_keys):
        df[f"seg:{k}"] = [s.split("|")[i] if isinstance(s, str) and len(s.split("|")) > i else "未知"
                          for s in pool["segment_key"]]
    for c in attrs.columns:
        df[f"attr:{c}"] = attrs[c].fillna("未知").astype(str).values
    for k in CAT.CONTROL_VARS:
        df[f"z:{k}"] = pd.to_numeric(ctrl[k], errors="coerce").values if k in ctrl.columns else np.nan
    for s in SIG.SIGNALS + SIG.CURRENT:
        df[f"m:{s}"] = [look.get((b, seg, s)) for b, seg in zip(pool["batch"], pool["segment_key"], strict=False)]
        df[f"m:{s}"] = pd.to_numeric(df[f"m:{s}"], errors="coerce")
    early = {k: [] for k in EARLY}
    for mj in pool["months_json"] if "months_json" in pool.columns else [None] * len(pool):
        tbl = D.loads(mj, []) or []
        early["units_m1"].append(tbl[0].get("units") if tbl else None)
        early["bsr_m1"].append(tbl[0].get("best_bsr") if tbl else None)
        early["units_m2"].append(tbl[1].get("units") if len(tbl) > 1 else None)
    for k, v in early.items():
        df[f"m:{k}"] = pd.to_numeric(pd.Series(v), errors="coerce").values
    catalogue = [{"name": "y", "label": "命中", "layer": "y", "timing": "事后", "kind": "binary",
                  "available": int(len(df))}]
    for k in dim_keys:
        catalogue.append({"name": f"seg:{k}", "label": f"细分维度 · {dim_labels[k]}", "layer": "x", "timing": "事前",
                          "kind": "category", "available": int((df[f"seg:{k}"] != "未知").sum())})
    for c in attrs.columns:
        catalogue.append({"name": f"attr:{c}", "label": c, "layer": "x", "timing": "事前", "kind": "category",
                          "available": int((df[f"attr:{c}"] != "未知").sum())})
    for k, lab in CAT.CONTROL_VARS.items():
        catalogue.append({"name": f"z:{k}", "label": lab, "layer": "z", "timing": "事前", "kind": "numeric",
                          "available": int(df[f"z:{k}"].notna().sum()), "on": k in controls})
    for s in SIG.SIGNALS + SIG.CURRENT:
        catalogue.append({"name": f"m:{s}", "label": SIG.LABELS[s], "layer": "m", "timing": "事前",
                          "kind": "numeric", "available": int(df[f"m:{s}"].notna().sum()),
                          "note": "细分在上架月的信号" if s in SIG.SIGNALS else "细分老品在上架月的现用指标"})
    for k, lab in EARLY.items():
        catalogue.append({"name": f"m:{k}", "label": lab, "layer": "m", "timing": "事后", "kind": "numeric",
                          "available": int(df[f"m:{k}"].notna().sum()), "note": "上架后才知道，只用于路径，不用于预测"})
    return {"df": df, "catalogue": catalogue, "cfg": cfg, "run": run_, "controls": controls,
            "dim_keys": dim_keys, "dim_labels": dim_labels, "attr_dims": list(attrs.columns), "look": look}


# ---- splits and design -----------------------------------------------------------------------


def splits(df: pd.DataFrame, cfg: dict[str, Any]) -> dict[str, list[str]]:
    """Launch batches → 训练 / 校准 / 验证. The 验证 window is the backtest's test group; 校准 is the last third of
    the remaining batches (none when fewer than three remain, which the page says)."""
    batches = sorted(df["batch"].dropna().unique())
    if len(batches) < 3:
        return {"train": batches, "calib": [], "test": []}
    n_test = BT.holdout_size(len(batches), cfg.get("backtest_split") or {"rule": 2, "test": 1})
    test = batches[-n_test:]
    rest = batches[:-n_test]
    n_cal = len(rest) // 3 if len(rest) >= 3 else 0
    return {"train": rest[: len(rest) - n_cal] if n_cal else rest, "calib": rest[len(rest) - n_cal:] if n_cal else [],
            "test": test}


def design(df: pd.DataFrame, controls: list[str], min_n: int = MIN_VALUE_N) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Model matrix: one-hot of segment dims and attribute values (≥ min_n rows, not 未知) + standardized controls."""
    cols: dict[str, np.ndarray] = {}
    meta: list[dict[str, Any]] = []
    for c in df.columns:
        if not (c.startswith("seg:") or c.startswith("attr:")):
            continue
        vals = df[c].astype(str)
        for v, n in vals.value_counts().items():
            if v == "未知" or n < min_n or n > len(df) - min_n:
                continue
            name = f"{c}={v}"
            cols[name] = (vals == v).astype(float).to_numpy()
            meta.append({"feature": name, "var": c, "value": v, "layer": "x", "n": int(n)})
    for k in controls:
        s = pd.to_numeric(df[f"z:{k}"], errors="coerce")
        if s.notna().sum() < min_n or s.std(skipna=True) == 0:
            continue
        s = s.fillna(s.median())
        cols[f"z:{k}"] = ((s - s.mean()) / (s.std() or 1.0)).to_numpy()
        meta.append({"feature": f"z:{k}", "var": f"z:{k}", "value": None, "layer": "z", "n": int(len(s))})
    X = pd.DataFrame(cols, index=df.index) if cols else pd.DataFrame(index=df.index)
    return X, meta


# ---- model 1: total effect -----------------------------------------------------------------


def _fit_logit(X: np.ndarray, y: np.ndarray) -> np.ndarray | None:
    import statsmodels.api as sm

    if len(y) < 10 or y.min() == y.max():
        return None
    Xc = sm.add_constant(X, has_constant="add")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = sm.GLM(y.astype(float), Xc, family=sm.families.Binomial()).fit_regularized(
                alpha=RIDGE, L1_wt=0.0, maxiter=300)
        return np.asarray(res.params, dtype=float)
    except Exception:  # noqa: BLE001 - reported as unavailable
        return None


def _predict_logit(params: np.ndarray, X: np.ndarray) -> np.ndarray:
    z = params[0] + X @ params[1:]
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def _fit_tree(X: np.ndarray, y: np.ndarray) -> Any:
    from sklearn.ensemble import HistGradientBoostingClassifier

    if len(y) < 10 or y.min() == y.max():
        return None
    m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=MIN_LEAF,
                                       l2_regularization=1.0, random_state=ST.SEED)
    m.fit(X, y)
    return m


def _metrics(y: np.ndarray, p: np.ndarray) -> dict[str, Any]:
    from sklearn.metrics import roc_auc_score

    n = int(len(y))
    out: dict[str, Any] = {"n": n, "hits": int(y.sum()), "auc": None, "lift20": None, "brier": None}
    if n == 0:
        return out
    base = float(y.mean())
    out["base"] = base
    if 0 < base < 1 and n >= 10:
        out["auc"] = float(roc_auc_score(y, p))
    k = max(1, int(math.ceil(n * 0.2)))
    top = np.argsort(-p)[:k]
    out["top_n"] = k
    out["top_rate"] = float(y[top].mean())
    out["lift20"] = (out["top_rate"] / base) if base > 0 else None
    out["brier"] = float(np.mean((p - y) ** 2))
    return out


def fit_models(X: pd.DataFrame, df: pd.DataFrame, sp: dict[str, list[str]]) -> dict[str, Any]:
    y = df["y"].to_numpy().astype(float)
    masks = {w: df["batch"].isin(sp[w]).to_numpy() for w in ("train", "calib", "test")}
    fit_mask = masks["train"] | (masks["calib"] if not sp["calib"] else np.zeros(len(df), bool))
    Xn = X.to_numpy(dtype=float)
    out: dict[str, Any] = {"models": {}, "chosen": None, "windows": {w: int(m.sum()) for w, m in masks.items()},
                           "selection": "校准窗 AUC" if sp["calib"] else "没有校准窗：按训练窗 AUC 选，验证窗仅报告"}
    fits: dict[str, Any] = {}
    params = _fit_logit(Xn[fit_mask], y[fit_mask]) if X.shape[1] else None
    if params is not None:
        fits["logit"] = ("logit", params)
    tree = _fit_tree(Xn[fit_mask], y[fit_mask]) if X.shape[1] else None
    if tree is not None:
        fits["tree"] = ("tree", tree)
    for name, (kind, m) in fits.items():
        entry = {"label": "岭回归 logit" if kind == "logit" else "梯度提升树", "by_window": {}}
        for w, mask in masks.items():
            if not mask.any():
                entry["by_window"][w] = {"n": 0}
                continue
            p = _predict_logit(m, Xn[mask]) if kind == "logit" else m.predict_proba(Xn[mask])[:, 1]
            entry["by_window"][w] = _metrics(y[mask], p)
        out["models"][name] = entry
    pick_w = "calib" if sp["calib"] else "train"
    best, best_auc = None, -1.0
    for name, e in out["models"].items():
        auc = (e["by_window"].get(pick_w) or {}).get("auc")
        if auc is not None and auc > best_auc:
            best, best_auc = name, auc
    out["chosen"] = best
    out["_fits"] = fits
    out["_masks"] = masks
    return out


def importance(fitres: dict[str, Any], X: pd.DataFrame, df: pd.DataFrame, meta: list[dict[str, Any]],
               sp: dict[str, list[str]], name: str | None = None) -> list[dict[str, Any]]:
    """Permutation importance of one model (default: the chosen one) on the 校准 window (训练 when there is none):
    the AUC lost when all columns of a variable are shuffled together, averaged over PERM_REPEATS seeded shuffles."""
    from sklearn.metrics import roc_auc_score

    name = name or fitres["chosen"]
    if name is None or name not in fitres["_fits"] or not X.shape[1]:
        return []
    kind, m = fitres["_fits"][name]
    w = "calib" if sp["calib"] else "train"
    mask = fitres["_masks"][w]
    Xe, ye = X.to_numpy(dtype=float)[mask], df["y"].to_numpy()[mask]
    if len(ye) < 10 or ye.min() == ye.max():
        return []

    def auc_of(Xq: np.ndarray) -> float:
        p = _predict_logit(m, Xq) if kind == "logit" else m.predict_proba(Xq)[:, 1]
        return float(roc_auc_score(ye, p))

    base = auc_of(Xe)
    cols_by_var: dict[str, list[int]] = {}
    for i, mt in enumerate(meta):
        cols_by_var.setdefault(mt["var"], []).append(i)
    rng = ST.rng()
    out = []
    for v, cols in cols_by_var.items():
        drops = []
        for _ in range(PERM_REPEATS):
            Xp = Xe.copy()
            perm = rng.permutation(len(ye))
            Xp[:, cols] = Xe[perm][:, cols]
            drops.append(base - auc_of(Xp))
        out.append({"var": v, "layer": "z" if v.startswith("z:") else "x", "importance": float(np.mean(drops)),
                    "sd": float(np.std(drops)), "n": int(len(ye)), "window": w})
    out.sort(key=lambda r: -r["importance"])
    return out


def marginal_effects(X: pd.DataFrame, df: pd.DataFrame, meta: list[dict[str, Any]], sp: dict[str, list[str]],
                     fitres: dict[str, Any]) -> list[dict[str, Any]]:
    """Odds ratio of every attribute / segment value from the multivariable logit, with a bootstrap 90% interval
    (rows resampled on the fitting windows), plus the raw hit rates on 训练+校准 and 验证."""
    if not X.shape[1]:
        return []
    y = df["y"].to_numpy().astype(float)
    fit_mask = df["batch"].isin(sp["train"] + sp["calib"]).to_numpy()
    test_mask = df["batch"].isin(sp["test"]).to_numpy()
    Xn = X.to_numpy(dtype=float)
    params = _fit_logit(Xn[fit_mask], y[fit_mask])
    if params is None:
        return []
    rng = ST.rng()
    idx_all = np.flatnonzero(fit_mask)
    boots = []
    for _ in range(BOOT):
        idx = rng.choice(idx_all, size=len(idx_all), replace=True)
        p = _fit_logit(Xn[idx], y[idx])
        if p is not None:
            boots.append(p[1:])
    B = np.array(boots) if boots else None
    out = []
    for j, mt in enumerate(meta):
        if mt["layer"] != "x":
            continue
        col = Xn[:, j] > 0.5
        row = {"var": mt["var"], "value": mt["value"], "or": float(math.exp(params[1 + j])),
               "n_fit": int((col & fit_mask).sum()), "n_test": int((col & test_mask).sum()),
               "rate_fit": float(y[col & fit_mask].mean()) if (col & fit_mask).any() else None,
               "rate_test": float(y[col & test_mask].mean()) if (col & test_mask).any() else None}
        if B is not None and len(B) >= 20:
            lo, hi = np.percentile(B[:, j], [5, 95])
            row["or_lo"], row["or_hi"] = float(math.exp(lo)), float(math.exp(hi))
        else:
            row["or_lo"] = row["or_hi"] = None
        base_fit = float(y[fit_mask].mean()) if fit_mask.any() else None
        base_test = float(y[test_mask].mean()) if test_mask.any() else None
        up_fit = row["rate_fit"] is not None and base_fit is not None and row["rate_fit"] > base_fit
        up_test = row["rate_test"] is not None and base_test is not None and row["rate_test"] > base_test
        row["consistent"] = (up_fit == up_test) if (row["rate_test"] is not None and row["n_test"] >= 5) else None
        row["stable"] = bool(row["or_lo"] is not None and (row["or_lo"] > 1 or row["or_hi"] < 1) and row["consistent"])
        out.append(row)
    out.sort(key=lambda r: (r["var"], -r["or"]))
    return out


# ---- model 2: paths ------------------------------------------------------------------------


def paths(X: pd.DataFrame, df: pd.DataFrame, meta: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """For each process indicator M: R² of M on the controllable variables (X → M), the odds ratio of M alone and
    given X (M → Y | X), and the share of its raw association that survives holding X fixed."""
    y = df["y"].to_numpy().astype(float)
    Xn = X.to_numpy(dtype=float) if X.shape[1] else np.zeros((len(df), 0))
    out = []
    for c in [c for c in df.columns if c.startswith("m:")]:
        key = c[2:]
        m = pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float)
        ok = ~np.isnan(m)
        row = {"key": key, "label": SIG.LABELS.get(key) or EARLY.get(key, key), "n": int(ok.sum()),
               "timing": "事后" if key in EARLY else "事前", "r2_x": None, "or_alone": None, "or_given_x": None,
               "survives": None, "reason": None}
        if ok.sum() < 20 or np.nanstd(m[ok]) == 0 or y[ok].min() == y[ok].max():
            row["reason"] = "无数据" if ok.sum() == 0 else "样本不足或无变化"
            out.append(row)
            continue
        ms = (m[ok] - m[ok].mean()) / m[ok].std()
        if Xn.shape[1]:
            def r2_of(cols: list[int], ok: np.ndarray = ok, ms: np.ndarray = ms) -> float:
                A = np.column_stack([np.ones(ok.sum()), Xn[ok][:, cols]]) if cols else np.ones((ok.sum(), 1))
                coef, *_ = np.linalg.lstsq(A, ms, rcond=None)
                resid = ms - A @ coef
                return float(max(0.0, 1 - resid.var() / ms.var())) if ms.var() > 0 else 0.0

            all_cols = list(range(Xn.shape[1]))
            full = r2_of(all_cols)
            row["r2_x"] = full
            # per controllable variable: how much of M it explains on its own (single-variable R²; variables that
            # duplicate each other, e.g. 尺寸 and 宽度档, both show their full share)
            by_var: dict[str, list[int]] = {}
            for j, mt in enumerate(meta):
                if mt["layer"] == "x":
                    by_var.setdefault(mt["var"], []).append(j)
            row["by_x"] = sorted(({"var": v, "share": r2_of(cols)} for v, cols in by_var.items()),
                                 key=lambda d: -d["share"])
        row["or_alone"] = ST.odds_ratio(y[ok], ms, None)
        row["or_given_x"] = ST.odds_ratio(y[ok], ms, Xn[ok] if Xn.shape[1] else None)
        if row["or_alone"] and row["or_given_x"]:
            la, lg = math.log(row["or_alone"]), math.log(row["or_given_x"])
            # only meaningful when the indicator had a real association on its own (|log OR| ≥ 0.1 ≈ 10%)
            row["survives"] = (min(float(lg / la), 1.5) if la * lg > 0 else 0.0) if abs(la) >= 0.1 else None
        out.append(row)
    return out


def logic_tree(path_rows: list[dict[str, Any]], importance_by: dict[str, list[dict[str, Any]]], n: int,
               top_x: int = 4) -> dict[str, Any]:
    """结果 → 过程指标 → 可控变量: edge strengths for the diagram. Y–M strength = |log OR| of M alone (how much M
    tells about hitting); M–X strength = the single-variable R² of X on M (how much X alone explains M). A '直接' branch
    carries each model's permutation importance of X on Y, so variables that act without any process indicator
    still show up."""
    ms = []
    for p in path_rows:
        if p.get("or_alone") is None:
            continue
        strength = abs(math.log(p["or_alone"]))
        kids = [{"var": d["var"], "strength": d["share"]} for d in (p.get("by_x") or [])[:top_x] if d["share"] > 0.005]
        ms.append({"key": p["key"], "label": p["label"], "timing": p["timing"], "strength": strength,
                   "or_alone": p["or_alone"], "or_given_x": p.get("or_given_x"), "n": p["n"], "children": kids})
    ms.sort(key=lambda d: -d["strength"])
    ms = ms[:6]  # the strongest process indicators keep the diagram readable; the table above lists all
    direct = {}
    for name, rows in (importance_by or {}).items():
        direct[name] = [{"var": r["var"], "strength": max(0.0, r["importance"])} for r in rows
                        if r["layer"] == "x" and r["importance"] > 0][:top_x + 2]
    return {"n": n, "process": ms, "direct": direct}


# ---- model 3: rules ------------------------------------------------------------------------


def _wilson(hits: int, n: int) -> tuple[float | None, float | None]:
    return ST.wilson(hits, n) if n else (None, None)


def _score(mask: np.ndarray, y: np.ndarray, wmask: np.ndarray) -> dict[str, Any]:
    sel = mask & wmask
    n, hits = int(sel.sum()), int(y[sel].sum())
    base = float(y[wmask].mean()) if wmask.any() else None
    lo, hi = _wilson(hits, n)
    return {"n": n, "hits": hits, "rate": hits / n if n else None, "lo": lo, "hi": hi, "base": base,
            "lift": (hits / n / base) if n and base else None}


def _tier(fit: dict[str, Any], test: dict[str, Any]) -> str:
    """高: ≥ 20 on 验证, interval above the 验证 base and lift ≥ 1.5 on both windows; 中: ≥ 10 on 验证 and above
    base on both; otherwise 低."""
    def up(s: dict[str, Any]) -> bool:
        return bool(s["rate"] is not None and s["base"] is not None and s["rate"] > s["base"])

    if test["n"] >= BT.MIN_SAMPLE and test["lo"] is not None and test["base"] is not None and test["lo"] > test["base"] \
            and (fit["lift"] or 0) >= 1.5 and (test["lift"] or 0) >= 1.5:
        return "高"
    if test["n"] >= MIN_LEAF and up(fit) and up(test):
        return "中"
    return "低"


def _cond_from_feature(feature: str, positive: bool, dim_labels: dict[str, str]) -> dict[str, Any]:
    var, value = feature.split("=", 1)
    op = "=" if positive else "!="
    if var.startswith("seg:"):
        return {"kind": "dim", "key": var[4:], "value": value, "op": op, "label": dim_labels.get(var[4:], var[4:])}
    return {"kind": "attr", "key": var[5:], "value": value, "op": op, "label": var[5:]}


def cond_text(conds: list[dict[str, Any]]) -> str:
    return " 且 ".join(f"{c.get('label', c['key'])}{'=' if c.get('op', '=') == '=' else '≠'}{c['value']}" for c in conds)


def tree_rules(X: pd.DataFrame, df: pd.DataFrame, meta: list[dict[str, Any]], sp: dict[str, list[str]],
               dim_labels: dict[str, str]) -> list[dict[str, Any]]:
    from sklearn.tree import DecisionTreeClassifier

    xcols = [i for i, m in enumerate(meta) if m["layer"] == "x"]
    if not xcols:
        return []
    y = df["y"].to_numpy().astype(int)
    fit_mask = df["batch"].isin(sp["train"] + sp["calib"]).to_numpy()
    test_mask = df["batch"].isin(sp["test"]).to_numpy()
    Xr = X.to_numpy(dtype=float)[:, xcols]
    names = [meta[i]["feature"] for i in xcols]
    if fit_mask.sum() < 2 * MIN_LEAF or y[fit_mask].min() == y[fit_mask].max():
        return []
    rules: dict[str, dict[str, Any]] = {}
    for depth in (1, 2, 3):
        t = DecisionTreeClassifier(max_depth=depth, min_samples_leaf=MIN_LEAF, random_state=ST.SEED,
                                   class_weight=None).fit(Xr[fit_mask], y[fit_mask])
        tr = t.tree_
        stack: list[tuple[int, list[tuple[int, bool]]]] = [(0, [])]
        while stack:
            node, path = stack.pop()
            left, right = tr.children_left[node], tr.children_right[node]
            if left == -1:
                if not path:
                    continue
                conds = [_cond_from_feature(names[f], pos, dim_labels) for f, pos in path]
                key = cond_text(conds)
                if key in rules or len(conds) > MAX_RULE_CONDS:
                    continue
                mask = np.ones(len(df), bool)
                for f, pos in path:
                    mask &= (Xr[:, f] > 0.5) == pos
                fit_s, test_s = _score(mask, y, fit_mask), _score(mask, y, test_mask)
                if fit_s["n"] < MIN_LEAF or not (fit_s["lift"] or 0) > 1.0:
                    continue
                rules[key] = {"source": "模型", "conds": conds, "text": key, "fit": fit_s, "test": test_s,
                              "tier": _tier(fit_s, test_s), "depth": len(conds)}
                continue
            f = int(tr.feature[node])
            stack.append((left, path + [(f, False)]))
            stack.append((right, path + [(f, True)]))
    out = list(rules.values())
    out.sort(key=lambda r: (TIERS.index(r["tier"]), -(r["test"]["lift"] or 0), -(r["fit"]["lift"] or 0)))
    return out


def library_rules(conn: Connection, category_id: int, df: pd.DataFrame, sp: dict[str, list[str]],
                  look: dict[tuple[str, str, str], float | None], cfg: dict[str, Any],
                  mode: str) -> list[dict[str, Any]]:
    """The strategy library's current rules scored on the same rows (dim / attr / signal conditions)."""
    y = df["y"].to_numpy().astype(int)
    fit_mask = df["batch"].isin(sp["train"] + sp["calib"]).to_numpy()
    test_mask = df["batch"].isin(sp["test"]).to_numpy()
    dim_keys = [d["key"] for d in cfg["segment_dims"]]
    segs = df["segment_key"].astype(str).tolist()
    batches = df["batch"].astype(str).tolist()
    attr_cols = {c[5:]: df[c].astype(str).tolist() for c in df.columns if c.startswith("attr:")}
    out = []
    for r in RULES.list_current(conn, category_id):
        if r["origin"] == "回测" and bool(r.get("cross_tag")) != (mode == "cross"):
            continue
        conds = r["conds"]
        mask = np.zeros(len(df), bool)
        for i in range(len(df)):
            labels = dict(zip(dim_keys, segs[i].split("|"), strict=False))
            ok = True
            for c in conds:
                neg = c.get("op") == "!="
                if c["kind"] == "dim":
                    ok = (labels.get(c["key"]) == c["value"]) != neg
                elif c["kind"] == "attr":
                    ok = ((attr_cols.get(c["key"], ["未知"] * len(df))[i]) == c["value"]) != neg
                elif c["kind"] == "signal":
                    v = look.get((batches[i], segs[i], c["key"]))
                    ok = v is not None and RULES._cmp(float(v), c["op"], float(c["value"]))
                if not ok:
                    break
            mask[i] = ok
        fit_s, test_s = _score(mask, y, fit_mask), _score(mask, y, test_mask)
        verdict = None
        if fit_s["n"] + test_s["n"] == 0:
            verdict = "数据未支持：没有新品满足条件"
        elif r["action"] == "立项候选" and not ((test_s["lift"] or 0) > 1 and (fit_s["lift"] or 0) > 1):
            verdict = "数据未支持：满足条件的新品命中率不高于全类目"
        out.append({"source": "策略库", "code": r["code"], "status": r["status"], "origin": r["origin"],
                    "action": r["action"], "conds": conds, "text": RULES.cond_text(conds), "fit": fit_s,
                    "test": test_s, "tier": _tier(fit_s, test_s) if r["action"] == "立项候选" else None,
                    "verdict": verdict})
    return out


# ---- run / store ---------------------------------------------------------------------------


def _verdict(fitres: dict[str, Any], n_pool: int) -> str:
    if n_pool < 2 * BT.MIN_SAMPLE or fitres["chosen"] is None:
        return "nodata"
    t = fitres["models"][fitres["chosen"]]["by_window"].get("test") or {}
    auc, lift = t.get("auc"), t.get("lift20")
    if auc is None or lift is None:
        return "nodata"
    if auc >= 0.65 and lift >= 1.5:
        return "effective"
    if auc > 0.55 and lift > 1.2:
        return "weak"
    return "none"


def run(conn: Connection, category_id: int, operator: str, mode: str = "history",
        report: Any = lambda s, f: None) -> int:
    started = clock.now_iso()
    report("读取变量表", 0.05)
    t = table(conn, category_id, mode)
    df, cfg = t["df"], t["cfg"]
    sp = splits(df, cfg)
    res: dict[str, Any] = {"mode": mode, "n_pool": int(len(df)), "n_hit": int(df["y"].sum()) if len(df) else 0,
                           "base_rate": float(df["y"].mean()) if len(df) else None, "splits": sp,
                           "catalogue": t["catalogue"], "controls": t["controls"],
                           "notes": [], "limits": []}
    pkg = conn.execute(select(D.package).where(D.package.c.id == t["run"]["package_id"])).mappings().first()
    res["simulated"] = bool(pkg and "真相" in str(pkg.get("source_name") or ""))
    if len(df) < 2 * BT.MIN_SAMPLE or df["y"].nunique() < 2:
        res["notes"].append(f"已判定的起量新品 {len(df)} 个（命中 {res['n_hit']}），少于 {2 * BT.MIN_SAMPLE} 个或全部同一结果，不建模")
        res["verdict"] = "nodata"
        return _store(conn, category_id, mode, t, res, started, operator)
    if not sp["test"]:
        res["notes"].append("上架批次少于 3 个，没有验证窗；只报告训练结果，不产出规则")
    X, meta = design(df, t["controls"])
    res["features"] = meta
    report("模型 1：总效应", 0.25)
    fitres = fit_models(X, df, sp)
    res["model1"] = {"models": fitres["models"], "chosen": fitres["chosen"], "selection": fitres["selection"],
                     "windows": fitres["windows"]}
    res["importance"] = importance(fitres, X, df, meta, sp)
    res["importance_by"] = {name: importance(fitres, X, df, meta, sp, name) for name in fitres["models"]}
    report("模型 1：边际效应（自助法）", 0.45)
    res["effects"] = marginal_effects(X, df, meta, sp, fitres)
    report("模型 2：路径", 0.65)
    res["paths"] = paths(X, df, meta)
    report("模型 3：规则", 0.8)
    res["tree"] = logic_tree(res["paths"], res["importance_by"], len(df))
    res["verdict"] = _verdict(fitres, len(df))
    res["rules"] = tree_rules(X, df, meta, sp, t["dim_labels"]) if sp["test"] and res["verdict"] != "none" else []
    if res["verdict"] == "none":
        res["notes"].append("验证窗上模型没有区分度（AUC ≤ 0.55 或前 20% 倍数 ≤ 1.2），不产出规则")
    res["library"] = library_rules(conn, category_id, df, sp, t["look"], cfg, mode)
    res["limits"] = [
        "样本只含起量新品（任一月父体月销达到门槛），没起量的同期新品不在分母里，命中率偏高",
        "观察到的是关联：控制了所选变量，不等于因果；想证明某个动作有用要做对照",
        "前身项目的经验：这类模型的解释力上限约三分之一，高分段会被低估；分组过细时不单独估计",
    ]
    if res["simulated"]:
        res["limits"].insert(0, "当前是模拟数据（M1-真相），结果只说明方法能否找回种入的关系，不代表业务效果")
    return _store(conn, category_id, mode, t, res, started, operator)


def _store(conn: Connection, category_id: int, mode: str, t: dict[str, Any], res: dict[str, Any], started: str,
           operator: str) -> int:
    now = clock.now_iso()
    mid = conn.execute(D.model_run.insert().values(
        category_id=category_id, mode=mode, compute_run_id=t["run"]["id"], package_id=t["run"]["package_id"],
        config_version_id=t["run"]["config_version_id"], adjust_hash=ADJ.adjust_hash(conn, t["run"]["package_id"]),
        status="success", verdict=res.get("verdict"), result_json=D.dumps(_clean(res)), started_at=started,
        ended_at=now, created_by=operator, created_at=now)).inserted_primary_key[0]
    return int(mid)


def _clean(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items() if not str(k).startswith("_")}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, (np.floating, np.integer)):
        v = v.item()
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def latest(conn: Connection, category_id: int, mode: str) -> dict[str, Any] | None:
    row = conn.execute(select(D.model_run).where(D.model_run.c.category_id == category_id, D.model_run.c.mode == mode)
                       .order_by(D.model_run.c.id.desc())).mappings().first()
    if not row:
        return None
    d = dict(row)
    d["result"] = D.loads(d.get("result_json"), {}) or {}
    return d


def stale_reasons(conn: Connection, category_id: int, mr: dict[str, Any] | None) -> list[str]:
    if mr is None:
        return []
    out = []
    run_ = CMP.latest_run(conn, category_id, mr["mode"])
    if run_ and run_["id"] != mr["compute_run_id"]:
        out.append("成败与信号已重算")
    if run_ and CMP.stale_reasons(conn, category_id, run_):
        out.append("计算结果本身需重算")
    cfg = CAT.current_version(conn, category_id)
    if cfg["id"] != mr["config_version_id"]:
        out.append(f"品类配置已保存为 v{cfg['version_no']}")
    return out


def adopt(conn: Connection, category_id: int, model_run_id: int, index: int, operator: str, reason: str = "",
          action: str = "立项候选") -> int:
    """A person takes a model rule into the strategy library as 历史观察 (origin 模型发现), with its evidence."""
    mr = conn.execute(select(D.model_run).where(D.model_run.c.id == model_run_id)).mappings().first()
    if not mr or mr["category_id"] != category_id:
        raise ModelError("找不到这次模型结果")
    res = D.loads(mr["result_json"], {}) or {}
    rules = res.get("rules") or []
    if not (0 <= index < len(rules)):
        raise ModelError("找不到这条规则")
    r = rules[index]
    conds = [{k: v for k, v in c.items() if k != "label"} for c in r["conds"]]
    basis = {"model_run": model_run_id, "tier": r["tier"], "fit": r["fit"], "test": r["test"],
             "mode": res.get("mode"), "simulated": res.get("simulated")}
    text = (reason.strip() or f"模型发现：满足条件的新品在验证窗命中率 {r['test']['rate']:.0%}（n={r['test']['n']}），"
            f"全类目 {r['test']['base']:.0%}；可信度 {r['tier']}") if r["test"]["rate"] is not None else (
        reason.strip() or f"模型发现（训练窗命中率 {r['fit']['rate']:.0%}，n={r['fit']['n']}）")
    return RULES.add(conn, category_id, conds, action, text, operator, origin="模型发现", status="历史观察",
                     basis=basis, cross=res.get("mode") == "cross")
