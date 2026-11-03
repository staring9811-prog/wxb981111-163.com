"""全链路验证（wen 2026-11-03）：老板的评分假设、新品占比、溢价率。三项都在"同月 × 同尺寸段 × 同拆装"的格子里比。
输出 solution-v2/开发建议/全链路验证_评分_新品占比_溢价率.md。"""
import os, numpy as np, pandas as pd, statsmodels.formula.api as smf
from scipy.stats import spearmanr
HERE = os.path.dirname(os.path.abspath(__file__)); os.environ['VER'] = '9'; os.environ['MODE'] = '库'
P = os.path.join(HERE, '回归预测.py'); src = open(P, encoding='utf-8').read()
G = {'__file__': P}; exec(compile(src[:src.index('FEAT = {T')], P, 'exec'), G)
A, U, feat, ms, mi, END, M0, ROOT, UNK = (G[k] for k in ('A', 'U', 'feat', 'ms', 'mi', 'END', 'M0', 'ROOT', 'UNK'))
pct = lambda x: f'{x:.0%}'; f2 = lambda x: f'{x:+.3f}'
def ols(formula, d, cl):
    m = smf.ols(formula, d).fit(cov_type='cluster', cov_kwds={'groups': pd.factorize(d[cl])[0]}); return m
def coef_rows(m, names):
    return [f"| {lab} | {m.params[n]:+.3f} | {m.bse[n]:.3f} | {m.tvalues[n]:+.2f} | {m.pvalues[n]:.3f} |" for n, lab in names if n in m.params]
HD = ['| 变量 | 系数 | 标准误（按单元聚类） | t | p |', '| :--- | ---: | ---: | ---: | ---: |']
L = ['# 全链路验证：老板的评分假设、新品占比、溢价率', '',
     '> 由 `trial/全链路验证.py` 生成（2026-11-03）。数据 2024-10 至 2026-09（卖家精灵月度导出 + 统一打标）。**三项都在"同月 × 同尺寸段 × 同拆装（整装 / 拆装）"的格子里比**，不跨尺寸、不跨拆装。',
     '> 回归都带"格子 × 月"固定效应（只比同一格子同一个月里的产品），标准误按产品 / 单元聚类（同一个产品多个月不算独立样本）。p < 0.05 记为"显著"。', '']

# ======================= 1. 家族 × 月 面板 =======================
A['r'] = pd.to_numeric(A['评分'], errors='coerce').where(lambda x: x.between(1, 5)); A['n'] = pd.to_numeric(A['评分数'], errors='coerce').where(lambda x: x > 0)
A['rc'] = A['r'] * A['c']
main = A.sort_values('c', ascending=False).drop_duplicates(['家族键', 'm'])[['家族键', 'm', '尺寸段', '装', '形态', '价格']]
FM = A.groupby(['家族键', 'm']).agg(S=('c', 'sum'), rc=('rc', 'sum'), cr=('c', lambda x: x[A.loc[x.index, 'r'].notna()].sum()), N=('n', 'max'), 月龄=('月龄', 'min')).reset_index()
FM['R'] = FM['rc'] / FM['cr'].replace(0, np.nan); FM = FM.merge(main, on=['家族键', 'm'])
FM = FM[FM['尺寸段'].notna() & FM['装'].notna() & (FM['S'] > 0)].copy(); FM['格子'] = FM['尺寸段'].astype(str) + '|' + FM['装'].astype(str)
FM['评分贡献'] = FM['S'] / FM['N']   # 原表公式：销量 ÷ 评分数
nxt = lambda col, k: FM.set_index(['家族键', 'm'])[col].reindex(pd.MultiIndex.from_arrays([FM['家族键'], FM['m'] + k])).values
for k in (3, 6):
    FM[f'S+{k}'] = nxt('S', k); FM[f'R+{k}'] = nxt('R', k)
L += ['## 0. 数据口径和限制', '',
      f"- 家族 × 月 面板：{len(FM):,} 行，{FM['家族键'].nunique():,} 个家族。评分 = 家族里各子体评分按销量加权；评分数取家族里最大的（亚马逊同一父体共享评论）。",
      f"- 评分数在 2026-06 至 09 全为 0（v11 表没有这一列）；本文只用星级评分，到 2026-09 都有。",
      '- 评分数会随家族组成跳变（例：某子体 2025-07 是 20，2025-08 变 309，2026-03 又变 38），评分也随之变。所以"评分变好"里混有口径变化，结论要打折看。',
      '- 销量是卖家精灵的估算，家族 × 月里 没在榜 = 当月不在导出里（记缺，不当 0）。', '']

