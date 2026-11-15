"""第一、二、三版机会识别并排比较（口径见 识别方法_预登记.md 补记）。
第一版 = 只看新品成败（类型排序 = 该类型历史新家族的平均做到概率）；第二版 = 三项信号百分位等权；第三版 = 前 6 个月月均销 × (合成分位 − 0.5)。
结果：类型 = T+3 至 T+8 月均销 − 前 6 个月月均销（实际增量）；新品 = T 至 T+3 上架的新家族做到没有。输出 solution-v2/开发建议/版本对比.md。"""
import os, numpy as np, pandas as pd
from scipy.stats import spearmanr
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
os.environ['MODE'] = '库'
P = os.path.join(HERE, '两层识别.py'); ns = {'__file__': P}
exec(compile(open(P, encoding='utf-8').read(), P, 'exec'), ns)
mi, ms, market, outcome, newprod, cohort, feat, U = (ns[k] for k in ('mi', 'ms', 'market', 'outcome', 'newprod', 'cohort', 'feat', 'U'))
CROSS = [('尺寸', '台面'), ('尺寸', '元素'), ('台面', '元素')]
def fam_keys(u):
    f = feat[u]; get = {'尺寸': f['主尺寸段'], '台面': f['台面类型'], '元素': [e for e in f['元素'] if e not in ('fluted', 'reeded', '未知')]}
    return [(k, (x, y)) for k in CROSS for x in get[k[0]] for y in get[k[1]]]
in10 = lambda v: '—' if pd.isna(v) else f'{v * 10:.1f}'.rstrip('0').rstrip('.')
L = ['# 机会识别：第一、二、三版并排比较', '',
     '> 由 `trial/版本对比.py` 生成，口径见 识别方法_预登记.md 补记（2026-11-02 先提交、后比较）。只比交叉类型：尺寸 × 台面、尺寸 × 元素、台面 × 元素。',
     '> 另加一个基准"只看体量"（按前 6 个月月均销排，不看任何增长信号），看第三版的增长信号有没有在体量之外多挑对。'
     '> 第一版 = 只看新品成败；第二版 = 增长率排位（三项信号等权）；第三版 = 体量 × 增长（前 6 个月月均销 × (合成分位 − 0.5)）。实际增量 = 立项后约 3–8 个月（T+3 至 T+8）的月均销 − 前 6 个月月均销，件 / 月。', '',
     '## 1. 类型层面：谁更能挑出之后真正多卖出来的类型', '',
     '| 时点 | 版本 | 排序和实际增量的秩相关 | 实际增量最大的 10 个里，排进前 10 的 | 排的前 10 里，之后实际减少的 | 排的前 10 合计实际增量（件 / 月） |', '| :--- | :--- | ---: | :--- | :--- | ---: |']
FAM = {}; TOP = {}
for Ts in ('2025-10', '2025-11', '2025-12', '2026-01'):
    T = mi(Ts); M = outcome(market(T), T); M = M[M['类型'].isin(CROSS) & (M['月均销_前'] > 0)].copy()
    M['实际增量'] = M['月均销_后'] - M['月均销_前']
    s1 = newprod(T, False); tr = U[U['L'] + 5 <= T - 1]; ptr = pd.Series(s1(list(tr.index)), index=tr.index)
    v1 = {}
    for u in tr.index:
        for k in fam_keys(u): v1.setdefault(k, []).append(ptr[u])
    M['第一版'] = [np.mean(v1[(k, kk)]) if (k, kk) in v1 else np.nan for k, kk in zip(M['类型'], M['键'])]
    M['第二版'] = M['合成分位']; M['第三版'] = M['月均销_前'] * (M['合成分位'] - 0.5); M['基准：只看体量'] = M['月均销_前']
    real10 = set(M.nlargest(10, '实际增量').index)
    for v in ('第一版', '第二版', '第三版', '基准：只看体量'):
        d = M.dropna(subset=[v]); rho = spearmanr(d[v], d['实际增量'])[0]; top = d.nlargest(10, v)
        L.append(f"| {Ts} | {v} | {rho:+.2f} | {len(real10 & set(top.index))} / 10 | {int((top['实际增量'] < 0).sum())} / 10 | {top['实际增量'].sum():+,.0f} |")
        if Ts == '2026-01' and not v.startswith('基准'): TOP[v] = top
    # 新品层面：每个版本的"建议上 / 避开"
    c = cohort(T); s2 = newprod(T, True); p = pd.Series(s2(list(c.index)), index=c.index); ptr2 = pd.Series(s2(list(tr.index)), index=tr.index)
    avg, lo20 = ptr2.mean(), ptr2.quantile(0.2); p1 = pd.Series(s1(list(c.index)), index=c.index)
    for v in ('第二版', '第三版'):
        pc = M.set_index(['类型', '键'])[v].rank(pct=True)
        mk = pd.Series([np.mean([pc[k] for k in fam_keys(u) if k in pc.index]) if any(k in pc.index for k in fam_keys(u)) else np.nan for u in c.index], index=c.index)
        rec = (mk >= 0.7) & (p >= avg); avd = (mk <= 0.3) | (p <= lo20)
        FAM.setdefault(Ts, {})[v] = (rec, avd)
    q7, q3 = ptr.quantile(0.7), ptr.quantile(0.3)
    FAM[Ts]['第一版'] = (p1 >= q7, p1 <= q3)
    FAM[Ts]['_y'] = c['y']
