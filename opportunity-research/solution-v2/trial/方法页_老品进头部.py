"""方法页第 2 题：1–9 月到过家族 BSR ≤ 50 的家族，按上架时间和是否 2026 年中途才进表分类（检验"老品因为需求出现突然好卖"）。家族 = 共享子体的父体串成一个。
用法：TRIAL_DUMP=<放 df.pkl 的目录> python3 -I 方法页_老品进头部.py"""
import os, sys, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 方法页_共用 import rows
x = rows(); x = x[x.groupby(['m', 'p'])['ps'].transform('first') >= 60]
# 用子体把同一家族跨月串起来（并查集：共享子体的父体算一个家族）
up = {p: p for p in x.p.unique()}
def root(z):
    while up[z] != z: up[z] = up[up[z]]; z = up[z]
    return z
for ps in x.groupby('k')['p'].unique():
    for o in ps[1:]: up[root(o)] = root(ps[0])
x['f'] = x.p.map(root)
fm = x.groupby(['f', 'm']).agg(ps=('ps', 'max'), bsr=('bsr', 'min')).reset_index()
info = x.groupby('f').agg(up=('up', 'min'), brand=('brand', 'first'))
ms = sorted(x.m.unique())
top = fm[fm.bsr <= 50].groupby('f')['m'].min().rename('首次前50')
t = info.join(top, how='inner')
first = fm.groupby('f')['m'].min(); t['首次进表'] = first
t['上架'] = np.select([t.up < '2024-01-01', t.up < '2025-01-01', t.up < '2026-01-01'], ['2023 年及以前', '2024 年', '2025 年'], '2026 年')
t['进表'] = np.where(t.首次进表 == ms[0], '1 月就在表里', '2026 年中途才进表')
print('到过家族 BSR ≤ 50 的家族', len(t))
print(pd.crosstab(t.上架, t.进表, margins=True))
old_mid = t[(t.上架.isin(['2023 年及以前', '2024 年'])) & (t.进表 == '2026 年中途才进表')]
print('\n上架满一年以上、2026 年中途才进表、后来进前 50：'); print(old_mid[['brand', 'up', '首次进表', '首次前50']].to_string())
# 这些老家族进表前后的月份：首次进表月销量与之后最高
for f in old_mid.index:
    g = fm[fm.f == f].set_index('m')
    print(f, info.loc[f, 'brand'], ' '.join(f"{m[5:]}:{int(r.ps)}/{'' if pd.isna(r.bsr) else int(r.bsr)}" for m, r in g.iterrows()))
