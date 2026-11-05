"""小平台调研：Home Depot / Lowe's / Wayfair 的"单元 × 指标"观察表（不做回测、不下立项结论）。
用法：python3 小平台调研_单元指标.py
  → solution-v2/开发建议/小平台调研_单元×指标_HD_Lowes_Wayfair.md（数字全部来自本次运行）
  → input/data_v2/渠道调研/小平台调研_单元指标_全量.csv、小平台调研_框_全量.csv（不入库）
叫法（wen 2026-11-04）：框 = 尺寸段 × 拆装 × 形态；属性 = 台面材质 / 元素 / 主色 / 柜体材质；取值 = 属性的值；
单元（行）= 框 × 属性取值；指标（列）= 观察的数据维度；模式 = 指标组合成的信号。比较只在同一框、同一渠道内。
数据：
- HD：评论重建（input/data_v2/渠道历史/homedepot/，与 小平台_HD回测小试.py / 跨渠道供给差_HD检验.py 同一读取与 v12.2 规格打标）；
- Lowe's / Wayfair：渠道VP_20261103.xlsx「商品月度明细」，同系列商品共享评论 → 按"10 个月 VP / 非 VP 序列 + 页面累计评论数"相同合成家族，
  家族销量按成员商品页均分（同 Amazon"子体月销（家族均分）"）；标题按 v12.2 规则打标；
- Amazon：input/data_v2/统一打标/统一打标_分析用.pkl（第二轮 / 第九版同一张表），2026-04 至 09。
月销 = VP × 50 + 非 VP × 20；窗口 2026-01 至 10（11 月不完整，不计）。不改 tools/ 与 app/，只 import。"""
import os, sys, re, json, glob, collections, numpy as np, pandas as pd, warnings
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
import 跨渠道供给差_HD检验 as XC   # noqa: E402  （内部 import 小平台_HD回测小试 与 app/pdt/core 的打标规则）
HD, TR = XC.HD, XC.TR
from families import mi, ms   # noqa: E402

MON = [mi(f'2026-{i:02d}') for i in range(1, 11)]
Q = {'1–3': MON[0:3], '4–6': MON[3:6], '7–9': MON[6:9], '10': MON[9:10]}
PRE, REC = MON[0:3], MON[7:10]                 # 前 3 月、近 3 月
AZM = [mi(f'2026-{i:02d}') for i in range(4, 10)]; AZ_PRE, AZ_REC = AZM[:3], AZM[3:]
FR_MIN, U_MIN = 200, 20                        # 框月均 ≥ 200 件、单元月均 ≥ 20 件
ATTRS = ('台面材质', '元素', '主色', '柜体材质')
UNK = set(HD.UNKS) | {'未知'}
PRICE_ABS = XC.PRICE_ABS
RESIN = '树脂一体（Cultured Marble + 树脂）'
AZKEY = lambda att, v: RESIN if att == '台面材质' and str(v) in ('Cultured Marble', '树脂') else str(v)   # 小平台取值 → Amazon 对照键
LN = 0.3                                       # 模式：份额 ln(近 3 ÷ 前 3) ≥ 0.3 算涨、≤ −0.3 算跌（与 机会扫描.py 同）
DIR = 0.2                                      # 三渠道方向：|ln| < 0.2 记 →
LW = "Lowe's"
XLSX = os.path.join(ROOT, 'input/data_v2/渠道VP/浴室柜_2026_渠道VP_20261103.xlsx')
OUTMD = os.path.join(ROOT, 'solution-v2', '开发建议', '小平台调研_单元×指标_HD_Lowes_Wayfair.md')
OUTDIR = os.path.join(ROOT, 'input', 'data_v2', '渠道调研')
OLD_MD = os.path.join(OUTDIR, '小平台调研_上一版_降级视图.md')     # 上一版（2026-11-04 上午）报告重跑时写到这里，不覆盖正式报告
L = []; P = lambda *a: L.extend(a)
pc = lambda x, d=0: '—' if x is None or not np.isfinite(x) else f'{x:.{d}%}'
num = lambda x, d=0: '—' if x is None or not np.isfinite(x) else f'{x:,.{d}f}'
ps = lambda x: '—' if x is None or not np.isfinite(x) else (f'{x:.1%}' if abs(x) < 0.1 else f'{x:.0%}')   # 份额：< 10% 保留一位小数
gx = lambda x: '新出现' if x is None or not np.isfinite(x) else f'{x:.2f}'                                  # 近 3 ÷ 前 3，前 3 为 0 时"新出现"
sg = lambda x, d=2: '—' if x is None or not np.isfinite(x) else f'{x:+.{d}f}'


def wq(x, w, q):
    x, w = np.asarray(x, float), np.asarray(w, float); k = ~np.isnan(x) & (w > 0); x, w = x[k], w[k]
    if not len(x): return np.nan
    o = np.argsort(x); c = np.cumsum(w[o]); return x[o][min(np.searchsorted(c, c[-1] * q), len(x) - 1)]


# ====================================================================== 1. 行级表（每行 = 渠道 × 商品页 × 月，c = 估算销量）
def hd_table():
    A, V, M0, END = XC.hd_rows()
    A = A[A['m'].isin(MON)].copy()
    first = {}; rat = []
    for f in glob.glob(os.path.join(HD.CACHE, 'reviews', '*.json')):
        g = HD.load_json(f) or {}; fk = os.path.basename(f)[:-5]; first[fk] = g.get('首条评论')
        for rid, x in (g.get('reviews') or {}).items():
            d = x.get('d') or ''
            if d[:4].isdigit() and mi(d) in MON: rat.append((rid, x['pid'], mi(d), x['r']))
    R = pd.DataFrame(rat, columns=['rid', 'pid', 'm', 'r']).drop_duplicates('rid')
    RS = R.groupby(['pid', 'm'])['r'].agg(rs='sum', rn='count')
    A = A.join(RS, on=['pid', 'm']); A[['rs', 'rn']] = A[['rs', 'rn']].fillna(0)
    A['首评'] = A['fam'].map(first)
    A['新家族'] = A['首评'].map(lambda d: isinstance(d, str) and d[:4] == '2026')
    A['进入月'] = A['首评'].map(lambda d: mi(d) if isinstance(d, str) and d[:4] == '2026' else np.nan)
    A['装来源'] = A['pid'].map(V['装来源']).fillna('家族补'); A.loc[A['装来源'].eq(''), '装来源'] = '家族补'; A.loc[A['装'] == '未知', '装来源'] = '未知'
    A['形态来源'] = A['pid'].map(V['形态来源']).fillna(''); A.loc[A['形态来源'].eq(''), '形态来源'] = '默认落地式/家族补'
    return A, V


def lw_table(ch):
    """Lowe's / Wayfair：商品页 → 家族（共享评论）→ 家族月销按成员均分 → 标题打标。"""
    d = pd.read_excel(XLSX, '商品月度明细'); d = d[d['渠道'] == ch].copy()
    vc = [f'{ms(m)} VP' for m in MON]; nc = [f'{ms(m)} 非VP' for m in MON]
    d['fam'] = 'F' + pd.factorize(d[vc + nc + ['2026-11（未完整） 合计']].astype(str).agg('|'.join, axis=1) + '#' + d['页面累计评论数'].astype(str))[0].astype(str)
    d['商品ID'] = d['商品ID'].astype(str); d = d.sort_values('排名').drop_duplicates('商品ID')
    rows = []
    for _, r in d.iterrows():
        t = HD.tag_variant(TR, r['标题'], None, None)
        rows.append(dict(pid=r['商品ID'], fam=r['fam'], 入口=r['入口'], 排名=r['排名'], 品牌=r['品牌'], title=r['标题'], 累计=r['页面累计评论数'],
                         y2026=r['1-10月 合计'] + r['2026-11（未完整） 合计'], **t))
    V = pd.DataFrame(rows).set_index('pid')
    # 同家族补（同系列只换颜色尺寸）：装、形态、柜体材质、台面材质
    for col in ('装', '形态'):
        mode = V[V[col] != '未知'].groupby('fam')[col].agg(lambda s: s.mode().iloc[0])
        k = (V[col] == '未知') & V['fam'].isin(mode.index); V.loc[k, col] = V.loc[k, 'fam'].map(mode); V.loc[k, col + '来源'] = '家族补'
    for col in ('D7', 'D8'):
        mode = V[~V[col].isin(UNK)].groupby('fam')[col].agg(lambda s: s.mode().iloc[0])
        k = V[col].isin(UNK) & V['fam'].isin(mode.index); V.loc[k, col] = V.loc[k, 'fam'].map(mode)
    V['装来源'] = V['装来源'].replace('', '未写')
    if ch == "Lowe's":   # wen 2026Q2 文档：Lowe's 100% 整装 → 判断不了的按业务默认整装
        k = V['装'] == '未知'; V.loc[k, '装'] = '整装'; V.loc[k, '装来源'] = '业务默认（wen 文档 100% 整装）'
    V['形态来源'] = V['形态来源'].replace('', '默认落地式')
    V['形态'] = V['形态'].replace({'两用': '落地式'}); V.loc[V['形态'] == '未知', '形态'] = '落地式'
    V['尺寸段'] = V['宽'].map(XC.band); V['柜体材质'] = V['D7'].map(XC.cab)
    V['台面材质'] = V['D8'].map(lambda v: '未知' if v in UNK else v); V['主色'] = V['D6'].map(XC.color)
    V['元素'] = V['D5'].map(lambda v: sorted({HD.ELEM_MAP[x] for x in str(v).split('；') if x in HD.ELEM_MAP}) or ['未知'])
    n = V.groupby('fam').size()
    fr = d.drop_duplicates('fam').set_index('fam')
    out = []
    for fam, r in fr.iterrows():
        first_m = next((m for m in MON if r[f'{ms(m)} 合计'] > 0), None)
        cum, y26 = r['页面累计评论数'], r['1-10月 合计'] + r['2026-11（未完整） 合计']
        new = bool(pd.notna(cum) and cum <= y26 and y26 > 0)
        for m in MON:
            c = (r[f'{ms(m)} VP'] * 50 + r[f'{ms(m)} 非VP'] * 20) / n[fam]
            for p in V.index[V['fam'] == fam]:
                out.append(dict(fam=fam, pid=p, m=m, c=c, 新家族=new, 进入月=first_m if new else np.nan, 累计不一致=bool(pd.notna(cum) and cum < y26)))
    A = pd.DataFrame(out).join(V[['尺寸段', '装', '装来源', '形态', '形态来源', '台面材质', '主色', '柜体材质', '元素', '品牌', 'title']], on='pid')
    A['价格'] = np.nan; A['rs'] = 0.0; A['rn'] = 0.0
    return A, V


def band10(x):
    """尺寸段 revision 10（wen 2026-11-05，与 大词抓取_三平台整理.band10 同）：新增 28″（26–29），30″ 改为 29–33，24″ 为 21–26。"""
    try: x = float(x)
    except (TypeError, ValueError): return None
    if x != x: return None
    for c, lo, hi in ((18, 15, 21), (24, 21, 26), (28, 26, 29), (30, 29, 33), (36, 33, 39), (42, 39, 45), (48, 45, 54), (60, 54, 66)):
        if lo <= x < hi: return f'{c}″'
    return '72″+' if x >= 66 else None


def az_table(v10=False):
    """v10：Amazon 也按 revision 10 分框——尺寸段用 band10，落地式里柜体结构 = 开放式的改为"开放式"形态（上一版视图仍用旧口径）。"""
    B = XC.az_rows()
    if v10:
        A = pd.read_pickle(os.path.join(ROOT, 'input/data_v2/统一打标/统一打标_分析用.pkl')); A = A[A['纳入浴室柜分析']]
        B['尺寸段'] = A['D9宽(in)'].map(band10).values
        B.loc[(B['形态'] == '落地式').values & A['柜体结构'].eq('开放式').values, '形态'] = '开放式'
    B = B[B['m'].isin(AZM)].copy()
    return B


# ---------------------------------------------------------------------- 1b. 新数据：大词商品范围（大词抓取_三平台整理.py 产出的两张表）
BWDIR = os.path.join(ROOT, 'input', 'data_v2', '渠道关键词', '大词')
HD_REV_DIRS = [os.path.join(HD.CACHE, 'reviews'), os.path.join(BWDIR, 'hd', 'reviews')]   # 与 大词抓取_三平台整理.build_hd 同两处评论缓存
NOMON = '无（只有评论总数）'
KBINS = [0, 20, 100, 300, np.inf]              # Wayfair 无月度 listing：按页面评论数分档换算 1–10 月销量
_BW = {}


def bw_raw():
    if not _BW:
        _BW['P'] = pd.read_csv(os.path.join(BWDIR, '三平台_商品表.csv'), dtype={'pid': str, 'fam': str})
        _BW['M'] = pd.read_csv(os.path.join(BWDIR, '三平台_月销表.csv'), dtype={'pid': str, 'fam': str})
    return _BW['P'], _BW['M']


def nomon_mask(p, m):
    """有页面评论、但没有 2026 年逐月评论来源的实体（Wayfair 标"无（只有评论总数）"；Lowe's 两词独有家族评论页没抓到，月度来源为空）。"""
    return (p['月度来源'] == NOMON) | (p['月度来源'].isna() & (p['页面评论数'].fillna(0) > 0) & ~p['fam'].isin(m['fam']))


def static_k(p, fs, low=False):
    """只有评论总数的 listing 都来自两词结果 → 用同样来自搜索结果（来源 = 两词 / 两者）且有月度的 listing，按页面评论数分档算
    1–10 月销量 ÷ 页面评论数（合计口径）。low = 只用"两词独有"的 listing（与无月度的同一来源，但 > 100 条评论的只有 6 个，两档合并），作低估计。"""
    q = p[p['月度来源'].notna() & (p['月度来源'] != NOMON) & (p['页面评论数'] > 0) & p['来源'].isin(['两词'] if low else ['两词', '两者'])].copy()
    q['s'] = q['fam'].map(fs).fillna(0)
    bins = KBINS[:3] + [np.inf] if low else KBINS
    q['档'] = pd.cut(q['页面评论数'], bins, right=True)
    k = q.groupby('档').agg(s=('s', 'sum'), r=('页面评论数', 'sum'), n=('fam', 'size'))
    k['k'] = k['s'] / k['r']
    return k, bins


def bw_table(ch):
    """行 = 商品 × 尺寸段 × 月（m = −1 为只有评论总数的 Wayfair listing：c = 1–10 月估算总量，只进体量 / 份额等静态指标）。"""
    P, M = bw_raw()
    p = P[P['渠道'] == ch].copy(); m = M[M['渠道'] == ch].copy()
    if ch != 'Home Depot': p = p[p['浴室柜'].astype(str).str.lower().ne('false')]
    m = m[m['fam'].isin(p['fam'])]
    assert not p.duplicated(['fam', 'pid']).any()
    cols = ['title', '品牌', '来源', '装来源', '形态来源', '台面材质', '主色', '柜体材质', '元素', '价格', '评分', '页面评论数', '月度来源', '多尺寸段', '有商品页', '选项段']
    m['m'] = m['月'].map(mi); m['c'] = m['销量']
    A = m[['fam', 'pid', 'm', 'c', 'VP', '非VP', '尺寸段', '装', '形态']].join(p.set_index(['fam', 'pid'])[cols], on=['fam', 'pid'])
    K = None; A['c_low'] = A['c']
    if ch != 'Home Depot':
        fs = m.groupby('fam')['c'].sum(); K = {}
        s = p[nomon_mask(p, m)].copy()
        for nm, low, col in (('中', False, 'c'), ('低', True, 'c_low')):
            if low and ch == "Lowe's":   # Lowe's 有月度的都是类目节点商品，没有"两词独有"的校准样本 → 低估计 = 不计（只算有月度）
                K[nm] = None; s[col] = 0.0; continue
            k, bins = static_k(p, fs, low); K[nm] = k
            s[col] = pd.cut(s['页面评论数'], bins, right=True).map(k['k']).astype(float) * s['页面评论数']
        s['尺寸段'] = s['尺寸段'].where(~s['多尺寸段'].astype(str).str.lower().eq('true'), '多尺寸未拆')
        s = s.assign(m=-1, VP=np.nan, 非VP=np.nan)
        A = pd.concat([A, s[['fam', 'pid', 'm', 'c', 'c_low', 'VP', '非VP', '尺寸段', '装', '形态'] + cols]], ignore_index=True)
    A['多尺寸未拆'] = A['尺寸段'].eq('多尺寸未拆'); A['尺寸段'] = A['尺寸段'].where(~A['多尺寸未拆']).astype(object)
    A['装'] = A['装'].fillna('未知'); A['形态'] = A['形态'].fillna('未知')
    A['装来源'] = A['装来源'].fillna('未知'); A['形态来源'] = A['形态来源'].fillna('未知')
    # 同家族补形态（同系列只换颜色 / 尺寸；装已在整理脚本里按家族补过，与上一版口径一致）
    kn = A[A['形态'] != '未知'].groupby(['fam', '形态'])['c'].sum().reset_index().sort_values('c').drop_duplicates('fam', keep='last').set_index('fam')['形态']
    k = (A['形态'] == '未知') & A['fam'].isin(kn.index); A.loc[k, '形态'] = A.loc[k, 'fam'].map(kn); A.loc[k, '形态来源'] = '家族补'
    for c in ('台面材质', '主色', '柜体材质'): A[c] = A[c].fillna('未知')
    A['元素'] = A['元素'].fillna('未知').map(lambda s: str(s).split('、'))
    A['评分'] = A['评分'].where(A['评分'] > 0)   # 页面没有评分时抓到的是 0
    if ch == 'Home Depot':
        # 评论里出现的同家族变体没有列表价：用同家族同尺寸段已知价的中位数，再退到同家族
        A['价格来源'] = np.where(A['价格'].notna(), '商品页 / 列表', '无')
        for keys, tag in ((['fam', '尺寸段'], '同家族同尺寸段补'), (['fam'], '同家族补')):
            fill = A[A['价格'].notna()].drop_duplicates('pid').groupby(keys)['价格'].median().rename('_f')
            A = A.join(fill, on=keys); k = A['价格'].isna() & A['_f'].notna()
            A.loc[k, '价格'] = A.loc[k, '_f']; A.loc[k, '价格来源'] = tag; A = A.drop(columns='_f')
        # 评分 = 窗口内评论星级（同上一版）；新家族 = 家族首条评论在 2026 年
        fam_of = p.set_index('pid')['fam'].to_dict(); first, rat = {}, {}
        for d in HD_REV_DIRS:
            for f in glob.glob(os.path.join(d, '*.json')):
                g = HD.load_json(f) or {}
                if g.get('状态') not in ('完整', '截断'): continue
                rv = g.get('reviews') or {}
                fk = next((fam_of[x['pid']] for x in rv.values() if x.get('pid') in fam_of), None)
                if fk is None: continue
                fr = g.get('首条评论')
                if isinstance(fr, str) and fr[:4].isdigit(): first[fk] = min(first.get(fk, fr), fr)
                for rid, x in rv.items():
                    dd = x.get('d') or ''
                    if dd[:4].isdigit() and mi(dd) in MON: rat[rid] = (x['pid'], mi(dd), x['r'])
        R = pd.DataFrame(list(rat.values()), columns=['pid', 'm', 'r'])
        A = A.join(R.groupby(['pid', 'm'])['r'].agg(rs='sum', rn='count'), on=['pid', 'm']); A[['rs', 'rn']] = A[['rs', 'rn']].fillna(0)
        A['首评'] = A['fam'].map(first)
        A['新家族'] = A['首评'].map(lambda d: isinstance(d, str) and d[:4] == '2026')
        A['进入月'] = A['首评'].map(lambda d: mi(d) if isinstance(d, str) and d[:4] == '2026' else np.nan)
    else:
        # 评分 = 页面总评分，按页面评论数加权（一个 listing 拆到多个尺寸段时按销量分摊权重）
        A['价格来源'] = np.where(A['价格'].notna(), '商品页 / 列表', '')
        ft = A.groupby('fam')['c'].transform('sum').replace(0, np.nan)
        w = A['页面评论数'].fillna(0) * A['c'] / ft; w = w.where(A['评分'].notna(), 0).fillna(0)
        A['rs'] = A['评分'].fillna(0) * w; A['rn'] = w
        # 新家族 = 页面累计评论数 ≤ 2026 年 1–10 月评论数（所有评论都在窗口内）；只有评论总数的 listing 判断不了，记非新
        n26 = A[A['m'] >= 0].groupby('fam')[['VP', '非VP']].sum().sum(axis=1)
        newf = (A.drop_duplicates('fam').set_index('fam')['页面评论数'] <= n26.reindex(A['fam'].unique())) & (n26.reindex(A['fam'].unique()) > 0)
        A['新家族'] = A['fam'].map(newf).fillna(False).astype(bool)
        e = A[(A['m'] >= 0) & (A['c'] > 0)].groupby('fam')['m'].min()
        A['进入月'] = np.where(A['新家族'], A['fam'].map(e), np.nan)
    return A, p, K


