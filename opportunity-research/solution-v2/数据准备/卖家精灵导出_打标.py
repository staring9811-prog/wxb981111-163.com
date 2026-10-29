"""给卖家精灵按月数据统一打标（每行 = 月 × 子体），规则全部用打标技能（现为 v12.1），不沿用以前的标签（wen 2026-10-29）。
来源三批（2026 年这一版用已给的数据，不重导）：
  - 卖家精灵 MCP 按月导出：input/data_v2/sellersprite_zip_*/（2024-10 至 2025-12，父体月销 ≥ 50、价格 ≥ 90）；
  - 2026 月度表：input/data_v2/202601-202605_打标/（2026-01 至 05，wen 的卖家精灵网页导出整理；文字在 _work/data_root/，销量等在分析用表）；
  - 2026 v11 表：input/data_v2/BathroomVanities_202606-202609_SKU销量预估_已打标_v11.xlsx（2026-06 至 09）。
1. 家族键：父体字段等于子体自己、但变体数 > 1 的行（卖家精灵当月没认出父体）补"家族键"：同月有别的行把它当父体 → 其他月份的父体 →
   同月同品牌同月销的唯一家族 → 同月同品牌同月销的这类行合并；原父体字段不改。三批一起算。
2. 文字：每行自己的标题、SKU、商品尺寸；五点按同子体自己的（子体详情）→ 同子体的父体五点 → 同家族的，从 2026 年两批材料里取
   （当前快照，不是当月历史），同一子体各月用同一份；详细参数只用同子体的，取 1–5 月表里最近一条。
3. 非浴室柜剔除（wen 2026-10-29 确认）：非浴室柜_wen确认_20261029.json 里的 87 个子体整条剔除；其余每行按自己的标题判
   （独立盆台、化妆台、镜柜/药柜、储物柜、单独的盆/龙头；v12.2 审计补镜子、厨房柜、挡水板等台面配件、儿童免接水管洗手台），
   命中就不纳入。标题主体（第一个逗号前）是"…Vanity"、后面不接 top / sink 等词的，不判独立盆台（UEV B0DT95PHVR 曾被误判）。
   2026 年已有的非目标名单照旧。
4. 用技能原脚本 tag_cached.py 打标（柱状盆、默认值、尺寸、实木价格复核等全部现行规则）；换技能版本只改 TAGGER。
5. 形态分两层（wen 2026-10-29："开放式属于站立式"）：形态（怎么装）= 技能 D1（落地 / 悬浮 / 柱状盆 / 转角 / 两用），技能的"开放式"
   （console）归落地式；柜体结构 = 开放式（文字写了不带门的开放层板：open shelf / open storage / open cubes / side shelves /
   two-tier shelf / console 等）或待图片核验；镜柜上的层板、放水管的柜内层板、门背置物架不算；父体五点只在子体标题/SKU 也提到
   层板时采信（v12.2 审计）。
6. 统一分析用表（共同列 + 口径标记"家族月销≥60""价格≥90"）；核对两批来源在 2025-12 → 2026-01 接不接得上；与 2026 年旧标签对同一子体
   比一致率；出证据、待核验清单和汇总报告。
环境变量：TAGGER（技能目录，含 scripts/）、EXPORTS（MCP 导出 JSON 的 glob）、OUT_DIR（默认 input/data_v2/统一打标，不入库）、REPORT_MD。
用法：TAGGER=<技能目录> python3 -I 卖家精灵导出_打标.py"""
import os, re, json, glob, html, subprocess, sys, numpy as np, pandas as pd
from collections import Counter
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
D2 = os.path.join(ROOT, 'input/data_v2')
TAGGER = os.environ['TAGGER']
FILES = sorted(glob.glob(os.environ.get('EXPORTS', f'{D2}/sellersprite_zip_*/*_full_data.json')))
OUT = os.environ.get('OUT_DIR', f'{D2}/统一打标')
REPORT = os.environ.get('REPORT_MD', os.path.join(HERE, '卖家精灵导出_打标结果.md'))
P15 = f'{D2}/202601-202605_打标'
V11 = f'{D2}/BathroomVanities_202606-202609_SKU销量预估_已打标_v11.xlsx'
CONF = json.load(open(os.path.join(HERE, '非浴室柜_wen确认_20261029.json'), encoding='utf-8'))  # 子体 → 类别
VANITY = '6810202011'
MCP, M15, M69 = '卖家精灵MCP', '2026 月度表', '2026 v11 表'
HEADERS = ['D1产品形态', 'D2安装方式', 'D3盆数', 'D4台面形态', 'D5元素', 'D6柜体颜色', 'D7柜体材质', 'D8台面材质', 'D8台盆材质',
           'D9宽(in)', 'D9深(in)', 'D9高(in)', 'D10镜子', 'D11龙头', '打标状态', '打标说明']
TAGGED_STATES = ('文本证据可用', '部分信息不足', '存在冲突待核验')
OPEN = (None, '信息不足', '待图片核验')
WORK = os.path.join(OUT, '_work'); DR = os.path.join(WORK, 'data_root'); TD = os.path.join(WORK, 'tag')
for d in (OUT, DR, TD): os.makedirs(d, exist_ok=True)

def nn(v):  # JSON 不接受 NaN
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else v

def num(v):
    try: v = float(v)
    except (TypeError, ValueError): return None
    return None if np.isnan(v) else v

