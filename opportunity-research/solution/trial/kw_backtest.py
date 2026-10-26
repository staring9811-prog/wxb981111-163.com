"""小试①：关键词趋势动量回测。
问题：某个词「前期同比上涨」，后期是否继续上涨？若是，关键词趋势可作领先信号。
前期同比 = 2025.10–2026.01 对 2024.10–2025.01；后期同比 = 2026.06–2026.09 对 2025.06–2025.09（同比去季节性，窗口不重叠）。"""
import pandas as pd, numpy as np
from scipy.stats import spearmanr
t = pd.read_csv('kw_trend.csv')
vol = t[[c for c in t.columns if c.endswith('月搜索量')]].apply(pd.to_numeric, errors='coerce')
vol.columns = [c.split('-')[0] for c in vol.columns]
vol.index = t['关键词']
def s(m): return vol[m].sum(axis=1)
early = s(['2025.10','2025.11','2025.12','2026.01']) / s(['2024.10','2024.11','2024.12','2025.01'])
late  = s(['2026.06','2026.07','2026.08','2026.09']) / s(['2025.06','2025.07','2025.08','2025.09'])
base = s(['2024.10','2024.11','2024.12','2025.01']) / 4
res = []
for lo in [0, 500, 2000]:
    m = (base >= lo) & np.isfinite(early) & np.isfinite(late) & (early > 0) & (late > 0)
    rho, p = spearmanr(np.log(early[m]), np.log(late[m]))
    # 前期涨幅前 1/3 的词，后期跑赢中位数的比例
    e, l = early[m], late[m]
    top = e >= e.quantile(2/3); bot = e <= e.quantile(1/3)
    hit_top = (l[top] > l.median()).mean(); hit_bot = (l[bot] > l.median()).mean()
    res.append(dict(基期月均搜索量下限=lo, n=int(m.sum()), spearman=round(rho,3), p=round(p,4),
                    前期涨幅前三分之一_后期跑赢中位数=round(hit_top,2), 前期涨幅后三分之一_后期跑赢中位数=round(hit_bot,2)))
print(pd.DataFrame(res).to_string(index=False))
tot = vol.sum()
print('\n品类总搜索量同比：前期', round(tot[['2025.10','2025.11','2025.12','2026.01']].sum()/tot[['2024.10','2024.11','2024.12','2025.01']].sum()-1,3),
      '后期', round(tot[['2026.06','2026.07','2026.08','2026.09']].sum()/tot[['2025.06','2025.07','2025.08','2025.09']].sum()-1,3))
