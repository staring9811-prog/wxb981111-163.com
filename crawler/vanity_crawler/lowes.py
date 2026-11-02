"""Lowe's: Best Sellers list + PDP + public review pages (/reviews/<slug>/<id>?offset=N), via BD."""
import os, re, json
from concurrent.futures import ThreadPoolExecutor
from . import bd
from .common import decode_at, save_json, load_json, DATA, YEAR_START
from .classify import include_reason

ENTRIES = {
    "Lowes带台面榜": "https://www.lowes.com/pl/bathroom-vanities-with-tops/4294684460",
    "Lowes无台面榜": "https://www.lowes.com/pl/bathroom-vanities-without-tops/4294684459",
}
BASE = "https://www.lowes.com"
IMG = "https://mobileimages.lowes.com"
OUT = os.path.join(DATA, "lowes")
BUDGET = 10.0
BATCH = 8  # review pages fetched in parallel per product


def _state(b):
    s = b.decode("utf-8", "ignore")
    m = re.search(r'window\[?.?__PRELOADED_STATE__.?\]?\s*=\s*', s)
    return (decode_at(s, m.end()) if m else None), s


def _get(url, tries=3):
    for _ in range(tries):
        st, b = bd.fetch(url, "lowes", retries=0, budget_usd=BUDGET)
        if st == 200 and b"__PRELOADED_STATE__" in b:
            return _state(b)
    return None, ""


def collect_list(entry, target=100):
    path = os.path.join(OUT, f"list_{entry}.json")
    cached = load_json(path)
    if cached and cached.get("done"):
        return cached["rows"]
    offsets = list(range(0, 24 * 6, 24))  # 6 pages = 144 slots, enough for 100 after exclusions
    urls = [f"{ENTRIES[entry]}?sortMethod=sortBy_bestSellers&offset={o}" for o in offsets]
    with ThreadPoolExecutor(len(urls)) as ex:
        pages = list(ex.map(_get, urls))
    rows, rank, seen = [], 0, set()
    for o, (st, _) in zip(offsets, pages):
        if not st:
            print(entry, "list page failed offset", o, flush=True)
            continue
        for it in st.get("itemList") or []:
            p, loc = it.get("product") or {}, it.get("location") or {}
            pid = p.get("omniItemId")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            title = p.get("description", "")
            sponsored = bool(p.get("sponsored"))
            inc = "排除-广告" if sponsored else include_reason(title, "vanity")
            badge = loc.get("badge") or {}
            badges = []
            if isinstance(badge, dict):
                badges = [v for k, v in badge.items() if isinstance(v, str) and v and k.lower() in ("text", "label", "name", "badgetext")]
            if loc.get("promoBadge"):
                badges.append(str(loc.get("promoBadge")))
            price = (loc.get("price") or {})
            imgs = [IMG + p["imageUrl"]] if p.get("imageUrl") else []
            imgs += [x.get("baseUrl") for x in (p.get("epc") or {}).get("additionalImages", []) if x.get("baseUrl")]
            r = {
                "平台": "Lowes", "入口": entry, "商品ID": pid, "平台徽章": "; ".join(badges),
                "品牌": p.get("brand", ""), "标题": title, "型号/SKU": f'{p.get("modelId","")} / Item {p.get("itemNumber","")}',
                "选中颜色/尺寸": ((p.get("productVariants") or {}).get("activeSwatchColor") or ""),
                "卖点": "\n".join(b.get("value", "") for b in p.get("marketingBullets") or []),
                "主图URL": imgs[0] if imgs else "", "全部图片URL": "\n".join(imgs),
                "商品链接": BASE + p.get("pdURL", ""),
                "价格(USD)": price.get("sellingPrice") or price.get("minPrice") or price.get("price"),
                "页面评分": float(p["rating"]) if p.get("rating") else None,
                "页面累计评论数": int(p["reviewCount"]) if p.get("reviewCount") else None,
                "纳入情况": inc, "list_offset": o,
            }
            if inc == "纳入":
                if rank >= target:
                    continue
                rank += 1
                r["排名"] = rank
            rows.append(r)
    save_json(path, {"done": rank >= target, "rows": rows, "store": (pages[0][0] or {}).get("requestParams", {}).get("queryString", "")[:400] if pages[0][0] else ""})
    return rows


