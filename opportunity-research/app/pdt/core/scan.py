"""机会扫描：移植第二轮 `solution-v2/trial/机会扫描.py`（四类规则与列口径），阈值取品类配置 scan（默认值即第二轮规则）。

每个“尺寸段 × 拆装 × 形态”框（形态扫落地式 / 悬浮式 / 开放式，revision 10）里，台面材质 / 元素 / 主色 / 柜体材质 的每个取值，近 6 个月对前 6 个月：
- 增长型：份额 ln(近 ÷ 前) ≥ 0.3、月销 ≥ 100、新品占比高于同框（证据：经回测）
- 评分缺口型：评分比同框低 ≥ 0.15、单款月销 ≥ 同框单款、月销 ≥ 50（历史观察）
- 价格缺口型：溢价 ≥ 1.3、月销 ≥ 20（历史观察）
- 坑：份额 ln 变化 ≤ −0.3、月销 ≥ 100（经回测）
其他渠道同一套框与规则，只用本渠道数据，证据等级按该渠道最近一次渠道回测（经回测（打折）/ 未验证，AC-F29-01、AC-F20-03）。
份额、溢价、评分差、新品占比的分母与比较对象只来自同一渠道的同一框（AC-F20-02、AC-F29-02）。
"""
import numpy as np
import pandas as pd

from .families import UNK, ms

ATT = {'台面材质': 'D8台面材质', '元素': '元素一', '主色': '主色', '柜体材质': '柜体材质'}
KINDS = ['增长型', '评分缺口型', '价格缺口型', '坑']
EVIDENCE_AMAZON = {'增长型': '经回测', '坑': '经回测', '评分缺口型': '历史观察', '价格缺口型': '历史观察'}
DEFAULT_RULES = {"min_frame_units": 200, "min_value_units": 10,
                 "growth": {"dlog_share": 0.3, "min_units": 100},
                 "rating_gap": {"rating_diff": -0.15, "per_family_ratio": 1.0, "min_units": 50},
                 "price_gap": {"premium": 1.3, "min_units": 20},
                 "pit": {"dlog_share": -0.3, "min_units": 100}}


def frame_key(size, zhuang, form):
    return f'{size} · {zhuang} · {form}'


def wmed(x, w):
    x, w = np.asarray(x, float), np.asarray(w, float)
    k = ~np.isnan(x) & (w > 0)
    x, w = x[k], w[k]
    if not len(x):
        return np.nan
    o = np.argsort(x)
    c = np.cumsum(w[o])
    return x[o][np.searchsorted(c, c[-1] / 2)]


def frame_rows(A: pd.DataFrame) -> pd.DataFrame:
    """行级表 → 只留可分框的行，加框、评分、价比（÷ 同月同框中位价）、是否新品。"""
    B = A[A['尺寸段'].notna() & A['装'].notna() & A['形态'].isin(['落地式', '悬浮式', '开放式'])].copy()
    B['框'] = B['尺寸段'].astype(str) + ' · ' + B['装'].astype(str) + ' · ' + B['形态'].astype(str)
    B['r'] = pd.to_numeric(B['评分'], errors='coerce').where(lambda x: x.between(1, 5))
    B['价比'] = (B['价格'] / B.groupby(['m', '框'])['价格'].transform('median')).where(B['价格'] > 0)
    B['新'] = B['月龄'] <= 6
    return B


