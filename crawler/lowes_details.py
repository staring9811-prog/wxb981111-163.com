"""Fetch Lowe's product detail pages (description/specs) via BD for all ranked products. Resumable."""
import sys, os, runpy
sys.path.insert(0, os.path.dirname(__file__))
from concurrent.futures import ThreadPoolExecutor
from vanity_crawler import lowes
from vanity_crawler.common import load_json, DATA
src = open(os.path.join(os.path.dirname(__file__), "run_lowes2.py")).read()
ns = {"__file__": os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_lowes2.py")}
exec(src.split("rows_all = []")[0], ns)  # load details() without running the pipeline
rows = []
for e in lowes.ENTRIES:
    rows += [r for r in load_json(os.path.join(DATA, "lowes", f"list_{e}.json"))["rows"] if r.get("排名")]
with ThreadPoolExecutor(6) as ex:
    got = list(ex.map(ns["details"], rows))
print("details ok", sum(g is not None for g in got), "of", len(rows), flush=True)
