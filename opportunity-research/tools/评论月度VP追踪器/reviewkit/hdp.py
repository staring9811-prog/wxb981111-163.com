"""Home Depot adapter — public pages, direct connection (no BD needed). No public BSR: Top Sellers order.

Reviews: /p/reviews/<slug>/<id>/<page>, 30 per page, photo reviews first (newest→oldest) then text reviews
(newest→oldest); HDP serves at most ~17 pages, so very large products may be 部分.
"""
import os, re, urllib.parse
from .common import direct_get, objects_by_key, decode_at, save_json, load_json, add_query

BASE = "https://www.homedepot.com"
NAME = "HomeDepot"


def entry_url(entry):
    if entry.get("mode") == "keyword":
        u = f"{BASE}/s/{urllib.parse.quote(entry['keyword'])}"
    else:
        u = entry["url"]
    return add_query(u, sortby=entry.get("sort") or "topsellers")


def list_page(ctx, entry, page_no, state):
    """page_no from 0; state['offset'] carries the Nao offset (page size differs: 12 category / 24 search)."""
    off = state.get("offset", 0)
    url = add_query(entry_url(entry), Nao=off or None)
    st, b = direct_get(url)
    if st != 200:
        return None
    s = b.decode("utf-8", "ignore")
    m = re.search(r'products\(\{\\"filter\\":\{[^)]*\}\)":(\[)', s)
    refs = decode_at(s, m.start(1)) if m else []
    ids = [r["__ref"].split("-")[-1] for r in refs if isinstance(r, dict) and "__ref" in r]
    objs = objects_by_key(s, r"base-searchNav-\d+")
    state["offset"] = off + len(ids)
    out = []
    for pid in ids:
        o = objs.get(f"base-searchNav-{pid}", {})
        ident = o.get("identifiers") or {}
        info = o.get("info") or {}
        badges = next((v for k, v in o.items() if k.startswith("badges")), None) or []
        pricing = next((v for k, v in o.items() if k.startswith("pricing")), None) or {}
        rr = (o.get("reviews") or {}).get("ratingsReviews") or {}
        out.append({"id": pid, "url": BASE + ident.get("canonicalUrl", f"/p/{pid}"),
                    "title": ident.get("productLabel", ""), "brand": ident.get("brandName", ""),
                    "model": ident.get("modelNumber", ""), "sponsored": bool(info.get("isSponsored")),
                    "badges": "; ".join(x.get("label", "") for x in badges if x.get("label")),
                    "price": pricing.get("value"),
                    "rating": float(rr["averageRating"]) if rr.get("averageRating") else None,
                    "review_count": int(rr["totalReviews"]) if rr.get("totalReviews") else 0,
                    "parent_id": None})
    return out


def _review_page(url, item_id, start_index):
    st, b = direct_get(url)
    if st != 200:
        return st, None, []
    s = b.decode("utf-8", "ignore")
    cat = objects_by_key(s, rf"base-catalog-{item_id}").get(f"base-catalog-{item_id}")
    pos = None
    for mm in re.finditer(r'"reviews\(\{', s):
        end = s.find('})":{', mm.start())
        k = s[mm.start():end]
        if end > 0 and len(k) < 600 and f'startIndex\\":{start_index}' in k and f'itemId\\":\\"{item_id}' in k:
            pos = end + len('})":')
            break
    if pos is None:
        return st, cat, []
    return st, cat, decode_at(s, pos).get("Results") or []


def _details(cat):
    if not cat:
        return {}
    d = cat.get("details") or {}
    imgs = [i.get("url", "").replace("<SIZE>", "1000") for i in (cat.get("media") or {}).get("images", []) if i.get("type") == "IMAGE"]
    specs = [f'{sp.get("specName")}: {sp.get("specValue")}' for g in cat.get("specificationGroup") or [] for sp in g.get("specifications") or []]
    return {"卖点": "\n".join(d.get("highlights") or []), "商品描述": d.get("description") or "",
            "规格参数": "\n".join(specs), "主图URL": imgs[0] if imgs else "", "全部图片URL": "\n".join(imgs)}


def family_signature(ctx, row):
    """IDs of the first review page: products sharing reviews (same family / 父体) have the same signature."""
    f = ctx.path("hdp", "sig", f"{row['id']}.json")
    got = load_json(f)
    if got is not None:
        return got["sig"]
    st, cat, res = _review_page(row["url"].replace("/p/", "/p/reviews/", 1) + "/1", row["id"], 1)
    sig = ",".join(sorted(str(r.get("Id")) for r in res)) if res else f"self:{row['id']}"
    save_json(f, {"sig": sig})
    return sig


def collect(ctx, row, max_pages=40):
    """Details + all in-window reviews for one product. Cached."""
    pid = row["id"]
    f = ctx.path("hdp", "products", f"{pid}.json")
    cached = load_json(f)
    if cached and cached.get("状态") in ("完整", "部分"):
        return cached
    base = row["url"].replace("/p/", "/p/reviews/", 1)
    reviews, details, status, note, text_phase = {}, None, "完整", "", False
    for page in range(1, max_pages + 1):
        start = (page - 1) * 30 + 1
        st, cat, res = _review_page(f"{base}/{page}", pid, start)
        if page == 1 and cat:
            details = cat
        if st == 404:
            if reviews and (row.get("review_count") or 0) > start:
                status, note = "部分", f"HDP 评论页上限：第{page}页返回404"
            break
        if st != 200:
            status, note = ("失败" if page == 1 else "部分"), f"评论第{page}页 HTTP {st}"
            break
        if not res:
            break
        stop = False
        for rv in res:
            d = (rv.get("SubmissionTime") or "")[:10]
            photo = bool(rv.get("Photos"))
            if not photo:
                text_phase = True
            if ctx.in_window(d):
                order = rv.get("BadgesOrder") or []
                syn = rv.get("IsSyndicated")
                reviews[str(rv.get("Id"))] = {
                    "评论ID": str(rv.get("Id")), "评论日期": d, "评分": rv.get("Rating"),
                    "评论标题": rv.get("Title") or "", "评论原文": rv.get("ReviewText") or "",
                    "VP状态": "VP" if "verifiedPurchaser" in order else "non_VP",
                    "VP证据": "BadgesOrder=" + (",".join(order) or "[]"), "转载": "是" if syn else "否",
                    "转载来源": ((rv.get("SyndicationSource") or {}).get("Name") or "") if syn else ""}
            elif d and d < ctx.start and text_phase and not photo:
                stop = True
        if stop or start + 30 > (row.get("review_count") or 0):
            break
    out = {"状态": status, "备注": note, "details": _details(details), "reviews": list(reviews.values())}
    save_json(f, out)
    return out
