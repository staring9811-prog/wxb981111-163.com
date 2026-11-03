"""历史回补（F23，REQ-F23-02 / AC-F23-03 / AC-F23-04 / NFR-013）与历史重建（F28，REQ-F28-03 / AC-F28-06～08）。

做法移植自已验证的小试 solution-v2/trial/小平台_HD回测小试.py（报告 solution-v2/开发建议/小平台_HD回测小试.md）：
- Home Depot 直连：两个类目页 Top Sellers 排序、排除广告位，各取前 N 个商品页；每个商品页抓一次评论首页（规格 + 首页评论）；
  首页评论 ID 重叠 ≥ 一半、或首页评论里记着对方商品页 ID 的 = 同一评论家族；每个家族用站点评论接口（每页 30 条、单一排序最多 17 页）
  按最新排序抓到“起始月 − 6 个月”；到上限时按 1–5 星分片，某星级仍到上限再加“仅 VP”分片，仍到上限记截断；另取最早排序第一页得家族首条评论。
  最后补抓家族里不在前 N、但起始月以来有评论的商品页（规格用于打标）。
- 礼貌限速（NFR-013）：相邻请求间隔 1.3–2.1 秒；403 / 429 间隔翻倍并停 30 秒起、计数；单个请求最多 3 次；全部缓存在
  data/backfill/<渠道>/（与小试缓存同结构），续采不重复请求已完成的商品页与家族。
- Lowe's / Wayfair：复用 reviewkit（Bright Data 列表与详情、Apify 评论），走费用闸门；先确认列表费用，列表采完再确认评论费用。
- 重建：按评论日期把每个商品页起始月以来的逐月 VP / 非 VP 评论数写成月度快照（批次来源 backfill），估算月销 = VP × vp_coef + 非 VP × nonvp_coef
  （品类配置，panel 读取时换算）；首条评论月当上架月；评论家族 = Product.series / family_key（份额计算单位），每条评论只记在写它的商品页上、只计一次。
  同时写评论明细、商品页规格、评论家族（DATA-F28-02），并规格优先打标（AC-F18-08）。
"""
import collections
import json
import math
import random
import re
import shutil
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import delete, insert, select

from .. import catconfig, costgate, services
from ..config import CHANNEL_NAMES, PROJECT_DIR, data_dir
from ..db import session
from ..models import Batch, Job, Product, Snapshot, now
from ..models_data import ChannelFamily, ChannelHistReview, ChannelPageSpec, ChannelRebuild
from ..reviewkit.common import add_query, decode_at, load_json, objects_by_key, save_json
from . import families as fm
from . import tagging

HD_BASE = 'https://www.homedepot.com'
HD_ENTRIES = {'带台面': HD_BASE + '/b/Bath-Bathroom-Vanities-Bathroom-Vanities-with-Tops/N-5yc1vZcfw5',
              '无台面': HD_BASE + '/b/Bath-Bathroom-Vanities-Bathroom-Vanities-without-Tops/N-5yc1vZcfv9'}
CAP_START = 481  # 单一排序最多到 startIndex 481（17 页 · 510 条）
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
TRIAL_REQ, TRIAL_PAGES = 2884, 598  # 2026-11-03 小试实测：598 个商品页共 2,884 次请求（估算依据）
TRIAL_CACHE = PROJECT_DIR / 'input' / 'data_v2' / '渠道历史' / 'homedepot'
PLAT = {'lowes': 'Lowes', 'wayfair': 'Wayfair'}
LOOKBACK = 6  # 评论多抓起始月前 6 个月，用来判断商品页是不是新品（首评后 ≤ 6 个月）


class Blocked(Exception):
    """403 / 429 降速重试后仍失败：渠道回补暂停，已采部分保留。"""


def cache_dir(channel: str) -> Path:
    d = data_dir() / 'backfill' / channel
    d.mkdir(parents=True, exist_ok=True)
    return d


def month_add(m: str, k: int) -> str:
    return fm.ms(fm.mi(m) + k)


def params_for(channel: str, params: dict | None = None) -> dict:
    """回补参数：页面传入的起始月 / N 优先，否则取品类配置当前版本（AC-F27-04）。"""
    ver, p = catconfig.channel_params(channel)
    bf = p['backfill']
    params = params or {}
    start = str(params.get('start') or bf['start'])[:7]
    n = int(params.get('n') or bf['n'])
    if not re.match(r'^\d{4}-\d{2}$', start):
        raise ValueError('起始月份格式应为 YYYY-MM')
    if n <= 0:
        raise ValueError('商品页数 N 要填正整数')
    return dict(channel=channel, start=start, n=n, config_version=ver)


# ====================================================================== 礼貌请求（NFR-013）
def http_transport(url, body=None):
    hdr = {'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9'}
    if body is not None:
        hdr.update({'Content-Type': 'application/json', 'x-experience-name': 'general-merchandise', 'apollographql-client-name': 'general-merchandise',
                    'Origin': HD_BASE, 'Referer': HD_BASE + '/'})
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # 网络错误按失败计，由重试处理
        return 0, str(e).encode()


class Polite:
    """直连同一站点的礼貌请求：每次请求前等 base + 随机 0–jitter 秒（≥ 1 秒）；403 / 429 间隔翻倍（≤ 20 秒）并停 30 秒起，记次数；
    成功后间隔逐步回落；单个请求最多 tries 次，仍失败记“失败”；最后一次仍是 403 / 429 时抛 Blocked。
    transport / sleep / rng 可注入（测试用假站点与假时钟）。"""

    def __init__(self, transport=None, sleep=time.sleep, rng=random.random, base=1.3, jitter=0.8, tries=3, log=None):
        self.transport = transport or http_transport
        self.sleep, self.rng, self.base, self.jitter, self.tries = sleep, rng, base, jitter, tries
        self.delay = base
        self.stat = collections.Counter()
        self.log = log or (lambda *a: None)

    def fetch(self, url, body=None):
        last = (0, b'')
        for i in range(self.tries):
            self.sleep(self.delay + self.rng() * self.jitter)
            self.stat['请求'] += 1
            st, b = self.transport(url, body)
            last = (st, b)
            if st == 200:
                self.delay = max(self.base, self.delay * 0.9)
                return st, b
            if st == 404:
                self.stat['HTTP 404'] += 1
                return st, b
            if st in (403, 429):
                self.stat[f'HTTP {st}'] += 1
                self.delay = min(self.delay * 2, 20)
                self.log(f'  {st}，降速到 {self.delay:.1f} 秒，停 {30 * (i + 1)} 秒')
                self.sleep(30 * (i + 1))
                continue
            self.stat['网络错误' if st == 0 else f'HTTP {st}'] += 1
            self.sleep(3 * (i + 1))
        self.stat['失败（重试 3 次）'] += 1
        if last[0] in (403, 429):
            raise Blocked(f'连续被拦截（HTTP {last[0]}，403 × {self.stat["HTTP 403"]}、429 × {self.stat["HTTP 429"]}）')
        return last


