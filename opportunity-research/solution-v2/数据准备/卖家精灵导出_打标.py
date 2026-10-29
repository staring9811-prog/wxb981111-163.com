"""给卖家精灵按月导出（product_research，每行 = 月 × 子体）打标，规则全部用打标技能 v12.1，不沿用以前的标签（wen 2026-10-29）。
1. 读 input/data_v2/sellersprite_zip_*/ 下全部月份，同一月份两份就停。父体字段等于子体自己、但变体数 > 1 的行（卖家精灵当月没认出父体）
   补"家族键"：同月有别的行把它当父体就是那个家族 → 其他月份的父体 → 同月同品牌同月销的唯一家族 → 同月同品牌同月销的这类行合并；原 parent 不改。
2. 文字：每月导出的标题、SKU、商品尺寸。五点和详细参数导出里没有，从 2026 年已有材料接（当前快照，不是当月历史）：
   五点先找同子体自己的（子体详情），再找同子体的父体五点，再找同家族的；详细参数只用同子体的（1–5 月卖家精灵导出）。
3. 用技能原脚本 tag_cached.py 打标（柱状盆、默认值、尺寸、实木价格复核等全部现行规则）。
4. 形态分两层（wen 2026-10-29："开放式属于站立式"）：形态（怎么装）= 技能 D1，技能的"开放式"（console）归落地式；
   柜体结构 = 开放式（文字写了不带门的开放层板：open shelf / open storage / open compartment / console 等）或待图片核验。
5. 与 2026 年已打标签（1–5 月 v12、6–9 月 v11）对同一子体比一致率；出分析用表、证据、待核验清单和汇总报告。
环境变量：TAGGER（技能目录，含 scripts/）、EXPORTS（导出 JSON 的 glob）、OUT_DIR（默认 input/data_v2/sellersprite_打标，不入库）、REPORT_MD。
用法：TAGGER=<技能目录> python3 -I 卖家精灵导出_打标.py"""
import os, re, json, glob, html, subprocess, sys, numpy as np, pandas as pd
from collections import Counter, defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
D2 = os.path.join(ROOT, 'input/data_v2')
TAGGER = os.environ['TAGGER']
FILES = sorted(glob.glob(os.environ.get('EXPORTS', f'{D2}/sellersprite_zip_*/*_full_data.json')))
OUT = os.environ.get('OUT_DIR', f'{D2}/sellersprite_打标')
REPORT = os.environ.get('REPORT_MD', os.path.join(HERE, '卖家精灵导出_打标结果.md'))
P15 = f'{D2}/202601-202605_打标'
V11 = f'{D2}/BathroomVanities_202606-202609_SKU销量预估_已打标_v11.xlsx'
VANITY = '6810202011'
HEADERS = ['D1产品形态', 'D2安装方式', 'D3盆数', 'D4台面形态', 'D5元素', 'D6柜体颜色', 'D7柜体材质', 'D8台面材质', 'D8台盆材质',
           'D9宽(in)', 'D9深(in)', 'D9高(in)', 'D10镜子', 'D11龙头', '打标状态', '打标说明']
TAGGED_STATES = ('文本证据可用', '部分信息不足', '存在冲突待核验')
OPEN = (None, '信息不足', '待图片核验')
WORK = os.path.join(OUT, '_work'); DR = os.path.join(WORK, 'data_root'); TD = os.path.join(WORK, 'tag')
for d in (OUT, DR, TD): os.makedirs(d, exist_ok=True)

def nn(v):  # JSON 不接受 NaN
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else v

def run(script, *args):
    r = subprocess.run([sys.executable, '-I', os.path.join(TAGGER, 'scripts', script), *map(str, args)], capture_output=True, text=True)
    if r.returncode != 0: raise SystemExit(f'{script} 失败：{r.stdout[-800:]}{r.stderr[-800:]}')
    return r.stdout

