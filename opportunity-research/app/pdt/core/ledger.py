"""预测台账与对账（F26，SEQ-F26-01）。

- register：卡片批准时登记（AC-F26-01）；
- link_items：关联自家 ASIN / 其他渠道商品 ID（ASIN 格式校验）；关联后卡片"已批准 → 跟踪中"；
- reconcile_due()：任一月份并入后由并入流程调用。检查到期条目（实际 / 预计上架起 6 个月且该渠道对应月份已并入），
  Amazon 按"6 个月内任一月小类 BSR ≤ 50 或 SPU 月销售额 ≥ $10 万"判定，其他渠道按品类配置成功线（任一月进类目榜前 N
  或估算月销 ≥ 阈值，同系列合并计算）分渠道判定（AC-F26-02、05、06），同时判是否触发停止条件，写回台账；
  超过预计上架 3 个月仍未关联自家商品的标"待关联"（AC-F26-04）；
- summary：已对账条目按分级与做到概率分档的准确率，标是否达到方案书有效标准（AC-F26-03）。
"""
import re
from datetime import datetime

from sqlalchemy import func, select

from .. import catconfig
from ..config import CHANNEL_NAMES, CHANNELS
from ..db import session
from ..models import Batch, Card, ChannelReview, Forecast, Product, Snapshot, now
from . import card as cardcore
from . import panel_adapter as pa

ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$")
STATUS_NAMES = {"tracking": "跟踪中", "due": "本月到期", "reconciled": "已对账", "unlinked": "待关联"}


class LedgerError(Exception):
    pass


def this_month() -> str:
    return now().strftime("%Y-%m")


def register(s, c: Card) -> Forecast:
    """批准即登记（在审批事务内调用）。"""
    n = c.snapshot["numbers"] if c.snapshot else c.numbers
    narr = c.narrative or {}
    sc = (n.get("bet") or {}).get("score") or {}
    pr = (n.get("bet") or {}).get("prob") or {}
    year = now().year
    k = (s.scalar(select(func.count()).select_from(Forecast).where(Forecast.code.like(f"TZ-{year}-%"))) or 0) + 1
    stop_defs = {x["kind"]: x for x in n.get("stop", [])}
    stops = []
    for st in narr.get("stop", []):
        d = stop_defs.get(st["kind"], {})
        stops.append(dict(kind=st["kind"], value=st["value"], text=(d.get("text") or "").replace("{v}", f"{st['value']:g}")))
    f = Forecast(code=f"TZ-{year}-{k:02d}", card_id=c.id, card_version=c.version, frame=c.frame, attr=c.attr, value=c.value,
                 grade=sc.get("grade") or "", grasp=sc.get("grasp"), share_lo=sc.get("lo"), share_hi=sc.get("hi"),
                 prob_raw=(pr.get("raw") or [None])[0], prob_adj=(pr.get("adj") or [None])[0], stop_conditions=stops,
                 launch_month=narr.get("launch_month") or cardcore.add_months(c.data_month or this_month(), 8),
                 channels=narr.get("launch_channels") or [c.channel], own_items={}, result={}, status="tracking")
    s.add(f)
    s.flush()
    cardcore.log(s, c.id, "ledger", f"已登记预测台账 {f.code}")
    return f


def link_items(fid: int, asins: str, actual_month: str, others: dict, user_id=None):
    """关联自家商品。asins 为逗号分隔的子 ASIN；others = {channel: '商品ID,商品ID'}。"""
    ids = [a.strip().upper() for a in (asins or "").replace("，", ",").split(",") if a.strip()]
    with session() as s:
        f = s.get(Forecast, fid)
        if "amazon" in f.channels and not ids:
            raise LedgerError("ASIN 格式不对：10 位，以 B0 开头")
        bad = [a for a in ids if not ASIN_RE.match(a)]
        if bad:
            raise LedgerError(f"ASIN 格式不对：10 位，以 B0 开头（{', '.join(bad)}）")
        if not re.match(r"^\d{4}-\d{2}$", actual_month or "") or actual_month > this_month():
            raise LedgerError("请填写实际上架月份（不晚于当月）")
        own = {"amazon": ids} if ids else {}
        for ch in f.channels:
            if ch == "amazon":
                continue
            v = [x.strip() for x in (others.get(ch) or "").replace("，", ",").split(",") if x.strip()]
            if not v:
                raise LedgerError(f"登记了 {CHANNEL_NAMES[ch]}，请填写该渠道商品 ID")
            own[ch] = v
        own["_actual_month"] = actual_month
        f.own_items = own
        if f.status == "unlinked":
            f.status = "tracking"
        c = s.get(Card, f.card_id)
        if c.status == "approved":
            cardcore.transition(c, "track")
        cardcore.log(s, c.id, "ledger", f"台账 {f.code} 关联自家商品，实际上架 {actual_month}", user_id)


