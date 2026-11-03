"""其他渠道数据（F28）：Home Depot / Lowe's / Wayfair 的商品、排名、月度 VP / 非 VP 评论数并入分析库，换算月销。

- 进入方式：评论 VP 追踪（F23）完成一个月份采集后调用 `ingest_tracker_month()`（AC-F28-01）；或上传追踪器导出的 Excel（含“商品月度明细”表，AC-F28-02）。
- 完整月才计入；未完整月份（表头带“未完整”，或采集日所在月）只作参考：批次状态 reference，不进入分析（AC-F28-02）。
- 去重（AC-F28-05）：同系列商品共享同一批评论。有评论 ID 时按评论 ID 去重，一条评论被 k 个商品共享时每个商品记 1/k，
  渠道或单元合计 = 去重后条数；只有 Excel（无评论 ID）时，渠道合计取文件“渠道月度汇总”的去重数，商品按“同品牌、逐月条数完全相同 = 同系列”
  先均分，再按渠道 × 月 × VP 口径等比例折算到去重合计（近似，页面注明）。
- 月销估算：评论换算法 = VP × vp_coef + 非 VP × nonvp_coef（品类配置，默认 50 / 20，AC-F28-03）；
  榜单排名平滑法 = 用同时有排名和评论换算月销的商品拟合 ln(月均销) = a + b·ln(排名)，这类商品 < 10 个时不提供（AC-F28-04）。
"""
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import delete, func, insert, select

from .. import catconfig
from ..config import CHANNEL_NAMES, data_dir
from ..db import session
from ..models import Batch, ChannelReview, Product, Snapshot, now
from . import panel

CH_ALIASES = {'home depot': 'homedepot', 'homedepot': 'homedepot', 'hdp': 'homedepot', "lowe's": 'lowes', 'lowes': 'lowes', 'wayfair': 'wayfair'}
MIN_RANK_POINTS = 10


def ch_key(name: str) -> str | None:
    return CH_ALIASES.get(str(name or '').strip().lower())


def _month_cols(columns):
    """表头 '2026-01 VP' / '2026-11（未完整） 非VP' → {月份: (VP列, 非VP列, 是否完整)}。"""
    out = {}
    for c in columns:
        m = re.match(r'^(\d{4}-\d{2})(（未完整）)?\s*(VP|非VP)$', str(c).strip())
        if m:
            d = out.setdefault(m.group(1), [None, None, m.group(2) is None])
            d[0 if m.group(3) == 'VP' else 1] = c
            if m.group(2):
                d[2] = False
    return out


def read_tracker_excel(path: Path) -> dict:
    """解析追踪器导出：商品月度明细 + 渠道月度汇总（去重数）。"""
    xl = pd.ExcelFile(path)
    if '商品月度明细' not in xl.sheet_names:
        raise ValueError(f'{path.name} 没有“商品月度明细”表，请上传评论 VP 追踪器导出的 Excel')
    det = xl.parse('商品月度明细', dtype={'商品ID': str})
    for need in ('渠道', '商品ID', '排名'):
        if need not in det.columns:
            raise ValueError(f'“商品月度明细”表缺少“{need}”列（第 1 行表头）')
    months = _month_cols(det.columns)
    summ = xl.parse('渠道月度汇总') if '渠道月度汇总' in xl.sheet_names else None
    totals = {}
    if summ is not None:
        sm = _month_cols(summ.columns)
        for _, r in summ.iterrows():
            ch = ch_key(r.get('渠道'))
            if ch and str(r.get('层级')) == '渠道小计':
                totals[ch] = {m: (float(r[v] or 0), float(r[n] or 0), ok) for m, (v, n, ok) in sm.items()}
                totals[ch]['_dedup_reviews'] = float(r.get('去重评论数') or 0)
    return dict(detail=det, months=months, totals=totals)


