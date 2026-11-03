"""打标确认（PAGE-F18-01，API-F18-01 / 02）。"""
import io
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from .. import services
from ..auth import operator_only
from ..config import CHANNEL_NAMES
from ..db import session
from ..models import Batch, Product, Tag
from ..core import panel, tagging
from .ui import redirect, render

router = APIRouter()


def _progress():
    out = []
    with session() as s:
        for ch in CHANNEL_NAMES:
            month = s.scalar(select(func.max(Batch.month)).where(Batch.channel == ch, Batch.status.in_(['merged', 'ok', 'anomaly', 'checking', 'suspect_month'])))
            if not month:
                continue
            new = s.scalar(select(func.count(func.distinct(Tag.item_id))).where(Tag.channel == ch, Tag.month == month)) or 0
            vis = s.scalar(select(func.count()).select_from(Tag).where(Tag.channel == ch, Tag.month == month, Tag.tag == '元素', Tag.source == 'vision')) or 0
            need = s.scalar(select(func.count()).select_from(Tag).where(Tag.channel == ch, Tag.month == month, Tag.tag == '元素', Tag.source == 'rule', Tag.value == '')) or 0
            pend = s.scalar(select(func.count()).select_from(Tag).join(Product, (Product.channel == Tag.channel) & (Product.item_id == Tag.item_id))
                            .where(Tag.channel == ch, Tag.status == 'queued', Product.excluded.is_(False))) or 0
            # 分框标签来源（以“装”为代表）：规格 / 标题 / 装未知（AC-F18-08）
            fs = dict(s.execute(select(Tag.source, func.count()).where(Tag.channel == ch, Tag.month == month, Tag.tag == '装', Tag.value != '')
                                .group_by(Tag.source)).all())
            unk = s.scalar(select(func.count()).select_from(Tag).where(Tag.channel == ch, Tag.month == month, Tag.tag == '装', Tag.value == '')) or 0
            queued = s.scalar(select(func.count()).select_from(Tag).where(Tag.channel == ch, Tag.month == month, Tag.status == 'queued')) or 0
            out.append(dict(channel=ch, name=CHANNEL_NAMES[ch], month=month, new=new, vision=vis, need_image=need, pending=pend, queued=queued,
                            frame_src=dict(spec=fs.get('spec', 0), rule=fs.get('rule', 0) + fs.get('manual', 0) + fs.get('vision', 0), unknown=unk)))
    return out


PER_PAGE = 60  # 每页组数


def _excluded():
    with session() as s:
        return [dict(channel=p.channel, item_id=p.item_id, title=p.title, image=p.image_url, at=p.excluded_at, link=p.link)
                for p in s.scalars(select(Product).where(Product.excluded.is_(True)).order_by(Product.excluded_at.desc()))]


