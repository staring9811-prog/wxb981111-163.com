"""关键词数据（美国浴室柜关键词研究包，2026-10-28）核对：覆盖面、打标覆盖、搜索需求走势、和我们估算的品类销量对照（含每月名单深浅）、按宽度的需求与销量份额、竞争快照。
只输出汇总数字。输入：KW（数据包目录）、Q15（1–5 月分析用 pkl）、V11（6–9 月 v11 表，不含扩展名）。输出：OUT_MD。
用法：python3 -I 关键词_需求核对.py"""
import os, re, json, glob, numpy as np, pandas as pd
from scipy.stats import pearsonr
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
KW = os.environ.get('KW', os.path.join(ROOT, 'input/data_v2/keywords_20261028'))
Q15 = os.environ.get('Q15', os.path.join(ROOT, 'input/data_v2/202601-202605_打标/BathroomVanities_202601-202605_分析用.pkl'))
V11 = os.environ.get('V11', os.path.join(ROOT, 'input/data_v2/BathroomVanities_202606-202609_SKU销量预估_已打标_v11'))
OUT = os.environ.get('OUT_MD', os.path.join(HERE, '关键词_需求核对.md'))
WB = f'{KW}/最终工作簿/美国浴室柜_关键词研究_含历史趋势_竞争与PPC参考竞价.xlsx'
SIZE = [(18, 15, 21), (24, 21, 27), (30, 27, 33), (36, 33, 39), (42, 39, 45), (48, 45, 54), (60, 54, 66)]  # wen 矩阵：±3 寸归段

def band(w):
    try: w = float(w)
    except (TypeError, ValueError): return None
    for c, lo, hi in SIZE:
        if lo <= w < hi: return f'{c}″'
    return '72″+' if w >= 66 else None

# ---- 关键词：打标、竞争、历史趋势（原始回包，2022-01 起 57 个月；工作簿只截了 2024.10–2026.09） ----
tag = pd.read_csv(f'{KW}/数据/01_关键词词库/tables/keywords_tagged.csv')
uni = pd.read_csv(f'{KW}/数据/01_关键词词库/tables/keywords_unified.csv')
log = pd.read_csv(f'{KW}/数据/01_关键词词库/tables/query_log.csv')
seeds = pd.read_csv(f'{KW}/数据/01_关键词词库/tables/seeds.csv')
comp = pd.read_excel(WB, sheet_name='关键词竞争', header=5)
rows = []
for f in sorted(glob.glob(f'{KW}/数据/02_Amazon历史趋势/raw/*.json')):
    j = json.load(open(f, encoding='utf-8'))
    for r in json.loads(j['response']['content'][0]['text'])['data']:
        y, m = re.match(r'(\d{4})年(\d{2})月', r['time']).groups()
        rows.append((j['keyword'], f'{y}-{m}', r['search'], r['purchase']))
long = pd.DataFrame(rows, columns=['关键词', '月', '搜索', '购买'])
wide = long.pivot(index='关键词', columns='月', values='搜索')
tot = long.groupby('月').agg(搜索=('搜索', 'sum'), 购买=('购买', 'sum'), 有搜索的词=('搜索', lambda s: int((s > 0).sum())))
def yoy(m, words=None):  # 同一批词（两个月都有搜索量）的同比
    p = f'{int(m[:4]) - 1}{m[4:]}'
    if p not in wide: return np.nan
    w = wide if words is None else wide.loc[wide.index.isin(words)]
    both = w[(w[m] > 0) & (w[p] > 0)]
    return both[m].sum() / both[p].sum() - 1 if len(both) else np.nan
SHOW = [m for m in tot.index if m >= '2024-10']  # 与工作簿相同的 24 个月
recent = [m for m in SHOW if m >= '2026-01']

L = ['# 关键词数据核对（美国浴室柜关键词研究包，2026-10-28）', '',
     '> 由 `关键词_需求核对.py` 生成。数据包：339 个确认有效的浴室柜关键词（2026.09 快照）、Amazon 历史搜索趋势、竞争与 PPC 参考竞价，来源 SellerSprite。', '']

# 1. 覆盖面
got = log.groupby('入口').agg(取到=('本页条数', 'sum'), 接口总数=('接口总条数', 'first'))
L += ['## 1. 覆盖面', '', '| 入口词 | 接口总条数 | 实际取到 |', '| :--- | ---: | ---: |'] + [f'| {i} | {r.接口总数:,} | {r.取到:,} |' for i, r in got.iterrows()]
expanded = seeds.loc[seeds['处理状态'] == '已扩展', '候选形态词'].tolist(); missing = seeds.loc[seeds['处理状态'].astype(str).str.startswith('未返回'), '候选形态词'].tolist()
L += ['', f'- 合并去重后 {len(uni):,} 个词，确认有效 {int((uni["处理状态"] == "有效").sum())} 个；只有有效词进入后面的指标。',
      '- 每个入口最多取 5 页（500 个词），"带盆""悬浮"两个入口的长尾没有取全。',
      f'- 用来扩词的入口：{"、".join(expanded)}；{"、".join(missing)} 接口没有返回。有"悬浮""双盆"入口、没有"落地"入口，所以按安装方式、盆数比份额会偏（见第 5 节）。', '']

