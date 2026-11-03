"""Review collection through Apify actors (see services/README.md).

- Wayfair: abotapi/wayfair-scraper (url mode, fetchReviews, newest first, up to 1000 per product)
- Lowe's:  automation-lab/lowes-product-reviews-scraper (newerThan 2026-01-01, newest + oldest first, 500 each)
"""
import os
from datetime import datetime
from . import apify
from .common import DATA, YEAR_START, save_json, load_json

WF_ACTOR = "abotapi/wayfair-scraper"
LO_ACTOR = "automation-lab/lowes-product-reviews-scraper"


def _wf_vp(badge):
    return "VP" if badge == "Verified Purchase" else "non_VP"  # 口径 A


def wayfair_reviews(urls_by_sku, batch=10, cap=300, max_charge_usd=3):
    """Returns {sku: (rows, complete_flag, n_returned)}; caches raw items per sku."""
    out, todo = {}, []
    for sku, url in urls_by_sku.items():
        raw = load_json(os.path.join(DATA, "wayfair", "apify", f"{sku}.json"))
        if raw is not None:
            out[sku] = raw
        else:
            todo.append((sku, url))
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        items, run = apify.run_actor(WF_ACTOR, {"mode": "url", "urls": [u for _, u in chunk], "fetchReviews": True,
                                                "maxReviewsPerProduct": cap, "reviewSort": "newest",
                                                "maxItems": len(chunk)}, timeout_s=290, max_charge_usd=max_charge_usd)
        print("apify wayfair batch", i // batch + 1, "items", len(items), "usd", run.get("usd"), flush=True)
        by = {str(it.get("sku", "")).upper(): it for it in items}
        for sku, _ in chunk:
            it = by.get(sku.upper())
            raw = {"reviews": (it or {}).get("reviews") or [], "reviewCount": (it or {}).get("reviewCount"), "found": bool(it)}
            save_json(os.path.join(DATA, "wayfair", "apify", f"{sku}.json"), raw)
            out[sku] = raw
    res = {}
    for sku, raw in out.items():
        rows = []
        for r in raw["reviews"]:
            try:
                d = datetime.strptime(r.get("date") or "", "%m/%d/%Y").strftime("%Y-%m-%d")
            except ValueError:
                d = ""
            if d >= YEAR_START:
                rows.append({"评论ID": str(r.get("reviewId")), "评论日期": d, "评分": r.get("rating"), "评论标题": "",
                             "评论原文": r.get("text") or "", "VP状态": _wf_vp(r.get("badge")),
                             "VP证据": f"badge={r.get('badge') or 'null'}; verifiedPurchase={r.get('verifiedPurchase')}",
                             "转载": "否", "转载来源": "",
                             "选项": ", ".join(f"{k}={v}" for k, v in (r.get("purchasedOptions") or {}).items())})
        n = len(raw["reviews"])
        oldest = min((x["评论日期"] for x in rows), default="")
        complete = raw["found"] and (n < cap or any(
            (r.get("date") or "")[-4:] < "2026" for r in raw["reviews"]))
        res[sku] = (rows, complete, n)
    return res


def _lo_row(r):
    vp = r.get("verifiedPurchaser")
    return {"评论ID": str(r.get("reviewId")), "评论日期": (r.get("submittedAt") or "")[:10], "评分": r.get("rating"),
            "评论标题": r.get("reviewTitle") or "", "评论原文": r.get("reviewText") or "",
            "VP状态": "VP" if vp is True else ("non_VP" if vp is False else "unknown"),
            "VP证据": f"verifiedPurchaser={vp}; incentivized={r.get('incentivizedReview')}",
            "转载": "是" if r.get("syndicated") else "否", "转载来源": r.get("source") if r.get("syndicated") else ""}


def lowes_reviews(ids, batch=40, cap=500):
    """Returns {pid: (rows, complete_flag)}; two passes (newest/oldest first) merged, cached per pid."""
    res, todo = {}, []
    for pid in ids:
        raw = load_json(os.path.join(DATA, "lowes", "apify", f"{pid}.json"))
        if raw is not None:
            res[pid] = raw
        else:
            todo.append(pid)
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        got = {p: {"newest": [], "oldest": []} for p in chunk}
        for sort, key in (("newestFirst", "newest"), ("oldestFirst", "oldest")):
            items, run = apify.run_actor(LO_ACTOR, {"productIds": chunk, "maxReviewsPerProduct": cap, "sort": sort,
                                                    "newerThan": YEAR_START, "includeRatingsOnly": True}, timeout_s=290,
                                                   max_charge_usd=2)
            print("apify lowes batch", i // batch + 1, sort, "items", len(items), "usd", run.get("usd"), flush=True)
            for it in items:
                p = str(it.get("productId"))
                if p in got:
                    got[p][key].append(it)
        for p in chunk:
            save_json(os.path.join(DATA, "lowes", "apify", f"{p}.json"), got[p])
            res[p] = got[p]
    out = {}
    for pid, raw in res.items():
        rows = {}
        for it in raw["newest"] + raw["oldest"]:
            r = _lo_row(it)
            if r["评论日期"] >= YEAR_START:
                rows[r["评论ID"]] = r
        # complete if one pass returned < cap (it saw every 2026 review) or the two passes overlap
        n_new, n_old = len(raw["newest"]), len(raw["oldest"])
        overlap = len({x.get("reviewId") for x in raw["newest"]} & {x.get("reviewId") for x in raw["oldest"]})
        complete = n_new < cap or n_old < cap or overlap > 0
        out[pid] = (list(rows.values()), complete)
    return out
