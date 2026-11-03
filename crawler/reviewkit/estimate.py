"""Time & cost estimate, computed after the list step (needs the selected products and their page review counts).

Calibration (measured on the bathroom-vanity project, Nov 2026 — update CAL when real runs differ):
- reviews inside the window ≈ lifetime review count × 2% per month in the window (seen 1%–4%)
- Bright Data Web Unlocker: $1.5 / 1000 requests; one async page takes 1–7 min (Lowe's/Wayfair)
- Apify Lowe's actor ≈ $0.00009 / review (+$0.005 per run); 10 products / ~4,000 rows ≈ 14 min
- Apify Wayfair actor ≈ $0.0005 / review + $0.0026 / product (+$0.05 per run)
- Home Depot direct: ~3 s per page, 3 in parallel, free
"""
import math
from .pipeline import selected, entries, low_mode

CAL = {"monthly_share": 0.02, "low": 0.5, "high": 2.0, "bd_price": 0.0015, "bd_page_min": 5,
       "lo_review": 0.00009, "lo_run": 0.005, "lo_batch": 20, "lo_batch_min": 25, "parallel": 4,
       "wf_review": 0.0005, "wf_unknown_count": 300, "wf_product": 0.0026, "wf_run": 0.05, "wf_batch": 10, "wf_product_min": 1.0,
       "hdp_page_s": 3, "hdp_workers": 3}


def run(ctx):
    months = len(ctx.months)
    share = min(1.0, CAL["monthly_share"] * months)
    rows = [r for r in selected(ctx) if low_mode(ctx, r) != "skip"]
    uniq = {}
    for r in rows:
        uniq[(r["平台"], r["id"])] = r
    out = {}
    for plat in ("HomeDepot", "Lowes", "Wayfair"):
        rs = [r for (p, _), r in uniq.items() if p == plat]
        n_entries = sum(1 for e in entries(ctx) if e["platform"] == plat)
        if not n_entries:
            continue
        lifetime = sum(r.get("review_count") or 0 for r in rs)
        est = lifetime * share
        e = {"商品数": len(rs), "页面累计评论数": lifetime, "预计窗口内评论": [round(est * CAL["low"]), round(est * CAL["high"])]}
        if plat == "HomeDepot":
            pages = sum(2 + (r.get("review_count") or 0) * share / 30 for r in rs)
            e.update(BD请求=0, BD费用=0, Apify费用=0,
                     预计耗时分钟=round(pages * CAL["hdp_page_s"] / CAL["hdp_workers"] / 60 + 1))
        elif plat == "Lowes":
            bd = n_entries * 6 * 1.2 + len(rs) * 1.2
            reviews = sum(min(1000, 2 * min(500, (r.get("review_count") or 0) * share * 1.5)) for r in rs)
            batches = math.ceil(len(rs) / CAL["lo_batch"])
            ap = reviews * CAL["lo_review"] + batches * 2 * CAL["lo_run"]
            mins = CAL["bd_page_min"] * 2 + len(rs) / 6 * CAL["bd_page_min"] * 0.6 + \
                math.ceil(batches / CAL["parallel"]) * CAL["lo_batch_min"]
            e.update(BD请求=round(bd), BD费用=round(bd * CAL["bd_price"], 2), Apify费用=round(ap, 2), 预计耗时分钟=round(mins))
        else:
            bd = n_entries * 8 * 1.5
            fetched = 0
            for r in rs:
                # list cards sometimes omit the count (0) although the product has hundreds of reviews → assume 300
                tot = r.get("review_count") or CAL["wf_unknown_count"]
                inwin = tot * share
                fetched += min(100, tot) + (min(300, tot) if inwin > 100 else 0) + (min(1000, tot) if inwin > 300 else 0)
            runs = math.ceil(len(rs) / CAL["wf_batch"]) * 1.5
            ap = fetched * CAL["wf_review"] + len(rs) * CAL["wf_product"] + runs * CAL["wf_run"]
            mins = CAL["bd_page_min"] * 2 + len(rs) * CAL["wf_product_min"] / CAL["parallel"]
            e.update(BD请求=round(bd), BD费用=round(bd * CAL["bd_price"], 2), Apify费用=round(ap, 2), 预计耗时分钟=round(mins))
        out[plat] = e
    tot = {"BD费用": round(sum(v["BD费用"] for v in out.values()), 2),
           "Apify费用": round(sum(v["Apify费用"] for v in out.values()), 2),
           "预计耗时分钟": max([v["预计耗时分钟"] for v in out.values()] or [0])}
    tot["总费用"] = round(tot["BD费用"] + tot["Apify费用"], 2)
    tot["说明"] = (f"时间窗 {months} 个月，按每月约 {CAL['monthly_share']:.0%} 的累计评论估算窗口内评论（区间 ×{CAL['low']}~×{CAL['high']}）；"
                 "三个平台并行，总耗时取最慢的平台；费用为上限估计，实际按条计费。")
    return {"平台": out, "合计": tot}
