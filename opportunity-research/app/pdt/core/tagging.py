"""打标（F18）：规则打标 + 看图打元素 + 确认队列。

- 规则打标：第二轮打标技能 v12.2（tagging_rules.py，逐字移植）读标题、SKU、商品尺寸、五点描述，得到 D1–D9；
  再按品类配置 tag_rules 归类成分析标签（尺寸段、装、形态、台面材质、台盆材质、元素、主色、柜体材质），每个标签带置信度（AC-F18-01）。
  置信度来自字段证据状态（tag_rules.confidence），低于 low_conf_threshold 的进入确认队列；“元素”一律进入确认队列（AC-F18-03）。
- 看图打元素：规则判断不了元素的商品，由所选大模型看主图给出元素和置信度（AC-F18-02，任务 vision_tag 走费用闸门）；
  未配置大模型时这些商品直接留在确认队列（值为空，候选为元素词表）。
- 同图一组：主图相同（去掉尺寸后缀后的图片地址相同）的商品分一组，一次确认应用到整组，组内可单改（AC-F18-04）。
- 确认后状态 confirmed，分析一律用确认值（panel.raw_frame）（AC-F18-05）。“看不出 / 不是本品类”→ Product.excluded（AC-F18-06），可恢复。
- 其他渠道商品同一套规则、同一队列，带渠道（AC-F18-07）。
"""
import hashlib
import json
import re

from sqlalchemy import func, select

from .. import catconfig, costgate, services
from ..db import session
from ..models import Product, Snapshot, Batch, Tag, now
from . import families as fm
from . import tagging_rules as T

TAG_ORDER = ['尺寸段', '装', '形态', '台面材质', '台盆材质', '元素', '主色', '柜体材质']

# 打标规则默认值在品类配置 tag_rules（catconfig.DEFAULT，分析组追加）；规则正则在 tagging_rules.py（v12.2 原文）。
DEFAULT_TAG_RULES = catconfig.DEFAULT['tag_rules']

CANDIDATES = {
    '尺寸段': ['18″', '24″', '30″', '36″', '42″', '48″', '60″', '72″+'], '装': ['拆装', '整装'], '形态': ['落地式', '悬浮式', '柱状盆', '转角式', '两用'],
    '台面材质': ['陶瓷', '树脂', '木板', '岗石', '石英石', '岩板', '卡拉拉大理石', 'Cultured Marble', '玻璃', '不锈钢', '不适用（不含台面）'],
    '台盆材质': ['陶瓷盆', '树脂盆', '玻璃盆', '岗石盆', 'Cultured Marble盆', '不锈钢盆', '不适用（不含盆）'],
    '主色': ['白', '黑', '灰', '原木', '深木', '蓝', '绿', '其他'], '柜体材质': ['MDF', '实木框架', '实木', '含胶合板', '含刨花板', '其他'],
}


def rules_cfg():
    cfg = catconfig.current()[1]
    r = dict(DEFAULT_TAG_RULES)
    r.update(cfg.get('tag_rules') or {})
    return r, float(cfg.get('low_conf_threshold', 0.75)), catconfig.current()[0]


def img_key(url: str) -> str:
    """主图指纹：去掉亚马逊图片尺寸后缀（._AC_US600_.）后取摘要；相同即同一张主图。"""
    if not url:
        return ''
    u = re.sub(r'\._[^/]*?_\.', '.', url.split('?')[0].strip())
    u = re.sub(r'^https?://[^/]+', '', u)
    return hashlib.md5(u.encode()).hexdigest()[:12]


def _band(w, bands):
    try:
        w = float(w)
    except (TypeError, ValueError):
        return ''
    for c, lo, hi in bands:
        if lo <= w < hi:
            return f'{c}″'
    return '72″+' if w >= 66 else ''


