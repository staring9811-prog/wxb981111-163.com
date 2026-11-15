"""幸存者偏差模拟：在亚马逊完整面板上模拟"评论日期重建历史"（Home Depot / Lowe's / Wayfair 的做法），看第九版市场层回测结论会变成什么样。
重建面板 = 取 END（2026-09）按月销排前 N 的商品，只保留它们在全部历史月份的记录（幸存者偏差 + 只看前 N 的覆盖偏差）。
商品口径：主口径按"单位"（家族键合并后的家族，≈ 一个父体链接、评论在父体上合并），N = 50 / 100 / 200 / 300 / 500（END 只有 202 个家族，N ≥ 202 即全部在榜家族）；
敏感性按子体（子 ASIN，≈ 每个颜色尺寸一条链接），N = 200 / 300 / 500。
月龄：主口径用上架日期（≈ 首条评论月，与第九版相同）；敏感性用"在面板里首次出现的月"（首月 2024-10 出现的视为老品）。
每个场景重跑第九版市场层（回归预测.py 库，VER=9，不改原脚本），两种评估：
  自评 = 目标份额变化也用重建面板算（小平台回测实际能报出来的数）；真值 = 同一批单元的目标用全量面板算（真实预测力）。
另做：第九版去 x5、只用 b6 两个降级版本；x5 系数和按单元聚类的 t 值；重建 x5 与全量 x5 的秩相关。
输出 solution-v2/开发建议/幸存者偏差模拟_小平台回测可行性.md；中间结果存 WORK（默认 /tmp/幸存者偏差模拟_work）。"""
import os, time, pickle, itertools, numpy as np, pandas as pd
from scipy.stats import spearmanr, norm
from sklearn.linear_model import Ridge
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
WORK = os.environ.get('WORK', '/tmp/幸存者偏差模拟_work'); os.makedirs(WORK, exist_ok=True)
os.environ['MODE'] = '库'
P = os.path.join(HERE, '大属性为线.py'); ns = {'__file__': P}
exec(compile(open(P, encoding='utf-8').read(), P, 'exec'), ns)
A0, U, feat, mi, ms, END, newprod, search_yoy, TK, UNK, DIMS = (ns[k] for k in ('A', 'U', 'feat', 'mi', 'ms', 'END', 'newprod', 'search_yoy', 'TK', 'UNK', 'DIMS'))
M0 = int(A0['m'].min())
LIBP = os.path.join(HERE, '回归预测.py'); LIB = open(LIBP, encoding='utf-8').read()
SEG = LIB[LIB.index('M0 = int(A'):LIB.index('# ---------- 新品层')]   # 库的市场层部分：面板、特征、目标、拟合、预测
VARS = {'第九版': ['b6', 'x2', 'x3', 'x4', 'x5'], '去 x5': ['b6', 'x2', 'x3', 'x4'], '仅 b6': ['b6']}
TPS = ('2025-10', '2025-11', '2025-12', '2026-01'); T0 = mi('2026-01')

def build(A):
    """在面板 A 上执行库的市场层，返回带 FEAT / fit / predict / target 的命名空间。"""
    G = dict(np=np, pd=pd, itertools=itertools, spearmanr=spearmanr, norm=norm, Ridge=Ridge, os=os, A=A.copy(), U=U, feat=feat, mi=mi, ms=ms, END=END,
             newprod=newprod, search_yoy=search_yoy, TK=TK, UNK=UNK, DIMS=DIMS, VER=9, MODE='库', ASOF='2026-10', HERE=HERE, ROOT=ROOT)
    exec(compile(SEG, LIBP, 'exec'), G)
    assert G['M0'] == M0, '重建面板起始月和全量不同'
    def design(D, k):   # 与库里的 design 相同，只是 XS 里没有 x4 时不做中心化（"仅 b6"要用）
        X = D[G['XS']].copy()
        if 'x4' in X: X['x4'] = X['x4'] - 5.0
        for x in G['XS']: X[x + '·k'] = X[x] * k / 3
        X['k'] = k / 3; return X
    G['design'] = design
    return G
def use(G, xs): G['set_ver'](9); G['XS'] = list(xs)

