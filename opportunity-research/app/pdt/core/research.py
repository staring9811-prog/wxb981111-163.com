"""渠道调研（F30，REQ-F30-01～04）：导入 wen 本机抓好的小平台商品表 / 月销表，按渠道 × 框算"单元 × 指标"与可读性。

口径移植自 `solution-v2/trial/小平台调研_单元指标.py`（bw_table / metrics / frame_cover / readability / pending_list），差别只在数据来源：
- 输入是导入的两张表（DATA-F30-02），不读 Home Depot 评论缓存：价格、评分只用商品表的列（评分按页面评论数加权，AC-F30-15），
  新家族按可选列"首评月"判定，没有该列时按"页面累计评论数 ≤ 窗口内评论数"（AC-F30-14，RA-126）。
- 窗口 = 导入数据里不晚于最近一个完整自然月的月份（AC-F30-04、AC-F30-11），晚于它的行只作参考。
- 无月度商品估算（AC-F30-17）：商品表带"月度来源"列时，只估算标为"无（只有评论总数）"、或月度来源为空且家族在月销表里没有行的商品
  （与小试 nomon_mask 同；其他没有窗口内月销行的商品是窗口内确实没有评论，销量记 0）；没有该列时按"月销表里没有行且页面评论数 > 0"。低估计的评论数档把 > 100 条合成一档（与小试同，两词独有的
  有月度商品里评论 > 100 条的太少）。
- 分框（AC-F30-10）：打标确认里已确认的尺寸段 / 装 / 形态（Tag，与机会扫描共用，RA-120）优先于导入值；多尺寸未拆选"不进框"的记在
  ResearchOverride；之后与小试相同，同家族已知形态补未知形态。
- 只读写调研自己的表与分框确认用的 Tag；不写 Batch / Snapshot（AC-F30-08）。
"""
import collections
import hashlib
import io
import re
import shutil
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import delete, insert, select

from ..config import CHANNEL_NAMES, data_dir
from ..db import session
from ..models import Batch, Tag, now
from ..models_research import (ResearchImport, ResearchMonthly, ResearchOverride, ResearchProduct, ResearchResult,
                               ResearchVersion)

CHANNELS = ['homedepot', 'lowes', 'wayfair']
NAME2KEY = {'Home Depot': 'homedepot', "Lowe's": 'lowes', 'Wayfair': 'wayfair'}
PROD_COLS = ['渠道', 'fam', 'pid', 'title', '来源', '尺寸段', '装', '形态', '台面材质', '主色', '柜体材质', '元素', '价格', '评分', '页面评论数']
MON_COLS = ['渠道', 'fam', 'pid', '尺寸段', '装', '形态', '月', 'VP', '非VP', '销量']
RAW_KEYS = ['宽', '选项段', '多尺寸段', '颜色原值', '台面原值', '柜体原值', '月度来源', '浴室柜', '装来源', '形态来源', '主图']  # 主图：可选列（AC-F30-33）
NOMON = '无（只有评论总数）'
MULTI = '多尺寸未拆'
NOFRAME = '不进框'
KBINS = [0, 20, 100, 300, np.inf]          # 评论数档：1–20、21–100、101–300、> 300
LOW_BINS = [0, 20, 100, np.inf]            # 低估计：> 100 合成一档（小试口径）
FR_MIN, U_MIN = 100, 20                    # 框门槛默认月均 ≥ 100（分渠道可配，AC-F30-35）、单元月均 ≥ 20（AC-F30-11）
READ_MIN = 200                             # 月均 < 200 的达门槛框标"样本少，只作参考"（AC-F30-34）
COVER_MIN, MONTHLY_MIN = 0.95, 0.60        # 可读性（AC-F30-19～21）
LN, DIR, EPS = 0.3, 0.2, 0.002             # 走势 ±0.3、Amazon 方向 ±0.2；份额 ln 加 0.002 平滑（小试口径）
ATTRS = ('台面材质', '元素', '主色', '柜体材质')
UNK = {'未知', '信息不足', '待图片核验', '', 'nan', 'None', '<NA>'}
SIZES = ['18″', '24″', '28″', '30″', '36″', '42″', '48″', '60″', '72″+']
FORMS = ['落地式', '悬浮式', '开放式', '转角式']
ASMS = ['拆装', '整装']
PRICE_ABS = [0, 200, 300, 450, 650, 900, 1300, np.inf]  # 与 F29 相同的 7 段绝对价位
REASONS = ['尺寸段未知', MULTI, '装未知', '形态未知']
FAMILY_NOTE = {'homedepot': 'Home Depot 评论家族', 'lowes': "Lowe's 父体", 'wayfair': 'Wayfair listing（一个 listing 算一个家族）'}


def today() -> date:
    return date.today()


def frame_min(channel: str) -> float:
    """该渠道调研框门槛（品类配置 research.frame_min，默认 100，AC-F30-35）。"""
    from .. import catconfig
    return float(((catconfig.current()[1].get('research') or {}).get('frame_min') or {}).get(channel, FR_MIN))


def image_map(channel: str) -> dict:
    """渠道 + 商品编号 → 主图网址（当前调研版本的"主图"列，AC-F30-33）；没有该列时为空。"""
    ver = current_version(channel)
    if ver is None:
        return {}
    with session() as s:
        return {p.pid: (p.raw or {}).get('主图') for p in s.scalars(select(ResearchProduct).where(ResearchProduct.version_id == ver.id))
                if (p.raw or {}).get('主图')}


def last_complete_month() -> str:
    t = today()
    y, m = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
    return f'{y}-{m:02d}'


def _mi(ym: str) -> int:
    return int(ym[:4]) * 12 + int(ym[5:7]) - 1


def _ms(i: int) -> str:
    return f'{i // 12}-{i % 12 + 1:02d}'


def _isnan(v) -> bool:
    return v is None or (isinstance(v, float) and np.isnan(v))


def _f(v):
    """JSON 友好的数：NaN / inf → None。"""
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(v) else v


def slug(frame: str) -> str:
    """框 → 地址里的键：'30″ · 整装 · 落地式' → '30-整装-落地式'，'72″+ · 拆装 · 落地式' → '72p-拆装-落地式'。"""
    return frame.replace('″+', 'p').replace('″', '').replace(' · ', '-')


# ====================================================================== 1. 读文件与检查（AC-F30-01～03）
def read_csv(content: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=True, encoding='utf-8-sig')
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _rows(idx) -> str:
    """行号（文件中的行，表头为第 1 行）列表 → '第 2、3 行' / '第 2,604–2,615 行'。"""
    n = sorted(int(i) + 2 for i in idx)
    if len(n) > 2 and n[-1] - n[0] == len(n) - 1:
        return f'第 {n[0]:,}–{n[-1]:,} 行'
    return '第 ' + '、'.join(f'{x:,}' for x in n[:20]) + (' 等' if len(n) > 20 else '') + ' 行'


