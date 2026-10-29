"""卖家精灵按月导出（product_research，展开全部子体）逐月核对。
用法：python3 -I 导出核对.py <月度 JSON 文件> [...]（文件放 input/data_v2/sellersprite_monthly/，不入库）
看：行数与父体数；销量 units 是不是父体数（同一父体的子体是否相同）；导出的子体数占变体数多少；
各字段缺失；能读出尺寸的比例（SKU、标题、尺寸字段）；有没有浴室柜小类排名；子体自己的销量（亚马逊"上月已购"标）有多少。"""
import json, re, sys, collections, statistics as st

def width(r):
    m = re.search(r'Size:\s*([0-9]{2}(?:\.\d+)?)\s*(?:"|”|in|inch|-inch)?', r.get('sku') or '', re.I) or \
        re.search(r'\b([0-9]{2}(?:\.\d+)?)\s*(?:"|”|-?inch|in\b)', r.get('title') or '', re.I)
    if m: return float(m.group(1))
    d = re.findall(r'([0-9]+(?:\.\d+)?)', r.get('dimension') or '')
    return float(d[1]) if len(d) == 3 else None   # 尺寸字段是 深 x 宽 x 高

for f in sys.argv[1:]:
    j = json.load(open(f, encoding='utf-8')); it = j['items']
    by = collections.defaultdict(list)
    for r in it: by[r['parent']].append(r)
    multi = [v for v in by.values() if len(v) > 1]
    spread = [max(r['units'] for r in v) / max(min(r['units'] for r in v), 1) for v in multi]
    cov = [len(v) / max(v[0].get('variations') or 1, 1) for v in by.values()]
    fam_units = [max(r['units'] for r in v) for v in by.values()]
    print(f"== {j['month']}  完整={j.get('complete')}  行 {len(it)}  父体 {len(by)}  筛选 {j['filters'].get('minUnits')} 件 / {j['filters'].get('minPrice')} 美金 / variation={j['filters'].get('variation')}")
    print(f"  销量 units：多行父体里同父体各子体最大÷最小 中位 {st.median(spread):.2f}（≈1 说明是父体销量，算时按父体去重）；父体月销 中位 {st.median(fam_units):.0f}，合计 {sum(fam_units):,}")
    print(f"  导出子体数 ÷ 变体数：中位 {st.median(cov):.2f}，全部导出的父体 {sum(c >= 1 for c in cov)}/{len(cov)}")
    miss = {k: sum(1 for r in it if r.get(k) in ((None, '') if k == 'ratingsCv' else (None, '', 0, -1))) for k in ['parent', 'units', 'price', 'rating', 'ratings', 'ratingsCv', 'availableDate', 'variations', 'sku', 'dimension', 'imageUrl', 'title', 'brand']}  # 评分数月变化为 0 是正常值
    print('  字段缺失（行）：', {k: v for k, v in miss.items() if v})
    print(f"  读得出宽度 {sum(width(r) is not None for r in it) / len(it):.0%}；有浴室柜小类排名 {sum(any(s.get('code') == '6810202011' for s in (r.get('subcategories') or [])) for r in it) / len(it):.0%}；"
          f"子体自带'上月已购'标 {sum(1 for r in it if r.get('amzUnit')) / len(it):.0%}")

# ---- 多个月一起给时：跨月核对 ----
if len(sys.argv) > 2:
    import pandas as pd
    rows = []
    for f in sys.argv[1:]:
        j = json.load(open(f, encoding='utf-8'))
        for r in j['items']:
            sub = next((s.get('rank') for s in (r.get('subcategories') or []) if s.get('code') == '6810202011'), None)
            rows.append((j['month'], r['asin'], r['parent'], r['units'], r['price'], r.get('ratings'), sub, r.get('availableDate')))
    x = pd.DataFrame(rows, columns=['m', 'asin', 'p', 'units', 'price', 'ratings', 'sub', 'up'])
    multi = x.groupby('asin').filter(lambda g: g.m.nunique() > 1)
    print('\n== 跨月')
    print(f"  出现在 2 个月以上的子体 {multi.asin.nunique()}：价格各月不全相同的 {(multi.groupby('asin').price.nunique() > 1).mean():.0%}，"
          f"评分数各月不全相同的 {(multi.groupby('asin').ratings.nunique() > 1).mean():.0%}，小类排名各月不全相同的 {(multi.groupby('asin')['sub'].nunique() > 1).mean():.0%}")
    s = multi.sort_values('m').groupby('asin').ratings.apply(lambda v: v.dropna().is_monotonic_increasing)
    print(f"  评分数随月份不减少的子体 {s.mean():.0%}（是当月读数的话应接近 100%）")
    fam = x.groupby(['m', 'p']).units.max().reset_index()
    t = fam.groupby('m').agg(父体=('p', 'nunique'), 父体月销合计=('units', 'sum'))
    t['与上月重合的父体'] = [None] + [len(set(fam[fam.m == a].p) & set(fam[fam.m == b].p)) for a, b in zip(t.index[:-1], t.index[1:])]
    up = pd.to_datetime(x.groupby('p').up.min(), unit='ms', errors='coerce').dt.strftime('%Y%m')
    t['当月上架的父体'] = [int((up == m).sum()) for m in t.index]
    print(t.to_string())