@router.get('/tagging')
def page(request: Request, channel: str = '', reason: str = '', tab: str = 'pending', page: int = 1, user=operator_only):
    ch = channel if channel in CHANNEL_NAMES else None
    rs = reason if reason in ('element', 'low', 'assembly') else None
    cnt = tagging.counts()
    fc = tagging.counts('confirmed') if tab == 'done' else cnt  # 筛选上的数量随当前页签
    groups = tagging.queue(ch, rs, 'queued' if tab == 'pending' else 'confirmed') if tab in ('pending', 'done') else []
    pages = max(1, -(-len(groups) // PER_PAGE))
    page = min(max(1, page), pages)
    excluded = _excluded() if tab == 'out' else []
    rules, thr, ver = tagging.rules_cfg()
    return render(request, 'tagging.html', 'PAGE-F18-01', '打标确认', groups=groups[(page - 1) * PER_PAGE:page * PER_PAGE], n_groups=len(groups),
                  n_items=sum(len(g['items']) for g in groups), page=page, pages=pages, per_page=PER_PAGE, cnt=cnt, fc=fc, prog=_progress(), channel=ch or 'all',
                  reason=rs or 'all', tab=tab, excluded=excluded, thr=thr, ver=ver, rule_version=rules.get('rule_version', ''),
                  llm=services.connected('llm'), vision_todo=len(tagging.vision_targets()), untagged=sum(len(v) for v in tagging.untagged_items().values()),
                  tag_src=_tag_sources())


def _tag_sources():
    """其他渠道历史回补的标签来源构成（PAGE-F18-01 v8 面板，数据来自最近一次历史重建）。"""
    from ..core import backfill
    out = []
    for ch in ('homedepot', 'lowes', 'wayfair'):
        rb = backfill.last_rebuild(ch)
        if rb and rb['stats'].get('tags'):
            out.append(dict(channel=ch, name=CHANNEL_NAMES[ch], stats=rb['stats']))
    return out


@router.get('/tagging/export')
def export(channel: str = '', reason: str = '', tab: str = 'pending', user=operator_only):
    """导出当前筛选下的队列明细（待确认 / 已确认按渠道与进队原因筛选；“不是本品类”导出被排除的商品）。"""
    from openpyxl import Workbook
    ch = channel if channel in CHANNEL_NAMES else None
    rs = reason if reason in ('element', 'low', 'assembly') else None
    wb = Workbook()
    ws = wb.active
    if tab == 'out':
        ws.title = '不是本品类'
        ws.append(['渠道', '商品ID', '标题', '链接', '标记时间'])
        for p in _excluded():
            ws.append([CHANNEL_NAMES.get(p['channel'], p['channel']), p['item_id'], p['title'], p['link'], p['at'].strftime('%Y-%m-%d %H:%M') if p['at'] else ''])
    else:
        ws.title = '待确认' if tab == 'pending' else '已确认'
        ws.append(['同图组', '标签', '进队原因', '来源', '渠道', '商品ID', '标题', '其他标签（自动）', '当前值', '置信度', '状态', '链接'])
        src = tagging.SRC_LABEL
        for g in tagging.queue(ch, rs, 'queued' if tab == 'pending' else 'confirmed'):
            for it in g['items']:
                st = ('已确认' + (' · 单改' if it['confirm_mode'] == 'single' else '')) if it['status'] == 'confirmed' else '待确认'
                ws.append([g['img_group'], g['tag'], g['reason'], src.get(g['source'], g['source']), CHANNEL_NAMES.get(it['channel'], it['channel']),
                           it['item_id'], it['title'], it['others'], it['value'], it['confidence'], st, it['link']])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fn = f"打标确认_{ws.title}{'_' + CHANNEL_NAMES[ch] if ch else ''}{'_' + {'element': '元素', 'low': '低置信度', 'assembly': '装未知'}[rs] if rs else ''}.xlsx"
    return StreamingResponse(buf, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                             headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(fn)})


@router.get('/tagging/queue')
def queue_json(channel: str = '', reason: str = '', user=operator_only):
    return tagging.queue(channel or None, reason or None)


@router.post('/tagging/run')
def run(request: Request, user=operator_only):
    """API-F18-01：规则打标（免费）。看图打元素由页面按钮走费用闸门（vision_tag）。"""
    st = tagging.run_rules()
    n = sum(v['items'] for v in st.values())
    q = sum(v['queued'] for v in st.values())
    img = sum(v['need_image'] for v in st.values())
    panel.clear_cache()
    msg = f'已规则打标 {n} 个商品，{q} 条进入确认队列' + (f'；{img} 个商品规则判断不了元素' + ('，可点“看图打元素”' if services.connected('llm') else '，大模型未配置，已直接进确认队列') if img else '')
    return redirect('/tagging', msg if n else '没有需要打标的新商品')


@router.post('/tagging/groups/confirm')
def confirm_group(img_group: str = Form(...), tag: str = Form(...), value: str = Form(''), other: str = Form(''), back: str = Form('/tagging'), user=operator_only):
    v = (other.strip() if value == 'other' else value).strip()
    if not v:
        return redirect(back, '请选择一个值', 'error')
    n = tagging.confirm_group(img_group, tag, v, user.id)
    panel.clear_cache()
    return redirect(back, f'已把整组 {n} 条“{tag}”确认为 {v}')


@router.post('/tagging/items/{tag_id}')
def item(tag_id: int, action: str = Form('confirm'), value: str = Form(''), channel: str = Form(''), item_id: str = Form(''),
         back: str = Form('/tagging'), user=operator_only):
    """组内单改 / 单条确认；看不出 / 不是本品类；恢复。"""
    if action in ('exclude', 'restore'):
        ok = tagging.set_excluded(channel, item_id, action == 'exclude', user.id)
        panel.clear_cache()
        return redirect(back, (f'{item_id} 已标为“看不出 / 不是本品类”，不进入任何分析' if action == 'exclude' else f'{item_id} 已恢复') if ok else '商品不存在',
                        'ok' if ok else 'error')
    if not value.strip():
        return redirect(back, '请选择一个值', 'error')
    ok = tagging.confirm_item(tag_id, value.strip(), user.id)
    panel.clear_cache()
    return redirect(back, '已单独确认该条' if ok else '标签不存在', 'ok' if ok else 'error')


@router.post('/tagging/groups/exclude')
def exclude_group(img_group: str = Form(...), back: str = Form('/tagging'), user=operator_only):
    """整组标为“看不出 / 不是本品类”。"""
    with session() as s:
        items = {(t.channel, t.item_id) for t in s.scalars(select(Tag).where(Tag.img_group == img_group, Tag.status == 'queued'))}
    for ch, i in items:
        tagging.set_excluded(ch, i, True, user.id)
    panel.clear_cache()
    return redirect(back, f'{len(items)} 个商品已标为“看不出 / 不是本品类”')
