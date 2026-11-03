"""分渠道模型与回测（REQ-F19-03、AC-F19-05 / 06；API-F19-02；DATA-F19-02）。

移植 `solution-v2/trial/小平台_HD回测小试.py` 的“框 × 属性”回测（§5.1），只用该渠道的重建数据：
- 单元 = 框（尺寸段 × 装 × 形态，装未知不进框）× 属性取值（台面材质 / 元素 / 主色 / 柜体材质）；
  份额 = 单元月销 ÷ 该属性已知且框已知的总月销（元素多值时分母按商品页去重）。
- 特征（只用 T 之前 6 个月）：b6 份额斜率、x5 新品占比差（单元 − 品类，新品 = 首条评论后 ≤ 6 个月）、x2 新进家族、x4 体量；没有 x3（渠道没有站内搜索）。
- 目标：立项后第 6–8 个月份额对近 6 个月份额的对数变化 y6；回归式同第九版（k ∈ {0, 3, 6, 8} 交互，按体量档 × k 纠偏与标准差），
  “把握” = Φ(第 6–8、8–10 个月预测平均 ÷ 标准差)。每个 T0 只用 T0 之前结果已知的样本（近 3 月 ≥ 50 件）。
- 立项时点 T0 = 起始月 + 15 至 数据截至月 − 8（数据 2024-01 至 2026-10 时为 2025-04 至 2026-02，共 11 个）。
- 大单元 = 近 3 个月月均 ≥ 品类近 22 个月月均的 1%（取整到 10 件）；D 档 = 把握 ≤ 30% 的大单元。
- 合计指标：把握四档与 D 档之后变大比例按全部拟合时点合并；秩相关、方向对为各时点平均（同小试报告）。
- 有效性（AC-F19-06）：把握四档逐档上升且 D 档之后变大 ≤ 30% → 证据等级“经回测（打折）”，否则“未验证”。
- 打折后读法读品类配置 `channels.<渠道>.discount`：秩相关减 rank_corr、把握 ≥ 70% 档减 high_pp 个百分点、方向对按 ≤ dir_cap% 看；其他指标不改。
- Amazon 侧丰富度（AC-F29-05）：同尺寸段 × 形态 × 属性取值（不分拆装）T 前 6 个月 Amazon 有销量的家族数；在回测面板上做“基础 → 加差距 G家族 /
  只加 Amazon 家族数”的跨单元 5 折交叉验证（同 `跨渠道供给差_HD检验.py` §3），作为该渠道评分的信号证据展示；滚动回测本身不放它
  （Amazon 表从 2024-10 起，T0 前能拿到完整 Amazon 窗口的训练时点太少，做不了按时间滚动，见检验报告 §3）。
"""
import os
import threading
import traceback

import numpy as np
import pandas as pd
from scipy.stats import norm, spearmanr
from sklearn.linear_model import Ridge
from sqlalchemy import select

from .. import catconfig
from ..config import CHANNEL_NAMES
from ..db import session
from ..models_channel import ChannelModelRun
from . import panel, richness
from .families import mi, ms

KS = (0, 3, 6, 8)
XS = ['b6', 'x2', 'x4', 'x5']
EPS = 0.001
ATTRS = ('台面材质', '元素', '主色', '柜体材质')
UNKS = {'未知', '信息不足', '待图片核验', '', 'nan', 'None', None}
MIN_MONTHS = 20
EVIDENCE_OK, EVIDENCE_NO = '经回测（打折）', '未验证'
BINS = (('≤30%', 0, 0.3), ('30–50%', 0.3, 0.5), ('50–70%', 0.5, 0.7), ('≥70%', 0.7, 1.01))
SIGNAL_NAMES = {'b6': '份额斜率（近 6 个月）', 'x5': '新品占比差（单元 − 品类）', 'x2': '新进家族（相对增长）', 'x4': '体量（ln 月均销，中心化）',
                'az': 'Amazon 侧丰富度（同尺寸段 × 形态 × 属性取值、不分拆装的 Amazon 家族数）'}


