"""开发建议（按时点）：站在 ASOF 月月初，只用到上个月为止的数据，给出"上什么样的新品、大概率几个月做到什么、什么时候上"。
做法：
1. 学习数据：截至时点、6 个月观察期已走完的新家族（单位、分母、成功、首月特征都沿用 回归_新家族.py 第 0–3 节，数据先截到 ASOF 前一个月）。
2. 做到的概率：L2 逻辑回归，只用开发能定的属性（主尺寸段、价格档、台面类型、元素、主色、装、形态、首月颜色 ≥ 2、首月子体 ≥ 4），
   强度用 5 折交叉验证选；候选方案 = 主要尺寸 × 价格档 × 台面 × 元素 × 主色（默认落地式、拆装、≥ 2 个颜色、≥ 4 个子体），区间用 200 次自助重抽。
3. 做到以后：同主尺寸段里做到的新家族，第几个月首次做到、观察期最高月销量 / 月销售额的中位数和四分位。
4. 市场：各尺寸段近 6 个月的销量份额和变化、新家族数、近期新家族做到的比例；关键词（研究包，有宽度的词）的搜索份额、同比和"搜索份额 − 销量份额"。
5. 上架时间：关键词总搜索量按月的季节指数（2022-01 起），加上我们自己的品类月销。
6. 回测（ASOF 早于数据末尾、而且之后上架的家族观察期已走完时）：用同一个模型给之后上架的新家族打分，和实际结果比；推荐、避开的方案类型实际做到的比例。
用法：ASOF=2026-01 python3 -I 开发建议.py；输出 solution-v2/开发建议/开发建议_<ASOF>.md。"""
import os, re, sys, json, glob, numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score, log_loss
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
ASOF = os.environ.get('ASOF', '2026-01')
SCR = os.environ.get('WORK', '/tmp/开发建议_work'); os.makedirs(SCR, exist_ok=True)
OUTMD = os.environ.get('OUT_MD', os.path.join(ROOT, f'solution-v2/开发建议/开发建议_{ASOF}.md'))
KW = os.path.join(ROOT, 'input/data_v2/keywords_20261028')
mi = lambda s: int(str(s)[:4]) * 12 + int(str(s)[5:7]) - 1
ms = lambda i: f'{i // 12}-{i % 12 + 1:02d}'
T = mi(ASOF)
FULL = os.path.join(ROOT, 'input/data_v2/统一打标/统一打标_分析用.pkl')

def load(cut_month):
    """跑回归脚本第 0–3 节（数据截到 cut_month），返回命名空间。"""
    A = pd.read_pickle(FULL); A = A[A['月份'].astype(str).str[:7].map(mi) <= cut_month]
    p = os.path.join(SCR, f'截至{ms(cut_month)}.pkl'); A.to_pickle(p)
    os.environ.update(DATA=p, OUT_DIR=SCR, WITH_HOLD='1', NPERM='10')
    P = os.path.join(HERE, '回归_新家族.py'); src = open(P, encoding='utf-8').read(); ns = {'__file__': P}
    exec(compile(src[:src.index('# ---------- 4. 时间信号')], P, 'exec'), ns)
    return ns

ns = load(T - 1)
U, feat, A, umw = ns['U'], ns['feat'], ns['A'], ns['umw']
U = U[U['L'] + 5 <= T - 1].copy()                       # 截至时点观察期已走完的
SZ = ['24″', '30″', '36″', '48″']

# ---------- 1. 模型：开发能定的属性 ----------
def toks(f):
    t = [f'尺寸={f["主尺寸段"][0]}', f'档={f["价格档"][0]}', f'台面={f["台面类型"][0]}', f'主色={f["主色"][0]}', f'装={f["装"][0]}', f'形态={f["形态"][0]}']
    t += [f'元素={e}' for e in f['元素'] if e not in ('未知', 'fluted', 'reeded')]
    t += ['颜色≥2'] * (f['_颜色数'] >= 2) + ['子体≥4'] * (f['_变体'] >= 4)
    return [x for x in t if not x.endswith('=未知')]
