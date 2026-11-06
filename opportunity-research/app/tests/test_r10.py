"""revision 10（2026-11-05）：FLOW-41～48 的行为部分。

期望值按 TDD 契约里写明的规则手算（不由被测函数生成）：
- 停止线：做成新品款上架第 2–3 个月整款月销两月平均的第 10 百分位（线性插值），不足 10 款退同尺寸段，再不足 60；
- 白话读法、需求范围、尺寸段九档与开放式、小平台框门槛 100 与"样本少，只作参考"、主图可选列。
"""
import math
from datetime import date

import pandas as pd
import pytest

from conftest import login_as  # noqa: F401


# ---------------------------------------------------------------- FLOW-45 尺寸段九档、开放式
def test_flow45_size_bands_and_open_shelf_rules(app_env):
    from pdt.core import families as fm, openshelf, tagging
    widths = [20.9, 21, 25.9, 26, 28.9, 29, 32.9, 33, 65.9, 66]
    want = ['18″', '24″', '24″', '28″', '28″', '30″', '30″', '36″', '60″', '72″+']
    assert [fm.band(w) for w in widths] == want
    bands = tagging.rules_cfg()[0]['size_bands']
    assert [tagging._band(w, bands) for w in widths] == want
    assert tagging._band(14.9, bands) == ''
    # 开放层板：落地柜写明 open shelf / console → 开放式；悬浮柜不改；镜柜层板、without 不算；只有泛指词 → 低把握
    assert openshelf.form_of('落地式', '30 in. Vanity with Open Shelf') == ('开放式', 'strong')
    assert openshelf.form_of('悬浮式', 'Floating Vanity with Open Shelf') == ('悬浮式', None)
    assert openshelf.form_of('落地式', 'Vanity with Medicine Cabinet open shelf') == ('落地式', None)
    assert openshelf.form_of('落地式', 'Vanity without open shelves') == ('落地式', None)
    assert openshelf.form_of('落地式', 'Vanity with open storage space') == ('开放式', 'weak')
    assert openshelf.form_of('落地式', 'Console Vanity') == ('开放式', 'strong')
    thr = tagging.rules_cfg()[1]
    t = tagging.rule_tag(dict(item_id='B0TEST0001', title='30 inch Bathroom Vanity with Sink, Open Shelf, Freestanding'))
    assert t['形态'][0] == '开放式' and t['形态'][1] >= thr
    t = tagging.rule_tag(dict(item_id='B0TEST0002', title='30 inch Bathroom Vanity with Sink and open storage space, Freestanding'))
    assert t['形态'][0] == '开放式' and t['形态'][1] < thr  # 只有泛指词：进确认队列
    # 品类配置默认分框与打标取值一致（AC-F27-01 r2）
    from pdt import catconfig
    dims = {d['dim']: d['values'] for d in catconfig.current()[1]['frame_dims']}
    assert dims['尺寸段'] == tagging.CANDIDATES['尺寸段'] and dims['形态'] == ['落地式', '悬浮式', '开放式']