def _known(s: pd.Series) -> pd.Series:
    return ~s.isin(list(UNKS)) & s.notna()


def _f(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)


# ====================================================================== 行级表
def rows_from_analysis(A: pd.DataFrame) -> pd.DataFrame:
    """panel.Analysis.A（其他渠道）→ 小试口径的行级表：fam, pid, m, c, 新, 尺寸段, 装, 形态, 框, 属性列, 元素（列表）, 价格。
    新品 = 首条评论月后 ≤ 6 个月（m − L ≤ 6，与小试同；panel 的 月龄 ≤ 6 相当于 ≤ 5）。"""
    zh = A['装'].map(lambda v: v if v in ('整装', '拆装') else '未知')
    size = A['尺寸段'].where(A['尺寸段'].notna() & (A['尺寸段'].astype(str) != ''), None)
    form = A['形态'].replace({'两用': '落地式'})
    R = pd.DataFrame({'fam': A['家族键'].values, 'pid': A['子ASIN'].astype(str).values, 'm': A['m'].values, 'c': A['c'].values,
                      '新': ((A['m'] - A['L']) <= 6).values, '尺寸段': size.values, '装': zh.values, '形态': form.values,
                      '台面材质': A['D8台面材质'].map(lambda v: '未知' if v in UNKS or (isinstance(v, float) and np.isnan(v)) else v).values,
                      '主色': A['主色'].values, '柜体材质': A['柜体材质'].values,
                      '元素': A['元素一'].map(lambda l: list(l) if len(l) else ['未知']).values,
                      '价格': pd.to_numeric(A['价格'], errors='coerce').values})
    R['框'] = np.where(R['尺寸段'].notna() & (R['装'] != '未知'), R['尺寸段'].fillna('') + ' · ' + R['装'] + ' · ' + R['形态'], '未知')
    return R