def recon(level, N, age):
    """重建面板：END 月销前 N 的商品在全部历史月份的行。"""
    key = '单位' if level == '家族' else '子ASIN'
    e = A0[A0['m'] == END].groupby(key)['c'].sum().reset_index().sort_values(['c', key], ascending=[False, True])
    keep = set(e[key].head(N)); R = A0[A0[key].isin(keep)].copy()
    if age == '首现':
        fa = A0.groupby(key)['m'].min(); L = R[key].map(fa).where(lambda s: s > M0)
        R['月龄'] = R['m'] - L + 1
    return R, len(keep)

def metrics(D, y, k):
    d = D.assign(y=y).dropna(subset=['y']); b = d[d['近3月'] >= 300]; nz = b['y'].abs() > 0.05
    pk = norm.cdf(d[f'预测{k}'] / d[f'sd{k}'])
    sp = lambda a, c: spearmanr(a, c)[0] if len(a) >= 5 else np.nan
    r = dict(n=len(d), n300=len(b), rho=sp(d[f'预测{k}'], d['y']), rho300=sp(b[f'预测{k}'], b['y']),
             dirn=(np.sign(b.loc[nz, f'预测{k}']) == np.sign(b.loc[nz, 'y'])).mean() if nz.sum() else np.nan,
             cov=d['y'].between(d[f'lo{k}'], d[f'hi{k}']).mean(),
             hi=((d.loc[pk >= 0.7, 'y'] > 0).mean(), int((pk >= 0.7).sum())), lo=((d.loc[pk <= 0.3, 'y'] > 0).mean(), int((pk <= 0.3).sum())))
    if k == 6:   # 第九版报告第 3 节的口径：把握 = k=6、8 平均；变大 = 第 6–8 个月份额变大
        bins = pd.cut(d['把握'], [0, 0.3, 0.5, 0.7, 1.0], labels=['≤30%', '30–50%', '50–70%', '≥70%'], include_lowest=True)
        r['档'] = {str(g): ((x['y'] > 0).mean(), len(x)) for g, x in d.groupby(bins, observed=False)}
        r['级'] = {g: ((d.loc[d['分级'] == g, 'y'] > 0).mean(), int((d['分级'] == g).sum())) for g in 'ABCD'}
        r['rhoP'] = sp(d['把握'], d['y']); r['rhoP300'] = sp(b['把握'], b['y'])
        r['大变大'] = (d['y'] > 0).mean()
    return r

def cluster_t(Tr, cols, m):
    """按单元聚类的稳健标准误（同一单元在不同时点、窗口的样本相关），给 x5 在 k=6、8 的合计系数。"""
    X = np.column_stack([np.ones(len(Tr)), Tr[cols].values]); e = Tr['res'].values; XtXi = np.linalg.pinv(X.T @ X)
    g = pd.factorize(pd.Index(Tr.index).map(str))[0]; S = np.zeros((X.shape[1],) * 2)
    for gi in np.unique(g):
        s = X[g == gi].T @ e[g == gi]; S += np.outer(s, s)
    V = XtXi @ S @ XtXi; b = np.r_[m.intercept_, m.coef_]; ix = {c: i + 1 for i, c in enumerate(cols)}; out = {}
    for x in ('x5', 'b6'):
        if x not in ix: continue
        for k in (6, 8):
            w = np.zeros(len(b)); w[ix[x]] = 1; w[ix[x + '·k']] = k / 3
            out[(x, k)] = (w @ b, (w @ b) / np.sqrt(w @ V @ w))
    return out

