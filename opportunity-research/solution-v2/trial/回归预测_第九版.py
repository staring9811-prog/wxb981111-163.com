"""第九版：立项后 6–10 个月 + 新品占比 + 新品校准方式（规则见 识别方法_预登记.md 补记第九版）。
复用 回归预测.py 的库部分（VER=9）。MODE=回测 → solution-v2/开发建议/回归预测_回测_第九版.md；MODE=建议 ASOF=yyyy-mm → 回归预测_第九版_<ASOF>.md。"""
import os, numpy as np, pandas as pd
from scipy.stats import spearmanr, norm
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
HERE = os.path.dirname(os.path.abspath(__file__)); MODE9 = os.environ.get('MODE', '回测'); ASOF9 = os.environ.get('ASOF', '2026-10')
os.environ['VER'] = '9'; os.environ['MODE'] = '库'
P = os.path.join(HERE, '回归预测.py'); src = open(P, encoding='utf-8').read()
G = {'__file__': P}; exec(compile(src[:src.index('# ---------- 回测')], P, 'exec'), G)
globals().update({k: v for k, v in G.items() if not k.startswith('__')})
MODE, ASOF = MODE9, ASOF9
VNS = {8: '第八版', 9: '第九版'}

# ---------- 新品层：三种校准 ----------
def newlayer9(T0, how):
    tr = U[U['L'] + 5 <= T0 - 1]; sc = newprod(T0, False); lg = lambda p: np.log(p / (1 - p))
    rec = tr[tr['L'] >= tr['L'].max() - 5]; p_bar = sc(list(rec.index)).mean()
    if how == 'a': r = rec['y'].mean()
    elif how == 'b': r = tr['y'].mean(); p_bar = sc(list(tr.index)).mean()
    else:
        m = LogisticRegression(C=1e6, max_iter=5000).fit(tr[['L']].values - tr['L'].max(), tr['y'].values)
        r = m.predict_proba(np.array([[T0 + 8 - tr['L'].max()]]))[0, 1]
    shift = lg(r) - lg(p_bar)
    return lambda us: 1 / (1 + np.exp(-(lg(sc(us)) + shift))), tr
def cohort9(T0): return U[U['L'].between(T0 + 6, T0 + 10) & (U['L'] + 5 <= END)]

def mkt_eval(T0, v):
    set_ver(v); D, m, cols, q, Tr = predict(T0); res = {}
    for k in (6, 8):
        if T0 + k + 2 > END or f'预测{k}' not in D: continue
        y = target(D, T0, k); d = D.assign(y=y); b = d[d['近3月'] >= 300]; nz = b['y'].abs() > 0.05
        pk = norm.cdf(d[f'预测{k}'] / d[f'sd{k}']) if f'sd{k}' in d else None
        res[k] = dict(n=len(d), rho=spearmanr(d[f'预测{k}'], d['y'])[0], rho300=spearmanr(b[f'预测{k}'], b['y'])[0],
                      dirn=(np.sign(b.loc[nz, f'预测{k}']) == np.sign(b.loc[nz, 'y'])).mean(), cov=d['y'].between(d[f'lo{k}'], d[f'hi{k}']).mean(),
                      hi=((d.loc[pk >= 0.7, 'y'] > 0).mean(), int((pk >= 0.7).sum())), lo=((d.loc[pk <= 0.3, 'y'] > 0).mean(), int((pk <= 0.3).sum())))
    set_ver(9); return res, D, m, cols, q, Tr