# ====================================================================== 回测
class ChannelBacktest:
    """一个渠道的“框 × 属性”面板、特征、目标与滚动拟合（小试 §5 的 build / feats / target / run）。"""

    def __init__(self, rows: pd.DataFrame, end: int | None = None):
        self.A = rows.reset_index(drop=True)
        self.M0 = int(self.A['m'].min())
        self.END = int(end if end is not None else self.A['m'].max())
        self.MONTHS = list(range(self.M0, self.END + 1))
        A, MONTHS = self.A, self.MONTHS
        self.CAT = A.groupby('m')['c'].sum().reindex(MONTHS, fill_value=0)
        self.CATN = A[A['新']].groupby('m')['c'].sum().reindex(MONTHS, fill_value=0)
        lo = max(self.M0, self.END - 21)
        self.BIG = round(float(self.CAT.loc[lo:self.END].mean()) * 0.01, -1)
        Ax = A.explode('元素')
        self.pans = []
        for att in ATTRS:
            rows_ = (Ax if att == '元素' else A).reset_index(drop=True)
            frk = rows_['框'].where(rows_['框'] != '未知')
            key = (frk + ' | ' + att + '：' + rows_[att].astype(str)).where(_known(rows_[att]) & frk.notna())
            df = rows_.assign(_k=key).dropna(subset=['_k'])
            C = df.groupby(['_k', 'm'])['c'].sum().unstack(fill_value=0).reindex(columns=MONTHS, fill_value=0)
            N = df[df['新']].groupby(['_k', 'm'])['c'].sum().unstack(fill_value=0).reindex(index=C.index, columns=MONTHS, fill_value=0)
            F = df.groupby(['_k', 'm'])['fam'].nunique().unstack(fill_value=0).reindex(columns=MONTHS, fill_value=0)
            den = rows_.loc[rows_.index.isin(df.index.unique())].drop_duplicates(['fam', 'pid', 'm']).groupby('m')['c'].sum().reindex(MONTHS, fill_value=0)
            self.pans.append((f'框 × {att}', C, N, F, den))
        self._fe, self._y = {}, {}

    @staticmethod
    def mean3(X, a):
        return X.loc[:, [m for m in range(a, a + 3) if m in X.columns]].mean(axis=1)

    def feats(self, T):
        if T in self._fe:
            return self._fe[T]
        mean3, CAT, CATN = self.mean3, self.CAT, self.CATN
        out = []
        for nm, C, N, F, den in self.pans:
            b1 = mean3(C, T - 3)
            d1 = den.loc[T - 3:T - 1].mean()
            f1, f0 = mean3(F, T - 3), mean3(F, T - 6)
            cols6 = list(range(T - 6, T))
            xc = np.arange(6) - 2.5
            D = pd.DataFrame({'属性': nm, '取值': C.index, '近3月': b1.values, '分母': d1})
            D['份额6'] = (C[cols6].sum(axis=1) / max(den.loc[T - 6:T - 1].sum(), 1)).values
            D['b6'] = ((np.log(C[cols6].div(den.loc[T - 6:T - 1].replace(0, np.nan), axis=1).fillna(0) + EPS) * xc).sum(axis=1) / (xc ** 2).sum()).values
            D['x5'] = (N[cols6].sum(axis=1) / C[cols6].sum(axis=1).replace(0, np.nan)).fillna(0).values \
                - CATN.loc[T - 6:T - 1].sum() / max(CAT.loc[T - 6:T - 1].sum(), 1)
            D['x2'] = ((f1 - f0) / (f0 + 1)).values
            out.append(D)
        D = pd.concat(out, ignore_index=True)
        D = D[D['近3月'] > 0].copy()
        D['x4'] = np.log(D['近3月'] + 5)
        D['T'] = T
        D = D.set_index(['属性', '取值'])
        self._fe[T] = D
        return D

    def target(self, T, k):
        if (T, k) in self._y:
            return self._y[(T, k)]
        D = self.feats(T)
        a = T + k
        if a + 2 > self.END:
            y = pd.Series(np.nan, index=D.index)
        else:
            res = {}
            for nm, C, N, F, den in self.pans:
                s = self.mean3(C, a) / max(den.loc[a:a + 2].mean(), 1)
                for v, x in s.items():
                    res[(nm, v)] = x
            s = pd.Series([res.get(i, 0.0) for i in D.index], index=D.index)
            y = np.log((s + EPS) / (D['份额6'] + EPS))
        self._y[(T, k)] = y
        return y

    def tier(self, b):
        return np.where(b >= self.BIG, '大', '小')

    @staticmethod
    def design(D, k):
        X = D[XS].copy()
        X['x4'] = X['x4'] - 5.0
        for x in XS:
            X[x + '·k'] = X[x] * k / 3
        X['k'] = k / 3
        return X

    def predict(self, T0, minv=50):
        """站在 T0：用 T0 之前结果已知的 (T, k) 拟合，给 T0 的每个单元把握。训练样本 < 100 或只有一个 k 时不拟合，降级为仅 b6 排序。"""
        rows = []
        for T in range(self.M0 + 6, T0):
            for k in KS:
                if T + k + 2 > T0 - 1:
                    continue
                D = self.feats(T)
                yy = self.target(T, k)
                ok = (D['近3月'] >= minv) & yy.notna()
                X = self.design(D[ok], k)
                X['y'] = yy[ok]
                X['tier'] = self.tier(D.loc[ok, '近3月'].values)
                X['kk'] = k
                rows.append(X)
        Tr = pd.concat(rows) if rows else pd.DataFrame()
        D = self.feats(T0).copy()
        fitted = len(Tr) >= 100 and Tr['kk'].nunique() >= 2
        coef = {}
        if fitted:
            cols = [c for c in Tr.columns if c not in ('y', 'tier', 'kk')]
            m = Ridge(alpha=1e-6).fit(Tr[cols], Tr['y'])
            Tr['res'] = Tr['y'] - m.predict(Tr[cols])
            q = Tr.groupby(['tier', 'kk'])['res'].agg(['mean', 'std'])

            def qg(t, k, c):
                if t not in q.index.get_level_values(0):
                    t = q.index.get_level_values(0)[0]  # 该体量档没有训练样本 → 用有的那档
                ks = list(q.loc[t].index)
                if k in ks:
                    return q.at[(t, k), c]
                kmax = max(ks)
                f = np.sqrt((k + 3) / (kmax + 3))
                return q.at[(t, kmax), c] * (f if c == 'std' else 1)
            tier = self.tier(D['近3月'].values)
            preds = {}
            for k in (6, 8):
                preds[k] = m.predict(self.design(D, k)[cols]) + np.array([qg(t, k, 'mean') for t in tier])
                D[f'sd{k}'] = [qg(t, k, 'std') for t in tier]
            D['预测'] = preds[6]
            D['预测8'] = preds[8]
            D['把握'] = norm.cdf(((preds[6] + preds[8]) / 2) / ((D['sd6'] + D['sd8']) / 2))
            coef = dict(zip(cols, m.coef_))
        else:
            D['预测'] = D['b6']
            D['把握'] = np.nan
        D['T0'] = T0
        D['拟合'] = fitted
        D['训练'] = len(Tr)
        D['coef_b6_k6'] = coef.get('b6', np.nan) + 2 * coef.get('b6·k', 0) if coef else np.nan
        D['coef_x5_k6'] = coef.get('x5', np.nan) + 2 * coef.get('x5·k', 0) if coef else np.nan
        return D, coef

    def t0s(self):
        return list(range(self.M0 + 15, self.END - 8 + 1))

    def run(self):
        res = []
        for T0 in self.t0s():
            D, _ = self.predict(T0)
            D['y6'] = self.target(T0, 6)
            res.append(D.dropna(subset=['y6']))
        return pd.concat(res) if res else pd.DataFrame()

    def metr(self, d):
        BIG = self.BIG
        big = d[d['近3月'] >= BIG]
        nz = big['y6'].abs() > 0.05
        sp = lambda a, b: spearmanr(a, b)[0] if len(a) > 4 else np.nan  # noqa: E731
        r = dict(n=len(d), nb=len(big), rho=sp(d['预测'], d['y6']), rhob=sp(big['预测'], big['y6']),
                 dirn=(np.sign(big.loc[nz, '预测']) == np.sign(big.loc[nz, 'y6'])).mean() if nz.sum() else np.nan, ndir=int(nz.sum()),
                 rb6=sp(d['b6'], d['y6']), rb6b=sp(big['b6'], big['y6']), rx5=sp(d['x5'], d['y6']), rx5b=sp(big['x5'], big['y6']),
                 up=(d['y6'] > 0).mean())
        if d['把握'].notna().any():
            for lab, lo, hi in BINS:
                x = d[(d['把握'] > lo if lo else d['把握'] >= 0) & (d['把握'] <= hi)]
                r[lab] = ((x['y6'] > 0).mean() if len(x) else np.nan, len(x))
            Dd = big[big['把握'] <= 0.3]
            r['D'] = ((Dd['y6'] > 0).mean() if len(Dd) else np.nan, len(Dd))
        return r


