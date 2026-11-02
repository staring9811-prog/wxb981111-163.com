"""第四版：大格子下探（规则见 识别方法_预登记.md 补记）。尺寸 → 尺寸里的台面 → 尺寸 × 台面里的元素 → 具体新品。
每层在兄弟格子里比：预估增量 = 前 6 个月月均销 × (兄弟里合成分位 − 0.5)；溢价 = 中位价 ÷ 上一层中位价；缺口（只有尺寸）= 搜索份额 − 销量份额。
ASOF=yyyy-mm python3 -I 下探.py → solution-v2/开发建议/下探_<ASOF>.md；时点早于数据末尾时附实际结果和第三版（拉平）对比。"""
import os, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
ASOF = os.environ.get('ASOF', '2026-01'); os.environ['MODE'] = '库'
P = os.path.join(HERE, '两层识别.py'); ns = {'__file__': P}
exec(compile(open(P, encoding='utf-8').read(), P, 'exec'), ns)
A, U, feat, mi, ms, END, newprod, search_yoy, TK, KS = (ns[k] for k in ('A', 'U', 'feat', 'mi', 'ms', 'END', 'newprod', 'search_yoy', 'TK', 'KS'))
T = mi(ASOF); HAS_OUT = T + 8 <= END or T + 3 <= END
R6, R12 = A['m'].between(T - 6, T - 1), A['m'].between(T - 12, T - 7)
RO = A['m'].between(T + 3, min(T + 8, END)); NO = max(1, min(T + 8, END) - (T + 3) + 1)
YO = search_yoy(T)
# 尺寸层的关键词缺口：近 3 个月搜索份额 − 销量份额
k3 = KS[(KS['维度'] == '尺寸') & KS['m'].between(T - 3, T - 1)].groupby('值')['v'].sum(); kshare = k3 / k3.sum()
s3 = A[A['m'].between(T - 3, T - 1)].groupby('尺寸段')['c'].sum(); s3 = s3[s3.index.isin(kshare.index)]; s3 = s3 / s3.sum()
def stats(mask):
    def mon(win, n):
        d = A[mask & win]; return d['c'].sum() / n, (d.groupby('m')['家族键'].nunique().sum() / n)
    v6, f6 = mon(R6, 6); v12, f12 = mon(R12, 6); vo = A[mask & RO]['c'].sum() / NO if HAS_OUT else np.nan
    return dict(月均销_前=v6, 月均销_前前=v12, 家族_前=f6, 家族_前前=f12, 中位价=A[mask & R6]['价格'].median(), 月均销_后=vo)
def newfam(cond, a, b):
    d = U[U['L'].between(a, b) & (U['L'] + 5 <= END)]; m = [u for u in d.index if cond(feat[u])]
    return int(d.loc[m, 'y'].sum()), len(m)
def score(rows, dim):
    D = pd.DataFrame(rows)
    D['S1'] = np.log((D['月均销_前'] + 1) / (D['月均销_前前'] + 1)); D['S2'] = D['家族_前'] - D['家族_前前']
    D['S3'] = [YO.get((dim, v), np.nan) for v in D['值']]
    for s in ('S1', 'S2', 'S3'): D[s + 'p'] = D[s].rank(pct=True)
    D['分位'] = D[['S1p', 'S2p', 'S3p']].mean(axis=1, skipna=True).rank(pct=True)
    D['预估增量'] = D['月均销_前'] * (D['分位'] - 0.5); D['份额'] = D['月均销_前'] / D['月均销_前'].sum()
    D['实际增量'] = D['月均销_后'] - D['月均销_前']
    return D
