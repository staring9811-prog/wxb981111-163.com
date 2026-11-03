"""Amazon 月度数据（PAGE-F17-01）：拉取、断点续拉、核对、并入、历史重放。"""
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select

from conftest import login_as, make_user
from v2fixture import FakeSellerSprite, api_rows, export_xlsx, set_secret, v2  # noqa: F401

from pdt import services
from pdt.db import session
from pdt.models import Batch, Budget, CostRecord, Job, Product, Snapshot


def _prev_month():
    t = date.today()
    i = t.year * 12 + t.month - 2
    return f'{i // 12}-{i % 12 + 1:02d}'


def _pull(c, month):
    j = c.post('/data/amazon/pull', data={'month': month}).json()
    return c.post(f"/jobs/{j['id']}/confirm").json()


def test_pull_fields_and_resume(wen):
    """FLOW-04：默认上一个自然月；确认费用后拉取，含 12 个字段；中途中断后重拉只请求缺的分片，页面显示“第 1 次 / 续拉”。"""
    month = _prev_month()
    page = wen.get('/data/amazon').text
    assert f'<option value="{month}" selected>{month}（上一个自然月）' in page
    set_secret('sellersprite')
    fake = FakeSellerSprite({month: api_rows(month, 230)}, fail_at=2)
    services.set_fake('sellersprite', fake)
    j = _pull(wen, month)
    assert j['status'] == 'failed' and '网络超时' in j['error']
    assert fake.calls == [(month, 1), (month, 2)]
    with session() as s:
        assert s.scalar(select(func.count()).select_from(CostRecord)) == 1  # 只有成功的第 1 页计费
    j2 = _pull(wen, month)  # 重新拉取：新任务，只拉缺的分片
    assert j2['status'] == 'done', j2
    assert fake.calls[2:] == [(month, 2), (month, 3), (month, 4)]  # 第 1 页没有再请求
    with session() as s:
        b = s.scalar(select(Batch).where(Batch.month == month, Batch.source == 'api'))
        assert b.rows == 230
        sn = s.scalar(select(Snapshot).where(Snapshot.batch_id == b.id, Snapshot.item_id == 'B0SYN00000'))
        p = s.scalar(select(Product).where(Product.item_id == 'B0SYN00000'))
        # AC-F17-01 的 12 个字段：ASIN、父体、品牌、价格、月销、小类排名、评分、评分数、上架日期、变体、图片、链接
        assert (sn.item_id, p.parent, p.brand, sn.price, sn.raw['fam_units'], sn.rank, sn.rating, sn.ratings_count) == \
               ('B0SYN00000', 'B0FAM00000', 'Yaheetech', 199.99, 300.0, 1.0, 4.0, 120.0)
        assert p.listed_at == '2025-06-15'[:10] or p.listed_at == '2026-05-02'
        assert sn.raw['variations'] == 3.0 and p.image_url.startswith('https://m.media-amazon.com/') and p.link == 'https://www.amazon.com/dp/B0SYN00000'
    html = wen.get(f'/data/amazon?batch={b.id}').text
    assert '第 1 次' in html and '第 2 次 · 续拉' in html and '已拉部分未重复调用' in html