def check(P: pd.DataFrame, M: pd.DataFrame) -> list[dict]:
    """返回问题列表 [{title, n, examples[≤20]}]；空列表 = 通过。任一问题都整次拒绝。"""
    out = []
    miss_p = [c for c in PROD_COLS if c not in P.columns]
    miss_m = [c for c in MON_COLS if c not in M.columns]
    if miss_p:
        out.append(dict(title='商品表缺少列', n=None, examples=miss_p))
    if miss_m:
        out.append(dict(title='月销表缺少列', n=None, examples=miss_m))
    if out:
        return out
    for nm, df in (('商品表', P), ('月销表', M)):
        ch = df['渠道'].fillna('').astype(str).str.strip()
        bad = ~ch.isin(NAME2KEY)
        if bad.any():
            ex = [f'"{v or "（空）"}"：{int(g.size)} 行（{_rows(g.index)}）' for v, g in ch[bad].groupby(ch[bad], sort=False)]
            out.append(dict(title=f'{nm}渠道值不认识（只认 Home Depot、Lowe\'s、Wayfair）', n=int(bad.sum()), examples=ex[:20]))
    mon = M['月'].fillna('').astype(str).str.strip()
    ok = mon.str.match(r'^\d{4}-(0[1-9]|1[0-2])$')
    if (~ok).any():
        out.append(dict(title='月销表"月"不是 YYYY-MM', n=int((~ok).sum()), examples=[f'第 {i + 2:,} 行 月：{v or "（空）"}' for i, v in mon[~ok].head(20).items()]))
    ex, n = [], 0
    for c in ('VP', '非VP', '销量'):
        v = pd.to_numeric(M[c], errors='coerce')
        b = v.isna() | (v < 0)
        n += int(b.sum())
        ex += [f'第 {i + 2:,} 行 {c}：{M.at[i, c] if not _isnan(M.at[i, c]) else "（空）"}' for i in M.index[b][:20]]
    if n:
        out.append(dict(title='月销表 VP / 非VP / 销量不是非负数', n=n, examples=ex[:20]))
    pk = P['渠道'].astype(str).str.strip() + '|' + P['pid'].astype(str).str.strip()
    d = pk[pk.duplicated(keep=False)]
    if len(d):
        ex = [f'{k.replace("|", " ")}（{_rows(g.index)}）' for k, g in d.groupby(d, sort=False)]
        out.append(dict(title='商品表同一渠道 + pid 出现多行', n=int(len(d)), examples=ex[:20]))
    mk = (M['渠道'].astype(str).str.strip() + '|' + M['pid'].astype(str).str.strip() + '|' + M['尺寸段'].fillna('').astype(str) + '|' + mon)
    d = mk[mk.duplicated(keep=False)]
    if len(d):
        ex = [f'{" ".join(x for x in k.split("|") if x)}（{_rows(g.index)}）' for k, g in d.groupby(d, sort=False)]
        out.append(dict(title='月销表同一渠道 + pid + 尺寸段 + 月出现多行', n=int(len(d)), examples=ex[:20]))
    mp = M['渠道'].astype(str).str.strip() + '|' + M['pid'].astype(str).str.strip()
    lost = ~mp.isin(set(pk))
    if lost.any():
        ex = [f'{k.replace("|", " ")}（{_rows(g.index)}）' for k, g in mp[lost].groupby(mp[lost], sort=False)]
        out.append(dict(title='月销表的商品在商品表里找不到', n=int(lost.sum()), examples=ex[:20]))
    return out


def normalize(P: pd.DataFrame, M: pd.DataFrame):
    """通过检查后的两张表 → 按渠道键的商品表、月销表（数值列转数）。"""
    P = P.copy()
    M = M.copy()
    for df in (P, M):
        for c in ('渠道', 'fam', 'pid'):
            df[c] = df[c].astype(str).str.strip()
        df['ch'] = df['渠道'].map(NAME2KEY)
    for c in ('价格', '评分', '页面评论数'):
        P[c] = pd.to_numeric(P[c], errors='coerce')
    for c in ('VP', '非VP', '销量'):
        M[c] = pd.to_numeric(M[c], errors='coerce').astype(float)
    M['月'] = M['月'].astype(str).str.strip()
    P.attrs['has_monthly_source'] = '月度来源' in P.columns
    P.attrs['has_first_month'] = '首评月' in P.columns and P['首评月'].notna().any()
    return P, M


def _clean(v) -> str:
    return '' if _isnan(v) or str(v).strip() in ('nan', 'None') else str(v).strip()


# ====================================================================== 2. 行级表（行 = 商品 × 尺寸段 × 月；m = -1 为估算的无月度商品）
def _excluded_mask(P: pd.DataFrame) -> pd.Series:
    """可选列"浴室柜" = false 的商品不是本品类（与小试同，标题不含 vanity 的 listing），不进任何指标。"""
    if '浴室柜' not in P.columns:
        return pd.Series(False, index=P.index)
    return P['浴室柜'].astype(str).str.strip().str.lower().eq('false')


def window_of(M: pd.DataFrame) -> tuple[list[str], dict]:
    """窗口 = 不晚于最近一个完整自然月的月份（连续区间）；晚于它的行只作参考，返回 {月: 行数}。"""
    lcm = last_complete_month()
    months = sorted(set(M['月']))
    win = [m for m in months if m <= lcm]
    ref = {m: int((M['月'] == m).sum()) for m in months if m > lcm}
    if not win:
        return [], ref
    lo, hi = _mi(win[0]), _mi(win[-1])
    return [_ms(i) for i in range(lo, hi + 1)], ref


