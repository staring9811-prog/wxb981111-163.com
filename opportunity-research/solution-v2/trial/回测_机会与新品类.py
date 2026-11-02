"""全面回测（站在 ASOF 月初，默认 2026-01）：① 所有产品类型，之前的机会有没有实现 / 变好；② 有没有冒出新的产品类型；③ 截至 ASOF 能看到的哪些信号能预测之后的高速增长。
产品类型 = 两个维度交叉（尺寸 × 台面、尺寸 × 元素、台面 × 元素、尺寸 × 价格档）或单维度（形态、主色、元素、台面）。
份额用"这个维度标签已知的行"作分母（台面、材质覆盖率逐月上升，直接用全部行会出假增长）。
三个时段：前前 = ASOF 前 12–7 个月，前 = ASOF 前 6–1 个月（1 月能看到的最近半年），后 = 2026-04 至 09（结果）。
新品：每个时段内上架、观察期走完的新家族做到的比例（做到 = 6 个月内小类前 50 或月销售额 $10 万）。
用法：ASOF=2026-01 python3 -I 回测_机会与新品类.py；输出 solution-v2/开发建议/回测_<ASOF>_全面.md。"""
import os, re, json, glob, numpy as np, pandas as pd
from scipy.stats import spearmanr
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
ASOF = os.environ.get('ASOF', '2026-01'); WORK = os.environ.get('WORK', '/tmp/开发建议_work'); os.makedirs(WORK, exist_ok=True)
mi = lambda s: int(str(s)[:4]) * 12 + int(str(s)[5:7]) - 1
ms = lambda i: f'{i // 12}-{i % 12 + 1:02d}'
T = mi(ASOF); END = mi('2026-09')
OUT = os.path.join(ROOT, f'solution-v2/开发建议/回测_{ASOF}_全面.md')
# 全量数据跑回归脚本第 0–3 节（单位、新家族、首月特征）
os.environ.update(DATA=os.path.join(ROOT, 'input/data_v2/统一打标/统一打标_分析用.pkl'), OUT_DIR=WORK, WITH_HOLD='1', NPERM='10')
P = os.path.join(HERE, '回归_新家族.py'); src = open(P, encoding='utf-8').read(); ns = {'__file__': P}
exec(compile(src[:src.index('# ---------- 4. 时间信号')], P, 'exec'), ns)
A, U, feat = ns['A'], ns['U'], ns['feat']
A = A.copy(); A['元素一'] = A['元素集'].map(lambda t: [e for e in t if e not in ('fluted', 'reeded')])
UNK = lambda v: v is None or (isinstance(v, float) and np.isnan(v)) or str(v) in ('未知', '', 'nan', 'None') or str(v).startswith('台面未知')
W = {'前前': (T - 12, T - 7), '前': (T - 6, T - 1), '后': (mi('2026-04'), END)}
# 维度取值（行级）
DIM = {'尺寸': A['尺寸段'], '台面': A['台面类型'], '价格档': A['价格档'], '形态': A['形态'], '主色': A['主色'], '材质': A['柜体材质']}
def row_keys(kind):
    a, b = kind
    if b is None:
        if a == '元素': return A['元素一'].map(lambda t: [(e,) for e in t])
        return DIM[a].map(lambda v: [] if UNK(v) else [(v,)])
    if '元素' in kind:
        o = a if b == '元素' else b
        return [[] if UNK(x) else [(x, e) for e in t] for x, t in zip(DIM[o], A['元素一'])]
    return [[] if (UNK(x) or UNK(y)) else [(x, y)] for x, y in zip(DIM[a], DIM[b])]
KINDS = [('尺寸', '台面'), ('尺寸', '元素'), ('台面', '元素'), ('尺寸', '价格档'), ('尺寸', '材质'), ('形态', None), ('主色', None), ('元素', None), ('台面', None), ('尺寸', None)]
# 新家族（首月特征）
def ukeys(u, kind):
    f = feat[u]; get = {'尺寸': f['主尺寸段'], '台面': f['台面类型'], '价格档': f['价格档'], '形态': f['形态'], '主色': f['主色'], '材质': f['柜体材质'],
                        '元素': [e for e in f['元素'] if e not in ('fluted', 'reeded', '未知')]}
    a, b = kind
    if b is None: return [(v,) for v in get[a] if not UNK(v)]
    return [(x, y) for x in get[a] for y in get[b] if not UNK(x) and not UNK(y)]
