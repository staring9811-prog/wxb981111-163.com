"""跨渠道供给丰富度差距（Amazon 多、Home Depot 少）作为候选信号，在 HD 重建面板上检验它对 HD 之后份额变化的作用。
用法：python3 跨渠道供给差_HD检验.py → solution-v2/开发建议/跨渠道供给差_HD检验.md（数字全部来自本次运行）。
- HD 面板：照搬 小平台_HD回测小试.py 的重建（评论 × 系数、v12.2 打标、框 = 尺寸段 × 装 × 形态、单元 = 框 × 属性取值、b6 / x5 / x2 / x4、目标 y6）。
- Amazon 面板：input/data_v2/统一打标/统一打标_分析用.pkl（与第九版同一张表，2024-10 至 2026-09），同一套 v12.2 标签口径归类。
- 对齐：严格（尺寸段 × 装 × 形态 × 属性取值）和忽略装（尺寸段 × 形态 × 属性取值，两侧都把整装、拆装合并）两种。
- 检验：y6 对 基础信号 + 差距信号 的 OLS，T0 × 属性类型固定效应，按单元聚类标准误；按单元分组 5 折交叉验证比较加入前后的秩相关与分档单调性。
不改 tools/ 与 app/，只 import。"""
import os, sys, html, collections, numpy as np, pandas as pd, warnings
from scipy.stats import spearmanr
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
import 小平台_HD回测小试 as HD   # noqa: E402
sys.path.insert(0, os.path.join(ROOT, 'app', 'pdt', 'core'))
import tagging_rules as TR   # noqa: E402
from families import band, cab, color, mi, ms   # noqa: E402
import statsmodels.api as sm   # noqa: E402
from sklearn.model_selection import GroupKFold   # noqa: E402

UNKS = HD.UNKS
EPS = 0.001
ATTRS = ('台面材质', '元素', '主色', '柜体材质')
PRICE_ABS = [0, 200, 300, 450, 650, 900, 1300, np.inf]          # 绝对价位段（美元），两个渠道共用
PRICE_REL = [0, 0.7, 0.85, 1.15, 1.5, np.inf]                   # 同渠道同尺寸段 × 装 中位价的比
OUT = os.path.join(ROOT, 'solution-v2', '开发建议', '跨渠道供给差_HD检验.md')
L = []; P = lambda *a: L.extend(a)
f2 = lambda x: '—' if x is None or (isinstance(x, float) and np.isnan(x)) else f'{x:+.2f}'
f3 = lambda x: '—' if x is None or (isinstance(x, float) and np.isnan(x)) else f'{x:+.3f}'
pc = lambda x: '—' if x is None or (isinstance(x, float) and np.isnan(x)) else f'{x:.0%}'


# ====================================================================== 1. HD 行级表（照搬小试的重建与打标）
def hd_rows():
    M0, END = mi('2024-01'), mi('2026-10')
    lists, fams, pages, revs = HD.load_all()
    listed = {}
    for n, (rows, _) in lists.items():
        for r in rows: listed.setdefault(r['id'], r)
    pid2fam = {p: fk for fk, ps in fams.items() for p in ps}
    rv = []
    for fk, g in revs.items():
        if not g or g.get('状态') not in ('完整', '截断'): continue
        for rid, x in g['reviews'].items():
            rv.append((fk, rid, x['d'], x['r'], x['vp'], x['syn'], x['pid'], x['name']))
    R = pd.DataFrame(rv, columns=['fam', 'rid', 'd', 'r', 'vp', 'syn', 'pid', 'name']).drop_duplicates('rid')
    R['m'] = R['d'].map(lambda d: mi(d) if d and d[:4].isdigit() else -1)
    trunc = {fk: g['完整到'] for fk, g in revs.items() if g and g.get('状态') == '截断'}
    W = R[(R['m'] >= M0) & (R['m'] <= END)].copy(); W['c'] = np.where(W['vp'], 50, 20)
    names = R.sort_values('d').groupby('pid')['name'].agg(lambda s: next((x for x in reversed(list(s)) if x), ''))
    rowsV = []
    for p in sorted(set(W['pid']) | set(listed)):
        if p not in pages: pages[p] = HD.load_json(os.path.join(HD.CACHE, 'pages', f'{p}.json')) or {}
        pg = pages.get(p) or {}; lr = listed.get(p)
        title = (lr or {}).get('title') or pg.get('title') or names.get(p, '')
        t = HD.tag_variant(TR, title, pg.get('specs'), pg.get('highlights'))
        fam = pid2fam.get(p) or (W.loc[W['pid'] == p, 'fam'].iloc[0] if (W['pid'] == p).any() else None)
        rowsV.append(dict(pid=p, fam=fam, title=title, 价格=(lr or {}).get('price') or pg.get('price'), 品牌=(lr or {}).get('brand') or pg.get('brand'), **t))
    V = pd.DataFrame(rowsV).set_index('pid')
    fb = V.dropna(subset=['品牌']).groupby('fam')['品牌'].agg(lambda s: s.mode().iloc[0]); V['品牌'] = V['品牌'].fillna(V['fam'].map(fb))
    for col in ('装', '形态'):
        mode = V[V[col] != '未知'].groupby('fam')[col].agg(lambda s: s.mode().iloc[0])
        k = (V[col] == '未知') & V['fam'].isin(mode.index); V.loc[k, col] = V.loc[k, 'fam'].map(mode)
    for col in ('D7', 'D8'):
        mode = V[~V[col].isin(UNKS)].groupby('fam')[col].agg(lambda s: s.mode().iloc[0])
        k = V[col].isin(UNKS) & V['fam'].isin(mode.index); V.loc[k, col] = V.loc[k, 'fam'].map(mode)
    V['形态'] = V['形态'].replace({'两用': '落地式'}); V.loc[V['形态'] == '未知', '形态'] = '落地式'
    V['尺寸段'] = V['宽'].map(band); V['柜体材质'] = V['D7'].map(cab)
    V['台面材质'] = V['D8'].map(lambda v: '未知' if v in UNKS else v); V['主色'] = V['D6'].map(color)
    V['元素'] = V['D5'].map(lambda v: sorted({HD.ELEM_MAP[x] for x in str(v).split('；') if x in HD.ELEM_MAP}) or ['未知'])
    V['PB'] = V['品牌'].isin(['Glacier Bay', 'Home Decorators Collection'])
    vfirst = R.groupby('pid')['d'].min()
    def reliable_first(p):
        d = vfirst.get(p); fk = V.at[p, 'fam'] if p in V.index else None
        if d is None: return None
        if fk in trunc and d < trunc[fk]: return None
        return d
    V['首评'] = [reliable_first(p) for p in V.index]
    V['L'] = V['首评'].map(lambda d: mi(d) if isinstance(d, str) and d >= HD.CUTOFF else -10 ** 6)
    W = W.join(V[['L']], on='pid'); W['新'] = (W['m'] - W['L']) <= 6
    A = W.groupby(['fam', 'pid', 'm']).agg(c=('c', 'sum'), 新=('新', 'first')).reset_index().join(
        V[['尺寸段', '装', '形态', '台面材质', '主色', '柜体材质', '元素', '价格', '品牌', 'PB', 'title']], on='pid')
    A['价格'] = pd.to_numeric(A['价格'], errors='coerce')
    return A, V, M0, END


# ====================================================================== 2. Amazon 行级表（第九版同一张表，同一套标签归类）
def az_elem(e):
    if not (isinstance(e, str) and e): return ['未知']
    out = set()
    for part in e.split('+'):
        if part.startswith('夏克式'): out.add('夏克式')
        elif part in ('竖棱', 'fluted', 'reeded'): out.add('竖棱')
        elif part == '农场风装饰饰条': out.add('农场风装饰饰条')
        elif part == '玻璃门': out.add('玻璃门')
        elif part == '木条格栅': out.add('木条格栅')
        elif part == 'rattan': out.add('rattan')
        else: out.add('其他（' + part + '）')
    return sorted(out)


def az_rows():
    A = pd.read_pickle(os.path.join(ROOT, 'input/data_v2/统一打标/统一打标_分析用.pkl')); A = A[A['纳入浴室柜分析']].copy()
    B = pd.DataFrame({'m': A['月份'].map(mi).values, 'fam': A['家族键'].values, 'pid': A['子ASIN'].values,
                      'c': pd.to_numeric(A['子体月销（家族均分）'], errors='coerce').fillna(0).clip(lower=0).values,
                      '价格': pd.to_numeric(A['价格'], errors='coerce').values, '品牌': A['品牌'].values, 'title': A['标题'].values})
    B['尺寸段'] = A['D9宽(in)'].map(band).values
    B['装'] = np.where(A['D2安装方式'].eq('整装').values, '整装', '拆装')   # 与第九版同：部分预装 / 未写 按拆装
    B['形态'] = A['形态（怎么装）'].fillna('落地式').astype(str).replace({'两用': '落地式'}).values
    B['台面材质'] = A['D8台面材质'].map(lambda v: '未知' if (pd.isna(v) or v in UNKS) else v).values
    B['主色'] = A['D6柜体颜色'].map(color).values
    B['柜体材质'] = A.get('D7柜体材质（价格复核前）', A['D7柜体材质']).map(cab).values
    B['元素'] = A['元素（看图）'].map(az_elem).values
    B['元素看图'] = A['元素（看图）'].fillna('未知').astype(str).values
    return B


