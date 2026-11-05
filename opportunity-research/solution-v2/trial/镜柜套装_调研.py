"""镜柜 + 浴室柜套装调研（wen 待办第 1 条，2026-11-05）。
读统一打标表（Amazon，2024-10 至 2026-10）、关键词研究包、三平台商品表 / 月销表，输出结果表到 input/data_v2/专题调研_20261105/，
屏幕打印报告要用的数字。报告：solution-v2/开发建议/镜柜浴室柜套装_调研.md。
口径：
- 子体是否带镜子：先看 SKU 属性（同一链接里常有"只要柜子 / 柜子 + 镜柜"两种子体），SKU 没写再看标题；写了 without / no mirror / cabinet only / vanity only 的算不带。
- 框 = 尺寸段 × 拆装 × 形态（revision 10：28″ 单独成档，开放式单独成框）。
- 销量：2026-01 起用子体自己的月销估算（缺的用家族均分），之前用家族均分；"款" = 家族键。
- 成功线：上架 6 个月内任一月小类 BSR ≤ 50 或家族月销售额 ≥ $10 万。"""
import os, re, json, glob, html
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
D = os.path.join(ROOT, 'input/data_v2'); OUT = os.path.join(D, '专题调研_20261105'); os.makedirs(OUT, exist_ok=True)
pd.set_option('display.width', 250); pd.set_option('display.max_colwidth', 110); pd.set_option('display.max_rows', 300)
mi = lambda s: int(str(s)[:4]) * 12 + int(str(s)[5:7]) - 1

# ---------- 1. 读表、分框 ----------
A = pd.read_pickle(os.path.join(D, '统一打标/统一打标_分析用.pkl'))
A['标题'] = A['标题'].fillna('').map(html.unescape); A['SKU'] = A['SKU'].fillna('').astype(str).map(html.unescape)
def band(w):   # revision 10：18 / 24 / 28 / 30 / 36 / 42 / 48 / 60 / 72+
    if pd.isna(w): return None
    for c, lo, hi in [(18, 15, 21), (24, 21, 26), (28, 26, 29), (30, 29, 33), (36, 33, 39), (42, 39, 45), (48, 45, 54), (60, 54, 66)]:
        if lo <= w < hi: return f'{c}″'
    return '72″+' if w >= 66 else None
A['尺寸段'] = pd.to_numeric(A['D9宽(in)'], errors='coerce').map(band)
A['装'] = np.where(A['D2安装方式'].eq('整装'), '整装', '拆装')
A['形态'] = np.where(A['柜体结构'].eq('开放式'), '开放式', A['形态（怎么装）'].fillna('落地式'))
A['框'] = A['尺寸段'].fillna('?') + ' · ' + A['装'] + ' · ' + A['形态']
A['m'] = A['月份'].map(mi)
A['c'] = np.where(A['m'] >= mi('2026-01'), pd.to_numeric(A['子体月销（2026 原流程估算）'], errors='coerce'), np.nan)
A['c'] = pd.Series(A['c']).fillna(pd.to_numeric(A['子体月销（家族均分）'], errors='coerce')).fillna(0).clip(lower=0).values
A['价格'] = pd.to_numeric(A['价格'], errors='coerce'); A['评分'] = pd.to_numeric(A['评分'], errors='coerce').where(lambda s: s.between(1, 5))

NEG = re.compile(r"without[^|;()]{0,45}mirror|w/o mirror|no mirror|mirror not included|excluding mirror|mirror (?:is )?sold separately|"
                 r"vanity only|cabinet only|cabint only|single cabinet only|sink cabinet only|not include[^|;()]{0,30}mirror", re.I)
CAB = re.compile(r"medicine cabinet|mirror cabinet|mirrored cabinet|cabinet mirror|mirror medicine", re.I)
MIR = re.compile(r"mirror", re.I)
def mirror(title, sku):
    for s in (sku, title):   # SKU 写了就按 SKU，没写看标题
        if NEG.search(s): return '不带'
        if CAB.search(s): return '带镜柜'
        if MIR.search(s): return '带镜子'
    return '不带'