def _merged_months(s, ch) -> set:
    return {m for (m,) in s.execute(select(Batch.month).where(Batch.channel == ch, Batch.status == "merged"))}


def _amazon_judge(s, items, months, succ):
    fams = {fk for (fk,) in s.execute(select(Product.family_key).where(Product.channel == "amazon", Product.item_id.in_(items))) if fk}
    fam_items = set(items)
    if fams:
        fam_items |= {i for (i,) in s.execute(select(Product.item_id).where(Product.channel == "amazon", Product.family_key.in_(fams)))}
    rows = s.execute(select(Snapshot.month, Snapshot.item_id, Snapshot.rank, Snapshot.revenue, Snapshot.price, Snapshot.units, Snapshot.rating)
                     .where(Snapshot.channel == "amazon", Snapshot.month.in_(months), Snapshot.item_id.in_(fam_items))).all()
    best_rank, best_rev, basis = None, 0.0, ""
    by_m = {}
    for m, it, rk, rev, pr, un, rt in rows:
        r = rev if rev is not None else (pr or 0) * (un or 0)
        d = by_m.setdefault(m, dict(rev=0.0, rank=None, units=0.0, rating=[]))
        d["rev"] += r or 0
        d["units"] += un or 0
        if rt is not None and it in items:
            d["rating"].append(rt)
        if rk is not None and it in items:
            d["rank"] = rk if d["rank"] is None else min(d["rank"], rk)
    made = False
    for m in sorted(by_m):
        d = by_m[m]
        if d["rank"] is not None and (best_rank is None or d["rank"] < best_rank):
            best_rank = d["rank"]
        best_rev = max(best_rev, d["rev"])
        if not made and d["rank"] is not None and d["rank"] <= succ.get("bsr_top", 50):
            made, basis = True, f"{m} 小类 BSR {d['rank']:.0f} ≤ {succ.get('bsr_top', 50)}"
        elif not made and d["rev"] >= succ.get("spu_revenue", 100000):
            made, basis = True, f"{m} SPU 月销售额 ${d['rev']:,.0f} ≥ ${succ.get('spu_revenue', 100000):,.0f}"
    best = f"最好小类排名 {best_rank:.0f}，SPU 月销售额最高 ${best_rev:,.0f}" if best_rank is not None else f"SPU 月销售额最高 ${best_rev:,.0f}"
    return made, basis or best, best, by_m


def _other_judge(s, ch, items, months, chcfg):
    """其他渠道：同系列合并；有评论明细时按评论 ID 去重换算月销，否则用月度快照的估算月销。"""
    succ = chcfg.get("success", {})
    series = {x for (x,) in s.execute(select(Product.series).where(Product.channel == ch, Product.item_id.in_(items))) if x}
    allitems = set(items)
    if series:
        allitems |= {i for (i,) in s.execute(select(Product.item_id).where(Product.channel == ch, Product.series.in_(series)))}
    by_m = {m: dict(units=0.0, rank=None) for m in months}
    revs = s.execute(select(ChannelReview.month, ChannelReview.review_id, ChannelReview.vp).where(
        ChannelReview.channel == ch, ChannelReview.item_id.in_(allitems), ChannelReview.month.in_(months))).all()
    if revs:
        seen = {}
        for m, rid, vp in revs:
            seen[(m, rid)] = vp
        for (m, _), vp in seen.items():
            by_m[m]["units"] += chcfg.get("vp_coef", 50) if vp else chcfg.get("nonvp_coef", 20)
        method = f"评论换算（VP × {chcfg.get('vp_coef', 50)} + 非 VP × {chcfg.get('nonvp_coef', 20)}，按评论 ID 去重）"
    else:
        for m, un in s.execute(select(Snapshot.month, Snapshot.units).where(Snapshot.channel == ch, Snapshot.item_id.in_(allitems), Snapshot.month.in_(months))):
            by_m[m]["units"] += un or 0
        method = "月度估算月销合计"
    for m, rk in s.execute(select(Snapshot.month, Snapshot.rank).where(Snapshot.channel == ch, Snapshot.item_id.in_(allitems), Snapshot.month.in_(months))):
        if rk is not None:
            by_m[m]["rank"] = rk if by_m[m]["rank"] is None else min(by_m[m]["rank"], rk)
    made, basis = False, ""
    top, units = succ.get("rank_top", 50), succ.get("units", 0)
    for m in months:
        d = by_m[m]
        if d["rank"] is not None and d["rank"] <= top:
            made, basis = True, f"{m} 类目榜第 {d['rank']:.0f} 名 ≤ 前 {top}"
            break
        if units and d["units"] >= units:
            made, basis = True, f"{m} 估算月销 {d['units']:,.0f} 件 ≥ {units} 件（同系列 {len(allitems)} 个商品合并）"
            break
    best_u = max((d["units"] for d in by_m.values()), default=0)
    ranks = [d["rank"] for d in by_m.values() if d["rank"] is not None]
    best = f"估算月销最高 {best_u:,.0f} 件" + (f"，最好类目排名 {min(ranks):.0f}" if ranks else "，没有类目排名")
    return made, basis or best, best + f"；{method}"


