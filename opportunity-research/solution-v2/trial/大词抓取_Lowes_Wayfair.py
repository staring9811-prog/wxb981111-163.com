"""大词抓取（Lowe's / Wayfair）：主词 "bathroom vanity" 前 500 + 6 个尺寸词各前 300，合并去重；按需抓商品页规格。
用法（可续跑，缓存在 input/data_v2/渠道关键词/大词/，不入库）：
  python 大词抓取_Lowes_Wayfair.py 列表      # 各词第 1–2 页先探翻页，再并发抓到目标条数
  python 大词抓取_Lowes_Wayfair.py 商品页    # 合并去重后，按评论数从高到低抓商品页（Lowe's 每父体 1 次，Wayfair 每 listing 1 次）
  python 大词抓取_Lowes_Wayfair.py 分析      # 打印报告数字 → solution-v2/开发建议/大词抓取_Lowes_Wayfair.md
Bright Data：复用 关键词抓取测试_reeded.py 的异步抓取与记账（本目录 ledger.json）。本轮上限 $5 ≈ 3,333 次（含 reeded 测试 36 次），
到 80%（合计 2,667 次）即停：本 ledger 上限 BD_CAP = 2,667 − 36 = 2,631。不改 tools/ 与 app/ 原文件。"""
import os, sys, re, json, math, html, collections, importlib.util, urllib.parse
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location('kw_reeded', os.path.join(HERE, '关键词抓取测试_reeded.py'))
K = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(K)
ROOT = K.ROOT
K.CACHE = os.path.join(ROOT, 'input', 'data_v2', '渠道关键词', '大词')
K.LEDGER = os.path.join(K.CACHE, 'ledger.json')
REEDED_USED = 36
K.BD_CAP = int(os.environ.get('BD_CAP', str(int(3333 * 0.8) - REEDED_USED)))
from reviewkit.common import save_json, load_json, add_query   # noqa: E402

KWS = {'bathroom vanity': 500, **{f'{w} inch bathroom vanity': 300 for w in (24, 30, 36, 48, 60, 72)}}
WORKERS = int(os.environ.get('WORKERS', '24'))
log, raw_path = K.log, K.raw_path


# ---------- 列表 ----------
LOWES_PL = 'https://www.lowes.com/pl/bathroom-vanities-vanity-tops/bathroom-vanities/4294684461'


def lowes_redirect(kw):
    """部分尺寸词（24/36/72 inch）搜索被 Lowe's 转成"浴室柜类目 + Popular Widths 筛选"，搜索 URL 的 offset 无效；
    改用类目 URL + refinement=<筛选 ID>（实测第 2 页正确）。返回筛选 ID 或 None。"""
    f = raw_path('raw', 'lowes', f'{kw}_0.html')
    if not os.path.exists(f): return None
    st = K.lowes_state(open(f, 'rb').read()) or {}
    if not str((st.get('requestParams') or {}).get('queryString', '')).startswith('department='): return None
    ids = [v for vs in (st.get('selectedFacets') or {}).values() for v in vs]
    return ','.join(ids) if ids else None


def page_url(plat, kw, n):
    if plat == 'lowes':
        ref = lowes_redirect(kw) if n else None
        if ref: return add_query(LOWES_PL, refinement=ref, offset=n * 24)
        return add_query(f'https://www.lowes.com/search?searchTerm={urllib.parse.quote_plus(kw)}', offset=n * 24 or None)
    return add_query(f'https://www.wayfair.com/keyword.php?keyword={urllib.parse.quote_plus(kw)}', curpage=n + 1 if n else None)


def wf_ok(b):
    return len(re.findall(rb'ListingCardContents::', b)) >= 24


def lowes_ok_n(n):
    """Lowe's 搜索页偶尔忽略 offset、返回第 1 页（服务端 queryString 里 offset=0）：这种结果算失败重抓。"""
    return lambda b: K.lowes_ok(b) and (f'offset={n * 24}&'.encode() in b)


