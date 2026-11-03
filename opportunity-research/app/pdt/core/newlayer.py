"""新品层：做到概率与“模型偏差”。移植第二轮 `回归预测_第九版.py` 的 newlayer9 / cohort9（校准方式 (a) 最近半年为现行，
(b) 全部、(c) 趋势外推只用于按预登记规则比较）。

模型偏差 = 近批（选择段立项时点）模型预测平均 − 实际做到（AC-F19-02），决策卡上“扣偏差后的值” = 原值 − 偏差（AC-F21-03）。
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from .families import mi, ms, newprod


def lg(p):
    return np.log(p / (1 - p))


def newlayer9(U, TK, T0, how='a'):
    """站在 T0 的校准后做到概率。返回 (cal, tr, 模型参数)。"""
    tr = U[U['L'] + 5 <= T0 - 1]
    sc, vocab, m = newprod(U, TK, T0, False)
    rec = tr[tr['L'] >= tr['L'].max() - 5]
    p_bar = sc(list(rec.index)).mean()
    if how == 'a':
        r = rec['y'].mean()
    elif how == 'b':
        r = tr['y'].mean()
        p_bar = sc(list(tr.index)).mean()
    else:
        lm = LogisticRegression(C=1e6, max_iter=5000).fit(tr[['L']].values - tr['L'].max(), tr['y'].values)
        r = lm.predict_proba(np.array([[T0 + 8 - tr['L'].max()]]))[0, 1]
    shift = lg(r) - lg(p_bar)

    def cal(us):
        return 1 / (1 + np.exp(-(lg(sc(us)) + shift)))
    params = dict(vocab=list(vocab), coef=[float(x) for x in m.coef_[0]], intercept=float(m.intercept_[0]), shift=float(shift),
                  how=how, T0=ms(T0), n_train=int(len(tr)), recent_rate=float(rec['y'].mean()))
    return cal, tr, params


def cohort9(U, T0, END):
    return U[U['L'].between(T0 + 6, T0 + 10) & (U['L'] + 5 <= END)]


def in10(p):
    return None if p is None or (isinstance(p, float) and np.isnan(p)) else round(float(p) * 10, 1)


def table(U, TK, END):
    """新品层检验表（立项时点 T0 的新品按 T0+6 至 T0+10 上架算）：选择段 = 前 3 个时点，检验段 = 后 2 个。返回 (rows, 选用方式, 偏差)。"""
    T0s = [END - 15 + i for i in range(5)]  # 数据到 2026-09 时为 2025-06 至 2025-10
    ERR = {'a': [], 'b': [], 'c': []}
    rows, bias_parts = [], []
    for i, T1 in enumerate(T0s):
        c = cohort9(U, T1, END)
        if len(c) < 10:
            continue
        cals = {h: newlayer9(U, TK, T1, h) for h in 'abc'}
        tr = cals['a'][1]
        ps = {h: pd.Series(cals[h][0](list(c.index)), index=c.index) for h in 'abc'}
        y = c['y']
        p = ps['a']
        use = '选择' if i < 3 else '检验'
        if use == '选择':
            for h in 'abc':
                ERR[h].append(abs(ps[h].mean() - y.mean()))
            bias_parts.append((float(ps['a'].mean()), float(y.mean()), int(len(c)), ms(T1)))
        try:
            auc = float(roc_auc_score(y, p))
        except ValueError:
            auc = None
        rows.append(dict(T0=ms(T1), n_train=int(len(tr)), n_test=int(len(c)), actual=in10(y.mean()), auc=auc,
                         top30=in10(y[p >= p.quantile(0.7)].mean()), bottom30=in10(y[p <= p.quantile(0.3)].mean()),
                         mean_a=in10(ps['a'].mean()), mean_b=in10(ps['b'].mean()), mean_c=in10(ps['c'].mean()), use=use,
                         small=len(c) < 20))
    mae = {h: (float(np.mean(v)) if v else None) for h, v in ERR.items()}
    best = min((h for h in mae if mae[h] is not None), key=lambda h: mae[h], default='a')
    if bias_parts:
        pred = float(np.mean([b[0] for b in bias_parts]))
        act = float(np.mean([b[1] for b in bias_parts]))
    else:
        pred = act = None
    bias = dict(pred=pred, actual=act, bias=(pred - act) if pred is not None else None,
                n=int(sum(b[2] for b in bias_parts)), parts=bias_parts, mae=mae, chosen=best)
    return rows, bias


def prob_for_tokens(params: dict, tokens: list[str]) -> float | None:
    """用存档的新品层参数给一组特征（如 ['尺寸=30″', '装=拆装', '台面=石材台面', '元素=竖棱']）打校准后的做到概率。"""
    if not params or not params.get('vocab'):
        return None
    x = np.array([1.0 if v in tokens else 0.0 for v in params['vocab']])
    z = float(x @ np.array(params['coef']) + params['intercept'])
    p = 1 / (1 + np.exp(-z))
    return float(1 / (1 + np.exp(-(lg(p) + params['shift']))))