# 2. 打标覆盖
cols = ['宽度（英寸）', '安装方式', '盆数', '是否带台面', '门板/装饰元素', '柜体材质', '风格', '颜色色系']
sv = pd.to_numeric(tag['月搜索量'], errors='coerce').fillna(0)
def has(s): return s.notna() & ~s.astype(str).isin(['未提及', 'nan', '待核实', ''])
L += ['## 2. 关键词打标覆盖（2026.09 搜索量口径）', '', '| 维度 | 写明的词 | 占搜索量 | 主要取值 |', '| :--- | ---: | ---: | :--- |']
for c in cols:
    h = has(tag[c]); vc = tag.loc[h, c].astype(str).value_counts().head(5)
    L.append(f'| {c} | {int(h.sum())} | {sv[h].sum() / sv.sum():.0%} | {"、".join(f"{k} {v}" for k, v in vc.items())} |')
wsh = sv[has(tag['宽度（英寸）'])].sum() / sv.sum()
L += ['', f'只有宽度写得多（占搜索量 {wsh:.0%}）；元素、台面、材质、风格几乎没有。大头是"bathroom vanity with sink""bathroom vanity"这类不带属性的泛词。这批词只能回答"哪个尺寸的需求多、在涨还是在跌"。', '']

# 3. 搜索需求走势
yr = tot.assign(年=tot.index.str[:4]).groupby('年')['有搜索的词'].mean()
L += ['## 3. 搜索需求月度走势（339 个词合计）', '', '| 月份 | 搜索量 | 有搜索量的词 | 同比（同一批词） | 购买率 |', '| :--- | ---: | ---: | ---: | ---: |']
for m in SHOW:
    r = tot.loc[m]; y = yoy(m)
    L.append(f'| {m} | {r.搜索:,.0f} | {r.有搜索的词} | {"—" if pd.isna(y) else f"{y:+.0%}"} | {r.购买 / r.搜索:.2%} |')
L += ['', '- 同比只比两个月都有搜索量的词，避免新词、死词把同比带偏。',
      f'- 原始回包从 2022-01 起，但每月有搜索量的词平均只有 {"、".join(f"{k} 年 {v:.0f} 个" for k, v in yr.items())}，2024 年以前的量不能和现在比；工作簿取 2024.10 起的 24 个月是对的。',
      '- 购买量口径断过不止一次：购买率 2024-03、2024-04、2025-06 掉到 0.2% 左右，2025-10 起整体从约 1% 掉到约 0.35%，量级前后不能比，**不用购买量**，只用搜索量。', '']

# 4. 和我们估算的品类销量对照（父体口径，父体月销 ≥ 60）
a = pd.read_pickle(Q15); a = a[a['纳入浴室柜分析']]
a = pd.DataFrame({'m': a['目标月份'], 'p': a['核验父ASIN'], 'k': a['子ASIN'], 'ps': a['父体月销量'].astype(float), 'bsr': pd.to_numeric(a['小类BSR'], errors='coerce'),
                  'w': a['D9宽(in)'], 'c': a['子体月销量（父体全分给导出子体）'], '价': pd.to_numeric(a['商品价格'], errors='coerce'), '形态': a['D1产品形态'], '盆数': a['D3盆数']})
man = json.load(open(V11 + '.analysis.json', encoding='utf-8'))['rowManifest']; keep = {(r['month'], r['childASIN']) for r in man if r['includeInBathroomAnalysis']}
v = pd.read_excel(V11 + '.xlsx', sheet_name='SKU估算明细'); v['m'] = v['目标月份'].astype(str).str[:6]
v = v[[(m, c) in keep for m, c in zip(v['m'], v['子ASIN'])]].dropna(subset=['核验父ASIN'])
v = pd.DataFrame({'m': v['m'].str[:4] + '-' + v['m'].str[4:], 'p': v['核验父ASIN'], 'k': v['子ASIN'], 'ps': pd.to_numeric(v['父体月销量预测'], errors='coerce'),
                  'bsr': pd.to_numeric(v['目标月校验小类BSR'], errors='coerce'), 'w': v['D9宽(in)'], 'c': pd.to_numeric(v['最终SKU月销量估算'], errors='coerce'),
                  '价': pd.to_numeric(v['商品价格'], errors='coerce'), '形态': v['D1产品形态'], '盆数': v['D3盆数']})
