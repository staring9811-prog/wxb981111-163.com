"""关键词抓取测试（reeded）：三个小平台按关键词搜索，抓前 300 条，核实尺寸 / 拆装 / 变体 / 评论选项字段，估计覆盖。
用法：
  python 关键词抓取测试_reeded.py hd / lowes / wayfair   # 断点续采列表（HD 另抓商品页）；原始缓存 input/data_v2/渠道关键词/reeded/（不入库）
  python 关键词抓取测试_reeded.py 抽样     # 商品页 / 评论变体字段核实（Lowe's、Wayfair 各 3 个经 Bright Data；HD 3 个直连）
  python 关键词抓取测试_reeded.py 分析     # 打印报告数字（报告 solution-v2/开发建议/关键词抓取测试_reeded.md 手写叙述 + 这些数字）
网络：Home Depot 直连（≥1.3 秒/次）；Lowe's / Wayfair 经 Bright Data Web Unlocker 异步接口（代理注入密钥，代码里是占位值）。
Bright Data 本次测试总请求上限 BD_CAP 次（ledger.json 记账，提交即计数，超过即停）。不改 tools/ 与 app/ 原文件，只 import。"""
import os, sys, re, json, time, random, html, math, collections, urllib.request, urllib.error, urllib.parse
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools', '评论月度VP追踪器'))
from reviewkit.common import objects_by_key, decode_at, add_query, save_json, load_json   # noqa: E402

CACHE = os.path.join(ROOT, 'input', 'data_v2', '渠道关键词', 'reeded')
KW, KW2 = 'reeded bathroom vanity', 'fluted bathroom vanity'
TOPN = 300
BD_CAP = int(os.environ.get('BD_CAP', '300'))
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
STAT = collections.Counter()


def log(*a):
    msg = time.strftime('%H:%M:%S ') + ' '.join(str(x) for x in a)
    print(msg, flush=True)
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, 'run.log'), 'a', encoding='utf-8') as f: f.write(msg + '\n')


def raw_path(*p):
    f = os.path.join(CACHE, *p); os.makedirs(os.path.dirname(f), exist_ok=True); return f


# ---------- Home Depot：直连，礼貌限速 ----------
DELAY = [1.3]


def hd_get(url, body=None, hdr_extra=None):
    last = (0, b'')
    for i in range(3):
        time.sleep(DELAY[0] + random.uniform(0, 0.8))
        hdr = {'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9'}
        if hdr_extra: hdr.update(hdr_extra)
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=hdr)
        STAT['HD 请求'] += 1
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            last = (e.code, e.read())
            if e.code == 404: return last
            if e.code in (403, 429):
                DELAY[0] = min(DELAY[0] * 2, 20); log(f'  HD {e.code}，降速 {DELAY[0]:.1f}s'); time.sleep(30 * (i + 1)); continue
        except Exception as e:
            last = (0, str(e).encode())
        time.sleep(3 * (i + 1))
    return last


# ---------- Bright Data：异步 /unblocker/req + get_result ----------
BD_API = 'https://api.brightdata.com/unblocker'
BD_Q = {'customer': 'hl_87b86747', 'zone': 'mcp_unlocker'}
LEDGER = os.path.join(CACHE, 'ledger.json')
import threading
_lk = threading.Lock()


class BudgetExceeded(Exception):
    pass


def _http(url, data=None, headers=None, timeout=90):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except Exception as e:
        return 0, {}, str(e).encode()


def ledger_add(k, n=1):
    import fcntl
    with _lk, open(LEDGER + '.lock', 'w') as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        d = load_json(LEDGER, {}) or {}
        if k == 'submitted' and d.get('submitted', 0) + n > BD_CAP:
            raise BudgetExceeded(f"Bright Data 已提交 {d.get('submitted', 0)} 次，上限 {BD_CAP}")
        d[k] = d.get(k, 0) + n
        save_json(LEDGER, d)
        return d