# ---------- 读导出 ----------
items, src = [], {}
for f in FILES:
    j = json.load(open(f, encoding='utf-8')); m = j['month']
    if m in src: raise SystemExit(f'{m} 有两份导出：{src[m]} 与 {f}')
    if not j.get('complete'): raise SystemExit(f'{f} 没有标记完整')
    src[m] = f
    for i, r in enumerate(j['items']): items.append(dict(r, _m=m, _file=os.path.basename(f), _i=i))
MONTHS = sorted(src)
print('月份', MONTHS, '行', len(items))

# ---------- 1. 家族键 ----------
x = pd.DataFrame({'m': [r['_m'] for r in items], 'asin': [r['asin'] for r in items], 'parent': [r.get('parent') or r['asin'] for r in items],
                  'brand': [r.get('brand') or None for r in items], 'units': [r.get('units') for r in items], 'var': [r.get('variations') or 0 for r in items]})
other = x[x.parent != x.asin].groupby('asin').parent.agg(lambda s: s.value_counts().index[0]).to_dict()
real = x[(x.parent != x.asin) & x.brand.notna()].groupby(['m', 'brand', 'units']).parent.agg(set).to_dict()
lost = (x.parent == x.asin) & (x['var'] > 1)
grp = x[lost & x.brand.notna()].groupby(['m', 'brand', 'units']).asin.agg(list).to_dict()
is_parent = set(zip(x.m[x.parent != x.asin], x.parent[x.parent != x.asin]))  # 同月有别的行把它当父体
FAM, FAM_HOW = [], []
for r in x.itertuples():
    key = (r.m, r.brand, r.units)
    if r.parent != r.asin: k, how = r.parent, '父体字段'
    elif (r.m, r.asin) in is_parent: k, how = r.asin, '被同月其他行当父体'
    elif r.var <= 1: k, how = r.asin, '单体链接'
    elif r.asin in other: k, how = other[r.asin], '其他月份的父体'
    elif r.brand and len(real.get(key, ())) == 1: k, how = next(iter(real[key])), '同月同品牌同月销的家族'
    elif r.brand and len(grp.get(key, [])) > 1: k, how = min(grp[key]), '同月同品牌同月销的无父体行合并'
    else: k, how = r.asin, '未补（按单体算）'
    FAM.append(k); FAM_HOW.append(how)
x['fam'] = FAM; x['how'] = FAM_HOW
REAL_PARENT = {'父体字段', '被同月其他行当父体', '其他月份的父体', '同月同品牌同月销的家族'}

# ---------- 2. 文字来源 ----------
pay = json.load(open(f'{P15}/_work/data_root/sales_payload.json', encoding='utf-8'))['detailRows']
pa = pd.DataFrame([{'子ASIN': r['子ASIN'], '核验父ASIN': r.get('核验父ASIN'), '五点': r.get('五点描述'), '来源': r.get('五点来源'),
                    '来源ASIN': r.get('五点来源ASIN'), '月': str(r['目标月份'])} for r in pay])
V = pd.read_excel(V11, sheet_name='SKU估算明细', dtype=str); V['月'] = V['目标月份'].str[:6]
pv = V.rename(columns={'五点描述': '五点', '五点来源': '来源', '五点来源ASIN': '来源ASIN'})[['子ASIN', '核验父ASIN', '五点', '来源', '来源ASIN', '月']]
B = pd.concat([pa, pv], ignore_index=True)
B = B[B['五点'].fillna('').str.strip() != ''].sort_values('月', kind='stable')
def latest(d, key): return d.dropna(subset=[key]).drop_duplicates(key, keep='last').set_index(key)  # 整行取最近一条，不跨行拼
own = latest(B[B['来源'] == '子体详情'], '子ASIN')                 # ① 同子体自己的
child_fill = latest(B[B['来源'] == '父体详情填充'], '子ASIN')      # ② 同子体的父体五点
par_fill = latest(B[B['来源'] == '父体详情填充'], '来源ASIN')      # ③ 同家族：父体详情
par_any = latest(B, '核验父ASIN')                                 # ③ 同家族：其他子体的五点

