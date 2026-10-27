"""Load a package's parsed rows as DataFrames, honouring the field contract (AC-F02-04)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
from sqlalchemy.engine import Connection

# raw column -> (contract file, field)
FIELD_MAP = {
    "c1": {"month": "月份", "child": "子ASIN", "parent": "当月父ASIN", "brand": "品牌", "seller": "卖家", "title": "标题",
           "launch_date": "上架日期", "child_units": "子体月销量", "child_sales": "子体月销售额",
           "parent_units": "父体月销量", "bsr": "小类BSR", "node": "类目节点", "fulfillment": "配送方式",
           "variant_count": "变体数", "first_review": "首次评分日期", "spu_no": "SPU编号",
           "bought_label": "过去一个月购买", "price": "当月价格", "rating": "当月评分", "bullets": "五点描述"},
    "c2": {"child": "子ASIN", "parent": "父ASIN", "brand": "品牌", "title": "标题", "launch_date": "上架日期",
           "fulfillment": "配送方式", "variant_count": "变体数", "first_review": "首次评分日期", "spu_no": "SPU编号",
           "bullets": "五点描述"},
    "c3": {"month": "月份", "child": "子ASIN", "child_units": "子体月销量", "child_sales": "子体月销售额", "bsr": "小类BSR",
           "parent_units": "父体月销量"},
    "c5": {"keyword": "关键词", "month": "月份", "volume": "月搜索量", "tags": "关键词属性标签", "purchases": "月购买量"},
    "c6": {"review_id": "评论ID", "asin": "ASIN", "level": "归属级别", "review_date": "评论日期", "stars": "星级",
           "pain_code": "痛点事件代码", "structural": "是否结构类痛点", "label_version": "标注版本"},
    "c7": {"name": "立项名称", "project_date": "立项日期", "segment_or_attr": "关联细分或属性",
           "launch_date": "上架日期", "asin": "对应ASIN"},
}
CONTRACT_OF = {"c1": "C1", "c2": "C2", "c3": "C3", "c5": "C5", "c6": "C6", "c7": "C7"}
KEY_COLS = {"month", "child", "keyword", "review_id", "name"}


@dataclass
class Bundle:
    package_id: int
    kind: str
    months_from: str | None
    months_to: str | None
    c1: pd.DataFrame
    c2: pd.DataFrame
    c3: pd.DataFrame
    c4: pd.DataFrame  # long: child, dim, value, status
    c5: pd.DataFrame
    c6: pd.DataFrame
    c7: pd.DataFrame
    dropped: list[str] = field(default_factory=list)
    has: dict[str, bool] = field(default_factory=dict)


def _read(conn: Connection, table: str, package_id: int) -> pd.DataFrame:
    return pd.read_sql_query(f"SELECT * FROM {table} WHERE package_id = ?", conn.connection.driver_connection,
                             params=(package_id,))


def load(conn: Connection, package_id: int, confirmed: set[tuple[str, str]] | None) -> Bundle:
    """confirmed=None loads every field (health checks run before the contract is confirmed)."""
    from oppo.core import packages as PK

    pkg = PK.get(conn, package_id)
    assert pkg is not None
    frames: dict[str, pd.DataFrame] = {}
    dropped: list[str] = []
    has: dict[str, bool] = {}
    for short in ("c1", "c2", "c3", "c5", "c6", "c7"):
        df = _read(conn, f"raw_{short}", package_id)
        has[short] = len(df) > 0
        if confirmed is not None:
            fmap = FIELD_MAP[short]
            for col, fname in fmap.items():
                if col in KEY_COLS:
                    continue
                if (CONTRACT_OF[short], fname) not in confirmed and col in df.columns:
                    if df[col].notna().any():
                        dropped.append(f"{CONTRACT_OF[short]} {fname}")
                    df[col] = None
        frames[short] = df
    c4 = _read(conn, "raw_c4", package_id)
    has["c4"] = len(c4) > 0
    if confirmed is not None and len(c4):
        allowed = {f for (fc, f) in confirmed if fc == "C4"}
        if allowed:
            keep_dims = {d for d in c4["dim"].unique() if d in allowed}
            status_ok = {d for d in keep_dims if f"{d}证据状态" in allowed}
            c4 = c4[c4["dim"].isin(keep_dims)].copy()
            c4.loc[~c4["dim"].isin(status_ok), "status"] = None
        else:
            c4 = c4.iloc[0:0].copy()
    for num in ("child_units", "child_sales", "parent_units", "bsr", "variant_count", "price", "rating"):
        for short in ("c1", "c2", "c3"):
            if num in frames[short].columns:
                frames[short][num] = pd.to_numeric(frames[short][num], errors="coerce")
    for short, cols in (("c5", ("volume", "purchases")), ("c6", ("stars", "structural"))):
        for col in cols:
            frames[short][col] = pd.to_numeric(frames[short][col], errors="coerce")
    return Bundle(package_id, pkg["kind"], pkg["months_from"], pkg["months_to"], frames["c1"], frames["c2"],
                  frames["c3"], c4, frames["c5"], frames["c6"], frames["c7"], dropped=sorted(set(dropped)), has=has)


def attr_table(c4: pd.DataFrame) -> pd.DataFrame:
    """Wide child × dim table of values and statuses."""
    if c4.empty:
        return pd.DataFrame(columns=["child"])
    v = c4.pivot_table(index="child", columns="dim", values="value", aggfunc="first")
    s = c4.pivot_table(index="child", columns="dim", values="status", aggfunc="first")
    s.columns = [f"{c}__status" for c in s.columns]
    out = v.join(s, how="outer").reset_index()
    return out


def child_master(b: Bundle) -> pd.DataFrame:
    """One row per child across C1 ∪ C2: parent, brand, title, launch date, first review, SPU number, bullets."""
    cols = ["child", "parent", "brand", "title", "launch_date", "first_review", "spu_no", "bullets", "fulfillment",
            "variant_count", "in_c2"]
    parts = []
    if len(b.c2):
        c2 = b.c2.copy()
        c2["in_c2"] = 1
        parts.append(c2[cols])
    if len(b.c1):
        # Earliest row per child: static attributes must not depend on later months (AC-F06-03).
        c1 = b.c1.sort_values(["child", "month"]).groupby("child", as_index=False).first()
        c1["in_c2"] = 0
        parts.append(c1[cols])
    if not parts:
        return pd.DataFrame(columns=cols)
    allc = pd.concat(parts, ignore_index=True)
    # C2 wins for new products; fill gaps from C1.
    allc = allc.sort_values(["child", "in_c2"], ascending=[True, False])
    first = allc.groupby("child", as_index=False).first()
    any_c2 = allc.groupby("child")["in_c2"].max()
    first["in_c2"] = first["child"].map(any_c2).fillna(0).astype(int)
    return first