def scan(A: pd.DataFrame, U: pd.DataFrame | None, END: int, rules: dict | None = None, attrs=None) -> pd.DataFrame:
    """返回全量单元表（列名同第二轮 CSV）。A 需有列：m, c, 家族键, 单位, 尺寸段, 装, 形态, 评分, 价格, 月龄, 及属性列。"""
    R = dict(DEFAULT_RULES, **(rules or {}))
    R6, P6 = list(range(END - 5, END + 1)), list(range(END - 11, END - 5))
    B = frame_rows(A)
    if U is not None and len(U):
        kf = A.drop_duplicates('单位').set_index('单位')['家族键']
        Ue = U[U['L'] + 5 <= END].copy()
        Ue['家族键'] = kf.reindex(Ue.index).values
        famfr = B.groupby('家族键')['框'].agg(lambda x: x.value_counts().index[0])
        Ue['框'] = famfr.reindex(Ue['家族键']).values
    else:
        Ue = pd.DataFrame(columns=['家族键', '框', 'y'])
    rows = []
    for att, col in ATT.items():
        if attrs and att not in attrs:
            continue
        d = B.assign(值=B[col])
        if att == '元素':
            d = d.explode('值')
        d = d[d['值'].notna() & ~d['值'].map(UNK) & ~d['值'].isin(['信息不足', '不适用（不含台面）'])]
        famv = d.groupby('家族键')['值'].agg(set)
        for fr, df in d.groupby('框'):
            r6, p6 = df[df['m'].isin(R6)], df[df['m'].isin(P6)]
            if r6['c'].sum() / 6 < R['min_frame_units']:
                continue
            rsum = r6.loc[r6['r'].notna(), 'c'].sum()
            F = dict(月销=r6['c'].sum() / 6, 家族=r6['家族键'].nunique(),
                     评分=(r6['r'] * r6['c']).sum() / rsum if rsum else np.nan,
                     新品=r6.loc[r6['新'], 'c'].sum() / r6['c'].sum(), 月销前=p6['c'].sum() / 6)
            F['单款'] = F['月销'] / max(F['家族'], 1)
            uf = Ue[Ue['框'] == fr]
            for v, dv in r6.groupby('值'):
                pv = p6[p6['值'] == v]
                s = dv['c'].sum() / 6
                if s < R['min_value_units']:
                    continue
                rr = dv.dropna(subset=['r'])
                fam = dv['家族键'].nunique()
                ufv = uf.loc[np.array([v in famv.get(k, set()) for k in uf['家族键']], dtype=bool)] if len(uf) else uf
                rows.append(dict(属性=att, 框=fr, 取值=v, 月销=s, 份额=s / F['月销'], 份额前=(pv['c'].sum() / 6) / max(F['月销前'], 1e-9),
                                 家族=fam, 单款=s / fam, 框单款=F['单款'],
                                 评分=(rr['r'] * rr['c']).sum() / rr['c'].sum() if rr['c'].sum() else np.nan, 框评分=F['评分'],
                                 溢价=wmed(dv['价比'], dv['c']), 中位价=wmed(dv['价格'], dv['c']),
                                 新品=dv.loc[dv['新'], 'c'].sum() / dv['c'].sum(), 框新品=F['新品'], 框月销=F['月销'],
                                 新家族=len(ufv), 新做到=int(ufv['y'].sum()) if len(ufv) else 0, 框新家族=len(uf), 框新做到=int(uf['y'].sum()) if len(uf) else 0))
    cols = ['属性', '框', '取值', '月销', '份额', '份额前', '家族', '单款', '框单款', '评分', '框评分', '溢价', '中位价', '新品', '框新品', '框月销',
            '新家族', '新做到', '框新家族', '框新做到']
    X = pd.DataFrame(rows, columns=cols)
    X['份额变化'] = np.log((X['份额'] + 0.002) / (X['份额前'] + 0.002))
    X['新品差'] = X['新品'] - X['框新品']
    X['评分差'] = X['评分'] - X['框评分']
    X['单款比'] = X['单款'] / X['框单款']
    g, rg, pg, pit = R['growth'], R['rating_gap'], R['price_gap'], R['pit']
    X['增长型'] = (X['份额变化'] >= g['dlog_share']) & (X['月销'] >= g['min_units']) & (X['新品差'] > 0)
    X['评分缺口型'] = (X['评分差'] <= rg['rating_diff']) & (X['单款比'] >= rg['per_family_ratio']) & (X['月销'] >= rg['min_units'])
    X['价格缺口型'] = (X['溢价'] >= pg['premium']) & (X['月销'] >= pg['min_units'])
    X['坑'] = (X['份额变化'] <= pit['dlog_share']) & (X['月销'] >= pit['min_units'])
    X.attrs['R6'] = (ms(R6[0]), ms(R6[-1]))
    X.attrs['P6'] = (ms(P6[0]), ms(P6[-1]))
    return X


def _n(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)


