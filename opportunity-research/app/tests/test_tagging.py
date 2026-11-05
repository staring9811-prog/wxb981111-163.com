"""打标确认（PAGE-F18-01）：规则打标 + 看图打元素 + 确认队列（同图一组、组内单改、不是本品类）、其他渠道同一套规则。"""
import re
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


def _queue_rows(n=130):
    """n 个不同主图的 Amazon 商品，各有一条待确认“元素”；另有 5 个 Lowe's 低置信度“台面材质”。"""
    titles = ['30 Inch Bathroom Vanity with Ceramic Sink, Fluted Doors', '36 Inch Floating Bathroom Vanity with Resin Top, Oak',
              '24 Inch Freestanding Bathroom Vanity with Farmhouse Barn Door']
    with session() as s:
        for i in range(n):
            s.add(Product(channel='amazon', item_id=f'B0Q{i:07d}', brand='Sweetcrispy', title=titles[i % 3],
                          image_url=f'https://m.media-amazon.com/images/I/71vanity{i:04d}.jpg', link=f'https://www.amazon.com/dp/B0Q{i:07d}'))
            s.add(Tag(channel='amazon', item_id=f'B0Q{i:07d}', tag='元素', value='竖棱' if i % 2 else '', confidence=0.7 if i % 2 else 0.0,
                      source='rule', status='queued', img_group=f'img{i:04d}', candidates=[{'value': '竖棱', 'confidence': 0.7}, {'value': '农场风'}]))
        for i in range(5):
            s.add(Product(channel='lowes', item_id=f'50144528{i:02d}', brand='allen + roth', title='allen + roth Presley 36-in Gray Bathroom Vanity with Carrara Marble Top'))
            s.add(Tag(channel='lowes', item_id=f'50144528{i:02d}', tag='台面材质', value='岗石', confidence=0.62, source='rule', status='queued', img_group=f'lw{i}'))


def test_queue_pagination_keeps_filters(wen):
    """DESIGN-08：确认队列每页 60 组，显示总组数与页码，翻页时渠道 / 进队原因筛选保持；超出最后一页时落到最后一页。"""
    _queue_rows(130)
    html = wen.get('/tagging', params={'channel': 'amazon', 'reason': 'element'}).text
    assert '共 <b class="num">130</b> 组' in html and '第 1 / 3 页，每页 60 组' in html
    assert html.count('class="qgroup"') == 60
    assert 'href="/tagging?channel=amazon&amp;reason=element&amp;tab=pending&amp;page=2"' in html
    p3 = wen.get('/tagging', params={'channel': 'amazon', 'reason': 'element', 'page': 3}).text
    assert p3.count('class="qgroup"') == 10 and '第 3 / 3 页' in p3 and 'aria-current="page">3<' in p3
    assert 'Lowe' not in p3.split('id="queue"')[1].split('</section>')[0]
    assert wen.get('/tagging', params={'channel': 'amazon', 'reason': 'element', 'page': 99}).text.count('class="qgroup"') == 10
    lw = wen.get('/tagging', params={'channel': 'lowes'}).text
    assert lw.count('class="qgroup"') == 5 and 'pager__btn' not in lw


def test_notcat_needs_confirm_modal(wen):
    """DESIGN-08（补）：整组“看不出 / 不是本品类”与单行“不是本品类”只打开确认弹窗（说明后果、可在“不是本品类”页签恢复），确认后才提交写库。"""
    _queue_rows(3)
    html = wen.get('/tagging').text
    assert 'id="modal-notcat"' in html and '不进入浴室柜的任何分析' in html and '可在"不是本品类"标签页恢复' in html
    assert 'formaction="/tagging/groups/exclude"' not in html
    assert re.search(r'<button class="btn btn--ghost btn--sm" type="button" data-notcat data-action="/tagging/groups/exclude" data-img-group="img0000"', html)
    assert re.search(r'type="button" data-notcat data-action="/tagging/items/\d+" data-channel="amazon" data-item-id="B0Q0000001" data-sub="只标这一个商品：B0Q0000001"', html)
    assert not re.search(r'name="action" value="exclude">.*?type="submit">不是本品类', html)
    with session() as s:
        assert s.scalar(select(func.count()).select_from(Product).where(Product.excluded.is_(True))) == 0
    # 弹窗确认提交（与弹窗表单字段一致）后才写库
    r = wen.post('/tagging/groups/exclude', data={'img_group': 'img0001', 'action': 'exclude', 'channel': '', 'item_id': '', 'back': '/tagging'}, follow_redirects=True)
    assert '1 个商品已标为“看不出 / 不是本品类”' in r.text
    with session() as s:
        assert s.scalar(select(Product.excluded).where(Product.item_id == 'B0Q0000001')) is True


