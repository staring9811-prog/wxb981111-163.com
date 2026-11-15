"""小试⑧：2026 年上架的新品（父体近似 SPU），在 6–9 月数据里按成功档位的分布。"""
import pandas as pd, numpy as np
df = pd.read_csv('sku.csv', low_memory=False)
b = df[df.includeInBathroomAnalysis == True].copy()
b['launch'] = pd.to_datetime(b['上架日期'], errors='coerce')
b['units'] = pd.to_numeric(b['最终SKU月销量估算'], errors='coerce')
b['price'] = pd.to_numeric(b['商品价格'], errors='coerce')
b['bsr'] = pd.to_numeric(b['目标月校验小类BSR'], errors='coerce')
b['gmv'] = b['units'] * b['price']
pm = b.groupby(['核验父ASIN', '目标月份']).agg(gmv=('gmv', 'sum'), bsr=('bsr', 'min')).reset_index()
fam = pm.groupby('核验父ASIN').agg(max_gmv=('gmv', 'max'), best_bsr=('bsr', 'min'))
fam['launch'] = b.groupby('核验父ASIN')['launch'].min()
new = fam[fam.launch >= '2026-01-01']
def tier(r):
    if r.best_bsr <= 50 or r.max_gmv >= 200000: return 'A 成功线（BSR≤50 或月≥$20万）'
    if r.max_gmv >= 100000: return 'B 月≥$10万但未进前50'
    return 'C 月销≥60件但未达成功线'
print('2026 年上架、在 6–9 月表中的父体:', len(new))
print(new.apply(tier, axis=1).value_counts().sort_index().to_string())
print('\n全体父体×月：BSR 31–50 档月 GMV 中位约 $4.3 万；月≥$10 万的父体×月占比:', round((pm.gmv >= 100000).mean(), 3))
