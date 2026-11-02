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
FEAT = {T: feats(T) for T in range(M0 + 6, END + 2)}
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

# ---------- 建议：全量评分 + 新品方案 + "实"的结论 ----------
if MODE == '建议':
    T0 = mi(ASOF); D, m, cols, q, Tr = predict(T0); KN = [k for k in KS_ if T0 + k + 2 <= END]
    for k in KN:
        D[f'实际{k}'] = target(D, T0, k); D[f'实件{k}'] = actual_units(D, T0, k)
    W = lambda k: f'{ms(T0 + k)} 至 {ms(T0 + k + 2)}'; F_ = lambda x: f'{x:.1%}'
    D['斜率'] = np.expm1(D['b6'])
    full = D.reset_index()[['层', '属性', '取值', '近3月', BASE, '斜率', 'x2', 'S3', '把握', '预计多卖', '分级', '体量档'] + [f'{a}{k}' for k in KS_ for a in ('件', '件lo', '件hi')] + [f'{a}{k}' for k in KN for a in ('实际', '实件')]]
    for k in KS_:
        full[f'份额{k}'] = D[BASE].values * np.exp(D[f'预测{k}'].values); full[f'份额lo{k}'] = D[BASE].values * np.exp(D[f'lo{k}'].values); full[f'份额hi{k}'] = D[BASE].values * np.exp(D[f'hi{k}'].values)
    full = full.sort_values(['层', '属性', '预计多卖'], ascending=[False, True, False])
    full.to_csv(os.path.join(ROOT, f'solution-v2/开发建议/回归预测_{ASOF}_全量评分.csv'), index=False, encoding='utf-8-sig')
    cover = {d: PAN[(d,)][2].loc[T0 - 6:T0 - 1].sum() / CAT.loc[T0 - 6:T0 - 1].sum() for d in DIMS}
    L = [f'# 开发建议（第八版 · 回归预测 + 评分）：站在 {ASOF} 月初', '',
         f'> 只用截至 {ms(T0 - 1)} 的数据。由 `trial/回归预测.py`（MODE=建议 ASOF={ASOF}）生成；方法见 识别方法_预登记.md 补记第六至八版，回测见 回归预测_回测_第八版.md。', '',
         '## 怎么读', '',
         f'- **全量还是片面**：五个大属性的每个取值、两两交叉的每个格子都打了分，共 {len(D)} 个单元，全部在 `回归预测_{ASOF}_全量评分.csv`，本页只摘要。'
         f'各属性有标签的销量占全部销量：' + '、'.join(f'{d} {v:.0%}' for d, v in cover.items()) + '，没标签的部分不在评分里。近 3 个月月均 < 300 件的单元也打了分，但回测里方向准确率低，只作参考。',
         '- **把握** = 回归模型给的"之后份额会变大"的概率。回测（站在 2026-01，看 2026-04 至 09）：把握 ≤ 30% 的单元，之后 22% 真的变大；30–50% 是 43%；50–70% 是 56%；≥ 70% 是 65%。',
         '- **分级**：A = 把握 ≥ 70% 且预计每月多卖 ≥ 100 件（机会）；D = 把握 ≤ 30% 且月均 ≥ 300 件（坑）；B / C = 把握高于 / 低于 50%。回测：A 档 83% 份额变大，D 档只有 20% 变大、合计每月少卖 1.2 万件。',
         '- **预测份额 / 件数**带 80% 区间。件数 = 预测份额 × 品类月销预测（去年同月 × 近 3 个月同比）。2026 年数据来源切换后品类总量偏高约 20%，所以件数看相对大小，份额更可靠。',
         f'- **时间**：k = 3 窗口（{W(3)}）= 现在立项、约 3 个月后上架的那段时间；k = 6 窗口（{W(6)}）= 再往后 3 个月。', '']
    def row(r, att, v):
        s = f"| {v} | {r['近3月']:,.0f} | {F_(r[BASE])} | {r['斜率']:+.1%} | {r['把握']:.0%} | **{r['分级']}** | {F_(r[BASE] * np.exp(r['预测3']))}（{F_(r[BASE] * np.exp(r['lo3']))}–{F_(r[BASE] * np.exp(r['hi3']))}） | {F_(r[BASE] * np.exp(r['预测6']))}（{F_(r[BASE] * np.exp(r['lo6']))}–{F_(r[BASE] * np.exp(r['hi6']))}） | {r['件6']:,.0f}（{r['件lo6']:,.0f}–{r['件hi6']:,.0f}） |"
        if 6 in KN: s += f" {F_(r[BASE] * np.exp(r['实际6']))} / {r['实件6']:,.0f} |"
        return s
    HD = f"| 取值 | 近 3 个月月均 | 近 6 个月份额 | 份额每月变化 | 把握 | 分级 | 预测份额 {W(3)}（80% 区间） | 预测份额 {W(6)} | 预测月均件 {W(6)} |" + (' 实际 份额 / 件 |' if 6 in KN else '')
    SEP = '| :--- | ---: | ---: | ---: | ---: | :--- | :--- | :--- | :--- |' + (' :--- |' if 6 in KN else '')
    for d in DIMS:
        X = D.xs(d, level='属性').sort_values('近3月', ascending=False)
        L += [f'## 大属性 · {d}（全部取值）', '', HD, SEP] + [row(r, d, v) for v, r in X.iterrows()] + ['']
    G = D[D['层'] == '两维格子']
    L += ['## 两维格子：A 档（机会）全部、B 档预计多卖前 10、D 档（坑）全部', '', HD.replace('| 取值 |', '| 格子 |'), SEP]
    for g, sel in (('A', G[G['分级'] == 'A'].sort_values('预计多卖', ascending=False)), ('B', G[G['分级'] == 'B'].sort_values('预计多卖', ascending=False).head(10)), ('D', G[G['分级'] == 'D'].sort_values('近3月', ascending=False))):
        L += [row(r, att, f'{att}：{v}') for (att, v), r in sel.iterrows()]
    L += ['']
    # 新品方案
    cal, sales, mo, tr = newlayer(T0)
    SZ = [v for v in D.xs('尺寸', level='属性').index if D.at[('尺寸', v), '近3月'] >= 300]
    ELS = [e for e in D.xs('元素', level='属性').sort_values('近3月', ascending=False).index[:10]]
    TOPS = [v for v in D.xs('台面', level='属性').index if D.at[('台面', v), '近3月'] >= 300]
    COLS = [v for v in D.xs('主色', level='属性').sort_values('近3月', ascending=False).index[:7]]
    price = pd.DataFrame({'s': [feat[u]['主尺寸段'][0] for u in tr.index], '档': [feat[u]['价格档'][0] for u in tr.index], 'p': tr['_中位价'].values}).groupby(['s', '档'])['p'].quantile([0.25, 0.75]).unstack()
    combo = pd.DataFrame([((feat[u]['主尺寸段'][0], feat[u]['台面类型'][0], e), tr.at[u, 'y']) for u in tr.index for e in feat[u]['元素']], columns=['k', 'y']).groupby('k')['y'].agg(['size', 'sum'])
    rows = []
    for s, tr_, tp, el, c in itertools.product(SZ, ('低', '中', '高'), TOPS, ELS, COLS):
        k_ = f'方案|{s}|{tr_}|{tp}|{el}|{c}'; TK[k_] = [f'尺寸={s}', f'档={tr_}', f'台面={tp}', f'主色={c}', '装=拆装', '形态=落地式', f'元素={el}', '颜色≥2', '子体≥4']
        TK[k_ + '|少铺'] = TK[k_][:-2]; rows.append(dict(尺寸=s, 档=tr_, 台面=tp, 元素=el, 主色=c, k=k_))
    Cn = pd.DataFrame(rows); Cn['p'] = cal(list(Cn['k'])); Cn['p少铺'] = cal([k + '|少铺' for k in Cn['k']])
    sv, slo, shi = sales(list(Cn['k'])); Cn['件'], Cn['件lo'], Cn['件hi'] = sv, slo, shi
    Cn['先例'] = [int(combo['size'].get((r.尺寸, r.台面, r.元素), 0)) for r in Cn.itertuples()]; Cn['先例做到'] = [int(combo['sum'].get((r.尺寸, r.台面, r.元素), 0)) for r in Cn.itertuples()]
    g_ = lambda att, v: D.at[(att, v), '分级'] if (att, v) in D.index else '—'
    Cn['市场'] = [f"尺寸 {g_('尺寸', r.尺寸)} · 台面 {g_('台面', r.台面)} · 主色 {g_('主色', r.主色)} · 元素 {g_('元素', r.元素)} · 尺寸×台面 {g_('尺寸 × 台面', f'{r.尺寸} × {r.台面}')}" for r in Cn.itertuples()]
    avg = cal(list(tr.index)).mean()
    pr = lambda s, t_: f"${price.at[(s, t_), 0.25]:.0f}–{price.at[(s, t_), 0.75]:.0f}" if (s, t_) in price.index else '价位无先例'
    smo = tr[tr['y'] == 1].assign(s=[feat[u]['主尺寸段'][0] for u in tr[tr['y'] == 1].index]).groupby('s')['首次达线月龄'].median()
    trs = tr.assign(s=[feat[u]['主尺寸段'][0] for u in tr.index])
    q46 = lambda s, y_: trs[(trs['s'] == s) & (trs['y'] == y_)]['月销46'].quantile([0.25, 0.5, 0.75]).values
    def sell(s):
        a, b = q46(s, 1), q46(s, 0)
        return f"{a[1]:,.0f}（{a[0]:,.0f}–{a[2]:,.0f}）/ {b[1]:,.0f}" if not np.isnan(a[1]) else '—'
    best = Cn[Cn['先例'] >= 3].sort_values('p', ascending=False).drop_duplicates(['尺寸', '台面', '元素']).head(12)
    worst = Cn[Cn['先例'] >= 3].sort_values('p').drop_duplicates(['尺寸', '台面', '元素']).head(6)
    L += ['## 新品方案：在什么情况下、多久、卖到多少', '',
          f'- 打分 = 做到概率（做到 = 上架 6 个月内小类前 50 或月销售额 $10 万），按最近半年上架的新品水平校准；当期平均每 10 个做到 {in10(avg)} 个。回测：AUC 0.62–0.66，打分前 30% 每 10 个做到 4.7–5.7，后 30% 2.4–2.9。',
          f'- 月销 = 上架第 4–6 个月的月均件数。新品销量两极分化（做到的和没做到的差几倍），所以按情形给：同尺寸历史新家族里做到的、没做到的各卖多少。（直接回归月销和实际的秩相关 +0.29 至 +0.42，但 80% 区间宽到几十倍，不用。）做到的时间：训练里做到的家族一般第 {mo[0]:.0f}–{mo[2]:.0f} 个月首次达线。',
          '- 默认条件：落地式、拆装、首月 ≥ 2 个颜色、≥ 4 个子体。只列 尺寸 × 台面 × 元素 有 ≥ 3 个历史新家族的方案（有依据）；"市场"列是这个方案各属性在上面市场评分里的分级。', '',
          '| # | 方案 | 价位（同尺寸同档 25–75%） | 每 10 个做到（打分） | 只铺 1 色、≤ 2 子体时 | 上架后第 4–6 个月月均件：做到的（中位，25–75%）/ 没做到的中位 | 做到的话第几个月 | 历史先例 做到 / 家族 | 市场 |', '| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |']
    for i, r in enumerate(best.itertuples(), 1):
        L.append(f"| {i} | {r.尺寸} · {r.档}档 · {r.台面} · {r.元素} · 主色{r.主色} | {pr(r.尺寸, r.档)} | **{in10(r.p)}** | {in10(r.p少铺)} | {sell(r.尺寸)} | 第 {smo.get(r.尺寸, mo[1]):.0f} 个月 | {r.先例做到} / {r.先例} | {r.市场} |")
    L += ['', '**要避开的方案（有依据、打分最低）**', '', '| 方案 | 每 10 个做到 | 历史先例 | 市场 |', '| :--- | :--- | :--- | :--- |']
    for r in worst.itertuples():
        L.append(f"| {r.尺寸} · {r.档}档 · {r.台面} · {r.元素} · 主色{r.主色} | {in10(r.p)} | {r.先例做到} / {r.先例} | {r.市场} |")
    b1 = best.iloc[0]
    base_t = TK[b1.k]; alts = {'档': ['低', '中', '高'], '主色': COLS, '台面': TOPS, '元素': ELS, '尺寸': SZ}
    L += ['', f'## 在什么情况下：同一方案（{b1.尺寸} · {b1.档}档 · {b1.台面} · {b1.元素} · 主色{b1.主色}）换一个条件，每 10 个做到几个', '', '| 条件 | 换成 → 每 10 个做到 |', '| :--- | :--- |']
    for att, vs in alts.items():
        cells = []
        for v in vs:
            kk = f'换|{att}|{v}'; TK[kk] = [x if not x.startswith(f'{att}=') else f'{att}={v}' for x in base_t]; cells.append(f"{v} {in10(cal([kk])[0])}")
        L.append(f"| {att} | {'、'.join(cells)} |")
    for lab, drop in (('首月颜色', '颜色≥2'), ('首月子体', '子体≥4')):
        kk = f'换|{lab}'; TK[kk] = [x for x in base_t if x != drop]; L.append(f"| {lab} | 有（{drop}）{in10(b1.p)}、没有 {in10(cal([kk])[0])} |")
    L += ['', '## 一句话结论（"什么东西、什么情况下、什么时间、达到什么"）', '',
          f"1. **上什么**：{b1.尺寸} {b1.档}档（{pr(b1.尺寸, b1.档)}）{b1.台面} + {b1.元素}，主色{b1.主色}。**条件**：首月 ≥ 2 色、≥ 4 子体（只铺 1 色、≤ 2 子体时每 10 个做到从 {in10(b1.p)} 降到 {in10(b1.p少铺)}）。"
          f"**时间**：{ms(T0 + 3)} 前上架。**达到**：每 10 个约 {in10(b1.p)} 个在第 {smo.get(b1.尺寸, mo[1]):.0f} 个月左右做到小类前 50 或月销售额 $10 万；做到的话上架后第 4–6 个月月均约 {q46(b1.尺寸, 1)[1]:,.0f} 件（同尺寸做到者 25–75%：{q46(b1.尺寸, 1)[0]:,.0f}–{q46(b1.尺寸, 1)[2]:,.0f}），没做到的中位 {q46(b1.尺寸, 0)[1]:,.0f} 件（多数第 4–6 个月已掉出榜单）。"]
    A_ = D[D['分级'] == 'A'].sort_values('预计多卖', ascending=False).head(5); D_ = D[D['分级'] == 'D'].sort_values('近3月', ascending=False).head(5)
    if len(A_): L.append('2. **在涨、可以多铺的方向（A 档）**：' + '；'.join(f"{att} {v}：份额 {F_(r[BASE])} → {W(6)} 约 {F_(r[BASE] * np.exp(r['预测6']))}（{F_(r[BASE] * np.exp(r['lo6']))}–{F_(r[BASE] * np.exp(r['hi6']))}），把握 {r['把握']:.0%}" for (att, v), r in A_.iterrows()) + '。')
    if len(D_): L.append('3. **坑（D 档，少铺或不新上）**：' + '；'.join(f"{att} {v}：份额 {F_(r[BASE])} → {W(6)} 约 {F_(r[BASE] * np.exp(r['预测6']))}，把握 {r['把握']:.0%}" for (att, v), r in D_.iterrows()) + '。')
    if T0 + 3 + 5 <= END or T0 + 3 <= END:
        c = U[U['L'].between(T0, T0 + 3) & (U['L'] + 5 <= END)]
        if len(c):
            pc = pd.Series(cal(list(c.index)), index=c.index)
            keyset = lambda S_: {(r.尺寸, r.台面, r.元素) for r in S_.itertuples()}
            hit = lambda S_: [u for u in c.index if any((feat[u]['主尺寸段'][0], feat[u]['台面类型'][0], e) in keyset(S_) for e in feat[u]['元素'])]
            hb, hw = hit(best), hit(worst)
            L += ['', f'## 核对：{ASOF} 至 {ms(T0 + 3)} 上架的新家族之后怎样（{len(c)} 个，每 10 个做到 {in10(c["y"].mean())}）', '',
                  f'- 和推荐方案同"尺寸 × 台面 × 元素"的：{len(hb)} 个，做到 {int(c.loc[hb, "y"].sum())} 个' + (f'（每 10 个 {in10(c.loc[hb, "y"].mean())}）' if hb else '') + '；',
                  f'- 和避开方案同"尺寸 × 台面 × 元素"的：{len(hw)} 个，做到 {int(c.loc[hw, "y"].sum())} 个' + (f'（每 10 个 {in10(c.loc[hw, "y"].mean())}）' if hw else '') + '；',
                  f'- 按每个新家族自己的打分：前 30% 每 10 个做到 {in10(c.loc[pc >= pc.quantile(0.7), "y"].mean())}，后 30% {in10(c.loc[pc <= pc.quantile(0.3), "y"].mean())}。']
            L += ['', '按条件看这批新家族的实际（模型说 / 实际，每 10 个做到）：', '', '| 条件 | 有这个条件的新家族 | 模型说 | 实际 | 没有这个条件的 模型说 / 实际 |', '| :--- | ---: | :--- | :--- | :--- |']
            for tok in ('档=高', '档=中', '档=低', '主色=原木', '主色=深木', '主色=白', '主色=黑', '主色=灰', '颜色≥2', '子体≥4', '台面=陶瓷一体', '台面=树脂一体', '台面=石材台面'):
                w = [u for u in c.index if tok in TK[u]]; wo = [u for u in c.index if tok not in TK[u]]
                if len(w) >= 4: L.append(f"| {tok} | {len(w)} | {in10(pc[w].mean())} | {in10(c.loc[w, 'y'].mean())} | {in10(pc[wo].mean())} / {in10(c.loc[wo, 'y'].mean())} |")
    out = os.path.join(ROOT, f'solution-v2/开发建议/回归预测_{ASOF}.md'); open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L))