def test_tagging_export_current_filter(wen):
    """DESIGN-08（补）：页头“导出 Excel”导出当前筛选下的队列明细。"""
    import io
    from openpyxl import load_workbook
    _queue_rows(70)
    assert 'href="/tagging/export?channel=lowes&amp;reason=all&amp;tab=pending"' in wen.get('/tagging', params={'channel': 'lowes'}).text
    r = wen.get('/tagging/export', params={'channel': 'lowes', 'reason': 'all', 'tab': 'pending'})
    assert r.status_code == 200 and 'spreadsheetml' in r.headers['content-type']
    ws = load_workbook(io.BytesIO(r.content)).active
    rows = list(ws.values)
    assert rows[0][:7] == ('同图组', '标签', '进队原因', '来源', '渠道', '商品ID', '标题')
    assert len(rows) == 6 and {x[4] for x in rows[1:]} == {"Lowe's"} and {x[8] for x in rows[1:]} == {'岗石'}
    ws = load_workbook(io.BytesIO(wen.get('/tagging/export', params={'channel': 'amazon', 'reason': 'element'}).content)).active
    assert ws.max_row == 71  # 全部 70 条，不受分页限制


def test_other_channel_image_sources_and_noimage_placeholder(wen):
    """DESIGN-08 / FLOW-08：其他渠道主图来源——评论追踪采集的商品详情里有“主图URL”（Home Depot / Wayfair 只在详情里，Lowe's 在列表行里）时并入写 Product.image_url；
    渠道 VP 汇总导出没有图片列时，分组卡片显示“没有主图，点商品链接去商品页看”并给商品链接，不显示截断的商品 ID 当图指纹（不再出现“wayf…765)”）；
    无图商品按同系列或同品牌同标题分组，而不是一商品一组。"""
    from pdt.core import channels, tagging
    revs = lambda iid: [{'评论ID': f'{iid}-r{k}', '评论日期': f'2026-10-1{k}', 'VP状态': 'VP', '评分': 5} for k in range(3)]
    rows = [
        {'平台': 'HomeDepot', '商品ID': '315064871', '品牌': 'Glacier Bay', '标题': 'Glacier Bay Brindley 36 in. Single Sink Freestanding Bath Vanity in Natural Oak', '排名': 1,
         'url': 'https://www.homedepot.com/p/Glacier-Bay-Brindley-36-in/315064871', 'reviews': revs('315064871'),
         'details': {'主图URL': 'https://images.thdstatic.com/productImages/2f6c1a8e/svn/glacier-bay-bathroom-vanities-with-tops-1000.jpg'}},
        {'平台': 'Lowes', '商品ID': '5014452871', '品牌': 'allen + roth', '标题': 'allen + roth Presley 36-in Gray Undermount Single Sink Bathroom Vanity', '排名': 1,
         '主图URL': 'https://mobileimages.lowes.com/productimages/5f2b1c9e-presley.jpg', 'url': 'https://www.lowes.com/pd/allen-roth-Presley/5014452871', 'reviews': revs('5014452871')},
    ]
    channels.ingest_tracker_month(rows, collected_on='2026-11-03')
    with session() as s:
        img = {p.item_id: p.image_url for p in s.scalars(select(Product).where(Product.channel.in_(['homedepot', 'lowes'])))}
    assert img['315064871'].startswith('https://images.thdstatic.com/') and img['5014452871'].startswith('https://mobileimages.lowes.com/')

    # 渠道 VP 汇总导出（无图片、无链接列）：Wayfair 两个同品牌同标题的商品 + 一个单独商品
    t1 = 'Ebern Designs 36" Free-Standing Modern Single Bathroom Vanity With Sink'
    with session() as s:
        for iid, title in (('W115187693 (piid 120906584)', t1), ('W115187692 (piid 1405707648)', t1),
                           ('W111999433 (piid 1959543287)', 'Birch Lane™ Lala 84" Double Bathroom Vanity with Grain White Engineered Stone Countertop')):
            s.add(Product(channel='wayfair', item_id=iid, brand='Ebern Designs' if title == t1 else 'Birch Lane™', title=title))
    tagging.tag_products('wayfair', ['W115187693 (piid 120906584)', 'W115187692 (piid 1405707648)', 'W111999433 (piid 1959543287)'], '2026-10')
    g = [x for x in tagging.queue('wayfair') if x['tag'] == '元素']
    assert sorted(len(x['items']) for x in g) == [1, 2]  # 同品牌同标题两个商品一组
    assert tagging.queued_groups() == len(tagging.queue())
    html = wen.get('/tagging', params={'channel': 'wayfair'}).text
    assert '没有主图，点商品链接去商品页看' in html and 'href="https://www.wayfair.com/keyword.php?keyword=W115187693"' in html
    assert '无主图 · 同品牌同标题 2 个商品' in html
    queue_html = html.split('id="queue"')[1]
    assert '图指纹' not in queue_html and 'wayf…' not in queue_html and '765)' not in queue_html
    hd = wen.get('/tagging', params={'channel': 'homedepot'}).text.split('id="queue"')[1]
    assert 'src="https://images.thdstatic.com/' in hd and '同图分组' in hd


