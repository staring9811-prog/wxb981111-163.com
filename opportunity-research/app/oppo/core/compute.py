"""Compute step (API-F05-01, SEQ-F05-01): SPUs, judgments, segments and signals in one transaction."""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.engine import Connection

from oppo import clock
from oppo import db as D
from oppo.core import categories as CAT
from oppo.core import contract as CT
from oppo.core import data as DATA
from oppo.core import jobs
from oppo.core import judge as J
from oppo.core import packages as PK
from oppo.core import segments as SEG
from oppo.core import signals as SIG
from oppo.core import spu as SPU
from oppo.core.packages import add_months, month_range

Report = Callable[[str, float], None]


class ComputeError(Exception):
    pass


def _noop(_s: str, _f: float) -> None:
    pass


def run(conn: Connection, category_id: int, operator: str, report: Report = _noop,
        modes: tuple[str, ...] = ("history", "cross")) -> list[int]:
    """Compute every mode that has a current package. Returns the new compute run ids."""
    started = clock.now_iso()
    ids = []
    any_pkg = False
    for mode in modes:
        pkg = PK.current_package(conn, category_id, mode)
        if pkg is None:
            continue
        any_pkg = True
        ids.append(_run_mode(conn, category_id, pkg, mode, operator, report))
    if not any_pkg:
        raise ComputeError("还没有可计算的数据包，请先导入")
    from oppo.core import ledger, runs

    report("到期对账", 0.97)
    ledger.reconcile_all(conn, category_id, operator)
    runs.record_step(conn, category_id, "计算", started, clock.now_iso(), operator, result="成败与信号已计算",
                     link="/signals")
    return ids