def bullets(a, p):
    if a in own.index: r = own.loc[a]; return r['五点'], '子体详情', a, '2026 同子体自己的五点'
    if a in child_fill.index: r = child_fill.loc[a]; return r['五点'], '父体详情填充', r['来源ASIN'], '2026 同子体的父体五点'
    if p and p in par_fill.index: r = par_fill.loc[p]; return r['五点'], '父体详情填充', p, '2026 同家族的父体五点'
    if p and p in par_any.index:
        r = par_any.loc[p]; s = r['来源ASIN'] if r['来源'] == '父体详情填充' else r['子ASIN']
        return r['五点'], '父体详情填充', s, '2026 同家族其他子体的五点'
    return None, None, None, None

ir = json.load(open(f'{P15}/_work/data_root/input_rows.json', encoding='utf-8'))
ATTR = {}
for r in sorted(ir, key=lambda r: str(r['month'])):
    if r.get('attributes'): ATTR[r['asin']] = r                          # 同子体最近一条详细参数

audit = json.load(open(f'{P15}/_work/data_root/step1_macro_audit.json', encoding='utf-8'))['confirmedNonTargetProducts']
nt = V[(V['打标状态'] == '不纳入浴室柜分析') & ~V['打标说明'].astype(str).str.startswith('保留原始记录')]
NONTARGET = {**nt.groupby('子ASIN')['打标说明'].first().to_dict(), **audit}

# ---------- 3. 规范化输入并打标 ----------
rows, meta = [], []
for k, r in enumerate(items):
    a = r['asin']; fam, how = FAM[k], FAM_HOW[k]; p = fam if how in REAL_PARENT else a
    b, bsrc, basin, bhow = bullets(a, p)
    img = r.get('imageUrl'); img = re.sub(r'\._[^/]*_\.jpg$', '._AC_SL500_.jpg', img) if img else None
    rows.append({'子ASIN': a, '目标月份': r['_m'], '站点': 'US', '核验父ASIN': p, 'SKU属性': nn(r.get('sku')), '商品标题': nn(r.get('title')),
                 '商品尺寸': nn(r.get('dimension')), '五点描述': nn(b), '五点来源': bsrc, '五点来源ASIN': basin, '商品价格': nn(r.get('price')),
                 '主图链接': img, '商品链接': f'https://www.amazon.com/dp/{a}', '关联原始记录ID': f"{r['_file']}#items[{r['_i']}]",
                 '_eligible': True, '_outside_input_scope': False})
    meta.append({'五点来源说明': bhow, '详细参数来源月份': str(ATTR[a]['month']) if a in ATTR else None})
ALL = set(x.asin)
inputs = [{'asin': a, 'month': str(r['month']), 'attributes': r['attributes'], 'features': None, 'sourceFile': r.get('sourceFile'), 'sourceRow': r.get('sourceRow')}
          for a, r in ATTR.items() if a in ALL]
json.dump({'detailRows': rows}, open(f'{DR}/sales_payload.json', 'w', encoding='utf-8'), ensure_ascii=False)
json.dump({}, open(f'{DR}/collected_details.json', 'w'))
json.dump({'confirmedNonTargetProducts': NONTARGET}, open(f'{DR}/step1_macro_audit.json', 'w', encoding='utf-8'), ensure_ascii=False)
json.dump([], open(f'{DR}/feature_field_provenance.json', 'w'))
json.dump(inputs, open(f'{DR}/input_rows.json', 'w', encoding='utf-8'), ensure_ascii=False)
run('selftest.py')
print(run('tag_cached.py', '--data-root', DR, '--out-dir', TD)[-600:])
M = json.load(open(f'{TD}/tagging_matrix.json', encoding='utf-8'))['matrix']
assert len(M) == len(rows)
os.replace(f'{TD}/tagging_evidence.json', f'{OUT}/打标证据.tags.json')

