"""跨渠道供给丰富度（REQ-F29-03、AC-F29-05 / 06；API-F29-02）。口径同 `solution-v2/trial/跨渠道供给差_HD检验.py`（忽略装对齐）：

- 对齐键 = 尺寸段 · 形态 × 属性取值（整装、拆装合并）；窗口 = 两渠道都有数据的最近 6 个月（Amazon 与该渠道数据截至月取较早的一个）。
- 只数窗口内有销量的行：家族数（Amazon 家族键 / 该渠道评论家族）、子体数（子 ASIN / 商品页）、价位段数（7 段绝对价位，两渠道共用）、
  月均销量、框内份额（÷ 同尺寸段 · 形态里该属性已知的销量）与框内份额斜率；Amazon 另给前两个半年的份额走势。
- 差距 G = ln((Amazon 家族数 + 1) / (本渠道家族数 + 1))。数据支持的读法是“Amazon 结构领先”，本渠道家族少本身不是机会。
- 元素：Amazon 看图元素按“+”拆开，只保留其他渠道文字规则认得出的 6 类（夏克式 / 竖棱 / 农场风装饰饰条 / 玻璃门 / 木条格栅 / rattan）。
- 样本外（AC-F29-06）：Amazon 单元需求已证明（月均 ≥ 300 件、框内份额 ≥ 10%、份额斜率 > 0）、本渠道同尺寸段 · 形态有市场（月均 ≥ 200 件），
  但本渠道窗口内没有任何家族；不含元素单元（本渠道元素认不全）。只给 Amazon 侧事实，不给本渠道把握与分级。
"""
import threading

import numpy as np
import pandas as pd

from . import panel
from .families import ms

ATTRS = ('台面材质', '元素', '主色', '柜体材质')
UNKS = {'未知', '信息不足', '待图片核验', '', 'nan', 'None', None}
PRICE_ABS = [0, 200, 300, 450, 650, 900, 1300, np.inf]
PB_LABELS = ['<$200', '$200–300', '$300–450', '$450–650', '$650–900', '$900–1,300', '$1,300+']
CH_ELEMS = ('夏克式', '竖棱', '农场风装饰饰条', '玻璃门', '木条格栅', 'rattan')
OOS_RULE = dict(az_units=300, az_share=0.10, ch_frame_units=200)
_cache: dict = {}
_lock = threading.Lock()


def az_elem(vals) -> list:
    """Amazon 看图元素（元素一列表）→ 其他渠道能认的 6 类；认不出的记“其他（…）”，不参与对齐。"""
    out = set()
    for e in vals or []:
        for part in str(e).split('+'):
            if part.startswith('夏克式'):
                out.add('夏克式')
            elif part in ('竖棱', 'fluted', 'reeded'):
                out.add('竖棱')
            elif part in CH_ELEMS:
                out.add(part)
            elif part:
                out.add('其他（' + part + '）')
    return sorted(out) or ['未知']


def amazon_rows(A: pd.DataFrame) -> pd.DataFrame:
    """panel.Analysis('amazon').A → 与渠道行级表同列（fam, pid, m, c, 尺寸段, 装, 形态, 属性列, 元素列表, 价格）。"""
    return pd.DataFrame({'fam': A['家族键'].values, 'pid': A['子ASIN'].astype(str).values, 'm': A['m'].values, 'c': A['c'].values,
                         '尺寸段': A['尺寸段'].values, '装': A['装'].values, '形态': A['形态'].replace({'两用': '落地式'}).fillna('落地式').values,
                         '台面材质': A['D8台面材质'].map(lambda v: '未知' if v in UNKS or (isinstance(v, float) and np.isnan(v)) else v).values,
                         '主色': A['主色'].values, '柜体材质': A['柜体材质'].values, '元素': A['元素一'].map(az_elem).values,
                         '价格': pd.to_numeric(A['价格'], errors='coerce').values})


def channel_rows(channel: str) -> pd.DataFrame:
    from .channel_model import rows_from_analysis
    an = panel.analysis(channel)
    if an.A.empty:
        return pd.DataFrame()
    return amazon_rows(an.A) if channel == 'amazon' else rows_from_analysis(an.A)


def unit_rows(d: pd.DataFrame, att: str) -> pd.DataFrame:
    """行 → (属性, 尺寸段 · 形态, 取值) 级别的行；元素展开；取值未知或“其他（…）”的不要。"""
    x = d.explode('元素') if att == '元素' else d
    x = x.assign(框=(x['尺寸段'].astype(object).fillna('') + ' · ' + x['形态'].astype(str)).where(x['尺寸段'].notna()), 取值=x[att].astype(str))
    return x[x['框'].notna() & ~x['取值'].isin([str(u) for u in UNKS]) & ~x['取值'].str.startswith('其他（')]