# ======================= 2. 老板的评分假设 =======================
L += ['## 1. 老板的假设：评分低、却和同类卖得差不多 → 这个形态消费者买单；之后有人把评分做上来，销量会升很多', '',
      '> 口径（wen 2026-11-03 更正）："评价"指星级评分（如 4.1、4.2），不是评分数。评分低说明质量或不符合预期；评分低却还有销量、和同类卖得差不多，说明形态是消费者要的。', '',
      '### 1.1 拆成可检验的步骤', '',
      '| 步 | 说法 | 怎么算 | 假设成立应该看到 |', '| :--- | :--- | :--- | :--- |',
      '| ① 识别 | 评分低、却和同类卖得差不多 | 同月、同格子（尺寸段 × 拆装）里：评分在后 1/3，月销在前 1/2，记为 **G（低分不低销）** | 这样的产品存在 |',
      '| ② 家族自己把评分做上来 | G 的评分之后升了，销量升得比别人多 | Δln 销量 对 ΔR、G、G × ΔR 回归（格子 × 月固定效应）；同期和"评分先变、销量后变"两种 | G × ΔR > 0 |',
      '| ③ 别人把同类型做好（老板原意） | 老品低分不低销的类型，后来的新品评分比老品高，就卖得特别好 | 类型 = 格子 × 台面 × 元素。老品"低分不低销"= 类型加权评分在同格各类型里后 1/3、单款月销在前 1/2。新品"做上来"= 上架后第 3–6 个月评分比老品高 ≥ 0.2 | 低分不低销类型 × 新品做上来 的做到率、销量明显高于其他三组（交互项 > 0） |',
      '| ④ 立项时能用 | 不知道新品评分时，进入低分不低销的类型本身有没有优势 | 新家族做到率按类型是否低分不低销分组 | 低分不低销类型更高 |', '']
H = FM[FM['R'].notna()].copy()
grp = H.groupby(['m', '格子']); H['格内家族'] = grp['家族键'].transform('size'); H = H[H['格内家族'] >= 6].copy(); grp = H.groupby(['m', '格子'])
H['R分位'] = grp['R'].rank(pct=True); H['S分位'] = grp['S'].rank(pct=True)
H['G'] = ((H['R分位'] <= 1 / 3) & (H['S分位'] >= 1 / 2)).astype(int); H['新'] = H['月龄'] <= 6; H['FE'] = H['格子'] + '|' + H['m'].astype(str)
H['dR'] = H['R+3'] - H['R']; H['dS3'] = np.log(H['S+3'] / H['S']); H['dS6'] = np.log(H['S+6'] / H['S']); H['dS36'] = np.log(H['S+6'] / H['S+3']); H['lnS'] = np.log(H['S'])
for scope, Hs in (('全部家族', H), ('刚上架（月龄 ≤ 6）', H[H['新']])):
    L += [f'### 1.2 家族自己把评分做上来（{scope}）', '', f"- 样本：{len(Hs):,} 个家族 × 月（{Hs['家族键'].nunique():,} 个家族），G {int(Hs['G'].sum()):,} 个（{Hs['G'].mean():.0%}）。G 平均评分 {Hs.loc[Hs.G == 1, 'R'].mean():.2f}、其他 {Hs.loc[Hs.G == 0, 'R'].mean():.2f}；G 月销中位 {Hs.loc[Hs.G == 1, 'S'].median():.0f}、其他 {Hs.loc[Hs.G == 0, 'S'].median():.0f}。"]
    d = Hs.dropna(subset=['dR']); up = lambda x: (x >= 0.2).mean()
    L.append(f"- 3 个月后评分升 ≥ 0.2 的比例：G {up(d.loc[d.G == 1, 'dR']):.0%}（{int((d.G == 1).sum())} 个）、其他 {up(d.loc[d.G == 0, 'dR']):.0%}（{int((d.G == 0).sum())} 个）。")
    for lab, yv, cond in (('同期：Δln 销量(t→t+3) 对 ΔR(t→t+3)', 'dS3', ['dR', 'dS3']), ('先后：Δln 销量(t+3→t+6) 对 ΔR(t→t+3)（评分先变、销量后变）', 'dS36', ['dR', 'dS36'])):
        dd = Hs.dropna(subset=cond)
        if len(dd) > 100 and dd['G'].sum() > 10:
            mm = ols(f'{yv} ~ dR + G + G:dR + lnS + C(FE)', dd, '家族键')
            L += ['', f'**{lab}**（n = {len(dd):,}）', ''] + HD + coef_rows(mm, [('dR', 'ΔR（评分每升 1 分）'), ('G', 'G 低分不低销'), ('G:dR', 'G × ΔR（G 里评分升 1 分额外多的）'), ('lnS', 'ln 现在销量')])
    L.append('')