def get_page(plat, kw, n):
    """返回该页解析后的行（失败 None）；原始 HTML 缓存。"""
    f = raw_path('pages', plat, f'{kw}_{n}.json')
    got = load_json(f)
    if got is not None: return got
    try:
        b = K.bd_cached(page_url(plat, kw, n), f'{kw}_{n}', plat, lowes_ok_n(n) if plat == 'lowes' else wf_ok, tries=3)
    except K.BudgetExceeded as e:
        log(str(e)); return None
    if not b: return None
    if plat == 'lowes':
        st = K.lowes_state(b)
        if not st: return None
        rows, _ = K.lowes_rows_from(st)
        if n and ((st.get('pagination') or {}).get('page') != n + 1):
            log(f'  Lowes {kw} 第 {n + 1} 页：服务端仍返回第 {(st.get("pagination") or {}).get("page")} 页（offset 被忽略），记失败'); os.remove(raw_path('raw', plat, f'{kw}_{n}.html')); return None
        out = {'rows': rows, 'meta': K.lowes_total(st), 'req_offset': ((st.get('requestParams') or {}).get('queryString') or '').split('offset=')[-1].split('&')[0]}
    else:
        s = b.decode('utf-8', 'ignore')
        out = {'rows': K.wf_cards(s), 'meta': {'total': K.wf_total(s)}}
    save_json(f, out)
    return out


def organic(plat, kw, upto):
    seen, out = set(), []
    for n in range(upto):
        p = load_json(raw_path('pages', plat, f'{kw}_{n}.json'))
        if p is None: break
        for r in p['rows']:
            if r['sponsored'] or not r['id'] or r['id'] in seen: continue
            seen.add(r['id']); out.append(dict(r, rank=len(out) + 1, kw=kw))
    return out


def lists():
    jobs = [(p, kw, n) for p in ('lowes', 'wayfair') for kw in KWS for n in (0, 1)]
    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(lambda j: get_page(*j), jobs))
    plan = []
    for p in ('lowes', 'wayfair'):
        for kw, N in KWS.items():
            p0, p1 = (load_json(raw_path('pages', p, f'{kw}_{n}.json')) for n in (0, 1))
            if not p0 or not p1:
                log(f'{p} {kw}: 第 1/2 页没拿到，跳过'); continue
            ids0 = {r['id'] for r in p0['rows'] if not r['sponsored']}; ids1 = {r['id'] for r in p1['rows'] if not r['sponsored']}
            new = len(ids1 - ids0)
            log(f'{p} {kw}: 总数 {p0["meta"]}，第 1 页自然位 {len(ids0)}，第 2 页新增 {new}')
            if new == 0:
                log(f'{p} {kw}: 翻页无效（第 2 页与第 1 页相同），停在第 1 页'); continue
            per = max(new, 10)
            pages = math.ceil(N / per) + (2 if p == 'wayfair' else 1)
            if p == 'lowes':
                pc = (p0['meta'].get('pagination') or {}).get('pageCount') or pages
                pages = min(pages, pc, 30)   # Lowe's maxOffset 720 = 30 页
            plan += [(p, kw, n) for n in range(2, pages)]
    log(f'列表第二批：{len(plan)} 页')
    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(lambda j: get_page(*j), plan))
    # 不够的补页（Wayfair 每页新增不稳定）
    for _ in range(3):
        more = []
        for p in ('lowes', 'wayfair'):
            for kw, N in KWS.items():
                n_have = 0
                while load_json(raw_path('pages', p, f'{kw}_{n_have}.json')) is not None: n_have += 1
                if n_have < 2: continue
                last = load_json(raw_path('pages', p, f'{kw}_{n_have - 1}.json'))
                if len(organic(p, kw, n_have)) < N and last and last['rows'] and n_have < 40:
                    if p == 'lowes':
                        pc = (load_json(raw_path('pages', p, f'{kw}_0.json'))['meta'].get('pagination') or {}).get('pageCount') or 0
                        if n_have >= min(pc, 30): continue
                    more += [(p, kw, n) for n in range(n_have, n_have + 3)]
        if not more: break
        log(f'补页 {len(more)}')
        with ThreadPoolExecutor(WORKERS) as ex:
            list(ex.map(lambda j: get_page(*j), more))
    for p in ('lowes', 'wayfair'):
        for kw, N in KWS.items():
            n_have = 0
            while load_json(raw_path('pages', p, f'{kw}_{n_have}.json')) is not None: n_have += 1
            log(f'{p} {kw}: {n_have} 页，自然位去重 {len(organic(p, kw, n_have))}（目标 {N}）')