def summarize(bt: ChannelBacktest, R: pd.DataFrame) -> dict:
    """回测结果 → 原值指标（可 JSON 化）。"""
    per = []
    for T0, d in R.groupby('T0'):
        r = bt.metr(d)
        per.append(dict(T0=ms(T0), fitted=bool(d['拟合'].iloc[0]), n_train=int(d['训练'].iloc[0]), n=r['n'], nb=r['nb'], rho=_f(r['rho']), rhob=_f(r['rhob']),
                        rb6=_f(r['rb6']), rb6b=_f(r['rb6b']), rx5=_f(r['rx5']), rx5b=_f(r['rx5b']), dirn=_f(r['dirn']), ndir=r['ndir'], up=_f(r['up']),
                        lo=[_f(r.get('≤30%', (np.nan, 0))[0]), int(r.get('≤30%', (np.nan, 0))[1])],
                        hi=[_f(r.get('≥70%', (np.nan, 0))[0]), int(r.get('≥70%', (np.nan, 0))[1])],
                        d=[_f(r.get('D', (np.nan, 0))[0]), int(r.get('D', (np.nan, 0))[1])]))
    Rf = R[R['拟合']]
    out = dict(per_t0=per, big=bt.BIG, t0s=[ms(t) for t in bt.t0s()], fitted_t0=int(Rf['T0'].nunique()) if len(Rf) else 0, n_unit_t=int(len(Rf)))
    if not len(Rf):
        out.update(available=False, reason='训练样本不足，没有一个立项时点能拟合（降级为仅 b6 排序），不做把握分档')
        return out
    r = bt.metr(Rf)
    pf = [x for x in per if x['fitted']]
    avg = lambda k: _f(np.nanmean([np.nan if x[k] is None else x[k] for x in pf]))  # noqa: E731
    out.update(available=True,
               bins=[dict(bin=lab, up=_f(r[lab][0]), n=int(r[lab][1])) for lab, _, _ in BINS],
               d=dict(up=_f(r['D'][0]), n=int(r['D'][1])), up_all=_f(r['up']),
               rho=avg('rho'), rhob=avg('rhob'), rb6=avg('rb6'), rb6b=avg('rb6b'), rx5=avg('rx5'), rx5b=avg('rx5b'), dirn=avg('dirn'),
               n_avg=float(np.mean([x['n'] for x in pf])), nb_avg=float(np.mean([x['nb'] for x in pf])),
               coef_b6_k6=_f(Rf.groupby('T0')['coef_b6_k6'].first().median()), coef_x5_k6=_f(Rf.groupby('T0')['coef_x5_k6'].first().median()))
    return out