# ---------- 4. 形态两层 ----------
# 不带门的开放层板 / 开放储物格；open-back、push-to-open、open the door 不算
OPEN_RE = re.compile(r'\bopen(?:[ -]+(?:storage|display|side|bottom|lower|middle|upper|top|left|right|tier))*[ -]+(?:shel(?:f|ves|ving)|storage|cubb(?:y|ies)|compartments?)\b'
                     r'|\bconsole\s+(?:vanity|sink|table)\b', re.I)
NEG_RE = re.compile(r'\b(?:no|not|without)\s+(?:an?\s+|any\s+)?$', re.I)

def open_cue(text):
    t = html.unescape(str(text or ''))
    for mm in OPEN_RE.finditer(t):
        if not NEG_RE.search(t[max(0, mm.start() - 20):mm.start()]): return True
    return False

STRUCT, STRUCT_SRC = [], []
for row in rows:
    srcs = [('标题', row['商品标题']), ('SKU', row['SKU属性']),
            ('子体五点' if row['五点来源'] == '子体详情' else '父体五点', row['五点描述']),
            ('详细参数', ATTR[row['子ASIN']]['attributes'] if row['子ASIN'] in ATTR else None)]
    hit = next((s for s, t in srcs if t and open_cue(t)), None)
    STRUCT.append('开放式' if hit else '待图片核验'); STRUCT_SRC.append(hit)

# ---------- 5. 分析用表 ----------
NESTED = {'badge', 'subcategories'}
A = pd.DataFrame([{k: v for k, v in r.items() if k not in NESTED and not k.startswith('_')} for r in items])
A.insert(0, '月份', [r['_m'][:4] + '-' + r['_m'][4:] for r in items])
for b in ('bestSeller', 'amazonChoice', 'newRelease', 'ebc', 'video'): A['badge.' + b] = [(r.get('badge') or {}).get(b) for r in items]
A['小类BSR'] = [next((s.get('rank') for s in (r.get('subcategories') or []) if str(s.get('code')) == VANITY), None) for r in items]
A['上架日期'] = pd.to_datetime(A['availableDate'], unit='ms', errors='coerce').dt.strftime('%Y-%m-%d')
A['家族键'] = FAM; A['家族键来源'] = FAM_HOW
A['家族导出子体数'] = A.groupby(['月份', '家族键']).asin.transform('size')
A['家族月销'] = A.groupby(['月份', '家族键']).units.transform('max')
A['子体月销（家族均分）'] = A['家族月销'] / A['家族导出子体数']
for j, h in enumerate(HEADERS): A[h] = [r[j] for r in M]
A['形态（怎么装）'] = A['D1产品形态'].replace({'开放式': '落地式'})
A['柜体结构'] = STRUCT; A['柜体结构来源'] = STRUCT_SRC
A['五点来源'] = [r['五点来源'] for r in rows]; A['五点来源说明'] = [m['五点来源说明'] for m in meta]
A['详细参数来源月份'] = [m['详细参数来源月份'] for m in meta]
A['主图500'] = [r['主图链接'] for r in rows]; A['商品链接'] = [r['商品链接'] for r in rows]

def suspect(t):
    t = html.unescape(str(t or '')); s = lambda p: re.search(p, t, re.I)
    if s(r'\b(?:medicine|mirror(?:ed)?)\s+cabinet\b') and not s(r'\bvanit(?:y|ies)\b'): return '独立镜柜/药柜'
    if s(r'\bmakeup\b|\bvanity\s+(?:desk|table)\b|\bdressing\s+table\b') and not s(r'\b(?:sinks?|basins?)\b'): return '化妆台'
    if s(r'\b(?:vanity|counter)\s*tops?\b') and s(r'\b(?:sinks?|basins?)\b') and not s(r'\b(?:cabinet|base|combo|storage|drawers?|doors?|vanit(?:y|ies)\s+(?:with|set))\b'): return '独立盆台（无柜）'
    if s(r'\bover[ -]the[ -]toilet\b|\blinen\s+(?:cabinet|tower)\b|\btall\s+(?:bathroom\s+)?(?:storage\s+)?cabinet\b|\bside\s+cabinet\b|\bstorage\s+tower\b|\bwall\s+cabinet\b') \
            and not s(r'\b(?:sinks?|basins?|vanit(?:y|ies)|pedestal)\b'): return '独立储物柜'
    if s(r'\b(?:vessel|bathroom|undermount)\s+sinks?\b|\bfaucets?\b') and not s(r'\b(?:vanit(?:y|ies)|cabinet|stand|console|pedestal|base)\b'): return '独立盆/龙头'
    return None