# ====================================================================== Home Depot 直连采集
GQL = ('query reviews($itemId: String!, $startIndex: Int, $pagesize: String, $sortBy: String, $filters: ReviewsFilterInput, $excludeFamily: Boolean, '
       '$searchTerm: String, $recfirstpage: String) { reviews(itemId: $itemId, startIndex: $startIndex, pagesize: $pagesize, sortBy: $sortBy, filters: $filters, '
       'excludeFamily: $excludeFamily, searchTerm: $searchTerm, recfirstpage: $recfirstpage) { Results { Id SubmissionTime Rating ProductId BadgesOrder IsSyndicated '
       'OriginalProductName } TotalResults } }')


def _rv(x):
    return dict(d=(x.get('SubmissionTime') or '')[:10], r=x.get('Rating'), vp='verifiedPurchaser' in (x.get('BadgesOrder') or []),
                syn=bool(x.get('IsSyndicated')), pid=str(x.get('ProductId')), name=x.get('OriginalProductName') or '')


class HD:
    """Home Depot 回补采集（小试 采集 / 补变体 两步的移植）。root = 缓存目录（lists/ pages/ reviews/）。"""

    def __init__(self, root: Path, fetcher: Polite, topn: int, cutoff: str, check=None, progress=None, log=None):
        self.root, self.f, self.topn, self.cutoff = Path(root), fetcher, topn, cutoff
        self.check = check or (lambda: None)
        self.progress = progress or (lambda **k: None)
        self.log = log or (lambda *a: None)
        self.stat = collections.Counter()

    def path(self, *p):
        return str(self.root.joinpath(*p))

    # ---------- 1. 列表（Top Sellers，排除广告位，取前 N） ----------
    def list_entry(self, name, url):
        f = self.path('lists', f'{name}.json')
        got = load_json(f) or {'rows': [], 'off': 0}
        rows, off = got['rows'], got['off']
        while not got.get('end') and sum(not r['sponsored'] for r in rows) < self.topn:
            self.check()
            st, b = self.f.fetch(add_query(url, sortby='topsellers', Nao=off or None))
            if st != 200:
                self.log(f'{name} 列表 Nao={off} HTTP {st}，停')
                self.stat['列表失败'] += 1
                break
            s = b.decode('utf-8', 'ignore')
            m = re.search(r'products\(\{\\"filter\\":\{[^)]*\}\)":(\[)', s)
            refs = decode_at(s, m.start(1)) if m else []
            ids = [r['__ref'].split('-')[-1] for r in refs if isinstance(r, dict) and '__ref' in r]
            tot = re.search(r'"totalProducts":(\d+)', s)
            if tot:
                got['totalProducts'] = int(tot.group(1))
            if not ids:
                got['end'] = True
                break
            objs = objects_by_key(s, r'base-searchNav-\d+')
            for pid in ids:
                o = objs.get(f'base-searchNav-{pid}', {})
                ident, info = o.get('identifiers') or {}, o.get('info') or {}
                pricing = next((v for k, v in o.items() if k.startswith('pricing')), None) or {}
                rr = (o.get('reviews') or {}).get('ratingsReviews') or {}
                rows.append(dict(id=pid, url=HD_BASE + ident.get('canonicalUrl', f'/p/{pid}'), title=ident.get('productLabel', ''),
                                 brand=ident.get('brandName', ''), sponsored=bool(info.get('isSponsored')), price=pricing.get('value'),
                                 rating=float(rr['averageRating']) if rr.get('averageRating') else None,
                                 review_count=int(rr['totalReviews']) if rr.get('totalReviews') else 0))
            off += len(ids)
            got.update(rows=rows, off=off)
            save_json(f, got)
        got['done'] = True
        save_json(f, got)
        return ranked(got, self.topn)

    # ---------- 2. 商品页（规格 + 首页评论） ----------
    def product_page(self, pid):
        f = self.path('pages', f'{pid}.json')
        got = load_json(f)
        if got and got.get('status') == 200:
            return got
        self.check()
        st, b = self.f.fetch(f'{HD_BASE}/p/reviews/x/{pid}/1')  # 只用 ID，站点重定向到规范地址
        out = {'status': st}
        if st == 200:
            s = b.decode('utf-8', 'ignore')
            cat = objects_by_key(s, rf'base-catalog-{pid}').get(f'base-catalog-{pid}') or {}
            d = cat.get('details') or {}
            out['specs'] = {sp.get('specName'): sp.get('specValue') for g in cat.get('specificationGroup') or [] for sp in g.get('specifications') or []}
            out['highlights'] = d.get('highlights') or []
            out['description'] = d.get('description') or ''
            pr = next((v for k, v in cat.items() if k.startswith('pricing')), None) or {}
            ident = cat.get('identifiers') or {}
            out.update(price=pr.get('value'), title=ident.get('productLabel'), brand=ident.get('brandName'),
                       discontinued=((cat.get('availabilityType') or {}).get('discontinued')))
            res = []
            for mm in re.finditer(r'"reviews\(\{', s):
                end = s.find('})":{', mm.start())
                k = s[mm.start():end]
                if end > 0 and len(k) < 600 and 'startIndex\\":1' in k and f'itemId\\":\\"{pid}' in k:
                    res = decode_at(s, end + len('})":')).get('Results') or []
                    break
            out['sig'] = sorted(str(x.get('Id')) for x in res)
            out['sig_pids'] = sorted({str(x.get('ProductId')) for x in res})
        else:
            self.stat['商品页失败'] += 1
        save_json(f, out)
        return out

    # ---------- 3. 家族评论（站点评论接口，按星级 / 仅 VP 分片） ----------
    def gql_page(self, pid, start, sort='newest', stars=None, vp=False):
        body = {'operationName': 'reviews', 'query': GQL, 'variables': {
            'itemId': pid, 'startIndex': start, 'pagesize': '30', 'sortBy': sort, 'excludeFamily': False, 'searchTerm': None, 'recfirstpage': '30',
            'filters': {'isVerifiedPurchase': vp, 'prosCons': None, 'starRatings': stars}}}
        st, b = self.f.fetch(HD_BASE + '/federation-gateway/graphql?opname=reviews', body)
        if st != 200:
            return st, None, []
        try:
            d = json.loads(b)['data']['reviews'] or {}
        except (ValueError, KeyError, TypeError):
            return -1, None, []
        return st, d.get('TotalResults'), d.get('Results') or []

    def sweep(self, pid, revs, stars=None, vp=False):
        """按最新排序往前抓，直到早于 cutoff 或到翻页上限。返回（这一片完整到的日期，总数，是否失败）。"""
        start, total, last = 1, None, '0000-00-00'
        while start <= CAP_START:
            self.check()
            st, tot, res = self.gql_page(pid, start, stars=stars, vp=vp)
            if st != 200:
                return None, total, True
            total = tot if total is None else total
            if not res:
                return '0000-00-00', total, False
            for x in res:
                revs[str(x['Id'])] = _rv(x)
            last = (res[-1].get('SubmissionTime') or '')[:10]
            if last < self.cutoff or start + 30 > (total or 0):
                return '0000-00-00', total, False
            start += 30
        return last, total, False  # 到上限：这一片只完整到 last

    def family_reviews(self, fk, pid):
        f = self.path('reviews', f'{fk}.json')
        got = load_json(f)
        if got and got.get('状态') in ('完整', '截断'):
            return got
        revs, notes = {}, []
        self.check()
        st, tot, res = self.gql_page(pid, 1, sort='oldest')
        if st != 200:
            out = {'状态': '失败', '备注': f'最早排序 HTTP {st}', 'reviews': {}}
            save_json(f, out)
            self.stat['家族失败'] += 1
            return out
        first = (res[0].get('SubmissionTime') or '')[:10] if res else None
        for x in res:
            revs[str(x['Id'])] = _rv(x)
        upto, total, fail = self.sweep(pid, revs)
        complete_to = upto
        if fail:
            complete_to = None
        elif upto > self.cutoff:  # 到上限：按星级分片
            notes.append(f'总排序到上限，只完整到 {upto}，按星级分片')
            parts = []
            for s_ in (1, 2, 3, 4, 5):
                u, _t, fl = self.sweep(pid, revs, stars=[s_])
                if fl:
                    fail = True
                    break
                if u > self.cutoff:
                    u2, _t2, fl2 = self.sweep(pid, revs, stars=[s_], vp=True)  # 该星级只看 VP 再往前
                    if fl2:
                        fail = True
                        break
                    notes.append(f'{s_} 星到上限（{u}），VP 分片到 {u2}')
                parts.append(u)  # 非 VP 仍只完整到 u
            complete_to = None if fail else max(parts)
        if fail:
            out = {'状态': '失败', '备注': '；'.join(notes + ['分页中途失败']), 'reviews': {}}
            save_json(f, out)
            self.stat['家族失败'] += 1
            return out
        status = '完整' if complete_to <= self.cutoff else '截断'
        out = {'状态': status, '完整到': complete_to, '首条评论': first, '评论总数': total, '备注': '；'.join(notes), 'reviews': revs}
        save_json(f, out)
        return out

    # ---------- 全流程 ----------
    def collect(self, start_day: str):
        lists = {n: self.list_entry(n, u) for n, u in HD_ENTRIES.items()}
        allp = {}
        for rows in lists.values():
            for r in rows:
                allp.setdefault(r['id'], r)
        st = self.stat
        self.progress(pages_total=len(allp), pages_done=sum(1 for p in allp if (load_json(self.path('pages', f'{p}.json')) or {}).get('status') == 200))
        for i, pid in enumerate(allp):
            self.product_page(pid)
            if i % 10 == 0 or i == len(allp) - 1:
                self.progress(pages_done=i + 1, **self.counters())
        fams = families_from_pages(lists, self.root)
        order = sorted(fams.items(), key=lambda kv: -max(allp[p]['review_count'] for p in kv[1]))
        need = [(fk, mem) for fk, mem in order if max(allp[p]['review_count'] for p in mem) > 0]
        self.progress(fams_total=len(fams), fams_done=len(fams) - len(need), **self.counters())
        for i, (fk, mem) in enumerate(need):
            rep = max(mem, key=lambda p: allp[p]['review_count'])
            self.family_reviews(fk, rep)
            self.progress(fams_done=len(fams) - len(need) + i + 1, **self.counters())
        # 补变体：不在前 N、但起始月以来有评论的商品页也抓一次（规格用于打标）
        todo = set()
        for fk in fams:
            g = load_json(self.path('reviews', f'{fk}.json')) or {}
            todo |= {x['pid'] for x in (g.get('reviews') or {}).values() if x['d'] >= start_day}
        todo = sorted(todo - set(allp))
        self.progress(extra_total=len(todo), extra_done=0)
        for i, p in enumerate(todo):
            self.product_page(p)
            if i % 10 == 0 or i == len(todo) - 1:
                self.progress(extra_done=i + 1, **self.counters())
        save_json(self.path('stat_app_run.json'), dict(self.f.stat + st))
        return lists, fams

    def counters(self):
        st = self.f.stat
        revs = sharded = trunc = 0
        rdir = self.root / 'reviews'
        if rdir.exists():
            for fn in rdir.glob('*.json'):
                g = load_json(str(fn)) or {}
                revs += len(g.get('reviews') or {})
                sharded += int('分片' in (g.get('备注') or ''))
                trunc += int(g.get('状态') == '截断')
        return dict(requests=st['请求'], http403=st['HTTP 403'], http429=st['HTTP 429'], failed=st['失败（重试 3 次）'],
                    reviews=revs, sharded=sharded, truncated=trunc)