def validity(raw: dict) -> dict:
    """AC-F19-06：把握四档逐档上升（有样本的档）且 D 档之后变大 ≤ 30%。"""
    if not raw.get('available'):
        return dict(mono=False, d_ok=False, valid=False, ups=[])
    ups = [b['up'] for b in raw['bins'] if b['n'] and b['up'] is not None]
    mono = len(ups) >= 2 and all(b > a for a, b in zip(ups, ups[1:]))
    d = raw['d']
    d_ok = d['n'] > 0 and d['up'] is not None and d['up'] <= 0.30
    return dict(mono=bool(mono), d_ok=bool(d_ok), valid=bool(mono and d_ok), ups=ups)


def discounted(raw: dict, disc: dict) -> dict:
    """打折后读法（AC-F19-05、AC-F27-04）：只调秩相关、把握 ≥ 70% 档、方向对三项，其他指标与原值相同。"""
    if not raw.get('available'):
        return {}
    rc, hp, cap = float(disc['rank_corr']), float(disc['high_pp']) / 100, float(disc['dir_cap']) / 100
    sub = lambda x, y: None if x is None else x - y  # noqa: E731
    bins = [dict(b, up=sub(b['up'], hp) if b['bin'] == '≥70%' else b['up']) for b in raw['bins']]
    return dict(rho=sub(raw['rho'], rc), rhob=sub(raw['rhob'], rc), dirn=None if raw['dirn'] is None else min(raw['dirn'], cap), dir_cap=cap,
                bins=bins, d=dict(raw['d']), rank_corr=rc, high_pp=float(disc['high_pp']))


# ====================================================================== Amazon 侧丰富度信号的交叉验证
def _cv_pred(df, xs, groups):
    from sklearn.model_selection import GroupKFold
    fe = pd.get_dummies(df['T'].astype(str) + '|' + df['属性'], dtype=float)
    X = pd.concat([df[xs].astype(float), fe], axis=1).values
    y = df['y6'].values
    pred = np.full(len(df), np.nan)
    for tr, te in GroupKFold(5).split(X, y, pd.factorize(groups)[0]):
        b, *_ = np.linalg.lstsq(X[tr], y[tr], rcond=None)
        pred[te] = X[te] @ b
    return pred