def merged(plat):
    """各词前 N 合并；Lowe's 按父体去重、Wayfair 按 listing 去重。返回 {家族: 代表行}，代表行带 kws / best_rank。"""
    fams = {}
    for kw, N in KWS.items():
        n_have = 0
        while load_json(raw_path('pages', plat, f'{kw}_{n_have}.json')) is not None: n_have += 1
        for r in organic(plat, kw, n_have)[:N]:
            fk = (r.get('parent') or r['id']) if plat == 'lowes' else r['id']
            if fk not in fams:
                fams[fk] = dict(r, fam=fk, kws={kw: r['rank']}, ids=[r['id']])
            else:
                f = fams[fk]; f['kws'][kw] = min(f['kws'].get(kw, 9999), r['rank'])
                if r['id'] not in f['ids']: f['ids'].append(r['id'])
                if (r['reviews'] or 0) > (f['reviews'] or 0): f['reviews'] = r['reviews']
    return fams


# ---------- 商品页 ----------
def pdp(plat, fam):
    f = raw_path('pdp', plat, f"{fam['id']}.json")
    got = load_json(f)
    if got is not None: return got
    try:
        b = K.bd_cached(fam['url'], fam['id'], plat + '_pdp', K.lowes_ok if plat == 'lowes' else (lambda b: len(b) > 300000), tries=2)
    except K.BudgetExceeded as e:
        return {'budget': str(e)}
    out = parse_lowes(b, fam['id']) if (b and plat == 'lowes') else (parse_wf(b) if b else None)
    if out is None: out = {'失败': True}
    save_json(f, out)
    return out


def parse_lowes(b, pid):
    st = K.lowes_state(b)
    if not st: return None
    pdd = (st.get('productDetails') or {})
    if pid not in pdd and pdd: pid = next(iter(pdd))
    d = pdd.get(pid) or {}; p = d.get('product') or {}
    specs = {x.get('key'): x.get('value') for x in p.get('specs') or [] if isinstance(x, dict)}
    v3 = p.get('productVariantsV3') or {}
    variants = {u.get('name'): [(x.get('value'), x.get('omniItemId')) for x in u.get('values') or []] for u in v3.get('variantUIData') or []}
    price = ((d.get('mfePrice') or {}).get('price') or {}).get('additionalData') or {}
    rt = (st.get('ratings') or {}).get(pid) or {}
    rv = re.search(rb'"(/reviews/[^"]+)"', b)
    return dict(id=pid, title=p.get('title'), brand=p.get('brand'), specs=specs, variants=variants,
                selected=[(a.get('name'), a.get('value')) for a in (v3.get('selectedVariant') or {}).get('attributes') or []],
                price=price.get('sellingPrice'), rating=rt.get('rating'), reviews=rt.get('reviewCount'),
                reviews_url=rv.group(1).decode() if rv else None)


def parse_wf(b):
    s = b.decode('utf-8', 'ignore'); dec = json.JSONDecoder()
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', s)
    try: t = ''.join(json.loads('"' + c + '"') for c in chunks)
    except Exception: return None
    specs = {}

    def walk(items):
        for it in items or []:
            if isinstance(it, dict):
                if 'key' in it: specs.setdefault(it['key'], it.get('value')); walk(it.get('children'))
                walk(it.get('items'))
    for m in re.finditer(r'"specifications_[a-z_]+":', t):
        try: walk(dec.raw_decode(t[m.end():])[0])
        except Exception: pass
    for m in re.finditer(r'\{"key":"(Overall Dimensions|Overall Width[^"]*)","value":"([^"]*)"', t):
        specs.setdefault(m.group(1), m.group(2))
    cats = []
    i = t.find('"choiceCategories":[{"displayType"')
    if i >= 0:
        try:
            for c in dec.raw_decode(t[i + len('"choiceCategories":'):])[0]:
                cats.append(dict(name=c.get('name'), selected=((c.get('selectedVariantChoice') or {}).get('choice') or {}).get('name'),
                                 n=(c.get('variantChoices') or {}).get('totalCount'),
                                 values=[e['node']['choice']['name'] for e in (c.get('variantChoices') or {}).get('edges') or []]))
        except Exception: pass
    revs = []
    for m in re.finditer(r'"node":\{"__typename":"MarketplaceListingReview",', t):
        try:
            r = dec.raw_decode(t[m.start() + len('"node":'):])[0]
            revs.append(dict(date=r.get('formattedDate'), rating=r.get('rating'), badge=r.get('badge'), choices=[(c['name'], c['value']) for c in r.get('choices') or []]))
        except Exception: pass
    tot = re.search(r'"reviews":\{"averageRating":([\d.]+),"totalCount":(\d+)', t)
    pr = re.search(r'"priceVariation":"(?:SALE|PRIMARY|STANDARD)","label":"[^"]*","price":\{"__typename":"FixedPrice","prefix":"","value":\{"amount":"([\d.]+)"', t)
    title = re.search(r'<title>([^<]*)', s)
    return dict(title=html.unescape(title.group(1)) if title else None, specs=specs, choices=cats, reviews_embedded=revs,
                rating=float(tot.group(1)) if tot else None, reviews=int(tot.group(2)) if tot else None, price=float(pr.group(1)) if pr else None)