def test_cap_resume_no_duplicate_calls_single_task(wen):
    """RULE-04：上限只够一半分片时停止且保留已拉；续拉时已完成分片 0 次调用、0 条新增费用；同一月份重复发起只生成一个任务；累计不超上限。"""
    month = '2026-10'
    set_secret('sellersprite')
    fake = FakeSellerSprite({month: api_rows(month, 380)})  # 4 页数据 + 1 个空页
    services.set_fake('sellersprite', fake)
    with session() as s:
        s.add(Budget(service='sellersprite', cap=2, unit='calls'))
    a = wen.post('/data/amazon/pull', data={'month': month}).json()
    b = wen.post('/data/amazon/pull', data={'month': month}).json()
    assert a['id'] == b['id']  # 重复点击只生成一个任务
    j = wen.post(f"/jobs/{a['id']}/confirm").json()
    assert j['status'] == 'stopped_cap' and len(fake.calls) == 2
    with session() as s:
        assert s.scalar(select(func.coalesce(func.sum(CostRecord.qty), 0))) <= 2  # 任何时刻不超上限
        s.get(Budget, 'sellersprite').cap = 100
    before = len(fake.calls)
    j = wen.post(f"/jobs/{a['id']}/confirm").json()
    assert j['status'] == 'done'
    new_calls = fake.calls[before:]
    assert all(p not in (1, 2) for _, p in new_calls)  # 已完成分片续拉 0 次调用
    assert sorted(p for _, p in fake.calls) == [1, 2, 3, 4, 5]
    with session() as s:
        assert s.scalar(select(func.count()).select_from(CostRecord)) == 5  # 每页只计费一次
        assert s.scalar(select(func.count()).select_from(Batch).where(Batch.month == month)) == 1
    # 两个任务同时被确认（重复发起）：第二个不再调用外部服务、不建第二个批次
    from pdt import costgate
    j1 = costgate.estimate('amazon_pull', {}, None, month='2026-09')
    j2 = costgate.estimate('amazon_pull', {}, None, month='2026-09')
    fake.month_rows['2026-09'] = api_rows('2026-09', 120)
    n0 = len(fake.calls)
    costgate.confirm(j1.id, None)
    n1 = len(fake.calls)
    costgate.confirm(j2.id, None)
    assert len(fake.calls) == n1 and n1 - n0 == 3
    with session() as s:
        assert s.scalar(select(func.count()).select_from(Batch).where(Batch.month == '2026-09')) == 1
        assert (s.get(Job, j2.id).progress or {}).get('duplicate')


def test_verify_suspect_anomaly_normal(wen, tmp_path):
    """FLOW-05：(a) 排名与上月相同 > 10% → 疑似月份错误、不并入；(b) 总月销超 ±30% → 异常，显示三项核对与阈值，确认前不并入，确认后带 * 与原因；(c) 正常批次直接并入。"""
    def up(month, path):
        with open(path, 'rb') as f:
            return wen.post('/data/amazon/upload', data={'month': month}, files={'file': (path.name, f, 'application/octet-stream')}, follow_redirects=False)
    r = up('2026-07', export_xlsx(tmp_path / '浴室柜_类目选品_2026-07.xlsx', '2026-07'))
    with session() as s:
        b0 = s.scalar(select(Batch).where(Batch.month == '2026-07'))
    assert b0.status == 'ok'
    wen.post(f'/data/batches/{b0.id}/merge')
    # (a) 实为上月的数据：排名完全相同
    up('2026-08', export_xlsx(tmp_path / '浴室柜_类目选品_2026-08_误标.xlsx', '2026-08'))
    with session() as s:
        ba = s.scalar(select(Batch).where(Batch.month == '2026-08').order_by(Batch.id.desc()))
    assert ba.status == 'suspect_month' and '小类排名完全相同' in ba.anomaly_reason
    r = wen.post(f'/data/batches/{ba.id}/merge', follow_redirects=False)
    assert '%E7%96%91%E4%BC%BC' in r.headers['location']  # “疑似…不能并入”
    with session() as s:
        assert s.get(Batch, ba.id).status == 'suspect_month'
    html = wen.get(f'/data/amazon?batch={ba.id}').text
    assert '疑似月份错误，未并入分析' in html and '确认异常并入' not in html
    # (b) 品类总月销 +80%：异常
    up('2026-08', export_xlsx(tmp_path / '浴室柜_类目选品_2026-08.xlsx', '2026-08', rank_shift=7, units_scale=1.8))
    with session() as s:
        bb = s.scalar(select(Batch).where(Batch.month == '2026-08').order_by(Batch.id.desc()))
    assert bb.status == 'anomaly'
    keys = {i['key']: i for i in bb.checks['items']}
    assert keys['total_change']['result'] == 'anomaly' and keys['total_change']['threshold'] == '±30% 内'
    assert keys['family_consistency']['threshold'] == '≥ 90%' and keys['tag_coverage']['threshold'] == '每项 ≥ 95%'
    html = wen.get(f'/data/amazon?batch={bb.id}').text
    assert '品类总月销变化' in html and '家族键月间一致率' in html and '标签覆盖率' in html and '确认异常并入' in html
    wen.post(f'/data/batches/{bb.id}/merge')  # 未确认 → 不并入
    with session() as s:
        assert s.get(Batch, bb.id).status == 'anomaly'
    wen.post(f'/data/batches/{bb.id}/merge', data={'confirm': '1', 'note': '卖家精灵 8 月起口径调整，抽查 20 个家族属实'})
    with session() as s:
        bb = s.get(Batch, bb.id)
    assert bb.status == 'merged' and bb.star and '品类总月销较上月' in bb.anomaly_reason and '抽查 20 个家族属实' in bb.anomaly_reason
    hist = wen.get('/data/amazon').text
    assert '2026-08</a><span class="star">*</span>' in hist
    from pdt.core import panel
    tl = panel.load_panel('amazon')
    assert tl[tl['month'] == '2026-08']['star'].all() and not tl[tl['month'] == '2026-07']['star'].any()
    scan = wen.get('/scan?month=2026-08').text
    assert '月份带 * 标记' in scan and '品类总月销较上月' in scan
    # (c) 正常批次
    up('2026-09', export_xlsx(tmp_path / '浴室柜_类目选品_2026-09.xlsx', '2026-09', rank_shift=3, units_scale=1.85))
    with session() as s:
        bc = s.scalar(select(Batch).where(Batch.month == '2026-09'))
    assert bc.status == 'ok'
    wen.post(f'/data/batches/{bc.id}/merge')
    with session() as s:
        assert s.get(Batch, bc.id).status == 'merged' and not s.get(Batch, bc.id).star


