"""机会扫描（PAGE-F20-01，API-F20-01）：读预计算的 Opportunity 表（NFR-009）；历史月份没有算过时当场算一次并保存。"""
import io
import time
from urllib.parse import quote

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from .. import catconfig
from ..auth import any_user
from ..config import CHANNEL_NAMES
from ..db import session
from ..models import Batch, Card, Opportunity, Product, Tag
from ..models_data import ScanMeta
from ..core import channel_model, pipeline, richness
from ..core.scan import KINDS, demand_scope
from .ui import render

router = APIRouter()
TYPE_KEYS = {'growth': '增长型', 'rating': '评分缺口型', 'price': '价格缺口型', 'pit': '坑'}
GRADE_KEYS = {'bt': '经回测', 'btd': '经回测（打折）', 'obs': '历史观察', 'un': '未验证'}
NONE_KEY = {'none': '未入四类'}  # 其他渠道：没有四类标记的单元（看 Amazon 侧丰富度时用）
ATTR_KEYS = {'tm': '台面材质', 'el': '元素', 'color': '主色', 'body': '柜体材质'}
ICON = {'增长型': 'trend-up', '评分缺口型': 'chart-bar', '价格缺口型': 'scales', '坑': 'trend-down'}


def _meta(channel, month):
    with session() as s:
        q = select(ScanMeta).where(ScanMeta.channel == channel)
        if month:
            q = q.where(ScanMeta.month == month)
        m = s.scalar(q.order_by(ScanMeta.month.desc(), ScanMeta.id.desc()).limit(1))
        if m is not None:
            s.expunge(m)
        return m


def _results(channel, month, frame, vars, type, grade):
    """当前渠道、当前筛选下的扫描结果；页面与导出共用。"""
    meta = _meta(channel, month or None)
    if meta is None:
        with session() as s:
            has = s.scalar(select(Batch.id).where(Batch.channel == channel, Batch.status == 'merged', *( [Batch.month == month] if month else [])).limit(1))
        if has:
            pipeline.rescan(channel, month or None)
            meta = _meta(channel, month or None)
    rows, frames_all, summary = [], [], []
    vars_ = [ATTR_KEYS[v] for v in vars if v in ATTR_KEYS] or list(ATTR_KEYS.values())
    types = [TYPE_KEYS[t] for t in type if t in TYPE_KEYS]
    show_none = channel != 'amazon' and 'none' in type
    grades = [GRADE_KEYS[g] for g in grade if g in GRADE_KEYS]
    ch_ev = channel_model.evidence(channel) if channel != 'amazon' else None
    rt = richness.saved(channel) if channel != 'amazon' and meta is not None else None
    if meta is not None:
        with session() as s:
            ops = list(s.scalars(select(Opportunity).where(Opportunity.channel == channel, Opportunity.month == meta.month)))
            cards = {}
            for c in s.scalars(select(Card).where(Card.channel == channel)):
                cards.setdefault((c.frame, c.attr, c.value), c.id)
                cards.setdefault(('*', c.attr, c.value), c.id)
        scope = demand_scope([(o.frame, o.attr, o.value, o.metrics or {}) for o in ops])  # 需求范围（AC-F20-06、07）
        fu = {f['frame']: f['units'] for f in meta.meta.get('frames', [])}
        frames_all = [f['frame'] for f in meta.meta.get('frames', [])]
        # 按框汇总（全部单元）
        agg = {}
        for o in ops:
            a = agg.setdefault(o.frame, {k: 0 for k in KINDS})
            for k in KINDS:
                a[k] += int(bool((o.metrics or {}).get('flags', {}).get(k)))
        summary = [dict(frame=f, units=fu.get(f, 0), **agg.get(f, {k: 0 for k in KINDS})) for f in frames_all]
        for o in ops:
            m = o.metrics or {}
            flags = [k for k in KINDS if m.get('flags', {}).get(k)]
            if not flags and not show_none:
                continue
            if o.attr not in vars_ or (frame and o.frame != frame):
                continue
            if flags and (types or show_none) and not set(flags) & set(types):
                continue
            ev = o.evidence if flags else (ch_ev or '—')
            if grades and ev not in grades:
                continue
            rows.append(dict(id=o.id, frame=o.frame, attr=o.attr, value=o.value, flags=flags, evidence=ev, m=m, frame_units=fu.get(o.frame, 0),
                             card=cards.get((o.frame, o.attr, o.value)), related=cards.get(('*', o.attr, o.value)), oos=False,
                             scope=scope.get((o.frame, o.attr, o.value)),
                             rich=richness.for_unit(channel, o.frame, o.attr, o.value, rt) if rt else None))
        if channel != 'amazon' and not types and not grades:
            # 样本外（AC-F29-06）：本渠道前 N 里没有家族、Amazon 需求已证明的单元，挂在同尺寸段 · 形态里月销最大的已扫描框下
            for u in (rt or {}).get('oos', []):
                tgt = [f for f in frames_all if richness.sizeform(f) == u['sizeform']]
                if not tgt or u['attr'] not in vars_ or (frame and tgt[0] != frame):
                    continue
                rows.append(dict(id=None, frame=tgt[0], attr=u['attr'], value=u['value'], flags=[], evidence='样本外', m={}, frame_units=fu.get(tgt[0], 0),
                                 card=None, related=None, oos=True, scope=None, rich=richness.for_unit(channel, tgt[0], u['attr'], u['value'], rt)))
        order = {f: i for i, f in enumerate(frames_all)}
        rows.sort(key=lambda r: (order.get(r['frame'], 999), 9 if r['oos'] else (min(KINDS.index(k) for k in r['flags']) if r['flags'] else 5),
                                 -(r['m'].get('units') or 0)))
    return meta, rows, frames_all, summary, vars_