def day(v):  # 毫秒时间戳或日期文本 → YYYY-MM-DD
    if isinstance(v, (int, float, np.integer, np.floating)):
        return pd.Timestamp(int(v), unit='ms').strftime('%Y-%m-%d') if v == v and v > 0 else None
    t = pd.to_datetime(v, errors='coerce'); return None if pd.isna(t) else t.strftime('%Y-%m-%d')

def run(script, *args):
    r = subprocess.run([sys.executable, '-I', os.path.join(TAGGER, 'scripts', script), *map(str, args)], capture_output=True, text=True)
    if r.returncode != 0: raise SystemExit(f'{script} 失败：{r.stdout[-800:]}{r.stderr[-800:]}')
    return r.stdout

# ---------- 读三批数据，统一成原始行 ----------
R, src = [], {}
for f in FILES:
    j = json.load(open(f, encoding='utf-8')); m = j['month']
    if m in src: raise SystemExit(f'{m} 有两份导出：{src[m]} 与 {f}')
    if not j.get('complete'): raise SystemExit(f'{f} 没有标记完整')
    src[m] = f
    for i, r in enumerate(j['items']):
        R.append({'m': m, 'asin': r['asin'], 'parent': r.get('parent') or r['asin'], 'brand': r.get('brand') or None, 'title': nn(r.get('title')),
                  'sku': nn(r.get('sku')), 'dim': nn(r.get('dimension')), 'price': num(r.get('price')), 'units': num(r.get('units')),
                  'var': r.get('variations') or 0, 'sub': next((s.get('rank') for s in (r.get('subcategories') or []) if str(s.get('code')) == VANITY), None),
                  'rating': num(r.get('rating')), 'ratings': num(r.get('ratings')), 'up': day(r.get('availableDate')), 'est26': None,
                  'ship': r.get('fulfillment'), 'img': r.get('imageUrl'), 'batch': MCP, 'rec': f"{os.path.basename(f)}#items[{i}]",
                  'eligible': True, 'outside': False, '月新增评分数（MCP）': r.get('ratingsCv'), '上月购买标（MCP）': r.get('amzUnit'),
                  '卖家数（MCP）': r.get('sellers'), '卖家所属地（MCP）': r.get('sellerNation'), '大类BSR（MCP）': r.get('bsr')})

pay = json.load(open(f'{P15}/_work/data_root/sales_payload.json', encoding='utf-8'))['detailRows']
q = pd.read_pickle(f'{P15}/BathroomVanities_202601-202605_分析用.pkl')
if len(pay) != len(q) or any(p['子ASIN'] != a for p, a in zip(pay, q['子ASIN'])): raise SystemExit('1–5 月文字与分析用表逐行对不上')
for p, r in zip(pay, q.to_dict('records')):
    R.append({'m': str(p['目标月份']), 'asin': p['子ASIN'], 'parent': p.get('核验父ASIN') or p['子ASIN'], 'brand': nn(r['品牌']), 'title': nn(p.get('商品标题')),
              'sku': nn(p.get('SKU属性')), 'dim': nn(p.get('商品尺寸')), 'price': num(r['商品价格']), 'units': num(r['父体月销量']), 'var': num(r['变体数']) or 0,
              'sub': num(r['小类BSR']), 'rating': num(r['评分']), 'ratings': num(r['评分数']), 'up': day(r['上架日期']),
              'est26': num(r['子体月销量（父体全分给导出子体）']), 'ship': nn(r['配送方式']), 'img': nn(p.get('主图链接')), 'batch': M15,
              'rec': p.get('关联原始记录ID'), 'eligible': bool(p.get('_eligible')), 'outside': bool(p.get('_outside_input_scope'))})

V = pd.read_excel(V11, sheet_name='SKU估算明细', dtype=str); V['月'] = V['目标月份'].str[:6]
for i, r in enumerate(V.to_dict('records')):
    st, note = r['打标状态'], str(r['打标说明'])
    outside = st == '不纳入浴室柜分析' and note.startswith('保留原始记录')  # v11 输入范围外；"目标月归属待核验"仍不打标
    R.append({'m': r['月'], 'asin': r['子ASIN'], 'parent': nn(r['核验父ASIN']) or r['子ASIN'], 'brand': nn(r['品牌']), 'title': nn(r['商品标题']),
              'sku': nn(r['SKU属性']), 'dim': nn(r['商品尺寸']), 'price': num(r['商品价格']), 'units': num(r['父体月销量预测']),
              'var': num(r['父体实际返回子体数']) or 0, 'sub': num(r['目标月校验小类BSR']), 'rating': num(r['商品评分']), 'ratings': num(r['评分数量']),
              'up': day(r['上架日期']), 'est26': num(r['最终SKU月销量估算']), 'ship': nn(r['配送方式']), 'img': nn(r['主图链接']), 'batch': M69,
              'rec': nn(r['关联原始记录ID']) or f'v11#R{i + 2}', 'eligible': st != '目标月归属待核验' and not outside, 'outside': outside})

MONTHS = sorted({r['m'] for r in R})
dup = [k for k, v in Counter((r['m'], r['asin']) for r in R).items() if v > 1]
if dup: raise SystemExit(f'同月同子体重复 {len(dup)} 处，如 {dup[:3]}')
print('月份', MONTHS, '行', len(R), dict(Counter(r['batch'] for r in R)))

