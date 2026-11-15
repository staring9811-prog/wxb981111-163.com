"""Wayfair adapter — list pages via Bright Data; details + reviews via Apify (abotapi/wayfair-scraper).

Reviews: newest first. Pass 1 takes 100 per product; products whose last review is still inside the window get
pass 2 (300), then pass 3 (1000). Wayfair shows one badge per review; VP = badge "Verified Purchase", everything else non_VP.
"""
import html, json, re, urllib.parse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from .common import save_json, load_json, add_query
from .services import BD, Apify

NAME = "Wayfair"
ACTOR = "abotapi/wayfair-scraper"


def entry_url(entry):
    if entry.get("mode") == "keyword":
        return f"https://www.wayfair.com/keyword.php?keyword={urllib.parse.quote_plus(entry['keyword'])}"
    return entry["url"]


def _cards(s):
    out = []
    for m in re.finditer(r'data-clio-id="ListingCardContents::', s):
        ts = s.rfind("<", 0, m.start())
        tag = s[ts:s.find(">", m.start())]
        a = {k: html.unescape(v) for k, v in re.findall(r'(data-[a-z\-]+)="([^"]*)"', tag)}
        try:
            meta = json.loads(a.get("data-tracking-metadata", "{}")).get("metadata", {})
        except Exception:
            meta = {}
        cs = s.rfind('data-clio-context="', 0, ts)
        try:
            ctx_j = json.loads(html.unescape(s[cs + 19:s.find('"', cs + 19)])) if cs > 0 else {}
        except Exception:
            ctx_j = {}
        tail = s[m.start():m.start() + 6000]
        link = re.search(r'href="(https://www\.wayfair\.com/[^"]+/pdp/[^"]+?\.html[^"]*)"', tail)
        out.append({"sku": meta.get("displayListingId"), "url": html.unescape(link.group(1)) if link else "",
                    "sponsored": bool(ctx_j.get("isSponsored")), "price": meta.get("firstPriceValue"),
                    "rating": meta.get("averageRating"), "reviews": meta.get("totalReviewCount"),
                    "badge": "; ".join(x for x in (meta.get("flagText"), "Best Value" if meta.get("bestValueStamp") else "") if x)})
    return out


def list_page(ctx, entry, page_no, state):
    f = ctx.path("wayfair", "listpages", f"{entry['name']}_{page_no}.json")
    cards = load_json(f)
    if cards is None:
        bd, best = BD(ctx), []
        url = add_query(entry_url(entry), curpage=page_no + 1 if page_no else None)
        for _ in range(4):  # pages sometimes render only a few cards → retry
            st, b = bd.fetch(url, "wayfair")
            if st == 200:
                c = _cards(b.decode("utf-8", "ignore"))
                if len(c) > len(best):
                    best = c
                if len(c) >= 30:
                    break
        if not best:
            return None
        cards = best
        save_json(f, cards)
    out = []
    for c in cards:
        if not c["sku"]:
            continue
        slug = c["url"].split("/pdp/")[-1].split(".html")[0].replace("-", " ")
        out.append({"id": c["sku"], "url": c["url"], "title": slug, "brand": "", "model": c["sku"],
                    "sponsored": c["sponsored"], "badges": c["badge"],
                    "price": float(c["price"]) if c["price"] else None, "rating": c["rating"],
                    "review_count": c["reviews"] or 0, "parent_id": c["sku"]})
    return out


def _date(s):
    try:
        return datetime.strptime(s or "", "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _details(it):
    imgs = it.get("images") or []
    imgs = [i if isinstance(i, str) else (i or {}).get("url", "") for i in imgs]
    specs = it.get("specifications") or {}
    if isinstance(specs, dict):
        specs = [f"{k}: {v}" for k, v in specs.items()]
    elif isinstance(specs, list):
        specs = [f"{x.get('name') or x.get('key')}: {x.get('value')}" if isinstance(x, dict) else str(x) for x in specs]
    return {"标题": it.get("name") or "", "品牌": it.get("brand") or "", "商品描述": it.get("description") or "",
            "卖点": "\n".join(it.get("highlights") or []) if isinstance(it.get("highlights"), list) else str(it.get("highlights") or ""),
            "规格参数": "\n".join(specs), "主图URL": it.get("imageUrl") or (imgs[0] if imgs else ""),
            "全部图片URL": "\n".join(i for i in imgs if i)}


def _run(ctx, ap, rows, cap, details):
    items, usd = ap.run(ACTOR, {"mode": "url", "urls": [r["url"] for r in rows], "fetchReviews": True,
                                "fetchDetails": details, "maxReviewsPerProduct": cap, "reviewSort": "newest",
                                "maxItems": len(rows)}, "wayfair")
    ctx.log(f"Wayfair Apify {len(rows)} 商品 (每个最多 {cap} 条) → {len(items)} 条, ${usd:.2f}")
    by = {str(i.get("sku", "")).upper(): i for i in items}
    for r in rows:
        it = by.get(r["id"].upper())
        if it is not None:
            if details:
                save_json(ctx.path("wayfair", "details", f"{r['id']}.json"), _details(it))
            save_json(ctx.path("wayfair", "apify", f"{r['id']}.json"), {"cap": cap, "item": it})


def reviews_batch(ctx, rows, batch=10, parallel=4):
    ap = Apify(ctx)
    def need(r, cap):
        raw = load_json(ctx.path("wayfair", "apify", f"{r['id']}.json"))
        if raw is None:
            return True
        rv = raw["item"].get("reviews") or []
        return raw["cap"] < cap and len(rv) >= raw["cap"] and ctx.in_window(_date(rv[-1].get("date")))
    for n, cap in enumerate((100, 300, 1000), 1):
        todo = [r for r in rows if need(r, cap)]
        if not todo:
            continue
        ctx.log(f"Wayfair 第{n}轮（每个最多 {cap} 条）：{len(todo)} 个商品")
        chunks = [todo[i:i + batch] for i in range(0, len(todo), batch)]
        with ThreadPoolExecutor(max(1, parallel)) as ex:
            list(ex.map(lambda c: _run(ctx, ap, c, cap, cap == 100), chunks))
    out = {}
    for r in rows:
        raw = load_json(ctx.path("wayfair", "apify", f"{r['id']}.json"))
        if raw is None:
            out[r["id"]] = ([], "失败", "Apify 未返回", {})
            continue
        it, revs = raw["item"], []
        for x in it.get("reviews") or []:
            d = _date(x.get("date"))
            if ctx.in_window(d):
                badge = x.get("badge")
                revs.append({"评论ID": str(x.get("reviewId")), "评论日期": d, "评分": x.get("rating"), "评论标题": "",
                             "评论原文": x.get("text") or "", "VP状态": "VP" if badge == "Verified Purchase" else "non_VP",
                             "VP证据": f"badge={badge or 'null'}", "转载": "否", "转载来源": ""})
        allrv = it.get("reviews") or []
        full = len(allrv) < raw["cap"] or not ctx.in_window(_date(allrv[-1].get("date"))) if allrv else True
        det = load_json(ctx.path("wayfair", "details", f"{r['id']}.json"))
        out[r["id"]] = (revs, "完整" if full else "部分", "" if full else "时间窗内评论超过 1000 条", det or {})
    return out
