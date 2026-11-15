"""卖家精灵选产品按月导出时，"价格 ≥ 90"会漏掉什么：用 2026-01 至 09 现有数据估（现有数据本身只含父体月销 ≥ 60 的家族，月销门槛的影响估不了）。
看三件事：价格 < 90 的子体占多少行、销量、金额（分尺寸段）；按子体筛价时会被拆开的家族（有的子体 ≥ 90、有的 < 90）有多少；
到过家族 BSR ≤ 50 的家族、1–7 月上架的新品里，有多少整家族或部分子体低于 90。
用法：TRIAL_DUMP=<放 df.pkl 的目录> python3 -I 导出筛选_门槛影响.py"""
import os, sys, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 方法页_共用 import S, Q15, band, ORDER
LINE = 90
q = pd.read_pickle(Q15); q = q[q['纳入浴室柜分析']]
a = pd.DataFrame({'m': q['目标月份'], 'p': q['核验父ASIN'], 'k': q['子ASIN'], 'ps': q['父体月销量'].astype(float), 'bsr': pd.to_numeric(q['小类BSR'], errors='coerce'),
                  'w': q['D9宽(in)'], 'c': pd.to_numeric(q['子体月销量（父体全分给导出子体）'], errors='coerce'), 'price': pd.to_numeric(q['商品价格'], errors='coerce'),
                  'up': pd.to_datetime(q['上架日期'], errors='coerce')})
d = pd.read_pickle(S + '/df.pkl').dropna(subset=['核验父ASIN'])
v = pd.DataFrame({'m': d['月'].str[:4] + '-' + d['月'].str[4:], 'p': d['核验父ASIN'], 'k': d['子ASIN'], 'ps': d['父体月销量预测'].astype(float), 'bsr': d['BSR'],
                  'w': d['D9宽(in)'], 'c': pd.to_numeric(d['最终SKU月销量估算'], errors='coerce'), 'price': pd.to_numeric(d['商品价格'], errors='coerce'),
                  'up': pd.to_datetime(d['上架日期'], errors='coerce')})
x = pd.concat([a, v], ignore_index=True)
x['段'] = x['w'].map(band).fillna('未知'); x['额'] = x['c'] * x['price']; x['低'] = x['price'] < LINE
print(f'子体×月 {len(x)} 行，家族×月 {x.groupby(["m", "p"]).ngroups} 个；价格缺失 {x.price.isna().mean():.1%} 的行')

print(f'\n1. 价格 < {LINE} 的子体占比（1–9 月合计）')
tot = pd.DataFrame({'行': x.groupby('段')['低'].mean(), '销量': x[x.低].groupby('段')['c'].sum() / x.groupby('段')['c'].sum(),
                    '金额': x[x.低].groupby('段')['额'].sum() / x.groupby('段')['额'].sum(), '该段销量占全品类': x.groupby('段')['c'].sum() / x['c'].sum()})
tot = tot.reindex([o for o in ORDER + ['未知'] if o in tot.index]).fillna(0)
tot.loc['全部'] = [x['低'].mean(), x.loc[x.低, 'c'].sum() / x['c'].sum(), x.loc[x.低, '额'].sum() / x['额'].sum(), 1.0]
print((tot * 100).round(1).astype(str).add('%').to_string())

fam = x.groupby(['m', 'p']).agg(ps=('ps', 'first'), best=('bsr', 'min'), n=('k', 'size'), 低=('低', 'sum'), 有价=('price', 'count'))
fam['类'] = np.where(fam.低 == 0, '全部 ≥ 90', np.where(fam.低 == fam.有价, '全部 < 90', '混合'))
print('\n2. 家族×月按子体价格分三类（个数、父体销量占比）')
g = fam.groupby('类').agg(个数=('ps', 'size'), 销量=('ps', 'sum')); g['销量占比'] = (g.销量 / g.销量.sum() * 100).round(1).astype(str) + '%'
print(g[['个数', '销量占比']].to_string())
mix = fam[fam.类 == '混合']
print(f'   混合家族里，按子体筛价会去掉的子体：平均每家 {mix.低.mean():.1f} 个（共 {mix.n.mean():.1f} 个）')

top = fam[fam.best <= 50]
print(f'\n3. 当月家族 BSR ≤ 50 的家族×月 {len(top)} 个：', top['类'].value_counts().to_dict())
up = x.groupby('p')['up'].min(); newp = up[(up >= '2026-01-01') & (up < '2026-08-01')].index
nf = fam[fam.index.get_level_values('p').isin(newp)]
by = nf.groupby(level='p').agg(best=('best', 'min'), 全低=('类', lambda s: (s == '全部 < 90').all()), 有混合=('类', lambda s: (s == '混合').any()))
print(f'   1–7 月上架的新品家族 {len(by)} 个（到过 BSR ≤ 50 的 {int((by.best <= 50).sum())} 个）：每月都全部 < 90 的 {int(by.全低.sum())} 个'
      f'（其中到过 BSR ≤ 50 的 {int((by.全低 & (by.best <= 50)).sum())} 个）；出现过混合的 {int(by.有混合.sum())} 个')

# 价格逐月会变：某个月整家族掉到 90 以下（如打折），按 90 筛就会在那个月断档
fam['整低'] = fam['类'] == '全部 < 90'
cross = fam.groupby(level='p')['整低'].agg(['any', 'all', 'size'])
gap = cross[cross['any'] & ~cross['all']]
gm = fam[fam.index.get_level_values('p').isin(gap.index)]
print(f'\n4. 有的月份整家族 < 90、有的月份 ≥ 90 的家族 {len(gap)} 个（按 90 筛会断档的月份共 {int(gm.整低.sum())} 个），'
      f'其中到过家族 BSR ≤ 50 的 {int((gm.groupby(level="p").best.min() <= 50).sum())} 个')
