"""第六 / 七版：回归预测 + 评分（规则见 识别方法_预登记.md 补记第六、七版，先提交后回测）。VER=6 / 7（默认 7）。
市场层：五个大属性的每个取值 + 两两交叉的每个格子（全量），预测 T+k 起 3 个月的份额变化（k = 0 / 3 / 6），给 80% 区间、把握、预计多卖、分级。
新品层：做到概率（第一版打分 + 校准）、上架第 4–6 个月月均销（L2 回归 + 区间）、做到的时间。
MODE=回测 → solution-v2/开发建议/回归预测_回测.md；MODE=建议 ASOF=yyyy-mm → solution-v2/开发建议/回归预测_<ASOF>.md。"""
import os, itertools, numpy as np, pandas as pd
from scipy.stats import spearmanr, norm
from sklearn.linear_model import Ridge
from sklearn.metrics import roc_auc_score
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
VER = int(os.environ.get('VER', '8')); MODE = os.environ.get('MODE', '回测'); ASOF = os.environ.get('ASOF', '2026-10'); os.environ['MODE'] = '库'
P = os.path.join(HERE, '大属性为线.py'); ns = {'__file__': P}
exec(compile(open(P, encoding='utf-8').read(), P, 'exec'), ns)
A, U, feat, mi, ms, END, newprod, search_yoy, TK, UNK, DIMS = (ns[k] for k in ('A', 'U', 'feat', 'mi', 'ms', 'END', 'newprod', 'search_yoy', 'TK', 'UNK', 'DIMS'))
M0 = int(A['m'].min()); MONTHS = list(range(M0, END + 1)); EPS = 0.001; KS_ = (0, 3, 6); TIER = lambda b: np.where(b >= 1000, '≥1,000', np.where(b >= 300, '300–1,000', '<300'))
in10 = lambda p: '—' if pd.isna(p) else f'{p * 10:.1f}'.rstrip('0').rstrip('.')
KEYCOL = {d: (A['元素一'] if d == '元素' else A[c]) for d, c in DIMS.items()}

# ---------- 面板：每个单元每月销量、在榜家族数、分母（已知标签总销量） ----------
def panel(dims):
    df = pd.DataFrame({'m': A['m'].values, 'c': A['c'].values, 'fam': A['家族键'].values})
    for d in dims: df[d] = KEYCOL[d].values
    for d in dims:
        if d == '元素': df = df.explode(d)
    for d in dims: df = df[~df[d].map(UNK)]
    den = A[np.logical_and.reduce([~KEYCOL[d].map(lambda v: (len(v) == 0) if isinstance(v, list) else UNK(v)) for d in dims])].groupby('m')['c'].sum().reindex(MONTHS, fill_value=0)
    key = df[list(dims)].astype(str).agg(' × '.join, axis=1)
    C = df.groupby([key, df['m']])['c'].sum().unstack(fill_value=0).reindex(columns=MONTHS, fill_value=0)
    F = df.groupby([key, df['m']])['fam'].nunique().unstack(fill_value=0).reindex(columns=MONTHS, fill_value=0)
    vals = df.assign(_k=key).drop_duplicates('_k').set_index('_k')[list(dims)]
    return C, F, den, vals
PAN = {}
for dims in [(d,) for d in DIMS] + list(itertools.combinations(DIMS, 2)):
    C, F, den, vals = panel(dims); PAN[dims] = (C, F, den, vals)
CAT = A.groupby('m')['c'].sum().reindex(MONTHS, fill_value=0)
mean3 = lambda X, a: X.loc[:, [m for m in range(a, a + 3) if m in X.columns]].mean(axis=1)

