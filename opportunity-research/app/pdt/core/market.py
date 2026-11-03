"""市场层评分：移植第二轮 `solution-v2/trial/回归预测.py` 库部分（set_ver / panel / feats / target / fit / predict）与
`两层识别.py` 的 search_yoy；第九版（VER=9）为现行规则，第八版（VER=8）用于回测并排。

单元 = 五个大属性（尺寸、台面、主色、材质、元素）的每个取值 + 两两交叉的每个格子。
预测“立项后第 k 个月起 3 个月”的份额对数变化（第九版 k ∈ {0,3,6,8}，把握看 k = 6 与 8），按（体量档, k）校准，给 80% 区间。
"""
import itertools

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.linear_model import Ridge

from .families import UNK, mi, ms

DIMS = {'尺寸': '尺寸段', '台面': '台面类型', '主色': '主色', '材质': '柜体材质', '元素': '元素一'}
EPS = 0.001


def TIER(b):
    return np.where(b >= 1000, '≥1,000', np.where(b >= 300, '300–1,000', '<300'))


class Market:
    """第二轮回归预测库的面向对象移植。A 来自 families.build；KS = 搜索量表（列 kw, m, v, 值, 维度, 来源）。"""

    def __init__(self, A: pd.DataFrame, KS: pd.DataFrame, ver: int = 9, end: int | None = None):
        self.A = A
        self.KS = KS
        self.M0 = int(A['m'].min())
        self.END = int(end if end is not None else A['m'].max())
        self.MONTHS = list(range(self.M0, self.END + 1))
        self.KEYCOL = {d: (A['元素一'] if d == '元素' else A[c]) for d, c in DIMS.items()}
        self.PAN, self.NEWC = {}, {}
        newrow = (A['月龄'] <= 6).values  # 上架 ≤ 6 个月的行（缺上架日期的按非新品）
        for dims in [(d,) for d in DIMS] + list(itertools.combinations(DIMS, 2)):
            C, F, den, vals = self.panel(dims)
            self.PAN[dims] = (C, F, den, vals)
            self.NEWC[dims] = self.panel(dims, A['c'].values * newrow)[0].reindex(C.index, fill_value=0)
        self.CATNEW = A[newrow].groupby('m')['c'].sum().reindex(self.MONTHS, fill_value=0)
        self.CAT = A.groupby('m')['c'].sum().reindex(self.MONTHS, fill_value=0)
        self._feat = {}
        self._yoy = {}
        self.set_ver(ver)

    # ---------- 搜索同比 ----------
    def search_yoy(self, T):
        """维度取值 → T−3 至 T−1 对一年前同期的搜索同比（亚马逊、Google 各算，取平均）。"""
        if T in self._yoy:
            return self._yoy[T]
        out = {}
        KS = self.KS
        if len(KS):
            for (d, v), g in KS.groupby(['维度', '值']):
                ys = []
                for _src, h in g.groupby('来源'):
                    now = h[h['m'].between(T - 3, T - 1)].groupby('m')['v'].sum().sum()
                    pre = h[h['m'].between(T - 15, T - 13)].groupby('m')['v'].sum().sum()
                    if pre > 0 and now > 0:
                        ys.append(now / pre - 1)
                if ys:
                    out[(d, v)] = float(np.mean(ys))
        self._yoy[T] = out
        return out

    # ---------- 面板：每个单元每月销量、在榜家族数、分母（已知标签总销量） ----------
    def panel(self, dims, c=None):
        A, KEYCOL, MONTHS = self.A, self.KEYCOL, self.MONTHS
        cc = A['c'].values if c is None else c
        df = pd.DataFrame({'m': A['m'].values, 'c': cc, 'fam': A['家族键'].values})
        for d in dims:
            df[d] = KEYCOL[d].values
        for d in dims:
            if d == '元素':
                df = df.explode(d)
        for d in dims:
            df = df[~df[d].map(UNK)]
        known = np.logical_and.reduce([~KEYCOL[d].map(lambda v: (len(v) == 0) if isinstance(v, list) else UNK(v)).values for d in dims])
        den = pd.Series(cc, index=A.index)[known].groupby(A['m'][known]).sum().reindex(MONTHS, fill_value=0)
        key = df[list(dims)].astype(str).agg(' × '.join, axis=1)
        C = df.groupby([key, df['m']])['c'].sum().unstack(fill_value=0).reindex(columns=MONTHS, fill_value=0)
        F = df.groupby([key, df['m']])['fam'].nunique().unstack(fill_value=0).reindex(columns=MONTHS, fill_value=0)
        vals = df.assign(_k=key).drop_duplicates('_k').set_index('_k')[list(dims)]
        return C, F, den, vals

    @staticmethod
    def mean3(X, a):
        return X.loc[:, [m for m in range(a, a + 3) if m in X.columns]].mean(axis=1)

    def feats(self, T):
        """站在 T（只用 T−1 及以前）的每个单元特征。"""
        if T in self._feat:
            return self._feat[T]
        mean3, CAT, CATNEW = self.mean3, self.CAT, self.CATNEW
        yo = self.search_yoy(T)
        out = []
        for dims, (C, F, den, vals) in self.PAN.items():
            b1, b0 = mean3(C, T - 3), mean3(C, T - 6)
            d1, d0 = den.loc[T - 3:T - 1].mean(), den.loc[T - 6:T - 4].mean()
            f1, f0 = mean3(F, T - 3), mean3(F, T - 6)
            s3 = [np.array([yo.get((d, v), np.nan) for v in vals.loc[C.index, d]]) for d in dims if d != '材质']
            with np.errstate(all='ignore'):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore')
                    s3 = np.nanmean(np.vstack(s3), axis=0) if s3 else np.full(len(C), np.nan)
            D = pd.DataFrame({'层': '大属性' if len(dims) == 1 else '两维格子', '属性': ' × '.join(dims), '取值': C.index, '近3月': b1.values,
                              '份额': (b1 / d1).values, '份额前': (b0 / d0).values, 'x2': ((f1 - f0) / (f0 + 1)).values, 'S3': s3, '分母': d1,
                              '标签占比': d1 / CAT.loc[T - 3:T - 1].mean()})
            cols6 = list(range(T - 6, T))
            xc = np.arange(6) - 2.5
            D['份额6'] = (C[cols6].sum(axis=1) / den.loc[T - 6:T - 1].sum()).values
            D['b6'] = ((np.log(C[cols6].div(den.loc[T - 6:T - 1].replace(0, np.nan), axis=1).fillna(0) + EPS) * xc).sum(axis=1) / (xc ** 2).sum()).values
            D['x5'] = (self.NEWC[dims][cols6].sum(axis=1) / C[cols6].sum(axis=1).replace(0, np.nan)).fillna(0).values - CATNEW.loc[T - 6:T - 1].sum() / CAT.loc[T - 6:T - 1].sum()
            D['dims'] = [dims] * len(D)
            out.append(D)
        D = pd.concat(out, ignore_index=True)
        D = D[D['近3月'] > 0].copy()
        D['x1'] = np.log((D['份额'] + EPS) / (D['份额前'] + EPS))
        D['x3'] = D['S3'].fillna(0).clip(-1, 2)
        D['无词'] = D['S3'].isna()
        D['x4'] = np.log(D['近3月'] + 5)
        D['T'] = T
        D = D.set_index(['属性', '取值'])
        self._feat[T] = D
        return D

    def target(self, D, T, k):
        """T+k 起 3 个月的份额对数变化；窗口未走完返回 NaN。"""
        a = T + k
        if a + 2 > self.END:
            return pd.Series(np.nan, index=D.index)
        res = {}
        for dims, (C, F, den, vals) in self.PAN.items():
            s = self.mean3(C, a) / den.loc[a:a + 2].mean()
            att = ' × '.join(dims)
            for v, x in s.items():
                res[(att, v)] = x
        s = pd.Series([res.get(i, 0.0) for i in D.index], index=D.index)
        return np.log((s + EPS) / (D[self.BASE] + EPS))

    def actual_units(self, D, T, k, what='件'):
        a = T + k
        res = {}
        for dims, (C, F, den, vals) in self.PAN.items():
            dd = den.loc[a:a + 2].mean()
            for v, x in self.mean3(C, a).items():
                res[(' × '.join(dims), v)] = x if what == '件' else dd
            if what != '件':
                res.update({(' × '.join(dims), v): dd for v in vals.index})
        return pd.Series([res.get(i, 0.0) for i in D.index], index=D.index)

    def set_ver(self, v):
        self.VER = v
        self.XS = ['x1', 'x2', 'x3', 'x4'] if v == 6 else (['b6', 'x2', 'x3', 'x4'] if v < 9 else ['b6', 'x2', 'x3', 'x4', 'x5'])
        self.BASE = '份额' if v == 6 else '份额6'
        self.KS_ = (0, 3, 6) if v < 9 else (0, 3, 6, 8)
        self.KA, self.KB = (3, 6) if v < 9 else (6, 8)

    def design(self, D, k):
        X = D[self.XS].copy()
        X['x4'] = X['x4'] - 5.0
        for x in self.XS:
            X[x + '·k'] = X[x] * k / 3
        X['k'] = k / 3
        return X

    def fit(self, T0):
        """只用结果在 T0−1 前已知的 (T, k)。"""
        rows = []
        for T in range(self.M0 + 6, T0):
            for k in self.KS_:
                if T + k + 2 > T0 - 1:
                    continue
                D = self.feats(T)
                y = self.target(D, T, k)
                ok = (D['近3月'] >= 50) & y.notna()
                X = self.design(D[ok], k)
                X['y'] = y[ok]
                X['tier'] = TIER(D.loc[ok, '近3月'].values)
                X['T'] = T
                X['kk'] = k
                rows.append(X)
        Tr = pd.concat(rows)
        cols = [c for c in Tr.columns if c not in ('y', 'tier', 'T', 'kk')]
        m = Ridge(alpha=1e-6).fit(Tr[cols], Tr['y'])
        Tr['res'] = Tr['y'] - m.predict(Tr[cols])
        agg = dict(mu='mean', lo=lambda r: r.quantile(0.1), hi=lambda r: r.quantile(0.9), sd='std', n='size')
        q = Tr.groupby('tier')['res'].agg(**agg)
        if self.VER >= 8:  # 第八版起：按（体量档, k）校准；缺的用同档最大 k、标准差按 √((k+3)/(kmax+3)) 放大
            qk = Tr.groupby(['tier', 'kk'])['res'].agg(**agg)
            full = {}
            for t in qk.index.get_level_values(0).unique():
                have = qk.loc[t]
                for k in self.KS_:
                    if k in have.index:
                        full[(t, k)] = have.loc[k]
                    else:
                        r = have.loc[have.index.max()].copy()
                        f = np.sqrt((k + 3) / (have.index.max() + 3))
                        r['lo'] = r['mu'] + (r['lo'] - r['mu']) * f
                        r['hi'] = r['mu'] + (r['hi'] - r['mu']) * f
                        r['sd'] *= f
                        r['n'] = 0
                        full[(t, k)] = r
            q = pd.DataFrame(full).T
            q.index.names = ['tier', 'kk']
        return m, cols, q, Tr

    def qget(self, q, tier, k, col):
        if self.VER >= 8:
            return np.array([q.at[(t, k), col] for t in tier])
        return tier.map(q[col]).values if col != 'mu' else np.zeros(len(tier))

    def cat_fc(self, T0, a):
        """品类第 a 至 a+2 月的月均销预测：去年同月 × 近 3 个月同比（算不出取 1）。"""
        CAT = self.CAT
        g = CAT.loc[T0 - 3:T0 - 1].sum() / CAT.loc[T0 - 15:T0 - 13].sum() if T0 - 15 >= self.M0 else 1.0
        return np.mean([CAT.get(m - 12, np.nan) for m in range(a, a + 3)]) * g

    def predict(self, T0):
        m, cols, q, Tr = self.fit(T0)
        D = self.feats(T0).copy()
        tier = pd.Series(TIER(D['近3月'].values), index=D.index)
        BASE, KA, KB = self.BASE, self.KA, self.KB
        for k in self.KS_:
            raw = m.predict(self.design(D, k)[cols])
            D[f'预测{k}'] = raw + self.qget(q, tier, k, 'mu')
            D[f'lo{k}'] = raw + self.qget(q, tier, k, 'lo')
            D[f'hi{k}'] = raw + self.qget(q, tier, k, 'hi')
            D[f'sd{k}'] = self.qget(q, tier, k, 'sd')
            base = D[BASE] * D['标签占比'] * self.cat_fc(T0, T0 + k)
            D[f'件{k}'] = base * np.exp(D[f'预测{k}'])
            D[f'件lo{k}'] = base * np.exp(D[f'lo{k}'])
            D[f'件hi{k}'] = base * np.exp(D[f'hi{k}'])
            D[f'不变{k}'] = base
        sd = (D[f'sd{KA}'] + D[f'sd{KB}']).values / 2
        D['把握'] = norm.cdf(((D[f'预测{KA}'] + D[f'预测{KB}']) / 2) / sd)
        D['预计多卖'] = ((D[f'件{KA}'] - D[f'不变{KA}']) + (D[f'件{KB}'] - D[f'不变{KB}'])) / 2
        D['分级'] = np.select([(D['把握'] >= 0.7) & (D['预计多卖'] >= 100), (D['把握'] <= 0.3) & (D['近3月'] >= 300), D['把握'] >= 0.5], ['A', 'D', 'B'], 'C')
        D['体量档'] = tier.values
        return D, m, cols, q, Tr