def test_group_key_series_title_and_fill_existing():
    """DESIGN-08：分组键——有主图按图指纹；无图有系列按系列；都没有按同品牌同标题；已入库无分组键的标签启动时补上。"""
    from pdt.core import tagging
    a = tagging.group_key('lowes', '', 'Presley', 'allen + roth', 'Presley 30-in White Bathroom Vanity')
    b = tagging.group_key('lowes', '', 'Presley', 'allen + roth', 'Presley 48-in Gray Bathroom Vanity')
    c = tagging.group_key('lowes', '', '', 'Style Selections', 'Bathroom Vanity Base Cabinet without Top')
    d = tagging.group_key('lowes', '', '', 'Project Source', 'Bathroom Vanity Base Cabinet without Top')
    e = tagging.group_key('amazon', 'https://m.media-amazon.com/images/I/71vanity0001._AC_SL1500_.jpg')
    assert a == b and a.startswith('s') and c != d and c.startswith('t') and len(e) == 12 and e == tagging.img_key('https://m.media-amazon.com/images/I/71vanity0001.jpg')
    from pdt.core.channels import item_link
    assert item_link('wayfair', 'W111999433 (piid 1959543287)') == 'https://www.wayfair.com/keyword.php?keyword=W111999433'
    assert item_link('homedepot', '203486567') == 'https://www.homedepot.com/p/203486567'


def test_fill_groups_for_existing_noimage_tags(wen):
    """DESIGN-08：已入库、分组键为空的无图标签（升级前一商品一组）补上同品牌同标题分组键，工作台“共 N 组”与打标页一致。"""
    from pdt.core import tagging
    with session() as s:
        for iid in ('5001952377', '5001952378'):
            s.add(Product(channel='lowes', item_id=iid, brand='Project Source', title='Dover Single Sink Bathroom Vanity with White Cultured Marble Top'))
            s.add(Tag(channel='lowes', item_id=iid, tag='元素', value='', source='rule', status='queued', img_group=''))
    assert tagging.queued_groups() == 2
    assert tagging.fill_groups() == 2
    assert tagging.queued_groups() == len(tagging.queue()) == 1
    assert '共 1 组（同主图的合为一组' in wen.get('/').text and '共 <b class="num">1</b> 组' in wen.get('/tagging').text