def feats(T):
    """站在 T（只用 T−1 及以前）的每个单元特征。"""
    yo = search_yoy(T); out = []
    for dims, (C, F, den, vals) in PAN.items():
        b1, b0 = mean3(C, T - 3), mean3(C, T - 6); d1, d0 = den.loc[T - 3:T - 1].mean(), den.loc[T - 6:T - 4].mean()
        f1, f0 = mean3(F, T - 3), mean3(F, T - 6)
        s3 = [np.array([yo.get((d, v), np.nan) for v in vals.loc[C.index, d]]) for d in dims if d != '材质']
        s3 = np.nanmean(np.vstack(s3), axis=0) if s3 else np.full(len(C), np.nan)
        D = pd.DataFrame({'层': '大属性' if len(dims) == 1 else '两维格子', '属性': ' × '.join(dims), '取值': C.index, '近3月': b1.values,
                          '份额': (b1 / d1).values, '份额前': (b0 / d0).values, 'x2': ((f1 - f0) / (f0 + 1)).values, 'S3': s3, '分母': d1, '标签占比': d1 / CAT.loc[T - 3:T - 1].mean()})
        cols6 = list(range(T - 6, T)); xc = np.arange(6) - 2.5
        D['份额6'] = (C[cols6].sum(axis=1) / den.loc[T - 6:T - 1].sum()).values
        D['b6'] = ((np.log(C[cols6].div(den.loc[T - 6:T - 1].replace(0, np.nan), axis=1).fillna(0) + EPS) * xc).sum(axis=1) / (xc ** 2).sum()).values
        D['dims'] = [dims] * len(D); out.append(D)
    D = pd.concat(out, ignore_index=True); D = D[D['近3月'] > 0].copy()
    D['x1'] = np.log((D['份额'] + EPS) / (D['份额前'] + EPS)); D['x3'] = D['S3'].fillna(0).clip(-1, 2); D['无词'] = D['S3'].isna()
    D['x4'] = np.log(D['近3月'] + 5); D['T'] = T
    return D.set_index(['属性', '取值'])

def target(D, T, k):
    """T+k 起 3 个月的份额对数变化；窗口未走完返回 NaN。"""
    a = T + k
    if a + 2 > END: return pd.Series(np.nan, index=D.index)
    res = {}
    for dims, (C, F, den, vals) in PAN.items():
        s = mean3(C, a) / den.loc[a:a + 2].mean(); att = ' × '.join(dims)
        for v, x in s.items(): res[(att, v)] = x
    s = pd.Series([res.get(i, 0.0) for i in D.index], index=D.index)
    return np.log((s + EPS) / (D[BASE] + EPS))
def actual_units(D, T, k, what='件'):
    a = T + k; res = {}
    for dims, (C, F, den, vals) in PAN.items():
        dd = den.loc[a:a + 2].mean()
        for v, x in mean3(C, a).items(): res[(' × '.join(dims), v)] = x if what == '件' else dd
        if what != '件': res.update({(' × '.join(dims), v): dd for v in vals.index})
    return pd.Series([res.get(i, 0.0) for i in D.index], index=D.index)

def set_ver(v):
    global VER, XS, BASE
    VER = v; XS = ['x1', 'x2', 'x3', 'x4'] if v == 6 else ['b6', 'x2', 'x3', 'x4']; BASE = '份额' if v == 6 else '份额6'
set_ver(VER)
def design(D, k):
    X = D[XS].copy(); X['x4'] = X['x4'] - 5.0
    for x in XS: X[x + '·k'] = X[x] * k / 3
    X['k'] = k / 3; return X
