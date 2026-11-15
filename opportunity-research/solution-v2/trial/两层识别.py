"""机会识别两层方法（规则见 solution-v2/开发建议/识别方法_预登记.md，2026-11-02 先提交后回测）。
市场层：类型的销量动量、家族进入、搜索同比，百分位等权合成；新品层：开发能定的属性做 L2 逻辑回归（同等权重 / 半衰期 6 个月两种，按预登记规则选）。
MODE=回测：在预登记的时点上滚动检验，输出 solution-v2/开发建议/两层识别_滚动回测.md；
MODE=建议 ASOF=yyyy-mm：出这个时点的两层建议，输出 solution-v2/开发建议/两层建议_<ASOF>.md。"""
import os, re, json, glob, numpy as np, pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
MODE = os.environ.get('MODE', '回测'); ASOF = os.environ.get('ASOF', '2026-10')
WORK = os.environ.get('WORK', '/tmp/两层识别_work'); os.makedirs(WORK, exist_ok=True)
mi = lambda s: int(str(s)[:4]) * 12 + int(str(s)[5:7]) - 1
ms = lambda i: f'{i // 12}-{i % 12 + 1:02d}'
END = mi('2026-09')
os.environ.update(DATA=os.path.join(ROOT, 'input/data_v2/统一打标/统一打标_分析用.pkl'), OUT_DIR=WORK, WITH_HOLD='1', NPERM='10')
P = os.path.join(HERE, '回归_新家族.py'); src = open(P, encoding='utf-8').read(); ns = {'__file__': P}
exec(compile(src[:src.index('# ---------- 4. 时间信号')], P, 'exec'), ns)
A, U, feat, band = ns['A'].copy(), ns['U'], ns['feat'], ns['band']
A['元素一'] = A['元素集'].map(lambda t: [e for e in t if e not in ('fluted', 'reeded')])
UNK = lambda v: v is None or (isinstance(v, float) and np.isnan(v)) or str(v) in ('未知', '', 'nan', 'None') or str(v).startswith('台面未知')
DIMV = {'尺寸': A['尺寸段'], '台面': A['台面类型'], '价格档': A['价格档'], '形态': A['形态'], '主色': A['主色'], '材质': A['柜体材质']}
KINDS = [('尺寸', '台面'), ('尺寸', '元素'), ('台面', '元素'), ('尺寸', '价格档'), ('尺寸', '材质'), ('形态', None), ('主色', None), ('元素', None), ('台面', None), ('尺寸', None)]
def row_keys(kind):
    a, b = kind
    if b is None:
        if a == '元素': return A['元素一'].map(lambda t: [(e,) for e in t])
        return DIMV[a].map(lambda v: [] if UNK(v) else [(v,)])
    if '元素' in kind:
        o = a if b == '元素' else b
        return [[] if UNK(x) else [(x, e) for e in t] for x, t in zip(DIMV[o], A['元素一'])]
    return [[] if (UNK(x) or UNK(y)) else [(x, y)] for x, y in zip(DIMV[a], DIMV[b])]
EX = {}
for kind in KINDS:
    rk = pd.Series(row_keys(kind), index=A.index)
    EX[kind] = pd.DataFrame({'m': A['m'], 'c': A['c'], 'fam': A['家族键'], 'k': rk}).explode('k').dropna(subset=['k'])
def window(kind, a, b):
    e = EX[kind][EX[kind]['m'].between(a, b)]
    g = e.groupby('k').agg(c=('c', 'sum')); g['月均销'] = g['c'] / (b - a + 1); g['份额'] = g['c'] / e['c'].sum()
    g['月均家族'] = e.groupby(['k', 'm'])['fam'].nunique().groupby('k').sum() / (b - a + 1)
    return g

# ---------- 关键词：尺寸（研究包）+ 属性（2026-11-02 拉的固定词表） ----------
KW = os.path.join(ROOT, 'input/data_v2/keywords_20261028'); tag = pd.read_csv(f'{KW}/数据/01_关键词词库/tables/keywords_tagged.csv')
kr = []
for f in sorted(glob.glob(f'{KW}/数据/02_Amazon历史趋势/raw/*.json')):
    j = json.load(open(f, encoding='utf-8'))
    for r in json.loads(j['response']['content'][0]['text'])['data']:
        yy, mm = re.match(r'(\d{4})年(\d{2})月', r['time']).groups(); kr.append((j['keyword'], mi(f'{yy}-{mm}'), r['search']))
