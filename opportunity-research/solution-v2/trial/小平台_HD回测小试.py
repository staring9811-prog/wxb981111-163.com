"""小平台回测小试：Home Depot 浴室柜，用评论日期重建月度历史，按 Amazon 第九版思路做简化回测。
用法：
  python 小平台_HD回测小试.py 采集     # 断点续采，缓存在 input/data_v2/渠道历史/homedepot/（不入库）
  python 小平台_HD回测小试.py 分析     # 重建面板、覆盖与换手、打标、回测、wen 判断核对 → solution-v2/开发建议/小平台_HD回测小试.md
采集口径：两个类目页（带台面 / 无台面，与 tools/评论月度VP追踪器 projects/浴室柜_2026.json 的 HDP 入口相同）Top Sellers 排序，
排除广告位，各取前 TOPN 个商品页；每个商品页抓一次评论首页 HTML（规格 + 首页评论，首页评论相同 = 同一评论家族），
每个家族用站点评论接口（与评论页同一数据源，每页 30 条、单个排序最多约 17 页）按最新排序抓到 CUTOFF；
到上限时按星级、再按"仅 VP"分片补深，仍不够的记为截断。另取按最早排序第一页，得家族首条评论日期。
不改 tools/ 与 app/ 下原文件，只 import。"""
import os, sys, re, json, time, random, math, urllib.request, urllib.error, collections
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools', '评论月度VP追踪器'))
from reviewkit.common import objects_by_key, decode_at, add_query, save_json, load_json   # noqa: E402

CACHE = os.path.join(ROOT, 'input', 'data_v2', '渠道历史', 'homedepot')
BASE = 'https://www.homedepot.com'
ENTRIES = {'带台面': BASE + '/b/Bath-Bathroom-Vanities-Bathroom-Vanities-with-Tops/N-5yc1vZcfw5',
           '无台面': BASE + '/b/Bath-Bathroom-Vanities-Bathroom-Vanities-without-Tops/N-5yc1vZcfv9'}
TOPN = int(os.environ.get('TOPN', '300'))
CUTOFF = '2023-07-01'          # 评论抓到这一天（窗口 2024-01 起，多抓半年判断变体是否为新）
CAP_START = 481                # 单个排序最多到 startIndex 481（17 页）
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36')
STAT = collections.Counter(); DELAY = [1.3]


def log(*a):
    msg = time.strftime('%H:%M:%S ') + ' '.join(str(x) for x in a)
    print(msg, flush=True)
    with open(os.path.join(CACHE, 'run.log'), 'a', encoding='utf-8') as f: f.write(msg + '\n')


def fetch(url, body=None):
    """礼貌请求：间隔 ≥ 1 秒；403/429 降速（间隔翻倍、停 30 秒起）；最多 3 次。"""
    last = (0, b'')
    for i in range(3):
        time.sleep(DELAY[0] + random.uniform(0, 0.8))
        hdr = {'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9'}
        if body is not None:
            hdr.update({'Content-Type': 'application/json', 'x-experience-name': 'general-merchandise', 'apollographql-client-name': 'general-merchandise',
                        'Origin': BASE, 'Referer': BASE + '/'})
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=hdr)
        STAT['请求'] += 1
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                DELAY[0] = max(1.3, DELAY[0] * 0.9)
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            last = (e.code, e.read()); STAT[f'HTTP {e.code}'] += 1
            if e.code == 404: return last
            if e.code in (403, 429):
                DELAY[0] = min(DELAY[0] * 2, 20); log(f'  {e.code}，降速到 {DELAY[0]:.1f}s，停 {30 * (i + 1)}s'); time.sleep(30 * (i + 1)); continue
        except Exception as e:
            last = (0, str(e).encode()); STAT['网络错误'] += 1
        time.sleep(3 * (i + 1))
    STAT['失败（重试 3 次）'] += 1
    return last


# ---------- 1. 列表 ----------
def list_entry(name, url):
    f = os.path.join(CACHE, 'lists', f'{name}.json'); got = load_json(f) or {'rows': [], 'off': 0, 'done': False}
    rows, off = got['rows'], got['off']
    while not got['done'] and sum(not r['sponsored'] for r in rows) < TOPN:
        st, b = fetch(add_query(url, sortby='topsellers', Nao=off or None))
        if st != 200: log(f'{name} 列表 Nao={off} HTTP {st}，停'); STAT['列表失败'] += 1; break
        s = b.decode('utf-8', 'ignore')
        m = re.search(r'products\(\{\\"filter\\":\{[^)]*\}\)":(\[)', s)
        refs = decode_at(s, m.start(1)) if m else []
        ids = [r['__ref'].split('-')[-1] for r in refs if isinstance(r, dict) and '__ref' in r]
        tot = re.search(r'"totalProducts":(\d+)', s)
        if tot: got['totalProducts'] = int(tot.group(1))
        if not ids: got['done'] = True; break
        objs = objects_by_key(s, r'base-searchNav-\d+')
        for pid in ids:
            o = objs.get(f'base-searchNav-{pid}', {}); ident = o.get('identifiers') or {}; info = o.get('info') or {}
            pricing = next((v for k, v in o.items() if k.startswith('pricing')), None) or {}
            rr = (o.get('reviews') or {}).get('ratingsReviews') or {}
            rows.append(dict(id=pid, url=BASE + ident.get('canonicalUrl', f'/p/{pid}'), title=ident.get('productLabel', ''), brand=ident.get('brandName', ''),
                             sponsored=bool(info.get('isSponsored')), price=pricing.get('value'),
                             rating=float(rr['averageRating']) if rr.get('averageRating') else None, review_count=int(rr['totalReviews']) if rr.get('totalReviews') else 0))
        off += len(ids); got.update(rows=rows, off=off); save_json(f, got)
    got['done'] = True; save_json(f, got)
    rank = 0
    for r in rows:
        if r['sponsored']: continue
        rank += 1; r['排名'] = rank
    log(f'{name}: 非广告 {rank} 个，类目商品总数 {got.get("totalProducts")}')
    return [r for r in rows if r.get('排名') and r['排名'] <= TOPN]


# ---------- 2. 商品页（规格 + 首页评论） ----------
def product_page(r):
    f = os.path.join(CACHE, 'pages', f"{r['id']}.json"); got = load_json(f)
    if got and got.get('status') == 200: return got
    url = f"{BASE}/p/reviews/x/{r['id']}/1"   # 只用 ID，站点重定向到规范地址（避免标题里的 é、á 等字符）
    st, b = fetch(url)
    out = {'status': st}
    if st == 200:
        s = b.decode('utf-8', 'ignore'); pid = r['id']
        cat = objects_by_key(s, rf'base-catalog-{pid}').get(f'base-catalog-{pid}') or {}
        d = cat.get('details') or {}
        out['specs'] = {sp.get('specName'): sp.get('specValue') for g in cat.get('specificationGroup') or [] for sp in g.get('specifications') or []}
        out['highlights'] = d.get('highlights') or []; out['description'] = d.get('description') or ''
        pr = next((v for k, v in cat.items() if k.startswith('pricing')), None) or {}
        ident = cat.get('identifiers') or {}
        out.update(price=pr.get('value'), title=ident.get('productLabel'), brand=ident.get('brandName'),
                   discontinued=((cat.get('availabilityType') or {}).get('discontinued')))
        res = []
        for mm in re.finditer(r'"reviews\(\{', s):
            end = s.find('})":{', mm.start()); k = s[mm.start():end]
            if end > 0 and len(k) < 600 and 'startIndex\\":1' in k and f'itemId\\":\\"{pid}' in k:
                res = decode_at(s, end + len('})":')).get('Results') or []; break
        out['sig'] = sorted(str(x.get('Id')) for x in res)
        out['sig_pids'] = sorted({str(x.get('ProductId')) for x in res})
    else:
        STAT['商品页失败'] += 1
    save_json(f, out); return out


# ---------- 3. 家族评论 ----------
GQL = ('query reviews($itemId: String!, $startIndex: Int, $pagesize: String, $sortBy: String, $filters: ReviewsFilterInput, $excludeFamily: Boolean, '
       '$searchTerm: String, $recfirstpage: String) { reviews(itemId: $itemId, startIndex: $startIndex, pagesize: $pagesize, sortBy: $sortBy, filters: $filters, '
       'excludeFamily: $excludeFamily, searchTerm: $searchTerm, recfirstpage: $recfirstpage) { Results { Id SubmissionTime Rating ProductId BadgesOrder IsSyndicated '
       'OriginalProductName } TotalResults } }')


def gql_page(pid, start, sort='newest', stars=None, vp=False):
    body = {'operationName': 'reviews', 'query': GQL, 'variables': {
        'itemId': pid, 'startIndex': start, 'pagesize': '30', 'sortBy': sort, 'excludeFamily': False, 'searchTerm': None, 'recfirstpage': '30',
        'filters': {'isVerifiedPurchase': vp, 'prosCons': None, 'starRatings': stars}}}
    st, b = fetch(BASE + '/federation-gateway/graphql?opname=reviews', body)
    if st != 200: return st, None, []
    try:
        d = json.loads(b)['data']['reviews'] or {}
    except Exception:
        return -1, None, []
    return st, d.get('TotalResults'), d.get('Results') or []


