"""给 2026-01～03 打标（v11 规则），并生成分析用合并表。
1. 把三个月"销量_output.xlsx"整理成 bathroom-vanity-tagger 的规范化输入（无接口详情，文本来自标题、SKU、详细参数、商品尺寸、五点）。
2. 用技能原脚本 tag_cached.py 打标。
3. 与 6–9 月 v11 重合的子体沿用 v11 标签；统计两套标签的一致率，用来估计新子体标签的可靠程度。
4. 按技能流程用 write_workbook.py 在每月底表末尾追加 16 列，verify_workbook.py 逐格校验，不通过就停。
5. 另出分析用合并表：统一表头、父体月销量、子体月销量（6–9 月公式）、16 列标签、标签来源。
环境变量：TAGGER（技能目录，含 scripts/）、Q1_RAW、V11、OUT_DIR（默认 input/data_v2/202601-202603_打标，不入库）、REPORT_MD。
用法：python3 -I 一到三月_打标.py"""
import os, json, subprocess, sys, numpy as np, pandas as pd
from collections import Counter
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
TAGGER = os.environ['TAGGER']
Q1 = os.environ.get('Q1_RAW', os.path.join(ROOT, 'input/data_v2/raw_202601-202603'))
V11 = os.environ.get('V11', os.path.join(ROOT, 'input/data_v2/BathroomVanities_202606-202609_SKU销量预估_已打标_v11'))
OUT = os.environ.get('OUT_DIR', os.path.join(ROOT, 'input/data_v2/202601-202603_打标'))
REPORT = os.environ.get('REPORT_MD', os.path.join(HERE, '一到三月_打标结果.md'))
MONTHS = ['01', '02', '03']
HEADERS = ['D1产品形态', 'D2安装方式', 'D3盆数', 'D4台面形态', 'D5元素', 'D6柜体颜色', 'D7柜体材质', 'D8台面材质', 'D8台盆材质',
           'D9宽(in)', 'D9深(in)', 'D9高(in)', 'D10镜子', 'D11龙头', '打标状态', '打标说明']
TAGGED_STATES = ('文本证据可用', '部分信息不足', '存在冲突待核验')
OPEN = (None, '信息不足', '待图片核验')
WORK = os.path.join(OUT, '_work'); DR = os.path.join(WORK, 'data_root'); TD = os.path.join(WORK, 'tag')
for d in (OUT, DR, TD): os.makedirs(d, exist_ok=True)

def nn(v):  # JSON 不接受 NaN
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else v

def is_vanity(s):
    return any(x.strip() in ('Bathroom Vanities', 'Bathroom Vanity Suites') for x in str(s).splitlines())

def run(script, *args, capture=False):
    r = subprocess.run([sys.executable, '-I', os.path.join(TAGGER, 'scripts', script), *map(str, args)], capture_output=True, text=True)
    if r.returncode != 0: raise SystemExit(f'{script} 失败：{r.stdout[-800:]}{r.stderr[-800:]}')
    return r.stdout

# ---------- 读数据 ----------
base = {m: f'{Q1}/2026-{m}/2026.{m} 销量_output.xlsx' for m in MONTHS}
X = {m: pd.read_excel(base[m], sheet_name=0) for m in MONTHS}
old = {m: pd.read_excel(next(f'{Q1}/2026-{m}/{f}' for f in os.listdir(f'{Q1}/2026-{m}') if f.endswith('_tagged_size_v2.xlsx'))) for m in MONTHS}
V = pd.read_excel(V11 + '.xlsx', sheet_name='SKU估算明细'); V['月'] = V['目标月份'].astype(str).str[:6]

# v11 标签：每个子体取最近一个已打标月份的那一行
vt = V[V['打标状态'].isin(TAGGED_STATES)].sort_values('月').groupby('子ASIN').tail(1).set_index('子ASIN')
V11TAG = {a: ([nn(r[h]) for h in HEADERS], r['月']) for a, r in vt.iterrows()}
# v11 已确认的非目标商品（不含"目标月归属待核验"那类说明）
nt = V[(V['打标状态'] == '不纳入浴室柜分析') & ~V['打标说明'].astype(str).str.startswith('保留原始记录')]
NONTARGET = nt.groupby('子ASIN')['打标说明'].first().to_dict()

