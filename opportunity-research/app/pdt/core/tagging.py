"""打标（F18）：规则打标 + 看图打元素 + 确认队列。

- 规则打标：第二轮打标技能 v12.2（tagging_rules.py，逐字移植）读标题、SKU、商品尺寸、五点描述，得到 D1–D9；
  再按品类配置 tag_rules 归类成分析标签（尺寸段、装、形态、台面材质、台盆材质、元素、主色、柜体材质），每个标签带置信度（AC-F18-01）。
  置信度来自字段证据状态（tag_rules.confidence），低于 low_conf_threshold 的进入确认队列；“元素”一律进入确认队列（AC-F18-03）。
- 看图打元素：规则判断不了元素的商品，由所选大模型看主图给出元素和置信度（AC-F18-02，任务 vision_tag 走费用闸门）；
  未配置大模型时这些商品直接留在确认队列（值为空，候选为元素词表）。
- 同图一组：主图相同（去掉尺寸后缀后的图片地址相同）的商品分一组，一次确认应用到整组，组内可单改（AC-F18-04）。
- 确认后状态 confirmed，分析一律用确认值（panel.raw_frame）（AC-F18-05）。“看不出 / 不是本品类”→ Product.excluded（AC-F18-06），可恢复。
- 其他渠道商品同一套规则、同一队列，带渠道（AC-F18-07）。
- 其他渠道规格优先（AC-F18-08）：Home Depot / Lowe's / Wayfair 商品有商品页规格（channel_page_spec 表）时，尺寸段、装、形态、台面材质、
  柜体材质、主色优先按规格字段打，Tag.source 记 spec（页面显示“规格”）；规格缺失才用标题规则（source = rule，页面显示“标题”）。
  “装”没有依据时记空值（未知）进确认队列，候选不预选，不默认拆装；Amazon 仍按原规则（含业务默认）。
"""
import hashlib
import json
import re

from sqlalchemy import func, select

from .. import catconfig, costgate, services
from ..db import session
from ..models import Product, Snapshot, Batch, Tag, now
from . import families as fm
from . import openshelf
from . import tagging_rules as T

TAG_ORDER = ['尺寸段', '装', '形态', '台面材质', '台盆材质', '元素', '主色', '柜体材质']

# 打标规则默认值在品类配置 tag_rules（catconfig.DEFAULT，分析组追加）；规则正则在 tagging_rules.py（v12.2 原文）。
DEFAULT_TAG_RULES = catconfig.DEFAULT['tag_rules']
# 开放式置信度：写明开放层板 / console 0.95；只有泛指词（open storage / open space）0.6，低于阈值进确认队列（AC-F18-10）
OPEN_CONF = {openshelf.STRONG: 0.95, openshelf.WEAK: 0.6, None: 0.95}