def ranked(got: dict, topn: int) -> list:
    rank, out = 0, []
    for r in got.get('rows') or []:
        if r['sponsored']:
            continue
        rank += 1
        if rank > topn:
            break
        out.append(dict(r, 排名=rank))
    return out


def families_from_pages(lists: dict, root: Path) -> dict:
    """首页评论 ID 有重叠（≥ 一半）或首页评论里出现对方商品 ID 的商品页 = 同一评论家族（共享评论）。家族键 = F + 并查集根商品页 ID。"""
    pids = list(dict.fromkeys(p['id'] for rows in lists.values() for p in rows))
    pg = {p: load_json(str(Path(root) / 'pages' / f'{p}.json')) or {} for p in pids}
    up = {p: p for p in pids}

    def root_(x):
        while up[x] != x:
            up[x] = up[up[x]]
            x = up[x]
        return x
    bysig = {}
    for p in pids:
        s = set(pg[p].get('sig') or [])
        if not s:
            continue
        for q, sq in bysig.items():
            if len(s & sq) >= min(len(s), len(sq)) / 2:
                up[root_(p)] = root_(q)
        bysig[p] = s
    for p in pids:
        for q in pg[p].get('sig_pids') or []:
            if q in up and pg[q].get('sig'):
                up[root_(q)] = root_(p)
    fam = collections.defaultdict(list)
    for p in pids:
        fam[root_(p)].append(p)
    return {f'F{k}': v for k, v in fam.items()}


def hd_dataset(root: Path, topn: int, collected_on: str | None = None) -> dict:
    """Home Depot 回补缓存 → 重建用的统一数据（列表、家族、商品页、家族状态、评论表）。"""
    root = Path(root)
    lists = {}
    for n in HD_ENTRIES:
        g = load_json(str(root / 'lists' / f'{n}.json')) or {'rows': []}
        lists[n] = dict(rows=[dict(r, 入口=n) for r in ranked(g, topn)], total=g.get('totalProducts'))
    fams = families_from_pages({n: v['rows'] for n, v in lists.items()}, root)
    famstat, rv = {}, []
    for fk in fams:
        g = load_json(str(root / 'reviews' / f'{fk}.json'))
        if not g:
            famstat[fk] = dict(status='无评论', note='0 条评论（无需采）')
            continue
        famstat[fk] = dict(status=g.get('状态'), complete_to=g.get('完整到') or '', first=g.get('首条评论') or '', total=g.get('评论总数'),
                           note=g.get('备注') or '', sharded='分片' in (g.get('备注') or ''))
        if g.get('状态') not in ('完整', '截断'):
            continue
        for rid, x in (g.get('reviews') or {}).items():
            rv.append((fk, rid, x['d'], x['r'], bool(x['vp']), bool(x.get('syn')), str(x['pid']), x.get('name') or ''))
    R = pd.DataFrame(rv, columns=['fam', 'rid', 'd', 'r', 'vp', 'syn', 'pid', 'name']).drop_duplicates('rid')
    pids = set(p for v in fams.values() for p in v) | set(R['pid'])
    pages = {}
    for p in pids:
        pg = load_json(str(root / 'pages' / f'{p}.json'))
        if pg:
            pages[p] = pg
    stat = collections.Counter()
    for fn in ('stat_main_run.json', 'stat_last_run.json', 'stat_supplement.json', 'stat_app_run.json'):
        stat.update(load_json(str(root / fn)) or {})
    return dict(lists=lists, fams=fams, pages=pages, famstat=famstat, reviews=R, req_stat=dict(stat),
                collected_on=collected_on or (R['d'].max() if len(R) else date.today().isoformat()), rep_pid=True)