def bd_fetch(url, tag, poll=10, max_wait=900):
    """返回 (目标站状态码, bytes)。每次提交计 1 次（不论成败），成功（目标站 200）另计。"""
    h = {'Authorization': 'Bearer dummy', 'Content-Type': 'application/json'}
    ledger_add('submitted'); ledger_add(f'submitted_{tag}')
    st, _, b = _http(f"{BD_API}/req?{urllib.parse.urlencode(BD_Q)}", json.dumps({'url': url, 'country': 'us'}).encode(), h)
    if st != 200:
        log(f'  BD 提交失败 HTTP {st} {b[:200]!r}'); return st, b
    rid = json.loads(b)['response_id']
    q = urllib.parse.urlencode(dict(BD_Q, response_id=rid)); t0 = time.time()
    while time.time() - t0 < max_wait:
        time.sleep(poll)
        st, hh, b = _http(f'{BD_API}/get_result?{q}', headers=h)
        if st == 200:
            code = int({k.lower(): v for k, v in hh.items()}.get('x-brd-status-code', 200) or 200)
            ledger_add('ok' if code == 200 else f'target_{code}')
            return code, b
        if st != 202:
            ledger_add(f'bd_{st}'); log(f'  BD get_result HTTP {st} {b[:200]!r}'); return st, b
    ledger_add('timeout')
    return 504, b'timeout'


def bd_cached(url, name, tag, ok=lambda b: True, tries=2):
    """缓存原始 HTML；ok(b) 不满足时重试（最多 tries 次）。"""
    f = raw_path('raw', tag, name + '.html')
    if os.path.exists(f):
        return open(f, 'rb').read()
    best = None
    for i in range(tries):
        st, b = bd_fetch(url, tag)
        log(f'  BD {tag} {name}: {st}, {len(b)} 字节')
        if st == 200 and ok(b):
            best = b; break
        if st == 200 and best is None: best = b
    if best is not None:
        open(f, 'wb').write(best)
    return best


# ---------- 1. 关键词搜索列表 ----------
def hd_rows_from(s):
    m = re.search(r'products\(\{\\"filter\\":\{[^)]*\}\)":(\[)', s)
    refs = decode_at(s, m.start(1)) if m else []
    ids = [r['__ref'].split('-')[-1] for r in refs if isinstance(r, dict) and '__ref' in r]
    objs = objects_by_key(s, r'base-searchNav-\d+')
    out = []
    for pid in ids:
        o = objs.get(f'base-searchNav-{pid}', {}); ident = o.get('identifiers') or {}; info = o.get('info') or {}
        pricing = next((v for k, v in o.items() if k.startswith('pricing')), None) or {}
        rr = (o.get('reviews') or {}).get('ratingsReviews') or {}
        sw = info.get('swatches') or []
        out.append(dict(id=pid, parent=ident.get('parentId'), url=BASE_HD + ident.get('canonicalUrl', f'/p/{pid}'),
                        title=ident.get('productLabel', ''), brand=ident.get('brandName', ''), sponsored=bool(info.get('isSponsored')),
                        price=pricing.get('value'), rating=float(rr['averageRating']) if rr.get('averageRating') else None,
                        reviews=int(rr['totalReviews']) if rr.get('totalReviews') else 0,
                        option=next((x.get('label') for x in sw if x.get('isSelected')), None),
                        swatches=[x.get('itemId') for x in sw], n_options=info.get('totalNumberOfOptions'),
                        collection=((o.get('details') or {}).get('collection') or {}).get('name')))
    return out


BASE_HD = 'https://www.homedepot.com'