# ====================================================================== 3. 单元键、HD 特征与目标
def frame_key(d, align):
    s = d['尺寸段'].astype(object)
    ok = s.notna() & (d['装'] != '未知') if align == '严格' else s.notna()
    k = s.fillna('') + ' · ' + d['装'] + ' · ' + d['形态'] if align == '严格' else s.fillna('') + ' · ' + d['形态']
    return k.where(ok)


def unit_rows(d, att, align):
    """行 → (框, 属性, 取值) 级别的行；元素展开。"""
    x = d.explode('元素') if att == '元素' else d
    x = x.assign(框=frame_key(x, align), 取值=x[att].astype(str))
    x = x[x['框'].notna() & ~x['取值'].isin(list(UNKS) + ['未知']) & ~x['取值'].str.startswith('其他（')]
    return x.assign(属性=att)


def hd_panel(A, M0, END):
    """HD 小试同口径：主粒度 框（严格）× 属性；返回每个 T 的特征表 与 目标函数。"""
    MONTHS = list(range(M0, END + 1))
    CAT = A.groupby('m')['c'].sum().reindex(MONTHS, fill_value=0)
    CATN = A[A['新']].groupby('m')['c'].sum().reindex(MONTHS, fill_value=0)
    pans = []; XR = []
    for att in ATTRS:
        x = unit_rows(A.reset_index(drop=True), att, '严格'); x['_k'] = x['框'] + ' ｜ ' + att + '：' + x['取值']
        C = x.groupby(['_k', 'm'])['c'].sum().unstack(fill_value=0).reindex(columns=MONTHS, fill_value=0)
        N = x[x['新']].groupby(['_k', 'm'])['c'].sum().unstack(fill_value=0).reindex(index=C.index, columns=MONTHS, fill_value=0)
        F = x.groupby(['_k', 'm'])['fam'].nunique().unstack(fill_value=0).reindex(columns=MONTHS, fill_value=0)
        den = x.drop_duplicates(['fam', 'pid', 'm']).groupby('m')['c'].sum().reindex(MONTHS, fill_value=0)
        meta = x.drop_duplicates('_k').set_index('_k')[['框', '取值', '尺寸段', '装', '形态']]
        pans.append((att, C, N, F, den, meta)); XR.append(x[['_k', 'fam', 'm', 'c']])
    mean3 = lambda X, a: X.loc[:, [m for m in range(a, a + 3) if m in X.columns]].mean(axis=1)

    def feats(T):
        out = []
        for att, C, N, F, den, meta in pans:
            cols6 = list(range(T - 6, T)); xc = np.arange(6) - 2.5
            D = pd.DataFrame({'属性': att, '单元': C.index, '近3月': mean3(C, T - 3).values})
            D['份额6'] = (C[cols6].sum(axis=1) / max(den.loc[T - 6:T - 1].sum(), 1)).values
            D['b6'] = ((np.log(C[cols6].div(den.loc[T - 6:T - 1].replace(0, np.nan), axis=1).fillna(0) + EPS) * xc).sum(axis=1) / (xc ** 2).sum()).values
            D['x5'] = (N[cols6].sum(axis=1) / C[cols6].sum(axis=1).replace(0, np.nan)).fillna(0).values - CATN.loc[T - 6:T - 1].sum() / max(CAT.loc[T - 6:T - 1].sum(), 1)
            f1, f0 = mean3(F, T - 3), mean3(F, T - 6); D['x2'] = ((f1 - f0) / (f0 + 1)).values
            D = D.join(meta, on='单元'); out.append(D)
        D = pd.concat(out, ignore_index=True); D = D[D['近3月'] > 0].copy(); D['x4'] = np.log(D['近3月'] + 5) - 5.0; D['T'] = T
        return D

    def y6(D, T):
        a = T + 6
        if a + 2 > END: return pd.Series(np.nan, index=D.index)
        res = {}
        for att, C, N, F, den, meta in pans:
            s = mean3(C, a) / max(den.loc[a:a + 2].mean(), 1)
            for v, x in s.items(): res[v] = x
        s = pd.Series([res.get(u, 0.0) for u in D['单元']], index=D.index)
        return np.log((s + EPS) / (D['份额6'] + EPS))

    def y6_old(D, T):
        """只算 T 前 6 个月就在这个单元有销量的家族（老家族）在第 6–8 个月的份额，对近 6 个月份额的对数变化；另给第 6–8 个月销量里新家族的占比。"""
        a = T + 6
        if a + 2 > END: return pd.Series(np.nan, index=D.index), pd.Series(np.nan, index=D.index)
        old, newfrac = {}, {}
        for (att, C, N, F, den, meta), x in zip(pans, XR):
            pre = set(map(tuple, x[x['m'].between(T - 6, T - 1) & (x['c'] > 0)][['_k', 'fam']].values))
            post = x[x['m'].between(a, a + 2)]
            isold = np.array([(k, f) in pre for k, f in zip(post['_k'], post['fam'])], dtype=bool)
            so = post[isold].groupby('_k')['c'].sum() / 3; sa = post.groupby('_k')['c'].sum() / 3; dd = max(den.loc[a:a + 2].mean(), 1)
            for k, v in so.items(): old[k] = v / dd
            for k, v in sa.items(): newfrac[k] = 1 - so.get(k, 0.0) / v if v > 0 else np.nan
        so = pd.Series([old.get(u, 0.0) for u in D['单元']], index=D.index)
        return np.log((so + EPS) / (D['份额6'] + EPS)), pd.Series([newfrac.get(u, np.nan) for u in D['单元']], index=D.index)
    return feats, y6, CAT, y6_old


# ====================================================================== 4. 两侧丰富度（同口径）
def richness(d, T, align, rel_den):
    """窗口 T−6..T−1，按 (框, 属性, 取值) 算：在售家族数、有效家族数、子体数、绝对 / 相对价位段数、主色数、单元销量；以及框内份额与份额斜率。"""
    w = d[d['m'].between(T - 6, T - 1) & (d['c'] > 0)].copy()
    if w.empty: return pd.DataFrame()
    w['pabs'] = pd.cut(w['价格'], PRICE_ABS, labels=False, right=False)
    med = w.drop_duplicates(['pid']).groupby(rel_den)['价格'].median()
    w = w.join(med.rename('中位'), on=rel_den); w['prel'] = pd.cut(w['价格'] / w['中位'], PRICE_REL, labels=False, right=False)
    out = []
    for att in ATTRS:
        x = unit_rows(w, att, align)
        if x.empty: continue
        g = x.groupby(['框', '取值'])
        fs = x.groupby(['框', '取值', 'fam'])['c'].sum(); fsh = fs / fs.groupby(level=[0, 1]).transform('sum')
        D = pd.DataFrame({'家族': g['fam'].nunique(), '有效家族': 1 / (fsh ** 2).groupby(level=[0, 1]).sum(), '子体': g['pid'].nunique(),
                          '价位段': g['pabs'].nunique(), '相对价位段': g['prel'].nunique(),
                          '主色数': x[~x['主色'].isin(['未知'])].groupby(['框', '取值'])['主色'].nunique(), '销量': g['c'].sum() / 6,
                          '价格中位': g['价格'].median(), '价格低': g['价格'].quantile(0.1), '价格高': g['价格'].quantile(0.9)})
        D['主色数'] = D['主色数'].fillna(0)
        # 框内份额（分母 = 框内该属性已知的销量）与份额斜率
        M = x.groupby(['框', '取值', 'm'])['c'].sum().unstack(fill_value=0).reindex(columns=range(T - 6, T), fill_value=0)
        den = M.groupby(level=0).transform('sum')
        D['框内份额'] = (M.sum(axis=1) / den.sum(axis=1).replace(0, np.nan))
        xc = np.arange(6) - 2.5
        D['框内斜率'] = (np.log(M.div(den.replace(0, np.nan)).fillna(0) + 0.01) * xc).sum(axis=1) / (xc ** 2).sum()
        D['框销量'] = den.sum(axis=1) / 6
        D['属性'] = att; out.append(D.reset_index())
    return pd.concat(out, ignore_index=True)


def az_looks(d, T, align):
    """Amazon 侧：单元内 看图元素 × 主色 组合数（HD 侧元素靠文字只认出约 6% 销量，量不出，所以只作 Amazon 单侧变量）。"""
    w = d[d['m'].between(T - 6, T - 1) & (d['c'] > 0)]
    out = []
    for att in ATTRS:
        x = unit_rows(w, att, align)
        out.append(x.groupby(['框', '取值']).apply(lambda g: g[['元素看图', '主色']].drop_duplicates().shape[0]).rename('外观组合').reset_index().assign(属性=att))
    return pd.concat(out, ignore_index=True)