def rule_tag(text: dict, rules: dict | None = None) -> dict:
    """一个商品的规则打标。text = {item_id, title, sku, dimension, features, price}。返回 {标签: (值, 置信度, 证据状态, 候选)}。"""
    rules = rules or DEFAULT_TAG_RULES
    row = {'子ASIN': text.get('item_id') or 'X', '目标月份': '', 'SKU属性': text.get('sku') or '', '商品标题': text.get('title') or '',
           '商品尺寸': text.get('dimension') or '', '五点描述': text.get('features') or None,
           '五点来源': '子体详情' if text.get('features') else None, '五点来源ASIN': text.get('item_id'), '核验父ASIN': None, '商品价格': text.get('price')}
    tags, ev, _conf = T.Tagger(row, {}, None, None).run()
    conf_map = rules.get('confidence') or DEFAULT_TAG_RULES['confidence']

    def cf(h, value):
        if value in ('', None):
            return 0.0
        st = (ev.get(h) or {}).get('status', 'missing')
        return float(conf_map.get(st, 0.6))

    def norm(v):
        return '' if v is None or str(v) in fm.RAW_UNK else str(v)
    H = T.HEADERS
    out = {}
    w = tags.get(H[9])
    size = _band(w, rules.get('size_bands') or DEFAULT_TAG_RULES['size_bands'])
    out['尺寸段'] = (size, cf(H[9], size), (ev.get(H[9]) or {}).get('status', 'missing'))
    z = '整装' if tags.get(H[1]) == '整装' else '拆装'
    out['装'] = (z, cf(H[1], z), (ev.get(H[1]) or {}).get('status', 'missing'))
    f = norm(tags.get(H[0])) or '落地式'
    out['形态'] = (f, cf(H[0], f), (ev.get(H[0]) or {}).get('status', 'missing'))
    t = norm(tags.get(H[7]))
    out['台面材质'] = (t, cf(H[7], t), (ev.get(H[7]) or {}).get('status', 'missing'))
    s = norm(tags.get(H[8]))
    out['台盆材质'] = (s, cf(H[8], s), (ev.get(H[8]) or {}).get('status', 'missing'))
    em = rules.get('element_map') or DEFAULT_TAG_RULES['element_map']
    els = [em.get(x.strip()) for x in str(tags.get(H[4]) or '').split('；') if em.get(x.strip())]
    els = list(dict.fromkeys(els))
    e = '|'.join(els)
    out['元素'] = (e, 0.7 if e else 0.0, 'text_clue' if e else 'need_image')
    cmap = rules.get('color_map') or fm.COLOR
    c0 = tags.get(H[5])
    col = '未知' if c0 is None or str(c0) in fm.RAW_UNK else cmap.get(str(c0), '其他')
    col = '' if col == '未知' else col
    out['主色'] = (col, cf(H[5], col), (ev.get(H[5]) or {}).get('status', 'missing'))
    cb = fm.cab(tags.get(H[6]))
    cb = '' if cb == '未知' else cb
    out['柜体材质'] = (cb, cf(H[6], cb), (ev.get(H[6]) or {}).get('status', 'missing'))
    return out


def _texts(s, channel, items):
    """商品文本：标题取 Product；SKU、尺寸、五点取最近一次快照 raw（导入时保存）。"""
    prods = {p.item_id: p for p in s.scalars(select(Product).where(Product.channel == channel, Product.item_id.in_(items)))}
    last = {}
    for sn in s.scalars(select(Snapshot).where(Snapshot.channel == channel, Snapshot.item_id.in_(items)).order_by(Snapshot.id)):
        last[sn.item_id] = sn
    out = {}
    for i in items:
        p = prods.get(i)
        r = (last[i].raw or {}) if i in last else {}
        out[i] = dict(item_id=i, title=(p.title if p else '') or r.get('title', ''), sku=r.get('sku', ''), dimension=r.get('dimension', ''),
                      features=r.get('features', ''), price=last[i].price if i in last else None, image=(p.image_url if p else ''))
    return out