def sweep(pid, revs, stars=None, vp=False):
    """按最新排序往前抓，直到早于 CUTOFF 或到上限。返回（这一片完整到的日期，总数，是否失败）。"""
    start, total = 1, None
    while start <= CAP_START:
        st, tot, res = gql_page(pid, start, stars=stars, vp=vp)
        if st != 200: return None, total, True
        total = tot if total is None else total
        if not res: return '0000-00-00', total, False
        for x in res:
            revs[str(x['Id'])] = dict(d=(x.get('SubmissionTime') or '')[:10], r=x.get('Rating'), vp='verifiedPurchaser' in (x.get('BadgesOrder') or []),
                                      syn=bool(x.get('IsSyndicated')), pid=str(x.get('ProductId')), name=x.get('OriginalProductName') or '')
        last = (res[-1].get('SubmissionTime') or '')[:10]
        if last < CUTOFF or start + 30 > (total or 0): return '0000-00-00', total, False
        start += 30
    return last, total, False   # 到上限：这一片只完整到 last


def family_reviews(fk, pid):
    f = os.path.join(CACHE, 'reviews', f'{fk}.json'); got = load_json(f)
    if got and got.get('状态') in ('完整', '截断'): return got
    revs = {}; notes = []
    st, tot, res = gql_page(pid, 1, sort='oldest')
    if st != 200:
        out = {'状态': '失败', '备注': f'最早排序 HTTP {st}', 'reviews': {}}; save_json(f, out); STAT['家族失败'] += 1; return out
    first = (res[0].get('SubmissionTime') or '')[:10] if res else None
    for x in res:
        revs[str(x['Id'])] = dict(d=(x.get('SubmissionTime') or '')[:10], r=x.get('Rating'), vp='verifiedPurchaser' in (x.get('BadgesOrder') or []),
                                  syn=bool(x.get('IsSyndicated')), pid=str(x.get('ProductId')), name=x.get('OriginalProductName') or '')
    upto, total, fail = sweep(pid, revs)
    complete_to = upto
    if fail: complete_to = None
    elif upto > CUTOFF:   # 截断：按星级分片
        notes.append(f'总排序到上限，只完整到 {upto}，按星级分片')
        parts = []
        for s_ in (1, 2, 3, 4, 5):
            u, t, fl = sweep(pid, revs, stars=[s_])
            if fl: fail = True; break
            if u > CUTOFF:
                u2, t2, fl2 = sweep(pid, revs, stars=[s_], vp=True)   # 该星级只看 VP 再往前
                if fl2: fail = True; break
                notes.append(f'{s_} 星到上限（{u}），VP 分片到 {u2}')
                parts.append(u)        # 非 VP 仍只完整到 u
            else:
                parts.append(u)
        complete_to = None if fail else max(parts)
    if fail:
        out = {'状态': '失败', '备注': '；'.join(notes + ['分页中途失败']), 'reviews': {}}; save_json(f, out); STAT['家族失败'] += 1; return out
    status = '完整' if complete_to <= CUTOFF else '截断'
    out = {'状态': status, '完整到': complete_to, '首条评论': first, '评论总数': total, '备注': '；'.join(notes), 'reviews': revs}
    save_json(f, out); return out


def collect():
    os.makedirs(CACHE, exist_ok=True)
    lists = {n: list_entry(n, u) for n, u in ENTRIES.items()}
    allp = {}
    for n, rows in lists.items():
        for r in rows: allp.setdefault(r['id'], r)
    log(f'商品页 {len(allp)} 个（两类目去重后）')
    for i, (pid, r) in enumerate(allp.items()):
        product_page(r)
        if i % 50 == 0: log(f'  商品页 {i}/{len(allp)}  {dict(STAT)}')
    fams = families(lists)
    log(f'评论家族 {len(fams)} 个')
    for i, (fk, mem) in enumerate(sorted(fams.items(), key=lambda kv: -max(allp[p]['review_count'] for p in kv[1]))):
        rep = max(mem, key=lambda p: allp[p]['review_count'])
        if allp[rep]['review_count'] == 0: continue
        g = family_reviews(fk, rep)
        if i % 10 == 0: log(f'  家族 {i}/{len(fams)} {fk} {g["状态"]} {len(g["reviews"])} 条  {dict(STAT)}')
    save_json(os.path.join(CACHE, 'stat_last_run.json'), dict(STAT))
    log('采集完成', dict(STAT))


def supplement():
    """补变体：不在榜、但 2024-01 起有评论的变体也抓一次页面（规格、当前价格、是否下架），用于打标和价位。"""
    lp = set()
    for n in ENTRIES: lp |= {r['id'] for r in (load_json(os.path.join(CACHE, 'lists', f'{n}.json')) or {'rows': []})['rows']}
    todo = set()
    for fn in os.listdir(os.path.join(CACHE, 'reviews')):
        g = load_json(os.path.join(CACHE, 'reviews', fn)) or {}
        todo |= {x['pid'] for x in (g.get('reviews') or {}).values() if x['d'] >= '2024-01-01'}
    todo = sorted(todo - lp)
    log(f'补变体 {len(todo)} 个')
    for i, p in enumerate(todo):
        product_page({'id': p, 'url': f'{BASE}/p/x/{p}'})
        if i % 50 == 0: log(f'  补变体 {i}/{len(todo)}  {dict(STAT)}')
    save_json(os.path.join(CACHE, 'stat_supplement.json'), dict(STAT)); log('补变体完成', dict(STAT))


def families(lists):
    """首页评论 ID 有重叠（≥ 一半）或首页评论里出现对方商品 ID 的商品页 = 同一评论家族（共享评论）。"""
    pids = list(dict.fromkeys(p['id'] for rows in lists.values() for p in rows))
    pg = {p: load_json(os.path.join(CACHE, 'pages', f'{p}.json')) or {} for p in pids}
    up = {p: p for p in pids}
    def root(x):
        while up[x] != x: up[x] = up[up[x]]; x = up[x]
        return x
    bysig = {}
    for p in pids:
        s = set(pg[p].get('sig') or [])
        if not s: continue
        for q, sq in bysig.items():
            if len(s & sq) >= min(len(s), len(sq)) / 2: up[root(p)] = root(q)
        bysig[p] = s
    for p in pids:   # 首页评论里出现的变体 ID 本身也在列表里 → 同家族
        for q in pg[p].get('sig_pids') or []:
            if q in up and pg[q].get('sig'): up[root(q)] = root(p)
    fam = collections.defaultdict(list)
    for p in pids: fam[root(p)].append(p)
    return {f'F{k}': v for k, v in fam.items()}


# ====================================================================== 分析
def load_all():
    lists = {}
    for n in ENTRIES:
        g = load_json(os.path.join(CACHE, 'lists', f'{n}.json')) or {'rows': []}
        rows = [dict(r) for r in g['rows'] if not r['sponsored']][:TOPN]
        for i, r in enumerate(rows, 1): r.update(排名=i, 入口=n)
        lists[n] = (rows, g.get('totalProducts'))
    fams = families({n: v[0] for n, v in lists.items()})
    pages = {p: load_json(os.path.join(CACHE, 'pages', f'{p}.json')) or {} for ps in fams.values() for p in ps}
    revs = {fk: load_json(os.path.join(CACHE, 'reviews', f'{fk}.json')) for fk in fams}
    return lists, fams, pages, revs


ELEM_MAP = {'Shaker': '夏克式', 'Fluted': '竖棱', 'Reeded': '竖棱', 'Farmhouse': '农场风装饰饰条', 'Barn Door': '农场风装饰饰条',
            'Glass Door': '玻璃门', 'Slatted': '木条格栅', 'Rattan': 'rattan'}
UNKS = {'未知', '信息不足', '待图片核验', '', 'nan', 'None', None}


def tag_variant(TR, title, specs, highlights):
    """v12.2 规则（app/pdt/core/tagging_rules.py 的 Tagger，不用默认值）+ HD 规格字段。返回原始标签与来源。"""
    row = {'子ASIN': 'HD', '商品标题': title or '', 'SKU属性': '', '商品尺寸': ''}
    ex = [{'attributes': ' | '.join(f'{k}:{v}' for k, v in (specs or {}).items() if v), 'features': ' '.join(highlights or [])}] if specs else []
    tags = TR.Tagger(row, {}, export_rows=ex, accessory_default=False).run()[0]
    out = {'宽': tags['D9宽(in)'], 'D7': tags['D7柜体材质'], 'D8': tags['D8台面材质'], 'D8盆': tags['D8台盆材质'], 'D6': tags['D6柜体颜色'], 'D5': tags['D5元素']}
    t = (title or '').lower(); sp = specs or {}
    asm = str(sp.get('Assembled', '')).lower()
    # 装：HD 规格"Assembled"字段 > 标题"(Assembled)" / RTA 字样 > v12.2 文本规则；都没有 → 未知（不默认拆装）
    if 'ready to assemble' in asm or 'unassembled' in asm or 'partially' in asm: out['装'], out['装来源'] = '拆装', '规格'
    elif asm.startswith('assembled') or asm == 'fully assembled': out['装'], out['装来源'] = '整装', '规格'
    elif '(assembled)' in t or 'fully assembled' in t: out['装'], out['装来源'] = '整装', '标题'
    elif re.search(r'ready[ -]to[ -]assemble|\brta\b|unassembled', t): out['装'], out['装来源'] = '拆装', '标题'
    elif tags['D2安装方式'] in ('整装', '拆装'): out['装'], out['装来源'] = tags['D2安装方式'], '规则'
    else: out['装'], out['装来源'] = '未知', ''
    vt = str(sp.get('Vanity Type', '')).lower()
    if 'float' in vt or 'wall' in vt: out['形态'], out['形态来源'] = '悬浮式', '规格'
    elif 'corner' in vt: out['形态'], out['形态来源'] = '转角式', '规格'
    elif 'pedestal' in vt or 'console' in vt: out['形态'], out['形态来源'] = '柱状盆', '规格'
    elif 'freestanding' in vt or 'free standing' in vt: out['形态'], out['形态来源'] = '落地式', '规格'
    elif tags['D1产品形态'] not in UNKS: out['形态'], out['形态来源'] = tags['D1产品形态'], '规则'
    else: out['形态'], out['形态来源'] = '未知', ''
    if out['宽'] is None:
        for k in ('Product Width (in.)', 'Cabinet Width (in.)', 'Vanity Width (in.)'):
            m = re.match(r'\s*(\d+(?:\.\d+)?)', str(sp.get(k, '')))
            if m: out['宽'] = float(m.group(1)); break
    return out


