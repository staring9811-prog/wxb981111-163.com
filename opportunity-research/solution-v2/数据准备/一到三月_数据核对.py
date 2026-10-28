"""2026-01～03 卖家精灵旧导出（Codex 处理版）数据核对：维度、父体预测销量、子体分摊、BSR、价格。
只输出汇总数字，不输出原始行。
输入：Q1_RAW（含 2026-01/02/03 子目录，每月取最新的"销量_output.xlsx"）、V11（6–9 月 v11 打标表，不含扩展名）。
输出：OUT_MD（核对报告）。用法：python3 -I 一到三月_数据核对.py"""
import os, json, numpy as np, pandas as pd
from scipy.stats import spearmanr
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
Q1 = os.environ.get('Q1_RAW', os.path.join(ROOT, 'input/data_v2/raw_202601-202603'))
V11 = os.environ.get('V11', os.path.join(ROOT, 'input/data_v2/BathroomVanities_202606-202609_SKU销量预估_已打标_v11'))
OUT = os.environ.get('OUT_MD', os.path.join(HERE, '一到三月_数据核对.md'))
MONTHS = ['01', '02', '03']
BINS = [0, 10, 20, 50, 100, 200, 500, 1e9]; LAB = ['1–10', '11–20', '21–50', '51–100', '101–200', '201–500', '>500']

def is_vanity(s):  # 小类目可能是多行，任一行是浴室柜即算
    return any(x.strip() in ('Bathroom Vanities', 'Bathroom Vanity Suites') for x in str(s).splitlines())

def load_q1(m):
    x = pd.read_excel(f'{Q1}/2026-{m}/2026.{m} 销量_output.xlsx', sheet_name=0)
    x['月'] = f'2026-{m}'; x['bsr'] = pd.to_numeric(x['小类BSR'], errors='coerce')
    x['价格'] = pd.to_numeric(x['价格($)'], errors='coerce'); x['浴室柜'] = x['小类目'].map(is_vanity)
    x['P'] = x['父ASIN'].map(x.groupby('父ASIN')['月销量'].agg(lambda s: s.mode().iloc[0]))
    return x

def load_v11():
    a = json.load(open(V11 + '.analysis.json', encoding='utf-8'))
    keep = {(r['month'], r['childASIN']) for r in a['rowManifest'] if r['includeInBathroomAnalysis']}
    v = pd.read_excel(V11 + '.xlsx', sheet_name='SKU估算明细')
    v['月'] = v['目标月份'].astype(str).str[:6]
    v = v[[(m, c) in keep for m, c in zip(v['月'], v['子ASIN'])]].dropna(subset=['核验父ASIN']).copy()
    v['bsr'] = pd.to_numeric(v['目标月校验小类BSR'], errors='coerce'); v['P'] = pd.to_numeric(v['父体月销量预测'], errors='coerce')
    v['销量'] = pd.to_numeric(v['最终SKU月销量估算'], errors='coerce')
    return v

def ratio_disp(b):
    b = b.dropna(); return b.max() / b.min() if len(b) >= 2 and b.min() > 0 else np.nan

def within_corr(g, s, b):
    g = g.dropna(subset=[s, b]); g = g[g[s] > 0]
    if len(g) < 4 or g[b].nunique() < 2 or g[s].nunique() < 2: return np.nan
    return spearmanr(g[s], g[b]).correlation

Q = {m: load_q1(m) for m in MONTHS}; V = load_v11()
L = ['# 2026-01～03 数据核对（卖家精灵旧导出，Codex 处理版）', '',
     '> 由 `一到三月_数据核对.py` 生成。每月用最新的"销量_output.xlsx"（2026-07-01 保存）；6–9 月对照用 v11 打标表（只取纳入浴室柜分析的行）。', '']

# 1. 规模与维度
L += ['## 1. 规模与维度', '', '| 月份 | 子体行 | 父体 | 非浴室柜小类目行 | 父体月销 < 60 件的父体 | 父体月销量合计 |', '| :--- | ---: | ---: | ---: | ---: | ---: |']
for m, x in Q.items():
    p = x[x['浴室柜']].groupby('父ASIN')['P'].first()
    L.append(f'| 2026-{m} | {len(x):,} | {x["父ASIN"].nunique()} | {int((~x["浴室柜"]).sum())} | {int((p < 60).sum())} | {int(p.sum()):,} |')
L += ['', '- 收录口径：行级"月销量"的 5% 分位约 50 件，6–9 月是父体月销 ≥ 60 件。合并分析时要统一成父体月销 ≥ 60 件。',
      '- 价格是逐月值：同一子体相邻两月价格不同的比例见第 5 节；6–9 月用的是一个当前快照价。', '']

