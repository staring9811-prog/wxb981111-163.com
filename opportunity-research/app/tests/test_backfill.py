"""历史回补与历史重建（v8 数据侧）：FLOW-27、FLOW-28、FLOW-29、FLOW-32、RULE-09。

- FLOW-27 / RULE-09 用假 Home Depot 站点（记录每次请求的 URL 与假时钟时间戳；sleep 推进假时钟，不真等）。
- FLOW-28 / FLOW-29 的数值基准来自 solution-v2/开发建议/小平台_HD回测小试.md（2026-11-03 真实采集）；原始缓存
  ../input/data_v2/渠道历史/homedepot/ 不入库，不在时跳过并说明。
"""
import json
import re
from collections import Counter

import pytest

from conftest import login_as
from pdt import costgate, services
from pdt.db import session
from pdt.models import Batch, Job, Product, Snapshot, Tag

J = {"accept": "application/json"}


# ================================================================ 假 Home Depot 站点
class Clock:
    def __init__(self):
        self.t = 0.0

    def sleep(self, dt):
        self.t += dt


class FakeHD:
    """两个类目（带台面 / 无台面），每页 24 个，每 8 个里有 1 个广告位；同一类目里每 3 个相邻商品页是一个评论家族。
    带台面第一个家族（Glacier Bay 人造大理石台面单盆系列）有 900 条评论，超过单一排序 17 页（510 条）上限，但每个星级都在上限内。"""
    BIG = 900

    def __init__(self, clock, n_per_entry=40):
        self.clock = clock
        self.log = []  # (时间, url, 关键参数)
        self.fail = {}  # url 片段 → 还要返回的错误码列表
        self.on_request = None
        self.entries = {}
        sizes = [24, 30, 36, 48, 60]
        self.items, self.fams = {}, {}
        for e, (name, code, pre) in enumerate((('带台面', 'N-5yc1vZcfw5', 31), ('无台面', 'N-5yc1vZcfv9', 32))):
            rows, k = [], 0
            for i in range(n_per_entry + n_per_entry // 7 + 2):
                if i % 8 == 3:
                    rows.append(dict(id=f'{pre}9{i:05d}', sponsored=True))
                    continue
                pid = f'{pre}0{k:05d}'
                fam = f'{pre}-{k // 3}'
                w = sizes[k % 5]
                no_asm = (k % 11 == 10)  # 规格里没有组装字段、标题也没写
                self.items[pid] = dict(fam=fam, w=w, no_asm=no_asm, rank=k + 1,
                                       title=(f'Glacier Bay {w} in. Single Sink Freestanding Bath Vanity in White with Cultured Marble Top'
                                              + ('' if no_asm else ' (Assembled)')) if e == 0 else f'Home Decorators Collection {w} in. Bath Vanity Cabinet without Top in Sage Green')
                self.fams.setdefault(fam, []).append(pid)
                rows.append(dict(id=pid, sponsored=False))
                k += 1
            self.entries[code] = rows
        self.reviews = {}
        for fi, (fam, mem) in enumerate(self.fams.items()):
            n = self.BIG if fi == 0 else 5 + fi % 4
            revs = []
            for j in range(n):
                # 900 条：2023-01 至 2026-10 均匀分布；星级 1–5 各 180 条
                m = 2023 * 12 + (j * 46) // n
                d = f'{m // 12}-{m % 12 + 1:02d}-{(j % 27) + 1:02d}'
                revs.append(dict(Id=f'{fam}-r{j:04d}', SubmissionTime=d + 'T10:00:00.000-05:00', Rating=j % 5 + 1, ProductId=mem[j % len(mem)],
                                 BadgesOrder=['verifiedPurchaser'] if j % 5 != 1 else [], IsSyndicated=False, OriginalProductName=''))
            revs.sort(key=lambda r: r['SubmissionTime'], reverse=True)
            self.reviews[fam] = revs

    # ---- 站点 ----
    def __call__(self, url, body=None):
        self.log.append((self.clock.t, url, json.dumps(body['variables'], sort_keys=True) if body else ''))
        if self.on_request:
            self.on_request(len(self.log))
        for frag, codes in self.fail.items():
            if frag in url + (json.dumps(body) if body else '') and codes:
                return codes.pop(0), b'err'
        if '/federation-gateway/graphql' in url:
            return self._gql(body['variables'])
        m = re.search(r'/p/reviews/x/(\d+)/1', url)
        if m:
            return self._page(m.group(1))
        code = next(c for c in self.entries if c in url)
        off = int((re.search(r'Nao=(\d+)', url) or [0, 0])[1])
        return self._list(self.entries[code][off:off + 24], len(self.entries[code]))

    def _list(self, rows, total):
        refs = json.dumps([{'__ref': f'base-searchNav-{r["id"]}'} for r in rows])
        objs = []
        for r in rows:
            it = self.items.get(r['id'], dict(title='Sponsored vanity', w=30))
            objs.append(f'"base-searchNav-{r["id"]}":' + json.dumps({'identifiers': {'canonicalUrl': f'/p/x/{r["id"]}', 'productLabel': it['title'], 'brandName': 'Glacier Bay'},
                                                                   'info': {'isSponsored': r['sponsored']}, 'pricing({"storeId":"1"})': {'value': 299.0},
                                                                   'reviews': {'ratingsReviews': {'averageRating': '4.5', 'totalReviews': '12'}}}))
        s = '{"totalProducts":%d,"ROOT_QUERY":{"products({\\"filter\\":{\\"a\\":1}})":%s},%s}' % (total, refs, ','.join(objs))
        return 200, s.encode()

    def _page(self, pid):
        it = self.items[pid]
        specs = [{'specName': 'Product Width (in.)', 'specValue': f'{it["w"]} in'}, {'specName': 'Vanity Type', 'specValue': 'Freestanding'},
                 {'specName': 'Cabinet Color Family', 'specValue': 'White'}]
        if not it['no_asm']:
            specs.append({'specName': 'Assembled', 'specValue': 'Assembled'})
        cat = {'details': {'highlights': [], 'description': ''}, 'specificationGroup': [{'specifications': specs}],
               'identifiers': {'productLabel': it['title'], 'brandName': 'Glacier Bay'}, 'pricing({"x":1})': {'value': 299.0}}
        first = self.reviews[it['fam']][:10]
        key = '"reviews({\\"itemId\\":\\"%s\\",\\"startIndex\\":1})":' % pid
        s = '{"base-catalog-%s":%s,%s%s}' % (pid, json.dumps(cat), key, json.dumps({'Results': first}))
        return 200, s.encode()

    def _gql(self, v):
        pid = v['itemId']
        revs = self.reviews[self.items[pid]['fam']]
        f = v['filters'] or {}
        if f.get('starRatings'):
            revs = [r for r in revs if r['Rating'] in f['starRatings']]
        if f.get('isVerifiedPurchase'):
            revs = [r for r in revs if r['BadgesOrder']]
        if v['sortBy'] == 'oldest':
            revs = list(reversed(revs))
        start = v['startIndex']
        if start > 481:  # 单一排序最多 17 页
            return 200, json.dumps({'data': {'reviews': {'TotalResults': len(revs), 'Results': []}}}).encode()
        return 200, json.dumps({'data': {'reviews': {'TotalResults': len(revs), 'Results': revs[start - 1:start + 29]}}}).encode()

    # ---- 统计 ----
    def page_requests(self):
        return Counter(re.search(r'/p/reviews/x/(\d+)/1', u).group(1) for _, u, _ in self.log if '/p/reviews/x/' in u)


@pytest.fixture()
def hd(wen):
    from pdt.core import backfill
    clock = Clock()
    site = FakeHD(clock)
    backfill._FETCHER['homedepot'] = backfill.Polite(transport=site, sleep=clock.sleep)
    yield wen, site, clock, backfill
    backfill._FETCHER.clear()


def _estimate(wen, ch='homedepot', **params):
    r = wen.post('/jobs/estimate', data={'kind': 'channel_backfill', 'target': f'backfill:{ch}', 'params': json.dumps(dict(params, channel=ch))})
    assert r.status_code == 200, r.text
    return r.json()


# ================================================================ FLOW-27
def test_flow27_backfill_cancel_confirm_shard_resume(hd):
    """FLOW-27：取消费用弹窗站点请求数为 0；确认后采到前 N 个商品页（排除广告位）的全部历史评论与规格；超上限的家族按星级分片补采，截断 0；
    中途暂停后续采不重复请求已完成的商品页；进度显示商品页、评论数、分片补采、失败数。"""
    wen, site, clock, backfill = hd
    N = 30
    j = _estimate(wen, start='2024-01', n=N)
    assert j['estimate']['usd_hi'] == 0 and j['estimate']['calls'] > 0 and 'Home Depot' not in (j['estimate'].get('service') or '')
    wen.post(f"/jobs/{j['id']}/cancel")
    assert site.log == []  # 取消：零请求
    with session() as s:
        assert s.get(Job, j['id']).status == 'cancelled'

    # 确认后，跑到第 100 次请求时 wen 点“暂停”
    j = _estimate(wen, start='2024-01', n=N)
    site.on_request = lambda k: costgate.pause(j['id']) if k == 100 else None
    wen.post(f"/jobs/{j['id']}/confirm")
    job = wen.get(f"/jobs/{j['id']}").json()
    assert job['status'] == 'paused'
    before = len(site.log)
    done_pages = {p for p, n in site.page_requests().items()}
    site.on_request = None
    # 续采：同一任务再确认
    wen.post(f"/jobs/{j['id']}/confirm")
    job = wen.get(f"/jobs/{j['id']}").json()
    assert job['status'] == 'done', job
    after = site.log[before:]
    assert not [u for _, u, _ in after if '/p/reviews/x/' in u and re.search(r'/x/(\d+)/1', u).group(1) in done_pages]  # 已完成商品页 0 次请求
    assert max(site.page_requests().values()) == 1

    # 前 N 个商品页（排除广告位）：每个类目 N 个，广告位商品不请求
    listed = [p for p in site.items if site.items[p]['rank'] <= N]
    assert set(site.page_requests()) == set(listed) and len(listed) == 2 * N
    assert not any('9' == p[2] for p in site.page_requests())
    pg = job['progress']
    assert pg['pages_done'] == pg['pages_total'] == 2 * N
    assert pg['sharded'] == 1 and pg['truncated'] == 0 and pg['failed'] == 0 and pg['requests'] > 0
    # 大家族按 1–5 星分片补采后全部评论都在
    st = backfill.last_rebuild('homedepot')['stats']
    assert st['truncated_pages'] == 0 and st['sharded'] == 1
    big = list(site.fams)[0]
    with session() as s:
        from pdt.models_data import ChannelHistReview, ChannelPageSpec
        n_big = s.query(ChannelHistReview).filter_by(channel='homedepot', family_key='F' + site.fams[big][0]).count()
        assert n_big == FakeHD.BIG
        sp = s.query(ChannelPageSpec).filter_by(channel='homedepot', item_id=site.fams[big][0]).one()
        assert sp.specs['Vanity Type'] == 'Freestanding' and sp.listed and sp.rank == 1
    star_req = [k for _, u, k in site.log if '"starRatings": [' in k]
    assert {json.loads(k)['filters']['starRatings'][0] for k in star_req} == {1, 2, 3, 4, 5}

    # 页面：进度区显示商品页、评论、分片补采、截断、失败 / 403·429
    html = wen.get('/tools/vp').text
    assert '历史回补' in html and '回补进度 · Home Depot' in html and '分片补采' in html and '截断' in html and '403 · 429' in html
    assert f'{2 * N} / {2 * N}' in re.sub(r'<[^>]+>', '', html)
    state = wen.get('/tools/vp/backfill/homedepot').json()
    assert state['status'] == 'done' and state['params']['n'] == 300 and state['rebuild']['stats']['pages_listed'] == 2 * N

    # 再次评估同样的 N：没有要采的商品页
    j3 = _estimate(wen, start='2024-01', n=N)
    assert j3['estimate']['calls'] == 0 and '没有需要采集的商品页' in j3['estimate']['note'] and j3['estimate']['nothing'] is True
    wen.post(f"/jobs/{j3['id']}/cancel")


# ================================================================ RULE-09
def test_rule09_polite_rate_limit_retry_and_resume(hd):
    """RULE-09：相邻请求间隔 ≥ 1 秒；429 后间隔变大并计数；单个请求最多 3 次后记失败，不无限重试；中断续采时已完成商品页请求数为 0。"""
    wen, site, clock, backfill = hd
    # 三个不同请求各返回一次 429；一个商品页连续失败 4 次（服务器错误）
    site.fail = {'"31000003"': [429], '/p/reviews/x/31000004/1': [429], '/p/reviews/x/31000010/1': [429], '/p/reviews/x/32000002/1': [500, 500, 500, 500]}
    j = _estimate(wen, start='2024-01', n=20)
    wen.post(f"/jobs/{j['id']}/confirm")
    job = wen.get(f"/jobs/{j['id']}").json()
    ts = [t for t, _, _ in site.log]
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    assert min(gaps) >= 1.0
    # 429 之后：停 30 秒起，之后的间隔比基础间隔大（降速）
    i429 = [k for k, (_, u, _) in enumerate(site.log) if '/p/reviews/x/31000004/1' in u][0]
    assert gaps[i429] >= 30
    assert gaps[i429 + 1] >= 1.3 * 2 * 0.9 - 1e-9  # 间隔翻倍后逐步回落
    pg = job['progress']
    assert pg['http429'] == 3 and pg['failed'] == 1
    assert site.page_requests()['32000002'] == 3  # 最多 3 次
    assert job['status'] == 'done'
    # 失败的商品页记在缓存里（状态 500），续采只重试它，已完成的商品页 0 次请求
    n0 = len(site.log)
    j2 = _estimate(wen, start='2024-01', n=20)
    assert j2['estimate']['calls'] > 0
    wen.post(f"/jobs/{j2['id']}/confirm")
    again = Counter(re.search(r'/x/(\d+)/1', u).group(1) for _, u, _ in site.log[n0:] if '/p/reviews/x/' in u)
    assert set(again) == {'32000002'}  # 只重试失败的那个（站点还剩 1 次错误，再试一次成功）


def test_rule09_blocked_pauses_channel(hd):
    """RULE-09 / PAGE-F23-01：403 / 429 降速重试 3 次仍被拦截 → 回补暂停并提示，已采部分保留。"""
    wen, site, clock, backfill = hd
    site.fail = {'/p/reviews/x/31000006/1': [429, 429, 429]}
    j = _estimate(wen, start='2024-01', n=10)
    wen.post(f"/jobs/{j['id']}/confirm")
    job = wen.get(f"/jobs/{j['id']}").json()
    assert job['status'] == 'paused' and '连续被拦截' in job['progress']['blocked']
    assert site.page_requests()['31000006'] == 3
    html = wen.get('/tools/vp').text
    assert '连续被拦截' in html and '续采' in html


# ================================================================ FLOW-29（单元）
def test_flow29_spec_first_tagging_unit():
    """FLOW-29：有规格的按规格打尺寸段、装、形态、台面、柜体、主色，来源“规格”；只有标题、没有组装信息的“装”为未知，不默认拆装。"""
    from pdt.core import tagging
    r = tagging.spec_tag({'title': 'Doveton 36 in. W x 22 in. D x 34 in. H Single Sink Bath Vanity in White with White Engineered Stone Top'},
                         {'Product Width (in.)': '36 in', 'Assembled': 'Assembled', 'Vanity Type': 'Freestanding', 'Top Material': 'Engineered Stone',
                          'Cabinet Material': 'Solid Wood', 'Cabinet Color Family': 'White'})
    assert r['尺寸段'][0] == '36″' and r['装'][0] == '整装' and r['形态'][0] == '落地式'
    assert r['台面材质'][0] == '岗石' and r['柜体材质'][0] == '实木' and r['主色'][0] == '白'
    assert all(r[k][3] == 'spec' for k in ('尺寸段', '装', '形态', '台面材质', '柜体材质', '主色'))
    t = tagging.spec_tag({'title': 'Home Decorators Collection Winsome 36 in. Sand Bath Vanity Cabinet and 37 in. x 22 in. White Rectangular Sink Vanity Top Combo'})
    assert t['装'][0] == '' and t['尺寸段'][0] == '36″' and t['尺寸段'][3] == 'rule'
    # Wayfair / Lowe's 写法
    assert tagging.spec_tag({'title': 'x'}, {'Assembly Level': 'No Assembly Required'})['装'][:1] == ('整装',)
    assert tagging.spec_tag({'title': 'x'}, {'Assembly Level': 'Full Assembly Needed'})['装'][:1] == ('拆装',)
    assert tagging.spec_tag({'title': 'x'}, {'Mount Type': 'Wall Mounted'})['形态'][:1] == ('悬浮式',)


def test_flow29_unknown_assembly_queue_page(hd):
    """FLOW-29：回补商品打标——规格写明 Assembled 的整装、来源“规格”；没有组装依据的“装”进确认队列（标渠道），不出现默认拆装。"""
    wen, site, clock, backfill = hd
    j = _estimate(wen, start='2024-01', n=12)
    wen.post(f"/jobs/{j['id']}/confirm")
    no_asm = [p for p, it in site.items.items() if it['no_asm'] and it['rank'] <= 12]
    with session() as s:
        tags = {(t.item_id, t.tag): t for t in s.query(Tag).filter_by(channel='homedepot')}
    p_ok = next(p for p, it in site.items.items() if not it['no_asm'] and it['rank'] <= 12 and it['fam'].startswith('31'))
    assert tags[(p_ok, '装')].value == '整装' and tags[(p_ok, '装')].source == 'spec' and tags[(p_ok, '尺寸段')].source == 'spec'
    # 同家族有规格的商品页 → 按同家族规格补；整个家族都没有依据的才进队列
    assert no_asm
    for p in no_asm:
        t = tags[(p, '装')]
        assert t.value in ('', '整装')
        assert t.value != '拆装' or site.items[p]['fam'].startswith('32')
    assert not [t for (p, k), t in tags.items() if k == '装' and t.value == '拆装' and site.items[p]['fam'].startswith('31')]
    # 让一个家族全部没有依据：直接写打标结果验证进队
    from pdt.core import tagging
    res = {'3100099': tagging.spec_tag({'title': 'Winsome 36 in. Sand Bath Vanity Cabinet and Top Combo'})}
    with session() as s:
        s.add(Product(channel='homedepot', item_id='3100099', title='Winsome 36 in. Sand Bath Vanity Cabinet and Top Combo', series='F3100099'))
    tagging.write_tags('homedepot', res, {'3100099': tagging.group_key('homedepot', series='F3100099')}, '2026-10')
    with session() as s:
        t = s.query(Tag).filter_by(channel='homedepot', item_id='3100099', tag='装').one()
        assert t.value == '' and t.status == 'queued' and all(c['confidence'] is None for c in t.candidates)
    cnt = tagging.counts()
    assert cnt['assembly'] >= 1
    html = wen.get('/tagging?channel=homedepot&reason=assembly').text
    assert '装：未知' in html and '这组是整装还是拆装？' in html and '仍不确定（保持未知，不进框）' in html and 'Home Depot' in html
    assert '3100099' in html
    html = wen.get('/tagging').text
    assert '分框标签来源' in html and '<span class="etag">规格</span>' in html


# ================================================================ FLOW-32
def test_flow32_backfill_and_discount_params_versioned(hd):
    """FLOW-32：品类配置渠道参数页把 Home Depot 回补 N 从 300 改为 200、秩相关减值从 0.1 改为 0.15，保存前显示前后对比并生成新版本；
    之后新发起的回补用 N = 200，打折参数供渠道回测读取，页面注明参数版本。"""
    wen, site, clock, backfill = hd
    from pdt import catconfig
    html = wen.get('/settings/category?tab=ch').text
    assert '历史回补与打折规则' in html and 'channels.homedepot.backfill.n' in html and 'channels.homedepot.discount.rank_corr' in html
    v, cfg = catconfig.current()
    new = json.loads(json.dumps(cfg))
    new['channels']['homedepot']['backfill']['n'] = 200
    new['channels']['homedepot']['discount']['rank_corr'] = 0.15
    pv = wen.post('/settings/category/preview', data={'data': json.dumps(new)}, headers=J).json()
    labels = {c['label']: (c['old'], c['new']) for c in pv['changes']}
    assert labels == {'Home Depot 回补商品页数 N': ('300', '200'), 'Home Depot 打折 · 秩相关减值': ('0.1', '0.15')}
    r = wen.post('/settings/category', data={'data': json.dumps(new), 'note': '回补 N 改 200、秩相关减值 0.15', 'tab': 'ch'}, follow_redirects=False)
    assert r.status_code == 303
    v2, p = catconfig.channel_params('homedepot')
    assert v2 == v + 1 and p['backfill']['n'] == 200 and p['discount']['rank_corr'] == 0.15
    assert catconfig.channel_params('lowes')[1]['discount']['rank_corr'] == 0.1
    # 之后新发起的回补默认 N = 200，页面注明参数版本
    est = wen.post('/jobs/estimate', data={'kind': 'channel_backfill', 'target': 'backfill:homedepot', 'params': json.dumps({'channel': 'homedepot'})}).json()
    assert est['estimate']['params']['n'] == 200 and est['estimate']['params']['config_version'] == v2
    assert '每个类目前 200 个商品页' in est['estimate']['note']
    html = wen.get('/tools/vp').text
    assert f'参数 v{v2}' in html and 'value="200"' in html
    # 非法值
    bad = json.loads(json.dumps(new))
    bad['channels']['homedepot']['backfill']['n'] = 0
    assert wen.post('/settings/category/preview', data={'data': json.dumps(bad)}, headers=J).status_code == 400


# ================================================================ Lowe's / Wayfair（reviewkit + 假 Bright Data / Apify）
def test_flow27_wayfair_backfill_two_step_fake_services(wen, monkeypatch):
    """FLOW-27（Lowe's / Wayfair）：未连接时估算即提示；连接后先确认列表（Bright Data）费用，列表采完再确认评论（Apify）费用，采完重建。"""
    import test_tools as tt
    from pdt.core import backfill
    from pdt.core import vp as vpcore
    from pdt.reviewkit import wayfair
    monkeypatch.setattr(wayfair.reviews_batch, '__defaults__', (10, 1))
    vpcore.projects()
    r = wen.post('/jobs/estimate', data={'kind': 'channel_backfill', 'target': 'backfill:wayfair', 'params': json.dumps({'channel': 'wayfair', 'n': 12})})
    assert r.status_code == 400 and '未连接' in r.json()['error']
    services.save_secret('brightdata', 'bd-测试密钥-7f3a')
    services.save_secret('apify', 'apify-测试密钥-k29Q')
    bd, ap = tt.FakeBD(), tt.FakeApify()
    services.set_fake('brightdata', bd)
    services.set_fake('apify', ap)
    j = _estimate(wen, 'wayfair', n=12)
    assert j['estimate']['stage'] == 'lists' and j['estimate']['usd_hi'] > 0 and '列表采完后再估算' in j['estimate']['note']
    wen.post(f"/jobs/{j['id']}/cancel")
    assert bd.calls == [] and ap.calls == []
    wen.post(f"/jobs/{_estimate(wen, 'wayfair', n=12)['id']}/confirm")
    assert bd.calls and ap.calls == []
    assert backfill.state('wayfair')['status'] == 'lists_done'
    j2 = _estimate(wen, 'wayfair', n=12)
    assert j2['estimate']['stage'] == 'collect' and set(j2['estimate']['services']) == {'brightdata', 'apify'}
    wen.post(f"/jobs/{j2['id']}/confirm")
    assert wen.get(f"/jobs/{j2['id']}").json()['status'] == 'done'
    h = wen.get('/data/channels/wayfair/history').json()
    assert h['families'] > 0 and h['start'] == '2024-01' and h['reviews_window'] > 0


# ================================================================ FLOW-28（真实缓存）
def _need_cache():
    from pdt.core import backfill
    if not (backfill.TRIAL_CACHE / 'lists').exists():
        pytest.skip(f'Home Depot 回补小试缓存不在本机（{backfill.TRIAL_CACHE}，原始缓存不入库），跳过真实数据回归')


@pytest.fixture()
def hd_cache(wen):
    _need_cache()
    from pdt.core import backfill
    st = backfill.import_cache('homedepot', log=lambda *a: None)
    return wen, st


def test_flow28_rebuild_matches_trial_report(hd_cache):
    """FLOW-28：用小试缓存重建——家族数 219、评论（2024-01 起）14,397、月份 2024-01 至 2026-10、覆盖 73% / 58%、前 50 半年重合率 78%；
    逐月估算月销 = VP × 50 + 非 VP × 20，首条评论月为上架月；评论只计一次。基准：solution-v2/开发建议/小平台_HD回测小试.md。"""
    wen, st = hd_cache
    assert (st['start'], st['end'], st['n_months']) == ('2024-01', '2026-10', 34)
    assert st['pages_listed'] == 598 and st['families'] == 219 and st['fam_status'] == {'完整': 185, '无评论': 34}
    assert st['reviews_all'] == 19359 and st['reviews_window'] == 14397 and round(st['vp_share'], 2) == 0.79
    assert st['truncated_pages'] == 0 and st['sharded'] == 7
    cov = st['coverage']
    assert round(cov['带台面']['cover'], 2) == 0.73 and round(cov['无台面']['cover'], 2) == 0.58
    assert round(cov['带台面']['b'], 2) == -1.27 and round(cov['无台面']['b'], 2) == -0.80
    assert [round(x['share'], 2) for x in cov['带台面']['segments']] == [0.56, 0.17, 0.17, 0.09]
    ov = {o['key']: (round(o['top50'], 2), round(o['top20'], 2)) for o in st['overlap']}
    assert ov == {'single4': (0.72, 0.60), 'half': (0.78, 0.80), 'year1': (0.68, 0.55), 'year3': (0.66, 0.80)}
    q = st['quarters'][0]
    assert q['q'] == '2024-01 至 03' and round(q['units']) == 16507 and q['families'] == 96 and q['pages'] == 455

    from pdt.core import panel
    from pdt.models_data import ChannelHistReview
    P = panel.load_panel('homedepot')
    assert P['month'].min() == '2024-01' and P['month'].max() == '2026-10'
    assert P['family_key'].str.startswith('F').all()
    with session() as s:
        hr = [(r.item_id, r.month, r.vp, r.date) for r in s.query(ChannelHistReview).filter_by(channel='homedepot')]
    # 月销口径：VP × 50 + 非 VP × 20；每条评论只记在写它的商品页上一次
    one = P.sort_values('units', ascending=False).iloc[0]
    vp = sum(1 for i, m, v, _ in hr if i == one['item_id'] and m == one['month'] and v)
    nv = sum(1 for i, m, v, _ in hr if i == one['item_id'] and m == one['month'] and not v)
    assert one['units'] == vp * 50 + nv * 20
    win = [x for x in hr if '2024-01' <= x[1] <= '2026-10']
    assert len(win) == 14397 and P['units'].sum() == sum(50 if v else 20 for _, _, v, _ in win)
    # 上架月 = 首条评论月
    first = {}
    for i, m, v, d in hr:
        first[i] = min(first.get(i, d), d)
    with session() as s:
        p = s.query(Product).filter_by(channel='homedepot', item_id=one['item_id']).one()
        assert p.listed_at == first[one['item_id']] and p.family_key == one['family_key'] == p.series
        # 原有的月度追踪批次（同渠道同月）被重建批次替换，不重复计数
        assert s.query(Batch).filter_by(channel='homedepot', status='merged', source='backfill').count() == 34
        assert s.query(Batch).filter(Batch.channel == 'homedepot', Batch.status == 'merged', Batch.source != 'backfill').count() == 0


def test_flow28_page_and_api(hd_cache):
    """FLOW-28 / DESIGN-07：其他渠道数据页历史重建区显示月份范围、商品页 / 家族、评论数、前 N 覆盖、前 50 半年重合率、幸存者偏差说明与家族列表。"""
    wen, st = hd_cache
    html = wen.get('/data/channels?ch=homedepot').text
    for s_ in ('历史重建', '幸存者偏差：只含当前仍在榜的商品', '2024-01 至 2026-10', '598 / 219', '14,397', '73% / 58%', '78%',
               '前 N 覆盖（按排名分段）', '换手（前 50 / 前 20 家族重合率）', '重建的月度历史（按季度）', '16,507', '评论家族 · Home Depot',
               '219 个家族（完整 185 · 无评论 34）', 'd-family', '未回补 · 未验证'):
        assert s_ in html, s_
    h = wen.get('/data/channels/homedepot/history').json()
    assert h['families'] == 219 and h['reviews_window'] == 14397 and h['start'] == '2024-01'
    assert wen.get('/data/channels/lowes/history').status_code == 404
    r = wen.post('/data/channels/homedepot/rebuild', follow_redirects=False)
    assert r.status_code == 303
    assert backfill_last()['families'] == 219


def backfill_last():
    from pdt.core import backfill
    return backfill.last_rebuild('homedepot')['stats']


def test_flow29_trial_cache_assembly_and_frame_share(hd_cache):
    """FLOW-29：用小试缓存打标——整装约 80%（小试 80%）、框可定的销量占比 ≥ 95%（小试 99%）；分框标签来源主要是规格；不出现默认拆装。"""
    wen, st = hd_cache
    from pdt.core import panel
    P = panel.load_panel('homedepot')
    x = P[P['month'] >= '2026-01']
    tot = x['units'].sum()
    assert 0.77 <= x.loc[x['装'] == '整装', 'units'].sum() / tot <= 0.83
    assert x.loc[x['frame'].notna(), 'units'].sum() / tot >= 0.95
    tg = {r['tag']: r for r in st['tags']}
    assert dict(tg['装']['sources'])['规格'] >= 0.95
    with session() as s:
        src = Counter(t.source for t in s.query(Tag).filter_by(channel='homedepot', tag='装') if t.value)
        unk = s.query(Tag).filter_by(channel='homedepot', tag='装', value='').all()
        assert all(t.status == 'queued' for t in unk)
    assert src['spec'] > 10 * src['rule']
    html = wen.get('/tagging').text
    assert '标签来源构成 · Home Depot 历史回补' in html and '同家族规格补' in html