def tag_products(channel: str, items: list[str], month: str = '') -> dict:
    """规则打标并写 Tag（不覆盖已确认的标签）。返回统计。"""
    rules, thr, ver = rules_cfg()
    stat = dict(items=0, tags=0, queued=0, need_image=0)
    if not items:
        return stat
    with session() as s:
        tx = _texts(s, channel, items)
        existing = {(t.item_id, t.tag): t for t in s.scalars(select(Tag).where(Tag.channel == channel, Tag.item_id.in_(items)))}
        for i in items:
            res = rule_tag(tx[i], rules)
            grp = img_key(tx[i]['image'])
            stat['items'] += 1
            for tg in TAG_ORDER:
                v, c, st = res[tg]
                old = existing.get((i, tg))
                if old is not None and old.status == 'confirmed':
                    continue
                if old is not None and old.source == 'vision' and tg == '元素' and old.value:
                    continue  # 已有看图结果，不用规则覆盖
                queued = tg == '元素' or c < thr
                cands = [v] if v else []
                pool = rules.get('element_vocab') if tg == '元素' else CANDIDATES.get(tg, [])
                cands += [x for x in (pool or []) if x not in cands]
                cand = [dict(value=x, confidence=(c if x == v else None)) for x in cands[:12]]
                if old is None:
                    old = Tag(channel=channel, item_id=i, tag=tg)
                    s.add(old)
                old.value, old.auto_value, old.confidence, old.source = v, v, c, 'rule'
                old.status = 'queued' if queued else 'auto'
                old.candidates, old.img_group, old.month, old.config_version = cand, grp, month or old.month or '', ver
                stat['tags'] += 1
                stat['queued'] += int(queued)
                stat['need_image'] += int(tg == '元素' and not v)
    return stat


def untagged_items(channel: str | None = None) -> dict:
    """已有快照但还没有任何标签的商品（按渠道）。"""
    with session() as s:
        qp = select(Product.channel, Product.item_id)
        qt = select(Tag.channel, Tag.item_id).distinct()
        if channel:
            qp, qt = qp.where(Product.channel == channel), qt.where(Tag.channel == channel)
        have = set(s.execute(qt).all())
        out = {}
        for ch, i in s.execute(qp):
            if (ch, i) not in have:
                out.setdefault(ch, []).append(i)
        return out


def run_rules(channel: str | None = None, month: str = '') -> dict:
    """API-F18-01 的免费部分：给所有还没打标的商品规则打标。"""
    tot = {}
    for ch, items in untagged_items(channel).items():
        tot[ch] = tag_products(ch, items, month)
    return tot


# ---------------- 看图打元素（大模型，走费用闸门） ----------------
def vision_targets(channel: str | None = None):
    with session() as s:
        q = (select(Tag.channel, Tag.item_id, Product.title, Product.image_url).join(Product, (Product.channel == Tag.channel) & (Product.item_id == Tag.item_id))
             .where(Tag.tag == '元素', Tag.status == 'queued', Tag.value == '', Product.excluded.is_(False)))
        if channel:
            q = q.where(Tag.channel == channel)
        return [dict(channel=c, item_id=i, title=t or '', image=u or '') for c, i, t, u in s.execute(q)]


def _vision_est(params):
    rules, _, _ = rules_cfg()
    services.client('llm')  # 未连接时抛 NotConnected，估算即失败并在弹窗里说明
    n = len(vision_targets(params.get('channel') or None))
    lo, hi = rules.get('vision_usd_per_call') or [0.004, 0.012]
    return dict(service='llm', calls=n, usd_lo=round(n * lo, 2), usd_hi=round(n * hi, 2), minutes=round(max(1, n * 0.1), 1),
                note=f'{n} 个规则判断不了元素的商品，每个看 1 张主图')


def parse_vision(text: str, vocab: list[str]):
    m = re.search(r'\{.*\}', text or '', re.S)
    if not m:
        return None
    try:
        j = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    el = str(j.get('element') or '').strip()
    try:
        c = float(j.get('confidence') or 0)
    except (TypeError, ValueError):
        c = 0.0
    alts = []
    for a in j.get('alternatives') or []:
        try:
            alts.append(dict(value=str(a.get('element')), confidence=float(a.get('confidence') or 0)))
        except (TypeError, ValueError, AttributeError):
            continue
    if el == '看不出':
        el = ''
    return el, max(0.0, min(1.0, c)), alts