def hd_list(kw, topn=TOPN, max_pages=None):
    f = raw_path('lists', f'homedepot_{kw}.json'); got = load_json(f) or {'pages': [], 'off': 0, 'done': False}
    while not got['done'] and len({r['id'] for p in got['pages'] for r in p if not r['sponsored']}) < topn and (max_pages is None or len(got['pages']) < max_pages):
        st, b = hd_get(add_query(f'{BASE_HD}/s/{urllib.parse.quote(kw)}', Nao=got['off'] or None))
        if st != 200: log(f'HD {kw} Nao={got["off"]} HTTP {st}，停'); break
        s = b.decode('utf-8', 'ignore')
        t = re.search(r'"searchReport":\{[^}]*"totalProducts":(\d+)', s)
        if t and 'total' not in got: got['total'] = int(t.group(1)); got['sort'] = (re.search(r'"sortBy":"(\w+)"', s) or [None, None])[1]
        rows = hd_rows_from(s)
        if not rows: got['done'] = True; break
        got['pages'].append(rows); got['off'] += len(rows); save_json(f, got)
        log(f'HD {kw} 第 {len(got["pages"])} 页 {len(rows)} 条（总 {got.get("total")}）')
    return got


def lowes_state(b):
    s = b.decode('utf-8', 'ignore')
    m = re.search(r'window\[?.?__PRELOADED_STATE__.?\]?\s*=\s*', s)
    return decode_at(s, m.end()) if m else None


def lowes_ok(b):
    return b'__PRELOADED_STATE__' in b


def lowes_total(st):
    return dict(productCount=st.get('productCount'), itemCount=st.get('itemCount'), sponsoredItemCount=st.get('sponsoredItemCount'),
                pagination=st.get('pagination'), sort=st.get('selectedSortMethod'), partialMatch=st.get('partialMatch'))


def lowes_rows_from(st):
    out = []
    for it in st.get('itemList') or []:
        p, loc = it.get('product') or {}, it.get('location') or {}
        if not p.get('omniItemId'): continue
        pv = p.get('productVariants') or {}; price = loc.get('price') or {}
        out.append(dict(id=p['omniItemId'], parent=pv.get('parentId'), url='https://www.lowes.com' + p.get('pdURL', ''), title=p.get('description', ''),
                        brand=p.get('brand', ''), sponsored=bool(p.get('sponsored')), price=price.get('sellingPrice') or price.get('minPrice'),
                        rating=float(p['rating']) if p.get('rating') else None, reviews=int(p['reviewCount']) if p.get('reviewCount') else 0,
                        option=pv.get('activeSwatchColor') or pv.get('defaultIden') or '', variant_type=pv.get('attributeType'),
                        n_variants=pv.get('totalVariants'), item_number=p.get('itemNumber'), marketplace=bool(p.get('marketplace')),
                        bullets=' | '.join(b.get('value', '') for b in p.get('marketingBullets') or [])))
    return out, st.get('adjustedNextOffset')


def lowes_list(kw, topn=TOPN, max_pages=None):
    f = raw_path('lists', f'lowes_{kw}.json'); got = load_json(f) or {'pages': [], 'done': False, 'off': 0}
    while not got['done'] and len({r['id'] for p in got['pages'] for r in p if not r['sponsored']}) < topn and (max_pages is None or len(got['pages']) < max_pages):
        n = len(got['pages'])
        url = add_query(f'https://www.lowes.com/search?searchTerm={urllib.parse.quote_plus(kw)}', offset=n * 24 or None)   # 页面 offset 按每页 24 计（adjustedNextOffset=20 实测无效）
        b = bd_cached(url, f'{kw}_{n}', 'lowes', lowes_ok, tries=2)
        st = lowes_state(b) if b else None
        if not st: log(f'Lowes {kw} 第 {n + 1} 页失败，停'); break
        rows, nxt = lowes_rows_from(st)
        if n == 0: got['total'] = lowes_total(st)
        if not rows: got['done'] = True; break
        got['pages'].append(rows)
        pg = st.get('pagination') or {}
        if (pg.get('page') or 0) >= (pg.get('pageCount') or 0): got['done'] = True
        save_json(f, got)
        log(f'Lowes {kw} 第 {n + 1} 页 {len(rows)} 条（总 {got.get("total")}）')
    return got