# ====================================================================== Lowe's / Wayfair（reviewkit，Bright Data + Apify）
def _rk_cfg(channel: str, start: str, n: int, full_end: str) -> dict:
    from . import vp as vpcore
    plat = PLAT[channel]
    ents = []
    for name in vpcore.projects():
        for e in vpcore.load(name).get('entries') or []:
            if e.get('platform') == plat and e.get('enabled', True) and e['name'] not in {x['name'] for x in ents}:
                ents.append(dict(e, top_n=n, exclude_sponsored=True))
        if ents:
            filters = vpcore.load(name).get('filters') or {}
            break
    if not ents:
        raise ValueError(f'评论 VP 追踪里没有 {CHANNEL_NAMES[channel]} 入口，先在项目设置里添加类目入口')
    return dict(name=f'回补_{channel}', category='浴室柜', window=dict(start=month_add(start, -LOOKBACK) + '-01', full_end=full_end, include_partial=False),
                entries=ents, filters=filters, dedupe_across_entries=True, low_reviews={'threshold': 0, 'mode': 'split'},
                budget={f'bd_{channel}_usd': 1e6, f'apify_{channel}_usd': 1e6})  # 项目预算不另设，受设置页月度上限约束


def _last_full_day(today: date | None = None) -> str:
    t = today or date.today()
    return (pd.Timestamp(t.year, t.month, 1) - pd.Timedelta(days=1)).strftime('%Y-%m-%d')


def rk_ctx(channel: str, start: str, n: int, job=None):
    from ..reviewkit.common import Ctx
    c = Ctx(_rk_cfg(channel, start, n, _last_full_day()), data_dir=str(cache_dir(channel) / 'rk'))
    c.job = job
    return c


def rk_lists_done(ctx) -> bool:
    from ..reviewkit import pipeline as rkp
    for e in rkp.entries(ctx):
        got = load_json(ctx.path('lists', f"{e['name']}.json")) or {}
        if not got.get('done') or sum(1 for r in got.get('rows', []) if r.get('排名')) < min(int(e.get('top_n', 0)), 1):
            return False
    return True


def rk_dataset(channel: str, ctx) -> dict:
    """reviewkit 采集结果 → 重建用的统一数据。评论家族 = 评论 ID 重叠 ≥ 一半的商品页（Lowe's / Wayfair 同系列显示同一批评论）；
    评论不带写评论的商品页，记在家族内排名最好的商品页上。"""
    from ..reviewkit import pipeline as rkp
    plat = PLAT[channel]
    lists = {}
    for e in rkp.entries(ctx):
        got = load_json(ctx.path('lists', f"{e['name']}.json")) or {}
        rows = [dict(id=r['id'], url=r.get('url', ''), title=r.get('title', ''), brand=r.get('brand', ''), price=r.get('price'), sponsored=False,
                     review_count=r.get('review_count') or 0, 排名=r['排名'], 入口=e['name']) for r in got.get('rows', []) if r.get('排名')]
        lists[e['name']] = dict(rows=rows, total=None)
    pids = list(dict.fromkeys(r['id'] for v in lists.values() for r in v['rows']))
    prod = {p: load_json(ctx.path('products', plat, f'{p}.json')) or {} for p in pids}
    sets = {p: {str(x['评论ID']) for x in prod[p].get('reviews') or []} for p in pids}
    up = {p: p for p in pids}

    def root_(x):
        while up[x] != x:
            up[x] = up[up[x]]
            x = up[x]
        return x
    for i, p in enumerate(pids):
        for q in pids[:i]:
            a, b = sets[p], sets[q]
            if a and b and len(a & b) >= min(len(a), len(b)) / 2:
                up[root_(p)] = root_(q)
    fams = collections.defaultdict(list)
    for p in pids:
        fams[root_(p)].append(p)
    fams = {f'F{k}': v for k, v in fams.items()}
    famstat, rv, pages = {}, [], {}
    for fk, mem in fams.items():
        sts = [prod[p].get('状态') for p in mem]
        revs = {}
        for p in mem:
            for x in prod[p].get('reviews') or []:
                revs[str(x['评论ID'])] = x
        status = '无评论' if not revs and all(s in ('完整', None) for s in sts) else ('截断' if '部分' in sts else ('失败' if '失败' in sts else '完整'))
        first = min((str(x['评论日期'])[:10] for x in revs.values() if x.get('评论日期')), default='')
        famstat[fk] = dict(status=status, complete_to='', first=first, total=len(revs), note='；'.join(sorted({prod[p].get('备注') or '' for p in mem} - {''})))
        rep = mem[0]
        for rid, x in revs.items():
            rv.append((fk, rid, str(x.get('评论日期') or '')[:10], x.get('评分'), x.get('VP状态') == 'VP', x.get('转载') == '是', rep, ''))
    for p in pids:
        det = prod[p].get('details') or {}
        pages[p] = dict(status=200 if det else None, specs=tagging.specs_from_text(det.get('规格参数', '')),
                        highlights=[x for x in str(det.get('卖点') or '').splitlines() if x.strip()], title='', brand='')
    R = pd.DataFrame(rv, columns=['fam', 'rid', 'd', 'r', 'vp', 'syn', 'pid', 'name']).drop_duplicates('rid')
    R = R[R['d'].str.len() >= 7]
    return dict(lists=lists, fams=fams, pages=pages, famstat=famstat, reviews=R, req_stat={}, collected_on=date.today().isoformat(), rep_pid=False)


# ====================================================================== 重建（AC-F28-06～08）
def _variant_tags(channel: str, V: pd.DataFrame, pages: dict) -> tuple[dict, dict]:
    """规格优先打标（AC-F18-08）；没有自己规格、某标签判断不了的商品页按同家族已知商品页的众数补（记为规格）；形态仍不知道按落地式（低置信度）。"""
    rules = tagging.rules_cfg()[0]
    res = {}
    for p, r in V.iterrows():
        pg = pages.get(p) or {}
        res[p] = tagging.spec_tag(dict(item_id=p, title=r['title'], highlights=pg.get('highlights') or []), pg.get('specs') or None, rules, default_form=False)
    fill = {}
    for tg in ('装', '形态', '柜体材质', '台面材质'):
        known = collections.defaultdict(collections.Counter)
        for p, t in res.items():
            if t[tg][0]:
                known[V.at[p, 'fam']][t[tg][0]] += 1
        for p, t in res.items():
            if not t[tg][0] and known.get(V.at[p, 'fam']):
                v = known[V.at[p, 'fam']].most_common(1)[0][0]
                t[tg] = (v, float((rules.get('confidence') or {}).get('family_fill', 0.8)), 'family_fill', 'spec')
                fill[(p, tg)] = True
    for p, t in res.items():
        if not t['形态'][0]:
            t['形态'] = ('落地式', 0.6, 'business_default', 'rule')
            fill[(p, '形态默认')] = True
    groups = {p: tagging.group_key(channel, '', V.at[p, 'fam'] or '', V.at[p, 'brand'] or '', V.at[p, 'title'] or '') for p in V.index}
    return res, groups


