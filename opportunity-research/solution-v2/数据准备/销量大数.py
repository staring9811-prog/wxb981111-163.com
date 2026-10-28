"""销量大数：判断卖家精灵预测销量（父体）与流量词分摊（子体）能不能用。只输出汇总数字。
口径统一：浴室柜小类目、父体月销 ≥ 60 件（6–9 月的收录门槛）。1–5 月价格是逐月值，6–9 月是快照价。
输入：Q1_TABLE（一到五月_打标.py 生成的分析用 pkl）、V11（6–9 月 v11 打标表，不含扩展名）。输出：OUT_MD。
用法：python3 -I 销量大数.py"""
import os, json, numpy as np, pandas as pd
from scipy.stats import spearmanr
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
Q1 = os.environ.get('Q1_TABLE', os.path.join(ROOT, 'input/data_v2/202601-202605_打标/BathroomVanities_202601-202605_分析用.pkl'))
V11 = os.environ.get('V11', os.path.join(ROOT, 'input/data_v2/BathroomVanities_202606-202609_SKU销量预估_已打标_v11'))
OUT = os.environ.get('OUT_MD', os.path.join(HERE, '销量大数.md'))
MIN_P = 60

# ---- 统一成：月 / 父体 / 子体 / 父体销量 / 子体销量 / 价格 / BSR / 品牌 / 上架 ----
a = pd.read_pickle(Q1); a = a[a['纳入浴室柜分析']].copy()
q = pd.DataFrame({'月': a['目标月份'], '父': a['核验父ASIN'], '子': a['子ASIN'], 'P': a['父体月销量'], 'c': a['子体月销量（父体全分给导出子体）'], 'c_raw': a['子体月销量（6–9月公式）'],
                  '价格': a['商品价格'], 'bsr': a['小类BSR'], '品牌': a['品牌'], '上架': pd.to_datetime(a['上架日期'], errors='coerce'),
                  '标签': a['子体销量（卖家精灵）']})
man = json.load(open(V11 + '.analysis.json', encoding='utf-8'))['rowManifest']
keep = {(r['month'], r['childASIN']) for r in man if r['includeInBathroomAnalysis']}
v = pd.read_excel(V11 + '.xlsx', sheet_name='SKU估算明细'); v['m'] = v['目标月份'].astype(str).str[:6]
v = v[[(m, c) in keep for m, c in zip(v['m'], v['子ASIN'])]].dropna(subset=['核验父ASIN'])
w = pd.DataFrame({'月': v['m'].str[:4] + '-' + v['m'].str[4:], '父': v['核验父ASIN'], '子': v['子ASIN'], 'P': pd.to_numeric(v['父体月销量预测'], errors='coerce'),
                  'c': pd.to_numeric(v['最终SKU月销量估算'], errors='coerce'), 'c_raw': pd.to_numeric(v['最终SKU月销量估算'], errors='coerce'), '价格': pd.to_numeric(v['商品价格'], errors='coerce'),
                  'bsr': pd.to_numeric(v['目标月校验小类BSR'], errors='coerce'), '品牌': v['品牌'], '上架': pd.to_datetime(v['上架日期'], errors='coerce'), '标签': np.nan})
D = pd.concat([q, w], ignore_index=True)
D = D[D['P'] >= MIN_P]

def parents(g):
    # 父体价格：按子体分摊销量加权，没有分摊时用子体价格中位数
    def price(t):
        t = t.dropna(subset=['价格'])
        return np.average(t['价格'], weights=t['c']) if len(t) and t['c'].fillna(0).sum() > 0 else t['价格'].median()
    p = g.groupby('父').agg(P=('P', 'first'), bsr=('bsr', 'min'), 品牌=('品牌', 'first'), 上架=('上架', 'min'), 子体=('子', 'nunique'), 分摊=('c', 'sum'), 原样分摊=('c_raw', 'sum'))
    p['价格'] = g.groupby('父').apply(price)
    return p