def wf_cards(s):
    out = []
    for m in re.finditer(r'data-clio-id="ListingCardContents::', s):
        ts = s.rfind('<', 0, m.start()); tag = s[ts:s.find('>', m.start())]
        a = {k: html.unescape(v) for k, v in re.findall(r'(data-[a-z\-]+)="([^"]*)"', tag)}
        try: meta = json.loads(a.get('data-tracking-metadata', '{}')).get('metadata', {})
        except Exception: meta = {}
        cs = s.rfind('data-clio-context="', 0, ts)
        try: cj = json.loads(html.unescape(s[cs + 19:s.find('"', cs + 19)])) if cs > 0 else {}
        except Exception: cj = {}
        link = re.search(r'href="(https://www\.wayfair\.com/[^"]+/pdp/[^"]+?\.html[^"]*)"', s[m.start():m.start() + 8000])
        url = html.unescape(link.group(1)) if link else ''
        piid = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get('piid', [''])[0]
        price = meta.get('leadPrice')
        out.append(dict(id=meta.get('displayListingId'), parent=meta.get('displayListingId'), url=url, title=meta.get('listingCardName') or '',
                        brand=meta.get('manufacturerName') or '', sponsored=bool(cj.get('isSponsored')),
                        price=float(re.sub(r'[^\d.]', '', price)) if price and re.sub(r'[^\d.]', '', price) else None,
                        rating=meta.get('averageRating'), reviews=meta.get('totalReviewCount') or 0,
                        option=piid or ','.join(str(x) for x in meta.get('displayedOptionIDs') or []), choices=meta.get('choicesText')))
    return out


def wf_total(s):
    m = re.search(r'resultCount&quot;:(\d+)', s)
    return int(m.group(1)) if m else None


def wf_list(kw, topn=TOPN, max_pages=None):
    f = raw_path('lists', f'wayfair_{kw}.json'); got = load_json(f) or {'pages': [], 'done': False}
    while not got['done'] and len({r['id'] for p in got['pages'] for r in p if not r['sponsored']}) < topn and (max_pages is None or len(got['pages']) < max_pages):
        n = len(got['pages'])
        url = add_query(f'https://www.wayfair.com/keyword.php?keyword={urllib.parse.quote_plus(kw)}', curpage=n + 1 if n else None)
        b = bd_cached(url, f'{kw}_{n}', 'wayfair', lambda b: len(re.findall(rb'ListingCardContents::', b)) >= 24, tries=3)
        if not b: log(f'Wayfair {kw} 第 {n + 1} 页失败，停'); break
        s = b.decode('utf-8', 'ignore'); rows = wf_cards(s)
        if n == 0: got['total'] = wf_total(s)
        if not rows: got['done'] = True; break
        got['pages'].append(rows); save_json(f, got)
        log(f'Wayfair {kw} 第 {n + 1} 页 {len(rows)} 条（总 {got.get("total")}）')
    return got


# ---------- HD 商品页（规格 + 评论首页 → 评论家族）；复用 HD 回测小试的缓存 ----------
OLD_HD = os.path.join(ROOT, 'input', 'data_v2', '渠道历史', 'homedepot', 'pages')


