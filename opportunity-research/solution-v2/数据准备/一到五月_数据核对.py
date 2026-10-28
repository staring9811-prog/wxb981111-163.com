"""2026-01～05 卖家精灵旧导出（Codex 处理版）数据核对：维度、父体预测销量、子体分摊、BSR、价格、下载与匹配完整性。
只输出汇总数字，不输出原始行。
输入：RAW（含 2026-MM 子目录，每月取最新的"2026.MM 销量_output.xlsx"）、MONTHS（默认 01,02,03,04,05）、V11（6–9 月 v11 打标表，不含扩展名）。
输出：OUT_MD（核对报告）。用法：python3 -I 一到五月_数据核对.py"""
import os, json, numpy as np, pandas as pd
from scipy.stats import spearmanr
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
RAW = os.environ.get('RAW', os.path.join(ROOT, 'input/data_v2/raw_202601-202605'))
V11 = os.environ.get('V11', os.path.join(ROOT, 'input/data_v2/BathroomVanities_202606-202609_SKU销量预估_已打标_v11'))
OUT = os.environ.get('OUT_MD', os.path.join(HERE, '一到五月_数据核对.md'))
MONTHS = os.environ.get('MONTHS', '01,02,03,04,05').split(',')
BINS = [0, 10, 20, 50, 100, 200, 500, 1e9]; LAB = ['1–10', '11–20', '21–50', '51–100', '101–200', '201–500', '>500']

def is_vanity(s):  # 小类目可能是多行，任一行是浴室柜即算
    return any(x.strip() in ('Bathroom Vanities', 'Bathroom Vanity Suites') for x in str(s).splitlines())

def load_q(m):
    x = pd.read_excel(f'{RAW}/2026-{m}/2026.{m} 销量_output.xlsx', sheet_name=0)
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

Q = {m: load_q(m) for m in MONTHS}; V = load_v11()
span = f'2026-{MONTHS[0]}～{MONTHS[-1]}'
L = [f'# {span} 数据核对（卖家精灵旧导出，Codex 处理版）', '',
     '> 由 `一到五月_数据核对.py` 生成。每月用最新的"销量_output.xlsx"；6–9 月对照用 v11 打标表（只取纳入浴室柜分析的行）。', '']

# 1. 规模与维度
L += ['## 1. 规模与维度', '', '| 月份 | 子体行 | 父体 | 非浴室柜小类目行 | 行级月销量 5% 分位 | 父体月销 < 60 件的父体 | 父体月销量合计 |', '| :--- | ---: | ---: | ---: | ---: | ---: | ---: |']
for m, x in Q.items():
    p = x[x['浴室柜']].groupby('父ASIN')['P'].first()
    L.append(f'| 2026-{m} | {len(x):,} | {x["父ASIN"].nunique()} | {int((~x["浴室柜"]).sum())} | {x["月销量"].quantile(.05):.0f} | {int((p < 60).sum())} | {int(p.sum()):,} |')
L += ['', '- 收录口径：行级"月销量"的 5% 分位约 50 件，6–9 月是父体月销 ≥ 60 件。合并分析时统一成父体月销 ≥ 60 件。',
      '- 价格是逐月值（见第 5 节）；6–9 月用的是一个当前快照价。', '']

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
L += ['', '父体层面的预测销量和 6–9 月比较：BSR 越靠前销量越高，同档位中位数应基本重合。', '']

