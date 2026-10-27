"""SPU merging and new-product identification (F04: REQ-F04-01/02, AC-F04-01..09, DEC-009/037/038)."""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from oppo import clock
from oppo import db as D
from oppo.core import contract as CT
from oppo.core import data as DATA

BASES = ("标题主干相同", "标题主干高度相似且类型属性一致", "五点描述相同")
SIMILAR_ATTRS = ("形态", "安装方式", "台面形态", "元素")
COLORS = {
    "white", "black", "gray", "grey", "blue", "green", "navy", "oak", "walnut", "espresso", "brown", "beige", "natural",
    "cream", "ivory", "teal", "sage", "charcoal", "taupe", "pink", "red", "gold", "silver", "chrome", "matte", "light",
    "dark", "wood", "tone", "two",
}
GENERIC = {
    "bathroom", "vanity", "vanities", "cabinet", "cabinets", "with", "and", "set", "sink", "sinks", "top", "inch",
    "inches", "in", "for", "the", "a", "an", "single", "double", "combo", "w", "x", "of", "to", "on", "ft",
}


class MergeError(Exception):
    pass


def title_stem(title: str | None, brand: str | None = None) -> str:
    if not title:
        return ""
    s = title.lower()
    if brand:
        s = s.replace(brand.lower(), " ")
    s = re.sub(r"\d+(?:\.\d+)?\s*(?:\"|”|″|''|inch(?:es)?|in\b|-inch)", " ", s)
    s = re.sub(r"[^a-z一-鿿]+", " ", s)
    words = [w for w in s.split() if w not in COLORS and w not in GENERIC and len(w) > 1]
    return " ".join(words)


def bullets_norm(b: str | None) -> str:
    if not b or (isinstance(b, float) and pd.isna(b)):
        return ""
    return re.sub(r"[\W_]+", "", str(b).lower())


def _parents_frame(b: DATA.Bundle, use_spu_no: bool) -> pd.DataFrame:
    master = DATA.child_master(b)
    if master.empty:
        return pd.DataFrame()
    attrs = DATA.attr_table(b.c4).set_index("child") if len(b.c4) else pd.DataFrame()
    rows = []
    for parent, g in master.dropna(subset=["parent"]).groupby("parent"):
        if use_spu_no and g["spu_no"].notna().all():
            continue  # DEC-038: children with confirmed SPU numbers are grouped by number
        titles = g["title"].dropna().tolist()
        title = max(set(titles), key=titles.count) if titles else ""
        brand = g["brand"].dropna().iloc[0] if g["brand"].notna().any() else ""
        bl = g["bullets"].dropna()
        attr_vals: dict[str, Any] = {}
        sizes: list[str] = []
        for d in SIMILAR_ATTRS + ("尺寸",):
            if len(attrs) and d in attrs.columns:
                vals = attrs.reindex(g["child"])[d].dropna()
                vals = [v for v in vals if v not in ("", "未知")]
                if d == "尺寸":
                    sizes = sorted(set(vals), key=lambda x: float(x) if re.match(r"^\d+(\.\d+)?$", str(x)) else 0)
                else:
                    attr_vals[d] = max(set(vals), key=vals.count) if vals else None
        rows.append({
            "parent": parent, "brand": brand, "title": title, "stem": title_stem(title, brand),
            "bullets": bl.iloc[0] if len(bl) else None, "bnorm": bullets_norm(bl.iloc[0]) if len(bl) else "",
            "children": sorted(g["child"].tolist()), "new": int(g["in_c2"].max()), **attr_vals, "sizes": sizes,
        })
    return pd.DataFrame(rows)


def _groups(items: list[str], pairs: list[tuple[str, str]]) -> list[list[str]]:
    parent = {i: i for i in items}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, c in pairs:
        ra, rc = find(a), find(c)
        if ra != rc:
            parent[max(ra, rc)] = min(ra, rc)
    out: dict[str, list[str]] = {}
    for i in items:
        out.setdefault(find(i), []).append(i)
    return [sorted(v) for v in out.values() if len(v) > 1]


