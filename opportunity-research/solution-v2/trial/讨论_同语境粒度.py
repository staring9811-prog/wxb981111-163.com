"""同语境切到多细还有得比：2026-01 至 09 每月的家族，按尺寸段 → 加整装/拆装 → 加形态 → 加台盆位置 → 加价档 → 加台面材质 → 加柜体材质 → 加元素逐层切。
单位 = 月 × 家族 × 尺寸段（一个家族有几个尺寸就算几份）。看每层：标签齐全的占多少销量；格子里同月有 ≥ 5 个家族可比的，占多少销量；格子家族数中位。
用法：TRIAL_DUMP=<放 df.pkl 的目录> python3 -I 讨论_同语境粒度.py"""
import os, sys, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 方法页_共用 import S, Q15, band
TAGS = {'D2安装方式': '装', 'D1产品形态': '形态', 'D4台面形态': '台盆位置', 'D8台面材质': '台面材质', 'D7柜体材质': '柜体材质', 'D5元素': '元素'}
q = pd.read_pickle(Q15); q = q[q['纳入浴室柜分析']]
a = q.assign(m=q['目标月份'], p=q['核验父ASIN'], c=pd.to_numeric(q['子体月销量（父体全分给导出子体）'], errors='coerce'), price=pd.to_numeric(q['商品价格'], errors='coerce'))
d = pd.read_pickle(S + '/df.pkl').dropna(subset=['核验父ASIN'])
v = d.assign(m=d['月'].str[:4] + '-' + d['月'].str[4:], p=d['核验父ASIN'], c=pd.to_numeric(d['最终SKU月销量估算'], errors='coerce'), price=pd.to_numeric(d['商品价格'], errors='coerce'))
cols = ['m', 'p', 'c', 'price', 'D9宽(in)'] + list(TAGS)
x = pd.concat([a[cols], v[cols]], ignore_index=True).rename(columns=TAGS)
x['尺寸段'] = x['D9宽(in)'].map(band)
UNK = {'信息不足', '待图片核验', '未知', '待核实', '未提及', 'nan', ''}
for c in TAGS.values():
    x[c] = x[c].astype(object).where(x[c].notna(), None).map(lambda s: None if s is None or str(s) in UNK else str(s))
def tier(g):
    lo, hi = g.quantile([1 / 3, 2 / 3]); return pd.Series(np.where(g.isna(), None, np.where(g <= lo, '低', np.where(g <= hi, '中', '高'))), index=g.index)
x['价档'] = x.groupby(['m', '尺寸段'])['price'].transform(tier)
x = x.dropna(subset=['尺寸段'])
LEVELS = ['尺寸段', '装', '形态', '台盆位置', '价档', '台面材质', '柜体材质', '元素']
tot = x['c'].sum(); out = []
for i in range(1, len(LEVELS) + 1):
    keys = LEVELS[:i]
    k = x.dropna(subset=keys)
    u = k.groupby(['m', 'p'] + keys, dropna=False)['c'].sum().reset_index()   # 月 × 家族 × 格子
    n = u.groupby(['m'] + keys)['p'].transform('nunique')
    cell = u.groupby(['m'] + keys)['p'].nunique()
    out.append((' + '.join(keys[1:]) or '只按尺寸段', f'{k.c.sum() / tot:.0%}', f'{u.loc[n >= 5, "c"].sum() / tot:.0%}', int(cell.median()), int(len(cell) / x.m.nunique())))
print(pd.DataFrame(out, columns=['在尺寸段上再加', '标签齐全的销量占比', '同月 ≥ 5 个家族可比的销量占比', '格子家族数中位', '每月格子数']).to_string(index=False))
