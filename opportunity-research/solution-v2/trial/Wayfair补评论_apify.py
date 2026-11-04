"""Wayfair 补逐月评论（Apify abotapi/wayfair-scraper），给"只有评论总数"的 listing 补 2026-01 至 10 逐月 VP / 非VP。
复用 tools/评论月度VP追踪器/reviewkit 的 Wayfair 评论抓取（三轮 100 / 300 / 1000 条、断点续跑、费用台账）。
密钥：不在代码里。云环境由代理在请求 api.apify.com 时注入（APIFY_TOKEN 只需给占位值）；本机按追踪器的 secrets.json。
用法：python3 Wayfair补评论_apify.py <清单.csv：pid,url> [预算美元，默认 5]
输出（不入库）：input/data_v2/渠道关键词/大词/wayfair_apify/ 缓存与 Wayfair补评论_月度.csv（pid, 月, VP, 非VP, 合计, 状态）。"""
import csv, os, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools', '评论月度VP追踪器'))
os.environ.setdefault('APIFY_TOKEN', 'proxy-injected')
from reviewkit.common import Ctx  # noqa: E402
from reviewkit import wayfair  # noqa: E402

src, budget = sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
OUT = os.path.join(ROOT, 'input/data_v2/渠道关键词/大词/wayfair_apify')
os.makedirs(OUT, exist_ok=True)
rows = [{'id': r['pid'], 'url': r['url']} for r in csv.DictReader(open(src, encoding='utf-8-sig')) if r.get('url')]
cfg = {'name': 'wayfair补评论', 'window': {'start': '2026-01-01', 'full_end': '2026-10-31'}, 'budget': {'apify_wayfair_usd': budget}}
ctx = Ctx(cfg, data_dir=OUT)
res = wayfair.reviews_batch(ctx, rows, batch=10, parallel=2)

with open(os.path.join(OUT, 'Wayfair补评论_月度.csv'), 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f); w.writerow(['pid', '月', 'VP', '非VP', '合计', '状态', '说明'])
    for pid, (revs, status, note, _) in res.items():
        vp, nv = Counter(), Counter()
        for x in revs:
            m = x['评论日期'][:7]
            (vp if x['VP状态'] == 'VP' else nv)[m] += 1
        months = sorted(set(vp) | set(nv)) or ['']
        for m in months:
            w.writerow([pid, m, vp[m], nv[m], vp[m] + nv[m], status, note])
print('完成', len(res), '个；状态', dict(Counter(v[1] for v in res.values())))
