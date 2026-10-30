"""成功线核对（2026-10-30，wen 问"入口松一点、之后剔除无效的，还是有更准的非最终销量指标"）：
1. 139 个"起来"的新家族里可能无效的：只过线一个月、降价冲上去、只在大促月过线、只靠销售额过线；过线后 6 个月还在不在。
2. 入口放宽到"最好排名 ≤ 100"会多进来哪些，之后怎样。
3. 上架 3 个月内能看到的早期指标（排名、评分数、星级、价格、变体），能不能提前判断第 4–6 个月起不起来。
单位、新家族、成功口径直接执行 回归_新家族.py 第 0–2 节，不另抄。用法：python3 -I 成功线_核对.py"""
import os, numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score
HERE = os.path.dirname(os.path.abspath(__file__)); P = os.path.join(HERE, '回归_新家族.py')
src = open(P, encoding='utf-8').read(); ns = {'__file__': P}
exec(src[:src.index('# ---------- 3. 家族特征')], ns)
A, U, um, umw, LAST, ms = ns['A'], ns['U'], ns['um'], ns['umw'], ns['LAST'], ns['ms']
pd.set_option('display.width', 250)

# ---------- 1. 起来的质量 ----------
pm = A[A['单位'].isin(U.index)].groupby(['单位', 'm'])['价格'].median().rename('价')
X = um.reset_index().join(U['L'], on='单位', how='inner').join(pm, on=['单位', 'm']); X['月龄'] = X['m'] - X['L'] + 1
win = X[X['月龄'].between(1, 6)]
S = U[U['y'] == 1].copy(); g = win[win['单位'].isin(S.index)]
S['过线月数'] = g[g['hit']].groupby('单位').size()
S['靠排名'] = g.groupby('单位')['bsr'].min() <= 50
first = g[g['hit']].sort_values('m').groupby('单位').first()
S['降价冲'] = first['价'] / g.groupby('单位')['价'].median() < 0.9
S['只在大促月'] = g[g['hit']].groupby('单位')['m'].agg(lambda s: all(int(i) % 12 + 1 in (7, 11) for i in s))
# 窗口之后 6 个月（月龄 7–12）还在不在：按窗口内的子 ASIN 找（家族键变了、换了单位也算），取这些子体的最好排名
kid = A[A['单位'].isin(U.index) & A['月龄'].between(1, 6)][['单位', '子ASIN']].drop_duplicates()
PK = kid.merge(A[['子ASIN', 'm', '小类BSR']], on='子ASIN').join(U['L'], on='单位')
after = PK[(PK['m'] - PK['L'] + 1).between(7, 12)].groupby('单位')['小类BSR'].min()
S['后6月看得到'] = (S['L'] + 11) <= LAST
S['后6月最好排名'] = after.reindex(S.index)
S['后6月在榜'] = S.index.isin(after.index)
print(f'起来的 {len(S)}；过线月数：', S['过线月数'].value_counts().sort_index().to_dict())
print(f'只过线 1 个月 {int((S["过线月数"] == 1).sum())}；首次过线那月比窗口中位价便宜 10% 以上 {int(S["降价冲"].sum())}（其中只过线 1 个月 {int((S["降价冲"] & (S["过线月数"] == 1)).sum())}）；'
      f'只在 7 / 11 月过线 {int(S["只在大促月"].sum())}；只靠销售额 {int((~S["靠排名"]).sum())}')
for cap, v in [('窗口之后 6 个月看得到的', S[S['后6月看得到']]), ('其中之后 6 个月都在 2026-06 之前的（v11 表家族键不稳，不受影响）', S[(S['L'] + 11) < ns['mi']('2026-06')])]:
  print(f'{cap} {len(v)} 个：')
  for lab, m in [('全部', v.index == v.index), ('过线 1 个月', v['过线月数'] == 1), ('过线 ≥ 2 个月', v['过线月数'] >= 2), ('只靠销售额', ~v['靠排名']), ('靠排名', v['靠排名']), ('只在 7 / 11 月过线', v['只在大促月']), ('首次过线那月降价 10% 以上', v['降价冲'])]:
      w = v[m]; print(f'  {lab}: {len(w)} 个，之后还在榜 {w["后6月在榜"].mean():.0%}，之后进过前 50 {(w["后6月最好排名"] <= 50).mean():.0%}')