# ---- ③ 类型层：老品低分不低销 + 新品做上来 ----
fam_attr = A.loc[A.groupby('家族键')['c'].idxmax()].copy()
fam_attr['元素0'] = fam_attr['元素一'].map(lambda t: t[0] if isinstance(t, list) and len(t) else None)
fam_attr = fam_attr.set_index('家族键')[['台面类型', '元素0']]
FMc = FM.join(fam_attr, on='家族键'); FMc = FMc[~FMc['台面类型'].map(UNK) & FMc['元素0'].notna()].copy()
FMc['类型'] = FMc['格子'] + '|' + FMc['台面类型'].astype(str) + '|' + FMc['元素0'].astype(str)
Ue = U[U['L'] + 5 <= END].copy(); keyfam = A.drop_duplicates('单位').set_index('单位')['家族键']; Ue['家族键'] = keyfam.reindex(Ue.index).values
famtype = FMc.drop_duplicates('家族键').set_index('家族键')[['类型', '格子']]
Ue = Ue.join(famtype, on='家族键').dropna(subset=['类型'])
rowsC = []
for Lm, grpU in Ue.groupby('L'):
    W = FMc[FMc['m'].between(Lm - 6, Lm - 1) & ~FMc['家族键'].isin(grpU['家族键'])]
    if W.empty: continue
    ct = W.groupby(['格子', '类型']).agg(rc=('rc', 'sum'), cr=('cr', 'sum'), S=('S', 'sum'), nf=('家族键', 'nunique')).reset_index()
    ct['R'] = ct['rc'] / ct['cr'].replace(0, np.nan); ct['单款月销'] = ct['S'] / 6 / ct['nf']; ct = ct.dropna(subset=['R'])
    ct['R分位'] = ct.groupby('格子')['R'].rank(pct=True); ct['S分位'] = ct.groupby('格子')['单款月销'].rank(pct=True)
    ct['低分不低销'] = ((ct['R分位'] <= 1 / 3) & (ct['S分位'] >= 1 / 2)).astype(int)
    for u, r in grpU.iterrows():
        c = ct[ct['类型'] == r['类型']]
        if c.empty: continue
        c = c.iloc[0]; own = FM[(FM['家族键'] == r['家族键']) & FM['m'].between(Lm + 2, Lm + 5)]
        s46 = FM[(FM['家族键'] == r['家族键']) & FM['m'].between(Lm + 3, Lm + 5)]['S'].sum() / 3
        rowsC.append(dict(u=u, L=Lm, y=r['y'], 类型=r['类型'], 低分不低销=int(c['低分不低销']), 老品评分=c['R'], 老品单款月销=c['单款月销'], 老品家族=c['nf'],
                          新品评分=own['R'].median() if own['R'].notna().any() else np.nan, 月销46=s46))