def test_upload_missing_column(wen, tmp_path):
    """FLOW-05（错误态）：上传文件缺“小类排名”列时阻断并指出列名。"""
    import pandas as pd
    p = tmp_path / '浴室柜_类目选品_缺列.xlsx'
    pd.DataFrame([{'ASIN': 'B0SYN00001', '月销量': 120, '价格($)': 239.99}]).to_excel(p, index=False)
    with open(p, 'rb') as f:
        r = wen.post('/data/amazon/upload', data={'month': '2026-10'}, files={'file': (p.name, f)}, follow_redirects=True)
    assert '缺少“小类排名”列' in r.text


def test_misdated_real_file(v2):
    """FLOW-05 (a)：wen 曾误标的“2026-10”文件（内容为 9 月）标“疑似月份错误”、不并入。"""
    from pdt.core import seed
    if not seed.SUSPECT.exists():
        pytest.skip('本机没有待核 2026-10 文件')
    with open(seed.SUSPECT, 'rb') as f:
        v2.post('/data/amazon/upload', data={'month': '2026-10'}, files={'file': ('2026-10_full_data.csv', f)})
    with session() as s:
        b = s.scalar(select(Batch).where(Batch.channel == 'amazon', Batch.month == '2026-10'))
        assert b.status == 'suspect_month'
        items = {i['key']: i for i in b.checks['items']}
    assert items['rank_same']['pct'] > 90 and items['purchase_label']['result'] == 'block'
    assert '2026-10 疑似月份错误，未并入分析' in v2.get('/data/amazon').text


def test_history_replay(v2, tmp_path):
    """RULE-07：并入多个月后回看历史月份 2026-01 的扫描与评分可重放、与当时保存的一致；原始文件与并入版本保留；带 * 的月份仍显示原异常原因。"""
    from pdt.core import pipeline
    from pdt.models import ModelRun, Opportunity, UnitScore
    pipeline.rescan('amazon', '2026-01')
    with session() as s:
        first = {(o.frame, o.attr, o.value): o.metrics for o in s.scalars(select(Opportunity).where(Opportunity.channel == 'amazon', Opportunity.month == '2026-01'))}
    rid = pipeline.rescore(None, '2026-01')
    with session() as s:
        r0 = s.get(ModelRun, rid)
        sc0 = {(u.frame, u.attr, u.value): u.data for u in s.scalars(select(UnitScore).where(UnitScore.run_id == rid))}
    assert first and r0.month == '2026-01' and sc0
    # 再并入一个新月份（2026-10，合成上传）
    p = export_xlsx(tmp_path / '浴室柜_类目选品_2026-10.xlsx', '2026-10', n=200, rank_shift=5)
    with open(p, 'rb') as f:
        v2.post('/data/amazon/upload', data={'month': '2026-10'}, files={'file': (p.name, f)})
    with session() as s:
        b = s.scalar(select(Batch).where(Batch.channel == 'amazon', Batch.month == '2026-10'))
    v2.post(f'/data/batches/{b.id}/merge', data={'confirm': '1', 'note': '合成月份'})
    with session() as s:
        assert s.get(Batch, b.id).status == 'merged'
    pipeline.rescan('amazon', '2026-01')
    with session() as s:
        again = {(o.frame, o.attr, o.value): o.metrics for o in s.scalars(select(Opportunity).where(Opportunity.channel == 'amazon', Opportunity.month == '2026-01'))}
    assert again == first
    rid2 = pipeline.rescore(None, '2026-01')
    with session() as s:
        sc1 = {(u.frame, u.attr, u.value): u.data for u in s.scalars(select(UnitScore).where(UnitScore.run_id == rid2))}
        assert sc1.keys() == sc0.keys()
        for k in sc0:
            a, b_ = sc0[k], sc1[k]
            assert (a['grasp'], a['grade'], a['pred_share']) == (b_['grasp'], b_['grade'], b_['pred_share']), k
        star = s.scalar(select(Batch).where(Batch.channel == 'amazon', Batch.month == '2026-07', Batch.status == 'merged'))
        assert star.star and '数据来源切换（v11 表）' in star.anomaly_reason
    assert Path(b.file_path).exists()  # 上传的原始文件保留
    html = v2.get('/data/amazon').text
    assert '数据来源切换（v11 表），家族键月间一致率' in html
    assert v2.get('/scan?month=2026-01').status_code == 200