A['疑似非浴室柜'] = A['title'].map(suspect)
A['纳入浴室柜分析'] = A['打标状态'] != '不纳入浴室柜分析'
A.to_pickle(f'{OUT}/卖家精灵导出_打标_分析用.pkl')
A.to_excel(f'{OUT}/卖家精灵导出_打标_分析用.xlsx', index=False, sheet_name='子体明细')

# ---------- 6. 与 2026 年标签比（同一子体，各取最近月份） ----------
q = pd.read_pickle(f'{P15}/BathroomVanities_202601-202605_分析用.pkl'); q['月'] = q['目标月份'].str.replace('-', '')
t26 = pd.concat([q[['子ASIN', '月', '打标状态'] + HEADERS[:14]], V[['子ASIN', '月', '打标状态'] + HEADERS[:14]]], ignore_index=True)
t26 = latest(t26[t26['打标状态'].isin(TAGGED_STATES)].sort_values('月', kind='stable'), '子ASIN')
T = A[A['纳入浴室柜分析']]
new = latest(T.sort_values('月份', kind='stable'), 'asin')
both = new.index.intersection(t26.index)

def same(h, a, b):
    if h.startswith('D9'):
        try: return abs(float(a) - float(b)) <= 0.5
        except (TypeError, ValueError): return False
    return str(a) == str(b)

def isopen(v): return v is None or (isinstance(v, float) and np.isnan(v)) or v in OPEN or str(v) in ('nan', 'None', '')
agree = {}
for h in HEADERS[:14]:
    a, b = new.loc[both, h], t26.loc[both, h]
    ok = [(not isopen(u)) and (not isopen(w)) for u, w in zip(a, b)]
    agree[h] = (sum(not isopen(u) for u in a), sum(ok), sum(o and same(h, u, w) for o, u, w in zip(ok, a, b)))

# ---------- 7. 待核验清单 ----------
fam_m = T.groupby(['月份', '家族键'])['家族月销'].first()
fam_max = fam_m.groupby(level=1).max()
child_total = T.groupby('asin')['子体月销（家族均分）'].sum(); GRAND = child_total.sum()
last = latest(T.sort_values('月份', kind='stable'), 'asin')
last['家族最高父体月销'] = last['家族键'].map(fam_max)
last['子体累计销量（家族均分）'] = child_total
COLS = ['家族键', 'brand', 'title', 'sku', 'price', '月份', '家族最高父体月销', '子体累计销量（家族均分）', '主图500', '商品链接']

def sheet(mask, extra=()):
    s = last[mask].sort_values(['家族最高父体月销', '家族键', '子体累计销量（家族均分）'], ascending=[False, True, False])
    s = s[COLS + list(extra)].rename(columns={'月份': '最近月份'})
    s.insert(len(COLS), '累计销量覆盖', (s['子体累计销量（家族均分）'].cumsum() / GRAND).round(4))
    return s.reset_index().rename(columns={'asin': '子ASIN'})
Q = {'冲突': sheet(last['打标状态'] == '存在冲突待核验', ['打标说明']),
     '疑似非浴室柜': sheet(last['疑似非浴室柜'].notna(), ['疑似非浴室柜']),
     '台面材质信息不足': sheet(last['D8台面材质'] == '信息不足', ['D3盆数', 'D8台盆材质', '五点来源说明']),
     '柜体结构待看图': sheet(last['柜体结构'] == '待图片核验', ['形态（怎么装）']),
     '元素待看图': sheet(last['D5元素'] == '待图片核验', ['形态（怎么装）', '柜体结构'])}