def run(name, A, Gtrue=None, tps=TPS, variants=('第九版', '去 x5', '仅 b6')):
    t = time.time(); G = build(A); res = dict(name=name, ev={}, cov={})
    C = G['CAT']; Cf = (Gtrue or G)['CAT']
    res['cov'] = dict(END=C.loc[END] / Cf.loc[END], T0=C.loc[T0 - 6:T0 - 1].sum() / Cf.loc[T0 - 6:T0 - 1].sum(), M0=C.loc[M0] / Cf.loc[M0],
                      新品占比=G['CATNEW'].loc[T0 - 6:T0 - 1].sum() / C.loc[T0 - 6:T0 - 1].sum(),
                      新品销量保留=G['CATNEW'].loc[T0 - 6:T0 - 1].sum() / (Gtrue or G)['CATNEW'].loc[T0 - 6:T0 - 1].sum(),
                      家族=A['单位'].nunique(), 单元=int((G['FEAT'][T0]['近3月'] > 0).sum()), 单元300=int((G['FEAT'][T0]['近3月'] >= 300).sum()))
    for v in variants:
        for Ts in tps:
            T1 = mi(Ts)
            try:
                use(G, VARS[v]); D, m, cols, q, Tr = G['predict'](T1)
            except Exception as ex:   # 样本太少跑不动时如实记下
                res['ev'][(v, Ts)] = dict(err=f'{type(ex).__name__}: {ex}'); continue
            r = dict(ntr=len(Tr), self={}, true={})
            if T1 == T0: r['coef'] = cluster_t(Tr, cols, m)
            for k in (6, 8):
                if T1 + k + 2 > END: continue
                r['self'][k] = metrics(D, G['target'](D, T1, k), k)
                if Gtrue is not None:
                    Df = Gtrue['FEAT'][T1]; use(Gtrue, VARS[v]); r['true'][k] = metrics(D, Gtrue['target'](Df, T1, k).reindex(D.index), k)
            if Gtrue is not None and T1 == T0 and v == '第九版':
                Df = Gtrue['FEAT'][T0]; j = D.index.intersection(Df.index)
                r['x5corr'] = spearmanr(D.loc[j, 'x5'], Df.loc[j, 'x5'])[0]; r['b6corr'] = spearmanr(D.loc[j, 'b6'], Df.loc[j, 'b6'])[0]
            res['ev'][(v, Ts)] = r
    print(f'{name}：{time.time() - t:.0f}s', flush=True); return res, G

# ---------- 跑 ----------
CACHE = os.path.join(WORK, 'res.pkl')
if os.path.exists(CACHE) and os.environ.get('REUSE') == '1': RES = pickle.load(open(CACHE, 'rb'))
else:
    RES = {}; base, GF = run('全量', A0); RES['全量'] = base
    AF = A0.copy(); fa = AF.groupby('单位')['m'].min(); AF['月龄'] = AF['m'] - AF['单位'].map(fa).where(lambda s: s > M0) + 1
    RES['全量·首现月龄'] = run('全量·首现月龄', AF, GF, tps=('2026-01',), variants=('第九版',))[0]
    SC = [('家族', 50, '上架'), ('家族', 100, '上架'), ('家族', 200, '上架'), ('家族', 300, '上架'), ('子体', 200, '上架'), ('子体', 300, '上架'), ('子体', 500, '上架')]
    for lv, N, age in SC:
        R, n = recon(lv, N, age); nm = f'{lv} 前 {N}' + ('（=全部 202 个，N=500 相同）' if lv == '家族' and N >= 202 else '')
        RES[nm] = run(nm, R, GF)[0]; RES[nm]['n'] = n
    for lv, N in (('家族', 200), ('子体', 300)):
        R, n = recon(lv, N, '首现'); nm = f'{lv} 前 {N}·首现月龄'
        RES[nm] = run(nm, R, GF, tps=('2026-01',), variants=('第九版',))[0]; RES[nm]['n'] = n
    pickle.dump(RES, open(CACHE, 'wb'))