def rebuild(channel: str, ds: dict, start: str, log=print) -> dict:
    """按评论日期重建 start 起的逐月历史并写入分析库；返回统计（也存 ChannelRebuild）。"""
    from . import channels as chm
    from . import ledger, panel
    ver, _ = catconfig.current()
    c = chm.channel_cfg(channel)
    vpc, nvc = c['vp_coef'], c['nonvp_coef']
    lists, fams, pages, famstat, R = ds['lists'], ds['fams'], ds['pages'], ds['famstat'], ds['reviews'].copy()
    coll = str(ds['collected_on'])[:10]
    END = fm.mi(coll[:7]) - 1  # 采集日所在月未完整，只重建到上一个月
    M0 = fm.mi(start)
    cutoff = month_add(start, -LOOKBACK) + '-01'
    if END < M0:
        raise ValueError('起始月份要早于最后一个完整月')
    MONTHS = list(range(M0, END + 1))
    R['m'] = R['d'].map(lambda d: fm.mi(d[:7]) if isinstance(d, str) and d[:4].isdigit() else -1)
    W = R[(R['m'] >= M0) & (R['m'] <= END)].copy()
    W['c'] = np.where(W['vp'], vpc, nvc)
    listed = {}
    for n, v in lists.items():
        for r in v['rows']:
            listed.setdefault(r['id'], dict(r, 入口=n))
    pid2fam = {p: fk for fk, ps in fams.items() for p in ps}
    wfam = W.drop_duplicates('pid').set_index('pid')['fam'].to_dict()
    names = R.sort_values('d').groupby('pid')['name'].agg(lambda s: next((x for x in reversed(list(s)) if x), ''))
    allpid = sorted(set(W['pid']) | set(listed))
    rows = []
    for p in allpid:
        pg, lr = pages.get(p) or {}, listed.get(p)
        rows.append(dict(pid=p, fam=pid2fam.get(p) or wfam.get(p) or f'F{p}', title=(lr or {}).get('title') or pg.get('title') or names.get(p, ''),
                         brand=(lr or {}).get('brand') or pg.get('brand') or '', price=(lr or {}).get('price') or pg.get('price'),
                         rank=(lr or {}).get('排名'), entry=(lr or {}).get('入口', ''), url=(lr or {}).get('url') or '', has_spec=bool(pg.get('specs'))))
    V = pd.DataFrame(rows).set_index('pid')
    fb = V[V['brand'] != ''].groupby('fam')['brand'].agg(lambda s: s.mode().iloc[0])
    V['brand'] = [b or fb.get(f, '') for b, f in zip(V['brand'], V['fam'])]
    vfirst = R.groupby('pid')['d'].min()
    ffirst = {fk: (famstat.get(fk) or {}).get('first') or '' for fk in fams}
    trunc = {fk: s['complete_to'] for fk, s in famstat.items() if s.get('status') == '截断' and s.get('complete_to')}

    def first_of(p):
        d = vfirst.get(p)
        fk = V.at[p, 'fam']
        if d is None or (fk in trunc and d < trunc[fk]):  # 截断家族早于“完整到”的首评不可信，用家族首评
            return ffirst.get(fk) or ''
        return d
    V['first'] = [first_of(p) for p in V.index]
    V['L'] = V['first'].map(lambda d: fm.mi(d[:7]) if isinstance(d, str) and d >= cutoff else -10 ** 6)  # 抓取起点前就有评论 = 老品
    log(f'{CHANNEL_NAMES[channel]}：{len(listed)} 个在榜商品页、{len(V)} 个有评论的商品页、{len(fams)} 个评论家族、窗口内评论 {len(W):,} 条')

    # ---------- 打标（规格优先） ----------
    res, groups = _variant_tags(channel, V, pages)
    month_end = fm.ms(END)

    # ---------- 写库 ----------
    with session() as s:
        s.execute(delete(ChannelHistReview).where(ChannelHistReview.channel == channel))
        recs = [dict(channel=channel, review_id=str(r.rid), item_id=str(r.pid), family_key=r.fam, date=str(r.d)[:10], month=str(r.d)[:7],
                     stars=None if r.r is None or (isinstance(r.r, float) and np.isnan(r.r)) else float(r.r), vp=bool(r.vp), syndicated=bool(r.syn))
                for r in R.itertuples()]
        for k in range(0, len(recs), 5000):
            s.execute(insert(ChannelHistReview), recs[k:k + 5000])
        s.execute(delete(ChannelPageSpec).where(ChannelPageSpec.channel == channel))
        sp = []
        for p, r in V.iterrows():
            pg = pages.get(p) or {}
            sp.append(dict(channel=channel, item_id=p, family_key=r['fam'], listed=p in listed, entry=r['entry'], rank=None if pd.isna(r['rank']) else int(r['rank']),
                           title=r['title'] or '', brand=r['brand'] or '', price=None if r['price'] is None or pd.isna(r['price']) else float(r['price']),
                           specs=pg.get('specs') or {}, highlights=pg.get('highlights') or [], page_status=pg.get('status'),
                           discontinued=bool(pg.get('discontinued')), collected_on=coll))
        s.execute(insert(ChannelPageSpec), sp)
        s.execute(delete(ChannelFamily).where(ChannelFamily.channel == channel))
        wf = W.groupby('fam').agg(n=('rid', 'size'), vp=('vp', 'sum'))
        wv = W.groupby('fam')['pid'].unique()
        fr = []
        for fk, mem in fams.items():
            st_ = famstat.get(fk) or {}
            ranks = [listed[p]['排名'] for p in mem if p in listed]
            best = min(mem, key=lambda p: listed[p]['排名'] if p in listed else 10 ** 6)
            fr.append(dict(channel=channel, family_key=fk, members=sorted(mem, key=lambda p: listed[p]['排名'] if p in listed else 10 ** 6),
                           variants=sorted(set(wv.get(fk, [])) | set(mem)), best_rank=min(ranks) if ranks else None,
                           brand=V.at[best, 'brand'] if best in V.index else '', title=V.at[best, 'title'] if best in V.index else '',
                           first_review=st_.get('first') or '', status=st_.get('status') or '', complete_to=st_.get('complete_to') or '',
                           sharded=bool(st_.get('sharded')), note=st_.get('note') or '',
                           reviews_window=int(wf['n'].get(fk, 0)), vp_window=int(wf['vp'].get(fk, 0))))
        s.execute(insert(ChannelFamily), fr)
        # 商品（家族键 = 评论家族）
        have = {p.item_id: p for p in s.scalars(select(Product).where(Product.channel == channel))}
        from .channels import item_link
        for p, r in V.iterrows():
            o = have.get(p)
            if o is None:
                o = Product(channel=channel, item_id=p)
                s.add(o)
            o.series, o.family_key = r['fam'], r['fam']
            o.brand, o.title = r['brand'] or o.brand, r['title'] or o.title
            o.link = r['url'] or o.link or item_link(channel, p)
            o.listed_at = (r['first'] or '')[:10]
        # 批次与快照：同渠道这些月份已有的并入批次（月度追踪或上一次重建）改为 superseded，避免重复计数
        for old in s.scalars(select(Batch).where(Batch.channel == channel, Batch.status.in_(['merged', 'reference']))):
            if old.source == 'backfill' or M0 <= fm.mi(old.month) <= END:
                old.status = 'superseded'
        G = W.groupby(['pid', 'm']).agg(vp=('vp', 'sum'), n=('rid', 'size')).reset_index()
        G['nonvp'] = G['n'] - G['vp']
        by_m = {m: g for m, g in G.groupby('m')}
        for m in MONTHS:
            g = by_m.get(m)
            mname = fm.ms(m)
            vp_t = int(g['vp'].sum()) if g is not None else 0
            nv_t = int(g['nonvp'].sum()) if g is not None else 0
            b = Batch(channel=channel, month=mname, source='backfill', file_path=str(ds.get('root') or ''), status='merged', merged_at=now(),
                      rows=0 if g is None else int(len(g)), checks=dict(dedup=dict(vp=vp_t, nonvp=nv_t), complete=True, items=0 if g is None else int(len(g)),
                                                                         rebuild=True, collected_on=coll))
            s.add(b)
            s.flush()
            if g is None:
                continue
            snaps = []
            for r in g.itertuples():
                v = V.loc[r.pid]
                price = None if v['price'] is None or pd.isna(v['price']) else float(v['price'])
                snaps.append(dict(batch_id=b.id, channel=channel, month=mname, item_id=r.pid, price=price, units=None,
                                  rank=float(v['rank']) if m == END and not pd.isna(v['rank']) else None,
                                  vp=int(r.vp), nonvp=int(r.nonvp), raw=dict(vp_d=float(r.vp), nonvp_d=float(r.nonvp), family_key=v['fam'], source='backfill',
                                                                             entry=v['entry'], in_scope=True, price_is_current=True)))
            s.execute(insert(Snapshot), snaps)
    tstat = tagging.write_tags(channel, res, groups, month_end)

    # ---------- 统计（覆盖、换手、季度） ----------
    A = W.groupby(['fam', 'pid', 'm']).agg(c=('c', 'sum'), vp=('vp', 'sum'), n=('rid', 'size')).reset_index()
    A['新'] = (A['m'] - A['pid'].map(V['L'])) <= 6
    FM = A.groupby(['fam', 'm'])['c'].sum().unstack(fill_value=0).reindex(columns=MONTHS, fill_value=0)
    last10 = [m for m in MONTHS if m > END - 10]
    f_recent = FM.loc[:, last10].sum(axis=1) / max(1, len(last10))
    quarters = []
    for q0 in range(M0, END + 1, 3):
        ms_ = [m for m in range(q0, q0 + 3) if m <= END]
        a = A[A['m'].isin(ms_)]
        quarters.append(dict(q=f'{fm.ms(q0)} 至 {fm.ms(ms_[-1])[5:]}', units=float(a['c'].sum() / len(ms_)), families=int(a.loc[a['c'] > 0, 'fam'].nunique()),
                             pages=int(a['pid'].nunique()), newshare=float(a.loc[a['新'], 'c'].sum() / max(a['c'].sum(), 1)),
                             vpshare=float(a['vp'].sum() / max(a['n'].sum(), 1))))
    coverage = _coverage(lists, fams, f_recent, W)
    overlap = _overlap(FM, END)
    stats = dict(start=fm.ms(M0), end=month_end, n_months=len(MONTHS), collected_on=coll, pages_listed=len(listed), pages_all=int(len(V)),
                 entries={n: dict(n=len(v['rows']), total=v['total']) for n, v in lists.items()},
                 families=len(fams), fam_status=dict(collections.Counter((famstat.get(fk) or {}).get('status', '无评论') for fk in fams)),
                 reviews_all=int(len(R)), reviews_window=int(len(W)), vp_share=float(W['vp'].mean()) if len(W) else None,
                 syn=int(W['syn'].sum()), truncated_families=len([fk for fk in fams if (famstat.get(fk) or {}).get('status') == '截断']),
                 truncated_pages=sum(len(fams[fk]) for fk in fams if (famstat.get(fk) or {}).get('status') == '截断'),
                 failed_families=len([fk for fk in fams if (famstat.get(fk) or {}).get('status') == '失败']),
                 sharded=sum(1 for fk in fams if (famstat.get(fk) or {}).get('sharded')), req=ds.get('req_stat') or {},
                 coverage=coverage, overlap=overlap, quarters=quarters, recent=[fm.ms(last10[0]), month_end],
                 coef=dict(vp=vpc, nonvp=nvc), config_version=ver, tags=_tag_sources(V, res, A, last10), tag_stat=tstat)
    with session() as s:
        s.add(ChannelRebuild(channel=channel, params=dict(start=start, n=ds.get('n'), collected_on=coll, config_version=ver), stats=stats))
    panel.bump()
    chm.refresh_rank_method()
    ledger.reconcile_due()
    from . import pipeline
    pipeline.after_merge(channel, month_end)
    return stats