def _stops(f: Forecast, am_by_m: dict, start: str) -> list:
    out = []
    m3 = [cardcore.add_months(start, i) for i in range(3)]
    for st in f.stop_conditions or []:
        hit, why = None, ""
        if st["kind"] == "rating_below":
            rs = [r for m in m3 for r in (am_by_m.get(m, {}).get("rating") or [])]
            if rs:
                avg = sum(rs) / len(rs)
                hit, why = avg < st["value"], f"前 3 个月评分 {avg:.2f}"
        elif st["kind"] == "units_below":
            # 整款口径（AC-F26-02 r2）：am_by_m 的月销已是自家商品所在款（同父体 / 家族全部尺寸、颜色）合计，取第 2–3 个月两月平均，
            # 与决策卡停止线（同框做成新品第 2–3 个月整款月销两月平均的第 10 百分位，card.stop_line）同一口径
            us = [am_by_m[m]["units"] for m in m3[1:] if m in am_by_m]
            if us:
                avg = sum(us) / len(us)
                hit, why = avg < st["value"], f"第 2–3 个月整个父体（所有尺寸、颜色加起来）月销平均 {avg:,.0f} 件"
        else:
            why = "需人工核对竞品价格"
        out.append(dict(text=st.get("text", ""), triggered=hit, why=why))
    return out


def reconcile_due(today: str | None = None) -> dict:
    """任一月份并入后调用（分析组的并入流程在 Batch 置为 merged 后调用本函数）。返回本次处理统计。"""
    today = today or this_month()
    cfg_v, cfg = catconfig.current()
    chcfg = cfg.get("channels", {})
    stat = dict(reconciled=0, due=0, unlinked=0)
    pa.clear_cache()
    with session() as s:
        for f in s.scalars(select(Forecast).where(Forecast.status.in_(["tracking", "due", "unlinked"]))):
            own = f.own_items or {}
            linked = any(own.get(ch) for ch in CHANNELS)
            if not linked:
                if today > cardcore.add_months(f.launch_month, 3):
                    if f.status != "unlinked":
                        f.status = "unlinked"
                    stat["unlinked"] += 1
                continue
            start = own.get("_actual_month") or f.launch_month
            months = [cardcore.add_months(start, i) for i in range(6)]
            end = months[-1]
            res = dict(f.result or {})
            all_done = True
            am_by_m = {}
            for ch in f.channels:
                merged = _merged_months(s, ch)
                items = own.get(ch) or []
                if not items:
                    res[ch] = dict(status="数据不全", reason="未关联该渠道商品")
                    all_done = False
                    continue
                if not merged or max(merged) < end:
                    res[ch] = dict(status="观察中" if today <= end else "数据不全", reason=f"等 {end} 并入", end=end)
                    all_done = False
                    continue
                if ch == "amazon":
                    made, basis, best, am_by_m = _amazon_judge(s, items, months, chcfg.get("amazon", {}).get("success", {}))
                    succ = chcfg.get("amazon", {}).get("success", {})
                    line = f"小类 BSR ≤ {succ.get('bsr_top', 50)} 或 SPU 月销售额 ≥ ${succ.get('spu_revenue', 100000):,.0f}"
                    nature = "实测"
                else:
                    made, basis, best = _other_judge(s, ch, items, months, chcfg.get(ch, {}))
                    sc_ = chcfg.get(ch, {}).get("success", {})
                    line = f"类目榜前 {sc_.get('rank_top', 50)} 或估算月销 ≥ {sc_.get('units')} 件（同系列合并）"
                    nature = "估算"
                res[ch] = dict(status="做到" if made else "未做到", made=made, basis=basis, best=best, line=line, nature=nature,
                               window=f"{months[0]} 至 {end}", params_version=cfg_v)
            if all_done:
                stops = _stops(f, am_by_m, start)
                res["_stop"] = stops
                res["_market"] = _market_outcome(f)
                f.result = res
                f.status = "reconciled"
                f.reconciled_at = now()
                f.params_version = cfg_v
                c = s.get(Card, f.card_id)
                if c.status in ("approved", "tracking"):
                    cardcore.transition(c, "reconcile")
                    cardcore.log(s, c.id, "ledger", f"台账 {f.code} 已对账：" + "；".join(f"{CHANNEL_NAMES[k]} {v['status']}" for k, v in res.items() if not k.startswith("_")))
                stat["reconciled"] += 1
            else:
                f.result = res
                if today > end:
                    f.status = "due"
                    stat["due"] += 1
    return stat