def frameable(A):
    return A['尺寸段'].notna() & (A['装'] != '未知') & (A['形态'] != '未知')


def pending_list(A, ch):
    """不能落框的商品（装 / 形态 / 尺寸段 未知或多尺寸未拆）→ 待人工确认清单。"""
    x = A[~frameable(A)].copy()
    x['原因'] = [('、'.join(r for r, k in (('装未知', a == '未知'), ('形态未知', f == '未知'), ('多尺寸未拆（销量拆不到尺寸段）', ms_), ('尺寸段未知', s is None or s != s and not ms_)) if k))
                for a, f, ms_, s in zip(x['装'], x['形态'], x['多尺寸未拆'], x['尺寸段'])]
    g = x.groupby(['fam', 'pid', '原因']).agg(title=('title', 'first'), 品牌=('品牌', 'first'), 尺寸段=('尺寸段', 'first'), 装=('装', 'first'), 形态=('形态', 'first'),
                                            装来源=('装来源', 'first'), 形态来源=('形态来源', 'first'), 有商品页=('有商品页', 'first'), 页面评论数=('页面评论数', 'first'),
                                            月度来源=('月度来源', 'first'), 销量1_10月=('c', 'sum')).reset_index()
    g.insert(0, '渠道', ch); g['占渠道销量'] = g['销量1_10月'] / A['c'].sum()
    return g.sort_values('销量1_10月', ascending=False)


def frame_cover(A, F):
    """每个框的分框标签覆盖：没进框的销量（装 / 形态未知、多尺寸未拆）按"已知维度一致"可能落到的框分摊。
    期望 = 按这些框的已落框销量比例分摊后，本框 ÷（本框 + 分到的）；最坏 = 本框 ÷（本框 + 所有可能落到本框的）。
    多尺寸未拆的 listing 只分到它商品页选项里有的尺寸段（选项段）。"""
    ok = frameable(A); IN = A[ok].groupby(['尺寸段', '装', '形态'])['c'].sum()
    allsz = sorted(A.loc[ok, '尺寸段'].unique()); forms = sorted(A.loc[ok, '形态'].unique())
    U = A[~ok].assign(选项段=A['选项段'].fillna('') if '选项段' in A else '')
    U = U.groupby([U['尺寸段'].fillna(''), '选项段', '装', '形态', '多尺寸未拆'])['c'].sum()
    exp, worst = collections.defaultdict(float), collections.defaultdict(float)
    for (sz, opt, a, f, multi), c in U.items():
        sizes = [sz] if sz else ([x for x in opt.split('、') if x] if multi and opt else allsz)
        comp = [k for k in IN.index if k[0] in sizes and (a == '未知' or k[1] == a) and (f == '未知' or k[2] == f)]
        t = IN[comp].sum()
        for k in comp:
            worst[k] += c
            if t > 0: exp[k] += c * IN[k] / t
    return {' · '.join(k): (v / (v + exp[k]), v / (v + worst[k])) for k, v in IN.items()}


def frame_key(A, view):
    s = A['尺寸段'].astype(object)
    if view == '框':
        ok = s.notna() & (A['装'] != '未知') & (A['形态'] != '未知'); k = s.fillna('') + ' · ' + A['装'] + ' · ' + A['形态']   # 上一版数据形态无未知（默认落地式），条件不影响旧视图
    elif view == '不分拆装':
        ok = s.notna(); k = s.fillna('') + ' · 不分拆装 · ' + A['形态']
    elif view == '不分尺寸段':
        ok = A['装'] != '未知'; k = '不分尺寸段 · ' + A['装'] + ' · ' + A['形态']
    elif view == '全尺寸不分拆装':
        ok = pd.Series(True, index=A.index); k = '全尺寸 · 不分拆装 · ' + A['形态']
    return k.where(ok)


def share_series(C, F):
    return C.reindex(MON, fill_value=0) / F.reindex(MON, fill_value=0).replace(0, np.nan)


def metrics(A, view, ch):
    """返回 框表、单元表。份额分母 = 整框销量（含该属性未知的部分，框表给出各属性已知占比）。"""
    A = A.assign(框=frame_key(A, view)); A = A[A['框'].notna()]
    FR, UN = [], []
    for fr, g in A.groupby('框'):
        Fm = g.groupby('m')['c'].sum().reindex(MON, fill_value=0); tot = g['c'].sum()   # 体量含只有评论总数的 listing（m = −1），趋势只用逐月
        fams = g.loc[g['c'] > 0, 'fam'].nunique(); famavg = tot / 10 / max(fams, 1)
        newf = g[g['新家族']]
        fi = dict(渠道=ch, 视图=view, 框=fr, 框月均=tot / 10, 家族=fams, 单款月均=famavg, 有月度占比=Fm.sum() / tot if tot else np.nan,
                  前3=Fm[PRE].sum() / 3, 近3=Fm[REC].sum() / 3, 框新家族=newf.loc[newf['c'] > 0, 'fam'].nunique(), 框新家族占比=newf['c'].sum() / tot if tot else np.nan,
                  框中位价=wq(g['价格'], g['c'], .5), 框评分=g['rs'].sum() / g['rn'].sum() if g['rn'].sum() else np.nan, 框评论数=g['rn'].sum(),
                  **{f'季{k}': Fm[v].sum() / len(v) for k, v in Q.items()})
        for att in ATTRS:
            x = g.explode('元素') if att == '元素' else g
            kn = x[~x[att].astype(str).isin(UNK | {'其他'})]
            fi[f'{att}已知'] = (kn.drop_duplicates(['pid', 'm'])['c'].sum() / tot) if tot else np.nan
            for v, u in kn.groupby(att):
                Um = u.groupby('m')['c'].sum().reindex(MON, fill_value=0); us = u['c'].sum()
                if us / 10 < 1: continue
                sh = share_series(Um, Fm); s_pre = Um[PRE].sum() / max(Fm[PRE].sum(), 1e-9); s_rec = Um[REC].sum() / max(Fm[REC].sum(), 1e-9)
                xs = np.arange(10); ok = sh.notna().values
                slope = np.polyfit(xs[ok], sh.values[ok], 1)[0] if ok.sum() >= 3 else np.nan
                uf = u.loc[u['c'] > 0, 'fam'].nunique()
                nu = u[u['新家族'] & (u['c'] > 0)]
                # 新家族进入后是否卖起来：进入月到 10 月，家族在该单元的月均 ≥ 同框单款月均
                up = 0
                for f, h in nu.groupby('fam'):
                    e = int(h['进入月'].iloc[0]) if pd.notna(h['进入月'].iloc[0]) else MON[0]; e = max(e, MON[0])
                    if h.loc[h['m'] >= e, 'c'].sum() / (MON[-1] - e + 1) >= famavg: up += 1
                mu = Um.mean()
                UN.append(dict(渠道=ch, 视图=view, 框=fr, 属性=att, 取值=v, 月均=us / 10, 份额=us / tot, 有月度占比=Um.sum() / us, 份额_仅有月度=Um.sum() / max(Fm.sum(), 1e-9),
                               **{f'份额{k}': Um[q].sum() / max(Fm[q].sum(), 1e-9) for k, q in Q.items()},
                               份额前3=s_pre, 份额近3=s_rec, 份额差pp=(s_rec - s_pre) * 100, 份额ln=np.log((s_rec + 0.002) / (s_pre + 0.002)),
                               斜率pp=slope * 100, 单元增长=Um[REC].sum() / Um[PRE].sum() if Um[PRE].sum() > 0 else np.nan, 框增长=Fm[REC].sum() / max(Fm[PRE].sum(), 1e-9),
                               CV=Um.std(ddof=0) / mu if mu else np.nan, 家族=uf, 单款比=(us / max(uf, 1)) / max(famavg * 10, 1e-9),
                               新家族=nu['fam'].nunique(), 新家族卖起来=up, 新家族占比=u.loc[u['新家族'], 'c'].sum() / us, 框新家族占比=fi['框新家族占比'], 家族列表='|'.join(sorted(map(str, u.loc[u['c'] > 0, 'fam'].unique()))),
                               P25=wq(u['价格'], u['c'], .25), 中位价=wq(u['价格'], u['c'], .5), P75=wq(u['价格'], u['c'], .75),
                               溢价=wq(u['价格'], u['c'], .5) / fi['框中位价'] if fi['框中位价'] == fi['框中位价'] else np.nan,
                               评分=u['rs'].sum() / u['rn'].sum() if u['rn'].sum() else np.nan, 评论数=u['rn'].sum(), 框评分=fi['框评分'],
                               尺寸段=g['尺寸段'].iloc[0], 形态=g['形态'].iloc[0], 框月均=tot / 10,
                               月序列='/'.join(f'{x * 100:.0f}' for x in sh.fillna(0).values)))
        FR.append(fi)
    F = pd.DataFrame(FR); U = pd.DataFrame(UN)
    if len(U):
        U['评分差'] = U['评分'] - U['框评分']
        U['走势'] = [trend_label(r) for r in U.itertuples()]
    return F, U


def trend_label(r):
    fr = '框涨' if r.框增长 >= 1.15 else ('框跌' if r.框增长 <= 0.87 else '框平')
    if r.份额ln >= LN: return f'抢份额（{fr}）'
    if r.份额ln <= -LN: return f'丢份额（{fr}）'
    return f'随框（{fr}）'


# ====================================================================== 3. Amazon 对照（尺寸段 × 形态 × 取值，不分拆装）
def az_cells(B, level):
    B = B.assign(框=(B['尺寸段'].astype(object).fillna('') + ' · ' + B['形态']).where(B['尺寸段'].notna()) if level == '尺寸段' else '全尺寸 · ' + B['形态'])
    B = B[B['框'].notna()]
    Fm = B.groupby(['框', 'm'])['c'].sum()
    out = {}
    for att in ATTRS:
        x = B.explode('元素') if att == '元素' else B
        x = x[~x[att].astype(str).isin(UNK | {'其他'}) & ~x[att].astype(str).str.startswith('其他（')]
        if att == '台面材质':   # Amazon 很少标 Cultured Marble，树脂一体多标"树脂"：另给合并键，供 Cultured Marble / 树脂 对照
            x = pd.concat([x, x[x[att].isin(['Cultured Marble', '树脂'])].assign(**{att: RESIN})])
        for (fr, v), u in x.groupby(['框', att]):
            Um = u.groupby('m')['c'].sum(); F = Fm.loc[fr]
            pre = Um.reindex(AZ_PRE, fill_value=0).sum() / max(F.reindex(AZ_PRE, fill_value=0).sum(), 1e-9)
            rec = Um.reindex(AZ_REC, fill_value=0).sum() / max(F.reindex(AZ_REC, fill_value=0).sum(), 1e-9)
            w = u[u['c'] > 0]
            out[(fr, att, str(v))] = dict(AZ月均=Um.sum() / 6, AZ份额=Um.sum() / F.sum(), AZ家族=w['fam'].nunique(),
                                          AZ价位段=pd.cut(w['价格'], PRICE_ABS, labels=False, right=False).nunique(),
                                          AZ份额前=pre, AZ份额近=rec, AZln=np.log((rec + 0.002) / (pre + 0.002)))
    return out


def arrow(x):
    return '—' if x is None or not np.isfinite(x) else ('↑' if x >= DIR else ('↓' if x <= -DIR else '→'))


def attach_az(U, AZ, level):
    if not len(U): return U
    keys = []
    for r in U.itertuples():
        fr = f'{r.尺寸段} · {r.形态}' if level == '尺寸段' else f'全尺寸 · {r.形态}'
        keys.append(AZ.get((fr, r.属性, AZKEY(r.属性, r.取值)), {}))
    Z = pd.DataFrame(keys, index=U.index)
    for c in ('AZ月均', 'AZ份额', 'AZ家族', 'AZ价位段', 'AZ份额前', 'AZ份额近', 'AZln'):
        U[c] = Z[c] if c in Z else np.nan
    return U


# ====================================================================== 4. 报告片段
def cov_table(A, ch):
    """每个标签的覆盖率：按商品页、按 1–10 月估算销量。"""
    V = A.drop_duplicates('pid'); S = A.groupby('pid')['c'].sum(); tot = S.sum()
    rows = []
    def add(name, known, note=''):
        kp = known.reindex(V['pid']).fillna(False).values if isinstance(known, pd.Series) else known
        ids = V['pid'][kp]; rows.append(f'| {name} | {kp.mean():.0%} | {S.reindex(ids).sum() / tot:.0%} | {note} |')
    vi = V.set_index('pid')
    add('尺寸段', vi['尺寸段'].notna())
    src = A.groupby('装来源')['c'].sum() / tot
    add('装（含业务默认 / 家族补）', vi['装'] != '未知', '来源（按销量）：' + '、'.join(f'{k} {v:.0%}' for k, v in src.sort_values(ascending=False).items()))
    src = A.groupby('形态来源')['c'].sum() / tot
    add('形态', pd.Series(True, index=vi.index), '来源（按销量）：' + '、'.join(f'{k} {v:.0%}' for k, v in src.sort_values(ascending=False).items()))
    for att in ('台面材质', '主色', '柜体材质'):
        add(att, ~vi[att].astype(str).isin(UNK))
    add('元素（文字规则）', vi['元素'].map(lambda e: e != ['未知']))
    add('框（尺寸段 × 装 × 形态）可定', vi['尺寸段'].notna() & (vi['装'] != '未知'))
    return ['| 标签 | 商品页覆盖 | 1–10 月销量覆盖 | 说明 |', '| :--- | ---: | ---: | :--- |'] + rows


def frame_table(F, cover=False, tot=None):
    """cover（新版）：加"分框覆盖 期望 / 最坏""有月度占比""可读性"列；tot：渠道内份额的分母（默认 = 表内框合计）。"""
    F = F.sort_values('框月均', ascending=False)
    out = ['| 框 | 月均 | 渠道内份额 | ' + ('季均（只算有月度）' if cover else '季均') + ' 1–3 / 4–6 / 7–9 / 10 月 | 近 3 ÷ 前 3 | 家族 | 单款月均 | 新家族（销量占比） | 中位价 | 评分 | 台面 / 主色 / 柜体 / 元素 已知 |' + (' 分框覆盖 期望 / 最坏 | 有月度占比 | 可读性 |' if cover else ''),
           '| :--- | ---: | ---: | :--- | ---: | ---: | ---: | :--- | ---: | ---: | :--- |' + (' :--- | ---: | :--- |' if cover else '')]
    tot = tot or F['框月均'].sum()
    for _, r in F.iterrows():
        out.append(f"| {r['框']} | {num(r['框月均'])} | {pc(r['框月均'] / tot)} | {num(r['季1–3'])} / {num(r['季4–6'])} / {num(r['季7–9'])} / {num(r['季10'])} | {gx(r['近3'] / r['前3'] if r['前3'] > 0 else np.nan)} | {r['家族']} | {num(r['单款月均'])} | "
                   f"{r['框新家族']}（{pc(r['框新家族占比'])}） | {('$' + num(r['框中位价'])) if np.isfinite(r['框中位价']) else '无'} | {num(r['框评分'], 2) if np.isfinite(r['框评分']) else '无'} | "
                   f"{pc(r['台面材质已知'])} / {pc(r['主色已知'])} / {pc(r['柜体材质已知'])} / {pc(r['元素已知'])} |" +
                   (f" {pc(r['分框覆盖_期望'], 1)} / {pc(r['分框覆盖_最坏'], 1)} | {pc(r['有月度占比'])} | {r['可读性']} |" if cover else ''))
    return out


def readability(r):
    """框的可读性：分框覆盖（期望）≥ 95% 才在框内下结论；趋势还要求有月度的销量 ≥ 60%。"""
    if not r['分框覆盖_期望'] >= 0.95: return '不下结论（分框覆盖 < 95%）'
    if not r['有月度占比'] >= 0.6: return '体量 / 份额可看，趋势不下结论（有月度 < 60%）'
    return '可读'


def unit_table(U, has_price, has_rating, has_static=False):
    h = '| 属性：取值 | 月均 | 份额 | 季度份额 1–3 / 4–6 / 7–9 / 10 | 近3−前3 | 斜率 pp/月 | 走势（单元 ÷ 框） | CV | 家族 | 单款 ÷ 同框 | 新家族 个（卖起来）· 占比（同框） |'
    s = '| :--- | ---: | ---: | :--- | ---: | ---: | :--- | ---: | ---: | ---: | :--- |'
    if has_static: h += ' 有月度占比 · 仅有月度的份额 |'; s += ' :--- |'
    if has_price: h += ' 价格带 P25–P75 · 溢价 |'; s += ' :--- |'
    if has_rating: h += ' 评分（同框差） |'; s += ' :--- |'
    h += ' Amazon 家族 · 价位段 · 份额前→近 |'; s += ' :--- |'
    out = [h, s]
    for r in U.itertuples():
        q = [U.at[r.Index, f'份额{k}'] for k in Q]
        line = (f"| {r.属性}：{r.取值} | {num(r.月均)} | {ps(r.份额)} | {ps(q[0])} / {ps(q[1])} / {ps(q[2])} / {ps(q[3])} | {sg(r.份额差pp, 1)} pp | {sg(r.斜率pp, 2)} | "
                f"{r.走势} {gx(r.单元增长)} ÷ {r.框增长:.2f} | {r.CV:.2f} | {r.家族} | {r.单款比:.2f} | {r.新家族}（{r.新家族卖起来}）· {pc(r.新家族占比)}（{pc(r.框新家族占比)}） |")
        if has_static: line += f" {pc(r.有月度占比)} · {ps(r.份额_仅有月度)} |"
        if has_price: line += f" ${num(r.P25)}–{num(r.P75)} · {r.溢价:.2f} |" if np.isfinite(r.中位价) else ' 无 |'
        if has_rating: line += f" {r.评分:.2f}（{sg(r.评分差)}） |" if np.isfinite(r.评分) else ' — |'
        line += (f" {int(r.AZ家族)} · {int(r.AZ价位段)} · {ps(r.AZ份额前)}→{ps(r.AZ份额近)} {arrow(r.AZln)}{'（树脂一体合并）' if AZKEY(r.属性, r.取值) == RESIN else ''} |" if np.isfinite(r.AZ家族) else ' 无 |')
        out.append(line)
    return out