TK = {u: toks(feat[u]) for u in U.index}
vocab = sorted({t for ts in TK.values() for t in ts if sum(t in TK[v] for v in U.index) >= 3})
def mat(tk_list): return np.array([[1.0 if v in ts else 0.0 for v in vocab] for ts in tk_list])
X = mat([TK[u] for u in U.index]); y = U['y'].values
skf = StratifiedKFold(5, shuffle=True, random_state=0)
def cvll(C):
    pr = np.zeros(len(y))
    for a, b in skf.split(X, y): pr[b] = LogisticRegression(C=C, max_iter=5000).fit(X[a], y[a]).predict_proba(X[b])[:, 1]
    return log_loss(y, pr), roc_auc_score(y, pr)
cvr = {C: cvll(C) for C in (0.03, 0.1, 0.3, 1.0)}; C = min(cvr, key=lambda c: cvr[c][0])
M = LogisticRegression(C=C, max_iter=5000).fit(X, y)
rng = np.random.default_rng(1); BOOT = []
for _ in range(200):
    i = rng.integers(0, len(y), len(y))
    if y[i].min() != y[i].max(): BOOT.append(LogisticRegression(C=C, max_iter=5000).fit(X[i], y[i]))
coef = pd.Series(M.coef_[0], index=vocab).sort_values()
# 校准：做到的比例在一路往下走，按学习数据里最近半年上架的新家族的实际比例平移截距（只改水平，不改排序）
REC = (U['L'] >= U['L'].max() - 5).values
r_obs = y[REC].mean(); p_bar = M.predict_proba(X[REC])[:, 1].mean()
SHIFT = np.log(r_obs / (1 - r_obs)) - np.log(p_bar / (1 - p_bar))
def prob(m, x): z = m.decision_function(x) + SHIFT; return 1 / (1 + np.exp(-z))

# ---------- 2. 候选方案 ----------
ELS = [e for e in pd.Series([e for u in U.index for e in feat[u]['元素'] if e not in ('未知', 'fluted', 'reeded')]).value_counts().index[:10]]
TOPS = ['陶瓷一体', '树脂一体', '石材台面', '木板台面', '不含台面']
COLS = ['白', '灰', '原木', '深木', '黑', '蓝', '绿']
rows = []
for s in SZ:
    for tr in ('低', '中', '高'):
        for tp in TOPS:
            for el in ELS:
                for c in COLS:
                    t = [f'尺寸={s}', f'档={tr}', f'台面={tp}', f'主色={c}', '装=拆装', '形态=落地式', f'元素={el}', '颜色≥2', '子体≥4']
                    rows.append(dict(尺寸=s, 档=tr, 台面=tp, 元素=el, 主色=c, t=t))
Cn = pd.DataFrame(rows); XC = mat(Cn['t'])
Cn['p'] = prob(M, XC)
# 同一方案"只铺 1 个颜色、≤ 2 个子体"时的概率，用来说明铺货的作用
XC1 = mat([[x for x in t if x not in ('颜色≥2', '子体≥4')] for t in Cn['t']]); Cn['p_少铺'] = prob(M, XC1)
# 只有学习数据里出现过的组合才算"有依据"（尺寸 × 台面、尺寸 × 元素都至少 3 个家族）
cnt_st = pd.Series([(feat[u]['主尺寸段'][0], feat[u]['台面类型'][0]) for u in U.index]).value_counts()
cnt_se = pd.Series([(feat[u]['主尺寸段'][0], e) for u in U.index for e in feat[u]['元素']]).value_counts()
combo = pd.Series([(feat[u]['主尺寸段'][0], feat[u]['台面类型'][0], e) for u in U.index for e in feat[u]['元素']])
cy = pd.Series([U.at[u, 'y'] for u in U.index for e in feat[u]['元素']])
CB = pd.DataFrame({'k': combo, 'y': cy}).groupby('k')['y'].agg(['size', 'sum'])
Cn['先例家族'] = [int(CB['size'].get((r.尺寸, r.台面, r.元素), 0)) for r in Cn.itertuples()]
Cn['先例做到'] = [int(CB['sum'].get((r.尺寸, r.台面, r.元素), 0)) for r in Cn.itertuples()]
Cn['有依据'] = [cnt_st.get((r.尺寸, r.台面), 0) >= 3 and cnt_se.get((r.尺寸, r.元素), 0) >= 3 for r in Cn.itertuples()]
def band_p(t):
    x = mat([t]); ps = np.array([prob(b, x)[0] for b in BOOT]); return np.percentile(ps, [10, 90])