# 五点：1–3 月旧打标文件按父体取（父体级文本）；没有时用 v11 同子体，再没有用 v11 同父体
b_parent = pd.concat(old.values()).dropna(subset=['五点描述']).groupby('父ASIN')['五点描述'].first().to_dict()
vb = V.dropna(subset=['五点描述'])
b_v11_child = vb.groupby('子ASIN').apply(lambda g: (g['五点描述'].iloc[-1], g['五点来源'].iloc[-1], g['五点来源ASIN'].iloc[-1])).to_dict()
b_v11_parent = vb.groupby('核验父ASIN').apply(lambda g: (g['五点描述'].iloc[-1], g['五点来源ASIN'].iloc[-1])).to_dict()

# ---------- 1. 规范化输入 ----------
rows, inputs, meta = [], [], []
for m in MONTHS:
    x = X[m]; fn = os.path.basename(base[m])
    for i, r in x.iterrows():
        a, p = r['ASIN'], r['父ASIN']; ok = is_vanity(r['小类目'])
        if p in b_parent: bullets, src, srca, how = b_parent[p], '父体详情填充', p, '1–3月旧打标五点（父体级）'
        elif a in b_v11_child: (bullets, src, srca), how = b_v11_child[a], '6–9月v11同子体五点'
        elif p in b_v11_parent: (bullets, srca), src, how = b_v11_parent[p], '父体详情填充', '6–9月v11同父体五点'
        else: bullets = src = srca = how = None
        rows.append({'子ASIN': a, '目标月份': f'2026{m}', '站点': 'US', '核验父ASIN': nn(p), 'SKU属性': nn(r['SKU']), '商品标题': nn(r['商品标题']),
                     '商品尺寸': nn(r['商品尺寸']), '五点描述': nn(bullets), '五点来源': src, '五点来源ASIN': srca, '商品价格': nn(r['价格($)']),
                     '主图链接': nn(r['商品主图']), '商品链接': nn(r['商品详情页链接']), '关联原始记录ID': f'{fn}#R{i + 2}',
                     '_eligible': bool(ok), '_outside_input_scope': not ok})
        inputs.append({'asin': a, 'month': f'2026{m}', 'attributes': nn(r['详细参数']), 'features': None, 'sourceFile': fn, 'sourceRow': i + 2})
        meta.append({'月': m, '子ASIN': a, '小类目': str(r['小类目']).replace('\r\n', ' / '), '浴室柜': ok, '五点来源说明': how})
json.dump({'detailRows': rows}, open(f'{DR}/sales_payload.json', 'w', encoding='utf-8'), ensure_ascii=False)
json.dump({}, open(f'{DR}/collected_details.json', 'w'))
json.dump({'confirmedNonTargetProducts': NONTARGET}, open(f'{DR}/step1_macro_audit.json', 'w', encoding='utf-8'), ensure_ascii=False)
json.dump([], open(f'{DR}/feature_field_provenance.json', 'w'))
json.dump(inputs, open(f'{DR}/input_rows.json', 'w', encoding='utf-8'), ensure_ascii=False)

# ---------- 2. 打标 ----------
run('selftest.py')
print(run('tag_cached.py', '--data-root', DR, '--out-dir', TD)[-600:])
M = json.load(open(f'{TD}/tagging_matrix.json', encoding='utf-8'))['matrix']
assert len(M) == len(rows)

# ---------- 3. 沿用 v11 与一致率 ----------
final, source, agree = [], [], {h: [0, 0, 0] for h in HEADERS[:14]}  # [两边都有值, 一致, 新打有值的行]
seen = set()
for k, (row, mt) in enumerate(zip(M, meta)):
    a, vals = mt['子ASIN'], list(row)
    if not mt['浴室柜']:
        vals[14], vals[15] = '不纳入浴室柜分析', '小类目不是浴室柜：' + mt['小类目']; final.append(vals); source.append('不纳入'); continue
    if vals[14] == '不纳入浴室柜分析': final.append(vals); source.append('不纳入（v11 已确认非目标）'); continue
    if a in V11TAG:
        v, vm = V11TAG[a]
        if a not in seen:  # 一致率按唯一子体算一次
            seen.add(a)
            for j, h in enumerate(HEADERS[:14]):
                t, w = vals[j], v[j]
                if t not in OPEN: agree[h][2] += 1
                if t in OPEN or w in OPEN: continue
                agree[h][0] += 1
                same = abs(float(t) - float(w)) <= 0.5 if h.startswith('D9') else str(t) == str(w)
                agree[h][1] += same
        final.append(v[:15] + [f'沿用6–9月v11同子体标签（{vm[:4]}-{vm[4:]}）；' + (v[15] or '')]); source.append('沿用 v11')
    else:
        vals[15] = '1–3月按v11规则新打（文本：标题/SKU/详细参数/尺寸' + ('/五点：' + mt['五点来源说明'] if mt['五点来源说明'] else '') + '）；' + (vals[15] or '')
        final.append(vals); source.append('新打（v11 规则）')