CANDIDATES = {
    '尺寸段': ['18″', '24″', '28″', '30″', '36″', '42″', '48″', '60″', '72″+'], '装': ['拆装', '整装'], '形态': ['落地式', '悬浮式', '开放式', '柱状盆', '转角式', '两用'],
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


def group_key(channel: str, image: str = '', series: str = '', brand: str = '', title: str = '') -> str:
    """确认队列分组键：有主图按主图指纹；没有主图（Home Depot / Lowe's / Wayfair 的评论追踪导出不带图）按同系列，
    没有系列按“同品牌 + 同标题”；都没有时返回空串（队列里退回一商品一组）。前缀 s / t 区分系列与标题，不会与 12 位图指纹混淆。"""
    if image:
        return img_key(image)
    if series:
        return 's' + hashlib.md5(f'{channel}|{series}'.encode()).hexdigest()[:11]
    t = re.sub(r'\s+', ' ', str(title or '')).strip().lower()
    if t:
        return 't' + hashlib.md5(f'{channel}|{str(brand or "").strip().lower()}|{t}'.encode()).hexdigest()[:11]
    return ''


def fill_groups() -> int:
    """给还没有分组键的标签补上 group_key（启动时调用；之前无图商品一商品一组）。返回补上的条数。"""
    n = 0
    with session() as s:
        rows = s.execute(select(Tag, Product).join(Product, (Product.channel == Tag.channel) & (Product.item_id == Tag.item_id))
                         .where(Tag.img_group == '')).all()
        for tg, p in rows:
            k = group_key(p.channel, p.image_url or '', p.series or '', p.brand or '', p.title or '')
            if k:
                tg.img_group = k
                n += 1
    return n


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
    f2, k = openshelf.form_of(f, text.get('title'), text.get('sku'))  # 开放式单独成形态（AC-F18-10）
    if f2 != f or k:
        out['形态'] = (f2, OPEN_CONF[k], 'text_supported' if k == openshelf.STRONG else 'business_inference')
    else:
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


SRC_LABEL = {'spec': '规格', 'rule': '标题', 'vision': '看图', 'manual': '人工'}  # 标签来源（页面显示）
SPEC_KEYS = {  # 商品页规格字段（三个渠道的写法，按键名正则匹配）
    'width': r'^(product|overall|cabinet|vanity|assembled)?\s*width',
    'assembled': r'^assembled$|assembly level|level of assembly',
    'assembly_required': r'^assembly required',
    'form': r'vanity type|mount(ing)? type|installation type|^vanity style$',
    'color': r'^(cabinet )?colou?r family$|^colou?r/finish family$',
}
SPEC_COLOR = {'white': '白', 'black': '黑', 'gray': '灰', 'grey': '灰', 'blue': '蓝', 'green': '绿'}  # 规格颜色族 → 主色（只收不含糊的；棕色等仍按规则区分原木 / 深木）


def specs_from_text(text: str) -> dict:
    """追踪器导出的“规格参数”（每行 “键: 值”）→ dict。"""
    out = {}
    for line in str(text or '').splitlines():
        k, sep, v = line.partition(':')
        if sep and k.strip() and v.strip():
            out[k.strip()] = v.strip()
    return out


def _spec(specs: dict, key: str) -> str:
    pat = SPEC_KEYS[key]
    for k, v in (specs or {}).items():
        if re.search(pat, str(k).strip(), re.I) and str(v or '').strip():
            return str(v).strip()
    return ''


def _spec_width(specs: dict):
    m = re.match(r'\s*(\d+(?:\.\d+)?)', _spec(specs, 'width'))
    return float(m.group(1)) if m else None


def spec_tag(text: dict, specs: dict | None = None, rules: dict | None = None, default_form: bool = True) -> dict:
    """其他渠道：规格优先打标（AC-F18-08）。返回 {标签: (值, 置信度, 证据状态, 来源 spec / rule)}；值为空 = 未知。
    做法与 HD 回测小试（solution-v2/trial/小平台_HD回测小试.py tag_variant）相同：v12.2 规则读标题 + 商品页规格（关掉业务默认值），
    规格的“Assembled / Assembly Required / Assembly Level”“Vanity Type / Mount Type”字段与标题 “(Assembled)” 优先；装判断不了记未知。"""
    rules = rules or DEFAULT_TAG_RULES
    specs = specs or {}
    row = {'子ASIN': text.get('item_id') or 'X', '商品标题': text.get('title') or '', 'SKU属性': '', '商品尺寸': ''}
    ex = [{'attributes': ' | '.join(f'{k}:{v}' for k, v in specs.items() if v), 'features': ' '.join(text.get('highlights') or [])}] if specs else []
    tags, ev, _c = T.Tagger(row, {}, export_rows=ex, accessory_default=False).run()
    conf_map = rules.get('confidence') or DEFAULT_TAG_RULES['confidence']
    H = T.HEADERS

    def st(h):
        return (ev.get(h) or {}).get('status', 'missing')

    def src(h):
        sel = (ev.get(h) or {}).get('selected') or []
        return 'spec' if any(str(e.get('sourceField', '')).startswith('卖家精灵导出') for e in sel) else 'rule'

    def cf(h, value):
        return 0.0 if value in ('', None) else float(conf_map.get(st(h), 0.6))

    def norm(v):
        return '' if v is None or str(v) in fm.RAW_UNK else str(v)
    spec_c = float(conf_map.get('text_supported', 0.95))
    out = {}
    # 尺寸段：规则读出的宽度（与小试同），读不出时用规格宽度；规格里有宽度字段即记“规格”
    w, sw = tags.get(H[9]), _spec_width(specs)
    if w is None:
        w = sw
    size = _band(w, rules.get('size_bands') or DEFAULT_TAG_RULES['size_bands'])
    out['尺寸段'] = (size, spec_c if size and sw is not None else cf(H[9], size), 'text_supported' if sw is not None else st(H[9]), 'spec' if sw is not None else src(H[9]))
    # 装：规格 Assembled / Assembly Level > 标题 (Assembled) / RTA > 规则（含规格 Assembly Required）> 未知（不默认拆装）
    asm = _spec(specs, 'assembled').lower()
    t = (text.get('title') or '').lower()
    if re.search(r'^assembled|fully assembled|no assembly', asm):
        out['装'] = ('整装', spec_c, 'text_supported', 'spec')
    elif re.search(r'ready to assemble|unassembled|partial|assembly needed|assembly required', asm):
        out['装'] = ('拆装', spec_c, 'text_supported', 'spec')
    elif '(assembled)' in t or 'fully assembled' in t:
        out['装'] = ('整装', spec_c, 'text_supported', 'rule')
    elif re.search(r'ready[ -]to[ -]assemble|\brta\b|unassembled', t):
        out['装'] = ('拆装', spec_c, 'text_supported', 'rule')
    elif tags.get(H[1]) in ('整装', '拆装'):
        out['装'] = (tags[H[1]], cf(H[1], tags[H[1]]), st(H[1]), src(H[1]))
    else:
        out['装'] = ('', 0.0, 'missing', 'rule')
    # 形态：规格 Vanity Type / Mount Type > 规则；都没有时按落地式（与 Amazon 同口径），标低置信度
    vt = _spec(specs, 'form').lower()
    if re.search(r'float|wall', vt):
        out['形态'] = ('悬浮式', spec_c, 'text_supported', 'spec')
    elif 'corner' in vt:
        out['形态'] = ('转角式', spec_c, 'text_supported', 'spec')
    elif 'pedestal' in vt:
        out['形态'] = ('柱状盆', spec_c, 'text_supported', 'spec')
    elif 'console' in vt:  # console vanity = 开放层板（AC-F18-10，与打标技能 console → 开放式同口径）
        out['形态'] = ('开放式', spec_c, 'text_supported', 'spec')
    elif re.search(r'free ?standing|floor', vt):
        out['形态'] = ('落地式', spec_c, 'text_supported', 'spec')
    elif norm(tags.get(H[0])):
        f = '落地式' if norm(tags.get(H[0])) == '两用' else norm(tags.get(H[0]))
        out['形态'] = (f, cf(H[0], f), st(H[0]), src(H[0]))
    else:
        out['形态'] = ('', 0.0, 'missing', 'rule')
    if default_form and not out['形态'][0]:
        out['形态'] = ('落地式', 0.6, 'business_default', 'rule')
    if out['形态'][0] == '落地式':
        f2, k = openshelf.form_of(out['形态'][0], text.get('title'), _spec(specs, 'form'))
        if f2 != out['形态'][0]:
            out['形态'] = (f2, OPEN_CONF[k], 'text_supported' if k == openshelf.STRONG else 'business_inference', out['形态'][3])
    for tg, h in (('台面材质', H[7]), ('台盆材质', H[8])):
        v = norm(tags.get(h))
        out[tg] = (v, cf(h, v), st(h), src(h))
    em = rules.get('element_map') or DEFAULT_TAG_RULES['element_map']
    els = list(dict.fromkeys(em.get(x.strip()) for x in str(tags.get(H[4]) or '').split('；') if em.get(x.strip())))
    e = '|'.join(els)
    out['元素'] = (e, 0.7 if e else 0.0, 'text_clue' if e else 'need_image', src(H[4]) if e else 'rule')
    cmap = rules.get('color_map') or fm.COLOR
    c0 = tags.get(H[5])
    col = '' if c0 is None or str(c0) in fm.RAW_UNK else cmap.get(str(c0), '其他')
    out['主色'] = (col, cf(H[5], col), st(H[5]), src(H[5]))
    sc = SPEC_COLOR.get(_spec(specs, 'color').strip().lower())
    if sc:
        out['主色'] = (sc, spec_c, 'text_supported', 'spec')
    cb = fm.cab(tags.get(H[6]))
    cb = '' if cb == '未知' else cb
    out['柜体材质'] = (cb, cf(H[6], cb), st(H[6]), src(H[6]))
    return out


def _page_specs(s, channel, items):
    from ..models_data import ChannelPageSpec
    return {r.item_id: r for r in s.scalars(select(ChannelPageSpec).where(ChannelPageSpec.channel == channel, ChannelPageSpec.item_id.in_(items)))}


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
                      features=r.get('features', ''), price=last[i].price if i in last else None, image=(p.image_url if p else ''),
                      series=(p.series if p else '') or '', brand=(p.brand if p else '') or '')
    return out