L = ['# 销量大数（2026-01～09）', '', '> 由 `销量大数.py` 生成。统一口径：浴室柜小类目、父体月销 ≥ 60 件。销量都是卖家精灵的预测值，不是真实订单；1–5 月价格是逐月值，6–9 月是快照价。1–5 月子体销量按"父体全分给导出子体"（wen 2026-10-28）。', '']
L += ['## 1. 品类总量', '', '| 月份 | 父体数 | 子体数 | 父体月销量合计（件） | 估算销售额（万美元） | 销量加权均价 | 前 10 个父体占销量 | 2026 年上架的父体占销量 |', '| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
P = {}
for mo, g in D.groupby('月'):
    p = parents(g); P[mo] = p
    gmv = (p['P'] * p['价格']).sum(); top10 = p['P'].nlargest(10).sum() / p['P'].sum(); new = p[p['上架'] >= '2026-01-01']['P'].sum() / p['P'].sum()
    L.append(f'| {mo} | {len(p)} | {g["子"].nunique():,} | {int(p["P"].sum()):,} | {gmv / 1e4:,.0f} | ${gmv / p["P"].sum():,.0f} | {top10:.0%} | {new:.0%} |')
L += ['', '- 件数和销售额都是父体口径：件数 = 每个父体的父体月销量只取一次再相加；销售额 = 父体月销量 × 父体内子体价格（按子体分摊销量加权），不是把子体分摊销售额相加。',
      '- 这里的"品类"只含父体月销 ≥ 60 件的商品，小卖家的长尾不在里面，总量是下限。6–9 月用快照价，两段销售额不能直接比。', '']
L += ['**头部覆盖**（不设销量门槛，按父体内最好的 BSR）', '', '| 月份 | BSR 前 50 的父体 | BSR 前 100 的父体 | 前 100 名里出现的不同排名值 |', '| :--- | ---: | ---: | ---: |']
for mo, g in pd.concat([q, w], ignore_index=True).groupby('月'):
    b = g.groupby('父')['bsr'].min()
    L.append(f'| {mo} | {int((b <= 50).sum())} | {int((b <= 100).sum())} | {g.loc[g["bsr"] <= 100, "bsr"].nunique()} |')
L += ['', '上半年和 6–9 月的头部覆盖相当；上半年父体少，差在 100–500 名这一段卖得少，跨过 60 件的父体少，更像淡季。', '']

L += ['## 2. 头部是否合理', '', '| 月份 | 第 1 名父体月销 | 第 10 名 | 第 50 名 | BSR 前 10 的父体月销中位 | BSR 41–60 的父体月销中位 |', '| :--- | ---: | ---: | ---: | ---: | ---: |']
for mo, p in P.items():
    s = p['P'].sort_values(ascending=False).values
    L.append(f'| {mo} | {s[0]:,.0f} | {s[9]:,.0f} | {s[49]:,.0f} | {p[p.bsr <= 10]["P"].median():,.0f} | {p[(p.bsr > 40) & (p.bsr <= 60)]["P"].median():,.0f} |')
br = pd.concat({mo: p.groupby('品牌')['P'].sum() for mo, p in P.items()}, axis=1).fillna(0)
top = br.sum(axis=1).nlargest(8).index
L += ['', '**销量最大的 8 个品牌（父体月销量合计，件）**', '', '| 品牌 | ' + ' | '.join(br.columns) + ' |', '| :--- |' + ' ---: |' * len(br.columns)]
for b in top: L.append(f'| {b} | ' + ' | '.join(f'{x:,.0f}' for x in br.loc[b]) + ' |')
L.append('')

L += ['## 3. 子体分摊', '', '| 月份 | 子体×月行 | 估算为 0 的行 | 按原始流量词占比分摊时落到导出子体的比例 | 父体内第一大子体占比（中位） | 有子体销量的父体中，子体数中位 |', '| :--- | ---: | ---: | ---: | ---: | ---: |']
for mo, g in D.groupby('月'):
    p = P[mo]; s = g.groupby(['父'])['c'].agg(lambda t: t.max() / t.sum() if t.sum() > 0 else np.nan).dropna()
    L.append(f'| {mo} | {len(g):,} | {(g["c"].fillna(0) == 0).mean():.0%} | {p["原样分摊"].sum() / p["P"].sum():.0%} | {s.median():.0%} | {p[p["分摊"] > 0]["子体"].median():.0f} |')
# 相邻月同一子体在父体里的占比是否稳定
D['share'] = D['c'] / D.groupby(['月', '父'])['c'].transform('sum')
pairs = [('2026-01', '2026-02'), ('2026-02', '2026-03'), ('2026-03', '2026-04'), ('2026-04', '2026-05'), ('2026-05', '2026-06'), ('2026-06', '2026-07'), ('2026-07', '2026-08'), ('2026-08', '2026-09')]
L += ['', '**相邻两个月，同一父体里同一子体的分摊占比是否稳定**', '', '| 月份对 | 两月都有的子体 | 占比的相关 | 占比变化中位（百分点） | 一个月为 0、另一个月 ≥ 20% 的子体 |', '| :--- | ---: | ---: | ---: | ---: |']
for m1, m2 in pairs:
    x = D[D['月'] == m1][['父', '子', 'share']].merge(D[D['月'] == m2][['父', '子', 'share']], on=['父', '子']).dropna()
    flip = (((x.share_x == 0) & (x.share_y >= .2)) | ((x.share_y == 0) & (x.share_x >= .2))).mean()
    L.append(f'| {m1} → {m2} | {len(x):,} | {spearmanr(x.share_x, x.share_y).correlation:.2f} | {(x.share_x - x.share_y).abs().median() * 100:.1f} | {flip:.0%} |')
L += ['', '- 1–5 月按"父体全分给导出子体"后，父体销量几乎全部落到导出子体上；上表这一列给的是重新分配之前的原始比例。', '- 6→7 月、8→9 月的高相关是规则造成的：v11 规定 6 月复用 7 月、8 月复用 9 月的流量词数。真正独立的两个月看 1→2 到 5→6 月和 7→8 月；5→6 月跨了新旧两套流程。', '']

# 亚马逊"过去一个月购买 X+"标签（只有旧流程的月份有）
t = D[D['标签'].notna()].copy()
L += [f'## 4. 用亚马逊"过去一个月购买 X+"标签检验（{"、".join(sorted(t["月"].unique()))} 有）', '',
      f'- 有标签的子体×月：{len(t)} 行，标签值只有 {"、".join(str(int(x)) for x in sorted(t["标签"].unique()))} 几档，是亚马逊给的下限。',
      f'- 子体估算 ≥ 标签下限：{(t["c"] >= t["标签"]).mean():.0%}；低于下限一半：{(t["c"] < t["标签"] / 2).mean():.0%}；估算为 0：{(t["c"].fillna(0) == 0).mean():.0%}。']
pb = t.groupby(['月', '父'])['标签'].sum().rename('标签和').reset_index().merge(D.groupby(['月', '父'])['P'].first().reset_index(), on=['月', '父'])
L += [f'- 父体层面：有标签的父体 {len(pb)} 个，父体预测 ≥ 子体标签下限之和的 {(pb["P"] >= pb["标签和"]).mean():.0%}。']
qq = q[q['P'] >= MIN_P]
hi = qq[qq['c'] >= 100]; mid = qq[(qq['c'] >= 50) & (qq['c'] < 100)]
L += [f'- 反过来看：子体估算 ≥ 100 件的 {len(hi)} 行里有标签的 {hi["标签"].notna().mean():.0%}；估算 50–99 件的 {len(mid)} 行里有标签的 {mid["标签"].notna().mean():.0%}。标签只在 ≥ 50 件时出现，只能检验"有没有低估"，查不出高估。', '']

# 口径风险：非整柜商品、同一产品挂多个父体
PAT = r'pedestal sink (?:storage )?cabinet|under[ -]?sink (?:storage )?cabinet for pedestal|pedestal (?:sink )?(?:storage|organizer)'
titles = pd.concat([a[['目标月份', '核验父ASIN', '商品标题']].set_axis(['月', '父', '标题'], axis=1), pd.DataFrame({'月': w['月'], '父': w['父'], '标题': v['商品标题']})])
ped = titles[titles['标题'].astype(str).str.contains(PAT, case=False, regex=True)].drop_duplicates(['月', '父'])
L += ['## 5. 口径风险', '', '| 月份 | 立柱盆储物柜父体 | 占品类销量 | 其中 2026 年上架 |', '| :--- | ---: | ---: | ---: |']
for mo, p in P.items():
    h = p[p.index.isin(ped[ped['月'] == mo]['父'])]
    L.append(f'| {mo} | {len(h)} | {h["P"].sum() / p["P"].sum():.0%} | {int((h["上架"] >= "2026-01-01").sum())} |')
L += ['', '- 立柱盆储物柜是罩在立柱盆外的柜子，不带盆、不带台面。wen 2026-10-28 确认算浴室柜，不排除，形态统一打成"柱状盆"（已写进打标技能 v12；1–5 月打标表与成功判定已执行；6–9 月 v11 原表未改，在分析层统一）。',
      '- 同一产品逐月换父 ASIN：按"当月父 ASIN"计数会把一个产品算成多个。例：T4TREAM 48 寸双盆柜的同一批子体 7、8、9 月各挂一个父 ASIN。同一个月内没有子体同时挂两个父体。成功判定已改为"整个家族搬到新父 ASIN 算同一产品"。',
      '- 旧流程合并组里，组内排名完全相同、像重复读数的，每月只有 1–3 组、200–700 件，约占品类 1%–3%；其余组内排名不同，是各自在卖的链接。', '']
open(OUT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