A['镜'] = [mirror(t, s) for t, s in zip(A['标题'], A['SKU'])]
A['套装'] = A['镜'].ne('不带')
LED = re.compile(r"\bled\b|light|lighted|defog|anti-fog", re.I)
A['灯'] = [bool(LED.search(t + ' ' + s)) and m for t, s, m in zip(A['标题'], A['SKU'], A['套装'])]
B = A[A['纳入浴室柜分析']].copy()

# ---------- 2. 全市场：套装有多少、卖多少（逐月） ----------
mon = B.groupby(['月份', '镜']).agg(月销=('c', 'sum'), 款=('家族键', 'nunique')).unstack(fill_value=0)
tot = B.groupby('月份')['c'].sum()
mon[('套装份额', '')] = (mon[('月销', '带镜柜')] + mon[('月销', '带镜子')]) / tot
print('== 逐月：带镜柜 / 带镜子 / 不带 的月销与款数 =='); print(mon.round(3).to_string())
mon.to_csv(os.path.join(OUT, '套装_逐月.csv'), encoding='utf-8-sig')

W = B[B['m'] >= mi('2026-01')]   # 2026-01 至 10：子体月销可用
NM = W['m'].nunique()
print(f'\n2026-01 至 10 共 {NM} 个月；套装子体行 {W["套装"].sum()}，款 {W[W["套装"]]["家族键"].nunique()}；全部款 {W["家族键"].nunique()}')
print('套装月均销', round(W[W['套装']]['c'].sum() / NM), '全市场月均销', round(W['c'].sum() / NM))

# ---------- 3. 同框比较：套装 vs 不带镜 ----------
def fam_month(d):   # 款 × 月：月销合计、加权价、评分
    g = d.groupby(['家族键', 'm']).agg(c=('c', 'sum'), p=('价格', 'median'), r=('评分', 'median'))
    return g.reset_index()
rows = []
for fr, d in W[W['尺寸段'].notna()].groupby('框'):
    a, b = d[d['套装']], d[~d['套装']]
    if a['家族键'].nunique() == 0: continue
    fa, fb = fam_month(a), fam_month(b)
    rows.append(dict(框=fr, 套装款=a['家族键'].nunique(), 不带款=b['家族键'].nunique(),
                     套装月销=a['c'].sum() / NM, 框月销=d['c'].sum() / NM,
                     套装单款月销=fa.groupby('家族键')['c'].mean().median(), 不带单款月销=fb.groupby('家族键')['c'].mean().median(),
                     套装中位价=a['价格'].median(), 不带中位价=b['价格'].median(),
                     套装评分=fa['r'].median(), 不带评分=fb['r'].median()))
F = pd.DataFrame(rows); F['套装份额'] = F['套装月销'] / F['框月销']; F['溢价'] = F['套装中位价'] / F['不带中位价']
F['单款比'] = F['套装单款月销'] / F['不带单款月销']
F = F.sort_values('框月销', ascending=False)
print('\n== 同框：套装 vs 不带镜（2026-01 至 10） =='); print(F.round(2).to_string(index=False))
F.to_csv(os.path.join(OUT, '套装_同框比较.csv'), index=False, encoding='utf-8-sig')
big = F[F['套装款'] >= 3]
print('\n套装款 ≥ 3 的框：', len(big), '；其中套装单款月销高于不带镜的框', int((big['单款比'] > 1).sum()),
      '；套装溢价中位', round(big['溢价'].median(), 2))

# 按尺寸段（拆装、形态合并只用来数个数，不下结论）
S = W[W['尺寸段'].notna()].groupby(['尺寸段', '镜']).agg(月销=('c', 'sum'), 款=('家族键', 'nunique'), 价=('价格', 'median')).unstack()
print('\n== 按尺寸段（只看个数） =='); print(S.round(0).to_string())

# 带镜柜 vs 带镜子，有灯 vs 无灯
K = W[W['套装']].groupby(['镜', '灯']).agg(月销=('c', 'sum'), 款=('家族键', 'nunique'), 价=('价格', 'median'), 评分=('评分', 'median'))
K['月销'] /= NM; print('\n== 套装内部：镜柜 / 镜子 × 有灯 / 无灯 =='); print(K.round(2).to_string())

