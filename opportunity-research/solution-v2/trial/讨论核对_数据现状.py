"""两段新讨论（2026-10-28 7:25、7:27）的数据现状核对：标签已知比例、评分和价格是不是逐月值、新品批次与上架前可用数据、按"尺寸 × 材质"回测时每格有多少新品。
用法：TRIAL_DUMP=<放 df.pkl 的目录> python3 -I 讨论核对_数据现状.py"""
import os, sys, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 方法页_共用 import S, Q15, band
UNK = ['待图片核验', '信息不足', '未知', '待核实', 'nan', '']
q = pd.read_pickle(Q15); q = q[q['纳入浴室柜分析']]
d = pd.read_pickle(S + '/df.pkl').dropna(subset=['核验父ASIN'])
print('1. 标签已知比例（子体去重）')
for t in ['D5元素', 'D8台面材质', 'D8台盆材质', 'D7柜体材质', 'D6柜体颜色']:
    k1 = ~q.drop_duplicates('子ASIN')[t].astype(str).isin(UNK); k2 = ~d.drop_duplicates('子ASIN')[t].astype(str).isin(UNK)
    print(f'   {t}：1–5 月 {k1.mean():.0%}，6–9 月 {k2.mean():.0%}')
print('2. 评分、价格是不是逐月值（出现在 ≥2 个月的子体里，各月取值不同的比例）')
for df, mcol, cols, name in [(q, '目标月份', ['评分', '商品价格'], '1–5 月'), (d, '月', ['商品评分', '商品价格'], '6–9 月')]:
    multi = df.groupby('子ASIN')[mcol].nunique()
    for c in cols:
        g = df.dropna(subset=[c]).groupby('子ASIN')[c].nunique(); k = g[multi.reindex(g.index) >= 2]
        print(f'   {name} {c}：{(k > 1).mean():.0%}（{len(k)} 个子体）')
a = pd.DataFrame({'m': q['目标月份'], 'p': q['核验父ASIN'], 'ps': q['父体月销量'].astype(float), 'bsr': pd.to_numeric(q['小类BSR'], errors='coerce'), 'up': pd.to_datetime(q['上架日期'], errors='coerce'),
                  'w': q['D9宽(in)'], '台盆材质': q['D8台盆材质'], '台面材质': q['D8台面材质']})
v = pd.DataFrame({'m': d['月'].str[:4] + '-' + d['月'].str[4:], 'p': d['核验父ASIN'], 'ps': d['父体月销量预测'].astype(float), 'bsr': d['BSR'], 'up': pd.to_datetime(d['上架日期'], errors='coerce'),
                  'w': d['D9宽(in)'], '台盆材质': d['D8台盆材质'], '台面材质': d['D8台面材质']})
x = pd.concat([a, v], ignore_index=True)
x['lm'] = x.p.map(x.groupby('p')['up'].min()).dt.to_period('M')
x['age'] = (pd.PeriodIndex(x.m, freq='M') - x.lm).map(lambda z: z.n + 1 if pd.notna(z) else np.nan)
new = x[(x.lm >= pd.Period('2026-01', 'M')) & (x.lm <= pd.Period('2026-07', 'M')) & x.age.between(1, 3) & (x.groupby(['m', 'p'])['ps'].transform('first') >= 60)]
o = new.groupby('p').agg(lm=('lm', 'first'), best=('bsr', 'min')); o['成功'] = o.best <= 50
t = o.groupby('lm').agg(新品=('best', 'size'), 到过前50=('成功', 'sum'))
t['上架前商品数据月数'] = [max(0, (p - pd.Period('2026-01', 'M')).n) for p in t.index]
t['上架前关键词数据月数'] = [(p - pd.Period('2024-10', 'M')).n for p in t.index]
print('3. 新品批次（父体口径粗算：上架 2026-01 至 07、3 个月内进过表；成功 = 3 个月内家族 BSR ≤ 50）'); print(t.to_string())
print(f'   合计 {int(t.新品.sum())} 个、成功 {int(t.到过前50.sum())} 个；上架前有 ≥3 个月商品数据的（4–7 月上架）{int(t.loc[t.上架前商品数据月数 >= 3, "新品"].sum())} 个、成功 {int(t.loc[t.上架前商品数据月数 >= 3, "到过前50"].sum())} 个')
print('4. 用 1–3 月看格子、4–7 月上架的新品验证：每格有多少新品')
g0 = new[new.lm >= pd.Period('2026-04', 'M')].assign(尺寸=lambda z: z.w.map(band)).dropna(subset=['尺寸'])
for col in ['台盆材质', '台面材质']:
    g = g0[~g0[col].astype(str).isin(UNK)]; cell = g.groupby(['尺寸', col])['p'].nunique()
    print(f'   尺寸 × {col}：{len(cell)} 格，每格新品中位 {int(cell.median())}，≥5 个的 {int((cell >= 5).sum())} 格，≥10 个的 {int((cell >= 10).sum())} 格；材质已知的新品 {g.p.nunique()} 个')