def _run_mode(conn: Connection, category_id: int, pkg: dict[str, Any], mode: str, operator: str,
              report: Report) -> int:
    PK.assert_computable(conn, pkg["id"])
    cfg_ver = CAT.current_version(conn, category_id)
    cfg = cfg_ver["config"]
    uf = CT.usable_fields(conn, category_id, pkg["id"])
    if uf["version"] is None:
        raise ComputeError("还没有字段约定，请先在“字段约定”页确认字段并保存")
    missing = [f"{fc} {f}" for fc, f in CT.REQUIRED_FOR_COMPUTE[mode] if (fc, f) not in uf["confirmed"]]
    if missing:
        raise ComputeError("以下必需字段未确认，不能计算：" + "、".join(missing))
    report(f"读取数据包 {pkg['label']}", 0.05)
    b = DATA.load(conn, pkg["id"], uf["confirmed"])
    use_no = ("C1", "SPU编号") in uf["confirmed"] or ("C2", "SPU编号") in uf["confirmed"]
    report("SPU 归并与上架日", 0.15)
    spus, kids = SPU.build(conn, category_id, b, use_no)
    if spus.empty:
        raise ComputeError("数据包里没有可识别的商品")
    latest = pkg["months_to"] or max(b.c1["month"].dropna())
    first_obs = pkg["months_from"]
    T_now = add_months(latest, 1)
    cm = J.child_months(b.c1, b.c3)
    cm_by_child = {c: g.set_index("month") for c, g in cm.groupby("child")}
    child_parent = dict(zip(kids["child"], kids["parent"]))
    pu = J.parent_units_by_parent(b.c1, cm, child_parent)
    rise_thr = float(cfg["rising_min_parent_units"])
    first_rise = pu[pu["parent_units"] >= rise_thr].groupby("parent")["month"].min().to_dict()
    pu_map = {(p, m): float(v) for p, m, v in pu[["parent", "month", "parent_units"]].itertuples(index=False)}
    attrs = SEG.effective_attrs(b.c4, cfg).set_index("child") if len(b.c4) else pd.DataFrame()
    manifest = D.loads(pkg["manifest_json"], {}) or {}
    win = (manifest.get("新品上架窗口") or {}).get("起")
    window_start = win[:7] if win else (min(spus.loc[spus["in_c2"] == 1, "batch"]) if (spus["in_c2"] == 1).any() else None)
    window = int(cfg["success"]["window_months"])
    report("成败判定", 0.25)
    kids_by_spu = {k: g for k, g in kids.groupby("spu_key")}
    statuses, judg_rows = [], []
    for r in spus.itertuples():
        ch = kids_by_spu[r.spu_key]
        parents = D.loads(r.parents_json, [])
        rf = min([first_rise[p] for p in parents if p in first_rise], default=None)
        if mode == "history":
            is_new = bool(r.in_c2) and window_start is not None and r.batch >= window_start
            is_old = not is_new
        else:
            is_new = add_months(r.batch, window - 1) >= first_obs
            is_old = not is_new
        lead = r.launch_child
        arow = attrs.loc[lead].to_dict() if len(attrs) and lead in attrs.index else None
        price = _launch_price(cm_by_child, ch["child"].tolist(), lead, r.batch)
        seg_key, _ = SEG.segment_of(arow, price, cfg)
        rec = {"spu_key": r.spu_key, "is_new": int(is_new), "is_old": int(is_old), "rising": int(rf is not None),
               "rising_from": rf or "9999-12", "segment_key": seg_key, "segment_name": SEG.seg_name(seg_key),
               "launch_price": price}
        if is_new:
            kids_list = ch["child"].tolist()
            if mode == "history":
                months = month_range(r.batch, add_months(r.batch, window - 1))
                tbl = J.spu_month_table(kids_list, cm_by_child, months)
                res = J.judge_history(r.batch, tbl, latest, cfg)
            else:
                months = month_range(max(first_obs, r.batch), latest)
                tbl = J.spu_month_table(kids_list, cm_by_child, months)
                res = J.judge_cross(r.batch, tbl, first_obs, latest, cfg)
            # parent units per month for the detail page
            for row in tbl:
                row["parent_units"] = max([pu_map[(p, row["month"])] for p in parents if (p, row["month"]) in pu_map],
                                          default=None)
            rec["status"] = res["status"]
            judg_rows.append({
                "spu_key": r.spu_key, "status": res["status"], "basis": res.get("basis"),
                "hit_month": res.get("hit_month"), "hit_age": res.get("hit_age"), "hit_child": res.get("hit_child"),
                "hit_bsr": res.get("hit_bsr"), "hit_amount": res.get("hit_amount"),
                "missing_months_json": D.dumps(res.get("missing", [])),
                "unobserved_ages_json": D.dumps(res.get("unobserved", [])),
                "best_bsr": res.get("best_bsr"), "max_sales": res.get("max_sales"), "remaining": res.get("remaining"),
                "months_json": D.dumps(tbl), "rising": int(rf is not None),
            })
        else:
            rec["status"] = J.OLD if mode == "cross" else None
            if mode == "cross":
                judg_rows.append({"spu_key": r.spu_key, "status": J.OLD, "rising": int(rf is not None),
                                  "months_json": D.dumps([]), "missing_months_json": "[]",
                                  "unobserved_ages_json": "[]"})
        statuses.append(rec)
    st = pd.DataFrame(statuses)
    spus = spus.merge(st, on="spu_key")
    # brand already had a hit SPU known before this launch (REQ-F07-02 confounder)
    hits = spus[spus["status"].isin([J.HIT, J.X_HIT])]
    jr = pd.DataFrame(judg_rows)
    hit_month = dict(zip(jr["spu_key"], jr["hit_month"])) if len(jr) else {}
    prior = []
    for r in spus.itertuples():
        same = hits[(hits["brand"] == r.brand) & (hits["spu_key"] != r.spu_key)]
        prior.append(int(any((hit_month.get(k) or "9999") < r.batch for k in same["spu_key"])))
    spus["brand_prior_hit"] = prior
    report("细分与信号", 0.4)
    new = spus[spus["is_new"] == 1].copy()
    old_children: set[str] = set()
    if mode == "cross":
        old_keys = set(spus.loc[spus["is_old"] == 1, "spu_key"])
        old_children = set(kids.loc[kids["spu_key"].isin(old_keys), "child"])
    c1m = b.c1 if mode == "history" else b.c1  # S1 is stored as C1 rows
    ctx = SIG.build_context(cfg, mode, c1m, attrs, b.c5, b.c6, new, b.has.get("c5", False), b.has.get("c6", False),
                            old_children)
    batches = sorted(new["batch"].unique()) if len(new) else []
    t_list = month_range(batches[0], T_now) if batches else [T_now]
    t_list = sorted(set(t_list) | {T_now})
    run_id = conn.execute(D.compute_run.insert().values(
        category_id=category_id, mode=mode, package_id=pkg["id"], contract_version_id=uf["version"]["id"],
        config_version_id=cfg_ver["id"], merge_hash=SPU.merge_hash(conn, category_id),
        excluded_fields_json=D.dumps(uf["excluded"]), rows_used_json=D.dumps(PK.raw_row_counts(conn, pkg["id"])),
        latest_month=latest, t_month=T_now, status="running", started_at=clock.now_iso(),
        created_by=operator, created_at=clock.now_iso())).inserted_primary_key[0]
    sig_rows, seg_rows = [], []
    # sample size per segment = decided rising new SPUs over all batches (DEC-026)
    dec = new[(new["rising"] == 1) & new["status"].isin([J.HIT, J.MISS, J.X_HIT, J.X_MISS])]
    sample = dec.groupby("segment_key").size().to_dict()
    for i, T in enumerate(t_list):
        jobs.maybe_fail("compute:signals")
        report(f"信号 T = {T}", 0.4 + 0.5 * i / max(1, len(t_list)))
        rows, info = SIG.compute_T(ctx, T)
        for row in rows:
            sig_rows.append({"run_id": run_id, "t_month": T, "segment_key": row["segment_key"],
                             "signal": row["signal"], "value": row["value"], "num": row["num"], "den": row["den"],
                             "cnt": row["cnt"], "flag": row["flag"],
                             "extra_json": D.dumps(row["extra"]) if row["extra"] else None})
        for s, inf in info.items():
            seg_rows.append({"run_id": run_id, "t_month": T, "segment_key": s, "name": SEG.seg_name(s),
                             "dims_json": D.dumps(s.split("|")), "child_count": inf["child_count"],
                             "backfill_share": inf["backfill_share"], "backfill_json": D.dumps(inf["backfill"]),
                             "sample": int(sample.get(s, 0)), "has_unknown": inf["has_unknown"]})
    report("写入结果", 0.92)
    spu_cols = [c.name for c in D.spu.columns]
    out = spus.assign(run_id=run_id, source_keys_json=None)
    out["source_keys_json"] = [D.dumps({"package": pkg["label"], "children": kids_by_spu[k]["child"].tolist()})
                               for k in out["spu_key"]]
    out[[c for c in spu_cols if c in out.columns]].to_sql("spu", conn, if_exists="append", index=False)
    kid_attrs = []
    type_attrs = cfg.get("type_attributes") or []
    for r in kids.itertuples():
        a = attrs.loc[r.child].to_dict() if len(attrs) and r.child in attrs.index else {}
        kid_attrs.append(D.dumps({d: {"value": a.get(d, SEG.UNKNOWN), "backfill": int(a.get(f"{d}__bf", 0) or 0)}
                                  for d in (cfg.get("attribute_dims") or [])}))
    kids_out = kids.assign(run_id=run_id, attrs_json=kid_attrs,
                           color=[D.loads(x)["颜色"]["value"] if "颜色" in D.loads(x) else None for x in kid_attrs],
                           size=[D.loads(x)["尺寸"]["value"] if "尺寸" in D.loads(x) else None for x in kid_attrs])
    del type_attrs
    kids_out[[c.name for c in D.spu_child.columns]].to_sql("spu_child", conn, if_exists="append", index=False)
    if len(jr):
        jr.assign(run_id=run_id)[[c.name for c in D.judgment.columns if c.name in list(jr.columns) + ["run_id"]]] \
            .to_sql("judgment", conn, if_exists="append", index=False)
    pd.DataFrame(sig_rows).to_sql("signal_value", conn, if_exists="append", index=False, chunksize=20000)
    pd.DataFrame(seg_rows).to_sql("segment_info", conn, if_exists="append", index=False, chunksize=20000)
    conn.execute(D.compute_run.update().where(D.compute_run.c.id == run_id).values(
        status="success", ended_at=clock.now_iso(), excluded_fields_json=D.dumps(uf["excluded"])))
    return int(run_id)