def _coverage(lists, fams, f_recent, W) -> dict:
    """前 N 覆盖估计（量级）：家族按它最靠前的商品页排名计一次；用 51 名以后、近期有评论的家族拟合 ln(月销) = a + b·ln(家族名次)，
    外推到类目全部家族（类目商品总数 ÷ 每个家族平均有评论的商品页数）。方法同小试 §3.1。"""
    pid2fam = {p: fk for fk, ps in fams.items() for p in ps}
    vpf = W.groupby('fam')['pid'].nunique()
    out = {}
    for n, v in lists.items():
        rows, totp = v['rows'], v['total']
        if not rows:
            continue
        seen, fr = set(), []
        for r in rows:
            fk = pid2fam.get(r['id'])
            if fk in seen:
                continue
            seen.add(fk)
            fr.append((r['排名'], fk, float(f_recent.get(fk, 0.0))))
        F_ = pd.DataFrame(fr, columns=['rank', 'fam', 's'])
        F_['frank'] = range(1, len(F_) + 1)
        tot = float(F_['s'].sum())
        topn = int(max(r['排名'] for r in rows))
        segs = []
        for lo, hi in ((1, 50), (51, 100), (101, 200), (201, 300), (301, 500), (501, 1000)):
            if lo > topn:
                break
            d = F_[F_['rank'].between(lo, hi)]
            segs.append(dict(seg=f'{lo}–{min(hi, topn)}', families=int(len(d)), active=int((d['s'] > 0).sum()), units=float(d['s'].sum()),
                             share=float(d['s'].sum() / tot) if tot else None, mean=float(d['s'].mean()) if len(d) else None))
        fit = F_[(F_['rank'] > 50) & (F_['s'] > 0)]
        b = a = np.nan
        if len(fit) > 5:
            b, a = np.polyfit(np.log(fit['frank']), np.log(fit['s']), 1)
        mean_v = vpf.reindex(F_['fam']).dropna().mean()
        nf_tot = totp / mean_v if totp and mean_v and not np.isnan(mean_v) else np.nan
        nf = len(F_)

        def tail(k):
            if np.isnan(b) or np.isnan(nf_tot) or nf_tot <= k:
                return np.nan
            r = np.arange(k + 1, int(nf_tot) + 1, dtype=float)
            return float((np.exp(a) * r ** b).sum())
        t_all = tail(nf)
        F200 = F_[F_['rank'] <= 200]
        nz = lambda x: None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)
        out[n] = dict(segments=segs, b=nz(b), n_fam=nf, zero=int((F_['s'] == 0).sum()), mean_v=nz(mean_v), n_fam_total=nz(nf_tot), total_products=totp,
                      units=tot, tail=nz(t_all), topn=topn, cover=nz(tot / (tot + t_all)) if not np.isnan(t_all) else None,
                      cover200=nz(F200['s'].sum() / (tot + t_all)) if not np.isnan(t_all) and topn > 200 else None,
                      top200share=nz(F200['s'].sum() / tot) if tot and topn > 200 else None,
                      last_seg_share=segs[-1]['share'] if segs else None)
    return out