def _vision_run(ctx):
    rules, _, _ = rules_cfg()
    vocab = rules.get('element_vocab') or DEFAULT_TAG_RULES['element_vocab']
    llm = services.client('llm')
    todo = vision_targets(ctx.params.get('channel') or None)
    lo, hi = rules.get('vision_usd_per_call') or [0.004, 0.012]
    done = 0
    for t in todo:
        key = f"{t['channel']}:{t['item_id']}"
        if ctx.shard_done(key):
            continue
        ctx.allow('llm', amount=hi, qty=1)
        prompt = rules.get('vision_prompt', DEFAULT_TAG_RULES['vision_prompt']).format(vocab='、'.join(vocab), title=t['title'][:200])
        text, usd = llm.complete(prompt, images=[t['image']] if t['image'] else None)
        ctx.charge('llm', qty=1, amount=float(usd or 0), task='看图打元素')
        got = parse_vision(text, vocab)
        with session() as s:
            tg = s.scalar(select(Tag).where(Tag.channel == t['channel'], Tag.item_id == t['item_id'], Tag.tag == '元素'))
            if tg is not None and tg.status != 'confirmed' and got:
                el, c, alts = got
                tg.value, tg.auto_value, tg.confidence, tg.source = el, el, c, 'vision'
                cands = [dict(value=el, confidence=c)] if el else []
                cands += [a for a in alts if a['value'] and a['value'] != el]
                cands += [dict(value=x, confidence=None) for x in vocab if x not in {c_['value'] for c_ in cands}]
                tg.candidates = cands[:12]
                tg.status = 'queued'  # 元素一律人工确认（AC-F18-03）
        ctx.mark_shard(key)
        done += 1
        ctx.progress(done=done, total=len(todo))


costgate.register('vision_tag', '看图打元素', _vision_est, _vision_run)


# ---------------- 确认队列 ----------------
def queue(channel: str | None = None, reason: str | None = None, status: str = 'queued'):
    """确认队列，按（主图, 标签）分组。返回组列表，组内含商品行。"""
    with session() as s:
        q = (select(Tag, Product).join(Product, (Product.channel == Tag.channel) & (Product.item_id == Tag.item_id))
             .where(Product.excluded.is_(False)))
        if status == 'queued':
            q = q.where(Tag.status == 'queued')
        else:
            q = q.where(Tag.status == 'confirmed', Tag.confirmed_by.is_not(None))
        if channel:
            q = q.where(Tag.channel == channel)
        if reason == 'element':
            q = q.where(Tag.tag == '元素')
        elif reason == 'low':
            q = q.where(Tag.tag != '元素')
        rows = list(s.execute(q))
        items = list({(t.channel, t.item_id) for t, _ in rows})
        other = {}
        if items:
            for t in s.scalars(select(Tag).where(Tag.item_id.in_([i for _, i in items]))):
                other.setdefault((t.channel, t.item_id), {})[t.tag] = t.value
        groups = {}
        for t, p in rows:
            gk = (t.img_group or f'{t.channel}:{t.item_id}', t.tag)
            g = groups.setdefault(gk, dict(key=f'{gk[0]}|{gk[1]}', img_group=gk[0], tag=t.tag, image=p.image_url, items=[], candidates=[], channels=set(),
                                           source=t.source, reason='元素' if t.tag == '元素' else '低置信度'))
            o = other.get((t.channel, t.item_id), {})
            g['items'].append(dict(tag_id=t.id, channel=t.channel, item_id=t.item_id, title=p.title, value=t.value, confidence=t.confidence,
                                   status=t.status, link=p.link, image=p.image_url, confirm_mode=t.confirm_mode,
                                   others=' · '.join(x for x in [o.get('尺寸段'), o.get('装'), o.get('形态'), fm.top_type(o.get('台面材质'), o.get('台盆材质')) if o else '', o.get('主色')] if x and x != '未知')))
            g['channels'].add(t.channel)
            for c in (t.candidates or []):
                if c.get('value') and c['value'] not in [x['value'] for x in g['candidates']]:
                    g['candidates'].append(dict(value=c['value'], confidence=c.get('confidence')))
        out = sorted(groups.values(), key=lambda g: (-len(g['items']), g['tag'], g['key']))
        for g in out:
            g['channels'] = sorted(g['channels'])
            if not g['candidates']:
                g['candidates'] = [dict(value=x, confidence=None) for x in CANDIDATES.get(g['tag'], [])]
        return out


