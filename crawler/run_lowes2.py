"""Lowe's v2: lists + product detail pages via BD, all 2026 reviews via Apify. Resumable.

usage: APIFY_TOKEN=... python3 run_lowes2.py   (or the token injected via Network secrets)
"""
import sys, os, re, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(__file__))
from vanity_crawler import lowes, apify_reviews
from vanity_crawler.common import load_json, save_json, DATA

DET = os.path.join(DATA, "lowes", "details")


def details(row):
    pid = row["商品ID"]
    f = os.path.join(DET, f"{pid}.json")
    got = load_json(f)
    if got:
        return got
    st, s = lowes._get(row["商品链接"])
    if not st:
        return None
    pd = ((st.get("productDetails") or {}).get(pid) or {}).get("product") or {}
    specs = [f'{x.get("key")}: {x.get("value")}' for x in pd.get("specs") or [] if isinstance(x, dict)]
    if not specs:
        specs = [f'{x.get("key")}: {x.get("value")}' for x in pd.get("featuredSpecs") or []]
    d = {"商品描述": re.sub("<[^>]+>", " ", pd.get("romanceCopy") or "").strip(), "规格参数": "\n".join(specs)}
    save_json(f, d)
    return d


rows_all = []
for entry in lowes.ENTRIES:
    t = time.time()
    rows = lowes.collect_list(entry)
    inc = [r for r in rows if r.get("排名")]
    print(entry, "list rows", len(rows), "included", len(inc), f"{time.time()-t:.0f}s", flush=True)
    rows_all += [(entry, r) for r in inc]

ids = list(dict.fromkeys(r["商品ID"] for _, r in rows_all))
print("apify reviews for", len(ids), "products", flush=True)
revs = apify_reviews.lowes_reviews(ids)

print("detail pages via BD", flush=True)
with ThreadPoolExecutor(6) as ex:
    dets = dict(zip([r["商品ID"] for _, r in rows_all], ex.map(lambda er: details(er[1]), rows_all)))

for entry, r in rows_all:
    pid = r["商品ID"]
    rows, complete = revs.get(pid, ([], False))
    d = dets.get(pid)
    note = [] if complete else ["评论超过 2×500 条上限，可能不全"]
    if d is None:
        note.append("商品详情页未取到（描述/规格缺）")
    save_json(os.path.join(DATA, "lowes", "products", f"{pid}.json"),
              {"状态": "完整" if complete else "部分", "备注": "；".join(note), "details": d or {},
               "reviews": [dict(x, 平台="Lowes", 入口=entry, 商品ID=pid) for x in rows]})
print("LOWES V2 DONE", flush=True)