def patterns(U, ch, has_price, has_rating, trend=True):
    out = []
    pat = [] if not trend else [('份额在涨 + 新家族进入', (U['份额ln'] >= LN) & (U['新家族'] > 0) & (U['新家族占比'] > U['框新家族占比']),
            lambda r: f"份额 {ps(r.份额前3)}→{ps(r.份额近3)}，单元销量 ×{gx(r.单元增长)}、框 ×{r.框增长:.2f}；新家族 {r.新家族} 个（{r.新家族卖起来} 个达到同框单款月均），销量占比 {pc(r.新家族占比)}（同框 {pc(r.框新家族占比)}）"),
           ('份额在涨（无新家族带动）', (U['份额ln'] >= LN) & ~((U['新家族'] > 0) & (U['新家族占比'] > U['框新家族占比'])),
            lambda r: f"份额 {ps(r.份额前3)}→{ps(r.份额近3)}，单元 ×{gx(r.单元增长)}、框 ×{r.框增长:.2f}；家族 {r.家族}、新家族 {r.新家族}"),
           ('份额在跌', U['份额ln'] <= -LN,
            lambda r: f"份额 {ps(r.份额前3)}→{ps(r.份额近3)}，单元 ×{gx(r.单元增长)}、框 ×{r.框增长:.2f}；家族 {r.家族}")]
    if has_rating:
        pat.append(('评分低于同框但单款卖得多', (U['评分差'] <= -0.15) & (U['单款比'] >= 1.0) & (U['评论数'] >= 20),
                    lambda r: f"评分 {r.评分:.2f}（同框 {r.框评分:.2f}，{int(r.评论数)} 条评论）、单款 ÷ 同框 {r.单款比:.2f}、份额 {ps(r.份额)}"))
    if has_price:
        pat.append(('高溢价且有成交', U['溢价'] >= 1.3,
                    lambda r: f"中位价 ${num(r.中位价)}（溢价 {r.溢价:.2f}），月均 {num(r.月均)}、份额 {ps(r.份额前3)}→{ps(r.份额近3)}"))
    for name, k, fmt in pat:
        d = U[k].copy(); d['_s'] = d['月均'] * d['份额ln'].abs(); d = d.sort_values('_s', ascending=False)
        out += [f'**{name}**（{len(d)} 个单元{"，列前 10" if len(d) > 10 else ""}）', '']
        if not len(d): out += ['- 无', '']; continue
        for r in d.head(10).itertuples():
            out.append(f'- {r.框} ｜ {r.属性}：{r.取值}（月均 {num(r.月均)}）：{fmt(r)}')
        out.append('')
    return out