# 3. 子体分摊
L += ['## 3. 子体分摊：子体合计 vs 父体', '', '| 月份 | 父体销量合计 | 子体分摊合计 | 差额 | 只列出 1 行的父体 | 整父体无流量词 | 触发封顶条件的行 | 其中按封顶改写 | 与"父体×占比"不符的行 | 其中属于旧流程合并 |', '| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
for m, x in Q.items():
    y = x[x['浴室柜']].copy()
    pa = y.groupby('父ASIN').agg(P=('P', 'first'), alloc=('流量推算销量', 'sum'), n=('ASIN', 'size'),
                                 kw=('流量词', lambda s: (pd.to_numeric(s, errors='coerce').fillna(0) > 0).any()))
    capped = y[(y['子体销量'] > 0) & (y['月销量'] > 4.5 * y['子体销量'])]
    cap_used = int(((capped['流量推算销量'] - 1.5 * capped['子体销量']).abs() < 0.6).sum())
    off = (y['流量推算销量'] - y['月销量'] * y['流量词占比']).abs() > 0.6
    L.append(f'| 2026-{m} | {int(pa.P.sum()):,} | {int(pa.alloc.sum()):,} | {int(pa.P.sum() - pa.alloc.sum()):,} | {int((pa.n == 1).sum())} | {int(((pa.n > 1) & ~pa.kw).sum())} | {len(capped)} | {cap_used} | {int(off.sum())} | {int((off & y["逻辑父体编码"].notna()).sum())} |')
L += ['', '- 子体合计小于父体，主要是导出表只列了部分子体：没导出的子体按销量太低处理（wen 2026-10-28），分析用表把父体销量全部分给导出的子体。',
      '- 没有流量词的子体按 0 计（wen 2026-10-28 确认：没有流量词就按没有流量判断）。',
      '- "数据说明"页写了旧版封顶规则（父体 > 4.5 × 子体销量时，子体 = 1.5 × 子体销量），看"其中按封顶改写"一列是否为 0；为 0 说明子体分摊和 6–9 月同一个公式：父体月销量 × 子体流量词占比。',
      '- 和这个公式对不上的少数行，多半来自旧流程的"v5 合并"（把同一产品的几个父 ASIN 并成一组后重新分配）。', '']

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
L += ['', '同一父体里子体销量能差十几到二十几倍，子体 BSR 却几乎不随子体销量变化：子体 BSR 基本是父体排名在不同时点的读数（因此按家族排名用，wen 2026-10-28 确认）。', '']

# 5. 价格：相邻两月同一子体价格是否变化
L += ['## 5. 价格', '', '| 月份对 | 两月都有的子体 | 价格不同的比例 |', '| :--- | ---: | ---: |']
for a, b in zip(MONTHS, MONTHS[1:]):
    t = Q[a][['ASIN', '价格']].merge(Q[b][['ASIN', '价格']], on='ASIN', suffixes=('_a', '_b')).dropna()
    L.append(f'| 2026-{a} → 2026-{b} | {len(t):,} | {(t["价格_a"] != t["价格_b"]).mean():.0%} |')
L += ['', '相邻月份有相当比例的价格不同，说明是逐月价格。', '']

# 6. 旧流程
L += ['## 6. 旧流程的其他处理', '',
      '- "逻辑父体编码"是旧流程把同一产品的多个父 ASIN 并成一组的结果（如 ARIEL-001），可作为 SPU 归并的参考。',
      '- 旧打标文件（_tagged_size_v2）按子体月销 > 10/20 件筛过行，且台面和台盆混在一列，词表和 v11 不一致，不沿用；本次按打标技能 v12 全量重打。', '']

# 7. 下载与匹配完整性：同一子体/父体跨月是否接得上（错配会让相关断开）
L += ['## 7. 下载与匹配完整性', '', '| 月份 | 行 | 重复子体行 | 月份标签不对 | 缺父 ASIN | 父体内占比之和 > 100% | 占比与流量词不成比例的父体 |', '| :--- | ---: | ---: | ---: | ---: | ---: | ---: |']
issues = 0
for m, x in Q.items():
    kw = pd.to_numeric(x['流量词'], errors='coerce'); y = x[(x['流量词占比'] > 0) & kw.notna()].assign(den=lambda t: pd.to_numeric(t['流量词']) / t['流量词占比'])
    bad = y.groupby('父ASIN')['den'].agg(lambda t: (t.max() - t.min()) / t.median() if len(t) > 1 else 0)
    row = [int(x['ASIN'].duplicated().sum()), int((x['月份'] != f'2026-{m}').sum()), int(x['父ASIN'].isna().sum()),
           int((x.groupby('父ASIN')['流量词占比'].sum() > 1.01).sum()), int((bad > 0.02).sum())]
    issues += row[0] + row[3] + row[4]
    L.append(f'| 2026-{m} | {len(x):,} | ' + ' | '.join(str(v) for v in row) + ' |')
K = {f'2026-{m}': pd.to_numeric(x.set_index('ASIN')['流量词'], errors='coerce') for m, x in Q.items()}
PP = {f'2026-{m}': x.groupby('父ASIN')['P'].first() for m, x in Q.items()}
for mo, g in V.groupby('月'):
    k = f'{mo[:4]}-{mo[4:]}'; K[k] = pd.to_numeric(g.set_index('子ASIN')['流量词数量'], errors='coerce'); PP[k] = g.groupby('核验父ASIN')['P'].first()
qm = [f'2026-{m}' for m in MONTHS]
pairs = list(zip(qm, qm[1:])) + [(qm[-1], '2026-06'), ('2026-07', '2026-08')]
corr = {}
def link(D, a, b, far, tag):
    s = pd.concat([D[a].rename('a'), D[b].rename('b')], axis=1, join='inner').dropna(); s = s[(s.a > 0) & (s.b > 0)]
    r = spearmanr(s.a, s.b).correlation; corr[(tag, a, b)] = r
    return f'| {a} → {b} | {len(s):,} | {r:.2f} | {(s.b / s.a).median():.2f} | {((s.b / s.a > far) | (s.a / s.b > far)).mean():.1%} |'
L += ['', '**同一子体的流量词数跨月是否接得上**（6→7 月、8→9 月是复用规则，不列；7→8 月是 6–9 月自己的对照）', '', '| 月份对 | 子体 | 相关 | 后月/前月中位 | 相差 10 倍以上 |', '| :--- | ---: | ---: | ---: | ---: |']
L += [link(K, a, b, 10, '词') for a, b in pairs]
L += ['', '| 月份 | ' + ' | '.join(K) + ' |', '| :--- |' + ' ---: |' * len(K),
      '| 有流量词的子体，流量词数中位 | ' + ' | '.join(f'{s[s > 0].median():.0f}' for s in K.values()) + ' |',
      '| 流量词数 P90 | ' + ' | '.join(f'{s[s > 0].quantile(.9):.0f}' for s in K.values()) + ' |']
L += ['', '**同一父体的月销量跨月是否接得上**', '', '| 月份对 | 父体 | 相关 | 后月/前月中位 | 相差 3 倍以上 |', '| :--- | ---: | ---: | ---: | ---: |']
L += [link(PP, a, b, 3, '销') for a, b in pairs]
ref_kw, ref_p = corr[('词', '2026-07', '2026-08')], corr[('销', '2026-07', '2026-08')]
weak = [(a, b) for (tag, a, b), r in corr.items() if (a, b) != ('2026-07', '2026-08') and r < (ref_kw if tag == '词' else ref_p) - 0.15]
# 接续偏弱时，看同一批父体的排名是否也同样变了、销量变化是否跟着排名变化走：是，就是真实的市场变动，不是错配
BB = {f'2026-{m}': x.groupby('父ASIN')['bsr'].min() for m, x in Q.items()}
for mo, g in V.groupby('月'): BB[f'{mo[:4]}-{mo[4:]}'] = g.groupby('核验父ASIN')['bsr'].min()
L += ['', '**父体销量的变化能否被排名变化解释**（排名来自亚马逊，是独立于销量估算的信号）', '', '| 月份对 | 父体 | 销量相关 | BSR 相关 | 销量变化与排名变化的相关 |', '| :--- | ---: | ---: | ---: | ---: |']
explained = {}
for a, b in pairs:
    s = pd.concat([PP[a].rename('Pa'), PP[b].rename('Pb'), BB[a].rename('ba'), BB[b].rename('bb')], axis=1, join='inner').dropna()
    s = s[(s.Pa > 0) & (s.Pb > 0) & (s.ba > 0) & (s.bb > 0)]
    rc = spearmanr(np.log(s.Pb / s.Pa), np.log(s.bb / s.ba)).correlation; explained[(a, b)] = rc
    L.append(f'| {a} → {b} | {len(s):,} | {spearmanr(s.Pa, s.Pb).correlation:.2f} | {spearmanr(s.ba, s.bb).correlation:.2f} | {rc:+.2f} |')
unexplained = [f'{a}→{b}' for a, b in weak if explained.get((a, b), 0) > -0.3]
verdict = ('没有发现下载或匹配错误：没有重复行、占比之和超标或占比与流量词不成比例；流量词和父体销量跨月接续与 6–9 月自己的 7→8 月相当'
           + ('' if not weak else f'；{"、".join(f"{a}→{b}" for a, b in weak)} 的父体销量接续偏低，但同期排名也变了，销量变化跟着排名变化走，是真实的市场变动') + '。'
           if issues == 0 and not unexplained else f'需要人工看：完整性问题 {issues} 处，接续偏弱且排名解释不了的月份对 {unexplained}。')
L += ['', '结论：' + verdict, '']
open(OUT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