def hd_page(pid, keep_reviews=False):
    f = raw_path('hd_pages', f'{pid}.json'); got = load_json(f)
    if got and got.get('status') == 200 and (not keep_reviews or 'reviews_sample' in got): return got
    old = load_json(os.path.join(OLD_HD, f'{pid}.json'))
    if old and old.get('status') == 200 and not keep_reviews:
        old['来源'] = 'HD回测小试缓存(2026-11-03)'; save_json(f, old); return old
    st, b = hd_get(f'{BASE_HD}/p/reviews/x/{pid}/1')
    out = {'status': st}
    if st == 200:
        s = b.decode('utf-8', 'ignore')
        cat = objects_by_key(s, rf'base-catalog-{pid}').get(f'base-catalog-{pid}') or {}
        out['specs'] = {sp.get('specName'): sp.get('specValue') for g in cat.get('specificationGroup') or [] for sp in g.get('specifications') or []}
        ident = cat.get('identifiers') or {}
        pr = next((v for k, v in cat.items() if k.startswith('pricing')), None) or {}
        out.update(price=pr.get('value'), title=ident.get('productLabel'), brand=ident.get('brandName'))
        res = []
        for mm in re.finditer(r'"reviews\(\{', s):
            end = s.find('})":{', mm.start()); k = s[mm.start():end]
            if end > 0 and len(k) < 600 and 'startIndex\\":1' in k and f'itemId\\":\\"{pid}' in k:
                res = decode_at(s, end + len('})":')).get('Results') or []; break
        out['sig'] = sorted(str(x.get('Id')) for x in res)
        out['sig_pids'] = sorted({str(x.get('ProductId')) for x in res})
        if keep_reviews:
            out['reviews_sample'] = [{k: x.get(k) for k in ('Id', 'ProductId', 'OriginalProductName', 'SubmissionTime', 'Rating',
                                      'ContextDataValues', 'TagDimensions', 'AdditionalFields', 'SecondaryRatings')} for x in res[:30]]
            out['review_keys'] = sorted({k for x in res for k in x})
            out['total_reviews'] = ((cat.get('reviews') or {}).get('ratingsReviews') or {}).get('totalReviews')
    save_json(f, out); return out


def hd_pages():
    g = load_json(raw_path('lists', f'homedepot_{KW}.json'))
    seen, todo = set(), []
    for r in (r for p in g['pages'] for r in p):
        if r['sponsored'] or r['id'] in seen: continue
        seen.add(r['id']); todo.append(r['id'])
    for i, pid in enumerate(todo[:TOPN]):
        hd_page(pid)
        if i % 25 == 0: log(f'HD 商品页 {i + 1}/{min(len(todo), TOPN)}')


# ---------- 3. 抽样：商品页 / 评论的变体字段 ----------
SAMPLE = {'lowes': ['5014516369', '5017482105', '5022709982', '5019332077'], 'wayfair': ['GCNE1307', 'GCNE1351', 'W111053305'],
          'homedepot': ['327193858', '319735856', '333485322']}


def sample_pages():
    jobs = []
    for plat in ('lowes', 'wayfair'):
        g = load_json(raw_path('lists', f'{plat}_{KW}.json'))
        by = {r['id']: r for p in g['pages'] for r in p}
        for pid in SAMPLE[plat]:
            if pid in ('5022709982',): continue   # 商品页两次 BD 502（02:21、02:26），换 5019332077
            jobs.append((plat, pid, by[pid]['url']))
    ok = {'lowes': lowes_ok, 'wayfair': lambda b: len(b) > 300000}
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda j: bd_cached(j[2], j[1], j[0] + '_pdp', ok[j[0]], tries=2), jobs))
    for pid in SAMPLE['homedepot']:
        hd_page(pid, keep_reviews=True)


# ---------- 分析 ----------
RE_KW = re.compile(r'reeded|fluted|fluting|ribbed|channel(?:ed)?\b', re.I)
RE_KW_STRICT = re.compile(r'reeded|fluted', re.I)


def tagger():
    sys.path.insert(0, os.path.join(ROOT, 'app', 'pdt', 'core'))
    import tagging_rules as TR
    from families import band
    return TR, band


