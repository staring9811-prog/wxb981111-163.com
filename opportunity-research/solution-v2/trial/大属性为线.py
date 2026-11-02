"""第五版：大属性为线（规则见 识别方法_预登记.md 补记第五版；state.json S2-57）。
1. 尺寸、台面、主色、柜体材质、元素各自算每个取值：预估增量、增长分位、溢价、缺口（只有尺寸）、新品做到的比例，给出 增 / 减 / 维持。
2. 月均销 ≥ 1,000 件的取值，按另一个大属性拆一层（300–1,000 件标"参考"，< 300 不拆）。
3. 方案的市场支撑 = 各属性第 1 层分位的平均（两维格子 ≥ 1,000 件时用格子分位替换对应两项）；配新品打分（近期加权、校准）。
MODE=建议 ASOF=yyyy-mm → solution-v2/开发建议/大属性为线_<ASOF>.md；MODE=回测 → 4 个时点和第一、三版比，solution-v2/开发建议/大属性为线_回测.md。"""
import os, numpy as np, pandas as pd
from scipy.stats import spearmanr
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
MODE = os.environ.get('MODE', '建议'); ASOF = os.environ.get('ASOF', '2026-10'); os.environ['MODE'] = '库'
P = os.path.join(HERE, '两层识别.py'); ns = {'__file__': P}
exec(compile(open(P, encoding='utf-8').read(), P, 'exec'), ns)
A, U, feat, mi, ms, END, newprod, search_yoy, TK, KS, UNK = (ns[k] for k in ('A', 'U', 'feat', 'mi', 'ms', 'END', 'newprod', 'search_yoy', 'TK', 'KS', 'UNK'))
DIMS = {'尺寸': '尺寸段', '台面': '台面类型', '主色': '主色', '材质': '柜体材质', '元素': '元素一'}
FKEY = {'尺寸': lambda f: f['主尺寸段'], '台面': lambda f: f['台面类型'], '主色': lambda f: f['主色'], '材质': lambda f: f['柜体材质'],
        '元素': lambda f: [e for e in f['元素'] if e not in ('fluted', 'reeded', '未知')]}
def member(col, v): return A[col].map(lambda t: v in t) if col == '元素一' else A[col].eq(v)
def vals(col, mask):
    s = A.loc[mask, col]
    if col == '元素一': return pd.Series([e for t in s for e in t]).value_counts().index.tolist()
    return [v for v in s.dropna().unique() if not UNK(v)]
pct = lambda x: '—' if pd.isna(x) else (f'{x:.1%}' if abs(x) < 0.1 else f'{x:.0%}')
in10 = lambda p: '—' if pd.isna(p) else f'{p * 10:.1f}'.rstrip('0').rstrip('.')

def level(T, parent, col, dim, ref_price):
    R6, R12 = A['m'].between(T - 6, T - 1), A['m'].between(T - 12, T - 7)
    RO = A['m'].between(T + 3, min(T + 8, END)); NO = max(1, min(T + 8, END) - T - 2); out = T + 3 <= END
    yo = search_yoy(T); rows = []
    for v in vals(col, parent & R6):
        m = parent & member(col, v); a6, a12 = A[m & R6], A[m & R12]
        rows.append(dict(值=v, 前=a6['c'].sum() / 6, 前前=a12['c'].sum() / 6, 家族=a6.groupby('m')['家族键'].nunique().sum() / 6,
                         家族前前=a12.groupby('m')['家族键'].nunique().sum() / 6, 中位价=a6['价格'].median(), S3=yo.get((dim, v), np.nan),
                         后=A[m & RO]['c'].sum() / NO if out else np.nan))
    D = pd.DataFrame(rows); D = D[D['前'] > 0].copy()
    if len(D) < 2: return None
    D['S1'] = np.log((D['前'] + 1) / (D['前前'] + 1)); D['S2'] = D['家族'] - D['家族前前']
    D['分位'] = D[['S1', 'S2', 'S3']].rank(pct=True).mean(axis=1, skipna=True).rank(pct=True)
    D['预估增量'] = D['前'] * (D['分位'] - 0.5); D['份额'] = D['前'] / D['前'].sum(); D['溢价'] = D['中位价'] / ref_price
    D['实际增量'] = D['后'] - D['前']
    D['动作'] = np.where((D['分位'] >= 0.7) & (D['预估增量'] > 0), '增', np.where(D['分位'] <= 0.3, '减', '维持'))
    return D