# ---------- 2. 入口放宽到最好排名 ≤ 100 ----------
N = U[U['y'] == 0]; gb = umw[umw['单位'].isin(N.index)].groupby('单位')['bsr'].min().reindex(N.index)
near = N.index[gb.between(51, 100)]; vis = [u for u in near if U.at[u, 'L'] + 11 <= LAST]
on = pd.Index(vis).isin(after.index)
print(f'没起来的 {len(N)} 个里，窗口内最好排名 51–100 的 {len(near)} 个；窗口后 6 个月看得到的 {len(vis)} 个：'
      f'之后还在榜 {int(on.sum())}（{on.mean():.0%}），之后进过前 50 {int((after.reindex(vis) <= 50).sum())}')

# ---------- 3. 早期指标（月龄 1–3） ----------
R = A[A['单位'].isin(U.index) & A['月龄'].between(1, 3)].copy()
for c in ('评分数', '评分', '变体数'): R[c] = pd.to_numeric(R[c], errors='coerce')
R['新增'] = pd.to_numeric(R['月新增评分数（MCP）'], errors='coerce')
def agg(g):
    gr = g.dropna(subset=['评分数']); top = gr.loc[gr['评分数'].idxmax()] if len(gr) else None
    return pd.Series(dict(评分数=gr['评分数'].max() if len(gr) else np.nan, 星级=top['评分'] if top is not None else np.nan,
                          价格=g['价格'].median(), 变体=g['变体数'].max(), 新增=g['新增'].max()))
M = R.groupby(['单位', '月龄']).apply(agg).reset_index().merge(umw[['单位', '月龄', 'bsr']], on=['单位', '月龄'], how='left').sort_values(['单位', '月龄'])
def fl(g, c):
    s = g.dropna(subset=[c]); return (s.iloc[0], s.iloc[-1]) if len(s) >= 2 else (None, None)
rows = {}
for u, g in M.groupby('单位'):
    d = {'早期最好排名': g['bsr'].min(), '前3月在榜月数': len(g)}
    a, b = fl(g, 'bsr'); d['排名每月爬升'] = np.log(a['bsr'] / b['bsr']) / (b['月龄'] - a['月龄']) if a is not None else np.nan
    s = g.dropna(subset=['评分数']); d['第3月评分数'] = s['评分数'].iloc[-1] if len(s) else np.nan
    a, b = fl(g, '评分数'); d['每月新增评分'] = (b['评分数'] - a['评分数']) / (b['月龄'] - a['月龄']) if a is not None else np.nan
    d['MCP月新增评分'] = g['新增'].mean()
    a, b = fl(g, '价格'); d['价格守住'] = b['价格'] / a['价格'] if a is not None else np.nan
    a, b = fl(g, '变体'); d['追加变体'] = b['变体'] - a['变体'] if a is not None else np.nan
    s = g.dropna(subset=['星级']); d['星级'] = s['星级'].iloc[-1] if len(s) else np.nan
    rows[u] = d
D = U[['段', 'y', '早期成功']].join(pd.DataFrame(rows).T); D['看得到'] = D['前3月在榜月数'].notna(); D['没早起'] = ~D['早期成功'].astype(bool)
late = D[D['y'].eq(1) & D['没早起']]
print(f'\n起来的 {int(D["y"].sum())} 个里，3 个月内过线 {int(D["早期成功"].sum())}；第 4–6 个月才过线 {len(late)}，其中前 3 个月根本没上榜 {int((~late["看得到"]).sum())}')
SIGN = {'早期最好排名': -1, '排名每月爬升': 1, '第3月评分数': 1, '每月新增评分': 1, 'MCP月新增评分': 1, '价格守住': 1, '追加变体': 1, '星级': 1, '前3月在榜月数': 1}
out = []
for col, sg in SIGN.items():
    r = {'指标': col}
    for seg in ('学习', '检验'):
        d = D[(D['段'] == seg) & D['没早起'] & D[col].notna()]
        r[f'{seg} 家族'] = len(d); r[f'{seg} 后来起来'] = int(d['y'].sum())
        r[f'{seg} AUC'] = roc_auc_score(d['y'], d[col] * sg) if d['y'].nunique() == 2 else np.nan
    out.append(r)
print('前 3 个月上了榜、还没过线的家族：各指标对"第 4–6 个月过线"的 AUC（0.5 = 瞎猜）'); print(pd.DataFrame(out).round(2).to_string(index=False))
d = D[D['没早起'] & D['早期最好排名'].notna()].copy()
d['档'] = pd.cut(d['早期最好排名'], [0, 100, 150, np.inf], labels=['进过前 100', '101–150', '150 以外'])
print('按前 3 个月最好排名分档，第 4–6 个月过线的比例：'); print(d.groupby(['档', '段'], observed=True)['y'].agg(['size', 'mean']).unstack('段').round(2).to_string())
