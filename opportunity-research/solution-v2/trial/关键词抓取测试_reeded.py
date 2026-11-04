"""关键词抓取测试（reeded）：三个小平台按关键词搜索，抓前 300 条，核实尺寸 / 拆装 / 变体 / 评论选项字段，估计覆盖。
用法：
  python 关键词抓取测试_reeded.py 采集     # 断点续采；原始缓存 input/data_v2/渠道关键词/reeded/（不入库）
  python 关键词抓取测试_reeded.py 抽样     # 商品页 / 评论变体字段核实（Lowe's、Wayfair 各 3 个经 Bright Data；HD 3 个直连）
  python 关键词抓取测试_reeded.py 分析     # → solution-v2/开发建议/关键词抓取测试_reeded.md
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
        url = add_query(f'https://www.lowes.com/search?searchTerm={urllib.parse.quote_plus(kw)}', offset=got['off'] or None)
        b = bd_cached(url, f'{kw}_{n}', 'lowes', lowes_ok, tries=2)
        st = lowes_state(b) if b else None
        if not st: log(f'Lowes {kw} 第 {n + 1} 页失败，停'); break
        rows, nxt = lowes_rows_from(st)
        if n == 0: got['total'] = lowes_total(st)
        if not rows: got['done'] = True; break
        got['pages'].append(rows)
        pg = st.get('pagination') or {}
        if not nxt or nxt <= got['off'] or (pg.get('page') or 0) >= (pg.get('pageCount') or 0): got['done'] = True
        got['off'] = nxt or got['off']; save_json(f, got)
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


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'hd':
        hd_list(KW); hd_list(KW2, max_pages=1); hd_pages()
    if cmd == 'wayfair':
        wf_list(KW); wf_list(KW2, max_pages=1)
    if cmd == 'lowes':
        lowes_list(KW); lowes_list(KW2, max_pages=1)
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
