"""单位（产品）与新家族：移植第二轮 `solution-v2/trial/回归_新家族.py` 第 0–3 节与 `两层识别.py` 的新品层（toks / newprod）。

口径不得另起（技术方案 §8.2 第 4 条、RA-104）：
- 单位：家族键沿用 replace 规则（旧键下月消失、一半以上子体整体搬到同一个新键 = 同一产品），再把同品牌、共用子体 ≥ 较小一方一半的单位并成一个；
- 新家族：单位最早子体上架在 2024-10 起；观察期 6 个月；进分母 = 观察期内至少一个月家族月销 ≥ 60 且有子体价格 ≥ 90；
  成功 = 观察期内任一月最好子体小类 BSR ≤ 50，或 SPU 月销售额（家族月销 × 子体均价）≥ $10 万；
- 新家族特征只用首个在榜月；做到概率 = L2 逻辑回归（C=0.1），词表 = 训练集中出现 ≥ 3 次的特征。

输入是 `panel.raw_frame()` 的行（每行 = 月 × 子体，已去掉不纳入分析与“不是本品类”的商品），列名用业务名；
这里转成第二轮脚本的列名（m、c、家族键、子ASIN …）后逐句移植，便于和第二轮结果逐项比对。
"""
import html
import itertools

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

WIN, EARLY, BSR_LINE, REV_LINE = 6, 3, 50, 100000
ENTRY_UNITS = 60  # 进分母：至少一个月整款卖到 60 件
SIZE = [(18, 15, 21), (24, 21, 26), (28, 26, 29), (30, 29, 33), (36, 33, 39), (42, 39, 45), (48, 45, 54), (60, 54, 66)]  # 下限含、上限不含；28″ 单独成档（AC-F18-09，wen 2026-11-05）
SIZE_ORDER = [f'{c}″' for c, _, _ in SIZE] + ['72″+']
COLOR = {'白色': '白', '黑色': '黑', '灰色': '灰', '原木色': '原木', '胡桃木色': '深木', '深咖啡色': '深木', '棕色': '深木',
         '蓝色': '蓝', '藏青色': '蓝', '灰蓝色': '蓝', '绿色': '绿', '灰绿色': '绿'}
RAW_UNK = {'信息不足', '待图片核验', '', 'nan', 'None', '<NA>'}


def mi(s) -> int:
    """'YYYY-MM' → 月序号。"""
    return int(str(s)[:4]) * 12 + int(str(s)[5:7]) - 1


def ms(i) -> str:
    i = int(i)
    return f'{i // 12}-{i % 12 + 1:02d}'


def band(x):
    """宽度（英寸）→ 尺寸段。"""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if np.isnan(x):
        return None
    for c, lo, hi in SIZE:
        if lo <= x < hi:
            return f'{c}″'
    return '72″+' if x >= 66 else None


def cab(v):
    """柜体材质文字标签（实木价格复核前）→ 分析用柜体材质。"""
    v = '' if v is None or (isinstance(v, float) and np.isnan(v)) else str(v)
    if v in RAW_UNK:
        return '未知'
    if v in ('实木', '实木框架+实木'):
        return '实木'
    if v.startswith('实木框架'):
        return '实木框架'
    if v == 'MDF':
        return 'MDF'
    if '胶合板' in v:
        return '含胶合板'
    if '刨花板' in v:
        return '含刨花板'
    return '其他'


def color(v):
    """柜体颜色 → 主色。"""
    if v is None or (isinstance(v, float) and np.isnan(v)) or str(v) in RAW_UNK:
        return '未知'
    return COLOR.get(str(v), '其他')