def build_rows(P: pd.DataFrame, M: pd.DataFrame, window: list[str], conf: dict, noframe: set):
    """一个渠道的行级表 A 与估算信息。P、M 已只含该渠道。conf = {pid: {尺寸段/装/形态: 确认值}}；noframe = 选"不进框"的 pid。"""
    P = P[~_excluded_mask(P)].copy()
    P['尺寸段'] = P['尺寸段'].map(_clean)
    for c in ('装', '形态'):
        P[c] = P[c].map(lambda v: _clean(v) or '未知')
    mi = {m: i for i, m in enumerate(window)}
    all_fams = set(M['fam'])
    M = M[M['pid'].isin(set(P['pid'])) & M['月'].isin(mi)].copy()
    pi = P.drop_duplicates('pid').set_index('pid')
    A = pd.DataFrame({'fam': M['fam'].values, 'pid': M['pid'].values, 'm': M['月'].map(mi).values, 'c': M['销量'].values,
                      'VP': M['VP'].values, '非VP': M['非VP'].values, '尺寸段': M['尺寸段'].map(_clean).values,
                      '装': M['装'].map(lambda v: _clean(v) or '未知').values, '形态': M['形态'].map(lambda v: _clean(v) or '未知').values})
    A['c_low'] = A['c']
    # ---- 无月度商品估算（AC-F30-17）
    sales = A.groupby('pid')['c'].sum()
    has_rows = set(M['pid'])
    if P.attrs.get('has_monthly_source'):
        src = P['月度来源'].map(_clean)
        # 标"无（只有评论总数）"的，或月度来源为空、有页面评论而家族在月销表里没有行的（Lowe's 两词独有家族，小试 nomon_mask）
        target = P[((src == NOMON) | ((src == '') & ~P['fam'].isin(all_fams))) & (P['页面评论数'] > 0)]
        refp = P[(src != '') & (src != NOMON) & (P['页面评论数'] > 0)]
    else:
        target = P[~P['pid'].isin(has_rows) & (P['页面评论数'] > 0)]
        refp = P[P['pid'].isin(has_rows) & (P['页面评论数'] > 0)]
    est = dict(bins={}, low_bins={}, n_target=int(len(target)), unestimable=0)
    S = None
    if len(target):
        S = target.copy()
        for nm, bins, srcs, col in (('bins', KBINS, ('两词', '两者'), 'c'), ('low_bins', LOW_BINS, ('两词',), 'c_low')):
            q = refp[refp['来源'].isin(srcs)].copy()
            q['s'] = q['pid'].map(sales).fillna(0)
            q['档'] = pd.cut(q['页面评论数'], bins, right=True)
            k = q.groupby('档', observed=False).agg(s=('s', 'sum'), r=('页面评论数', 'sum'), n=('pid', 'size'))
            k['k'] = k['s'] / k['r'].replace(0, np.nan)
            est[nm] = {str(i): dict(k=_f(r['k']), n=int(r['n'])) for i, r in k.iterrows()}
            S[col] = pd.cut(S['页面评论数'], bins, right=True).map(k['k']).astype(float) * S['页面评论数']
        bad = S['c'].isna()
        est['unestimable'] = int(bad.sum())
        S = S[~bad]
        S['c_low'] = S['c_low'].fillna(0)
        multi = S['多尺寸段'].astype(str).str.lower().eq('true') if '多尺寸段' in S.columns else pd.Series(False, index=S.index)
        S = pd.DataFrame({'fam': S['fam'].values, 'pid': S['pid'].values, 'm': -1, 'c': S['c'].values, 'c_low': S['c_low'].values,
                          'VP': np.nan, '非VP': np.nan, '尺寸段': np.where(multi, MULTI, S['尺寸段'].values), '装': S['装'].values, '形态': S['形态'].values})
        A = pd.concat([A, S], ignore_index=True)
    est['n_static'] = 0 if S is None else int(len(S))
    # ---- 商品属性
    cols = {'title': 'title', '品牌': 'brand', '来源': '来源', '台面材质': '台面材质', '主色': '主色', '柜体材质': '柜体材质', '元素': '元素',
            '价格': '价格', '评分': '评分', '页面评论数': '页面评论数', '选项段': '选项段'}
    for c in cols:
        A[c] = A['pid'].map(pi[c]) if c in pi.columns else np.nan
    A['多尺寸未拆'] = A['尺寸段'].eq(MULTI)
    A['尺寸段'] = A['尺寸段'].where(~A['多尺寸未拆'] & A['尺寸段'].ne(''), None).astype(object)
    # ---- 已确认的分框标签优先（AC-F30-10、AC-F30-30）
    if conf:
        sizes_known = A[A['尺寸段'].notna()].groupby('pid')['尺寸段'].nunique()
        for pid, d in conf.items():
            k = A['pid'] == pid
            if not k.any():
                continue
            for tg in ('装', '形态'):
                if d.get(tg):
                    A.loc[k, tg] = d[tg]
            if d.get('尺寸段'):
                kk = k & (A['尺寸段'].isna() | (sizes_known.get(pid, 0) <= 1))
                A.loc[kk, '尺寸段'] = d['尺寸段']
                A.loc[kk, '多尺寸未拆'] = False
    A['不进框'] = A['pid'].isin(noframe) & (A['尺寸段'].isna())
    # ---- 同家族补形态（小试口径：同系列只换颜色 / 尺寸）
    kn = (A[A['形态'] != '未知'].groupby(['fam', '形态'])['c'].sum().reset_index().sort_values('c')
          .drop_duplicates('fam', keep='last').set_index('fam')['形态'])
    k = (A['形态'] == '未知') & A['fam'].isin(kn.index)
    A.loc[k, '形态'] = A.loc[k, 'fam'].map(kn)
    for c in ('台面材质', '主色', '柜体材质'):
        A[c] = A[c].map(lambda v: _clean(v) or '未知')
    A['元素'] = A['元素'].map(lambda s: [x.strip() for x in re.split(r'[、|]', _clean(s) or '未知') if x.strip()] or ['未知'])
    A['评分'] = A['评分'].where(A['评分'] > 0)
    # 评分按页面评论数加权；一个商品拆到多个尺寸段 / 月时按销量分摊权重（AC-F30-15）
    ft = A.groupby('fam')['c'].transform('sum').replace(0, np.nan)
    w = (A['页面评论数'].fillna(0) * A['c'] / ft).where(A['评分'].notna(), 0).fillna(0)
    A['rs'], A['rn'] = A['评分'].fillna(0) * w, w
    # ---- 新家族（AC-F30-14）
    fams = A['fam'].unique()
    if P.attrs.get('has_first_month'):
        fm = P.groupby('fam')['首评月'].agg(lambda s: min([_clean(x) for x in s if _clean(x)] or ['']))
        newf = fm.map(lambda x: bool(x) and x in mi)
        A['新家族'] = A['fam'].map(newf).fillna(False).astype(bool)
        A['进入月'] = np.where(A['新家族'], A['fam'].map(fm).map(lambda x: mi.get(x, np.nan)), np.nan)
        est['new_rule'] = '首评月在窗口内'
    else:
        n26 = A[A['m'] >= 0].groupby('fam')[['VP', '非VP']].sum().sum(axis=1).reindex(fams).fillna(0)
        pr = P.groupby('fam')['页面评论数'].max().reindex(fams)
        newf = (pr <= n26) & (n26 > 0)
        A['新家族'] = A['fam'].map(newf).fillna(False).astype(bool)
        e = A[(A['m'] >= 0) & (A['c'] > 0)].groupby('fam')['m'].min()
        A['进入月'] = np.where(A['新家族'], A['fam'].map(e), np.nan)
        est['new_rule'] = '页面累计评论数 ≤ 窗口内评论数（商品表没有首评月）'
    return A, est


def frameable(A: pd.DataFrame) -> pd.Series:
    return A['尺寸段'].notna() & (A['装'] != '未知') & (A['形态'] != '未知')


# ====================================================================== 3. 指标（框、单元、覆盖、可读性）
def wq(x, w, q):
    x, w = np.asarray(x, float), np.asarray(w, float)
    k = ~np.isnan(x) & (w > 0)
    x, w = x[k], w[k]
    if not len(x):
        return np.nan
    o = np.argsort(x)
    c = np.cumsum(w[o])
    return x[o][min(np.searchsorted(c, c[-1] * q), len(x) - 1)]


def frame_cover(A: pd.DataFrame) -> dict:
    """分框覆盖（AC-F30-19）：待确认销量按已知的尺寸段 / 装 / 形态可能落到的框，按这些框已落框销量比例分摊；多尺寸未拆只分到其选项段。"""
    ok = frameable(A)
    IN = A[ok].groupby(['尺寸段', '装', '形态'])['c'].sum()
    allsz = sorted(A.loc[ok, '尺寸段'].unique())
    U = A[~ok & ~A['不进框']].assign(选项段=A['选项段'].map(_clean))
    U = U.groupby([U['尺寸段'].fillna(''), '选项段', '装', '形态', '多尺寸未拆'])['c'].sum()
    exp, worst = collections.defaultdict(float), collections.defaultdict(float)
    for (sz, opt, a, f, multi), c in U.items():
        sizes = [sz] if sz else ([x for x in opt.split('、') if x] if multi and opt else allsz)
        comp = [k for k in IN.index if k[0] in sizes and (a == '未知' or k[1] == a) and (f == '未知' or k[2] == f)]
        t = IN[comp].sum()
        for k in comp:
            worst[k] += c
            if t > 0:
                exp[k] += c * IN[k] / t
    return {' · '.join(k): (v / (v + exp[k]), v / (v + worst[k])) for k, v in IN.items()}


def _trend_label(ln, pre, rec):
    if pre <= 0 and rec > 0:
        return '新出现'
    if ln >= LN:
        return '抢份额'
    if ln <= -LN:
        return '丢份额'
    return '随框'


def _frame_label(r):
    return '框涨' if r >= 1.15 else ('框跌' if r <= 0.87 else '框平')