def test_flow45_retag_keeps_confirmed_and_panel_uses_new_frames(app_env):
    from pdt import services
    from pdt.core import panel, tagging
    from pdt.db import session
    from pdt.models import Batch, Product, Snapshot, Tag
    items = {  # 商品：标题、尺寸文本、并入时标签（尺寸段, 形态）
        'B0R10A0001': ('Vanity 28 inch, Freestanding', '18"D x 28"W x 34"H', ('30″', '落地式')),
        'B0R10A0002': ('Vanity 28 inch confirmed', '18"D x 28"W x 34"H', ('30″', '落地式')),
        'B0R10A0003': ('30 in. Vanity with Open Shelf', '18"D x 30"W x 34"H', ('30″', '落地式')),
        'B0R10A0004': ('Floating Vanity with Open Shelf', '18"D x 30"W x 20"H', ('30″', '悬浮式')),
        'B0R10A0005': ('Vanity with open storage space', '18"D x 36"W x 34"H', ('36″', '落地式')),
    }
    with session() as s:
        b = Batch(channel='amazon', month='2026-09', source='api', status='merged', rows=5)
        s.add(b)
        s.flush()
        for i, (title, dim, (sz, form)) in items.items():
            s.add(Product(channel='amazon', item_id=i, family_key=i, title=title, brand='测试'))
            s.add(Snapshot(batch_id=b.id, channel='amazon', month='2026-09', item_id=i, units=50, price=200,
                           raw=dict(dimension=dim, tags={'尺寸段': sz, '装': '拆装', '形态': form})))
        s.add(Tag(channel='amazon', item_id='B0R10A0002', tag='尺寸段', value='30″', auto_value='30″', status='confirmed', source='manual', confidence=1))
    services.put_setting('frame_rules_version', '')
    res = tagging.retag_frames()
    assert res['amazon']['size'] == 1 and res['amazon']['form'] == 2 and res['amazon']['queued'] == 1
    with session() as s:
        t = {(x.item_id, x.tag): x for x in s.query(Tag).all()}
    assert t[('B0R10A0001', '尺寸段')].value == '28″'
    assert t[('B0R10A0002', '尺寸段')].value == '30″' and t[('B0R10A0002', '尺寸段')].status == 'confirmed'
    assert t[('B0R10A0003', '形态')].value == '开放式' and t[('B0R10A0003', '形态')].status == 'auto'
    assert ('B0R10A0004', '形态') not in t
    assert t[('B0R10A0005', '形态')].value == '开放式' and t[('B0R10A0005', '形态')].status == 'queued'
    panel.clear_cache()
    df = panel.load_panel('amazon')
    fr = dict(zip(df['item_id'], df['frame']))
    assert fr['B0R10A0001'] == '28″ · 拆装 · 落地式' and fr['B0R10A0003'] == '30″ · 拆装 · 开放式' and fr['B0R10A0004'] == '30″ · 拆装 · 悬浮式'
    assert services.get_setting('models_stale_frames') is True


# ---------------------------------------------------------------- FLOW-41 停止线（整款）与台账同口径
def _panel(frame_vals: dict) -> pd.DataFrame:
    """每个做成款两个子体（各一半），上架第 1 个月排名 30（做到），第 2、3 个月整款月销 = 给定值。"""
    rows = []
    for frame, vals in frame_vals.items():
        size = frame.split(' · ')[0]
        for k, v in enumerate(vals):
            fk = f'{frame}-{k}'
            for age, units, rank in ((1, 40, 30), (2, v, 80), (3, v, 90)):
                for j in range(2):
                    rows.append(dict(month=f'2026-0{age}', item_id=f'{fk}-{j}', family_key=fk, units=units / 2, revenue=units / 2 * 200,
                                     rank=rank, age_months=age, frame=frame, 尺寸段=size))
    return pd.DataFrame(rows)


def test_flow41_stop_line_family_percentile_fallbacks_and_ledger_same_basis(app_env, monkeypatch):
    from pdt.core import card, ledger
    from pdt.core import panel_adapter as pa
    A = '30″ · 拆装 · 落地式'
    B = '48″ · 整装 · 悬浮式'
    C = '18″ · 整装 · 开放式'
    df = _panel({A: [22, 34, 40, 48, 55, 61, 70, 82, 95, 120, 150, 210], B: [10, 20, 30, 40],
                 '48″ · 拆装 · 落地式': [15, 30, 44, 52, 66, 73, 80], C: [5, 6, 7]})
    monkeypatch.setattr(pa, 'load_panel', lambda ch: df)
    a = card.stop_line('amazon', A)
    assert (a['value'], a['scope'], a['n']) == (35, 'frame', 12)  # 34 + 0.1 × (40 − 34) = 34.6 → 35
    b = card.stop_line('amazon', B)  # 同框 4 款 → 同尺寸段 48″：4 + 7 = 11 款，第 10 百分位 = 第 1.0 位 = 15 + 1.0 × (20 − 15)…
    vals = sorted([10, 20, 30, 40, 15, 30, 44, 52, 66, 73, 80])  # 10 15 20 30 30 40 44 52 66 73 80
    assert (b['scope'], b['n'], b['n_frame']) == ('size', 11, 4) and b['value'] == 15  # 第 1.0 位 = 15
    assert '同框只有 4 款，按同尺寸段 11 款算' in b['basis'] and vals[1] == 15
    c = card.stop_line('amazon', C)
    assert (c['value'], c['scope']) == (60, 'fallback') and '用起量线 60 件兜底' in c['basis']
    # 台账：自家整款第 2–3 个月（两个子体合计）70、40 → 平均 55，与停止线 35 比较：未触发；说明写整个父体
    from pdt.models import Forecast
    f = Forecast(stop_conditions=[dict(kind='units_below', value=35, text='上架第 2–3 个月整个父体（所有尺寸、颜色加起来）月销低于 35 件就停')])
    am = {'2026-05': dict(units=60, rating=[]), '2026-06': dict(units=70, rating=[]), '2026-07': dict(units=40, rating=[])}
    st = ledger._stops(f, am, '2026-05')[0]
    assert st['triggered'] is False and st['why'] == '第 2–3 个月整个父体（所有尺寸、颜色加起来）月销平均 55 件'
    # 同口径：卡上的值来自整款（两个子体相加），不是单个子体（单个子体会让 A 的线变成一半）
    assert card._made_families(df[df['frame'] == A], 'amazon', {'bsr_top': 50})[0] == 22.0