def unit_score_rows(D: pd.DataFrame, T0: int, BASE: str = '份额6') -> list[dict]:
    """把 predict 的结果转成 UnitScore.data（开发约定）。frame 取“全品类”：第九版单元是大属性与两两格子，不分框。"""
    out = []
    for (att, v), r in D.iterrows():
        sh = float(r[BASE])
        out.append(dict(attr=att, value=str(v), data=dict(
            grasp=float(r['把握']), grade=str(r['分级']), share_now=sh,
            pred_share=float(sh * np.exp((r['预测6'] + r['预测8']) / 2)),
            pred_lo=float(sh * np.exp((r['lo6'] + r['lo8']) / 2)), pred_hi=float(sh * np.exp((r['hi6'] + r['hi8']) / 2)),
            pred_share_k6=float(sh * np.exp(r['预测6'])), pred_lo_k6=float(sh * np.exp(r['lo6'])), pred_hi_k6=float(sh * np.exp(r['hi6'])),
            pred_share_k8=float(sh * np.exp(r['预测8'])), pred_lo_k8=float(sh * np.exp(r['lo8'])), pred_hi_k8=float(sh * np.exp(r['hi8'])),
            extra_units=float(r['预计多卖']), units_3m=float(r['近3月']), tier=str(r['体量档']), k_months='6–10',
            b6=float(r['b6']), x2=float(r['x2']), x3=None if pd.isna(r['S3']) else float(r['S3']), x5=float(r['x5']),
            prob_raw=None, prob_adj=None, n_families=None, made_rate=None, made_p=None,
            sources=dict(frame='全品类', months=f'{ms(T0 - 6)} 至 {ms(T0 - 1)}', n=None, window=f'{ms(T0 + 6)} 至 {ms(T0 + 10)}'))))
    return out


def ks_frame(rows) -> pd.DataFrame:
    """SearchVolume 行 → 第二轮 KS 表结构。"""
    KS = pd.DataFrame([(r.keyword, mi(r.month), r.volume, r.value, r.dim, r.source) for r in rows],
                      columns=['kw', 'm', 'v', '值', '维度', '来源'])
    return KS