def _alloc_excel(det: pd.DataFrame, months: dict, totals: dict) -> pd.DataFrame:
    """无评论 ID 时的去重折算：同品牌逐月条数完全相同的商品均分，再等比例折算到渠道去重合计。返回长表。"""
    det = det.copy()
    det['channel'] = det['渠道'].map(ch_key)
    vcols = [c for m, (v, n, ok) in months.items() for c in (v, n) if c]
    det['_sig'] = det['品牌'].astype(str) + '|' + det[vcols].fillna(0).astype(int).astype(str).agg(','.join, axis=1)
    det['_k'] = det.groupby(['channel', '_sig'])['商品ID'].transform('count')
    rows = []
    for _, r in det.iterrows():
        for m, (v, n, ok) in months.items():
            rows.append(dict(channel=r['channel'], item_id=str(r['商品ID']), month=m, complete=ok, vp_page=int(r[v] or 0), nonvp_page=int(r[n] or 0),
                             vp_d=float(r[v] or 0) / r['_k'], nonvp_d=float(r[n] or 0) / r['_k']))
    L = pd.DataFrame(rows)
    for (ch, m), g in L.groupby(['channel', 'month']):
        t = (totals.get(ch) or {}).get(m)
        if not t:
            continue
        for col, tot in (('vp_d', t[0]), ('nonvp_d', t[1])):
            s = g[col].sum()
            if s > 0:
                L.loc[g.index, col] = g[col] * (tot / s)
    return L


def _alloc_reviews(reviews: list[dict]) -> pd.DataFrame:
    """有评论 ID：每条评论在共享它的 k 个商品间各记 1/k（渠道、单元合计即按评论 ID 去重）。"""
    owners = defaultdict(set)
    for r in reviews:
        owners[(r['channel'], r['review_id'])].add(r['item_id'])
    acc = defaultdict(lambda: [0, 0, 0.0, 0.0])
    seen = set()
    for r in reviews:
        key = (r['channel'], r['review_id'], r['item_id'])
        if key in seen:
            continue
        seen.add(key)
        k = len(owners[(r['channel'], r['review_id'])])
        a = acc[(r['channel'], r['item_id'], r['month'])]
        if r['vp']:
            a[0] += 1
            a[2] += 1 / k
        else:
            a[1] += 1
            a[3] += 1 / k
    return pd.DataFrame([dict(channel=c, item_id=i, month=m, vp_page=a[0], nonvp_page=a[1], vp_d=a[2], nonvp_d=a[3])
                         for (c, i, m), a in acc.items()])


def _write(items: pd.DataFrame, L: pd.DataFrame, source: str, file_path: str, complete_months: set, totals: dict | None = None) -> dict:
    """写商品、批次（每渠道 × 月一个）与快照；未完整月份批次状态 reference（只参考，不计入）。同渠道同月旧批次标 superseded。"""
    from . import tagging
    stat = {}
    with session() as s:
        have = {(p.channel, p.item_id): p for p in s.scalars(select(Product).where(Product.channel.in_(list(items['channel'].unique()))))}
        new = defaultdict(list)
        for r in items.to_dict('records'):
            p = have.get((r['channel'], r['item_id']))
            if p is None:
                p = Product(channel=r['channel'], item_id=r['item_id'])
                s.add(p)
                new[r['channel']].append(r['item_id'])
            for k in ('brand', 'title', 'image_url', 'link', 'series'):
                if r.get(k):
                    setattr(p, k, str(r[k]))
        rank = items.set_index(['channel', 'item_id'])
        for (ch, m), g in L.groupby(['channel', 'month']):
            ok = m in complete_months
            for old in s.scalars(select(Batch).where(Batch.channel == ch, Batch.month == m, Batch.status.in_(['merged', 'reference']))):
                old.status = 'superseded'
            tot = (totals or {}).get(ch, {}).get(m)
            dedup = dict(vp=float(g['vp_d'].sum()), nonvp=float(g['nonvp_d'].sum()))
            if tot:
                dedup = dict(vp=tot[0], nonvp=tot[1])
            b = Batch(channel=ch, month=m, source=source, file_path=file_path, status='merged' if ok else 'reference', rows=int(len(g)),
                      checks=dict(dedup=dedup, complete=ok, items=int(len(g))), merged_at=now() if ok else None,
                      anomaly_reason='' if ok else '未完整月份，只作参考，不计入')
            s.add(b)
            s.flush()
            snaps = []
            for r in g.to_dict('records'):
                info = rank.loc[(ch, r['item_id'])] if (ch, r['item_id']) in rank.index else {}
                price = info.get('price') if hasattr(info, 'get') else None
                snaps.append(dict(batch_id=b.id, channel=ch, month=m, item_id=r['item_id'], price=None if price is None or pd.isna(price) else float(price),
                                  rank=None if info is None or pd.isna(info.get('rank')) else float(info.get('rank')),
                                  rating=None if pd.isna(info.get('rating', np.nan)) else float(info.get('rating')),
                                  vp=int(r['vp_page']), nonvp=int(r['nonvp_page']), units=None,
                                  raw=dict(vp_d=float(r['vp_d']), nonvp_d=float(r['nonvp_d']), entry=info.get('entry', ''), source=source, in_scope=True)))
            s.execute(insert(Snapshot), snaps)
            st = stat.setdefault(ch, dict(months=0, reference=0, items=0))
            st['months' if ok else 'reference'] += 1
            st['items'] = max(st['items'], int(len(g)))
    last = max(complete_months) if complete_months else ''
    for ch, ids in new.items():
        tagging.tag_products(ch, ids, last)
    refresh_rank_method()
    panel.bump()
    return stat


