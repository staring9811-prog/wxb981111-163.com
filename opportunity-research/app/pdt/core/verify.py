"""Amazon 月度批次核对（AC-F17-03 / 04，DEC-102）。阈值取品类配置 verify。

- 月份误标（阻断，标“疑似月份错误”、不并入）：
  1) “上月购买标”日期多数不在所标月份；
  2) 两个月都出现的 ASIN 中，小类排名与上一个已并入月完全相同的比例 > rank_same_max_pct（默认 10%）。
- 来源与覆盖（异常，需确认后并入，并入后带 *）：
  1) 品类总月销较上月变化超出 ±total_change_pct（默认 30%）；
  2) 家族键月间一致率 < family_consistency_min（默认 90%）：上月的家族里，有子体本月仍在的，其子体本月仍归同一家族键的比例；
  3) 各标签覆盖率 < tag_coverage_min（默认 95%）：本批商品有取值的占比（尺寸、拆装、形态、台面、台面材质、主色、柜体材质）。
"""
import numpy as np
import pandas as pd

from .families import top_type

COVER_TAGS = [('尺寸', '尺寸段'), ('拆装', '装'), ('形态', '形态'), ('台面', '台面'), ('台面材质', '台面材质'), ('主色', '主色'), ('柜体材质', '柜体材质')]
UNKNOWN = {'', '未知', '信息不足', '待图片核验', None}


def _total(df):
    """品类总月销 = 各家族月销之和（子体月销按家族均分后相加）。"""
    return float(pd.to_numeric(df['units'], errors='coerce').fillna(0).clip(lower=0).sum())