# ---------- 1. 家族键 ----------
x = pd.DataFrame({'m': [r['m'] for r in R], 'asin': [r['asin'] for r in R], 'parent': [r['parent'] for r in R],
                  'brand': [r['brand'] for r in R], 'units': [r['units'] for r in R], 'var': [r['var'] for r in R]})
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

# ---------- 2. 非浴室柜（每行按自己的标题判） ----------
def suspect(t):
    t = html.unescape(str(t or '')); s = lambda p: re.search(p, t, re.I)
    head = re.split(r'[,，|]', t, maxsplit=1)[0]
    # 标题主体是"…Bathroom Vanity"（vanity 后面不接 top / sink 等），是带柜子的浴室柜
    vanity_head = re.search(r'\bvanit(?:y|ies)\b(?!\s+(?:sink|vessel|counter)?\s*(?:tops?|countertops?|sinks?|bowls?|basins?)\b)', head, re.I)
    if s(r'\bportable\s+sink\b|\bwash\s+station\b'): return '独立盆/龙头'  # 移动洗手台，标题也会写 Bathroom Vanity Sink
    if s(r'\b(?:medicine|mirror(?:ed)?)\s+cabinet\b') and not s(r'\bvanit(?:y|ies)\b'): return '独立镜柜/药柜'
    if s(r'\bmakeup\b|\bvanity\s+(?:desk|table)\b|\bdressing\s+table\b') and not s(r'\b(?:sinks?|basins?)\b'): return '化妆台'
    if s(r'\b(?:vanity|counter)\s*tops?\b') and s(r'\b(?:sinks?|basins?)\b') and not vanity_head \
            and not s(r'\b(?:cabinet|base|combo|storage|drawers?|doors?)\b'): return '独立盆台（无柜）'
    if s(r'\bover[ -]the[ -]toilet\b|\blinen\s+(?:cabinet|tower)\b|\btall\s+(?:bathroom\s+)?(?:storage\s+)?cabinet\b|\bside\s+cabinet\b|\bstorage\s+tower\b|\bwall\s+cabinet\b') \
            and not s(r'\b(?:sinks?|basins?|vanit(?:y|ies)|pedestal)\b'): return '独立储物柜'
    if s(r'\b(?:vessel|bathroom|undermount)\s+sinks?\b|\bfaucets?\b') and not s(r'\b(?:vanit(?:y|ies)|cabinet|stand|console|pedestal|base)\b'): return '独立盆/龙头'
    return more_suspect(t, s)

# v12.2 审计（2026-10-29）补的几类：标题里 vanity 只当 sink / top 的修饰词时不算柜子；镜子、厨房柜、挡水板、
# 不写 sink 的台面、高柜、尺寸很小的单盆单龙头、儿童免接水管洗手台（wen：不是浴室柜的剔除）
VANITY_FURN = r'\bvanit(?:y|ies)\b(?!\s*(?:sinks?|tops?|basins?|bowls?|vessel|mirrors?|lights?|space|side\s+cabinet|desk|table|stool|bench|chair)\b)'
CAB_WORDS = r'\b(?:cabinets?|storage|drawers?|doors?|shel(?:f|ves)|console|stand|legs?|pedestal|combo|base)\b'

def more_suspect(t, s):
    furn = s(VANITY_FURN)
    if s(r'\b(?:kids?|children|toddlers?|montessori)\b') and s(r'\bsinks?\b') and s(r'\bportable\b|\bno plumbing\b'): return '儿童洗手台'
    if s(r'\banti[ -]?fog\b|\bdefog\w*\b|\b(?:led|lighted)\s+(?:bathroom\s+)?mirrors?\b') and not furn and not s(r'\b(?:sinks?|basins?|cabinets?)\b'): return '镜子'
    if s(r'\bkitchen\s+(?:base\s+|wall\s+|sink\s+base\s+|blind\s+base\s+)?cabinets?\b|\b(?:base|wall|blind\s+base)\s+kitchen\s+cabinets?\b') and not furn and not s(r'\bbathroom\b'): return '厨房柜'
    if s(r'\b(?:back|side)splash\b') and not furn and not s(r'\b(?:sinks?|basins?|cabinets?)\b'): return '台面配件'
    if s(r'\b(?:vanity|counter)\s*tops?\b|\bcountertops?\b') and not furn and not s(CAB_WORDS): return '独立盆台（无柜）'
    if s(r'\btall\s+(?:\w+\s+)?cabinet\b') and not furn and not s(r'\b(?:sinks?|basins?)\b'): return '独立储物柜'
    return None
SUS = [CONF.get(r['asin']) or suspect(r['title']) for r in R]
for r, c in zip(R, SUS):
    if c and r['asin'] not in CONF: r['eligible'], r['outside'] = False, True  # 规则命中：按这一行剔除

# ---------- 3. 文字来源 ----------
pa = pd.DataFrame([{'子ASIN': r['子ASIN'], '核验父ASIN': r.get('核验父ASIN'), '五点': r.get('五点描述'), '来源': r.get('五点来源'),
                    '来源ASIN': r.get('五点来源ASIN'), '月': str(r['目标月份'])} for r in pay])
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
NONTARGET = {**nt.groupby('子ASIN')['打标说明'].first().to_dict(), **audit,
             **{a: f'非浴室柜（wen 2026-10-29 确认）：{c}' for a, c in CONF.items()}}