def import_excel(path: Path, source: str = 'upload') -> dict:
    """上传追踪器导出的 Excel 并入（AC-F28-02）。"""
    d = read_tracker_excel(path)
    det = d['detail']
    items = pd.DataFrame(dict(channel=det['渠道'].map(ch_key), item_id=det['商品ID'].astype(str), brand=det.get('品牌', ''), title=det.get('标题', ''),
                              rank=pd.to_numeric(det['排名'], errors='coerce'), entry=det.get('入口', '')))
    items = items[items['channel'].notna()]
    L = _alloc_excel(det[det['渠道'].map(ch_key).notna()], d['months'], d['totals'])
    complete = {m for m, (_, _, ok) in d['months'].items() if ok}
    stat = _write(items.drop_duplicates(['channel', 'item_id']), L, source, str(path), complete, d['totals'])
    stat['_dedup'] = {ch: dict(all=t.get('_dedup_reviews'), complete=sum(v[0] + v[1] for m, v in t.items() if m != '_dedup_reviews' and v[2]))
                      for ch, t in d['totals'].items()}
    return stat


PLAT = {'HomeDepot': 'homedepot', 'Lowes': 'lowes', 'Wayfair': 'wayfair'}


def ingest_tracker_month(project_dir_or_rows, months: list[str] | None = None, collected_on: str | None = None) -> dict:
    """评论 VP 追踪完成采集后并入（AC-F28-01，供组 C 调用）。

    参数可以是追踪器项目数据目录（含 lists/*.json 与 products/<平台>/<商品ID>.json），或已整理的行：
    [{channel 或 平台, item_id 或 商品ID 或 id, 品牌, 标题, 排名, 价格, 主图URL, 商品链接, 入口,
      reviews: [{评论ID, 评论日期 YYYY-MM-DD, VP状态 'VP' / 'non_VP', 评分}]}]
    months：只并入这些月份（默认评论里出现的全部）；collected_on：采集日（其所在月为未完整月，只作参考）。"""
    rows = []
    if isinstance(project_dir_or_rows, (str, Path)):
        root = Path(project_dir_or_rows)
        for f in sorted((root / 'lists').glob('*.json')):
            for r in (json.loads(f.read_text(encoding='utf-8')) or {}).get('rows', []):
                if not r.get('排名'):
                    continue
                plat = r.get('平台') or ''
                pf = root / 'products' / plat / f"{r['id']}.json"
                p = json.loads(pf.read_text(encoding='utf-8')) if pf.exists() else {}
                rows.append(dict(r, 入口=f.stem, reviews=p.get('reviews') or [], details=p.get('details') or {}))
    else:
        rows = list(project_dir_or_rows)
    items, reviews = [], []
    for r in rows:
        ch = PLAT.get(r.get('平台')) or ch_key(r.get('channel') or r.get('平台') or r.get('渠道'))
        if not ch:
            continue
        iid = str(r.get('item_id') or r.get('商品ID') or r.get('id'))
        det = r.get('details') or {}
        items.append(dict(channel=ch, item_id=iid, brand=r.get('品牌') or r.get('brand') or det.get('品牌', ''), title=r.get('标题') or r.get('title') or det.get('标题', ''),
                          rank=pd.to_numeric(r.get('排名') or r.get('rank'), errors='coerce'), price=pd.to_numeric(r.get('价格') or r.get('price'), errors='coerce'),
                          rating=pd.to_numeric(r.get('页面评分') or r.get('rating'), errors='coerce'), image_url=r.get('主图URL') or r.get('image_url') or '',
                          link=r.get('商品链接') or r.get('url') or '', entry=r.get('入口', ''), series=r.get('系列') or ''))
        for x in r.get('reviews') or []:
            dt = str(x.get('评论日期') or x.get('date') or '')[:10]
            if len(dt) < 7:
                continue
            reviews.append(dict(channel=ch, item_id=iid, review_id=str(x.get('评论ID') or x.get('review_id')), month=dt[:7], date=dt,
                                vp=(x.get('VP状态') or x.get('vp')) in ('VP', True), stars=x.get('评分') or x.get('stars'), text=x.get('评论原文') or x.get('text') or ''))
    if months:
        reviews = [x for x in reviews if x['month'] in months]
    items = pd.DataFrame(items).drop_duplicates(['channel', 'item_id'])
    L = _alloc_reviews(reviews)
    if L.empty:
        return {}
    cut = (collected_on or '')[:7]
    complete = {m for m in L['month'].unique() if not cut or m < cut}
    # 评论明细入库（按评论 ID 唯一）
    with session() as s:
        exist = {(c, r, i) for c, r, i in s.execute(select(ChannelReview.channel, ChannelReview.review_id, ChannelReview.item_id))}
        add = [dict(channel=x['channel'], review_id=x['review_id'], item_id=x['item_id'], month=x['month'], vp=bool(x['vp']),
                    stars=None if x['stars'] in (None, '') else float(x['stars']), text=str(x['text'])[:4000], date=x['date'])
               for x in reviews if (x['channel'], x['review_id'], x['item_id']) not in exist]
        uniq = {}
        for a in add:
            uniq[(a['channel'], a['review_id'], a['item_id'])] = a
        if uniq:
            s.execute(insert(ChannelReview), list(uniq.values()))
    return _write(items, L, 'tracker', str(project_dir_or_rows) if isinstance(project_dir_or_rows, (str, Path)) else '', complete)


