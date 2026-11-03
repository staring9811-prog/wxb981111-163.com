"""决策卡读取分析数据的薄适配层。

优先调用分析组的 `pdt/core/panel.py`（接口见 开发约定.md）；它还不存在时，用本文件里的最小实现按同一数据口径从
Snapshot / Product / Tag / Batch 现算，保证决策卡、台账能先跑通。panel.py 一旦提供，这里自动改用它，不再自算。

口径（开发约定"数据口径"）：
- 框键 = f"{尺寸段} · {装} · {形态}"；份额、溢价、评分差、新品占比只在同一渠道同一框内算；
- Product.excluded 的商品不进入；标签取已确认值，其次自动值（queued 也参与）；
- 份额 = 该取值销量 ÷ 框内该属性已知的销量；价比 = 价格 ÷ 同月同框中位价；新品 = 上架 ≤ 6 个月。
"""
import numpy as np
import pandas as pd
from sqlalchemy import select

from ..db import session
from ..models import Batch, Product, Snapshot, Tag

TAGS = ["尺寸段", "装", "形态", "台面材质", "元素", "主色", "柜体材质"]
BANDS = [(0, 200, "< $200"), (200, 250, "$200–250"), (250, 300, "$250–300"), (300, 400, "$300–400"), (400, 1e12, "≥ $400")]


def _panel_module():
    try:
        from . import panel  # 分析组提供
        return panel
    except ImportError:
        return None


def using_fallback() -> bool:
    return _panel_module() is None


def _mdiff(a: str, b: str) -> int:
    """a − b 的月数（YYYY-MM）。"""
    return (int(a[:4]) - int(b[:4])) * 12 + int(a[5:7]) - int(b[5:7])


