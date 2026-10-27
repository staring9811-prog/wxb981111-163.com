"""Signals per segment and month T (F06: REQ-F06-02..08). Every input goes through `AsOf`, which only
exposes monthly rows with month < T, reviews dated before T-01 and keyword months < T (AC-F06-03)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from oppo.core import segments as SEG
from oppo.core.judge import HIT, MISS
from oppo.core.packages import add_months, month_range

SIGNALS = ("demand", "entry", "pain", "hslr")
CURRENT = ("unit_asin", "premium", "trend", "low_score")
LABELS = {
    "demand": "需求在涨", "entry": "新品进得去", "pain": "结构类痛点占比", "hslr": "高销低评占比",
    "unit_asin": "单位 ASIN 贡献", "premium": "属性溢价", "trend": "属性趋势", "low_score": "低分高销",
}
NO_DATA, NOT_APPLICABLE = "无数据", "截面模式不适用"


@dataclass
class Context:
    cfg: dict[str, Any]
    mode: str
    c1: pd.DataFrame  # child, month, units, sales, parent
    attrs: pd.DataFrame  # effective attributes (index child)
    c5: pd.DataFrame
    c6: pd.DataFrame
    spus: pd.DataFrame  # new SPUs with segment_key, batch, status, rising_from
    has_c5: bool
    has_c6: bool
    old_children: set[str] = field(default_factory=set)
    months_avail: set[str] = field(default_factory=set)
    kw_map: dict[str, tuple[str, str] | None] = field(default_factory=dict)


def keyword_segments(tags: str | None, cfg: dict[str, Any]) -> tuple[str, str] | None:
    """Map a keyword's tags to (width label, form label); None for generic keywords."""
    if not tags or str(tags).strip() in ("", "通用"):
        return None
    kv: dict[str, str] = {}
    for part in str(tags).replace("；", ";").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            kv[k.strip()] = v.strip()
    width_dim = next(d for d in cfg["segment_dims"] if d["key"] == "width")
    size_tag = cfg["keyword_mapping"]["width"].get("tag", "尺寸")
    w = SEG.bin_numeric(SEG._num(kv.get(size_tag)), width_dim["bins"]) if kv.get(size_tag) else None
    fmap = cfg["keyword_mapping"]["form"]["map"]
    raw_form = kv.get(cfg["keyword_mapping"]["form"].get("tag", "形态"), "").lower()
    f = next((label for label, words in fmap.items() if raw_form in [x.lower() for x in words]), None)
    if not w or w == SEG.UNKNOWN or not f:
        return None
    return w, f


def build_context(cfg: dict[str, Any], mode: str, c1: pd.DataFrame, attrs: pd.DataFrame, c5: pd.DataFrame,
                  c6: pd.DataFrame, spus: pd.DataFrame, has_c5: bool, has_c6: bool,
                  old_children: set[str] | None = None) -> Context:
    c1 = c1[["child", "month", "child_units", "child_sales", "parent"]].copy()
    kw_map = {}
    if len(c5):
        for kw, tags in c5.drop_duplicates("keyword")[["keyword", "tags"]].itertuples(index=False):
            kw_map[kw] = keyword_segments(tags, cfg)
    return Context(cfg=cfg, mode=mode, c1=c1, attrs=attrs, c5=c5, c6=c6, spus=spus, has_c5=has_c5, has_c6=has_c6,
                   old_children=old_children or set(), months_avail=set(c1["month"].dropna()), kw_map=kw_map)


class AsOf:
    """Point-in-time view of the data for month T."""

    def __init__(self, ctx: Context, T: str):
        self.ctx, self.T = ctx, T
        self.t_first_day = f"{T}-01"

    def months(self, a: str, b: str) -> pd.DataFrame:
        assert b < self.T
        c1 = self.ctx.c1
        return c1[(c1["month"] >= a) & (c1["month"] <= b)]

    def month(self, m: str) -> pd.DataFrame:
        assert m < self.T
        c1 = self.ctx.c1
        return c1[c1["month"] == m]

    def before(self) -> pd.DataFrame:
        c1 = self.ctx.c1
        return c1[c1["month"] < self.T]

    def reviews(self) -> pd.DataFrame:
        c6 = self.ctx.c6
        if not len(c6):
            return c6
        return c6[c6["review_date"] < self.t_first_day]

    def keywords(self) -> pd.DataFrame:
        c5 = self.ctx.c5
        if not len(c5):
            return c5
        return c5[c5["month"] < self.T]


