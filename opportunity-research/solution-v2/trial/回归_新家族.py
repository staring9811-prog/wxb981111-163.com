"""回归第一版：新家族上架后 6 个月内起没起来，和它的属性、组合、价格位置、品牌力、时间信号有什么关系（做法见 state.json S2-45）。
标签取统一打标表（打标技能版本从同目录 _work/tag/tagging_summary.json 读出并写进报告；2026-10-29 起为 v12.2）。
1. 单位：在 24 个月的"家族键"上沿用 成功率口径_对齐.py 的 replace 规则（旧键下月消失、一半以上子体整体搬到同一个新键 = 同一产品）。
2. 新家族：单位里最早的子体上架在 2024-10 至 2026-03；上架当月为月龄 1，观察期 6 个月（3 个月作早期结果另算）。
   分母：观察期内至少一个月"家族月销 ≥ 60 且有子体价格 ≥ 90"。
   成功：观察期内任一月，单位内最好的子体小类 BSR ≤ 50，或 SPU 月销售额（家族月销 × 导出子体均价）≥ $10 万；程度分 = ln(50 ÷ 窗口内最好 BSR)。
3. 输入（只用上架时能知道的）：属性（尺寸段多选、整装/拆装、柜体材质、台面类型、元素多选、形态、开放式、盆数、主色）、
   价格位置（子体价 ÷ 同月同尺寸段同装中位价，取家族中位数后取对数；低 / 中 / 高三档）、品牌力（上架当月同品牌其他单位数）、变体数、上架季度、
   时间信号（家族所属元素、台面类型、柜体材质、尺寸段在上架前一个月的 wen 原表指标：三档新品成功率、平均新品渗透率、单位 ASIN 贡献 ÷ 平均、份额增长比）。
4. 比较框 = 主尺寸段 × 价格档（2026-10-30 起）：主尺寸段 = 家族首个在榜月里子体最多的尺寸段，并列时按尺寸从小到大排、取中间那个（偶数个取偏小的）。
   重要属性用两把尺（同尺寸段内对 log 价格的单变量 R²；学习段上单变量对"起没起来"的交叉验证提升），尺寸段不参加排名、固定和重要属性两两组合；
   其余两两组合只在重要属性之间，三三只做两两已有提升的；价格档 × 重要属性。
5. 模型：L2 逻辑回归（二元特征不缩放，样本少的格子自动往 0 收），含比较框哑变量；学习段（2024-10 至 2025-06 上架）按上架季度分块交叉验证选强度，
   检验段（2025-07 至 2026-03 上架）评估：AUC、预测前 20% 的成功率是平均的几倍（标准 ≥ 2 倍）；和单指标比；消融（去组合、去时间信号、不加比较框）。
6. 发现表：同一比较框内比"有它 / 对照"，各格的差按 n1·n0/(n1+n0) 加权（同格差，Mantel–Haenszel 式）；学习段、检验段格内能对上的各至少 5 个家族，
   两段同格差同号且都 ≥ 5 个百分点、两段分别拟合的系数也同号才收；其余列"没站住的"。尺寸段、价格档本身不当发现，看分格成功率表。
   回归只说明先后和强弱，原因写成可能的解释。
用法：python3 -I 回归_新家族.py；DATA（输入表）、OUT_DIR（默认 input/data_v2/回归，不入库）、REPORT_MD（默认 solution-v2/回归_新家族_第一版.md）可改。"""
import os, re, html, json, itertools, warnings, numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, log_loss
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
DATA = os.environ.get('DATA', os.path.join(ROOT, 'input/data_v2/统一打标/统一打标_分析用.pkl'))
OUT = os.environ.get('OUT_DIR', os.path.join(ROOT, 'input/data_v2/回归'))
REPORT = os.environ.get('REPORT_MD', os.path.join(ROOT, 'solution-v2/回归_新家族_第一版.md'))
os.makedirs(OUT, exist_ok=True)
_SUM = os.path.join(os.path.dirname(DATA), '_work', 'tag', 'tagging_summary.json')
TAG_VER = re.search(r'v\d+(?:\.\d+)?$', json.load(open(_SUM, encoding='utf-8'))['ruleVersion']).group(0) if os.path.exists(_SUM) else '未知'
WIN, EARLY, BSR_LINE, REV_LINE, MINF = 6, 3, 50, 100000, 5
mi = lambda s: int(str(s)[:4]) * 12 + int(str(s)[5:7]) - 1          # 'YYYY-MM' → 月序号
ms = lambda i: f'{i // 12}-{i % 12 + 1:02d}'
LEARN, TEST = (mi('2024-10'), mi('2025-06')), (mi('2025-07'), mi('2026-03'))
PERIODS = [('2024-10 至 2025-03', mi('2024-10'), mi('2025-03')), ('2025-04 至 09', mi('2025-04'), mi('2025-09')),
           ('2025-10 至 2026-03', mi('2025-10'), mi('2026-03')), ('2026-04 至 09', mi('2026-04'), mi('2026-09'))]
SIZE = [(18, 15, 21), (24, 21, 27), (30, 27, 33), (36, 33, 39), (42, 39, 45), (48, 45, 54), (60, 54, 66)]  # wen 矩阵：±3 寸归段
SIZE_ORDER = [f'{c}″' for c, _, _ in SIZE] + ['72″+']
FRAME = ('尺寸段', '价格档')   # 比较框的两边
ELEM = ['Shaker', 'Fluted', 'Farmhouse', 'Barn Door', 'Glass Door', 'Slatted', 'Rattan', 'Reeded']
COLOR = {'白色': '白', '黑色': '黑', '灰色': '灰', '原木色': '原木', '胡桃木色': '深木', '深咖啡色': '深木', '棕色': '深木',
         '蓝色': '蓝', '藏青色': '蓝', '灰蓝色': '蓝', '绿色': '绿', '灰绿色': '绿'}
UNK = {'信息不足', '待图片核验', '', 'nan', 'None', '<NA>'}

def band(x):
    try: x = float(x)
    except (TypeError, ValueError): return None
    if np.isnan(x): return None
    for c, lo, hi in SIZE:
        if lo <= x < hi: return f'{c}″'
    return '72″+' if x >= 66 else None

def cab(v):
    v = '' if pd.isna(v) else str(v)
    if v in UNK: return '未知'
    if v in ('实木', '实木框架+实木'): return '实木'
    if v.startswith('实木框架'): return '实木框架'
    if v == 'MDF': return 'MDF'
    if '胶合板' in v: return '含胶合板'
    if '刨花板' in v: return '含刨花板'
    return '其他'

def top_type(t, s):
    t = '' if pd.isna(t) else str(t); s = '' if pd.isna(s) else str(s)
    if t == '陶瓷': return '陶瓷一体'
    if t in ('树脂', 'Cultured Marble'): return '树脂一体'
    if t in ('岗石', '石英石', '岩板', '卡拉拉大理石'): return '石材台面'
    if t == '木板': return '木板台面'
    if t == '玻璃': return '玻璃台面'
    if t.startswith('不适用'): return '不含台面'
    if s.startswith('不适用'): return '不含盆'
    return {'玻璃盆': '台面未知·玻璃盆', '陶瓷盆': '台面未知·陶瓷盆', '树脂盆': '台面未知·树脂盆'}.get(s, '未知')

tier = lambda r: '未知' if pd.isna(r) else ('低' if r < 0.85 else ('高' if r > 1.15 else '中'))
pct = lambda x: '—' if x is None or (isinstance(x, float) and np.isnan(x)) else f'{x:.0%}'

# ---------- 0. 读表、行级字段 ----------
A = pd.read_pickle(DATA); A = A[A['纳入浴室柜分析']].copy().reset_index(drop=True)
A['m'] = A['月份'].map(mi); A['up'] = pd.to_datetime(A['上架日期'], errors='coerce')
A['尺寸段'] = A['D9宽(in)'].map(band)
A['品牌键'] = A['品牌'].fillna('').map(lambda s: html.unescape(str(s)).strip().lower())
A['c'] = pd.to_numeric(A['子体月销（家族均分）'], errors='coerce').fillna(0).clip(lower=0)
A['装'] = np.where(A['D2安装方式'].eq('整装'), '整装', '拆装')
# 实木价格复核用了价格，这里用复核前的文字标签，避免用价格解释价格（v12.2 起表里有这一列）
A['柜体材质'] = A.get('D7柜体材质（价格复核前）', A['D7柜体材质']).map(cab)
A['台面类型'] = [top_type(t, s) for t, s in zip(A['D8台面材质'], A['D8台盆材质'])]
A['元素集'] = A['D5元素'].map(lambda v: tuple(x for x in str(v).split('；') if x in ELEM) if pd.notna(v) else ())
A['主色'] = A['D6柜体颜色'].map(lambda v: COLOR.get(str(v), '未知' if (pd.isna(v) or str(v) in UNK) else '其他'))
A['形态'] = A['形态（怎么装）'].fillna('落地式').astype(str)
A['开放式'] = A['柜体结构'].eq('开放式')
A['盆数'] = A['D3盆数'].fillna('单盆').astype(str)
A['同格中位价'] = A.groupby(['m', A['尺寸段'].fillna('未知'), '装'])['价格'].transform('median')
A['价比'] = A['价格'] / A['同格中位价']; A['价格档'] = A['价比'].map(tier)
FIRST, LAST = A['m'].min(), A['m'].max()

# ---------- 1. 单位：replace 规则 ----------
up_ = {p: p for p in A['家族键'].unique()}
def root(x):
    while up_[x] != x: up_[x] = up_[up_[x]]; x = up_[x]
    return x
kids = {(m, p): set(g['子ASIN']) for (m, p), g in A.groupby(['m', '家族键'])}
months = sorted(A['m'].unique()); merges = 0
for a, b in zip(months, months[1:]):
    pa = {p for (m, p) in kids if m == a}; pb = sorted(p for (m, p) in kids if m == b)
    for X in sorted(pa - set(pb)):  # 旧键下个月消失
        share = {B: len(kids[(a, X)] & kids[(b, B)]) / len(kids[(a, X)]) for B in pb}
        top = max(share.values(), default=0); win = [B for B, v in share.items() if v == top]
        if top >= 0.5 and len(win) == 1: up_[root(X)] = root(win[0]); merges += 1   # 子体平分到几个新键是拆分，不合并
A['单位'] = A['家族键'].map(root)
unit_stat = {src: (int(g['家族键'].nunique()), int(g['单位'].nunique())) for src, g in A.groupby('数据来源批次')}