with pd.ExcelWriter(f'{OUT}/待核验清单.xlsx') as w:
    for name, s in Q.items(): s.to_excel(w, sheet_name=name, index=False)

# ---------- 报告（只写汇总） ----------
def pct(v): return f'{v:.0%}'
L = [f'# 卖家精灵导出打标结果（{MONTHS[0][:4]}-{MONTHS[0][4:]} 至 {MONTHS[-1][:4]}-{MONTHS[-1][4:]}，打标技能 v12.1）', '',
     '> 由 `卖家精灵导出_打标.py` 生成。全部行用技能 v12.1 新打，不沿用以前的标签。导出没有五点和详细参数，从 2026 年已有材料按同子体、同家族接上，'
     '是当前快照，不是当月历史；产品属性基本不随月份变。', '',
     '## 1. 范围与文字来源', '', '| 月份 | 子体行 | 家族（修正前 → 后） | 有子体五点 | 只有父体五点 | 只有标题/SKU/尺寸 | 有详细参数 | 不纳入 |',
     '| :--- | ---: | :--- | ---: | ---: | ---: | ---: | ---: |']
for m in MONTHS:
    s = A[A['月份'] == m[:4] + '-' + m[4:]]; xs = x[x.m == m]
    L.append(f"| {m[:4]}-{m[4:]} | {len(s):,} | {xs.parent.nunique()} → {xs.fam.nunique()} | {pct((s['五点来源'] == '子体详情').mean())} | "
             f"{pct((s['五点来源'] == '父体详情填充').mean())} | {pct(s['五点来源'].isna().mean())} | {pct(s['详细参数来源月份'].notna().mean())} | {int((~s['纳入浴室柜分析']).sum())} |")
u = T.drop_duplicates('asin'); hc = Counter(FAM_HOW)
L += ['', f"- 共 {len(A):,} 行、{A.asin.nunique():,} 个子体；纳入打标 {len(T):,} 行、{T.asin.nunique():,} 个子体；没接上五点的子体 {int(u['五点来源'].isna().sum()):,} 个。",
      f"- 家族键：父体字段是别的 ASIN 的 {hc['父体字段']:,} 行；父体字段等于子体自己的行里，单体链接（变体数 ≤ 1）{hc['单体链接']:,}，其余 {sum(v for k, v in hc.items() if k not in ('父体字段', '单体链接')):,} 行是卖家精灵当月没认出父体，"
      f"其中被同月其他行当父体（就是那个家族）{hc['被同月其他行当父体']:,}、用其他月份的父体补 {hc['其他月份的父体']:,}、同月同品牌同月销的家族补 {hc['同月同品牌同月销的家族']:,}、这类行之间合并 {hc['同月同品牌同月销的无父体行合并']:,}、没补 {hc['未补（按单体算）']:,}。", '',
      '## 2. 各字段有值的比例（纳入打标的子体 × 月）', '', '| 字段 | 全部 | 有五点 | 只有标题/SKU/尺寸 |', '| :--- | ---: | ---: | ---: |']
hasb = T['五点来源'].notna()
def filled(s, h): return pct((~s[h].isin(OPEN) & s[h].notna()).mean()) if len(s) else '—'
for h in HEADERS[:14]: L.append(f'| {h} | {filled(T, h)} | {filled(T[hasb], h)} | {filled(T[~hasb], h)} |')
L += ['', '默认值（落地式、拆装、单盆、台下盆、无镜、无龙头）都算有值；元素没有文字线索的记"待图片核验"。', '',
      f'## 3. 与 2026 年标签比（同一子体 {len(both):,} 个，各取最近一个月）', '',
      '2026 年标签是 1–5 月 v12、6–9 月 v11（用到当时的子体详情）；这里新打用的是导出标题/SKU/尺寸加接上的五点。宽深高差 ≤ 0.5 寸算一致，信息不足、待图片核验不算。', '',
      '| 字段 | 新打有值 | 两边都有值 | 一致 | 一致率 |', '| :--- | ---: | ---: | ---: | ---: |']
