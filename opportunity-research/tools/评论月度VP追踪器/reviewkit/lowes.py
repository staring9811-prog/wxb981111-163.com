"""Lowe's adapter — list + detail pages via Bright Data (cloud IPs are blocked), reviews via Apify
(automation-lab/lowes-product-reviews-scraper: newest-first + oldest-first, 500 each, merged).
Lowe's review pages show the whole family (父体) — same reviews for every variant of a parent.
"""
import json, re, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from .common import decode_at, save_json, load_json, add_query
from .services import BD, Apify

BASE = "https://www.lowes.com"
IMG = "https://mobileimages.lowes.com"
NAME = "Lowes"
ACTOR = "automation-lab/lowes-product-reviews-scraper"
PAGE = 24


def _state(b):
    s = b.decode("utf-8", "ignore")
    m = re.search(r'window\[?.?__PRELOADED_STATE__.?\]?\s*=\s*', s)
    return (decode_at(s, m.end()) if m else None), s


def _get(ctx, url, tries=3):
    bd = BD(ctx)
    for _ in range(tries):
        st, b = bd.fetch(url, "lowes")
        if st == 200 and b"__PRELOADED_STATE__" in b:
            return _state(b)
    return None, ""


def entry_url(entry):
    if entry.get("mode") == "keyword":
        u = f"{BASE}/search?searchTerm={urllib.parse.quote_plus(entry['keyword'])}"
    else:
        u = entry["url"]
    sort = entry.get("sort") or ("sortBy_bestSellers" if entry.get("mode") in ("bsr", "category", None) else None)
    return add_query(u, sortMethod=sort)


def list_page(ctx, entry, page_no, state):
    f = ctx.path("lowes", "listpages", f"{entry['name']}_{page_no}.json")
    items = load_json(f)
    if items is None:
        st, _ = _get(ctx, add_query(entry_url(entry), offset=page_no * PAGE))
        if not st:
            return None
        items = st.get("itemList") or []
        save_json(f, items)
    out = []
    for it in items:
        p, loc = it.get("product") or {}, it.get("location") or {}
        if not p.get("omniItemId"):
            continue
        price = loc.get("price") or {}
        imgs = ([IMG + p["imageUrl"]] if p.get("imageUrl") else []) + \
               [x.get("baseUrl") for x in (p.get("epc") or {}).get("additionalImages", []) if x.get("baseUrl")]
        out.append({"id": p["omniItemId"], "url": BASE + p.get("pdURL", ""), "title": p.get("description", ""),
                    "brand": p.get("brand", ""), "model": f'{p.get("modelId", "")} / Item {p.get("itemNumber", "")}',
                    "sponsored": bool(p.get("sponsored")), "badges": str(loc.get("promoBadge") or ""),
                    "price": price.get("sellingPrice") or price.get("minPrice"),
                    "rating": float(p["rating"]) if p.get("rating") else None,
                    "review_count": int(p["reviewCount"]) if p.get("reviewCount") else 0,
                    "parent_id": (p.get("productVariants") or {}).get("parentId"),
                    "选中颜色/尺寸": (p.get("productVariants") or {}).get("activeSwatchColor") or "",
                    "卖点": "\n".join(b.get("value", "") for b in p.get("marketingBullets") or []),
                    "主图URL": imgs[0] if imgs else "", "全部图片URL": "\n".join(imgs)})
    return out


def details(ctx, row):
    f = ctx.path("lowes", "details", f"{row['id']}.json")
    got = load_json(f)
    if got is not None:
        return got
    st, _ = _get(ctx, row["url"])
    if not st:
        return None
    pd = ((st.get("productDetails") or {}).get(row["id"]) or {}).get("product") or {}
    specs = [f'{x.get("key")}: {x.get("value")}' for x in (pd.get("specs") or pd.get("featuredSpecs") or []) if isinstance(x, dict)]
    d = {"商品描述": re.sub("<[^>]+>", " ", pd.get("romanceCopy") or "").strip(), "规格参数": "\n".join(specs)}
    save_json(f, d)
    return d


def _row(r):
    vp = r.get("verifiedPurchaser")
    return {"评论ID": str(r.get("reviewId")), "评论日期": (r.get("submittedAt") or "")[:10], "评分": r.get("rating"),
            "评论标题": r.get("reviewTitle") or "", "评论原文": r.get("reviewText") or "",
            "VP状态": "VP" if vp is True else ("non_VP" if vp is False else "unknown"),
            "VP证据": f"verifiedPurchaser={vp}; incentivized={r.get('incentivizedReview')}",
            "转载": "是" if r.get("syndicated") else "否", "转载来源": (r.get("source") or "") if r.get("syndicated") else ""}


def reviews_batch(ctx, rows, batch=20, parallel=4, cap=500):
    """{id: (reviews, status, note)} for all rows; Apify runs in parallel batches; cached per product."""
    ap = Apify(ctx)
    todo = [r["id"] for r in rows if load_json(ctx.path("lowes", "apify", f"{r['id']}.json")) is None]
    chunks = [todo[i:i + batch] for i in range(0, len(todo), batch)]

    def run_chunk(chunk):
        got = {p: {"newest": [], "oldest": []} for p in chunk}
        for sort, k in (("newestFirst", "newest"), ("oldestFirst", "oldest")):
            items, usd = ap.run(ACTOR, {"productIds": chunk, "maxReviewsPerProduct": cap, "sort": sort,
                                        "newerThan": ctx.start, "includeRatingsOnly": True}, "lowes")
            ctx.log(f"Lowe's Apify {sort} {len(chunk)} 商品 → {len(items)} 条评论, ${usd:.2f}")
            for it in items:
                if str(it.get("productId")) in got:
                    got[str(it.get("productId"))][k].append(it)
        for p in chunk:
            save_json(ctx.path("lowes", "apify", f"{p}.json"), got[p])

    with ThreadPoolExecutor(max(1, parallel)) as ex:
        list(ex.map(run_chunk, chunks))
    out = {}
    for r in rows:
        raw = load_json(ctx.path("lowes", "apify", f"{r['id']}.json"))
        if raw is None:
            out[r["id"]] = ([], "失败", "Apify 未返回")
            continue
        revs = {}
        for it in raw["newest"] + raw["oldest"]:
            x = _row(it)
            if ctx.in_window(x["评论日期"]):
                revs[x["评论ID"]] = x
        nn, no = len(raw["newest"]), len(raw["oldest"])
        overlap = {i.get("reviewId") for i in raw["newest"]} & {i.get("reviewId") for i in raw["oldest"]}
        ok = nn < cap or no < cap or bool(overlap)
        out[r["id"]] = (list(revs.values()), "完整" if ok else "部分", "" if ok else f"时间窗内评论超过 {2 * cap} 条，中间部分未取到")
    return out