def build(T):
    allm = pd.Series(True, index=A.index); cat = A[A['m'].between(T - 6, T - 1)]['价格'].median()
    L1 = {d: level(T, allm, c, d, cat) for d, c in DIMS.items()}
    # 新品做到的比例（T−15 至 T−7 上架、已走完）
    co = U[U['L'].between(T - 15, T - 7) & (U['L'] + 5 <= END)]
    for d, D in L1.items():
        D[['新品做到', '新品数']] = [(int(co.loc[[u for u in co.index if v in FKEY[d](feat[u])], 'y'].sum()), sum(v in FKEY[d](feat[u]) for u in co.index)) for v in D['值']]
    # 下探：≥ 1,000 件拆一层（300–1,000 参考）
    L2 = {}
    for d, D in L1.items():
        for r in D[D['前'] >= 300].itertuples():
            pm = member(DIMS[d], r.值)
            for d2, c2 in DIMS.items():
                if d2 == d: continue
                X = level(T, pm, c2, d2, r.中位价)
                if X is not None: L2[(d, r.值, d2)] = (X, '下探' if r.前 >= 1000 else '参考')
    return L1, L2

def support(T, L1, L2, attrs):
    """方案 / 家族的市场支撑：各属性第 1 层分位平均；所在两维格子 ≥ 1,000 件时，用格子里的分位替换这两项。"""
    p = {}
    for d, v in attrs.items():
        D = L1.get(d)
        if D is not None and v in set(D['值']): p[d] = float(D.set_index('值').at[v, '分位'])
    for (d, v, d2), (X, how) in L2.items():
        if how == '下探' and attrs.get(d) == v and d2 in attrs and attrs[d2] in set(X['值']):
            q = float(X.set_index('值').at[attrs[d2], '分位']); p[d] = q; p[d2] = q
    return np.mean(list(p.values())) if p else np.nan

def fam_attrs(u):
    f = feat[u]; return {d: (FKEY[d](f)[0] if FKEY[d](f) else None) for d in DIMS}

if MODE == '回测':
    L = ['# 第五版（大属性为线）回测：和第一版、第三版并排比', '', '> 由 `trial/大属性为线.py` 生成；规则见 识别方法_预登记.md 补记第五版。门槛（300 / 1,000 件）是从这 4 个时点看出来的，属于样本内。', '',
         '## 1. 大属性层面：每个属性"增"的取值，之后实际怎样', '', '| 时点 | 属性 | 标"增"的取值 | 这些取值之后合计实际增量（件 / 月） | 标"减"的取值合计 | 秩相关（预估 vs 实际） |', '| :--- | :--- | :--- | ---: | ---: | ---: |']
    FAMROWS = []
    for Ts in ('2025-10', '2025-11', '2025-12', '2026-01'):
        T = mi(Ts); L1, L2 = build(T)
        for d, D in L1.items():
            up = D[D['动作'] == '增']; dn = D[D['动作'] == '减']
            L.append(f"| {Ts} | {d} | {'、'.join(map(str, up['值'])) or '—'} | {up['实际增量'].sum():+,.0f} | {dn['实际增量'].sum():+,.0f} | {spearmanr(D['预估增量'], D['实际增量'])[0]:+.2f} |")
        # 新品层面：第五版 = 支撑 ≥ 0.6 且新品打分 ≥ 平均；避开 = 支撑 ≤ 0.4 或打分后 20%
        c = U[U['L'].between(T, T + 3) & (U['L'] + 5 <= END)]; tr = U[U['L'] + 5 <= T - 1]
        s2 = newprod(T, True); p = pd.Series(s2(list(c.index)), index=c.index); ptr = pd.Series(s2(list(tr.index)), index=tr.index)
        sup = pd.Series([support(T, L1, L2, fam_attrs(u)) for u in c.index], index=c.index)
        rec5 = (sup >= 0.6) & (p >= ptr.mean()); avd5 = (sup <= 0.4) | (p <= ptr.quantile(0.2))
        s1 = newprod(T, False); p1 = pd.Series(s1(list(c.index)), index=c.index); ptr1 = pd.Series(s1(list(tr.index)), index=tr.index)
        rec1, avd1 = p1 >= ptr1.quantile(0.7), p1 <= ptr1.quantile(0.3)
        FAMROWS.append((Ts, c['y'], rec1, avd1, rec5, avd5, sup))
    L += ['', '## 2. 新品层面："建议上 / 避开"的新品实际做到的比例（T 至 T+3 上架、观察期已走完）', '',
          '第五版：市场支撑（各属性分位平均）≥ 60% 且新品打分 ≥ 平均 = 建议上；支撑 ≤ 40% 或打分在后 20% = 避开。第一版：新品打分前 30% / 后 30%。', '',
          '| 时点 | 全部 | 第一版 建议上 / 避开 | 第五版 建议上 / 避开 | 只看市场支撑：前 30% / 后 30% |', '| :--- | :--- | :--- | :--- | :--- |']
    for Ts, y, r1, a1, r5, a5, sup in FAMROWS:
        f = lambda m: f"{int(y[m].sum())}/{int(m.sum())}（{in10(y[m].mean()) if m.any() else '—'}）"
        hs, ls_ = sup >= sup.quantile(0.7), sup <= sup.quantile(0.3)
        L.append(f"| {Ts} | {in10(y.mean())}（{len(y)} 个） | {f(r1)} / {f(a1)} | {f(r5)} / {f(a5)} | {f(hs)} / {f(ls_)} |")
    out = os.path.join(ROOT, 'solution-v2/开发建议/大属性为线_回测.md'); open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L))

