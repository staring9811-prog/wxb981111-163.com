"""Fixed health checks (F03: REQ-F03-01, AC-F03-01..03, DEC-022). Checks only read data."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.engine import Connection

from oppo import clock
from oppo import db as D
from oppo.core import categories as CAT
from oppo.core import data as DATA
from oppo.core import packages as PK

ITEMS = ("first_review_early", "family_span", "below_bought", "unknown_share", "parent_change", "dup_key")
PCT_ITEMS = {"first_review_early", "family_span", "below_bought", "unknown_share"}


def _lower_bound(label: Any) -> float | None:
    if label is None or (isinstance(label, float) and pd.isna(label)):
        return None
    m = re.search(r"(\d[\d,]*)\s*(k|K)?\+?", str(label))
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    return v * 1000 if m.group(2) else v


def _text(v: Any) -> str:
    return "无数据" if v is None or (isinstance(v, float) and pd.isna(v)) or v == "" else str(v)


def compute(b: DATA.Bundle, dup_rows: int) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    master = DATA.child_master(b)
    # 1. first review earlier than launch by more than 7 days
    m = master.dropna(subset=["launch_date", "first_review"]).copy()
    if len(m):
        m["gap"] = (pd.to_datetime(m["launch_date"]) - pd.to_datetime(m["first_review"])).dt.days
        hit = m[m["gap"] > 7].sort_values(["gap", "child"], ascending=[False, True])
        out["first_review_early"] = dict(
            numerator=len(hit), denominator=len(m), value=len(hit) / len(m) * 100,
            samples=[{"子ASIN": r.child, "父ASIN": r.parent, "品牌": _text(r.brand), "上架日期": r.launch_date,
                      "首次评分日期": r.first_review, "早于上架（天）": int(r.gap)} for r in hit.head(5).itertuples()])
    else:
        out["first_review_early"] = dict(numerator=0, denominator=0, value=None, samples=[], na="数据里没有首次评分日期")
    # 2. family launch span > 180 days
    fam = master.dropna(subset=["parent", "launch_date"]).copy()
    fam["ld"] = pd.to_datetime(fam["launch_date"])
    g = fam.groupby("parent").agg(n=("child", "count"), lo=("ld", "min"), hi=("ld", "max"), brand=("brand", "first"))
    g = g[g["n"] >= 2]
    g["span"] = (g["hi"] - g["lo"]).dt.days
    wide = g[g["span"] > 180].sort_values("span", ascending=False)
    out["family_span"] = dict(
        numerator=len(wide), denominator=len(g), value=(len(wide) / len(g) * 100) if len(g) else None,
        samples=[{"父ASIN": p, "品牌": _text(r.brand), "子体数": int(r.n), "最早上架": r.lo.date().isoformat(),
                  "最晚上架": r.hi.date().isoformat(), "跨度（天）": int(r.span)} for p, r in wide.head(5).iterrows()])
    # 3. child units below the "bought in past month" label lower bound
    c1 = b.c1
    if len(c1) and "bought_label" in c1 and c1["bought_label"].notna().any():
        lab = c1.dropna(subset=["bought_label"]).copy()
        lab["lb"] = lab["bought_label"].map(_lower_bound)
        lab = lab.dropna(subset=["lb", "child_units"])
        below = lab[lab["child_units"] < lab["lb"]].sort_values(["month", "child"])
        out["below_bought"] = dict(
            numerator=len(below), denominator=len(lab), value=(len(below) / len(lab) * 100) if len(lab) else None,
            samples=[{"子ASIN": r.child, "月份": r.month, "子体月销量": int(r.child_units), "标签": r.bought_label}
                     for r in below.head(5).itertuples()])
    else:
        out["below_bought"] = dict(numerator=0, denominator=0, value=None, samples=[],
                                   na="数据里没有“过去一个月购买”标签，不适用")
    # 4. unknown share per attribute dimension
    attrs = DATA.attr_table(b.c4)
    per_dim = []
    for dim in sorted(set(b.c4["dim"])) if len(b.c4) else []:
        col = attrs[dim].fillna("")
        unk = col.isin(["", "未知"])
        per_dim.append({"维度": dim, "未知": int(unk.sum()), "子体": int(len(col)),
                        "占比": float(unk.mean() * 100) if len(col) else 0.0,
                        "examples": attrs.loc[unk, "child"].head(5).tolist()})
    per_dim.sort(key=lambda d: (-d["占比"], d["维度"]))
    if per_dim:
        top = per_dim[0]
        brands = master.set_index("child")["brand"] if len(master) else pd.Series(dtype=object)
        last = (c1[c1["month"] == c1["month"].max()].groupby("child")["child_units"].sum()
                if len(c1) and "child_units" in c1 else pd.Series(dtype=float))
        dims = [d["维度"] for d in per_dim]
        rows = attrs.set_index("child")
        samples = []
        for c in top["examples"]:
            r = rows.loc[c]
            unknown = [d for d in dims if str(r.get(d) if pd.notna(r.get(d)) else "") in ("", "未知")]
            samples.append({"子ASIN": c, "品牌": _text(brands.get(c)), "“未知”的维度": "、".join(unknown),
                            "证据状态": _text(r.get(f"{top['维度']}__status")),
                            "上月销量": int(last[c]) if c in last.index and pd.notna(last[c]) else None})
        out["unknown_share"] = dict(numerator=top["未知"], denominator=top["子体"], value=top["占比"],
                                    detail={"dims": per_dim, "max_dim": top["维度"],
                                            "last_month": str(c1["month"].max()) if len(c1) else None},
                                    samples=samples)
    else:
        out["unknown_share"] = dict(numerator=0, denominator=0, value=None, samples=[], na="没有属性标签")
    # 5. children whose parent ASIN changes across months
    if len(c1):
        pc = c1.dropna(subset=["parent"]).groupby("child")["parent"].nunique()
        changed = sorted(pc[pc > 1].index)
        brands = master.set_index("child")["brand"] if len(master) else pd.Series(dtype=object)
        samples = []
        for ch in changed[:5]:
            seq = c1[c1["child"] == ch].dropna(subset=["parent"]).sort_values("month")
            prev = seq["parent"].shift()
            first = seq[(prev.notna()) & (seq["parent"] != prev)].iloc[0]
            samples.append({"子ASIN": ch, "品牌": _text(brands.get(ch)), "变化月份": first["month"],
                            "原父ASIN": prev[first.name], "新父ASIN": first["parent"]})
        out["parent_change"] = dict(numerator=len(changed), denominator=int(c1["child"].nunique()),
                                    value=float(len(changed)), samples=samples)
    else:
        out["parent_change"] = dict(numerator=0, denominator=0, value=0.0, samples=[])
    out["dup_key"] = dict(numerator=dup_rows, denominator=None, value=float(dup_rows), samples=[])
    return out


def status_of(item: str, res: dict[str, Any], thresholds: dict[str, Any]) -> str:
    if res.get("value") is None:
        return "na"
    th = thresholds.get(item)
    if th is None:
        return "normal"
    return "warn" if res["value"] > float(th) else "normal"


def run(conn: Connection, category_id: int, package_id: int) -> None:
    cfg = CAT.current_version(conn, category_id)
    b = DATA.load(conn, package_id, None)
    dup = conn.execute(text("SELECT COALESCE(SUM(affected_rows),0) FROM validation_item WHERE package_id=:p "
                            "AND check_name='unique_key'"), {"p": package_id}).scalar() or 0
    res = compute(b, int(dup))
    # dup_key samples: the excluded duplicate line numbers per file
    rows = conn.execute(text("SELECT file_code, sample_rows_json, affected_note FROM validation_item WHERE package_id=:p "
                             "AND check_name='unique_key' AND affected_rows>0"), {"p": package_id}).all()
    keys = {fc: (D.loads(note, {}) or {}).get("keys", {}) if (note or "").startswith("{") else {} for fc, _s, note in rows}
    res["dup_key"]["samples"] = [{"文件": fc, "主键值": keys[fc].get(str(line), "无数据"), "行号": line}
                                 for fc, s, _n in rows for line in D.loads(s, [])][:5]
    now = clock.now_iso()
    conn.execute(text("DELETE FROM health_result WHERE package_id=:p"), {"p": package_id})
    for item in ITEMS:
        r = res[item]
        conn.execute(D.health_result.insert().values(
            package_id=package_id, config_version_id=cfg["id"], item=item, value=r.get("value"),
            numerator=r.get("numerator"), denominator=r.get("denominator"),
            detail_json=D.dumps({"detail": r.get("detail"), "na": r.get("na")}), samples_json=D.dumps(r["samples"]),
            created_at=now))
    verify_fingerprints(conn, package_id)


def verify_fingerprints(conn: Connection, package_id: int) -> bool:
    """AC-F03-03: the read-only copy must be byte-identical to what was imported."""
    from pathlib import Path

    pkg = PK.get(conn, package_id)
    ok_all = True
    now = clock.now_iso()
    conn.execute(text("DELETE FROM fingerprint_check WHERE package_id=:p"), {"p": package_id})
    for f in PK.files(conn, package_id):
        path = Path(pkg["readonly_path"]) / f["filename"] if pkg and pkg["readonly_path"] else None
        sha_now = PK.sha256_file(path) if path and path.exists() else None
        ok = sha_now == f["sha256"]
        ok_all = ok_all and ok
        conn.execute(D.fingerprint_check.insert().values(package_id=package_id, file_code=f["file_code"],
                                                         sha_import=f["sha256"], sha_now=sha_now, ok=int(ok),
                                                         created_at=now))
    if not ok_all:  # DEC-022
        conn.execute(D.package.update().where(D.package.c.id == package_id).values(conclusion="block"))
    return ok_all


def results(conn: Connection, category_id: int, package_id: int) -> list[dict[str, Any]]:
    cfg = CAT.current_version(conn, category_id)["config"]
    th = cfg.get("health_thresholds") or {}
    rows = conn.execute(select(D.health_result).where(D.health_result.c.package_id == package_id)
                        .order_by(D.health_result.c.id)).mappings().all()
    acks = {r["item"]: dict(r) for r in conn.execute(select(D.health_ack).where(
        D.health_ack.c.package_id == package_id).order_by(D.health_ack.c.id)).mappings().all()}
    out = []
    for r in rows:
        d = dict(r)
        extra = D.loads(r["detail_json"], {}) or {}
        d["detail"] = extra.get("detail")
        d["na"] = extra.get("na")
        d["samples"] = D.loads(r["samples_json"], [])
        d["label"] = CAT.HEALTH_LABELS[r["item"]]
        d["threshold"] = th.get(r["item"])
        st = status_of(r["item"], d, th)
        d["ack"] = acks.get(r["item"])
        d["status"] = "acked" if st == "warn" and d["ack"] else st
        out.append(d)
    return out


def open_warnings(conn: Connection, category_id: int) -> list[dict[str, Any]]:
    pkg = PK.current_package(conn, category_id, "history") or PK.current_package(conn, category_id, "cross")
    if not pkg:
        return []
    return [r for r in results(conn, category_id, pkg["id"]) if r["status"] == "warn"]


class AckError(Exception):
    pass


def acknowledge(conn: Connection, category_id: int, package_id: int, item: str, note: str, operator: str) -> None:
    if not (note or "").strip():
        raise AckError("请填写说明")
    if item not in ITEMS:
        raise AckError("体检项不存在")
    conn.execute(D.health_ack.insert().values(category_id=category_id, package_id=package_id, item=item,
                                              note=note.strip(), created_by=operator, created_at=clock.now_iso()))
    conn.execute(D.change_log.insert().values(
        category_id=category_id, object="体检", object_id=str(package_id), action="标为已知晓", item=item,
        before=None, after=D.dumps(note.strip()), created_by=operator, created_at=clock.now_iso()))


def fingerprint_rows(conn: Connection, package_id: int) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(select(D.fingerprint_check).where(
        D.fingerprint_check.c.package_id == package_id).order_by(D.fingerprint_check.c.id)).mappings().all()]