def metrics(A: pd.DataFrame, n: int, est_low: bool):
    """框表与单元表（小试 metrics 的窗口泛化版）。份额分母 = 整框销量（含该属性未知）；趋势、新品只用有月度的行（m ≥ 0）。"""
    MON = list(range(n))
    PRE, REC = MON[:3], MON[-3:]
    trend_ok = n >= 6
    A = A[frameable(A)].copy()
    A['框'] = A['尺寸段'].astype(str) + ' · ' + A['装'] + ' · ' + A['形态']
    FR, UN = [], {}
    for fr, g in A.groupby('框'):
        Fm = g[g['m'] >= 0].groupby('m')['c'].sum().reindex(MON, fill_value=0)
        tot = g['c'].sum()
        low = g['c_low'].sum()
        fams = g.loc[g['c'] > 0, 'fam'].nunique()
        famavg = tot / n / max(fams, 1)
        newf = g[g['新家族']]
        pre, rec = Fm[PRE].sum(), Fm[REC].sum()
        fi = dict(frame=fr, slug=slug(fr), size=g['尺寸段'].iloc[0], asm=g['装'].iloc[0], form=g['形态'].iloc[0],
                  units=tot / n, units_low=low / n, estimated=bool((g['m'] < 0).any() and g.loc[g['m'] < 0, 'c'].sum() > 0) and est_low,
                  families=int(fams), per_family=famavg, monthly_share=_f(Fm.sum() / tot) if tot else None,
                  ratio=_f(rec / pre) if pre > 0 and trend_ok else None, new_appear=bool(pre <= 0 and rec > 0),
                  new_fams=int(newf.loc[newf['c'] > 0, 'fam'].nunique()), new_share=_f(newf['c'].sum() / tot) if tot else None,
                  median_price=_f(wq(g['价格'], g['c'], .5)), rating=_f(g['rs'].sum() / g['rn'].sum()) if g['rn'].sum() else None,
                  series=[_f(x) for x in Fm.values])
        fi['ratio_label'] = _frame_label(fi['ratio']) if fi['ratio'] is not None else ''
        for att in ATTRS:
            x = g.explode('元素') if att == '元素' else g
            kn = x[~x[att].astype(str).isin(UNK | {'其他'})]
            fi[f'known_{att}'] = _f(kn.drop_duplicates(['pid', 'm', '尺寸段'])['c'].sum() / tot) if tot else None
        units = []
        for att in ATTRS:
            x = g.explode('元素') if att == '元素' else g
            kn = x[~x[att].astype(str).isin(UNK | {'其他'})]
            for v, u in kn.groupby(att):
                us = u['c'].sum()
                if us / n < 1:
                    continue
                Um = u[u['m'] >= 0].groupby('m')['c'].sum().reindex(MON, fill_value=0)
                sh = Um / Fm.replace(0, np.nan)
                s_pre = Um[PRE].sum() / max(Fm[PRE].sum(), 1e-9)
                s_rec = Um[REC].sum() / max(Fm[REC].sum(), 1e-9)
                ok = sh.notna().values
                xs = np.arange(n)
                slope = np.polyfit(xs[ok], sh.values[ok], 1)[0] if ok.sum() >= 3 else np.nan
                uf = u.loc[u['c'] > 0, 'fam'].nunique()
                nu = u[u['新家族'] & (u['c'] > 0) & (u['m'] >= 0)]
                up, entries = 0, []
                for f, h in nu.groupby('fam'):
                    e0 = h['进入月'].iloc[0]
                    e = int(e0) if pd.notna(e0) else 0
                    e = max(e, 0)
                    entries.append(e)
                    if h.loc[h['m'] >= e, 'c'].sum() / (n - e) >= famavg:
                        up += 1
                mu = Um.mean()
                w = u[u['c'] > 0]
                p50 = wq(u['价格'], u['c'], .5)
                ln = np.log((s_rec + EPS) / (s_pre + EPS))
                urec, upre = Um[REC].sum(), Um[PRE].sum()
                ul = u['c_low'].sum()
                units.append(dict(attr=att, value=str(v), units=us / n, share=us / tot, units_low=ul / n, share_low=_f(ul / low) if low else None,
                                  estimated=fi['estimated'] and bool((u['m'] < 0).any() and u.loc[u['m'] < 0, 'c'].sum() > 0),
                                  monthly_share=_f(Um.sum() / us) if us else None, series=[_f(s) for s in sh.values],
                                  share_pre=_f(s_pre), share_rec=_f(s_rec), diff_pp=_f((s_rec - s_pre) * 100) if trend_ok else None,
                                  ln=_f(ln), trend=_trend_label(ln, s_pre, s_rec) if trend_ok else '',
                                  unit_ratio=_f(urec / upre) if upre > 0 else None, frame_ratio=_f(rec / max(pre, 1e-9)),
                                  slope_pp=_f(slope * 100), cv=_f(Um.std(ddof=0) / mu) if mu else None,
                                  families=int(uf), price_bands=int(pd.cut(w['价格'], PRICE_ABS, labels=False, right=False).nunique()),
                                  per_family_ratio=_f((us / max(uf, 1)) / max(famavg * n, 1e-9)),
                                  new_fams=int(nu['fam'].nunique()), new_up=int(up), entries=[window_label(i) for i in sorted(set(entries))],
                                  new_share=_f(u.loc[u['新家族'], 'c'].sum() / us) if us else None, frame_new_share=fi['new_share'],
                                  p25=_f(wq(u['价格'], u['c'], .25)), p50=_f(p50), p75=_f(wq(u['价格'], u['c'], .75)),
                                  premium=_f(p50 / fi['median_price']) if fi['median_price'] else None,
                                  rating=_f(u['rs'].sum() / u['rn'].sum()) if u['rn'].sum() else None))
        for u in units:
            u['rating_diff'] = _f(u['rating'] - fi['rating']) if u['rating'] is not None and fi['rating'] is not None else None
        FR.append(fi)
        UN[fr] = units
    return FR, UN


_WINDOW: list = []


def window_label(i: int) -> str:
    return _WINDOW[i] if 0 <= i < len(_WINDOW) else ''


def readability(cover, monthly):
    if cover is None or not cover >= COVER_MIN:
        return 'noconc'
    if monthly is None or not monthly >= MONTHLY_MIN:
        return 'notrend'
    return 'ok'


def pending_list(A: pd.DataFrame, P: pd.DataFrame, channel: str) -> list[dict]:
    """分框待确认（AC-F30-26）：尺寸段 / 装 / 形态任一未知（含多尺寸未拆）且没选"不进框"的商品，每个未知维度一条，按窗口销量从大到小。"""
    x = A[~frameable(A) & ~A['不进框']]
    if x.empty:
        return []
    tot = A.groupby('pid')['c'].sum()
    pi = P.drop_duplicates('pid').set_index('pid')
    from .channels import item_link
    out = []
    for pid, g in x.groupby('pid'):
        r = pi.loc[pid] if pid in pi.index else {}
        raw = {k: _clean(r.get(k)) for k in RAW_KEYS if hasattr(r, 'get')}
        opts = [s for s in raw.get('选项段', '').split('、') if s in SIZES]
        base = dict(pid=pid, fam=str(g['fam'].iloc[0]), title=_clean(r.get('title')), brand=_clean(r.get('品牌')) if hasattr(r, 'get') else '',
                    sales=_f(tot.get(pid, 0)), link=item_link(channel, pid), raw=raw,
                    top_raw=_clean(r.get('台面材质')), color=_clean(r.get('主色')), cab=_clean(r.get('柜体材质')),
                    size=_clean(r.get('尺寸段')), asm=_clean(r.get('装')), form=_clean(r.get('形态')))
        if g['多尺寸未拆'].any():
            out.append(dict(base, tag='尺寸段', reason=MULTI, candidates=(opts or SIZES) + [NOFRAME]))
        elif g['尺寸段'].isna().any():
            out.append(dict(base, tag='尺寸段', reason='尺寸段未知', candidates=SIZES + [NOFRAME]))
        if (g['装'] == '未知').any():
            out.append(dict(base, tag='装', reason='装未知', candidates=ASMS))
        if (g['形态'] == '未知').any():
            out.append(dict(base, tag='形态', reason='形态未知', candidates=FORMS))
    out.sort(key=lambda e: (-(e['sales'] or 0), e['pid'], e['tag']))
    return out


