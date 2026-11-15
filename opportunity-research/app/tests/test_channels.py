"""其他渠道数据（PAGE-F28-01）：上传追踪器导出 / 评论追踪并入、未完整月只参考、按评论 ID 去重、两种估算方法。"""
import pytest
from sqlalchemy import func, select

from pdt import catconfig
from pdt.db import session
from pdt.models import Batch, ChannelReview, Snapshot, Tag

from pdt.core import seed

VP = seed.VP_XLSX


def _upload(c, path):
    with open(path, 'rb') as f:
        return c.post('/data/channels/import', files={'file': (path.name, f)}, follow_redirects=True)


def test_upload_wen_vp_export(wen):
    """FLOW-24：上传 wen 的 浴室柜_2026_渠道VP_20261103.xlsx：11 月只作参考不计入；按评论 ID 去重的合计与文件一致；
    任一商品估算月销 = VP × 50 + 非 VP × 20 并注明方法与系数。"""
    if not VP.exists():
        pytest.skip('本机没有 渠道VP/浴室柜_2026_渠道VP_20261103.xlsx')
    r = _upload(wen, VP)
    assert '已并入' in r.text and '1 个月只作参考' in r.text
    from pdt.core import channels, panel
    summ = channels.summary()
    # 契约期望（按评论 ID 去重）：HD 3,325、Lowe's 3,850、Wayfair 7,394 —— 文件“去重评论数”列，含 11 月未完整的 2 / 0 / 21 条
    assert {c: round(summ[c]['reviews_all']) for c in summ} == {'homedepot': 3325, 'lowes': 3850, 'wayfair': 7394}
    # 1–10 月完整月（计入分析）：文件“1-10月 合计”去重数 3,323 / 3,850 / 7,373
    assert {c: round(summ[c]['reviews_complete']) for c in summ} == {'homedepot': 3323, 'lowes': 3850, 'wayfair': 7373}
    with session() as s:
        ref = {b.channel: b.status for b in s.scalars(select(Batch).where(Batch.month == '2026-11'))}
        assert ref == {'homedepot': 'reference', 'lowes': 'reference', 'wayfair': 'reference'}
        # 商品去重分摊后，渠道 × 月合计 = 文件按评论 ID 去重的合计（HD 2026-01：VP 229、非 VP 54）
        vp = sum(sn.raw['vp_d'] for sn in s.scalars(select(Snapshot).where(Snapshot.channel == 'homedepot', Snapshot.month == '2026-01')))
        nv = sum(sn.raw['nonvp_d'] for sn in s.scalars(select(Snapshot).where(Snapshot.channel == 'homedepot', Snapshot.month == '2026-01')))
        assert round(vp) == 229 and round(nv) == 54
        sn = s.scalar(select(Snapshot).where(Snapshot.channel == 'homedepot', Snapshot.month == '2026-03', Snapshot.item_id == '203486567'))
        assert (sn.vp, sn.nonvp) == (29, 2)  # 商品页上看到的数
        exp_units = sn.raw['vp_d'] * 50 + sn.raw['nonvp_d'] * 20
        # 新商品已按商品 ID 与渠道关联打标
        assert s.scalar(select(func.count()).select_from(Tag).where(Tag.channel == 'homedepot', Tag.item_id == '203486567')) == 8
    p = panel.load_panel('homedepot')
    assert p['month'].max() == '2026-10'  # 11 月不计入
    row = p[(p['item_id'] == '203486567') & (p['month'] == '2026-03')].iloc[0]
    assert row['units'] == pytest.approx(exp_units) and row['尺寸段'] == '24″'
    html = wen.get('/data/channels').text
    assert '评论换算 VP×50 + 非 VP×20' in html and '2026-11 未完整，只作参考' in html and '3,325' in html