# ---------------------------------------------------------------- FLOW-42 白话读法
def test_flow42_plain_readings():
    from pdt.core import card
    assert card.prob_reading(0.42, 0.14, 0.28) == '照这个方向开发新品，估计每 10 个约有 3 个能做到成功线（模型原始算出 4.2，它过去在同类新品上平均多估 1.4，扣掉后是 2.8）'
    assert '平均少估 1.0，加上后是 5.2' in card.prob_reading(0.42, -0.10, 0.52)
    assert card.made_reading('绿', '主色', 7, 2, 20, 10, 0.41) == '同框里带绿的新品 7 个做到 2 个（29%），同框其他主色 50%；样本太少，看不出绿占优势'
    assert card.made_reading('树脂', '台面材质', 30, 21, 60, 15, 0.0001).endswith('差别明显，树脂更容易做到')
    assert card.made_reading('树脂', '台面材质', 30, 12, 60, 25, 0.9).endswith('差别不明显，看不出树脂占优势')
    assert card.band_reading(dict(band='$200–250', median_units=6, max_units=113)) == \
        '$200–250 这档单个链接（子体）每月一般卖 6 件、最多 113 件：这个价位能卖，但单个链接量小，要靠多款或爆款'
    assert card.band_reading(dict(band='$200–250', median_units=25, max_units=214)).endswith('这个价位走量稳')
    assert card.band_reading(dict(band='$300–400', median_units=8, max_units=40)).endswith('这个价位卖得少，要慎重')
    assert 'p = 0.11' in card.p_tip(0.11) and '纯靠运气' in card.p_tip(0.11)


# ---------------------------------------------------------------- FLOW-44 需求范围
def test_flow44_demand_scope():
    from pdt.core.scan import demand_scope

    def m(prev, now):
        return dict(share=now, share_prev=prev, dlog_share=math.log((now + 0.002) / (prev + 0.002)))
    rows = [('24″ · 拆装 · 落地式', '台面材质', 'X', m(.05, .07)), ('30″ · 拆装 · 落地式', '台面材质', 'X', m(.08, .085)),
            ('36″ · 拆装 · 落地式', '台面材质', 'X', m(.04, .041)), ('48″ · 拆装 · 落地式', '台面材质', 'X', m(.02, .015)),
            ('30″ · 拆装 · 落地式', '台面材质', 'Y', m(.1, .1)),
            ('30″ · 拆装 · 落地式', '台面材质', 'Z', m(.1, .1)), ('36″ · 拆装 · 落地式', '台面材质', 'Z', m(.02, .018)),
            ('30″ · 整装 · 落地式', '台面材质', 'Z', m(.01, .3))]  # 不同拆装：不算
    d = demand_scope(rows)
    x = d[('30″ · 拆装 · 落地式', '台面材质', 'X')]
    assert x['kind'] == '可拓展' and x['sizes'] == ['24″'] and x['text'] == '可拓展到 24″'  # 平均 (7 + 8.5 + 4.1 + 1.5) ÷ 4 = 5.3%
    assert '24″ 份额 5.0% → 7.0%，在涨' in x['tip'] and '48″ 份额 2.0% → 1.5%，在跌' in x['tip']
    assert d[('30″ · 拆装 · 落地式', '台面材质', 'Y')]['text'] == '细分需求'
    assert d[('30″ · 拆装 · 落地式', '台面材质', 'Z')]['text'] == '细分需求'
    assert d[('36″ · 拆装 · 落地式', '台面材质', 'Z')]['text'] == '可拓展到 30″'