CT = pd.DataFrame(rowsC); CT['做上来'] = ((CT['新品评分'] - CT['老品评分']) >= 0.2).astype(int); CT.loc[CT['新品评分'].isna(), '做上来'] = np.nan
CT['销量比'] = np.log((CT['月销46'] + 1) / (CT['老品单款月销'] + 1))
Cd = CT.dropna(subset=['做上来'])
L += ['### 1.3 别人把同类型做好（老板原意）：类型 = 尺寸段 × 拆装 × 台面 × 元素', '',
      f"- 新家族 {len(CT)} 个（上架前 6 个月这个类型里已有老品，观察期已走完）；其中有上架后第 3–6 个月评分的 {len(Cd)} 个。",
      f"- 老品\"低分不低销\"的类型里进入的新家族 {int(CT['低分不低销'].sum())} 个，老品平均评分 {CT.loc[CT['低分不低销'] == 1, '老品评分'].mean():.2f}（其他类型 {CT.loc[CT['低分不低销'] == 0, '老品评分'].mean():.2f}）。", '',
      '| 老品类型 | 新品评分比老品高 ≥ 0.2 | 新家族数 | 每 10 个做到 | 第 4–6 月月销 ÷ 老品单款月销（中位） |', '| :--- | :--- | ---: | :--- | ---: |']
for a_ in (1, 0):
    for b_ in (1, 0):
        g = Cd[(Cd['低分不低销'] == a_) & (Cd['做上来'] == b_)]
        L.append(f"| {'低分不低销' if a_ else '其他'} | {'是（做上来了）' if b_ else '否'} | {len(g)} | {g['y'].mean() * 10:.1f} | ×{np.exp(g['销量比'].median()):.2f} |" if len(g) else f"| {'低分不低销' if a_ else '其他'} | {'是' if b_ else '否'} | 0 | — | — |")
if len(Cd) > 30:
    Cd = Cd.rename(columns={'低分不低销': 'F', '做上来': 'B'}); Cd['B'] = Cd['B'].astype(int)
    for yv, lab in (('y', '做到（0/1，线性概率）'), ('销量比', 'ln(第 4–6 月月销 ÷ 老品单款月销)')):
        mm = smf.ols(f'{yv} ~ F + B + F:B', Cd).fit(cov_type='HC1')
        L += ['', f'**回归：{lab}**（n = {len(Cd)}）', '', '| 变量 | 系数 | 标准误（稳健） | t | p |', '| :--- | ---: | ---: | ---: | ---: |'] + \
             [f"| {lab_} | {mm.params[n]:+.3f} | {mm.bse[n]:.3f} | {mm.tvalues[n]:+.2f} | {mm.pvalues[n]:.3f} |" for n, lab_ in (('F', '低分不低销类型'), ('B', '新品评分做上来'), ('F:B', '低分不低销 × 做上来（老板假设的关键项）'))]
L += ['', '### 1.4 立项时能不能用（还不知道新品评分）', '',
      f"进入老品低分不低销类型的新家族每 10 个做到 {CT.loc[CT['低分不低销'] == 1, 'y'].mean() * 10:.1f}（{int(CT['低分不低销'].sum())} 个），进入其他类型的 {CT.loc[CT['低分不低销'] == 0, 'y'].mean() * 10:.1f}（{int((CT['低分不低销'] == 0).sum())} 个）；"
      f"Fisher 精确检验 p = {__import__('scipy.stats', fromlist=['fisher_exact']).fisher_exact(pd.crosstab(CT['低分不低销'], CT['y']).values)[1]:.2f}。", '']
# ======================= 3. 格子内单元面板（新品占比、溢价率） =======================
A['新行'] = (A['月龄'] <= 6).astype(float)
B = A[A['尺寸段'].notna() & A['装'].notna()].copy(); B['格子'] = B['尺寸段'].astype(str) + '|' + B['装'].astype(str)
B['lp'] = np.log(B['价格'] / B.groupby(['m', '格子'])['价格'].transform('median')).where(B['价格'] > 0)
ATT = {'台面': '台面类型', '元素': '元素一', '材质': '柜体材质', '主色': '主色'}
parts = []
for att, col in ATT.items():
    d = B[['m', 'c', '格子', '新行', 'lp', '家族键', col]].rename(columns={col: '值'})
    if att == '元素': d = d.explode('值')
    d = d[~d['值'].map(UNK)]; d['属性'] = att; parts.append(d)