def _market_outcome(f: Forecast) -> dict:
    """市场层：登记后第 6–10 个月份额是否比登记时大（准确率汇总用）。"""
    reg = f.registered_at.strftime("%Y-%m")
    ts = pa.unit_timeseries("amazon", f.frame, f.attr, f.value)
    win = {cardcore.add_months(reg, k) for k in range(6, 11)}
    after = [r["share"] for r in ts if r["month"] in win and r.get("share") is not None]
    before = [r["share"] for r in ts if r["month"] < reg and r.get("share") is not None][-6:]
    if not after or not before:
        return dict(grew=None)
    return dict(grew=sum(after) / len(after) > sum(before) / len(before))


def unlinked_alerts() -> list:
    """待关联条目（工作台提示用，AC-F26-04）。"""
    with session() as s:
        out = []
        for f in s.scalars(select(Forecast).where(Forecast.status == "unlinked")):
            c = s.get(Card, f.card_id)
            out.append(dict(id=f.id, code=f.code, card=cardcore.card_name(c), launch_month=f.launch_month))
        return out


def summary(s) -> dict:
    rows = list(s.scalars(select(Forecast).where(Forecast.status == "reconciled")))
    grades = []
    for g in "ABCD":
        rs = [f for f in rows if f.grade == g]
        grew = [f for f in rs if ((f.result or {}).get("_market") or {}).get("grew") is not None]
        made = [f for f in rs if ((f.result or {}).get("amazon") or {}).get("made") is not None]
        grades.append(dict(grade=g, n=len(rs), grew_n=len(grew), grew=sum(1 for f in grew if f.result["_market"]["grew"]),
                           made_n=len(made), made=sum(1 for f in made if f.result["amazon"]["made"])))
    rate = lambda a, b: a / b if b else None
    d = next(x for x in grades if x["grade"] == "D")
    rates = [rate(x["grew"], x["grew_n"]) for x in grades]  # A B C D
    if any(x["grew_n"] == 0 for x in grades):
        mono, d_ok = None, (None if d["grew_n"] == 0 else rate(d["grew"], d["grew_n"]) <= 0.3)
    else:
        mono = all(rates[i] > rates[i + 1] for i in range(3))
        d_ok = rates[3] <= 0.3
    bins = []
    pts = [f for f in rows if f.prob_adj is not None and ((f.result or {}).get("amazon") or {}).get("made") is not None]
    for lab, lo, hi in (("≥ 50%", 0.5, 2), ("40%–50%", 0.4, 0.5), ("< 40%", -1, 0.4)):
        rs = [f for f in pts if lo <= f.prob_adj < hi]
        bins.append(dict(label=lab, n=len(rs), made=sum(1 for f in rs if f.result["amazon"]["made"])))
    top_ok, ratio = None, None
    if len(pts) >= 5:
        srt = sorted(pts, key=lambda f: -f.prob_adj)
        k = max(1, round(len(srt) * 0.2))
        top = sum(1 for f in srt[:k] if f.result["amazon"]["made"]) / k
        avg = sum(1 for f in srt if f.result["amazon"]["made"]) / len(srt)
        ratio = top / avg if avg else None
        top_ok = ratio is not None and ratio >= 2
    return dict(n=len(rows), grades=grades, d_ok=d_ok, mono=mono, bins=bins, top_ok=top_ok, top_ratio=ratio, n_new=len(pts))


def counts(s) -> dict:
    out = {k: 0 for k in STATUS_NAMES}
    for st, n in s.execute(select(Forecast.status, func.count()).group_by(Forecast.status)):
        out[st] = n
    out["all"] = sum(out.values())
    return out


def fmt_month(v: datetime | None):
    return v.strftime("%Y-%m-%d %H:%M") if v else "—"