def analyze():
    import numpy as np, pandas as pd
    from scipy.stats import spearmanr, norm
    from sklearn.linear_model import Ridge
    sys.path.insert(0, os.path.join(ROOT, 'app', 'pdt', 'core'))
    import tagging_rules as TR
    from families import band, cab, color, top_type, mi, ms
    L = []; P = lambda *a: L.extend(a)
    pct = lambda x: '—' if x is None or (isinstance(x, float) and np.isnan(x)) else f'{x:.0%}'
    M0, END = mi('2024-01'), mi('2026-10'); MONTHS = list(range(M0, END + 1))
    lists, fams, pages, revs = load_all()
    listed = {}
    for n, (rows, _) in lists.items():
        for r in rows: listed.setdefault(r['id'], r)
    pid2fam = {p: fk for fk, ps in fams.items() for p in ps}

    # ---------------- 1. 采集统计 ----------------
    stat = collections.Counter()
    for fn in ('stat_main_run.json', 'stat_last_run.json', 'stat_supplement.json'):   # 主采集、续采重试、补变体三轮（第一次运行只翻了列表页，约 50 次请求，未计）
        stat.update(load_json(os.path.join(CACHE, fn)) or {})
    st_fam = collections.Counter((g or {}).get('状态', '无评论（未采）') for g in revs.values())
    rv = []
    for fk, g in revs.items():
        if not g or g.get('状态') not in ('完整', '截断'): continue
        for rid, x in g['reviews'].items():
            rv.append((fk, rid, x['d'], x['r'], x['vp'], x['syn'], x['pid'], x['name']))
    R = pd.DataFrame(rv, columns=['fam', 'rid', 'd', 'r', 'vp', 'syn', 'pid', 'name']).drop_duplicates('rid')
    R['m'] = R['d'].map(lambda d: mi(d) if d and d[:4].isdigit() else -1)
    trunc = {fk: g['完整到'] for fk, g in revs.items() if g and g.get('状态') == '截断'}
    W = R[(R['m'] >= M0) & (R['m'] <= END)].copy()
    W['c'] = np.where(W['vp'], 50, 20)
    fam_first = {fk: g.get('首条评论') for fk, g in revs.items() if g and g.get('首条评论')}

    # ---------------- 4. 打标（变体 = 商品页 ID） ----------------
    names = R.sort_values('d').groupby('pid')['name'].agg(lambda s: next((x for x in reversed(list(s)) if x), ''))
    allpid = sorted(set(W['pid']) | set(listed))
    rowsV = []
    for p in allpid:
        if p not in pages: pages[p] = load_json(os.path.join(CACHE, 'pages', f'{p}.json')) or {}
        pg = pages.get(p) or {}; lr = listed.get(p)
        title = (lr or {}).get('title') or pg.get('title') or names.get(p, '')
        t = tag_variant(TR, title, pg.get('specs'), pg.get('highlights'))
        fam = pid2fam.get(p) or (W.loc[W['pid'] == p, 'fam'].iloc[0] if (W['pid'] == p).any() else None)
        rowsV.append(dict(pid=p, fam=fam, title=title, 有规格=bool(pg.get('specs')), 在榜=lr is not None, 价格=(lr or {}).get('price') or pg.get('price'),
                          品牌=(lr or {}).get('brand') or pg.get('brand'), 下架=bool(pg.get('discontinued')), 页面=pg.get('status'),
                          入口=(lr or {}).get('入口'), 排名=(lr or {}).get('排名'), **t))
    V = pd.DataFrame(rowsV).set_index('pid')
    fb = V.dropna(subset=['品牌']).groupby('fam')['品牌'].agg(lambda s: s.mode().iloc[0])
    V['品牌'] = V['品牌'].fillna(V['fam'].map(fb))
    # 家族内补：同系列没有自己规格的变体，装 / 形态 / 柜体 / 台面按同家族已知变体的众数补（标"家族补"）
    for col, src in (('装', '装来源'), ('形态', '形态来源')):
        mode = V[V[col] != '未知'].groupby('fam')[col].agg(lambda s: s.mode().iloc[0])
        k = (V[col] == '未知') & V['fam'].isin(mode.index)
        V.loc[k, col] = V.loc[k, 'fam'].map(mode); V.loc[k, src] = '家族补'
    for col in ('D7', 'D8'):
        V[col + '来源'] = np.where(V[col].isin(UNKS), '', '文本')
        mode = V[~V[col].isin(UNKS)].groupby('fam')[col].agg(lambda s: s.mode().iloc[0])
        k = V[col].isin(UNKS) & V['fam'].isin(mode.index)
        V.loc[k, col] = V.loc[k, 'fam'].map(mode); V.loc[k, col + '来源'] = '家族补'
    V['形态'] = V['形态'].replace({'两用': '落地式'})
    k = V['形态'] == '未知'; V.loc[k, '形态来源'] = '默认'; V.loc[k, '形态'] = '落地式'   # 与 Amazon 口径同：没写形态按落地式
    V['尺寸段'] = V['宽'].map(band)
    V['柜体材质'] = V['D7'].map(cab)
    V['台面材质'] = V['D8'].map(lambda v: '未知' if v in UNKS else v)
    V['台面类型'] = [top_type(t, s) for t, s in zip(V['D8'], V['D8盆'])]
    V['主色'] = V['D6'].map(color)
    V['元素'] = V['D5'].map(lambda v: sorted({ELEM_MAP[x] for x in str(v).split('；') if x in ELEM_MAP}) or ['未知'])
    V['元素一'] = V['元素'].map(lambda l: l[0])
    V['框'] = np.where(V['尺寸段'].notna() & (V['装'] != '未知'), V['尺寸段'].fillna('') + ' · ' + V['装'] + ' · ' + V['形态'], '未知')
    V['PB'] = V['品牌'].isin(['Glacier Bay', 'Home Decorators Collection'])

    # ---------------- 2. 重建：月销与上架月 ----------------
    vfirst = R.groupby('pid')['d'].min()
    def reliable_first(p):
        d = vfirst.get(p); fk = V.at[p, 'fam'] if p in V.index else None
        if d is None: return None
        if fk in trunc and d < trunc[fk]: return None   # 截断家族里早于"完整到"的首评不可信，按老品
        return d
    V['首评'] = [reliable_first(p) for p in V.index]
    V['L'] = V['首评'].map(lambda d: mi(d) if isinstance(d, str) and d >= CUTOFF else -10 ** 6)   # 抓取起点前就有评论 = 老品
    W = W.join(V[['L']], on='pid')
    W['新'] = (W['m'] - W['L']) <= 6
    A = W.groupby(['fam', 'pid', 'm']).agg(c=('c', 'sum'), vp=('vp', 'sum'), n=('rid', 'size'), 新=('新', 'first')).reset_index().join(
        V[['尺寸段', '装', '形态', '框', '台面材质', '台面类型', '主色', '柜体材质', '元素', '元素一', 'PB', '价格', '品牌']], on='pid')
    CAT = A.groupby('m')['c'].sum().reindex(MONTHS, fill_value=0)
    FM = A.groupby(['fam', 'm'])['c'].sum().unstack(fill_value=0).reindex(columns=MONTHS, fill_value=0)

    P('# 小平台回测小试：Home Depot 浴室柜（评论重建月度历史 → 按 Amazon 方法回测）', '',
      f'> 由 `trial/小平台_HD回测小试.py` 生成（`采集` 断点续采，`分析` 出本页）。采集日 2026-11-03，原始缓存在 `input/data_v2/渠道历史/homedepot/`（不入库）。'
      '本页数字都是脚本实际输出；"结论"一节的判断写在脚本里，跟着数字一起生成。', '')
    nrev_all = len(R); nw = len(W)
    P('## 1. 采集', '',
      f'- **范围**：两个类目页（带台面 / 无台面，入口与评论追踪器 `projects/浴室柜_2026.json` 的 HDP 两项相同），Top Sellers 排序，排除广告位，各取前 {TOPN} 个商品页；'
      f'页面显示类目商品总数：带台面 {lists["带台面"][1]:,}、无台面 {lists["无台面"][1]:,}（含所有颜色尺寸页和第三方卖家，大多数没有销量）。',
      f'- **商品页**：两类目合计 {len(listed)} 个（去重后），商品页抓取失败 {sum(1 for p in listed if (pages.get(p) or {}).get("status") != 200)} 个。'
      f'同系列不同颜色 / 尺寸是不同商品页、但共享同一批评论（每条评论带写评论时的商品页 ID），按首页评论重叠合并成 **{len(fams)} 个评论家族**（相当于亚马逊父体）。',
      f'- **评论**：家族状态 ' + '、'.join(f'{k} {v}' for k, v in st_fam.most_common()).replace('无评论（未采）', '0 条评论（无需采）') + f'；共采到 {nrev_all:,} 条评论（去重），其中 2024-01 至 2026-10 的 {nw:,} 条'
      f'（VP {int(W["vp"].sum()):,} 条 = {W["vp"].mean():.0%}；转载自品牌站 {int(W["syn"].sum()):,} 条 = {W["syn"].mean():.0%}，按 hdp.py 口径计入）。',
      f'- **请求**：主采集、失败重试、补变体三轮合计 ' + '、'.join(f'{k} {v}' for k, v in stat.items()) + '（续采重试只计最后一次；另有最早一次只翻了列表页的运行约 50 次请求）；' + ('没有遇到 403 / 429。' if not (stat.get('HTTP 403') or stat.get('HTTP 429')) else f"403 {stat.get('HTTP 403', 0)} 次、429 {stat.get('HTTP 429', 0)} 次。") +
      '每次请求间隔 1.3–2.1 秒，403 / 429 时间隔翻倍并停 30 秒起，最多重试 3 次。', '',
      '**评论口径与截断**：站点每个排序最多给约 17 页（510 条）。先按最新排序往前抓到 2023-07；到上限的家族按 1–5 星分片各自再抓 17 页，某个星级仍到上限的再加"仅 VP"分片；'
      '另取按最早排序第一页拿家族首条评论日期。分片后仍到上限的记为**截断**，"完整到"之前的月份评论不全。', '')
    if trunc:
        tw = FM.loc[FM.index.isin(list(trunc))]
        early = [m for m in MONTHS]
        lost = []
        for fk, d in trunc.items():
            if fk in FM.index: lost.append((fk, d, FM.loc[fk, mi('2026-01'):END].sum() / 10))
        P(f'截断家族 {len(trunc)} 个，"完整到"日期：' + '、'.join(sorted({d[:7] for d in trunc.values()})) +
          f'；它们 2026 年月均重建销量占全部的 {sum(x[2] for x in lost) / (CAT.loc[mi("2026-01"):END].mean()):.0%}。'
          f'这些家族在"完整到"之前的月份只少算了非 VP 的部分（VP 分片更深），影响见 §2。', '')
    else:
        P('分片后**没有家族被截断**：所有家族 2023-07 以来的评论都抓全了（最大的家族 Glacier Bay 白色树脂一体系列靠星级分片补全）。', '')

    P('## 2. 重建的月度历史', '',
      '- 月销 ≈ VP 评论 × 50 + 非 VP 评论 × 20（与系统默认一致），按评论写在哪个商品页（变体）记到变体上，再按变体的尺寸、颜色等打标；家族 = 评论家族。',
      '- 上架月：变体的首条评论月（抓取起点 2023-07 之前已有评论的算老品）；新品 = 首评后 ≤ 6 个月，与 Amazon 第九版"上架 ≤ 6 个月"对应。', '',
      '| 季度 | 月均重建销量 | 有销量家族 | 有销量变体 | 新品销量占比 | VP 占比 |', '| :--- | ---: | ---: | ---: | ---: | ---: |')
    for q0 in range(M0, END + 1, 3):
        ms_ = [m for m in range(q0, q0 + 3) if m <= END]; a = A[A['m'].isin(ms_)]
        P(f"| {ms(q0)} 至 {ms(ms_[-1])} | {a['c'].sum() / len(ms_):,.0f} | {a.loc[a['c'] > 0, 'fam'].nunique()} | {a['pid'].nunique()} | {a.loc[a['新'], 'c'].sum() / max(a['c'].sum(), 1):.0%} | {a['vp'].sum() / max(a['n'].sum(), 1):.0%} |")
    ff = pd.Series(fam_first).map(lambda d: d[:4])
    P('', f'家族首条评论年份（≈ 上架年）分布：' + '、'.join(f'{y} 年 {n} 个' for y, n in ff.value_counts().sort_index().items()) + '。', '')
    if trunc:
        P('截断的影响：', '', '| 家族 | 品牌 | "完整到" | 2026 月均重建销量 | 完整到之前月份的 VP / 非 VP 评论 |', '| :--- | :--- | :--- | ---: | :--- |')
        for fk, d in sorted(trunc.items(), key=lambda kv: kv[1]):
            w = W[(W['fam'] == fk) & (W['d'] < d)]
            P(f"| {fk} | {fb.get(fk, '')} | {d} | {FM.loc[fk, mi('2026-01'):END].mean() if fk in FM.index else 0:,.0f} | {int(w['vp'].sum())} / {int((~w['vp']).sum())} |")
        P('')

    # ---------------- 3. 覆盖与换手 ----------------
    f26 = FM.loc[:, mi('2026-01'):END].sum(axis=1) / 10
    P('## 3. 实测：前 N 覆盖与换手', '', '### 3.1 前 N 覆盖（评论量随排名递减 → 外推长尾）', '',
      '做法：每个类目按 Top Sellers 排名，家族按它最靠前的商品页排名计一次（同一家族不重复算）；看各排名段家族 2026-01 至 10 的重建月销合计。'
      '再用排名 51–300 的家族拟合 ln(月销) = a + b·ln(排名)（只用有评论的家族，0 评论的单列），外推到类目里全部家族。'
      '类目家族总数 = 页面显示的商品总数 ÷ 每个家族平均有评论的变体数（样本里算的），这一步只能给量级。', '',
      '| 类目 | 排名段 | 家族数 | 其中 2026 有评论 | 月均重建销量合计 | 占前 300 合计 | 家族平均 |', '| :--- | :--- | ---: | ---: | ---: | ---: | ---: |')
    vpf = W.groupby('fam')['pid'].nunique()
    cover = {}
    for n, (rows, totp) in lists.items():
        seen, fr = set(), []
        for r in rows:
            fk = pid2fam.get(r['id'])
            if fk in seen: continue
            seen.add(fk); fr.append((r['排名'], fk, f26.get(fk, 0.0)))
        F_ = pd.DataFrame(fr, columns=['rank', 'fam', 's']); F_['frank'] = range(1, len(F_) + 1); tot300 = F_['s'].sum()
        for lo, hi in ((1, 50), (51, 100), (101, 200), (201, 300)):
            d = F_[F_['rank'].between(lo, hi)]
            P(f"| {n} | {lo}–{hi} | {len(d)} | {int((d['s'] > 0).sum())} | {d['s'].sum():,.0f} | {d['s'].sum() / tot300:.0%} | {d['s'].mean():,.0f} |")
        fit = F_[(F_['rank'] > 50) & (F_['s'] > 0)]
        b, a = np.polyfit(np.log(fit['frank']), np.log(fit['s']), 1) if len(fit) > 5 else (np.nan, np.nan)
        mean_v = vpf.reindex(F_['fam']).dropna().mean()
        nf_tot = totp / mean_v if totp and mean_v else np.nan
        nf = len(F_); tail = sum(np.exp(a) * r ** b for r in range(nf + 1, int(nf_tot) + 1)) if not np.isnan(b) and nf_tot > nf else np.nan
        # 只用 200 内的家族时的覆盖（N = 200）
        F200 = F_[F_['rank'] <= 200]; nf200 = len(F200)
        tail200 = sum(np.exp(a) * r ** b for r in range(nf200 + 1, int(nf_tot) + 1)) if not np.isnan(b) else np.nan
        cover[n] = dict(b=b, nf=nf, nf_tot=nf_tot, mean_v=mean_v, tot=tot300, tail=tail, c300=tot300 / (tot300 + tail), c200=F200['s'].sum() / (tot300 + tail),
                        top200share=F200['s'].sum() / tot300, zero=int((F_['s'] == 0).sum()))
    P('')
    for n, c in cover.items():
        P(f"- **{n}**：前 {TOPN} 个商品页合并成 {c['nf']} 个家族（其中 {c['zero']} 个 2026 年没有评论）；拟合斜率 b = {c['b']:+.2f}；每个家族平均 {c['mean_v']:.1f} 个有评论的变体，"
          f"类目约 {c['nf_tot']:,.0f} 个家族；外推的长尾月销约 {c['tail']:,.0f}，前 {TOPN} 覆盖约 **{c['c300']:.0%}**，前 200 覆盖约 **{c['c200']:.0%}**"
          f"（前 200 占前 300 的 {c['top200share']:.0%}）。")
    P('', '外推的不确定性：斜率按幂律外推到上万个家族，长尾量对 b 很敏感（b 越接近 −1，长尾越大）；页面"商品总数"含大量零销量的第三方页，按它算家族数会高估长尾。'
      '所以外推覆盖率是**下限的量级**，更可靠的是"201–300 名占前 300 的比例"这个直接观察。', '')
    # 换手
    P('### 3.2 换手（没有历史榜单，用重建月销近似）', '')
    def topk(a_, b_, k=50):
        s1 = FM.loc[:, a_].sum(axis=1) if isinstance(a_, list) else FM[a_]; s2 = FM.loc[:, b_].sum(axis=1) if isinstance(b_, list) else FM[b_]
        t1 = set(s1[s1 > 0].sort_values(ascending=False).index[:k]); t2 = set(s2[s2 > 0].sort_values(ascending=False).index[:k])
        return len(t1 & t2) / max(min(len(t1), len(t2)), 1), len(t1), len(t2)
    P('| 比较 | 前 50 家族重合率 | 前 20 重合率 |', '| :--- | ---: | ---: |')
    for lab, a_, b_ in (('2026-06 vs 2026-10（单月）', mi('2026-06'), END), ('2026-04 至 06 vs 2026-08 至 10（3 个月）', list(range(mi('2026-04'), mi('2026-07'))), list(range(mi('2026-08'), END + 1))),
                        ('2025-10 vs 2026-10（单月，隔一年）', mi('2025-10'), END), ('2025-08 至 10 vs 2026-08 至 10（3 个月，隔一年）', list(range(mi('2025-08'), mi('2025-11'))), list(range(mi('2026-08'), END + 1)))):
        r50, r20 = topk(a_, b_, 50), topk(a_, b_, 20)
        P(f'| {lab} | {r50[0]:.0%} | {r20[0]:.0%} |')
    P('', '注意：这里的家族都是今天还在前 300 的（幸存者），过去在头部、今天掉出前 300 的看不到，所以重合率是**上限**。'
      '单月重建销量颗粒很粗（1 条 VP 评论 = 50 件），单月比较噪声大，3 个月更稳。', '')
    # wen 样本对照
    wfile = os.path.join(ROOT, 'input', 'data_v2', '渠道VP', '浴室柜_2026_渠道VP_20261103.xlsx')
    if os.path.exists(wfile):
        wd = pd.read_excel(wfile, sheet_name='商品月度明细'); wd = wd[wd['渠道'] == 'Home Depot'].copy(); wd['商品ID'] = wd['商品ID'].astype(str)
        ent = {'HDP带台面': '带台面', 'HDP无台面': '无台面'}
        P('### 3.3 和 wen 已有的 2026-01 至 10 HD 样本对照（`渠道VP_20261103.xlsx`"商品月度明细"，只做同口径对照）', '')
        for e_, n in ent.items():
            w_ = wd[wd['入口'] == e_]; ours = {r['id']: r['排名'] for r in lists[n][0]}
            inn = w_['商品ID'].isin(ours); same100 = w_['商品ID'].isin([p for p, k in ours.items() if k <= 100])
            P(f'- {n}：wen 的前 100 个商品页，{int(inn.sum())} 个在本次前 {TOPN} 里，{int(same100.sum())} 个在本次前 100 里（wen 采集 11-02、本次 11-03）。')
        mm = [f'2026-{i:02d}' for i in range(1, 11)]
        wd['fam'] = wd['商品ID'].map(pid2fam)
        x = wd.dropna(subset=['fam']).drop_duplicates('fam')
        ours_m = W[W['m'] >= mi('2026-01')].groupby(['fam', 'm']).size().unstack(fill_value=0).reindex(columns=[mi(m) for m in mm], fill_value=0)
        o = ours_m.reindex(x['fam']).fillna(0).values; w = x[[f'{m} 合计' for m in mm]].fillna(0).values
        P(f'- 同一家族（{len(x)} 个，按家族去重后比）2026-01 至 10 的评论条数：wen 合计 {w.sum():,.0f}、本次 {o.sum():,.0f}（本次 ÷ wen = {o.sum() / max(w.sum(), 1):.2f}）；'
          f'家族 × 月的秩相关 {spearmanr(o.ravel(), w.ravel())[0]:+.2f}，逐家族 10 个月合计完全相同的 {np.mean(o.sum(axis=1) == w.sum(axis=1)):.0%}。'
          '个别家族的差异没有逐条核对（采集日差一天，wen 那边每个商品页单一排序最多 17 页）。', '')

    # ---------------- 4. 打标覆盖 ----------------
    s26 = A[A['m'] >= mi('2026-01')].groupby('pid')['c'].sum(); V['s26'] = s26.reindex(V.index).fillna(0)
    sw = V['s26'].sum()
    P('## 4. 打标与分框', '',
      f'- 变体 {len(V)} 个：在榜商品页 {int(V["在榜"].sum())} 个；其余 {int((~V["在榜"]).sum())} 个是家族里不在前 {TOPN}、但 2024 年起有评论的变体，补抓了它们的页面'
      f'（拿到规格的 {int((~V["在榜"] & V["有规格"]).sum())} 个，页面已下架 / 打不开的用评论里记的商品名）。',
      '- 规则：v12.2 打标规则（`app/pdt/core/tagging_rules.py` 的 Tagger，关掉默认值）读标题 + 商品页规格；HD 规格的"Assembled""Vanity Type"字段和标题"(Assembled)"优先。'
      '没有自己规格的变体，装 / 形态 / 柜体材质 / 台面材质按同家族已知变体补（同系列只换颜色尺寸）。**装不默认拆装**，判断不了记"未知"，不进框；形态没写的按落地式（与 Amazon 口径同）。'
      '元素只用文字规则（Shaker / Fluted / Farmhouse 等），判断不了记"未知"，不调大模型、不看图。'
      '尺寸段、主色、柜体材质、台面类型的业务归类用 `app/pdt/core/families.py`（与 Amazon 同）。', '',
      '| 标签 | 变体覆盖 | 2026 重建销量覆盖 | 来源构成（按销量） | 主要取值（按 2026 销量） |', '| :--- | ---: | ---: | :--- | :--- |')
    def cov(col, src=None, unk=lambda v: v in UNKS or v is None or (isinstance(v, float) and np.isnan(v))):
        k = ~V[col].map(unk)
        top = V[k].groupby(col)['s26'].sum().sort_values(ascending=False)
        srcs = '、'.join(f'{a or "—"} {b / sw:.0%}' for a, b in V[k].groupby(src)['s26'].sum().sort_values(ascending=False).items()) if src else ''
        P(f"| {col} | {k.mean():.0%} | {V.loc[k, 's26'].sum() / sw:.0%} | {srcs} | " + '、'.join(f'{a} {b / sw:.0%}' for a, b in top.head(7).items()) + ' |')
    cov('尺寸段'); cov('装', '装来源'); cov('形态', '形态来源'); cov('台面材质', 'D8来源'); cov('台面类型'); cov('主色'); cov('柜体材质', 'D7来源'); cov('元素一')
    k = V['框'] != '未知'
    P('', f'框（尺寸段 × 装 × 形态）可定的变体 {k.mean():.0%}，按 2026 销量 {V.loc[k, "s26"].sum() / sw:.0%}；框的分布（2026 月均销量）：' +
      '、'.join(f'{a} {b / 10:,.0f}' for a, b in V[k].groupby('框')['s26'].sum().sort_values(ascending=False).head(12).items()) + '。', '')

    # ---------------- 5. 回测 ----------------
    EPS = 0.001; KS = (0, 3, 6, 8); XS = ['b6', 'x2', 'x4', 'x5']
    Ax = A.explode('元素')
    BIG = float(os.environ.get('BIG', '0'))
    BIG = BIG or round(float(CAT.loc[mi('2025-01'):END].mean()) * 0.01, -1)   # 大单元：近 3 个月月均 ≥ 品类月销的 1%
    def mk_panel(keyfn, rows):
        df = rows.assign(_k=keyfn(rows)).dropna(subset=['_k'])
        C = df.groupby(['_k', 'm'])['c'].sum().unstack(fill_value=0).reindex(columns=MONTHS, fill_value=0)
        N = df[df['新']].groupby(['_k', 'm'])['c'].sum().unstack(fill_value=0).reindex(index=C.index, columns=MONTHS, fill_value=0)
        F = df.groupby(['_k', 'm'])['fam'].nunique().unstack(fill_value=0).reindex(columns=MONTHS, fill_value=0)
        den = rows.loc[rows.index.isin(df.index.unique())].drop_duplicates(['fam', 'pid', 'm']).groupby('m')['c'].sum().reindex(MONTHS, fill_value=0)
        return C, N, F, den
    known = lambda s: ~s.isin(list(UNKS)) & s.notna()
    FRK = lambda d: d['框'].where(d['框'] != '未知')
    GRANS = {
        '框 × 属性': [(f'框 × {att}', (lambda att: lambda d: (FRK(d) + ' | ' + att + '：' + d[att].astype(str)).where(known(d[att]) & FRK(d).notna()))(att), Ax if att == '元素' else A)
                    for att in ('台面材质', '元素', '主色', '柜体材质')],
        '只按框': [('框', lambda d: FRK(d), A)],
        '大属性（不分框）': [(att, (lambda att: lambda d: (att + '：' + d[att].astype(str)).where(known(d[att])))(att), Ax if att == '元素' else A)
                       for att in ('尺寸段', '装', '形态', '台面材质', '台面类型', '主色', '柜体材质', '元素')],
    }
    CATN = A[A['新']].groupby('m')['c'].sum().reindex(MONTHS, fill_value=0)
    mean3 = lambda X, a: X.loc[:, [m for m in range(a, a + 3) if m in X.columns]].mean(axis=1)
    def build(gran):
        pans = []
        for nm, kf, rows in GRANS[gran]:
            rows = rows.reset_index(drop=True)
            pans.append((nm,) + mk_panel(kf, rows))
        return pans
    def feats(pans, T):
        out = []
        for nm, C, N, F, den in pans:
            b1 = mean3(C, T - 3); d1 = den.loc[T - 3:T - 1].mean(); f1, f0 = mean3(F, T - 3), mean3(F, T - 6)
            cols6 = list(range(T - 6, T)); xc = np.arange(6) - 2.5
            D = pd.DataFrame({'属性': nm, '取值': C.index, '近3月': b1.values, '分母': d1})
            D['份额6'] = (C[cols6].sum(axis=1) / max(den.loc[T - 6:T - 1].sum(), 1)).values
            D['b6'] = ((np.log(C[cols6].div(den.loc[T - 6:T - 1].replace(0, np.nan), axis=1).fillna(0) + EPS) * xc).sum(axis=1) / (xc ** 2).sum()).values
            D['x5'] = (N[cols6].sum(axis=1) / C[cols6].sum(axis=1).replace(0, np.nan)).fillna(0).values - CATN.loc[T - 6:T - 1].sum() / max(CAT.loc[T - 6:T - 1].sum(), 1)
            D['x2'] = ((f1 - f0) / (f0 + 1)).values
            out.append(D)
        D = pd.concat(out, ignore_index=True); D = D[D['近3月'] > 0].copy(); D['x4'] = np.log(D['近3月'] + 5); D['T'] = T
        return D.set_index(['属性', '取值'])
    def target(pans, D, T, k):
        a = T + k
        if a + 2 > END: return pd.Series(np.nan, index=D.index)
        res = {}
        for nm, C, N, F, den in pans:
            s = mean3(C, a) / max(den.loc[a:a + 2].mean(), 1)
            for v, x in s.items(): res[(nm, v)] = x
        s = pd.Series([res.get(i, 0.0) for i in D.index], index=D.index)
        return np.log((s + EPS) / (D['份额6'] + EPS))
    TIER = lambda b: np.where(b >= BIG, '大', '小')
    def design(D, k):
        X = D[XS].copy(); X['x4'] = X['x4'] - 5.0
        for x in XS: X[x + '·k'] = X[x] * k / 3
        X['k'] = k / 3; return X
    def run(gran, T0s, minv=50):
        pans = build(gran); FE = {T: feats(pans, T) for T in range(M0 + 6, END + 1)}; Y = {}
        def y(T, k):
            if (T, k) not in Y: Y[(T, k)] = target(pans, FE[T], T, k)
            return Y[(T, k)]
        res = []
        for T0 in T0s:
            rows = []
            for T in range(M0 + 6, T0):
                for k in KS:
                    if T + k + 2 > T0 - 1: continue
                    D = FE[T]; yy = y(T, k); ok = (D['近3月'] >= minv) & yy.notna()
                    X = design(D[ok], k); X['y'] = yy[ok]; X['tier'] = TIER(D.loc[ok, '近3月'].values); X['kk'] = k; rows.append(X)
            Tr = pd.concat(rows) if rows else pd.DataFrame()
            D = FE[T0].copy(); D['y6'] = y(T0, 6); D = D.dropna(subset=['y6'])
            fitted = len(Tr) >= 100 and Tr['kk'].nunique() >= 2
            if fitted:
                cols = [c for c in Tr.columns if c not in ('y', 'tier', 'kk')]
                m = Ridge(alpha=1e-6).fit(Tr[cols], Tr['y']); Tr['res'] = Tr['y'] - m.predict(Tr[cols])
                q = Tr.groupby(['tier', 'kk'])['res'].agg(['mean', 'std'])
                def qg(t, k, c):
                    if t not in q.index.get_level_values(0): t = q.index.get_level_values(0)[0]   # 该体量档没有训练样本 → 用有的那档
                    ks = list(q.loc[t].index)
                    if not ks: return np.nan
                    if k in ks: return q.at[(t, k), c]
                    kmax = max(ks); f = np.sqrt((k + 3) / (kmax + 3))
                    return q.at[(t, kmax), c] * (f if c == 'std' else 1)
                tier = TIER(D['近3月'].values); preds = {}
                for k in (6, 8):
                    preds[k] = m.predict(design(D, k)[cols]) + np.array([qg(t, k, 'mean') for t in tier]); D[f'sd{k}'] = [qg(t, k, 'std') for t in tier]
                D['预测'] = preds[6]; D['把握'] = norm.cdf(((preds[6] + preds[8]) / 2) / ((D['sd6'] + D['sd8']) / 2))
                coef = dict(zip(cols, m.coef_))
            else:
                coef = {}
                D['预测'] = D['b6']; D['把握'] = np.nan
            D['T0'] = T0; D['拟合'] = fitted; D['训练'] = len(Tr); D['coef_b6_k6'] = coef.get('b6', np.nan) + 2 * coef.get('b6·k', 0) if coef else np.nan
            D['coef_x5_k6'] = coef.get('x5', np.nan) + 2 * coef.get('x5·k', 0) if coef else np.nan
            res.append(D)
        return pd.concat(res)
    T0s = [mi(t) for t in ('2025-04', '2025-05', '2025-06', '2025-07', '2025-08', '2025-09', '2025-10', '2025-11', '2025-12', '2026-01', '2026-02')]
    def metr(d):
        big = d[d['近3月'] >= BIG]; nz = big['y6'].abs() > 0.05
        r = dict(n=len(d), nb=len(big),
                 rho=spearmanr(d['预测'], d['y6'])[0] if len(d) > 4 else np.nan, rhob=spearmanr(big['预测'], big['y6'])[0] if len(big) > 4 else np.nan,
                 dirn=(np.sign(big.loc[nz, '预测']) == np.sign(big.loc[nz, 'y6'])).mean() if nz.sum() else np.nan, ndir=int(nz.sum()),
                 rb6=spearmanr(d['b6'], d['y6'])[0] if len(d) > 4 else np.nan, rb6b=spearmanr(big['b6'], big['y6'])[0] if len(big) > 4 else np.nan,
                 rx5=spearmanr(d['x5'], d['y6'])[0] if len(d) > 4 else np.nan, rx5b=spearmanr(big['x5'], big['y6'])[0] if len(big) > 4 else np.nan,
                 up=(d['y6'] > 0).mean())
        if d['把握'].notna().any():
            for lab, lo, hi in (('≤30%', 0, 0.3), ('30–50%', 0.3, 0.5), ('50–70%', 0.5, 0.7), ('≥70%', 0.7, 1.01)):
                x = d[(d['把握'] > lo if lo else d['把握'] >= 0) & (d['把握'] <= hi)]; r[lab] = ((x['y6'] > 0).mean() if len(x) else np.nan, len(x))
            Dd = big[big['把握'] <= 0.3]; r['D'] = ((Dd['y6'] > 0).mean() if len(Dd) else np.nan, len(Dd))
        return r
    RES = {g: run(g, T0s) for g in GRANS}
    P('## 5. 回测（Amazon 第九版的简化版）', '',
      f'- **单元**：主粒度 = 框（尺寸段 × 装 × 形态）× 属性取值（台面材质 / 元素 / 主色 / 柜体材质）；另做"只按框"和"大属性不分框"两个粗粒度。份额 = 单元月销 ÷ 该属性已知且框已知的总月销。',
      '- **特征**（只用 T0 之前 6 个月）：b6 份额斜率、x5 新品占比差（单元内新品销量占比 − 品类新品占比）、x2 新进家族、x4 体量；没有 x3 搜索同比（HD 没有站内搜索数据）。',
      '- **目标**：立项后第 6–8 个月（T0+6 至 T0+8）份额相对近 6 个月份额的对数变化，> 0 = 之后变大。',
      '- **拟合**：与第九版相同的回归式（k ∈ {0, 3, 6, 8} 交互、按体量档 × k 纠偏和标准差），每个 T0 只用 T0 之前结果已知的样本（近 3 月 ≥ 50 件）；'
      '"把握" = Φ(第 6–8、8–10 个月预测平均 ÷ 标准差)。训练样本 < 100 或只有一个 k 时不拟合，降级为"仅 b6"排序。',
      f'- **T0**：2025-04 至 2026-02 共 {len(T0s)} 个（2024-01 起的数据，特征最早 2024-07，k = 6 的训练样本最早要到 2025-04 才有）。'
      f'**大单元** = 近 3 个月月均 ≥ {BIG:,.0f} 件（品类 2025-01 至 2026-10 月均的 1%；Amazon 的 300 件约为其 2026 年品类月销 2.5–2.8 万件的 1.1–1.2%，见 回归预测_回测_第八版.md）；D 档（坑）= 把握 ≤ 30% 的大单元。', '')
    for g, D in RES.items():
        P(f'### 5.{list(RES).index(g) + 1} {g}', '',
          '| T0 | 拟合 / 训练样本 | 单元（大） | 秩相关 预测 全部 / 大 | 仅 b6 全部 / 大 | 仅 x5 全部 / 大 | 方向对（大，个数） | 把握 ≤30% / ≥70% 之后变大（个数） | D 档变大（个数） | 全部变大 |',
          '| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: |')
        for T0, d in D.groupby('T0'):
            r = metr(d); f_ = lambda x: '—' if np.isnan(x) else f'{x:+.2f}'
            lo_, hi_, dd = r.get('≤30%', (np.nan, 0)), r.get('≥70%', (np.nan, 0)), r.get('D', (np.nan, 0))
            P(f"| {ms(T0)} | {'是' if d['拟合'].iloc[0] else '否（仅 b6）'} / {d['训练'].iloc[0]:,} | {r['n']}（{r['nb']}） | {f_(r['rho'])} / {f_(r['rhob'])} | {f_(r['rb6'])} / {f_(r['rb6b'])} | {f_(r['rx5'])} / {f_(r['rx5b'])} | "
              f"{pct(r['dirn'])}（{r['ndir']}） | {pct(lo_[0])}（{lo_[1]}） / {pct(hi_[0])}（{hi_[1]}） | {pct(dd[0])}（{dd[1]}） | {r['up']:.0%} |")
        Df = D[D['拟合']]
        if len(Df):
            r = metr(Df); per = [metr(d) for _, d in Df.groupby('T0')]
            avg = lambda k: np.nanmean([x[k] for x in per])
            P('', f"**拟合时点合计**（{Df['T0'].nunique()} 个 T0、{len(Df)} 个单元 × 时点，同一单元跨时点重复出现，不独立）：", '',
              '| 把握 | ≤30% | 30–50% | 50–70% | ≥70% | D 档 |', '| :--- | :--- | :--- | :--- | :--- | :--- |',
              '| 之后变大（个数） | ' + ' | '.join(f"{pct(r[k][0])}（{r[k][1]}）" for k in ('≤30%', '30–50%', '50–70%', '≥70%', 'D')) + ' |', '',
              f"各时点平均：秩相关 预测 全部 / 大 {avg('rho'):+.2f} / {avg('rhob'):+.2f}；仅 b6 {avg('rb6'):+.2f} / {avg('rb6b'):+.2f}；仅 x5 {avg('rx5'):+.2f} / {avg('rx5b'):+.2f}；"
              f"方向对（大）{avg('dirn'):.0%}；全部单元变大 {r['up']:.0%}。"
              f"k = 6 的合计系数（各时点中位）：b6 {Df.groupby('T0')['coef_b6_k6'].first().median():+.2f}，x5 {Df.groupby('T0')['coef_x5_k6'].first().median():+.2f}。", '')
            RES[g] = (D, r, dict(rho=avg('rho'), rhob=avg('rhob'), rb6=avg('rb6'), rb6b=avg('rb6b'), rx5=avg('rx5'), rx5b=avg('rx5b'), dirn=avg('dirn'), n=np.mean([x['n'] for x in per]), nb=np.mean([x['nb'] for x in per])))
        else:
            per = [metr(d) for _, d in D.groupby('T0')]
            RES[g] = (D, None, dict(rb6=np.nanmean([x['rb6'] for x in per]), rb6b=np.nanmean([x['rb6b'] for x in per]), rx5=np.nanmean([x['rx5'] for x in per]),
                                    rx5b=np.nanmean([x['rx5b'] for x in per]), n=np.mean([x['n'] for x in per]), nb=np.mean([x['nb'] for x in per])))
    # 打折后读法
    P('### 5.4 对照表与打折后读法', '', '打折规则来自 `幸存者偏差模拟_小平台回测可行性.md` §6.4：秩相关当上限、全部单元减 0.05–0.1；把握 ≥ 70% 档"之后变大"减 10–20 个百分点；方向对按 ≤ 60% 看；'
      '把握 ≤ 30% 档和 D 档的变大比例加约 5 个百分点。Amazon 第九版全量（2026-01，第 6–8 月）作参照。', '',
      '| 粒度 | 每个 T0 单元数（大） | 秩相关 全部 / 大（自评 → 打折后） | 仅 b6 全部 / 大 | 仅 x5 全部 / 大 | 方向对（大）（→ 打折后） | 把握 ≤30% 变大（→ 打折后） | ≥70% 变大（→ 打折后） | D 档变大（→ 打折后） |',
      '| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |',
      '| Amazon 第九版全量（参照） | 579（207） | +0.27 / +0.47 | +0.20 / +0.26（四时点平均） | — | 64% | 25% | 63% | 19% |')
    f2 = lambda x: '—' if x is None or np.isnan(x) else f'{x:+.2f}'
    SUM = {}
    for g, (D, r, a) in RES.items():
        if r is None:
            P(f"| {g} | {a['n']:.0f}（{a['nb']:.0f}） | 未拟合 | {f2(a['rb6'])} / {f2(a['rb6b'])} | {f2(a['rx5'])} / {f2(a['rx5b'])} | — | — | — | — |"); continue
        disc = lambda x, lo, hi: '—' if np.isnan(x) else f'{x + lo:.0%}–{x + hi:.0%}'
        P(f"| {g} | {a['n']:.0f}（{a['nb']:.0f}） | {f2(a['rho'])} / {f2(a['rhob'])} → {f2(a['rho'] - 0.1)}–{f2(a['rho'] - 0.05)} / {f2(a['rhob'] - 0.1)}–{f2(a['rhob'] - 0.05)} | "
          f"{f2(a['rb6'])} / {f2(a['rb6b'])} | {f2(a['rx5'])} / {f2(a['rx5b'])} | {pct(a['dirn'])}（→ ≤ {pct(min(a['dirn'], 0.6))}） | "
          f"{pct(r['≤30%'][0])}（→ {disc(r['≤30%'][0], 0.05, 0.05)}） | {pct(r['≥70%'][0])}（→ {disc(r['≥70%'][0], -0.2, -0.1)}） | {pct(r['D'][0])}（→ {disc(r['D'][0], 0.05, 0.05)}） |")
        SUM[g] = (r, a)
    P('')

    # ---------------- 6. wen 判断的走势核对 ----------------
    P('## 6. 对照 wen 老方法的判断：这些格子过去在扩大还是缩小', '',
      '只摆事实，不替 wen 下结论。价格是 2026-11-03 当天的价（在榜的用列表价，不在榜的用补抓的商品页价；已下架或页面不给价的变体没有价格），不是历史价；'
      f'有价格的变体占 2026 重建销量的 {V.loc[V["价格"].notna(), "s26"].sum() / max(V["s26"].sum(), 1):.0%}。带价位条件的格子只算有价格的变体，同时给不限价位的同格子作对照。'
      '"新家族" = 家族首条评论在 2025-01 以后。"实木类" = v12.2 柜体材质为实木或实木框架（HD 规格里 263 个商品页只写"Wood"，规则从标题 / 卖点里认出实木框架等；单写"Wood"的认不出）。', '')
    QS = [(q, min(q + 2, END)) for q in range(M0, END + 1, 3)]
    SUMM = []
    def trend(mask, lab):
        a = A[mask.reindex(A['pid']).values] if isinstance(mask, pd.Series) else A[mask]
        cells = []
        for q0, q1 in QS:
            x = a[a['m'].between(q0, q1)]; tot = CAT.loc[q0:q1].sum()
            cells.append(f"{x['c'].sum() / (q1 - q0 + 1):,.0f}（{x['c'].sum() / tot:.1%}，{x['fam'].nunique()}）")
        fams_ = a['fam'].unique(); nf = [f for f in fams_ if (fam_first.get(f) or '0') >= '2025-01']
        s_new = a[a['fam'].isin(nf) & (a['m'] >= mi('2026-01'))]['c'].sum() / 10; s_all = a[a['m'] >= mi('2026-01')]['c'].sum() / 10
        h1 = a[a['m'].between(M0, M0 + 5)]['c'].sum() / CAT.loc[M0:M0 + 5].sum(); h2 = a[a['m'].between(END - 5, END)]['c'].sum() / CAT.loc[END - 5:END].sum()
        SUMM.append(f"{lab}：份额 {ms(M0)} 至 {ms(M0 + 5)} {h1:.1%} → {ms(END - 5)} 至 {ms(END)} {h2:.1%}；2025 年后进入的新家族 {len(nf)} 个，占格子 2026 销量 {s_new / max(s_all, 1):.0%}")
        return f"| {lab} | " + ' | '.join(cells) + f" | {len(nf)} 个，2026 月均 {s_new:,.0f}（占格子 {s_new / max(s_all, 1):.0%}） |"
    vm = V
    sz36_48 = vm['尺寸段'].isin(['36″', '42″', '48″']); sz48_60 = vm['尺寸段'].isin(['48″', '60″'])
    solid = vm['柜体材质'].isin(['实木', '实木框架']); strict = vm['柜体材质'].eq('实木'); stone = vm['台面材质'].isin(['岗石', '石英石']); quartz = vm['台面材质'].eq('石英石')
    pr = vm['价格'].astype(float)
    hdr = '| 格子 | ' + ' | '.join(f'{ms(a)[2:]}–{ms(b)[5:]}' for a, b in QS) + ' | 2025 年后进入的新家族 |'
    sep = '| :--- |' + ' ---: |' * len(QS) + ' :--- |'
    P(hdr, sep)
    for lab, msk in (('36–48″ 实木类 + 岗石 / 石英石（不限价）', sz36_48 & solid & stone), ('其中柜体严格"实木"（不含实木框架）', sz36_48 & strict & stone),
                     ('36–48″ 实木类 + 岗石 / 石英石，$649–799（有价格的变体）', sz36_48 & solid & stone & pr.between(649, 799)),
                     ('36–48″ 岗石 / 石英石，$649–799（不限柜体材质）', sz36_48 & stone & pr.between(649, 799)),
                     ('48–60″ 实木类 + 石英石（不限价）', sz48_60 & solid & quartz), ('48–60″ 实木类 + 石英石，$700–1,400', sz48_60 & solid & quartz & pr.between(700, 1400)),
                     ('48–60″ 石英石，$700–1,400（不限柜体材质）', sz48_60 & quartz & pr.between(700, 1400)),
                     ('岩板台面（任意）', vm['台面材质'].eq('岩板')), ('42″ 全部', vm['尺寸段'].eq('42″')), ('42″ 自有品牌（Glacier Bay / Home Decorators Collection）', vm['尺寸段'].eq('42″') & vm['PB']),
                     ('全部尺寸 自有品牌', vm['PB']), ('实木类柜体（任意）', solid)):
        P(trend(msk, lab))
    P('', f'每格：月均重建销量（占品类份额，有销量的家族数）；季度列为 年-月 至 月，最后一格为 {ms(QS[-1][0])} 至 {ms(QS[-1][1])}。', '')
    P('首尾半年对比（事实摘要）：', '', *[f'- {x}' for x in SUMM], '')
    # 42″ PB 占比
    a42 = A[A['尺寸段'] == '42″']
    P('42″ 里自有品牌的销量占比（按季度）：' + '、'.join(f"{ms(q0)[2:]} {a42.loc[a42['m'].between(q0, q1) & a42['PB'], 'c'].sum() / max(a42.loc[a42['m'].between(q0, q1), 'c'].sum(), 1):.0%}" for q0, q1 in QS) +
      '；全品类自有品牌占比：' + '、'.join(f"{ms(q0)[2:]} {A.loc[A['m'].between(q0, q1) & A['PB'], 'c'].sum() / max(CAT.loc[q0:q1].sum(), 1):.0%}" for q0, q1 in QS) + '。', '')
    inc = vm[sz36_48 & solid & stone & pr.between(649, 799)]
    P(f'有价格且落在 36–48″ 实木类 + 岗石 / 石英石 $649–799 的在榜变体：{len(inc)} 个' + ('（' + '；'.join(f"{r.品牌} {r.title[:60]} ${r.价格:,.0f}" for r in inc.head(8).itertuples()) + '）' if len(inc) else '') + '。')
    sint = vm[vm['台面材质'] == '岩板']
    P(f'岩板台面变体：{len(sint)} 个，家族 {sint["fam"].nunique()} 个' + ('（' + '；'.join(f"{r.品牌} {r.title[:60]}" for r in sint.drop_duplicates('fam').head(6).itertuples()) + '）' if len(sint) else '') +
      '；文字里能认出"一体 / integrated"的：' + str(int(sint['title'].str.contains('integrat|one[- ]piece', case=False, regex=True).sum())) + ' 个。', '')
    return L, dict(cover=cover, SUM=SUM, BIG=BIG, trunc=trunc, V=V, CAT=CAT)