# ---------- 3. 做到以后：按主尺寸段 ----------
umw2 = umw[umw['单位'].isin(U.index)].copy()
peak = umw2.groupby('单位').agg(峰值月销=('fu', 'max'), 峰值销售额=('rev', 'max'))
U = U.join(peak)
def after(s):
    g = U[U['主尺寸段'] == s]; w = g[g['y'] == 1]
    q = lambda v: (np.nanpercentile(v, 25), np.nanmedian(v), np.nanpercentile(v, 75)) if len(v) else (np.nan,) * 3
    return dict(家族=len(g), 做到=int(w.shape[0]), 比例=g['y'].mean() if len(g) else np.nan, 月=q(w['首次达线月龄']), 件=q(w['峰值月销']), 额=q(w['峰值销售额']), 没做到额=q(g[g['y'] == 0]['峰值销售额']))
AFT = {s: after(s) for s in SZ}

# ---------- 4. 市场：近 6 个月 vs 前 6 个月（按主尺寸段算份额） ----------
B = A[A['m'] <= T - 1].copy(); B['段'] = B['尺寸段'].fillna('未知')
r6, p6 = B['m'].between(T - 6, T - 1), B['m'].between(T - 12, T - 7)
share = lambda m: B[m].groupby('段')['c'].sum() / B.loc[m, 'c'].sum()
S6, S12 = share(r6), share(p6)
med_price = B[r6].groupby('段')['价格'].median()
newfam = U.groupby('主尺寸段').apply(lambda g: int((g['L'] >= T - 12).sum()))
recent_rate = U[U['L'] >= T - 18].groupby('主尺寸段')['y'].agg(['mean', 'size'])
# 关键词：有宽度的词，近 3 个月搜索份额、同比，和销量份额比
tag = pd.read_csv(f'{KW}/数据/01_关键词词库/tables/keywords_tagged.csv')
rowsk = []
for f in sorted(glob.glob(f'{KW}/数据/02_Amazon历史趋势/raw/*.json')):
    j = json.load(open(f, encoding='utf-8'))
    for r in json.loads(j['response']['content'][0]['text'])['data']:
        yy, mm = re.match(r'(\d{4})年(\d{2})月', r['time']).groups(); rowsk.append((j['keyword'], mi(f'{yy}-{mm}'), r['search']))
KL = pd.DataFrame(rowsk, columns=['关键词', 'm', '搜索']); KL = KL[KL['m'] <= T - 1]
def kband(w):
    try: w = float(w)
    except (TypeError, ValueError): return None
    for c, lo, hi in [(18, 15, 21), (24, 21, 27), (30, 27, 33), (36, 33, 39), (42, 39, 45), (48, 45, 54), (60, 54, 66)]:
        if lo <= w < hi: return f'{c}″'
    return '72″+' if w >= 66 else None
kb = dict(zip(tag['关键词'], tag['宽度（英寸）'].map(kband)))
KL['段'] = KL['关键词'].map(kb)
k3 = KL[KL['m'].between(T - 3, T - 1)]; k3y = KL[KL['m'].between(T - 15, T - 13)]
ks = k3[k3['段'].notna()].groupby('段')['搜索'].sum(); ks_share = ks / ks.sum()
kyoy = k3[k3['段'].notna()].groupby('段')['搜索'].sum() / k3y[k3y['段'].notna()].groupby('段')['搜索'].sum() - 1
s3 = B[B['m'].between(T - 3, T - 1)]; s3 = s3[s3['段'].isin(ks.index)].groupby('段')['c'].sum(); s3 = s3 / s3.sum()
tot_yoy = k3['搜索'].sum() / k3y['搜索'].sum() - 1 if k3y['搜索'].sum() else np.nan

# ---------- 5. 上架时间：季节指数 ----------
KM = KL.groupby('m')['搜索'].sum(); KM = KM[KM.index >= mi('2022-01')]
seas = KM.groupby(KM.index % 12).mean(); seas = seas / seas.mean()
cat = B.groupby('m')['c'].sum(); cats = cat.groupby(cat.index % 12).mean(); cats = cats / cats.mean()
MON = ['1 月', '2 月', '3 月', '4 月', '5 月', '6 月', '7 月', '8 月', '9 月', '10 月', '11 月', '12 月']
def best_launch():
    """上架后第 2–4 个月（多数做到的月份）落在搜索旺季的上架月。"""
    sc = {L: np.mean([seas.get((L + k) % 12, np.nan) for k in (1, 2, 3)]) for L in range(12)}
    return sorted(sc.items(), key=lambda x: -x[1])