UNK = ns['UNK']
pct = lambda x: '—' if pd.isna(x) else (f'{x:.1%}' if abs(x) < 0.1 else f'{x:.0%}')
in10 = lambda p: '—' if pd.isna(p) else f'{p * 10:.1f}'.rstrip('0').rstrip('.')
cat_med = A[R6]['价格'].median()
# ---------- 第 1 层：尺寸 ----------
SZ = [s for s in A['尺寸段'].dropna().unique()]
L1 = score([dict(值=s, **stats(A['尺寸段'].eq(s))) for s in SZ], '尺寸')
L1['溢价'] = L1['中位价'] / cat_med; L1['缺口'] = [kshare.get(s, np.nan) - s3.get(s, np.nan) for s in L1['值']]
L1[['新品做到', '新品数']] = [newfam(lambda f, s=s: f['主尺寸段'][0] == s, T - 15, T - 7) for s in L1['值']]
pick1 = L1.nlargest(3, '预估增量'); emg1 = L1[(L1['分位'] >= 0.8) & (L1['份额'] < 0.05) & ~L1.index.isin(pick1.index)]
tree, leaves, emerg = [], [], [('尺寸', r) for r in emg1.itertuples()]
for r1 in pick1.itertuples():
    m1 = A['尺寸段'].eq(r1.值)
    tops = [t for t in A.loc[m1 & R6, '台面类型'].dropna().unique() if not UNK(t)]
    L2 = score([dict(值=t, **stats(m1 & A['台面类型'].eq(t))) for t in tops], '台面'); L2['溢价'] = L2['中位价'] / r1.中位价
    L2[['新品做到', '新品数']] = [newfam(lambda f, s=r1.值, t=t: f['主尺寸段'][0] == s and f['台面类型'][0] == t, T - 15, T - 7) for t in L2['值']]
    pick2 = L2.nlargest(2, '预估增量'); emerg += [(f'{r1.值} ×', r) for r in L2[(L2['分位'] >= 0.8) & (L2['份额'] < 0.05) & ~L2.index.isin(pick2.index)].itertuples()]
    kids2 = []
    for r2 in pick2.itertuples():
        m2 = m1 & A['台面类型'].eq(r2.值)
        els = pd.Series([e for t in A.loc[m2 & R6, '元素一'] for e in t]).value_counts(); els = [e for e in els.index if els[e] >= 3]
        L3 = score([dict(值=e, **stats(m2 & A['元素一'].map(lambda t, e=e: e in t))) for e in els], '元素'); L3['溢价'] = L3['中位价'] / r2.中位价
        L3[['新品做到', '新品数']] = [newfam(lambda f, s=r1.值, t=r2.值, e=e: f['主尺寸段'][0] == s and f['台面类型'][0] == t and e in f['元素'], T - 15, T - 7) for e in L3['值']]
        pick3 = L3.nlargest(2, '预估增量'); emerg += [(f'{r1.值} × {r2.值} ×', r) for r in L3[(L3['分位'] >= 0.8) & (L3['份额'] < 0.05) & ~L3.index.isin(pick3.index)].itertuples()]
        for r3 in pick3.itertuples(): leaves.append((r1.值, r2.值, r3.值, r3))
        kids2.append((r2, L3, pick3))
    tree.append((r1, L2, pick2, kids2))
# ---------- 第 4 层：具体新品 ----------
tr = U[U['L'] + 5 <= T - 1]; sc = newprod(T, True)
rec_u = tr[tr['L'] >= tr['L'].max() - 5]; r_obs = rec_u['y'].mean(); p_bar = sc(list(rec_u.index)).mean()
shift = np.log(r_obs / (1 - r_obs)) - np.log(p_bar / (1 - p_bar)); cal = lambda p: 1 / (1 + np.exp(-(np.log(p / (1 - p)) + shift)))
umw = ns['ns']['umw'] if 'ns' in ns else None
from_umw = U.join(A.groupby('单位')['c'].sum().rename('_'), how='left')
def spec(s, t, e):
    best = None
    for tier in ('低', '中', '高'):
        for col in ('白', '灰', '原木', '深木', '黑'):
            for spread in (True, False):
                k = f'S|{s}|{t}|{e}|{tier}|{col}|{spread}'
                TK[k] = [f'尺寸={s}', f'档={tier}', f'台面={t}', f'主色={col}', '装=拆装', '形态=落地式', f'元素={e}'] + (['颜色≥2', '子体≥4'] if spread else [])
                p = cal(sc([k])[0])
                if spread and (best is None or p > best[0]): best = (p, tier, col)
    p_few = cal(sc([f'S|{s}|{t}|{e}|{best[1]}|{best[2]}|False'])[0])
    d = tr[(tr['主尺寸段'] == s) & (tr['y'] == 1)]
    return best, p_few, d['首次达线月龄'].median(), d['最高销售额'].median()