# ---------- 2. 单位 × 月：家族月销、SPU 月销售额、最好 BSR、是否进分母 ----------
km = A.groupby(['单位', 'm', '家族键']).agg(fu=('家族月销', 'first'), price=('价格', 'mean'), bsr=('小类BSR', 'min'), bsr_med=('小类BSR', 'median'), p90=('价格', lambda s: bool((s >= 90).any())))
km['rev'] = km['fu'] * km['price']
um = km.groupby(level=[0, 1]).agg(fu=('fu', 'sum'), rev=('rev', 'sum'), bsr=('bsr', 'min'), bsr_med=('bsr_med', 'min'), p90=('p90', 'any'))
um['ok'] = (um['fu'] >= 60) & um['p90']
um['hit'] = (um['bsr'] <= BSR_LINE) | (um['rev'] >= REV_LINE)
um['hit_med'] = (um['bsr_med'] <= BSR_LINE) | (um['rev'] >= REV_LINE)   # 稳健性：子体排名基本是家族排名在不同时点的读数，子体越多"最好的一次"越容易好看
U = A.groupby('单位').agg(up=('up', 'min'), 品牌键=('品牌键', lambda s: s[s != ''].mode().iloc[0] if (s != '').any() else ''),
                         品牌=('品牌', lambda s: s.dropna().iloc[0] if s.notna().any() else ''))
U['L'] = U['up'].map(lambda t: t.year * 12 + t.month - 1 if pd.notna(t) else np.nan)
U = U[(U['L'] >= LEARN[0]) & (U['L'] <= TEST[1])].copy(); U['L'] = U['L'].astype(int)
A = A.join(U['L'], on='单位'); A['月龄'] = A['m'] - A['L'] + 1
W = A[A['月龄'].between(1, WIN)].copy()                       # 新单位观察期内的行
umw = um.reset_index().join(U['L'], on='单位', how='inner'); umw['月龄'] = umw['m'] - umw['L'] + 1
umw = umw[umw['月龄'].between(1, WIN)]
o = umw.groupby('单位').agg(进分母=('ok', 'any'), 成功=('hit', 'any'), 最好BSR=('bsr', 'min'), 最高销售额=('rev', 'max'), 看到月数=('m', 'size'))
o['早期成功'] = umw[umw['月龄'] <= EARLY].groupby('单位')['hit'].any().reindex(o.index).fillna(False)
o['成功_中位'] = umw.groupby('单位')['hit_med'].any()
first_hit = umw[umw['hit']].groupby('单位')['月龄'].min()
o['首次达线月龄'] = first_hit.reindex(o.index)
U = U.join(o, how='inner')
U = U[U['进分母'] & (U['L'] + WIN - 1 <= LAST)].copy()
U['段'] = np.where(U['L'] <= LEARN[1], '学习', '检验')
U['y'] = U['成功'].astype(int); U['y_med'] = U['成功_中位'].astype(int)
U['程度分'] = np.log(BSR_LINE / U['最好BSR'])

# ---------- 3. 家族特征（只用上架时能知道的） ----------
def modev(s, drop=('未知',)):
    s = s[~s.isin(drop)]; return s.mode().iloc[0] if len(s) else None