# ---------- 6. 写报告 ----------
pct = lambda x: '—' if pd.isna(x) else f'{x:.0%}'
k = lambda x: '—' if pd.isna(x) else f'${x / 1000:.0f}k'
in10 = lambda p: f'{p * 10:.1f}'.rstrip('0').rstrip('.')
L = [f'# 开发建议：站在 {ASOF} 月初', '',
     f'> 只用截至 {ms(T - 1)} 的数据（统一打标表、看图标签、子体销量、关键词研究包里 {ms(T - 1)} 及以前的月份）。由 `trial/开发建议.py` 生成。',
     '> **"做到"的意思**：上架后 6 个月内，任一个月做到小类排名前 50，或者月销售额 ≥ $10 万（我们的成功线）。下面"每 10 个做到几个"都是这个意思。'
     '这是历史上同类新品做到的比例，不是保证；只说明先后和强弱，不说明因果。', '',
     f'学习数据：截至 {ms(T - 1)} 观察期已走完的新家族 {len(U)} 个（上架 {ms(int(U["L"].min()))} 至 {ms(int(U["L"].max()))}），做到的 {int(U["y"].sum())} 个，'
     f'**平均每 10 个做到 {in10(U["y"].mean())} 个**。模型交叉验证 AUC {cvr[C][1]:.2f}（0.5 是瞎猜）。', '']
# 6.1 推荐：有先例的、空白的分开列
def top_list(D, n):
    out, seen = [], set()
    for r in D.itertuples():
        key = (r.尺寸, r.台面, r.元素)
        if key in seen: continue
        seen.add(key); out.append(r)
        if len(out) == n: break
    return out
HEAD = ['| # | 方案 | 每 10 个做到几个（区间） | 只铺 1 色、≤ 2 个子体时 | 历史先例：同尺寸 × 台面 × 元素 做到 / 家族 | 做到的话第几个月做到 | 做到后最高月销量 / 月销售额（中位） | 同尺寸平均每 10 个做到 |',
        '| ---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- |']
def rows_of(lst):
    out = []
    for i, r in enumerate(lst, 1):
        lo, hi = band_p(r.t); a = AFT[r.尺寸]
        out.append(f"| {i} | {r.尺寸} · {r.档}档 · {r.台面} · {r.元素} · 主色{r.主色} | **{in10(r.p)}**（{in10(lo)}–{in10(hi)}） | {in10(r.p_少铺)} | {r.先例做到} / {r.先例家族} | 第 {a['月'][1]:.0f} 个月（{a['月'][0]:.0f}–{a['月'][2]:.0f}） | "
                   f"{a['件'][1]:.0f} 件 / {k(a['额'][1])} | {in10(a['比例'])}（{a['家族']} 个家族） |")
    return out
pick = top_list(Cn[Cn['有依据'] & (Cn['先例家族'] >= 3)].sort_values('p', ascending=False), 6)
blank = top_list(Cn[Cn['有依据'] & (Cn['先例家族'] < 3)].sort_values('p', ascending=False), 4)
L += ['## 1. 建议上的方案', '',
      '默认：落地式、拆装、首月至少 2 个颜色、至少 4 个子体（加分项，见第 3 节）。同一个"尺寸 × 台面 × 元素"只列最好的价位和颜色。',
      f'"每 10 个做到几个"已按学习数据里最近半年上架的新品水平校准（那批每 10 个做到 {in10(r_obs)} 个）；区间是 200 次重抽样本重新拟合的 10%–90%，只反映模型本身的不确定，实际更宽。', '',
      '### 1a. 有先例的（学习数据里同"尺寸 × 台面 × 元素"至少 3 个家族）', '', *HEAD, *rows_of(pick), '',
      '### 1b. 空白方案（模型按各属性推出来的，历史上同组合不到 3 个家族，属于"没人做过"，风险更大）', '', *HEAD, *rows_of(blank)]
bad = Cn[Cn['有依据'] & (Cn['先例家族'] >= 3)].sort_values('p')
avoid, seen = [], set()
for r in bad.itertuples():
    key = (r.尺寸, r.台面, r.元素)
    if key in seen: continue
    seen.add(key); avoid.append(r)
    if len(avoid) == 6: break