def top_type(t, s):
    """台面材质 + 台盆材质 → 台面类型（市场层“台面”大属性）。"""
    t = '' if t is None or (isinstance(t, float) and np.isnan(t)) else str(t)
    s = '' if s is None or (isinstance(s, float) and np.isnan(s)) else str(s)
    if t == '陶瓷':
        return '陶瓷一体'
    if t in ('树脂', 'Cultured Marble'):
        return '树脂一体'
    if t in ('岗石', '石英石', '岩板', '卡拉拉大理石'):
        return '石材台面'
    if t == '木板':
        return '木板台面'
    if t == '玻璃':
        return '玻璃台面'
    if t.startswith('不适用'):
        return '不含台面'
    if s.startswith('不适用'):
        return '不含盆'
    return {'玻璃盆': '台面未知·玻璃盆', '陶瓷盆': '台面未知·陶瓷盆', '树脂盆': '台面未知·树脂盆'}.get(s, '未知')


def img_el(e):
    """看图元素 → 元素集：标题拆出的 fluted / reeded 同时算上层的“竖棱”。"""
    if not (isinstance(e, str) and e):
        return ()
    base = e.replace('fluted', '竖棱').replace('reeded', '竖棱')
    return (base,) if base == e else (base, e)


def elements_from_tag(v):
    """Tag「元素」存的是去掉 fluted / reeded 后的元素一（多值用 | 分隔）。"""
    if not isinstance(v, str) or not v or v in RAW_UNK:
        return []
    return [x for x in v.split('|') if x and x not in RAW_UNK]


def tier(r):
    return '未知' if pd.isna(r) else ('低' if r < 0.85 else ('高' if r > 1.15 else '中'))


def UNK(v):
    return v is None or (isinstance(v, float) and np.isnan(v)) or str(v) in ('未知', '', 'nan', 'None') or str(v).startswith('台面未知')


LEARN0 = mi('2024-10')


