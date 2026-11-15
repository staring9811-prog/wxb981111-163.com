"""小试④：上架日期口径体检——是子体口径还是父体口径？和首次评分日期是否矛盾？"""
import pandas as pd, numpy as np
df = pd.read_csv('sku.csv', low_memory=False)
b = df[df.includeInBathroomAnalysis == True].copy()
b['launch'] = pd.to_datetime(b['上架日期'], errors='coerce')
b['first_rating'] = pd.to_datetime(b['首次评分日期'], errors='coerce')
fam = b.groupby(['目标月份', '核验父ASIN']).agg(n_child=('子ASIN', 'nunique'), n_dates=('launch', lambda s: s.dt.normalize().nunique()),
                                            span=('launch', lambda s: (s.max() - s.min()).days if s.notna().any() else np.nan))
multi = fam[fam.n_child > 1]
print(f'多子体家族-月 {len(multi)}：上架日期全相同 {(multi.n_dates == 1).mean():.0%}；不同 {(multi.n_dates > 1).mean():.0%}；跨度>180天 {int((multi.span > 180).sum())}')
u = b.drop_duplicates('子ASIN')
both = u[u.launch.notna() & u.first_rating.notna()]
gap = (both.first_rating - both.launch).dt.days
print(f'有两种日期的子体 {len(both)}：首次评分早于上架>7天 {(gap < -7).mean():.0%}；上架后0–90天内首评 {((gap >= -7) & (gap <= 90)).mean():.0%}；上架>365天后才首评 {(gap > 365).mean():.0%}')