def _overlap(FM: pd.DataFrame, END: int) -> list:
    """换手：没有历史榜单，用重建月销近似排名，比较两个时段前 50 / 前 20 家族的重合率（只含今天仍在榜的家族，是上限）。"""
    def top(cols, k):
        s = FM.loc[:, cols].sum(axis=1)
        return set(s[s > 0].sort_values(ascending=False).index[:k])

    def rate(a, b, k):
        t1, t2 = top(a, k), top(b, k)
        return len(t1 & t2) / max(min(len(t1), len(t2)), 1) if t1 and t2 else None
    cmp_ = [('single4', f'{fm.ms(END - 4)} vs {fm.ms(END)}（单月）', [END - 4], [END]),
            ('half', f'{fm.ms(END - 6)} 至 {fm.ms(END - 4)[5:]} vs {fm.ms(END - 2)} 至 {fm.ms(END)[5:]}（3 个月）', [END - 6, END - 5, END - 4], [END - 2, END - 1, END]),
            ('year1', f'{fm.ms(END - 12)} vs {fm.ms(END)}（单月，隔一年）', [END - 12], [END]),
            ('year3', f'{fm.ms(END - 14)} 至 {fm.ms(END - 12)[5:]} vs {fm.ms(END - 2)} 至 {fm.ms(END)[5:]}（3 个月，隔一年）', [END - 14, END - 13, END - 12], [END - 2, END - 1, END])]
    out = []
    for key, lab, a, b in cmp_:
        if min(a) < FM.columns.min():
            continue
        out.append(dict(key=key, label=lab, top50=rate(a, b, 50), top20=rate(a, b, 20)))
    return out


def _tag_sources(V, res, A, last10) -> list:
    """标签来源构成（按近 10 个月重建销量）：商品页覆盖、来源构成、主要取值（PAGE-F18-01 v8 面板）。"""
    s = A[A['m'].isin(last10)].groupby('pid')['c'].sum().reindex(V.index).fillna(0)
    sw = float(s.sum()) or 1.0
    out = []
    for tg in ('尺寸段', '装', '形态', '台面材质', '柜体材质', '主色', '元素'):
        vals = {p: res[p][tg] for p in V.index}
        known = [p for p, v in vals.items() if v[0]]
        src = collections.Counter()
        top = collections.Counter()
        for p in known:
            v, _c, st, so = vals[p]
            lab = '同家族规格补' if st == 'family_fill' else ('默认' if st == 'business_default' else tagging.SRC_LABEL.get(so, so))
            src[lab] += s[p]
            for x in str(v).split('|'):
                top[x] += s[p]
        out.append(dict(tag=tg, cover=len(known) / max(len(V), 1), cover_units=sum(s[p] for p in known) / sw,
                        sources=[(k, v / sw) for k, v in src.most_common()], top=[(k, v / sw) for k, v in top.most_common(5)]))
    return out


# ====================================================================== 导入现有缓存（免得重新采集）
def import_cache(channel: str = 'homedepot', src: Path | None = None, start: str | None = None, n: int | None = None, log=print) -> dict:
    """把小试缓存（../input/data_v2/渠道历史/homedepot/）复制到 data/backfill/homedepot/ 并重建（以后续采从这里接着）。"""
    if channel != 'homedepot':
        raise ValueError('目前只有 Home Depot 有现成的回补缓存')
    src = Path(src or TRIAL_CACHE)
    if not (src / 'lists').exists():
        raise FileNotFoundError(f'找不到回补缓存 {src}（原始缓存不入库，只在 wen 本机）')
    p = params_for(channel, dict(start=start, n=n))
    dst = cache_dir(channel)
    for sub in ('lists', 'pages', 'reviews'):
        shutil.copytree(src / sub, dst / sub, dirs_exist_ok=True)
    for f in src.glob('stat_*.json'):
        shutil.copy(f, dst / f.name)
    ds = hd_dataset(dst, p['n'])
    ds.update(root=str(dst), n=p['n'])
    return rebuild(channel, ds, p['start'], log)


def rebuild_from_cache(channel: str, log=print) -> dict:
    """API-F28-02 POST /data/channels/{channel}/rebuild：用已有回补缓存重建（参数取品类配置当前版本）。"""
    p = params_for(channel)
    if channel == 'homedepot':
        root = cache_dir(channel)
        if not (root / 'lists').exists():
            raise ValueError('Home Depot 还没有回补数据，先在评论 VP 追踪里发起历史回补')
        ds = hd_dataset(root, p['n'])
        ds.update(root=str(root), n=p['n'])
    else:
        ctx = rk_ctx(channel, p['start'], p['n'])
        if not rk_lists_done(ctx):
            raise ValueError(f'{CHANNEL_NAMES[channel]} 还没有回补数据')
        ds = rk_dataset(channel, ctx)
        ds.update(root=ctx.data, n=p['n'])
    return rebuild(channel, ds, p['start'], log)


# ====================================================================== 状态（页面与 GET 接口）
def last_rebuild(channel: str) -> dict | None:
    with session() as s:
        r = s.scalar(select(ChannelRebuild).where(ChannelRebuild.channel == channel).order_by(ChannelRebuild.id.desc()).limit(1))
        return dict(at=r.at, params=r.params, stats=r.stats) if r else None


def last_job(channel: str) -> dict | None:
    with session() as s:
        j = s.scalar(select(Job).where(Job.kind == 'channel_backfill', Job.target == f'backfill:{channel}', Job.status != 'estimated')
                     .order_by(Job.id.desc()).limit(1))
        return dict(id=j.id, status=j.status, error=j.error, progress=j.progress or {}, params=j.params or {}, at=j.created_at,
                    finished_at=j.finished_at) if j else None


def state(channel: str) -> dict:
    """GET /tools/vp/backfill/{channel}：参数（含版本）、最近任务与进度、最近一次重建摘要。"""
    p = params_for(channel)
    rb = last_rebuild(channel)
    job = last_job(channel)
    st = 'none'
    if job and job['status'] in ('running', 'queued'):
        st = 'running'
    elif job and job['status'] in ('paused', 'stopped_cap', 'failed'):
        st = 'paused'
    elif job and job['status'] == 'done' and job['progress'].get('stage') == 'lists':
        st = 'lists_done'
    elif rb:
        st = 'done'
    return dict(channel=channel, name=CHANNEL_NAMES[channel], params=p, job=job, rebuild=rb, status=st,
                connected=channel == 'homedepot' or (services.connected('brightdata') and services.connected('apify')))