L += ['', '## 2. 建议避开的方案（有先例的里面最低的）', '', '| 方案 | 每 10 个做到几个（区间） | 历史先例 做到 / 家族 | 同尺寸平均每 10 个做到 |', '| :--- | :--- | :--- | :--- |']
for r in avoid:
    lo, hi = band_p(r.t); L.append(f"| {r.尺寸} · {r.档}档 · {r.台面} · {r.元素} · 主色{r.主色} | **{in10(r.p)}**（{in10(lo)}–{in10(hi)}） | {r.先例做到} / {r.先例家族} | {in10(AFT[r.尺寸]['比例'])} |")
# 6.2 规律（模型里最大的几项）
def nm(t): return t.replace('=', '：').replace('≥', ' ≥ ')
L += ['', '## 3. 依据：哪些属性让"做到"的机会变大 / 变小（模型系数，正 = 更容易做到）', '',
      '| 加分最多 | 系数 | 减分最多 | 系数 |', '| :--- | ---: | :--- | ---: |']
pos, neg = coef[::-1].head(8), coef.head(8)
for (a, b), (c_, d) in zip(pos.items(), neg.items()): L.append(f'| {nm(a)} | {b:+.2f} | {nm(c_)} | {d:+.2f} |')
L += ['', '系数是对数几率，只比大小和方向；对应的同格比较和可信度见回归第四版和机会判定卡。']
# 6.3 市场
L += ['', f'## 4. 市场（截至 {ms(T - 1)}）', '',
      '| 尺寸段 | 销量份额 近 6 个月（前 6 个月） | 近 12 个月新家族 | 近期新家族每 10 个做到 | 中位价 | 关键词搜索份额 近 3 个月 | 搜索同比 | 搜索份额 − 销量份额 |', '| :--- | :--- | ---: | :--- | ---: | ---: | ---: | ---: |']
for s in SZ + ['42″', '60″']:
    rr = recent_rate.loc[s] if s in recent_rate.index else None
    L.append(f"| {s} | {pct(S6.get(s))}（{pct(S12.get(s))}） | {newfam.get(s, 0)} | {in10(rr['mean']) if rr is not None else '—'}（{int(rr['size']) if rr is not None else 0} 个） | "
             f"${med_price.get(s, np.nan):.0f} | {pct(ks_share.get(s))} | {pct(kyoy.get(s))} | {('%+.0f' % ((ks_share.get(s, np.nan) - s3.get(s, np.nan)) * 100)) if s in s3.index else '—'} 个百分点 |")
L += ['', f'- 关键词（研究包 339 个有效词里写了宽度的词）：近 3 个月总搜索量同比 {pct(tot_yoy)}。搜索份额高于销量份额 = 搜的人比买到的多，可能有缺口；只覆盖写了宽度的词（约四成搜索量），元素、台面、颜色的关键词还没有。']
# 6.4 时间
bl = best_launch()
L += ['', '## 5. 什么时候上', '',
      '| 月 | ' + ' | '.join(MON) + ' |', '| :--- |' + ' ---: |' * 12,
      '| 搜索季节指数（2022-01 起） | ' + ' | '.join(f'{seas.get(i, np.nan):.2f}' for i in range(12)) + ' |',
      '| 我们的品类月销季节指数 | ' + ' | '.join(f'{cats.get(i, np.nan):.2f}' if i in cats.index else '—' for i in range(12)) + ' |', '',
      f'- 做到的新品多在上架后第 2–3 个月做到。让第 2–4 个月落在搜索旺季，最好的上架月是：{"、".join(MON[i] for i, _ in bl[:3])}；最差的是：{"、".join(MON[i] for i, _ in bl[-3:])}。',
      f'- 立项到上架约 3 个月（纪要 D1）。站在 {ASOF} 月初，最早能上架的是 {MON[(T + 3) % 12]}。']
L += ['', '## 6. 每个尺寸做到以后大概卖多少（同主尺寸段里做到的新家族）', '',
      '| 尺寸段 | 新家族 | 做到 | 第几个月做到（四分位） | 最高月销量（四分位） | 最高月销售额（四分位） | 没做到的最高月销售额（中位） |', '| :--- | ---: | ---: | :--- | :--- | :--- | :--- |']