# 按元素（看图）
E = W.assign(元素=W['元素（看图）'].fillna('未看图')).groupby(['元素', '套装']).agg(月销=('c', 'sum'), 款=('家族键', 'nunique'), 价=('价格', 'median')).unstack()
E[('月销', True)] /= NM; E[('月销', False)] /= NM
E['套装份额'] = E[('月销', True)] / (E[('月销', True)] + E[('月销', False)])
print('\n== 按元素 =='); print(E.sort_values(('月销', False), ascending=False).head(20).round(2).to_string())

# ---------- 4. 同一链接里"只要柜子"和"柜子 + 镜子"两种子体：价差和谁卖得多 ----------
def strip(s): return re.sub(r"(with(out)?|w/o|w/|\+|and|&)?\s*(led\s*)?(mirror|medicine)\s*(cabinet)?(\s*set)?|sink cabinet|cabinet only|cabint only|vanity only|style:|only|set", '', s.lower()).replace(' ', '')
P = []
for (fam, m), d in A[A['SKU'].str.len() > 0].groupby(['家族键', 'm']):
    if d['套装'].nunique() < 2: continue
    d = d.assign(k=d['SKU'].map(strip))
    for k, e in d.groupby('k'):
        a, b = e[e['套装']], e[~e['套装']]
        if len(a) and len(b):
            P.append(dict(家族键=fam, 月份=e['月份'].iloc[0], 品牌=e['品牌'].iloc[0], 框=e['框'].iloc[0], 变体=k[:40], 镜=a['镜'].iloc[0],
                          带镜价=a['价格'].median(), 不带价=b['价格'].median(), 带镜子体销=a['c'].sum(), 不带子体销=b['c'].sum(),
                          带镜BSR=a['小类BSR'].min(), 不带BSR=b['小类BSR'].min(), 标题=e['标题'].iloc[0][:90]))
P = pd.DataFrame(P); P['加价'] = P['带镜价'] - P['不带价']; P['加价比'] = P['加价'] / P['不带价']
P.to_csv(os.path.join(OUT, '套装_同链接带镜不带镜配对.csv'), index=False, encoding='utf-8-sig')
pf = P.groupby(['家族键', '品牌', '镜']).agg(月=('月份', 'nunique'), 框=('框', 'first'), 不带价=('不带价', 'median'), 带镜价=('带镜价', 'median'), 加价=('加价', 'median'), 加价比=('加价比', 'median'),
                                       带镜销=('带镜子体销', 'sum'), 不带销=('不带子体销', 'sum'), 标题=('标题', 'first')).reset_index()
pf['带镜销占'] = pf['带镜销'] / (pf['带镜销'] + pf['不带销'])
print('\n== 同链接配对（同色同尺寸，带镜 vs 不带镜） =='); print(pf.round(2).to_string(index=False))
print('加价中位 $', round(pf['加价'].median()), '加价比中位', round(pf['加价比'].median(), 2), '；2026 有子体销量的配对：带镜子体销占比中位',
      round(pf.loc[pf['带镜销'] + pf['不带销'] > 0, '带镜销占'].median(), 2))

# 单独镜柜 / 镜子（被剔除的行）
X = A[A['非浴室柜类别'].isin(['独立镜柜/药柜', '镜子'])]
xs = X.groupby('家族键').agg(品牌=('品牌', 'first'), 标题=('标题', 'first'), 月=('月份', lambda s: f'{s.min()}~{s.max()}'), 月数=('月份', 'nunique'),
                            价=('价格', 'median'), 家族月销=('家族月销', 'median'), BSR=('小类BSR', 'min'), SKU=('SKU', lambda s: '; '.join(sorted(set(s)))[:80]))
print('\n== 被剔除的单独镜柜 / 镜子 =='); print(xs.to_string())

