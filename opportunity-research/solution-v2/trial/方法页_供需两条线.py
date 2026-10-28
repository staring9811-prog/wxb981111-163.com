"""方法页第 1 题：各尺寸段需求线（搜索份额）与供给线（在卖子体份额，每月前 150 个家族），4–6 月 → 7–9 月；空间 = 需求线 ÷ 供给线；鸿沟 = 成交份额 ÷ 搜索份额（7–9 月）。
用法：TRIAL_DUMP=<放 df.pkl 的目录> python3 -I 方法页_供需两条线.py"""
import os, sys, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 方法页_共用 import rows, top150, searches, band, ORDER
k = searches().dropna(subset=['band']); ks = k.pivot_table(index='m', columns='band', values='s', aggfunc='sum')
x = top150(rows()); x['band'] = x.w.map(band); x = x.dropna(subset=['band'])
x['新进入'] = x.p.map(x.groupby('p')['up'].min()) >= pd.to_datetime(x.m + '-01') - pd.DateOffset(months=3)
W = {'4–6 月': ['2026-04', '2026-05', '2026-06'], '7–9 月': ['2026-07', '2026-08', '2026-09']}
t = {}
for wn, mm in W.items():
    s = ks.loc[mm].sum(); s = s / s.sum()
    g = x[x.m.isin(mm)].groupby('band').agg(子体=('k', 'size'), 新=('新进入', 'sum'), 成交=('c', 'sum'))
    n = g.子体 / g.子体.sum()
    t[wn] = pd.DataFrame({'搜索份额': s, '在卖子体份额': n, '空间': s / n, '新进入子体占比': g.新 / g.子体, '成交份额': g.成交 / g.成交.sum()})
a, b = t['4–6 月'].loc[ORDER], t['7–9 月'].loc[ORDER]
out = pd.DataFrame({'空间 4–6 月': a.空间, '空间 7–9 月': b.空间, '需求线': b.搜索份额 / a.搜索份额 - 1, '供给线': b.在卖子体份额 / a.在卖子体份额 - 1,
                    '空间速度': b.空间 / a.空间 - 1, '鸿沟（成交÷搜索）': b.成交份额 / b.搜索份额, '新进入子体占比 7–9 月': b.新进入子体占比})
pd.set_option('display.width', 200); print(out.round(3).to_string())