for h, (has, b2, sm) in agree.items(): L.append(f"| {h} | {has:,} | {b2:,} | {sm:,} | {'—' if not b2 else pct(sm / b2)} |")
# D7 的证据来自"比 MDF / 刨花板更耐用"这类对比句的行：技能 D7 规则没排除对比句，会把被比较的材料当成柜体材质
CMP = re.compile(r'\b(?:than|unlike|instead of|compared (?:to|with)|versus|vs\.?)\s+(?:\w+\s+){0,3}?(?:mdf|particle\s*board|plywood|chipboard|engineered wood)', re.I)
ev = json.load(open(f'{OUT}/打标证据.tags.json', encoding='utf-8'))['rows']
cmp = [(r['childASIN'], r['verifiedParentASIN']) for r in ev if r['includeInBathroomAnalysis'] and any(CMP.search(e['quote']) for e in (r['fields'].get('D7柜体材质') or {}).get('selected', []))]
L += ['', f"D7 一致率偏低：多数是组合粒度不同（如 MDF 对 MDF+胶合板）；另有 {len(cmp):,} 行（{len({a for a, _ in cmp}):,} 个子体、{len({p for _, p in cmp}):,} 个家族）的柜体材质证据来自\"比 MDF / 刨花板更耐用\"这类对比句，"
      '被当成了材质（如 ARIEL 标成 MDF+胶合板+刨花板，2026 年标签是实木），属技能 D7 规则漏洞，要修技能后重打。']
ct = pd.crosstab(T['形态（怎么装）'], T['柜体结构'])
L += ['', '## 4. 形态两层', '', '| 形态（怎么装） | 开放式 | 待图片核验 | 开放式占比 |', '| :--- | ---: | ---: | ---: |']
for f_, r in ct.iterrows(): L.append(f"| {f_} | {int(r.get('开放式', 0)):,} | {int(r.get('待图片核验', 0)):,} | {pct(r.get('开放式', 0) / r.sum())} |")
sc = Counter(T['柜体结构来源'].dropna())
L += ['', f"开放式按文字来源：{'、'.join(f'{k} {v:,}' for k, v in sc.most_common())}（行）。技能的\"开放式\"（console）已归落地式。", '',
      '## 5. 待核验清单（待核验清单.xlsx，按唯一子体，取最近一个月）', '',
      '每页按家族最高父体月销从高到低排；"累计销量覆盖"= 看到这一行时，已覆盖全部子体累计销量（家族月销按导出子体均分）的比例。', '',
      '| 页 | 子体数 | 家族数 | 销量占比 |', '| :--- | ---: | ---: | ---: |']
for name, s in Q.items(): L.append(f"| {name} | {len(s):,} | {s['家族键'].nunique():,} | {pct(s['子体累计销量（家族均分）'].sum() / GRAND)} |")
ctype = Counter()
for note in Q['冲突']['打标说明']:
    ctype.update({h for part in str(note).split('；') if any(w in part for w in ('不一致', '待核验', '冲突')) for h in HEADERS[:14] if part.startswith(h)})
L += ['', '冲突页按字段（子体数，一个子体可有多项）：' + '、'.join(f'{k} {v:,}' for k, v in ctype.most_common()) + '。',
      f"疑似非浴室柜（只标出、未剔除）：{'、'.join(f'{k} {v}' for k, v in Q['疑似非浴室柜']['疑似非浴室柜'].value_counts().items())}（子体）。"]
L += ['', f'## 6. 输出（不入库，在 {os.path.relpath(OUT, ROOT)}/）', '',
      '- 分析用表：卖家精灵导出_打标_分析用.pkl / .xlsx（导出标量字段原名、小类BSR、上架日期、家族键、子体月销（家族均分）、16 列标签、形态（怎么装）、柜体结构、五点来源）。',
      '- 逐字段证据：打标证据.tags.json；待核验清单：待核验清单.xlsx。', '']
open(REPORT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
