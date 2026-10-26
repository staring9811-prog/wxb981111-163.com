"""小试⑦：父体月销 ≥60 的门槛附近，商品分布长什么样；高价商品低于 60 件也可能达到月 GMV 门槛。"""
import pandas as pd, numpy as np
par = pd.read_csv('sku_parent.csv', low_memory=False)
par['pf'] = pd.to_numeric(par['父体月销量预测'], errors='coerce')
x = par[(par['目标月份'] == 202606) & par.pf.notna()].drop_duplicates('核验父ASIN')
bins = [60, 70, 80, 90, 100, 120, 150, 200, 300, 1000]
print('2026-06 父体月销分布（件/月）:')
print(pd.cut(x.pf, bins, right=False).value_counts().sort_index().to_string())
df = pd.read_csv('sku.csv', low_memory=False)
b = df[df.includeInBathroomAnalysis == True].drop_duplicates('子ASIN')
price = pd.to_numeric(b['商品价格'], errors='coerce')
thr = 200000 / 6 / 60
print(f'\n月 GMV 门槛 $33,333 ÷ 60 件 = ${thr:,.0f}；价格高于此的子体占比: {(price > thr).mean():.0%}（n={price.notna().sum()}）')