def _share_slope(M):
    den = M.groupby(level=0).transform('sum')
    share = M.sum(axis=1) / den.sum(axis=1).replace(0, np.nan)
    xc = np.arange(M.shape[1]) - (M.shape[1] - 1) / 2
    slope = (np.log(M.div(den.replace(0, np.nan)).fillna(0) + 0.01) * xc).sum(axis=1) / (xc ** 2).sum()
    return share, slope


def counts(rows: pd.DataFrame, T: int, n: int = 6, detail: bool = False) -> dict:
    """窗口 T−n 至 T−1：{(属性, 尺寸段 · 形态, 取值): {fam, var, pb, units, share, slope}}；detail 时另给价位段分布。"""
    w = rows[rows['m'].between(T - n, T - 1) & (rows['c'] > 0)]
    if w.empty:
        return {}
    w = w.assign(pabs=pd.cut(w['价格'], PRICE_ABS, labels=False, right=False))
    out = {}
    for att in ATTRS:
        x = unit_rows(w, att)
        if x.empty:
            continue
        g = x.groupby(['框', '取值'])
        M = x.groupby(['框', '取值', 'm'])['c'].sum().unstack(fill_value=0).reindex(columns=range(T - n, T), fill_value=0)
        share, slope = _share_slope(M)
        fam, var, pb, units = g['fam'].nunique(), g['pid'].nunique(), g['pabs'].nunique(), g['c'].sum() / n
        dist = None
        if detail:
            cs = x.dropna(subset=['pabs']).groupby(['框', '取值', 'pabs'])['c'].sum()
            dist = {}
            for (f, v, b), c in cs.items():
                dist.setdefault((f, v), {})[PB_LABELS[int(b)]] = float(c)
        for k in fam.index:
            d = dict(fam=int(fam[k]), var=int(var[k]), pb=int(pb[k]), units=float(units[k]), share=float(share.get(k, np.nan)), slope=float(slope.get(k, np.nan)))
            if detail:
                tot = sum((dist.get(k) or {}).values())
                d['pb_dist'] = {b: c / tot for b, c in (dist.get(k) or {}).items()} if tot else {}
            out[(att,) + k] = d
    return out


def frame_units(rows: pd.DataFrame, T: int, n: int = 6) -> dict:
    """窗口内各尺寸段 · 形态的月均销量（尺寸段已知的全部行）。"""
    w = rows[rows['m'].between(T - n, T - 1) & rows['尺寸段'].notna()]
    k = w['尺寸段'].astype(str) + ' · ' + w['形态'].astype(str)
    return (w.groupby(k)['c'].sum() / n).to_dict()


def table(channel: str) -> dict:
    """某个其他渠道的丰富度对照表（缓存，数据变了重算）。返回 {window, end, units: {(属性, 尺寸段 · 形态, 取值): {...}}, frames, oos}。"""
    sig = panel.signature()
    with _lock:
        hit = _cache.get(channel)
        if hit and hit[0] == sig:
            return hit[1]
    az, ch = channel_rows('amazon'), channel_rows(channel)
    if az.empty or ch.empty:
        res = dict(available=False, reason='没有 Amazon 数据' if az.empty else '该渠道没有数据', units={}, frames={}, oos=[])
    else:
        T = min(int(az['m'].max()), int(ch['m'].max())) + 1  # 两渠道同窗口
        A0 = counts(az, T, detail=True)
        H0 = counts(ch, T, detail=True)
        trend = [counts(az, T - 12), counts(az, T - 6), A0]
        fr = frame_units(ch, T)
        units = {}
        for k in set(A0) | set(H0):
            a, h = A0.get(k) or {}, H0.get(k) or {}
            af, hf = a.get('fam', 0), h.get('fam', 0)
            units[k] = dict(az=a or None, ch=h or None, az_fam=af, ch_fam=hf, az_pb=a.get('pb', 0), ch_pb=h.get('pb', 0),
                            G=float(np.log((af + 1) / (hf + 1))),
                            az_trend=[dict(units=(t.get(k) or {}).get('units'), share=(t.get(k) or {}).get('share')) for t in trend],
                            ch_frame_units=float(fr.get(k[1], 0.0)))
        oos = []
        for k, u in units.items():
            a = u['az'] or {}
            if (k[0] != '元素' and u['ch_fam'] == 0 and a.get('units', 0) >= OOS_RULE['az_units'] and (a.get('share') or 0) >= OOS_RULE['az_share']
                    and (a.get('slope') or 0) > 0 and u['ch_frame_units'] >= OOS_RULE['ch_frame_units']):
                oos.append(dict(attr=k[0], sizeform=k[1], value=k[2], **u))
        oos.sort(key=lambda r: -r['G'])
        res = dict(available=True, window=f'{ms(T - 6)} 至 {ms(T - 1)}', windows=[f'{ms(T - 18)} 至 {ms(T - 13)}', f'{ms(T - 12)} 至 {ms(T - 7)}',
                                                                              f'{ms(T - 6)} 至 {ms(T - 1)}'],
                   T=ms(T), units=units, frames=fr, oos=oos)
    with _lock:
        _cache[channel] = (sig, res)
    return res