# ---------- 4. 规范化输入并打标 ----------
rows, meta = [], []
for k, r in enumerate(R):
    a = r['asin']; fam, how = FAM[k], FAM_HOW[k]; p = fam if how in REAL_PARENT else a
    b, bsrc, basin, bhow = bullets(a, p)
    img = r['img']; img = re.sub(r'\._[^/]*_\.jpg$', '._AC_SL500_.jpg', img) if img else None
    rows.append({'子ASIN': a, '目标月份': r['m'], '站点': 'US', '核验父ASIN': p, 'SKU属性': r['sku'], '商品标题': r['title'],
                 '商品尺寸': r['dim'], '五点描述': nn(b), '五点来源': bsrc, '五点来源ASIN': basin, '商品价格': r['price'],
                 '主图链接': img, '商品链接': f'https://www.amazon.com/dp/{a}', '关联原始记录ID': r['rec'],
                 '_eligible': r['eligible'], '_outside_input_scope': r['outside']})
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
VERSION = json.load(open(f'{TD}/tagging_summary.json', encoding='utf-8'))['ruleVersion']

# ---------- 5. 形态两层 ----------
# 不带门的开放层板 / 开放储物格；open-back、push-to-open、open the door、open space under the vanity 不算
OPEN_RE = re.compile(r'\bopen(?:[ -]+(?:storage|display|side|bottom|lower|middle|upper|top|left|right|tier))*[ -]+(?:shel(?:f|ves|ving)|storage|cubb(?:y|ies)|cubes?|compartments?|spaces)\b'
                     r'|\bopening\s+(?:bottom\s+|lower\s+|side\s+)?shel(?:f|ves)\b'
                     r'|\bside\s+(?:open\s+)?(?:storage\s+)?shel(?:f|ves)\b'
                     r'|\b(?:2|3|two|three)[ -]tier(?:ed)?\s+(?:open\s+)?(?:side\s+)?(?:storage\s+)?shel(?:f|ves)\b'
                     r'|\bconsole\s+(?:vanity|sink|table)\b', re.I)
NEG_RE = re.compile(r'\b(?:no|not|without)\s+(?:an?\s+|any\s+)?$', re.I)
# v12.2 审计：层板属于镜柜/药柜、或是柜内放水管的层板、或是门背置物架，都不是柜体开放层板
MIRROR_BEFORE = re.compile(r'\b(?:mirror|medicine)\s+cabinet\b[^.|]{0,40}$', re.I)
PIPES_AFTER = re.compile(r'^[^.|]{0,20}\b(?:accommodat\w*|fits?|for|around|hid(?:es?|ing))\s+(?:the\s+)?(?:pipes?|plumbing)\b', re.I)
DOOR_RACK_BEFORE = re.compile(r'\bdoors?\s+(?:features?|has|have|with|includes?)\s+(?:an?\s+)?$', re.I)
DOOR_RACK_AFTER = re.compile(r'^\s*(?:on|inside|behind|in)\b', re.I)
# 父体五点可能写的是别的变体：子体标题/SKU 自己也提到层板/开放/侧边储物时才采信
CHILD_STORAGE_CUE = re.compile(r'\bshel(?:f|ves)\b|\bopen\b|\bracks?\b|\btier\b|\bcub(?:e|es|by|bies)\b|\bside\s+storage\b', re.I)

def open_cue(text):
    t = html.unescape(str(text or ''))
    for mm in OPEN_RE.finditer(t):
        before, after = t[max(0, mm.start() - 60):mm.start()], t[mm.end():mm.end() + 40]
        if NEG_RE.search(before[-20:]): continue
        if MIRROR_BEFORE.search(before) or PIPES_AFTER.search(after): continue
        # 门背/柜内的 tier 置物架（"doors features a three-tiered storage shelf"）不算；带 open 的照算
        if re.match(r'(?:2|3|two|three)[ -]tier', mm.group(0), re.I) and 'open' not in mm.group(0).lower() \
                and (DOOR_RACK_BEFORE.search(before) or DOOR_RACK_AFTER.search(after)): continue
        return True
    return False

def struct_of(title, sku, bullets, bullets_src, attrs):
    srcs = [('标题', title), ('SKU', sku), ('子体五点' if bullets_src == '子体详情' else '父体五点', bullets), ('详细参数', attrs)]
    child = html.unescape(f'{title or ""} {sku or ""}')
    for s, t in srcs:
        if not (t and open_cue(t)): continue
        if s == '父体五点' and not CHILD_STORAGE_CUE.search(child): continue
        return s
    return None

STRUCT_SRC = [struct_of(row['商品标题'], row['SKU属性'], row['五点描述'], row['五点来源'],
                        ATTR[row['子ASIN']]['attributes'] if row['子ASIN'] in ATTR else None) for row in rows]
STRUCT = ['开放式' if s else '待图片核验' for s in STRUCT_SRC]

# ---------- 6. 统一分析用表 ----------
A = pd.DataFrame({'月份': [r['m'][:4] + '-' + r['m'][4:] for r in R], '子ASIN': [r['asin'] for r in R], '家族键': FAM, '家族键来源': FAM_HOW,
                  '父体字段': [r['parent'] for r in R], '品牌': [r['brand'] for r in R], '标题': [r['title'] for r in R], 'SKU': [r['sku'] for r in R],
                  '尺寸文本': [r['dim'] for r in R], '价格': [r['price'] for r in R], '家族月销（行值）': [r['units'] for r in R],
                  '变体数': [r['var'] for r in R], '小类BSR': [r['sub'] for r in R], '评分': [r['rating'] for r in R], '评分数': [r['ratings'] for r in R],
                  '上架日期': [r['up'] for r in R], '子体月销（2026 原流程估算）': [r['est26'] for r in R], '配送方式': [r['ship'] for r in R],
                  '数据来源批次': [r['batch'] for r in R], '关联原始记录ID': [r['rec'] for r in R]})