# ====================================================================== 4. Amazon 同框对照（AC-F30-16）
def amazon_cells() -> dict:
    """Amazon 最近 6 个完整月：{(尺寸段 · 形态, 属性, 取值): {fam, pb, pre, rec, ln, dir, months}}（不分拆装，元素按 F29 的 6 类）。"""
    from . import panel, richness
    an = panel.analysis('amazon')
    if an.A.empty:
        return {}
    B = richness.amazon_rows(an.A)
    ms_ = sorted(B['m'].unique())[-6:]
    B = B[B['m'].isin(ms_)]
    pre_m, rec_m = ms_[:3], ms_[3:]
    B = B.assign(框=(B['尺寸段'].astype(object).fillna('') + ' · ' + B['形态']).where(B['尺寸段'].notna()))
    B = B[B['框'].notna()]
    F = B.groupby(['框', 'm'])['c'].sum()
    out = {}
    label = f'{_ms(int(ms_[0]))} 至 {_ms(int(ms_[-1]))}'
    for att in ATTRS:
        x = B.explode('元素') if att == '元素' else B
        x = x[~x[att].astype(str).isin(UNK | {'其他'}) & ~x[att].astype(str).str.startswith('其他（')]
        for (fr, v), u in x.groupby(['框', att]):
            Um = u.groupby('m')['c'].sum()
            Fr = F.loc[fr]
            pre = Um.reindex(pre_m, fill_value=0).sum() / max(Fr.reindex(pre_m, fill_value=0).sum(), 1e-9)
            rec = Um.reindex(rec_m, fill_value=0).sum() / max(Fr.reindex(rec_m, fill_value=0).sum(), 1e-9)
            w = u[u['c'] > 0]
            ln = float(np.log((rec + EPS) / (pre + EPS)))
            out[(fr, att, str(v))] = dict(fam=int(w['fam'].nunique()), pb=int(pd.cut(w['价格'], PRICE_ABS, labels=False, right=False).nunique()),
                                          pre=_f(pre), rec=_f(rec), ln=_f(ln), dir='↑' if ln >= DIR else ('↓' if ln <= -DIR else '→'))
    out['_months'] = label
    return out


# ====================================================================== 5. 一个渠道的完整计算
def confirmations(channel: str, pids) -> tuple[dict, set]:
    """已确认的分框标签（Tag，人工确认、值非空非未知）与"不进框"。"""
    pids = list(set(pids))
    conf, nof = {}, set()
    with session() as s:
        for k in range(0, len(pids), 500):
            part = pids[k:k + 500]
            for t in s.scalars(select(Tag).where(Tag.channel == channel, Tag.item_id.in_(part), Tag.tag.in_(['尺寸段', '装', '形态']),
                                                 Tag.status == 'confirmed')):
                if t.value and t.value not in UNK:
                    conf.setdefault(t.item_id, {})[t.tag] = t.value
            nof |= {o.pid for o in s.scalars(select(ResearchOverride).where(ResearchOverride.channel == channel, ResearchOverride.pid.in_(part),
                                                                             ResearchOverride.value == NOFRAME))}
    return conf, nof


def compute(channel: str, P: pd.DataFrame, M: pd.DataFrame, with_amazon: bool = True, conf=None, noframe=None) -> dict:
    """P、M：该渠道（已 normalize）。返回可 JSON 化的结果（渠道状态、汇总、框、单元、待确认）。"""
    global _WINDOW
    window, ref = window_of(M)
    _WINDOW = window
    n = len(window)
    if conf is None:
        conf, noframe = confirmations(channel, P['pid'])
    A, est = build_rows(P, M, window, conf, noframe or set())
    fmin = frame_min(channel)
    Pk = P[~_excluded_mask(P)]
    tot = A['c'].sum()
    ok = frameable(A)
    nof = A['不进框']
    pend = pending_list(A, Pk, channel)
    pend_pids = {e['pid'] for e in pend}
    reasons = {}
    if tot:
        un = A[~ok & ~nof]
        reasons = {'尺寸段未知': _f(un.loc[un['尺寸段'].isna() & ~un['多尺寸未拆'], 'c'].sum() / tot),
                   MULTI: _f(un.loc[un['多尺寸未拆'], 'c'].sum() / tot),
                   '装未知': _f(un.loc[un['装'] == '未知', 'c'].sum() / tot), '形态未知': _f(un.loc[un['形态'] == '未知', 'c'].sum() / tot)}
    est_any = bool(est['n_static']) and bool((A['m'] < 0).any())
    summ = dict(window=window, n_months=n, reference=ref, ref_rows=int(sum(ref.values())),
                n_products=int(Pk['pid'].nunique()), n_families=int(Pk['fam'].nunique()),
                n_images=int(Pk.drop_duplicates('pid')['主图'].map(_clean).astype(bool).sum()) if '主图' in Pk.columns else 0,
                n_families_sold=int(A.loc[A['c'] > 0, 'fam'].nunique()), n_excluded=int(_excluded_mask(P).sum()),
                sales=_f(tot), sales_monthly=_f(A.loc[A['m'] >= 0, 'c'].sum()), sales_est=_f(A.loc[A['m'] < 0, 'c'].sum()),
                sales_est_low=_f(A.loc[A['m'] < 0, 'c_low'].sum()), sales_low=_f(A['c_low'].sum()),
                monthly_avg=_f(tot / n) if n else None, monthly_avg_low=_f(A['c_low'].sum() / n) if n else None,
                monthly_share=_f(A.loc[A['m'] >= 0, 'c'].sum() / tot) if tot else None,
                framed_share=_f(A.loc[ok, 'c'].sum() / tot) if tot else None, noframe_share=_f(A.loc[nof, 'c'].sum() / tot) if tot else None,
                pending_share=_f(A.loc[~ok & ~nof, 'c'].sum() / tot) if tot else None, pending_products=len(pend_pids), pending_entries=len(pend),
                pending_reasons=dict(collections.Counter(e['reason'] for e in pend)), reasons=reasons, estimate=est, estimated=est_any,
                family_note=FAMILY_NOTE[channel], n_static=est['n_static'])
    frames, units = ([], {}) if not n or not tot else metrics(A, n, est_any)
    cov = frame_cover(A) if frames else {}
    framed_tot = sum(f['units'] for f in frames)
    for f in frames:
        e, w = cov.get(f['frame'], (None, None))
        f['cover'], f['cover_worst'] = _f(e), _f(w)
        f['read'] = 'small' if f['units'] < READ_MIN else readability(f['cover'], f['monthly_share'])
        f['channel_share'] = _f(f['units'] / framed_tot) if framed_tot else None
        f['low_below'] = bool(f['estimated'] and f['units_low'] < fmin)
    big = sorted([f for f in frames if f['units'] >= fmin], key=lambda f: -f['units'])
    small = [f for f in frames if f['units'] < fmin]
    az = amazon_cells() if with_amazon else {}
    out_units = {}
    for f in big:
        us = [u for u in units.get(f['frame'], []) if u['units'] >= U_MIN]
        for u in us:
            a = az.get((f"{f['size']} · {f['form']}", u['attr'], u['value']))
            u['amazon'] = a
        us.sort(key=lambda u: (ATTRS.index(u['attr']), -u['units']))
        out_units[f['frame']] = us
    summ.update(frame_min=fmin, frames_all=len(frames), frames_big=len(big), frames_small=sum(f['read'] == 'small' for f in big), frames_readable=sum(f['read'] == 'ok' for f in big),
                small_n=len(small), small_units=_f(sum(f['units'] for f in small)), amazon_months=az.get('_months', '') if az else '')
    state = 'insufficient' if not big else 'ok'
    return dict(channel=channel, state=state, summary=summ, frames=big, units=out_units, pending=pend, trend_ok=n >= 6)


