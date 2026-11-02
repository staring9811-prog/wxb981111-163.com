"""Wayfair: category list (Recommended) + PDP (details + reviews embedded in the page), via BD."""
import os, re, json, html
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from . import bd
from .common import save_json, load_json, DATA, YEAR_START
from .classify import include_reason

ENTRIES = {
    "Wayfair主类目": ("https://www.wayfair.com/bed-bath/sb0/bathroom-vanities-c527058.html", 200),
    "Wayfair无台面类目": ("https://www.wayfair.com/bed-bath/sb0/vanity-bases-c527056.html", 50),
}
OUT = os.path.join(DATA, "wayfair")
BUDGET = 10.0


def _get(url, tries=3, min_cards=0):
    best = ""
    for _ in range(tries):
        st, b = bd.fetch(url, "wayfair", retries=0, budget_usd=BUDGET)
        if st == 200 and len(b) > 100000:
            s = b.decode("utf-8", "ignore")
            if not min_cards or len(_cards(s)) >= min_cards:
                return s
            if len(_cards(s)) > len(_cards(best)) if best else True:
                best = s
    return best


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
        ctx_s = s.rfind('data-clio-context="', 0, ts)
        ctx_raw = s[ctx_s + 19:s.find('"', ctx_s + 19)] if ctx_s > 0 else "{}"
        try:
            ctx = json.loads(html.unescape(ctx_raw))
        except Exception:
            ctx = {}
        sponsored = bool(ctx.get("isSponsored")) or "Sponsored" in a.get("data-node-id", "") and "SponsoredShop" not in a.get("data-node-id", "")
        tail = s[m.start():m.start() + 6000]
        link = re.search(r'href="(https://www\.wayfair\.com/[^"]+/pdp/[^"]+?\.html\?piid=[^"&]+)', tail) or re.search(r'href="(https://www\.wayfair\.com/[^"]+/pdp/[^"]+?\.html[^"]*)"', tail)
        name = re.search(r'data-name-id="ListingCardName"[^>]*>(?:<[^>]+>)*([^<]+)', tail)
        out.append({"sku": meta.get("displayListingId"), "url": html.unescape(link.group(1)) if link else "",
                    "sponsored": sponsored, "price": meta.get("firstPriceValue"), "rating": meta.get("averageRating"),
                    "reviews": meta.get("totalReviewCount"), "flag": meta.get("flagText") or "",
                    "stamp": "Best Value" if meta.get("bestValueStamp") else "",
                    "name": html.unescape(name.group(1)).strip() if name else ""})
    return out


