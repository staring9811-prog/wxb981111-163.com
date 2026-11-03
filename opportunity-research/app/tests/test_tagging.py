"""打标确认（PAGE-F18-01）：规则打标 + 看图打元素 + 确认队列（同图一组、组内单改、不是本品类）、其他渠道同一套规则。"""
import json
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import func, select

from v2fixture import FakeLLM, api_rows, set_secret

from pdt import services
from pdt.db import session
from pdt.models import Batch, Product, Tag

TAGS = ['尺寸段', '装', '形态', '台面材质', '台盆材质', '元素', '主色', '柜体材质']
CASES = Path(__file__).parent / 'data' / 'v12.2_cases.jsonl'


def test_v122_rule_cases():
    """AC-F18-01（规则口径）：移植后的打标规则通过第二轮打标技能 v12.2 的全部规则用例。"""
    from pdt.core import tagging_rules as T
    bad, n = [], 0
    for line in CASES.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        n += 1
        f, exp = c['field'], c['expected']
        if c['mode'] == 'family':
            D2 = T.HEADERS[1]
            rows = [('A', '202510', {D2: '整装', T.HEADERS[15]: ''}, {D2: {'status': 'parent_fill'}}, {D2: 'A3'}, {}, {'核验父ASIN': 'P'}, 0),
                    ('B', '202510', {D2: '拆装', T.HEADERS[15]: ''}, {D2: {'status': 'business_default'}}, {D2: 'A2'}, {}, {'核验父ASIN': 'P'}, 1)]
            mtx = [[None] * 16, [None, '拆装'] + [None] * 14]
            T.apply_family_assembly_fill(rows, mtx, [{'tags': {}, 'fields': {}, 'feasibility': {}}] * 2)
            got = mtx[1][1]
        elif c['mode'] == 'structure':
            (field, text), = c['sources'].items()
            if field.startswith('卖家精灵导出.详细参数'):
                x = T.Tagger({'子ASIN': 'X', 'SKU属性': '', '商品标题': '', '五点来源': None, '核验父ASIN': None, '商品尺寸': ''}, {}, None, [{'attributes': text, 'month': '202605'}])
            else:
                x = T.Tagger.__new__(T.Tagger)
                x.row, x.asin, x.provenance, x.tags, x.evidence, x.conflicts, x.notes, x.rejected_dims = {}, 'X', {}, {}, {}, [], [], []
                x.enable_dim_rules, x.accessory_default, x.parent_fill, x.std_width, x.parent_detail = False, False, True, False, {}
                x.sources = [{'field': field, 'text': text, 'scope': 'child', 'asin': 'X'}]
            for h in T.HEADERS[:14]:
                x.tags.setdefault(h, T.UNKNOWN)
            x.structure()
            got = x.tags[f]
        else:
            row = {'子ASIN': 'BTEST00001', '目标月份': '202601', 'SKU属性': '', '商品标题': 'Bathroom Vanity' if c['suite'] == '台面台盆' else '', '商品尺寸': '',
                   '五点描述': None, '五点来源': None, '五点来源ASIN': None, '核验父ASIN': None, '商品价格': None}
            ex = []
            for k, v in c['sources'].items():
                if k in ('商品标题', 'SKU属性', '商品尺寸'):
                    row[k] = v
                elif k in ('五点描述', '五点描述(子体)'):
                    row.update({'五点描述': v, '五点来源': '子体详情', '五点来源ASIN': 'BTEST00001'})
                elif k == '五点描述(父体)':
                    row.update({'五点描述': v, '五点来源': '父体详情填充', '五点来源ASIN': 'BPARENT001'})
                else:
                    key = k[len('卖家精灵导出.详细参数'):].lstrip('.')
                    ex.append({'attributes': f'{key}:{v}' if key else v, 'features': None, 'month': '202605'})
            tags, ev, conf = T.Tagger(row, {}, None, ex or None).run()
            got = ('有' if any(x.startswith(('D6', 'D9')) for x in conf) else '无') if f == '冲突标记(D6/D9)' else tags[f]
        ok = (got is not None and exp is not None and abs(float(got) - float(exp)) <= 0.5) if f.startswith('D9') and not (got is None or exp is None) else got == exp
        if not ok:
            bad.append((c.get('id'), f, exp, got))
    assert n > 200 and not bad, bad[:5]


def _new_batch(month='2026-10', n=30):
    from pdt.core import ingest
    df = ingest.normalize(pd.DataFrame(api_rows(month, n)), '测试')
    return ingest.create_batch(month, df, 'upload')


