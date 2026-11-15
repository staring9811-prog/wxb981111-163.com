"""滚动回测与有效性检验：移植第二轮 `回归预测_第九版.py` 的 mkt_eval 与回测各节（AC-F19-03 / 04）。

数据截至月 END 时：主时点 T0 = END − 8（立项后第 6–8 个月窗口刚好走完；数据到 2026-09 时为 2026-01）；
并排时点 = END − 11 至 END − 8（2025-10 至 2026-01），第八版与第九版各算一次。
有效性：D 档之后变大比例 > 30%，或把握四档之后变大比例不再逐档上升 → 未通过。
"""
import numpy as np
import pandas as pd
from scipy.stats import norm, spearmanr

from .families import ms

GRASP_BINS = [0, 0.3, 0.5, 0.7, 1.0]
GRASP_LABELS = ['≤30%', '30–50%', '50–70%', '≥70%']
INVALID_MSG = '市场评分本月未通过有效性检验'


def _f(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)


def mkt_eval(mk, T0, v):
    """某版本在 T0 的预测，与 k = 6 / 8 窗口的实际比。"""
    mk.set_ver(v)
    try:
        D, m, cols, q, Tr = mk.predict(T0)
    finally:
        mk.set_ver(9)
    mk.set_ver(v)
    res = {}
    for k in (6, 8):
        if T0 + k + 2 > mk.END or f'预测{k}' not in D:
            continue
        y = mk.target(D, T0, k)
        d = D.assign(y=y)
        b = d[d['近3月'] >= 300]
        nz = b['y'].abs() > 0.05
        pk = norm.cdf(d[f'预测{k}'] / d[f'sd{k}'])
        res[k] = dict(n=int(len(d)), rho=_f(spearmanr(d[f'预测{k}'], d['y'])[0]), rho300=_f(spearmanr(b[f'预测{k}'], b['y'])[0]),
                      dirn=_f((np.sign(b.loc[nz, f'预测{k}']) == np.sign(b.loc[nz, 'y'])).mean()),
                      cov=_f(d['y'].between(d[f'lo{k}'], d[f'hi{k}']).mean()),
                      hi=[_f((d.loc[pk >= 0.7, 'y'] > 0).mean()), int((pk >= 0.7).sum())],
                      lo=[_f((d.loc[pk <= 0.3, 'y'] > 0).mean()), int((pk <= 0.3).sum())])
    mk.set_ver(9)
    return res, D, m, cols, q, Tr


def run(mk, U=None, TK=None, newlayer_rows=None, bias=None) -> dict:
    """完整回测。返回可 JSON 化的 dict（ModelRun.backtest）。"""
    END = mk.END
    T0 = END - 8
    out = dict(T0=ms(T0), window=f'{ms(T0 + 6)} 至 {ms(T0 + 8)}', end=ms(END))
    if newlayer_rows is not None:
        out['newlayer'] = newlayer_rows
        out['bias'] = bias
    try:
        _, D, m, cols, q, Tr = mkt_eval(mk, T0, 9)
    except ValueError as e:  # 数据太短（如回看 2026-01）：回测时点不足，不做有效性判断
        out.update(available=False, reason=str(e), side=[], grades=[], grasp_bins=[], coef={}, rho={}, n_train=0, valid=True,
                   valid_detail=dict(note='回测时点不足，未检验', d_ok=True, mono=True, bins=[], d_up=None, d_n=None))
        return out
    out['available'] = True
    coef = pd.Series(m.coef_, index=cols)
    out['coef'] = {x: dict(b=float(coef[x]), c=float(coef[x + '·k']), k6=float(coef[x] + 2 * coef[x + '·k']), k8=float(coef[x] + 8 / 3 * coef[x + '·k'])) for x in mk.XS}
    out['coef']['截距'] = dict(b=float(m.intercept_), c=float(coef['k']))
    out['n_train'] = int(len(Tr))
    out['train_T'] = [ms(Tr['T'].min()), ms(Tr['T'].max())]
    # 并排
    side = []
    for T1 in range(END - 11, END - 7):
        for v in (8, 9):
            try:
                res = mkt_eval(mk, T1, v)[0]
            except ValueError:
                continue
            for k, r in res.items():
                side.append(dict(T0=ms(T1), k=k, window=f'{ms(T1 + k)} 至 {ms(T1 + k + 2)}', ver=v, **r))
    out['side'] = side
    # 主时点：把握分档、分级
    D['y6'] = mk.target(D, T0, 6)
    D['实件6'] = mk.actual_units(D, T0, 6)
    D['实分母6'] = mk.actual_units(D, T0, 6, '分母')
    D['实际多卖'] = D['实件6'] - D[mk.BASE] * D['实分母6']
    D['变大'] = D['y6'] > 0
    D['预计多卖6'] = D['件6'] - D['不变6']
    D['把握档'] = pd.cut(D['把握'], GRASP_BINS, labels=GRASP_LABELS, include_lowest=True)
    bins = []
    for b_, d in D.groupby('把握档', observed=True):
        bins.append(dict(bin=str(b_), n=int(len(d)), n300=int((d['近3月'] >= 300).sum()), up=float(d['变大'].mean()), extra=float(d['实际多卖'].sum())))
    out['grasp_bins'] = bins
    big = D[D['近3月'] >= 300]
    out['rho'] = dict(grasp=_f(spearmanr(D['把握'], D['y6'])[0]), grasp300=_f(spearmanr(big['把握'], big['y6'])[0]),
                      extra=_f(spearmanr(D['预计多卖6'], D['实际多卖'])[0]), extra300=_f(spearmanr(big['预计多卖6'], big['实际多卖'])[0]))
    grades = []
    for g in 'ABCD':
        d = D[D['分级'] == g]
        if len(d):
            grades.append(dict(grade=g, n=int(len(d)), up=float(d['变大'].mean()), extra=float(d['实际多卖'].sum()), median=float(d['实际多卖'].median())))
    out['grades'] = grades
    out['n_units'] = int(len(D))
    out['valid'], out['valid_detail'] = validity(out)
    return out


def validity(bt: dict):
    """AC-F19-04：D 档之后变大 > 30% 或把握分档不再逐档上升 → 未通过。"""
    d = next((g for g in bt.get('grades', []) if g['grade'] == 'D'), None)
    d_ok = d is None or d['up'] <= 0.30
    ups = [b['up'] for b in bt.get('grasp_bins', [])]
    mono = all(b > a for a, b in zip(ups, ups[1:])) and len(ups) >= 2
    return bool(d_ok and mono), dict(d_up=None if d is None else d['up'], d_n=None if d is None else d['n'], d_ok=d_ok, bins=ups, mono=mono)