done = U[U['L'] + 5 <= END]
rows = []
for kind in KINDS:
    rk = pd.Series(row_keys(kind), index=A.index)
    ex = pd.DataFrame({'m': A['m'], 'c': A['c'], 'fam': A['家族键'], 'k': rk}).explode('k').dropna(subset=['k'])
    rec = {}
    for wn, (a, b) in W.items():
        e = ex[ex['m'].between(a, b)]; tot = e['c'].sum()
        g = e.groupby('k').agg(c=('c', 'sum'), fam=('fam', 'nunique'))
        nm = e.groupby(['k', 'm'])['fam'].nunique().groupby('k').mean()   # 平均每月在榜家族数
        for k_, r in g.iterrows(): rec.setdefault(k_, {})[wn] = dict(份额=r['c'] / tot, 月均销=r['c'] / (b - a + 1), 家族=r['fam'], 月均家族=nm.get(k_, np.nan))
    # 新品：前 = ASOF 前 12–7 个月上架（1 月时已走完）；后 = ASOF 起至 2026-04 上架（结果）
    nf = {}
    for wn, (a, b) in {'新品前': (T - 15, T - 7), '新品后': (T, mi('2026-04'))}.items():
        d = done[done['L'].between(a, b)]
        for u in d.index:
            for k_ in ukeys(u, kind): nf.setdefault(k_, {}).setdefault(wn, []).append(int(d.at[u, 'y']))
    for k_, v in rec.items():
        r = dict(类型=' × '.join(kind[:1] if kind[1] is None else kind), 取值=' × '.join(map(str, k_)))
        for wn in W: r.update({f'{m}_{wn}': v.get(wn, {}).get(m, 0.0) for m in ('份额', '月均销', '家族', '月均家族')})
        for wn in ('新品前', '新品后'):
            ys = nf.get(k_, {}).get(wn, []); r[f'{wn}_n'] = len(ys); r[f'{wn}_做到'] = sum(ys)
        rows.append(r)
R = pd.DataFrame(rows)
R['销量增长'] = (R['月均销_后'] + 1) / (R['月均销_前'] + 1) - 1          # 后 vs 前，绝对量
R['份额变化'] = R['份额_后'] - R['份额_前']
R['前动量'] = R['份额_前'] - R['份额_前前']                               # 1 月能看到的：最近半年份额比再前半年
R['前销量动量'] = (R['月均销_前'] + 1) / (R['月均销_前前'] + 1) - 1
R['单家族销_前'] = R['月均销_前'] / R['月均家族_前'].replace(0, np.nan)
R['新品率_前'] = R['新品前_做到'] / R['新品前_n'].replace(0, np.nan)
R['新品率_后'] = R['新品后_做到'] / R['新品后_n'].replace(0, np.nan)
cat_g = A[A['m'].between(*W['后'])]['c'].sum() / 6 / (A[A['m'].between(*W['前'])]['c'].sum() / 6) - 1
# 关键词：尺寸层面的搜索同比（研究包，1 月能看到的部分）
KW = os.path.join(ROOT, 'input/data_v2/keywords_20261028'); tag = pd.read_csv(f'{KW}/数据/01_关键词词库/tables/keywords_tagged.csv')
kr = []
for f in sorted(glob.glob(f'{KW}/数据/02_Amazon历史趋势/raw/*.json')):
    j = json.load(open(f, encoding='utf-8'))
    for r in json.loads(j['response']['content'][0]['text'])['data']:
        yy, mm = re.match(r'(\d{4})年(\d{2})月', r['time']).groups(); kr.append((j['keyword'], mi(f'{yy}-{mm}'), r['search']))
KL = pd.DataFrame(kr, columns=['kw', 'm', 's']); kb = dict(zip(tag['关键词'], tag['宽度（英寸）'].map(lambda w: ns['band'](w))))
KL['尺寸'] = KL['kw'].map(kb)
def kyoy(a, b):
    x = KL[KL['m'].between(a, b) & KL['尺寸'].notna()].groupby('尺寸')['s'].sum(); y = KL[KL['m'].between(a - 12, b - 12) & KL['尺寸'].notna()].groupby('尺寸')['s'].sum()
    return x / y - 1
KY_pre = kyoy(T - 6, T - 1); KY_post = kyoy(mi('2026-04'), END)
R['尺寸键'] = [v.split(' × ')[0] if t.startswith('尺寸') else None for t, v in zip(R['类型'], R['取值'])]
R['搜索同比_前'] = R['尺寸键'].map(KY_pre)