x = pd.concat([a, v], ignore_index=True)
fam = x.groupby(['m', 'p']).agg(ps=('ps', 'first'), bsr=('bsr', 'min'), kids=('k', set)).reset_index()
fam = fam[fam.ps >= 60]
fam['档'] = np.select([fam.bsr <= 50, fam.bsr <= 200], ['1–50', '51–200'], '200 以外或无')
ms = sorted(fam.m.unique()); kid = {m: set(x.loc[x.m == m, 'k']) for m in ms}
cm = fam.groupby('m').agg(件数=('ps', 'sum'), 家族=('ps', 'size'))
cm = cm.join(fam.pivot_table(index='m', columns='档', values='ps', aggfunc='size').fillna(0).astype(int).add_suffix(' 家族'))
cm['前 50 名件数'] = fam[fam.档 == '1–50'].groupby('m')['ps'].sum()
cm = cm.join(tot['搜索'])
def deep(m0, m1):
    d = cm.loc[m0] - cm.loc[m1]; return f'{d.家族:.0f} 个家族、{d.件数:,.0f} 件（前 50 名 {d["1–50 家族"]:+.0f} 个，51 名以后 {d["51–200 家族"] + d["200 以外或无 家族"]:+.0f} 个）'
def rank_at(lo, hi):
    md = fam[fam.bsr.between(lo, hi)].groupby('m')['ps'].median(); return f'{md.min():.0f}–{md.max():.0f} 件'