def _per_t_rho(df, col, big):
    r = []
    for _, d in df.groupby('T'):
        d = d[d['近3月'] >= big] if big else d
        if len(d) > 4:
            r.append(spearmanr(d[col], d['y6'])[0])
    return _f(np.nanmean(r)) if r else None


def richness_signal(bt: ChannelBacktest, R: pd.DataFrame, ch_rows: pd.DataFrame, az_rows: pd.DataFrame | None) -> dict:
    """在回测面板（全部单元 × T0）上接 Amazon 侧丰富度（忽略装），比较基础（b6、x5、x2、x4）与加 G家族 / 只加 Amazon 家族数的
    跨单元 5 折交叉验证秩相关（各 T0 平均）。Amazon 窗口不完整的 T0 不用。"""
    if az_rows is None or az_rows.empty or R.empty:
        return dict(available=False, reason='没有 Amazon 数据，算不了 Amazon 侧丰富度')
    az_m0 = int(az_rows['m'].min())
    parts = []
    for T0, d in R.groupby('T0'):
        if T0 - 6 < az_m0:
            continue
        d = d.reset_index()
        fr = d['取值'].str.split(' | ', regex=False).str[0]
        val = d['取值'].str.split(' | ', regex=False).str[1]
        att = val.str.split('：').str[0]
        v = val.str.split('：', n=1).str[1]
        size = fr.str.split(' · ').str[0]
        form = fr.str.split(' · ').str[2]
        key = list(zip(att, size + ' · ' + form, v))
        h = richness.counts(ch_rows, T0)
        z = richness.counts(az_rows, T0)
        d['hd_fam'] = [h.get(k, {}).get('fam', 0) for k in key]
        d['az_fam'] = [z.get(k, {}).get('fam', 0) for k in key]
        d['单元'] = d['取值']
        d['属性'] = att.values
        parts.append(d)
    if not parts:
        return dict(available=False, reason='Amazon 数据起始月晚于各立项时点的前 6 个月窗口')
    P = pd.concat(parts, ignore_index=True)
    P['G家族'] = np.log((P['az_fam'] + 1) / (P['hd_fam'] + 1))
    P['lnAZ家族'] = np.log(P['az_fam'] + 1)
    zs = lambda s: (s - s.mean()) / s.std() if s.std() > 0 else s * 0  # noqa: E731
    for c in XS + ['G家族', 'lnAZ家族']:
        P['z_' + c] = zs(P[c].astype(float))
    ZB = ['z_' + c for c in XS]
    out = dict(available=True, n=int(len(P)), t0=[ms(t) for t in sorted(P['T0'].unique())], big=bt.BIG)
    for lab, xs in (('base', ZB), ('g', ZB + ['z_G家族']), ('az', ZB + ['z_lnAZ家族'])):
        P['p_' + lab] = _cv_pred(P, xs, P['单元'])
        out[lab] = dict(rho=_per_t_rho(P, 'p_' + lab, 0), rhob=_per_t_rho(P, 'p_' + lab, bt.BIG))
    out['g_single'] = dict(rho=_per_t_rho(P, 'G家族', 0), rhob=_per_t_rho(P, 'G家族', bt.BIG))
    return out


