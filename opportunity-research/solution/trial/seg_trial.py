"""小试②：用户现用指标在细分层面有没有区分度、稳不稳定。
细分 = 宽度档 × 产品形态（这两个字段覆盖最好）。
稳定性检验：6+7 月与 8+9 月分别计算，看细分排序是否一致（父体销量逐月独立，子体词数权重 6 用 7、8 用 9）。"""
import pandas as pd, numpy as np
from scipy.stats import spearmanr
df = pd.read_csv('sku.csv', low_memory=False)
b = df[df.includeInBathroomAnalysis == True].copy()
b['units'] = pd.to_numeric(b['最终SKU月销量估算'], errors='coerce')
b['price'] = pd.to_numeric(b['商品价格'], errors='coerce')
b['rating'] = pd.to_numeric(b['商品评分'], errors='coerce')
b['launch'] = pd.to_datetime(b['上架日期'], errors='coerce')
w = pd.to_numeric(b['D9宽(in)'], errors='coerce')
b['宽度档'] = pd.cut(w, [0, 21, 27, 33, 39, 45, 54, 66, 200], labels=['≤21','24','30','36','42','48','60','72+'])
form = b['D1产品形态'].astype(str).str.replace('（父体候选）', '')
b['形态'] = np.where(form.isin(['落地式', '悬浮式']), form, '未知')
b['seg'] = b['宽度档'].astype(str) + '|' + b['形态']
b['新品'] = b['launch'] >= '2025-06-01'          # 观察窗前 12 个月内上架
b['half'] = np.where(b['目标月份'].isin([202606, 202607]), 'H1', 'H2')
b = b[b.units.notna()]

def seg_metrics(x):
    g = x.groupby('seg')
    m = pd.DataFrame({
        'n_asin': g['子ASIN'].nunique(),
        'units': g['units'].sum(),
        '单位ASIN贡献': g['units'].sum() / g['子ASIN'].nunique(),
        '新品销量占比': g.apply(lambda d: d.loc[d['新品'], 'units'].sum() / d['units'].sum()),
        '销量加权价格': g.apply(lambda d: np.average(d['price'], weights=d['units']) if d['price'].notna().all() and d['units'].sum() > 0 else np.nan),
        '低分销量占比': g.apply(lambda d: d.loc[d['rating'] < 4.0, 'units'].sum() / d['units'].sum()),
        'Top3品牌份额': g.apply(lambda d: d.groupby('品牌')['units'].sum().nlargest(3).sum() / d['units'].sum()),
    })
    m['销量份额'] = m['units'] / m['units'].sum()
    return m

h1, h2 = seg_metrics(b[b.half == 'H1']), seg_metrics(b[b.half == 'H2'])
both = h1.join(h2, lsuffix='_H1', rsuffix='_H2', how='inner')
both = both[(both['n_asin_H1'] >= 20) & (both['n_asin_H2'] >= 20)]
print('细分数（两半年各 ≥20 个子 ASIN）:', len(both))
rows = []
for k in ['销量份额', '单位ASIN贡献', '新品销量占比', '销量加权价格', '低分销量占比', 'Top3品牌份额']:
    rho, p = spearmanr(both[k + '_H1'], both[k + '_H2'], nan_policy='omit')
    rows.append(dict(指标=k, 细分n=len(both), H1H2排序相关=round(rho, 2), p=round(p, 4),
                     细分间极差_H1=f"{both[k+'_H1'].min():.2f}–{both[k+'_H1'].max():.2f}"))
print(pd.DataFrame(rows).to_string(index=False))

full = seg_metrics(b)
full = full[full.n_asin >= 20].sort_values('销量份额', ascending=False)
pd.set_option('display.width', 200)
print('\n全窗口细分概览（销量为模型估算，仅头部≥60件/月父体）:')
print(full[['n_asin', '销量份额', '单位ASIN贡献', '新品销量占比', '销量加权价格', '低分销量占比', 'Top3品牌份额']].round(3).head(16).to_string())
print('\n整体：新品(2025-06后上架)销量占比', round(b.loc[b['新品'], 'units'].sum() / b['units'].sum(), 3))