# 2. 父体预测销量
L += ['## 2. 父体预测销量：BSR 档位对应的父体月销量中位数', '', '| 月份 | ' + ' | '.join(LAB) + ' | BSR 与父体销量相关 |', '| :--- |' + ' ---: |' * (len(LAB) + 1)]
def bsr_row(name, g):
    med = g.groupby(pd.cut(g['bsr'], BINS, labels=LAB), observed=False)['P'].median()
    gg = g.dropna(subset=['bsr'])
    return f'| {name} | ' + ' | '.join('—' if pd.isna(v) else f'{v:.0f}' for v in med.values) + f' | {spearmanr(gg["bsr"], gg["P"]).correlation:.2f} |'
for m, x in Q.items():
    L.append(bsr_row(f'2026-{m}', x[x['浴室柜']].groupby('父ASIN').agg(P=('P', 'first'), bsr=('bsr', 'min'))))
for mo, g in V.groupby('月'):
    L.append(bsr_row(f'{mo[:4]}-{mo[4:]}（v11）', g.groupby('核验父ASIN').agg(P=('P', 'first'), bsr=('bsr', 'min'))))
L += ['', '结论：父体层面的预测销量和 6–9 月是同一把尺子，BSR 越靠前销量越高，档位中位数基本重合。', '']