def run(month: str, cur: pd.DataFrame, prev: pd.DataFrame | None, tags: dict, cfg: dict) -> dict:
    """cur / prev：列 item_id, family_key, rank, units, purchase_date（可空）。tags：{item_id: {标签: 值}}。返回 checks。"""
    th = dict(total_change_pct=30, family_consistency_min=90, tag_coverage_min=95, rank_same_max_pct=10)
    th.update(cfg or {})
    items = []
    prev_month = None if prev is None or prev.empty else str(prev.attrs.get('month', ''))
    # 1. 上月购买标日期
    dates = pd.to_datetime(cur.get('purchase_date', pd.Series(dtype=object)), errors='coerce').dropna() if 'purchase_date' in cur else pd.Series(dtype='datetime64[ns]')
    if len(dates):
        # 商品身上的购买标常年不更新，日期分散在过去很多个月，所以只看本批"最新"的购买标日期：
        # 正常导出最新标签落在所标月份或下个月月初；误标批次（如标为 2026-10、实为 9 月）最新日期整批停在上个月。
        latest = dates.max()
        nxt = (pd.Period(month, 'M') + 1).strftime('%Y-%m')
        lm = latest.strftime('%Y-%m')
        ok = lm in (month, nxt)
        share_out = float(1 - dates.dt.strftime('%Y-%m').isin([month, nxt]).mean())
        items.append(dict(key='purchase_label', name='月份误标 · 上月购买标日期', sub='本批最新购买标须落在所标月份（或下月初）',
                          value=f"最新 {latest:%Y-%m-%d}（范围 {dates.min():%Y-%m-%d} 至 {latest:%Y-%m-%d}）", detail=f'应在 {month} 或 {nxt}', n=int(len(dates)),
                          threshold='最新日期在所标月份内', result='pass' if ok else 'block', share_out=share_out))
    else:
        items.append(dict(key='purchase_label', name='月份误标 · 上月购买标日期', sub='须落在所标月份', value='本批无上月购买标', detail='不判定',
                          n=0, threshold='在所标月份内', result='na'))
    # 2. 排名完全相同
    if prev is not None and not prev.empty:
        a = cur[['item_id', 'rank']].dropna().drop_duplicates('item_id')
        b = prev[['item_id', 'rank']].dropna().drop_duplicates('item_id')
        m = a.merge(b, on='item_id', suffixes=('', '_p'))
        same = int((m['rank'].astype(float) == m['rank_p'].astype(float)).sum())
        pct = same / len(m) * 100 if len(m) else 0.0
        items.append(dict(key='rank_same', name='月份误标 · 与上月排名完全相同', sub='两月都出现的 ASIN 中，小类排名一样的比例',
                          value=f'{pct:.1f}%', pct=pct, n=int(len(m)), same=same, detail=f'对照 {prev_month}',
                          threshold=f"> {th['rank_same_max_pct']:g}% 判月份错误", result='block' if pct > th['rank_same_max_pct'] else 'pass'))
        # 3. 品类总月销变化
        t1, t0 = _total(cur), _total(prev)
        ch = (t1 / t0 - 1) * 100 if t0 else None
        items.append(dict(key='total_change', name='品类总月销变化', sub='与上月相比', value='—' if ch is None else f'{ch:+.1f}%', pct=ch,
                          detail=f'{t1:,.0f} 件 vs {t0:,.0f} 件', cur_total=t1, prev_total=t0,
                          threshold=f"±{th['total_change_pct']:g}% 内", result='pass' if ch is None or abs(ch) <= th['total_change_pct'] else 'anomaly'))
        # 4. 家族键月间一致率
        pm = prev.drop_duplicates('item_id').set_index('item_id')['family_key']
        cm = cur.drop_duplicates('item_id').set_index('item_id')['family_key']
        both = pm.index.intersection(cm.index)
        fams = pd.DataFrame({'prev': pm.reindex(both).values, 'cur': cm.reindex(both).values})
        cons = fams.groupby('prev').apply(lambda g: bool((g['cur'] == g.name).all()), include_groups=False) if len(fams) else pd.Series(dtype=bool)
        rate = float(cons.mean() * 100) if len(cons) else 100.0
        bad = int((~cons).sum()) if len(cons) else 0
        items.append(dict(key='family_consistency', name='家族键月间一致率', sub='同一父体家族两月归属一致', value=f'{rate:.1f}%', pct=rate,
                          n=int(len(cons)), detail=(f'{bad} 个家族的归属与 {prev_month} 不同' if bad else ''),
                          threshold=f"≥ {th['family_consistency_min']:g}%", result='pass' if rate >= th['family_consistency_min'] else 'anomaly'))
    else:
        items.append(dict(key='rank_same', name='月份误标 · 与上月排名完全相同', sub='两月都出现的 ASIN 中，小类排名一样的比例', value='无上月数据',
                          n=0, threshold=f"> {th['rank_same_max_pct']:g}% 判月份错误", result='na'))
    # 5. 标签覆盖率
    ids = list(dict.fromkeys(cur['item_id']))
    cov, low = {}, []
    for name, tg in COVER_TAGS:
        if tg == '台面':
            vals = [top_type((tags.get(i) or {}).get('台面材质'), (tags.get(i) or {}).get('台盆材质')) for i in ids]
            known = [v not in ('未知',) and not str(v).startswith('台面未知') for v in vals]
        else:
            known = [((tags.get(i) or {}).get(tg) not in UNKNOWN) for i in ids]
        p = float(np.mean(known) * 100) if ids else 0.0
        cov[name] = p
        if p < th['tag_coverage_min']:
            low.append(name)
    items.append(dict(key='tag_coverage', name='标签覆盖率', sub='每个标签有取值的商品占比', coverage=cov, n=len(ids), low=low,
                      threshold=f"每项 ≥ {th['tag_coverage_min']:g}%", result='anomaly' if low else 'pass'))
    status = 'suspect_month' if any(i['result'] == 'block' for i in items) else ('anomaly' if any(i['result'] == 'anomaly' for i in items) else 'ok')
    return dict(month=month, prev_month=prev_month, items=items, status=status, thresholds=th, reason=reason_text(items, prev_month))


def reason_text(items, prev_month) -> str:
    out = []
    for i in items:
        if i['result'] == 'block' and i['key'] == 'rank_same':
            out.append(f"与 {prev_month} 小类排名完全相同的 ASIN 占 {i['pct']:.1f}%（n={i['n']:,}）")
        elif i['result'] == 'block' and i['key'] == 'purchase_label':
            out.append(f"上月购买标日期为 {i['value']}，不在所标月份")
        elif i['result'] == 'anomaly' and i['key'] == 'total_change':
            out.append(f"品类总月销较上月 {i['value']}（阈值 {i['threshold']}）")
        elif i['result'] == 'anomaly' and i['key'] == 'family_consistency':
            out.append(f"家族键月间一致率 {i['value']}（阈值 {i['threshold']}，n={i['n']:,}）")
        elif i['result'] == 'anomaly' and i['key'] == 'tag_coverage':
            out.append('标签覆盖率不足：' + '、'.join(f"{k} {i['coverage'][k]:.0f}%" for k in i['low']))
    return '；'.join(out)