def to_metrics(r) -> dict:
    """单元行 → Opportunity.metrics（开发约定字段）。"""
    return dict(units=_n(r['月销']), share=_n(r['份额']), share_prev=_n(r['份额前']), dlog_share=_n(r['份额变化']), families=int(r['家族']),
                per_family=_n(r['单款']), per_family_ratio=_n(r['单款比']), rating=_n(r['评分']), frame_rating=_n(r['框评分']), rating_diff=_n(r['评分差']),
                premium=_n(r['溢价']), median_price=_n(r['中位价']), newshare=_n(r['新品']), frame_newshare=_n(r['框新品']), newshare_diff=_n(r['新品差']),
                newfam=int(r['新家族']), newmade=int(r['新做到']), frame_newfam=int(r['框新家族']), frame_newmade=int(r['框新做到']),
                frame_units=_n(r['框月销']), frame_per_family=_n(r['框单款']),
                flags={k: bool(r[k]) for k in KINDS})


def evidence_for(channel: str, flags: dict) -> str:
    """证据等级：Amazon 增长型 / 坑 = 经回测，评分缺口 / 价格缺口 = 历史观察；其他渠道 = 该渠道最近一次回测给出的等级（经回测（打折）/ 未验证）。多类时取最强。"""
    on = [k for k in KINDS if flags.get(k)]
    if not on:
        return ''
    if channel != 'amazon':  # 其他渠道按该渠道最近一次渠道回测（AC-F19-06、AC-F20-03 revision 2）
        from .channel_model import evidence
        return evidence(channel)
    grades = [EVIDENCE_AMAZON[k] for k in on]
    return '经回测' if '经回测' in grades else '历史观察'


# ---------------------------------------------------------------- 需求范围（AC-F20-06、07，revision 10）
SCOPE_UP = 0.2  # 份额 ln(近 ÷ 前) ≥ 0.2 算"在涨"（与系统其他"上升"同口径）


def _size_key(s):
    from .families import SIZE_ORDER
    return SIZE_ORDER.index(s) if s in SIZE_ORDER else 99


def demand_scope(rows: list) -> dict:
    """rows = [(框, 属性, 取值, metrics)]（同一渠道同一月份的全部单元）。返回 {(框, 属性, 取值): {kind, sizes, head, tip}}。
    同拆装、同形态、同属性取值的其他尺寸段框里，在涨（ln ≥ 0.2）或份额 ≥ 这些尺寸段（含本框）平均份额的计为可拓展；否则细分需求。"""
    groups = {}
    for fr, att, val, m in rows:
        p = fr.split(' · ')
        if len(p) != 3:
            continue
        groups.setdefault((p[1], p[2], att, val), []).append((p[0], m.get('share'), m.get('share_prev'), m.get('dlog_share')))
    out = {}
    for (asm, form, att, val), es in groups.items():
        es.sort(key=lambda e: _size_key(e[0]))
        shares = [e[1] for e in es if e[1] is not None]
        avg = sum(shares) / len(shares) if shares else None

        def trend(d):
            return '在涨' if d is not None and d >= SCOPE_UP else ('在跌' if d is not None and d <= -SCOPE_UP else '持平')
        tip = [f'同{asm} · {form}各尺寸段的 {att}：{val}'] + [
            f"{s} 份额 {(pp or 0) * 100:.1f}% → {(sh or 0) * 100:.1f}%，{trend(d)}" for s, sh, pp, d in es]
        if avg is not None:
            tip.append(f'这些尺寸段的平均份额 {avg * 100:.1f}%；在涨或不低于平均的尺寸段算"可拓展"')
        for s, sh, pp, d in es:
            ok = [x for x, xsh, _, xd in es if x != s and ((xd is not None and xd >= SCOPE_UP) or (xsh is not None and avg is not None and xsh >= avg))]
            out[(f'{s} · {asm} · {form}', att, val)] = dict(
                kind='可拓展' if ok else '细分需求', sizes=ok, head=f'{s} · {asm} · {form} · {att}：{val}',
                text=('可拓展到 ' + '、'.join(ok)) if ok else '细分需求',
                tip='|'.join(tip if len(es) > 1 else tip[:1] + [f'其他尺寸段（同{asm} · {form}）都没有这个取值'] + tip[1:]))
    return out