def suggest(b: DATA.Bundle, use_spu_no: bool, use_bullets: bool) -> list[dict[str, Any]]:
    pf = _parents_frame(b, use_spu_no)
    if pf.empty:
        return []
    out: list[dict[str, Any]] = []
    for brand, g in pf.groupby("brand"):
        if len(g) < 2 or not g["new"].any():
            continue
        g = g.set_index("parent")
        taken: set[frozenset[str]] = set()
        # 1. identical title stem
        for stem, sub in g.groupby("stem"):
            if stem and len(sub) > 1:
                grp = sorted(sub.index)
                taken.add(frozenset(grp))
                out.append(_suggestion(brand, grp, BASES[0], g, use_bullets))
        # 3. identical bullets (only when the field is provided and confirmed, D-29)
        if use_bullets:
            for _bn, sub in g[g["bnorm"] != ""].groupby("bnorm"):
                grp = sorted(sub.index)
                if len(grp) > 1 and not any(frozenset(grp) <= t for t in taken):
                    taken.add(frozenset(grp))
                    out.append(_suggestion(brand, grp, BASES[2], g, use_bullets))
        # 2. highly similar stem and identical type attributes
        parents = sorted(g.index)
        pairs = []
        for i, a in enumerate(parents):
            for c in parents[i + 1:]:
                if any({a, c} <= t for t in taken):
                    continue
                sa, sc = g.at[a, "stem"], g.at[c, "stem"]
                if not sa or not sc or sa == sc:
                    continue
                if SequenceMatcher(None, sa, sc).ratio() < 0.9:
                    continue
                ra, rc = g.loc[a], g.loc[c]
                if all(ra.get(d) and ra.get(d) == rc.get(d) for d in SIMILAR_ATTRS):
                    pairs.append((a, c))
        for grp in _groups(parents, pairs):
            out.append(_suggestion(brand, grp, BASES[1], g, use_bullets))
    return out


def _suggestion(brand: str, parents: list[str], basis: str, g: pd.DataFrame, use_bullets: bool) -> dict[str, Any]:
    detail = []
    for p in parents:
        r = g.loc[p]
        detail.append({
            "parent": p, "title": r["title"], "stem": r["stem"], "children": len(r["children"]),
            "sizes": "、".join(f"{s}″" for s in r["sizes"]) if r["sizes"] else "无数据",
            **{d: (r.get(d) or "无数据") for d in SIMILAR_ATTRS},
            "bullets": (str(r["bullets"])[:48] + ("…" if len(str(r["bullets"])) > 48 else ""))
            if use_bullets and r["bullets"] else "无数据",
        })
    return {"brand": brand, "parents": parents, "basis": basis, "child_count": int(sum(len(g.loc[p]["children"])
                                                                                       for p in parents)),
            "detail": detail}


def _fields_state(conn: Connection, category_id: int, package_id: int) -> tuple[bool, bool, set[tuple[str, str]]]:
    uf = CT.usable_fields(conn, category_id, package_id)
    conf = uf["confirmed"]
    use_no = ("C1", "SPU编号") in conf or ("C2", "SPU编号") in conf
    use_bul = ("C1", "五点描述") in conf or ("C2", "五点描述") in conf
    return use_no, use_bul, conf


def refresh_suggestions(conn: Connection, category_id: int, package_id: int, operator: str) -> int:
    """(Re)generate pending suggestions for the package once a field contract exists."""
    if CT.current_version(conn, category_id) is None:
        return 0
    use_no, use_bul, conf = _fields_state(conn, category_id, package_id)
    b = DATA.load(conn, package_id, conf)
    found = suggest(b, use_no, use_bul)
    existing = {(r["basis"], r["parents_json"]): r for r in conn.execute(
        select(D.merge_suggestion).where(D.merge_suggestion.c.category_id == category_id)).mappings().all()}
    n = 0
    now = clock.now_iso()
    wanted = set()
    for s in found:
        key = (s["basis"], D.dumps(s["parents"]))
        wanted.add(key)
        if key in existing:
            conn.execute(D.merge_suggestion.update().where(D.merge_suggestion.c.id == existing[key]["id"]).values(
                detail_json=D.dumps(s["detail"]), child_count=s["child_count"]))
            continue
        count = conn.execute(select(func.count()).select_from(D.merge_suggestion)).scalar() or 0
        conn.execute(D.merge_suggestion.insert().values(
            category_id=category_id, code=f"MS-{count + 1:04d}", brand=s["brand"], parents_json=D.dumps(s["parents"]),
            child_count=s["child_count"], basis=s["basis"], detail_json=D.dumps(s["detail"]), status="pending",
            package_id=package_id, created_by=operator, created_at=now))
        n += 1
    # Pending suggestions that no longer apply (e.g. now grouped by SPU number) are withdrawn.
    for key, r in existing.items():
        if key not in wanted and r["status"] == "pending":
            conn.execute(D.merge_suggestion.update().where(D.merge_suggestion.c.id == r["id"]).values(
                status="withdrawn", decided_at=now))
    return n