def write_report():
    L, info = analyze()
    L += conclusions(info)
    out = os.path.join(ROOT, 'solution-v2', '开发建议', '小平台_HD回测小试.md')
    open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print('\n'.join(L))


def conclusions(info):
    import numpy as np
    S, cv = info['SUM'], info['cover']
    L = ['## 7. 结论', '']
    f2 = lambda x: '—' if x is None or np.isnan(x) else f'{x:+.2f}'
    pc = lambda x: '—' if x is None or np.isnan(x) else f'{x:.0%}'
    # 1. 能不能用：全部单元、大单元分开判断
    # 判据（写在看结果之前的偏差模拟报告口径上）：排序有用 = 秩相关打折后仍 > 0（全部单元 ≥ 0.15、大单元 ≥ 0.25）；
    # 坑认得出 = D 档（≥ 20 个）之后变大的比例打折（+5 个百分点）后仍比全部单元低 10 个百分点以上。
    L.append('**Home Depot 能不能用回测思路**（判据：秩相关全部单元 ≥ 0.15 / 大单元 ≥ 0.25，打折后仍为正；D 档 ≥ 20 个且打折后变大比例比全部单元低 ≥ 10 个百分点）：')
    for g, (r, a) in S.items():
        ok_all = a['rho'] >= 0.15; ok_big = a['rhob'] >= 0.25
        ok_d = r['D'][1] >= 20 and r['D'][0] + 0.05 <= r['up'] - 0.1
        verdict = []
        verdict.append('全部单元排序' + ('可用' if ok_all else '弱（打折后接近 0），不能用'))
        verdict.append('大单元排序' + ('可用' if ok_big else '不可用'))
        verdict.append('坑（D 档）' + ('认得出' if ok_d else ('个数太少，不可读' if r['D'][1] < 20 else '认不出')))
        L.append(f"- {g}：每个 T0 平均 {a['n']:.0f} 个单元（大单元 {a['nb']:.0f} 个）；预测秩相关 全部 / 大 {f2(a['rho'])} / {f2(a['rhob'])}（打折后约 {f2(a['rho'] - 0.1)}–{f2(a['rho'] - 0.05)} / {f2(a['rhob'] - 0.1)}–{f2(a['rhob'] - 0.05)}）；"
                 f"把握 ≤ 30% / 30–50% / 50–70% / ≥ 70% 之后变大 {pc(r['≤30%'][0])} / {pc(r['30–50%'][0])} / {pc(r['50–70%'][0])} / {pc(r['≥70%'][0])}（全部单元 {pc(r['up'])}）；"
                 f"D 档 {pc(r['D'][0])}（{r['D'][1]} 个）；方向对（大）{pc(a['dirn'])}。→ " + '；'.join(verdict) + '。'
                 + (f" 每个 T0 单元数 < 30，样本太少，只能参考。" if a['n'] < 30 else '')
                 + (f" ≥ 70% 档合计只有 {r['≥70%'][1]} 个，不可读。" if r['≥70%'][1] < 20 else ''))
    main_r, main_a = S['框 × 属性']
    L.append(f"- **能支持的最小粒度**：框 × 属性每个 T0 有约 {main_a['n']:.0f} 个单元（≥ 30），粒度够；只按框只有约 {S['只按框'][1]['n']:.0f} 个，太少。"
             "概率（把握的绝对值）、方向对、A 档都按偏差模拟的打折规则看，不直接用。")
    # 2. N
    L += ['', '**要多大的 N**：']
    for n, c in cv.items():
        L.append(f"- {n}：前 200 名占前 300 重建销量的 {c['top200share']:.0%}，即 201–300 名还贡献 {1 - c['top200share']:.0%}；外推覆盖 前 200 约 {c['c200']:.0%}、前 {TOPN} 约 {c['c300']:.0%}（量级）。")
    L.append('- 偏差模拟的要求是"前 N 占类目当前销量约 90% 以上"。' + (
        '按外推，前 300 已接近这个要求。' if all(c['c300'] >= 0.85 for c in cv.values()) else
        '按外推（量级），前 300 还达不到；201–300 名仍贡献约一成，说明前 300 还没到饱和。在本次数据上 N = 300（每个类目）是下限，再深要看 400–500 名的增量；小单元受长尾缺失影响最大，所以只看大单元。'))
    L.append('- 换手：今天前 300 的家族里，2026-04 至 06 与 08 至 10 前 50 名重合约八成（§3.2），这是幸存者口径的上限。')
    # 3. 信号
    L += ['', '**哪些信号可用**：']
    for g, (r, a) in S.items():
        L.append(f"- {g}：仅 b6 秩相关 全部 / 大 {f2(a['rb6'])} / {f2(a['rb6b'])}；仅 x5 {f2(a['rx5'])} / {f2(a['rx5b'])}。")
    L += ['', '## 8. 局限', '',
          '1. 评论 × 系数换算月销：VP × 50、非 VP × 20 是系统默认，没有按 HD 校准（不同价位、品牌的留评率不同）；品牌站转载评论按 hdp.py 口径计入（占比见 §1）；1 条 VP 评论 = 50 件，小单元月度颗粒很粗。',
          '2. 幸存者偏差：只看得到今天在两个类目前 300 的商品页所在的家族；过去卖得好、今天掉出去的看不到。换手率只能用重建月销近似，是上限。',
          '3. 上架月 = 变体首条评论月，通常比真实上架晚 1–2 个月；抓取起点 2023-07 之前就有评论的算老品。大家族里评论稀少的老变体，2023-07 后的第一条评论会被当成首评，所以 2024 年上半年的新品占比（§2 表）偏高，影响 2024-07 至 12 时点的 x5。',
          '4. 打标只用文字（标题 + 规格），元素覆盖很低、认出的基本是"夏克式"，主色约三成认不出（见 §4）。不在榜的变体补抓了页面（已下架 / 404 的只用评论里的商品名）；价格是 2026-11-03 当天的价，不是历史价。实木没有做 Amazon 那条"按同宽 MDF 价格复核"的规则；HD 规格只写"Wood"的柜体靠标题 / 卖点判断。',
          '5. 回测只有 2025-04 至 2026-02 的 T0，前几个时点训练样本很少；同一单元跨时点重复出现，合计数不独立。没有 x3（搜索同比）。',
          '6. 评论用的是站点评论接口（与评论页同一数据源）按星级 / 仅 VP 分片补深，不是评论页 HTML；hdp.py 原来的 17 页上限在这里被分片绕开了，所以和 wen 样本的个别家族条数不完全一样。']
    return L


if __name__ == '__main__':
    if sys.argv[1:] == ['采集']: collect()
    elif sys.argv[1:] == ['补变体']: supplement()
    elif sys.argv[1:] == ['分析']: write_report()