def signals(DH, hdA, azA, T, align):
    """DH：HD 单元特征（严格框）；按对齐口径接上两侧丰富度并算差距。"""
    H = richness(hdA, T, align, ['尺寸段', '装']).set_index(['属性', '框', '取值'])
    Z = richness(azA, T, align, ['尺寸段', '装']).set_index(['属性', '框', '取值'])
    Zl = az_looks(azA, T, align).set_index(['属性', '框', '取值'])['外观组合']
    azframe = Z.groupby(level=1)['框销量'].first() if len(Z) else pd.Series(dtype=float)
    fk = DH['框'] if align == '严格' else (DH['尺寸段'] + ' · ' + DH['形态'])
    idx = list(zip(DH['属性'], fk, DH['取值']))
    h = H.reindex(idx); z = Z.reindex(idx); zl = Zl.reindex(idx)
    S = pd.DataFrame(index=DH.index)
    S['az框销量'] = fk.map(azframe).fillna(0).values
    for c in ('家族', '有效家族', '子体', '价位段', '相对价位段', '主色数', '销量'):
        S['hd_' + c] = h[c].fillna(0).values; S['az_' + c] = z[c].fillna(0).values
    S['az_外观组合'] = zl.fillna(0).values
    S['az_框内份额'] = z['框内份额'].fillna(0).values; S['az_框内斜率'] = z['框内斜率'].values
    S['hd_框内份额'] = h['框内份额'].fillna(0).values
    S['az_价格中位'] = z['价格中位'].values; S['hd_价格中位'] = h['价格中位'].values
    S['G家族'] = np.log((S['az_家族'] + 1) / (S['hd_家族'] + 1))
    S['G有效家族'] = np.log((S['az_有效家族'] + 1) / (S['hd_有效家族'] + 1))
    S['G子体'] = np.log((S['az_子体'] + 1) / (S['hd_子体'] + 1))
    S['G价位段'] = S['az_价位段'] - S['hd_价位段']
    S['G相对价位段'] = S['az_相对价位段'] - S['hd_相对价位段']
    S['G主色数'] = np.where(DH['属性'].values == '主色', 0.0, S['az_主色数'] - S['hd_主色数'])
    S['D份额'] = np.log(S['az_框内份额'] + 0.01)
    S['D斜率'] = S['az_框内斜率'].fillna(0)
    S['D份额差'] = np.log((S['az_框内份额'] + 0.01) / (S['hd_框内份额'] + 0.01))
    S['az_外观'] = np.log(S['az_外观组合'] + 1)
    S['lnAZ家族'] = np.log(S['az_家族'] + 1); S['lnHD家族'] = np.log(S['hd_家族'] + 1); S['lnHD框内份额'] = np.log(S['hd_框内份额'] + 0.01)
    return S


# ====================================================================== 5. 回归与交叉验证
BASE = ['b6', 'x5', 'x2', 'x4']


def zs(s): return (s - s.mean()) / s.std() if s.std() > 0 else s * 0


def ols(df, xs, cluster='单元', y='y6'):
    fe = pd.get_dummies(df['T'].astype(str) + '|' + df['属性'], drop_first=True, dtype=float)
    X = pd.concat([df[xs].astype(float), fe], axis=1); X = sm.add_constant(X)
    g = pd.factorize(df[cluster])[0]
    m = sm.OLS(df[y].astype(float), X).fit(cov_type='cluster', cov_kwds={'groups': g})
    return m


def cv_pred(df, xs, seed_groups='单元'):
    """按单元分组 5 折：留出的单元在所有 T0 都不进训练；固定效应（T0 × 属性类型）在训练里估。"""
    fe = pd.get_dummies(df['T'].astype(str) + '|' + df['属性'], dtype=float)
    X = pd.concat([df[xs].astype(float), fe], axis=1).values; y = df['y6'].values
    pred = np.full(len(df), np.nan)
    for tr, te in GroupKFold(5).split(X, y, pd.factorize(df[seed_groups])[0]):
        b, *_ = np.linalg.lstsq(X[tr], y[tr], rcond=None); pred[te] = X[te] @ b
    return pred


def per_t_rho(df, col, big):
    r = []
    for T, d in df.groupby('T'):
        d = d[d['近3月'] >= big] if big else d
        if len(d) > 4: r.append(spearmanr(d[col], d['y6'])[0])
    return np.nanmean(r), r


def bins_table(df, col, q=5):
    d = df.copy(); d['档'] = d.groupby('T')[col].transform(lambda s: pd.qcut(s.rank(method='first'), q, labels=False))
    return d.groupby('档').agg(n=('y6', 'size'), up=('y6', lambda s: (s > 0).mean()), my=('y6', 'mean'))