def tag_text(TR, title, extra=''):
    """v12.2 Tagger，只用文字（标题 + 可选列表字段），不用默认值。返回 宽 / 装 / 形态。"""
    row = {'子ASIN': 'X', '商品标题': title or '', 'SKU属性': '', '商品尺寸': ''}
    ex = [{'attributes': '', 'features': extra}] if extra else []
    t = TR.Tagger(row, {}, export_rows=ex, accessory_default=False).run()[0]
    low = (title or '').lower() + ' ' + (extra or '').lower()
    if re.search(r'ready[ -]to[ -]assemble|\brta\b|unassembled|assembly required', low): asm = '拆装'
    elif re.search(r'\(assembled\)|fully assembled|pre[- ]?assembled|\bassembled\b', low): asm = '整装'
    elif t['D2安装方式'] in ('整装', '拆装'): asm = t['D2安装方式']
    else: asm = '未知'
    if re.search(r'float|wall[- ]?mount|wall[- ]?hung', low): form = '悬浮式'
    elif re.search(r'freestanding|free[- ]standing|floor[- ]?standing', low): form = '落地式'
    elif t['D1产品形态'] not in ('未知', '信息不足', '待图片核验', '', None): form = t['D1产品形态']
    else: form = '未知'
    w = t['D9宽(in)']
    w = w if w not in ('未知', '', None) else title_width(title)
    return dict(宽=w, 装=asm, 形态=form, 色=t['D6柜体颜色'])


RE_W = re.compile(r'(?<![\d./])(\d{2}(?:\.\d+)?)\s*(?:-|\s)?(?:in\b\.?|inch(?:es)?\b|"|\'\'|″)(?!\s*(?:\.\s*)?(?:h\b|d\b|tall|high|deep|height|depth))', re.I)


def title_width(title):
    """Tagger 没认出宽时的补充：标题里第一个"数字 + in/inch/\""、且后面不是 H / D 的数（15–100）。多尺寸写法（24"/30"）不认。"""
    if re.search(r'\d\s*["″]?\s*/\s*\d', title or ''): return None
    for m in RE_W.finditer(title or ''):
        v = float(m.group(1))
        if 15 <= v <= 100: return v
    return None


def hd_spec_tags(pg):
    sp = pg.get('specs') or {}
    asm = str(sp.get('Assembled', '')).lower()
    a = '拆装' if ('unassembled' in asm or 'ready to assemble' in asm or 'partially' in asm) else ('整装' if asm.startswith('assembled') or asm == 'fully assembled' else None)
    vt = str(sp.get('Vanity Type', '')).lower()
    f = '悬浮式' if ('float' in vt or 'wall' in vt) else ('落地式' if 'freestanding' in vt else None)
    w = None
    for k in ('Product Width (in.)', 'Cabinet Width (in.)', 'Vanity Width (in.)'):
        m = re.match(r'\s*(\d+(?:\.\d+)?)', str(sp.get(k, '')))
        if m: w = float(m.group(1)); break
    return dict(宽=w, 装=a, 形态=f)


def ranked_rows(plat, kw=KW):
    g = load_json(raw_path('lists', f'{plat}_{kw}.json'))
    seen, out = set(), []
    allrows = [r for p in g['pages'] for r in p]
    for r in allrows:
        if r['sponsored'] or r['id'] in seen: continue
        seen.add(r['id']); out.append(dict(r, rank=len(out) + 1))
    return g, allrows, out[:TOPN]


def stem(title):
    t = re.sub(r'\d+(\.\d+)?\s*(in\.?|inch(es)?|["\'″]+|-in\b)?', ' ', title.lower())
    t = re.sub(r'\b(single|double|sink|bath(room)?|vanity|with|and|in|w|x|d|h|top|the|a)\b', ' ', t)
    return ' '.join(t.split()[:4])


def hd_families(rows):
    parent = {}
    def root(x):
        while parent.get(x, x) != x: x = parent[x]
        return x
    by_sig = {}
    for r in rows:
        pg = load_json(raw_path('hd_pages', f"{r['id']}.json")) or {}
        sig = tuple(pg.get('sig') or [])
        parent.setdefault(r['id'], r['id'])
        if sig:
            if sig in by_sig: parent[root(r['id'])] = root(by_sig[sig])
            else: by_sig[sig] = r['id']
        for q in pg.get('sig_pids') or []:
            if q in parent and q != r['id']: parent[root(q)] = root(r['id'])
    return {r['id']: root(r['id']) for r in rows}


