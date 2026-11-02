"""Full run for a BD platform (lowes | wayfair): lists, then per-product details + reviews. Resumable.

usage: python3 run_bd.py lowes|wayfair [product_workers]
"""
import sys, os, time, json
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(__file__))
from vanity_crawler import lowes, wayfair, bd

plat = sys.argv[1]
workers = int(sys.argv[2]) if len(sys.argv) > 2 else 6
mod = {"lowes": lowes, "wayfair": wayfair}[plat]


def ledger():
    try:
        return json.load(open(bd.LEDGER)).get(plat, 0)
    except Exception:
        return 0


for entry in mod.ENTRIES:
    t = time.time()
    rows = mod.collect_list(entry)
    inc = [r for r in rows if r.get("排名")]
    print(entry, "list rows", len(rows), "included", len(inc), f"{time.time()-t:.0f}s", "BD req", ledger(), flush=True)

    def work(r):
        t0 = time.time()
        try:
            o = mod.collect_product(entry, r)
            print(entry, r["排名"], r["商品ID"], o["状态"], len(o["reviews"]), o.get("备注", "")[:60],
                  f"{time.time()-t0:.0f}s", "BD req", ledger(), flush=True)
        except bd.BudgetExceeded as e:
            print("BUDGET STOP", e, flush=True)
        except Exception as e:
            print(entry, r["排名"], r["商品ID"], "ERROR", repr(e)[:200], flush=True)

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(work, inc))
print(plat.upper(), "DONE", "BD req", ledger(), flush=True)