def build(raw: pd.DataFrame):
    """raw → (A, U, feat, TK)。A 为第二轮口径的行级表，U 为新家族（单位）表。"""
    A = pd.DataFrame({
        '月份': raw['month'].values, '子ASIN': raw['item_id'].values, '家族键': raw['family_key'].values,
        '品牌': raw['brand'].values, '价格': pd.to_numeric(raw['price'], errors='coerce').values,
        '小类BSR': pd.to_numeric(raw['rank'], errors='coerce').values, '评分': pd.to_numeric(raw['rating'], errors='coerce').values,
        '家族月销': pd.to_numeric(raw['fam_units'], errors='coerce').values, '上架日期': raw['listed_at'].values,
        '标题': raw['title'].values, '主图500': raw['image_url'].values, '商品链接': raw['link'].values,
        'D8台面材质': raw['台面材质'].values, 'D8台盆材质': raw['台盆材质'].values,
    })
    A['m'] = A['月份'].map(mi)
    A['up'] = pd.to_datetime(A['上架日期'].replace('', None), errors='coerce')
    A['尺寸段'] = raw['尺寸段'].replace('', None).values
    A['品牌键'] = A['品牌'].fillna('').map(lambda s: html.unescape(str(s)).strip().lower())
    A['c'] = pd.to_numeric(raw['units'], errors='coerce').fillna(0).clip(lower=0).values
    A['装'] = np.where(raw['装'].eq('整装').values, '整装', '拆装')
    A['柜体材质'] = raw['柜体材质'].map(lambda v: v if isinstance(v, str) and v else '未知').values
    A['台面类型'] = [top_type(t, s) for t, s in zip(A['D8台面材质'], A['D8台盆材质'])]
    A['元素一'] = raw['元素'].map(elements_from_tag).values
    A['元素集'] = A['元素一'].map(tuple)
    A['主色'] = raw['主色'].map(lambda v: v if isinstance(v, str) and v else '未知').values
    A['形态'] = raw['形态'].map(lambda v: v if isinstance(v, str) and v else '落地式').values
    A['同格中位价'] = A.groupby(['m', A['尺寸段'].fillna('未知'), '装'])['价格'].transform('median')
    A['价比'] = A['价格'] / A['同格中位价']
    A['价格档'] = A['价比'].map(tier)
    A['子体销量'] = pd.to_numeric(raw['child_units'], errors='coerce').values
    LAST = A['m'].max()

    # ---------- 1. 单位：replace 规则 ----------
    up_ = {p: p for p in A['家族键'].unique()}

    def root(x):
        while up_[x] != x:
            up_[x] = up_[up_[x]]
            x = up_[x]
        return x
    kids = {(m, p): set(g['子ASIN']) for (m, p), g in A.groupby(['m', '家族键'])}
    months = sorted(A['m'].unique())
    for a, b in zip(months, months[1:]):
        pa = {p for (m, p) in kids if m == a}
        pb = sorted(p for (m, p) in kids if m == b)
        for X in sorted(pa - set(pb)):  # 旧键下个月消失
            share = {B: len(kids[(a, X)] & kids[(b, B)]) / len(kids[(a, X)]) for B in pb}
            top = max(share.values(), default=0)
            win = [B for B, v in share.items() if v == top]
            if top >= 0.5 and len(win) == 1:
                up_[root(X)] = root(win[0])  # 子体平分到几个新键是拆分，不合并
    A['单位'] = A['家族键'].map(root)
    # 去重：同品牌、共用子体 ≥ 较小一方子体数一半的再并成一个
    ukids = A.groupby('单位')['子ASIN'].agg(set)
    ubr = A.groupby('单位')['品牌键'].agg(lambda s: s[s != ''].mode().iloc[0] if (s != '').any() else '')
    up2 = {u: u for u in ukids.index}

    def root2(x):
        while up2[x] != x:
            up2[x] = up2[up2[x]]
            x = up2[x]
        return x
    for us in A.groupby('子ASIN')['单位'].unique():
        for a, b in itertools.combinations(sorted(us), 2):
            if ubr[a] == ubr[b] and len(ukids[a] & ukids[b]) >= 0.5 * min(len(ukids[a]), len(ukids[b])):
                x, y_ = root2(a), root2(b)
                if x != y_:
                    up2[y_] = x
    A['单位'] = A['单位'].map(root2)

    # ---------- 2. 单位 × 月：家族月销、SPU 月销售额、最好 BSR、是否进分母 ----------
    km = A.groupby(['单位', 'm', '家族键']).agg(fu=('家族月销', 'first'), price=('价格', 'mean'), bsr=('小类BSR', 'min'),
                                               p90=('价格', lambda s: bool((s >= 90).any())))
    km['rev'] = km['fu'] * km['price']
    um = km.groupby(level=[0, 1]).agg(fu=('fu', 'sum'), rev=('rev', 'sum'), bsr=('bsr', 'min'), p90=('p90', 'any'))
    um['ok'] = (um['fu'] >= ENTRY_UNITS) & um['p90']
    um['hit'] = (um['bsr'] <= BSR_LINE) | (um['rev'] >= REV_LINE)
    U = A.groupby('单位').agg(up=('up', 'min'), 品牌键=('品牌键', lambda s: s[s != ''].mode().iloc[0] if (s != '').any() else ''),
                             品牌=('品牌', lambda s: s.dropna().iloc[0] if s.notna().any() else ''))
    U['L'] = U['up'].map(lambda t: t.year * 12 + t.month - 1 if pd.notna(t) else np.nan)
    # 第二轮 WITH_HOLD=1：上架 2024-10 起（含留出段）都进单位表
    U = U[U['L'] >= LEARN0].copy()
    U['L'] = U['L'].astype(int)
    A = A.join(U['L'], on='单位')
    A['月龄'] = A['m'] - A['L'] + 1
    W = A[A['月龄'].between(1, WIN)].copy()
    umw = um.reset_index().join(U['L'], on='单位', how='inner')
    umw['月龄'] = umw['m'] - umw['L'] + 1
    umw = umw[umw['月龄'].between(1, WIN)]
    o = umw.groupby('单位').agg(进分母=('ok', 'any'), 成功=('hit', 'any'), 最好BSR=('bsr', 'min'), 最高销售额=('rev', 'max'), 看到月数=('m', 'size'))
    first_hit = umw[umw['hit']].groupby('单位')['月龄'].min()
    o['首次达线月龄'] = first_hit.reindex(o.index)
    U = U.join(o, how='inner')
    U = U[U['进分母'] & (U['L'] + WIN - 1 <= LAST)].copy()
    U['y'] = U['成功'].astype(int)

    # ---------- 3. 家族特征（只用上架时能知道的、首个在榜月） ----------
    def modev(s, drop=('未知',)):
        s = s[~s.isin(drop)]
        return s.mode().iloc[0] if len(s) else None

    def main_band(gf):
        g2 = gf.dropna(subset=['尺寸段'])
        sv = g2.groupby('尺寸段')['子体销量'].sum(min_count=1)
        if sv.notna().any() and sv.sum() > 0:
            top = sv[sv == sv.max()].index
            if len(top) == 1:
                return top[0]
        n = g2.groupby('尺寸段')['子ASIN'].nunique()
        if not len(n):
            return '未知'
        tie = sorted(n[n == n.max()].index, key=SIZE_ORDER.index)
        return tie[(len(tie) - 1) // 2]
    feat = {}
    for u, g in W.groupby('单位'):
        if u not in U.index:
            continue
        F = g['m'].min()
        gf = g[g['m'] == F]
        tt = gf['台面类型']
        spec = tt[~tt.str.startswith('台面未知') & (tt != '未知')]
        el = sorted({e for t in gf['元素集'] for e in t})
        feat[u] = dict(主尺寸段=[main_band(gf)], 装=[modev(gf['装']) or '拆装'], 柜体材质=[modev(gf['柜体材质']) or '未知'],
                       台面类型=[modev(spec) or modev(tt, ('未知',)) or '未知'], 元素=el or ['未知'], 形态=[modev(gf['形态']) or '落地式'],
                       主色=[modev(gf['主色']) or '未知'],
                       价格档=[tier(np.exp(np.nanmedian(np.log(gf['价比'])))) if gf['价比'].notna().any() else '未知'],
                       _变体=gf['子ASIN'].nunique(), _颜色数=gf['主色'][gf['主色'] != '未知'].nunique(), _中位价=float(g['价格'].median()), _首月=F)
    U = U[U.index.isin(feat)].copy()
    TK = {u: toks(feat[u]) for u in U.index}
    return A, U, feat, TK


def toks(f):
    """新家族 → 新品层特征（开发能定的属性）。"""
    t = [f'尺寸={f["主尺寸段"][0]}', f'档={f["价格档"][0]}', f'台面={f["台面类型"][0]}', f'主色={f["主色"][0]}', f'装={f["装"][0]}', f'形态={f["形态"][0]}']
    t += [f'元素={e}' for e in f['元素'] if e not in ('未知', 'fluted', 'reeded')]
    t += ['颜色≥2'] * (f['_颜色数'] >= 2) + ['子体≥4'] * (f['_变体'] >= 4)
    return [x for x in t if not x.endswith('=未知')]


def newprod(U, TK, T, decay=False):
    """站在 T 的做到概率模型（未校准）。返回 (打分函数, 词表, 模型)。打分函数接受单位 ID 或特征列表。"""
    tr = U[U['L'] + 5 <= T - 1]
    vocab = sorted({t for u in tr.index for t in TK[u] if sum(t in TK[v] for v in tr.index) >= 3})
    X = np.array([[1.0 if v in TK[u] else 0.0 for v in vocab] for u in tr.index])
    y = tr['y'].values
    w = 0.5 ** ((tr['L'].max() - tr['L'].values) / 6.0) if decay else np.ones(len(y))
    m = LogisticRegression(C=0.1, max_iter=5000).fit(X, y, sample_weight=w)

    def sc(us):
        rows = [(TK[u] if not isinstance(u, (list, tuple)) else u) for u in us]
        return m.predict_proba(np.array([[1.0 if v in t else 0.0 for v in vocab] for t in rows]))[:, 1]
    return sc, vocab, m