if MODE == '建议':
    T = mi(ASOF); L1, L2 = build(T); out_known = T + 3 <= END
    L = [f'# 开发建议（第五版 · 大属性为线）：站在 {ASOF} 月初', '',
         f'> 只用截至 {ms(T - 1)} 的数据。由 `trial/大属性为线.py` 生成；规则见 识别方法_预登记.md 补记第五版、state.json S2-57。',
         '> 先在五个大属性（尺寸、台面、颜色、柜体材质、元素）上各自看信号，再只在月均销 ≥ 1,000 件的大格子里往下拆一层；方案由各属性信号合起来支撑，再配新品打分。',
         '> "预估增量" = 前 6 个月月均销 ×（增长分位 − 0.5），件 / 月；"增长分位"综合销量动量、新进家族、搜索同比，只和同一属性里的其他取值比；"溢价" = 中位价 ÷ 全品类中位价；'
         '"缺口" = 关键词搜索份额 − 销量份额（只有尺寸）；"新品" = 已走完 6 个月的新家族，做到 / 家族（做到 = 6 个月内小类前 50 或月销售额 $10 万）。', '']
    for d, D in L1.items():
        D = D.sort_values('预估增量', ascending=False)
        L += [f'## 第 1 层 · {d}', '', '| 取值 | 动作 | 月均销 前 6 个月（变化） | 份额 | 增长分位 | 预估增量 | 溢价 | 搜索同比 | 新品 做到/家族 |' + (' 实际增量 |' if out_known else ''),
              '| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | :--- |' + (' ---: |' if out_known else '')]
        for r in D.head(10).itertuples():
            L.append(f"| {r.值} | **{r.动作}** | {r.前:,.0f}（{np.expm1(r.S1):+.0%}） | {pct(r.份额)} | {r.分位:.0%} | {r.预估增量:+,.0f} | {r.溢价:.2f} | {pct(r.S3) if pd.notna(r.S3) else '—'} | {r.新品做到}/{r.新品数} |"
                     + (f" {r.实际增量:+,.0f} |" if out_known else ''))
        L += ['']
    L += ['## 第 2 层 · 只在月均销 ≥ 1,000 件的大格子里往下拆（每个格子列"增"的前 3 个和"减"的前 2 个）', '']
    for (d, v, d2), (X, how) in L2.items():
        if how != '下探': continue
        up = X[X['动作'] == '增'].sort_values('预估增量', ascending=False).head(3); dn = X[X['动作'] == '减'].sort_values('预估增量').head(2)
        if not len(up) and not len(dn): continue
        f = lambda r: f"{r.值}（{r.前:,.0f} 件，{np.expm1(r.S1):+.0%}" + (f"，实际 {r.实际增量:+,.0f}" if out_known else '') + '）'
        L.append(f"- **{d} = {v} 里按{d2}**：增 {'、'.join(f(r) for r in up.itertuples()) or '—'}；减 {'、'.join(f(r) for r in dn.itertuples()) or '—'}")
    # 方案：尺寸 × 台面 × 主色 × 材质 × 元素，市场支撑 + 新品打分
    tr = U[U['L'] + 5 <= T - 1]; sc = newprod(T, True)
    rec_u = tr[tr['L'] >= tr['L'].max() - 5]; r_obs = rec_u['y'].mean(); p_bar = sc(list(rec_u.index)).mean()
    shift = np.log(r_obs / (1 - r_obs)) - np.log(p_bar / (1 - p_bar)); cal = lambda p: 1 / (1 + np.exp(-(np.log(p / (1 - p)) + shift)))
    avg = cal(sc(list(tr.index))).mean()
    top = lambda d, n: L1[d].sort_values('预估增量', ascending=False).head(n)['值'].tolist()
    cands = []
    for s in top('尺寸', 5):
        for t in top('台面', 4):
            for c in top('主色', 4):
                for mtl in top('材质', 3):
                    for e in top('元素', 6):
                        attrs = dict(尺寸=s, 台面=t, 主色=c, 材质=mtl, 元素=e)
                        k = f'V5|{s}|{t}|{c}|{e}'
                        TK[k] = [f'尺寸={s}', '档=中', f'台面={t}', f'主色={c}', '装=拆装', '形态=落地式', f'元素={e}', '颜色≥2', '子体≥4']
                        cands.append(dict(**attrs, 支撑=support(T, L1, L2, attrs), k=k))
    Cd = pd.DataFrame(cands); Cd['p'] = cal(sc(list(Cd['k'])))
    best = Cd[Cd['p'] >= avg].sort_values(['支撑', 'p'], ascending=False).drop_duplicates(['尺寸', '台面', '元素']).head(10)
    def after(s):
        d = tr[(tr['主尺寸段'] == s) & (tr['y'] == 1)]; return d['首次达线月龄'].median(), d['最高销售额'].median()
    L += ['', '## 第 3 步 · 方案：各属性都在"增"的方向上，而且新品做到的机会 ≥ 平均', '', f'当期新品平均每 10 个做到 {in10(avg)} 个（按最近半年上架的新品水平校准）。默认中档、落地式、拆装、首月 ≥ 2 色、≥ 4 子体。', '',
          '| 方案 | 市场支撑（各属性增长分位平均） | 每 10 个做到几个 | 做到的话第几个月 | 做到后最高月销售额（同尺寸中位） |', '| :--- | ---: | :--- | :--- | :--- |']
    for r in best.itertuples():
        mo, rev = after(r.尺寸)
        L.append(f"| {r.尺寸} + {r.台面} + {r.元素}，主色{r.主色}，{r.材质} | {r.支撑:.0%} | **{in10(r.p)}** | 第 {mo:.0f} 个月 | ${rev / 1000:.0f}k |")
    if out_known:
        c = U[U['L'].between(T, T + 3) & (U['L'] + 5 <= END)]
        m = [u for u in c.index if any((feat[u]['主尺寸段'][0], feat[u]['台面类型'][0], e) in {(r.尺寸, r.台面, r.元素) for r in best.itertuples()} for e in feat[u]['元素'])]
        L += ['', f'核对：{ASOF} 至 {ms(T + 3)} 上架的新家族里，和这些方案同"尺寸 × 台面 × 元素"的 {len(m)} 个，做到 {int(c.loc[m, "y"].sum())} 个'
              + (f'（每 10 个 {in10(c.loc[m, "y"].mean())}，全部 {in10(c["y"].mean())}）。' if m else '。')]
    out = os.path.join(ROOT, f'solution-v2/开发建议/大属性为线_{ASOF}.md'); open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L[:80]))