pct = lambda x: '—' if pd.isna(x) else f'{x:.1%}' if abs(x) < 0.1 else f'{x:.0%}'
pp = lambda x: '—' if pd.isna(x) else f'{x * 100:+.1f}'
nf_txt = lambda d, n: f'{d}/{n}' if n else '—'
L = [f'# 全面回测：站在 {ASOF} 月初，到 2026-09 看结果', '',
     f'> 由 `trial/回测_机会与新品类.py` 生成。"前" = {ms(W["前"][0])} 至 {ms(W["前"][1])}（1 月能看到的最近半年），"前前" = {ms(W["前前"][0])} 至 {ms(W["前前"][1])}，"后" = 2026-04 至 09（结果）。',
     '> 份额 = 这一维度标签已知的行里的销量占比（台面、材质标签覆盖率逐月上升，用全部行作分母会出假增长）。销量是卖家精灵的家族月销按子体平分后加总。',
     f'> 新品"前" = {ms(T - 15)} 至 {ms(T - 7)} 上架（1 月时已走完 6 个月），"后" = {ASOF} 至 2026-04 上架；格子里是 做到 / 新家族。', '',
     f'品类总月销："后"比"前" {cat_g:+.0%}。', '']

# ① 机会有没有实现 / 变好：各维度份额涨得最多、跌得最多
L += ['## 1. 之前的机会点有没有实现、变好（每个类型的份额和新品表现，前 → 后）', '']
for t in ['尺寸', '台面', '形态', '尺寸 × 台面', '尺寸 × 元素', '台面 × 元素', '尺寸 × 价格档']:
    d = R[(R['类型'] == t) & ((R['份额_前'] >= 0.01) | (R['份额_后'] >= 0.01))].sort_values('份额变化', ascending=False)
    if not len(d): continue
    show = pd.concat([d.head(6), d.tail(4)]).drop_duplicates('取值') if len(d) > 10 else d
    L += [f'### {t}', '', '| 取值 | 份额 前前 → 前 → 后 | 份额变化（前 → 后） | 月均销 前 → 后 | 平均每月在榜家族 前 → 后 | 新品 做到/家族 前 → 后 | 1 月能看到的动量（前前 → 前） |',
          '| :--- | :--- | ---: | :--- | :--- | :--- | ---: |']
    for r in show.itertuples():
        L.append(f"| {r.取值} | {pct(r.份额_前前)} → {pct(r.份额_前)} → {pct(r.份额_后)} | {pp(r.份额变化)} | {r.月均销_前:,.0f} → {r.月均销_后:,.0f} | {r.月均家族_前:.0f} → {r.月均家族_后:.0f} | "
                 f"{nf_txt(r.新品前_做到, r.新品前_n)} → {nf_txt(r.新品后_做到, r.新品后_n)} | {pp(r.前动量)} |")
    L += ['']

# ② 新冒出来的产品类型：前 份额 < 0.5% 且平均在榜家族 ≤ 2，后 份额 ≥ 1% 或平均在榜家族 ≥ 4
NEW = R[(R['份额_前'] < 0.005) & (R['月均家族_前'] <= 2) & ((R['份额_后'] >= 0.01) | (R['月均家族_后'] >= 4))].sort_values('份额_后', ascending=False)
L += ['## 2. 新冒出来的产品类型（1 月前半年几乎没有：份额 < 0.5%、平均每月在榜 ≤ 2 个家族；2026-04 至 09 份额 ≥ 1% 或平均每月在榜 ≥ 4 个家族）', '',
      '| 类型 | 份额 前前 → 前 → 后 | 平均每月在榜家族 前 → 后 | 新品 做到/家族 前 → 后 | 1 月时能看到的迹象 |', '| :--- | :--- | :--- | :--- | :--- |']
for r in NEW.itertuples():
    sig = []
    if r.前动量 > 0.001: sig.append(f'前半年份额已在涨（{pp(r.前动量)}）')
    if r.新品前_n and r.新品前_做到: sig.append(f'1 月前已有新品做到（{r.新品前_做到}/{r.新品前_n}）')
    if pd.notna(r.搜索同比_前) and r.搜索同比_前 > 0.15: sig.append(f'该尺寸搜索同比 {r.搜索同比_前:+.0%}')
    L.append(f"| {r.类型}：{r.取值} | {pct(r.份额_前前)} → {pct(r.份额_前)} → {pct(r.份额_后)} | {r.月均家族_前:.0f} → {r.月均家族_后:.0f} | {nf_txt(r.新品前_做到, r.新品前_n)} → {nf_txt(r.新品后_做到, r.新品后_n)} | {'；'.join(sig) or '看不出'} |")