# ---------- 5. 新款：套装能不能卖起来 ----------
fam = A[A['纳入浴室柜分析']].copy(); fam['rev'] = pd.to_numeric(fam['家族月销'], errors='coerce') * fam['价格']
fam['up'] = pd.to_datetime(fam['上架日期'], errors='coerce')
U = fam.groupby('家族键').agg(up=('up', 'min'), 套装=('套装', 'mean'), 框=('框', lambda s: s.value_counts().index[0]), 品牌=('品牌', 'first'), 标题=('标题', 'first')).reset_index()
U = U[U['up'].notna()]; U['L'] = U['up'].dt.year * 12 + U['up'].dt.month - 1
U = U[(U['L'] >= mi('2025-01')) & (U['L'] <= mi('2026-04'))]   # 观察满 6 个月
fm = fam.groupby(['家族键', 'm']).agg(bsr=('小类BSR', 'min'), rev=('rev', 'max')).reset_index().merge(U[['家族键', 'L']], on='家族键')
fm = fm[(fm['m'] >= fm['L']) & (fm['m'] <= fm['L'] + 5)]
hit = fm.groupby('家族键').apply(lambda d: bool(((d['bsr'] <= 50) | (d['rev'] >= 1e5)).any()), include_groups=False)
U['做到'] = U['家族键'].map(hit).fillna(False); U['组'] = np.where(U['套装'] >= 0.5, '套装', '不带')
U['尺寸段'] = U['框'].str.split(' · ').str[0]
print('\n== 2025-01 至 2026-04 上架的新款：做到成功线 =='); print(U.groupby('组')['做到'].agg(['size', 'sum', 'mean']).round(3))
sz = U[U['组'] == '套装']['框'].unique()
print('只看有套装新款的框：'); print(U[U['框'].isin(sz)].groupby(['框', '组'])['做到'].agg(['size', 'sum']).unstack(fill_value=0).to_string())
print(U[U['组'] == '套装'][['家族键', '品牌', 'up', '框', '做到', '标题']].sort_values('up').to_string(index=False))

# ---------- 6. 套装代表产品 ----------
R = W[W['套装']].groupby('家族键').agg(品牌=('品牌', 'first'), 标题=('标题', 'first'), 框=('框', lambda s: s.value_counts().index[0]), 镜=('镜', lambda s: s.value_counts().index[0]),
                                     有灯=('灯', 'max'), 元素=('元素（看图）', 'first'), 颜色=('D6柜体颜色', lambda s: s.value_counts().index[0] if s.notna().any() else None),
                                     价=('价格', 'median'), 套装月销=('c', 'sum'), 月数=('月份', 'nunique'), 评分=('评分', 'median'), 评分数=('评分数', 'max'),
                                     上架=('上架日期', 'min'), 最好BSR=('小类BSR', 'min'), 子ASIN=('子ASIN', lambda s: s.value_counts().index[0]))
R['套装月均销（在榜月）'] = R['套装月销'] / R['月数']
R = R.sort_values('套装月销', ascending=False)
R.to_csv(os.path.join(OUT, '套装_代表产品_2026.csv'), encoding='utf-8-sig')
print('\n== 2026 套装代表产品（按 2026-01 至 10 套装子体销量合计） =='); print(R.head(25).round(1).to_string())

# 套装的"同元素"：镜柜和柜体同色同款的写法
MATCH = re.compile(r"matching|sink cabinet \+ mirror cabinet set|mirror cabinet set|vanity set with mirror cabinet|with medicine cabinet", re.I)
W2 = W[W['套装']].assign(配套=lambda d: [bool(MATCH.search(t + ' ' + s)) for t, s in zip(d['标题'], d['SKU'])])
M2 = W2.groupby(['配套', '镜']).agg(款=('家族键', 'nunique'), 月销=('c', 'sum'), 价=('价格', 'median')); M2['月销'] /= NM
print('\n== 套装里写明"配套 / 同款镜柜"的 =='); print(M2.round(1).to_string())

# 价位：套装价相对同框不带镜中位价，单款月销
med = W[~W['套装']].groupby('框')['价格'].median()
fa = fam_month(W[W['套装']]).merge(W[['家族键', '框']].drop_duplicates('家族键'), on='家族键')
fa['价比'] = fa['p'] / fa['框'].map(med)
fa['价位'] = pd.cut(fa['价比'], [0, 1.0, 1.3, 1.6, 9], labels=['≤ 同框中位', '高 0–30%', '高 30–60%', '高 60% 以上'])
pv = fa.groupby('价位', observed=True).agg(款=('家族键', 'nunique'), 款月=('c', 'size'), 单款月销中位=('c', 'median'), 单款月销平均=('c', 'mean'))
print('\n== 套装价位（相对同框不带镜中位价）与单款月销 =='); print(pv.round(1).to_string())

