"""三平台商品范围整理（wen 2026-11-04 定）：每个平台 = "bathroom vanity" + "bathroom vanity with sink" 自然位前 300 并集
+ wen 渠道VP 表「商品月度明细」的类目节点商品（HD 两类目各 100、Lowe's 两榜各 100、Wayfair 主类目 200 + 无台面 50），合并去重
（Lowe's 按 parentId，HD 按评论家族，Wayfair 按 listing）。
用法：
  python 大词抓取_三平台整理.py 现状        # 范围、重合、规格已有 / 缺、评论补抓需要的请求数估算
  python 大词抓取_三平台整理.py 补规格      # 只为范围内缺规格的商品抓商品页（Lowe's / Wayfair 经 BD；HD 直连）
  python 大词抓取_三平台整理.py 补评论      # 关键词独有商品补 2026 逐月评论（HD 直连、Lowe's 经 BD 评论页）
  python 大词抓取_三平台整理.py 整理        # → input/data_v2/渠道关键词/大词/三平台_商品表.csv、三平台_月销表.csv（供 小平台调研_单元指标.py）
  python 大词抓取_三平台整理.py 分析        # 打印报告数字（solution-v2/开发建议/大词抓取_三平台.md）
Bright Data 记账同 大词抓取_Lowes_Wayfair.py（ledger 上限 = $4 线）。"""
import os, sys, re, json, math, collections, importlib.util
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
_s = importlib.util.spec_from_file_location('dc', os.path.join(HERE, '大词抓取_Lowes_Wayfair.py'))
B = importlib.util.module_from_spec(_s); _s.loader.exec_module(B)
K, ROOT = B.K, B.ROOT
log, raw_path, load_json, save_json = K.log, K.raw_path, B.load_json, B.save_json
XLSX = os.path.join(ROOT, 'input/data_v2/渠道VP/浴室柜_2026_渠道VP_20261103.xlsx')
MONTHS = [f'2026-{i:02d}' for i in range(1, 11)]
CH = {'homedepot': 'Home Depot', 'lowes': "Lowe's", 'wayfair': 'Wayfair'}


def vp_table():
    import pandas as pd
    d = pd.read_excel(XLSX, '商品月度明细')
    d['商品ID'] = d['商品ID'].astype(str)
    d['id'] = d['商品ID'].str.split(' ').str[0]
    d['piid'] = d['商品ID'].str.extract(r'piid (\d+)')[0]
    return d


def kw_rows(plat):
    """两个词各前 300 自然位（HD 来自直连列表）。"""
    out = []
    for kw, N in B.KWS.items():
        if plat == 'homedepot':
            g = load_json(raw_path('lists', f'homedepot_{kw}.json')) or {'pages': []}
            seen, rows = set(), []
            for r in (r for p in g['pages'] for r in p):
                if r['sponsored'] or r['id'] in seen: continue
                seen.add(r['id']); rows.append(dict(r, rank=len(rows) + 1, kw=kw))
        else:
            n = 0
            while load_json(raw_path('pages', plat, f'{kw}_{n}.json')) is not None: n += 1
            rows = B.organic(plat, kw, n)
        out += rows[:N]
    return out


# ---------------- HD ----------------
OLD_HD_REV = os.path.join(ROOT, 'input', 'data_v2', '渠道历史', 'homedepot', 'reviews')