# ---------------- 估算与对照 ----------------
def channel_cfg(ch: str) -> dict:
    cfg = (catconfig.current()[1].get('channels') or {}).get(ch) or {}
    return dict(method=cfg.get('method', 'review'), vp_coef=float(cfg.get('vp_coef', 50)), nonvp_coef=float(cfg.get('nonvp_coef', 20)))


def item_months(ch: str, include_reference: bool = False) -> pd.DataFrame:
    with session() as s:
        st = ['merged', 'reference'] if include_reference else ['merged']
        q = (select(Snapshot.id, Snapshot.item_id, Snapshot.month, Snapshot.rank, Snapshot.vp, Snapshot.nonvp, Snapshot.raw, Batch.status)
             .join(Batch, Batch.id == Snapshot.batch_id).where(Snapshot.channel == ch, Batch.status.in_(st)))
        rows = [dict(sid=i, item_id=it, month=m, rank=rk, vp=v, nonvp=n, vp_d=(raw or {}).get('vp_d', v), nonvp_d=(raw or {}).get('nonvp_d', n),
                     units_rank=(raw or {}).get('units_rank'), complete=stt == 'merged') for i, it, m, rk, v, n, raw, stt in s.execute(q)]
    return pd.DataFrame(rows)


def rank_fit(ch: str):
    """排名平滑：用同时有排名和评论换算月销的商品拟合 ln(月均销) = a + b·ln(排名)。不足 10 个返回 (None, 原因, n)。"""
    c = channel_cfg(ch)
    L = item_months(ch)
    if L.empty:
        return None, '还没有本渠道的完整月数据', 0
    L['units'] = L['vp_d'] * c['vp_coef'] + L['nonvp_d'] * c['nonvp_coef']
    g = L.groupby('item_id').agg(units=('units', 'mean'), rank=('rank', 'min'))
    pts = g[(g['rank'] > 0) & (g['units'] > 0)]
    n = int(len(pts))
    if n < MIN_RANK_POINTS:
        return None, f'同时有排名和评论换算销量的商品只有 {n} 个（少于 {MIN_RANK_POINTS} 个），不提供榜单排名平滑法', n
    b, a = np.polyfit(np.log(pts['rank']), np.log(pts['units']), 1)
    return dict(a=float(a), b=float(b), n=n), '', n