def test_rule_tags_and_queue_without_llm(wen):
    """FLOW-06（未配置大模型）：每个子体都有全部标签和置信度；规则判断不了元素的直接进确认队列；队列只含元素与低于阈值的标签，每条显示主图、标题、候选值。"""
    _new_batch()
    from pdt.core import tagging
    with session() as s:
        tags = list(s.scalars(select(Tag)))
    by = {}
    for t in tags:
        by.setdefault(t.item_id, {})[t.tag] = t
    assert len(by) == 30 and all(set(v) == set(TAGS) for v in by.values())
    _, thr, _ = tagging.rules_cfg()
    for item, ts in by.items():
        for k, t in ts.items():
            assert 0 <= t.confidence <= 1
            assert t.status == ('queued' if (k == '元素' or t.confidence < thr) else 'auto'), (item, k, t.confidence, t.status)
    shaker = by['B0SYN00000']  # “30 Inch White Shaker Bathroom Vanity with Ceramic Sink Countertop”
    assert (shaker['尺寸段'].value, shaker['装'].value, shaker['形态'].value, shaker['元素'].value, shaker['主色'].value, shaker['台面材质'].value) == \
           ('30″', '拆装', '落地式', '夏克式', '白', '陶瓷')
    floating = by['B0SYN00002']  # 规则判断不了元素
    assert floating['形态'].value == '悬浮式' and floating['元素'].value == '' and floating['元素'].status == 'queued'
    r = wen.post('/jobs/estimate', data={'kind': 'vision_tag', 'month': '2026-10'})
    assert r.status_code == 400 and '未连接' in r.json()['error']
    html = wen.get('/tagging').text
    assert '看图打元素' in html and '大模型未配置' in html
    g = tagging.queue()
    assert g and all(x['tag'] == '元素' or all(i['confidence'] < thr for i in x['items']) for x in g)
    assert all(x['image'] and x['candidates'] and all(i['title'] for i in x['items']) for x in g)
    assert 'https://m.media-amazon.com/images/I/IMG00000._AC_US200_.jpg' in html and '这组的"元素"是什么？' in html


def test_vision_with_llm(wen):
    """FLOW-06（配置了大模型）：规则判断不了元素的商品经费用闸门由大模型看主图给出元素和置信度，仍进确认队列等人确认。"""
    _new_batch()
    set_secret('llm')
    fake = FakeLLM('竖棱', 0.82)
    services.set_fake('llm', fake)
    from pdt.core import tagging
    todo = tagging.vision_targets()
    assert len(todo) == 6  # 30 个商品里第 3 种款式（悬浮式、标题无元素词）每 5 个一个
    j = wen.post('/jobs/estimate', data={'kind': 'vision_tag', 'month': '2026-10'}).json()
    assert j['estimate']['calls'] == 6 and fake.calls == []
    j = wen.post(f"/jobs/{j['id']}/confirm").json()
    assert j['status'] == 'done' and len(fake.calls) == 6 and fake.calls[0][1][0].startswith('https://m.media-amazon.com/')
    with session() as s:
        t = s.scalar(select(Tag).where(Tag.item_id == 'B0SYN00002', Tag.tag == '元素'))
        assert (t.value, t.confidence, t.source, t.status) == ('竖棱', 0.82, 'vision', 'queued')
        assert [c['value'] for c in t.candidates][:2] == ['竖棱', '木条格栅']