def _rows(channel, n_items, months=('2026-09', '2026-10', '2026-11'), shared=3):
    """评论 VP 追踪的商品行：前 shared 个商品是同一系列（共享同一批评论 ID）。"""
    rows = []
    titles = ['Glacier Bay Brindley 36 in. Single Sink Freestanding Bath Vanity in Natural Oak with White Cultured Marble Top',
              'Home Decorators Collection Sonoma 48 in. Double Sink Bath Vanity in Gray with Carrara Marble Top',
              'allen + roth Presley 30 in. White Undermount Single Sink Bathroom Vanity with Engineered Stone Top']
    for i in range(n_items):
        revs = []
        sid = 'SER' if i < shared else f'P{i}'
        for mi_, m in enumerate(months):
            for k in range(2 + max(0, n_items - i) // 2):  # 排名越靠前评论越多
                revs.append({'评论ID': f'{channel}-{sid}-{m}-{k}', '评论日期': f'{m}-1{k % 9}', 'VP状态': 'VP' if k % 3 else 'non_VP', '评分': 5 - (k % 3)})
        rows.append({'平台': {'homedepot': 'HomeDepot', 'lowes': 'Lowes', 'wayfair': 'Wayfair'}[channel], '商品ID': f'{channel[:2].upper()}{1000 + i}',
                     '品牌': 'Glacier Bay', '标题': titles[i % 3], '排名': i + 1, '价格': 399 + i, 'reviews': revs, '入口': '带台面'})
    return rows


def test_tracker_ingest_dedup_by_review_id(wen):
    """FLOW-24 / AC-F28-01 / 05：评论 VP 追踪完成采集后并入：按评论 ID 去重（同系列共享评论只算一次），采集日所在月只作参考，新商品关联打标。"""
    from pdt.core import channels, panel
    rows = _rows('homedepot', 12)
    st = channels.ingest_tracker_month(rows, collected_on='2026-11-03')
    assert st['homedepot']['months'] == 2 and st['homedepot']['reference'] == 1
    uniq = {(r['评论ID']) for x in rows for r in x['reviews'] if r['评论日期'][:7] == '2026-10'}
    with session() as s:
        snaps = list(s.scalars(select(Snapshot).where(Snapshot.channel == 'homedepot', Snapshot.month == '2026-10')))
        page_total = sum(sn.vp + sn.nonvp for sn in snaps)
        dedup_total = sum(sn.raw['vp_d'] + sn.raw['nonvp_d'] for sn in snaps)
        assert s.scalar(select(func.count(func.distinct(ChannelReview.review_id))).where(ChannelReview.month == '2026-10')) == len(uniq)
        assert s.scalar(select(func.count()).select_from(Tag).where(Tag.channel == 'homedepot')) == 12 * 8
    assert dedup_total == pytest.approx(len(uniq)) and page_total > dedup_total  # 同系列 3 个商品页重复计了
    summ = channels.summary()['homedepot']
    assert summ['reviews_complete'] == pytest.approx(len({r['评论ID'] for x in rows for r in x['reviews'] if r['评论日期'][:7] < '2026-11'}))
    assert summ['reference'] == ['2026-11']
    assert panel.load_panel('homedepot')['month'].max() == '2026-10'


def test_rank_method_and_min_anchors(wen):
    """FLOW-25：把 Home Depot 估算方法切到“榜单排名平滑”后按排名平滑换算并注明方法；数据页并排对照两种方法；
    同时有排名和评论换算销量的商品少于 10 个的渠道不提供该方法并提示原因。"""
    from pdt.core import channels, panel
    channels.ingest_tracker_month(_rows('homedepot', 14, shared=2), collected_on='2026-11-03')
    channels.ingest_tracker_month(_rows('lowes', 6, shared=0), collected_on='2026-11-03')
    fit, why, n = channels.rank_fit('homedepot')
    assert fit is not None and n == 14 and fit['b'] < 0  # 排名越靠后月销越低
    nf, why2, n2 = channels.rank_fit('lowes')
    assert nf is None and n2 == 6 and '少于 10 个' in why2
    before = panel.load_panel('homedepot').set_index(['item_id', 'month'])['units']
    v, cfg = catconfig.current()
    cfg['channels']['homedepot']['method'] = 'rank'
    cfg['channels']['lowes']['method'] = 'rank'
    catconfig.save(cfg, None)
    after = panel.load_panel('homedepot').set_index(['item_id', 'month'])['units']
    with session() as s:
        sn = s.scalar(select(Snapshot).where(Snapshot.channel == 'homedepot', Snapshot.item_id == 'HO1003', Snapshot.month == '2026-10'))
        assert after[('HO1003', '2026-10')] == pytest.approx(sn.raw['units_rank']) != pytest.approx(before[('HO1003', '2026-10')])
    lw0 = panel.load_panel('lowes')
    assert (lw0['units'] > 0).all()  # 不可用时仍按评论换算
    html = wen.get('/data/channels?ch=homedepot').text
    assert '榜单排名平滑</strong><span class="badge badge--accent">在用' in html and '排名平滑月销' in html
    html = wen.get('/data/channels?ch=lowes').text
    assert '榜单排名平滑法不可用' in html and '只有 6 个（少于 10 个）' in html and '配置为排名平滑，但本渠道不可用' in html
    j = wen.get('/data/channels/estimate', params={'channel': 'lowes'}).json()
    assert j['rank_available'] is False and j['anchors'] == 6


def test_anchor_count_same_on_both_pages_and_diff_sortable(wen):
    """DESIGN-07 / DESIGN-18（补）/ AC-F28-04：其他渠道数据页与品类配置页的“榜单排名平滑可用锚点数”出自同一函数
    （同时有排名和评论换算销量的商品数，少于 10 个不提供）；估算对照表“差异”列可排序。"""
    import re
    from pdt.core import channels
    channels.ingest_tracker_month(_rows('homedepot', 14, shared=2), collected_on='2026-11-03')
    channels.ingest_tracker_month(_rows('lowes', 6, shared=0), collected_on='2026-11-03')
    assert channels.rank_fit('homedepot')[2] == 14 and channels.rank_fit('lowes')[2] == 6
    cat = wen.get('/settings/category', params={'tab': 'ch'}).text
    assert dict(re.findall(r'data-path="channels\.(\w+)\.method".*?data-anchors="(\d+)"', cat, re.S)) == {'homedepot': '14', 'lowes': '6', 'wayfair': '0'}
    assert '可用 · 锚点 14 个' in cat and '锚点不足 10 个，暂不能用排名平滑（现有 6 个）' in cat
    hd = wen.get('/data/channels?ch=homedepot').text
    assert '可用 · 锚点 14 个' in hd and '锚点 14 个 · 按排名列前' in hd
    assert '锚点 6 个 · 按排名列前' in wen.get('/data/channels?ch=lowes').text
    assert re.search(r'<button class="th-sort" type="button" data-sort-diff>差异', hd)
    diffs = re.findall(r'class="t-num [^"]*" data-sort="(-?[\d.]+)">([^<]+)</td></tr>', hd)
    assert len(diffs) == 14 and all(abs(float(a) - float(b.replace('%', ''))) < 0.06 for a, b in diffs)


def test_estimate_tabs_anchor_not_under_topbar(wen):
    """DESIGN-07：切换估算对照页签（链接带 #t-est）后，区块标题与页签条留出顶栏高度，不被吸顶顶栏遮住。"""
    html = wen.get('/data/channels', params={'ch': 'lowes'}).text
    assert 'href="/data/channels?ch=wayfair#t-est"' in html and '<h2 class="section__title" id="t-est">' in html
    css = wen.get('/static/pdt.css').text
    assert '.section__title[id], .panel__title[id] { scroll-margin-top: calc(var(--topbar-h) + var(--space-4)); }' in css


def test_design07_channel_names_range_and_listed_total(wen):
    """DESIGN-07（v8 复核）：并入来源记录里历史回补重建显示中文渠道名（Home Depot），不露出渠道键 homedepot；
    副标题按实际数据范围（各渠道完整月最早至最晚）；月度并入表合计只加表中所列月份，并注明全部完整月合计；
    估算对照商品名不重复品牌（品牌已在标题开头时不再前置）。"""
    import re
    from pdt.config import data_dir
    from pdt.core import channels
    channels.ingest_tracker_month(_rows('homedepot', 6), collected_on='2026-11-03')
    channels.ingest_tracker_month(_rows('wayfair', 4, shared=0), collected_on='2026-11-03')
    # Home Depot 历史回补重建批次：2025-01 至 2025-12，每月去重 VP 10 条、非 VP 2 条
    with session() as s:
        for m in range(1, 13):
            s.add(Batch(channel='homedepot', month=f'2025-{m:02d}', source='backfill', file_path=str(data_dir() / 'backfill' / 'homedepot'),
                        status='merged', checks={'rebuild': True, 'dedup': {'vp': 10, 'nonvp': 2}}, rows=40))
    summ = channels.summary()['homedepot']
    html = wen.get('/data/channels', params={'ch': 'homedepot'}).text
    text = re.sub(r'<[^>]+>', '', html)
    assert '历史回补重建 · Home Depot 回补缓存' in text
    assert not re.search(r'>[^<]*\b(homedepot|lowes|wayfair)\b[^<]*<', html.split('<script', 1)[0])
    assert '2025-01 至 2026-10 · 2 个渠道' in text
    # 所列 12 个月 = 2025-03 至 2026-10（不含 2025-01、02）
    listed = 12 * 10 + summ['reviews_complete'] - 12 * 12
    assert '所列 12 个月合计' in text and '2025-03 至 2026-10 · 去重口径' in text
    assert f'{listed:,.0f}全部 14 个完整月 {summ["reviews_complete"]:,.0f}' in text
    assert 'Glacier Bay Glacier Bay' not in text and 'Glacier Bay Brindley 36 in. Single Sink' in text