def test_design08_filter_counts_follow_tab_and_layout(wen):
    """DESIGN-08（v8 复核）：切到“已确认”页签后，渠道与进队原因筛选上的数量按已确认条目计算，与列表条数一致；
    “待确认”页签仍是待确认数。标题“自动打标进度”不换行、页头按钮保持一行（页面样式）。"""
    from pdt.models import User
    _queue_rows(130)
    with session() as s:
        uid = s.scalar(select(User.id).where(User.username == 'wen'))
        am = list(s.scalars(select(Tag).where(Tag.channel == 'amazon').order_by(Tag.item_id).limit(3)))
        lw = list(s.scalars(select(Tag).where(Tag.channel == 'lowes').order_by(Tag.item_id).limit(2)))
        for t in am:
            t.value, t.status, t.confirmed_by, t.confirm_mode = '竖棱', 'confirmed', uid, 'group'
        for t in lw:
            t.value, t.status, t.confirmed_by, t.confirm_mode = '石英石', 'confirmed', uid, 'single'
    done = wen.get('/tagging', params={'tab': 'done'}).text
    flt = done.split('id="queue-filters"')[1].split('id="queue"')[0]
    assert '全部 <span class="count">5</span>' in flt and 'Amazon <span class="count">3</span>' in flt and "Lowe&#39;s <span class=\"count\">2</span>" in flt
    assert 'Home Depot <span class="count">0</span>' in flt and 'Wayfair <span class="count">0</span>' in flt
    assert '元素 <span class="count">3</span>' in flt and '低置信度 <span class="count">2</span>' in flt and '装：未知 <span class="count">0</span>' in flt
    assert '共 <b class="num">5</b> 组 · 5 条' in flt
    pend = wen.get('/tagging').text.split('id="queue-filters"')[1].split('id="queue"')[0]
    assert '全部 <span class="count">130</span>' in pend and 'Amazon <span class="count">127</span>' in pend and "Lowe&#39;s <span class=\"count\">3</span>" in pend
    assert '.section__head .section__title { flex: none; white-space: nowrap; }' in done
    assert '.page-head__actions { flex: none; flex-wrap: nowrap; }' in done


def test_design08_element_values_shown_in_chinese(wen):
    """DESIGN-08（v8 复核）：元素取值的英文原值在打标确认页显示为中文（rattan → 藤编、rustic → 乡村风），表单提交的存储值不变。"""
    from pdt.catconfig import value_name
    assert value_name('rattan') == '藤编' and value_name('夏克式+rattan') == '夏克式+藤编' and value_name('rustic|竖棱') == '乡村风|竖棱'
    with session() as s:
        s.add(Product(channel='wayfair', item_id='W004918261', brand='Bay Isle Home', title="Bay Isle Home Kimbrough 30'' Single Bathroom Vanity with Rattan Doors",
                      image_url='https://assets.wfcdn.com/im/30473922/rattan-vanity.jpg'))
        s.add(Tag(channel='wayfair', item_id='W004918261', tag='元素', value='rattan', confidence=0.7, source='rule', status='queued', img_group='wf-rattan',
                  candidates=[{'value': 'rattan', 'confidence': 0.7}, {'value': 'rustic', 'confidence': 0.2}]))
    html = wen.get('/tagging', params={'channel': 'wayfair'}).text
    q = html.split('id="queue"')[1]
    assert 'value="rattan" checked>藤编' in q and 'value="rustic" >乡村风' in q
    assert '<option value="rattan" selected>藤编</option>' in q and '<option value="rustic" >乡村风</option>' in q
    assert not re.search(r'>[^<]*\b(rattan|rustic)\b[^<]*<', q.split('</section>')[0])