def _price_of(rows: pd.DataFrame) -> pd.Series:
    """Latest month with units > 0 before T: sales / units per child."""
    r = rows[(rows["child_units"] > 0) & rows["child_sales"].notna()].sort_values(["child", "month"])
    last = r.groupby("child").last()
    return last["child_sales"] / last["child_units"]


def child_segments(view: AsOf) -> pd.Series:
    """Segment of every child seen before T (price from its latest month before T)."""
    before = view.before()
    price = _price_of(before)
    attrs = view.ctx.attrs
    out = {}
    for ch in sorted(set(before["child"].dropna())):
        arow = attrs.loc[ch].to_dict() if ch in attrs.index else None
        key, _ = SEG.segment_of(arow, price.get(ch), view.ctx.cfg)
        out[ch] = key
    return pd.Series(out, dtype=object)


def _row(seg: str, sig: str, value: float | None, num: float | None = None, den: float | None = None,
         cnt: int | None = None, flag: str | None = None, **extra: Any) -> dict[str, Any]:
    if value is not None and (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        value, flag = None, flag or NO_DATA
    return {"segment_key": seg, "signal": sig, "value": value, "num": num, "den": den, "cnt": cnt,
            "flag": flag or (NO_DATA if value is None else None), "extra": extra or None}


def compute_T(ctx: Context, T: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """All signal rows for month T and per-segment info (child count, backfill shares)."""
    cfg = ctx.cfg
    view = AsOf(ctx, T)
    segs = child_segments(view)
    seg_keys = sorted(set(segs.values))
    prev = add_months(T, -1)
    rows: list[dict[str, Any]] = []
    info: dict[str, dict[str, Any]] = {}
    attrs = ctx.attrs
    type_attrs = [a for a in cfg.get("type_attributes") or [] if f"{a}__bf" in attrs.columns]
    prev_m = add_months(T, -1)
    active = set(ctx.c1[(ctx.c1["month"] == prev_m) & (ctx.c1["child_units"] > 0)]["child"]) \
        if prev_m in ctx.months_avail else set()
    for s in seg_keys:
        members = segs[segs == s].index
        act = [c for c in members if c in active]
        if act:  # backfill share among children with sales in T-1 (same population as the T-1 signals)
            members = pd.Index(act)
        bf = attrs.reindex(members)
        share = float(bf["any_bf"].fillna(0).mean()) if len(members) and "any_bf" in bf else 0.0
        info[s] = {"child_count": int(len(members)), "backfill_share": share,
                   "backfill": {a: float(bf[f"{a}__bf"].fillna(0).mean()) for a in type_attrs} if len(members) else {},
                   "has_unknown": int(SEG.UNKNOWN in s.split("|"))}

    # ---- 需求在涨 (REQ-F06-03)
    n = int(cfg["signal_windows"]["demand_months"])
    recent = month_range(add_months(T, -n), prev)
    prior = [add_months(m, -12) for m in recent]
    kw = view.keywords()
    by_combo: dict[tuple[str, str], list[str]] = {}
    for k, combo in ctx.kw_map.items():
        if combo:
            by_combo.setdefault(combo, []).append(k)
    pivot = kw.pivot_table(index="keyword", columns="month", values="volume", aggfunc="sum") if len(kw) else None
    for s in seg_keys:
        w, f = s.split("|")[0], s.split("|")[1]
        if not ctx.has_c5:
            rows.append(_row(s, "demand", None, flag=NO_DATA, reason="数据包不含关键词（C5）"))
            continue
        kws = by_combo.get((w, f), [])
        need = recent + prior
        ok = []
        if pivot is not None:
            for k in kws:
                if k in pivot.index and all(m in pivot.columns and pd.notna(pivot.at[k, m]) for m in need):
                    ok.append(k)
        if not ok:
            rows.append(_row(s, "demand", None, flag=NO_DATA, reason="所需月份的关键词数据缺失" if kws else "没有映射到该细分的关键词"))
            continue
        num = float(pivot.loc[ok, recent].to_numpy().sum())
        den = float(pivot.loc[ok, prior].to_numpy().sum())
        rows.append(_row(s, "demand", (num / den - 1) if den > 0 else None, num, den, len(ok)))

    # ---- 新品进得去 (REQ-F06-04; not in cross mode, AC-F06-11)
    window = int(cfg["success"]["window_months"])
    look = int(cfg["signal_windows"]["entry_lookback_months"])
    lo, hi = add_months(T, -(window + look)), add_months(T, -(window + 1))
    sp = ctx.spus
    for s in seg_keys:
        if ctx.mode == "cross":
            rows.append(_row(s, "entry", None, flag=NOT_APPLICABLE))
            continue
        g = sp[(sp["segment_key"] == s) & (sp["batch"] >= lo) & (sp["batch"] <= hi) & (sp["rising_from"] < T)]
        hits = int((g["status"] == HIT).sum())
        dec = int(g["status"].isin([HIT, MISS]).sum())
        entry_extra: dict[str, Any] = {"incomplete": int((~g["status"].isin([HIT, MISS])).sum()), "window": f"{lo}–{hi}"}
        if not dec:
            entry_extra["reason"] = "回看期内没有已判定的新 SPU"
        rows.append(_row(s, "entry", hits / dec if dec else None, hits, dec, int(len(g)),
                         flag=None if dec else NO_DATA, **entry_extra))

    # ---- T-1 month figures and review attribution
    mprev = view.month(prev) if prev in ctx.months_avail else ctx.c1.iloc[0:0]
    mprev = mprev[mprev["child_units"] > 0].copy()
    if ctx.mode == "cross":
        mprev_cur = mprev[mprev["child"].isin(ctx.old_children)]
    else:
        mprev_cur = mprev
    mprev["seg"] = mprev["child"].map(segs)
    mprev_cur = mprev_cur.assign(seg=mprev_cur["child"].map(segs))
    rev = view.reviews()
    child_rating: dict[str, list[float]] = {}
    seg_reviews: dict[str, list[int]] = {}
    seg_codes: dict[str, dict[str, int]] = {}  # structural pain codes per segment (PAGE-F06-02 构成)
    label_versions: set[str] = set()
    if ctx.has_c6 and len(rev):
        before = view.before()
        # parent-level reviews go to that parent's best-selling child in T-1 (or latest month before T)
        ref = before[before["month"] == prev] if prev in ctx.months_avail else before
        if not len(ref):
            ref = before
        best = (ref.sort_values(["parent", "child_units", "child"], ascending=[True, False, True])
                .dropna(subset=["parent"]).groupby("parent")["child"].first())
        target = np.where(rev["level"] == "父体", rev["asin"].map(best), rev["asin"])
        rev = rev.assign(target=target)
        rev = rev.dropna(subset=["target"])
        rev = rev.assign(seg=rev["target"].map(segs)).dropna(subset=["seg"])
        for t, st in zip(rev["target"], rev["stars"], strict=False):
            if pd.notna(st):
                child_rating.setdefault(t, []).append(float(st))
        codes = rev["pain_code"] if "pain_code" in rev.columns else pd.Series([None] * len(rev), index=rev.index)
        for sg, structural, code in zip(rev["seg"], rev["structural"], codes, strict=False):
            seg_reviews.setdefault(sg, []).append(int(structural or 0))
            if int(structural or 0):
                key = str(code) if isinstance(code, str) and code.strip() else "未标代码"
                cc = seg_codes.setdefault(sg, {})
                cc[key] = cc.get(key, 0) + 1
        if "label_version" in rev.columns:
            label_versions = {str(v) for v in rev["label_version"].dropna().unique()}

    for s in seg_keys:
        # 结构类痛点占比 (REQ-F06-05)
        if not ctx.has_c6:
            rows.append(_row(s, "pain", None, flag=NO_DATA, reason="数据包不含评论痛点（C6）"))
        else:
            lst = seg_reviews.get(s, [])
            pain_extra: dict[str, Any] = {"codes": dict(sorted(seg_codes.get(s, {}).items())),
                                          "label_versions": sorted(label_versions)}
            if not lst:
                pain_extra["reason"] = "早于 T 月没有评论"
            rows.append(_row(s, "pain", (sum(lst) / len(lst)) if lst else None, float(sum(lst)), float(len(lst)),
                             len(lst), flag=None if lst else NO_DATA, **pain_extra))
        # 高销低评 (REQ-F06-05)
        g = mprev[mprev["seg"] == s].sort_values(["child_units", "child"], ascending=[False, True])
        if not ctx.has_c6:
            rows.append(_row(s, "hslr", None, flag=NO_DATA, reason="数据包不含评论痛点（C6）"))
        elif not len(g):
            rows.append(_row(s, "hslr", None, flag=NO_DATA, reason="第 T−1 月没有销量数据"))
        else:
            k = math.ceil(len(g) * 0.25)
            top = g.head(k)
            low = [c for c in top["child"] if child_rating.get(c) and np.mean(child_rating[c]) < 4.0]
            num = float(top[top["child"].isin(low)]["child_units"].sum())
            den = float(g["child_units"].sum())
            rows.append(_row(s, "hslr", num / den if den else None, num, den, len(low)))

    # ---- current indicators (REQ-F06-06; cross mode uses old products only, AC-F06-12)
    width_of = {s: s.split("|")[0] for s in seg_keys}
    base_rows = mprev_cur
    for s in seg_keys:
        g = base_rows[base_rows["seg"] == s]
        cur_note = {"old": int(g["child"].nunique())} if ctx.mode == "cross" else {}
        if not len(g):
            reason = "没有老品数据" if ctx.mode == "cross" else "第 T−1 月没有销量数据"
            for sig in ("unit_asin", "premium"):
                rows.append(_row(s, sig, None, flag=NO_DATA, reason=reason, **cur_note))
        else:
            units = float(g["child_units"].sum())
            nch = int(g["child"].nunique())
            rows.append(_row(s, "unit_asin", units / nch, units, float(nch), nch, **cur_note))
            w = width_of[s]
            if w == SEG.UNKNOWN:
                rows.append(_row(s, "premium", None, flag=NO_DATA, reason="宽度档未知", **cur_note))
            else:
                same_w = base_rows[base_rows["seg"].map(lambda x, w=w: isinstance(x, str) and x.split("|")[0] == w)]
                sp_ = float(g["child_sales"].sum()) / units
                wu = float(same_w["child_units"].sum())
                wp = float(same_w["child_sales"].sum()) / wu if wu else None
                rows.append(_row(s, "premium", (sp_ / wp - 1) if wp else None, sp_, wp, nch, **cur_note))
        # 属性趋势: share T-3..T-1 vs T-6..T-4
        need6 = month_range(add_months(T, -6), prev)
        if not all(m in ctx.months_avail for m in need6):
            rows.append(_row(s, "trend", None, flag=NO_DATA,
                             reason=f"观察期 {len([m for m in need6 if m in ctx.months_avail])} 个月，不足 6 个月", **cur_note))
        else:
            win = view.months(need6[0], prev)
            if ctx.mode == "cross":
                win = win[win["child"].isin(ctx.old_children)]
            win = win.assign(seg=win["child"].map(segs))
            rec_m, pri_m = set(need6[3:]), set(need6[:3])
            tr = win[win["month"].isin(rec_m)]
            tp = win[win["month"].isin(pri_m)]
            tot_r, tot_p = float(tr["child_units"].sum()), float(tp["child_units"].sum())
            if tot_r and tot_p:
                sr = float(tr[tr["seg"] == s]["child_units"].sum()) / tot_r
                spr = float(tp[tp["seg"] == s]["child_units"].sum()) / tot_p
                rows.append(_row(s, "trend", (sr - spr) * 100, sr * 100, spr * 100,
                                 int(win[win["seg"] == s]["child"].nunique()), **cur_note))
            else:
                rows.append(_row(s, "trend", None, flag=NO_DATA, **cur_note))
        # 低分高销 = 高销低评 on the indicator population
        if not ctx.has_c6:
            rows.append(_row(s, "low_score", None, flag=NO_DATA, reason="数据包不含评论痛点（C6）", **cur_note))
        else:
            g2 = g.sort_values(["child_units", "child"], ascending=[False, True])
            if not len(g2):
                rows.append(_row(s, "low_score", None, flag=NO_DATA, **cur_note))
            else:
                k = math.ceil(len(g2) * 0.25)
                top = g2.head(k)
                low = [c for c in top["child"] if child_rating.get(c) and np.mean(child_rating[c]) < 4.0]
                num = float(top[top["child"].isin(low)]["child_units"].sum())
                den = float(g2["child_units"].sum())
                rows.append(_row(s, "low_score", num / den if den else None, num, den, len(low), **cur_note))
    return rows, info