for s in SZ:
    a = AFT[s]; L.append(f"| {s} | {a['家族']} | {a['做到']} | {a['月'][1]:.0f}（{a['月'][0]:.0f}–{a['月'][2]:.0f}） | {a['件'][1]:.0f}（{a['件'][0]:.0f}–{a['件'][2]:.0f}） | {k(a['额'][1])}（{k(a['额'][0])}–{k(a['额'][2])}） | {k(a['没做到额'][1])} |")

# ---------- 7. 回测：之后上架的家族 ----------
EVAL = {}
nf = load(mi('2026-09'))
Uf, ff = nf['U'], nf['feat']
later = Uf[(Uf['L'] >= T) & (Uf['L'] + 5 <= mi('2026-09'))]
if len(later) >= 10:
    pl = prob(M, mat([toks(ff[u]) for u in later.index])); yl = later['y'].values
    order = np.argsort(-pl); k20 = max(1, round(0.2 * len(pl)))
    EVAL = dict(n=len(later), k=int(yl.sum()), pbar=float(pl.mean()), auc=roc_auc_score(yl, pl) if yl.min() != yl.max() else np.nan,
                top=yl[order[:k20]].mean(), base=yl.mean(), bottom=yl[order[-k20:]].mean())
    def match(r, u): f = ff[u]; return f['主尺寸段'][0] == r.尺寸 and f['台面类型'][0] == r.台面 and r.元素 in f['元素']
    gp = [u for u in later.index if any(match(r, u) for r in pick)]; gb = [u for u in later.index if any(match(r, u) for r in blank)]; ga = [u for u in later.index if any(match(r, u) for r in avoid)]
    L += ['', f'## 7. 回测：{ASOF} 以后上架、观察期到 2026-09 已走完的新家族（{ms(T)} 至 {ms(int(later["L"].max()))} 上架）', '',
          f'- 共 {EVAL["n"]} 个，做到 {EVAL["k"]} 个（每 10 个 {in10(EVAL["base"])} 个）。',
          f'- 模型给它们的平均预测是每 10 个做到 {in10(EVAL["pbar"])} 个，实际 {in10(EVAL["base"])} 个：**水平高估了**（新品做到的比例还在往下走），排序仍有用：',
          f'- 用这份建议的模型给它们打分：AUC {EVAL["auc"]:.2f}；打分最高的 20% 每 10 个做到 {in10(EVAL["top"])} 个（是平均的 {EVAL["top"] / EVAL["base"]:.2f} 倍），最低的 20% 每 10 个做到 {in10(EVAL["bottom"])} 个。',
          f'- 和"建议上的方案"同类（同主尺寸、同台面、含同一元素）的：{len(gp)} 个，做到 {int(Uf.loc[gp, "y"].sum()) if gp else 0} 个'
          + (f'（每 10 个 {in10(Uf.loc[gp, "y"].mean())} 个）' if gp else '') + '。',
          f'- 和"空白方案"同类的：{len(gb)} 个' + (f'，做到 {int(Uf.loc[gb, "y"].sum())} 个' if gb else '（2026 年也没人做）') + '。',
          f'- 和"建议避开的方案"同类的：{len(ga)} 个，做到 {int(Uf.loc[ga, "y"].sum()) if ga else 0} 个' + (f'（每 10 个 {in10(Uf.loc[ga, "y"].mean())} 个）' if ga else '') + '。',
          '- 留出的家族少，区间很宽，只看方向。']
    # wen 2026 年规划（回放_26年规划_2026.md）里能翻成标签的几条：在这份建议里的分数、2026 年同类新家族的实际
    PLAN = [('SPU5 陶瓷一体盆 + fluted', dict(台面='陶瓷一体', 元素='竖棱')), ('SPU6 陶瓷一体盆 + 自然木纹', dict(台面='陶瓷一体', 元素='自然木纹')),
            ('SPU7 壁挂 + 自然木纹', dict(形态='悬浮式', 元素='自然木纹')), ('SPU8 壁挂 + 纯色', dict(形态='悬浮式', 元素='纯色')),
            ('SPU2 大理石纹台面 + fluted', dict(台面='石材台面', 元素='竖棱')), ('SPU3 大理石纹台面 + 夏克式', dict(台面='石材台面', 元素='夏克式')),
            ('SPU4 大理石纹台面 + 自然木纹', dict(台面='石材台面', 元素='自然木纹'))]
    L += ['', '### 和 wen 2026 年规划对照（规划约 2025-11 定；翻成标签的近似，见 回放_26年规划_2026.md）', '',
          '| 规划 | 这份建议给的每 10 个做到几个（24″ / 30″ / 36″，中档、≥ 2 色、≥ 4 子体、主色白） | 2026-01 至 04 上架的同类新家族 实际做到 / 家族 |', '| :--- | :--- | :--- |']
    for nm_, cond in PLAN:
        ps = []
        for s_ in ('24″', '30″', '36″'):
            t = [f'尺寸={s_}', '档=中', f'台面={cond.get("台面", "陶瓷一体")}', '主色=白', '装=拆装', f'形态={cond.get("形态", "落地式")}', f'元素={cond["元素"]}', '颜色≥2', '子体≥4']
            if '台面' not in cond: t = [x for x in t if not x.startswith('台面=')]
            ps.append(in10(prob(M, mat([t]))[0]))
        mm = [u for u in later.index if cond['元素'] in ff[u]['元素'] and ('台面' not in cond or ff[u]['台面类型'][0] == cond['台面']) and ('形态' not in cond or ff[u]['形态'][0] == cond['形态'])]
        L.append(f"| {nm_} | {' / '.join(ps)} | {int(Uf.loc[mm, 'y'].sum()) if mm else 0} / {len(mm)} |")
    L += ['', '壁挂两条（SPU7、SPU8）不指定台面；同尺寸平均见第 6 节。']