X = pd.concat(parts, ignore_index=True); X['单元'] = X['格子'] + '|' + X['属性'] + '|' + X['值'].astype(str)
X['c_new'] = X['c'] * X['新行']; X['c_lp'] = X['c'] * X['lp'].fillna(0); X['c_p'] = X['c'] * X['lp'].notna()
UM = X.groupby(['单元', '格子', '属性', 'm']).agg(c=('c', 'sum'), cn=('c_new', 'sum'), clp=('c_lp', 'sum'), cp=('c_p', 'sum'), 家族=('家族键', 'nunique')).reset_index()
DEN = X.groupby(['格子', '属性', 'm'])['c'].sum().rename('den'); DENN = X.groupby(['格子', '属性', 'm'])['c_new'].sum().rename('denn')
UM = UM.join(DEN, on=['格子', '属性', 'm']).join(DENN, on=['格子', '属性', 'm'])
PV = {c: UM.pivot_table(index='单元', columns='m', values=c, aggfunc='sum').reindex(columns=range(M0, END + 1)).fillna(0) for c in ('c', 'cn', 'clp', 'cp', 'den', 'denn', '家族')}
meta = UM.drop_duplicates('单元').set_index('单元')[['格子', '属性']]
E = 0.002; rows = []
for T in range(M0 + 6, END - 7):
    w6 = list(range(T - 6, T)); share_m = (PV['c'][w6] / PV['den'][w6].replace(0, np.nan)).fillna(0)
    xc = np.arange(6) - 2.5; b6 = (np.log(share_m + E) * xc).sum(axis=1) / (xc ** 2).sum()
    s6 = PV['c'][w6].sum(axis=1) / PV['den'][w6].sum(axis=1).replace(0, np.nan)
    x5 = PV['cn'][w6].sum(axis=1) / PV['c'][w6].sum(axis=1).replace(0, np.nan) - PV['denn'][w6].sum(axis=1) / PV['den'][w6].sum(axis=1).replace(0, np.nan)
    prem = PV['clp'][w6].sum(axis=1) / PV['cp'][w6].sum(axis=1).replace(0, np.nan)
    w3 = list(range(T - 3, T)); w3b = list(range(T - 6, T - 3))
    for k in (6, 8):
        if T + k + 2 > END: continue
        wf = list(range(T + k, T + k + 3)); sf = PV['c'][wf].sum(axis=1) / PV['den'][wf].sum(axis=1).replace(0, np.nan)
        pf = PV['clp'][list(range(T + k - 3, T + k + 3))].sum(axis=1) / PV['cp'][list(range(T + k - 3, T + k + 3))].sum(axis=1).replace(0, np.nan)
        newfam_after = PV['家族'][list(range(T, T + 6))].mean(axis=1) - PV['家族'][w6].mean(axis=1)
        rows.append(pd.DataFrame({'单元': PV['c'].index, 'T': T, 'k': k, 'vol': PV['c'][w6].mean(axis=1).values, 'y': np.log((sf + E) / (s6 + E)).values,
                                  'b6': b6.values, 'x5': x5.values, 'prem': prem.values, 'dprem': (pf - prem).values, 'dfam': newfam_after.values}))
R = pd.concat(rows, ignore_index=True).join(meta, on='单元'); R = R.dropna(subset=['y', 'x5', 'prem'])
R['FE'] = R['格子'] + '|' + R['属性'] + '|' + R['T'].astype(str) + '|' + R['k'].astype(str); R['尺寸'] = R['格子'].str.split('|').str[0]
for v in ('vol100', 'vol300'):
    pass
R100 = R[R['vol'] >= 100].copy()
L += ['## 2. 新品占比：能不能预测之后份额（同尺寸、同拆装的格子里比）', '',
      '### 2.1 定义', '',
      '- 单元 = 格子（尺寸段 × 拆装）里某个属性的一个取值，例如"30″ 拆装里的竖棱""30″ 拆装里的石材台面"。',
      '- 份额 = 单元销量 ÷ 这个格子里有这个属性标签的销量。',
      '- **新品占比 x5** = 近 6 个月单元销量里上架 ≤ 6 个月家族的比例 − 同格子同属性整体的这个比例。',
      '- **份额斜率 b6** = 近 6 个月每月份额取对数后对月份的斜率。',
      '- **结果 y** = ln(立项后第 k 至 k+2 个月份额 ÷ 近 6 个月份额)，k = 6、8（立项到上架约 8 个月）。',
      f"- 样本：近 6 个月月均 ≥ 100 件的单元，时点 {ms(R100['T'].min())} 至 {ms(R100['T'].max())}，共 {len(R100):,} 个（单元 × 时点 × 窗口），{R100['单元'].nunique():,} 个单元。", '',
      '### 2.2 合并回归（格子 × 属性 × 时点 × 窗口 固定效应）', '', 'y = β1·b6 + β2·x5 + β3·溢价 + 固定效应', '']