# ====================================================================== 费用闸门任务 channel_backfill
def _hd_plan(p: dict) -> dict:
    """Home Depot 待采量（只读缓存，不发请求）：新增商品页、未完成家族、补变体。"""
    root = cache_dir('homedepot')
    lists_need, pages_new, cached = 0, 0, 0
    allp = {}
    for n in HD_ENTRIES:
        g = load_json(str(root / 'lists' / f'{n}.json')) or {'rows': []}
        rows = ranked(g, p['n'])
        if len(rows) < p['n'] and not g.get('end'):
            lists_need += math.ceil((p['n'] - len(rows)) / 24)
        for r in rows:
            allp.setdefault(r['id'], r)
    for pid in allp:
        if (load_json(str(root / 'pages' / f'{pid}.json')) or {}).get('status') == 200:
            cached += 1
    missing_list = sum(max(0, p['n'] - len(ranked(load_json(str(root / 'lists' / f'{n}.json')) or {'rows': []}, p['n']))) for n in HD_ENTRIES)
    pages_new = len(allp) - cached + missing_list
    fam_todo = 0
    if allp and not missing_list:
        fams = families_from_pages({n: ranked(load_json(str(root / 'lists' / f'{n}.json')) or {'rows': []}, p['n']) for n in HD_ENTRIES}, root)
        for fk, mem in fams.items():
            if max(allp[x].get('review_count') or 0 for x in mem) > 0 and (load_json(str(root / 'reviews' / f'{fk}.json')) or {}).get('状态') not in ('完整', '截断'):
                fam_todo += 1
    return dict(lists=lists_need, pages_new=pages_new, cached=cached, fam_todo=fam_todo)


def est_backfill(params: dict) -> dict:
    ch = params.get('channel') or (params.get('target') or '').split(':')[-1]
    if ch not in PLAT and ch != 'homedepot':
        raise ValueError('未知渠道')
    p = params_for(ch, params)
    if ch == 'homedepot':
        plan = _hd_plan(p)
        calls = plan['lists'] + round(plan['pages_new'] * TRIAL_REQ / TRIAL_PAGES) + plan['fam_todo'] * 4
        if not calls:  # 没有要采的内容：弹窗显示说明并禁用“确认并开始”；按新参数重建走其他渠道数据页
            note = (f"没有需要采集的商品页（已完成 {plan['cached']} 个商品页）；要按参数 v{p['config_version']} 重建历史，"
                    f"到其他渠道数据页点“按当前参数重建”")
        else:
            note = (f"起始 {p['start']} · 每个类目前 {p['n']} 个商品页 · 新增约 {plan['pages_new']} 个商品页、{plan['fam_todo']} 个未完成家族；"
                    f"已完成的 {plan['cached']} 个商品页不重复请求。估算依据：2026-11-03 回补 598 个商品页共 2,884 次请求，按新增商品页折算。直连免费")
        return dict(service=None, channel=ch, calls=calls, usd_lo=0, usd_hi=0, minutes=round(calls * 1.7 / 60 + (1 if calls else 0), 1), note=note,
                    stage='collect', params=p, nothing=not calls)
    services.client('brightdata')  # 未连接时抛 NotConnected，弹窗里说明（AC-F16-03）
    services.client('apify')
    ctx = rk_ctx(ch, p['start'], p['n'])
    from ..reviewkit import pipeline as rkp
    if not rk_lists_done(ctx):
        hi = sum(max(5, math.ceil(int(e['top_n']) * 3 / 24) + 3) * (4 if ch == 'wayfair' else 3) for e in rkp.entries(ctx))
        lo = sum(math.ceil(int(e['top_n']) / 24) for e in rkp.entries(ctx))
        return dict(service='brightdata', channel=ch, calls=hi, usd_lo=round(lo * 0.0015, 2), usd_hi=round(hi * 0.0015, 2), minutes=round(2 + hi * 0.5, 1),
                    note=f"第一步：列表 + 规格（Bright Data 约 {lo}–{hi} 次请求，$1.5 / 千次）；评论（Apify）费用列表采完后再估算、再确认", stage='lists', params=p)
    from ..reviewkit import estimate as rk_estimate
    est = rk_estimate.run(ctx)
    pl, t = est['平台'], est['合计']
    svcs = {'brightdata': dict(calls=sum(v.get('BD请求', 0) for v in pl.values()), usd_lo=round(t['BD费用'] * 0.5, 2), usd_hi=t['BD费用']),
            'apify': dict(calls=len(pl), usd_lo=round(t['Apify费用'] * 0.5, 2), usd_hi=t['Apify费用'])}
    note = '第二步：全部历史评论（Apify）与商品详情（Bright Data）。' + '；'.join(
        f"{v['商品数']} 个商品页，预计评论 {v['预计窗口内评论'][0]}–{v['预计窗口内评论'][1]} 条" for v in pl.values()) + '。只计未完成部分，达到月度上限即停，已采保留'
    return dict(service='apify', services=svcs, channel=ch, calls=sum(v['calls'] for v in svcs.values()), usd_lo=round(t['总费用'] * 0.5, 2),
                usd_hi=t['总费用'], minutes=t['预计耗时分钟'], note=note, stage='collect', params=p)


def run_backfill(ctx):
    ch = ctx.params.get('channel') or ctx.target.split(':')[-1]
    p = params_for(ch, ctx.params)
    ctx.progress(channel=ch, start=p['start'], n=p['n'], config_version=p['config_version'], blocked='', stage='collect')
    if ch == 'homedepot':
        def check():
            ctx.allow('homedepot')  # 只检查“暂停”（Home Depot 不计费）
        fetcher = _FETCHER.get('homedepot') or Polite()
        hd = HD(cache_dir(ch), fetcher, p['n'], month_add(p['start'], -LOOKBACK) + '-01', check=check, progress=lambda **k: ctx.progress(**k))
        try:
            hd.collect(p['start'] + '-01')
        except Blocked as e:
            ctx.progress(blocked=f'Home Depot 回补已暂停：{e}，已采部分保留', **hd.counters())
            raise costgate.Paused() from e
        ctx.progress(**hd.counters())
        ds = hd_dataset(cache_dir(ch), p['n'], collected_on=date.today().isoformat())
        ds.update(root=str(cache_dir(ch)), n=p['n'])
    else:
        from ..reviewkit import pipeline as rkp
        rc = rk_ctx(ch, p['start'], p['n'], job=ctx)
        if not rk_lists_done(rc):
            ctx.progress(stage='lists')
            rkp.step_lists(rc)
            ctx.progress(pages_total=len(rkp.selected(rc)), lists_done=True)
            return  # 列表采完：再点“评估并回补”确认评论费用
        rows = rkp.selected(rc)
        ctx.progress(pages_total=len(rows))
        rkp.step_collect(rc)
        ds = rk_dataset(ch, rc)
        ds.update(root=rc.data, n=p['n'])
        ctx.progress(pages_done=len(rows), reviews=int(len(ds['reviews'])),
                     truncated=sum(1 for s in ds['famstat'].values() if s['status'] == '截断'))
    stats = rebuild(ch, ds, p['start'], log=lambda *a: None)
    ctx.progress(rebuilt=True, families=stats['families'], reviews_window=stats['reviews_window'], truncated_pages=stats['truncated_pages'])


_FETCHER: dict = {}  # 测试注入假站点：backfill._FETCHER['homedepot'] = Polite(transport=假站点, sleep=假时钟)

costgate.register('channel_backfill', '历史回补', est_backfill, run_backfill)