def coverage(rows, fam, val):
    """家族按最靠前的排名计一次；val(r) = 评论数或 价格×评论数。返回分段表与幂律外推。"""
    import numpy as np
    seen, F = set(), []
    for r in rows:
        f = fam[r['id']]
        if f in seen: continue
        seen.add(f); F.append((r['rank'], val(r)))
    tot = sum(v for _, v in F) or 1
    seg = []
    for lo, hi in ((1, 50), (51, 100), (101, 200), (201, 300)):
        d = [v for rk, v in F if lo <= rk <= hi]
        seg.append(dict(seg=f'{lo}–{hi}', n=len(d), pos=sum(v > 0 for v in d), sum=sum(d), share=sum(d) / tot, mean=(sum(d) / len(d)) if d else 0))
    fit = [(i + 1, v) for i, (rk, v) in enumerate(F) if rk > 50 and v > 0]
    ext = {}
    if len(fit) > 8:
        b, a = np.polyfit(np.log([x for x, _ in fit]), np.log([v for _, v in fit]), 1)
        # 有正值的家族比例，用于把外推乘上"有评论"的概率
        p_pos = len(fit) / max(1, sum(1 for rk, _ in F if rk > 50))
        for N in (1000, 3000):
            tail = sum(math.exp(a) * k ** b for k in range(len(F) + 1, N + 1)) * p_pos
            ext[N] = tot / (tot + tail)
        ext['b'] = b
    return seg, ext, len(F), tot


def analyze():
    import numpy as np
    TR, band = tagger()
    L = []; P = lambda *a: L.extend(a)
    led = load_json(LEDGER, {})
    res = {}
    for plat in ('homedepot', 'lowes', 'wayfair'):
        g, allrows, rows = ranked_rows(plat)
        g2 = load_json(raw_path('lists', f'{plat}_{KW2}.json')) or {}
        if plat == 'homedepot':
            fam = hd_families(rows)
        elif plat == 'lowes':
            fam = {r['id']: (r.get('parent') or r['id']) for r in rows}
        else:
            fam = {r['id']: r['id'] for r in rows}
        stems = {r['id']: ((r.get('brand') or '').lower(), stem(r['title'])) for r in rows}
        for r in rows:
            extra = r.get('bullets', '') if plat == 'lowes' else ''
            t1 = tag_text(TR, r['title']); t2 = tag_text(TR, r['title'], extra) if extra else t1
            r['宽_标题'], r['装_标题'], r['形态_标题'] = t1['宽'], t1['装'], t1['形态']
            r['宽_列表'], r['装_列表'], r['形态_列表'] = t2['宽'], t2['装'], t2['形态']
            if plat == 'homedepot':
                pg = load_json(raw_path('hd_pages', f"{r['id']}.json")) or {}
                sp = hd_spec_tags(pg)
                r['宽_页'] = t1['宽'] or sp['宽']; r['装_页'] = sp['装'] or t1['装']; r['形态_页'] = sp['形态'] or t1['形态']
            r['段_标题'] = band(r['宽_标题']); r['段_列表'] = band(r['宽_列表']); r['段_页'] = band(r.get('宽_页'))
            r['kw'] = bool(RE_KW_STRICT.search(r['title'])); r['kw_list'] = bool(RE_KW_STRICT.search(r['title'] + ' ' + r.get('bullets', '')))
            r['fam'] = fam[r['id']]
        res[plat] = dict(g=g, g2=g2, allrows=allrows, rows=rows, fam=fam, stems=stems)
    save_json(raw_path('分析_rows.json'), {k: v['rows'] for k, v in res.items()})
    return res, led