L += ['## 4. 和我们估算的品类销量对照（2026 年 1–9 月，父体月销 ≥ 60）', '',
      '| 月份 | 品类件数 | 家族数 | 家族最好 BSR 1–50 | 51–200 | 200 以外或无 | 前 50 名家族件数 | 关键词搜索量 |', '| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
L += [f'| {m} | {r.件数:,.0f} | {r.家族:.0f} | {r["1–50 家族"]:.0f} | {r["51–200 家族"]:.0f} | {r["200 以外或无 家族"]:.0f} | {r["前 50 名件数"]:,.0f} | {r.搜索:,.0f} |' for m, r in cm.iterrows()]
chg = cm[['件数', '搜索']].pct_change().dropna(); agree = (np.sign(chg['件数']) == np.sign(chg['搜索'])).mean()
L += ['', f'- 品类件数和搜索量的相关 {pearsonr(cm.件数, cm.搜索)[0]:.2f}，相邻月涨跌方向一致 {agree:.0%}（{len(chg)} 对）：我们按月加总的品类件数和需求走势对不上。',
      f'- 原因在名单深浅，不在排名换算：前 50 名家族每月 {cm["1–50 家族"].min()}–{cm["1–50 家族"].max()} 个、件数 {cm["前 50 名件数"].min():,.0f}–{cm["前 50 名件数"].max():,.0f}，很稳；'
      f'6 月比 7 月多 {deep("2026-06", "2026-07")}，8 月比 9 月多 {deep("2026-08", "2026-09")}，品类件数跟着 51 名以后这一段上下跳。',
      f'- 排名换算各月一致，不是销量模型在变：家族最好 BSR 31–50 名的父体销量中位数各月 {rank_at(31, 50)}，51–100 名 {rank_at(51, 100)}，没有跟着 6 月、8 月一起跳。', '']
L += ['**相邻月接续**：上个月在表里的家族，下个月一个子体都不在表里（"整家不见"）；隔一个月又回来的，中间那个月要么漏抓、要么断货，这份数据分不出来。', '',
      '| 月份 | 家族数 | 下月整家不见 | 件数 | 其中前 50 名 | 隔一个月又回来 | 其中前 50 名 |', '| :--- | ---: | ---: | ---: | ---: | ---: | ---: |']
for i, (m0, m1) in enumerate(zip(ms, ms[1:])):
    f0 = fam[fam.m == m0]; gone = f0[f0.kids.map(lambda s: not (s & kid[m1]))]
    back = gone[gone.kids.map(lambda s: bool(s & kid[ms[i + 2]]))] if i + 2 < len(ms) else None
    L.append(f'| {m0}→{m1} | {len(f0)} | {len(gone)} | {gone.ps.sum():,.0f} | {int((gone.bsr <= 50).sum())} | '
             + ('— | — |' if back is None else f'{len(back)} | {int((back.bsr <= 50).sum())} |'))
L += ['', '- 每个月都有前 50 名的家族整家不见、隔月又回来：头部也会缺月，只是少。',
      '- 结论：**按月加总的品类件数不能当需求走势用**（不能说"6 月比 7 月卖得多"）；季节和同比看搜索量；同一个月里的结构（尺寸、形态、价格的份额）照常用我们的数据。',
      '- 对成功判定的影响：成功线看的是头部（BSR ≤ 50 或月销售额 ≥ $10 万），头部覆盖稳定，但个别月份会漏；新品在观察期内缺月时可能误判为未成功，影响量见 `成功率口径_对齐.md`。', '']

# 5. 按宽度：搜索需求份额 vs 销量份额
x = x.merge(fam[['m', 'p']], on=['m', 'p'])  # 只算父体月销 ≥ 60 的家族，与第 4 节一致
x['宽度段'] = x['w'].map(band); x['额'] = x['c'] * x['价']
long = long.merge(tag[['关键词', '宽度（英寸）', '安装方式', '盆数']], on='关键词', how='left')
long['宽度段'] = long['宽度（英寸）'].map(band)
prev = [f'{int(m[:4]) - 1}{m[4:]}' for m in recent]
k = long[long['月'].isin(recent)].dropna(subset=['宽度段']).groupby('宽度段')['搜索'].sum()
s = x.dropna(subset=['宽度段']).groupby('宽度段')[['c', '额']].sum()
t = pd.concat([k.rename('搜索'), s], axis=1).fillna(0)
t['搜索份额'] = t['搜索'] / t['搜索'].sum(); t['件数份额'] = t['c'] / t['c'].sum(); t['金额份额'] = t['额'] / t['额'].sum()
L += ['## 5. 按宽度：搜索需求份额 vs 销量份额（2026 年 1–9 月合计）', '',
      '| 宽度段 | 搜索份额 | 件数份额 | 金额份额 | 搜索÷件数 | 搜索÷金额 | 搜索同比（同一批词） |', '| :--- | ---: | ---: | ---: | ---: | ---: | ---: |']
for g, r in t.sort_values('搜索', ascending=False).iterrows():
    words = set(long.loc[long['宽度段'] == g, '关键词'])
    cur = sum(wide.loc[wide.index.isin(words) & (wide[m] > 0) & (wide[p] > 0), m].sum() for m, p in zip(recent, prev))
    base = sum(wide.loc[wide.index.isin(words) & (wide[m] > 0) & (wide[p] > 0), p].sum() for m, p in zip(recent, prev))
    L.append(f'| {g} | {r.搜索份额:.0%} | {r.件数份额:.0%} | {r.金额份额:.0%} | {r.搜索份额 / r.件数份额:.1f} | {r.搜索份额 / r.金额份额:.1f} | {cur / base - 1:+.0%} |')
nm = int(has(tag['安装方式']).sum()); nb = int(has(tag['盆数']).sum())
def share(col, val):
    h = has(tag[col]); return sv[h & (tag[col] == val)].sum() / sv[h].sum()
L += ['', f'- 搜索份额只在写明宽度的词里算（占全部搜索量 {wsh:.0%}）。写明尺寸的人多半是在换同尺寸的旧柜，未必代表全部买家，只当方向参考。',
      '- "搜索÷件数"大于 1：这个尺寸在搜索里的份额比在销量里高。大尺寸单价高、转化低，搜索份额本来就会偏高，所以同时看"搜索÷金额"，两列都明显大于 1 才算线索；线索只进格子的候选，要用这个尺寸段新品后来的表现去检验，不直接当结论。',
      f'- 悬浮 vs 落地、单盆 vs 双盆不比：写明安装方式的词只有 {nm} 个、写明盆数的 {nb} 个，又有"悬浮""双盆"入口、没有"落地"入口，悬浮占 {share("安装方式", "壁挂/悬浮式"):.0%}、双盆占 {share("盆数", "双盆"):.0%} 是取词造成的。', '']

# 6. 竞争快照
c2 = comp.merge(tag[['关键词', '宽度（英寸）']], on='关键词', how='left'); c2['宽度段'] = c2['宽度（英寸）'].map(band)
g = c2.dropna(subset=['宽度段']).groupby('宽度段').agg(词数=('关键词', 'size'), 结果商品数中位=('结果商品数', 'median'), 点击集中度中位=('点击集中度', 'median'))
L += ['## 6. 竞争快照（2026.09，按宽度段）', '', '| 宽度段 | 词数 | 搜索结果商品数中位 | 前三 ASIN 点击占比中位 |', '| :--- | ---: | ---: | ---: |']
L += [f'| {i} | {int(r.词数)} | {r.结果商品数中位:,.0f} | {r.点击集中度中位:.0%} |' for i, r in g.iterrows()]
L += ['', '- 只有 2026.09 一个月，没有历史，不能看竞争在变多还是变少。PPC 参考竞价币种未注明、100 个词缺失，暂不用。', '']
open(OUT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