SEP = '||'


def save(channel: str) -> dict:
    """算一份最新的对照表并存库（扫描后调用），返回结果。"""
    from ..db import session
    from ..models_channel import ChannelRichness
    t = table(channel)
    data = dict(t, units={SEP.join(k): v for k, v in t.get('units', {}).items()})
    with session() as s:
        s.add(ChannelRichness(channel=channel, data=data))
    return t


def saved(channel: str) -> dict:
    """扫描页用：最近一次存库的对照表（与预计算的扫描结果同批）；没有时现算并存库。"""
    from sqlalchemy import select

    from ..db import session
    from ..models_channel import ChannelRichness
    with session() as s:
        r = s.scalar(select(ChannelRichness).where(ChannelRichness.channel == channel).order_by(ChannelRichness.id.desc()).limit(1))
        data = r.data if r is not None else None
    if data is None:
        return save(channel)
    return dict(data, units={tuple(k.split(SEP)): v for k, v in (data.get('units') or {}).items()})


def sizeform(frame: str) -> str:
    """框键“30″ · 整装 · 落地式”→ 对齐键“30″ · 落地式”。"""
    p = frame.split(' · ')
    return f'{p[0]} · {p[2]}' if len(p) >= 3 else frame


def for_unit(channel: str, frame: str, attr: str, value: str, t: dict | None = None) -> dict | None:
    """某个其他渠道单元的 Amazon 侧丰富度与差距（扫描、决策卡共用）。t 不给时现算（决策卡）；扫描页传入存库的对照表。"""
    if channel == 'amazon':
        return None
    t = table(channel) if t is None else t
    if not t.get('available'):
        return None
    k = (attr, sizeform(frame), value)
    u = t['units'].get(k)
    if u is None:
        u = dict(az=None, ch=None, az_fam=0, ch_fam=0, az_pb=0, ch_pb=0, G=0.0, az_trend=[], ch_frame_units=float(t['frames'].get(k[1], 0.0)))
    from ..config import CHANNEL_NAMES
    r = dict(u, attr=attr, sizeform=k[1], value=value, window=t['window'], windows=t['windows'], oos=u['ch_fam'] == 0)
    r['src'] = pop_text(CHANNEL_NAMES.get(channel, channel), r)
    return r


def pop_text(channel_name: str, r: dict) -> str:
    """“来源”小标签：两侧事实与公式（证据小标签 data-pop 格式，分号分隔）。"""
    a, h = r.get('az') or {}, r.get('ch') or {}
    dist = lambda d: '、'.join(f'{b} {x:.0%}' for b, x in sorted((d or {}).items(), key=lambda kv: PB_LABELS.index(kv[0]))) or '—'  # noqa: E731
    tr = ' → '.join(f"{t['units']:,.0f} 件（{t['share']:.0%}）" if t.get('units') is not None and t.get('share') is not None and not np.isnan(t['share']) else '—'
                    for t in r.get('az_trend') or [])
    parts = [f"框={r['sizeform']} · {r['attr']}：{r['value']}（尺寸段 × 形态对齐，不分拆装）", f"月份={r['window']}",
             f"样本数=Amazon {r['az_fam']} 个家族、{channel_name} {r['ch_fam']} 个家族",
             f"Amazon=家族 {r['az_fam']}、子体 {a.get('var', 0)}、价位段 {r['az_pb']}（{dist(a.get('pb_dist'))}），月均 {a.get('units', 0):,.0f} 件，框内 {(a.get('share') or 0):.0%}",
             f"Amazon 走势={tr}"]
    if r['ch_fam']:
        parts.append(f"{channel_name}=家族 {r['ch_fam']}、子体 {h.get('var', 0)}、价位段 {r['ch_pb']}（{dist(h.get('pb_dist'))}），月均 {h.get('units', 0):,.0f} 件，框内 {(h.get('share') or 0):.0%}")
    else:
        parts.append(f'{channel_name}=前 N 个商品页里没有这个单元的家族（样本外）')
    parts.append(f"G=ln(({r['az_fam']} + 1) ÷ ({r['ch_fam']} + 1)) = {r['G']:+.2f}")
    parts.append('读法=Amazon 结构领先，加分信号，不作独立立项理由；本渠道少不等于机会')
    return ';'.join(p.replace(';', '，') for p in parts)


def clear_cache():
    with _lock:
        _cache.clear()