def hd_universe(V):
    """HD：两词商品页 + 类目节点商品页 → 评论家族（评论首页相同 / 评论里出现对方商品页 ID 即同家族）。"""
    kw = kw_rows('homedepot')
    vp = V[V['渠道'] == 'Home Depot']
    items = {}
    for r in kw:
        it = items.setdefault(r['id'], dict(id=r['id'], title=r['title'], price=r['price'], rating=r['rating'], reviews=r['reviews'], kws={}, vp_entries=[]))
        it['kws'][r['kw']] = min(it['kws'].get(r['kw'], 999), r['rank'])
    for _, r in vp.iterrows():
        it = items.setdefault(r['id'], dict(id=r['id'], title=r['标题'], price=None, rating=None, reviews=r['页面累计评论数'], kws={}, vp_entries=[]))
        it['vp_entries'].append(r['入口'])
    parent = {p: p for p in items}

    def root(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    by_sig = {}
    for p in items:
        pg = load_json(raw_path('hd_pages', f'{p}.json')) or load_json(os.path.join(K.OLD_HD, f'{p}.json')) or {}
        items[p]['page'] = pg
        sig = tuple(pg.get('sig') or [])
        if sig:
            if sig in by_sig: parent[root(p)] = root(by_sig[sig])
            else: by_sig[sig] = p
    for p in items:
        for q in items[p]['page'].get('sig_pids') or []:
            if q in parent and q != p: parent[root(q)] = root(p)
    for p in items: items[p]['fam'] = root(p)
    return items


def status():
    import pandas as pd
    V = vp_table()
    print('ledger', load_json(K.LEDGER, {}))
    # HD
    hd = hd_universe(V)
    fams = collections.defaultdict(list)
    for p, it in hd.items(): fams[it['fam']].append(it)
    kwf = {f for f, L in fams.items() if any(i['kws'] for i in L)}; vpf = {f for f, L in fams.items() if any(i['vp_entries'] for i in L)}
    page_ok = sum(1 for it in hd.values() if it['page'].get('status') == 200)
    print(f"HD 商品页 {len(hd)}（两词 {sum(bool(i['kws']) for i in hd.values())}，类目节点 {sum(bool(i['vp_entries']) for i in hd.values())}），家族 {len(fams)}；"
          f"两词家族 {len(kwf)}，类目节点家族 {len(vpf)}，重合 {len(kwf & vpf)}；商品页规格已有 {page_ok}")
    have_rev = {f for f in fams if os.path.exists(os.path.join(OLD_HD_REV, f'F{f}.json')) or os.path.exists(raw_path('hd_reviews', f'F{f}.json'))}
    # 旧缓存的家族键是旧家族根，不一定等于新根：按成员 ID 查
    old = {}
    for fn in os.listdir(OLD_HD_REV):
        g = load_json(os.path.join(OLD_HD_REV, fn)) or {}
        for x in (g.get('reviews') or {}).values(): old[x.get('pid')] = fn
    rev_ok = {f for f, L in fams.items() if any(i['id'] in old for i in L)}
    need = [f for f in kwf - vpf if f not in rev_ok and sum(i['reviews'] or 0 for i in fams[f]) > 0]
    print(f"HD 关键词独有家族 {len(kwf - vpf)}，其中已有评论缓存 {len((kwf - vpf) & rev_ok)}，需补评论（有评论的）{len(need)}，"
          f"评论数合计 {sum(max(i['reviews'] or 0 for i in fams[f]) for f in need)}（直连免费）")
    # Lowe's / Wayfair
    for plat in ('lowes', 'wayfair'):
        m = B.merged(plat)
        vp = V[V['渠道'] == CH[plat]]
        ids_in_kw = {}
        for fk, f in m.items():
            for i in f['ids']: ids_in_kw[i] = fk
            pg = load_json(raw_path('pdp', plat, f"{f['id']}.json")) or {}
            for vals in (pg.get('variants') or {}).values():
                for _, oid in vals: ids_in_kw.setdefault(oid, fk)
        vp_ids = list(dict.fromkeys(vp['id']))
        overlap = [i for i in vp_ids if i in ids_in_kw]
        vp_only = [i for i in vp_ids if i not in ids_in_kw]
        kw_fams = len(m); kw_fams_vp = len({ids_in_kw[i] for i in overlap})
        has = lambda pid: (lambda d: bool(d) and not d.get('失败') and not d.get('budget'))(load_json(raw_path('pdp', plat, f'{pid}.json')))
        kw_has = sum(has(f['id']) for f in m.values()); kw_rev = [f for f in m.values() if (f['reviews'] or 0) > 0]
        kw_rev_has = sum(has(f['id']) for f in kw_rev)
        vp_has = sum(has(i) for i in vp_only)
        # 关键词独有（不在类目节点）且有评论的家族：月度评论要补
        vpfam = {ids_in_kw[i] for i in overlap}
        kwonly_rev = [f for fk, f in m.items() if fk not in vpfam and (f['reviews'] or 0) > 0]
        print(f"{plat}: 两词并集 {kw_fams} 个家族（有评论 {len(kw_rev)}，其中已有规格 {kw_rev_has}；全部已有规格 {kw_has}）；"
              f"类目节点商品 {len(vp_ids)}，与两词并集重合 {len(overlap)}（落在 {kw_fams_vp} 个家族），类目独有 {len(vp_only)}（已有商品页 {vp_has}）")
        print(f"   缺规格：两词有评论 {len(kw_rev) - kw_rev_has}，两词零评论 {kw_fams - len(kw_rev) - (kw_has - kw_rev_has)}，类目独有 {len(vp_only) - vp_has}")
        tot = sum(f['reviews'] for f in kwonly_rev)
        print(f"   关键词独有且有评论的家族 {len(kwonly_rev)}，页面评论合计 {tot}")
        if plat == 'lowes':
            # 2026 1–10 月评论占累计评论的比例（用类目节点表估）
            r26 = vp[[f'{mm} 合计' for mm in MONTHS]].sum(axis=1).sum() / vp.drop_duplicates('页面累计评论数')['页面累计评论数'].sum()
            pages = sum(math.ceil(f['reviews'] * min(1, r26 * 1.2) / 20) + 1 for f in kwonly_rev)
            print(f"   估：2026 年 1–10 月评论约占累计 {r26:.0%}（类目节点表）；按评论页 20 条 / 页、新到旧翻到 2026-01 前，约需 {pages} 次")
        if plat == 'wayfair':
            full = sum(1 for f in kwonly_rev if (lambda d: d and d.get('reviews_embedded') is not None and len(d['reviews_embedded']) >= (d.get('reviews') or 0))(load_json(raw_path('pdp', plat, f"{f['id']}.json"))))
            print(f"   其中商品页内嵌评论已是全部（可做月度）{full}；其余只能用评论总数（GraphQL 经 BD 返回 400）")
    print('尺寸词额外商品（仅参考）：', {p: len(set(B.merged(p, B.SIZE_KWS)) - set(B.merged(p))) for p in ('lowes', 'wayfair')})



# ---------------- 补评论：HD（直连，复用 小平台_HD回测小试.py 的评论接口与分片逻辑） ----------------
def hd_trial():
    s = importlib.util.spec_from_file_location('hdt', os.path.join(HERE, '小平台_HD回测小试.py'))
    T = importlib.util.module_from_spec(s); s.loader.exec_module(T)
    T.CACHE = os.path.join(K.CACHE, 'hd'); os.makedirs(os.path.join(T.CACHE, 'reviews'), exist_ok=True)
    T.CUTOFF = '2025-12-01'          # 只需要 2026 年起；多抓一个月判断首评
    return T


def old_hd_index():
    idx = {}
    for fn in os.listdir(OLD_HD_REV):
        g = load_json(os.path.join(OLD_HD_REV, fn)) or {}
        for x in (g.get('reviews') or {}).values(): idx.setdefault(x.get('pid'), os.path.join(OLD_HD_REV, fn))
    return idx


def hd_reviews():
    T = hd_trial(); V = vp_table(); items = hd_universe(V)
    fams = collections.defaultdict(list)
    for p, it in items.items(): fams[it['fam']].append(it)
    old = old_hd_index()
    todo = [f for f, L in fams.items() if any(i['kws'] for i in L) and not any(i['vp_entries'] for i in L)
            and not any(i['id'] in old for i in L) and max(i['reviews'] or 0 for i in L) > 0]
    log(f'HD 补评论家族 {len(todo)}')
    for k, f in enumerate(todo):
        g = T.family_reviews(f'F{f}', f)
        if k % 10 == 0: log(f'  HD 评论 {k + 1}/{len(todo)} {g.get("状态")} {len(g.get("reviews") or {})}')



# ---------------- 补规格（Lowe's / Wayfair 经 BD） ----------------
def vp_fam(d):
    """同 小平台调研_单元指标.lw_table：10 个月 VP / 非 VP 序列 + 11 月 + 页面累计评论数完全相同 = 同一家族（共享评论）。"""
    vc = [f'{m} VP' for m in MONTHS] + [f'{m} 非VP' for m in MONTHS] + ['2026-11（未完整） 合计']
    import pandas as pd
    return 'F' + pd.Series(pd.factorize(d[vc].astype(str).agg('|'.join, axis=1) + '#' + d['页面累计评论数'].astype(str))[0], index=d.index).astype(str)


def is_vanity(title):
    return bool(re.search(r'vanit', title or '', re.I))


def has_pdp(plat, pid):
    d = load_json(raw_path('pdp', plat, f'{pid}.json'))
    return bool(d) and not d.get('失败') and not d.get('budget')


def spec_jobs():
    V = vp_table(); jobs = []
    for plat in ('lowes', 'wayfair'):
        m = B.merged(plat)
        known = set()
        for f in m.values():
            known.update(f['ids'])
            pg = load_json(raw_path('pdp', plat, f"{f['id']}.json")) or {}
            for vals in (pg.get('variants') or {}).values(): known.update(o for _, o in vals)
            if not is_vanity(f['title']): continue    # 关键词结果里混着淋浴龙头、镜子等非浴室柜，不抓
            if (f['reviews'] or 0) > 0 and not has_pdp(plat, f['id']): jobs.append((f['reviews'], plat, dict(id=f['id'], url=f['url'])))
        d = V[V['渠道'] == CH[plat]].copy(); d['vfam'] = vp_fam(d)
        d['y26'] = d[[f'{mm} 合计' for mm in MONTHS]].sum(axis=1)
        for vf, g in d.groupby('vfam'):
            if any(i in known for i in g['id']): continue
            if any(has_pdp(plat, i) for i in g['id']): continue
            r = g.sort_values('排名').iloc[0]
            if (r['页面累计评论数'] or 0) <= 0 and r['y26'] <= 0: continue
            url = f"https://www.lowes.com/pd/-/{r['id']}" if plat == 'lowes' else f"https://www.wayfair.com/x/pdp/x-{r['id'].lower()}.html" + (f"?piid={r['piid']}" if isinstance(r['piid'], str) else '')
            jobs.append((r['页面累计评论数'] or 0, plat, dict(id=r['id'], url=url)))
    jobs.sort(key=lambda j: -j[0])
    return jobs


def fill_specs(plats=('lowes', 'wayfair')):
    jobs = [j for j in spec_jobs() if j[1] in plats]
    log(f"补规格 {len(jobs)}（Lowe's {sum(j[1] == 'lowes' for j in jobs)}，Wayfair {sum(j[1] == 'wayfair' for j in jobs)}）")
    stop = []
    def run(j):
        if stop: return
        r = B.pdp(j[1], j[2])
        if r.get('budget') and not stop: stop.append(1); log('到预算线，停：' + r['budget'])
    with ThreadPoolExecutor(B.WORKERS) as ex: list(ex.map(run, jobs))
    log(f"补规格结束，ledger {load_json(K.LEDGER, {})}")


# ---------------- 补评论：Lowe's（BD 评论页，每页 20 条，新到旧，翻到 2026-01 前） ----------------
def lowes_review_family(pid, rurl):
    f = raw_path('lowes_reviews', f'{pid}.json'); got = load_json(f)
    if got and got.get('状态') in ('完整', '部分'): return got
    revs, off, status, total = {}, 0, '完整', None
    while True:
        try:
            b = K.bd_cached('https://www.lowes.com' + rurl + (f'?offset={off}' if off else ''), f'{pid}_{off}', 'lowes_rnr', K.lowes_ok, tries=2)
        except K.BudgetExceeded as e:
            status = '预算停'; break
        st = None
        try: st = K.lowes_state(b) if b else None
        except ValueError: st = None
        rl = ((st or {}).get('ratingList') or {})
        rl = rl.get(pid) or (next(iter(rl.values())) if rl else None)
        if not rl:
            status = '失败' if off == 0 else '部分'; break
        total = rl.get('totalResults')
        res = rl.get('results') or []
        for x in res:
            revs[x['id']] = dict(d=(x.get('submissionTime') or '')[:10], r=x.get('rating'), vp=bool(x.get('verifiedPurchaser')),
                                 inc=bool(x.get('incentivizedReview')), syn=bool(x.get('isSyndicated')), pid=str(x.get('productId')),
                                 u=x.get('pdPageURL') or '')
        off += 20
        if not res or off >= (total or 0) or min((x.get('submissionTime') or '9')[:10] for x in res) < '2026-01-01': break
    out = {'状态': status, '评论总数': total, 'reviews': revs}
    if status != '预算停': save_json(f, out)
    return out


def lowes_reviews():
    """按商品表：类目节点里的多尺寸家族（评论 productId 拆尺寸用）+ 两词独有有评论家族（补月度），按 2026 评论量估计从大到小。"""
    import pandas as pd
    P = pd.read_csv(raw_path('三平台_商品表.csv'), dtype={'pid': str})
    p = P[(P['渠道'] == "Lowe's") & (P['来源'] == '两词') & (P['页面评论数'].fillna(0) > 0) & P['浴室柜'].fillna(True).astype(bool)]
    todo = [(r['页面评论数'], r['pid'], lowes_rurl(r['pid'])) for _, r in p.iterrows()]
    todo.sort(key=lambda t: -t[0])
    log(f"Lowe's 补评论家族 {len(todo)}（商品表里符合条件 {len(p)}，无评论链接 {len(p) - len(todo)}）")
    stop = []
    def run(t):
        if stop: return
        g = lowes_review_family(t[1], t[2])
        if g.get('状态') == '预算停' and not stop: stop.append(1); log('到 $4 线，停')
    with ThreadPoolExecutor(B.WORKERS) as ex: list(ex.map(run, todo))
    log(f"Lowe's 补评论结束，ledger {load_json(K.LEDGER, {})}")


def lowes_reviews_old():
    V = vp_table(); m = B.merged('lowes')
    vp_ids = set(V[V['渠道'] == "Lowe's"]['id'])
    todo = []
    for fk, f in m.items():
        pg = load_json(raw_path('pdp', 'lowes', f"{f['id']}.json")) or {}
        ids = set(f['ids']) | {o for vals in (pg.get('variants') or {}).values() for _, o in vals}
        if ids & vp_ids or (f['reviews'] or 0) <= 0: continue
        todo.append((f['reviews'], f['id'], pg.get('reviews_url')))
    todo.sort(key=lambda t: -t[0])
    log(f"Lowe's 补评论家族 {len(todo)}（无评论链接 {sum(t[2] is None for t in todo)}）")
    def run(t):
        if t[2]: return lowes_review_family(t[1], t[2])
    with ThreadPoolExecutor(B.WORKERS) as ex: list(ex.map(run, todo))
    log(f"Lowe's 补评论结束，ledger {load_json(K.LEDGER, {})}")


# ---------------- 整理：商品表 + 月销表 ----------------
def xc():
    sys.path.insert(0, HERE)
    import 跨渠道供给差_HD检验 as XC
    return XC


def labels(XC, title, spec_text_dict, highlights=None):
    """D5–D8 与 宽 / 装 / 形态（v12.2 Tagger，标题 + 规格文本）。"""
    t = XC.HD.tag_variant(XC.TR, title or '', spec_text_dict or None, highlights or [])
    if t['宽'] is None: t['宽'] = K.title_width(title)   # Tagger 认不出"30 in. W x 18 in. D"这类写法时用标题正则补
    return t


def mapped(XC, t):
    U = XC.UNKS
    return dict(台面材质='未知' if t['D8'] in U else t['D8'], 主色=XC.color(t['D6']), 柜体材质=XC.cab(t['D7']),
                元素='、'.join(sorted({XC.HD.ELEM_MAP[x] for x in str(t['D5']).split('；') if x in XC.HD.ELEM_MAP})) or '未知')


def mrow(ch, fam, pid, seg, asm, form, m, vp, nvp, src, w=1.0):
    return dict(渠道=ch, fam=fam, pid=pid, 尺寸段=seg, 装=asm, 形态=form, 月=m, VP=vp * w, 非VP=nvp * w, 销量=(vp * 50 + nvp * 20) * w, 月度来源=src)


def build_hd(XC, V):
    items = hd_universe(V)
    # 评论：旧缓存（HD 回测小试，类目 Top Sellers 前 300 家族）+ 本次补抓
    files = [os.path.join(OLD_HD_REV, f) for f in os.listdir(OLD_HD_REV)] + \
            [os.path.join(K.CACHE, 'hd', 'reviews', f) for f in os.listdir(os.path.join(K.CACHE, 'hd', 'reviews'))]
    fam_of = {p: it['fam'] for p, it in items.items()}
    R = {}
    for fn in files:
        g = load_json(fn) or {}
        if g.get('状态') not in ('完整', '截断'): continue
        rv = g.get('reviews') or {}
        fk = next((fam_of[x['pid']] for x in rv.values() if x.get('pid') in fam_of), None) or fam_of.get(os.path.basename(fn)[1:-5])   # 评论只落在未列出的变体上时，按文件名（F+家族根商品页）归家族
        if fk is None: continue
        for rid, x in rv.items():
            if (x.get('d') or '')[:7] in MONTHS: R[rid] = dict(x, fam=fk)
    names = {}
    for x in R.values(): names.setdefault(x['pid'], x.get('name'))
    prod, mon = [], []
    pids = set(items) | {x['pid'] for x in R.values()}
    lab = {}
    for p in pids:
        it = items.get(p); pg = (it or {}).get('page') or load_json(os.path.join(K.OLD_HD, f'{p}.json')) or {}
        title = (it or {}).get('title') or pg.get('title') or names.get(p) or ''
        t = labels(XC, title, pg.get('specs'), pg.get('highlights'))
        fam = (it or {}).get('fam') or next(x['fam'] for x in R.values() if x['pid'] == p)
        lab[p] = dict(t, fam=fam, title=title, page=bool(pg.get('specs')))
        src = '两者' if it and it['kws'] and it['vp_entries'] else ('两词' if it and it['kws'] else ('类目节点' if it and it['vp_entries'] else '同家族变体（评论里出现）'))
        prod.append(dict(渠道='Home Depot', fam=fam, pid=p, title=title, 品牌=pg.get('brand'), 来源=src,
                         两词排名=json.dumps((it or {}).get('kws') or {}, ensure_ascii=False), 宽=t['宽'], 尺寸段=XC.band(t['宽']),
                         装=t['装'], 装来源=t['装来源'], 形态=t['形态'], 形态来源=t['形态来源'], **mapped(XC, t),
                         价格=(it or {}).get('price') or pg.get('price'), 评分=(it or {}).get('rating'), 页面评论数=(it or {}).get('reviews'),
                         有商品页=bool(pg.get('specs')), 月度来源='评论（变体级）', 主图=None))   # HD 缓存（商品页规格 / 列表接口）没存图片字段，补图要新请求
    # 同家族补装（同系列只换颜色 / 尺寸；与 小平台调研_单元指标 同口径）
    fm = collections.defaultdict(collections.Counter)
    for p_, L_ in lab.items():
        if L_['装'] != '未知': fm[L_['fam']][L_['装']] += 1
    for p_, L_ in lab.items():
        if L_['装'] == '未知' and fm[L_['fam']]: L_['装'] = fm[L_['fam']].most_common(1)[0][0]; L_['装来源'] = '家族补'
    for r_ in prod:
        L_ = lab[r_['pid']]; r_['装'], r_['装来源'], r_['宽'], r_['尺寸段'] = L_['装'], L_['装来源'], L_['宽'], XC.band(L_['宽'])
    agg = collections.defaultdict(lambda: [0, 0])
    for x in R.values():
        agg[(x['pid'], x['d'][:7])][0 if x['vp'] else 1] += 1
    for (p, m), (a, b) in agg.items():
        L_ = lab[p]; mon.append(mrow('Home Depot', L_['fam'], p, XC.band(L_['宽']), L_['装'], L_['形态'], m, a, b, '评论（变体级）'))
    return prod, mon


def width_of_variant(pg):
    """Lowe's 商品页：变体 omniItemId → 宽（宽度维度的选项值）。"""
    out = {}
    for name, vals in (pg.get('variants') or {}).items():
        if re.search(r'width|size', name or '', re.I):
            for v, o in vals:
                x = B.num(v)
                if x: out[o] = x
    return out


def build_lw(XC, V, plat):
    import pandas as pd
    ch = CH[plat]; TRx = XC.TR
    m = B.merged(plat)
    d = V[V['渠道'] == ch].copy(); d['vfam'] = vp_fam(d)
    known = {}
    for fk, f in m.items():
        for i in f['ids']: known[i] = fk
        pg = load_json(raw_path('pdp', plat, f"{f['id']}.json")) or {}
        for vals in (pg.get('variants') or {}).values():
            for _, o in vals: known.setdefault(o, fk)
    # 实体：两词家族 + 类目节点独有家族（按渠道VP表的家族；同家族里任何商品落在两词家族就并入）
    ent = {}
    for fk, f in m.items():
        ent[fk] = dict(fam=fk, rep=f, ids=set(f['ids']), kws=f['kws'], vp=None)
    for vf, g in d.groupby('vfam'):
        hit = next((known[i] for i in g['id'] if i in known), None)
        key = hit or f'VP{vf}'
        e = ent.setdefault(key, dict(fam=key, rep=None, ids=set(), kws={}, vp=None))
        e['ids'] |= set(g['id']); e['vp'] = g if e['vp'] is None else pd.concat([e['vp'], g])
    prod, mon = [], []
    for key, e in ent.items():
        f = e['rep']
        pg = None
        cands = ([f['id']] if f else []) + sorted(e['ids'])
        for c in cands:
            x = load_json(raw_path('pdp', plat, f'{c}.json'))
            if x and not x.get('失败') and not x.get('budget'): pg = x; pid0 = c; break
        else: pid0 = cands[0]
        g = e['vp']
        title = (f or {}).get('title') or (pg or {}).get('title') or (g.iloc[0]['标题'] if g is not None else '')
        if plat == 'wayfair' and pg and pg.get('title'): title = re.sub(r'\s*&amp; Reviews.*|\s*& Reviews.*', '', pg['title'])
        row = dict(f or {}, title=title, bullets=(f or {}).get('bullets', ''))
        o = (B.fields_lowes if plat == 'lowes' else B.fields_wf)(row, pg, TRx)
        # 颜色：商品页颜色字段（Lowe's Color/Finish Family、Wayfair Base Color / Base Finish）接在标题后交给 Tagger 认主色
        t = labels(XC, title + (f" in {o['颜色']}" if o['颜色'] else ''), {k: v for k, v in ((pg or {}).get('specs') or {}).items() if v} or None)
        bands = sorted({XC.band(x) for x in o['选项宽']} - {None})
        seg = XC.band(o['宽'])
        page_rev = (f or {}).get('reviews') or (int(g['页面累计评论数'].max()) if g is not None and pd.notna(g['页面累计评论数'].max()) else 0)
        src = '两者' if e['kws'] and g is not None else ('两词' if e['kws'] else '类目节点')
        price = (f or {}).get('price') or (pg or {}).get('price')
        rating = (f or {}).get('rating') or (pg or {}).get('rating')
        multi = len(bands) > 1
        # 月度
        msrc = ''
        if g is not None:
            msrc = '渠道VP表（家族合计）'
            split = split_weights(plat, pid0, pg, seg, bands)
            for _, r0 in g.drop_duplicates('vfam').iterrows():     # 一个实体可能并入渠道VP表的多个家族
                for mm in MONTHS:
                    for (sg, w) in split:
                        mon.append(mrow(ch, key, pid0, sg, o['装'], o['形态'], mm, r0[f'{mm} VP'], r0[f'{mm} 非VP'], msrc + ('；按评论选项拆尺寸' if len(split) > 1 else ''), w))
        elif plat == 'lowes':
            rv = load_json(raw_path('lowes_reviews', f'{pid0}.json'))
            if rv and rv.get('状态') in ('完整', '部分'):
                msrc = 'BD 评论页（变体级）'
                wmap = width_of_variant(pg or {})
                cnt = collections.defaultdict(lambda: [0, 0])
                for x in rv['reviews'].values():
                    if x['d'][:7] in MONTHS:
                        w = review_width(x, wmap); sg = XC.band(w) if w else (seg if not multi else '多尺寸未拆')
                        cnt[(sg, x['d'][:7])][0 if x['vp'] else 1] += 1
                for (sg, mm), (a, b_) in cnt.items():
                    mon.append(mrow(ch, key, pid0, sg, o['装'], o['形态'], mm, a, b_, msrc))
        else:
            if pg and pg.get('reviews_embedded') is not None and len(pg['reviews_embedded']) >= (pg.get('reviews') or 0) and pg['reviews_embedded']:
                msrc = '商品页内嵌评论（全部）'
                cnt = collections.defaultdict(lambda: [0, 0])
                for x in pg['reviews_embedded']:
                    dt = x.get('date') or ''
                    mm = f'{dt[6:10]}-{dt[0:2]}' if len(dt) == 10 else ''
                    if mm not in MONTHS: continue
                    wv = next((B.num(v) for n, v in x['choices'] if re.search(r'width|size', n, re.I)), None)
                    sg = XC.band(wv) if wv else (seg if not multi else '多尺寸未拆')
                    cnt[(sg, mm)][0 if x.get('badge') == 'Verified Purchase' else 1] += 1
                for (sg, mm), (a, b_) in cnt.items():
                    mon.append(mrow(ch, key, pid0, sg, o['装'], o['形态'], mm, a, b_, msrc))
            elif load_json(raw_path('wayfair_apify', 'wayfair', 'apify', f'{pid0}.json')):
                # 只有评论总数的 listing：Apify（abotapi/wayfair-scraper）补到 2026-01–10 逐月评论；VP 口径同上（徽章 = Verified Purchase）。
                # 多尺寸 listing 与 Lowe's 同法：按 2026 年评论 purchasedOptions 里的宽度分布把月销拆到尺寸段（至少 5 条带宽度才拆）
                rv = (load_json(raw_path('wayfair_apify', 'wayfair', 'apify', f'{pid0}.json'))['item'].get('reviews') or [])
                part = apify_status().get(pid0, '完整') != '完整'
                msrc = 'Apify 评论' + ('（部分：只抓到最近 100 条，更早的 2026 评论缺）' if part else '')
                cnt = collections.defaultdict(lambda: [0, 0]); wd = collections.Counter()
                for x in rv:
                    dt = x.get('date') or ''
                    mm = f'{dt[6:10]}-{dt[0:2]}' if len(dt) == 10 else ''
                    if mm not in MONTHS: continue
                    cnt[mm][0 if x.get('badge') == 'Verified Purchase' else 1] += 1
                    wv = next((B.num(v) for n, v in (x.get('purchasedOptions') or {}).items() if re.search(r'width|size', n, re.I)), None)
                    if wv and XC.band(wv): wd[XC.band(wv)] += 1
                if not multi: split = [(seg, 1.0)]
                elif sum(wd.values()) >= 5: split = [(k, v / sum(wd.values())) for k, v in wd.items()]; msrc += '；按评论选项拆尺寸'
                else: split = [('多尺寸未拆', 1.0)]
                for mm, (a, b_) in cnt.items():
                    for sg, w in split:
                        mon.append(mrow(ch, key, pid0, sg, o['装'], o['形态'], mm, a, b_, msrc, w))
            elif page_rev:
                msrc = '无（只有评论总数）'
        prod.append(dict(渠道=ch, fam=key, pid=pid0, title=title, 品牌=(pg or {}).get('brand') or (f or {}).get('brand') or (g.iloc[0]['品牌'] if g is not None else None),
                         来源=src, 两词排名=json.dumps(e['kws'], ensure_ascii=False), 宽=o['宽'], 尺寸段=seg, 装=o['装'] or '未知', 装来源=o['装来源'] or '',
                         形态=o['形态'] or '未知', 形态来源=o['形态来源'] or '', **mapped(XC, t), 颜色原值=o['颜色'], 台面原值=o['台面'], 柜体原值=o['柜体'],
                         价格=price, 评分=rating, 页面评论数=page_rev, 有商品页=pg is not None, 多尺寸段=multi, 选项段='、'.join(bands), 月度来源=msrc,
                         浴室柜=is_vanity(title), 主图=main_image(plat, [pid0] + ([f['id']] if f else []) + sorted(e['ids']) + [o for vals in ((pg or {}).get('variants') or {}).values() for _, o in vals])))
    return prod, mon


_APS = {}
_IMG = {}


def image_index():
    """主图索引（只读已抓缓存，不发请求）：{平台: {商品 ID: 图片 URL}}。优先级从低到高：列表页卡片 < Lowe's 评论页 og:image < Wayfair Apify imageUrl < 商品页 og:image。
    解析结果存 主图索引.json，缓存有变化时删掉它重建。"""
    if _IMG: return _IMG
    f = raw_path('主图索引.json'); got = load_json(f)
    if got: _IMG.update(got); return _IMG
    import glob, html as H
    idx = {'lowes': {}, 'wayfair': {}}
    og = re.compile(r'property="og:image"\s+content="([^"]+)"|content="([^"]+)"\s+property="og:image"')
    def ogimg(fn):
        m = og.search(open(fn, encoding='utf-8', errors='ignore').read())
        u = m and (m.group(1) or m.group(2))
        return ('https:' + u if u and u.startswith('//') else u) or None
    for fn in glob.glob(raw_path('raw', 'lowes', '*.html')):             # Lowe's 列表页：__PRELOADED_STATE__.itemList[].product.imageUrl
        st = K.lowes_state(open(fn, 'rb').read()) or {}
        for it in st.get('itemList') or []:
            p = it.get('product') or {}; u = p.get('imageUrl') or p.get('alternateImageUrl')
            if p.get('omniItemId') and u: idx['lowes'][str(p['omniItemId'])] = u if u.startswith('http') else 'https://mobileimages.lowes.com' + u
    for fn in glob.glob(raw_path('raw', 'wayfair', '*.html')):           # Wayfair 列表页：卡片里第一张 assets.wfcdn.com 图
        s_ = open(fn, encoding='utf-8', errors='ignore').read(); starts = [m.start() for m in re.finditer(r'data-clio-id="ListingCardContents::', s_)] + [len(s_)]
        for a, b in zip(starts, starts[1:]):
            ts = s_.rfind('<', 0, a); tag = s_[ts:s_.find('>', a)]
            mm = re.search(r'data-tracking-metadata="([^"]*)"', tag)
            try: lid = json.loads(H.unescape(mm.group(1))).get('metadata', {}).get('displayListingId') if mm else None
            except ValueError: lid = None
            im = re.search(r'(https://assets\.wfcdn\.com/im/[^"\s]+)', s_[a:b])
            if lid and im: idx['wayfair'][str(lid)] = H.unescape(im.group(1))
    for fn in glob.glob(raw_path('raw', 'lowes_rnr', '*_0.html')):       # Lowe's 评论页 og:image
        u = ogimg(fn)
        if u: idx['lowes'][os.path.basename(fn)[:-7]] = u
    for fn in glob.glob(raw_path('wayfair_apify', 'wayfair', 'apify', '*.json')):   # Wayfair Apify 原始返回
        it = (load_json(fn) or {}).get('item') or {}
        u = it.get('imageUrl') or next((x if isinstance(x, str) else (x or {}).get('url') for x in it.get('images') or []), None)
        if u: idx['wayfair'][os.path.basename(fn)[:-5]] = u
    for plat in ('lowes', 'wayfair'):                                     # 商品页 og:image（最高优先）
        for fn in glob.glob(raw_path('raw', f'{plat}_pdp', '*.html')):
            u = ogimg(fn)
            if u: idx[plat][os.path.basename(fn)[:-5]] = u
    save_json(f, idx); _IMG.update(idx)
    return _IMG


def main_image(plat, ids):
    d = image_index().get(plat) or {}
    return next((d[str(i)] for i in ids if i and str(i) in d), None)


def apify_status():
    """Wayfair 补评论_月度.csv 的状态（完整 / 部分（只抓到最近 100 条…））。"""
    if not _APS:
        import pandas as pd
        f = raw_path('wayfair_apify', 'Wayfair补评论_月度.csv')
        if os.path.exists(f):
            d = pd.read_csv(f, dtype={'pid': str})
            _APS.update(d.drop_duplicates('pid').set_index('pid')['状态'].to_dict())
    return _APS


def split_weights(plat, pid0, pg, seg, bands):
    """类目节点家族的月销拆到尺寸段：单尺寸 → 原段；多尺寸 → Wayfair 用内嵌评论的 Overall Width 分布、Lowe's 用已抓评论页的变体分布；都没有 → 多尺寸未拆。"""
    if len(bands) <= 1: return [(seg if seg else (bands[0] if bands else None), 1.0)]
    c = collections.Counter()
    if plat == 'wayfair':
        for x in (pg or {}).get('reviews_embedded') or []:
            wv = next((B.num(v) for n, v in x['choices'] if re.search(r'width|size', n, re.I)), None)
            if wv: c[xc().band(wv)] += 1
    else:
        rv = load_json(raw_path('lowes_reviews', f'{pid0}.json')) or {}
        wmap = width_of_variant(pg or {})
        for x in (rv.get('reviews') or {}).values():
            wv = review_width(x, wmap)
            if wv: c[xc().band(wv)] += 1
    c.pop(None, None)
    if sum(c.values()) >= 5:
        n = sum(c.values()); return [(k, v / n) for k, v in c.items()]
    return [('多尺寸未拆', 1.0)]


def dedupe_pid(P, M):
    """同渠道同 pid 只留一行（系统导入按 AC-F30-03 拒绝重复）：留月销表里有该 渠道+fam+pid 的那行，都有或都没有时留第一行。
    例：Lowe's 5018243355 同时挂在父体 5018441651（有月销）和 6003479666（列表顺带、无月销）下。"""
    has = set(zip(M['渠道'], M['fam'].astype(str), M['pid'].astype(str)))
    P = P.assign(_有月销=[(c, str(f), str(p)) in has for c, f, p in zip(P['渠道'], P['fam'], P['pid'])])
    P = P.sort_values('_有月销', ascending=False, kind='stable').drop_duplicates(['渠道', 'pid']).sort_index()
    return P.drop(columns='_有月销')


def build():
    import pandas as pd
    XC = xc(); V = vp_table()
    P, M = [], []
    for fn in (lambda: build_hd(XC, V), lambda: build_lw(XC, V, 'lowes'), lambda: build_lw(XC, V, 'wayfair')):
        p_, m_ = fn(); P += p_; M += m_
    P = pd.DataFrame(P); M = pd.DataFrame(M)
    P = dedupe_pid(P, M)
    P.to_csv(raw_path('三平台_商品表.csv'), index=False, encoding='utf-8-sig')
    M.to_csv(raw_path('三平台_月销表.csv'), index=False, encoding='utf-8-sig')
    # 装判断不了的：记未知、不进框，单列待确认清单（wen 2026-11-04）
    s26 = M.groupby(['渠道', 'fam'])['销量'].sum()
    Q = P[(P['装'] == '未知') | P['装'].isna()].copy()
    Q['1–10 月销量'] = [s26.get((c, f), 0) for c, f in zip(Q['渠道'], Q['fam'])]
    Q = Q[['渠道', 'fam', 'pid', 'title', '来源', '尺寸段', '形态', '页面评论数', '1–10 月销量', '有商品页']].sort_values(['渠道', '1–10 月销量'], ascending=[True, False])
    Q.to_csv(raw_path('三平台_装待确认.csv'), index=False, encoding='utf-8-sig')
    log(f'整理：商品表 {len(P)} 行，月销表 {len(M)} 行，装待确认 {len(Q)} 行')
    return P, M


def analyze():
    import pandas as pd
    P = pd.read_csv(raw_path('三平台_商品表.csv')); M = pd.read_csv(raw_path('三平台_月销表.csv'))
    print('ledger', load_json(K.LEDGER, {}))
    UNK = {'未知', '', None}
    for ch in ('Home Depot', "Lowe's", 'Wayfair'):
        p = P[P['渠道'] == ch].copy(); m = M[M['渠道'] == ch].copy()
        if ch != 'Home Depot': p = p[p['浴室柜'].fillna(True)]
        fam = p.groupby('fam').agg(来源=('来源', lambda s: '两者' if '两者' in set(s) or {'两词', '类目节点'} <= set(s) else ('两词' if '两词' in set(s) else ('类目节点' if '类目节点' in set(s) else s.iloc[0]))),
                                   评论=('页面评论数', 'max'), 月度=('月度来源', 'first'))
        print('=' * 10, ch, '商品行', len(p), '家族/实体', len(fam), fam['来源'].value_counts().to_dict())
        sales = m.groupby('fam')['销量'].sum()
        fam['销量'] = sales.reindex(fam.index).fillna(0)
        print('  月度来源（实体数 / 销量）', fam.groupby('月度').agg(n=('销量', 'size'), s=('销量', 'sum')).to_dict('index'))
        print('  页面评论数合计', fam['评论'].sum(), '有月度销量的实体评论占', round(fam.loc[fam['销量'] > 0, '评论'].sum() / max(fam['评论'].sum(), 1), 3))
        # 字段覆盖（商品行；按评论数加权）
        w = p['页面评论数'].fillna(0)
        def cov(col, unk=UNK):
            k = ~p[col].isin(unk) & p[col].notna()
            return f'{k.mean():.0%}（评论加权 {w[k].sum() / max(w.sum(), 1):.0%}）'
        for col in ('尺寸段', '装', '形态', '主色', '台面材质', '柜体材质', '价格', '评分', '页面评论数'):
            print(f'  {col}: {cov(col)}')
        # 分框标签（按销量）
        tot = m['销量'].sum()
        for col in ('尺寸段', '装', '形态'):
            k = ~m[col].isin(UNK | {'多尺寸未拆'}) & m[col].notna()
            print(f'  分框 {col} 按 2026-01–10 销量覆盖 {m.loc[k, "销量"].sum() / max(tot, 1):.1%}')
        k = (~m['尺寸段'].isin(UNK | {'多尺寸未拆'}) & m['尺寸段'].notna() & ~m['装'].isin(UNK) & m['装'].notna() & ~m['形态'].isin(UNK) & m['形态'].notna())
        print(f'  能落框销量占比 {m.loc[k, "销量"].sum() / max(tot, 1):.1%}（销量 {tot:,.0f}，多尺寸未拆 {m.loc[m["尺寸段"] == "多尺寸未拆", "销量"].sum() / max(tot, 1):.1%}）')
        print('  月均销量（1–10 月）', round(tot / 10))
        if ch != 'Home Depot':
            print('  多尺寸段实体', int(p['多尺寸段'].fillna(False).sum()), '有商品页', int(p['有商品页'].sum()), '/', len(p))
        fb = m[k].groupby(['尺寸段', '装', '形态'])['销量'].sum().sort_values(ascending=False) / 10
        print('  框月均（前 12）', [(a, round(v)) for a, v in fb.head(12).items()])


def slug_width(u):
    """Lowe's 评论的 pdPageURL（写评论时的变体页）里的宽度：…-Sandbanks-48-in-Greige-… → 48。"""
    m = re.search(r'[-/](\d{2}(?:\.\d+)?)-?(?:in|inch)(?:es)?\b', u or '', re.I)
    if m and 15 <= float(m.group(1)) <= 100: return float(m.group(1))
    return None


def review_width(x, wmap):
    return wmap.get(x.get('pid')) or slug_width(x.get('u'))


def lowes_reviews_vp():
    """第 1 步：类目节点（渠道VP表）里的多尺寸 / 尺寸未定家族，抓评论页（新到旧翻到 2026-01 前），按评论变体拆尺寸。"""
    import pandas as pd
    P = pd.read_csv(raw_path('三平台_商品表.csv'), dtype={'pid': str}); M = pd.read_csv(raw_path('三平台_月销表.csv'), dtype={'pid': str})
    p = P[(P['渠道'] == "Lowe's") & P['来源'].isin(['类目节点', '两者'])]
    bad = set(M[(M['渠道'] == "Lowe's") & (M['尺寸段'].isna() | (M['尺寸段'] == '多尺寸未拆'))]['fam'])
    s26 = M[M['渠道'] == "Lowe's"].groupby('fam')['VP'].sum() + M[M['渠道'] == "Lowe's"].groupby('fam')['非VP'].sum()
    p = p[p['fam'].isin(bad)].copy(); p['w'] = p['fam'].map(s26).fillna(0)
    todo = [(r['w'], r['pid'], lowes_rurl(r['pid'])) for _, r in p.sort_values('w', ascending=False).iterrows() if r['w'] > 0]
    log(f"Lowe's 类目节点待拆家族 {len(todo)}，2026 评论约 {int(sum(t[0] for t in todo))} 条")
    run_lowes_reviews(todo)


def lowes_rurl(pid):
    pg = load_json(raw_path('pdp', 'lowes', f'{pid}.json')) or {}
    return pg.get('reviews_url') or f'/reviews/x/{pid}'      # 不带商品名的评论页 URL 实测可用（同一父体）


def run_lowes_reviews(todo):
    stop = []
    def run(t):
        if stop: return
        g = lowes_review_family(t[1], t[2])
        if g.get('状态') == '预算停' and not stop: stop.append(1); log('到 $5.3 线，停')
    with ThreadPoolExecutor(B.WORKERS) as ex: list(ex.map(run, todo))
    log(f"Lowe's 评论结束，ledger {load_json(K.LEDGER, {})}")

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == '现状': status()
    elif cmd == '补评论HD': hd_reviews()
    elif cmd == '补规格': fill_specs()
    elif cmd == '补评论Lowes': lowes_reviews()
    elif cmd == '补评论Lowes类目': lowes_reviews_vp()
    elif cmd == '补规格Wayfair': fill_specs(('wayfair',))
    elif cmd == '补规格Lowes': fill_specs(('lowes',))
    elif cmd == '整理': build()
    elif cmd == '分析': analyze()