# 柱状盆统一（wen 2026-10-28，已写进打标技能 v12 的 FORM-PEDESTAL-PRIORITY）：
# 技能对全部行都打了一遍，判为柱状盆的行，沿用 v11 的也一并统一，两种来源同一口径
n_ped = 0
for k, vals in enumerate(final):
    if source[k].startswith('不纳入'): continue
    if M[k][0] == '柱状盆' and vals[0] != '柱状盆':
        vals[0] = '柱状盆'; vals[15] = '形态按打标技能 v12 柱状盆规则统一（wen 2026-10-28）；' + (vals[15] or ''); n_ped += 1
print('统一为柱状盆的行', n_ped)

# ---------- 4. 写入每月底表并逐格校验 ----------
verify, k0 = {}, 0
for m in MONTHS:
    n = len(X[m]); mj = f'{WORK}/matrix_2026-{m}.json'
    json.dump({'headers': HEADERS, 'matrix': final[k0:k0 + n]}, open(mj, 'w', encoding='utf-8'), ensure_ascii=False)
    out = f'{OUT}/BathroomVanities_2026-{m}_SKU销量预估_已打标_v11规则.xlsx'
    run('write_workbook.py', '--base', base[m], '--matrix', mj, '--out', out, '--sheet', f'Competitor-US-2026-{m}')
    r = subprocess.run([sys.executable, '-I', os.path.join(TAGGER, 'scripts', 'verify_workbook.py'), '--base', base[m], '--out', out, '--matrix', mj, '--sheet', f'Competitor-US-2026-{m}'], capture_output=True, text=True)
    verify[m] = json.loads(r.stdout)
    if not verify[m]['ok']: raise SystemExit(f'2026-{m} 校验未通过：{r.stdout[:800]}')
    k0 += n