L += ['', '## 8. 限制', '',
      f'- 学习数据只有 {len(U)} 个新家族，很多"尺寸 × 台面 × 元素"组合只有几个家族；表里只列学习数据里出现过（尺寸 × 台面、尺寸 × 元素各至少 3 个家族）的方案。',
      '- 只看得到进过榜（家族月销 ≥ 50 / 60、价格 ≥ 90）的新品，没起量的看不到，"每 10 个做到几个"是起量新品里的比例。',
      '- 销量是卖家精灵的估算，不是真实订单；做到以后的销量是同尺寸做到的新家族的分布，不是这个方案的保证。',
      '- 元素、台面、颜色的关键词还没有（研究包只有尺寸层面能用），站外 Google 趋势也还没有。']
bl3 = '、'.join(MON[i] for i, _ in bl[:3]); r1 = pick[0]; r2 = pick[1]; a1 = AFT[r1.尺寸]; a2 = AFT[r2.尺寸]; av = avoid[0]
CONC = ['', '## 结论', '',
        f'1. **最值得上的（有先例）**：{r1.尺寸} {r1.档}档 {r1.台面} + {r1.元素}，首月 ≥ 2 个颜色、≥ 4 个子体。同类新品**每 10 个约 {in10(r1.p)} 个**在 6 个月内做到"小类前 50 或月销售额 $10 万"'
        f'（同尺寸平均 {in10(a1["比例"])} 个），做到的多在第 {a1["月"][1]:.0f} 个月，做到后最高月销量中位约 {a1["件"][1]:.0f} 件、月销售额约 {k(a1["额"][1])}。'
        f'其次是 {r2.尺寸} {r2.档}档 {r2.台面} + {r2.元素}（每 10 个约 {in10(r2.p)} 个）。',
        f'2. **要避开的**：低档、陶瓷一体、主色{av.主色}的 {av.尺寸} {av.元素}，同类每 10 个只做到约 {in10(av.p)} 个；只铺 1 个颜色、≤ 2 个子体的，同一方案每 10 个少做到约 {in10(r1.p - r1.p_少铺)} 个。',
        f'3. **什么时候上**：让上架后第 2–4 个月落在搜索旺季，最好在 {bl3} 上架；站在 {ASOF} 月初、立项到上架约 3 个月，最早 {MON[(T + 3) % 12]} 能上。',
        f'4. **可信度**：模型排序有用但水平偏乐观（见第 7 节回测或第 8 节）；"空白方案"是模型外推，没人做过，只适合小批量试。', '']
L[6:6] = CONC
os.makedirs(os.path.dirname(OUTMD), exist_ok=True)
open(OUTMD, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L[:12])); print(EVAL)
