"""打标确认（PAGE-F18-01，API-F18-01 / 02）。"""
from fastapi import APIRouter, Form, Request
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
            month = s.scalar(select(func.max(Batch.month)).where(Batch.channel == ch, Batch.status.in_(['merged', 'ok', 'anomaly', 'checking'])))
            if not month:
                continue
            new = s.scalar(select(func.count(func.distinct(Tag.item_id))).where(Tag.channel == ch, Tag.month == month)) or 0
            vis = s.scalar(select(func.count()).select_from(Tag).where(Tag.channel == ch, Tag.month == month, Tag.tag == '元素', Tag.source == 'vision')) or 0
            need = s.scalar(select(func.count()).select_from(Tag).where(Tag.channel == ch, Tag.month == month, Tag.tag == '元素', Tag.source == 'rule', Tag.value == '')) or 0
            pend = s.scalar(select(func.count()).select_from(Tag).join(Product, (Product.channel == Tag.channel) & (Product.item_id == Tag.item_id))
                            .where(Tag.channel == ch, Tag.status == 'queued', Product.excluded.is_(False))) or 0
            out.append(dict(channel=ch, name=CHANNEL_NAMES[ch], month=month, new=new, vision=vis, need_image=need, pending=pend))
    return out


@router.get('/tagging')
def page(request: Request, channel: str = '', reason: str = '', tab: str = 'pending', user=operator_only):
    ch = channel if channel in CHANNEL_NAMES else None
    rs = reason if reason in ('element', 'low') else None
    cnt = tagging.counts()
    groups = tagging.queue(ch, rs, 'queued' if tab == 'pending' else 'confirmed') if tab in ('pending', 'done') else []
    excluded = []
    if tab == 'out':
        with session() as s:
            excluded = [dict(channel=p.channel, item_id=p.item_id, title=p.title, image=p.image_url, at=p.excluded_at)
                        for p in s.scalars(select(Product).where(Product.excluded.is_(True)).order_by(Product.excluded_at.desc()))]
    rules, thr, ver = tagging.rules_cfg()
    return render(request, 'tagging.html', 'PAGE-F18-01', '打标确认', groups=groups[:60], n_groups=len(groups), cnt=cnt, prog=_progress(), channel=ch or 'all',
                  reason=rs or 'all', tab=tab, excluded=excluded, thr=thr, ver=ver, rule_version=rules.get('rule_version', ''),
                  llm=services.connected('llm'), vision_todo=len(tagging.vision_targets()), untagged=sum(len(v) for v in tagging.untagged_items().values()))


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