def tag_products(channel: str, items: list[str], month: str = '') -> dict:
    """规则打标并写 Tag（不覆盖已确认的标签）。Amazon 用 rule_tag；其他渠道规格优先（spec_tag，AC-F18-08）。返回统计。"""
    if not items:
        return dict(items=0, tags=0, queued=0, need_image=0)
    rules, thr, ver = rules_cfg()
    res, groups = {}, {}
    with session() as s:
        tx = _texts(s, channel, items)
        sp = _page_specs(s, channel, items) if channel != 'amazon' else {}
        for i in items:
            if channel == 'amazon':
                res[i] = {k: v + ('rule',) for k, v in rule_tag(tx[i], rules).items()}
            else:
                p = sp.get(i)
                res[i] = spec_tag(dict(tx[i], highlights=p.highlights if p else []), p.specs if p else None, rules)
            groups[i] = group_key(channel, tx[i]['image'], tx[i]['series'], tx[i]['brand'], tx[i]['title'])
    return write_tags(channel, res, groups, month)


def write_tags(channel: str, res: dict, groups: dict, month: str = '') -> dict:
    """写入打标结果 {商品: {标签: (值, 置信度, 证据状态, 来源)}}；已确认的不覆盖，已有看图元素不被规则覆盖。
    进队：元素一律进；置信度低于阈值进；“装”为空（未知）进，候选不预选（AC-F18-08）。"""
    rules, thr, ver = rules_cfg()
    stat = dict(items=0, tags=0, queued=0, need_image=0, assembly_unknown=0)
    items = list(res)
    with session() as s:
        existing = {}
        for k in range(0, len(items), 500):
            for t in s.scalars(select(Tag).where(Tag.channel == channel, Tag.item_id.in_(items[k:k + 500]))):
                existing[(t.item_id, t.tag)] = t
        for i in items:
            stat['items'] += 1
            for tg in TAG_ORDER:
                v, c, _st, src = res[i][tg]
                old = existing.get((i, tg))
                if old is not None and old.status == 'confirmed':
                    continue
                if old is not None and old.source == 'vision' and tg == '元素' and old.value:
                    continue  # 已有看图结果，不用规则覆盖
                unknown_asm = tg == '装' and not v and channel != 'amazon'
                queued = tg == '元素' or c < thr or unknown_asm
                pool = rules.get('element_vocab') if tg == '元素' else CANDIDATES.get(tg, [])
                cands = [v] if v else []
                cands += [x for x in (pool or []) if x not in cands]
                cand = [dict(value=x, confidence=(c if x == v and v else None)) for x in cands[:12]]
                if old is None:
                    old = Tag(channel=channel, item_id=i, tag=tg)
                    s.add(old)
                old.value, old.auto_value, old.confidence, old.source = v, v, c, src
                old.status = 'queued' if queued else 'auto'
                old.candidates, old.img_group, old.month, old.config_version = cand, groups.get(i, ''), month or old.month or '', ver
                stat['tags'] += 1
                stat['queued'] += int(queued)
                stat['need_image'] += int(tg == '元素' and not v)
                stat['assembly_unknown'] += int(unknown_asm)
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
            q = q.where(Tag.tag != '元素', ~((Tag.tag == '装') & (Tag.value == '') & (Tag.channel != 'amazon')))
        elif reason == 'assembly':
            q = q.where(Tag.tag == '装', Tag.value == '', Tag.channel != 'amazon')
        rows = list(s.execute(q))
        items = list({(t.channel, t.item_id) for t, _ in rows})
        other, osrc = {}, {}
        if items:
            for t in s.scalars(select(Tag).where(Tag.item_id.in_([i for _, i in items]))):
                other.setdefault((t.channel, t.item_id), {})[t.tag] = t.value
                osrc.setdefault((t.channel, t.item_id), {})[t.tag] = 'manual' if t.status == 'confirmed' and t.confirmed_by else t.source
        from .channels import item_link  # 没有商品链接时（追踪导出不带链接）按渠道商品 ID 拼链接
        groups = {}
        imaps = {}

        def image_of(t, p):
            """主图：商品自带（Amazon、带图片列的其他渠道上传）；没有时按渠道 + 商品编号取渠道调研导入的"主图"列（AC-F18-12）。"""
            if p.image_url or t.channel == 'amazon':
                return p.image_url or ''
            if t.channel not in imaps:
                from . import research
                imaps[t.channel] = research.image_map(t.channel)
            m = imaps[t.channel]
            return m.get(t.item_id) or m.get(str(t.item_id).split(' ')[0]) or ''
        for t, p in rows:
            img = image_of(t, p)
            asm = t.tag == '装' and not t.value and t.channel != 'amazon'
            gk = (t.img_group or f'{t.channel}:{t.item_id}', t.tag)
            g = groups.setdefault(gk, dict(key=f'{gk[0]}|{gk[1]}', img_group=gk[0], tag=t.tag, image=img, items=[], candidates=[], channels=set(),
                                           source='manual' if status != 'queued' else t.source,
                                           reason='元素' if t.tag == '元素' else ('装：未知' if asm else '低置信度'),
                                           by=('image' if img else ('series' if (t.img_group or '').startswith('s') else
                                                                         ('title' if (t.img_group or '').startswith('t') else 'item')))))
            o = other.get((t.channel, t.item_id), {})
            os_ = osrc.get((t.channel, t.item_id), {})
            g['items'].append(dict(tag_id=t.id, channel=t.channel, item_id=t.item_id, title=p.title, value=t.value, confidence=t.confidence,
                                   status=t.status, link=p.link or item_link(t.channel, t.item_id), image=img, confirm_mode=t.confirm_mode,
                                   source=SRC_LABEL.get('manual' if t.status == 'confirmed' and t.confirmed_by else t.source, t.source),
                                   others_tags=[(o.get(k), SRC_LABEL.get(os_.get(k), '')) for k in ('尺寸段', '装', '形态', '台面材质', '主色', '柜体材质')
                                                if k != t.tag and o.get(k) and o.get(k) != '未知'],
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


def _queued_q(*cols):
    """待确认标签的统一口径：Tag.status == 'queued'，且商品未被标为“不是本品类”（Product.excluded）。"""
    return (select(*cols).select_from(Tag).join(Product, (Product.channel == Tag.channel) & (Product.item_id == Tag.item_id))
            .where(Product.excluded.is_(False), Tag.status == 'queued'))


def queued_count() -> int:
    """待确认条数；侧栏角标、工作台、打标确认页共用此口径（含"分框未知（渠道调研）"条目，REQ-F30-04）。"""
    from . import research
    with session() as s:
        return (s.scalar(_queued_q(func.count())) or 0) + research.pending_count()


def queued_groups() -> int:
    """待确认的组数，与打标确认页“共 N 组”同口径：按（分组键, 标签）分组，没有分组键的商品自成一组（见 queue）。"""
    from sqlalchemy import case
    gk = case((Tag.img_group != '', Tag.img_group), else_=Tag.channel + ':' + Tag.item_id)
    with session() as s:
        sub = _queued_q(gk.label('g'), Tag.tag).distinct().subquery()
        return s.scalar(select(func.count()).select_from(sub)) or 0


def _confirmed_q(*cols):
    """已确认页签的口径（与 queue(status='confirmed') 一致）：人工确认过的标签，商品未被标为“不是本品类”。"""
    return (select(*cols).select_from(Tag).join(Product, (Product.channel == Tag.channel) & (Product.item_id == Tag.item_id))
            .where(Product.excluded.is_(False), Tag.status == 'confirmed', Tag.confirmed_by.is_not(None)))


def counts(status: str = 'queued'):
    """页签计数与筛选计数。by_channel / element / assembly / low / total 按 status 所指页签（queued 待确认 / confirmed 已确认）计算，
    与该页签下列表的条数同口径；confirmed、excluded 是页签上的总数。"""
    sq = _confirmed_q if status == 'confirmed' else _queued_q
    with session() as s:
        base = sq(Tag.channel, Tag.tag, func.count()).group_by(Tag.channel, Tag.tag)
        q = {}
        for ch, tg, n in s.execute(base):
            q.setdefault(ch, {})[tg] = n
        confirmed = s.scalar(_confirmed_q(func.count())) or 0
        excluded = s.scalar(select(func.count()).select_from(Product).where(Product.excluded.is_(True))) or 0
        assembly = s.scalar(sq(func.count()).where(Tag.tag == '装', Tag.value == '', Tag.channel != 'amazon')) or 0
    total = sum(sum(v.values()) for v in q.values())
    element = sum(v.get('元素', 0) for v in q.values())
    by_channel = {ch: sum(v.values()) for ch, v in q.items()}
    frame, frame_by = 0, {}
    if status == 'queued':  # "分框未知（渠道调研）"条目（来自渠道调研最近一次计算，REQ-F30-04）
        from . import research
        frame_by = research.pending_by_channel()
        frame = sum(frame_by.values())
        for ch, n in frame_by.items():
            if n:
                by_channel[ch] = by_channel.get(ch, 0) + n
    return dict(by_channel=by_channel, element=element, assembly=assembly, frame=frame, frame_by=frame_by,
                low=total - element - assembly, total=total + frame, confirmed=confirmed, excluded=excluded)


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


# ---------------------------------------------------------------- 分框规则变更后重打标（AC-F18-11，revision 10）
R10 = 'rule_r10'  # 重打标写入的 Tag.source：分析面板对尺寸段 / 形态以它优先于并入时的旧标签（已确认值仍最优先）


def _width(channel, tx, spec):
    """规则读出的宽度（英寸）；其他渠道读不出时用商品页规格宽度。"""
    row = {'子ASIN': tx.get('item_id') or 'X', '目标月份': '', 'SKU属性': tx.get('sku') or '', '商品标题': tx.get('title') or '',
           '商品尺寸': tx.get('dimension') or '', '五点描述': None, '五点来源': None, '五点来源ASIN': tx.get('item_id'), '核验父ASIN': None,
           '商品价格': tx.get('price')}
    w = T.Tagger(row, {}, None, None).run()[0].get(T.HEADERS[9])
    if w is None and spec is not None:
        w = _spec_width(spec.specs)
    return w


def retag_frames(user_id=None) -> dict:
    """按当前分框规则重打尺寸段、形态（只改未人工确认的；AC-F18-11）。
    尺寸段：只有当前为 24″ / 30″ 的商品受 28″ 新档影响，按宽度重分档；形态：当前为落地式的按开放层板规则重判。
    当前值 = 已确认 > 本规则已重打 > 并入时标签（快照 raw.tags，取最近一次）> 自动值，与分析面板同口径。返回各渠道改动数。"""
    rules, thr, ver = rules_cfg()
    bands = rules.get('size_bands') or DEFAULT_TAG_RULES['size_bands']
    out = {}
    with session() as s:
        channels = [c for (c,) in s.execute(select(Product.channel).distinct())]
    for ch in channels:
        st = dict(size=0, form=0, queued=0)
        with session() as s:
            items = [i for (i,) in s.execute(select(Product.item_id).where(Product.channel == ch, Product.excluded.is_(False)))]
            tags = {(t.item_id, t.tag): t for t in s.scalars(select(Tag).where(Tag.channel == ch, Tag.tag.in_(['尺寸段', '形态'])))}
            raw = {}
            for i, r in s.execute(select(Snapshot.item_id, Snapshot.raw).where(Snapshot.channel == ch).order_by(Snapshot.id)):
                tg = (r or {}).get('tags') if isinstance(r, dict) else None
                if tg:
                    raw[i] = tg
            tx = _texts(s, ch, items)
            sp = _page_specs(s, ch, items) if ch != 'amazon' else {}

            def cur(i, tg):
                t = tags.get((i, tg))
                if t is not None and (t.status == 'confirmed' or t.source == R10):
                    return t.value, t.status == 'confirmed'
                v = (raw.get(i) or {}).get(tg)
                if v is None and t is not None:
                    v = t.value
                return v or '', False
            for i in items:
                for tg in ('尺寸段', '形态'):
                    v, confirmed = cur(i, tg)
                    if confirmed:
                        continue
                    new, c = v, None
                    if tg == '尺寸段' and v in ('24″', '30″'):
                        b = _band(_width(ch, tx[i], sp.get(i)), bands)
                        if b and b != v:
                            new, c = b, float((rules.get('confidence') or {}).get('text_supported', 0.95))
                    if tg == '形态' and v == '落地式':
                        p = sp.get(i)
                        f2, k = openshelf.form_of('落地式', tx[i].get('title'), tx[i].get('sku'), _spec(p.specs, 'form') if p else '')
                        if f2 != v:
                            new, c = f2, OPEN_CONF[k]
                    if new == v:
                        continue
                    t = tags.get((i, tg))
                    if t is None:
                        t = Tag(channel=ch, item_id=i, tag=tg)
                        s.add(t)
                    q = c < thr
                    pool = CANDIDATES.get(tg, [])
                    t.value, t.auto_value, t.confidence, t.source = new, new, c, R10
                    t.status = 'queued' if q else 'auto'
                    t.candidates = [dict(value=x, confidence=(c if x == new else None)) for x in [new] + [x for x in pool if x != new]]
                    t.img_group = t.img_group or group_key(ch, tx[i]['image'], tx[i]['series'], tx[i]['brand'], tx[i]['title'])
                    t.config_version = ver
                    st['size' if tg == '尺寸段' else 'form'] += 1
                    st['queued'] += int(q)
        out[ch] = st
    from .. import services
    services.put_setting('frame_rules_version', catconfig.FRAME_RULES)
    services.put_setting('frame_retag', dict(at=now().strftime('%Y-%m-%d %H:%M'), result=out))
    services.put_setting('models_stale_frames', True)
    return out


def ensure_frame_rules() -> dict | None:
    """启动时检查：品类配置分框规则还不是 revision 10 时升级配置、重打标、重扫描（AC-F18-11）。已是则什么都不做。"""
    from .. import services
    if services.get_setting('frame_rules_version', '') == catconfig.FRAME_RULES:
        return None
    catconfig.upgrade_frames()
    res = retag_frames()
    from . import panel, pipeline, research
    panel.clear_cache()
    for ch in res:
        pipeline.rescan(ch)  # 没有并入数据的渠道返回空，不报错
    for ch in research.CHANNELS:
        research.recompute(ch)
    services.put_setting('frame_retag', dict(at=now().strftime('%Y-%m-%d %H:%M'), result=res))
    return res