# ====================================================================== 6. 读写版本、导入、重算
def _version_frames(version_id: int):
    with session() as s:
        P = pd.DataFrame([dict(渠道=CHANNEL_NAMES[p.channel], ch=p.channel, fam=p.fam, pid=p.pid, title=p.title, 品牌=p.brand, 来源=p.source,
                               尺寸段=p.size or np.nan, 装=p.asm or np.nan, 形态=p.form or np.nan, 台面材质=p.top or np.nan, 主色=p.color or np.nan,
                               柜体材质=p.cab or np.nan, 元素=p.elements or np.nan, 价格=p.price, 评分=p.rating, 页面评论数=p.reviews,
                               首评月=p.first_month or np.nan, **{k: (p.raw or {}).get(k, np.nan) for k in RAW_KEYS})
                          for p in s.scalars(select(ResearchProduct).where(ResearchProduct.version_id == version_id))])
        M = pd.DataFrame([dict(渠道=CHANNEL_NAMES[m.channel], ch=m.channel, fam=m.fam, pid=m.pid, 尺寸段=m.size or np.nan, 装=m.asm or np.nan,
                               形态=m.form or np.nan, 月=m.month, VP=m.vp, 非VP=m.nonvp, 销量=m.units)
                          for m in s.scalars(select(ResearchMonthly).where(ResearchMonthly.version_id == version_id))])
        ver = s.get(ResearchVersion, version_id)
        flags = (ver.summary or {}).get('_cols', {}) if ver else {}
    for c in ('价格', '评分', '页面评论数'):
        P[c] = pd.to_numeric(P[c], errors='coerce')
    if M.empty:
        M = pd.DataFrame(columns=MON_COLS + ['ch'])
    P.attrs['has_monthly_source'] = bool(flags.get('月度来源'))
    if not flags.get('月度来源'):
        P = P.drop(columns=['月度来源'])
    P.attrs['has_first_month'] = bool(flags.get('首评月')) and P['首评月'].notna().any()
    for k in ('多尺寸段', '浴室柜'):
        if not flags.get(k):
            P = P.drop(columns=[k])
    return P, M


def current_version(channel: str):
    with session() as s:
        return s.scalar(select(ResearchVersion).where(ResearchVersion.channel == channel, ResearchVersion.status == 'current')
                        .order_by(ResearchVersion.id.desc()).limit(1))


def result(channel: str):
    with session() as s:
        return s.scalar(select(ResearchResult).where(ResearchResult.channel == channel).order_by(ResearchResult.id.desc()).limit(1))


def recompute(channel: str) -> tuple[bool, str]:
    """该渠道按当前版本与当前分框确认重算并写缓存（AC-F30-29）。出错时保留上次结果，记出错原因与时间（DEC-106）。"""
    ver = current_version(channel)
    if ver is None:
        return False, '尚未导入'
    with session() as s:
        r = s.scalar(select(ResearchResult).where(ResearchResult.channel == channel).order_by(ResearchResult.id.desc()).limit(1))
        if r is None:
            r = ResearchResult(channel=channel, version_id=ver.id, data={})
            s.add(r)
        r.status = 'running'
    try:
        P, M = _version_frames(ver.id)
        data = compute(channel, P, M)
    except Exception as e:  # noqa: BLE001 —— DEC-106：出错保留上次结果并显示原因（原因原样记录，不吞掉）
        with session() as s:
            r = s.scalar(select(ResearchResult).where(ResearchResult.channel == channel).order_by(ResearchResult.id.desc()).limit(1))
            r.status, r.error, r.error_at = 'error', f'{type(e).__name__}: {e}', now()
        return False, f'{type(e).__name__}: {e}'
    with session() as s:
        r = s.scalar(select(ResearchResult).where(ResearchResult.channel == channel).order_by(ResearchResult.id.desc()).limit(1))
        r.version_id, r.data, r.computed_at, r.status, r.error, r.error_at = ver.id, data, now(), 'ok', '', None
        r.pending_n = len(data.get('pending', []))
    return True, ''


def status_all() -> dict:
    """三个渠道的页签状态：none 尚未导入 / insufficient 数据不足 / ok（可读 x / 达标 y 框）。"""
    out = {}
    for ch in CHANNELS:
        r = result(ch)
        ver = current_version(ch)
        if ver is None or r is None or not r.data:
            out[ch] = dict(state='none', name=CHANNEL_NAMES[ch])
            continue
        sm = r.data.get('summary', {})
        out[ch] = dict(state=r.data.get('state'), name=CHANNEL_NAMES[ch], readable=sm.get('frames_readable', 0), big=sm.get('frames_big', 0),
                       pending=sm.get('pending_products', 0), entries=sm.get('pending_entries', 0), window=sm.get('window', []),
                       computed_at=r.computed_at, status=r.status, error=r.error, version=ver)
    return out


def pending_entries(channel: str | None = None) -> list[dict]:
    """打标确认队列里的"分框未知（渠道调研）"条目（来自各渠道最近一次计算结果）。"""
    out = []
    for ch in ([channel] if channel else CHANNELS):
        r = result(ch)
        if r is None or not r.data or current_version(ch) is None:
            continue
        for e in r.data.get('pending', []):
            out.append(dict(e, channel=ch))
    return out


def pending_by_channel() -> dict:
    """各渠道"分框未知（渠道调研）"条目数（只读计数列，不读整份结果）。没有当前版本的渠道为 0。"""
    from sqlalchemy import func
    out = {ch: 0 for ch in CHANNELS}
    with session() as s:
        cur = set(s.scalars(select(ResearchVersion.id).where(ResearchVersion.status == 'current')))
        last = select(func.max(ResearchResult.id)).group_by(ResearchResult.channel)
        for r in s.scalars(select(ResearchResult).where(ResearchResult.id.in_(last))):
            if r.version_id in cur:
                out[r.channel] = r.pending_n or 0
    return out


def pending_count(channel: str | None = None) -> int:
    c = pending_by_channel()
    return c.get(channel, 0) if channel else sum(c.values())


def confirm(channel: str, pid: str, tag: str, value: str, user_id: int) -> tuple[bool, str]:
    """确认一个调研商品的分框标签（AC-F30-28、AC-F30-29）：值写 Tag（人工确认，与机会扫描共用，RA-120）；"不进框"写 ResearchOverride。
    确认后该渠道调研重算。返回 (重算是否成功, 出错原因)。"""
    entry = next((e for e in pending_entries(channel) if e['pid'] == pid and e['tag'] == tag), None)
    if entry is None:
        raise ValueError('这个商品已不在分框待确认队列里')
    if value not in entry['candidates']:
        raise ValueError(f'“{value}”不是这个商品的候选值')
    with session() as s:
        if value == NOFRAME:
            s.add(ResearchOverride(channel=channel, pid=pid, tag='尺寸段', value=NOFRAME, by=user_id))
        else:
            s.execute(delete(ResearchOverride).where(ResearchOverride.channel == channel, ResearchOverride.pid == pid))
            t = s.scalar(select(Tag).where(Tag.channel == channel, Tag.item_id == pid, Tag.tag == tag))
            if t is None:
                t = Tag(channel=channel, item_id=pid, tag=tag, source='manual', auto_value='', confidence=0.0)
                s.add(t)
            t.value, t.status, t.confirm_mode, t.confirmed_by, t.confirmed_at = value, 'confirmed', 'single', user_id, now()
    from . import panel
    panel.clear_cache()
    return recompute(channel)