def counts():
    with session() as s:
        base = (select(Tag.channel, Tag.tag, func.count()).join(Product, (Product.channel == Tag.channel) & (Product.item_id == Tag.item_id))
                .where(Product.excluded.is_(False), Tag.status == 'queued').group_by(Tag.channel, Tag.tag))
        q = {}
        for ch, tg, n in s.execute(base):
            q.setdefault(ch, {})[tg] = n
        confirmed = s.scalar(select(func.count()).select_from(Tag).where(Tag.status == 'confirmed', Tag.confirmed_by.is_not(None))) or 0
        excluded = s.scalar(select(func.count()).select_from(Product).where(Product.excluded.is_(True))) or 0
    total = sum(sum(v.values()) for v in q.values())
    return dict(by_channel={ch: sum(v.values()) for ch, v in q.items()}, element=sum(v.get('元素', 0) for v in q.values()),
                low=total - sum(v.get('元素', 0) for v in q.values()), total=total, confirmed=confirmed, excluded=excluded)


def confirm_group(img_group: str, tag: str, value: str, user_id: int, channel: str | None = None) -> int:
    """整组确认：同一主图、同一标签的待确认条目全部设为该值（AC-F18-04）。"""
    n = 0
    with session() as s:
        q = select(Tag).where(Tag.img_group == img_group, Tag.tag == tag, Tag.status == 'queued')
        if channel:
            q = q.where(Tag.channel == channel)
        for t in s.scalars(q):
            p = s.scalar(select(Product).where(Product.channel == t.channel, Product.item_id == t.item_id))
            if p is not None and p.excluded:
                continue
            t.value, t.status, t.confirm_mode, t.confirmed_by, t.confirmed_at = value, 'confirmed', 'group', user_id, now()
            n += 1
    return n


def confirm_item(tag_id: int, value: str, user_id: int) -> bool:
    """单条确认或改值（组内单改）。"""
    with session() as s:
        t = s.get(Tag, tag_id)
        if t is None:
            return False
        t.value, t.status, t.confirm_mode, t.confirmed_by, t.confirmed_at = value, 'confirmed', 'single', user_id, now()
        return True


def set_excluded(channel: str, item_id: str, excluded: bool, user_id: int) -> bool:
    """看不出 / 不是本品类（AC-F18-06），或恢复。"""
    with session() as s:
        p = s.scalar(select(Product).where(Product.channel == channel, Product.item_id == item_id))
        if p is None:
            return False
        p.excluded = excluded
        p.excluded_by = user_id if excluded else None
        p.excluded_at = now()
        return True


def pending_for_month(channel: str = 'amazon', month: str | None = None) -> int:
    """重算前置：当月（最新已并入月）商品还有多少条待确认标签。"""
    with session() as s:
        if month is None:
            month = s.scalar(select(func.max(Batch.month)).where(Batch.channel == channel, Batch.status == 'merged'))
        if not month:
            return 0
        items = select(Snapshot.item_id).join(Batch, Batch.id == Snapshot.batch_id).where(Batch.status == 'merged', Batch.channel == channel, Batch.month == month)
        return s.scalar(select(func.count()).select_from(Tag).join(Product, (Product.channel == Tag.channel) & (Product.item_id == Tag.item_id))
                        .where(Tag.channel == channel, Tag.status == 'queued', Product.excluded.is_(False), Tag.item_id.in_(items))) or 0