def summary():
    """打印报告用的全部数字（报告 solution-v2/开发建议/关键词抓取测试_reeded.md 的数字出自这里）。"""
    res, led = analyze()
    print('Bright Data ledger', led)
    for p, v in res.items():
        g, rows = v['g'], v['rows']; fam = v['fam']
        famc = collections.Counter(fam.values()); stc = collections.Counter(v['stems'].values())
        print('=====', p, 'total', g.get('total'), 'pages', len(g['pages']), 'allrows', len(v['allrows']), 'sp', sum(r['sponsored'] for r in v['allrows']),
              'dupe rows', len(v['allrows']) - len({r['id'] for r in v['allrows']}), 'n', len(rows))
        print(' fluted total', v['g2'].get('total'), 'fluted p1 kw', sum(bool(RE_KW_STRICT.search(r['title'])) for p_ in v['g2'].get('pages', []) for r in p_), '/', sum(len(p_) for p_ in v['g2'].get('pages', [])))
        print(' fam', len(famc), 'multi', sum(c > 1 for c in famc.values()), 'max', max(famc.values()), 'rows in multi', sum(c for c in famc.values() if c > 1),
              'stem fam', len(stc), 'rows in multi stem', sum(c for c in stc.values() if c > 1))
        for key in ('段_标题', '段_页', '装_标题', '装_页', '形态_标题', '形态_页'):
            if key in rows[0]: print(' ', key, collections.Counter(r[key] for r in rows).most_common())
        print(' kw', sum(r['kw'] for r in rows), 'kw by seg', [sum(r['kw'] for r in rows if lo <= r['rank'] <= hi) for lo, hi in ((1, 50), (51, 100), (101, 200), (201, 300))])
        print(' price', sum(r['price'] is not None for r in rows), 'rating', sum(r['rating'] is not None for r in rows), 'rev>0', sum((r['reviews'] or 0) > 0 for r in rows), 'reviews', sum(r['reviews'] or 0 for r in rows))
        if p == 'wayfair':
            ms = [r for r in rows if 'Sizes' in (r.get('choices') or '')]
            print(' choices', collections.Counter(r.get('choices') is not None for r in rows), 'multi-size', len(ms), sum(r['reviews'] for r in ms))
        if p == 'lowes':
            print(' variant types', collections.Counter(r.get('variant_type') for r in rows), 'marketplace', sum(r['marketplace'] for r in rows))
        for val, lab in ((lambda r: r['reviews'] or 0, '评论'), (lambda r: (r['reviews'] or 0) * (r['price'] or 0), '价×评')):
            seg, ext, nf, tot = coverage(rows, fam, val)
            print(' cov', lab, nf, round(tot), [(x['seg'], x['n'], x['pos'], round(x['share'], 3)) for x in seg], {a: round(float(b), 3) for a, b in ext.items()})
        kr = [r for r in rows if r['kw']]
        print(' kw reviews', sum(r['reviews'] or 0 for r in kr), 'kw rev>0', sum((r['reviews'] or 0) > 0 for r in kr))


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'hd':
        hd_list(KW); hd_list(KW2, max_pages=1); hd_pages()
    if cmd == 'wayfair':
        wf_list(KW); wf_list(KW2, max_pages=1)
    if cmd == 'lowes':
        lowes_list(KW); lowes_list(KW2, max_pages=1)
    if cmd == '抽样':
        sample_pages()
    if cmd == '分析':
        summary()
    if cmd == 'probe':
        which = sys.argv[2]
        if which == 'hd':
            st, b = hd_get(add_query(f'https://www.homedepot.com/s/{urllib.parse.quote(KW)}', sortby=None))
            open(raw_path('raw', 'probe', 'hd_search.html'), 'wb').write(b); print(st, len(b))
        elif which == 'lowes':
            b = bd_cached(f'https://www.lowes.com/search?searchTerm={urllib.parse.quote_plus(KW)}', 'probe_search', 'lowes')
            print(len(b or b''))
        elif which == 'wayfair':
            b = bd_cached(f'https://www.wayfair.com/keyword.php?keyword={urllib.parse.quote_plus(KW)}', 'probe_search', 'wayfair')
            print(len(b or b''))