A['小类BSR'] = pd.to_numeric(A['小类BSR'], errors='coerce')
A['家族导出子体数'] = A.groupby(['月份', '家族键'])['子ASIN'].transform('size')
A['家族月销'] = A.groupby(['月份', '家族键'])['家族月销（行值）'].transform('max')
A['子体月销（家族均分）'] = A['家族月销'] / A['家族导出子体数']
for j, h in enumerate(HEADERS): A[h] = [r[j] for r in M]
A['形态（怎么装）'] = A['D1产品形态'].replace({'开放式': '落地式'})
A['柜体结构'] = STRUCT; A['柜体结构来源'] = STRUCT_SRC
A['五点来源'] = [r['五点来源'] for r in rows]; A['五点来源说明'] = [m['五点来源说明'] for m in meta]
A['详细参数来源月份'] = [m['详细参数来源月份'] for m in meta]
A['主图500'] = [r['主图链接'] for r in rows]; A['商品链接'] = [r['商品链接'] for r in rows]
A['非浴室柜类别'] = SUS
cut = A['非浴室柜类别'].notna() & ~A['子ASIN'].isin(NONTARGET) & (A['打标状态'] == '不纳入浴室柜分析')  # 已在名单里的保留原说明
A.loc[cut, '打标说明'] = '非浴室柜（wen 2026-10-29：不是浴室柜的剔除）：标题判为' + A.loc[cut, '非浴室柜类别']
A['纳入浴室柜分析'] = ~A['打标状态'].isin(['不纳入浴室柜分析', '目标月归属待核验'])
A['家族月销≥60'] = A['家族月销'] >= 60; A['价格≥90'] = A['价格'] >= 90
for k in ('月新增评分数（MCP）', '上月购买标（MCP）', '卖家数（MCP）', '卖家所属地（MCP）', '大类BSR（MCP）'): A[k] = [r.get(k) for r in R]
A.to_pickle(f'{OUT}/统一打标_分析用.pkl')
with pd.ExcelWriter(f'{OUT}/统一打标_分析用.xlsx', engine='xlsxwriter', engine_kwargs={'options': {'strings_to_urls': False}}) as w:  # 链接超过单表 6.5 万上限会被丢
    A.to_excel(w, index=False, sheet_name='子体明细')
I = A[A['纳入浴室柜分析']]

# ---------- 7. 两批来源接不接得上：相邻两月都出现的家族 ----------
fam = I.groupby(['月份', '家族键'])['家族月销'].first()
kid = I.set_index(['月份', '子ASIN'])['家族键']
def link(a, b):
    sa, sb = fam.loc[a], fam.loc[b]
    k = pd.concat([kid.loc[a], kid.loc[b]], axis=1, keys=['a', 'b'], join='inner')
    j = pd.concat([sa, sb], axis=1, keys=['a', 'b'], join='inner').dropna(); j = j[(j.a > 0) & (j.b > 0)]
    return {'前月家族': len(sa), '后月家族': len(sb), '两月都有': len(j), '比值中位': (j.b / j.a).median(),
            '对数相关': np.corrcoef(np.log(j.a), np.log(j.b))[0, 1], '排名相关': j.a.rank().corr(j.b.rank()), '前月合计': sa.sum(), '后月合计': sb.sum(),
            '同子体家族键相同': (k.a == k.b).mean()}
have = set(I['月份'])
LINKS = [(a, b, n, link(a, b)) for a, b, n in [('2024-12', '2025-01', 'MCP 内部（同为 12 → 1 月）'), ('2025-11', '2025-12', 'MCP 内部'), ('2025-12', '2026-01', 'MCP → 2026 月度表'),
                                              ('2026-01', '2026-02', '月度表内部'), ('2026-05', '2026-06', '月度表 → v11 表'), ('2026-06', '2026-07', 'v11 表内部')]
         if a in have and b in have]

# ---------- 8. 与 2026 年旧标签比（同一子体，各取最近月份） ----------
q['月'] = q['目标月份'].str.replace('-', '')
t26 = pd.concat([q[['子ASIN', '月', '打标状态'] + HEADERS[:14]], V[['子ASIN', '月', '打标状态'] + HEADERS[:14]]], ignore_index=True)
t26 = latest(t26[t26['打标状态'].isin(TAGGED_STATES)].sort_values('月', kind='stable'), '子ASIN')
new = latest(I.sort_values('月份', kind='stable'), '子ASIN')
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

# ---------- 9. 待核验清单 ----------
fam_max = fam.groupby(level=1).max()
child_total = I.groupby('子ASIN')['子体月销（家族均分）'].sum(); GRAND = child_total.sum()
last = new.copy()
last['家族最高父体月销'] = last['家族键'].map(fam_max)
last['子体累计销量（家族均分）'] = child_total
COLS = ['家族键', '品牌', '标题', 'SKU', '价格', '月份', '数据来源批次', '家族最高父体月销', '子体累计销量（家族均分）', '主图500', '商品链接']