avg = cal(sc(list(tr.index))).mean()

L = [f'# 大格子下探：站在 {ASOF} 月初（第四版）', '',
     f'> 规则见 识别方法_预登记.md 补记（第四版）；只用截至 {ms(T - 1)} 的数据。由 `trial/下探.py` 生成。',
     '> 每层都在上一层格子里比："预估增量" = 前 6 个月月均销 ×（在兄弟格子里的增长分位 − 0.5），件 / 月，正 = 值得往下看；"溢价" = 中位价 ÷ 上一层中位价；"缺口" = 关键词搜索份额 − 销量份额（只有尺寸）。'
     '"新品" = 1 月前已走完 6 个月的新家族，做到 / 家族（做到 = 6 个月内小类前 50 或月销售额 $10 万）。' + ('右侧"实际"列是之后 T+3 至 T+8 的结果，当时看不到。' if HAS_OUT else ''), '',
     '## 第 1 层：尺寸（全部尺寸，前 3 个往下探）', '',
     '| 尺寸 | 月均销 前 6 个月（变化） | 份额 | 增长分位 | 预估增量 | 溢价 | 缺口 | 新品 做到/家族 |' + (' 实际增量 |' if HAS_OUT else ''), '| :--- | :--- | ---: | ---: | ---: | ---: | ---: | :--- |' + (' ---: |' if HAS_OUT else '')]
def row(r, extra=''):
    return (f"| {r.值}{extra} | {r.月均销_前:,.0f}（{np.expm1(r.S1):+.0%}） | {pct(r.份额)} | {r.分位:.0%} | {r.预估增量:+,.0f} | {r.溢价:.2f} | "
            + (f"{(r.缺口 * 100):+.0f} 个百分点" if hasattr(r, '缺口') and pd.notna(getattr(r, '缺口', np.nan)) else '—') + f" | {r.新品做到}/{r.新品数} |" + (f" {r.实际增量:+,.0f} |" if HAS_OUT else ''))
for r in L1.sort_values('预估增量', ascending=False).itertuples(): L.append(row(r, ' ←' if r.Index in pick1.index else ''))
for r1, L2, pick2, kids2 in tree:
    L += ['', f'## 第 2 层：{r1.值} 里的台面（前 2 个往下探）', '', '| 台面 | 月均销 前 6 个月（变化） | 尺寸内份额 | 增长分位 | 预估增量 | 溢价（÷ 这个尺寸） | 缺口 | 新品 做到/家族 |' + (' 实际增量 |' if HAS_OUT else ''),
          '| :--- | :--- | ---: | ---: | ---: | ---: | ---: | :--- |' + (' ---: |' if HAS_OUT else '')]
    for r in L2.sort_values('预估增量', ascending=False).head(8).itertuples(): L.append(row(r, ' ←' if r.Index in pick2.index else ''))
    for r2, L3, pick3 in kids2:
        L += ['', f'### 第 3 层：{r1.值} × {r2.值} 里的元素（前 2 个）', '', '| 元素 | 月均销 前 6 个月（变化） | 格内份额 | 增长分位 | 预估增量 | 溢价（÷ 上一层） | 缺口 | 新品 做到/家族 |' + (' 实际增量 |' if HAS_OUT else ''),
              '| :--- | :--- | ---: | ---: | ---: | ---: | ---: | :--- |' + (' ---: |' if HAS_OUT else '')]
        for r in L3.sort_values('预估增量', ascending=False).head(6).itertuples(): L.append(row(r, ' ←' if r.Index in pick3.index else ''))
L += ['', '## 第 4 层：每个叶子格子里，做什么样的新品', '', f'当期新品平均每 10 个做到 {in10(avg)} 个（按最近半年上架的新品水平校准）。', '',
      '| 叶子格子 | 建议的价位、主色（首月 ≥ 2 色、≥ 4 子体） | 每 10 个做到几个 | 只铺 1 色、≤ 2 子体时 | 做到的话第几个月 | 做到后最高月销售额（同尺寸中位） |', '| :--- | :--- | :--- | :--- | :--- | :--- |']