# ---------- 7. 关键词 ----------
K0 = pd.read_csv(os.path.join(D, 'keywords_20261028/数据/01_关键词词库/tables/keywords_unified.csv'))
kw = K0[K0['关键词'].str.contains(r'mirror|medicine|vanity set|combo set', case=False)].sort_values('月搜索量', ascending=False)
kw.to_csv(os.path.join(OUT, '套装_相关搜索词.csv'), index=False, encoding='utf-8-sig')
for w in ['medicine cabinet', 'bathroom medicine cabinet with mirror', 'medicine cabinet with mirror', 'bathroom mirror cabinet', 'bathroom vanity mirror cabinet',
          'bathroom vanity with sink and mirror', 'bathroom vanity set', 'bathroom sink and cabinet combo set', 'vanity without mirror', 'bathroom vanity with sink', 'bathroom vanity']:
    r = K0[K0['关键词'] == w]
    if len(r): print('搜索量', w, int(r['月搜索量'].iloc[0]), r['处理状态'].iloc[0])
TR = {}
for f in glob.glob(os.path.join(D, 'keywords_20261028/数据/02_Amazon历史趋势/raw/*.json')):
    j = json.load(open(f)); k = j.get('keyword')
    if k in ('bathroom vanity with sink and mirror', 'bathroom vanity set', 'bathroom sink and cabinet combo set', 'bathroom vanity with sink'):
        try: data = json.loads(j['response']['content'][0]['text'])['data']
        except Exception: continue
        TR[k] = {x['time']: x['search'] for x in data}
tr = pd.DataFrame(TR); tr.index = [f"{t[:4]}-{t[5:7]}" for t in tr.index]; tr = tr.sort_index().loc['2024-10':]
print('\n== 搜索量走势 =='); print(tr.to_string())
tr.to_csv(os.path.join(OUT, '套装_搜索词走势.csv'), encoding='utf-8-sig')

# ---------- 8. 小平台：带镜子的套装和单独的同系列镜子 ----------
T = pd.read_csv(os.path.join(D, '渠道关键词/大词/三平台_商品表.csv')); MS = pd.read_csv(os.path.join(D, '渠道关键词/大词/三平台_月销表.csv'))
T['t'] = T['title'].fillna('').map(html.unescape)
def kind(t):
    tl = t.lower()
    if NEG.search(tl) or not re.search('mirror|medicine', tl): return '不带'
    if re.search(r'vanity mirror in|wall mount bathroom vanity mirror|medicine cabinet with mirror$|surface mount .*medicine cabinet|recessed', tl) and not re.search(r'sink|vanity with|top', tl.split('mirror')[0][-60:] if 'mirror' in tl else ''):
        return '单独镜子/镜柜'
    return '带镜柜' if CAB.search(tl) else '带镜子'
T['镜'] = T['t'].map(kind)
ms = MS[MS['月'].between('2026-01', '2026-10')].groupby(['渠道', 'pid'])['销量'].sum() / 10
T['月均销'] = [ms.get((c, p), np.nan) for c, p in zip(T['渠道'], T['pid'])]
TC = T.groupby(['渠道', '镜']).agg(商品=('pid', 'size'), 有销量=('月均销', 'count'), 月均销=('月均销', 'sum'), 中位价=('价格', 'median'))
print('\n== 三平台（2026-01 至 10 月均，评论换算） =='); print(TC.round(1).to_string())
TT = T[T['镜'] != '不带'][['渠道', '镜', 't', '价格', '尺寸段', '装', '形态', '月均销']].sort_values('月均销', ascending=False)
print(TT.head(40).round(1).to_string(index=False))
TT.to_csv(os.path.join(OUT, '套装_三平台带镜商品.csv'), index=False, encoding='utf-8-sig')
# HD 同框比较
H = T[(T['渠道'] == 'Home Depot') & T['尺寸段'].notna() & T['装'].isin(['整装', '拆装']) & T['形态'].isin(['落地式', '悬浮式'])].copy()
H['框'] = H['尺寸段'] + ' · ' + H['装'] + ' · ' + H['形态']
hc = H[H['镜'].isin(['带镜子', '带镜柜', '不带'])].assign(套=lambda d: d['镜'] != '不带').groupby(['框', '套']).agg(n=('pid', 'size'), 销=('月均销', 'median'), 价=('价格', 'median')).unstack()
print('\n== HD 同框：带镜套装 vs 不带（单品月均销中位、中位价） =='); print(hc[hc[('n', True)].fillna(0) > 0].round(1).to_string())