# ---------------------------------------------------------------- FLOW-47 / FLOW-46 小平台框门槛与样本少、主图可选列
def _research_frames(with_image=True):
    from pdt.core import research as R
    P, M = [], []
    months = [f'2026-{i:02d}' for i in range(1, 11)]
    for size, per in (('30″', 260), ('28″', 150), ('36″', 90)):
        for k in range(3):
            pid = f'{size[:2]}{k}'
            row = dict(渠道='Home Depot', fam=f'F{pid}', pid=pid, title=f'{size} Vanity {k}', 来源='两词', 尺寸段=size, 装='整装', 形态='落地式',
                       台面材质='岗石' if k else '石英石', 主色='白', 柜体材质='MDF', 元素='夏克式', 价格=300, 评分=4.5, 页面评论数=10)
            if with_image:
                row['主图'] = f'https://images.example.com/{pid}.jpg' if k else ''
            P.append(row)
            for mth in months:
                M.append(dict(渠道='Home Depot', fam=f'F{pid}', pid=pid, 尺寸段=size, 装='整装', 形态='落地式', 月=mth, VP=1, 非VP=0, 销量=per / 3))
    P, M = pd.DataFrame(P).astype(str), pd.DataFrame(M).astype(str)
    assert R.check(P, M) == []
    return R.normalize(P, M)


def test_flow47_small_platform_threshold_and_small_label(app_env, monkeypatch):
    from pdt import catconfig
    from pdt.core import research as R
    monkeypatch.setattr(R, 'today', lambda: date(2026, 11, 5))
    P, M = _research_frames()
    d = R.compute('homedepot', P, M, with_amazon=False, conf={}, noframe=set())
    fr = {f['frame']: f for f in d['frames']}
    assert set(fr) == {'30″ · 整装 · 落地式', '28″ · 整装 · 落地式'}
    assert fr['30″ · 整装 · 落地式']['read'] == 'ok' and fr['28″ · 整装 · 落地式']['read'] == 'small'
    assert d['summary']['small_n'] == 1 and d['summary']['frame_min'] == 100 and d['summary']['frames_readable'] == 1
    assert d['units']['28″ · 整装 · 落地式']  # 样本少的框照常有单元指标
    assert d['summary']['n_images'] == 6  # 9 个商品里 6 个带主图（每尺寸段第 1 个为空）
    _, cfg = catconfig.current()
    cfg['research']['frame_min']['homedepot'] = 160
    catconfig.save(cfg, None)
    d = R.compute('homedepot', P, M, with_amazon=False, conf={}, noframe=set())
    assert [f['frame'] for f in d['frames']] == ['30″ · 整装 · 落地式'] and d['summary']['frame_min'] == 160
    assert catconfig.current()[1]['scan']['min_frame_units'] == 200  # Amazon 机会扫描门槛不变
    P2, M2 = _research_frames(with_image=False)
    assert R.check(P2, M2) == [] and R.compute('homedepot', P2, M2, with_amazon=False, conf={}, noframe=set())['summary']['n_images'] == 0


def test_flow46_tagging_card_image_from_research(wen, monkeypatch):
    """F28 其他渠道商品没有图时按渠道 + 编号取调研主图（AC-F18-12）；对不上的显示无图提示与商品页链接（AC-F18-13）。"""
    from pdt.core import research as R
    from pdt.db import session
    from pdt.models import Product, Tag
    monkeypatch.setattr(R, 'image_map', lambda ch: {'W111999433': 'https://images.example.com/w1.jpg'} if ch == 'wayfair' else {})
    with session() as s:
        for iid, title in (('W111999433 (piid 1959543287)', 'Wayfair vanity with image'), ('W222', 'Wayfair vanity no image')):
            s.add(Product(channel='wayfair', item_id=iid, title=title, brand='测试', series=iid))
            s.add(Tag(channel='wayfair', item_id=iid, tag='主色', value='白', auto_value='白', status='queued', source='rule', confidence=0.5,
                      img_group='s' + iid[:6]))
    h = wen.get('/tagging?channel=wayfair').text
    assert 'src="https://images.example.com/w1.jpg"' in h and 'data-zoom="https://images.example.com/w1.jpg"' in h
    assert '没有主图，<br>点商品链接<br>去商品页看' in h and 'keyword=W222' in h and 'target="_blank"' in h