FEAT = {T: feats(T) for T in range(M0 + 6, END + 1)}
def fit(T0):
    """只用结果在 T0−1 前已知的 (T, k)。"""
    rows = []
    for T in range(M0 + 6, T0):
        for k in KS_:
            if T + k + 2 > T0 - 1: continue
            D = FEAT[T]; y = target(D, T, k); ok = (D['近3月'] >= 50) & y.notna()
            X = design(D[ok], k); X['y'] = y[ok]; X['tier'] = TIER(D.loc[ok, '近3月'].values); X['T'] = T; X['kk'] = k; rows.append(X)
    Tr = pd.concat(rows); cols = [c for c in Tr.columns if c not in ('y', 'tier', 'T', 'kk')]
    m = Ridge(alpha=1e-6).fit(Tr[cols], Tr['y']); Tr['res'] = Tr['y'] - m.predict(Tr[cols])
    agg = dict(mu='mean', lo=lambda r: r.quantile(0.1), hi=lambda r: r.quantile(0.9), sd='std', n='size')
    q = Tr.groupby('tier')['res'].agg(**agg)
    if VER >= 8:   # 第八版：按（体量档, k）校准；缺的用同档最大 k、标准差按 √((k+3)/(kmax+3)) 放大
        qk = Tr.groupby(['tier', 'kk'])['res'].agg(**agg); full = {}
        for t in qk.index.get_level_values(0).unique():
            have = qk.loc[t]
            for k in KS_:
                if k in have.index: full[(t, k)] = have.loc[k]
                else:
                    r = have.loc[have.index.max()].copy(); f = np.sqrt((k + 3) / (have.index.max() + 3))
                    r['lo'] = r['mu'] + (r['lo'] - r['mu']) * f; r['hi'] = r['mu'] + (r['hi'] - r['mu']) * f; r['sd'] *= f; r['n'] = 0; full[(t, k)] = r
        q = pd.DataFrame(full).T; q.index.names = ['tier', 'kk']
    return m, cols, q, Tr
def qget(q, tier, k, col):
    if VER >= 8: return np.array([q.at[(t, k), col] for t in tier])
    return tier.map(q[col]).values if col != 'mu' else np.zeros(len(tier))

def cat_fc(T0, a):
    """品类第 a 至 a+2 月的月均销预测：去年同月 × 近 3 个月同比（算不出取 1）。"""
    g = CAT.loc[T0 - 3:T0 - 1].sum() / CAT.loc[T0 - 15:T0 - 13].sum() if T0 - 15 >= M0 else 1.0
    return np.mean([CAT.get(m - 12, np.nan) for m in range(a, a + 3)]) * g

def predict(T0):
    m, cols, q, Tr = fit(T0); D = FEAT[T0].copy(); tier = pd.Series(TIER(D['近3月'].values), index=D.index)
    for k in KS_:
        raw = m.predict(design(D, k)[cols]); D[f'预测{k}'] = raw + qget(q, tier, k, 'mu'); D[f'lo{k}'] = raw + qget(q, tier, k, 'lo'); D[f'hi{k}'] = raw + qget(q, tier, k, 'hi')
        D[f'sd{k}'] = qget(q, tier, k, 'sd')
        base = D[BASE] * D['标签占比'] * cat_fc(T0, T0 + k)
        D[f'件{k}'] = base * np.exp(D[f'预测{k}']); D[f'件lo{k}'] = base * np.exp(D[f'lo{k}']); D[f'件hi{k}'] = base * np.exp(D[f'hi{k}']); D[f'不变{k}'] = base
    sd = (D['sd3'] + D['sd6']).values / 2
    D['把握'] = norm.cdf(((D['预测3'] + D['预测6']) / 2) / sd); D['预计多卖'] = ((D['件3'] - D['不变3']) + (D['件6'] - D['不变6'])) / 2
    D['分级'] = np.select([(D['把握'] >= 0.7) & (D['预计多卖'] >= 100), (D['把握'] <= 0.3) & (D['近3月'] >= 300), D['把握'] >= 0.5], ['A', 'D', 'B'], 'C')
    D['体量档'] = tier.values
    return D, m, cols, q, Tr

# ---------- 新品层 ----------
def fam_sales46(u):
    a = A[A['单位'] == u]; L = U.at[u, 'L']; s = a.groupby('m')['c'].sum()
    return s.reindex(range(L + 3, L + 6), fill_value=0).mean()