# ====================================================================== 5. 主流程
def main_old():
    """上一版：HD 类目 Top Sellers 评论重建 + Lowe's / Wayfair 渠道VP表（降级视图）。python3 小平台调研_单元指标.py 上一版"""
    L.clear()
    print('读 HD …'); AH, VH = hd_table()
    print("读 Lowe's / Wayfair …"); AL, VL = lw_table("Lowe's"); AW, VW = lw_table('Wayfair')
    print('读 Amazon …'); B = az_table()
    AZs, AZa = az_cells(B, '尺寸段'), az_cells(B, '全尺寸')
    CH = {'Home Depot': (AH, True, True), "Lowe's": (AL, False, False), 'Wayfair': (AW, False, False)}
    VIEWS = {'Home Depot': ['框', '不分拆装', '全尺寸不分拆装'], "Lowe's": ['框', '不分尺寸段', '全尺寸不分拆装'], 'Wayfair': ['框', '不分拆装', '全尺寸不分拆装']}
    RES = {}
    for ch, (A, hp, hr) in CH.items():
        for v in VIEWS[ch]:
            F, U = metrics(A, v, ch)
            U = attach_az(U, AZa if v in ('不分尺寸段', '全尺寸不分拆装') else AZs, '全尺寸' if v in ('不分尺寸段', '全尺寸不分拆装') else '尺寸段')
            RES[(ch, v)] = (F, U)
    os.makedirs(OUTDIR, exist_ok=True)
    pd.concat([r[1] for r in RES.values()]).to_csv(os.path.join(OUTDIR, '小平台调研_单元指标_全量.csv'), index=False, encoding='utf-8-sig')
    pd.concat([r[0] for r in RES.values()]).to_csv(os.path.join(OUTDIR, '小平台调研_框_全量.csv'), index=False, encoding='utf-8-sig')

    # ---------------- 一、口径
    tot = {ch: A.groupby('m')['c'].sum().mean() for ch, (A, _, _) in CH.items()}
    lw_fam = {ch: (A['fam'].nunique(), A['pid'].nunique()) for ch, (A, _, _) in CH.items()}
    incons = {ch: A.drop_duplicates('fam')['累计不一致'].mean() for ch, (A, _, _) in CH.items() if ch != 'Home Depot'}
    P('# 小平台调研：单元 × 指标（Home Depot / Lowe\'s / Wayfair）', '',
      '> 由 `solution-v2/trial/小平台调研_单元指标.py` 生成，数字都是脚本实际运行结果。本页是**观察分析**，不是回测，不下立项结论；"模式"一节只列符合条件的事实。'
      '全量单元表在 `input/data_v2/渠道调研/小平台调研_单元指标_全量.csv`（框表 `小平台调研_框_全量.csv`，不入库）。', '')
    P('## 一、口径', '',
      '**叫法**（wen 2026-11-04）：框 = 尺寸段 × 拆装 × 形态；属性 = 台面材质 / 元素 / 主色 / 柜体材质；取值 = 属性的值；单元（表的一行）= 框 × 属性取值；指标（表的一列）= 观察的数据维度；模式 = 指标组合成的信号。'
      '**一切比较只在同一框、同一渠道内**；三渠道对照只比方向和结构，不比绝对销量。', '',
      '**数据与窗口**', '',
      f'- Home Depot：评论重建（两个类目 Top Sellers 各前 300 个商品页 → 评论家族，采集 2026-11-03），变体级销量 = 该变体当月 VP 评论 × 50 + 非 VP × 20；主窗口 2026-01 至 10，月均 {num(tot["Home Depot"])} 件（重建口径，覆盖类目头部约 6–7 成，见 `小平台_HD回测小试.md` §3）。'
      '价格 = 采集日（2026-11-03）列表 / 商品页当天价，套到整个窗口；评分 = 窗口内评论星级的平均（按评论条数），不是页面总评分。',
      f'- Lowe\'s / Wayfair：`渠道VP_20261103.xlsx`「商品月度明细」（Lowe\'s 两个 Best Sellers 榜各前 100；Wayfair 主类目 Recommended 前 200 + 无台面前 50；采集 2026-11-02 至 03）。'
      f'同系列不同颜色 / 尺寸的商品页共享评论，按"1–10 月 VP / 非 VP 序列 + 11 月 + 页面累计评论数"完全相同合成家族：Lowe\'s {lw_fam[LW][1]} 个商品页 → {lw_fam[LW][0]} 个家族，Wayfair {lw_fam["Wayfair"][1]} → {lw_fam["Wayfair"][0]}；'
      '家族月销按成员商品页均分（同 Amazon"子体月销（家族均分）"）。核对：Lowe\'s 家族去重后 1–10 月评论 3,852 条（表内去重口径 3,850），Wayfair 7,550 条（表内 7,373，多 2%：少数商品页累计数不同但共享部分评论，没有逐条去重）。'
      f'月均 Lowe\'s {num(tot[LW])}、Wayfair {num(tot["Wayfair"])} 件。**没有价格、评分字段**，表里写"无"。',
      '- Amazon：第二轮统一打标表（`统一打标_分析用.pkl`，与第九版、跨渠道检验同一张），窗口 2026-04 至 09（数据到 9 月）；按"尺寸段 × 形态 × 属性取值"（不分拆装，跨渠道检验报告的"忽略装"口径）给家族数、绝对价位段数（$0–200 / 200–300 / 300–450 / 450–650 / 650–900 / 900–1,300 / 1,300+）、框内份额 4–6 月 → 7–9 月。',
      '- 11 月不完整，不计入；10 月是评论采集前最后一个完整月，评论有滞后（买后才评），三个渠道 10 月都可能略低，影响"近 3 月"的销量水平，对同框份额影响较小。', '',
      '**指标**（每个单元一行）', '',
      '- 体量：月均 = 1–10 月估算销量 ÷ 10；份额 = 单元销量 ÷ **整框**销量（分母含该属性未知的部分，所以同一框同一属性的份额加起来 = 该属性已知占比，框表里给出）。',
      f'- 趋势：季度份额（1–3 / 4–6 / 7–9 / 10 月，CSV 里有逐月）；近 3−前 3 = 8–10 月份额 − 1–3 月份额（百分点）；斜率 = 10 个月月度份额的线性斜率（百分点 / 月）；'
      f'走势 = 份额 ln(近 3 ÷ 前 3) ≥ {LN} 记"抢份额"、≤ −{LN} 记"丢份额"、其余"随框"，括号里是框本身近 3 ÷ 前 3（≥ 1.15 框涨、≤ 0.87 框跌），后面两个数 = 单元销量近 3 ÷ 前 3、框销量近 3 ÷ 前 3（区分"整框在涨"和"取值在抢份额"）；CV = 10 个月月销的变异系数。',
      '- 新家族：家族首条评论在 2026 年（HD 用按最早排序抓到的首评日期；Lowe\'s / Wayfair 用"页面累计评论数 ≤ 2026 年 1–11 月评论数"，即所有评论都在 2026 年）；"卖起来" = 进入月到 10 月在该单元的月均 ≥ 同框单款月均；占比 = 新家族在单元 1–10 月销量里的占比，括号是同框。'
      f'Lowe\'s {pc(incons[LW])}、Wayfair {pc(incons["Wayfair"])} 的家族页面累计数小于 2026 年评论数（口径不一致），这些按"非新"处理。',
      '- 供给：家族 = 窗口内单元里有销量的家族数；单款 ÷ 同框 = 单元每个家族的月均 ÷ 同框每个家族的月均。',
      '- 价格（仅 HD）：价格带 = 按销量加权的 P25–P75；溢价 = 单元加权中位价 ÷ 同框加权中位价。评分（仅 HD）：单元评分与同框评分的差。',
      '- Amazon 对照：同尺寸段 × 形态 × 取值（不分拆装）的家族数 · 价位段数 · 框内份额 4–6 月 → 7–9 月，箭头 ↑ / → / ↓ 按 ln 变化 ±0.2。', '',
      f'**门槛**：框月均 ≥ {FR_MIN} 件、单元月均 ≥ {U_MIN} 件才列（三个渠道体量相近，月均 1.7–2.9 万件，用同一门槛；{FR_MIN} 件约为渠道月销的 0.7–1.2%，与 HD 回测"大单元"同量级）。'
      '1 条 VP 评论 = 50 件，月均 20 件的单元 10 个月只有约 4 条 VP 评论，**小单元的趋势和 CV 噪声很大**，只看方向，家族数 1–2 的单元基本是单个产品的走势。', '')
    P('**幸存者偏差**：三个渠道都是"今天在榜（前 100–300）"的商品往回看。过去卖得好、今天掉出榜单的商品看不到，所以：① 早月份的框销量偏低，"框在涨""份额在涨"会偏乐观（尤其新家族多的单元，进入早期本来就是 0）；'
      '② "份额在跌"只看到还在榜的商品在跌，真实下跌更多；③ HD 2024–2025 年的重建只作背景，2026 年 1–10 月离采集日近、偏差较小，但仍有。这也是本页只做观察、不做回测的原因（`幸存者偏差模拟_小平台回测可行性.md`）。', '')

    P('### 打标覆盖', '',
      '规则：v12.2 打标（`app/pdt/core/tagging_rules.py` 的 Tagger，关掉默认值）。HD 用标题 + 商品页规格（"Assembled""Vanity Type"规格优先），Lowe\'s / Wayfair 只有标题；同家族已知值补装、形态、柜体材质、台面材质；'
      '形态没写的按落地式（与 Amazon、HD 小试同口径）；元素只用文字规则（夏克式 / 竖棱 / 农场风 / 玻璃门 / 木条格栅 / rattan），不看图。'
      '**装**：HD 判断不了记未知、不进框；Lowe\'s 判断不了按 wen《2026-Q2 浴室柜品类规划》"Lowe\'s 100% 整装"作业务默认整装（来源：wen 文档，非数据）；Wayfair 拆装约 23%（wen 文档），不能默认，判断不了的不进带"装"的框，另给"尺寸段 × 形态（不分拆装）"降级视图。', '')
    for ch, (A, _, _) in CH.items():
        P(f'**{ch}**', '', *cov_table(A, ch), '')

    # ---------------- 二、每个渠道
    P('## 二、各渠道', '')
    SEC = {'Home Depot': [('框', '主视图：框 = 尺寸段 × 装 × 形态')],
           "Lowe's": [('框', '主视图：框 = 尺寸段 × 装 × 形态（尺寸段几乎认不出，见覆盖表）'), ('不分尺寸段', '**降级视图**：不分尺寸段 × 装（业务默认整装）× 形态 —— 不满足"同尺寸段"硬规则，只能看属性结构和走势，不能当框内比较')],
           'Wayfair': [('框', '主视图：框 = 尺寸段 × 装 × 形态（只含装能从标题判断的商品）'), ('不分拆装', '**降级视图**：尺寸段 × 形态（不分拆装）—— 整装、拆装混在一个框里，价格、单款比较会偏')]}
    KEYN = {'Home Depot': 5, "Lowe's": 3, 'Wayfair': 4}
    for ch, (A, hp, hr) in CH.items():
        P(f'### {ch}', '')
        for v, title in SEC[ch]:
            F, U = RES[(ch, v)]
            F2 = F[F['框月均'] >= FR_MIN]
            P(f'#### {title}', '', f'框月均 ≥ {FR_MIN} 的框 {len(F2)} 个（全部框 {len(F)} 个，合计月均 {num(F["框月均"].sum())}；达标框占 {pc(F2["框月均"].sum() / max(F["框月均"].sum(), 1e-9))}）。', '')
            if not len(F2): P('（没有达标的框。）', ''); continue
            P(*frame_table(F2), '')
            U2 = U[U['框'].isin(F2['框']) & (U['月均'] >= U_MIN)]
            P(f'达标单元 {len(U2)} 个（单元月均 ≥ {U_MIN}）。', '')
            for fr in F2.sort_values('框月均', ascending=False)['框'].head(KEYN[ch]):
                d = U2[U2['框'] == fr].sort_values(['属性', '月均'], ascending=[True, False])
                P(f'**{fr}**（框月均 {num(F2.set_index("框").at[fr, "框月均"])}）', '', *unit_table(d, hp, hr), '')
            P(f'**模式观察（{ch} · {v}，所有达标框）**：条件 —— 份额在涨 / 跌：ln(近 3 ÷ 前 3 份额) ≥ {LN} / ≤ −{LN}；新家族进入：有新家族且新家族销量占比高于同框；'
              '评分低于同框：差 ≤ −0.15、单款 ÷ 同框 ≥ 1、窗口评论 ≥ 20 条；高溢价：溢价 ≥ 1.3。只陈述事实，排序按 月均 × |份额 ln 变化|。', '', *patterns(U2, ch, hp, hr))

    # ---------------- 三、三渠道对照
    P('## 三、三渠道与 Amazon 对照（只比方向和结构）', '',
      f'方向：小平台 = 份额 ln(8–10 月 ÷ 1–3 月)，Amazon = ln(7–9 月 ÷ 4–6 月)，|ln| < {DIR} 记 →。窗口不同（Amazon 数据到 9 月），只看是否同向。份额 = 同（尺寸段 ×）形态框内的份额（不分拆装）。', '')
    def struct(A, att, w='c'):
        x = A.explode('元素') if att == '元素' else A
        x = x[~x[att].astype(str).isin(UNK | {'其他'}) & ~x[att].astype(str).str.startswith('其他（')]
        return x.groupby(att)[w].sum() / A[w].sum()
    COV = {ch: {att: struct(A, att).sum() for att in ATTRS} for ch, (A, _, _) in CH.items()}
    COVMIN = 0.3
    P(f'属性覆盖不足的渠道不参与该属性的方向比较：某渠道某属性已知销量 < {COVMIN:.0%} 时记"覆盖不足"（' +
      '；'.join(f'{ch} ' + '、'.join(f'{a} {COV[ch][a]:.0%}' for a in ATTRS) for ch in CH) + '）。台面材质 Cultured Marble 与 树脂 在 Amazon 侧按"树脂一体"合并对照（Amazon 很少单标 Cultured Marble）。', '')
    # 3.1 全尺寸 × 形态 × 取值（含 Lowe's）
    GA = {ch: RES[(ch, '全尺寸不分拆装')][1] for ch in CH}
    keys = set()
    for ch, U in GA.items(): keys |= set(map(tuple, U.loc[U['月均'] >= U_MIN, ['框', '属性', '取值']].values))
    rows = []
    for k in sorted(keys):
        rec = {'框': k[0], '属性': k[1], '取值': k[2]}
        for ch, U in GA.items():
            r = U[(U['框'] == k[0]) & (U['属性'] == k[1]) & (U['取值'] == k[2])]
            rec[ch] = r.iloc[0] if len(r) else None
        az = AZa.get((k[0].replace('全尺寸 · 不分拆装 · ', '全尺寸 · '), k[1], AZKEY(k[1], k[2])))
        rec['AZ'] = az; rows.append(rec)
    def cell(r, ch, att):
        if COV[ch][att] < COVMIN: return '覆盖不足'
        return '—' if r is None else f'{ps(r["份额"])} {arrow(r["份额ln"])}'
    def azc(a):
        return '—' if not a else f'{ps(a["AZ份额"])} {arrow(a["AZln"])}（{a["AZ家族"]} 家族）'
    P('### 3.1 全尺寸 × 形态 × 取值（四个渠道，Lowe\'s 只能在这一层比）', '',
      '格式：框内份额 方向。只列至少一个小平台月均 ≥ 20 件（且该渠道该属性覆盖够）、在落地式框里的取值（悬浮式在 HD / Lowe\'s 几乎没有）；"一致"只数月均 ≥ 20 且覆盖够的渠道。', '',
      '| 属性：取值 | HD | Lowe\'s | Wayfair | Amazon（家族） | 三个小平台方向一致？ |', '| :--- | :--- | :--- | :--- | :--- | :--- |')
    agree = []
    for rec in rows:
        if '落地式' not in rec['框']: continue
        dirs = [arrow(rec[ch]['份额ln']) for ch in CH if rec[ch] is not None and rec[ch]['月均'] >= U_MIN and COV[ch][rec['属性']] >= COVMIN]
        if not any(rec[ch] is not None and rec[ch]['月均'] >= U_MIN and COV[ch][rec['属性']] >= COVMIN for ch in CH): continue
        same = '—' if len(dirs) < 2 else ('一致' if len(set(dirs)) == 1 else '不一致')
        azd = arrow(rec['AZ']['AZln']) if rec['AZ'] else None
        agree.append((same, dirs, azd))
        P(f"| {rec['属性']}：{rec['取值']} | {cell(rec['Home Depot'], 'Home Depot', rec['属性'])} | {cell(rec[LW], LW, rec['属性'])} | {cell(rec['Wayfair'], 'Wayfair', rec['属性'])} | {azc(rec['AZ'])} | {same} |")
    n2 = [a for a in agree if a[0] != '—']
    P('', f'落地式里能在 ≥ 2 个小平台比较的取值 {len(n2)} 个，方向一致 {sum(a[0] == "一致" for a in n2)} 个。', '')
    # 3.2 尺寸段 × 形态 × 取值（HD / Wayfair / Amazon）
    UH = RES[('Home Depot', '不分拆装')][1]; UW = RES[('Wayfair', '不分拆装')][1]
    FH = RES[('Home Depot', '不分拆装')][0]; FW = RES[('Wayfair', '不分拆装')][0]
    okH = UH[UH['框'].isin(FH.loc[FH['框月均'] >= FR_MIN, '框']) & (UH['月均'] >= U_MIN)]
    okW = UW[UW['框'].isin(FW.loc[FW['框月均'] >= FR_MIN, '框']) & (UW['月均'] >= U_MIN)]
    M = okH.merge(okW, on=['框', '属性', '取值'], suffixes=('_H', '_W'))
    M = M[M['属性'].map(lambda a: COV['Home Depot'][a] >= COVMIN and COV['Wayfair'][a] >= COVMIN)]
    P('### 3.2 尺寸段 × 形态 × 取值（HD、Wayfair 都达标的单元 + Amazon）', '',
      f'两边框月均 ≥ {FR_MIN}、单元月均 ≥ {U_MIN}、属性覆盖两边都 ≥ {COVMIN:.0%}（实际只剩台面材质）的交集 {len(M)} 个单元。格式：框内份额 方向（不分拆装）。', '')
    if len(M):
        P('| 框 | 属性：取值 | HD | Wayfair | Amazon（家族 · 价位段） | HD 与 Wayfair | 与 Amazon 同向的小平台 |', '| :--- | :--- | :--- | :--- | :--- | :--- | :--- |')
        same_hw = 0; az_same = []
        for r in M.sort_values(['框', '属性']).itertuples():
            a = AZs.get((r.框.replace(' · 不分拆装 · ', ' · '), r.属性, AZKEY(r.属性, r.取值)))
            dh, dw = arrow(r.份额ln_H), arrow(r.份额ln_W); same_hw += dh == dw
            da = arrow(a['AZln']) if a else None
            hit = [n for n, dd in (('HD', dh), ('Wayfair', dw)) if da and dd == da]; az_same.append(len(hit))
            P(f"| {r.框} | {r.属性}：{r.取值} | {ps(r.份额_H)} {dh} | {ps(r.份额_W)} {dw} | " + (f"{ps(a['AZ份额'])} {da}（{a['AZ家族']} · {a['AZ价位段']}）" if a else '无') + f" | {'同向' if dh == dw else '不同'} | {'、'.join(hit) or '—'} |")
        P('', f'HD 与 Wayfair 同向 {same_hw}/{len(M)}；与 Amazon 同向的小平台个数分布：' + '、'.join(f'{k} 个 {v} 次' for k, v in sorted(pd.Series(az_same).value_counts().items())) + '。', '')
    # 3.3 结构：各渠道属性取值的份额（全尺寸、全形态、不分拆装）
    P('### 3.3 结构：各渠道取值占渠道销量的比例（全尺寸、全形态，只看结构）', '')
    for att in ATTRS:
        S = {ch: struct(A, att) for ch, (A, _, _) in CH.items()}; S['Amazon（4–9 月）'] = struct(B, att)
        vals = pd.concat(S, axis=1).fillna(0); vals = vals[vals.max(axis=1) >= 0.02].sort_values('Home Depot', ascending=False)
        if att == '台面材质': vals.loc[RESIN] = vals.reindex(['Cultured Marble', '树脂']).fillna(0).sum()
        P(f'**{att}**（已知部分占渠道销量：' + '、'.join(f'{k} {v.sum():.0%}' for k, v in S.items()) + '）', '',
          '| 取值 | ' + ' | '.join(vals.columns) + ' |', '| :--- |' + ' ---: |' * len(vals.columns))
        for v, r in vals.iterrows(): P(f'| {v} | ' + ' | '.join(pc(x) for x in r.values) + ' |')
        P('')

    # ---------------- 四、wen 老文档判断核对
    P('## 四、对 wen 老文档判断的核对（只给事实）', '', '老文档：小平台 2026 年 4–5 月截面、Lowe\'s / HDP 前两页手动收集（约 80–130 SKU）；这里用 1–10 月和更大的样本，口径不同，差异不一定说明老判断错。', '')
    # 4.1 HDP 36–48 实木 + 岗石/石英石 $649–799
    H = AH.copy(); H['实木类'] = H['柜体材质'].isin(['实木', '实木框架']); H['石材'] = H['台面材质'].isin(['岗石', '石英石'])
    for sz, band_ in ((['36″', '42″', '48″'], (649, 799)), (['48″', '60″'], (900, 1200))):
        g = H[H['尺寸段'].isin(sz)]; s = g[g['实木类'] & g['石材']]
        inb = s[(s['价格'] >= band_[0]) & (s['价格'] <= band_[1])]
        sp = lambda q: s.loc[s['m'].isin(q), 'c'].sum() / max(g.loc[g['m'].isin(q), 'c'].sum(), 1)
        bands = pd.cut(s['价格'], [0, 450, 649, 800, 900, 1200, 1e9], right=False, labels=['<$450', '$450–648', '$649–799', '$800–899', '$900–1,199', '≥$1,200'])
        bd = (s.groupby(bands)['c'].sum() / s['c'].sum())
        P(f'- **HD {"/".join(sz)}（全部装与形态）实木 / 实木框架 × 岗石 / 石英石**：月均 {num(s["c"].sum() / 10)} 件，占这几个尺寸段 {pc(s["c"].sum() / g["c"].sum())}；'
          f'份额 1–3 月 {pc(sp(PRE))} → 8–10 月 {pc(sp(REC))}；家族 {s.loc[s["c"] > 0, "fam"].nunique()} 个（2026 首评的新家族 {s.loc[s["新家族"] & (s["c"] > 0), "fam"].nunique()} 个）；'
          f'加权中位价 ${num(wq(s["价格"], s["c"], .5))}（P25–P75 ${num(wq(s["价格"], s["c"], .25))}–{num(wq(s["价格"], s["c"], .75))}），'
          f'落在 ${band_[0]}–{band_[1]} 的销量占 {pc(inb["c"].sum() / s["c"].sum())}；价格段分布：' + '、'.join(f'{k} {v:.0%}' for k, v in bd.items() if v > 0) + '。')
        ab = g[(g['价格'] >= band_[0]) & (g['价格'] <= band_[1])]
        combo = (ab.groupby([ab['柜体材质'], ab['台面材质']])['c'].sum() / ab['c'].sum()).sort_values(ascending=False).head(4)
        P(f'  同尺寸段全部商品里 ${band_[0]}–{band_[1]} 的销量占 {pc(ab["c"].sum() / g["c"].sum())}（家族 {ab.loc[ab["c"] > 0, "fam"].nunique()} 个），主要是：' +
          '、'.join(f'{a} × {b} {v:.0%}' for (a, b), v in combo.items()) + '（价格为 2026-11-03 当天价）。')
    sint = AH[AH['台面材质'] == '岩板']
    P(f'- **HD 岩板**：台面材质 = 岩板的销量 {num(sint["c"].sum() / 10)} 件 / 月（商品页 {sint["pid"].nunique()} 个），' + ('老文档"岩板一体热弯盆空白"在本样本里仍成立（以标题 / 规格文字为准）。' if sint['c'].sum() == 0 else '有少量。'))
    # 4.2 Lowe's
    lv = AL; tt = lv['c'].sum()
    top = lv[~lv['台面材质'].astype(str).isin(UNK | {'不适用（不含台面）'})]
    resin = top['台面材质'].isin(['Cultured Marble', '树脂'])
    Vd = VL[~VL['台面材质'].astype(str).isin(UNK | {'不适用（不含台面）'})]
    P(f'- **Lowe\'s 树脂盆 81%**：带台面且台面材质已知的销量占渠道 {pc(top["c"].sum() / tt)}；其中 Cultured Marble / 树脂（树脂一体）占 {pc(top.loc[resin, "c"].sum() / top["c"].sum())}'
      f'（按商品页数 {pc(Vd["台面材质"].isin(["Cultured Marble", "树脂"]).mean())}，{int(Vd["台面材质"].isin(["Cultured Marble", "树脂"]).sum())}/{len(Vd)} 个，少数 Cultured Marble 系列销量很大）；'
      '其余：' + '、'.join(f'{k} {v:.0%}' for k, v in (top.groupby('台面材质')['c'].sum() / top['c'].sum()).sort_values(ascending=False).items() if k not in ('Cultured Marble', '树脂') and v >= 0.01) +
      '。岗石 / 石英石台面常配陶瓷台下盆，标题不写盆材，所以"树脂盆"比例只能按台面推，按销量约在这个数上下。')
    src = lv.groupby('装来源')['c'].sum() / tt
    P(f'- **Lowe\'s 100% 整装**：标题写明装的销量占 {pc(src.drop(index=[i for i in src.index if "默认" in i], errors="ignore").sum())}，其中整装 {pc(lv.loc[~lv["装来源"].str.contains("默认") & (lv["装"] == "整装"), "c"].sum() / max(lv.loc[~lv["装来源"].str.contains("默认"), "c"].sum(), 1))}；'
      f'其余 {pc(src[[i for i in src.index if "默认" in i]].sum())} 按业务默认记整装（没有反证，也没有直接证据）。')
    # 4.3 Wayfair
    wv = AW; wt = wv['c'].sum(); kn = wv[wv['装'] != '未知']
    P(f'- **Wayfair 拆装 23%**：标题能判断装的销量只占 {pc(kn["c"].sum() / wt)}，其中拆装 {pc(kn.loc[kn["装"] == "拆装", "c"].sum() / max(kn["c"].sum(), 1))}；覆盖太低，验证不了 23%。')
    cb = wv[~wv['柜体材质'].astype(str).isin(UNK)]
    P(f'- **Wayfair 实木类 83%**：柜体材质已知销量占 {pc(cb["c"].sum() / wt)}，其中实木 + 实木框架 {pc(cb.loc[cb["柜体材质"].isin(["实木", "实木框架"]), "c"].sum() / cb["c"].sum())}'
      f'（标题里写 "solid wood" 的常是"实木 + 人造板"混合，规则归到实木框架或含胶合板等，口径与老文档可能不同）；分布：' + '、'.join(f'{k} {v:.0%}' for k, v in (cb.groupby('柜体材质')['c'].sum() / cb['c'].sum()).sort_values(ascending=False).items() if v >= 0.02) + '。')
    fam = wv.groupby(['fam', '形态'])['c'].sum().reset_index(); fam['月均'] = fam['c'] / 10
    fs = fam.groupby('形态')['月均'].agg(['count', 'mean', 'median'])
    P('- **Wayfair 悬浮式单链接贡献高（老文档 556 vs 落地 199）**：按家族（≈ 链接）1–10 月月均：' + '；'.join(f'{k} {int(r["count"])} 个家族，平均 {num(r["mean"])}、中位 {num(r["median"])}' for k, r in fs.iterrows()) + '。'
      + ('悬浮式平均高于落地式。' if fs.loc['悬浮式', 'mean'] > fs.loc['落地式', 'mean'] else '本样本里悬浮式的单家族月均不高于落地式。') if '悬浮式' in fs.index else '')
    fl = RES[('Wayfair', '全尺寸不分拆装')][0].set_index('框')['框月均']
    P(f'  Wayfair 全尺寸悬浮式月均 {num(fl.get("全尺寸 · 不分拆装 · 悬浮式", np.nan))}、落地式 {num(fl.get("全尺寸 · 不分拆装 · 落地式", np.nan))}；形态"悬浮式"来自标题（floating / wall-mounted），没写的按落地式，悬浮式可能被低估。')
    # 4.4 42″
    def size_share(A):
        s = A[A['尺寸段'].notna()]; return s.groupby('尺寸段')['c'].sum() / s['c'].sum(), s['c'].sum() / A['c'].sum()
    parts = []
    for nm, A_ in (('HD', AH), ("Lowe's", AL), ('Wayfair', AW), ('Amazon（4–9 月）', B)):
        sh, cv = size_share(A_)
        parts.append(f'{nm}：尺寸段已知 {pc(cv)}，不可读' if cv < 0.3 else f'{nm}：42″ {pc(sh.get("42″", 0))}（36″ {pc(sh.get("36″", 0))}、48″ {pc(sh.get("48″", 0))}；尺寸段已知 {pc(cv)}）')
    P('- **42″ 体量**（占尺寸段已知销量）：' + '；'.join(parts) + '。')
    h42 = RES[('Home Depot', '框')][0].set_index('框')
    if '42″ · 整装 · 落地式' in h42.index:
        r = h42.loc['42″ · 整装 · 落地式']
        P(f'  HD 42″ · 整装 · 落地式 框月均 {num(r["框月均"])}，季均 {num(r["季1–3"])} / {num(r["季4–6"])} / {num(r["季7–9"])} / {num(r["季10"])}，家族 {r["家族"]}、单款月均 {num(r["单款月均"])}、中位价 ${num(r["框中位价"])}。')
    P('')

    # ---------------- 五、局限
    P('## 五、局限', '',
      '1. **幸存者偏差**（见口径）：只看今天在榜的商品，涨的偏乐观、跌的偏少；新家族"进入后卖起来"的比例偏高（没卖起来的多半已不在榜）。',
      '2. **销量是评论换算**（VP × 50 + 非 VP × 20），没有按各渠道校准；Wayfair 非 VP 占 43%（Incentivized 等），换算系数对它的偏差可能更大。小单元颗粒粗。',
      '3. **Lowe\'s 标题几乎不写尺寸**（同一商品页含多个尺寸），尺寸段覆盖极低，Lowe\'s 无法按"同尺寸段"框比较，只有降级视图；"装"有一部分是业务默认值。',
      '4. **Wayfair 标题多不写装**，带"装"的框只覆盖少数商品；降级视图混了整装和拆装。Wayfair 家族多数只有一个商品页，变体尺寸以标题那个为准。',
      '5. **Lowe\'s / Wayfair 家族销量按成员商品页均分**，同一家族内不同尺寸 / 颜色的真实分布未知；HD 评论带变体 ID，没有这个问题。',
      '6. **价格只有 HD、且是采集日当天价**；评分只有 HD（窗口评论平均）。Lowe\'s / Wayfair 价格、评分写"无"。',
      '7. **元素只用文字规则**，三个渠道元素覆盖都很低（HD 约 6% 销量），元素单元基本不可读；主色 HD 约 7 成、Lowe\'s / Wayfair 见覆盖表。',
      '8. Amazon 窗口（4–9 月）与小平台（1–10 月）不同，三渠道对照只看同向与否；Amazon 拆装为主、HD / Lowe\'s 整装为主，忽略装对齐会把不同市场混在一起（跨渠道检验 §1）。',
      '9. 这是一次观察：没有回测，模式不代表之后会延续；要用作立项证据需等月度快照积累后按同法回测。', '')
    open(OLD_MD, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('写出', OLD_MD, len(L), '行')
    return RES


# ====================================================================== 5b. 报告（按框正式视图）
def cov_new(A, P_, ch):
    """分框标签与属性覆盖：按实体（HD 商品页 / Wayfair listing）、按 1–10 月销量（含 Wayfair 无月度 listing 的估算）。"""
    tot = A['c'].sum(); V = A.drop_duplicates('pid').set_index('pid'); S = A.groupby('pid')['c'].sum()
    rows = []
    def add(name, ks, kp, note=''):
        rows.append(f'| {name} | {kp.mean():.0%} | {A.loc[ks, "c"].sum() / tot:.1%} | {note} |')
    src = lambda col: '来源（按销量）：' + '、'.join(f'{k} {v:.0%}' for k, v in (A.groupby(col)['c'].sum() / tot).sort_values(ascending=False).items() if v >= 0.005)
    add('尺寸段（多尺寸未拆不算）', A['尺寸段'].notna(), V['尺寸段'].notna(), f'多尺寸未拆 {A.loc[A["多尺寸未拆"], "c"].sum() / tot:.1%}')
    add('装', A['装'] != '未知', V['装'] != '未知', src('装来源'))
    add('形态', A['形态'] != '未知', V['形态'] != '未知', src('形态来源'))
    add('**框可定（三项都定）**', frameable(A), V.index.isin(A.loc[frameable(A), 'pid']), '≥ 95% 才满足分框门槛' if frameable(A).mean() else '')
    for att in ('台面材质', '主色', '柜体材质'):
        add(att, ~A[att].astype(str).isin(UNK | {'其他'}), ~V[att].astype(str).isin(UNK | {'其他'}))
    add('元素（文字规则）', A['元素'].map(lambda e: e != ['未知']), V['元素'].map(lambda e: e != ['未知']))
    add('价格', A['价格'].notna(), V['价格'].notna(), src('价格来源') if ch == 'Home Depot' else '采集日当天价')
    add('评分', A['rn'] > 0 if ch == 'Home Depot' else A['评分'].notna(), (A.groupby('pid')['rn'].sum() > 0).reindex(V.index).values if ch == 'Home Depot' else V['评分'].notna(),
        '窗口内评论星级（按行：有评论的变体 × 月）' if ch == 'Home Depot' else '页面总评分')
    add('有逐月销量', A['m'] >= 0, V.index.isin(A.loc[A['m'] >= 0, 'pid']), '' if ch == 'Home Depot' or (A['m'] >= 0).all() else '其余 = 只有评论总数，按评论数档换算（见上）')
    return ['| 标签 | 实体覆盖 | 1–10 月销量覆盖 | 说明 |', '| :--- | ---: | ---: | :--- |'] + rows


def units_of(U, F, fr):
    return U[(U['框'] == fr) & (U['月均'] >= U_MIN)].sort_values(['属性', '月均'], ascending=[True, False])


def wf_apify_check(D):
    """Wayfair 168 个原"只有评论总数"listing 补到 Apify 逐月评论后：回看上一轮的评论数档估算准不准，并给 3 个"部分"listing 的影响。"""
    P, M = bw_raw(); p = P[(P['渠道'] == 'Wayfair') & P['浴室柜'].astype(str).str.lower().ne('false')]; m = M[M['渠道'] == 'Wayfair']
    apf = p[p['月度来源'].astype(str).str.startswith('Apify')]
    q = p[~p['fam'].isin(apf['fam'])]; fs = m[~m['fam'].isin(apf['fam'])].groupby('fam')['销量'].sum()
    act = m[m['fam'].isin(apf['fam'])].groupby('fam')['销量'].sum().reindex(apf['fam']).fillna(0)
    est = {}
    for nm, low in (('中', False), ('低', True)):
        k, bins = static_k(q, fs, low)
        est[nm] = (pd.cut(apf['页面评论数'], bins, right=True).map(k['k']).astype(float) * apf['页面评论数']).set_axis(apf['fam']).fillna(0)
    AW = D['AW']; ap = AW[AW['月度来源'].astype(str).str.startswith('Apify')]
    fr_act = ap[frameable(ap)].assign(框=lambda x: x['尺寸段'] + ' · ' + x['装'] + ' · ' + x['形态']).groupby('框')['c'].sum() / 10
    e = apf.assign(c=apf['fam'].map(est['中']), 尺寸段=apf['尺寸段'].where(~apf['多尺寸段'].astype(str).str.lower().eq('true')))
    e = e[e['尺寸段'].notna() & e['装'].notna() & e['形态'].notna()]
    fr_est = e.assign(框=e['尺寸段'] + ' · ' + e['装'] + ' · ' + e['形态']).groupby('框')['c'].sum() / 10
    part = apf[apf['月度来源'].astype(str).str.contains('部分')]
    pm = m[m['fam'].isin(part['fam'])]
    first = pm[pm['销量'] > 0].groupby('fam')['月'].min()
    return dict(n=len(apf), act=act.sum() / 10, mid=est['中'].sum() / 10, low=est['低'].sum() / 10,
                rho=act.corr(est['中'], method='spearman'), fr=pd.DataFrame({'估算（中）': fr_est, 'Apify 实测': fr_act}).fillna(0),
                part=part, part_s=pm['销量'].sum() / 10, part_first=first, part_rows=pm, nsplit=int(apf['月度来源'].astype(str).str.contains('拆尺寸').sum()),
                nmulti=int(apf['多尺寸段'].astype(str).str.lower().eq('true').sum()), rev=int((m.loc[m['fam'].isin(apf['fam']), 'VP'] + m.loc[m['fam'].isin(apf['fam']), '非VP']).sum()))


def est_section(D, ch, no):
    """Wayfair / Lowe's 的按框章节（两者都有无月度实体的估算）。Lowe's 另给"只算有月度"的覆盖与可读性。"""
    F, U = D['RES'][ch]; Fl, Fm, Um, Am = D['SENS'][ch]
    F2 = F[F['框月均'] >= FR_MIN]; U2 = U[U['框'].isin(F2['框']) & (U['月均'] >= U_MIN)]
    rd = F2['可读性'].value_counts()
    P(f'## {no}、{ch}（按框）', '',
      f'框月均 ≥ {FR_MIN} 的框 **{len(F2)} 个**（全部框 {len(F)} 个，合计月均 {num(F["框月均"].sum())}；达标框占 {pc(F2["框月均"].sum() / F["框月均"].sum())}），达标单元 **{len(U2)} 个**。'
      f'可读性：' + '、'.join(f'{k} {v} 个' for k, v in rd.items()) + '。', '',
      '"分框覆盖"把没进框的销量（多尺寸未拆、形态 / 装未知）按"已知维度一致"可能落到的框分摊（多尺寸实体只分到它选项里有的尺寸段）：**期望** = 按这些框已落框销量的比例分摊，**最坏** = 全部算给本框。期望 < 95% 的框，体量和份额都可能明显变化，只给方向参考。', '')
    if ch == LW:
        m2 = F2.set_index('框')
        P('**Lowe\'s 的覆盖缺口几乎全部来自估算部分**：两词独有、无月度的家族多数是多尺寸父体（拆不到尺寸段），它们的估算销量按选项尺寸段分摊后压低了所有框的覆盖。'
          '只看有月度的部分（类目 Best Sellers 两榜家族，尺寸段已按评论变体宽度拆开）时，分框覆盖和可读性见表最后两列。'
          '**本页 Lowe\'s 的框内结论以"只算有月度"口径为准**（单元表和模式观察用有月度的销量），含估算的体量只作参考。', '')
        P(*frame_table(F2, cover=True, tot=F['框月均'].sum()), '')
        P('| 框 | 只算有月度：月均 | 分框覆盖（期望） | 可读性 |', '| :--- | ---: | ---: | :--- |',
          *[f'| {k} | {num(Fm.set_index("框")["框月均"].get(k, np.nan))} | {pc(m2.at[k, "分框覆盖_期望_只算有月度"], 1)} | {m2.at[k, "可读性_只算有月度"]} |' for k in F2.sort_values('框月均', ascending=False)['框']], '')
    else:
        P(*frame_table(F2, cover=True, tot=F['框月均'].sum()), '')
    if ch == 'Wayfair' and 'APF' in D:
        AC = D['APF']; T = AC['fr'].reindex(F2.sort_values('框月均', ascending=False)['框']).fillna(0)
        P(f'### {no}.2 估算回看：上一轮评论数档估算 vs Apify 实测（{AC["n"]} 个原无月度 listing）', '',
          f'渠道合计：中估计月均 {num(AC["mid"])}、低估计 {num(AC["low"])}、Apify 实测 {num(AC["act"])}；listing 级 Spearman {AC["rho"]:.2f}。按框（估算时多尺寸 listing 不进框，实测已按评论选项拆尺寸）：', '',
          '| 框 | 估算（中） | Apify 实测 | 本框现月均 | 实测占本框 |', '| :--- | ---: | ---: | ---: | ---: |',
          *[f'| {k} | {num(r["估算（中）"])} | {num(r["Apify 实测"])} | {num(F2.set_index("框").at[k, "框月均"])} | {pc(r["Apify 实测"] / F2.set_index("框").at[k, "框月均"])} |' for k, r in T.iterrows()], '')
    else:
        _est_sens(D, ch, no, F, F2, Fl, Fm)
    _est_units(D, ch, no, F, U, F2, U2, Fm, Um)


def _est_sens(D, ch, no, F, F2, Fl, Fm):
    S3 = pd.DataFrame({'中': F.set_index('框')['框月均'], '低': Fl.set_index('框')['框月均'], '仅有月度': Fm.set_index('框')['框月均']}).reindex(F2['框'])
    for c in ('中', '低', '仅有月度'): S3[c + '名次'] = S3[c].rank(ascending=False)
    S3 = S3.sort_values('中', ascending=False)
    rows = [f'| {k} | {num(r["中"])} | {int(r["中名次"])} | ' + (f'{num(r["低"])} | {int(r["低名次"])} | ' if ch == 'Wayfair' else '') + f'{num(r["仅有月度"])} | {int(r["仅有月度名次"]) if r["仅有月度名次"] == r["仅有月度名次"] else "—"} |' for k, r in S3.iterrows()]
    P(f'### {no}.2 敏感性：无月度实体的估算口径', '',
      '| 框 | 月均（中估计） | 名次 | ' + ('月均（低估计） | 名次 | ' if ch == 'Wayfair' else '') + '月均（只算有月度） | 名次 |', '| :--- | ---: | ---: |' + (' ---: | ---: |' if ch == 'Wayfair' else '') + ' ---: | ---: |',
      *rows, '', (f'名次相关（Spearman）：中 vs 低 {S3["中"].corr(S3["低"], method="spearman"):.2f}、' if ch == 'Wayfair' else '') + f'中 vs 只算有月度 {S3["中"].corr(S3["仅有月度"], method="spearman"):.2f}。', '')


def _est_units(D, ch, no, F, U, F2, U2, Fm, Um):
    P(f'### {no}.3 单元', '')
    if ch == LW:
        Fm2 = Fm[Fm['框月均'] >= FR_MIN]; okm = Fm2.loc[Fm2['可读性'] == '可读', '框']
        Um2 = Um[Um['框'].isin(Fm2['框']) & (Um['月均'] >= U_MIN)]
        P(f'只算有月度时达标框 {len(Fm2)} 个、达标单元 {len(Um2)} 个，其中可读框 {len(okm)} 个。下面列可读框里体量最大的 6 个（单元数字只用有月度的销量）。', '')
        for fr in Fm2[Fm2['框'].isin(okm)].sort_values('框月均', ascending=False)['框'].head(6):
            P(f'**{fr}**（只算有月度的框月均 {num(Fm2.set_index("框").at[fr, "框月均"])}）', '', *unit_table(units_of(Um, Fm2, fr), True, True), '')
        P(f'**模式观察（Lowe\'s，只算有月度、可读框：{"、".join(okm)}）**：条件同 HD（评分用页面总评分，"评论 ≥ 20"指页面评论数）。', '',
          *patterns(Um2[Um2['框'].isin(okm)], LW, True, True))
        D['ULm2'] = Um2; D['FLm2'] = Fm2
        return
    shown = [fr for fr in F2.sort_values('框月均', ascending=False)['框'] if F2.set_index('框').at[fr, '可读性'] != '不下结论（分框覆盖 < 95%）']
    rest = [fr for fr in F2.sort_values('框月均', ascending=False)['框'] if fr not in shown][:4]
    for fr in shown + rest:
        r = F2.set_index('框').loc[fr]
        P(f'**{fr}**（框月均 {num(r["框月均"])}；{r["可读性"]}）', '', *unit_table(units_of(U, F2, fr), True, True, has_static=bool((D['AW']['m'] < 0).any())), '')
    P(f'上面列分框覆盖 ≥ 95% 的框和体量最大的 {len(rest)} 个"不下结论"框；其余见全量 CSV。', '')
    okW = F2.loc[F2['可读性'] == '可读', '框']; okS = F2.loc[F2['可读性'] != '不下结论（分框覆盖 < 95%）', '框']
    P(f'**模式观察（{ch}）**：条件同 HD（评分用页面总评分，"评论 ≥ 20"指页面评论数）。份额趋势类只在可读框（{"、".join(okW)}），只用有月度的销量；评分、溢价类在分框覆盖 ≥ 95% 的框（{"、".join(okS)}）。', '',
      *patterns(U2[U2['框'].isin(okW)], ch, False, False), *patterns(U2[U2['框'].isin(okS)], ch, True, True, trend=False))


def report(D, CHKD):
    AH, AW, PH, PW, KW = D['AH'], D['AW'], D['PH'], D['PW'], D['KW']
    RES, REC, SMP, DIFF, PEND = D['RES'], D['REC'], D['SMP'], D['DIFF'], D['PEND']
    FH, UH = RES['Home Depot']; FW, UW = RES['Wayfair']
    FH2, FW2 = FH[FH['框月均'] >= FR_MIN], FW[FW['框月均'] >= FR_MIN]
    UH2 = UH[UH['框'].isin(FH2['框']) & (UH['月均'] >= U_MIN)]; UW2 = UW[UW['框'].isin(FW2['框']) & (UW['月均'] >= U_MIN)]
    D.update(FH2=FH2, FW2=FW2, UH2=UH2, UW2=UW2)
    totH, totW = AH['c'].sum() / 10, AW['c'].sum() / 10
    wm = AW[AW['m'] >= 0]['c'].sum() / 10; wst = AW[AW['m'] < 0]['c'].sum() / 10; wstl = AW[AW['m'] < 0]['c_low'].sum() / 10
    nW = AW.drop_duplicates('fam').groupby('月度来源').size()
    P0 = bw_raw()[0]; nonvan = int(((P0['渠道'] == 'Wayfair') & (P0['浴室柜'].astype(str).str.lower() == 'false')).sum())
    AL, PL, KL = D['AL'], D['PL'], D['KL']; FL, UL = RES[LW]
    nonvanL = int(((P0['渠道'] == LW) & (P0['浴室柜'].astype(str).str.lower() == 'false')).sum())
    lm = AL[AL['m'] >= 0]['c'].sum() / 10; lst = AL[AL['m'] < 0]['c'].sum() / 10; nLst = AL.loc[AL['m'] < 0, 'fam'].nunique()
    Fm_ = D['SENS'][LW][1]; Um_ = D['SENS'][LW][2]; FLm2 = Fm_[Fm_['框月均'] >= FR_MIN]
    D.update(FLm2=FLm2, ULm2=Um_[Um_['框'].isin(FLm2['框']) & (Um_['月均'] >= U_MIN)], FL2=FL[FL['框月均'] >= FR_MIN])
    P('# 小平台调研：单元 × 指标（按框：Home Depot / Wayfair / Lowe\'s）', '',
      '> 由 `solution-v2/trial/小平台调研_单元指标.py` 生成（`python3 小平台调研_单元指标.py`），数字都是脚本实际运行结果。本页是**观察分析**，不是回测，不下立项结论。'
      '全量表在 `input/data_v2/渠道调研/`（不入库）：单元表 `小平台调研_按框_单元指标_全量.csv`、框表 `小平台调研_按框_框_全量.csv`、待人工确认清单 `小平台调研_待人工确认.csv`、抽检样本 `小平台调研_按框_抽检样本.csv`。'
      '上一版（HD 类目 Top Sellers + Lowe\'s / Wayfair 降级视图）用 `python3 小平台调研_单元指标.py 上一版` 可重跑，输出到 `input/data_v2/渠道调研/小平台调研_上一版_降级视图.md`；差异见 §八。', '')
    # ---------------- 一、口径
    P('## 一、口径', '',
      '**叫法**（wen 2026-11-04）：框 = 尺寸段 × 拆装 × 形态；属性 = 台面材质 / 元素 / 主色 / 柜体材质；取值 = 属性的值；单元（表的一行）= 框 × 属性取值；指标（表的一列）= 观察的数据维度；模式 = 指标组合成的信号。'
      '**一切比较只在同一框、同一渠道内**；三渠道对照（§五）只比同框内的结构和方向，不比绝对销量。', '',
      '**商品范围与销量**（数据整理见 `大词抓取_三平台.md`，表 `input/data_v2/渠道关键词/大词/三平台_商品表.csv`、`三平台_月销表.csv`）', '',
      f'- 每个平台 = "bathroom vanity" + "bathroom vanity with sink" 自然位前 300 并集 + wen 渠道VP 表类目节点商品（HD 两类目各 100、Lowe\'s 两个 Best Sellers 榜各 100、Wayfair 主类目 200 + 无台面 50），合并去重（HD 按评论家族，Lowe\'s 按父体，Wayfair 按 listing）。销量 = 2026-01 至 10 月逐月评论 VP × 50 + 非 VP × 20；11 月不完整不计。',
      f'- **Home Depot**：{PH["fam"].nunique()} 个评论家族、{len(PH)} 个变体（含评论里出现的同家族其他尺寸 / 颜色），1–10 月有销量的家族 {AH.loc[AH["c"] > 0, "fam"].nunique()} 个；月度全部来自变体级评论（类目节点家族用 HD 回测小试的评论缓存，两词独有家族本次直连补抓），月均 **{num(totH)}** 件。'
      '价格 = 采集日商品页 / 列表价，评论里出现、没有列表价的变体用同家族同尺寸段已知价补（再退到同家族）；评分 = 窗口内评论星级平均（同上一版）。',
      f'- **Wayfair**：{len(PW)} 个浴室柜 listing（标题不含 vanity 的 {nonvan} 个剔除），其中 {AW["fam"].nunique()} 个有销量（含估算）。逐月销量来源：渠道VP 表 {nW.get("渠道VP表（家族合计）", 0)} 个（家族合计，多尺寸的按商品页内嵌评论的 Overall Width 选项分布拆到尺寸段）、商品页内嵌全部评论 {nW.get("商品页内嵌评论（全部）", 0)} 个；'
      + (f'**只有评论总数、没有月度的 {nW.get(NOMON, 0)} 个**（评论翻页接口经 BD 返回 400）；' if nW.get(NOMON, 0) else
         f'**Apify 补抓逐月评论 {sum(v for k, v in nW.items() if str(k).startswith("Apify"))} 个**（原"只有评论总数"的两词独有 listing，2026-11-04 用 Apify abotapi/wayfair-scraper 补到 2026-01–10 逐月评论，VP 口径相同；多尺寸的按评论 purchasedOptions 宽度分布拆到尺寸段，同 Lowe\'s）；') +
      f'其余 {len(PW) - AW["fam"].nunique()} 个没有销量（零评论 {int(PW["月度来源"].isna().sum())} 个，评论都在 2026 年以前 {len(PW) - AW["fam"].nunique() - int(PW["月度来源"].isna().sum())} 个）。'
      f'有月度部分月均 {num(wm)} 件。价格 = 采集日商品页价；评分 = 页面总评分（按页面评论数加权，HD 与 Wayfair 口径不同，只在同渠道内比）。',
      f'- **Lowe\'s**（补数后，2026-11-04 第二轮）：{len(PL)} 个浴室柜父体（标题不含 vanity 的 {nonvanL} 个剔除）。逐月销量只有类目节点（两个 Best Sellers 榜）家族：渠道VP 表家族合计，按 BD 评论页每条评论的变体宽度拆到尺寸段（至少 5 条带宽度的评论才拆），有月度部分月均 {num(lm)} 件；'
      f'**两词独有、有评论的 {nLst} 个家族没有月度**（Lowe\'s 对 BD 连续拦截，评论页没抓到，约占范围内页面评论的两成）。装来自商品页 Assembly / RTA 规格和标题，**不再用上一版"100% 整装"业务默认**，判断不了记未知。价格、评分 = 采集日商品页（页面总评分）。', '')
    kt = KW['中']; kl = KW['低']
    if wst > 0:
        P(f'**Wayfair 无月度 listing 怎么进静态指标**：这些 listing 都来自两词搜索结果，用同样来自搜索结果（来源 = 两词 / 两者）、有月度的 listing，按页面评论数分档算"1–10 月销量 ÷ 页面评论数"，乘到无月度 listing 的页面评论数上，作为它们 1–10 月销量的**估算**：'
          + '；'.join(f'{"> " + str(int(i.left)) if not np.isfinite(i.right) else f"{int(i.left) + 1}–{int(i.right)}"} 条评论 {r.k:.1f}（{int(r.n)} 个）' for i, r in kt.iterrows()) +
          f'。合计月均 **{num(wst)}** 件，占 Wayfair 估算总量 {pc(wst / (wm + wst))}，**比例很大**。'
          f'评论多的老 listing 2026 年评论占比低，而"两词独有"的有月度 listing 里 > 100 条评论的只有 {int(kl.iloc[-1].n)} 个、换算系数只有 {kl.iloc[-1].k:.1f}（中估计同档 {kt.iloc[2].k:.1f} / {kt.iloc[3].k:.1f}），所以另给**低估计**（只用两词独有 listing 的系数）：无月度部分月均 {num(wstl)} 件。'
          '规则：体量、份额、家族数、价格、评分用中估计（含无月度 listing）；季度份额、近 3−前 3、斜率、走势、CV、新家族只用有月度的销量；框表给出"有月度占比"，单元表给出"仅有月度的份额"，§四.2 给出三种口径下的框月均。', '')
    else:
        AC = wf_apify_check(D); D['APF'] = AC
        P(f'**Wayfair 不再有估算**：上一轮 168 个只有评论总数的 listing 已用 Apify 补到逐月评论（{AC["n"]} 个，2026 年 1–10 月评论 {num(AC["rev"])} 条，与 `wayfair_apify/Wayfair补评论_月度.csv` 合计一致），月均 **{num(AC["act"])}** 件。'
          f'回看上一轮的评论数档估算：中估计 {num(AC["mid"])}、低估计 {num(AC["low"])}，实测落在中估计的 {pc(AC["act"] / AC["mid"])}，listing 级 Spearman {AC["rho"]:.2f}（§四.2 有分框对比）。'
          f'其中 {AC["nmulti"]} 个多尺寸 listing、{AC["nsplit"]} 个按评论选项宽度拆到了尺寸段，其余记"多尺寸未拆"进待确认清单。'
          f'**{len(AC["part"])} 个"部分"listing**（只抓到最近 100 条，2026 年更早的评论缺）1–10 月合计月均 {num(AC["part_s"])} 件，占 Wayfair {pc(AC["part_s"] / (wm + wst), 1)}；它们最早有评论的月份是 '
          + '、'.join(f'{fm}（{v}）' for fm, v in AC['part_first'].items()) + '，早月份偏低会让所在框的份额趋势偏"涨"，影响见 §九。', '')
    klc = KL['中']
    P(f'**Lowe\'s 无月度家族的处理（与 Wayfair 同法，择"估算后只进静态指标"）**：用来源 = 两词 / 两者、有月度的家族按页面评论数分档算换算系数（Lowe\'s 有月度的两词来源家族都是"两者"，即同时在 Best Sellers 榜上）：'
      + '；'.join(f'{"> " + str(int(i.left)) if not np.isfinite(i.right) else f"{int(i.left) + 1}–{int(i.right)}"} 条评论 {r.k:.1f}（{int(r.n)} 个）' for i, r in klc.iterrows()) +
      f'。估算月均 **{num(lst)}** 件，占 Lowe\'s 估算总量 {pc(lst / (lm + lst))}。校准样本都是榜上商品，系数大概率偏高；又没有"两词独有"的有月度家族可做低估计，所以低估计 = 不计（只算有月度）。'
      '这些家族多数是多尺寸父体，估算销量拆不到尺寸段，只进渠道级体量和"分框覆盖"的分母。**Lowe\'s 框内结论以"只算有月度"为准**（§六）。', '')
    P('**分框**：尺寸段用商品页宽度（Wayfair Overall Width，HD Product / Cabinet Width），标题兜底；装：HD 规格 Assembled，Wayfair Assembly 字段，**"Partially Assembled" 算拆装**（wen 2026-11-04 确认，与系统规格规则同）；形态：HD Vanity Type、Wayfair Mounting / Installation，标题兜底；同家族已知值补装、形态。'
      '**判断不了的记未知、不进框**（上一版 HD 形态没写的默认落地式，这一版不默认），单列待人工确认清单。'
      '**分框口径 revision 10**（wen 2026-11-05）：尺寸段新增 28″（26 ≤ 宽 < 29），30″ 改为 29 ≤ 宽 < 33，24″ 为 21 ≤ 宽 < 26，其余不变；形态改为落地式 / 悬浮式 / 开放式，开放式 = 落地式里标题、规格或卖点写了不带门的开放层板（open shelf / open storage / open cubes / console 等，规则同 `卖家精灵导出_打标.py` 第 5 点）。'
      'Amazon 对照同口径（宽度按新尺寸段重分，柜体结构 = 开放式的落地式记开放式）。系统侧 tag_rules.size_bands 改完后以系统边界为准。多尺寸 listing 拆不到尺寸段的（"多尺寸未拆"）也不进框。', '')
    pend = PEND.groupby(['渠道', '原因']).agg(n=('pid', 'size'), s=('销量1_10月', 'sum'), r=('占渠道销量', 'sum')).reset_index()
    P('**待人工确认清单**（`input/data_v2/渠道调研/小平台调研_待人工确认.csv`，按 1–10 月销量从大到小）：', '',
      '| 渠道 | 原因 | 商品数 | 1–10 月销量 | 占渠道销量 |', '| :--- | :--- | ---: | ---: | ---: |',
      *[f'| {r.渠道} | {r.原因} | {r.n} | {num(r.s)} | {pc(r.r, 1)} |' for r in pend.itertuples()],
      *[f'| **{ch} 合计** | | **{g["pid"].nunique()}** | **{num(g["销量1_10月"].sum())}** | **{pc(g["占渠道销量"].sum(), 1)}** |' for ch, g in PEND.groupby('渠道')], '')
    P('**指标**（每个单元一行，与上一版相同）', '',
      '- 体量：月均 = 1–10 月估算销量 ÷ 10；份额 = 单元销量 ÷ **整框**销量（分母含该属性未知的部分，同一框同一属性的份额加起来 = 该属性已知占比，框表里给出）。',
      f'- 趋势：季度份额（1–3 / 4–6 / 7–9 / 10 月，CSV 有逐月）；近 3−前 3 = 8–10 月份额 − 1–3 月份额（百分点）；斜率 = 10 个月份额的线性斜率（百分点 / 月）；走势 = 份额 ln(近 3 ÷ 前 3) ≥ {LN} 记"抢份额"、≤ −{LN} 记"丢份额"、其余"随框"，括号是框本身近 3 ÷ 前 3（≥ 1.15 框涨、≤ 0.87 框跌），后两个数 = 单元销量、框销量各自的近 3 ÷ 前 3；CV = 月销变异系数。',
      '- 新家族：HD = 家族首条评论在 2026 年；Wayfair / Lowe\'s = 页面累计评论数 ≤ 2026 年 1–10 月评论数（所有评论都在窗口内，无月度 listing 判断不了、记非新）；"卖起来" = 进入月到 10 月在该单元的月均 ≥ 同框单款月均；占比 = 新家族在单元销量里的占比，括号是同框。',
      '- 供给：家族 = 单元里有销量的家族数（Wayfair 一个 listing 算一个家族）；单款 ÷ 同框 = 单元每家族月均 ÷ 同框每家族月均。价格带 = 按销量加权 P25–P75；溢价 = 单元加权中位价 ÷ 同框加权中位价。评分：单元评分与同框评分的差。',
      '- Amazon 对照（同上一版）：Amazon 第二轮统一打标表 2026-04 至 09，同尺寸段 × 形态 × 取值（**不分拆装**）的家族数 · 价位段数 · 框内份额 4–6 → 7–9 月，箭头按 ln 变化 ±0.2。', '',
      f'**门槛**（同上一版）：框月均 ≥ {FR_MIN} 件、单元月均 ≥ {U_MIN} 件才列。1 条 VP 评论 = 50 件，月均 20 件的单元 10 个月只有约 4 条 VP 评论，小单元的趋势和 CV 噪声很大，家族数 1–2 的单元基本是单个产品的走势。'
      '**可读性**（这一版新加）：框的分框覆盖（期望）≥ 95% 才在框内下结论，趋势类指标还要求有月度的销量 ≥ 60%（见 §四、§六）。', '',
      '**幸存者偏差**（同上一版）：都是"今天在榜 / 在搜索前 300"的商品往回看，早月份框销量偏低，"框在涨""份额在涨"偏乐观、"份额在跌"偏少；新家族"卖起来"的比例偏高。', '')
    # 核对
    r0, r1, r2 = REC.iloc[0], REC.iloc[1], REC.iloc[2]
    P('### 核对', '',
      '| 渠道 | 月销表销量（1–10 月） | 按 VP × 50 + 非VP × 20 重算 | 类目节点部分 1–10 月评论（VP / 非VP） | 渠道VP 表「渠道月度汇总」去重小计（VP / 非VP） | 「商品月度明细」按家族去重 | 差 |',
      '| :--- | ---: | ---: | :--- | :--- | ---: | :--- |',
      *[f'| {r.渠道} | {num(r.月销表销量)} | {num(r.重算)} | {num(r.类目节点VP + r.类目节点非VP)}（{num(r.类目节点VP)} / {num(r.类目节点非VP)}） | {num(r.表合计)}（{num(r.表VP)} / {num(r.表非VP)}） | {num(r.明细家族去重)} | '
        f'对小计 {(r.类目节点VP + r.类目节点非VP) / r.表合计 - 1:+.1%} |' for r in REC.itertuples()], '',
      f'- 重算的渠道销量与月销表一致（HD {num(r0.重算)}、Wayfair {num(r1.重算)}）。本报告读入后再剔除非浴室柜：Wayfair 有月度部分 {num(AW[AW["m"] >= 0]["c"].sum())}。',
      f'- **Wayfair** 类目节点部分 {num(r1.类目节点VP + r1.类目节点非VP)} 条 = 「商品月度明细」按家族去重的 {num(r1.明细家族去重)} 条（完全一致）；比按评论 ID 去重的小计 {num(r1.表合计)} 多 {(r1.类目节点VP + r1.类目节点非VP) / r1.表合计 - 1:.1%}：同系列 listing 部分共享评论，按"序列相同"合家族去不掉这部分（上一版已说明）。',
      f'- **Home Depot** 类目节点家族 {num(r0.类目节点VP + r0.类目节点非VP)} 条，比小计 {num(r0.表合计)} 少 {1 - (r0.类目节点VP + r0.类目节点非VP) / r0.表合计:.1%}：少的部分主要是"柜体 + 台面"组合商品（如 Winsome 组合）的评论挂在组件商品页上，组件商品页属于两词范围里的另一个家族，评论按 ID 去重后算到那个家族，不是丢失。'
      '核对中发现并修正了整理脚本的一处漏计：评论缓存里的评论只落在"未列出的变体"上时整份文件被跳过（范围内 16 个家族、157 条评论、6,680 件，含 2 个类目节点家族），已改为按缓存文件名归家族（`大词抓取_三平台整理.py` build_hd 一行），HD 月销表从 200,070 变为 '
      f'{num(r0.重算)}（Lowe\'s 补数时两张表整体重建，已含此修正，HD 行与修正后一致）。',
      f'- **Lowe\'s** 类目节点（= 全部有月度部分）{num(r2.类目节点VP + r2.类目节点非VP)} 条 = 「商品月度明细」按家族去重的 {num(r2.明细家族去重)} 条，比按评论 ID 去重的小计 {num(r2.表合计)} 多 {num(r2.类目节点VP + r2.类目节点非VP - r2.表合计)} 条；拆到尺寸段后销量合计 {num(r2.重算)} 不变。', '')
    P('**抽检**：按 1–10 月销量加权、固定种子随机抽能落框的商品（HD 2、Wayfair 3；Lowe\'s 补数后追加 2 个，按"父体 × 尺寸段"抽），对商品页原始规格手核分框标签：', '',
      '| 渠道 | 商品 | 标题 | 分框标签 | 标签来源 | 商品页原始规格 | 手核 |', '| :--- | :--- | :--- | :--- | :--- | :--- | :--- |',
      *[f'| {r.渠道} | {r.pid} | {r.title} | {r.标签} | {r.来源} | {r.原始规格} | {CHKD.get(str(r.pid), "未手核")} |' for r in SMP.itertuples()], '')
    P('### 打标覆盖', '')
    for ch, (A, P_) in {'Home Depot': (AH, PH), 'Wayfair': (AW, PW), LW: (AL, PL)}.items():
        P(f'**{ch}**', '', *cov_new(A, P_, ch), '')
    fH, fW = frameable(AH), frameable(AW)
    P(f'**分框标签覆盖率**：HD 框可定 {pc(AH.loc[fH, "c"].sum() / AH["c"].sum(), 1)}（≥ 95%）；**Wayfair {pc(AW.loc[fW, "c"].sum() / AW["c"].sum(), 1)}（< 95%）**，'
      f'缺口 = 多尺寸未拆 {pc(AW.loc[AW["多尺寸未拆"], "c"].sum() / AW["c"].sum(), 1)}、形态未知 {pc(AW.loc[AW["形态"] == "未知", "c"].sum() / AW["c"].sum(), 1)}、装未知 {pc(AW.loc[AW["装"] == "未知", "c"].sum() / AW["c"].sum(), 1)}（有重叠）。'
      'Wayfair 哪些框能下结论按框看（§四），整体不满足 95%。'
      f'**Lowe\'s 含估算 {pc(AL.loc[frameable(AL), "c"].sum() / AL["c"].sum(), 1)}（< 95%）**，缺口几乎都是无月度家族的估算销量拆不到尺寸段（多尺寸未拆 {pc(AL.loc[AL["多尺寸未拆"], "c"].sum() / AL["c"].sum(), 1)}）；'
      f'只算有月度 {pc(AL.loc[frameable(AL) & (AL["m"] >= 0), "c"].sum() / AL.loc[AL["m"] >= 0, "c"].sum(), 1)}（≥ 95%）。', '')
    # ---------------- 二、关键发现
    P('## 二、关键发现', '', *findings(D), '')
    # ---------------- 三、HD
    P('## 三、Home Depot（按框）', '',
      f'框月均 ≥ {FR_MIN} 的框 **{len(FH2)} 个**（全部框 {len(FH)} 个，合计月均 {num(FH["框月均"].sum())}；达标框占 {pc(FH2["框月均"].sum() / FH["框月均"].sum())}），达标单元 **{len(UH2)} 个**。'
      '渠道内份额的分母 = 全部能落框的销量。', '', *frame_table(FH2, cover=True, tot=FH['框月均'].sum()), '')
    for fr in FH2.sort_values('框月均', ascending=False)['框'].head(6):
        P(f'**{fr}**（框月均 {num(FH2.set_index("框").at[fr, "框月均"])}）', '', *unit_table(units_of(UH, FH2, fr), True, True), '')
    P(f'其余 {len(FH2) - 6} 个达标框的单元见全量 CSV。', '')
    P(f'**模式观察（HD，所有达标框）**：条件 —— 份额在涨 / 跌：ln(近 3 ÷ 前 3 份额) ≥ {LN} / ≤ −{LN}；新家族进入：有新家族且新家族销量占比高于同框；评分低于同框：差 ≤ −0.15、单款 ÷ 同框 ≥ 1、窗口评论 ≥ 20 条；高溢价：溢价 ≥ 1.3。只陈述事实，排序按 月均 × |份额 ln 变化|。', '',
      *patterns(UH2, 'Home Depot', True, True))
    # ---------------- 四、Wayfair / 五、对照 / 六、Lowe's
    est_section(D, 'Wayfair', '四')
    P('## 五、三渠道同框对照（+ Amazon，只比结构和方向）', '', *compare_hw(D), '')
    est_section(D, LW, '六')
    # ---------------- 七、老文档
    P('## 七、对 wen 老文档判断的核对（只给事实）', '', *old_doc(D), '')
    # ---------------- 八、差异
    P('## 八、和上一版的差异', '', *diff_old(D), '')
    # ---------------- 九、局限
    P('## 九、局限', '',
      (f'1. **Wayfair 约 4 成销量是估算**：{nW.get(NOMON, 0)} 个只有评论总数的 listing 按评论数档换算，中估计与低估计差 {num(wst - wstl)} 件 / 月；体量排名受影响的框见 §四.2。趋势只用有月度的部分，有月度 < 60% 的框不读趋势。' if wst > 0 else
       f'1. **Wayfair 已全部是逐月评论**（Apify 补抓 {D["APF"]["n"]} 个 listing）。其中 {len(D["APF"]["part"])} 个"部分"listing 只抓到最近 100 条评论、2026 年早月份缺，1–10 月合计月均 {num(D["APF"]["part_s"])} 件（占 Wayfair {pc(D["APF"]["part_s"] / (wm + wst), 1)}），所在框（'
       + '、'.join(sorted({f"{r.尺寸段} · {r.装} · {r.形态}" for r in D["APF"]["part_rows"].itertuples() if isinstance(r.尺寸段, str) and r.尺寸段 != "多尺寸未拆"})) + '）的份额趋势会略偏"涨"；这几个框都是"不下结论"框，不进本页的趋势结论；占渠道不到 2%，不改变框排序。'),
      f'2. **Wayfair 分框覆盖 {pc(AW.loc[fW, "c"].sum() / AW["c"].sum())} < 95%**：多尺寸 listing 拆不到尺寸段、规格里没写安装方式的 listing 记形态未知；按框看，期望覆盖 ≥ 95% 的只有 {int((FW2['可读性'] != '不下结论（分框覆盖 < 95%）').sum())} 个达标框，其余只给方向参考。待人工确认清单补完后可提高。',
      f'2b. **Lowe\'s 只有 Best Sellers 两榜家族有月度**：两词独有的 {nLst} 个家族（约两成页面评论）没有月度，估算月均 {num(lst)} 件且拆不到尺寸段；框内结论只代表"榜上家族"的结构。Lowe\'s 补规格还缺 25 个商品、15 个类目家族评论不完整（`大词抓取_三平台.md` §6）。',
      '3. **销量是评论换算**（VP × 50 + 非 VP × 20），没有按渠道校准；Wayfair 非 VP 占比高（激励评论、Pro 会员评论计非 VP），系数偏差可能更大。小单元颗粒粗。',
      '4. **Wayfair 多尺寸 listing 的尺寸拆分**只用内嵌评论里写了 Overall Width 的评论比例（≥ 5 条才拆）；HD 评论带变体 ID，没有这个问题。',
      '5. **评分口径不同**：HD = 窗口内评论星级，Wayfair / Lowe\'s = 页面总评分；只在同渠道同框里比。价格都是采集日当天价，套到整个窗口。',
      '6. **元素只用文字规则**，三个渠道元素覆盖都很低（HD 约 5%、Wayfair 约 1% 销量），元素单元基本不可读；Wayfair 主色覆盖约一半。',
      '7. **范围变了**：HD 从"类目 Top Sellers 前 300"改为"两词前 300 + 类目前 100"，与上一版的框数字不完全可比（§八）。Amazon 对照不分拆装，窗口 4–9 月。',
      '8. **幸存者偏差**同上一版；这是一次观察，没有回测，模式不代表之后会延续。',
      '9. **开放式按文字规则判**（与 Amazon 同规则）：会把"open storage space"这类指柜内空间的写法也算成开放层板（例：Lowe\'s 5017604281，带门柜，月均 333 件被判开放式），开放式框和它所在尺寸段的落地式框都可能有误差，需人工确认。', '')


def compare_hw(D):
    FH2, FW2, UH, UW, AZs = D['FH2'], D['FW2'], D['RES']['Home Depot'][1], D['RES']['Wayfair'][1], D['AZs']
    FL = D['RES'][LW][0]; FLm2, ULm = D['FLm2'], D['SENS'][LW][2]
    h, w, l, lm = FH2.set_index('框'), FW2.set_index('框'), FL.set_index('框'), FLm2.set_index('框')
    allf = sorted(set(FH2['框']) | set(FW2['框']) | set(FLm2['框']), key=lambda k: -(h['框月均'].get(k, 0) + w['框月均'].get(k, 0) + lm['框月均'].get(k, 0)))
    short = {'可读': '可读', '体量 / 份额可看，趋势不下结论（有月度 < 60%）': '趋势不读', '不下结论（分框覆盖 < 95%）': '不下结论'}
    cell = lambda T, k, rd=None: '—' if k not in T.index else f"{num(T.at[k, '框月均'])} · {T.at[k, '家族']} · {num(T.at[k, '单款月均'])} · ${num(T.at[k, '框中位价'])}" + (f"（{short.get(rd, rd)}）" if rd else '')
    out = [f'任一渠道达标（框月均 ≥ {FR_MIN}；Lowe\'s 按只算有月度）的框 {len(allf)} 个，三渠道都达标的 {len(set(FH2["框"]) & set(FW2["框"]) & set(FLm2["框"]))} 个。'
           '绝对销量各渠道口径不同（Wayfair 含估算，Lowe\'s 只算榜上家族），只看框内结构：单款月均、中位价、家族数。', '',
           '| 框 | HD 月均 · 家族 · 单款月均 · 中位价 | Wayfair 同（可读性） | Lowe\'s 只算有月度 同（可读性） |', '| :--- | :--- | :--- | :--- |']
    for k in allf:
        out.append(f"| {k} | {cell(h, k)} | {cell(w, k, w['可读性'].get(k))} | {cell(lm, k, lm['可读性'].get(k))} |")
    okW = set(FW2.loc[FW2['可读性'] == '可读', '框']); okS = set(FW2.loc[FW2['可读性'] != '不下结论（分框覆盖 < 95%）', '框'])
    okL = set(FLm2.loc[FLm2['可读性'] == '可读', '框'])
    sel = UH[(UH['月均'] >= U_MIN) & UH['框'].isin(FH2['框']) & (UH['属性'] != '元素')]
    W_ = UW[UW['框'].isin(FW2['框']) & (UW['月均'] >= U_MIN)].set_index(['框', '属性', '取值'])
    L_ = ULm[ULm['框'].isin(FLm2['框']) & (ULm['月均'] >= U_MIN)].set_index(['框', '属性', '取值'])
    sel = sel[sel['框'].isin(okS | okL)]
    rows, sw, sl = [], [0, 0], [0, 0]
    for r in sel.sort_values(['框', '属性', '月均'], ascending=[True, True, False]).itertuples():
        kk = (r.框, r.属性, r.取值); wr = W_.loc[kk] if kk in W_.index else None; lr = L_.loc[kk] if kk in L_.index else None
        if wr is None and lr is None: continue
        a = AZs.get((r.框.split(' · ')[0] + ' · ' + r.框.split(' · ')[2], r.属性, AZKEY(r.属性, r.取值)))
        dh = arrow(r.份额ln)
        cw = '—' if wr is None else f"{ps(wr['份额'])} {arrow(wr['份额ln'])}{'' if r.框 in okW else '*'}"
        cl = '—' if lr is None else f"{ps(lr['份额'])} {arrow(lr['份额ln'])}{'' if r.框 in okL else '*'}"
        if wr is not None and r.框 in okW: sw[1] += 1; sw[0] += arrow(wr['份额ln']) == dh
        if lr is not None and r.框 in okL: sl[1] += 1; sl[0] += arrow(lr['份额ln']) == dh
        rows.append(f"| {r.框} | {r.属性}：{r.取值} | {ps(r.份额)} {dh} | {cw} | {cl} | " + (f"{ps(a['AZ份额'])} {arrow(a['AZln'])}（{a['AZ家族']}）" if a else '无') + ' |')
    out += ['', f'**同框同取值单元**（HD 单元月均 ≥ {U_MIN}，且 Wayfair 或 Lowe\'s 至少一边也 ≥ {U_MIN}；只列 Wayfair 分框覆盖 ≥ 95% 或 Lowe\'s 可读的框；元素覆盖太低不比）：{len(rows)} 个。'
            f'格式：框内份额 方向（小平台 ln(8–10 月 ÷ 1–3 月)、Amazon ln(7–9 ÷ 4–6)，|ln| < {DIR} 记 →；Wayfair 方向只用有月度销量，Lowe\'s 全部用只算有月度）。该渠道趋势不可读的框加"*"，不计入同向统计。', '',
            '| 框 | 属性：取值 | HD 份额 方向 | Wayfair 份额 方向 | Lowe\'s 份额 方向 | Amazon 份额 方向（家族） |', '| :--- | :--- | :--- | :--- | :--- | :--- |', *rows,
            '', f'可读框里与 HD 同向：Wayfair {sw[0]}/{sw[1]}，Lowe\'s {sl[0]}/{sl[1]}（同框不同渠道的单元走势多数不一致，渠道间不能互相代替）。', '']
    # 结构
    AH, AW, AL, B = D['AH'], D['AW'], D['AL'], D['B']
    def struct(A, att):
        x = A.explode('元素') if att == '元素' else A
        x = x[~x[att].astype(str).isin(UNK | {'其他'}) & ~x[att].astype(str).str.startswith('其他（')]
        return x.groupby(att)['c'].sum() / A['c'].sum()
    out += ['**结构：各渠道取值占渠道销量的比例**（全尺寸、全形态、不分拆装，只看结构；Lowe\'s 含估算）', '']
    for att in ('台面材质', '主色', '柜体材质'):
        S = {'Home Depot': struct(AH, att), 'Wayfair': struct(AW, att), LW: struct(AL, att), 'Amazon（4–9 月）': struct(B, att)}
        vals = pd.concat(S, axis=1).fillna(0); vals = vals[vals.max(axis=1) >= 0.02].sort_values('Home Depot', ascending=False)
        out += [f'*{att}*（已知部分占渠道销量：' + '、'.join(f'{k} {v.sum():.0%}' for k, v in S.items()) + '）', '',
                '| 取值 | ' + ' | '.join(vals.columns) + ' |', '| :--- |' + ' ---: |' * len(vals.columns)]
        out += [f'| {v} | ' + ' | '.join(pc(x) for x in r.values) + ' |' for v, r in vals.iterrows()] + ['']
    return out


def old_doc(D):
    AH, AW, B = D['AH'], D['AW'], D['B']; out = []
    H = AH[frameable(AH)].copy(); H['实木类'] = H['柜体材质'].isin(['实木', '实木框架']); H['石材'] = H['台面材质'].isin(['岗石', '石英石'])
    for sz, band_ in ((['36″', '42″', '48″'], (649, 799)), (['48″', '60″'], (900, 1200))):
        g = H[H['尺寸段'].isin(sz)]; s = g[g['实木类'] & g['石材']]
        inb = s[(s['价格'] >= band_[0]) & (s['价格'] <= band_[1])]
        sp = lambda q: s.loc[s['m'].isin(q), 'c'].sum() / max(g.loc[g['m'].isin(q), 'c'].sum(), 1)
        out.append(f'- **HD {"/".join(sz)}（全部装与形态）实木 / 实木框架 × 岗石 / 石英石**：月均 {num(s["c"].sum() / 10)} 件，占这几个尺寸段 {pc(s["c"].sum() / g["c"].sum())}；份额 1–3 月 {pc(sp(PRE))} → 8–10 月 {pc(sp(REC))}；'
                   f'家族 {s.loc[s["c"] > 0, "fam"].nunique()} 个；加权中位价 ${num(wq(s["价格"], s["c"], .5))}（P25–P75 ${num(wq(s["价格"], s["c"], .25))}–{num(wq(s["价格"], s["c"], .75))}），落在 ${band_[0]}–{band_[1]} 的销量占 {pc(inb["c"].sum() / s["c"].sum())}。')
    sint = AH[AH['台面材质'] == '岩板']
    out.append(f'- **HD 岩板**：台面材质 = 岩板的销量 {num(sint["c"].sum() / 10)} 件 / 月（商品页 {sint["pid"].nunique()} 个）' + ('，老文档"岩板一体热弯盆空白"在本样本里仍成立（以标题 / 规格文字为准）。' if sint['c'].sum() == 0 else '。'))
    # Wayfair 拆装：原始 Assembly 字段
    asm = {}
    for pid in AW['pid'].unique():
        pg = HD.load_json(os.path.join(BWDIR, 'pdp', 'wayfair', f'{pid}.json')) or {}
        v = (pg.get('specs') or {}).get('Assembly') or ''
        asm[pid] = 'Partially Assembled' if v.startswith('Partially') else ('No Assembly Required' if v.startswith('No Assembly') else ('Full Assembly Needed' if v.startswith('Full') else ('其他 Assembly 值' if v else '无字段')))
    x = AW.assign(A=AW['pid'].map(asm)); t = x['c'].sum(); kn = x[x['装'] != '未知']
    dist = x.groupby('A')['c'].sum() / t
    rta = kn.loc[kn['装'] == '拆装', 'c'].sum() / kn['c'].sum(); part = kn.loc[kn['A'] == 'Partially Assembled', 'c'].sum() / kn['c'].sum()
    out.append(f'- **Wayfair 拆装 23%**：装已知的销量占 {pc(kn["c"].sum() / t)}，其中拆装 **{pc(rta)}**（含 Partially Assembled {pc(part)}；若把部分组装算整装，拆装 {pc(rta - part)}）。Assembly 原始字段按销量：' + '、'.join(f'{k} {v:.0%}' for k, v in dist.sort_values(ascending=False).items()) + '。'
               '按 wen 定的口径（部分组装算拆装），Wayfair 拆装是主流，远高于老文档的 23%；即使不算部分组装，也高于 23%。')
    cb = AW[~AW['柜体材质'].astype(str).isin(UNK | {'其他'})]
    out.append(f'- **Wayfair 实木类 83%**：柜体材质已知销量占 {pc(cb["c"].sum() / AW["c"].sum())}，其中实木 + 实木框架 {pc(cb.loc[cb["柜体材质"].isin(["实木", "实木框架"]), "c"].sum() / cb["c"].sum())}；分布：'
               + '、'.join(f'{k} {v:.0%}' for k, v in (cb.groupby('柜体材质')['c'].sum() / cb['c'].sum()).sort_values(ascending=False).items() if v >= 0.02) + '（Base Material 常写"Solid + Manufactured Wood"，规则按含人造板归类，口径与老文档可能不同）。')
    fam = AW[AW['形态'] != '未知'].groupby(['fam', '形态'])['c'].sum().reset_index(); fam['月均'] = fam['c'] / 10
    fs = fam.groupby('形态')['月均'].agg(['count', 'mean', 'median'])
    out.append('- **Wayfair 悬浮式单链接贡献高（老文档 556 vs 落地 199）**：按 listing 1–10 月月均：' + '；'.join(f'{k} {int(r["count"])} 个，平均 {num(r["mean"])}、中位 {num(r["median"])}' for k, r in fs.iterrows()) + '。'
               + (('悬浮式平均高于落地式。' if fs.loc['悬浮式', 'mean'] > fs.loc['落地式', 'mean'] else '本样本里悬浮式的单 listing 月均不高于落地式。') if '悬浮式' in fs.index else ''))
    parts = []
    for nm, A_ in (('HD', AH), ('Wayfair', AW), ('Lowe\'s（只算有月度）', D['AL'][D['AL']['m'] >= 0]), ('Amazon（4–9 月）', B)):
        s_ = A_[A_['尺寸段'].notna()]; sh = s_.groupby('尺寸段')['c'].sum() / s_['c'].sum()
        parts.append(f'{nm} 42″ {pc(sh.get("42″", 0))}（36″ {pc(sh.get("36″", 0))}、48″ {pc(sh.get("48″", 0))}）')
    out.append('- **42″ 体量**（占尺寸段已知销量）：' + '；'.join(parts) + '。')
    Lm = D['AL'][D['AL']['m'] >= 0]; tl = Lm[~Lm['台面材质'].astype(str).isin(UNK | {'不适用（不含台面）', '其他'})]
    rs = tl['台面材质'].isin(['Cultured Marble', '树脂'])
    out.append(f'- **Lowe\'s 树脂盆 81%**（只算有月度）：台面材质已知且带台面的销量占 {pc(tl["c"].sum() / Lm["c"].sum())}，其中 Cultured Marble / 树脂 {pc(tl.loc[rs, "c"].sum() / tl["c"].sum())}；其余 '
               + '、'.join(f'{k} {v:.0%}' for k, v in (tl.groupby('台面材质')['c'].sum() / tl['c'].sum()).sort_values(ascending=False).items() if k not in ('Cultured Marble', '树脂') and v >= 0.01) + '。岗石台面多配陶瓷台下盆，"树脂盆"只能按台面推。')
    for nm, X in (('只算有月度', Lm), ('含估算', D['AL'])):
        kn = X[X['装'] != '未知']
        out.append(f'- **Lowe\'s 100% 整装**（{nm}）：装已知的销量占 {pc(kn["c"].sum() / X["c"].sum(), 1)}，其中整装 {pc(kn.loc[kn["装"] == "整装", "c"].sum() / kn["c"].sum(), 1)}、拆装 {pc(kn.loc[kn["装"] == "拆装", "c"].sum() / kn["c"].sum(), 1)}（来源：商品页 Assembly / RTA 规格与标题，不再用业务默认）。')
    return out


def diff_old(D):
    FO, UO, FH, UH, S = D['FO'], D['UO'], D['RES']['Home Depot'][0], D['RES']['Home Depot'][1], D['DIFF']
    FO2 = FO[FO['框月均'] >= FR_MIN]; UO2 = UO[UO['框'].isin(FO2['框']) & (UO['月均'] >= U_MIN)]
    FH2, UH2 = D['FH2'], D['UH2']
    out = ['**Home Depot**', '',
           f'- 范围：上一版 = 两个类目 Top Sellers 各前 300 → 1–10 月有销量的家族 {S["上一版家族"]} 个、月均 {num(S["上一版月均"])}；这一版 = 两词前 300 + 类目前 100 → {S["新家族"]} 个、月均 {num(S["新月均"])}。'
           f'共同家族（有共同商品页）{S["新里沿用"]} 个；上一版有、这一版没有的 {S["上一版丢掉"]} 个（月均 {num(S["丢掉销量"])}，主要是类目第 101–300 名且不在两词前 300 的）；这一版新增 {S["新增"]} 个（月均 {num(S["新增销量"])}，两词独有）。',
           f'- 口径：形态未知不再默认落地式（不进框，HD 影响 {pc(D["AH"].loc[D["AH"]["形态"] == "未知", "c"].sum() / D["AH"]["c"].sum(), 1)}）；装同上一版（规格优先、家族补，判断不了不进框）；价格补了评论里出现的变体（同家族同尺寸段）。',
           f'- 结果：达标框 {len(FO2)} → **{len(FH2)}** 个，达标单元 {len(UO2)} → **{len(UH2)}** 个。', '',
           '| 框 | 上一版 月均 · 家族 · 近3÷前3 | 这一版 月均 · 家族 · 近3÷前3 |', '| :--- | :--- | :--- |']
    o, n = FO.set_index('框'), FH.set_index('框')
    for k in sorted(set(FO2['框']) | set(FH2['框']), key=lambda k: -n['框月均'].get(k, 0)):
        f = lambda T, k: f"{num(T.at[k, '框月均'])} · {T.at[k, '家族']} · {T.at[k, '近3'] / max(T.at[k, '前3'], 1e-9):.2f}" if k in T.index else '—'
        out.append(f'| {k} | {f(o, k)} | {f(n, k)} |')
    M = UO2.merge(UH2, on=['框', '属性', '取值'], suffixes=('_o', '_n'))
    lab = lambda x: x.split('（')[0]
    same = (M['走势_o'].map(lab) == M['走势_n'].map(lab))
    flip = M[~same & ~M['走势_o'].str.startswith('随框') & ~M['走势_n'].str.startswith('随框')]
    out += ['', f'- 两版都达标的单元 {len(M)} 个：走势标签（抢 / 丢份额 / 随框）一致 {int(same.sum())} 个（{pc(same.mean())}）；从"抢份额"翻到"丢份额"或反过来的 {len(flip)} 个'
            + ('：' + '；'.join(f'{r.框} {r.属性}：{r.取值}（{lab(r.走势_o)} → {lab(r.走势_n)}）' for r in flip.itertuples()) if len(flip) else '') + '。'
            f'份额（1–10 月）相关 {M["份额_o"].corr(M["份额_n"]):.2f}。范围变了约四成家族，趋势标签对范围敏感，单元级趋势要谨慎读。', '']
    FOW, FOWd, FW2 = D['FOW'], D['FOWd'], D['FW2']
    out += ['**Wayfair**', '',
            f'- 上一版：只有渠道VP 表（类目节点 250 个商品页）、只有标题，装覆盖约 2%，按框主视图 {int((FOW["框月均"] >= FR_MIN).sum())} 个达标框；降级视图（尺寸段 × 形态，不分拆装）{int((FOWd["框月均"] >= FR_MIN).sum())} 个；没有价格、评分。',
            f'- 这一版：加两词前 300、补商品页规格（尺寸 / 装 / 形态 / 颜色 / 材质 / 价格 / 评分），按框 **{len(FW2)}** 个达标框、**{len(D["UW2"])}** 个达标单元，有价格和评分；但分框覆盖 < 95%' + ('、约 4 成销量是估算（§四）' if (D['AW']['m'] < 0).any() else '；168 个只有评论总数的 listing 已用 Apify 补到逐月评论，不再估算（§一）') + '。',
            '- 拆装认定变了：上一版标题几乎不写装、借 wen 文档"拆装约 23%"；这一版用 Assembly 字段且部分组装算拆装，拆装是 Wayfair 主流（§七）。', '',
            '**Lowe\'s**', '',
            f'- 上一版：只有渠道VP 表、只有标题，尺寸段销量覆盖 0%，只能给"不分尺寸段 × 装（业务默认整装）× 形态"降级视图（{int((D["FOLd"]["框月均"] >= FR_MIN).sum())} 个达标"框"），不满足同尺寸段硬规则。',
            f'- 这一版：评论页按变体宽度拆到尺寸段、补商品页规格（装 / 形态 / 价格 / 评分），按框 {len(D["FL2"])} 个达标框（含估算），只算有月度 {len(D["FLm2"])} 个达标框、{len(D["ULm2"])} 个达标单元；装不再用业务默认（装已知部分整装 {pc((lambda X: X.loc[X["装"] == "整装", "c"].sum() / X.loc[X["装"] != "未知", "c"].sum())(D["AL"][D["AL"]["m"] >= 0]), 1)}，与 wen 文档"100% 整装"基本一致，见 §七）。']
    return out


def findings(D):
    """关键发现：选择是人工判断（看过全量表后挑的），数字全部从本次运行取。每条带框、数字、数据来源与局限。"""
    RES = D['RES']; FH, UH = RES['Home Depot']; FW, UW = RES['Wayfair']; UO = D['UO']
    fh, fw = FH.set_index('框'), FW.set_index('框')
    def u(U, fr, att, v):
        r = U[(U['框'] == fr) & (U['属性'] == att) & (U['取值'] == v)]
        return r.iloc[0] if len(r) else None
    sh = lambda r: f'{ps(r["份额前3"])}→{ps(r["份额近3"])}'
    out = []
    # 1 拆装 / 整装 结构
    rH = FH.loc[FH['框'].str.contains('拆装'), '框月均'].sum() / FH['框月均'].sum(); rW = FW.loc[FW['框'].str.contains('拆装'), '框月均'].sum() / FW['框月均'].sum()
    AWx = D['AW']; nost = not (AWx['m'] < 0).any()
    rWm = D['FWm'].loc[D['FWm']['框'].str.contains('拆装'), '框月均'].sum() / D['FWm']['框月均'].sum()
    k = '30″ · 拆装 · 落地式'
    FLm = D['SENS'][LW][1]; rL = FLm.loc[FLm['框'].str.contains('拆装'), '框月均'].sum() / FLm['框月均'].sum()
    out.append(f'1. **Wayfair 是拆装为主的渠道，HD、Lowe\'s 是整装为主，主力框不同。** Wayfair 能落框的销量里拆装框占 {pc(rW)}{'' if nost else f'（只算有月度的 {pc(rWm)}）'}，HD 只占 {pc(rH)}，Lowe\'s（只算有月度）{pc(rL)}；'
               f'Wayfair 最大的两个框是 24″ · 拆装 · 落地式（月均 {num(fw.at["24″ · 拆装 · 落地式", "框月均"])}）和 30″ · 拆装 · 落地式（{num(fw.at[k, "框月均"])}）{'，两个都可读' if nost else '，三种估算口径下都是前两名（§四.2）'}；'
               f'HD 最大的是 30″ / 24″ · 整装 · 落地式（{num(fh.at["30″ · 整装 · 落地式", "框月均"])} / {num(fh.at["24″ · 整装 · 落地式", "框月均"])}），同一个 30″ · 拆装 · 落地式在 HD 只有 {num(fh.at[k, "框月均"])} 件 / 月、{fh.at[k, "家族"]} 个家族。'
               '老文档"Wayfair 拆装约 23%"按现在的口径（部分组装算拆装）不成立（§七）。'
               f'*来源*：Wayfair 商品页 Assembly 字段（装覆盖 {pc(AWx.loc[AWx["装"] != "未知", "c"].sum() / AWx["c"].sum(), 1)}），' + ('销量全部来自逐月评论（含 Apify 补抓）。' if nost else '销量含无月度 listing 的估算。') + f'*局限*：Wayfair 分框覆盖 {pc(AWx.loc[frameable(AWx), "c"].sum() / AWx["c"].sum())} < 95%，24″ · 拆装 · 落地式期望覆盖 {pc(fw.at["24″ · 拆装 · 落地式", "分框覆盖_期望"], 1)}{'（≥ 95%，可读）' if fw.at["24″ · 拆装 · 落地式", "分框覆盖_期望"] >= 0.95 else '，只能说"是最大框之一"，份额细节不下结论'}；跨渠道只比结构，不比绝对销量。')
    # 2 Wayfair 30″ 拆装：低价新品抢份额、评分偏低
    w, rs, pb, sw = u(UW, k, '主色', '白'), u(UW, k, '台面材质', '树脂'), u(UW, k, '柜体材质', '含刨花板'), u(UW, k, '柜体材质', '实木框架')
    lab = lambda r: r['走势'].split('（')[0]
    d24 = u(UW, '24″ · 拆装 · 落地式', '主色', '深木')
    out.append(f'2. **Wayfair 30″ · 拆装 · 落地式（{fw.at[k, "可读性"]}，月均 {num(fw.at[k, "框月均"])}，框销量近 3 ÷ 前 3 = {fw.at[k, "近3"] / fw.at[k, "前3"]:.2f}）：低价含刨花板新品在抢份额，树脂台面在丢；卖得多的白色、树脂款评分低于同框。** '
               f'含刨花板 {sh(pb)}（{lab(pb)}；新家族 {pb["新家族"]} 个、{pb["新家族卖起来"]} 个卖起来，价格带 ${num(pb["P25"])}–{num(pb["P75"])}，溢价 {pb["溢价"]:.2f}，评分 {pb["评分"]:.2f}）；'
               f'树脂台面 {sh(rs)}（{lab(rs)}；单款 ÷ 同框 {rs["单款比"]:.2f}，评分 {rs["评分"]:.2f}）；主色白 {sh(w)}（{lab(w)}；新家族 {w["新家族"]} 个、{w["新家族卖起来"]} 个卖起来，评分 {w["评分"]:.2f}）；实木框架 {sh(sw)}（{lab(sw)}），同框评分 {w["框评分"]:.2f}。'
               f'同为可读框的 24″ · 拆装 · 落地式（{fw.at["24″ · 拆装 · 落地式", "近3"] / fw.at["24″ · 拆装 · 落地式", "前3"]:.2f}）里最大的变化是深木 {sh(d24)}（{lab(d24)}）。'
               f'Amazon 同尺寸段落地式里白色 {ps(w["AZ份额前"])}→{ps(w["AZ份额近"])}、树脂一体 {ps(rs["AZ份额前"])}→{ps(rs["AZ份额近"])}（不分拆装）。'
               f'*来源*：Wayfair 渠道VP 表 + 商品页内嵌评论' + ('+ Apify 补抓' if nost else '') + f'的逐月评论（本框有月度 {pc(fw.at[k, "有月度占比"])}），页面总评分。*局限*：幸存者偏差让"抢份额 + 新家族卖起来"偏乐观；含刨花板单元月均只有 {num(pb["月均"])}；'
               '与上一轮（缺 168 个 listing 月度时）相比，这一框的趋势结论变了：框从"涨"变"平"、树脂从"抢"变"丢"，说明 Wayfair 的单元趋势对样本覆盖很敏感。')
    # 3 HD 整装：卡拉拉大理石丢、石英石抢
    zz = [x for x in D['FH2']['框'] if '整装' in x]
    H = UH[UH['框'].isin(zz) & (UH['月均'] >= U_MIN) & (UH['属性'] == '台面材质')]
    ca, qz = H[H['取值'] == '卡拉拉大理石'], H[H['取值'] == '石英石']
    qup = qz[qz['走势'].str.startswith('抢')].sort_values('月均', ascending=False)
    old = UO.set_index(['框', '属性', '取值'])['走势']
    agree = sum(str(old.get((r.框, '台面材质', r.取值), '')).startswith(r.走势[:3]) for r in pd.concat([ca[ca['走势'].str.startswith('丢')], qup]).itertuples())
    out.append(f'3. **HD 整装框：卡拉拉大理石台面在丢份额，石英石在抢份额且卖得贵、评分高。** {len(zz)} 个整装达标框里，卡拉拉大理石 {int(ca["走势"].str.startswith("丢").sum())} 个"丢份额"（' +
               '、'.join(f'{r.框.split(" · ")[0]} {ps(r.份额前3)}→{ps(r.份额近3)}' for r in ca[ca['走势'].str.startswith('丢')].sort_values('月均', ascending=False).itertuples()) + '）；'
               f'石英石 {len(qup)} 个"抢份额"（' + '、'.join(f'{r.框.split(" · ")[0]} {ps(r.份额前3)}→{ps(r.份额近3)}，溢价 {r.溢价:.1f}，评分差 {sg(r.评分差)}' for r in qup.itertuples()) + '）。'
               f'同时 36″ / 48″ / 60″ · 整装 · 落地式整框在跌（近 3 ÷ 前 3 = {fh.at["36″ · 整装 · 落地式", "近3"] / fh.at["36″ · 整装 · 落地式", "前3"]:.2f} / {fh.at["48″ · 整装 · 落地式", "近3"] / fh.at["48″ · 整装 · 落地式", "前3"]:.2f} / {fh.at["60″ · 整装 · 落地式", "近3"] / fh.at["60″ · 整装 · 落地式", "前3"]:.2f}），幸存者偏差本来偏向"涨"，跌更值得注意。'
               f'这些单元在上一版（类目 Top Sellers 范围）里同向的 {agree} / {int(ca["走势"].str.startswith("丢").sum()) + len(qup)} 个。'
               f'*来源*：HD 变体级评论重建（窗口评论星级、采集日价格）。*局限*：石英石单元小（月均 {num(qup["月均"].min())}–{num(qup["月均"].max())}、家族 {int(qup["家族"].min())}–{int(qup["家族"].max())} 个），多是一两个产品的走势；溢价是当天价。')
    # 4 HD 评分缺口
    c30, c36 = u(UH, '30″ · 整装 · 落地式', '台面材质', 'Cultured Marble'), u(UH, '36″ · 整装 · 落地式', '台面材质', 'Cultured Marble')
    out.append(f'4. **HD 30″ / 36″ · 整装 · 落地式：卖得最多的 Cultured Marble（树脂一体）单元评分最低。** 30″：份额 {ps(c30["份额"])}、单款 ÷ 同框 {c30["单款比"]:.2f}、评分 {c30["评分"]:.2f}（同框 {c30["框评分"]:.2f}，窗口评论 {int(c30["评论数"])} 条）、溢价 {c30["溢价"]:.2f}；'
               f'36″：份额 {ps(c36["份额"])}、单款 ÷ 同框 {c36["单款比"]:.2f}、评分 {c36["评分"]:.2f}（同框 {c36["框评分"]:.2f}，{int(c36["评论数"])} 条）、溢价 {c36["溢价"]:.2f}。'
               '同一批产品柜体多是含刨花板（柜体材质单元同样"评分低、单款大"），是"体量集中在低价低分款"的评分缺口形态，与 Amazon 机会扫描里"评分缺口 = 装配 / 做工"的结论方向一致（未在 HD 差评文本上核对）。'
               f'*来源*：HD 窗口内评论星级。*局限*：评分差 {abs(c30["评分差"]):.2f} / {abs(c36["评分差"]):.2f} 星，评论数够但差距不大；台面和柜体两行是同一批产品。')
    # 5 同框价格结构
    def mp(T, fr): return f"${num(T.at[fr, '框中位价'])}" if fr in T.index else '—'
    AH = D['AH']; hs = AH[frameable(AH) & AH['尺寸段'].isin(['36″', '42″', '48″']) & AH['柜体材质'].isin(['实木', '实木框架']) & AH['台面材质'].isin(['岗石', '石英石'])]
    fl_ = D['FLm2'].set_index('框')
    out.append('5. **同一个框，各渠道卖的是不同价位的产品：HD 的拆装是高价款，Wayfair 的拆装是低价款；整装 Wayfair 最贵、Lowe\'s 最便宜。** 加权中位价 HD vs Wayfair（vs Lowe\'s）：'
               + '；'.join(f'{fr} {mp(fh, fr)} vs {mp(fw, fr)}' + (f' vs {mp(fl_, fr)}' if fr in fl_.index else '') for fr in ('36″ · 拆装 · 落地式', '48″ · 拆装 · 落地式', '30″ · 拆装 · 落地式', '24″ · 整装 · 落地式', '30″ · 整装 · 落地式', '36″ · 整装 · 落地式', '48″ · 整装 · 落地式')) + '。'
               f'HD 36″–48″ 实木类 × 岗石 / 石英石的加权中位价 ${num(wq(hs["价格"], hs["c"], .5))}、$649–799 段销量占 {pc(hs.loc[hs["价格"].between(649, 799), "c"].sum() / hs["c"].sum())}（§七）。所以"同框"跨渠道对照时价格不可直接搬，开发定价要按渠道各自的框内价格带。'
               '*来源*：采集日价格（HD 商品页 / 列表，Wayfair 商品页），按 1–10 月销量加权。*局限*：当天价套整个窗口；' + f'Wayfair 拆装框里分框覆盖 ≥ 95% 的只有 {"、".join(sorted(x for x in fw.index if "拆装" in x and fw.at[x, "分框覆盖_期望"] >= 0.95)) or "无"}。')
    # 6 悬浮式
    fl = FW[FW['框'].str.contains('悬浮') & (FW['框月均'] >= FR_MIN)]; flH = FH[FH['框'].str.contains('悬浮')]
    flL = D['FLm2'][D['FLm2']['框'].str.contains('悬浮')]
    out.append(f'6. **悬浮式在 Wayfair（拆装悬浮）和 Lowe\'s（整装悬浮）成框，HD 没有。** Wayfair 达标的悬浮式框 {len(fl)} 个、合计月均 {num(fl["框月均"].sum())}（拆装悬浮式 30″ / 24″ / 36″ = {num(fw.at["30″ · 拆装 · 悬浮式", "框月均"])} / {num(fw.at["24″ · 拆装 · 悬浮式", "框月均"])} / {num(fw.at["36″ · 拆装 · 悬浮式", "框月均"])}）；'
               f'Lowe\'s（只算有月度）达标的悬浮式框 {len(flL)} 个、合计月均 {num(flL["框月均"].sum())}，全是整装、家族很少（' + '、'.join(f'{r.框} {num(r.框月均)} · {r.家族} 个家族 · ${num(r.框中位价)}' for r in flL.sort_values('框月均', ascending=False).itertuples()) + '）；'
               f'HD 悬浮式全部框合计月均 {num(flH["框月均"].sum())}，没有一个达标。Wayfair 单 listing 并不更强（§七：悬浮式平均月均低于落地式，与老文档"悬浮 556 vs 落地 199"相反）。'
               f'*局限*：Wayfair 形态未知占 {pc(AWx.loc[AWx["形态"] == "未知", "c"].sum() / AWx["c"].sum())}，悬浮式达标框的分框覆盖期望 {pc(fl["分框覆盖_期望"].min())}–{pc(fl["分框覆盖_期望"].max())}、最坏 {pc(fl["分框覆盖_最坏"].min())}–{pc(fl["分框覆盖_最坏"].max())}，'
               f'{int((fl["可读性"] != "可读").sum())} / {len(fl)} 个不可读，只能说悬浮式在 Wayfair 有一定体量。')
    # 7 HD 范围变更下的稳定性
    UO2 = UO[UO['框'].isin(D['FO'].loc[D['FO']['框月均'] >= FR_MIN, '框']) & (UO['月均'] >= U_MIN)]
    M = UO2.merge(D['UH2'], on=['框', '属性', '取值'], suffixes=('_o', '_n')); lab = lambda x: x.split('（')[0]
    out.append(f'7. **HD 换了商品范围（约四成家族不同），框的体量和单元份额基本稳定，单元趋势标签约两成会变。** 两版都达标的 {len(M)} 个单元份额相关 {M["份额_o"].corr(M["份额_n"]):.2f}，走势标签一致 {pc((M["走势_o"].map(lab) == M["走势_n"].map(lab)).mean())}（§八）。'
               '所以 HD 的框结构、单元份额可以当稳定事实用；单个单元的"抢 / 丢份额"要看是否在两版都成立（第 3 条已标）。')
    # 8 Lowe's
    Fm2 = D['FLm2'].set_index('框'); Um2 = D['ULm2']; zz = [k for k in ('30″ · 整装 · 落地式', '36″ · 整装 · 落地式', '24″ · 整装 · 落地式', '48″ · 整装 · 落地式') if k in Fm2.index]
    cm = [u(Um2, k, '台面材质', 'Cultured Marble') for k in zz]
    g30, g48, c48 = u(Um2, '30″ · 整装 · 落地式', '台面材质', '岗石'), u(Um2, '48″ · 整装 · 落地式', '台面材质', '岗石'), u(Um2, '48″ · 整装 · 落地式', '台面材质', 'Cultured Marble')
    hc30 = u(UH, '30″ · 整装 · 落地式', '台面材质', 'Cultured Marble')
    out.append(f'8. **Lowe\'s（只算 Best Sellers 两榜有月度的家族）：整装、低价、少数 Cultured Marble 爆款撑起主框；30″ / 48″ 整装里岗石在涨。** '
               '主框中位价 ' + '、'.join(f'{k.split(" · ")[0]} ${num(Fm2.at[k, "框中位价"])}（{Fm2.at[k, "家族"]} 个家族）' for k in zz) + '，低于 HD 同框；'
               'Cultured Marble 台面单元份额 ' + '、'.join(f'{k.split(" · ")[0]} {ps(r["份额"])}（单款 ÷ 同框 {r["单款比"]:.1f}）' for k, r in zip(zz, cm) if r is not None) + '。'
               f'30″ · 整装 · 落地式岗石 {sh(g30)}，48″ · 整装 · 落地式岗石 {sh(g48)}、Cultured Marble {sh(c48)}（"丢份额"）。'
               f'和 HD 不同，Lowe\'s 的 Cultured Marble 单元评分不低于同框（30″ {cm[0]["评分"]:.2f} vs 同框 {cm[0]["框评分"]:.2f}；HD 30″ {hc30["评分"]:.2f} vs {hc30["框评分"]:.2f}，口径不同只看各自同框差）。'
               f'*来源*：渠道VP 表家族月销 + BD 评论页变体宽度拆尺寸段，页面总评分、采集日价格。*局限*：两词独有家族（约两成评论）没有月度、估算部分拆不到尺寸段，含估算时所有框分框覆盖 < 95%；'
               f'结论只代表"榜上家族"；Cultured Marble 与含刨花板多是同一批产品。')
    return out


# ====================================================================== 6. 主流程（按框正式视图：大词商品范围，HD + Wayfair；Lowe's 补数据中）
SEED = 20261104
CHK = os.path.join(OUTDIR, '小平台调研_按框_抽检.json')   # 手核记录（抽样由本脚本按 SEED 生成，核对结论人工填写）


def reconcile():
    """核对：① 月销表销量 = VP × 50 + 非VP × 20；② 类目节点部分的 1–10 月评论数 vs 渠道VP 表「渠道月度汇总」去重小计 /「商品月度明细」家族去重。"""
    P, M = bw_raw(); out = []
    S = pd.read_excel(XLSX, '渠道月度汇总'); X = pd.read_excel(XLSX, '商品月度明细')
    vc = [f'{ms(m)} VP' for m in MON]; nc = [f'{ms(m)} 非VP' for m in MON]
    for ch in ('Home Depot', 'Wayfair', LW):
        m = M[M['渠道'] == ch]; p = P[P['渠道'] == ch]
        recal = (m['VP'] * 50 + m['非VP'] * 20).sum()
        if ch == 'Home Depot': cat = m[m['fam'].isin(p.loc[p['来源'].isin(['类目节点', '两者']), 'fam'])]
        else: cat = m[m['月度来源'].astype(str).str.startswith('渠道VP表')]
        sub = S[(S['渠道'] == ch) & (S['层级'] == '渠道小计')].iloc[0]
        d = X[X['渠道'] == ch].copy()
        d['vf'] = pd.factorize(d[vc + nc + ['2026-11（未完整） 合计']].astype(str).agg('|'.join, axis=1) + '#' + d['页面累计评论数'].astype(str))[0]
        dd = d.drop_duplicates('vf')
        out.append(dict(渠道=ch, 月销表销量=m['销量'].sum(), 重算=recal, 类目节点VP=cat['VP'].sum(), 类目节点非VP=cat['非VP'].sum(),
                        表VP=sub['1-10月 VP'], 表非VP=sub['1-10月 非VP'], 表合计=sub['1-10月 合计'], 明细家族去重=dd[vc].sum().sum() + dd[nc].sum().sum(),
                        类目节点销量=cat['销量'].sum(), 表销量=sub['1-10月 VP'] * 50 + sub['1-10月 非VP'] * 20))
    return pd.DataFrame(out)


def sample_check(AH, AW, AL):
    """随机抽 5 个能落框的商品（HD 2 个、Wayfair 3 个，按 1–10 月销量加权，固定种子），列出标签与原始规格，供手核。"""
    rng = np.random.default_rng(SEED); rows = []
    for ch, A, n in (('Home Depot', AH, 2), ('Wayfair', AW, 3), (LW, AL, 2)):   # Lowe's 2 个在补数后追加（种子序列不变，前 5 个不变）
        if ch == LW:   # Lowe's 一个父体拆到多个尺寸段：按"父体 × 尺寸段"抽
            g = A[frameable(A)].groupby(['fam', 'pid', '尺寸段']).agg(c=('c', 'sum'), 装=('装', 'first'), 形态=('形态', 'first'),
                                                                 装来源=('装来源', 'first'), 形态来源=('形态来源', 'first'), title=('title', 'first')).reset_index()
        else:
            g = A[frameable(A)].groupby(['fam', 'pid']).agg(c=('c', 'sum'), 尺寸段=('尺寸段', 'first'), 装=('装', 'first'), 形态=('形态', 'first'),
                                                          装来源=('装来源', 'first'), 形态来源=('形态来源', 'first'), title=('title', 'first')).reset_index()
        idx = rng.choice(len(g), n, replace=False, p=g['c'] / g['c'].sum())
        for i in idx:
            r = g.iloc[i]
            if ch == 'Home Depot':
                pg = HD.load_json(os.path.join(BWDIR, 'hd_pages', f"{r['pid']}.json")) or HD.load_json(os.path.join(HD.CACHE, 'pages', f"{r['pid']}.json")) or {}
                sp = pg.get('specs') or {}
                raw = {k: sp.get(k) for k in ('Product Width (in.)', 'Cabinet Width (in.)', 'Assembled', 'Assembly Required', 'Vanity Type')}
            elif ch == 'Wayfair':
                pg = HD.load_json(os.path.join(BWDIR, 'pdp', 'wayfair', f"{r['pid']}.json")) or {}
                sp = pg.get('specs') or {}
                raw = {k: sp.get(k) for k in ('Overall Width from Side to Side', 'Overall Dimensions', 'Assembly', 'Mounting / Installation', 'Product Type')}
            else:
                pg = HD.load_json(os.path.join(BWDIR, 'pdp', 'lowes', f"{r['pid']}.json")) or {}
                sp = pg.get('specs') or {}
                raw = {k: v for k, v in sp.items() if re.search(r'width|assembl|rta|install|floating|mount', k, re.I)}
                raw['本父体落到的尺寸段（评论变体宽度拆分）'] = '、'.join(sorted(A.loc[A['pid'] == r['pid'], '尺寸段'].dropna().unique()))
            rows.append(dict(渠道=ch, pid=r['pid'], title=r['title'], 标签=f"{r['尺寸段']} · {r['装']} · {r['形态']}", 来源=f"装：{r['装来源']}；形态：{r['形态来源']}",
                             原始规格='；'.join(f'{k} = {v}' for k, v in raw.items() if v) or '无商品页规格（标签来自标题）'))
    return pd.DataFrame(rows)


def old_vs_new_hd(FH_new, AH_new):
    """和上一版 HD 主视图对比：重跑上一版读取（类目 Top Sellers 前 300 评论重建）→ 框月均；家族按商品页 ID 对上。"""
    AO, _ = hd_table(); FO, UO = metrics(AO, '框', 'Home Depot')
    po = AO.groupby('pid')['c'].sum(); pn = AH_new.groupby('pid')['c'].sum()
    fo = AO.drop_duplicates('pid').set_index('pid')['fam']; fn = AH_new.drop_duplicates('pid').set_index('pid')['fam']
    old_f = set(fo); new_f = set(fn)
    shared_new = set(fn[fn.index.isin(fo.index)])            # 新范围里与上一版有共同商品页的家族
    shared_old = set(fo[fo.index.isin(fn.index)])
    s = dict(上一版家族=len(old_f), 新家族=len(new_f), 新里沿用=len(shared_new), 上一版丢掉=len(old_f - shared_old), 新增=len(new_f - shared_new),
             上一版月均=AO['c'].sum() / 10, 新月均=AH_new['c'].sum() / 10,
             丢掉销量=AO.loc[~AO['fam'].isin(shared_old), 'c'].sum() / 10, 新增销量=AH_new.loc[~AH_new['fam'].isin(shared_new), 'c'].sum() / 10)
    return FO, UO, s


def main():
    L.clear()
    print('读 HD / Wayfair / Lowe\'s（大词范围）…'); AH, PH, _ = bw_table('Home Depot'); AW, PW, KW = bw_table('Wayfair'); AL, PL, KL = bw_table(LW)
    print('读 Amazon …'); B = az_table(v10=True); AZs = az_cells(B, '尺寸段')
    CH = {'Home Depot': AH, 'Wayfair': AW, LW: AL}
    RES, COVR = {}, {}

    def framed(A, F, ch):
        C = frame_cover(A, F)
        F['分框覆盖_期望'] = F['框'].map(lambda k: C.get(k, (np.nan, np.nan))[0]); F['分框覆盖_最坏'] = F['框'].map(lambda k: C.get(k, (np.nan, np.nan))[1])
        F['可读性'] = F.apply(readability, axis=1)
        return C
    for ch, A in CH.items():
        F, U = metrics(A, '框', ch); U = attach_az(U, AZs, '尺寸段'); RES[ch] = (F, U); COVR[ch] = framed(A, F, ch)
    # 敏感性：无月度实体用低估计 / 不计（Lowe's 低估计 = 不计）；只算有月度时的覆盖与可读性
    SENS = {}
    for ch, A in ((ch, CH[ch]) for ch in ('Wayfair', LW)):
        Fl, _ = metrics(A.assign(c=A['c_low']), '框', ch)
        Am = A[A['m'] >= 0]; Fm, Um = metrics(Am, '框', ch); Um = attach_az(Um, AZs, '尺寸段'); framed(Am, Fm, ch)
        SENS[ch] = (Fl, Fm, Um, Am)
    F, U = RES[LW]; Fm = SENS[LW][1].set_index('框')
    F['可读性_只算有月度'] = F['框'].map(Fm['可读性']); F['分框覆盖_期望_只算有月度'] = F['框'].map(Fm['分框覆盖_期望'])
    FWl, FWm, UWm = SENS['Wayfair'][0], SENS['Wayfair'][1], SENS['Wayfair'][2]
    PEND = pd.concat([pending_list(A, ch) for ch, A in CH.items()])
    os.makedirs(OUTDIR, exist_ok=True)
    pd.concat([RES[c][1] for c in CH]).to_csv(os.path.join(OUTDIR, '小平台调研_按框_单元指标_全量.csv'), index=False, encoding='utf-8-sig')
    pd.concat([RES[c][0] for c in CH]).to_csv(os.path.join(OUTDIR, '小平台调研_按框_框_全量.csv'), index=False, encoding='utf-8-sig')
    PEND.to_csv(os.path.join(OUTDIR, '小平台调研_待人工确认.csv'), index=False, encoding='utf-8-sig')
    REC = reconcile(); SMP = sample_check(AH, AW, AL)
    SMP.to_csv(os.path.join(OUTDIR, '小平台调研_按框_抽检样本.csv'), index=False, encoding='utf-8-sig')
    CHKD = json.load(open(CHK, encoding='utf-8')) if os.path.exists(CHK) else {}
    print('读上一版 HD（对比用）…'); FO, UO, DIFF = old_vs_new_hd(RES['Home Depot'][0], AH)
    AOW = lw_table('Wayfair')[0]; FOW, _ = metrics(AOW, '框', 'Wayfair'); FOWd, _ = metrics(AOW, '不分拆装', 'Wayfair')
    AOL = lw_table(LW)[0]; FOLd, _ = metrics(AOL, '不分尺寸段', LW)
    RESX = {'F': RES, 'FWl': FWl, 'FWm': FWm, 'UWm': UWm, 'FO': FO, 'UO': UO, 'SENS': SENS, 'FOLd': FOLd}
    globals()['_LAST'] = dict(AH=AH, AW=AW, AL=AL, PH=PH, PW=PW, PL=PL, KW=KW, KL=KL, RES=RES, COVR=COVR, PEND=PEND, REC=REC, SMP=SMP, DIFF=DIFF, B=B, AZs=AZs, FOW=FOW, FOWd=FOWd, **RESX)
    report(globals()['_LAST'], CHKD)
    open(OUTMD, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('写出', OUTMD, len(L), '行')
    return globals()['_LAST']


if __name__ == '__main__':
    main_old() if sys.argv[1:] == ['上一版'] else main()