# ====================================================================== 当前评分（站在数据截至月的下一个月）
def score_now(bt: ChannelBacktest) -> tuple[dict, dict]:
    """T0 = 数据截至月 + 1：每个单元的把握与分级。分级：A 把握 ≥ 70%；D 把握 ≤ 30% 且大单元；B ≥ 50%；其余 C。"""
    T0 = bt.END + 1
    D, coef = bt.predict(T0)
    units = {}
    for (att, key), r in D.iterrows():
        fr, val = key.split(' | ', 1)
        a, v = val.split('：', 1)
        g = r['把握']
        if pd.isna(g):
            grade = None
        elif g >= 0.7:
            grade = 'A'
        elif g <= 0.3 and r['近3月'] >= bt.BIG:
            grade = 'D'
        elif g >= 0.5:
            grade = 'B'
        else:
            grade = 'C'
        units[f'{fr}|{a}|{v}'] = dict(grasp=_f(g), grade=grade, units_3m=_f(r['近3月']), big=bool(r['近3月'] >= bt.BIG), b6=_f(r['b6']), x5=_f(r['x5']),
                                      share6=_f(r['份额6']))
    info = dict(T0=ms(T0), fitted=bool(D['拟合'].iloc[0]) if len(D) else False, n_train=int(D['训练'].iloc[0]) if len(D) else 0,
                coef={k: float(v) for k, v in coef.items()}, window=f'{ms(T0 + 6)} 至 {ms(T0 + 10)}')
    return units, info


# ====================================================================== 状态、运行、存取
_state: dict = {}
_lock = threading.Lock()


def run_state(channel: str) -> dict:
    return dict(_state.get(channel) or dict(running=False, error='', step=''))


def latest(channel: str):
    with session() as s:
        r = s.scalar(select(ChannelModelRun).where(ChannelModelRun.channel == channel).order_by(ChannelModelRun.id.desc()).limit(1))
        if r is not None:
            s.expunge(r)
        return r


def status(channel: str) -> dict:
    """渠道当前证据等级与原因（扫描、决策卡、模型页共用）。Amazon 不走这里。"""
    from . import backfill
    rb = backfill.last_rebuild(channel)
    st = (rb or {}).get('stats') or {}
    n = int(st.get('n_months') or 0)
    run = latest(channel)
    out = dict(channel=channel, name=CHANNEL_NAMES[channel], rebuilt=rb is not None, n_months=n, start=st.get('start'), end=st.get('end'),
               rebuild=st, rebuild_at=(rb or {}).get('at'), run=run, evidence=EVIDENCE_NO, reason='', show_scores=False)
    if rb is None:
        months = _tracked_months(channel)
        out['tracked'] = months
        out['reason'] = '未回补：' + (f'重建月份 {len(months)} 个（{months[0]} 至 {months[-1]}，只有月度追踪），不到 {MIN_MONTHS} 个月'
                                     if months else '还没有该渠道的数据') + '，不能做渠道回测'
        out['state'] = 'none'
    elif n < MIN_MONTHS:
        out['reason'] = f'重建 {n} 个月，不到 {MIN_MONTHS} 个月，不能做渠道回测'
        out['state'] = 'short'
    elif run is None:
        out['reason'] = f'重建 {n} 个月（{st.get("start")} 至 {st.get("end")}），还没有做渠道回测'
        out['state'] = 'ready'
    else:
        out['state'] = 'done'
        out['evidence'] = run.evidence
        out['show_scores'] = run.evidence == EVIDENCE_OK
        if run.evidence != EVIDENCE_OK:
            out['reason'] = run.reason or '回测未达标'
    return out


def _tracked_months(channel: str) -> list:
    from ..models import Batch
    with session() as s:
        return [m for (m,) in s.execute(select(Batch.month).where(Batch.channel == channel, Batch.status == "merged").distinct().order_by(Batch.month))]


def evidence(channel: str) -> str:
    """该渠道最近一次回测给出的证据等级（AC-F19-06、AC-F20-03）。"""
    if channel == 'amazon':
        return '经回测'
    run = latest(channel)
    return run.evidence if run is not None else EVIDENCE_NO


def unit_score(channel: str, frame: str, attr: str, value: str) -> dict | None:
    """决策卡、扫描用：最近一次渠道回测给出的该单元把握与分级（证据等级不是“经回测（打折）”时返回 None，不显示把握与分级）。"""
    run = latest(channel)
    if run is None or run.evidence != EVIDENCE_OK:
        return None
    u = (run.units or {}).get(f'{frame}|{attr}|{value}')
    return dict(u, run_id=run.id, run_month=run.month) if u else None