# ---------------------------------------------------------------- FLOW-43 四个渠道段（调研行、按月柱、代表产品）
def test_flow43_card_channel_section(wen, monkeypatch):
    import re
    import decision_seed as ds
    from pdt.core import research as R
    from pdt.db import session
    from pdt.models import Batch, Snapshot
    ds.seed_all()
    real = R.unit_view
    months = [f'26-{i:02d}' for i in range(1, 11)]

    def fake_view(ch, frame, attr, value):
        if ch == 'wayfair':
            return dict(state='ok', read='ok', window='2026-01 至 2026-10', months=months, frame_units=900, units=120, families=9, share=0.12,
                        share_pre=0.139, share_rec=0.105, series=[.14, .15, .13, None, .118, .11, .108, .105, .104, .106], reason=None)
        return real(ch, frame, attr, value)
    prods = [dict(fam=f'F{k}', pid=f'W{k}', title=f'Wayfair 树脂浴室柜 {k}', brand='测试牌', price=259.0, rating=4.4, reviews=120.0,
                  image='https://images.example.com/w.jpg' if k else '', link=f'https://www.wayfair.com/keyword.php?keyword=W{k}', units=60.0 - k,
                  listed='2026-07' if k == 4 else '', listed_kind='首评月', series=[5, None, 7, 8, 9, 10, 11, 12, 13, 14], months=months,
                  new=k == 4, sold=k == 4) for k in range(6)]
    monkeypatch.setattr(R, 'unit_view', fake_view)
    monkeypatch.setattr(R, 'unit_products', lambda ch, *a, **k: dict(top=prods[:5], new=[p for p in prods if p['new']], per_family=40.0))
    with session() as s:
        before = (s.query(Batch).count(), s.query(Snapshot).count())
    r = wen.post('/cards', data=dict(channel='amazon', frame=ds.FRAME, attr='台面材质', value='树脂'), headers={'accept': 'application/json'})
    cid = r.json()['id']
    h = wen.get(f'/cards/{cid}').text
    s1 = h.split('id="s1"')[1].split('id="s2"')[0]
    wf = s1.split('data-channel="wayfair"')[1].split('</tr>')[0]
    assert '13.9%' in wf and '10.5% ↓' in wf and 'class="bad"' in wf and '历史观察' in wf and '只作观察' in wf and '9 款' in wf
    assert wf.count('<rect') == 9 and '>04<' in wf  # 10 个月里 1 个月没数据：只有月份标签，不画柱、不写 0
    lw = s1.split('data-channel="lowes"')[1].split('</tr>')[0]
    assert '尚未导入渠道调研' in lw and '%' not in lw.split('</td>')[1]
    prod = s1.split('data-prod-ch="wayfair"')[1].split('</details>')[0]
    assert prod.count('class="prod"') == 6 and '没有主图' in prod and 'data-zoom="https://images.example.com/w.jpg"' in prod
    assert '卖起来了' in prod and 'target="_blank"' in prod and '首评月 2026-07' in prod
    am = s1.split('data-prod-ch="amazon"')[1].split('</details>')[0]
    assert 'JUMMICO' in am and 'class="prod"' in am
    assert re.search(r'th-q[^>]*data-tip="按月柱状图', s1)
    with session() as s:
        assert (s.query(Batch).count(), s.query(Snapshot).count()) == before  # 不写 F28 分析库
    s2 = h.split('id="s2"')[1].split('id="s3"')[0]
    assert '照这个方向开发新品，估计每 10 个约有' in s2 and 'p = ' not in re.sub(r'data-tip="[^"]*"', '', s2)
    s3 = h.split('id="s3"')[1].split('id="s4"')[0]
    assert '整个父体（所有尺寸、颜色加起来）月销低于' in s3 and '依据：' in s3