def pdps(plats=('lowes', 'wayfair'), min_reviews=1):
    """只抓评论数 ≥ min_reviews 的家族（零评论家族对销量 / 评论占比没有贡献，预算不够时不抓，字段只用列表 + 标题）。"""
    todo = []
    for plat in plats:
        for fk, f in merged(plat).items():
            if (f['reviews'] or 0) >= min_reviews: todo.append((-(f['reviews'] or 0), plat, f))
    todo.sort(key=lambda x: x[0])           # 评论多的先抓；两个平台交替按评论数排
    log(f'商品页待抓 {len(todo)}（Lowe\'s {sum(t[1] == "lowes" for t in todo)}，Wayfair {sum(t[1] == "wayfair" for t in todo)}）')
    stop = []

    def job(t):
        if stop: return
        r = pdp(t[1], t[2])
        if isinstance(r, dict) and r.get('budget'):
            if not stop: log('到预算上限，停止商品页：' + r['budget'])
            stop.append(1)
    done = [0]
    with ThreadPoolExecutor(WORKERS) as ex:
        for _ in ex.map(job, todo):
            done[0] += 1
            if done[0] % 100 == 0: log(f'商品页 {done[0]}/{len(todo)}，ledger {load_json(K.LEDGER, {})}')


# ---------- 分析 ----------
def num(v):
    m = re.search(r'(\d+(?:\.\d+)?)', str(v or ''))
    return float(m.group(1)) if m else None


def wf_width(dim):
    m = re.search(r"(\d+(?:\.\d+)?)''?\s*W", str(dim or ''))
    return float(m.group(1)) if m else None


def fields_lowes(f, pg, TR):
    sp = (pg or {}).get('specs') or {}
    t = K.tag_text(TR, f['title'], f.get('bullets', ''))
    o = {}
    w = num(sp.get('Actual Width (Inches)')) or num(sp.get('Common Width (Inches)'))
    o['宽'], o['宽来源'] = (w, '规格') if w else (t['宽'], '标题' if t['宽'] else '')
    title = (f['title'] or '').lower()
    rta, req = str(sp.get('Ready to Assemble (RTA)') or sp.get('Assembly') or '').lower(), str(sp.get('Assembly Required') or '').lower()
    if 'fully assembled' in title: o['装'], o['装来源'] = '整装', '标题'
    elif 'ready to assemble' in rta: o['装'], o['装来源'] = '拆装', '规格'
    elif req == 'no': o['装'], o['装来源'] = '整装', '规格'
    elif req == 'yes': o['装'], o['装来源'] = '拆装', '规格'
    elif t['装'] != '未知': o['装'], o['装来源'] = t['装'], '标题'
    else: o['装'], o['装来源'] = None, ''
    it, fl = str(sp.get('Installation Type') or '').lower(), str(sp.get('Floating') or '').lower()
    if fl == 'yes' or 'wall' in it or 'float' in it: o['形态'], o['形态来源'] = '悬浮式', '规格'
    elif 'freestanding' in it or 'floor' in it or fl == 'no': o['形态'], o['形态来源'] = '落地式', '规格'
    elif t['形态'] != '未知': o['形态'], o['形态来源'] = t['形态'], '标题'
    else: o['形态'], o['形态来源'] = None, ''
    o['颜色'] = sp.get('Color/Finish Family') or sp.get('Manufacturer Color/Finish')
    o['台面'] = next((v for k, v in sp.items() if v and re.search(r'top material|countertop material', k, re.I)), None)
    o['柜体'] = next((v for k, v in sp.items() if v and re.search(r'^(base|cabinet|vanity|frame) material', k, re.I)), None)
    widths = set()
    for name, vals in ((pg or {}).get('variants') or {}).items():
        if re.search(r'width|size', name or '', re.I):
            for v, _ in vals:
                x = num(v)
                if x: widths.add(x)
    o['选项宽'] = sorted(widths)
    return o