L += ['', '## 2. 新品层面：每个版本"建议上 / 避开"的新品，实际做到的比例（T 至 T+3 上架、观察期已走完）', '',
      '第一版：新品打分在学习数据前 30% = 建议上，后 30% = 避开。第二、三版：市场分位 ≥ 70% 且新品打分 ≥ 平均 = 建议上；市场分位 ≤ 30% 或新品打分在后 20% = 避开。', '',
      '| 时点 | 全部 每 10 个做到 | 第一版 建议上 / 避开 | 第二版 建议上 / 避开 | 第三版 建议上 / 避开 |', '| :--- | :--- | :--- | :--- | :--- |']
for Ts, d in FAM.items():
    y = d['_y']; f = lambda m: f"{int(y[m].sum())}/{int(m.sum())}（{in10(y[m].mean()) if m.any() else '—'}）"
    L.append(f"| {Ts} | {in10(y.mean())}（{len(y)} 个） | " + ' | '.join(f"{f(d[v][0])} / {f(d[v][1])}" for v in ('第一版', '第二版', '第三版')) + ' |')
L += ['', '各时点的新家族有重叠（上架窗口 4 个月、时点隔 1 个月），不是独立样本。', '',
      '## 3. 站在 2026-01，各版排的前 10 个类型，之后实际怎样', '']
for v, top in TOP.items():
    L += [f'### {v}', '', '| 类型 | 前 6 个月月均销 | 之后月均销 | 实际增量 |', '| :--- | ---: | ---: | ---: |']
    for r in top.itertuples(): L.append(f"| {' × '.join(r.类型)}：{r.取值} | {r.月均销_前:,.0f} | {r.月均销_后:,.0f} | {r.实际增量:+,.0f} |")
    L += ['']
M = outcome(market(mi('2026-01')), mi('2026-01')); M = M[M['类型'].isin(CROSS)]; M['实际增量'] = M['月均销_后'] - M['月均销_前']
L += ['### 对照：之后实际增量最大的 10 个类型', '', '| 类型 | 前 6 个月月均销 | 之后月均销 | 实际增量 | 第二版排位 | 第三版机会分排位 |', '| :--- | ---: | ---: | ---: | ---: | ---: |']
M['v3'] = (M['月均销_前'] * (M['合成分位'] - 0.5)).rank(ascending=False)
M['v2'] = M['合成分位'].rank(ascending=False)
for r in M.nlargest(10, '实际增量').itertuples():
    L.append(f"| {' × '.join(r.类型)}：{r.取值} | {r.月均销_前:,.0f} | {r.月均销_后:,.0f} | {r.实际增量:+,.0f} | 第 {r.v2:.0f} | 第 {r.v3:.0f} |")
out = os.path.join(ROOT, 'solution-v2/开发建议/版本对比.md'); open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L))