def main():
    hdA, V, M0, END = hd_rows(); azA = az_rows()
    feats, y6, CAT, y6_old = hd_panel(hdA, M0, END)
    BIG = round(float(CAT.loc[mi('2025-01'):END].mean()) * 0.01, -1)
    T0s = [mi(t) for t in ('2025-04', '2025-05', '2025-06', '2025-07', '2025-08', '2025-09', '2025-10', '2025-11', '2025-12', '2026-01', '2026-02')]
    PAN = {}
    for align in ('忽略装', '严格'):
        parts = []
        for T in T0s:
            D = feats(T); D['y6'] = y6(D, T); D['y6老'], D['新家族占比'] = y6_old(D, T); D = D.dropna(subset=['y6'])
            S = signals(D, hdA, azA, T, align); parts.append(pd.concat([D, S], axis=1))
        PAN[align] = pd.concat(parts, ignore_index=True)
    # 核对：仅 b6 / 仅 x5 的秩相关应与小试报告（框 × 属性 +0.10 / +0.16；+0.14 / +0.28）一致
    D0 = PAN['严格']
    chk = {c: (per_t_rho(D0, c, 0)[0], per_t_rho(D0, c, BIG)[0]) for c in ('b6', 'x5')}

    # ---------------- 报告头 ----------------
    P('# 跨渠道供给丰富度差距：在 Home Depot 重建面板上的检验', '',
      '> 由 `trial/跨渠道供给差_HD检验.py` 生成，数字都是脚本实际输出。HD 面板与 `小平台_HD回测小试.md` 同口径（评论重建 2024-01 至 2026-10，框 × 属性，T0 = 2025-04 至 2026-02，'
      '目标 = 立项后第 6–8 个月份额相对近 6 个月的对数变化 y6）；Amazon 用第九版同一张统一打标表（2024-10 至 2026-09）。', '',
      f'> 面板核对：重建后仅 b6 秩相关 全部 / 大 {f2(chk["b6"][0])} / {f2(chk["b6"][1])}，仅 x5 {f2(chk["x5"][0])} / {f2(chk["x5"][1])}'
      '（小试报告 §5.1：+0.10 / +0.16，+0.14 / +0.28）' + ('，与小试一致。' if max(abs(chk['b6'][0] - 0.10), abs(chk['b6'][1] - 0.16), abs(chk['x5'][0] - 0.14), abs(chk['x5'][1] - 0.28)) < 0.006 else '，与小试有出入，见脚本。'), '')
    HEAD_END = len(L)
    w26 = hdA[hdA['m'] >= mi('2026-01')]; a26 = azA[azA['m'] >= mi('2026-01')]
    hd_zz = w26.loc[w26['装'] == '整装', 'c'].sum() / max(w26.loc[w26['装'] != '未知', 'c'].sum(), 1); az_cz = a26.loc[a26['装'] == '拆装', 'c'].sum() / a26['c'].sum()

    # ---------------- 1. 定义 ----------------
    P('## 1. 信号定义', '',
      '单元 u = 框 × 属性取值（属性：台面材质 / 元素 / 主色 / 柜体材质）；时点 T 只用 T−6 至 T−1 这 6 个月。两侧丰富度都只数窗口内**有销量**的家族 / 子体（HD：有评论 → 重建销量 > 0；Amazon：导出里月销 > 0）。', '',
      '| 量 | 公式（两侧同口径） |', '| :--- | :--- |',
      '| 家族数 N_fam | 窗口内单元里有销量的不同家族（HD 评论家族 / Amazon 家族键 ≈ 父体） |',
      '| 有效家族数 N_eff | 1 / Σ_f s_f²，s_f = 家族在单元窗口销量里的占比（小家族几乎不计，抗"导出深浅、评论门槛不同"） |',
      '| 子体数 N_var | 有销量的不同子体（HD 商品页 / Amazon 子 ASIN）= 颜色、尺寸等变体 |',
      '| 价位段数 N_pb | 子体价格落在几个绝对价位段：$0–200 / 200–300 / 300–450 / 450–650 / 650–900 / 900–1,300 / 1,300+（7 段，两渠道共用） |',
      '| 相对价位段数 N_pr | 价格 ÷ 同渠道同尺寸段 × 装 中位价，按 <0.7 / 0.7–0.85 / 0.85–1.15 / 1.15–1.5 / >1.5 分 5 档，覆盖几档 |',
      '| 主色数 N_col | 有销量子体的已知主色种类（属性 = 主色的单元记 0 差距） |',
      '| Amazon 外观组合 | Amazon 单元内 看图元素 × 主色 的组合数（只 Amazon 单侧：HD 元素靠文字只认出约 6% 销量，量不出，不做差） |',
      '| Amazon 需求 | 框内份额 s_AZ = 单元销量 ÷ Amazon 同框该属性已知销量；框内斜率 = 近 6 个月 ln(框内份额 + 0.01) 的线性斜率 |',
      '', '差距信号（越大 = Amazon 越丰富、HD 越少）：', '',
      '- **G家族** = ln((N_fam^AZ + 1) / (N_fam^HD + 1))（主定义）；G有效家族、G子体 同式；',
      '- **G价位段** = N_pb^AZ − N_pb^HD；G相对价位段 = N_pr^AZ − N_pr^HD；G主色数 = N_col^AZ − N_col^HD；',
      '- **D份额** = ln(s_AZ + 0.01)（Amazon 需求已证明的程度）；**D斜率** = Amazon 框内斜率（需求在涨）；**D份额差** = ln((s_AZ + 0.01) / (s_HD + 0.01))，s_HD = HD 同框内份额（需求结构差）；',
      '- **交互**：z(D份额) × z(G家族)（需求已证明 × 供给稀缺）；另一版用 1[s_AZ 在样本上半 且 D斜率 > 0] × G家族。', '',
      f'**框的对齐**。2026 年 HD 重建销量 {hd_zz:.0%} 是整装、Amazon {az_cz:.0%} 是拆装，按"尺寸段 × 装 × 形态"严格对齐时，HD 的大框（30″ / 24″ / 36″ 整装）在 Amazon 只对上很薄的整装市场。所以给两种：',
      '- **忽略装（主口径）**：两侧都按 尺寸段 × 形态 × 属性取值 汇总丰富度和框内份额（整装、拆装合并），再挂到 HD 单元上（同尺寸同属性的 HD 整装单元、拆装单元拿到同一个差距值）；',
      '- **严格**：尺寸段 × 装 × 形态 × 属性取值 两侧各自算；Amazon 同框窗口内没有销量的单元，差距照算（Amazon 记 0），另报 Amazon 同框有销量的子样本。',
      '- 标签：两侧都用 v12.2 打标规则的同一套取值（台面材质 D8、主色 D6 → 主色、柜体材质 D7（价格复核前）→ 归类、宽 → 尺寸段）；元素 Amazon 用看图标签归到 HD 文字规则能认的 6 类（夏克式 / 竖棱 / 农场风装饰饰条 / 玻璃门 / 木条格栅 / rattan），其余 Amazon 元素不参与对齐。'
      '价格：Amazon 用当月价；HD 只有 2026-11-03 当天的价（历史价拿不到），所以 HD 价位段是"今天的价套到过去"。', '')

    # 描述
    d = PAN['忽略装']
    P('### 1.1 样本与分布（忽略装）', '',
      f'单元 × 时点 {len(d):,} 个（{d["单元"].nunique()} 个单元、{d["T"].nunique()} 个 T0），其中大单元（近 3 个月月均 ≥ {BIG:,.0f} 件）{int((d["近3月"] >= BIG).sum()):,} 个。'
      f'Amazon 同（尺寸段 × 形态）框窗口内有销量的占 {(d["az框销量"] > 0).mean():.0%}；单元本身在 Amazon 有销量的占 {(d["az_销量"] > 0).mean():.0%}。', '',
      '| 量 | HD 中位（P25–P75） | Amazon 中位（P25–P75） | 差距 中位（P25–P75） |', '| :--- | :--- | :--- | :--- |')
    q = lambda s: f'{s.median():.1f}（{s.quantile(0.25):.1f}–{s.quantile(0.75):.1f}）'
    for c, g in (('家族', 'G家族'), ('有效家族', 'G有效家族'), ('子体', 'G子体'), ('价位段', 'G价位段'), ('相对价位段', 'G相对价位段'), ('主色数', 'G主色数')):
        P(f'| {c} | {q(d["hd_" + c])} | {q(d["az_" + c])} | {q(d[g])} |')
    P(f'| 框内份额 | {q(d["hd_框内份额"] * 100)}% | {q(d["az_框内份额"] * 100)}% | D份额差 {q(d["D份额差"])} |', '')
    cm = d[['G家族', 'G有效家族', 'G子体', 'G价位段', 'G主色数', 'D份额', 'D斜率', 'D份额差', 'b6', 'x5', 'x4']].corr(method='spearman')
    P('信号之间的秩相关（单元 × 时点）：G家族 与 G子体 ' + f2(cm.at['G家族', 'G子体']) + '、与 G有效家族 ' + f2(cm.at['G家族', 'G有效家族']) + '、与 G价位段 ' + f2(cm.at['G家族', 'G价位段'])
      + '、与 D份额 ' + f2(cm.at['G家族', 'D份额']) + '、与 HD 体量 x4 ' + f2(cm.at['G家族', 'x4']) + '、与 b6 ' + f2(cm.at['G家族', 'b6']) + '、与 x5 ' + f2(cm.at['G家族', 'x5'])
      + '；D份额差 与 x4 ' + f2(cm.at['D份额差', 'x4']) + '。G家族和 HD 体量负相关有机械成分（HD 单元越小，家族越少），所以所有回归都控制 x4。', '')

    # ---------------- 2. 回归 ----------------
    P('## 2. 回归：在 b6、x5（及 x2、x4）之上加差距信号', '',
      'y6 = Σ β·基础信号 + γ·差距信号 + T0 × 属性类型 固定效应 + ε；标准误按单元聚类（同一单元在 11 个 T0 重复出现）。信号都标准化（全样本 z 分数），系数 = 信号高 1 个标准差，y6（对数份额变化）多多少。', '')
    SIG = ['G家族', 'G有效家族', 'G子体', 'G价位段', 'G相对价位段', 'G主色数', 'az_外观', 'lnAZ家族', 'lnHD家族', 'lnHD框内份额', 'D份额', 'D斜率', 'D份额差']
    def prep(d):
        d = d.copy()
        for c in BASE + SIG: d['z_' + c] = zs(d[c].astype(float))
        d['z_交互'] = zs(d['z_D份额'] * d['z_G家族'])
        d['证明'] = ((d['az_框内份额'] >= d['az_框内份额'].median()) & (d['D斜率'] > 0)).astype(float)
        d['z_证明×稀缺'] = zs(d['证明'] * d['G家族'])
        return d
    ZB = ['z_' + c for c in BASE]
    RES = {}; DEC = {}
    def reg_rows(d, label_extra=''):
        rows = []
        m0 = ols(d, ZB); rows.append(('基础（b6、x5、x2、x4）', m0, None))
        for s in SIG:
            rows.append((f'+ {s}', ols(d, ZB + ['z_' + s]), 'z_' + s))
        rows.append(('+ G家族 + D份额 + D斜率', ols(d, ZB + ['z_G家族', 'z_D份额', 'z_D斜率']), 'z_G家族'))
        rows.append(('+ G家族 + D份额 + 交互', ols(d, ZB + ['z_G家族', 'z_D份额', 'z_交互']), 'z_交互'))
        rows.append(('+ G家族 + 证明 + 证明×稀缺', ols(d, ZB + ['z_G家族', 'z_证明×稀缺']), 'z_证明×稀缺'))
        return rows
    for align in ('忽略装', '严格'):
        d = prep(PAN[align]); PAN[align] = d
        rows = reg_rows(d); RES[align] = rows
        m0 = rows[0][1]
        P(f'### 2.{1 if align == "忽略装" else 2} {align}对齐（N = {int(m0.nobs):,}，聚类 {d["单元"].nunique()} 个单元）', '',
          '| 模型 | 关注的系数 | 系数 | t | p | b6 系数（t） | x5 系数（t） | R²（含固定效应） |', '| :--- | :--- | ---: | ---: | ---: | :--- | :--- | ---: |')
        for lab, m, k in rows:
            cc = k[2:] if k else '—'
            P(f"| {lab} | {cc} | {f3(m.params[k]) if k else '—'} | {f'{m.tvalues[k]:+.2f}' if k else '—'} | {f'{m.pvalues[k]:.3f}' if k else '—'} | "
              f"{m.params['z_b6']:+.3f}（{m.tvalues['z_b6']:+.1f}） | {m.params['z_x5']:+.3f}（{m.tvalues['z_x5']:+.1f}） | {m.rsquared:.3f} |")
        mm = rows[len(SIG) + 1][1]
        md = ols(d, ZB + ['z_lnAZ家族', 'z_lnHD家族'])
        P('', f'**拆开看差距的两头**（同一模型里同时放 ln(Amazon 家族 + 1) 和 ln(HD 家族 + 1)）：Amazon 侧 {f3(md.params["z_lnAZ家族"])}（t {md.tvalues["z_lnAZ家族"]:+.2f}，p {md.pvalues["z_lnAZ家族"]:.3f}），'
          f'HD 侧 {f3(md.params["z_lnHD家族"])}（t {md.tvalues["z_lnHD家族"]:+.2f}，p {md.pvalues["z_lnHD家族"]:.3f}）。'
          '"供给稀缺"要求 HD 侧系数为负（HD 家族越少，之后越涨）；正号说明作用来自 Amazon 侧。')
        me = ols(d, ZB + ['z_D份额', 'z_lnHD框内份额'])
        P(f'D份额差 同样拆开：Amazon 框内份额 {f3(me.params["z_D份额"])}（t {me.tvalues["z_D份额"]:+.2f}，p {me.pvalues["z_D份额"]:.3f}），'
          f'HD 框内份额 {f3(me.params["z_lnHD框内份额"])}（t {me.tvalues["z_lnHD框内份额"]:+.2f}，p {me.pvalues["z_lnHD框内份额"]:.3f}）。')
        DEC[align] = (md, me)
        P('', f'"+ G家族 + D份额 + D斜率" 一行里另两个系数：D份额 {f3(mm.params["z_D份额"])}（t {mm.tvalues["z_D份额"]:+.2f}，p {mm.pvalues["z_D份额"]:.3f}），'
          f'D斜率 {f3(mm.params["z_D斜率"])}（t {mm.tvalues["z_D斜率"]:+.2f}，p {mm.pvalues["z_D斜率"]:.3f}）。', '')

    # ---------------- 3. 区分力：加入前后 ----------------
    d = PAN['忽略装']
    P('## 3. 区分力：加入前后（按单元分组 5 折交叉验证，忽略装）', '',
      '同一个单元在所有 T0 一起留出，用其他单元估的系数（含 T0 × 属性类型固定效应）预测它；再在每个 T0 内算预测与 y6 的秩相关，11 个 T0 平均。这是"跨单元"的样本外，不是"跨时间"的'
      '（Amazon 表从 2024-10 起，T0 前能拿到完整 Amazon 窗口且结果已知的训练时点太少，做不了按时间滚动）。', '',
      '| 模型 | 秩相关 全部 | 秩相关 大单元 | T0 里比基础高的个数（全部 / 大） | 五分档 之后变大比例（低 → 高） | 五分档 y6 均值（低 → 高） |', '| :--- | ---: | ---: | :--- | :--- | :--- |')
    MODELS = [('仅 b6', ['z_b6']), ('基础（b6、x5、x2、x4）', ZB), ('基础 + G家族', ZB + ['z_G家族']), ('基础 + G价位段', ZB + ['z_G价位段']),
              ('基础 + D份额差', ZB + ['z_D份额差']), ('基础 + ln(Amazon 家族 + 1)（只看 Amazon）', ZB + ['z_lnAZ家族']),
              ('基础 + Amazon 外观组合（只看 Amazon）', ZB + ['z_az_外观']), ('基础 + G家族 + D份额 + 交互', ZB + ['z_G家族', 'z_D份额', 'z_交互'])]
    CVR = {}
    for lab, xs in MODELS:
        d['p_' + lab] = cv_pred(d, xs); a, ra = per_t_rho(d, 'p_' + lab, 0); b, rb = per_t_rho(d, 'p_' + lab, BIG); CVR[lab] = (a, b, ra, rb)
    ba, bb, bra, brb = CVR['基础（b6、x5、x2、x4）']
    for lab, xs in MODELS:
        a, b, ra, rb = CVR[lab]; bt = bins_table(d, 'p_' + lab)
        win = '—' if lab.startswith(('仅', '基础（')) else f"{sum(x > y for x, y in zip(ra, bra))}/{len(ra)} / {sum(x > y for x, y in zip(rb, brb))}/{len(rb)}"
        P(f"| {lab} | {f2(a)} | {f2(b)} | {win} | {' / '.join(pc(x) for x in bt['up'])} | {' / '.join(f'{x:+.2f}' for x in bt['my'])} |")
    P('', '五分档：每个 T0 内按预测值排成 5 档再合并（每档约 ' + f'{len(d) // 5:,}' + ' 个单元 × 时点）。', '')

    # 差距本身的分档（扣掉基础后）
    m0 = ols(d, ZB); d['残差'] = m0.resid
    gres = sm.OLS(d['z_G家族'], sm.add_constant(pd.concat([d[ZB], pd.get_dummies(d['T'].astype(str) + '|' + d['属性'], drop_first=True, dtype=float)], axis=1))).fit().resid
    d['G家族_扣基础'] = gres.values
    P('### 3.1 G家族 分三档，之后怎样（忽略装）', '', '| 分档（每个 T0 内） | 个数 | 之后变大 | y6 均值 | 扣基础后 y6 残差均值 | 大单元：个数 / 之后变大 |', '| :--- | ---: | ---: | ---: | ---: | :--- |')
    for col, nm in (('G家族', 'G家族 原值'), ('G家族_扣基础', 'G家族 扣掉 b6、x5、x2、x4 后')):
        d['档'] = d.groupby('T')[col].transform(lambda s: pd.qcut(s.rank(method='first'), 3, labels=['低', '中', '高']))
        for b, g in d.groupby('档', observed=True):
            gb = g[g['近3月'] >= BIG]
            P(f"| {nm}：{b} | {len(g)} | {pc((g['y6'] > 0).mean())} | {g['y6'].mean():+.2f} | {g['残差'].mean():+.3f} | {len(gb)} / {pc((gb['y6'] > 0).mean())} |")
    # 2×2：需求已证明 × 供给稀缺
    d['稀缺'] = d.groupby('T')['G家族_扣基础'].transform(lambda s: s >= s.quantile(2 / 3))
    P('', '**需求已证明 × 供给稀缺（2 × 2）**：证明 = Amazon 框内份额在样本上半且 Amazon 框内斜率 > 0；稀缺 = 扣基础后 G家族 在该 T0 的前 1/3。', '',
      '| | 个数 | 之后变大 | y6 均值 | 扣基础后残差均值 |', '| :--- | ---: | ---: | ---: | ---: |')
    for (pz, sc_), g in d.groupby(['证明', '稀缺']):
        P(f"| {'需求已证明' if pz else '未证明'} × {'稀缺' if sc_ else '不稀缺'} | {len(g)} | {pc((g['y6'] > 0).mean())} | {g['y6'].mean():+.2f} | {g['残差'].mean():+.3f} |")
    P('')
    # 每个 T0 的偏相关（与第二轮候选信号检验同做法）
    pr = []
    for T, g in d.groupby('T'):
        Xb = sm.add_constant(pd.concat([g[ZB], pd.get_dummies(g['属性'], drop_first=True, dtype=float)], axis=1))
        ry = sm.OLS(g['y6'], Xb).fit().resid; rg = sm.OLS(g['G家族'], Xb).fit().resid
        pr.append((ms(T), spearmanr(g['G家族'], g['y6'])[0], spearmanr(rg, ry)[0], spearmanr(g['D份额差'], g['y6'])[0]))
    P('### 3.2 每个 T0 的相关（与 `候选信号检验_20261103.md` 同做法：单独 / 扣掉 b6、x5、x2、x4 后）', '',
      '| T0 | G家族 单独 | G家族 扣掉后 | D份额差 单独 |', '| :--- | ---: | ---: | ---: |')
    for r in pr: P(f'| {r[0]} | {f2(r[1])} | {f2(r[2])} | {f2(r[3])} |')
    P('', f"G家族 扣掉后：{sum(r[2] > 0 for r in pr)}/{len(pr)} 个 T0 为正，范围 {min(r[2] for r in pr):+.2f} 至 {max(r[2] for r in pr):+.2f}；"
      f"单独：{sum(r[1] > 0 for r in pr)}/{len(pr)} 为正，范围 {min(r[1] for r in pr):+.2f} 至 {max(r[1] for r in pr):+.2f}。", '')

    # 机制：老家族变大 vs 新家族进来
    do = d.dropna(subset=['y6老']).copy(); mo = ols(do.assign(y6=do['y6老']), ZB + ['z_G家族'])
    P('### 3.3 差距怎么起作用：HD 老家族变大，还是 HD 新家族进来', '',
      '把 y6 拆开：y6老 = 只算 T0 前 6 个月就在这个单元卖的家族，第 6–8 个月的份额对近 6 个月份额的对数变化；"新家族占比" = 第 6–8 个月单元销量里 T0 前不在这个单元卖的家族的占比。', '',
      f'- y6老 对 基础 + G家族：G家族 {f3(mo.params["z_G家族"])}（t {mo.tvalues["z_G家族"]:+.2f}，p {mo.pvalues["z_G家族"]:.3f}）；全 y6 时为 {f3(RES["忽略装"][1][1].params["z_G家族"])}。', '',
      '| G家族 扣基础后分档 | 第 6–8 个月新家族占比（均值） | y6老 均值 | y6老 > 0 的比例 | y6 均值 |', '| :--- | ---: | ---: | ---: | ---: |')
    d['档'] = d.groupby('T')['G家族_扣基础'].transform(lambda s: pd.qcut(s.rank(method='first'), 3, labels=['低', '中', '高']))
    MECH = {}
    for b, g in d.groupby('档', observed=True):
        MECH[b] = (g['新家族占比'].mean(), g['y6老'].mean())
        P(f"| {b} | {pc(g['新家族占比'].mean())} | {g['y6老'].mean():+.2f} | {pc((g['y6老'] > 0).mean())} | {g['y6'].mean():+.2f} |")
    P('')

    # ---------------- 4. 稳健性 ----------------
    P('## 4. 稳健性（主信号 G家族，模型 = 基础 + G家族；另列 D份额差、交互）', '',
      '| 设定 | N | G家族 系数（t，p） | 拆开：Amazon 侧 / HD 侧 系数（t） | Amazon 外观组合（只看 Amazon）系数（t，p） | D份额差 系数（t，p） | 交互 系数（t，p） | CV 秩相关 全部 / 大：基础 → + G家族 → + G家族 + D份额 + 交互 |',
      '| :--- | ---: | :--- | :--- | :--- | :--- | :--- | :--- |')
    big_unit = d.groupby('单元')['近3月'].mean().idxmax()
    big_frame = d.groupby('框')['近3月'].sum().idxmax()
    SETS = [('忽略装，全部', PAN['忽略装'], '单元'), ('严格，全部', PAN['严格'], '单元'),
            ('严格，Amazon 同框有销量', PAN['严格'][PAN['严格']['az框销量'] > 0], '单元'),
            (f'忽略装，去掉最大单元（{big_unit}）', d[d['单元'] != big_unit], '单元'),
            (f'忽略装，去掉最大框（{big_frame}）', d[d['框'] != big_frame], '单元'),
            (f'忽略装，只看大单元（≥ {BIG:,.0f} 件）', d[d['近3月'] >= BIG], '单元'),
            ('忽略装，近 3 月 ≥ 50 件（与小试训练门槛同）', d[d['近3月'] >= 50], '单元'),
            ('忽略装，去掉元素单元', d[d['属性'] != '元素'], '单元'),
            ('忽略装，只看整装单元', d[d['装'] == '整装'], '单元'),
            ('忽略装，只看拆装单元', d[d['装'] == '拆装'], '单元'),
            ('忽略装，按框聚类', d, '框'),
            ('忽略装，y6 两端各截 5%', d.assign(y6=d['y6'].clip(d['y6'].quantile(0.05), d['y6'].quantile(0.95))), '单元')]
    ROB = []
    for lab, g, cl in SETS:
        g = g.copy()
        for c in BASE + SIG: g['z_' + c] = zs(g[c].astype(float))
        g['z_交互'] = zs(g['z_D份额'] * g['z_G家族'])
        try:
            m1 = ols(g, ZB + ['z_G家族'], cl); m2 = ols(g, ZB + ['z_D份额差'], cl); m3 = ols(g, ZB + ['z_G家族', 'z_D份额', 'z_交互'], cl)
            m4 = ols(g, ZB + ['z_lnAZ家族', 'z_lnHD家族'], cl); m5 = ols(g, ZB + ['z_az_外观'], cl)
        except Exception as e:   # 子样本太小时固定效应吃光自由度，如实记下
            P(f'| {lab} | {len(g)} | 估不出（{type(e).__name__}） | | | |'); continue
        cvs = ''; cvv = (np.nan,) * 6
        if len(g) >= 200 and g['单元'].nunique() >= 10:
            g['_p0'] = cv_pred(g, ZB); g['_p1'] = cv_pred(g, ZB + ['z_G家族']); g['_p2'] = cv_pred(g, ZB + ['z_G家族', 'z_D份额', 'z_交互'])
            cvv = tuple(per_t_rho(g, c, b_)[0] for c in ('_p0', '_p1', '_p2') for b_ in (0, BIG))
            cvs = ' → '.join(f"{f2(cvv[i])} / {f2(cvv[i + 1])}" for i in (0, 2, 4))
        k = lambda m, c: f"{m.params[c]:+.3f}（{m.tvalues[c]:+.2f}，{m.pvalues[c]:.3f}）"
        P(f"| {lab} | {int(m1.nobs):,} | {k(m1, 'z_G家族')} | {m4.params['z_lnAZ家族']:+.3f}（{m4.tvalues['z_lnAZ家族']:+.2f}） / {m4.params['z_lnHD家族']:+.3f}（{m4.tvalues['z_lnHD家族']:+.2f}） | {k(m5, 'z_az_外观')} | "
          f"{k(m2, 'z_D份额差')} | {k(m3, 'z_交互')} | {cvs or '样本太小，不做'} |")
        ROB.append(dict(lab=lab, g=m1.params['z_G家族'], gp=m1.pvalues['z_G家族'], az=m4.params['z_lnAZ家族'], azp=m4.pvalues['z_lnAZ家族'], hd=m4.params['z_lnHD家族'],
                        hdp=m4.pvalues['z_lnHD家族'], dd=m2.params['z_D份额差'], ddp=m2.pvalues['z_D份额差'], ia=m3.params['z_交互'], iap=m3.pvalues['z_交互'], cv=cvv, lk=m5.params['z_az_外观'], lkp=m5.pvalues['z_az_外观']))
    P('')

    # ---------------- 5. 站在 2026-10 的例子 ----------------
    T = mi('2026-10')   # 窗口 2026-04 至 09，两渠道同窗口（Amazon 表到 09）
    rows = []
    hdT = richness(hdA, T, '忽略装', ['尺寸段', '装']).set_index(['属性', '框', '取值'])
    azT = richness(azA, T, '忽略装', ['尺寸段', '装']).set_index(['属性', '框', '取值'])
    hdframe = hdT.groupby(level=1)['框销量'].first()
    E = azT.join(hdT, rsuffix='_hd', how='left')
    for c in ('家族', '有效家族', '子体', '价位段', '销量', '框内份额'): E[c + '_hd'] = E[c + '_hd'].fillna(0)
    E['HD框销量'] = [hdframe.get(f, 0) for f in E.index.get_level_values(1)]
    E['G家族'] = np.log((E['家族'] + 1) / (E['家族_hd'] + 1)); E['G价位段'] = E['价位段'] - E['价位段_hd']
    cand = E[(E['销量'] >= 300) & (E['框内份额'] >= 0.10) & (E['框内斜率'] > 0) & (E['HD框销量'] >= 200) & (E.index.get_level_values(0) != '元素')].sort_values('G家族', ascending=False)
    # HD 单元份额走势（全品类口径，季度）与 Amazon 单元份额走势（框内，季度）
    def hd_trend(att, fr, v):
        x = unit_rows(hdA, att, '忽略装'); x = x[(x['框'] == fr) & (x['取值'] == v)]
        fx = unit_rows(hdA, att, '忽略装'); fx = fx[fx['框'] == fr]
        out = []
        for a, b in ((mi('2025-04'), mi('2025-09')), (mi('2025-10'), mi('2026-03')), (mi('2026-04'), mi('2026-09'))):
            s = x[x['m'].between(a, b)]['c'].sum(); t = fx[fx['m'].between(a, b)].drop_duplicates(['fam', 'pid', 'm'])['c'].sum()
            out.append(f'{s / 6:,.0f} 件（框内 {s / max(t, 1):.0%}）')
        return ' → '.join(out)
    def az_trend(att, fr, v):
        x = unit_rows(azA, att, '忽略装'); fx = x[x['框'] == fr]; x = fx[fx['取值'] == v]
        out = []
        for a, b in ((mi('2025-04'), mi('2025-09')), (mi('2025-10'), mi('2026-03')), (mi('2026-04'), mi('2026-09'))):
            s = x[x['m'].between(a, b)]['c'].sum(); t = fx[fx['m'].between(a, b)]['c'].sum()
            out.append(f'{s / 6:,.0f} 件（框内 {s / max(t, 1):.0%}）')
        return ' → '.join(out)
    def tops(dd, att, fr, v, n=4):
        w = unit_rows(dd[dd['m'].between(T - 6, T - 1)], att, '忽略装'); w = w[(w['框'] == fr) & (w['取值'] == v)]
        f = w.groupby('fam').agg(c=('c', 'sum'), 品牌=('品牌', 'first'), p=('价格', 'median')).sort_values('c', ascending=False)
        return '；'.join(f"{r.品牌 or '—'} ${r.p:,.0f}（{r.c / 6:,.0f} 件/月）" for r in f.head(n).itertuples())
    def pb_list(dd, att, fr, v):
        w = unit_rows(dd[dd['m'].between(T - 6, T - 1) & (dd['c'] > 0)], att, '忽略装'); w = w[(w['框'] == fr) & (w['取值'] == v)]
        lab = ['<$200', '$200–300', '$300–450', '$450–650', '$650–900', '$900–1,300', '$1,300+']
        b = pd.cut(w['价格'], PRICE_ABS, labels=False, right=False).dropna().astype(int)
        cs = w.assign(b=b).dropna(subset=['b']).groupby('b')['c'].sum(); cs = cs / max(cs.sum(), 1)
        return '、'.join(f'{lab[i]} {x:.0%}' for i, x in cs.items()) or '—'
    def hd_mix(att, fr, v):
        """HD 同框（尺寸段 × 形态）里自有品牌占比、整装占比，以及（主色单元）主色可认出的比例。"""
        w = hdA[hdA['m'].between(T - 6, T - 1)]; w = w.assign(框=frame_key(w, '忽略装')); f = w[w['框'] == fr]; tot = max(f['c'].sum(), 1)
        u = unit_rows(w, att, '忽略装'); u = u[(u['框'] == fr) & (u['取值'] == v)]
        s_ = f"HD 同框自有品牌占 {f.loc[f['PB'], 'c'].sum() / tot:.0%}、整装占 {f.loc[f['装'] == '整装', 'c'].sum() / tot:.0%}"
        if len(u): s_ += f"；本单元 HD 销量里整装占 {u.loc[u['装'] == '整装', 'c'].sum() / max(u['c'].sum(), 1):.0%}"
        if att == '主色': s_ += f"；HD 同框主色认得出的销量只占 {f.loc[f['主色'] != '未知', 'c'].sum() / tot:.0%}（认不出的不计入，HD 侧可能少算）"
        return s_
    def az_mix(att, fr, v):
        w = azA[azA['m'].between(T - 6, T - 1)]; u = unit_rows(w, att, '忽略装'); u = u[(u['框'] == fr) & (u['取值'] == v)]
        return f"Amazon 本单元销量里整装占 {u.loc[u['装'] == '整装', 'c'].sum() / max(u['c'].sum(), 1):.0%}"
    have = cand[cand['家族_hd'] >= 1]; absent = cand[cand['家族_hd'] < 1]
    P('## 5. 站在 2026-10：差距最大、且 Amazon 需求已证明的 HD 单元', '',
      '窗口 2026-04 至 09（两渠道同窗口），忽略装对齐（尺寸段 × 形态 × 属性取值）。筛选：Amazon 单元月均 ≥ 300 件、框内份额 ≥ 10%、框内份额斜率 > 0（需求已证明、在涨）；'
      'HD 同框月均 ≥ 200 件（HD 有这个尺寸的市场）；不含元素单元（HD 元素认不全，差距会被高估）。按 G家族 从大到小。', '',
      f'### 5.1 HD 有、但很薄（回归样本里的情形，{len(have)} 个，列前 8）', '',
      '| 单元（尺寸段 · 形态 · 属性） | Amazon 家族 / 子体 / 价位段 | HD 家族 / 子体 / 价位段 | G家族 | Amazon 月均（框内份额） | HD 月均（框内份额） |', '| :--- | :--- | :--- | ---: | :--- | :--- |')
    for (att, fr, v), r in have.head(8).iterrows():
        P(f"| {fr} · {att}：{v} | {r['家族']:.0f} / {r['子体']:.0f} / {r['价位段']:.0f} | {r['家族_hd']:.0f} / {r['子体_hd']:.0f} / {r['价位段_hd']:.0f} | {r['G家族']:+.2f} | "
          f"{r['销量']:,.0f}（{r['框内份额']:.0%}） | {r['销量_hd']:,.0f}（{r['框内份额_hd']:.0%}） |")
    P('', f'### 5.2 HD 前 300 里完全没有（{len(absent)} 个；回归只覆盖 HD 已有销量的单元，这类在样本外，只作参考）', '',
      '| 单元 | Amazon 家族 / 子体 / 价位段 | Amazon 月均（框内份额） |', '| :--- | :--- | :--- |')
    for (att, fr, v), r in absent.head(6).iterrows():
        P(f"| {fr} · {att}：{v} | {r['家族']:.0f} / {r['子体']:.0f} / {r['价位段']:.0f} | {r['销量']:,.0f}（{r['框内份额']:.0%}） |")
    P('', '**5.1 前 3 个的两侧事实**（份额走势 = 2025-04 至 09 → 2025-10 至 2026-03 → 2026-04 至 09 的月均销量与框内份额；价位段 = 窗口内销量落在各段的占比，HD 用今天的价；'
      '主要家族 = 窗口内销量前 4 的家族：品牌、中位价、月均）：', '')
    EX = []
    for i, ((att, fr, v), r) in enumerate(have.head(3).iterrows(), 1):
        EX.append((fr, att, v, r))
        P(f'{i}. **{fr} · {att}：{v}**（G家族 {r["G家族"]:+.2f}，G价位段 {r["G价位段"]:+.0f}）',
          f'   - Amazon：家族 {r["家族"]:.0f}、子体 {r["子体"]:.0f}、价位段 {r["价位段"]:.0f}（{pb_list(azA, att, fr, v)}）；份额走势 {az_trend(att, fr, v)}；{az_mix(att, fr, v)}；主要家族 {tops(azA, att, fr, v)}',
          f'   - HD：家族 {r["家族_hd"]:.0f}、子体 {r["子体_hd"]:.0f}、价位段 {r["价位段_hd"]:.0f}（{pb_list(hdA, att, fr, v)}）；份额走势 {hd_trend(att, fr, v)}；{hd_mix(att, fr, v)}；主要家族 {tops(hdA, att, fr, v) or "—"}')
    P('')
    # ---------------- 6. 推导 ----------------
    def wmed(p_, w_):
        k = p_.notna() & (w_ > 0); o = np.argsort(p_[k].values); cw = np.cumsum(w_[k].values[o])
        return float(p_[k].values[o][np.searchsorted(cw, cw[-1] / 2)])
    nb = lambda x: html.unescape(str(x)).strip().lower() if isinstance(x, str) and x.strip() else ''
    azb = set(azA['品牌'].map(nb)) - {''}
    h = hdA.assign(b=hdA['品牌'].map(nb)); h['跨'] = h['b'].isin(azb) & ~h['PB']
    ff = h[h['c'] > 0].groupby('fam')['m'].min(); h['新家族'] = h['fam'].map(ff) >= mi('2025-01')
    h26 = h[h['m'] >= mi('2026-01')]; tot26 = h26['c'].sum()
    st = dict(pb=h26.loc[h26['PB'], 'c'].sum() / tot26, cross=h26.loc[h26['跨'], 'c'].sum() / tot26,
              new_cross=h26.loc[h26['新家族'] & h26['跨'], 'c'].sum() / max(h26.loc[h26['新家族'], 'c'].sum(), 1),
              new_pb=h26.loc[h26['新家族'] & h26['PB'], 'c'].sum() / max(h26.loc[h26['新家族'], 'c'].sum(), 1),
              ncross=h26.loc[h26['跨'], 'fam'].nunique(), nfam=h26['fam'].nunique(),
              hd_med=wmed(h26['价格'], h26['c']), az_med=wmed(a26['价格'], a26['c']))
    # 跨渠道品牌在高 / 低差距单元里的份额（T0 前 6 个月，单元内）
    mG = RES['忽略装'][1][1]; mGs = RES['严格'][1][1]; md, me = DEC['忽略装']; mds, mes = DEC['严格']
    cvb, cvg = CVR['基础（b6、x5、x2、x4）'], CVR['基础 + G家族']; cvaz = CVR['基础 + ln(Amazon 家族 + 1)（只看 Amazon）']; cvlk = CVR['基础 + Amazon 外观组合（只看 Amazon）']; cvi = CVR['基础 + G家族 + D份额 + 交互']
    rb = next(r for r in ROB if r['lab'].startswith('忽略装，只看大单元'))
    rs = next(r for r in ROB if r['lab'] == '严格，全部')['cv']; CVR_S = (rs[0], rs[1], rs[2], rs[3]); cvb_big = (rb['cv'][0], rb['cv'][2], rb['cv'][4])
    rob_ok = [r for r in ROB if r['lab'].startswith('忽略装') and r['gp'] < 0.05]
    rob_lo = [r['lab'] for r in ROB if r['gp'] >= 0.05]
    P('## 6. 推导：为什么会有用、为什么"稀缺"本身不起作用', '',
      f'1. **起作用的是 Amazon 那一头，不是 HD 那一头**。把 G家族拆成两头（§2.1），Amazon 家族数 {f3(md.params["z_lnAZ家族"])}（t {md.tvalues["z_lnAZ家族"]:+.2f}），'
      f'HD 家族数 {f3(md.params["z_lnHD家族"])}（t {md.tvalues["z_lnHD家族"]:+.2f}）——HD 家族多的单元之后**不是**更差，反而略好；份额差也一样：Amazon 框内份额 {f3(me.params["z_D份额"])}（t {me.tvalues["z_D份额"]:+.2f}），'
      f'HD 框内份额 {f3(me.params["z_lnHD框内份额"])}（t {me.tvalues["z_lnHD框内份额"]:+.2f}）。所以数据支持的读法是"**HD 的结构在往 Amazon 的结构靠**"（Amazon 上款多、份额大的尺寸 × 属性，HD 之后份额往上走），'
      '而不是"HD 供给少 → 有缺口 → 会涨"。差距信号有效，是因为它里面装着 Amazon 侧的丰富度；单看 Amazon 侧丰富度，区分力' + ('反而更好' if cvaz[0] > cvg[0] + 0.02 else '和差距差不多') + '（§3 表：'
      f'只看 Amazon 家族数 全部 / 大 {f2(cvaz[0])} / {f2(cvaz[1])}，只看 Amazon 外观组合 {f2(cvlk[0])} / {f2(cvlk[1])}，G家族 {f2(cvg[0])} / {f2(cvg[1])}）。'
      '这两个"只看 Amazon"的版本是看到拆开结果后加的比较，属于事后选择，按同样的打折读。',
      f'2. **靠拢一部分靠新家族进来，一部分靠老家族变大**（§3.3）：差距高的 1/3，第 6–8 个月单元销量里新家族占 {pc(MECH["高"][0])}，低的 1/3 只有 {pc(MECH["低"][0])}；'
      f'只算老家族的 y6老 对 G家族 仍为 {f3(mo.params["z_G家族"])}（p {mo.pvalues["z_G家族"]:.3f}），为全 y6 系数的 {mo.params["z_G家族"] / mG.params["z_G家族"]:.0%}。'
      f'进来的是谁：2026 年 HD 重建销量里自有品牌（Glacier Bay / Home Decorators Collection）占 {pc(st["pb"])}，非自有品牌里同时在 Amazon 表里出现的品牌占全部销量的 {pc(st["cross"])}'
      f'（{st["ncross"]} 个家族 / 共 {st["nfam"]} 个）；2025 年起才有销量的新家族，销量里 {pc(st["new_cross"])} 来自这些 Amazon 也在卖的品牌、{pc(st["new_pb"])} 是自有品牌。'
      '§5 的例子里 HD 30″ / 24″ 黑色柜的主要家族也有 eclife、DELUXE DL LIVING 这类两边都卖的品牌，但量小。'
      + ('合理的推断：HD 的新款主要由买手通过自有品牌上（新家族销量大头是自有品牌），买手跟的是整个市场的款式走向，Amazon 款多、卖得多的尺寸 × 属性正好是这个走向更早、更全的读数；'
         '第三方 / 直发卖家把 Amazon 款搬过来是次要通道。' if st['new_pb'] > 0.5 else
         '合理的推断：HD.com 线上货架上的第三方 / 直发卖家把 Amazon 上卖得动的款搬过来，自有品牌也跟进。')
      + '于是 HD 的尺寸 × 属性结构滞后地向 Amazon 靠。这是推断，数据只能说明"先后和同向"，不能说明因果。',
      f'3. **"稀缺"本身为什么不起作用**：HD 的结构不是由"消费者想要但没货"决定的，而是由门店模式和买手决定的——重建销量 {pc(hd_zz)} 是整装（门店 / 送货上门、免组装）、'
      f'自有品牌占约 {pc(st["pb"])}、按销量加权的价格中位数 ${st["hd_med"]:,.0f}（Amazon ${st["az_med"]:,.0f}；HD 用今天的价）。HD 某个单元家族少，常常是有意不做'
      '（例如陶瓷一体台面、木板台面在 HD 前 300 里几乎没有，§5.2），不等于有一块没满足的需求；HD 家族多的单元往往是 HD 正在加码的方向，所以 HD 侧系数为正。',
      f'4. **严格对齐（同装）时差距基本失效**（G家族 {f3(mGs.params["z_G家族"])}，p {mGs.pvalues["z_G家族"]:.3f}；交叉验证 全部 / 大 {f2(CVR_S[0])} / {f2(CVR_S[1])} → {f2(CVR_S[2])} / {f2(CVR_S[3])}）：'
      f'Amazon 整装只占约 {pc(1 - az_cz)}，同装对齐后 Amazon 侧家族数很薄、噪声大。信息来自 Amazon 整个"尺寸段 × 形态 × 属性"的偏好（主要是拆装货），不是同装的一对一对照。'
      f'严格对齐下仍然显著的是 D份额差（{f3(RES["严格"][SIG.index("D份额差") + 1][1].params["z_D份额差"])}，p {RES["严格"][SIG.index("D份额差") + 1][1].pvalues["z_D份额差"]:.3f}），拆开是 Amazon 框内份额 {f3(mes.params["z_D份额"])}（t {mes.tvalues["z_D份额"]:+.2f}）和 HD 框内份额 {f3(mes.params["z_lnHD框内份额"])}（t {mes.tvalues["z_lnHD框内份额"]:+.2f}）两头都有：'
      '同装框里 HD 份额低的单元之后回升，这一半是 HD 内部的变化（也可能是均值回归），不是跨渠道信息；跨渠道的那一半仍是 Amazon 侧。',
      f'5. **大单元里不一样**：只看大单元（≥ {BIG:,.0f} 件），G家族单独不显著（{f3(rb["g"])}，p {rb["gp"]:.3f}），交叉验证也没有提升；'
      f'倒是"需求已证明 × 供给稀缺"的交互显著（{f3(rb["ia"])}，p {rb["iap"]:.3f}），把交互放进去交叉验证从 {f2(cvb_big[0])} 到 {f2(cvb_big[2])}。'
      '也就是说，在已经有量的 HD 单元里，只有"Amazon 份额大且 HD 家族少"同时成立时才多涨一点；' + f'{len(ROB)} 个稳健性设定里交互 p < 0.05 的只有 {sum(r["iap"] < 0.05 for r in ROB)} 个，'
      + '又是事后看到的，只能当线索，不能当结论。' + f'大单元里只看 Amazon 外观组合为 {f3(rb["lk"])}（p {rb["lkp"]:.3f}）。',
      '6. **幸存者偏差会把它往好看的方向推**：HD 面板只看得到今天在前 300 的家族。差距高的单元里约两成之后销量来自新家族，而新家族里进来又掉出前 300 的失败者看不到，'
      '所以"新家族进来"那一半最容易被高估；老家族那一半（y6老）受影响小一些。按偏差模拟的打折规则，秩相关减 0.05–0.1。', '')

    # ---------------- 7. 结论 ----------------
    gain_all, gain_big = cvg[0] - cvb[0], cvg[1] - cvb[1]
    P('## 7. 结论与决策卡用法', '',
      f'- **能检验出来的**：在 HD 框 × 属性面板上，扣掉 b6、x5、x2、x4 和 T0 × 属性类型固定效应后，跨渠道差距（忽略装，G家族）系数 {f3(mG.params["z_G家族"])}（每 1 个标准差），'
      f't {mG.tvalues["z_G家族"]:+.2f}，p {mG.pvalues["z_G家族"]:.3f}；11 个 T0 的偏相关 {sum(r[2] > 0 for r in pr)}/{len(pr)} 为正（{min(r[2] for r in pr):+.2f} 至 {max(r[2] for r in pr):+.2f}）；'
      f'去掉最大单元 / 最大框、按框聚类、截尾、去掉元素单元都还显著（{len(rob_ok)} 个忽略装设定 p < 0.05）。'
      f'跨单元交叉验证的秩相关 全部 / 大 {f2(cvb[0])} / {f2(cvb[1])} → {f2(cvg[0])} / {f2(cvg[1])}（+{gain_all:.2f} / +{gain_big:.2f}），五分档"之后变大"从低到高更单调。'
      f'打折后（减 0.05–0.1）约 {f2(cvg[0] - 0.1)}–{f2(cvg[0] - 0.05)} / {f2(cvg[1] - 0.1)}–{f2(cvg[1] - 0.05)}。',
      f'- **站不住或没检验到的**：严格同装对齐不显著；只看大单元不显著；拆装单元只到 p ≈ 0.1；'
      f'不显著的设定：{"、".join(rob_lo) or "无"}。"需求已证明 × 供给稀缺"交互在全部单元上为 0（{f3(RES["忽略装"][-2][1].params["z_交互"])}，p {RES["忽略装"][-2][1].pvalues["z_交互"]:.3f}），只在大单元里显著。'
      'Amazon 份额走势（D斜率）没有作用。HD 侧"家族少"本身没有正向作用。只有 11 个相互重叠的 T0、一个渠道一个品类，交叉验证是跨单元的、不是跨时间的。',
      '- **怎么命名**：数据支持的是"**Amazon 结构领先**"（Amazon 上款多、份额大的尺寸 × 属性，HD 之后往那边靠），不是"HD 供给缺口"。'
      '卡片上主读数用 Amazon 侧丰富度（家族数、外观组合），差距值（G家族）和 HD 侧家族数作对照展示；解读写成前者。',
      '- **决策卡上怎么用**：',
      '  1. 作为 HD 机会卡的**证据项，等级"经回测（打折）"**：展示 Amazon 与 HD 两侧的家族数、子体数、价位段、框内份额和走势，以及差距值；用于 HD 全部单元的排序加分（同等 b6、x5 下优先 Amazon 侧丰富的单元），不单独作为立项理由；',
      '  2. **大单元只作参考**：大单元里单独的差距不加分；"Amazon 份额大 + HD 家族少"同时成立时标"线索"，等下一个渠道（Lowe\'s / Wayfair）或滚动到 2026 年后的新 T0 复验；',
      '  3. **HD 完全没有的单元**（如 36″ / 48″ 陶瓷一体台面、木板台面）在回归样本外，差距最大但不能外推；要回答的是"HD 买手为什么不做"（门店整装、品类规划、退货率），属于渠道调研问题，卡上写"未验证"；',
      '  4. 用的时候按忽略装对齐（尺寸段 × 形态 × 属性取值），HD 主色约三成认不出、元素几乎认不出，主色 / 元素单元的 HD 侧家族数要标"可能少算"。', '')
    fpm = azA[azA['c'] > 0].groupby('m')['fam'].nunique()
    P('## 8. 局限', '',
      f'1. 两侧的"家族数"都不是全市场在售数：Amazon 表是每月导出的头部（{ms(fpm.index.min())} 至 {ms(fpm.index.max())} 每月 {fpm.min()}–{fpm.max()} 个有销量的家族，2026 年导出更深），'
      'HD 是今天两个类目前 300 个商品页所在的家族（幸存者）。差距是"头部丰富度"的差距；Amazon 导出深浅随月变化的部分被 T0 固定效应吸收，不同单元受影响不同的部分吸收不了。',
      '2. HD 只有 2026-11-03 当天的价，价位段是今天的价套到过去；Amazon 用当月价。',
      '3. HD 主色约三成、元素九成以上认不出（只用文字规则），主色 / 元素单元的 HD 侧丰富度偏低、差距偏大；去掉元素单元结论不变（§4），主色单元没单独去掉。',
      '4. 只有 11 个相互重叠的 T0（2025-04 至 2026-02），同一单元跨时点重复，t 值按单元聚类仍可能偏乐观；交叉验证是跨单元的，不是跨时间的；只有一个渠道、一个品类。',
      '5. HD 月销 = VP 评论 × 50 + 非 VP × 20，没有按 HD 校准；小单元月度颗粒粗（1 条 VP 评论 = 50 件）。', '')
    # 摘要插到报告头后面
    S0 = ['## 0. 摘要', '',
          f'- 定义：G家族 = ln((Amazon 家族数 + 1) / (HD 家族数 + 1))，同一尺寸段 × 形态 × 属性取值（忽略装），T0 前 6 个月；另有价位段差、子体差、主色差、份额差、"需求已证明 × 稀缺"交互等版本。',
          f'- 回归（加在 b6、x5、x2、x4 之上，T0 × 属性类型固定效应，按单元聚类）：G家族 {f3(mG.params["z_G家族"])}（t {mG.tvalues["z_G家族"]:+.2f}，p {mG.pvalues["z_G家族"]:.3f}）；'
          f'拆开后 Amazon 侧 {f3(md.params["z_lnAZ家族"])}（t {md.tvalues["z_lnAZ家族"]:+.2f}），HD 侧 {f3(md.params["z_lnHD家族"])}（t {md.tvalues["z_lnHD家族"]:+.2f}，方向与"稀缺"相反）。',
          f'- 区分力（跨单元 5 折交叉验证，11 个 T0 平均秩相关 全部 / 大）：基础 {f2(cvb[0])} / {f2(cvb[1])} → 加 G家族 {f2(cvg[0])} / {f2(cvg[1])}；只加 Amazon 侧家族数 {f2(cvaz[0])} / {f2(cvaz[1])}、Amazon 外观组合 {f2(cvlk[0])} / {f2(cvlk[1])}（事后比较）；'
          '严格同装对齐无提升；只看大单元无提升（"需求已证明 × 稀缺"交互例外）。',
          '- 结论：有中等强度、需要打折的证据说明"Amazon 侧款多、份额大 → HD 之后份额上升"（HD 结构向 Amazon 靠）；"HD 少所以会涨"不成立。决策卡上作"经回测（打折）"的证据和全部单元的排序加分，不作独立立项理由；大单元和 HD 完全没有的单元只作参考。', '']
    L[HEAD_END:HEAD_END] = S0
    return dict(PAN=PAN, RES=RES, CVR=CVR, ROB=ROB, pr=pr, BIG=BIG, cand=cand, EX=EX, chk=chk)


if __name__ == '__main__':
    info = main()
    open(OUT, 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L))