KS = pd.DataFrame(kr, columns=['kw', 'm', 'v']); KS['值'] = KS['kw'].map(dict(zip(tag['关键词'], tag['宽度（英寸）'].map(band)))); KS['维度'] = '尺寸'; KS['来源'] = 'amazon'
KS = KS.dropna(subset=['值'])
KMAP = {'resin top bathroom vanity': ('台面', '树脂一体'), 'marble top bathroom vanity': ('台面', '石材台面'), 'quartz top bathroom vanity': ('台面', '石材台面'),
        'stone top bathroom vanity': ('台面', '石材台面'), 'bathroom vanity with ceramic sink': ('台面', '陶瓷一体'), 'wood top bathroom vanity': ('台面', '木板台面'),
        'bathroom vanity without top': ('台面', '不含台面'), 'bathroom vanity cabinet only': ('台面', '不含盆'),
        'fluted bathroom vanity': ('元素', '竖棱'), 'reeded bathroom vanity': ('元素', '竖棱'), 'shaker bathroom vanity': ('元素', '夏克式'),
        'farmhouse bathroom vanity': ('元素', '农场风装饰饰条'), 'barn door bathroom vanity': ('元素', '农场风装饰饰条'), 'slatted bathroom vanity': ('元素', '木条格栅'),
        'rattan bathroom vanity': ('元素', 'rattan'), 'glass door bathroom vanity': ('元素', '玻璃门'), 'rustic bathroom vanity': ('元素', 'rustic'),
        'vintage bathroom vanity': ('元素', '夏克式+复古立柱'),
        'black bathroom vanity': ('主色', '黑'), 'white bathroom vanity': ('主色', '白'), 'gray bathroom vanity': ('主色', '灰'), 'grey bathroom vanity': ('主色', '灰'),
        'wood bathroom vanity': ('主色', '原木'), 'oak bathroom vanity': ('主色', '原木'), 'natural wood bathroom vanity': ('主色', '原木'), 'walnut bathroom vanity': ('主色', '深木'),
        'green bathroom vanity': ('主色', '绿'), 'blue bathroom vanity': ('主色', '蓝'),
        'floating bathroom vanity': ('形态', '悬浮式'), 'wall mounted bathroom vanity': ('形态', '悬浮式'), 'freestanding bathroom vanity': ('形态', '落地式'),
        'pedestal sink': ('形态', '柱状盆'), 'corner bathroom vanity': ('形态', '转角式')}
AT = os.path.join(ROOT, 'input/data_v2/关键词_属性/汇总.csv'); HAS_ATTR = os.path.exists(AT)
if HAS_ATTR:
    at = pd.read_csv(AT, encoding='utf-8-sig'); at = at[at['关键词'].isin(KMAP)].copy()
    KS = pd.concat([KS, pd.DataFrame({'kw': at['关键词'], 'm': at['月'].map(mi), 'v': pd.to_numeric(at['值'], errors='coerce'),
                                      '值': [KMAP[k][1] for k in at['关键词']], '维度': [KMAP[k][0] for k in at['关键词']], '来源': at['来源']})], ignore_index=True)
def search_yoy(T):
    """维度取值 → T−3 至 T−1 对一年前同期的搜索同比（亚马逊、Google 各算，取平均）。"""
    out = {}
    for (d, v), g in KS.groupby(['维度', '值']):
        ys = []
        for src_, h in g.groupby('来源'):
            now = h[h['m'].between(T - 3, T - 1)].groupby('m')['v'].sum().sum(); pre = h[h['m'].between(T - 15, T - 13)].groupby('m')['v'].sum().sum()
            if pre > 0 and now > 0: ys.append(now / pre - 1)
        if ys: out[(d, v)] = float(np.mean(ys))
    return out

