"""小试③：成功线标定——类目 BSR 前 50 对应多少月销与月 GMV。
父体层：同月父体取子体中最优（最小）小类 BSR；月 GMV = Σ子体分摊销量 × 当前快照价格（价格非历史值）。"""
import pandas as pd
df = pd.read_csv('sku.csv', low_memory=False)
b = df[df.includeInBathroomAnalysis == True].copy()
for c, src in [('bsr', '目标月校验小类BSR'), ('pf', '父体月销量预测'), ('price', '商品价格'), ('units', '最终SKU月销量估算')]:
    b[c] = pd.to_numeric(b[src], errors='coerce')
b['gmv'] = b['units'] * b['price']
par = b.groupby(['目标月份', '核验父ASIN']).agg(bsr=('bsr', 'min'), pf=('pf', 'first'), gmv=('gmv', 'sum')).reset_index()
par = par[par.bsr.notna()]
for lo, hi in [(1, 10), (11, 30), (31, 50), (51, 100), (101, 200), (201, 500)]:
    g = par[(par.bsr >= lo) & (par.bsr <= hi)]
    print(f'BSR {lo}-{hi}: n={len(g)} 父体月销中位={g.pf.median():.0f} (P25 {g.pf.quantile(.25):.0f}–P75 {g.pf.quantile(.75):.0f}) 月GMV中位=${g.gmv.median():,.0f}')