def refresh_rank_method():
    """重算各渠道排名平滑的逐月估算，写入快照 raw.units_rank（月度起伏按渠道评论换算合计的逐月比例分配）。"""
    for ch in ('homedepot', 'lowes', 'wayfair'):
        fit, why, n = rank_fit(ch)
        c = channel_cfg(ch)
        L = item_months(ch)
        if L.empty:
            continue
        L['units'] = L['vp_d'] * c['vp_coef'] + L['nonvp_d'] * c['nonvp_coef']
        mt = L.groupby('month')['units'].sum()
        season = mt / mt.mean() if mt.mean() > 0 else mt * 0 + 1
        with session() as s:
            for r in L.itertuples():
                sn = s.get(Snapshot, int(r.sid))
                raw = dict(sn.raw or {})
                if fit and r.rank and r.rank > 0:
                    raw['units_rank'] = float(np.exp(fit['a'] + fit['b'] * np.log(r.rank)) * season.get(r.month, 1.0))
                else:
                    raw.pop('units_rank', None)
                sn.raw = raw


def summary() -> dict:
    """数据页：各渠道月份、商品数、去重评论数、两种方法合计与对照。"""
    out = {}
    with session() as s:
        for ch in ('homedepot', 'lowes', 'wayfair'):
            bs = list(s.scalars(select(Batch).where(Batch.channel == ch, Batch.status.in_(['merged', 'reference'])).order_by(Batch.month)))
            if not bs:
                continue
            c = channel_cfg(ch)
            fit, why, n = rank_fit(ch)
            months = []
            for b in bs:
                d = (b.checks or {}).get('dedup') or {}
                vp, nv = float(d.get('vp', 0)), float(d.get('nonvp', 0))
                months.append(dict(month=b.month, complete=b.status == 'merged', items=b.rows, vp=vp, nonvp=nv, reviews=vp + nv,
                                   units=vp * c['vp_coef'] + nv * c['nonvp_coef'], source=b.source, at=b.created_at, batch_id=b.id))
            comp = [m for m in months if m['complete']]
            out[ch] = dict(name=CHANNEL_NAMES[ch], months=months, n_items=max((m['items'] for m in months), default=0),
                           reviews_complete=sum(m['reviews'] for m in comp), reviews_all=sum(m['reviews'] for m in months),
                           vp_complete=sum(m['vp'] for m in comp), nonvp_complete=sum(m['nonvp'] for m in comp),
                           units_review=sum(m['units'] for m in comp) / max(1, len(comp)), cfg=c, fit=fit, fit_why=why, fit_n=n,
                           first=comp[0]['month'] if comp else '', last=comp[-1]['month'] if comp else '',
                           reference=[m['month'] for m in months if not m['complete']])
    return out


def compare(ch: str, top: int = 15) -> list[dict]:
    """两种方法对照（商品级，完整月平均）。"""
    c = channel_cfg(ch)
    L = item_months(ch)
    if L.empty:
        return []
    L['units'] = L['vp_d'] * c['vp_coef'] + L['nonvp_d'] * c['nonvp_coef']
    g = L.groupby('item_id').agg(units=('units', 'mean'), units_rank=('units_rank', 'mean'), rank=('rank', 'min'), vp=('vp_d', 'sum'), nonvp=('nonvp_d', 'sum'))
    with session() as s:
        prods = {p.item_id: p for p in s.scalars(select(Product).where(Product.channel == ch, Product.item_id.in_(list(g.index))))}
    out = []
    for i, r in g.sort_values('rank').head(top).iterrows():
        p = prods.get(i)
        out.append(dict(item_id=i, brand=p.brand if p else '', title=p.title if p else '', rank=None if pd.isna(r['rank']) else int(r['rank']),
                        vp=float(r['vp']), nonvp=float(r['nonvp']), units_review=float(r['units']),
                        units_rank=None if pd.isna(r['units_rank']) else float(r['units_rank']),
                        diff=None if pd.isna(r['units_rank']) or r['units'] == 0 else float(r['units_rank'] / r['units'] - 1)))
    return out


def save_upload(filename: str, content: bytes) -> Path:
    d = data_dir() / 'raw' / 'channels'
    d.mkdir(parents=True, exist_ok=True)
    p = d / (pd.Timestamp.now().strftime('%Y%m%d%H%M%S_') + re.sub(r'[^\w.\-]+', '_', filename)[-120:])
    p.write_bytes(content)
    return p