def fields_wf(f, pg, TR):
    sp = (pg or {}).get('specs') or {}
    t = K.tag_text(TR, f['title'])
    o = {}
    sel = next((c for c in (pg or {}).get('choices') or [] if re.search(r'width|size', c['name'] or '', re.I)), None)
    w = (num(sel['selected']) if sel else None) or num(sp.get('Overall Width from Side to Side')) or wf_width(sp.get('Overall Dimensions'))
    o['宽'], o['宽来源'] = (w, '商品页') if w else (t['宽'], '标题' if t['宽'] else '')
    a = str(sp.get('Assembly') or sp.get('Level of Assembly') or '').lower()
    if 'no assembly' in a: o['装'], o['装来源'] = '整装', '规格'
    elif 'assembl' in a: o['装'], o['装来源'] = '拆装', '规格'   # Full Assembly Needed / Partially Assembled（同 HD 口径，部分组装算拆装）
    elif t['装'] != '未知': o['装'], o['装来源'] = t['装'], '标题'
    else: o['装'], o['装来源'] = None, ''
    m = str(sp.get('Mounting / Installation') or sp.get('Mounting Type') or '').lower()
    if 'wall' in m or 'float' in m: o['形态'], o['形态来源'] = '悬浮式', '规格'
    elif 'freestanding' in m or 'floor' in m: o['形态'], o['形态来源'] = '落地式', '规格'
    elif t['形态'] != '未知': o['形态'], o['形态来源'] = t['形态'], '标题'
    else: o['形态'], o['形态来源'] = None, ''
    o['颜色'] = sp.get('Base Color') or sp.get('Base Finish') or sp.get('Color')
    o['装原值'] = sp.get('Assembly')
    o['台面'] = sp.get('Countertop Material') or sp.get('Top Material')
    o['柜体'] = sp.get('Base Material') or sp.get('Material')
    widths = set()
    for c in (pg or {}).get('choices') or []:
        if re.search(r'width|size', c['name'] or '', re.I):
            for v in c['values']:
                if '/' in v: continue
                x = num(v)
                if x and 15 <= x <= 100: widths.add(x)
    o['选项宽'] = sorted(widths)
    o['评论带选项'] = sum(bool(r['choices']) for r in (pg or {}).get('reviews_embedded') or [])
    o['内嵌评论'] = len((pg or {}).get('reviews_embedded') or [])
    return o


def table(plat):
    TR, band = K.tagger()
    out = []
    for fk, f in merged(plat).items():
        pg = load_json(raw_path('pdp', plat, f"{f['id']}.json"))
        ok = bool(pg) and not pg.get('失败') and not pg.get('budget')
        o = (fields_lowes if plat == 'lowes' else fields_wf)(f, pg if ok else None, TR)
        bands = {band(x) for x in o['选项宽']} - {None}
        o.update(fam=fk, id=f['id'], title=f['title'], kws=f['kws'], n_ids=len(f['ids']), 商品页=ok,
                 price=f['price'] if f['price'] is not None else (pg or {}).get('price') if ok else f['price'],
                 rating=f['rating'] if f['rating'] is not None else ((pg or {}).get('rating') if ok else None),
                 reviews=f['reviews'] or 0, 段=band(o['宽']), 选项段=sorted(bands), 多尺寸段=len(bands) > 1)
        if ok and plat == 'lowes' and pg.get('reviews'):
            try: o['reviews_pdp'] = int(pg['reviews'])
            except (TypeError, ValueError): pass
        out.append(o)
    return out


