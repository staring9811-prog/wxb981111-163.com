import sys, os, json, collections
sys.path.insert(0, os.path.dirname(__file__))
from vanity_crawler import lowes
entry = "Lowes带台面榜"
url = f'{lowes.ENTRIES[entry]}?sortMethod=sortBy_bestSellers&offset=0'
st, _ = lowes._get(url)
items = st.get("itemList") or []
print("LIST bestSellers offset0 items", len(items), "| query:", (st.get("requestParams") or {}).get("queryString","")[:300], flush=True)
for i, it in enumerate(items[:24]):
    p = it["product"]; print(i+1, p["omniItemId"], "SPONSORED" if p.get("sponsored") else "", p.get("rating"), p.get("reviewCount"), p["description"][:60])
p = items[0]["product"]
row = {"商品ID": p["omniItemId"], "商品链接": lowes.BASE + p["pdURL"]}
o = lowes.collect_product(entry, row)
rv = o["reviews"]
print("PRODUCT", row["商品ID"], o["状态"], o["备注"], "2026 reviews", len(rv))
print("VP", collections.Counter(r["VP状态"] for r in rv), "syndicated", collections.Counter(r["转载"] for r in rv))
print("months", sorted(collections.Counter(r["评论日期"][:7] for r in rv).items()))
print("details", {k: v[:100] for k, v in o["details"].items()})
for r in rv[:3]: print(json.dumps(r, ensure_ascii=False)[:400])
print("BD ledger", open(os.path.join(os.path.dirname(__file__),"data","bd_ledger.json")).read())
