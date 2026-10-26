"""Success judgments (F05: REQ-F05-01, REQ-F05-02, AC-F05-01..12)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from oppo.core.packages import add_months, month_range

HIT, MISS, WATCH, INCOMPLETE = "命中", "未命中", "观察中", "数据不全"
X_HIT, X_MISS, OLD = "截面命中", "截面未命中", "老品"


def child_months(c1: pd.DataFrame, c3: pd.DataFrame) -> pd.DataFrame:
    """Monthly child rows: C3 trajectory first, C1 fills months that C3 lacks."""
    cols = ["child", "month", "child_units", "child_sales", "bsr", "parent_units"]
    a = c3[cols].copy() if len(c3) else pd.DataFrame(columns=cols)
    a["src"] = "C3"
    b = c1[cols].copy() if len(c1) else pd.DataFrame(columns=cols)
    b["src"] = "C1"
    allm = pd.concat([a, b], ignore_index=True)
    allm = allm.dropna(subset=["child", "month"])
    allm = allm.sort_values(["child", "month", "src"], ascending=[True, True, False])  # C3 before C1
    first = allm.groupby(["child", "month"], as_index=False).first()
    # Parent units may only be present in C1 (C3 has it as optional): take the max seen.
    pu = allm.groupby(["child", "month"])["parent_units"].max()
    first["parent_units"] = first.set_index(["child", "month"]).index.map(pu)
    return first


def parent_units_by_parent(c1: pd.DataFrame, cm: pd.DataFrame, child_parent: dict[str, str]) -> pd.DataFrame:
    """parent × month max parent units across C1 rows and child rows."""
    rows = []
    if len(c1):
        x = c1.dropna(subset=["parent", "parent_units"])[["parent", "month", "parent_units"]]
        rows.append(x)
    if len(cm):
        y = cm.dropna(subset=["parent_units"]).copy()
        y["parent"] = y["child"].map(child_parent)
        rows.append(y.dropna(subset=["parent"])[["parent", "month", "parent_units"]])
    if not rows:
        return pd.DataFrame(columns=["parent", "month", "parent_units"])
    allp = pd.concat(rows, ignore_index=True)
    return allp.groupby(["parent", "month"], as_index=False)["parent_units"].max()


def spu_month_table(children: list[str], cm_by_child: dict[str, pd.DataFrame], months: list[str]) -> list[dict[str, Any]]:
    out = []
    for m in months:
        units = sales = 0.0
        has_sales = has_bsr = False
        best_bsr, best_child = None, None
        for ch in children:
            df = cm_by_child.get(ch)
            if df is None or m not in df.index:
                continue
            r = df.loc[m]
            if pd.notna(r["child_sales"]):
                sales += float(r["child_sales"])
                has_sales = True
            if pd.notna(r["child_units"]):
                units += float(r["child_units"])
            if pd.notna(r["bsr"]):
                has_bsr = True
                if best_bsr is None or r["bsr"] < best_bsr or (r["bsr"] == best_bsr and ch < best_child):
                    best_bsr, best_child = float(r["bsr"]), ch
        out.append({"month": m, "sales": sales if has_sales else None, "units": units if has_sales else None,
                    "best_bsr": best_bsr, "best_child": best_child, "missing": not (has_sales and has_bsr)})
    return out


def judge_history(launch_month: str, table_months: list[dict[str, Any]], latest: str, cfg: dict[str, Any]
                  ) -> dict[str, Any]:
    """table_months: rows for window ages 1..6 (only months <= latest are meaningful)."""
    succ = cfg["success"]
    window = int(succ["window_months"])
    bsr_max, gmv_min = float(succ["bsr_max"]), float(succ["gmv_min"])
    end = add_months(launch_month, window - 1)
    res: dict[str, Any] = {"best_bsr": None, "max_sales": None, "missing": [], "remaining": None}
    for age, row in enumerate(table_months, start=1):
        m = row["month"]
        if m > latest:
            break
        row["age"] = age
        if row["best_bsr"] is not None and (res["best_bsr"] is None or row["best_bsr"] < res["best_bsr"]):
            res["best_bsr"] = row["best_bsr"]
        if row["sales"] is not None and (res["max_sales"] is None or row["sales"] > res["max_sales"]):
            res["max_sales"] = row["sales"]
        by_bsr = row["best_bsr"] is not None and row["best_bsr"] <= bsr_max
        by_gmv = row["sales"] is not None and row["sales"] >= gmv_min
        row["achieved"] = by_bsr or by_gmv
        if row["achieved"] and "status" not in res:
            res.update(status=HIT, hit_month=m, hit_age=age,
                       basis="BSR" if by_bsr and not by_gmv else ("GMV" if by_gmv and not by_bsr else "BSR+GMV"),
                       hit_child=row["best_child"] if by_bsr else None, hit_bsr=row["best_bsr"] if by_bsr else None,
                       hit_amount=row["sales"] if by_gmv else None)
        if row["missing"]:
            res["missing"].append(m)
    if "status" not in res:
        if end > latest:
            res["status"] = WATCH
            res["remaining"] = len(month_range(add_months(latest, 1), end))
        elif res["missing"]:
            res["status"] = INCOMPLETE
        else:
            res["status"] = MISS
    return res


def judge_cross(launch_month: str, obs: list[dict[str, Any]], first_obs: str, last_obs: str, cfg: dict[str, Any]
                ) -> dict[str, Any]:
    succ = cfg["success"]
    window = int(succ["window_months"])
    bsr_max, gmv_min = float(succ["bsr_max"]), float(succ["gmv_min"])
    end = add_months(launch_month, window - 1)
    if end < first_obs:
        return {"status": OLD, "missing": [], "unobserved": []}
    res: dict[str, Any] = {"best_bsr": None, "max_sales": None, "missing": [], "observed_ages": []}
    for row in obs:
        m = row["month"]
        age = len(month_range(launch_month, m)) if m >= launch_month else 0
        row["age"] = age
        if not (1 <= age <= window):
            continue
        res["observed_ages"].append(age)
        if row["best_bsr"] is not None and (res["best_bsr"] is None or row["best_bsr"] < res["best_bsr"]):
            res["best_bsr"] = row["best_bsr"]
        if row["sales"] is not None and (res["max_sales"] is None or row["sales"] > res["max_sales"]):
            res["max_sales"] = row["sales"]
        by_bsr = row["best_bsr"] is not None and row["best_bsr"] <= bsr_max
        by_gmv = row["sales"] is not None and row["sales"] >= gmv_min
        row["achieved"] = by_bsr or by_gmv
        if row["achieved"] and "status" not in res:
            res.update(status=X_HIT, hit_month=m, hit_age=age,
                       basis="BSR" if by_bsr and not by_gmv else ("GMV" if by_gmv and not by_bsr else "BSR+GMV"),
                       hit_child=row["best_child"] if by_bsr else None, hit_bsr=row["best_bsr"] if by_bsr else None,
                       hit_amount=row["sales"] if by_gmv else None)
        if row["missing"]:
            res["missing"].append(m)
    observed_with_data = {r["age"] for r in obs if 1 <= r.get("age", 0) <= window and not r["missing"]}
    res["unobserved"] = [a for a in range(1, window + 1) if a not in observed_with_data]
    if "status" not in res:
        if end <= last_obs:
            res["status"] = X_MISS
        else:
            res["status"] = WATCH
            res["remaining"] = len(month_range(add_months(last_obs, 1), end))
    return res