def suggestions(conn: Connection, category_id: int, status: str | None = None) -> list[dict[str, Any]]:
    q = select(D.merge_suggestion).where(D.merge_suggestion.c.category_id == category_id)
    if status:
        q = q.where(D.merge_suggestion.c.status == status)
    rows = conn.execute(q.order_by(D.merge_suggestion.c.id)).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["parents"] = D.loads(r["parents_json"], [])
        d["detail"] = D.loads(r["detail_json"], [])
        out.append(d)
    return out


def active_merges(conn: Connection, category_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(select(D.merge).where(D.merge.c.category_id == category_id, D.merge.c.status == "active")
                        .order_by(D.merge.c.id)).mappings().all()
    return [{**dict(r), "parents": D.loads(r["parents_json"], [])} for r in rows]


def all_merges(conn: Connection, category_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(select(D.merge).where(D.merge.c.category_id == category_id).order_by(D.merge.c.id.desc())
                        ).mappings().all()
    return [{**dict(r), "parents": D.loads(r["parents_json"], [])} for r in rows]


def merge_hash(conn: Connection, category_id: int) -> str:
    groups = sorted(D.dumps(sorted(m["parents"])) for m in active_merges(conn, category_id))
    return hashlib.sha256("\n".join(groups).encode()).hexdigest()


def _next_merge_code(conn: Connection) -> str:
    n = conn.execute(select(func.count()).select_from(D.merge)).scalar() or 0
    return f"MG-{n + 1:04d}"


def _log(conn: Connection, category_id: int, obj_id: str, action: str, before: Any, after: Any, operator: str) -> None:
    conn.execute(D.change_log.insert().values(
        category_id=category_id, object="SPU 归并", object_id=obj_id, action=action, item=obj_id,
        before=D.dumps(before), after=D.dumps(after), created_by=operator, created_at=clock.now_iso()))


def decide(conn: Connection, category_id: int, ids: list[int], decision: str, operator: str,
           source: str = "逐条") -> dict[str, int]:
    """Confirm or reject suggestions; already-handled ones are skipped and counted (state machine)."""
    done = skipped = 0
    now = clock.now_iso()
    for sid in ids:
        s = conn.execute(select(D.merge_suggestion).where(D.merge_suggestion.c.id == sid)).mappings().first()
        if s is None or s["status"] != "pending":
            skipped += 1
            continue
        conn.execute(D.merge_suggestion.update().where(D.merge_suggestion.c.id == sid).values(
            status="confirmed" if decision == "confirm" else "rejected", source=source, decided_by=operator,
            decided_at=now))
        if decision == "confirm":
            parents = set(D.loads(s["parents_json"], []))
            overlapping = [m for m in active_merges(conn, category_id) if parents & set(m["parents"])]
            for m in overlapping:
                parents |= set(m["parents"])
            code = _next_merge_code(conn)
            mid = conn.execute(D.merge.insert().values(
                category_id=category_id, code=code, suggestion_id=sid, parents_json=D.dumps(sorted(parents)),
                status="active", source=source, created_by=operator, created_at=now)).inserted_primary_key[0]
            for m in overlapping:
                conn.execute(D.merge.update().where(D.merge.c.id == m["id"]).values(
                    status="revised", ended_by=operator, ended_at=now, superseded_by=mid))
            _log(conn, category_id, code, f"确认合并建议 {s['code']}（{source}）", None, sorted(parents), operator)
        else:
            _log(conn, category_id, s["code"], "拒绝合并建议", D.loads(s["parents_json"]), None, operator)
        done += 1
    return {"done": done, "skipped": skipped}


def confirm_by_basis(conn: Connection, category_id: int, basis: str, operator: str) -> dict[str, int]:
    if basis not in BASES:
        raise MergeError(f"匹配依据只能是：{'、'.join(BASES)}")
    ids = [s["id"] for s in suggestions(conn, category_id, "pending") if s["basis"] == basis]
    return decide(conn, category_id, ids, "confirm", operator, source="批量确认")


def parent_info(conn: Connection, package_id: int) -> dict[str, dict[str, Any]]:
    """parent ASIN → brand, child count and a title, from the package's C2 (new products) and C1 rows."""
    raw = conn.connection.driver_connection
    c2 = pd.read_sql_query("SELECT child, parent, brand, title FROM raw_c2 WHERE package_id = ?", raw,
                           params=(package_id,))
    c1 = pd.read_sql_query("SELECT child, parent, brand, title, month FROM raw_c1 WHERE package_id = ? "
                           "ORDER BY child, month", raw, params=(package_id,))
    c1 = c1.groupby("child", as_index=False).first() if len(c1) else c1
    allc = pd.concat([c2.assign(o=0), c1.drop(columns=["month"], errors="ignore").assign(o=1)], ignore_index=True)
    allc = allc.dropna(subset=["child"]).sort_values(["child", "o"]).groupby("child", as_index=False).first()
    out: dict[str, dict[str, Any]] = {}
    for parent, g in allc.dropna(subset=["parent"]).groupby("parent"):
        brands = g["brand"].dropna()
        titles = g["title"].dropna().tolist()
        out[str(parent)] = {"brand": str(brands.iloc[0]) if len(brands) else "",
                            "children": int(g["child"].nunique()),
                            "title": max(set(titles), key=titles.count) if titles else ""}
    return out


def revise(conn: Connection, category_id: int, code: str, operator: str, keep_parents: list[str] | None = None,
           note: str = "", add_parents: list[str] | None = None, package_id: int | None = None) -> str | None:
    """Split (keep_parents=None) or modify an active merge (AC-F04-05); returns the new merge code if any.

    add_parents: parent ASINs to bring into the merge; they must be in the package (`package_id`), share the
    merge's brand and not belong to another active merge."""
    m = conn.execute(select(D.merge).where(D.merge.c.code == code, D.merge.c.category_id == category_id)
                     ).mappings().first()
    if m is None or m["status"] != "active":
        raise MergeError("该归并不存在或已失效")
    before = D.loads(m["parents_json"], [])
    now = clock.now_iso()
    if keep_parents is None and not add_parents:
        conn.execute(D.merge.update().where(D.merge.c.id == m["id"]).values(
            status="split", ended_by=operator, ended_at=now, note=note or None))
        _log(conn, category_id, code, "拆分归并", before, [[p] for p in before], operator)
        return None
    keep = sorted(set(keep_parents if keep_parents is not None else before) & set(before))
    extra = sorted({p.strip() for p in (add_parents or []) if p and p.strip()} - set(before))
    if extra:
        if package_id is None:
            raise MergeError("没有当前数据包，不能加入父 ASIN")
        info = parent_info(conn, package_id)
        brand = next((info[p]["brand"] for p in before if p in info and info[p]["brand"]), None)
        others = {p: x["code"] for x in active_merges(conn, category_id) if x["id"] != m["id"] for p in x["parents"]}
        for p in extra:
            if p not in info:
                raise MergeError(f"父 ASIN {p} 不在当前数据包中")
            if brand is not None and info[p]["brand"] != brand:
                raise MergeError(f"父 ASIN {p} 的品牌是 {info[p]['brand'] or '未知'}，只能加入同品牌（{brand}）的父 ASIN")
            if p in others:
                raise MergeError(f"父 ASIN {p} 已在归并 {others[p]} 中，请先拆分那条归并")
        keep = sorted(set(keep) | set(extra))
    if len(keep) < 2:
        raise MergeError("修改后至少要保留 2 个父 ASIN；只剩 1 个请用拆分")
    if keep == sorted(before):
        raise MergeError("没有修改")
    new_code = _next_merge_code(conn)
    mid = conn.execute(D.merge.insert().values(
        category_id=category_id, code=new_code, suggestion_id=m["suggestion_id"], parents_json=D.dumps(keep),
        status="active", source="修改", note=note or None, created_by=operator, created_at=now)).inserted_primary_key[0]
    conn.execute(D.merge.update().where(D.merge.c.id == m["id"]).values(
        status="revised", ended_by=operator, ended_at=now, superseded_by=mid, note=note or None))
    _log(conn, category_id, code, f"修改归并 → {new_code}", before, keep, operator)
    return new_code


def merge_log(conn: Connection, category_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(select(D.change_log).where(D.change_log.c.category_id == category_id,
                                                   D.change_log.c.object == "SPU 归并").order_by(
        D.change_log.c.id.desc())).mappings().all()
    return [dict(r) for r in rows]


# ---- SPU construction ----------------------------------------------------------------------


def build(conn: Connection, category_id: int, b: DATA.Bundle, use_spu_no: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Group children into SPUs; return (spus, children) frames."""
    master = DATA.child_master(b)
    if master.empty:
        return pd.DataFrame(), pd.DataFrame()
    merges = active_merges(conn, category_id)
    parent_to_merge = {p: m["code"] for m in merges for p in m["parents"]}
    keys, sources, codes = [], [], []
    for r in master.itertuples():
        if use_spu_no and isinstance(r.spu_no, str) and r.spu_no:
            keys.append(f"N:{r.spu_no}")
            sources.append("编号")
            codes.append(None)
        elif isinstance(r.parent, str) and r.parent in parent_to_merge:
            keys.append(f"M:{parent_to_merge[r.parent]}")
            sources.append("已确认建议")
            codes.append(parent_to_merge[r.parent])
        else:
            keys.append(f"P:{r.parent}")
            sources.append("暂按父体")
            codes.append(None)
    master = master.assign(spu_key=keys, source=sources, merge_code=codes)
    master["launch_dt"] = pd.to_datetime(master["launch_date"], errors="coerce")
    master["first_dt"] = pd.to_datetime(master["first_review"], errors="coerce")
    rows = []
    child_rows = []
    for key, g in master.groupby("spu_key", sort=True):
        g = g.sort_values(["launch_dt", "child"])
        launch = g["launch_dt"].min()
        if pd.isna(launch):
            continue
        same = g[g["launch_dt"] == launch]
        launch_child = sorted(same["child"])[0]
        first_min = g["first_dt"].min()
        relaunch = int(pd.notna(first_min) and (launch - first_min).days > 7)
        lead = g[g["child"] == launch_child].iloc[0]
        titles = g["title"].dropna()
        parents = sorted(set(g["parent"].dropna()))
        display = key.split(":", 1)[1] if key.startswith(("N:", "M:")) else f"SPU-{parents[0] if parents else lead.child}"
        rows.append({
            "spu_key": key, "display_id": display, "brand": lead.brand, "title": titles.iloc[0] if len(titles) else "",
            "source": g["source"].iloc[0], "merge_code": g["merge_code"].dropna().iloc[0]
            if g["merge_code"].notna().any() else None, "parents_json": D.dumps(parents),
            "launch_date": launch.date().isoformat(), "launch_child": launch_child, "same_day_count": int(len(same)),
            "batch": launch.strftime("%Y-%m"), "relaunch": relaunch,
            "first_review_min": first_min.date().isoformat() if pd.notna(first_min) else None,
            "new_variant_count": int((g["launch_dt"] > launch).sum()), "child_count": int(len(g)),
            "fulfillment": lead.fulfillment, "variant_count": lead.variant_count, "in_c2": int(g["in_c2"].max()),
        })
        for c in g.itertuples():
            child_rows.append({
                "spu_key": key, "child": c.child, "parent": c.parent, "launch_date": c.launch_date,
                "first_review": c.first_review, "new_variant": int(pd.notna(c.launch_dt) and c.launch_dt > launch),
            })
    return pd.DataFrame(rows), pd.DataFrame(child_rows)