# ---------- 市场层 ----------
def market(T):
    yo = search_yoy(T); rows = []
    for kind in KINDS:
        q, p = window(kind, T - 6, T - 1), window(kind, T - 12, T - 7)
        for k_ in q.index.union(p.index):
            r = dict(类型=kind, 键=k_, 取值=' × '.join(map(str, k_)))
            r['月均销_前'] = q['月均销'].get(k_, 0.0); r['月均销_前前'] = p['月均销'].get(k_, 0.0)
            r['份额_前'] = q['份额'].get(k_, 0.0); r['家族_前'] = q['月均家族'].get(k_, 0.0); r['家族_前前'] = p['月均家族'].get(k_, 0.0)
            dims = [d for d in kind if d]
            s3 = [yo[(d, v)] for d, v in zip(dims, k_) if (d, v) in yo]
            r['S1'] = np.log((r['月均销_前'] + 1) / (r['月均销_前前'] + 1)); r['S2'] = r['家族_前'] - r['家族_前前']; r['S3'] = np.mean(s3) if s3 else np.nan
            rows.append(r)
    M = pd.DataFrame(rows); M = M[(M['家族_前'] > 0) | (M['家族_前前'] > 0)].copy()
    for s in ('S1', 'S2', 'S3'): M[s + '分'] = M[s].rank(pct=True)
    M['合成'] = M[['S1分', 'S2分', 'S3分']].mean(axis=1, skipna=True); M['合成分位'] = M['合成'].rank(pct=True)
    return M
def outcome(M, T):
    a, b = T + 3, min(T + 8, END); res = []
    for kind in KINDS:
        w = window(kind, a, b); res.append(pd.DataFrame({'类型': [kind] * len(w), '键': list(w.index), '月均销_后': w['月均销'].values, '份额_后': w['份额'].values}))
    O = pd.concat(res); M = M.merge(O, on=['类型', '键'], how='left').fillna({'月均销_后': 0.0, '份额_后': 0.0})
    M['增长'] = np.log((M['月均销_后'] + 1) / (M['月均销_前'] + 1)); M['高速'] = (M['月均销_后'] >= 2.5 * M['月均销_前']) & (M['份额_后'] >= 0.01)
    return M

# ---------- 新品层 ----------
def toks(f):
    t = [f'尺寸={f["主尺寸段"][0]}', f'档={f["价格档"][0]}', f'台面={f["台面类型"][0]}', f'主色={f["主色"][0]}', f'装={f["装"][0]}', f'形态={f["形态"][0]}']
    t += [f'元素={e}' for e in f['元素'] if e not in ('未知', 'fluted', 'reeded')]
    t += ['颜色≥2'] * (f['_颜色数'] >= 2) + ['子体≥4'] * (f['_变体'] >= 4)
    return [x for x in t if not x.endswith('=未知')]
TK = {u: toks(feat[u]) for u in U.index}
def newprod(T, decay):
    tr = U[U['L'] + 5 <= T - 1]
    vocab = sorted({t for u in tr.index for t in TK[u] if sum(t in TK[v] for v in tr.index) >= 3})
    X = np.array([[1.0 if v in TK[u] else 0.0 for v in vocab] for u in tr.index]); y = tr['y'].values
    w = 0.5 ** ((tr['L'].max() - tr['L'].values) / 6.0) if decay else np.ones(len(y))
    m = LogisticRegression(C=0.1, max_iter=5000).fit(X, y, sample_weight=w)
    return lambda us: m.predict_proba(np.array([[1.0 if v in TK[u] else 0.0 for v in vocab] for u in us]))[:, 1]
def cohort(T): return U[U['L'].between(T, T + 3) & (U['L'] + 5 <= END)]
def lift(y, s): o = np.argsort(-np.asarray(s)); k = max(1, round(0.2 * len(s))); return float(np.asarray(y)[o[:k]].mean() / np.mean(y))
FAMTYPES = [('尺寸', '台面'), ('尺寸', '元素'), ('台面', '元素'), ('尺寸', '价格档')]
def fam_market(u, M):
    f = feat[u]; get = {'尺寸': f['主尺寸段'], '台面': f['台面类型'], '价格档': f['价格档'], '元素': [e for e in f['元素'] if e not in ('fluted', 'reeded', '未知')]}
    idx = M.set_index(['类型', '键'])['合成分位']; vals = []
    for kind in FAMTYPES:
        for x in get[kind[0]]:
            for y_ in get[kind[1]]:
                if (kind, (x, y_)) in idx.index: vals.append(idx[(kind, (x, y_))])
    return float(np.mean(vals)) if vals else np.nan