def sheet(mask, extra=()):
    s = last[mask].sort_values(['家族最高父体月销', '家族键', '子体累计销量（家族均分）'], ascending=[False, True, False])
    s = s[COLS + list(extra)].rename(columns={'月份': '最近月份'})
    s.insert(len(COLS), '累计销量覆盖', (s['子体累计销量（家族均分）'].cumsum() / GRAND).round(4))
    return s.reset_index()
Q = {'冲突': sheet(last['打标状态'] == '存在冲突待核验', ['打标说明']),
     '台面材质信息不足': sheet(last['D8台面材质'] == '信息不足', ['D3盆数', 'D8台盆材质', '五点来源说明']),
     '柜体结构待看图': sheet(last['柜体结构'] == '待图片核验', ['形态（怎么装）']),
     '元素待看图': sheet(last['D5元素'] == '待图片核验', ['形态（怎么装）', '柜体结构'])}
X = A[A['非浴室柜类别'].notna()]
NV = X.groupby('子ASIN').agg(类别=('非浴室柜类别', 'first'), 品牌=('品牌', 'first'), 标题=('标题', 'last'), 剔除行=('月份', 'size'),
                            月份=('月份', lambda s: '、'.join(sorted(s))), 来源批次=('数据来源批次', lambda s: '、'.join(sorted(set(s)))),
                            家族最高父体月销=('家族月销', 'max'))
NV['依据'] = np.where(NV.index.isin(CONF), 'wen 确认（87 个）', np.where(NV.index.isin(NONTARGET), '2026 非目标名单（规则也命中）', '规则命中（新）'))
NV['该子体其他月份仍纳入'] = NV.index.isin(I['子ASIN'])
NV = NV.sort_values(['依据', '家族最高父体月销'], ascending=[True, False])
with pd.ExcelWriter(f'{OUT}/待核验清单.xlsx') as w:
    for name, s in Q.items(): s.to_excel(w, sheet_name=name, index=False)
    NV.reset_index().to_excel(w, sheet_name='已剔除非浴室柜', index=False)

# ---------- 报告（只写汇总） ----------
def pct(v): return f'{v:.0%}'
def ym(m): return f'{m[:4]}-{m[4:]}'
L = [f'# 统一打标结果（{ym(MONTHS[0])} 至 {ym(MONTHS[-1])}，打标技能 {VERSION}）', '',
     '> 由 `卖家精灵导出_打标.py` 生成。三批来源全部用同一版技能新打，不沿用以前的标签：卖家精灵 MCP 按月导出（2024-10 至 2025-12）、'
     '2026 月度表（2026-01 至 05）、2026 v11 表（2026-06 至 09；wen：这一版就用已给的 2026 年数据）。五点和详细参数从 2026 年材料按同子体、同家族接上，'
     '是当前快照，不是当月历史；产品属性基本不随月份变。', '',
     '## 1. 范围与文字来源', '',
     '| 月份 | 来源 | 子体行 | 纳入分析的家族（修正前 → 后） | 有子体五点 | 只有父体五点 | 只有标题/SKU/尺寸 | 有详细参数 | 不纳入 | 归属待核验 |',
     '| :--- | :--- | ---: | :--- | ---: | ---: | ---: | ---: | ---: | ---: |']
for m in MONTHS:
    s = A[A['月份'] == ym(m)]; xs = x[(x.m == m).values & A['纳入浴室柜分析'].values]  # 家族数只数纳入分析的行
    L.append(f"| {ym(m)} | {s['数据来源批次'].iloc[0]} | {len(s):,} | {xs.parent.nunique()} → {xs.fam.nunique()} | {pct((s['五点来源'] == '子体详情').mean())} | "
             f"{pct((s['五点来源'] == '父体详情填充').mean())} | {pct(s['五点来源'].isna().mean())} | {pct(s['详细参数来源月份'].notna().mean())} | "
             f"{int((s['打标状态'] == '不纳入浴室柜分析').sum())} | {int((s['打标状态'] == '目标月归属待核验').sum())} |")
