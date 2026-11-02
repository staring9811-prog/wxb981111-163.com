"""Fill Wayfair products marked 部分 with Apify reviews (abotapi/wayfair-scraper)."""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from vanity_crawler import apify_reviews
from vanity_crawler.common import load_json, save_json, DATA

todo = {}
for e in ["Wayfair主类目", "Wayfair无台面类目"]:
    for r in load_json(os.path.join(DATA, "wayfair", f"list_{e}.json"))["rows"]:
        if not r.get("排名"):
            continue
        p = load_json(os.path.join(DATA, "wayfair", "products", f"{r['sku']}.json")) or {}
        if p.get("状态") != "完整":
            todo[r["sku"]] = r["商品链接"]
print("to fill", len(todo), flush=True)
res = apify_reviews.wayfair_reviews(todo)
for sku, (rows, complete, n) in res.items():
    f = os.path.join(DATA, "wayfair", "products", f"{sku}.json")
    p = load_json(f) or {"details": {}}
    p["reviews_page"] = p.get("reviews", [])
    p["reviews"] = rows
    p["状态"] = "完整" if complete else "部分"
    p["备注"] = f"评论由 Apify 补全（按最新排序取 {n} 条）" + ("" if complete else "，达到1000条上限仍在2026年内")
    save_json(f, p)
print("done", sum(1 for v in res.values() if v[1]), "complete of", len(res), flush=True)