def test_group_confirm_single_override_exclude(wen):
    """FLOW-07：同图 3 个商品一次“应用到整组”，再单改其中 1 个；另把一个商品标为“看不出 / 不是本品类”；重算后扫描与面板用确认值、被排除的商品不出现。"""
    bid = _new_batch(n=60)
    from pdt.core import panel, tagging
    g = next(x for x in tagging.queue(reason='element') if len(x['items']) == 3)
    items = sorted(i['item_id'] for i in g['items'])
    r = wen.post('/tagging/groups/confirm', data={'img_group': g['img_group'], 'tag': '元素', 'value': '竖棱'}, follow_redirects=True)
    assert '已把整组 3 条“元素”确认为 竖棱' in r.text
    one = next(i for i in g['items'] if i['item_id'] == items[0])
    wen.post(f"/tagging/items/{one['tag_id']}", data={'value': '木条格栅'})
    with session() as s:
        ts = {t.item_id: t for t in s.scalars(select(Tag).where(Tag.item_id.in_(items), Tag.tag == '元素'))}
    assert [ts[i].status for i in items] == ['confirmed'] * 3
    assert (ts[items[0]].value, ts[items[0]].confirm_mode) == ('木条格栅', 'single')
    assert [(ts[i].value, ts[i].confirm_mode) for i in items[1:]] == [('竖棱', 'group')] * 2
    victim = 'B0SYN00010'
    t = tagging.queue(reason='element')[0]['items'][0]
    wen.post(f"/tagging/items/{t['tag_id']}", data={'action': 'exclude', 'channel': 'amazon', 'item_id': victim})
    with session() as s:
        assert s.scalar(select(Product).where(Product.item_id == victim)).excluded
    assert all(i['item_id'] != victim for x in tagging.queue() for i in x['items'])
    # 并入并重算
    wen.post(f'/data/batches/{bid}/merge', data={'confirm': '1'})
    p = panel.load_panel('amazon')
    assert victim not in set(p['item_id'])
    got = p[p['item_id'].isin(items)].drop_duplicates('item_id').set_index('item_id')['元素'].to_dict()
    assert got == {items[0]: '木条格栅', items[1]: '竖棱', items[2]: '竖棱'}
    from pdt.core import scan as sc
    an = panel.analysis('amazon')
    X = sc.scan(an.A, an.U, an.END, rules={'min_frame_units': 0, 'min_value_units': 0})
    el = X[X['属性'] == '元素']
    assert {'竖棱', '木条格栅'} <= set(el['取值'])  # 扫描用确认值
    assert victim not in set(an.A['子ASIN'])  # 被排除的商品不进入扫描底表
    assert '不是本品类 <span class="count">1</span>' in wen.get('/tagging').text
    # 可恢复
    wen.post('/tagging/items/0', data={'action': 'restore', 'channel': 'amazon', 'item_id': victim})
    assert victim in set(panel.load_panel('amazon')['item_id'])


def test_other_channel_same_rules_and_filter(wen):
    """FLOW-08：Home Depot / Lowe's / Wayfair 商品用同一套规则打全部标签，需确认的进同一个队列、带渠道标识，按渠道筛选数量正确。"""
    from pdt.core import channels, tagging
    rows = []
    for ch, plat, title in (('homedepot', 'HomeDepot', 'Glacier Bay Everdean 31 in. Single Sink White Freestanding Bath Vanity with White Cultured Marble Top (Assembled)'),
                            ('lowes', 'Lowes', 'allen + roth Presley 36-in Gray Undermount Single Sink Bathroom Vanity with Carrara Marble Top'),
                            ('wayfair', 'Wayfair', "Wade Logan Arlo 30'' Free-standing Single Bathroom Vanity with Ceramic Top, Fluted Doors")):
        for i in range(4):
            rows.append({'平台': plat, '商品ID': f'{ch[:2].upper()}{i}', '品牌': title.split()[0], '标题': title, '排名': i + 1,
                         '主图URL': f'https://images.example-cdn.com/{ch}/{i // 2}.jpg',
                         'reviews': [{'评论ID': f'{ch}{i}-{k}', '评论日期': '2026-10-05', 'VP状态': 'VP', '评分': 5} for k in range(3)]})
    channels.ingest_tracker_month(rows, collected_on='2026-11-03')
    with session() as s:
        for ch in ('homedepot', 'lowes', 'wayfair'):
            n = s.scalar(select(func.count()).select_from(Tag).where(Tag.channel == ch))
            assert n == 4 * 8
        wf = {t.tag: t.value for t in s.scalars(select(Tag).where(Tag.channel == 'wayfair', Tag.item_id == 'WA0'))}
        q_by = dict(s.execute(select(Tag.channel, func.count()).where(Tag.status == 'queued').group_by(Tag.channel)).all())
    assert (wf['尺寸段'], wf['形态'], wf['元素'], wf['台面材质']) == ('30″', '落地式', '竖棱', '陶瓷')
    c = tagging.counts()
    assert c['by_channel'] == q_by
    for ch in ('homedepot', 'lowes', 'wayfair'):
        g = tagging.queue(ch)
        assert g and all(i['channel'] == ch for x in g for i in x['items'])
        assert sum(len(x['items']) for x in g) == q_by[ch]
    html = wen.get('/tagging', params={'channel': 'wayfair'}).text
    assert f"Wayfair <span class=\"count\">{q_by['wayfair']}</span>" in html and '<td>Wayfair</td>' in html and '<td>Home Depot</td>' not in html