u = I.drop_duplicates('子ASIN'); hc = Counter(FAM_HOW); bc = A['数据来源批次'].value_counts()
L += ['', f"- 共 {len(A):,} 行、{A['子ASIN'].nunique():,} 个子体（{'、'.join(f'{k} {v:,} 行' for k, v in bc.items())}）；纳入分析 {len(I):,} 行、{I['子ASIN'].nunique():,} 个子体；"
          f"纳入的子体里没接上五点的 {int(u['五点来源'].isna().sum()):,} 个。",
      f"- 2026 v11 表里\"目标月归属待核验\"的 {int((A['打标状态'] == '目标月归属待核验').sum()):,} 行（当时就没核实目标月归属、没有父体）照旧不打标、不纳入。",
      f"- 家族键：父体字段是别的 ASIN 的 {hc['父体字段']:,} 行；父体字段等于子体自己的行里，单体链接（变体数 ≤ 1）{hc['单体链接']:,}，其余 {sum(v for k, v in hc.items() if k not in ('父体字段', '单体链接')):,} 行是当月没认出父体，"
      f"其中被同月其他行当父体（就是那个家族）{hc['被同月其他行当父体']:,}、用其他月份的父体补 {hc['其他月份的父体']:,}、同月同品牌同月销的家族补 {hc['同月同品牌同月销的家族']:,}、这类行之间合并 {hc['同月同品牌同月销的无父体行合并']:,}、没补 {hc['未补（按单体算）']:,}。", '',
      '## 2. 两批来源接不接得上', '',
      '相邻两月都出现的家族（纳入分析的行，家族月销按家族键取），比后月 ÷ 前月的家族月销：', '',
      '| 两个月 | 衔接 | 前月家族 | 后月家族 | 两月都有 | 比值中位 | 对数相关 | 排名相关 | 前月合计 | 后月合计 | 同子体家族键相同 |', '| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
for a, b, n, s in LINKS:
    L.append(f"| {a} → {b} | {n} | {s['前月家族']} | {s['后月家族']} | {s['两月都有']} | {s['比值中位']:.2f} | {s['对数相关']:.2f} | {s['排名相关']:.2f} | {s['前月合计']:,.0f} | {s['后月合计']:,.0f} | {pct(s['同子体家族键相同'])} |")
lk = {n: s for a, b, n, s in LINKS}
c, r0 = lk.get('MCP → 2026 月度表'), lk.get('MCP 内部（同为 12 → 1 月）')
if c:
    ok = abs(c['比值中位'] - 1) < 0.15 and c['对数相关'] >= 0.6
    L += ['', f"MCP → 2026 月度表：两月都有的家族 {c['两月都有']} 个，比值中位 {c['比值中位']:.2f}、对数相关 {c['对数相关']:.2f}"
          + (f"；MCP 自己的 2024-12 → 2025-01 是 {r0['两月都有']} 个、{r0['比值中位']:.2f}、{r0['对数相关']:.2f}" if r0 else '') + '。'
          + ('同一家族的销量量级接得上，没有整体抬高或压低；12 → 1 月能延续的家族只有一半左右，两年都这样，是季节性进出 50 件线，不是来源不同。' if ok
             else '两批来源的家族销量差得多，不能直接接，需另查。')]
v = lk.get('v11 表内部')
if v and v['同子体家族键相同'] < 0.8:
    L.append(f"注意：v11 表内部相邻两月，同一子体的家族键只有 {pct(v['同子体家族键相同'])} 相同（其他衔接 83–94%），v11 的核验父体逐月变动多，2026-06 至 09 按家族算时要留意。")
L += ['', '## 3. 口径标记', '', 'MCP 导出本身是父体月销 ≥ 50、价格 ≥ 90；2026 年两批原本没有价格门槛。跨来源比较时，用"家族月销≥60"和"价格≥90"两列统一口径。', '',
      '| 月份 | 纳入行 | 家族 | 两项都满足的行 | 两项都满足的家族 | 两项都满足的家族销量占比 |', '| :--- | ---: | ---: | ---: | ---: | ---: |']
for m in MONTHS:
    s = I[I['月份'] == ym(m)]; ok = s['家族月销≥60'] & s['价格≥90']
    fs = s.groupby('家族键')['家族月销'].first(); fo = s[ok].groupby('家族键')['家族月销'].first()
    L.append(f"| {ym(m)} | {len(s):,} | {len(fs):,} | {int(ok.sum()):,} | {len(fo):,} | {pct(fo.sum() / fs.sum()) if fs.sum() else '—'} |")
L += ['', '## 4. 各字段有值的比例（纳入分析的子体 × 月）', '', '| 字段 | 全部 | 有五点 | 只有标题/SKU/尺寸 |', '| :--- | ---: | ---: | ---: |']
hasb = I['五点来源'].notna()
def filled(s, h): return pct((~s[h].isin(OPEN) & s[h].notna()).mean()) if len(s) else '—'
for h in HEADERS[:14]: L.append(f'| {h} | {filled(I, h)} | {filled(I[hasb], h)} | {filled(I[~hasb], h)} |')
L += ['', '默认值（落地式、拆装、单盆、台下盆、无镜、无龙头）都算有值；元素没有文字线索的记"待图片核验"。', '',
      f'## 5. 与 2026 年旧标签比（同一子体 {len(both):,} 个，各取最近一个月）', '',
      '旧标签是 1–5 月 v12（与 6–9 月重合的沿用 v11）、6–9 月 v11（用到当时的子体详情）；新打用的是各行自己的标题/SKU/尺寸加统一接上的五点。'
      '宽深高差 ≤ 0.5 寸算一致，信息不足、待图片核验不算。', '',
      '| 字段 | 新打有值 | 两边都有值 | 一致 | 一致率 |', '| :--- | ---: | ---: | ---: | ---: |']
for h, (has, b2, sm) in agree.items(): L.append(f"| {h} | {has:,} | {b2:,} | {sm:,} | {'—' if not b2 else pct(sm / b2)} |")
# D7 的证据来自"比 MDF / 刨花板更耐用"这类对比句的行：技能 D7 规则没排除对比句，会把被比较的材料当成柜体材质
CMP = re.compile(r'\b(?:than|unlike|instead of|compared (?:to|with)|versus|vs\.?)\s+(?:\w+\s+){0,3}?(?:mdf|particle\s*board|plywood|chipboard|engineered wood)', re.I)
ev = json.load(open(f'{OUT}/打标证据.tags.json', encoding='utf-8'))['rows']
cmp = [(r['childASIN'], r['verifiedParentASIN']) for r in ev if r['includeInBathroomAnalysis'] and any(CMP.search(e['quote']) for e in (r['fields'].get('D7柜体材质') or {}).get('selected', []))]
del ev
L += ['', f"D7 一致率偏低：多数是组合粒度不同（如 MDF 对 MDF+胶合板）；另有 {len(cmp):,} 行（{len({a for a, _ in cmp}):,} 个子体、{len({p for _, p in cmp}):,} 个家族）的柜体材质证据来自\"比 MDF / 刨花板更耐用\"这类对比句，"
      '被当成了材质（如 ARIEL 标成 MDF+胶合板+刨花板，2026 年旧标签是实木），属技能 D7 规则漏洞，修技能后重打。']
ct = pd.crosstab(I['形态（怎么装）'], I['柜体结构'])
L += ['', '## 6. 形态两层', '', '| 形态（怎么装） | 开放式 | 待图片核验 | 开放式占比 |', '| :--- | ---: | ---: | ---: |']
for f_, r in ct.iterrows(): L.append(f"| {f_} | {int(r.get('开放式', 0)):,} | {int(r.get('待图片核验', 0)):,} | {pct(r.get('开放式', 0) / r.sum())} |")
sc = Counter(I['柜体结构来源'].dropna())
L += ['', f"开放式按文字来源：{'、'.join(f'{k} {v:,}' for k, v in sc.most_common())}（行）。技能的\"开放式\"（console）已归落地式。", '',
      '## 7. 非浴室柜剔除（wen 2026-10-29：不是浴室柜的剔除）', '']
nv_new = NV[NV['依据'] == '规则命中（新）']
L += [f"- wen 确认的 87 个子体整条剔除：{int(X['子ASIN'].isin(CONF).sum()):,} 行（{'、'.join(f'{k} {v}' for k, v in NV[NV['依据'] == 'wen 确认（87 个）']['类别'].value_counts().items())}）。",
      f"- 规则新命中、按行剔除：{len(nv_new)} 个子体、{int(nv_new['剔除行'].sum()):,} 行（{'、'.join(f'{k} {v}' for k, v in nv_new['类别'].value_counts().items())}）；"
      f"按来源：{'、'.join(f'{k} {v}' for k, v in Counter(b for s in nv_new['来源批次'] for b in s.split('、')).items())}（子体）。"
      f"其中 {int(nv_new['该子体其他月份仍纳入'].sum())} 个子体只在部分月份命中（链接换过产品），其余月份照常纳入。",
      '- 规则修正：标题主体（第一个逗号前）是"…Vanity"、后面不接 top / sink 等词的不判独立盆台（UEV B0DT95PHVR 看图是真浴室柜，已不再剔除）；'
      '去掉了原来"标题里有 vanity with / vanity set 就不判盆台"的豁免（台面产品标题常写"Sintered Stone Vanity with … Sink"，原来漏判）。', '']
if len(nv_new):
    L += ['规则新命中的子体：', '', '| 子体 | 类别 | 剔除月份 | 来源 | 标题（前 70 字） |', '| :--- | :--- | :--- | :--- | :--- |']
    for a, r in nv_new.head(60).iterrows():
        L.append(f"| {a} | {r['类别']} | {r['月份']} | {r['来源批次']} | {html.unescape(str(r['标题']))[:70].replace('|', '/')} |")
    if len(nv_new) > 60: L.append(f'| …… | 另 {len(nv_new) - 60} 个见待核验清单"已剔除非浴室柜"页 | | | |')
L += ['', '## 8. 待核验清单（待核验清单.xlsx，按唯一子体，取最近一个月）', '',
      '每页按家族最高父体月销从高到低排；"累计销量覆盖"= 看到这一行时，已覆盖全部子体累计销量（家族月销按导出子体均分）的比例。', '',
      '| 页 | 子体数 | 家族数 | 销量占比 |', '| :--- | ---: | ---: | ---: |']
for name, s in Q.items(): L.append(f"| {name} | {len(s):,} | {s['家族键'].nunique():,} | {pct(s['子体累计销量（家族均分）'].sum() / GRAND)} |")
ctype = Counter()
for note in Q['冲突']['打标说明']:
    ctype.update({h for part in str(note).split('；') if any(w in part for w in ('不一致', '待核验', '冲突')) for h in HEADERS[:14] if part.startswith(h)})
L += ['', '冲突页按字段（子体数，一个子体可有多项）：' + '、'.join(f'{k} {v:,}' for k, v in ctype.most_common()) + '。',
      f'另有"已剔除非浴室柜"页：{len(NV)} 个子体（wen 确认 {int((NV["依据"] == "wen 确认（87 个）").sum())}、2026 非目标名单 {int(NV["依据"].str.startswith("2026").sum())}、规则新命中 {len(nv_new)}）。',
      '', f'## 9. 输出（不入库，在 {os.path.relpath(OUT, ROOT)}/）', '',
      '- 统一分析用表：统一打标_分析用.pkl / .xlsx。共同列：月份、子ASIN、家族键、品牌、标题、SKU、尺寸文本、价格、家族月销、家族导出子体数、子体月销（家族均分）、'
      '子体月销（2026 原流程估算）、小类BSR、评分、评分数、上架日期、数据来源批次；16 列标签、形态（怎么装）、柜体结构、五点来源；口径标记"家族月销≥60""价格≥90"；'
      'MCP 才有的月新增评分数、上月购买标、卖家数、卖家所属地、大类BSR。',
      '- 逐字段证据：打标证据.tags.json；待核验清单：待核验清单.xlsx。', '']
open(REPORT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