# ---------------------------------------------------------------- FLOW-48 模型与回测白话
def test_flow48_models_page_plain_language(wen):
    from pdt.db import session
    from pdt.models import Batch, ModelRun
    with session() as s:
        s.add(Batch(channel='amazon', month='2026-09', source='api', status='merged', rows=10))
        s.add(ModelRun(month='2026-09', valid=True, valid_msg='',
                       backtest={'T0': '2026-01', 'window': '2026-07 至 09',
                                 'grades': [{'grade': 'A', 'n': 9, 'up': 0.78, 'extra': 1840, 'median': 35}, {'grade': 'D', 'n': 89, 'up': 0.19, 'extra': -2210, 'median': -12}],
                                 'grasp_bins': [{'bin': '≤30%', 'n': 64, 'n300': 18, 'up': 0.25, 'extra': -980}, {'bin': '≥70%', 'n': 27, 'n300': 11, 'up': 0.72, 'extra': 1520}],
                                 'coef': {'b6': {'b': 0.757, 'c': 0.317, 'k6': 1.39, 'k8': 1.7}, 'x2': {'b': -0.105, 'c': -0.076, 'k6': -0.258, 'k8': -0.309},
                                          '截距': {'b': -0.056, 'c': -0.034}},
                                 'side': [], 'rho': {'grasp': 0.28, 'grasp300': 0.51, 'extra': 0.33, 'extra300': 0.44},
                                 'valid_detail': {'d_up': 0.19, 'd_n': 89, 'd_ok': True, 'mono': True, 'bins': [0.25, 0.72]}},
                       market={'n_units': 2, 'grades': {'A': 1, 'D': 1}},
                       newlayer={'rows': [{'T0': '2025-10', 'n_train': 107, 'n_test': 15, 'actual': 4.0, 'auc': 0.45, 'top30': 4.0, 'bottom30': 6.0,
                                           'mean_a': 5.4, 'mean_b': 5.2, 'mean_c': 7.4, 'use': '检验', 'small': True}],
                                 'bias': {'bias': 0.14, 'pred': 0.47, 'actual': 0.33, 'n': 140, 'parts': [], 'mae': {'a': 0.12, 'b': 0.12, 'c': 0.25}, 'chosen': 'a'}}))
    h = wen.get('/models').text
    assert 'data-plain="b6">份额最近半年在涨的单元，之后更可能继续变大；这一项影响最大' in h
    assert 'data-plain="x2">新进来的款越多的单元，之后反而更不容易变大' in h and '所有单元共同的起点，不用单独看' in h
    assert '最近一批新品，模型估计每 10 个能成 4.7 个，实际只成了 3.3 个，模型偏乐观，所以决策卡上把模型估计往下调 1.4' in h
    assert '平均每 10 个差 1.2 个' in h and '平均绝对误差' not in h
    assert '<span class="bad">0.45 比瞎猜还差</span>' in h and '高分组没比低分组好' in h and '能不能分出好坏' in h
    assert '把握 ≥70% 的那批之后真有 72% 份额变大' in h
    foot = h.split('data-rho-reading>')[1].split('</div>')[0]
    assert foot.startswith('把握和实际变化方向基本一致，月销 ≥ 300 件的大单元更一致') and '+0.28' in foot.split('data-tip=')[1]
    assert 'A 档之后真有 78% 份额变大，D 档只有 19%' in h


def test_flow46_image_index_import(wen):
    """主图索引（渠道、商品编号、主图URL）一次性导入：给其他渠道没有图的商品补图；Wayfair 带 piid 的编号按去括号后匹配；已有图不改；缺列拒绝。"""
    from pdt.core import research as R
    from pdt.db import session
    from pdt.models import Product
    with session() as s:
        s.add(Product(channel='homedepot', item_id='335644797', title='HD 1'))
        s.add(Product(channel='wayfair', item_id='W111999433 (piid 1959543287)', title='WF 1'))
        s.add(Product(channel='lowes', item_id='5017604281', title='LW 1', image_url='https://old.example.com/a.jpg'))
    csv = ('渠道,商品编号,主图URL,来源,编号来自\nHome Depot,335644797,https://images.example.com/hd.jpg,商品页,三平台_商品表\n'
           'Wayfair,W111999433,https://images.example.com/wf.jpg,商品页,渠道VP\nLowe\'s,5017604281,https://images.example.com/lw.jpg,商品页,三平台_商品表\n').encode('utf-8-sig')
    r = wen.post('/data/research/images', files={'index': ('主图索引.csv', csv, 'text/csv')}, follow_redirects=False)
    assert r.status_code == 303 and 'kind=error' not in r.headers['location']
    with session() as s:
        img = {p.item_id: p.image_url for p in s.query(Product).all()}
    assert img['335644797'] == 'https://images.example.com/hd.jpg' and img['W111999433 (piid 1959543287)'] == 'https://images.example.com/wf.jpg'
    assert img['5017604281'] == 'https://old.example.com/a.jpg'
    assert R.import_image_index('渠道,商品编号\nHome Depot,1\n'.encode())['missing'] == ['主图URL']