def main():
    led = load_json(K.LEDGER, {})
    print('ledger', led)
    for plat in ('lowes', 'wayfair'):
        print('=' * 20, plat)
        for kw, N in KWS.items():
            n_have = 0
            while load_json(raw_path('pages', plat, f'{kw}_{n_have}.json')) is not None: n_have += 1
            p0 = load_json(raw_path('pages', plat, f'{kw}_0.json')) or {}
            allr = [r for n in range(n_have) for r in load_json(raw_path('pages', plat, f'{kw}_{n}.json'))['rows']]
            print(f' {kw}: 总数 {p0.get("meta")} 页 {n_have} 原始 {len(allr)} 广告 {sum(r["sponsored"] for r in allr)} 自然位去重 {len(organic(plat, kw, n_have))} 取 {min(N, len(organic(plat, kw, n_have)))}')
        T = table(plat)
        n = len(T); rv = sum(o['reviews'] for o in T) or 1
        print(' 合并去重家族', n, '商品页', sum(o['商品页'] for o in T), '评论合计', rv, '有评论', sum(o['reviews'] > 0 for o in T))
        print(' 只出现在一个词', sum(len(o['kws']) == 1 for o in T), '主词独有', sum(list(o['kws']) == ['bathroom vanity'] for o in T))
        def cov(key, sub=None):
            S = [o for o in T if sub is None or sub(o)]
            k = [o for o in S if o.get(key) not in (None, '', [])]
            return len(k), len(S), sum(o['reviews'] for o in k) / (sum(o['reviews'] for o in S) or 1)
        for key in ('段', '装', '形态', '颜色', '台面', '柜体', 'price', 'rating'):
            a, b_, c = cov(key); a2, b2, c2 = cov(key, lambda o: o['商品页'])
            print(f'  {key}: 全部 {a}/{b_} 评论占 {c:.0%} | 有商品页的 {a2}/{b2} 评论占 {c2:.0%}')
        for key in ('宽来源', '装来源', '形态来源'):
            print(f'  {key}', collections.Counter(o[key] for o in T).most_common(), '按评论', {k: round(sum(o["reviews"] for o in T if o[key] == k) / rv, 3) for k in set(o[key] for o in T)})
        frame = [o for o in T if o['段'] and o['装'] and o['形态']]
        single = [o for o in frame if not o['多尺寸段']]
        multi = [o for o in frame if o['多尺寸段']]
        print(f'  框可定 {len(frame)}/{n} 评论占 {sum(o["reviews"] for o in frame) / rv:.0%}；其中单尺寸段 {len(single)} 评论占 {sum(o["reviews"] for o in single) / rv:.0%}，多尺寸段家族 {len(multi)} 评论占 {sum(o["reviews"] for o in multi) / rv:.0%}')
        print('  多尺寸段家族（全部）', sum(o['多尺寸段'] for o in T), '评论占', round(sum(o['reviews'] for o in T if o['多尺寸段']) / rv, 3))
        fb = collections.Counter((o['段'], o['装'], o['形态']) for o in frame)
        fr = collections.defaultdict(int)
        for o in frame: fr[(o['段'], o['装'], o['形态'])] += o['reviews']
        print('  框分布（家族数，评论）', sorted(((k, fb[k], fr[k]) for k in fb), key=lambda x: -x[2])[:25])
        if plat == 'wayfair':
            P = [o for o in T if o['商品页']]
            print('  内嵌评论', sum(o['内嵌评论'] for o in P), '带选项', sum(o['评论带选项'] for o in P), '有带选项评论的 listing', sum(o['评论带选项'] > 0 for o in P), '/', sum(o['内嵌评论'] > 0 for o in P))
        if plat == 'lowes':
            P = [o for o in T if o['商品页'] and 'reviews_pdp' in o]
            print('  列表评论数 vs 商品页评论数 一致', sum(o['reviews'] == o['reviews_pdp'] for o in P), '/', len(P))
        # 覆盖：主词按排名分段
        rows = organic(plat, 'bathroom vanity', 99)[:500]
        famof = (lambda r: r.get('parent') or r['id']) if plat == 'lowes' else (lambda r: r['id'])
        seen, F = set(), []
        for r in rows:
            if famof(r) in seen: continue
            seen.add(famof(r)); F.append((r['rank'], r['reviews'] or 0))
        tot = sum(v for _, v in F) or 1
        print('  主词分段评论占比', [(f'{lo}-{hi}', sum(1 for rk, _ in F if lo <= rk <= hi), round(sum(v for rk, v in F if lo <= rk <= hi) / tot, 3)) for lo, hi in ((1, 50), (51, 100), (101, 200), (201, 300), (301, 400), (401, 500))])
        allrv = sum(o['reviews'] for o in T); mainrv = tot
        print('  主词前500评论', mainrv, '合并后评论', allrv, '尺寸词新增评论占合并', round(1 - mainrv / allrv, 3) if allrv else None)
        save_json(raw_path(f'分析_{plat}.json'), T)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == '列表': lists()
    elif cmd == '商品页': pdps(tuple(sys.argv[2:]) or ('lowes', 'wayfair'), int(os.environ.get('MIN_REVIEWS', '1')))
    elif cmd == '分析':
        main()