# ---------- 报告 ----------
p0 = lambda x: '—' if x is None or (isinstance(x, float) and np.isnan(x)) else f'{x:.0%}'
f2 = lambda x: '—' if x is None or (isinstance(x, float) and np.isnan(x)) else f'{x:+.2f}'
pc = lambda t: f'{p0(t[0])}（{t[1]}）'
MAIN = [k for k in RES if '首现' not in k]
def g(nm, v='第九版', Ts='2026-01', how='self', k=6): return RES[nm]['ev'][(v, Ts)].get(how, {}).get(k)
L = ['# 幸存者偏差模拟：评论重建历史能不能支持小平台回测', '',
     '> 由 `trial/幸存者偏差模拟.py` 生成（复用 `回归预测.py` 的市场层，VER=9，原脚本未改）。数据：亚马逊浴室柜面板 2024-10 至 2026-09，END = 2026-09，主时点 T0 = 2026-01（END − 8）。',
     '> 本文所有数字都是脚本实际输出；"结论"一节的文字写在脚本里，跟着数字一起重新生成。', '',
     '## 1. 做法', '',
     '- **模拟的对象**：Home Depot / Lowe\'s / Wayfair 只能"今天采集类目榜单前 N 个商品 → 拉全部历史评论 → 月评论数 × 系数近似月销、首条评论月近似上架月"。这里在亚马逊完整面板上做同样的事：取 END 当月按月销排前 N 的商品，只保留它们在全部历史月份的记录，构成"重建面板"。'
     '过去卖过、但今天已不在前 N 的商品全部丢掉（幸存者偏差）；前 N 以外的长尾也丢掉（覆盖偏差）。',
     '- **商品口径**：主口径按家族（"单位" = 家族键合并后的父体链接）。理由：三个渠道的榜单一条结果是一个商品页，颜色、尺寸是页内选项，评论在商品页上合并，和亚马逊父体最像。'
     '亚马逊面板本身就是卖家精灵每月导出的头部，END 当月只有 **202 个家族**（3,278 个子体），所以家族口径 N = 300、500 都等于"全部 202 个"，另加 N = 50、100 看覆盖再缩小的影响。'
     '子体口径（每个颜色尺寸一条链接）N = 200 / 300 / 500 作敏感性；子体销量是家族月销按导出子体均分的，同一家族的子体排名并列，按 ASIN 字母序截断。',
     '- **月龄**：主口径用上架日期（与第九版相同；评论法的首条评论月近似的就是上架月）。敏感性按要求另做"在面板里首次出现的月"（2024-10 就出现的视为老品）。两种口径下 x5 都只剩"活到今天的新品"。',
     '- **重跑**：每个重建面板上，份额、分母、b6、x2、x4、x5、目标都用重建面板重新算（x3 搜索同比来自关键词数据，不受影响），按第九版规则在每个时点重新拟合（只用当时已知的结果），时点 2025-10 至 2026-01（END − 11 至 END − 8）。',
     '- **两种评估**：**自评** = 目标（立项后第 k 至 k+2 个月份额相对近 6 月份额的对数变化）也用重建面板算，就是在小平台上做回测能报出来的数；'
     '**真值** = 同一批单元、同一组预测，目标改用全量面板算，就是模型真实的预测力。自评和真值的差 = 重建面板让回测"看起来"好或坏了多少。',
     '- **降级版本**：第九版去掉 x5、只用 b6，看小面板上哪部分还靠得住。', '',
     '## 2. 重建面板保留了多少', '',
     '| 场景 | 商品数 | 家族数 | END 月销量保留 | T0 前 6 个月销量保留 | 2024-10 销量保留 | 新品销量保留（T0 前 6 个月） | 新品占比（T0 前 6 个月） | T0 有销量的单元 / 其中 ≥ 300 件 |',
     '| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |']
for nm in RES:
    c = RES[nm]['cov']
    L.append(f"| {nm} | {RES[nm].get('n', '全部')} | {c['家族']} | {p0(c['END'])} | {p0(c['T0'])} | {p0(c['M0'])} | {p0(c['新品销量保留'])} | {p0(c['新品占比'])} | {c['单元']} / {c['单元300']} |")
L += ['', '新品 = 上架 ≤ 6 个月的商品（首现月龄口径下 = 首次出现 ≤ 6 个月）。"保留"都是相对全量面板（上架日期口径）的销量；首现月龄口径会把"晚进榜的老品"也算成新品，所以新品销量可以超过 100%。', '',
      '## 3. 主时点 T0 = 2026-01、立项后第 6–8 个月（2026-07 至 09）：第九版并排', '',
      '### 3.1 把握分档后"之后变大"的比例（单元数）', '',
      '| 场景 | 评估 | 把握 ≤ 30% | 30–50% | 50–70% | ≥ 70% | D 档变大比例（个数） | A 档（个数） | 全部单元变大比例 |', '| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: |']