U['月销46'] = [fam_sales46(u) for u in U.index]
def newlayer(T0):
    tr = U[U['L'] + 5 <= T0 - 1]; sc = newprod(T0, False)
    rec = tr[tr['L'] >= tr['L'].max() - 5]; r_obs, p_bar = rec['y'].mean(), sc(list(rec.index)).mean()
    shift = np.log(r_obs / (1 - r_obs)) - np.log(p_bar / (1 - p_bar)); cal = lambda us: 1 / (1 + np.exp(-(np.log(sc(us) / (1 - sc(us))) + shift)))
    vocab = sorted({t for u in tr.index for t in TK[u] if sum(t in TK[v] for v in tr.index) >= 3})
    X = lambda us: np.array([[1.0 if v in TK[u] else 0.0 for v in vocab] for u in us])
    tr46 = tr[tr['L'] + 5 <= T0 - 1]; rg = Ridge(alpha=3.0).fit(X(tr46.index), np.log1p(tr46['月销46']))
    res = np.log1p(tr46['月销46']) - rg.predict(X(tr46.index)); lo, hi = res.quantile(0.1), res.quantile(0.9)
    sales = lambda us: (np.expm1(rg.predict(X(us))), np.expm1(rg.predict(X(us)) + lo), np.expm1(rg.predict(X(us)) + hi))
    mo = tr.loc[tr['y'] == 1, '首次达线月龄'].quantile([0.25, 0.5, 0.75]).values
    return cal, sales, mo, tr

