"""Full HDP run: lists for both entries, then reviews/details per product. Resumable."""
import sys, os, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(__file__))
from vanity_crawler import hdp

for entry in hdp.ENTRIES:
    rows = hdp.collect_list(entry)
    inc = [r for r in rows if r.get("排名")]
    print(entry, "list rows", len(rows), "included", len(inc), flush=True)

    def work(r):
        t = time.time()
        o = hdp.collect_product(entry, r)
        print(entry, r["排名"], r["商品ID"], o["状态"], len(o["reviews"]), f"{time.time()-t:.0f}s", flush=True)

    with ThreadPoolExecutor(3) as ex:
        list(ex.map(work, inc))
print("HDP DONE", flush=True)
