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
