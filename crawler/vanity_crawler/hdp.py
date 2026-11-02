"""Home Depot: category list (Top Sellers) + public review pages, direct from the cloud."""
import os, re, json
from .common import direct_get, objects_by_key, decode_at, save_json, load_json, DATA, YEAR_START
from .classify import include_reason

ENTRIES = {
    "HDP带台面": "https://www.homedepot.com/b/Bath-Bathroom-Vanities-Bathroom-Vanities-with-Tops/N-5yc1vZcfw5",
    "HDP无台面": "https://www.homedepot.com/b/Bath-Bathroom-Vanities-Bathroom-Vanities-without-Tops/N-5yc1vZcfv9",
}
BASE = "https://www.homedepot.com"
OUT = os.path.join(DATA, "hdp")


def _list_page(url):
    st, b = direct_get(url)
    if st != 200:
        return st, []
    s = b.decode("utf-8", "ignore")
    m = re.search(r'products\(\{\\"filter\\":\{\},\\"orderBy[^)]*\}\)":(\[)', s)
    refs = decode_at(s, m.start(1)) if m else []
    ids = [r["__ref"].split("-")[-1] for r in refs]
    objs = objects_by_key(s, r"base-searchNav-\d+")
    prods = []
    for i in ids:
        o = objs.get(f"base-searchNav-{i}", {})
        prods.append((i, o))
    return st, prods


def collect_list(entry, target=100):
    path = os.path.join(OUT, f"list_{entry}.json")
    cached = load_json(path)
    if cached and cached.get("done"):
        return cached["rows"]
    rows, rank, nao, seen = [], 0, 0, set()
    while rank < target and nao < 600:
        url = f"{ENTRIES[entry]}?Nao={nao}&sortby=topsellers" if nao else f"{ENTRIES[entry]}?sortby=topsellers"
        st, prods = _list_page(url)
        if st != 200 or not prods:
            print(entry, "list page failed", nao, st, flush=True)
            break
        for pid, o in prods:
            if pid in seen:
                continue
            seen.add(pid)
            ident = o.get("identifiers", {}) or {}
            info = o.get("info", {}) or {}
            title = ident.get("productLabel", "")
            badges = next((v for k, v in o.items() if k.startswith("badges")), None) or []
            pricing = next((v for k, v in o.items() if k.startswith("pricing")), None) or {}
            rr = (o.get("reviews") or {}).get("ratingsReviews") or {}
            sponsored = bool(info.get("isSponsored"))
            inc = "排除-广告" if sponsored else include_reason(title, "vanity")
            r = {
                "平台": "HomeDepot", "入口": entry, "商品ID": pid,
                "平台徽章": "; ".join(b.get("label", "") for b in badges if b.get("label")),
                "品牌": ident.get("brandName", ""), "标题": title, "型号/SKU": ident.get("modelNumber", ""),
                "商品链接": BASE + ident.get("canonicalUrl", f"/p/{pid}"),
                "价格(USD)": pricing.get("value"),
                "页面评分": float(rr["averageRating"]) if rr.get("averageRating") else None,
                "页面累计评论数": int(rr["totalReviews"]) if rr.get("totalReviews") else None,
                "纳入情况": inc, "list_page_nao": nao,
            }
            if inc == "纳入" and rank < target:
                rank += 1
                r["排名"] = rank
            elif inc == "纳入":
                continue
            rows.append(r)
        nao += 12
        save_json(path, {"done": False, "rows": rows})
    save_json(path, {"done": rank >= target, "rows": rows})
    return rows


def _review_page(url, item_id, start_index):
    st, b = direct_get(url)
    if st != 200:
        return st, None, []
    s = b.decode("utf-8", "ignore")
    cat = objects_by_key(s, rf"base-catalog-{item_id}").get(f"base-catalog-{item_id}")
    # the page's own result set (not the photo carousel)
    pos = None
    for mm in re.finditer(r'"reviews\(\{', s):
        end = s.find('})":{', mm.start())
        key = s[mm.start():end]
        if end > 0 and len(key) < 600 and f'startIndex\\":{start_index}' in key and f'itemId\\":\\"{item_id}' in key:
            pos = end + len('})":')
            break
    if pos is None:
        return st, cat, []
    resp = decode_at(s, pos)
    return st, cat, resp.get("Results") or []


def _review_row(entry, pid, rv):
    order = rv.get("BadgesOrder") or []
    vp = "VP" if "verifiedPurchaser" in order else "non_VP"
    syn = rv.get("IsSyndicated")
    src = (rv.get("SyndicationSource") or {}).get("Name") if rv.get("SyndicationSource") else None
    return {
        "平台": "HomeDepot", "入口": entry, "商品ID": pid, "评论ID": str(rv.get("Id")),
        "评论日期": (rv.get("SubmissionTime") or "")[:10], "评分": rv.get("Rating"),
        "评论标题": rv.get("Title") or "", "评论原文": rv.get("ReviewText") or "",
        "VP状态": vp, "VP证据": "BadgesOrder=" + (",".join(order) if order else "[]"),
        "转载": "是" if syn else "否", "转载来源": src or "",
        "has_photo": bool(rv.get("Photos")),
    }


def collect_product(entry, row, max_pages=40):
    pid = row["商品ID"]
    path = os.path.join(OUT, "products", f"{pid}.json")
    cached = load_json(path)
    if cached and cached.get("状态") in ("完整", "部分"):
        return cached
    slug_url = row["商品链接"].replace("/p/", "/p/reviews/", 1)
    reviews, details, status, note = {}, None, "完整", ""
    in_text_phase = False
    for page in range(1, max_pages + 1):
        start = (page - 1) * 30 + 1
        st, cat, res = _review_page(f"{slug_url}/{page}", pid, start)
        if page == 1 and cat:
            details = cat
        if st == 404:
            if not in_text_phase or (reviews and min(r["评论日期"] for r in reviews.values()) >= YEAR_START and row.get("页面累计评论数", 0) > start):
                status, note = "部分", f"HDP 评论页上限：第{page}页返回404，之后的2026评论无法翻到"
            break
        if st != 200:
            status, note = "失败" if page == 1 else "部分", f"评论第{page}页 HTTP {st}"
            break
        if not res:
            break
        stop = False
        for rv in res:
            r = _review_row(entry, pid, rv)
            if not r["has_photo"]:
                in_text_phase = True
            if r["评论日期"] >= YEAR_START:
                reviews[r["评论ID"]] = r
            elif in_text_phase and not r["has_photo"]:
                stop = True
        if stop or start + 30 > (row.get("页面累计评论数") or 0):
            break
    out = {"状态": status, "备注": note, "details": _details(details), "reviews": list(reviews.values())}
    save_json(path, out)
    return out


def _details(cat):
    if not cat:
        return {}
    d = cat.get("details") or {}
    imgs = [i.get("url", "").replace("<SIZE>", "1000") for i in (cat.get("media") or {}).get("images", []) if i.get("type") == "IMAGE"]
    specs = []
    for g in cat.get("specificationGroup") or []:
        for sp in g.get("specifications") or []:
            specs.append(f'{sp.get("specName")}: {sp.get("specValue")}')
    return {
        "卖点": "\n".join(d.get("highlights") or []),
        "商品描述": d.get("description") or "",
        "规格参数": "\n".join(specs),
        "主图URL": imgs[0] if imgs else "",
        "全部图片URL": "\n".join(imgs),
        "选中颜色/尺寸": next((s.split(": ", 1)[1] for s in specs if s.startswith("Color Family") or s.startswith("Cabinet Color")), ""),
    }
