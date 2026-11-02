import sys, os, json, collections
sys.path.insert(0, os.path.dirname(__file__))
from vanity_crawler import wayfair, hdp
from concurrent.futures import ThreadPoolExecutor

def wf():
    out = []
    for entry, (url, _) in wayfair.ENTRIES.items():
        s = wayfair._get(url)
        cards = wayfair._cards(s)
        org = [c for c in cards if not c["sponsored"]]
        out.append(f"WAYFAIR LIST {entry}: cards {len(cards)}, organic {len(org)}, sponsored {len(cards)-len(org)}")
        out += [f"  {i+1} {c['sku']} {c['rating']} {c['reviews']} {c['flag']} {c['url'][:90]}" for i, c in enumerate(org[:5])]
        if entry == "Wayfair主类目" and org:
            c = org[0]
            row = {"sku": c["sku"], "商品ID": c["sku"], "商品链接": c["url"], "页面累计评论数": c["reviews"]}
            o = wayfair.collect_product(entry, row)
            rv = o["reviews"]
            out.append(f"WAYFAIR PRODUCT {c['sku']} {o['状态']} {o['备注']} embedded {o.get('embedded')} / total {c['reviews']}, 2026: {len(rv)}")
            out.append(f"  VP {collections.Counter(r['VP状态'] for r in rv)} evidence {collections.Counter(r['VP证据'] for r in rv)}")
            out.append(f"  months {sorted(collections.Counter(r['评论日期'][:7] for r in rv).items())}")
            out.append(f"  details { {k: v[:80] for k, v in o['details'].items()} }")
    return "\n".join(out)

def hd():
    out = []
    entry = "HDP无台面"
    st, prods = hdp._list_page(hdp.ENTRIES[entry] + "?sortby=topsellers")
    out.append(f"HDP LIST {entry}: status {st}, products {len(prods)}")
    for i, (pid, o) in enumerate(prods[:5]):
        out.append(f"  {i+1} {pid} {(o.get('identifiers') or {}).get('productLabel','')[:70]}")
    pid, o = prods[0]
    ident = o.get("identifiers") or {}
    row = {"商品ID": pid, "商品链接": hdp.BASE + ident.get("canonicalUrl", f"/p/{pid}"),
           "页面累计评论数": int(((o.get("reviews") or {}).get("ratingsReviews") or {}).get("totalReviews") or 0)}
    r = hdp.collect_product(entry, row)
    rv = r["reviews"]
    out.append(f"HDP PRODUCT {pid} {r['状态']} {r['备注']} 2026: {len(rv)} VP {collections.Counter(x['VP状态'] for x in rv)}")
    out.append(f"  months {sorted(collections.Counter(x['评论日期'][:7] for x in rv).items())}")
    return "\n".join(out)

with ThreadPoolExecutor(2) as ex:
    a, b = ex.submit(wf), ex.submit(hd)
    print(b.result(), flush=True)
    print(a.result(), flush=True)
print("BD ledger", open(os.path.join(os.path.dirname(__file__), "data", "bd_ledger.json")).read())