# 3. 子体分摊
L += ['## 3. 子体分摊：子体合计 vs 父体', '', '| 月份 | 父体销量合计 | 子体分摊合计 | 差额 | 只列出 1 行的父体 | 整父体无流量词 | 触发封顶条件的行 | 其中按封顶改写 | 与"父体×占比"不符的行 | 其中属于旧流程合并 |', '| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
for m, x in Q.items():
    y = x[x['浴室柜']].copy()
    pa = y.groupby('父ASIN').agg(P=('P', 'first'), alloc=('流量推算销量', 'sum'), n=('ASIN', 'size'),
                                 kw=('流量词', lambda s: (s.fillna(0) > 0).any()))
    capped = y[(y['子体销量'] > 0) & (y['月销量'] > 4.5 * y['子体销量'])]
    cap_used = int(((capped['流量推算销量'] - 1.5 * capped['子体销量']).abs() < 0.6).sum())
    off = (y['流量推算销量'] - y['月销量'] * y['流量词占比']).abs() > 0.6
    L.append(f'| 2026-{m} | {int(pa.P.sum()):,} | {int(pa.alloc.sum()):,} | {int(pa.P.sum() - pa.alloc.sum()):,} | {int((pa.n == 1).sum())} | {int(((pa.n > 1) & ~pa.kw).sum())} | {len(capped)} | {cap_used} | {int(off.sum())} | {int((off & y["逻辑父体编码"].notna()).sum())} |')
L += ['', '- 子体合计小于父体，主要是导出表只列了部分子体：没列出的子体在流量词表里有份额，这部分销量没有落到任何一行。6–9 月同样只分摊给已核验的子体。',
      '- 没有流量词的子体按 0 计（wen 2026-10-28 确认：没有流量词就按没有流量判断）。',
      '- "数据说明"页写了旧版封顶规则（父体 > 4.5 × 子体销量时，子体 = 1.5 × 子体销量），但最终版没有一行按它改写。子体分摊和 6–9 月是同一个公式：父体月销量 × 子体流量词占比。',
      '- 约 5% 的行和这个公式对不上，近一半来自旧流程的"v5 合并"（把同一产品的几个父 ASIN 并成一组后重新分配）。分析用表另加一列"子体月销量（6–9 月公式）"，原列不动。', '']

# 4. BSR 是谁的排名
L += ['## 4. 子体 BSR 是子体自己的排名吗', '', '| 月份 | 多子体父体 | 子体 BSR 完全相同 | 最大/最小 ≤ 3 倍 | 子体销量最大/最小（中位） | 子体销量与 BSR 的相关（中位） |', '| :--- | ---: | ---: | ---: | ---: | ---: |']
def bsr_line(name, g, fam, sales):
    r = g.groupby(fam)['bsr'].apply(ratio_disp).dropna()
    c = g.groupby(fam).apply(lambda t: within_corr(t, sales, 'bsr')).dropna()
    s = g[g[sales] > 0].groupby(fam)[sales].agg(lambda t: t.max() / t.min() if len(t) >= 2 else np.nan).dropna()
    return f'| {name} | {len(r)} | {(r == 1).mean():.0%} | {(r <= 3).mean():.0%} | {s.median():.0f} 倍 | {c.median():+.2f} |'
for m, x in Q.items():
    L.append(bsr_line(f'2026-{m}', x[x['浴室柜']], '父ASIN', '流量推算销量'))
for mo, g in V.groupby('月'):
    L.append(bsr_line(f'{mo[:4]}-{mo[4:]}（v11）', g, '核验父ASIN', '销量'))
L += ['', '结论：同一父体里子体销量能差十几到二十几倍，子体 BSR 却几乎不随子体销量变化，九成父体内子体 BSR 相差不到 3 倍。两份数据里的子体 BSR 基本是父体排名在不同时点的读数，不是子体自己的排名。', '']

# 5. 价格
a = Q['01'][['ASIN', '价格']].merge(Q['02'][['ASIN', '价格']], on='ASIN', suffixes=('1', '2')).merge(Q['03'][['ASIN', '价格']].rename(columns={'价格': '价格3'}), on='ASIN')
L += ['## 5. 价格', '', f'- 1–3 月都出现的子体 {len(a):,} 个：1 月与 2 月价格不同 {(a.价格1 != a.价格2).mean():.0%}，2 月与 3 月不同 {(a.价格2 != a.价格3).mean():.0%}。说明是逐月价格。', '']

# 6. 合并、旧打标
L += ['## 6. 旧流程的其他处理', '',
      '- "逻辑父体编码"是旧流程把同一产品的多个父 ASIN 并成一组的结果（如 ARIEL-001），每月约 20 组，可作为 SPU 归并的参考。',
      '- 旧打标文件（_tagged_size_v2）按子体月销 > 10/20 件筛过行，且台面和台盆混在一列，词表和 v11 不一致，不沿用；本次按 v11 规则全量重打。', '']
# 7. 下载与匹配完整性：同一子体/父体跨月是否接得上（错配会让相关断开）
L += ['## 7. 下载与匹配完整性', '', '| 月份 | 行 | 重复子体行 | 月份标签不对 | 缺父 ASIN | 父体内占比之和 > 100% | 占比与流量词不成比例的父体 |', '| :--- | ---: | ---: | ---: | ---: | ---: | ---: |']
for m, x in Q.items():
    kw = pd.to_numeric(x['流量词'], errors='coerce'); y = x[(x['流量词占比'] > 0) & kw.notna()].assign(den=lambda t: pd.to_numeric(t['流量词']) / t['流量词占比'])
    bad = y.groupby('父ASIN')['den'].agg(lambda t: (t.max() - t.min()) / t.median() if len(t) > 1 else 0)
    L.append(f'| 2026-{m} | {len(x):,} | {int(x["ASIN"].duplicated().sum())} | {int((x["月份"] != f"2026-{m}").sum())} | {int(x["父ASIN"].isna().sum())} | {int((x.groupby("父ASIN")["流量词占比"].sum() > 1.01).sum())} | {int((bad > 0.02).sum())} |')
K = {f'2026-{m}': pd.to_numeric(x.set_index('ASIN')['流量词'], errors='coerce') for m, x in Q.items()}
PP = {f'2026-{m}': x.groupby('父ASIN')['P'].first() for m, x in Q.items()}
for mo, g in V.groupby('月'):
    k = f'{mo[:4]}-{mo[4:]}'; K[k] = pd.to_numeric(g.set_index('子ASIN')['流量词数量'], errors='coerce'); PP[k] = g.groupby('核验父ASIN')['P'].first()
def link(D, a, b, far):
    s = pd.concat([D[a].rename('a'), D[b].rename('b')], axis=1, join='inner').dropna(); s = s[(s.a > 0) & (s.b > 0)]
    return f'| {a} → {b} | {len(s):,} | {spearmanr(s.a, s.b).correlation:.2f} | {(s.b / s.a).median():.2f} | {((s.b / s.a > far) | (s.a / s.b > far)).mean():.1%} |'
L += ['', '**同一子体的流量词数跨月是否接得上**（6→7 月、8→9 月是复用规则，不列）', '', '| 月份对 | 子体 | 相关 | 后月/前月中位 | 相差 10 倍以上 |', '| :--- | ---: | ---: | ---: | ---: |']
L += [link(K, a, b, 10) for a, b in [('2026-01', '2026-02'), ('2026-02', '2026-03'), ('2026-03', '2026-06'), ('2026-07', '2026-08')]]
L += ['', '| 月份 | ' + ' | '.join(K) + ' |', '| :--- |' + ' ---: |' * len(K),
      '| 有流量词的子体，流量词数中位 | ' + ' | '.join(f'{s[s > 0].median():.0f}' for s in K.values()) + ' |',
      '| 流量词数 P90 | ' + ' | '.join(f'{s[s > 0].quantile(.9):.0f}' for s in K.values()) + ' |']
L += ['', '**同一父体的月销量跨月是否接得上**', '', '| 月份对 | 父体 | 相关 | 后月/前月中位 | 相差 3 倍以上 |', '| :--- | ---: | ---: | ---: | ---: |']
L += [link(PP, a, b, 3) for a, b in [('2026-01', '2026-02'), ('2026-02', '2026-03'), ('2026-03', '2026-06'), ('2026-07', '2026-08')]]
L += ['', '结论：没有发现下载或匹配错误。流量词和父体销量跨月接得上，接续程度和 6–9 月自己相邻月份相当；流量词数量级与 6–9 月一致，是同一种"全部流量词"。3 月有 3 行缺父 ASIN、没有流量词，影响可忽略。', '']
open(OUT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