m2 = ols('y ~ b6 + x5 + prem + C(FE)', R100, '单元')
L += HD + coef_rows(m2, [('b6', 'b6 份额斜率'), ('x5', 'x5 新品占比'), ('prem', '溢价（ln 价比）')])
L += ['', f"白话：同格子同属性里，新品占比每高 10 个百分点，6–10 个月后份额约多 {np.expm1(m2.params['x5'] * 0.1):+.1%}（其他不变）。", '',
      '### 2.3 按时点、按属性、按尺寸拆开（偏相关 = 先扣掉 b6 再看 x5 和结果的秩相关）', '', '| 拆法 | 组 | n | x5 单独秩相关 | x5 扣掉 b6 后 | 溢价 单独 | 溢价 扣掉 b6、x5 后 |', '| :--- | :--- | ---: | ---: | ---: | ---: | ---: |']
def partial(d):
    d = d.copy(); d['yd'] = d['y'] - d.groupby('FE')['y'].transform('mean')
    for c in ('b6', 'x5', 'prem'): d[c + 'd'] = d[c] - d.groupby('FE')[c].transform('mean')
    Xb = np.c_[np.ones(len(d)), d['b6d']]; r1 = d['yd'] - Xb @ np.linalg.lstsq(Xb, d['yd'], rcond=None)[0]
    Xbx = np.c_[np.ones(len(d)), d['b6d'], d['x5d']]; r2 = d['yd'] - Xbx @ np.linalg.lstsq(Xbx, d['yd'], rcond=None)[0]
    return len(d), spearmanr(d['x5d'], d['yd'])[0], spearmanr(d['x5d'], r1)[0], spearmanr(d['premd'], d['yd'])[0], spearmanr(d['premd'], r2)[0]
for lab, key in (('时点', 'T'), ('属性', '属性'), ('尺寸', '尺寸')):
    for g, d in R100.groupby(key):
        if len(d) < 60: continue
        n, a, b, c, e = partial(d); L.append(f"| {lab} | {ms(g) if key == 'T' else g} | {n} | {a:+.2f} | {b:+.2f} | {c:+.2f} | {e:+.2f} |")
L += ['', '## 3. 溢价率：wen 的链条——溢价高 → 新品涌入 → 盘子变大 → 竞争加剧 → 价格变低', '',
      '### 3.1 定义', '', '- **溢价** = 单元近 6 个月销量加权的 ln(价格 ÷ 同月同尺寸段同拆装的中位价)。0 = 和同格中位价一样，+0.10 ≈ 贵 10%。', '- 链条拆成四环，每环一条回归（同样的固定效应和聚类）。', '']
R100['新家族增'] = R100['dfam']
chain = [('环 1：溢价高 → 之后新家族变多', 'dfam ~ prem + b6 + np.log(vol)', 'prem', '之后 6 个月月均在榜家族数 − 近 6 个月（个）'),
         ('环 2：新品多 → 盘子（份额）变大', 'y ~ x5 + b6', 'x5', '立项后 6–10 个月份额对数变化'),
         ('环 3：新品多 → 之后溢价下降', 'dprem ~ x5 + prem + b6', 'x5', '之后溢价 − 现在溢价（ln）'),
         ('环 4：溢价本身 → 之后份额', 'y ~ prem + b6 + x5', 'prem', '立项后 6–10 个月份额对数变化')]
for title, fml, var, ylab in chain:
    d = R100.dropna(subset=['dprem']) if 'dprem' in fml else R100
    m = ols(fml + ' + C(FE)', d, '单元')
    L += [f'**{title}**（结果：{ylab}，n = {len(d):,}）', ''] + HD + coef_rows(m, [(c, c) for c in ('prem', 'x5', 'b6', 'np.log(vol)')]) + ['']