def main_band(gf):
    """主尺寸段：首个在榜月里子体最多的尺寸段；并列时按尺寸从小到大排，取中间那个（偶数个取偏小的）。"""
    n = gf.dropna(subset=['尺寸段']).groupby('尺寸段')['子ASIN'].nunique()
    if not len(n): return '未知'
    tie = sorted(n[n == n.max()].index, key=SIZE_ORDER.index)
    return tie[(len(tie) - 1) // 2]
feat = {}
for u, g in W.groupby('单位'):
    if u not in U.index: continue
    F = g['m'].min(); gf = g[g['m'] == F]
    tt = g['台面类型']; spec = tt[~tt.str.startswith('台面未知') & (tt != '未知')]
    el = sorted({e for t in g['元素集'] for e in t})
    feat[u] = dict(尺寸段=sorted(gf['尺寸段'].dropna().unique()) or ['未知'], 主尺寸段=[main_band(gf)], 装=[modev(g['装']) or '拆装'], 柜体材质=[modev(g['柜体材质']) or '未知'],
                   台面类型=[modev(spec) or modev(tt, ('未知',)) or '未知'], 元素=el or ['未知'], 形态=[modev(g['形态']) or '落地式'],
                   开放式=['是' if g['开放式'].any() else '否'], 盆数=['双盆' if gf['盆数'].eq('双盆').any() else (modev(gf['盆数']) or '单盆')],
                   主色=[modev(gf['主色']) or '未知'], 价格档=[tier(np.exp(np.nanmedian(np.log(gf['价比'])))) if gf['价比'].notna().any() else '未知'],
                   _价位=float(np.nanmedian(np.log(gf['价比']))) if gf['价比'].notna().any() else np.nan, _变体=gf['子ASIN'].nunique(),
                   _颜色数=gf['主色'][gf['主色'] != '未知'].nunique(), _中位价=float(g['价格'].median()), _首月=F)
U = U[U.index.isin(feat)].copy()
for u, f in feat.items():
    if u in U.index:
        for k in ('_价位', '_变体', '_颜色数', '_中位价', '_首月'): U.at[u, k] = f[k]
U['主尺寸段'] = [feat[u]['主尺寸段'][0] for u in U.index]
U['比较框'] = [f"{feat[u]['主尺寸段'][0]}·{feat[u]['价格档'][0]}" for u in U.index]
U['季度'] = U['L'].map(lambda L: f'Q{L % 12 // 3 + 1}')
bm = A.groupby(['m', '品牌键'])['单位'].agg(lambda s: set(s))
def brand_n(u):
    b, L = U.at[u, '品牌键'], U.at[u, 'L']
    if not b: return np.nan
    return len(bm.get((L, b), set()) - {u})
U['_品牌力'] = [brand_n(u) for u in U.index]
U['新品牌'] = U['_品牌力'].eq(0)

# ---------- 4. 时间信号：wen 原表指标，按候选（维度 × 取值）逐月算，取上架前一个月 ----------
tot = A.groupby('m').agg(C=('c', 'sum'), N=('c', 'size'))
def cand(col, explode=False):
    X = A[['m', 'c', 'up']].copy(); X['v'] = A[col]
    if explode: X = X.assign(v=X['v'].map(list)).explode('v')
    X = X[X['v'].notna()]; X = X[~X['v'].astype(str).isin(UNK | {'未知'}) & ~X['v'].astype(str).str.startswith('台面未知')]
    sales = X.groupby(['v', 'm'])['c'].sum().unstack(fill_value=0).reindex(columns=months, fill_value=0)
    share = sales / tot['C'].reindex(months).values
    rec = {}
    for (v, t), g in X.groupby(['v', 'm']):
        if len(g) < 5: continue
        end = pd.Period(ms(t), 'M').end_time.normalize(); r = {}
        for k in (3, 6, 12):
            new = g['up'] >= end - pd.DateOffset(months=k); cnt = new.mean(); s = g['c'][new].sum() / g['c'].sum() if g['c'].sum() > 0 else np.nan
            r[f'成功率{k}'] = s / cnt if cnt > 0 else np.nan
        vals = [r[f'成功率{k}'] for k in (3, 6, 12) if pd.notna(r[f'成功率{k}'])]
        r['渗透率'] = float(np.mean(vals)) if vals else np.nan
        r['单位贡献比'] = (g['c'].sum() / len(g)) / (tot.at[t, 'C'] / tot.at[t, 'N'])
        i = months.index(t)
        if i >= 5:
            now, before = share.loc[v, months[i - 2:i + 1]].mean(), share.loc[v, months[i - 5:i - 2]].mean()
            r['增长比'] = now / before if before > 0 else np.nan
        rec[(v, t)] = r
    return pd.DataFrame(rec).T
DIMS = {'元素': ('元素集', True), '台面类型': ('台面类型', False), '柜体材质': ('柜体材质', False), '尺寸段': ('尺寸段', False)}
MET = ['成功率3', '成功率6', '成功率12', '渗透率', '单位贡献比', '增长比']
CM = {d: cand(c, e) for d, (c, e) in DIMS.items()}
for d in DIMS:
    for k in MET:
        vals = []
        for u in U.index:
            t = U.at[u, 'L'] - 1; xs = [CM[d][k].get((v, t), np.nan) for v in feat[u][d] if v != '未知'] if k in CM[d] else []
            xs = [x for x in xs if pd.notna(x)]; vals.append(float(np.mean(xs)) if xs else np.nan)
        U[f'信号·{d}·{k}'] = vals
SIG = [f'信号·{d}·{k}' for d in DIMS for k in MET]

# ---------- 5. 设计矩阵 ----------
ATTRS = ['尺寸段', '装', '柜体材质', '台面类型', '元素', '形态', '开放式', '盆数', '主色']
CONT = ['_价位', '_品牌力', '_变体', '_颜色数']
lrn = U['段'].eq('学习'); tst = ~lrn

def tok_main(u, attrs=ATTRS, extras=True):
    t = [f'{a}={v}' for a in attrs for v in feat[u][a] if not (a == '开放式' and v == '否')]
    if extras: t += [f'季度={U.at[u, "季度"]}'] + (['新品牌'] if U.at[u, '新品牌'] else [])
    return t
def tok_combo(u, combos):
    t = []
    for cmb in combos:
        for vs in itertools.product(*[feat[u][a] for a in cmb]):
            if any(v in ('未知', '否') or str(v).startswith('台面未知') for v in vs): continue
            t.append('×'.join(f'{a}={v}' for a, v in zip(cmb, vs)))
    return t
def cont_matrix(cols, ref):
    X = U[cols].astype(float).copy()
    for c in cols:
        if c.startswith('信号'): X[c] = np.log(X[c].clip(0.05, 20))
        elif c in ('_品牌力', '_变体', '_颜色数'): X[c] = np.log1p(X[c])
    med = X[ref].median(); X = X.fillna(med); mu, sd = X[ref].mean(), X[ref].std().replace(0, 1)
    return (X - mu) / sd
def design(main=True, combos=(), cont=CONT, sig=(), attrs=ATTRS, minsup=3, extras=True, cells=False):
    toks = {u: (tok_main(u, attrs, extras) if main else []) + ([f'比较框={U.at[u, "比较框"]}'] if cells else []) + tok_combo(u, combos) for u in U.index}
    cnt = pd.Series([t for u in U.index[lrn] for t in set(toks[u])]).value_counts()
    vocab = sorted(cnt[cnt >= minsup].index)
    B = pd.DataFrame(0.0, index=U.index, columns=vocab)
    for u, ts in toks.items():
        for t in set(ts):
            if t in B.columns: B.at[u, t] = 1.0
    parts = [B]
    if cont: parts.append(cont_matrix(list(cont), lrn))
    if sig:
        S = cont_matrix(list(sig), lrn); parts.append(S)
        miss = pd.DataFrame({f'缺·{d}': U[[s for s in sig if s.startswith(f'信号·{d}')]].isna().all(axis=1).astype(float) for d in DIMS if any(s.startswith(f'信号·{d}') for s in sig)})
        parts.append(miss)
    return pd.concat(parts, axis=1)
CS = [0.003, 0.01, 0.03, 0.1, 0.3, 1.0]
FOLDS = U.loc[lrn, 'L'].map(lambda L: (L - LEARN[0]) // 3)
def fit(X, y, C):
    return LogisticRegression(penalty='l2', C=C, solver='lbfgs', max_iter=5000).fit(X, y)
def cv(X, C=None):
    """学习段按上架季度留一块交叉验证，返回（最好平均 log-loss，强度，AUC）。"""
    Xl, yl = X[lrn.values], U.loc[lrn, 'y'].values; best = None
    for c in ([C] if C else CS):
        ll, pr_all, y_all = [], [], []
        for f in sorted(FOLDS.unique()):
            te = (FOLDS == f).values
            if yl[~te].min() == yl[~te].max(): continue
            m = fit(Xl[~te], yl[~te], c); pr = m.predict_proba(Xl[te])[:, 1]
            ll.append(log_loss(yl[te], pr, labels=[0, 1])); pr_all += list(pr); y_all += list(yl[te])
        r = (float(np.mean(ll)), c, roc_auc_score(y_all, pr_all))
        if best is None or r[0] < best[0]: best = r
    return best
base_ll = cv(np.zeros((len(U), 1)), 1e-6)[0]
def lift(y, s, q=0.2, seed=0):
    rng = np.random.default_rng(seed); order = np.lexsort((rng.random(len(s)), -np.asarray(s)))
    k = max(1, int(round(q * len(s)))); return float(np.asarray(y)[order[:k]].mean() / np.mean(y))
def evaluate(X, C):
    m = fit(X[lrn.values], U.loc[lrn, 'y'].values, C); s = m.predict_proba(X[tst.values])[:, 1]; y = U.loc[tst, 'y'].values
    rng = np.random.default_rng(1); aucs, lifts = [], []
    for _ in range(500):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() == y[i].max(): continue
        aucs.append(roc_auc_score(y[i], s[i])); lifts.append(lift(y[i], s[i]))
    return dict(auc=roc_auc_score(y, s), lift=lift(y, s), auc_ci=np.percentile(aucs, [2.5, 97.5]), lift_ci=np.percentile(lifts, [2.5, 97.5]), model=m, score=s)

# ---------- 6. 两把尺：价格 R²、对起没起来的交叉验证提升 ----------
def price_r2(col, explode=False):
    X = A[list(dict.fromkeys(['价格', '尺寸段', col]))].dropna(subset=['价格', '尺寸段']).copy(); X['lp'] = np.log(X['价格'])
    if explode: X[col] = X[col].map(lambda t: '；'.join(t) if t else '未知')
    X[col] = X[col].astype(str); X = X[~X[col].isin(UNK | {'未知'})]
    if col == '尺寸段': return float(1 - ((X.lp - X.groupby(col).lp.transform('mean')) ** 2).sum() / ((X.lp - X.lp.mean()) ** 2).sum()), len(X)
    sse = ((X.lp - X.groupby(['尺寸段', col]).lp.transform('mean')) ** 2).sum(); sst = ((X.lp - X.groupby('尺寸段').lp.transform('mean')) ** 2).sum()
    return float(1 - sse / sst), len(X)
RCOL = {'尺寸段': ('尺寸段', False), '装': ('装', False), '柜体材质': ('柜体材质', False), '台面类型': ('台面类型', False), '元素': ('元素集', True),
        '形态': ('形态', False), '开放式': ('开放式', False), '盆数': ('盆数', False), '主色': ('主色', False)}
ruler = []
for a in ATTRS:
    r2, n = price_r2(*RCOL[a])
    ll, c, auc = cv(design(attrs=[a], cont=(), extras=False).values)
    known = sum(1 for u in U.index[lrn] if feat[u][a] not in (['未知'],))
    ruler.append(dict(属性=a, 价格R2=r2, 有标签行=n, 起没起来提升=(base_ll - ll) / base_ll, 交叉验证AUC=auc, 学习段有标签家族=known))
ruler = pd.DataFrame(ruler)
ruler['价格名次'] = ruler['价格R2'].rank(ascending=False); ruler['成败名次'] = ruler['起没起来提升'].rank(ascending=False)
ruler['综合'] = (ruler['价格名次'] + ruler['成败名次']) / 2
ruler = ruler.sort_values(['综合', '成败名次'])
IMP = [a for a in ruler['属性'] if a != '尺寸段'][:5]   # 尺寸段是比较框的一边，不参加排名，下面固定和重要属性两两组合

# ---------- 7. 组合：重要属性 × 尺寸段（固定）→ 其余两两 → 三三 → 价格档 × 重要属性；都在比较框哑变量之上 ----------
SIGS = [s for s in SIG if U.loc[lrn, s].notna().sum() >= 30]
base_spec = dict(cont=CONT, sig=(), cells=True)
bc = cv(design(**base_spec).values)
SIZEPAIRS = [(a, '尺寸段') for a in IMP]
size_res = pd.DataFrame([dict(组合=f'{p[0]} × 尺寸段', 元=p, 提升=(bc[0] - cv(design(combos=[p], **base_spec).values)[0]) / bc[0]) for p in SIZEPAIRS])
b0 = cv(design(combos=SIZEPAIRS, **base_spec).values)
pairs_res = []
for p in itertools.combinations(IMP, 2):
    r = cv(design(combos=SIZEPAIRS + [p], **base_spec).values); pairs_res.append(dict(组合=' × '.join(p), 元=p, 提升=(b0[0] - r[0]) / b0[0]))
pairs_res = pd.DataFrame(pairs_res).sort_values('提升', ascending=False)
KEEP2 = [r.元 for r in pairs_res.itertuples() if r.提升 > 0]
b2 = cv(design(combos=SIZEPAIRS + KEEP2, **base_spec).values) if KEEP2 else b0
ORDER = IMP + ['尺寸段']
tri_res = []
for p in KEEP2:
    for c3 in ORDER:
        if c3 in p: continue
        t3 = tuple(sorted(p + (c3,), key=ORDER.index))
        if any(r['元'] == t3 for r in tri_res): continue
        r = cv(design(combos=SIZEPAIRS + KEEP2 + [t3], **base_spec).values); tri_res.append(dict(组合=' × '.join(t3), 元=t3, 提升=(b2[0] - r[0]) / b2[0]))
tri_res = pd.DataFrame(tri_res).sort_values('提升', ascending=False) if tri_res else pd.DataFrame(columns=['组合', '元', '提升'])
KEEP3 = [r.元 for r in tri_res.itertuples() if r.提升 > 0][:3]
b3 = cv(design(combos=SIZEPAIRS + KEEP2 + KEEP3, **base_spec).values) if KEEP3 else b2
ptier = []
for a in IMP:
    r = cv(design(combos=SIZEPAIRS + KEEP2 + KEEP3 + [('价格档', a)], **base_spec).values); ptier.append(dict(组合=f'价格档 × {a}', 元=('价格档', a), 提升=(b3[0] - r[0]) / b3[0]))
ptier = pd.DataFrame(ptier).sort_values('提升', ascending=False)
KEEPP = [r.元 for r in ptier.itertuples() if r.提升 > 0]
COMBOS = SIZEPAIRS + KEEP2 + KEEP3 + KEEPP

# ---------- 8. 模型、单指标、消融 ----------
FULL = '完整（比较框 + 属性 + 组合 + 价格 / 品牌 / 变体 + 时间信号）'
SPECS = {FULL: dict(combos=COMBOS, cont=CONT, sig=SIGS, cells=True),
         '去掉组合': dict(combos=[], cont=CONT, sig=SIGS, cells=True),
         '去掉时间信号': dict(combos=COMBOS, cont=CONT, sig=(), cells=True),
         '只有单个属性 + 价格 / 品牌 / 变体': dict(combos=[], cont=CONT, sig=(), cells=True),
         '只有时间信号': dict(main=False, combos=[], cont=(), sig=SIGS),
         '完整，不加比较框': dict(combos=COMBOS, cont=CONT, sig=SIGS),
         '去掉时间信号、不加比较框': dict(combos=COMBOS, cont=CONT, sig=())}
abl = {}
for name, sp in SPECS.items():
    X = design(**sp); ll, c, auc = cv(X.values); ev = evaluate(X.values, c)
    abl[name] = dict(X=X, C=c, cv_ll=ll, cv_gain=(base_ll - ll) / base_ll, cv_auc=auc, **ev)
XF, CF = abl[FULL]['X'], abl[FULL]['C']
single = []
for col, name in [('_价位', '价格位置（比同格中位价贵多少）'), ('_品牌力', '品牌力（同品牌其他家族数）'), ('_变体', '变体数'), ('_颜色数', '颜色数')] + [(s, s.replace('信号·', '上架前 ')) for s in SIGS]:
    X = cont_matrix([col], lrn).values; m = fit(X[lrn.values], U.loc[lrn, 'y'].values, 1.0); s = m.predict_proba(X[tst.values])[:, 1]; y = U.loc[tst, 'y'].values
    single.append(dict(指标=name, 方向='越高越好' if m.coef_[0][0] > 0 else '越低越好', 检验AUC=roc_auc_score(y, s), 前20倍数=lift(y, s), 有值家族=int(U.loc[tst, col].notna().sum())))
single = pd.DataFrame(single).sort_values('检验AUC', ascending=False)

# ---------- 9. 发现：同一比较框内比，两段同格差同号、都 ≥ 5 个百分点，两段分别拟合的系数也同号才收 ----------
yL, yT = U.loc[lrn, 'y'].values, U.loc[tst, 'y'].values
mL = fit(XF[lrn.values].values, yL, CF); mT = fit(XF[tst.values].values, yT, CF)
def ame(m, X, j, rows):
    X1 = X[rows].copy(); X0 = X1.copy()
    if set(np.unique(X.iloc[:, j])) <= {0.0, 1.0}: X1.iloc[:, j] = 1.0; X0.iloc[:, j] = 0.0
    else: X1.iloc[:, j] = X1.iloc[:, j] + 0.5; X0.iloc[:, j] = X0.iloc[:, j] - 0.5   # 连续特征：±0.5 个标准差
    return float((m.predict_proba(X1.values)[:, 1] - m.predict_proba(X0.values)[:, 1]).mean())
def parse(tok):
    return [tuple(x.split('=', 1)) for x in tok.split('×')]
def has(u, tok):
    if tok == '新品牌': return bool(U.at[u, '新品牌'])
    return all(v in feat[u].get(a, []) if a != '季度' else U.at[u, '季度'] == v for a, v in parse(tok))
def known(u, a):
    return all(v != '未知' and not str(v).startswith('台面未知') for v in feat[u][a])
def ref_group(u, tok):
    """对照组（只用相关属性已知的家族）：单属性 = 同属性已知但取值不同；组合 = 锚定的条件相同、其余属性已知但不全相同。
    组合里有尺寸段 / 价格档时锚在它们上（如"实木 × 30″"的对照是有 30″、材质已知但不是实木的），否则锚在第一个条件上。"""
    if tok == '新品牌': return not U.at[u, '新品牌'] and pd.notna(U.at[u, '_品牌力'])
    p = parse(tok); a0, v0 = p[0]
    if len(p) == 1: return known(u, a0) and v0 not in feat[u][a0] if a0 != '季度' else U.at[u, '季度'] != v0
    anc = [x for x in p if x[0] in FRAME] or p[:1]
    return all(v in feat[u][a] for a, v in anc) and all(known(u, a) for a, v in p if (a, v) not in anc) and not has(u, tok)
# 比较框：主尺寸段或价格档不明的家族不进同格比较（回归里照常）
S = pd.get_dummies(U['比较框'].where(~U['比较框'].str.contains('未知'))).astype(float).values
# 每个候选特征的"有它 / 对照"成员（学习段、检验段），只算一次；打乱对照时只换结果
idx = {u: i for i, u in enumerate(U.index)}; isL = lrn.values
cands, skip = [], {}
for j, col in enumerate(XF.columns):
    if col.startswith('缺·') or ('未知' in col) or col.startswith('比较框='): continue
    if col == '_价位' or ('×' not in col and col.split('=')[0] in FRAME): skip[col] = '比较框本身（尺寸段、价格档、价格位置）不再当发现，见分格成功率表'; continue
    cont = col in CONT or col.startswith('信号')
    if cont:
        v = U[col].astype(float); q1, q2 = v[lrn].quantile([1 / 3, 2 / 3]); inm, refm = (v >= q2).values, (v <= q1).values
        nL, nT = int(v[lrn].notna().sum()), int(v[tst].notna().sum())
    else:
        inm = (XF[col] == 1).values; refm = np.array([ref_group(u, col) for u in U.index]); nL, nT = int((inm & isL).sum()), int((inm & ~isL).sum())
    # 格内能对上的家族：所在比较框里对照组也有家族的"有它"家族数，反过来同理
    cmp = [((inm & s).astype(float) @ S, (refm & s).astype(float) @ S) for s in (isL, ~isL)]
    cmp = [(int(n1[n0 > 0].sum()), int(n0[n1 > 0].sum())) for n1, n0 in cmp]
    if min(min(x) for x in cmp) < MINF: skip[col] = f'同一比较框里能对上的家族不到 {MINF} 个'; continue
    if not cont and '×' not in col and (inm & isL).mean() / isL.mean() > 0.6: skip[col] = '太普遍（学习段 > 60% 的家族都有），是基准'; continue
    sig = (tuple(np.flatnonzero(inm)), tuple(np.flatnonzero(refm)))
    cands.append(dict(j=j, col=col, cont=cont, inm=inm, refm=refm, nL=nL, nT=nT, cmpL=cmp[0], cmpT=cmp[1], sig=sig))
# 成员完全相同的只留最短的写法（如"MDF × Farmhouse"和"MDF × Farmhouse × 拆装"），互为对照的只留小的一边（如双盆 / 单盆）
seen, keep = {}, []
for c in sorted(cands, key=lambda c: (len(c['col']), c['col'])):
    if c['sig'] in seen or (c['sig'][1], c['sig'][0]) in seen:
        skip[c['col']] = f'和"{seen.get(c["sig"]) or seen.get((c["sig"][1], c["sig"][0]))}"是同一批家族，只留那条'; continue
    seen[c['sig']] = c['col']; keep.append(c)
cands = sorted(keep, key=lambda c: c['j'])
IN = np.array([c['inm'] for c in cands], float); REF = np.array([c['refm'] for c in cands], float)
def diffs(y):
    """原始差（不分格）。"""
    yL, yT = np.where(isL, y, 0.0), np.where(~isL, y, 0.0)
    f = lambda M, yy, seg: (M * seg) @ yy / np.maximum((M * seg).sum(1), 1)
    return f(IN, yL, isL) - f(REF, yL, isL), f(IN, yT, ~isL) - f(REF, yT, ~isL)
def mh(y):
    """同格差：每个比较框内"有它 − 对照"的成功率差，按 n1·n0/(n1+n0) 加权平均（Mantel–Haenszel 式，格里两边都有家族才算），学习段、检验段分开。"""
    out = []
    for s in (isL, ~isL):
        Ms, Rs, Sy = IN * s, REF * s, S * y[:, None]
        n1, n0, y1, y0_ = Ms @ S, Rs @ S, Ms @ Sy, Rs @ Sy
        w = np.where((n1 > 0) & (n0 > 0), n1 * n0 / np.maximum(n1 + n0, 1), 0.0)
        out.append((w * (y1 / np.maximum(n1, 1) - y0_ / np.maximum(n0, 1))).sum(1) / w.sum(1))
    return out
def judge(y, fits=True):
    dL, dT = mh(y)
    bL = bT = None
    ok = (np.sign(dL) == np.sign(dT)) & (np.minimum(abs(dL), abs(dT)) >= 0.05)
    if fits:
        bL = fit(XF[isL].values, y[isL], CF).coef_[0]; bT = fit(XF[~isL].values, y[~isL], CF).coef_[0]
        cL, cT = np.array([bL[c['j']] for c in cands]), np.array([bT[c['j']] for c in cands])
        ok &= (np.sign(cL) == np.sign(dL)) & (np.sign(cT) == np.sign(dT))
    return ok, dL, dT, bL, bT
y0 = U['y'].values.astype(float)
OK, DL, DT, BL, BT = judge(y0)
RL, RT = diffs(y0)
DLm, DTm = mh(U['y_med'].values.astype(float)); RLm, RTm = diffs(U['y_med'].values.astype(float))
# 打乱对照：各段、各比较框内把"起没起来"随机打乱（格子之间的成败差别保留），同样的标准会"站住"几条
NPERM = int(os.environ.get('NPERM', 1000)); rng = np.random.default_rng(7); null_n, null_hit = [], np.zeros(len(cands))
strength = np.where(OK, np.minimum(abs(DL), abs(DT)), np.nan)
gkey = (U['段'] + '|' + U['比较框']).values; GRP = [np.flatnonzero(gkey == k) for k in np.unique(gkey)]
for _ in range(NPERM):
    yp = y0.copy()
    for ix in GRP: yp[ix] = rng.permutation(y0[ix])
    ok_p, dl, dt, _, _ = judge(yp)
    null_n.append(int(ok_p.sum())); null_hit += ok_p & (np.minimum(abs(dl), abs(dt)) >= np.nan_to_num(strength, nan=9))
PERM_P = (1 + null_hit) / (1 + NPERM)
# 多重比较：所有候选特征一起做 BH 校正（没站住的按 p = 1 计）
pa = np.where(OK, PERM_P, 1.0); order = np.argsort(pa); m_ = len(pa); qv = np.empty(m_); run = 1.0
for r_, i_ in list(enumerate(order, 1))[::-1]: run = min(run, pa[i_] * m_ / r_); qv[i_] = run
rows = []
for i, c in enumerate(cands):
    j, col, inm, refm = c['j'], c['col'], c['inm'], c['refm']
    aL = ame(mL, XF[isL], j, slice(None)) if c['cont'] else ame(mL, XF[isL], j, (XF[isL][col] == 1).values)
    aT = ame(mT, XF[~isL], j, slice(None)) if c['cont'] else ame(mT, XF[~isL], j, (XF[~isL][col] == 1).values)
    seg = lambda m, s: (U['y'].values[m & s].mean() if (m & s).any() else np.nan, int((m & s).sum()))
    win = U.index[inm & (U['y'].values == 1)]
    rows.append(dict(特征=col, 连续=c['cont'], 学习家族=c['nL'], 检验家族=c['nT'], 格内可比学习=c['cmpL'], 格内可比检验=c['cmpT'], 系数学习=mL.coef_[0][j], 系数检验=mT.coef_[0][j], 分量学习=aL, 分量检验=aT,
                     同格差学习=DL[i], 同格差检验=DT[i], 原始差学习=RL[i], 原始差检验=RT[i], 中位口径同格学习=DLm[i], 中位口径同格检验=DTm[i], 中位口径学习=RLm[i], 中位口径检验=RTm[i],
                     学习=seg(inm, isL) + seg(refm, isL), 检验=seg(inm, ~isL) + seg(refm, ~isL),
                     靠排名=int((U.loc[win, '最好BSR'] <= BSR_LINE).sum()), 靠销售额=int((U.loc[win, '最高销售额'] >= REV_LINE).sum()), 起来=len(win), 站住=bool(OK[i]), 打乱p=PERM_P[i] if OK[i] else np.nan, q=qv[i]))
FD = pd.DataFrame(rows)
FD['强度'] = FD[['同格差学习', '同格差检验']].abs().min(axis=1)
STAND = FD[FD['站住']].sort_values(['打乱p', '强度'], ascending=[True, False])
FALL = FD[~FD['站住']].assign(最大=lambda d: d[['同格差学习', '同格差检验']].abs().max(axis=1)).sort_values('最大', ascending=False)
NULL = (float(np.mean(null_n)), float(np.percentile(null_n, 95)))

# ---------- 10. 长时间之后的变化、例子 ----------
def row_mask(tok):
    m = pd.Series(True, index=A.index)
    for a, v in parse(tok):
        if a == '元素': m &= A['元素集'].map(lambda t: v in t)
        elif a == '开放式': m &= A['开放式'] if v == '是' else ~A['开放式']
        elif a in ('季度',): return None
        else: m &= A[a].astype(str).eq(v)
    return m
def traj(tok):
    if tok == '新品牌' or tok.startswith('季度') or tok in CONT or tok.startswith('信号'): return None
    rm = row_mask(tok)
    if rm is None: return None
    out = []
    for name, a, b in PERIODS:
        pm = A['m'].between(a, b); sh = A.loc[pm & rm, 'c'].sum() / A.loc[pm, 'c'].sum()
        newu = [u for u in U.index if a <= U.at[u, 'L'] <= b and has(u, tok)]
        out.append(dict(期=name, 份额=sh, 新家族=len(newu), 起来=int(U.loc[newu, 'y'].sum()) if newu else 0, 中位价=A.loc[pm & rm, '价格'].median()))
    return out
def traj_txt(t):
    if not t: return '—'
    s = '销量份额 ' + ' → '.join(pct(x['份额']) for x in t)
    s += '；新家族（其中起来的）' + ' → '.join(f"{x['新家族']}（{x['起来']}）" if x['新家族'] else '0' for x in t[:3]) + ' → 观察中'
    s += '；中位价 ' + ' → '.join('—' if pd.isna(x['中位价']) else f"${x['中位价']:.0f}" for x in t)
    return s
def cohort_txt(col):
    v = U[col].astype(float); q1, q2 = v[lrn].quantile([1 / 3, 2 / 3]); out = []
    for name, a, b in PERIODS[:3]:
        c = U[U['L'].between(a, b)]; hi, lo = c[v.reindex(c.index) >= q2], c[v.reindex(c.index) <= q1]
        out.append(f"{name} 上架的：高的三分之一起来 {pct(hi['y'].mean()) if len(hi) else '—'}（{len(hi)} 家），低的三分之一 {pct(lo['y'].mean()) if len(lo) else '—'}（{len(lo)} 家）")
    return '；'.join(out)
def examples(tok, k=2):
    if tok in CONT or tok.startswith('信号'):
        v = U[tok].astype(float); us = U[v >= v[lrn].quantile(2 / 3)]
    else: us = U[[has(u, tok) for u in U.index]]
    want = [v for a, v in parse(tok) if a == '尺寸段'] if not (tok in CONT or tok.startswith('信号') or tok == '新品牌') else []
    good = us[us['y'] == 1].sort_values('最好BSR').head(k); bad = us[us['y'] == 0].sort_values('最高销售额', ascending=False).head(1)
    def one(u):
        g = W[(W['单位'] == u)]; g2 = g[g['尺寸段'].isin(want)] if want and g['尺寸段'].isin(want).any() else g
        r = g2.loc[g2['小类BSR'].idxmin()] if g2['小类BSR'].notna().any() else g2.iloc[0]
        return (f"{U.at[u, '品牌']} {r['子ASIN']}（{ms(U.at[u, 'L'])} 上架，尺寸 {'/'.join(feat[u]['尺寸段'])}，中位价 ${U.at[u, '_中位价']:.0f}，"
                f"最好排名 {int(U.at[u, '最好BSR']) if pd.notna(U.at[u, '最好BSR']) else '—'}，最高月销售额 ${U.at[u, '最高销售额'] / 1000:.0f}k）")
    return '；'.join(one(u) for u in good.index) or '—', ('；反例：' + one(bad.index[0])) if len(bad) else ''

NAME = {'_价位': '价格位置', '_品牌力': '品牌力', '_变体': '变体数', '_颜色数': '颜色数'}
DEF = {'_价位': '首次进榜那个月，子体价格 ÷ 同月、同尺寸段、同整装/拆装的中位价，取家族中位数',
       '_品牌力': '上架当月，同品牌在榜（家族月销 ≥ 50 / 60）的其他家族数',
       '_变体': '首次进榜那个月，家族里的子体数（尺寸 × 颜色等）', '_颜色数': '首次进榜那个月，家族里不同柜体颜色的个数'}
AN = {'尺寸段': '家族首次进榜时有 {v} 的变体', '装': '{v}', '柜体材质': '柜体材质标为 {v}', '台面类型': '台面类型为{v}', '元素': '文字写了 {v}',
      '形态': '形态为{v}', '开放式': '文字写了开放层板', '盆数': '家族首次进榜时有{v}的变体', '主色': '主色为{v}', '价格档': '价格在同格{v}档（同月、同尺寸段、同整装/拆装的中位价 ±15% 为中档）', '季度': '在 {v} 上架'}
def fname(c):
    if c in NAME: return NAME[c]
    if c.startswith('信号'): _, d, k = c.split('·'); return f'上架前一月：所属{d}的{k}'
    return ' × '.join(f'{a}={v}' for a, v in parse(c)) if c != '新品牌' else '新品牌'
def define(c):
    if c in DEF: return DEF[c]
    if c.startswith('信号'):
        _, d, k = c.split('·'); kk = {'成功率3': '三个月新品成功率', '成功率6': '半年新品成功率', '成功率12': '一年新品成功率', '渗透率': '平均新品渗透率', '单位贡献比': '单位 ASIN 贡献 ÷ 品类平均', '增长比': '近 3 个月份额 ÷ 前 3 个月份额'}[k]
        return f'上架前一个月，家族所属{d}（取值的平均）的{kk}（wen 原表公式）'
    if c == '新品牌': return '上架当月同品牌没有别的家族在榜'
    return '，且'.join(AN.get(a, '{v}').format(v=v) for a, v in parse(c))
def metric_txt(r):
    L, T = r['学习'], r['检验']
    head = f"**{define(r['特征'])}**。"
    gap = (f"同格差（同一比较框里比）：学习 {r['同格差学习'] * 100:+.0f}、检验 {r['同格差检验'] * 100:+.0f} 个百分点"
           f"（格内能对上的有 / 对照：学习 {r['格内可比学习'][0]} / {r['格内可比学习'][1]} 家，检验 {r['格内可比检验'][0]} / {r['格内可比检验'][1]} 家）；"
           f"原始差（不分格）：学习 {r['原始差学习'] * 100:+.0f}、检验 {r['原始差检验'] * 100:+.0f}。")
    if r['连续']:
        v = U[r['特征']].astype(float); q1, q2 = v[lrn].quantile([1 / 3, 2 / 3])
        fmt = (lambda x: f'{np.exp(x) - 1:+.0%}') if r['特征'] == '_价位' else ((lambda x: f'{x:.0f}') if r['特征'] in ('_变体', '_颜色数', '_品牌力') else (lambda x: f'{x:.2f}'))
        head += f"高的三分之一指 ≥ {fmt(q2)}，低的三分之一指 ≤ {fmt(q1)}，格内比高的和低的。"
        body = f"不分格时：学习段高的起来 {pct(L[0])}（{L[1]} 家），低的 {pct(L[2])}（{L[3]} 家）；检验段 {pct(T[0])}（{T[1]}）对 {pct(T[2])}（{T[3]}）"
    else: body = f"不分格时：学习段有这条的 {L[1]} 家起来 {pct(L[0])}，对照 {L[3]} 家 {pct(L[2])}；检验段 {T[1]} 家 {pct(T[0])}，对照 {T[3]} 家 {pct(T[2])}"
    return head + gap + body + f"。起来的 {r['起来']} 家里，靠排名进前 50 的 {r['靠排名']}、靠月销售额 ≥ $10 万的 {r['靠销售额']}"
EXPLAIN = {   # 特征 → 可能的解释（看过结果后写的定性解释；具体数字见同一行的指标、变化两列，避免写死过期）
    '盆数=双盆': '可能的解释：双盆多是 48–72″ 大柜，大尺寸单价高、月销不多就能过 $10 万销售额线（不分格时的差距有一部分是这个原因）；同一尺寸、价位档里比，双盆仍比单盆起来得多，'
                 '可能是大尺寸买家（主卫、两人用）本来就要双盆，大柜做单盆的需求小。限制：学习段格内能对上的双盆家族很少（见指标一列），起来的家族里靠销售额线的比例比别的条目高',
    '柜体材质=MDF×元素=Farmhouse': '可能的解释：MDF 做的农舍风饰条款价格在主流带，起来的多靠排名；但进来的人越来越多，起来的比例在降，红利在被分掉',
    '_变体': '可能的解释：尺寸、颜色铺得多，能接住更多搜索（不同尺寸是不同的搜索词），家族排名按全部变体合计；也可能是有实力的卖家才铺得多。'
            '还有一个口径原因：家族排名取子体排名里最好的一次，子体越多，读到好排名的机会越多；换成子体排名中位数判（见稳健性），差距仍在，所以不全是这个原因。'
            '限制：变体数是首次进榜那个月的，有的家族是起来以后才补的变体',
    '_颜色数': '和变体数是同一件事的两面（颜色多，变体就多），解释同上；两条高度相关，不要当成两条独立的规律',
    '形态=悬浮式': '可能的解释：同一尺寸、价位档里比，悬浮式起来的也少，所以不只是尺寸、价位不同造成的：悬浮柜要挂墙、改水路，安装门槛高，换旧柜的买家多半仍买落地式；'
                 '悬浮式的中位价这两年在涨（见变化一列），高价款变多',
    '柜体材质=MDF×装=拆装×尺寸段=36″': '可能的解释：36″ 是最大的单盆需求段之一，拆装 MDF 在主流价位，最容易冲件数。限制：校正后不显著；和"MDF × 36″"基本是同一批家族',
    '柜体材质=实木框架×台面类型=石材台面': '可能的解释：实木框架配石材台面，是"加料涨价"那条路（你说的 Shaker mix 实木款属于这类）：价格高，起来的多靠月销售额线，贵了也卖得动。限制：家族很少；多重比较校正后不显著',
    '柜体材质=MDF×元素=Barn Door': '可能的解释：谷仓门是农舍风的典型做法，MDF 谷仓门款价格在主流带。限制：换成子体排名中位数判不稳；校正后不显著',
    '柜体材质=MDF×尺寸段=36″': '和"MDF × 拆装 × 36″"几乎是同一批家族，见那条',
    '台面类型=树脂一体': '可能的解释：树脂一体盆台（含 SMC、亚克力、Cultured Marble）轻、不易碎、好运输；同一尺寸、价位档里比也比别的台面起来得多，所以不只是因为便宜',
    '台面类型=树脂一体×尺寸段=36″': '可能的解释：树脂一体盆台在 36″ 的表现：台面越大，轻、不易碎、运输破损少的好处越明显；同一价位档里比也高。'
                                  '限制：有这条的家族很少（见指标一列）；和"树脂一体"单条、其他尺寸的几条是重叠的家族，不要当成几条独立的规律',
    '台面类型=树脂一体×尺寸段=24″': '可能的解释：树脂一体盆台轻、不易碎、好运输，小尺寸也能做到主流价位；同一价位档里比也高。'
                                  '限制：有这条的家族很少（见指标一列）；和"树脂一体"单条、其他尺寸的几条是重叠的家族，不要当成几条独立的规律',
    '台面类型=树脂一体×尺寸段=30″': '可能的解释：同"树脂一体 × 24″ / 36″"，树脂一体盆台轻、不易碎、好运输；同一价位档里比也高。'
                                  '限制：有这条的家族很少（见指标一列）；和"树脂一体"单条、其他尺寸的几条是重叠的家族，不要当成几条独立的规律',
    '台面类型=陶瓷一体×尺寸段=24″': '可能的解释：24″ 的陶瓷一体盆台是主流做法，新家族多（见变化一列），拼价格和件数，每个新家族起来的机会小；同一价位档里比也低。'
                                  '注意：不是说 24″ 陶瓷一体卖得不好，而是新进来的家族里起来的比例低于同尺寸其他台面。限制：一部分陶瓷一体是"盆材已知、没写台面"按一体盆推断的',
    '台面类型=陶瓷一体×尺寸段=36″': '可能的解释：同"陶瓷一体 × 24″"：36″ 也是单盆主力尺寸，陶瓷一体新家族多（见变化一列），挤进来的人多，每个新家族起来的机会小；同一价位档里比也低。'
                                  '限制：一部分陶瓷一体是按一体盆推断的；和 24″ 那条有重叠的家族（一个家族可以同时有 24″ 和 36″）',
    '新品牌': '可能的解释：上架当月同品牌没有别的家族在榜的，多是集中资源推一个款的卖家，广告、运营都压在这一个家族上；老品牌同时铺很多家族，每个家族分到的流量少。'
              '限制：只数得到在榜（月销 ≥ 50 / 60）的父体，"新品牌"可能有不在榜的老款',
    '主色=黑': '可能的解释：黑色的销量份额在涨，但涨的多是已在榜的老款（新家族数没跟着涨，见变化一列），新进来的黑色家族要和老款抢；同一尺寸、价位档里比也低。限制：有这条的家族不多',
    '台面类型=木板台面': '可能的解释：木板台面（含台上盆配木台面）多是农舍、复古风，同一尺寸、价位档里比也高；木板台面的份额和新家族这两年在减少（见变化一列），做的人少、竞争小。'
                       '限制：换成子体排名中位数判，差距明显变小（见稳健性）；检验段家族很少',
    '价格档=低×盆数=单盆': '可能的解释：对照是同格低档里不带盆（只卖柜体）或双盆的款：只卖柜体的便宜、好运输，买家自配台面，起来的多；所以这条更像"低档里只卖柜体的比带盆的好起"，不是单盆本身不好。'
                         '限制：对照组很小（见指标一列）；学习段的对照几乎全是无盆款、检验段多是双盆款，两段比的不完全是同一回事',
    '元素=Barn Door': '可能的解释：谷仓门（滑门）是农舍风的典型做法，看得见、好区分；对照是写了其他元素的家族，同一尺寸、价位档里比也高。'
                    '限制：元素文字标签只覆盖少数家族；换成子体排名中位数判方向反了（见稳健性），不稳',
    '台面类型=陶瓷一体': '可能的解释：陶瓷一体盆台是主流，份额一直在涨、新家族也最多（见变化一列），挤进来的人多，每个新家族起来的机会就小；中位价多年不变，拼的是价格和件数。'
                       '注意：这不是说陶瓷一体卖得不好，而是新进来的家族里起来的比例低于其他台面类型。限制：v12.2 起"盆材已知、没写台面"的按一体盆推断，陶瓷一体里有一部分是推断出来的；校正后不显著',
    '信号·元素·成功率3': '可能的解释：和"红利被分掉"一致：上架前一个月这个元素的三个月新品成功率越高，说明它正热、跟进的人扎堆，后进来的反而起来得少。'
                                 '如果这条站住，意味着"新品成功率高就去做"要看进场时机，数字已经很高时再进可能晚了。限制：元素只有少数家族有文字标签，格内能对上的家族很少（见指标一列）；换成子体排名中位数判，差距变小',
    '信号·台面类型·成功率12': '可能的解释：同上，某种台面的一年新品成功率高，说明它正被大量新品验证、跟进者多，后来者起来的比例反而低。限制：不分格时检验段差距小（见原始差），同一尺寸、价位档里比两段才一致',
    '元素=Fluted×尺寸段=30″': '可能的解释：fluted 在 30″ 的份额在涨，跟进的新家族很多，和 2026 年案例模拟里"窗口在关"一致。限制：对照组很小，校正后不显著',
    '_品牌力': '可能的解释：老品牌有现成的评论、广告预算和运营经验；但大品牌同时铺很多家族，每个家族分到的流量也少。限制：只数得到在榜（月销 ≥ 50 / 60）的父体',
}

def finding_rows(D):
    out = []
    for _, r in D.iterrows():
        c = r['特征']; ex, bad = examples(c)
        change = cohort_txt(c) if r['连续'] else traj_txt(traj(c))
        rob = f"稳健性：换成“子体排名中位数 ≤ 50”判成败，同格差为学习 {r['中位口径同格学习'] * 100:+.0f}、检验 {r['中位口径同格检验'] * 100:+.0f} 个百分点"
        out.append(f"| {fname(c)} | {metric_txt(r)} | {change} | {ex}{bad} | "
                   f"扣掉其他因素（含比较框）后（回归分量）：学习 {r['分量学习'] * 100:+.1f}、检验 {r['分量检验'] * 100:+.1f}（系数 {r['系数学习']:+.2f} / {r['系数检验']:+.2f}；家族 {r['学习家族']} / {r['检验家族']}）；"
                   f"格内打乱对照里同样强的概率 {r['打乱p']:.3f}，多重比较校正后 q = {r['q']:.2f}（{'较可信' if r['q'] < 0.2 else '有迹象，校正后不显著'}） | "
                   f"{EXPLAIN.get(c, '可能的解释：待补')}。{rob} |")
    return out

# ---------- 11. 描述表：实木类 × 尺寸段 × 装；品牌力分档 ----------
desc = []
for (sz, zh), g in A[A['柜体材质'].isin(['实木', '实木框架', 'MDF'])].groupby(['尺寸段', '装']):
    mdf = g[g['柜体材质'] == 'MDF']['价格'].median()
    for mat in ('实木', '实木框架'):
        mk = g[g['柜体材质'] == mat]
        nu = [u for u in U.index if sz in feat[u]['尺寸段'] and feat[u]['装'] == [zh] and feat[u]['柜体材质'] == [mat]]
        nm = [u for u in U.index if sz in feat[u]['尺寸段'] and feat[u]['装'] == [zh] and feat[u]['柜体材质'] == ['MDF']]
        if len(mk) < 20 or len(nu) < 3: continue
        desc.append(dict(尺寸段=sz, 装=zh, 材质=mat, 市场中位价=mk['价格'].median(), MDF中位价=mdf, 贵多少=mk['价格'].median() / mdf - 1,
                         新家族=len(nu), 起来=int(U.loc[nu, 'y'].sum()), MDF新家族=len(nm), MDF起来=int(U.loc[nm, 'y'].sum())))
desc = pd.DataFrame(desc)
U['品牌档'] = pd.cut(U['_品牌力'], [-1, 0, 3, 9, 1e9], labels=['0（新品牌）', '1–3', '4–9', '10 以上'])
bt = U.groupby(['品牌档', '段'], observed=False)['y'].agg(['size', 'mean']).unstack()

# ---------- 12. 核对：用旧口径（6–9 月表、3 个月观察期）比 2026-06、07 上架的 ----------
old = os.path.join(os.environ.get('TRIAL_DUMP', ''), 'success_window3_replace_all_parent.json')
chk_old = json.load(open(old, encoding='utf-8'))['rate'] if os.environ.get('TRIAL_DUMP') and os.path.exists(old) else None
um2 = um.reset_index(); cu = A.groupby('单位')['up'].min().map(lambda t: t.year * 12 + t.month - 1 if pd.notna(t) else np.nan)
um2['L'] = um2['单位'].map(cu); um2['月龄'] = um2['m'] - um2['L'] + 1
c6 = um2[um2['L'].between(mi('2026-06'), mi('2026-07')) & um2['月龄'].between(1, 3)].groupby('单位').agg(ok=('ok', 'any'), hit=('hit', 'any'))
c6 = c6[c6['ok']]; chk = dict(n=int(len(c6)), k=int(c6['hit'].sum()))

# ---------- 输出 ----------
# 每个单位的属性一并存下，供窗口期、成功线口径等后续分析用（多选属性用 / 连接）
for a in ('尺寸段', '装', '柜体材质', '台面类型', '元素', '形态', '开放式', '盆数', '主色', '价格档'):
    U['属性·' + a] = [ '/'.join(feat[u][a]) for u in U.index]
U.drop(columns=[c for c in U.columns if c.startswith('_首月')]).to_pickle(os.path.join(OUT, '新家族_特征与结果.pkl'))
json.dump({'merges': merges, 'units': unit_stat, 'imp': IMP, 'frame': {f'{a}|{b}': [int(r['size']), int(r['sum'])] for (a, b), r in U.groupby(['比较框', '段'])['y'].agg(['size', 'sum']).iterrows()},
           'size_pairs': size_res[['组合', '提升']].to_dict('records'), 'pairs': pairs_res[['组合', '提升']].to_dict('records'), 'triples': tri_res[['组合', '提升']].to_dict('records') if len(tri_res) else [],
           'ptier': ptier[['组合', '提升']].to_dict('records'), 'ablation': {k: {x: (float(v[x]) if np.isscalar(v[x]) else [float(z) for z in v[x]]) for x in ('C', 'cv_ll', 'cv_gain', 'cv_auc', 'auc', 'lift', 'auc_ci', 'lift_ci')} for k, v in abl.items()},
           'check_2026_06_07_w3': chk, 'check_old': chk_old}, open(os.path.join(OUT, '回归_摘要.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
FD.to_pickle(os.path.join(OUT, '发现_全部.pkl'))

nL, nT = int(lrn.sum()), int(tst.sum()); kL, kT = int(U.loc[lrn, 'y'].sum()), int(U.loc[tst, 'y'].sum())
F = abl[FULL]
# 分格成功率：主尺寸段 × 价格档，学习 / 检验各给 家族数 / 起来的（比例）
TIER = pd.Series({u: feat[u]['价格档'][0] for u in U.index})
def cell_txt(m):
    out = []
    for sg, s in (('学', lrn), ('检', tst)):
        n, k = int((m & s).sum()), int(U.loc[m & s, 'y'].sum())
        out.append(f'{sg} {n}/{k}（{k / n:.0%}）' if n else f'{sg} 0')
    return ' · '.join(out)
SZS = [s for s in SIZE_ORDER + ['未知'] if U['主尺寸段'].eq(s).any()]; TRS = [t for t in ('低', '中', '高', '未知') if TIER.eq(t).any()]
FRAME_TAB = ['| 主尺寸段 | ' + ' | '.join(f'价格{t}档' if t != '未知' else '价格未知' for t in TRS) + ' | 合计 |', '| :--- |' + ' :--- |' * (len(TRS) + 1)]
for s in SZS:
    sm = U['主尺寸段'].eq(s); FRAME_TAB.append(f'| {s} | ' + ' | '.join(cell_txt(sm & TIER.eq(t)) for t in TRS) + f' | {cell_txt(sm)} |')
FRAME_TAB.append('| 合计 | ' + ' | '.join(cell_txt(TIER.eq(t)) for t in TRS) + f' | {cell_txt(U["主尺寸段"].notna())} |')
NUNK = int(U['比较框'].str.contains('未知').sum())
# 限制用的两个数：主尺寸段靠并列规则定的家族；同一子体分在几个新家族单位里
w_ = W[W['单位'].isin(U.index)]; f_ = w_[w_['m'] == w_.groupby('单位')['m'].transform('min')]
nb_ = f_.dropna(subset=['尺寸段']).groupby(['单位', '尺寸段'])['子ASIN'].nunique()
TIE_N = int((nb_.groupby(level=0).apply(lambda s: int((s == s.max()).sum())) > 1).sum())
k_ = w_.groupby('子ASIN')['单位'].nunique(); DUPU = U.index.isin(w_.loc[w_['子ASIN'].isin(k_[k_ > 1].index), '单位'])
BEST = max(abl, key=lambda k: abl[k]['lift'])
L = ['# 回归第一版：新家族上架后 6 个月起没起来', '',
     f'> **标签为打标技能 {TAG_VER}（四路审计修复后全部重打）。元素和柜体结构多数还要看图补，看图后再跑一次。** 每条发现由 wen 逐条判断合不合理。',
     f'> 由 `trial/回归_新家族.py` 生成。数据：统一打标表 {ms(FIRST)} 至 {ms(LAST)}（卖家精灵 15 个月 + 2026 年月度表、v11 表），只用纳入浴室柜分析的行。做法见 state.json S2-45。', '',
     '## 1. 范围与结果定义', '',
     f'- 单位：家族键 {A["家族键"].nunique():,} 个，按 replace 规则（旧键下月消失、一半以上子体整体搬到同一个新键）合并 {merges} 次后 {A["单位"].nunique():,} 个单位。各来源（家族键 → 单位）：' + '，'.join(f'{k} {v[0]} → {v[1]}' for k, v in unit_stat.items()) + '。',
     f'- 新家族：单位里最早的子体上架在 2024-10 至 2026-03；观察期 = 上架当月起 6 个月；分母 = 观察期内至少一个月家族月销 ≥ 60 且有子体价格 ≥ 90。',
     f'- 成功（起来了）：观察期内任一月，单位内最好的子体小类 BSR ≤ 50，或 SPU 月销售额 ≥ $10 万。',
     '', '| 段 | 上架月 | 新家族 | 起来的 | 起来的比例 | 3 个月内起来的 |', '| :--- | :--- | ---: | ---: | ---: | ---: |',
     f'| 学习 | 2024-10 至 2025-06 | {nL} | {kL} | {kL / nL:.0%} | {int(U.loc[lrn, "早期成功"].sum())} |',
     f'| 检验 | 2025-07 至 2026-03 | {nT} | {kT} | {kT / nT:.0%} | {int(U.loc[tst, "早期成功"].sum())} |', '',
     f'核对：用同一口径算 2026-06、07 上架、3 个月观察期的新家族 {chk["n"]} 个、起来 {chk["k"]} 个' + (f'；旧口径（成功率口径_对齐.py，只用 6–9 月表）是 {chk_old["n"]} 个、{chk_old["k"]} 个。' if chk_old else '。'), '',
     '### 比较框（2026-10-30 加）', '',
     'wen 2026-10-30 看组合表时问："这里没有价格、尺寸这个大维度的同比框吗？没有怎么对比？"——上一版的原始差是不分尺寸、价位混在一起比的，尺寸段又被两把尺挤出了重要属性、没进组合，和"比较要在同语境里做（同尺寸、相近价位）"不一致，所以补上。', '',
     '- 比较框 = 主尺寸段 × 价格档。主尺寸段 = 家族首个在榜月里子体最多的尺寸段；几个尺寸段子体一样多时，按尺寸从小到大排、取中间那个（偶数个取偏小的）。'
     '价格档 = 首个在榜月子体价格 ÷ 同月、同尺寸段、同整装/拆装的中位价，取家族中位数：< 0.85 低，> 1.15 高，其余中。',
     '- 为什么：大尺寸单价高，月销不多就能过 $10 万销售额线，在榜的家族也少，进前 50 相对容易；同一尺寸里贵的和便宜的拼法也不同。不同尺寸、价位的家族混在一起比，差距可能只是尺寸或价位不同造成的。',
     '- 怎么用：① 发现表在同一个格子里比"有它 / 对照"，各格的差按 n1·n0/(n1+n0) 加权平均（同格差，见第 4 节）；② 回归里每个格子一个哑变量；③ 尺寸段不再经两把尺筛选，固定和重要属性两两组合；④ 尺寸段、价格档本身不再当发现，看下表。',
     f'- 主尺寸段或价格档不明的家族 {NUNK} 个，不进同格比较（回归里照常）。', '',
     '分格成功率（学 = 学习段，检 = 检验段；家族数 / 起来的（起来的比例））：', '', *FRAME_TAB, '',
     '## 2. 模型表现（标准：检验段预测前 20% 的家族，起来的比例 ≥ 平均的 2 倍）', '',
     '| 模型 | 学习段交叉验证：比"只猜平均"好多少 | 学习段交叉验证 AUC | 检验段 AUC（95% 区间） | 检验段前 20% 是平均的几倍（95% 区间） |', '| :--- | ---: | ---: | :--- | :--- |']
for k, v in abl.items():
    L.append(f'| {k} | {v["cv_gain"]:.1%} | {v["cv_auc"]:.2f} | {v["auc"]:.2f}（{v["auc_ci"][0]:.2f}–{v["auc_ci"][1]:.2f}） | {v["lift"]:.2f} 倍（{v["lift_ci"][0]:.2f}–{v["lift_ci"][1]:.2f}） |')
L += ['', f'- AUC = 随便挑一个起来的和一个没起来的，模型给起来的那个打分更高的概率；0.5 是瞎猜。检验段平均起来的比例 {kT / nT:.0%}。',
      '- 除"只有时间信号"和标了"不加比较框"的两行，模型都含比较框哑变量（每格一个，学习段至少 3 个家族的格子才进）。',
      f'- 比较框哑变量的作用：完整模型 {F["lift"]:.2f} 倍、不加 {abl["完整，不加比较框"]["lift"]:.2f} 倍；去掉时间信号 {abl["去掉时间信号"]["lift"]:.2f} 倍、不加 {abl["去掉时间信号、不加比较框"]["lift"]:.2f} 倍'
      + ('——几乎没变：交叉验证选出的收缩很强，格子哑变量被收到接近 0，比较框主要用在发现表的同格比较上。'
         if max(abs(F['lift'] - abl['完整，不加比较框']['lift']), abs(abl['去掉时间信号']['lift'] - abl['去掉时间信号、不加比较框']['lift'])) < 0.05 else '。'),
      f'- 完整模型对 2 倍标准：前 20% 是平均的 **{F["lift"]:.2f} 倍**，' + ('达标。' if F['lift'] >= 2 else '没达标。') +
      f'最好的是"{BEST}"：{abl[BEST]["lift"]:.2f} 倍（95% 区间 {abl[BEST]["lift_ci"][0]:.2f}–{abl[BEST]["lift_ci"][1]:.2f}），' + ('达标。' if abl[BEST]['lift'] >= 2 else '没达标。'), '',
      '单指标对照（学习段定方向，检验段评估）：', '', '| 指标 | 方向 | 检验段 AUC | 前 20% 是平均的几倍 | 检验段有值家族 |', '| :--- | :--- | ---: | ---: | ---: |']
for r in single.itertuples(): L.append(f'| {r.指标} | {r.方向} | {r.检验AUC:.2f} | {r.前20倍数:.2f} | {r.有值家族} |')
L += ['', '## 3. 重要属性（两把尺）与组合', '', '| 属性 | 同尺寸段内解释价格差异 | 对起没起来的交叉验证提升 | 交叉验证 AUC | 学习段有标签的家族 | 综合名次 |', '| :--- | ---: | ---: | ---: | ---: | ---: |']
for r in ruler.itertuples(): L.append(f'| {r.属性} | {r.价格R2:.0%} | {r.起没起来提升:+.1%} | {r.交叉验证AUC:.2f} | {r.学习段有标签家族} | {r.综合:.1f} |')
L += ['', f'重要属性（综合前 5，尺寸段除外）：{"、".join(IMP)}。尺寸段是比较框的一边，不参加排名，固定和这 {len(IMP)} 个两两组合。', '',
      '组合（学习段交叉验证 log-loss 改善）："× 尺寸段"是在"比较框 + 单个属性 + 价格 / 品牌 / 变体"之上单独加入的，固定保留；其余两两在此之上再加全部"× 尺寸段"后单独加入，三三在保留的两两之上，价格档组合在保留的两两、三三之上；> 0 才保留：', '',
      '| 组合 | 改善 | 保留 |', '| :--- | ---: | :--- |']
for r in size_res.itertuples(): L.append(f'| {r.组合} | {r.提升:+.2%} | 固定保留（比较框） |')
for r in pairs_res.itertuples(): L.append(f'| {r.组合} | {r.提升:+.2%} | {"是" if r.提升 > 0 else "否"} |')
for r in tri_res.itertuples(): L.append(f'| {r.组合}（三三） | {r.提升:+.2%} | {"是" if r.元 in KEEP3 else "否"} |')
for r in ptier.itertuples(): L.append(f'| {r.组合} | {r.提升:+.2%} | {"是" if r.提升 > 0 else "否"} |')
L += ['', '## 4. 发现表（同一比较框里比：学习段、检验段格内能对上的各 ≥ 5 个家族；两段的同格差同号、都 ≥ 5 个百分点；两段分别拟合的回归系数也同号）', '',
      '- "同格差" = 在同一个比较框（主尺寸段 × 价格档）里，有这条的新家族起来的比例 − 对照组起来的比例，各格的差再按 n1·n0/(n1+n0) 加权平均（n1、n0 是格里两边的家族数，只有一边的格子不算；Mantel–Haenszel 式）。"格内能对上的"= 所在格子里另一边也有家族的家族数。',
      '- 对照组只用相关属性已知的家族：单项 = 同属性已知但取值不同；组合 = 锚定的条件相同、其余属性已知但不全相同（组合里有尺寸段 / 价格档时锚在它们上，例如"实木 × 30″"的对照是有 30″、材质已知但不是实木的；否则锚在第一个条件上）；连续项 = 格内比高三分之一和低三分之一（分界按学习段全部家族定）。',
      '- "原始差" = 不分格直接比（上一版的口径），放在旁边对照：两者差得多，说明原来的差距有一部分是尺寸、价位不同带来的。',
      '- 价格位置（连续）是价格档的连续版，和尺寸段、价格档一样只作控制，不当发现。',
      '- "回归分量" = 把比较框、属性、组合、价格、品牌、变体、时间信号都放进去以后，这一项单独让起来的概率高或低几个百分点（连续项按高半个标准差对低半个标准差），学习段、检验段分别拟合。岭回归收得很紧（交叉验证选出的强度），所以分量偏小，看方向和两段是否一致。',
      '- "长时间之后的变化"按半年看：2024-10 至 2025-03 → 2025-04 至 09 → 2025-10 至 2026-03 → 2026-04 至 09；新家族括号里是起来的个数（2026-04 以后上架的观察期没走完，不算）。',
      '- 回归只说明"有它的新家族后来起来得多 / 少"，不说明是它造成的；原因写成可能的解释。',
      f'- 打乱对照：在学习段、检验段的每个比较框里把"起没起来"随机打乱 {NPERM} 次（格子之间的成败差别保留），用同样的标准，平均也会"站住" {NULL[0]:.1f} 条（95% 情况下不超过 {NULL[1]:.0f} 条）；实际站住 {len(STAND)} 条——'
      + ('**比碰巧多，但仍要看每条自己的强度**。' if len(STAND) > NULL[1] else '**站住的条数本身没比碰巧多多少，要看每条自己的强度**。'),
      f'- 所以每条再给两个数：①"格内打乱对照里同样强的概率"（越小越不像碰巧）；② 对全部 {len(FD)} 个候选一起做多重比较校正后的 q 值，q < 0.2 记"较可信"。下表只列①< 0.1 的，其余放在表后存疑。', '',
      '| 发现 | 指标是什么（同格差、原始差、当时的数） | 长时间之后的变化 | 例子 | 回归分量 | 为什么，以及反例 / 限制 |', '| :--- | :--- | :--- | :--- | :--- | :--- |']
S1, S2 = STAND[STAND['打乱p'] < 0.1], STAND[STAND['打乱p'] >= 0.1]
L += finding_rows(S1) if len(S1) else ['| （没有打乱对照里也站得住的发现） | | | | | |']
L += ['', f'站住了、但打乱对照里同样强的概率 ≥ 0.1、先存疑的 {len(S2)} 条：', '', '| 特征 | 同格差 学习 / 检验 | 原始差 学习 / 检验 | 不分格 学习段（有 / 对照） | 不分格 检验段（有 / 对照） | 打乱对照概率 |', '| :--- | :--- | :--- | :--- | :--- | ---: |']
for r in S2.itertuples(): L.append(f'| {fname(r.特征)} | {r.同格差学习 * 100:+.0f} / {r.同格差检验 * 100:+.0f} | {r.原始差学习 * 100:+.0f} / {r.原始差检验 * 100:+.0f} | {pct(r.学习[0])}（{r.学习[1]}）/ {pct(r.学习[2])}（{r.学习[3]}） | {pct(r.检验[0])}（{r.检验[1]}）/ {pct(r.检验[2])}（{r.检验[3]}） | {r.打乱p:.3f} |')
L += ['', '## 5. 没站住的（格内能对上的家族够，但两段同格差方向不一、差不到 5 个百分点或回归方向相反；按两段里较大的同格差排前 15）', '', '| 特征 | 学习段 / 检验段家族 | 同格差 学习 / 检验 | 原始差 学习 / 检验 | 回归系数 学习 / 检验 |', '| :--- | :--- | :--- | :--- | :--- |']
for r in FALL.head(15).itertuples(): L.append(f'| {fname(r.特征)} | {r.学习家族} / {r.检验家族} | {r.同格差学习 * 100:+.0f} / {r.同格差检验 * 100:+.0f} 个百分点 | {r.原始差学习 * 100:+.0f} / {r.原始差检验 * 100:+.0f} | {r.系数学习:+.2f} / {r.系数检验:+.2f} |')
L += ['', '## 6. 描述表', '', '实木类 × 尺寸段 × 整装/拆装（市场价是全部行的中位价；新家族是 2024-10 至 2026-03 上架、观察期走完的）：', '',
      '| 尺寸段 | 装 | 材质 | 市场中位价 | 同格 MDF 中位价 | 贵多少 | 新家族（起来的） | 同格 MDF 新家族（起来的） |', '| :--- | :--- | :--- | ---: | ---: | ---: | :--- | :--- |']
for r in desc.itertuples(): L.append(f'| {r.尺寸段} | {r.装} | {r.材质} | ${r.市场中位价:.0f} | ${r.MDF中位价:.0f} | {r.贵多少:+.0%} | {r.新家族}（{r.起来}，{r.起来 / r.新家族:.0%}） | {r.MDF新家族}（{r.MDF起来}，{(r.MDF起来 / r.MDF新家族) if r.MDF新家族 else float("nan"):.0%}） |')
L += ['', '品牌力分档（上架当月同品牌在榜的其他家族数）：', '', '| 品牌力 | 学习段 家族（起来比例） | 检验段 家族（起来比例） |', '| :--- | :--- | :--- |']
for idx in bt.index:
    L.append(f'| {idx} | {int(bt.loc[idx, ("size", "学习")]) if pd.notna(bt.loc[idx, ("size", "学习")]) else 0}（{pct(bt.loc[idx, ("mean", "学习")])}） | {int(bt.loc[idx, ("size", "检验")]) if pd.notna(bt.loc[idx, ("size", "检验")]) else 0}（{pct(bt.loc[idx, ("mean", "检验")])}） |')
L += ['', '## 7. 限制', '',
      f'- 标签：打标技能 {TAG_VER}。元素文字只覆盖少数家族（Farmhouse 只认看得见的饰条后更少），柜体结构只有文字写明的开放式，台面材质约三分之一未知（其余含一体盆推断）；看图补标后再跑。',
      '- 只看得到进过榜（家族月销 ≥ 50 / 60、价格 ≥ 90）的新家族，没起量的看不到；"起来的比例"是起量新家族里的比例。',
      '- 2026-06 至 09 来自 v11 表，家族键逐月不稳（同一子体 06 → 07 只有 67% 键相同），replace 规则只能并"整体搬家"，可能把一个产品拆成两个单位。',
      '- 子体排名基本是家族排名在不同时间的读数，成功只看单位内最好排名；子体销量是家族销量平均分。',
      '- 新家族数有限（学习 / 检验各几百个、起来的约四分之一），组合格子大多很小，岭回归会把它们往 0 收，所以组合的分量偏保守。',
      '- 比较框按主尺寸段分，多尺寸家族只归到一个格子；格子切得细，很多格里只有一边，同格差只用两边都有家族的格子，"格内能对上的"家族数比原始比较少，看这个数判断稳不稳。',
      f'- 主尺寸段：{TIE_N} / {len(U)} 个家族首个在榜月有几个尺寸段子体一样多，靠并列规则定。2026-10-30 用 v12.2 标签试过把"偶数个取偏小"改成"取偏大"：'
      '19 条两种规则下都站住；新品牌、Barn Door、MDF × Barn Door 和存疑里的两条时间信号（元素渗透率、台面类型单位贡献比）会掉，另外多出 MDF × 拆装 × 36″、实木框架；模型结果不变。这几条要按"对并列规则敏感"看。',
      f'- 同一子体可能分在两个新家族单位里：{int((k_ > 1).sum())} 个子 ASIN、涉及 {int(DUPU.sum())} / {len(U)} 个单位（子体从原家族拆出去单独成家、或家族键变了又不满足"整体搬家"）。'
      f'这批单位起来的比例 {U.loc[DUPU, "y"].mean():.0%}，其他单位 {U.loc[~DUPU, "y"].mean():.0%}，暂时看不出偏向；做"款"层合并时一起处理。', '']
# 和上一版比：上一版 = 加比较框之前的发现文件（跑之前另存的副本）
PREV = os.environ.get('PREV_FD', os.path.join(OUT, '发现_全部_上一版.pkl'))
if os.path.exists(PREV):
    P, FDi = pd.read_pickle(PREV).set_index('特征'), FD.set_index('特征')
    ps, ns_ = set(P.index[P['站住']]), set(STAND['特征'])
    def old_txt(c):
        if c not in P.index: return '不是候选'
        r = P.loc[c]; s = f"原始差 {r['原始差学习'] * 100:+.0f} / {r['原始差检验'] * 100:+.0f}"
        return f"站住（{s}，打乱 p {r['打乱p']:.3f}）" if r['站住'] else f'没站住（{s}）'
    def new_txt(c):
        if c not in FDi.index: return '不是候选：' + skip.get(c, '这一版模型里没有这一项（组合筛选结果变了，或学习段家族不到 3 个）')
        r = FDi.loc[c]; s = f"同格差 {r['同格差学习'] * 100:+.0f} / {r['同格差检验'] * 100:+.0f}，原始差 {r['原始差学习'] * 100:+.0f} / {r['原始差检验'] * 100:+.0f}"
        if r['站住']: return f"站住（{s}，格内打乱 p {r['打乱p']:.3f}）"
        why = ('两段同格差方向相反' if np.sign(r['同格差学习']) != np.sign(r['同格差检验']) else
               '同格差不到 5 个百分点' if min(abs(r['同格差学习']), abs(r['同格差检验'])) < 0.05 else '回归系数方向和差距不一致')
        return f'没站住（{s}；{why}）'
    L += ['## 8. 和上一版比（上一版 = 加比较框之前的结果）', '', f'上一版站住 {len(ps)} 条，这一版 {len(ns_)} 条。差的单位都是百分点，"学习 / 检验"。'
          '个别条目这一版的原始差和上一版不同，是因为对照组改成只用相关属性已知的家族（"台面未知·某盆"不算已知，组合的其余条件也要已知）。', '',
          '| 变化 | 特征 | 上一版 | 这一版 |', '| :--- | :--- | :--- | :--- |']
    for title, group in (('消失', sorted(ps - ns_, key=lambda c: P.at[c, '打乱p'])), ('新出现', [c for c in STAND['特征'] if c not in ps]), ('两版都站住', [c for c in STAND['特征'] if c in ps])):
        for c in group: L.append(f'| {title} | {fname(c)} | {old_txt(c)} | {new_txt(c)} |')
    L.append('')
open(REPORT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L[:40]))
print('站住的发现', len(STAND), '没站住', len(FALL))