def collect_list(entry):
    url0, target = ENTRIES[entry]
    path = os.path.join(OUT, f"list_{entry}.json")
    cached = load_json(path)
    if cached and cached.get("done"):
        return cached["rows"]
    pdir = os.path.join(OUT, "listpages")

    def page_cards(p):
        f = os.path.join(pdir, f"{entry}_{p}.json")
        got = load_json(f)
        if got:
            return got
        s = _get(url0 if p == 1 else f"{url0}?curpage={p}", tries=4, min_cards=30)
        cards = _cards(s) if s else None
        if cards:
            save_json(f, cards)
        return cards

    n = (target // 40) + 2
    while True:
        with ThreadPoolExecutor(n) as ex:
            allp = list(ex.map(page_cards, range(1, n + 1)))
        if any(c is None for c in allp):
            bad = [i + 1 for i, c in enumerate(allp) if c is None]
            print(entry, "list pages failed", bad, "- ranks stop before first gap", flush=True)
            allp = allp[:bad[0] - 1]
            break
        organic = sum(1 for cs in allp for c in cs if not c["sponsored"])
        if organic >= target * 1.15 or n >= 20:
            break
        n += 3
    rows, rank, seen = [], 0, set()
    for p, cs in enumerate(allp, 1):
        for c in cs:
            if not c["sku"] or c["sku"] in seen:
                continue
            seen.add(c["sku"])
            slug = c["url"].split("/pdp/")[-1].split(".html")[0].replace("-", " ")
            inc = "排除-广告" if c["sponsored"] else include_reason(c["name"] or slug, "vanity")
            piid = re.search(r"piid=([0-9,%C]+)", c["url"])
            r = {"平台": "Wayfair", "入口": entry,
                 "商品ID": c["sku"] + (f" (piid {piid.group(1)})" if piid else ""), "sku": c["sku"],
                 "平台徽章": "; ".join(x for x in (c["flag"], c["stamp"]) if x),
                 "标题": c["name"], "商品链接": c["url"], "价格(USD)": float(c["price"]) if c["price"] else None,
                 "页面评分": c["rating"], "页面累计评论数": c["reviews"], "纳入情况": inc, "list_page": p}
            if inc == "纳入":
                if rank >= target:
                    continue
                rank += 1
                r["排名"] = rank
            rows.append(r)
    save_json(path, {"done": rank >= target, "rows": rows})
    return rows


def _unesc(s):
    return s.replace('\\\\"', '\u0001').replace('\\"', '"').replace('\u0001', '\\"')


def _vp(badge):
    if badge == "Verified Purchase":
        return "VP"
    if not badge:
        return "non_VP"
    return "unknown"  # Incentivized / Wayfair Professional: single badge slot, purchase status not shown


def parse_pdp(s, sku):
    u = _unesc(s)
    title = re.search(r'og:title" content="([^"]+)"', s)
    title = html.unescape(title.group(1)).replace(" & Reviews | Wayfair", "") if title else ""
    brand = re.search(r'"manufacturer":\{"manufacturerId":\d+,"name":"([^"]+)"', u)
    specs = list(dict.fromkeys(f"{k}: {v}" for k, v in re.findall(r'\{"key":"([^"]+)","value":"((?:[^"\\]|\\.)*)","(?:children|__typename)', u)))
    copy = re.search(r'"marketingCopy":"((?:[^"\\]|\\.)*)"', u)
    bullets = re.search(r'"featureBullets":\[(.*?)\]', u)
    bl = re.findall(r'"((?:[^"\\]|\\.)+)"', bullets.group(1)) if bullets else []
    why = re.search(r'"title":"Why We Love It","bullets":\[(.*?)\]', u)
    if why:
        bl += re.findall(r'"((?:[^"\\]|\\.)+)"', why.group(1))
    lead = re.search(r'"leadImage":\{[^}]*"imageId":(\d+)', u)
    tray = u[u.find('"leadImage"'):u.find('"leadImage"') + 20000] if lead else ""
    ids = list(dict.fromkeys(re.findall(r'"imageId":(\d+)', tray)))
    imgs = [f"https://assets.wfcdn.com/im/x/resize-h800-w800%5Ecompr-r85/{i[:4]}/{i}/x.jpg" for i in ids]
    reviews = {}
    for m in re.finditer(r'"__typename":"MarketplaceListingReview","reviewId":(\d+)', u):
        nxt = u.find('"__typename":"MarketplaceListingReview","reviewId"', m.end())
        seg = u[m.start():(nxt if 0 < nxt < m.start() + 6000 else m.start() + 6000)]
        def g(k, pat='"((?:[^"\\\\]|\\\\.)*)"'):
            mm = re.search('"' + k + '":' + pat, seg)
            return mm.group(1) if mm else None
        d = g("formattedDate")
        try:
            iso = datetime.strptime(d, "%m/%d/%Y").strftime("%Y-%m-%d") if d else ""
        except ValueError:
            iso = ""
        badge = g("badge")
        reviews[m.group(1)] = {"评论ID": m.group(1), "评论日期": iso, "评分": int(g("rating", r"(\d)") or 0) or None,
                               "评论标题": g("headline") or "", "评论原文": (g("body") or "").replace('\\"', '"'),
                               "VP状态": _vp(badge), "VP证据": f"badge={badge or 'null'}",
                               "转载": "否", "转载来源": "", "选项": ", ".join(f"{a}={b}" for a, b in re.findall(r'"ReviewChoice","name":"([^"]+)","value":"([^"]+)"', seg))}
    return {"标题": title, "品牌": brand.group(1) if brand else "",
            "商品描述": (copy.group(1) if copy else "").replace('\\"', '"'), "卖点": "\n".join(bl),
            "规格参数": "\n".join(specs), "主图URL": imgs[0] if imgs else "", "全部图片URL": "\n".join(imgs),
            "型号/SKU": sku}, list(reviews.values())


def collect_product(entry, row):
    sku = row["sku"]
    path = os.path.join(OUT, "products", f"{sku}.json")
    cached = load_json(path)
    if cached and cached.get("状态") in ("完整", "部分"):
        return cached
    s = _get(row["商品链接"])
    if not s:
        out = {"状态": "失败", "备注": "商品页取不到", "details": {}, "reviews": []}
        save_json(path, out)
        return out
    det, revs = parse_pdp(s, sku)
    for r in revs:
        r.update({"平台": "Wayfair", "入口": entry, "商品ID": row["商品ID"]})
    got = len(revs)
    total = row.get("页面累计评论数") or 0
    in_year = [r for r in revs if r["评论日期"] >= YEAR_START]
    older_seen = any(r["评论日期"] and r["评论日期"] < YEAR_START for r in revs)
    if got >= total:
        status, note = "完整", ""
    else:
        status = "部分"
        note = f"商品页内嵌评论 {got}/{total} 条（相关度排序），更多评论需翻页接口，未取"
    out = {"状态": status, "备注": note, "details": det, "reviews": in_year, "embedded": got}
    save_json(path, out)
    return out