def _launch_price(cm_by_child: dict[str, pd.DataFrame], children: list[str], lead: str, batch: str) -> float | None:
    """Sales ÷ units in the first month with sales, for the launch child (else the whole SPU)."""
    df = cm_by_child.get(lead)
    if df is not None:
        d = df[(df.index >= batch) & (df["child_units"] > 0) & df["child_sales"].notna()].sort_index()
        if len(d):
            return float(d["child_sales"].iloc[0] / d["child_units"].iloc[0])
    tot_u = tot_s = 0.0
    first = None
    for ch in children:
        df = cm_by_child.get(ch)
        if df is None:
            continue
        d = df[(df.index >= batch) & (df["child_units"] > 0)].sort_index()
        if len(d):
            m = d.index[0]
            first = m if first is None or m < first else first
    if first is None:
        return None
    for ch in children:
        df = cm_by_child.get(ch)
        if df is not None and first in df.index and df.at[first, "child_units"] > 0:
            tot_u += float(df.at[first, "child_units"])
            tot_s += float(df.at[first, "child_sales"] or 0)
    return tot_s / tot_u if tot_u else None


# ---- reading results ---------------------------------------------------------------------


def latest_run(conn: Connection, category_id: int, mode: str) -> dict[str, Any] | None:
    row = conn.execute(select(D.compute_run).where(
        D.compute_run.c.category_id == category_id, D.compute_run.c.mode == mode,
        D.compute_run.c.status == "success").order_by(D.compute_run.c.id.desc()).limit(1)).mappings().first()
    return dict(row) if row else None