json.dump(verify, open(f'{WORK}/verify.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
os.replace(f'{TD}/tagging_evidence.json', f'{OUT}/BathroomVanities_202601-202603_打标证据.tags.json')

# ---------- 5. 分析用合并表 ----------
parts = []
for m in MONTHS:
    x = X[m].copy()
    x.insert(0, '目标月份', f'2026-{m}')
    x['父体月销量'] = x['父ASIN'].map(x.groupby('父ASIN')['月销量'].agg(lambda s: s.mode().iloc[0]))
    x['列出子体数'] = x.groupby('父ASIN')['ASIN'].transform('size')
    fam_kw = x.groupby('父ASIN')['流量词'].transform(lambda s: (s.fillna(0) > 0).any())
    single = (x['列出子体数'] == 1) & (x['变体数'] == 1)
    x['子体月销量（6–9月公式）'] = np.where(single, x['父体月销量'], np.where(fam_kw, x['父体月销量'] * x['流量词占比'].fillna(0), np.nan))
    # wen 2026-10-28：没导出的子体按销量太低处理，父体销量全部分给导出的子体（流量词占比在导出子体内归一）
    tot = x.groupby('父ASIN')['流量词占比'].transform(lambda s: s.fillna(0).sum())
    # 只导出 1 行的父体：其余变体按销量太低处理，这一行拿走全部父体销量（不论有没有流量词）
    only_one = x['列出子体数'] == 1
    x['子体月销量（父体全分给导出子体）'] = np.where(only_one, x['父体月销量'], np.where(tot > 0, x['父体月销量'] * x['流量词占比'].fillna(0) / tot.where(tot > 0, 1), np.nan))
    x['小类BSR数值'] = pd.to_numeric(x['小类BSR'], errors='coerce'); x['商品价格'] = pd.to_numeric(x['价格($)'], errors='coerce')
    x['纳入浴室柜分析'] = x['小类目'].map(is_vanity)
    parts.append(x)
A = pd.concat(parts, ignore_index=True)
for j, h in enumerate(HEADERS): A[h] = [r[j] for r in final]
A['标签来源'] = source
keep = ['目标月份', 'ASIN', '父ASIN', '逻辑父体编码', '品牌', '商品标题', 'SKU', '上架时间', '商品价格', '买家运费($)', '配送方式', '小类目', '纳入浴室柜分析',
        '小类BSR数值', '父体月销量', '月销量', '子体销量', '变体数', '列出子体数', '流量词', '流量词占比', '流量推算销量', '子体月销量（6–9月公式）', '子体月销量（父体全分给导出子体）',
        '评分', '评分数', '商品详情页链接'] + HEADERS + ['标签来源']
A = A[keep].rename(columns={'ASIN': '子ASIN', '父ASIN': '核验父ASIN', 'SKU': 'SKU属性', '上架时间': '上架日期', '小类BSR数值': '小类BSR',
                            '月销量': '父体月销量（行值）', '子体销量': '子体销量（卖家精灵）', '流量推算销量': '子体月销量（原流程）'})
A.to_pickle(f'{OUT}/BathroomVanities_202601-202603_分析用.pkl')
A.to_excel(f'{OUT}/BathroomVanities_202601-202603_分析用.xlsx', index=False, sheet_name='SKU明细')

# ---------- 报告（只写汇总） ----------
T = A[A['纳入浴室柜分析'] & ~A['标签来源'].str.startswith('不纳入')]
L = ['# 2026-01～03 打标结果（v11 规则）', '', '> 由 `一到三月_打标.py` 生成。底表是每月最新的"销量_output.xlsx"，只在末尾追加 16 列标签，其余单元格逐格校验未变。', '',
     '## 1. 范围与来源', '', '| 月份 | 子体行 | 纳入打标 | 沿用 v11 | 新打（v11 规则） | 不纳入 | 校验 |', '| :--- | ---: | ---: | ---: | ---: | ---: | :--- |']
for m in MONTHS:
    s = A[A['目标月份'] == f'2026-{m}']['标签来源'].value_counts()
    L.append(f'| 2026-{m} | {len(X[m]):,} | {int(s.get("沿用 v11", 0) + s.get("新打（v11 规则）", 0)):,} | {int(s.get("沿用 v11", 0)):,} | {int(s.get("新打（v11 规则）", 0)):,} | {int(sum(v for k, v in s.items() if k.startswith("不纳入"))):,} | 非标签单元格改动 {verify[m]["nonTagCellsChanged"]}，标签不符 {verify[m]["tagCellMismatches"]} |')
u = T.drop_duplicates('子ASIN')
L += ['', f'- 唯一子体：沿用 v11 {int((u["标签来源"] == "沿用 v11").sum()):,} 个，新打 {int((u["标签来源"] == "新打（v11 规则）").sum()):,} 个。',
      '- 新打的文本只有标题、SKU、卖家精灵导出的详细参数、商品尺寸和父体五点，没有接口抓的子体详情，信息不足的比例会高于 6–9 月。', '',
      '## 2. 新打标签的可靠程度：同一子体，用 1–3 月文本新打 vs v11 标签', '',
      f'对象：与 6–9 月重合的 {len(seen):,} 个子体。先只用 1–3 月能拿到的文本把它们重打一遍，再和 v11 标签逐字段比较；新打子体的标签可靠程度大致看这一列。', '',
      '| 字段 | 重打后有值 | 两边都有值 | 一致 | 一致率 |', '| :--- | ---: | ---: | ---: | ---: |']
for h, (both, same, has) in agree.items():
    L.append(f'| {h} | {has:,} | {both:,} | {same:,} | {"—" if not both else f"{same / both:.0%}"} |')
L += ['', '一致率低的字段，新打子体的标签要谨慎使用；默认值（落地式、拆装、单盆、台下盆、无镜、无龙头）两边都会填，一致率偏高。D1 的差异里包含柱状盆新规则：技能 v12 把立柱盆储物柜统一为柱状盆，v11 原标签按旧规则。', '',
      f'沿用 v11 的行里，技能 v12 判为柱状盆、原标签不是的，统一为柱状盆：共 {n_ped} 行（新打的行已由技能直接判定）。', '',
      '## 3. 打标后各字段"有值"的比例（纳入打标的子体×月）', '', '| 字段 | 沿用 v11 | 新打 |', '| :--- | ---: | ---: |']
for h in HEADERS[:14]:
    f = lambda s: f'{(~T[T["标签来源"] == s][h].isin(OPEN) & T[T["标签来源"] == s][h].notna()).mean():.0%}'
    L.append(f'| {h} | {f("沿用 v11")} | {f("新打（v11 规则）")} |')
L += ['', '## 4. 输出（不入库，在 input/data_v2/202601-202603_打标/）', '',
      '- 每月一份正式打标表：BathroomVanities_2026-0X_SKU销量预估_已打标_v11规则.xlsx（原 70 列不动，末尾 16 列标签）。',
      '- 分析用合并表：BathroomVanities_202601-202603_分析用.xlsx / .pkl（统一表头、父体月销量、子体月销量两种口径、标签来源）。',
      '- 逐字段证据：BathroomVanities_202601-202603_打标证据.tags.json（新打部分）。', '']
open(REPORT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