def compute(channel: str, end: str | None = None) -> dict:
    """只用该渠道数据重算与回测（不写库）。返回 ChannelModelRun 的字段。"""
    an = panel.analysis(channel)
    if an.A.empty:
        raise ValueError(f'{CHANNEL_NAMES[channel]} 还没有已并入的数据')
    A = an.A if end is None else an.A[an.A['m'] <= mi(end)]
    rows = rows_from_analysis(A)
    bt = ChannelBacktest(rows)
    _state.setdefault(channel, {})['step'] = '滚动回测'
    R = bt.run()
    raw = summarize(bt, R)
    v, params = catconfig.channel_params(channel)
    val = validity(raw)
    disc = discounted(raw, params['discount'])
    _state[channel]['step'] = 'Amazon 侧丰富度'
    az = panel.analysis('amazon').A
    az_rows = richness.amazon_rows(az) if not az.empty else None
    sig = richness_signal(bt, R, rows, az_rows) if raw.get('available') else dict(available=False, reason='回测不可用')
    _state[channel]['step'] = '本次评分'
    units, now_info = score_now(bt)
    ev = EVIDENCE_OK if val['valid'] else EVIDENCE_NO
    reason = ''
    if not val['valid']:
        why = []
        if not raw.get('available'):
            why.append(raw.get('reason') or '回测不可用')
        else:
            if not val['d_ok']:
                why.append(f"D 档之后变大 {raw['d']['up']:.0%} > 30%" if raw['d']['up'] is not None else 'D 档没有样本')
            if not val['mono']:
                why.append('把握分档未逐档上升（' + ' → '.join(f'{u:.0%}' for u in val['ups']) + '）')
        reason = '回测未达标：' + '；'.join(why)
    return dict(channel=channel, month=ms(bt.END), start=ms(bt.M0), n_months=len(bt.MONTHS), config_version=v, discount_params=params['discount'],
                raw=raw, discounted=disc, validity=val, valid=val['valid'], evidence=ev, reason=reason, signals=sig, units=units, now_info=now_info)


def run(channel: str, user_id: int | None = None) -> int:
    """API-F19-02 POST：前置（重建 ≥ 20 个月）满足时重算、回测并保存；随后重扫该渠道，让机会证据等级跟上。"""
    st = status(channel)
    if not st['rebuilt'] or st['n_months'] < MIN_MONTHS:
        raise ValueError(st['reason'])
    d = compute(channel)
    with session() as s:
        r = ChannelModelRun(created_by=user_id, **d)
        s.add(r)
        s.flush()
        rid = r.id
    from . import pipeline
    _state.setdefault(channel, {})['step'] = '机会扫描'
    pipeline.rescan(channel)
    return rid


def start(channel: str, user_id: int | None = None) -> tuple[bool, str]:
    with _lock:
        cur = _state.get(channel) or {}
        if cur.get('running'):
            return False, f'{CHANNEL_NAMES[channel]} 正在重算，请等这次完成'
        _state[channel] = dict(running=True, error='', step='准备数据')

    def _go():
        try:
            _state[channel]['last_run'] = run(channel, user_id)
        except Exception as e:  # 失败要在页面可见
            _state[channel]['error'] = f'{type(e).__name__}: {e}'
            traceback.print_exc()
        finally:
            _state[channel].update(running=False, step='')
    if os.environ.get('PDT_SYNC_JOBS') == '1':
        _go()
    else:
        threading.Thread(target=_go, daemon=True).start()
    return True, f'已开始重算 {CHANNEL_NAMES[channel]}（本地计算，不花钱）'


def as_json(r: ChannelModelRun | None) -> dict | None:
    if r is None:
        return None
    return dict(id=r.id, channel=r.channel, month=r.month, start=r.start, n_months=r.n_months, created_at=str(r.created_at), config_version=r.config_version,
                discount_params=r.discount_params, raw=r.raw, discounted=r.discounted, validity=r.validity, evidence=r.evidence, reason=r.reason,
                signals=r.signals, now=r.now_info)