if MODE == '回测':
    L = ['# 第九版（立项后 6–10 个月 · 新品占比 · 新品校准）回测', '',
         '> 由 `trial/回归预测_第九版.py` 生成；规则见 识别方法_预登记.md 补记第九版（先提交、后回测）。数据到 2026-09。立项到上架约 8 个月（wen 2026-11-03），所以看立项后第 6–8、8–10 个月。',
         '> x5 新品占比和窗口是看过 2026 年诊断后定的，严格检验要等 2026-10 起的数据。', '']
    T0 = mi('2026-01'); _, D, m, cols, q, Tr = mkt_eval(T0, 9)
    coef = pd.Series(m.coef_, index=cols)
    NM = {'b6': '份额斜率（近 6 个月每月对数变化）', 'x2': '新进家族（相对增长）', 'x3': '搜索同比', 'x4': '体量（ln 月均销，中心化）', 'x5': '新品占比（近 6 个月新上架家族的销量占比 − 品类整体）'}
    L += ['## 1. 回归式（站在 2026-01 估出来的系数）', '', f'训练样本 {len(Tr):,} 个（单元 × 时点 × 窗口），时点 {ms(Tr["T"].min())} 至 {ms(Tr["T"].max())}，窗口 k ∈ {{0, 3, 6, 8}} 中结果在 2025-12 前已知的；k = 6 只有 2025-04 一个时点、k = 8 没有，靠按 k 线性外推。', '',
          '份额对数变化 = a + θ·(k/3) + Σ (b + c·(k/3))·x + 按（体量档, k）的纠偏。', '', '| 特征 | 意思 | b（k = 0） | c（每多 3 个月） | k = 6 时合计 | k = 8 时合计 |', '| :--- | :--- | ---: | ---: | ---: | ---: |']
    for x in XS: L.append(f"| {x} | {NM[x]} | {coef[x]:+.3f} | {coef[x + '·k']:+.3f} | {coef[x] + 2 * coef[x + '·k']:+.3f} | {coef[x] + 8 / 3 * coef[x + '·k']:+.3f} |")
    L += [f"| 截距 | | a = {m.intercept_:+.3f} | θ = {coef['k']:+.3f} | | |", '']
    # 2. 各时点、第八版 vs 第九版
    L += ['## 2. 市场层：各时点，第八版和第九版并排', '', '| 时点 | 窗口（立项后） | 版本 | 秩相关 全部 / ≥ 300 件 | 方向对 ≥ 300 件 | 80% 覆盖 | 把握 ≥ 70% 之后变大（个数） | 把握 ≤ 30% 之后变大（个数） |', '| :--- | :--- | :--- | :--- | ---: | ---: | :--- | :--- |']
    for Ts in ('2025-10', '2025-11', '2025-12', '2026-01'):
        T1 = mi(Ts)
        for v in (8, 9):
            res = mkt_eval(T1, v)[0]
            for k, r in res.items():
                L.append(f"| {Ts} | 第 {k}–{k + 2} 个月（{ms(T1 + k)} 至 {ms(T1 + k + 2)}） | {VNS[v]} | {r['rho']:+.2f} / {r['rho300']:+.2f} | {r['dirn']:.0%} | {r['cov']:.0%} | "
                         f"{r['hi'][0]:.0%}（{r['hi'][1]}） | {r['lo'][0]:.0%}（{r['lo'][1]}） |".replace('nan%', '—'))
    L += ['', '第八版没有 k = 8 的窗口，只比 k = 6。', '']
    # 3. 主时点 2026-01：评分和结果（k = 6 已知）
    D['y6'] = target(D, T0, 6); D['实件6'] = actual_units(D, T0, 6); D['实分母6'] = actual_units(D, T0, 6, '分母')
    D['实际多卖'] = D['实件6'] - D[BASE] * D['实分母6']; D['变大'] = D['y6'] > 0
    D['预计多卖6'] = D['件6'] - D['不变6']
    D['把握档'] = pd.cut(D['把握'], [0, 0.3, 0.5, 0.7, 1.0], labels=['≤30%', '30–50%', '50–70%', '≥70%'], include_lowest=True)
    L += ['## 3. 站在 2026-01：评分和立项后第 6–8 个月（2026-07 至 09）的实际', '', '| 把握 | 单元数 | 其中 ≥ 300 件 | 实际份额变大的比例 | 实际多卖合计（件 / 月） |', '| :--- | ---: | ---: | ---: | ---: |']
    for b_, d in D.groupby('把握档', observed=True): L.append(f"| {b_} | {len(d)} | {int((d['近3月'] >= 300).sum())} | {d['变大'].mean():.0%} | {d['实际多卖'].sum():+,.0f} |")
    big = D[D['近3月'] >= 300]
    L += ['', f"相关性：把握 vs 实际份额变化 {spearmanr(D['把握'], D['y6'])[0]:+.2f}（≥ 300 件 {spearmanr(big['把握'], big['y6'])[0]:+.2f}）；预计多卖 vs 实际多卖 {spearmanr(D['预计多卖6'], D['实际多卖'])[0]:+.2f}（≥ 300 件 {spearmanr(big['预计多卖6'], big['实际多卖'])[0]:+.2f}）。", '',
          '| 分级 | 单元数 | 实际变大的比例 | 实际多卖合计 | 实际多卖中位 |', '| :--- | ---: | ---: | ---: | ---: |']
    for g in 'ABCD':
        d = D[D['分级'] == g]
        if len(d): L.append(f"| {g} | {len(d)} | {d['变大'].mean():.0%} | {d['实际多卖'].sum():+,.0f} | {d['实际多卖'].median():+,.0f} |")
    # 4. 大机会召回：第八版 vs 第九版
    set_ver(8); D8 = predict(T0)[0]; set_ver(9)
    L += ['', '## 4. 之后实际多卖最多的 15 个单元（2026-07 至 09），站在 2026-01 两版给的评分', '', '| 单元 | 近 3 个月月均 | 新品占比（相对品类） | 实际多卖 | 第八版 把握 / 分级 | 第九版 把握 / 分级 |', '| :--- | ---: | ---: | ---: | :--- | :--- |']
    for (att, v), r in D.sort_values('实际多卖', ascending=False).head(15).iterrows():
        r8 = D8.loc[(att, v)]
        L.append(f"| {att}：{v} | {r['近3月']:,.0f} | {r['x5']:+.0%} | {r['实际多卖']:+,.0f} | {r8['把握']:.0%} / {r8['分级']} | {r['把握']:.0%} / {r['分级']} |")
    top15 = D.sort_values('实际多卖', ascending=False).head(15).index
    L += ['', f"这 15 个的平均把握：第八版 {D8.loc[top15, '把握'].mean():.0%}，第九版 {D.loc[top15, '把握'].mean():.0%}；给到 A / B 的：第八版 {int(D8.loc[top15, '分级'].isin(['A', 'B']).sum())} 个，第九版 {int(D.loc[top15, '分级'].isin(['A', 'B']).sum())} 个。", '']
    # 5. 新品层
    L += ['## 5. 新品层：立项时点 T0 的新品按 T0+6 至 T0+10 上架算', '', '| T0 | 训练新家族 | 检验新家族 | 实际每 10 个做到 | AUC | 打分前 30% / 后 30% 每 10 个 | 模型平均每 10 个：(a) 最近半年 / (b) 全部 / (c) 趋势外推 | 用途 |', '| :--- | ---: | ---: | :--- | ---: | :--- | :--- | :--- |']
    ERR = {'a': [], 'b': [], 'c': []}; ROWS = []
    for Ts in ('2025-06', '2025-07', '2025-08', '2025-09', '2025-10'):
        T1 = mi(Ts); c = cohort9(T1)
        if len(c) < 10: continue
        cals = {h: newlayer9(T1, h) for h in 'abc'}; tr = cals['a'][1]
        ps = {h: pd.Series(cals[h][0](list(c.index)), index=c.index) for h in 'abc'}; y = c['y']; p = ps['a']
        use = '选择' if Ts <= '2025-08' else '检验'
        if use == '选择':
            for h in 'abc': ERR[h].append(abs(ps[h].mean() - y.mean()))
        L.append(f"| {Ts} | {len(tr)} | {len(c)} | {in10(y.mean())} | {roc_auc_score(y, p):.2f} | {in10(y[p >= p.quantile(0.7)].mean())} / {in10(y[p <= p.quantile(0.3)].mean())} | "
                 f"{in10(ps['a'].mean())} / {in10(ps['b'].mean())} / {in10(ps['c'].mean())} | {use} |")
    best = min(ERR, key=lambda h: np.mean(ERR[h]))
    L += ['', f"按预登记规则在 2025-06 至 08 上选：平均绝对误差（每 10 个）(a) {np.mean(ERR['a']) * 10:.1f}、(b) {np.mean(ERR['b']) * 10:.1f}、(c) {np.mean(ERR['c']) * 10:.1f}，选 **({best})**。", '']
    out = os.path.join(ROOT, 'solution-v2/开发建议/回归预测_回测_第九版.md'); open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L))
