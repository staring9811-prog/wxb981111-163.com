"""案例：竖棱（fluted / reeded）起来之前有哪些信号。逐月：份额、新品占比、搜索、新上架家族及做到、第九版站在当月给的把握与分级；附代表家族链接和主图。
输出 solution-v2/机会判定卡/案例_竖棱起来前的信号.md 与 案例_竖棱趋势.png。"""
import os, numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib import font_manager
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ['VER'] = '9'; os.environ['MODE'] = '库'
P = os.path.join(HERE, '回归预测.py'); src = open(P, encoding='utf-8').read()
G = {'__file__': P}; exec(compile(src[:src.index('# ---------- 回测')], P, 'exec'), G); globals().update({k: v for k, v in G.items() if not k.startswith('__')})
KS = G['ns']['KS']
V = '竖棱'; C, F, den, vals = PAN[('元素',)]; NC = NEWC[('元素',)]
share = C.loc[V] / den; newsh = NC.loc[V] / C.loc[V].replace(0, np.nan); catnew = CATNEW / CAT
# 搜索：月度，按来源
ks = KS[(KS['维度'] == '元素') & (KS['值'] == V)].groupby(['来源', 'm'])['v'].sum().unstack(0)
# 溢价率：同月、同尺寸段、同安装方式（装）的中位价为基准，竖棱各行价比按销量加权取中位
def wmed(x, w):
    o = np.argsort(x); x, w = np.asarray(x)[o], np.asarray(w)[o]; c = np.cumsum(w); return x[np.searchsorted(c, c[-1] / 2)] if len(x) else np.nan
B = A[A['价格'].gt(0) & A['尺寸段'].notna() & A['装'].notna()].copy()
B['基准'] = B.groupby(['m', '尺寸段', '装'])['价格'].transform('median'); B['价比'] = B['价格'] / B['基准']
BV = B[B['元素一'].map(lambda t: V in t)]
prem = BV.groupby('m').apply(lambda g: wmed(g['价比'].values, g['c'].values)).reindex(MONTHS)
# 新上架竖棱家族
isv = pd.Series({u: V in feat[u]['元素'] for u in U.index}); NV = U[isv.reindex(U.index).values]
launch = NV.groupby('L').agg(新家族=('y', 'size'), 做到=('y', 'sum'))
rows = []
for T in range(M0 + 9, END + 2):   # 最早能估回归的时点：2025-07（要有已知结果）
    D = predict(T)[0]; r = D.loc[('元素', V)]
    rows.append(dict(T=T, 份额6=r['份额6'], 斜率=np.expm1(r['b6']), 新品占比相对=r['x5'], 把握=r['把握'], 分级=r['分级'], 预测份额6=r['份额6'] * np.exp(r['预测6'])))
S = pd.DataFrame(rows).set_index('T')
L = ['# 案例：竖棱（fluted / reeded）起来之前，有哪些信号', '',
     '> 由 `trial/案例_竖棱.py` 生成。份额 = 竖棱家族销量 ÷ 有元素标签的销量（一个家族可有多个元素）。新品占比 = 竖棱销量里上架 ≤ 6 个月家族的比例。把握 / 分级 = 第九版站在当月（只用之前的数据）给的评分，看立项后第 6–10 个月。', '',
     '![竖棱趋势](案例_竖棱趋势.png)', '', '## 逐月时间线', '',
     '| 月 | 竖棱份额（当月） | 溢价率（同尺寸同安装方式） | 新品占比（竖棱 / 品类） | Google 搜索 | 亚马逊搜索 | 当月新上架竖棱家族（之后做到） | 站在当月：近 6 个月份额 | 份额每月变化 | 新品占比高出品类 | 第九版把握 / 分级 |', '| :--- | ---: | ---: | :--- | ---: | ---: | :--- | ---: | ---: | ---: | :--- |']
