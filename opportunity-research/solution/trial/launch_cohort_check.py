"""小试⑥：6–9 月数据里按上架月份能看到多少新品，能否直接做回归。
SPU 近似为父 ASIN（家族最早子体上架日）；结果用"6–9 月任一月小类 BSR ≤ 50"。"""
import pandas as pd, numpy as np
df = pd.read_csv('sku.csv', low_memory=False)
b = df[df.includeInBathroomAnalysis == True].copy()
b['launch'] = pd.to_datetime(b['上架日期'], errors='coerce')
b['bsr'] = pd.to_numeric(b['目标月校验小类BSR'], errors='coerce')
b['pf'] = pd.to_numeric(b['父体月销量预测'], errors='coerce')
fam = b.groupby('核验父ASIN').agg(launch=('launch', 'min'), best_bsr=('bsr', 'min'), min_pf=('pf', 'min'), n_child=('子ASIN', 'nunique')).dropna(subset=['launch'])
fam['launch_m'] = fam['launch'].dt.to_period('M')
fam['top50'] = fam['best_bsr'] <= 50
recent = fam[(fam.launch_m >= pd.Period('2025-01', 'M')) & (fam.launch_m <= pd.Period('2026-09', 'M'))]
tab = recent.groupby('launch_m').agg(父体数=('top50', 'size'), 进前50=('top50', 'sum'))
print(tab.to_string())
print('\n2025-01 至 2026-06 上架、出现在 6–9 月头部清单的父体合计:', int(tab.loc[:'2026-06', '父体数'].sum()))
print('这些父体的父体月销量最小值（截断点）:', fam['min_pf'].min())