for s, t, e, r in leaves:
    (p, tier, col), pf, mo, rev = spec(s, t, e)
    L.append(f"| {s} × {t} × {e} | {tier}档、主色{col} | **{in10(p)}** | {in10(pf)} | 第 {mo:.0f} 个月 | ${rev / 1000:.0f}k |")
L += ['', '## 冒头的格子（在兄弟里增长分位 ≥ 80%、份额 < 5%，列出不下探，可小批量试）', '', '| 位置 | 格子 | 月均销（变化） | 增长分位 | 新品 做到/家族 |' + (' 实际增量 |' if HAS_OUT else ''), '| :--- | :--- | :--- | ---: | :--- |' + (' ---: |' if HAS_OUT else '')]
for where, r in emerg:
    L.append(f"| {where} | {r.值} | {r.月均销_前:,.0f}（{np.expm1(r.S1):+.0%}） | {r.分位:.0%} | {r.新品做到}/{r.新品数} |" + (f" {r.实际增量:+,.0f} |" if HAS_OUT else ''))
# ---------- 和第三版（拉平）比 ----------
if HAS_OUT:
    n = len(leaves)
    allk = A[R6 | RO].dropna(subset=['尺寸段'])
    combos = {(s, t, e) for s, t, es in zip(allk['尺寸段'], allk['台面类型'], allk['元素一']) if not UNK(t) for e in es}
    flat = []
    for s, t, e in combos:
        m = A['尺寸段'].eq(s) & A['台面类型'].eq(t) & A['元素一'].map(lambda x, e=e: e in x); st = stats(m)
        if st['家族_前'] > 0 or st['家族_前前'] > 0: flat.append(dict(值=(s, t, e), **st))
    F = pd.DataFrame(flat); F['S1'] = np.log((F['月均销_前'] + 1) / (F['月均销_前前'] + 1)); F['S2'] = F['家族_前'] - F['家族_前前']
    F['S3'] = [np.nanmean([YO.get(('尺寸', s), np.nan), YO.get(('台面', t), np.nan), YO.get(('元素', e), np.nan)]) for s, t, e in F['值']]
    for c in ('S1', 'S2', 'S3'): F[c + 'p'] = F[c].rank(pct=True)
    F['分位'] = F[['S1p', 'S2p', 'S3p']].mean(axis=1, skipna=True).rank(pct=True); F['v3'] = F['月均销_前'] * (F['分位'] - 0.5); F['实际增量'] = F['月均销_后'] - F['月均销_前']
    top3 = F.nlargest(n, 'v3'); leafset = {(s, t, e) for s, t, e, _ in leaves}
    lv = F[F['值'].isin(leafset)]
    def nf(keys):
        d = U[U['L'].between(T, T + 3) & (U['L'] + 5 <= END)]; m = [u for u in d.index if any((feat[u]['主尺寸段'][0], feat[u]['台面类型'][0], e) in keys for e in feat[u]['元素'])]
        return f"{int(d.loc[m, 'y'].sum())}/{len(m)}（{in10(d.loc[m, 'y'].mean()) if m else '—'}）", in10(d['y'].mean())
    a1, base = nf(leafset); a2, _ = nf(set(top3['值']))
    real = F.nlargest(n, '实际增量')
    L += ['', f'## 和第三版（拉平排名）比：都选 {n} 个"尺寸 × 台面 × 元素"', '', '| | 第四版（下探） | 第三版（拉平） |', '| :--- | :--- | :--- |',
          f"| 选中格子之后合计实际增量（件 / 月） | {lv['实际增量'].sum():+,.0f} | {top3['实际增量'].sum():+,.0f} |",
          f"| 其中之后减少的格子 | {int((lv['实际增量'] < 0).sum())} / {len(lv)} | {int((top3['实际增量'] < 0).sum())} / {n} |",
          f"| 实际增量最大的 {n} 个里选中了几个 | {len(set(real['值']) & leafset)} | {len(set(real['值']) & set(top3['值']))} |",
          f"| 同组合新品（{ASOF} 至 {ms(T + 3)} 上架）做到 / 家族（每 10 个；全部是 {base}） | {a1} | {a2} |"]
out = os.path.join(ROOT, f'solution-v2/开发建议/下探_{ASOF}.md'); open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L))