# ---------- 回测 ----------
if MODE == '回测':
    VNS = {6: '第六版', 7: '第七版', 8: '第八版'}; VN = VNS[VER]
    L = [f'# {VN}（回归预测 + 评分）回测', '',
         f'> 由 `trial/回归预测.py`（VER={VER}）生成；规则见 识别方法_预登记.md 补记{VN}（先提交、后回测）。数据到 2026-09。' + ('第七、八版的基准、特征是看过 2026 年诊断后选的，见补记第七版。' if VER >= 7 else ''),
         '> 单元 = 五个大属性的每个取值 + 两两交叉的每个格子，**全部打分**（全量）；份额按已知标签算。"把握" = 模型给的"之后份额变大"的概率；"预计多卖" = 预测销量 − 份额不变时的销量（件 / 月）。', '']
    # 主时点 2026-01
    T0 = mi('2026-01'); D, m, cols, q, Tr = predict(T0)
    for k in KS_:
        D[f'实际{k}'] = target(D, T0, k); D[f'实件{k}'] = actual_units(D, T0, k); D[f'实分母{k}'] = actual_units(D, T0, k, '分母')
        D[f'实多{k}'] = D[f'实件{k}'] - D[BASE] * D[f'实分母{k}']
    D['实际变大'] = ((D['实际3'] + D['实际6']) / 2) > 0
    D['实际多卖'] = (D['实多3'] + D['实多6']) / 2
    coef = pd.Series(m.coef_, index=cols)
    F_ = lambda x: f'{x:.1%}'
    SHROW = lambda att, v, r: (f"| {att}：{v} | {r['近3月']:,.0f} | {F_(r[BASE])} | {r['把握']:.0%} | {F_(r[BASE] * np.exp(r['预测3']))}（{F_(r[BASE] * np.exp(r['lo3']))}–{F_(r[BASE] * np.exp(r['hi3']))}） | {F_(r[BASE] * np.exp(r['实际3']))} | "
                               f"{F_(r[BASE] * np.exp(r['预测6']))}（{F_(r[BASE] * np.exp(r['lo6']))}–{F_(r[BASE] * np.exp(r['hi6']))}） | {F_(r[BASE] * np.exp(r['实际6']))} | {r['件6']:,.0f}（{r['件lo6']:,.0f}–{r['件hi6']:,.0f}） | {r['实件6']:,.0f} |")
    L += ['## 1. 回归式（站在 2026-01 估出来的系数）', '',
          f'训练样本：{len(Tr):,} 个（单元 × 时点 × 预测窗口），时点 {ms(Tr["T"].min())} 至 {ms(Tr["T"].max())}，结果都在 2025-12 前已知。', '',
          '份额对数变化 = a + θ·(k/3) + Σ (b + c·(k/3))·x。k = 往后第几个月起的 3 个月（0 = 下个季度，3 = 立项后上架那 3 个月，6 = 再往后）。', '',
          '| 特征 | 意思 | b（k = 0 时） | c（每多 3 个月加的） |', '| :--- | :--- | ---: | ---: |']
    NM = {'b6': '份额斜率（近 6 个月每月对数变化）', 'x1': '份额动量（近 3 个月对再前 3 个月）', 'x2': '新进家族（相对增长）', 'x3': '搜索同比', 'x4': '体量（ln 月均销，中心化）'}
    for x in XS: L.append(f"| {x} | {NM[x]} | {coef[x]:+.3f} | {coef[x + '·k']:+.3f} |")
    L += [f"| 截距 | | a = {m.intercept_:+.3f} | θ = {coef['k']:+.3f} |", '', '80% 区间（训练残差 10% / 90% 分位，对数；第八版按体量档 × k，预测值加上纠偏）：']
    for t, r in q.iterrows(): L.append(f"- {t if isinstance(t, str) else f'{t[0]} 件、k = {t[1]}'}：{r.lo:+.2f} 至 {r.hi:+.2f}（约 ×{np.exp(r.lo):.2f} 至 ×{np.exp(r.hi):.2f}），纠偏 {r.mu:+.2f}，标准差 {r.sd:.2f}，{int(r.n)} 个样本")
    L += ['', '## 2. 站在 2026-01，预测和 2026-04 至 2026-09 的实际比', '',
          '| 预测窗口 | 体量档 | 单元数 | 预测和实际份额变化的秩相关 | 方向对的比例 | 80% 区间覆盖 | 误差 / "份额不变"误差 |', '| :--- | :--- | ---: | ---: | ---: | ---: | ---: |']
    for k in KS_:
        Dk = D.dropna(subset=[f'实际{k}'])
        for t in ('全部', '<300', '300–1,000', '≥1,000'):
            d = Dk if t == '全部' else Dk[Dk['体量档'] == t]
            if len(d) < 5: continue
            rho = spearmanr(d[f'预测{k}'], d[f'实际{k}'])[0]; nz = d[f'实际{k}'].abs() > 0.05
            dirn = (np.sign(d.loc[nz, f'预测{k}']) == np.sign(d.loc[nz, f'实际{k}'])).mean(); cov = d[f'实际{k}'].between(d[f'lo{k}'], d[f'hi{k}']).mean()
            ratio = (d[f'实际{k}'] - d[f'预测{k}']).abs().mean() / d[f'实际{k}'].abs().mean()
            L.append(f"| {ms(T0 + k)} 至 {ms(T0 + k + 2)} | {t} | {len(d)} | {rho:+.2f} | {dirn:.0%} | {cov:.0%} | {ratio:.2f} |")
    L += ['', '方向对的比例只算实际变化超过 ±5% 的单元。误差比 < 1 说明比"份额不变"更准。', '',
          '品类总量预测（去年同月 × 近 3 个月同比）和实际：' + '；'.join(f"{ms(T0 + k)} 至 {ms(T0 + k + 2)} 预测月均 {cat_fc(T0, T0 + k):,.0f}、实际 {CAT.loc[T0 + k:T0 + k + 2].mean():,.0f}" for k in KS_)
          + '。另外 2026 年起已知标签的覆盖率明显上升（材质从约 67% 到约 88%），所以下面的"多卖"一律按份额变化 × 实际分母算，不受覆盖率和品类总量误差影响。', '',
          '## 3. 评分和结果：把握分档后，实际份额变大的比例（2026-04 至 09 平均）', '',
          '| 把握 | 单元数 | 其中 ≥ 300 件 | 实际变大的比例 | 实际多卖合计（件 / 月） |', '| :--- | ---: | ---: | ---: | ---: |']
    D['把握档'] = pd.cut(D['把握'], [0, 0.3, 0.5, 0.7, 1.0], labels=['≤30%', '30–50%', '50–70%', '≥70%'], include_lowest=True)
    for b, d in D.groupby('把握档', observed=True):
        L.append(f"| {b} | {len(d)} | {int((d['近3月'] >= 300).sum())} | {d['实际变大'].mean():.0%} | {d['实际多卖'].sum():+,.0f} |")
    big = D[D['近3月'] >= 300]
    L += ['', f"评分和结果的相关性（全部单元）：把握 vs 实际份额变化 秩相关 {spearmanr(D['把握'], (D['实际3'] + D['实际6']) / 2)[0]:+.2f}；预计多卖 vs 实际多卖 {spearmanr(D['预计多卖'], D['实际多卖'])[0]:+.2f}；"
          f"≥ 300 件的单元里分别为 {spearmanr(big['把握'], (big['实际3'] + big['实际6']) / 2)[0]:+.2f}、{spearmanr(big['预计多卖'], big['实际多卖'])[0]:+.2f}。", '',
          '## 4. 分级：A（机会）、D（坑）之后实际怎样', '', '| 分级 | 单元数 | 实际变大的比例 | 实际多卖合计（件 / 月） | 实际多卖中位 |', '| :--- | ---: | ---: | ---: | ---: |']
    for g in 'ABCD':
        d = D[D['分级'] == g]
        if len(d): L.append(f"| {g} | {len(d)} | {d['实际变大'].mean():.0%} | {d['实际多卖'].sum():+,.0f} | {d['实际多卖'].median():+,.0f} |")
    # 第三版对照：同单元第 1 层用 6 个月口径的机会分 → 用 大属性为线 的 level
    L += ['', '### A 档明细（按预计多卖排）', '', '| 单元 | 近 3 个月月均 | 近 6 个月份额 | 把握 | 预测 2026-04 至 06 份额（80% 区间） | 实际 | 预测 2026-07 至 09 份额（80% 区间） | 实际 | 预测 07 至 09 月均件（80% 区间） | 实际 |', '| :--- | ---: | ---: | ---: | :--- | ---: | :--- | ---: | :--- | ---: |']
    for (att, v), r in D[D['分级'] == 'A'].sort_values('预计多卖', ascending=False).head(20).iterrows():
        L.append(SHROW(att, v, r))
    L += ['', '### D 档（坑）明细', '', '| 单元 | 近 3 个月月均 | 近 6 个月份额 | 把握 | 预测 2026-04 至 06 份额（80% 区间） | 实际 | 预测 2026-07 至 09 份额（80% 区间） | 实际 | 预测 07 至 09 月均件（80% 区间） | 实际 |', '| :--- | ---: | ---: | ---: | :--- | ---: | :--- | ---: | :--- | ---: |']
    for (att, v), r in D[D['分级'] == 'D'].sort_values('近3月', ascending=False).head(15).iterrows():
        L.append(SHROW(att, v, r))
    L += ['', '### 之后实际多卖（按份额变化算）最多的 15 个单元，当时的评分', '', '| 单元 | 近 3 个月月均 | 当时把握 | 当时分级 | 实际多卖 |', '| :--- | ---: | ---: | :--- | ---: |']
    for (att, v), r in D.sort_values('实际多卖', ascending=False).head(15).iterrows():
        L.append(f"| {att}：{v} | {r['近3月']:,.0f} | {r['把握']:.0%} | {r['分级']} | {r['实际多卖']:+,.0f} |")
    # 其他时点
    MAIN = VER
    L += ['', '## 5. 各时点、第六、七、八版并排（只报结果窗口已走完的部分）', '', '| 版本 | 时点 | 训练样本 | 窗口 | 秩相关 全部 / ≥ 300 件 | 方向对 ≥ 300 件 | 80% 覆盖 | 把握 ≥ 70% 实际变大 / 把握 ≤ 30% 实际变大 |', '| :--- | :--- | ---: | :--- | :--- | ---: | ---: | :--- |']
    for v_, Ts in [(v_, Ts) for v_ in (6, 7, 8) for Ts in ('2025-11', '2025-12', '2026-01', '2026-02', '2026-03')]:
        set_ver(v_); T1 = mi(Ts); Dx, *_, Trx = predict(T1)
        for k in KS_:
            y = target(Dx, T1, k)
            if y.isna().all(): continue
            d = Dx.assign(y=y); b = d[d['近3月'] >= 300]; nz = b['y'].abs() > 0.05
            pk = norm.cdf(d[f'预测{k}'] / (d[f'sd{k}'] if VER >= 8 else 0.5)); hi_, lo_ = d[pk >= 0.7], d[pk <= 0.3]
            L.append(f"| {VNS[v_]} | {Ts} | {len(Trx):,} | {ms(T1 + k)} 至 {ms(T1 + k + 2)} | {spearmanr(d[f'预测{k}'], d['y'])[0]:+.2f} / {spearmanr(b[f'预测{k}'], b['y'])[0]:+.2f} | "
                     f"{(np.sign(b.loc[nz, f'预测{k}']) == np.sign(b.loc[nz, 'y'])).mean():.0%} | {d['y'].between(d[f'lo{k}'], d[f'hi{k}']).mean():.0%} | {(hi_['y'] > 0).mean():.0%}（{len(hi_)}） / {(lo_['y'] > 0).mean():.0%}（{len(lo_)}） |")
    set_ver(MAIN)
    L += ['', '这一节的把握按单个窗口算（标准差取 0.5 近似），只用来看方向；各时点训练样本互相重叠，不是独立检验。', '']
    # 新品层
    L += ['## 6. 新品层：做到概率、月销预测（T0 至 T0+3 上架、观察期已走完）', '',
          '| 时点 | 新品数 | 实际每 10 个做到 | AUC | 前 20% 是平均的几倍 | 打分前 30% / 后 30% 每 10 个做到 | 第 4–6 月月销 预测和实际秩相关 | 月销 80% 区间覆盖 |', '| :--- | ---: | :--- | ---: | ---: | :--- | ---: | ---: |']
    CAL = []
    for Ts in ('2025-10', '2025-11', '2025-12', '2026-01'):
        T1 = mi(Ts); cal, sales, mo, tr = newlayer(T1); c = U[U['L'].between(T1, T1 + 3) & (U['L'] + 5 <= END)]
        p = pd.Series(cal(list(c.index)), index=c.index); s, slo, shi = sales(list(c.index)); y = c['y']
        o = p.sort_values(ascending=False); k = max(1, round(0.2 * len(p))); top = y[o.index[:k]].mean() / y.mean()
        h, l_ = p >= p.quantile(0.7), p <= p.quantile(0.3); act = c['月销46']
        L.append(f"| {Ts} | {len(c)} | {in10(y.mean())} | {roc_auc_score(y, p):.2f} | {top:.1f} | {in10(y[h].mean())} / {in10(y[l_].mean())} | {spearmanr(s, act)[0]:+.2f} | {np.mean((act >= slo) & (act <= shi)):.0%} |")
        if Ts == '2026-01': CAL = (p, y, mo, c, s, slo, shi)
    p, y, mo, c, s, slo, shi = CAL
    L += ['', '站在 2026-01 的做到概率校准（2026-01 至 04 上架的新品）：', '', '| 模型说每 10 个做到 | 新品数 | 实际每 10 个做到 |', '| :--- | ---: | :--- |']
    for b, g in pd.cut(p, [0, 0.25, 0.4, 0.55, 1.0], labels=['< 2.5', '2.5–4', '4–5.5', '≥ 5.5']).groupby(pd.cut(p, [0, 0.25, 0.4, 0.55, 1.0], labels=['< 2.5', '2.5–4', '4–5.5', '≥ 5.5']), observed=True):
        L.append(f"| {b} | {len(g)} | {in10(y[g.index].mean())} |")
    L += ['', f'做到的时间（训练里做到的家族）：首次达线一般在上架后第 {mo[0]:.0f}–{mo[2]:.0f} 个月，中位第 {mo[1]:.0f} 个月。']
    out = os.path.join(ROOT, f'solution-v2/开发建议/回归预测_回测{ {6: "", 7: "_第七版", 8: "_第八版"}[VER] }.md'); open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L))
