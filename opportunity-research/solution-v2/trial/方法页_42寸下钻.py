"""方法页第 1 题"往下钻"示例：42″ 的关键词哪些在涨；7–9 月每月前 150 个家族里带 42″ 的家族是谁、什么价、什么款、卖了多少。
用法：TRIAL_DUMP=<放 df.pkl 的目录> python3 -I 方法页_42寸下钻.py"""
import os, sys, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 方法页_共用 import S, searches, band, top150, rows
B = os.environ.get('BAND', '42″')
cur, pre = ['2026-07', '2026-08', '2026-09'], ['2025-07', '2025-08', '2025-09']
k = searches(); w = k[k.band == B].pivot_table(index='kw', columns='m', values='s', aggfunc='sum')
t = pd.DataFrame({'7–9 月搜索': w[cur].sum(axis=1), '去年同期': w[pre].sum(axis=1)}); t['同比'] = t['7–9 月搜索'] / t['去年同期'] - 1
print(B, '关键词', len(t), '个；搜索量前 8：'); print(t.sort_values('7–9 月搜索', ascending=False).head(8).round(2).to_string())
d = pd.read_pickle(S + '/df.pkl').dropna(subset=['核验父ASIN'])
d['m'] = d['月'].str[:4] + '-' + d['月'].str[4:]; d['band'] = d['D9宽(in)'].map(band)
x = top150(rows()); keep = set(zip(x.m, x.p))
ink = np.array([(m, p) in keep for m, p in zip(d.m, d['核验父ASIN'])]); inm = d.m.isin(cur).values
g = d[ink & inm & (d.band == B).values]
def mode(s): return s.mode().iloc[0] if s.notna().any() else None
fam = g.groupby('核验父ASIN').agg(品牌=('品牌', 'first'), 月数=('m', 'nunique'), 子体=('子ASIN', 'nunique'), 价格中位=('价格', 'median'), 形态=('形态', mode),
                               台面材质=('台面材质', mode), 元素=('元素', mode), 该尺寸销量=('销量', 'sum'), 家族最好BSR=('BSR', 'min'))
print(f'\n7–9 月前 150 家族里带 {B} 的家族 {len(fam)} 个，价格 ≥ $900 的 {int((fam.价格中位 >= 900).sum())} 个')
print(fam.sort_values('该尺寸销量', ascending=False).round(0).to_string())
allp = d[ink & inm]
print('\n同期子体价格中位：全品类', round(allp['价格'].median()), ' ', B, round(g['价格'].median()), ' 36″', round(allp[allp.band == '36″']['价格'].median()), ' 48″', round(allp[allp.band == '48″']['价格'].median()))