def test_data_page_operator_only(client):
    """PAGE-F17-01 权限：只读角色无入口，直接访问显示无权限。"""
    make_user('lixiaomei', '李晓梅', 'readonly')
    login_as(client, 'lixiaomei', '密码-123456')
    r = client.get('/data/amazon')
    assert r.status_code == 403 and '无权限' in r.text


def test_real_raw_month_not_misdated(wen):
    """FLOW-05 (c)：正常的卖家精灵原始月度导出（2025-03，购买标日期分散在 2023-12 至 2025-04）不能被判为月份错误。
    期望依据：该文件确为 2025-03 数据（第二轮已核对），购买标常年不更新，只有最新日期反映导出月份。"""
    from pdt.core import seed
    f = seed.D2 / 'sellersprite_zip_2025-03_2025-12' / '2025-03_full_data.csv'
    if not f.exists():
        pytest.skip('本机没有第二轮原始月度导出')
    with open(f, 'rb') as fh:
        wen.post('/data/amazon/upload', data={'month': '2025-03'}, files={'file': (f.name, fh)})
    with session() as s:
        b = s.scalar(select(Batch).where(Batch.channel == 'amazon', Batch.month == '2025-03'))
        items = {i['key']: i for i in b.checks['items']}
    assert items['purchase_label']['result'] == 'pass', items['purchase_label']
    assert b.status != 'suspect_month'


def test_history_shows_total_for_unmerged_batch(wen, tmp_path):
    """DESIGN-06（补）：被拦截（疑似月份错误）的批次在“历史月份”表里也显示本批品类总月销并标“未并入”，与核对表“品类总月销变化”的本批数一致。"""
    import re

    def up(month, path):
        with open(path, 'rb') as f:
            return wen.post('/data/amazon/upload', data={'month': month}, files={'file': (path.name, f, 'application/octet-stream')}, follow_redirects=False)
    up('2026-09', export_xlsx(tmp_path / '浴室柜_类目选品_2026-09.xlsx', '2026-09'))
    with session() as s:
        b0 = s.scalar(select(Batch).where(Batch.month == '2026-09'))
    wen.post(f'/data/batches/{b0.id}/merge')
    up('2026-10', export_xlsx(tmp_path / '浴室柜_类目选品_2026-10_误标.xlsx', '2026-10'))
    with session() as s:
        ba = s.scalar(select(Batch).where(Batch.month == '2026-10'))
        assert ba.status == 'suspect_month'
        snap_total = s.scalar(select(func.sum(Snapshot.units)).where(Snapshot.batch_id == ba.id))
        check_total = next(i['cur_total'] for i in ba.checks['items'] if i['key'] == 'total_change')
    assert round(snap_total) == round(check_total) > 0
    html = wen.get('/data/amazon').text
    hist = html.split('id="t-hist"')[1]
    row = re.search(r'href="/data/amazon\?batch=%d">2026-10</a>.*?</tr>' % ba.id, hist, re.S).group(0)
    assert f'{check_total:,.0f}<span class="etag">估算</span><span class="etag etag--nodata">未并入</span>' in row
    assert '无数据' not in row
    assert f'{check_total:,.0f} 件 vs' in wen.get(f'/data/amazon?batch={ba.id}').text  # 核对表同一个数