L += ['', f'共 {len(NEW)} 个；1 月时至少有一个迹象的 {int(sum(1 for r in NEW.itertuples() if (r.前动量 > 0.001) or (r.新品前_n and r.新品前_做到) or (pd.notna(r.搜索同比_前) and r.搜索同比_前 > 0.15)))} 个。', '']

# ②b 小类型高速起来：前 份额 < 1%，后 ≥ 1% 且月均销是前的 2.5 倍以上（不含上面的全新类型）
FAST = R[(R['份额_前'] < 0.01) & (R['份额_后'] >= 0.01) & (R['月均销_后'] >= 2.5 * R['月均销_前']) & ~R.index.isin(NEW.index)].sort_values('份额_后', ascending=False)
L += ['### 小类型高速起来的（前半年份额 < 1%，之后 ≥ 1%、月均销涨到 2.5 倍以上）', '',
      '| 类型 | 份额 前前 → 前 → 后 | 月均销 前 → 后 | 平均每月在榜家族 前 → 后 | 新品 做到/家族 前 → 后 | 1 月时能看到的迹象 |', '| :--- | :--- | :--- | :--- | :--- | :--- |']
for r in FAST.itertuples():
    sig = []
    if r.前动量 > 0.001: sig.append(f'前半年份额已在涨（{pp(r.前动量)}）')
    if r.新品前_n and r.新品前_做到: sig.append(f'1 月前已有新品做到（{r.新品前_做到}/{r.新品前_n}）')
    if pd.notna(r.搜索同比_前) and r.搜索同比_前 > 0.15: sig.append(f'该尺寸搜索同比 {r.搜索同比_前:+.0%}')
    L.append(f"| {r.类型}：{r.取值} | {pct(r.份额_前前)} → {pct(r.份额_前)} → {pct(r.份额_后)} | {r.月均销_前:,.0f} → {r.月均销_后:,.0f} | {r.月均家族_前:.0f} → {r.月均家族_后:.0f} | {nf_txt(r.新品前_做到, r.新品前_n)} → {nf_txt(r.新品后_做到, r.新品后_n)} | {'；'.join(sig) or '看不出'} |")
L += ['', f'共 {len(FAST)} 个；1 月时至少有一个迹象的 {int(sum(1 for r in FAST.itertuples() if (r.前动量 > 0.001) or (r.新品前_n and r.新品前_做到) or (pd.notna(r.搜索同比_前) and r.搜索同比_前 > 0.15)))} 个。', '']
# ③ 哪些 1 月能看到的信号能预测"后"的增长（类型层面的秩相关）
D = R[(R['月均家族_前'] >= 2) & (R['月均销_前'] > 0)].copy()
D['后增长'] = D['销量增长']
sigs = {'前半年份额动量（前前 → 前）': '前动量', '前半年销量增长': '前销量动量', '前半年新品做到的比例': '新品率_前', '单家族月销（供不应求）': '单家族销_前',
        '在榜家族数（越少越空）': '月均家族_前', '尺寸的搜索同比（只有尺寸类型）': '搜索同比_前'}
L += ['## 3. 1 月能看到的哪个信号，能预测之后哪些类型涨得快', '',
      f'在"前"半年至少平均每月 2 个家族在榜的 {len(D)} 个类型上，算每个信号和"后 vs 前 月均销增长"的秩相关（Spearman；正 = 信号越高之后涨得越快）。', '',
      '| 信号 | 秩相关 | p | 能算的类型 | 按信号排前 20% 的类型，之后月均销增长中位 | 后 20% |', '| :--- | ---: | ---: | ---: | :--- | :--- |']
for nm_, c in sigs.items():
    d = D[[c, '后增长']].dropna()
    if len(d) < 8: continue
    rho, p = spearmanr(d[c], d['后增长']); q = d[c].quantile([0.2, 0.8])
    L.append(f"| {nm_} | {rho:+.2f} | {p:.3f} | {len(d)} | {d.loc[d[c] >= q[0.8], '后增长'].median():+.0%} | {d.loc[d[c] <= q[0.2], '后增长'].median():+.0%} |")
R.to_csv(os.path.join(WORK, f'回测类型_{ASOF}.csv'), index=False, encoding='utf-8-sig')
os.makedirs(os.path.dirname(OUT), exist_ok=True); open(OUT, 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L))