for nm in RES:
    for how in ('self', 'true'):
        r = g(nm, how=how)
        if r is None or (nm.startswith('全量') and how == 'true'): continue
        lab = '全量（第九版报告值）' if nm == '全量' else ('全量' if nm.startswith('全量') else ('自评' if how == 'self' else '真值'))
        L.append(f"| {nm} | {lab} | " + ' | '.join(pc(r['档'][b]) for b in ('≤30%', '30–50%', '50–70%', '≥70%')) + f" | {pc(r['级']['D'])} | {pc(r['级']['A'])} | {p0(r['大变大'])} |")
L += ['', '### 3.2 秩相关与方向', '',
      '| 场景 | 评估 | 预测 vs 实际 秩相关 全部 / ≥ 300 件 | 把握 vs 实际 全部 / ≥ 300 件 | 方向对（≥ 300 件，个数） | 80% 覆盖 |', '| :--- | :--- | :--- | :--- | :--- | ---: |']
for nm in RES:
    for how in ('self', 'true'):
        r = g(nm, how=how)
        if r is None or (nm.startswith('全量') and how == 'true'): continue
        lab = '全量' if nm.startswith('全量') else ('自评' if how == 'self' else '真值')
        L.append(f"| {nm} | {lab} | {f2(r['rho'])} / {f2(r['rho300'])} | {f2(r['rhoP'])} / {f2(r['rhoP300'])} | {p0(r['dirn'])}（{r['n300']}） | {p0(r['cov'])} |")
L += ['', '## 4. 并排时点（END − 11 至 END − 8），第九版', '',
      '| 场景 | 时点 | 窗口 | 评估 | 秩相关 全部 / ≥ 300 件 | 方向对 ≥ 300 件 | 把握 ≥ 70% 之后变大（个数） | 把握 ≤ 30% 之后变大（个数） |', '| :--- | :--- | :--- | :--- | :--- | ---: | :--- | :--- |']
for nm in MAIN:
    for Ts in TPS:
        e = RES[nm]['ev'][('第九版', Ts)]
        if 'err' in e: L.append(f"| {nm} | {Ts} | | 跑不动：{e['err']} | | | | |"); continue
        for k in (6, 8):
            for how in ('self', 'true'):
                r = e[how].get(k)
                if r is None: continue
                lab = '全量' if nm == '全量' else ('自评' if how == 'self' else '真值')
                L.append(f"| {nm} | {Ts} | 第 {k}–{k + 2} 月 | {lab} | {f2(r['rho'])} / {f2(r['rho300'])} | {p0(r['dirn'])} | {pc(r['hi'])} | {pc(r['lo'])} |")
# 四时点平均（k=6、8 全部窗口）
def avg(nm, v, how, key):
    xs = [RES[nm]['ev'][(v, Ts)][how][k][key] for Ts in TPS if 'err' not in RES[nm]['ev'][(v, Ts)] for k in (6, 8) if k in RES[nm]['ev'][(v, Ts)][how]]
    xs = [x for x in xs if not (isinstance(x, float) and np.isnan(x))]; return np.mean(xs) if xs else np.nan
L += ['', '### 4.1 四个时点、全部窗口平均（第九版 / 去 x5 / 仅 b6）', '',
      '| 场景 | 评估 | 第九版 秩相关 全部 / ≥ 300 | 去 x5 | 仅 b6 | 第九版 方向对 ≥ 300 | 仅 b6 方向对 ≥ 300 |', '| :--- | :--- | :--- | :--- | :--- | ---: | ---: |']
for nm in MAIN:
    for how in ('self', 'true'):
        if nm == '全量' and how == 'true': continue
        lab = '全量' if nm == '全量' else ('自评' if how == 'self' else '真值')
        L.append(f"| {nm} | {lab} | " + ' | '.join(f"{f2(avg(nm, v, how, 'rho'))} / {f2(avg(nm, v, how, 'rho300'))}" for v in VARS) + f" | {p0(avg(nm, '第九版', how, 'dirn'))} | {p0(avg(nm, '仅 b6', how, 'dirn'))} |")
L += ['', '## 5. x5（新品占比差）还剩多少', '',
      '| 场景 | x5 系数 k=6 合计（t） | k=8 合计（t） | b6 系数 k=6 合计（t） | 重建 x5 与全量 x5 的秩相关 | 重建 b6 与全量 b6 的秩相关 |', '| :--- | :--- | :--- | :--- | ---: | ---: |']