# ---------------- 导入（API-F30-01） ----------------
def _import_dir(import_id: int):
    d = data_dir() / 'research' / str(import_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _conflicts(channel: str, Pc: pd.DataFrame, Mc: pd.DataFrame, window: list[str]) -> list[dict]:
    """与已并入评论 VP 数据（F28）逐月对照（AC-F30-06）：类目节点 / 两者商品所在家族当月 VP + 非VP vs 已并入批次去重条数。"""
    fams = set(Pc.loc[Pc['来源'].astype(str).isin(['类目节点', '两者']), 'fam'])
    cat = Mc[Mc['fam'].isin(fams)]
    out = []
    with session() as s:
        for m in window:
            b = s.scalar(select(Batch).where(Batch.channel == channel, Batch.month == m, Batch.status == 'merged')
                         .order_by(Batch.created_at.desc(), Batch.id.desc()).limit(1))
            if b is None:
                continue
            d = (b.checks or {}).get('dedup') or {}
            have = float(d.get('vp', 0) or 0) + float(d.get('nonvp', 0) or 0)
            g = cat[cat['月'] == m]
            imp = float(g['VP'].sum() + g['非VP'].sum())
            diff = (imp - have) / have if have else None
            bad = (have == 0 and imp > 0) or (have > 0 and abs(imp - have) / have > 0.05)
            out.append(dict(month=m, imported=imp, merged=have, diff=_f(diff), bad=bool(bad)))
    return out


def start_import(prod_name: str, prod_bytes: bytes, mon_name: str, mon_bytes: bytes, user_id: int) -> tuple[list[dict], int | None]:
    """上传 → 检查 → 核对摘要（AC-F30-01～06）。检查不通过返回问题列表、不写库；通过则记一次"待确认"的导入（替换之前未确认的那次，RA-129）。"""
    try:
        P0, M0 = read_csv(prod_bytes), read_csv(mon_bytes)
    except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as e:
        return [dict(title='文件不是可读的 CSV（UTF-8）', n=None, examples=[str(e)[:200]])], None
    probs = check(P0, M0)
    if probs:
        return probs, None
    P, M = normalize(P0, M0)
    summary = {}
    for ch in CHANNELS:
        Pc, Mc = P[P['ch'] == ch].copy(), M[M['ch'] == ch].copy()
        if Pc.empty:
            continue
        Pc.attrs.update(P.attrs)
        data = compute(ch, Pc, Mc, with_amazon=False)
        sm = data['summary']
        conf = _conflicts(ch, Pc, Mc, sm['window'])
        cur = current_version(ch)
        summary[ch] = dict(name=CHANNEL_NAMES[ch], state=data['state'], summary=sm, conflicts=conf, conflict=any(c['bad'] for c in conf),
                           current=dict(no=cur.no, at=cur.created_at.strftime('%Y-%m-%d %H:%M')) if cur else None,
                           n_products_rows=int(len(Pc)), n_monthly_rows=int(len(Mc)))
    with session() as s:
        for old in s.scalars(select(ResearchImport).where(ResearchImport.status == 'pending')):
            shutil.rmtree(data_dir() / 'research' / str(old.id), ignore_errors=True)
            s.delete(old)
        imp = ResearchImport(created_by=user_id, status='pending', summary=summary,
                             files=dict(products=prod_name, monthly=mon_name, products_sha=hashlib.sha256(prod_bytes).hexdigest(),
                                        monthly_sha=hashlib.sha256(mon_bytes).hexdigest(), rows=[int(len(P0)), int(len(M0))],
                                        cols={k: k in P0.columns for k in ('月度来源', '首评月', '多尺寸段', '浴室柜')}))
        s.add(imp)
        s.flush()
        iid = imp.id
    d = _import_dir(iid)
    (d / 'products.csv').write_bytes(prod_bytes)
    (d / 'monthly.csv').write_bytes(mon_bytes)
    return [], iid


def pending_import():
    with session() as s:
        return s.scalar(select(ResearchImport).where(ResearchImport.status == 'pending').order_by(ResearchImport.id.desc()).limit(1))


def abandon(import_id: int) -> bool:
    with session() as s:
        imp = s.get(ResearchImport, import_id)
        if imp is None or imp.status != 'pending':
            return False
        imp.status, imp.decided_at = 'abandoned', now()
    return True


def confirm_import(import_id: int, channels: list[str], user_id: int) -> list[str]:
    """确认导入勾选的渠道（AC-F30-05、AC-F30-07）：该渠道当前版本标"已替换"，写入新版本商品与月销，再计算；未勾选的渠道不变。"""
    with session() as s:
        imp = s.get(ResearchImport, import_id)
        if imp is None or imp.status != 'pending':
            raise ValueError('这次导入已确认或已放弃')
        chs = [c for c in channels if c in (imp.summary or {})]
        if not chs:
            raise ValueError('至少勾选一个渠道')
        files, cols = dict(imp.files), (imp.files or {}).get('cols', {})
    d = _import_dir(import_id)
    P, M = normalize(read_csv((d / 'products.csv').read_bytes()), read_csv((d / 'monthly.csv').read_bytes()))
    for ch in chs:
        Pc, Mc = P[P['ch'] == ch], M[M['ch'] == ch]
        window, _ = window_of(Mc)
        with session() as s:
            last = s.scalar(select(ResearchVersion).where(ResearchVersion.channel == ch).order_by(ResearchVersion.no.desc()).limit(1))
            for old in s.scalars(select(ResearchVersion).where(ResearchVersion.channel == ch, ResearchVersion.status == 'current')):
                old.status = 'replaced'
            sm = (imp.summary or {}).get(ch, {}).get('summary', {})
            ver = ResearchVersion(import_id=import_id, channel=ch, no=(last.no + 1) if last else 1, status='current', created_by=user_id,
                                  files=dict(products=files.get('products'), monthly=files.get('monthly')), n_products=sm.get('n_products', 0),
                                  n_families=sm.get('n_families', 0), months=[window[0], window[-1]] if window else [],
                                  summary=dict(_cols=cols, ref_rows=sm.get('ref_rows', 0)))
            s.add(ver)
            s.flush()
            vid = ver.id
            prods = []
            for r in Pc.to_dict('records'):
                prods.append(dict(version_id=vid, channel=ch, fam=r['fam'], pid=r['pid'], title=_clean(r.get('title')), brand=_clean(r.get('品牌')),
                                  source=_clean(r.get('来源')), size=_clean(r.get('尺寸段')), asm=_clean(r.get('装')), form=_clean(r.get('形态')),
                                  top=_clean(r.get('台面材质')), color=_clean(r.get('主色')), cab=_clean(r.get('柜体材质')), elements=_clean(r.get('元素')),
                                  price=_f(r.get('价格')), rating=_f(r.get('评分')), reviews=_f(r.get('页面评论数')), first_month=_clean(r.get('首评月')),
                                  raw={k: _clean(r.get(k)) for k in RAW_KEYS if k in Pc.columns}, category='浴室柜'))
            s.execute(insert(ResearchProduct), prods)
            mons = [dict(version_id=vid, channel=ch, fam=r['fam'], pid=r['pid'], size=_clean(r.get('尺寸段')), asm=_clean(r.get('装')),
                         form=_clean(r.get('形态')), month=r['月'], vp=float(r['VP']), nonvp=float(r['非VP']), units=float(r['销量']))
                    for r in Mc.to_dict('records')]
            if mons:
                s.execute(insert(ResearchMonthly), mons)
        recompute(ch)
    with session() as s:
        imp = s.get(ResearchImport, import_id)
        imp.status, imp.imported, imp.decided_at = 'confirmed', chs, now()
    return chs


def records() -> list[dict]:
    """导入记录（AC-F30-07）：各渠道版本（当前 / 已替换）与放弃的核对，按时间倒序。"""
    from ..models import User
    out = []
    with session() as s:
        names = {u.id: u.name for u in s.scalars(select(User))}
        for v in s.scalars(select(ResearchVersion).order_by(ResearchVersion.created_at.desc(), ResearchVersion.id.desc())):
            out.append(dict(no=f'v{v.no}', channel=v.channel, name=CHANNEL_NAMES[v.channel], at=v.created_at, files=v.files,
                            n_products=v.n_products, months=v.months, by=names.get(v.created_by, '—'),
                            status='当前' if v.status == 'current' else '已替换'))
        for imp in s.scalars(select(ResearchImport).where(ResearchImport.status == 'abandoned')):
            for ch, c in (imp.summary or {}).items():
                sm = c.get('summary', {})
                w = sm.get('window') or []
                out.append(dict(no='—', channel=ch, name=CHANNEL_NAMES[ch], at=imp.created_at, files=dict(products=imp.files.get('products'),
                                monthly=imp.files.get('monthly')), n_products=sm.get('n_products', 0), months=[w[0], w[-1]] if w else [],
                                by=names.get(imp.created_by, '—'), status='已放弃'))
    out.sort(key=lambda r: r['at'], reverse=True)
    return out


def backtest_marks(channel: str) -> dict:
    """AC-F30-25：该渠道最近一次回测为"经回测（打折）"时，各单元（框|属性|取值）的分级。"""
    from . import channel_model
    run = channel_model.latest(channel)
    if run is None or run.evidence != channel_model.EVIDENCE_OK:
        return {}
    return {k: dict(grade=v.get('grade'), evidence=run.evidence) for k, v in (run.units or {}).items() if v.get('grade')}


# ====================================================================== 7. 决策卡渠道段读取（AC-F21-15～18，revision 10；只读，不写 F28）
def unit_view(channel: str, frame: str, attr: str, value: str) -> dict:
    """决策卡 Lowe's / Wayfair 行：当前调研版本里同框同属性取值的结果；不可用时给原因（AC-F21-16）。"""
    ver = current_version(channel)
    r = result(channel)
    if ver is None or r is None or not r.data:
        return dict(state='none', reason='尚未导入渠道调研')
    data = r.data
    sm = data.get('summary') or {}
    win = sm.get('window') or []
    base = dict(window=f'{win[0]} 至 {win[-1]}' if win else '', months=[m[2:] for m in win], frame_min=sm.get('frame_min', FR_MIN))
    if data.get('state') == 'insufficient':
        return dict(base, state='na', reason=f"该渠道调研数据不足（没有框达到月均 {sm.get('frame_min', FR_MIN):.0f} 件门槛）")
    f = next((x for x in data.get('frames', []) if x['frame'] == frame), None)
    if f is None:
        return dict(base, state='na', reason=f"该框月均不到门槛（{sm.get('frame_min', FR_MIN):.0f} 件）")
    u = next((x for x in (data.get('units') or {}).get(frame, []) if x['attr'] == attr and x['value'] == value), None)
    read = f.get('read')
    if u is None:
        return dict(base, state='na', read=read, reason=f'该取值在这个框里月均不到 {U_MIN} 件')
    out = dict(base, state='ok', read=read, frame_units=f['units'], units=u['units'], families=u['families'], share=u['share'],
               share_pre=u.get('share_pre'), share_rec=u.get('share_rec'), series=u.get('series') or [], estimated=u.get('estimated'),
               cover=f.get('cover'), monthly_share=f.get('monthly_share'), per_family=f.get('per_family'))
    if read == 'noconc':
        out.update(reason=f"不下结论（分框覆盖 {(f.get('cover') or 0) * 100:.0f}%）", share_pre=None, share_rec=None, series=[])
    elif read == 'notrend':
        out.update(reason=f"趋势不下结论（有月度 {(f.get('monthly_share') or 0) * 100:.0f}%）", share_pre=None, share_rec=None, series=[])
    elif read == 'small':
        out.update(reason='样本少，只作参考')
    return out


def unit_products(channel: str, frame: str, attr: str, value: str, top: int = 5) -> dict:
    """同框同属性取值按窗口月销的前 N 款与近 6 个月新款（AC-F21-17、18）。款 = 导入的 fam；代表商品取窗口销量最大的 pid。"""
    ver = current_version(channel)
    if ver is None:
        return dict(top=[], new=[])
    P, M = _version_frames(ver.id)
    window, _ = window_of(M)
    n = len(window)
    if not n or P.empty:
        return dict(top=[], new=[])
    conf, nof = confirmations(channel, P['pid'])
    A, _est = build_rows(P[~_excluded_mask(P)], M, window, conf, nof)
    A = A[frameable(A)].copy()
    A['框'] = A['尺寸段'].astype(str) + ' · ' + A['装'] + ' · ' + A['形态']
    G = A[A['框'] == frame]
    if G.empty:
        return dict(top=[], new=[])
    famavg = G['c'].sum() / n / max(G.loc[G['c'] > 0, 'fam'].nunique(), 1)
    U = G[G[attr].map(lambda v: value in v) if attr == '元素' else G[attr] == value]
    if U.empty:
        return dict(top=[], new=[])
    pi = P.drop_duplicates('pid').set_index('pid')
    from .channels import item_link
    rows = []
    for fam, g in U.groupby('fam'):
        tot = g['c'].sum()
        if tot <= 0:
            continue
        pid = g.groupby('pid')['c'].sum().idxmax()
        r = pi.loc[pid]
        mon = g[g['m'] >= 0].groupby('m')['c'].sum()
        series = [_f(mon.get(i)) if i in mon.index else None for i in range(n)]
        e = g['进入月'].iloc[0]
        new = bool(g['新家族'].iloc[0]) and pd.notna(e) and int(e) >= n - 6
        e = int(e) if pd.notna(e) else None
        since = g.loc[g['m'] >= (e or 0), 'c'].sum() / (n - (e or 0)) if e is not None else None
        fm_ = _clean(r.get('首评月')) if hasattr(r, 'get') else ''
        rows.append(dict(fam=str(fam), pid=str(pid), title=_clean(r.get('title')), brand=_clean(r.get('品牌')), price=_f(r.get('价格')),
                         rating=_f(r.get('评分')), reviews=_f(r.get('页面评论数')), image=_clean(r.get('主图')) if '主图' in pi.columns else '',
                         link=item_link(channel, pid), units=_f(tot / n), listed=fm_ or (window[e] if e is not None and e < n else ''),
                         listed_kind='首评月' if fm_ else '首次有销量', series=series, months=[m[2:] for m in window],
                         new=new, sold=bool(since is not None and since >= famavg)))
    rows.sort(key=lambda x: -(x['units'] or 0))
    return dict(top=rows[:top], new=[x for x in rows if x['new']][:top], per_family=_f(famavg))