# 分阶段：新品多 / 少 的溢价作用
L += ['**环 4 分阶段**：按新品占比把单元分成两半，各自看溢价对之后份额（扣掉 b6）', '', '| 组 | n | 溢价系数 | t | p |', '| :--- | ---: | ---: | ---: | ---: |']
for lab, d in (('新品多（x5 > 0）', R100[R100['x5'] > 0]), ('新品少（x5 ≤ 0）', R100[R100['x5'] <= 0])):
    m = ols('y ~ prem + b6 + C(FE)', d, '单元'); L.append(f"| {lab} | {len(d):,} | {m.params['prem']:+.3f} | {m.tvalues['prem']:+.2f} | {m.pvalues['prem']:.3f} |")
L += ['', '## 4. 读表结论（2026-11-03）', '',
      '**老板的评分假设（按星级评分，wen 2026-11-03 更正后）**',
      '- ① 识别：同格子里评分在后 1/3、月销却在前一半的家族占约 16%（刚上架的约 18%），平均评分 3.4–3.7，月销中位反而比其他高。这类产品确实存在：形态有人买，评分拖后腿。',
      '- ② 家族自己把评分做上来：同期看，评分升 1 分、同 3 个月销量多约 8%（p = 0.025）；但 G 里并不更明显（交互项 +0.01，p = 0.90）。而且"评分先升、销量后涨"不成立（p = 0.38）。',
      '- **意外的一条**：G 本身之后 3–6 个月销量涨得比同格同体量的产品多约 11%（p = 0.005），和评分变没变无关。也就是"低分还卖得动"说明这个形态有真实需求，需求会延续。',
      '- ③ 别人把同类型做好（老板原意）：进入老品"低分不低销"类型的新家族，每 10 个做到 4.8，其他类型 3.7（p = 0.37）；回归里这类类型的主效应 +0.33（p = 0.053），方向支持老板。',
      '- 但"新品评分比老品高"这一组反而做得差（做上来的 2.7、没做上来的 7.5，只有 15 和 8 个）。原因很可能是口径：新品销量少、评论少时，评分容易虚高到 4.8–5.0。卖得差的新品看起来"评分做上来了"，测量被污染了。要排除这一点，需要评分数，而 2026-06 后的评分数缺失。',
      '- **结论**：',
      '  - 支持的部分：老品"评分低、销量不低"的类型 = 消费者认这个形态，后来者进入的做到率偏高，自身需求也会延续。方向一致，但样本少、p 在 0.05–0.4 之间。',
      '  - 还验证不了的部分："评分做上来 → 销量升很多"。需要逐月评分数或评论数据来排除虚高。',
      '  - 策略库状态：从"未验证经验"升为"历史观察（方向一致、未显著）"，可以在机会卡上作为一条信号展示：老品评分、单款月销、和同格的对比。',
      '',
      '**新品占比**',
      '- 同尺寸、同拆装的格子里，加上格子 × 属性 × 时点固定效应、按单元聚类：x5 系数 +0.86（t = 3.06，p = 0.002），扣掉份额斜率后仍显著。',
      '- 10 个时点全为正（偏相关 +0.17 至 +0.30）；四个属性都为正。尺寸里 60″ 为负、42″ 混杂（样本少）。',
      '- **结论**：有回归相关性，进入打分。',
      '',
      '**溢价率**',
      '- 在同尺寸、同拆装的格子里比，溢价对之后份额的偏相关 10 个时点里 9 个为负（−0.05 至 −0.19），合并系数 −0.46（p = 0.115）。方向是"同格里卖得更贵的属性取值，之后份额略降"，但不显著。尺寸之间差别大：24″ −0.50，48″ +0.34。',
      '- wen 的链条逐环检验：',
      '  - 环 1"溢价高 → 之后新家族变多"不显著（p = 0.29）；',
      '  - 环 2"新品多 → 份额变大"显著（p = 0.004）；',
      '  - 环 3"新品多 → 之后溢价下降"不显著（p = 0.45）；',
      '  - 环 4 分阶段也都不显著。',
      '- **结论**：竖棱是这条链条的典型案例，但放到全部同格比较里，只有"新品多 → 份额变大"这一环站得住。溢价率不进入打分，作为机会卡上的阶段信息展示；24″ 等尺寸单独看时可作参考。',
      '']
out = os.path.join(ROOT, 'solution-v2/开发建议/全链路验证_评分_新品占比_溢价率.md'); open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L))