def spus_frame(conn: Connection, run_id: int) -> pd.DataFrame:
    raw = conn.connection.driver_connection
    s = pd.read_sql_query("SELECT * FROM spu WHERE run_id = ?", raw, params=(run_id,))
    j = pd.read_sql_query("SELECT * FROM judgment WHERE run_id = ?", raw, params=(run_id,))
    j = j.drop(columns=["run_id", "rising"], errors="ignore")
    return s.merge(j, on="spu_key", how="left")


def signals_frame(conn: Connection, run_id: int, T: str | None = None) -> pd.DataFrame:
    raw = conn.connection.driver_connection
    if T:
        return pd.read_sql_query("SELECT * FROM signal_value WHERE run_id = ? AND t_month = ?", raw, params=(run_id, T))
    return pd.read_sql_query("SELECT * FROM signal_value WHERE run_id = ?", raw, params=(run_id,))


def segments_frame(conn: Connection, run_id: int, T: str) -> pd.DataFrame:
    raw = conn.connection.driver_connection
    return pd.read_sql_query("SELECT * FROM segment_info WHERE run_id = ? AND t_month = ?", raw, params=(run_id, T))


def stale_reasons(conn: Connection, category_id: int, run: dict[str, Any] | None) -> list[str]:
    """Why results based on `run` need recomputing (DEC-016)."""
    if run is None:
        return []
    out = []
    cv = CT.current_version(conn, category_id)
    if cv and cv["id"] != run["contract_version_id"]:
        out.append(f"字段约定已保存为 v{cv['version_no']}")
    cfg = CAT.current_version(conn, category_id)
    if cfg["id"] != run["config_version_id"]:
        out.append(f"品类配置已保存为 v{cfg['version_no']}")
    if SPU.merge_hash(conn, category_id) != run["merge_hash"]:
        out.append("SPU 归并已修改")
    pkg = PK.current_package(conn, category_id, run["mode"])
    if pkg and pkg["id"] != run["package_id"]:
        out.append(f"当前数据包已换为 {pkg['label']}")
    return out


def excluded_fields(run: dict[str, Any] | None) -> list[dict[str, str]]:
    return D.loads(run["excluded_fields_json"], []) if run else []


def purge_runs_except_latest(conn: Connection, category_id: int, keep: int = 3) -> None:
    """Keep result tables small: drop rows of old compute runs that no backtest refers to."""
    ids = [r[0] for r in conn.execute(text(
        "SELECT id FROM compute_run WHERE category_id=:c ORDER BY id DESC"), {"c": category_id})]
    used = {r[0] for r in conn.execute(text("SELECT DISTINCT compute_run_id FROM backtest_run"))}
    for rid in ids[keep * 2:]:
        if rid in used:
            continue
        for t in ("spu", "spu_child", "judgment", "signal_value", "segment_info"):
            conn.execute(text(f"DELETE FROM {t} WHERE run_id=:r"), {"r": rid})