for m in MONTHS + [END + 1]:
    g = ks['google'].get(m, np.nan) if 'google' in ks else np.nan; a = ks['amazon'].get(m, np.nan) if 'amazon' in ks else np.nan
    la = launch.loc[m] if m in launch.index else None
    s = S.loc[m] if m in S.index else None
    L.append(f"| {ms(m)} | {share.get(m, np.nan):.1%} | {prem.get(m, np.nan):.2f} | {newsh.get(m, np.nan):.0%} / {catnew.get(m, np.nan):.0%} | {g:,.0f} | {a:,.0f} | {(f'{int(la.新家族)}（{int(la.做到)}）' if la is not None else '—')} | "
             + (f"{s.份额6:.1%} | {s.斜率:+.1%} | {s.新品占比相对:+.0%} | {s.把握:.0%} / {s.分级} |" if s is not None else '— | — | — | — |'))
L = [x.replace('nan%', '—').replace('| nan |', '| — |') for x in L]
# 代表家族：近 6 个月销量最高的竖棱家族
rec = A[(A['m'] >= END - 5) & A['元素一'].map(lambda t: V in t)]
top = rec.groupby('家族键').agg(销量=('c', 'sum'), 品牌=('品牌', 'first'), 链接=('商品链接', 'first'), 图=('主图500', 'first'), 价格=('价格', 'median'), 尺寸=('尺寸段', 'first'), 台面=('台面类型', 'first'), 上架=('上架日期', 'first')).sort_values('销量', ascending=False).head(8)
L += ['', f'## 代表家族（{ms(END - 5)} 至 {ms(END)} 竖棱销量前 8）', '', '| 主图 | 家族 | 品牌 | 尺寸 · 台面 | 中位价 | 上架日期 | 近 6 个月月均销 |', '| :--- | :--- | :--- | :--- | ---: | :--- | ---: |']
for k, r in top.iterrows():
    img = f'<img src="{r.图}" width="90">' if isinstance(r.图, str) and r.图.startswith('http') else '—'
    lk = f'[{k}]({r.链接})' if isinstance(r.链接, str) and r.链接.startswith('http') else k
    L.append(f"| {img} | {lk} | {r.品牌} | {r.尺寸} · {r.台面} | ${r.价格:,.0f} | {str(r.上架)[:10]} | {r.销量 / 6:,.0f} |")
# 图：三联小图（份额、新品占比、搜索）
fp = [f for f in font_manager.findSystemFonts() if any(x in f for x in ('wqy-zenhei', 'NotoSansCJK', 'SourceHanSans', 'Noto Sans CJK'))]
if fp: font_manager.fontManager.addfont(fp[0]); plt.rcParams['font.family'] = font_manager.FontProperties(fname=fp[0]).get_name()
x = [ms(m) for m in MONTHS]; fig, ax = plt.subplots(4, 1, figsize=(10, 10), sharex=True)
ax[0].plot(x, share.values * 100, color='#2a6fdb', lw=2); ax[0].set_ylabel('竖棱份额 %')
ax[1].plot(x, newsh.reindex(MONTHS).values * 100, color='#2a6fdb', lw=2, label='竖棱'); ax[1].plot(x, catnew.values * 100, color='#999', lw=1.5, label='品类'); ax[1].set_ylabel('新品占比 %'); ax[1].legend(frameon=False)
for src_, col in (('google', '#2a6fdb'), ('amazon', '#e07b39')):
    if src_ in ks: ax[2].plot(x, ks[src_].reindex(MONTHS).values, color=col, lw=2, label={'google': 'Google', 'amazon': '亚马逊站内'}[src_])
ax[2].set_ylabel('搜索量'); ax[2].legend(frameon=False)
ax[3].plot(x, prem.values, color='#2a6fdb', lw=2); ax[3].axhline(1, color='#999', lw=1); ax[3].set_ylabel('溢价率（×同尺寸同安装）')
for a in ax: a.grid(axis='y', color='#eee'); a.spines[['top', 'right']].set_visible(False)
plt.xticks(rotation=60, fontsize=8); fig.tight_layout()
OUTD = os.path.join(ROOT, 'solution-v2/机会判定卡'); fig.savefig(os.path.join(OUTD, '案例_竖棱趋势.png'), dpi=130)
open(os.path.join(OUTD, '案例_竖棱起来前的信号.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L)); print('font', fp[:1])
