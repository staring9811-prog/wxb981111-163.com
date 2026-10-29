"""wen 的"岗石"案例：vanity 市场分析 · 两个大机会方向 · 机会方向 2"将带台面盆配件以同价设计到现有产品形态中"（约 2025-11 写成，用 2025-09 数据）。
按 wen 的口径重做：30″、36″ 里按 50 美金一档的价格段，比"带石材台面"（台面材质为岗石、石英石、卡拉拉大理石、岩板、Cultured Marble）和不带的。
看 2026 年：各价格段带台面的子体占比、销量占比、单位 ASIN 贡献、评分；IRONCK B0FJD7VNS5 后来怎样；2025-09 以后上架的带台面新品有没有起来。
台面材质有一半是"信息不足"，占比只在有台面材质标签的子体里算。
用法：TRIAL_DUMP=<放 df.pkl 的目录> python3 -I 模拟_台面案例.py"""
import os, sys, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 方法页_共用 import tagged
pd.set_option('display.width', 250)
STONE = {'岗石', '石英石', '卡拉拉大理石', '岩板', 'Cultured Marble'}
BINS = [0, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650, np.inf]
LABELS = ['100以下', '100-150', '150-200', '200-250', '250-300', '300-350', '350-400', '400-450', '450-500', '500-550', '550-600', '600-650', '650以上']

x = tagged()
x = x[x['尺寸段'].isin(['30″', '36″'])].copy()
x['带台面'] = x['台面材质'].map(lambda v: np.nan if pd.isna(v) else v in STONE)
x['rt'] = x['rt'].where(x['rt'] > 0)  # 0 分是还没有评分
x['价格段'] = pd.cut(x.price, BINS, right=False, labels=LABELS)
x['季'] = x.m.map(lambda m: f'{m[:4]}Q{(int(m[5:]) - 1) // 3 + 1}')
k = x.dropna(subset=['带台面']).copy(); k['带台面'] = k['带台面'].astype(bool)
print(f'30″/36″ 子体×月 {len(x)} 行，台面材质有标签的 {len(k) / len(x):.0%}')

def wavg(g, col):
    g = g.dropna(subset=[col]); return np.average(g[col], weights=g.c + 1e-9) if len(g) else np.nan

print('\n1. 各价格段带石材台面的：子体占比、销量占比、单位 ASIN 贡献（= 销量占比 ÷ 子体占比）、评分（按件数加权）与不带的比')
for qq, g in k.groupby('季'):
    t = g.groupby(['价格段', '带台面'], observed=True).agg(子体=('k', 'nunique'), 销量=('c', 'sum')).unstack('带台面').fillna(0)
    out = pd.DataFrame({'带台面子体': t[('子体', True)].astype(int), '子体占比': t[('子体', True)] / t['子体'].sum(axis=1),
                        '销量占比': t[('销量', True)] / t['销量'].sum(axis=1)})
    out['单位ASIN贡献'] = out.销量占比 / out.子体占比
    out['评分(带)'] = g[g.带台面].groupby('价格段', observed=True).apply(lambda z: wavg(z, 'rt'))
    out['评分(不带)'] = g[~g.带台面].groupby('价格段', observed=True).apply(lambda z: wavg(z, 'rt'))
    print(f'\n{qq}'); print(out.round(2).to_string())

print('\n2. IRONCK B0FJD7VNS5（wen 的标杆）在 2026 年')
b = tagged(); print('  全部尺寸里 IRONCK 品牌的子体×月：', int((b.brand.astype(str).str.upper() == 'IRONCK').sum()))
r = x[(x.k == 'B0FJD7VNS5') | (x.p == 'B0FJD7VNS5')]
fam = r.p.unique()
print('  所在家族', list(fam))
print(x[x.p.isin(fam) & (x.k == 'B0FJD7VNS5')][['m', 'price', 'rt', 'c', 'fbsr', '台面材质', '元素']].to_string(index=False) if len(r) else '  2026 年数据里没有')
if len(fam): print('  家族每月最好 BSR', x[x.p.isin(fam)].groupby('m').fbsr.min().to_dict())

print('\n3. 2025-09 以后上架、30″/36″、价格 250–450 的带石材台面家族')
n = k[k.带台面 & (k.p.map(x.groupby('p').up.min()) >= '2025-09-01') & k.price.between(250, 450)]
s = n.groupby('p').agg(品牌=('brand', 'first'), 上架=('up', 'min'), 尺寸=('尺寸段', lambda v: '/'.join(sorted(set(v)))), 价格=('price', 'median'),
                        最好BSR=('fbsr', 'min'), 出现月数=('m', 'nunique'), 最后月份=('m', 'max'), 评分=('rt', 'last'))
print(s.sort_values('最好BSR').to_string())
print(f'  共 {len(s)} 个家族，最好 BSR ≤ 50 的 {int((s.最好BSR <= 50).sum())} 个，≤ 100 的 {int((s.最好BSR <= 100).sum())} 个')

# 对照：同期（2025-09 以后上架）30″/36″ 的其他新家族，到过前 50、前 100 的比例
fu = x.groupby('p').up.min(); newfam = fu[fu >= '2025-09-01'].index
f = x[x.p.isin(newfam)].groupby('p').agg(最好BSR=('fbsr', 'min'), 价格=('price', 'median'), 带台面=('带台面', lambda v: bool(v.fillna(False).astype(bool).any())))
for name, g in [('全部新家族', f), ('其中价格 250–450、不带石材台面', f[f.价格.between(250, 450) & ~f.带台面])]:
    print(f'  对照 {name} {len(g)} 个：到过前 50 的 {(g.最好BSR <= 50).mean():.0%}，前 100 的 {(g.最好BSR <= 100).mean():.0%}')