def _load_panel_fallback(channel: str) -> pd.DataFrame:
    with session() as s:
        snaps = s.execute(select(Snapshot.month, Snapshot.item_id, Snapshot.price, Snapshot.units, Snapshot.revenue,
                                 Snapshot.rank, Snapshot.rating, Snapshot.ratings_count)
                          .where(Snapshot.channel == channel)).all()
        prods = s.execute(select(Product.item_id, Product.parent, Product.family_key, Product.series, Product.brand,
                                 Product.title, Product.image_url, Product.link, Product.listed_at, Product.excluded)
                          .where(Product.channel == channel)).all()
        tags = s.execute(select(Tag.item_id, Tag.tag, Tag.value, Tag.auto_value, Tag.status)
                         .where(Tag.channel == channel)).all()
    cols = ["month", "item_id", "price", "units", "revenue", "rank", "rating", "ratings_count"]
    df = pd.DataFrame(snaps, columns=cols)
    pr = pd.DataFrame(prods, columns=["item_id", "parent", "family_key", "series", "brand", "title", "image_url", "link", "listed_at", "excluded"])
    if df.empty or pr.empty:
        return pd.DataFrame(columns=cols + ["parent", "family_key", "series", "brand", "title", "image_url", "link", "listed_at", "age_months", "frame"] + TAGS)
    pr = pr[~pr["excluded"].astype(bool)].drop(columns="excluded")
    df = df.merge(pr, on="item_id", how="inner")
    tv = {}
    for item, tag, value, auto, status in tags:
        v = value if status == "confirmed" else (value or auto)
        if v:
            tv[(item, tag)] = v
    for t in TAGS:
        df[t] = [tv.get((i, t)) for i in df["item_id"]]
    df["age_months"] = [(_mdiff(m, la[:7]) + 1) if la else np.nan for m, la in zip(df["month"], df["listed_at"])]
    ok = df["尺寸段"].notna() & df["装"].notna() & df["形态"].notna()
    df["frame"] = np.where(ok, df["尺寸段"].astype(str) + " · " + df["装"].astype(str) + " · " + df["形态"].astype(str), None)
    for c in ("price", "units", "revenue", "rank", "rating", "ratings_count"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


_cache: dict = {}


def load_panel(channel: str) -> pd.DataFrame:
    m = _panel_module()
    if m is not None:
        return m.load_panel(channel)
    if channel not in _cache:
        _cache[channel] = _load_panel_fallback(channel)
    return _cache[channel]


def clear_cache():
    _cache.clear()


def _has(series: pd.Series, value: str) -> pd.Series:
    """取值匹配；多值标签（元素）用 | 分隔。"""
    return series.fillna("").astype(str).map(lambda x: value in x.split("|"))


def _wmed(x, w):
    x, w = np.asarray(x, float), np.asarray(w, float)
    k = ~np.isnan(x) & ~np.isnan(w) & (w > 0)
    x, w = x[k], w[k]
    if not len(x):
        return None
    o = np.argsort(x)
    x, w = x[o], w[o]
    c = np.cumsum(w)
    return float(x[np.searchsorted(c, c[-1] / 2)])


def _wavg(x, w):
    x, w = np.asarray(x, float), np.asarray(w, float)
    k = ~np.isnan(x) & ~np.isnan(w) & (w > 0)
    return float((x[k] * w[k]).sum() / w[k].sum()) if k.any() else None


def _frame_rows(channel, frame, attr):
    df = load_panel(channel)
    if df.empty or attr not in df.columns:
        return df.iloc[0:0]
    d = df[(df["frame"] == frame)].copy()
    d["pratio"] = d["price"] / d.groupby("month")["price"].transform("median")
    return d


def _star_months(channel) -> set:
    with session() as s:
        return {m for (m,) in s.execute(select(Batch.month).where(Batch.channel == channel, Batch.star.is_(True)))}


def unit_timeseries(channel, frame, attr, value):
    m = _panel_module()
    if m is not None:
        return m.unit_timeseries(channel, frame, attr, value)
    d = _frame_rows(channel, frame, attr)
    if d.empty:
        return []
    known = d[d[attr].notna() & (d[attr].astype(str) != "")]
    stars = _star_months(channel)
    out = []
    for mon, g in known.groupby("month"):
        u = g[_has(g[attr], value)]
        fu = g["units"].sum()
        uu = u["units"].sum()
        newu = u.loc[u["age_months"] <= 6, "units"].sum()
        out.append(dict(month=mon, units=float(uu), share=float(uu / fu) if fu else None,
                        newshare=float(newu / uu) if uu else None,
                        frame_newshare=float(g.loc[g["age_months"] <= 6, "units"].sum() / fu) if fu else None,
                        premium=_wmed(u["pratio"], u["units"]), median_price=_wmed(u["price"], u["units"]),
                        rating=_wavg(u["rating"], u["units"]), frame_rating=_wavg(g["rating"], g["units"]),
                        star=mon in stars, families=int(u["family_key"].nunique()), frame_units=float(fu)))
    return sorted(out, key=lambda r: r["month"])


def unit_skus(channel, frame, attr, value, top=20):
    m = _panel_module()
    if m is not None:
        return m.unit_skus(channel, frame, attr, value, top=top)
    d = _frame_rows(channel, frame, attr)
    if d.empty:
        return []
    u = d[_has(d[attr], value)]
    rows = []
    for item, g in u.groupby("item_id"):
        g = g.sort_values("month")
        pk = g.loc[g["units"].fillna(-1).idxmax()]
        top50 = g[g["rank"] <= 50]
        spec = " · ".join(str(x) for x in (g[attr].iloc[0], g["元素"].iloc[0] if attr != "元素" else None, g["主色"].iloc[0]) if x and str(x) != "nan")
        rows.append(dict(
            item_id=item, link=g["link"].iloc[0] or "", image_url=g["image_url"].iloc[0] or "", brand=g["brand"].iloc[0] or "",
            title=g["title"].iloc[0] or "", spec=spec.replace("|", "、"), first_month=g["month"].iloc[0], months_listed=int(g["month"].nunique()),
            peak_month=pk["month"], peak_units=float(pk["units"]) if pd.notna(pk["units"]) else None,
            best_rank=float(g["rank"].min()) if g["rank"].notna().any() else None,
            first_top50=top50["month"].iloc[0] if len(top50) else None,
            series=[dict(month=r.month, price=_f(r.price), price_ratio=_f(r.pratio), rating=_f(r.rating), units=_f(r.units), rank=_f(r.rank))
                    for r in g.itertuples()]))
    rows.sort(key=lambda r: -(r["peak_units"] or 0))
    return rows[:top]


def price_bands(channel, frame, attr, value):
    m = _panel_module()
    if m is not None:
        return m.price_bands(channel, frame, attr, value)
    d = _frame_rows(channel, frame, attr)
    if d.empty:
        return []
    u = d[_has(d[attr], value) & d["price"].notna()]
    out = []
    for lo, hi, label in BANDS:
        g = u[(u["price"] >= lo) & (u["price"] < hi)]
        if g.empty:
            continue
        out.append(dict(band=label, lo=lo, hi=hi if hi < 1e11 else None, skus=int(g["item_id"].nunique()), obs=int(len(g)),
                        median_units=_f(g["units"].median()), max_units=_f(g["units"].max()), rating=_f(g["rating"].median())))
    return out


def _f(v):
    try:
        return None if v is None or pd.isna(v) else float(v)
    except (TypeError, ValueError):
        return None