pct = lambda x: '—' if pd.isna(x) else (f'{x:.1%}' if abs(x) < 0.1 else f'{x:.0%}')
in10 = lambda p: '—' if pd.isna(p) else f'{p * 10:.1f}'.rstrip('0').rstrip('.')
L = []
if MODE == '回测':
    L += ['# 两层识别：滚动回测', '', '> 规则见 识别方法_预登记.md（2026-11-02 先提交、后回测）。由 `trial/两层识别.py` 生成。',
          f'> 搜索同比：尺寸用研究包；台面、元素、颜色、形态{"用 2026-11-02 拉的属性词（亚马逊站内 + Google）" if HAS_ATTR else "的属性词还没拉到，这次只有尺寸"}。', '']
    # 市场层
    L += ['## 1. 市场层：合成分能不能挑出之后涨的类型', '', '| 时点 T | 类型数 | 合成分 vs 之后增长 秩相关 | 前 20% 增长中位 | 后 20% | 高速起来的类型 | 其中被排进前 20% | 各信号单独的秩相关 S1 / S2 / S3 |',
          '| :--- | ---: | ---: | :--- | :--- | ---: | :--- | :--- |']
    MK = {}
    for T in [mi(x) for x in ('2025-10', '2025-11', '2025-12', '2026-01')]:
        M = outcome(market(T), T); MK[T] = M
        d = M[M['月均销_前'] > 0]; rho = spearmanr(d['合成'], d['增长'])[0]; q = d['合成分位']
        sing = ' / '.join(f"{spearmanr(d[s], d['增长'], nan_policy='omit')[0]:+.2f}" for s in ('S1', 'S2', 'S3'))
        hs = M[M['高速']]; cap = int((hs['合成分位'] >= 0.8).sum())
        L.append(f"| {ms(T)} | {len(d)} | {rho:+.2f} | {np.expm1(d.loc[q >= 0.8, '增长'].median()):+.0%} | {np.expm1(d.loc[q <= 0.2, '增长'].median()):+.0%} | {len(hs)} | {cap}（{cap / max(len(hs), 1):.0%}，随机约 20%） | {sing} |")
    M = MK[mi('2026-01')]; hs = M[M['高速']].sort_values('合成分位', ascending=False)
    L += ['', '2026-01 时点"高速起来"的类型，各自的合成分位（≥ 80% = 被排进前 20%）：', '', '| 类型 | 份额 前 → 后 | 合成分位 | S1 销量动量 | S2 家族进入 | S3 搜索同比 |', '| :--- | :--- | ---: | ---: | ---: | ---: |']
    for r in hs.itertuples():
        L.append(f"| {' × '.join(d for d in r.类型 if d)}：{r.取值} | {pct(r.份额_前)} → {pct(r.份额_后)} | {r.合成分位:.0%} | {r.S1:+.2f} | {r.S2:+.1f} | {pct(r.S3) if pd.notna(r.S3) else '—'} |")
    # 新品层：选做法
    L += ['', '## 2. 新品层：同等权重 vs 近期加权（半衰期 6 个月）', '', '| 时点 T | 评估的新家族（T 至 T+3 上架） | 做到 | AUC 同等 | AUC 近期加权 | 前 20% 倍数 同等 | 近期加权 | 用途 |', '| :--- | ---: | ---: | ---: | ---: | ---: | ---: | :--- |']
    sel = {False: [], True: []}
    for Ts in ('2025-07', '2025-08', '2025-09', '2025-10', '2026-01'):
        T = mi(Ts); c = cohort(T); yv = c['y'].values
        if len(c) < 10 or yv.min() == yv.max(): continue
        r = {}
        for dec in (False, True):
            s = newprod(T, dec)(list(c.index)); r[dec] = (roc_auc_score(yv, s), lift(yv, s))
            if Ts != '2026-01': sel[dec].append(r[dec][0])
        L.append(f"| {Ts} | {len(c)} | {int(yv.sum())} | {r[False][0]:.2f} | {r[True][0]:.2f} | {r[False][1]:.2f} | {r[True][1]:.2f} | {'验收' if Ts == '2026-01' else '选做法'} |")
    DEC = np.mean(sel[True]) > np.mean(sel[False])
    L += ['', f'按预登记规则（2025-07 至 10 的平均 AUC）选：**{"近期加权" if DEC else "同等权重"}**（平均 AUC 同等 {np.mean(sel[False]):.2f}、近期加权 {np.mean(sel[True]):.2f}）。']
    # 两层合起来
    L += ['', '## 3. 两层合起来：每个时点"建议上 / 避开"的新品，实际做到的比例', '', '| 时点 T | 新家族 | 全部做到 | 建议上 做到 / 家族 | 避开 做到 / 家族 | 其余 |', '| :--- | ---: | :--- | :--- | :--- | :--- |']
    for Ts in ('2025-10', '2025-11', '2025-12', '2026-01'):
        T = mi(Ts); c = cohort(T)
        if len(c) < 10: continue
        Mk = MK.get(T) if T in MK else market(T); s = newprod(T, DEC)(list(c.index)); avg = s.mean(); lo = np.quantile(s, 0.2)
        mk = np.array([fam_market(u, Mk) for u in c.index])
        rec = (mk >= 0.7) & (s >= avg); avd = (mk <= 0.3) | (s <= lo); oth = ~rec & ~avd; yv = c['y'].values
        f_ = lambda m: f"{int(yv[m].sum())} / {int(m.sum())}（{in10(yv[m].mean()) if m.any() else '—'}）"
        L.append(f"| {Ts} | {len(c)} | {f_(np.ones(len(c), bool))} | {f_(rec)} | {f_(avd)} | {f_(oth)} |")
    L += ['', '括号里是每 10 个做到几个。各时点的新家族有重叠（上架窗口 4 个月、时点隔 1 个月），不是独立样本。']
    open(os.path.join(ROOT, 'solution-v2/开发建议/两层识别_滚动回测.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L))

if MODE == '建议':
    T = mi(ASOF); M = market(T); DEC = True                      # 新品层按滚动回测选定的做法（近期加权）
    tr = U[U['L'] + 5 <= T - 1]; score = newprod(T, DEC)
    # 校准：按最近半年上架、已走完的新家族实际比例平移（只改水平）
    rec_u = tr[tr['L'] >= tr['L'].max() - 5]; r_obs = rec_u['y'].mean(); p_bar = score(list(rec_u.index)).mean()
    shift = np.log(r_obs / (1 - r_obs)) - np.log(p_bar / (1 - p_bar))
    cal = lambda p: 1 / (1 + np.exp(-(np.log(p / (1 - p)) + shift)))
    # 候选方案：主要尺寸 × 价格档 × 台面 × 元素（默认 ≥ 2 色、≥ 4 子体、落地式、拆装、主色原木 / 白 / 灰取最好）
    vocab_all = sorted({t for u in tr.index for t in TK[u]})
    class F: pass
    SZ = ['24″', '30″', '36″', '48″', '60″']; TOPS = ['陶瓷一体', '树脂一体', '石材台面', '木板台面', '不含台面', '不含盆']
    ELS = list(pd.Series([e for u in tr.index for e in feat[u]['元素'] if e not in ('未知', 'fluted', 'reeded')]).value_counts().index[:12])
    fake = {}
    for s_ in SZ:
        for tr_ in ('低', '中', '高'):
            for tp in TOPS:
                for el in ELS:
                    for c in ('原木', '白', '灰'):
                        fake[f'C|{s_}|{tr_}|{tp}|{el}|{c}'] = [f'尺寸={s_}', f'档={tr_}', f'台面={tp}', f'主色={c}', '装=拆装', '形态=落地式', f'元素={el}', '颜色≥2', '子体≥4']
    TK.update(fake); keys = list(fake); P_ = cal(score(keys))
    idx = M.set_index(['类型', '键'])
    def mkt(s_, tp, el):
        v = [idx['合成分位'].get((k, kk), np.nan) for k, kk in ((('尺寸', '台面'), (s_, tp)), (('尺寸', '元素'), (s_, el)), (('台面', '元素'), (tp, el)))]
        v = [x for x in v if pd.notna(x)]; return float(np.mean(v)) if v else np.nan
    C = pd.DataFrame([dict(zip(['_', '尺寸', '档', '台面', '元素', '主色'], k.split('|'))) for k in keys]); C['p'] = P_
    C['市场'] = [mkt(r.尺寸, r.台面, r.元素) for r in C.itertuples()]
    hist = pd.Series([(feat[u]['主尺寸段'][0], feat[u]['台面类型'][0], e) for u in tr.index for e in feat[u]['元素']]).value_counts()
    C['先例'] = [int(hist.get((r.尺寸, r.台面, r.元素), 0)) for r in C.itertuples()]
    ptr = cal(score(list(tr.index))); avg = ptr.mean(); lo20 = np.quantile(ptr, 0.2)   # 推荐、避开都以学习数据里新家族的打分分布为参照
    best = C.sort_values('p', ascending=False).drop_duplicates(['尺寸', '台面', '元素'])
    REC = best[(best['市场'] >= 0.7) & (best['p'] >= avg) & (best['先例'] >= 3)].sort_values(['市场', 'p'], ascending=False)
    EMG = best[(best['市场'] >= 0.8) & (best['先例'] < 3)].sort_values('市场', ascending=False)
    AVD = best[((best['市场'] <= 0.3) | (best['p'] <= lo20)) & (best['先例'] >= 3)].sort_values(['市场', 'p'])
    # 做到以后：按主尺寸段
    done = tr[tr['y'] == 1]; umw = ns['umw']; pk = umw[umw['单位'].isin(tr.index)].groupby('单位').agg(件=('fu', 'max'), 额=('rev', 'max'))
    def after(s_):
        d = done[done['主尺寸段'] == s_].join(pk); return (d['首次达线月龄'].median(), d['件'].median(), d['额'].median(), len(tr[tr['主尺寸段'] == s_]))
    k_ = lambda x: '—' if pd.isna(x) else f'${x / 1000:.0f}k'
    L = [f'# 两层开发建议：站在 {ASOF} 月初', '',
         f'> 规则见 识别方法_预登记.md；只用截至 {ms(T - 1)} 的数据。由 `trial/两层识别.py` 生成。',
         '> **市场层**看"这类产品在不在涨"：销量动量、新进家族、搜索同比三项的百分位等权合成，100% = 当期最靠前。'
         '**新品层**看"新品进去能不能做起来"：每 10 个新品里 6 个月内做到"小类前 50 或月销售额 $10 万"的有几个，按最近半年上架的新品水平校准。', '',
         f'当期新品平均每 10 个做到 {in10(avg)} 个（最近半年上架的实际是 {in10(r_obs)} 个）。', '',
         '## 1. 在涨的产品类型（市场层前 20%）', '', '| 类型 | 份额 前 6 个月（再前 6 个月动量） | 销量动量 | 平均每月在榜家族 变化 | 搜索同比 | 市场分位 |', '| :--- | :--- | ---: | ---: | ---: | ---: |']
    top = M[(M['合成分位'] >= 0.8) & (M['份额_前'] >= 0.005)].sort_values('合成分位', ascending=False).head(20)
    for r in top.itertuples():
        L.append(f"| {' × '.join(d for d in r.类型 if d)}：{r.取值} | {pct(r.份额_前)} | {np.expm1(r.S1):+.0%} | {r.S2:+.1f} | {pct(r.S3) if pd.notna(r.S3) else '—'} | {r.合成分位:.0%} |")
    em = M[(M['合成分位'] >= 0.8) & (M['份额_前'] < 0.005)].sort_values('合成分位', ascending=False).head(10)
    L += ['', '### 正在冒头的（份额还不到 0.5%，但动量、新进家族、搜索都在往上）', '', '| 类型 | 份额 | 销量动量 | 在榜家族 变化 | 搜索同比 | 市场分位 |', '| :--- | :--- | ---: | ---: | ---: | ---: |']
    for r in em.itertuples():
        L.append(f"| {' × '.join(d for d in r.类型 if d)}：{r.取值} | {pct(r.份额_前)} | {np.expm1(r.S1):+.0%} | {r.S2:+.1f} | {pct(r.S3) if pd.notna(r.S3) else '—'} | {r.合成分位:.0%} |")
    def tab(D, n):
        out = ['| 方案（≥ 2 色、≥ 4 子体） | 市场分位 | 每 10 个做到几个 | 历史同组合新家族 | 做到的话第几个月 | 做到后最高月销量 / 月销售额（同尺寸中位） |', '| :--- | ---: | :--- | ---: | :--- | :--- |']
        for r in D.head(n).itertuples():
            a = after(r.尺寸); out.append(f"| {r.尺寸} {r.档}档 {r.台面} + {r.元素}，主色{r.主色} | {r.市场:.0%} | **{in10(r.p)}** | {r.先例} | 第 {a[0]:.0f} 个月 | {a[1]:.0f} 件 / {k_(a[2])} |")
        return out
    L += ['', '## 2. 建议上的方案（两层都过：市场分位 ≥ 70%，做到的机会 ≥ 平均，历史同组合 ≥ 3 个新家族）', '', *tab(REC, 10),
          '', '## 3. 正在冒头、可以小批量试的方案（市场分位 ≥ 80%，但历史同组合不到 3 个新家族，新品层没依据）', '', *tab(EMG, 8),
          '', '## 4. 建议避开的（市场分位 ≤ 30%，或做到的机会在后 20%）', '', *tab(AVD, 8)]
    L += ['', '## 5. 怎么读', '',
          '- 市场分位高 = 这类产品最近半年在涨、新进的家族在增加、相关搜索在涨，三项一起看；分位只说明在当期所有类型里的相对位置。',
          '- "每 10 个做到几个"是历史上同类新品的比例，按最近半年水平校准；新品做到的比例在逐年往下走，绝对值偏乐观，排序更可信。',
          '- 做到以后的销量是同主尺寸段做到的新家族的中位数，不是这个方案的保证。',
          '- 滚动回测（两层识别_滚动回测.md，4 个时点）：市场层前 20% 的类型，之后月均销中位 +6% 至 +31%，后 20% −17% 至 −33%；新品层 AUC 0.56–0.67；具体方案层面（两层合起来）时好时坏，见回测第 3 节。']
    later = U[U['L'].between(T, T + 3) & (U['L'] + 5 <= END)]
    if len(later) >= 10:
        def act(D):
            ks = {(r.尺寸, r.台面, r.元素) for r in D.itertuples()}
            m = [u for u in later.index if any((feat[u]['主尺寸段'][0], feat[u]['台面类型'][0], e) in ks for e in feat[u]['元素'])]
            return f"{int(later.loc[m, 'y'].sum())} / {len(m)}" + (f"（每 10 个 {in10(later.loc[m, 'y'].mean())}）" if m else '（没人做）')
        def act_type(D):
            sz = {r.尺寸 for r in D.itertuples()}; return sz
        top_t = M[(M['合成分位'] >= 0.8)]
        L += ['', f'## 6. 核对：{ASOF} 至 {ms(T + 3)} 上架、观察期已走完的 {len(later)} 个新家族（全部每 10 个做到 {in10(later["y"].mean())}）', '',
              f'- 和"建议上"同组合（尺寸 × 台面 × 元素）的：{act(REC.head(10))}',
              f'- 和"正在冒头、可小批量试"同组合的：{act(EMG.head(8))}',
              f'- 和"建议避开"同组合的：{act(AVD.head(8))}',
              '- 市场层"在涨的类型"之后怎样：见 两层识别_滚动回测.md 第 1 节。']
    out = os.path.join(ROOT, f'solution-v2/开发建议/两层建议_{ASOF}.md'); open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L[:60]))