def _review_rows(entry, pid, results):
    out = []
    for x in results:
        cdv = x.get("contextDataValues") or {}
        badges = [b.get("id") for b in (x.get("badges") or []) if b.get("id")]
        vp = x.get("verifiedPurchaser")
        vps = "VP" if vp is True else ("non_VP" if vp is False else "unknown")
        ev = f'verifiedPurchaser={vp}; incentivized={x.get("incentivizedReview")}; badges={",".join(badges) or "[]"}'
        if "VerifiedPurchaserCDV" in cdv:
            ev += f'; CDV={cdv["VerifiedPurchaserCDV"].get("value")}'
        syn = x.get("isSyndicated")
        out.append({
            "平台": "Lowes", "入口": entry, "商品ID": pid, "评论ID": str(x.get("legacyId") or x.get("id")),
            "评论日期": (x.get("submissionTime") or "")[:10], "评分": x.get("rating"),
            "评论标题": x.get("title") or "", "评论原文": x.get("reviewText") or "",
            "VP状态": vps, "VP证据": ev, "转载": "是" if syn else "否",
            "转载来源": (x.get("clientName") or "") if syn else "",
            "评论所属商品ID": x.get("productId") or "",
        })
    return out


_family_cache = {}


def collect_product(entry, row):
    pid = row["商品ID"]
    path = os.path.join(OUT, "products", f"{pid}.json")
    cached = load_json(path)
    if cached and (cached.get("状态") == "完整" or (cached.get("状态") == "部分" and "取不到" not in cached.get("备注", ""))):
        return cached
    st, s = _get(row["商品链接"])
    det, rev_path = {}, None
    if st:
        pd = ((st.get("productDetails") or {}).get(pid) or {}).get("product") or {}
        specs = [f'{x.get("key")}: {x.get("value")}' for x in pd.get("specs") or [] if isinstance(x, dict)]
        if not specs:
            specs = [f'{x.get("key")}: {x.get("value")}' for x in pd.get("featuredSpecs") or []]
        det = {"商品描述": re.sub("<[^>]+>", " ", pd.get("romanceCopy") or "").strip(), "规格参数": "\n".join(specs)}
        m = re.search(r'/reviews/[a-z0-9\-]+/' + pid, s)
        rev_path = m.group(0) if m else None
    if not rev_path:
        out = {"状态": "失败", "备注": "商品页未取到或无评论页链接", "details": det, "reviews": []}
        save_json(path, out)
        return out
    reviews, status, note, first_ids = {}, "完整", "", None

    def page(off):
        rst, _ = _get(f"{BASE}{rev_path}?offset={off}")
        if not rst:
            return off, None, 0
        rl = next(iter((rst.get("ratingList") or {}).values()), {}) or {}
        return off, rl.get("results") or [], rl.get("totalResults") or 0

    def absorb(res):
        old = False
        for r in _review_rows(entry, pid, res):
            if r["评论日期"] >= YEAR_START:
                reviews[r["评论ID"]] = r
            else:
                old = True
        return old

    _, res, total = page(0)
    if res is None:
        status, note = "失败", "评论页 offset=0 取不到"
    else:
        first_ids = tuple(str(x.get("id")) for x in res)
        if first_ids and first_ids in _family_cache:
            src = _family_cache[first_ids]
            srcd = load_json(os.path.join(OUT, "products", f"{src}.json")) or {}
            if srcd.get("reviews") is not None:
                rows = [dict(r, 商品ID=pid, 入口=entry) for r in srcd["reviews"]]
                out = {"状态": srcd["状态"], "备注": f"与 {src} 同系列共享评论", "details": det, "reviews": rows}
                save_json(path, out)
                return out
        done = absorb(res) or not res
        nxt = 20
        while not done and nxt < total:
            batch = [o for o in range(nxt, min(nxt + 20 * BATCH, total), 20)]
            with ThreadPoolExecutor(len(batch)) as ex:
                got = sorted(ex.map(page, batch))
            for off, r, _t in got:
                if r is None:
                    status, note = "部分", f"评论页 offset={off} 取不到"
                    done = True
                    continue
                if absorb(r) or not r:
                    done = True
            nxt += 20 * BATCH
    out = {"状态": status, "备注": note, "details": det, "reviews": list(reviews.values())}
    save_json(path, out)
    if first_ids and status == "完整":
        _family_cache[first_ids] = pid
    return out