def _asm_unknown(channel: str) -> int:
    """“装”未知（不进框）的商品数：没有可扫描的框时，用来区分“缺分框标签”和“筛选为空”。"""
    with session() as s:
        return s.scalar(select(func.count(func.distinct(Tag.item_id))).select_from(Tag)
                        .join(Product, (Product.channel == Tag.channel) & (Product.item_id == Tag.item_id))
                        .where(Tag.channel == channel, Tag.tag == '装', Tag.value.in_(['', '未知']), Product.excluded.is_(False))) or 0


@router.get('/scan')
def scan_page(request: Request, channel: str = 'amazon', month: str = '', frame: str = '', vars: list[str] = Query(default=[]),
              type: list[str] = Query(default=[]), grade: list[str] = Query(default=[]), user=any_user):
    t0 = time.time()
    if channel not in CHANNEL_NAMES:
        channel = 'amazon'
    meta, rows, frames_all, summary, vars_ = _results(channel, month, frame, vars, type, grade)
    months = pipeline.scan_months(channel)
    with session() as s:
        merged = [m for (m,) in s.execute(select(Batch.month).where(Batch.channel == channel, Batch.status == 'merged').distinct().order_by(Batch.month.desc()))]
    from ..core.channels import channel_cfg
    cfg = channel_cfg(channel) if channel != 'amazon' else None
    chst = channel_model.status(channel) if channel != 'amazon' else None
    rich = richness.saved(channel) if channel != 'amazon' and meta is not None else None
    asm_unknown = _asm_unknown(channel) if meta is not None and not frames_all else 0
    min_fu = (catconfig.current()[1].get('scan') or {}).get('min_frame_units', 200)
    run = pipeline.latest_run()
    return render(request, 'scan.html', 'PAGE-F20-01', '机会扫描', run_invalid=bool(run is not None and not run.valid), channel=channel, meta=meta, rows=rows, summary=summary, frames=frames_all, frame=frame,
                  chst=chst, rich_window=(rich or {}).get('window'), none_key=NONE_KEY, asm_unknown=asm_unknown, min_fu=min_fu,
                  vars=[k for k, v in ATTR_KEYS.items() if v in vars_], types=type, grades=grade, months=sorted(set(months) | set(merged), reverse=True),
                  month=meta.month if meta else month, cfg=cfg, icon=ICON, type_keys=TYPE_KEYS, grade_keys=GRADE_KEYS, attr_keys=ATTR_KEYS,
                  elapsed=round(time.time() - t0, 2), export_qs=request.url.query)


@router.get('/scan/export')
def scan_export(channel: str = 'amazon', month: str = '', frame: str = '', vars: list[str] = Query(default=[]),
                type: list[str] = Query(default=[]), grade: list[str] = Query(default=[]), user=any_user):
    """导出当前渠道、当前筛选下的扫描结果，列同页面表格。"""
    from openpyxl import Workbook
    if channel not in CHANNEL_NAMES:
        channel = 'amazon'
    meta, rows, _, _, _ = _results(channel, month, frame, vars, type, grade)
    est = '' if channel == 'amazon' else '估算'
    wb = Workbook()
    ws = wb.active
    ws.title = '扫描结果'
    ws.append(['框', f'框{est}月销', '机会类型', '属性', '取值', '需求范围', f'{est}月销', '份额（前期）', '份额（近期）', '在卖的款数', '单款 ÷ 同框', '评分', '同框评分',
               '溢价', '中位价', '新品占比', '同框新品占比', '新家族做到', '新家族数', '同框新家族做到', '同框新家族数', '证据等级'])
    for r in rows:
        m = r['m']
        am = channel == 'amazon'
        ws.append([r['frame'], r['frame_units'], '、'.join(r['flags']), r['attr'], r['value'], (r.get('scope') or {}).get('text', ''), m.get('units'), m.get('share_prev'), m.get('share'),
                   m.get('families'), m.get('per_family_ratio'), m.get('rating'), m.get('frame_rating'), m.get('premium'), m.get('median_price'),
                   m.get('newshare'), m.get('frame_newshare'), m.get('newmade') if am else None, m.get('newfam') if am else None,
                   m.get('frame_newmade') if am else None, m.get('frame_newfam') if am else None, r['evidence']])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fn = f"机会扫描_{CHANNEL_NAMES[channel]}_{meta.month if meta else month or '无数据'}.xlsx"
    return StreamingResponse(buf, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                             headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(fn)})