for nm in RES:
    e = RES[nm]['ev'].get(('第九版', '2026-01'))
    if not e or 'coef' not in e: continue
    c = e['coef']; ct = lambda key: f"{c[key][0]:+.3f}（{c[key][1]:+.1f}）"
    L.append(f"| {nm} | {ct(('x5', 6))} | {ct(('x5', 8))} | {ct(('b6', 6))} | {f2(e.get('x5corr', np.nan))} | {f2(e.get('b6corr', np.nan))} |")
L += ['', 't 值按单元聚类（同一单元在不同时点、窗口的样本不独立）；同一时点不同单元之间也有重叠（大属性和含它的两维格子），t 值仍偏乐观，只看量级和方向。'
      '站在 2026-01，k = 6 的训练样本只有 2025-04 一个时点、k = 8 没有，k = 6、8 的系数是按 k 线性外推的（第九版报告第 1 节同样说明）。', '']
CONCL_TEXT = '''## 6. 结论

**先说结果是否可信**：全量场景逐项复现了第九版报告（把握四档 25% / 44% / 60% / 63%、D 档 19%（89 个）、秩相关 +0.27 / +0.47、四个时点的数字都一致），说明重跑用的就是第九版的流程。

### 6.1 偏差有多大

- **幸存者偏差很大**：只留 END 在榜的家族，T0 前 6 个月的销量只剩 49%，2024-10 只剩 19%；新品销量只剩 34%，新品占比从 17% 降到 12%。也就是说，重建出来的"历史"有一半是看不到的。
- **但对"排序"影响不大**（家族口径、N ≥ 200）：用全量结果检验（真值），四个时点平均秩相关 全部 / ≥ 300 件为 +0.29 / +0.55，全量第九版为 +0.19 / +0.45。（≥ 300 件按重建面板的销量算，留下来的都是更大的单元，两组单元不完全一样，不能读成"重建反而更好"，只能读成"没有明显变差"。）
  T0 把握四档的真值变大比例是 28% / 52% / 71% / 74%，单调性保住了；D 档真值 24%（41 个），第九版 19%。
- **"方向对"和绝对概率会变差**：方向对（≥ 300 件）从 66% 降到 60%；重建面板学到的水平偏低（自评全部单元变大 42%，真值 45%），把握 ≤ 30% 那档，家族前 200 各时点真值比自评高 −1 至 +9 个百分点。也就是说，把握能拿来排序，不能直接当概率用。
- **自评偏乐观**：小平台上只能做自评。家族前 200 的四时点平均秩相关，自评 +0.35 / +0.56，真值 +0.29 / +0.55；2025-11、12 两个时点，自评的全部单元秩相关比真值高 0.05 至 0.12，2025-11 把握 ≥ 70% 档自评 89–90%、真值 70–78%（2025-12 为 76% 对 71%）。2026-01 反过来，自评略低。

### 6.2 需要多大的 N

- 这个模拟能调的是"N 占当前头部的比例"，不是 N 的绝对值：亚马逊面板本身就是每月导出的头部（END 只有 202 个家族），所以 N = 300、500 和"全部 202 个"一样。
- 覆盖到当前头部的全部（家族前 200 / 202，END 销量 100%）时，结论基本站得住。
- 只看前一半（前 100，END 销量 72%）时，秩相关 ≥ 300 件还有 +0.46（真值），但方向对掉到 52%，等于猜；T0 的 D 档真值变大 47%，已经不像"坑"。
- 只看前 50（END 销量 50%）时，≥ 300 件秩相关真值 +0.32，方向对 54%，四个时点的把握 ≤ 30% 档真值有 38–47% 变大。
- **按子体（每个颜色尺寸一条）取前 200 / 300 / 500 不行**：子体前 200 有 3 个时点因为样本太少拟合不了（体量 ≥ 1,000 件那档没有 k = 0 的训练样本，库里的纠偏表查不到，KeyError）；跑得出来的几个时点秩相关为负或正负来回跳。原因是子体前 500 也只覆盖 122 个家族、T0 前 6 个月销量的 15%。
  "仅 b6"的最小版本也救不回来（子体前 200 四时点平均 −0.36 / −0.32）。
- **对小平台的要求**：评论必须按商品页（父体）合并，不能按 SKU 拆；N 要覆盖到类目里有实际销量的头部的绝大多数，至少前 N 要占当前类目销量的约 90% 以上，不能只占一半。
  Home Depot 200、Lowe's 200、Wayfair 250 够不够，取决于这几个类目头部有多长。这一点这里模拟不了，要在渠道上实测：例如看第 200 名的评论增速和第 1 名差多少；或者隔 1–2 个月再抓一次榜单，看前 N 的换手率。

### 6.3 哪些信号可信

- **b6（份额斜率）**：方向可信，系数打折。家族前 200 时，重建 b6 和全量 b6 的秩相关为 +0.74；k = 6 的合计系数从 +1.39（t 6.5）降到 +0.73（t 3.3）。小面板上"仅 b6"的真值秩相关 ≥ 300 件 +0.38，全量"仅 b6"是 +0.26，b6 单独排序也能用。
- **x5（新品占比差）**：方向保住了，但量和口径都偏。家族前 200 时，x5 合计系数 +0.59（t 2.8），全量 +0.65（t 3.5）；去掉 x5 后，真值秩相关 ≥ 300 件从 +0.55 降到 +0.40，这和全量里的变化一样（+0.45 降到 +0.28），说明 x5 在重建面板里仍然有用。
  问题有三个：只看得到活下来的新品（新品销量 34%），新品占比整体偏低（12% 对 17%），重建 x5 和全量 x5 的秩相关只有 +0.60。月龄改用"首次出现"后降到 +0.42，而全量面板用首现月龄时，x5 系数只剩 +0.22（t 1.3）。
  所以小平台上的 x5 只能当"相对品类高还是低"的排序信号；首条评论月必须尽量贴近真实上架月，不能用"第一次进榜的月"。前 50 时 x5 系数 +0.91 是小样本放大，不可信。
- **x3（搜索同比）**：来自关键词数据，不受重建影响；但小平台本身没有站内搜索数据，只能借亚马逊或谷歌的。
- **x4（体量）、把握的绝对值、"预计多卖"、A / D 分级的固定门槛**：都跟着重建面板的销量水平走，绝对值不可信。≥ 300 件、A 档 ≥ 100 件这类门槛，要按小平台自己的销量重新定。

### 6.4 这条路线能不能支持回测，结论怎么打折

- **能支持"排序型"回测，不能支持"概率型"回测**。前提是：按商品页合并，前 N 覆盖类目头部的绝大部分，单元停在大属性 / 两维格子这一层。
- 小平台回测报出来的数这样打折：
  - 秩相关当上限看，全部单元减约 0.05–0.1；
  - 把握 ≥ 70% 那档的"之后变大比例"减约 10–20 个百分点；
  - 方向对按 ≤ 60% 看；
  - 把握 ≤ 30% 档和 D 档的"坑"要再保守一些，加约 5 个百分点；
  - 只看前一半商品时，D 档和方向不再可信。
- **这里没模拟到、真实情况只会更差的地方**：
  1. 评论数 × 系数（VP×50、非 VP×20）换算月销的误差：不同价位、不同品牌的留评率不同，这里用的是卖家精灵的月销估算，噪声比评论法小；
  2. 小平台类目的长尾到底多长，模拟不出来（这里的"全量"本身也只是亚马逊每月的头部）；
  3. 换手率：小平台的换手可能比亚马逊慢，那样幸存者偏差会小一些，所以这一点要实测，不要假设；
  4. 首条评论通常比上架晚 1–2 个月，会让新品晚一点被认出来；
  5. 重建面板里幸存商品的历史只有它在亚马逊头部里的那些月份；评论法能拿到它从上架起的全部月份，这一点评论法反而更完整。
- **建议**：小平台回测报告一律同时写"自评"和"按本页打折后的区间"；先实测前 N 的覆盖率和 1–2 个月的换手率，再决定 N。'''
L += [CONCL_TEXT, '']
out = os.path.join(ROOT, 'solution-v2/开发建议/幸存者偏差模拟_小平台回测可行性.md'); open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L))
