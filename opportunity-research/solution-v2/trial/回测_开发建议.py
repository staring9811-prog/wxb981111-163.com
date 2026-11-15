"""回测：站在 ASOF（默认 2026-01）出的开发建议，拿之后实际发生的核对——推荐的实现了没有、避开的是不是真不好、有没有漏掉的机会。
实际结果：ASOF 以后上架、观察期到 2026-09 已走完的新家族（做到 = 6 个月内小类前 50 或月销售额 $10 万）；市场：ASOF 前半年 vs 2026-04 至 09 的销量份额。
用法：ASOF=2026-01 python3 -I 回测_开发建议.py；输出 solution-v2/开发建议/回测_<ASOF>.md。"""
import os, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
ASOF = os.environ.get('ASOF', '2026-01')
WORK = os.environ.get('WORK', '/tmp/开发建议_work')
OUTMD = os.path.join(ROOT, f'solution-v2/开发建议/回测_{ASOF}.md')
os.environ['OUT_MD'] = os.path.join(WORK, f'_建议_{ASOF}.md')
P = os.path.join(HERE, '开发建议.py'); ns = {'__file__': P}
exec(compile(open(P, encoding='utf-8').read(), P, 'exec'), ns)
g = ns.get
Cn, pick, blank, avoid, M, prob, mat, toks = g('Cn'), g('pick'), g('blank'), g('avoid'), g('M'), g('prob'), g('mat'), g('toks')
Uf, ff, T, mi, ms, A_f = g('Uf'), g('ff'), g('T'), g('mi'), g('ms'), g('nf')['A']
in10 = g('in10'); pct = g('pct')
later = Uf[(Uf['L'] >= T) & (Uf['L'] + 5 <= mi('2026-09'))].copy()
later['p'] = prob(M, mat([toks(ff[u]) for u in later.index]))
key = lambda u: (ff[u]['主尺寸段'][0], ff[u]['台面类型'][0])
# 方案在 1 月所有候选里的名次（百分位，越小越靠前）
Cn['名次'] = Cn['p'].rank(ascending=False, pct=True)
def concept_rank(s, tp, el):
    d = Cn[(Cn['尺寸'] == s) & (Cn['台面'] == tp) & (Cn['元素'] == el)]
    return (float(d['p'].max()), float(d['名次'].min())) if len(d) else (np.nan, np.nan)

L = [f'# 回测：站在 {ASOF} 月初的开发建议，到 2026-10 实现了没有', '',
     f'> 由 `trial/回测_开发建议.py` 生成。建议只用截至 {ms(T - 1)} 的数据（见 开发建议_{ASOF}.md）；实际结果用到 2026-09 的数据。',
     '> "做到" = 上架后 6 个月内任一月小类前 50 或月销售额 ≥ $10 万。实际结果只能看 观察期已走完的新家族：'
     f'{ms(T)} 至 {ms(int(later["L"].max()))} 上架的 {len(later)} 个；之后上架的还没满 6 个月，不算。', '',
     f'这 {len(later)} 个新家族实际做到 {int(later["y"].sum())} 个，**每 10 个 {in10(later["y"].mean())} 个**（1 月时学习数据是每 10 个 {in10(g("U")["y"].mean())} 个，水平在往下走）。', '']

# 1. 推荐、避开的方案：实际
def actual(s, tp, el):
    m = [u for u in later.index if ff[u]['主尺寸段'][0] == s and ff[u]['台面类型'][0] == tp and el in ff[u]['元素']]
    m2 = [u for u in later.index if ff[u]['主尺寸段'][0] == s and ff[u]['台面类型'][0] == tp]
    return m, m2
A6 = A_f[A_f['m'].between(mi('2026-04'), mi('2026-09'))]; B6 = A_f[A_f['m'].between(T - 6, T - 1)]
def share_of(D, s, tp, el):
    m = D['尺寸段'].eq(s) & D['台面类型'].eq(tp) & D['元素集'].map(lambda t: el in t)
    return D.loc[m, 'c'].sum() / D['c'].sum()
def block(title, lst):
    out = [f'### {title}', '', '| 方案（1 月建议） | 1 月给的每 10 个做到 | 2026 实际：同尺寸 × 台面 × 元素 做到 / 家族 | 同尺寸 × 台面 做到 / 家族 | 这类的销量份额 前半年 → 2026-04 至 09 |', '| :--- | :--- | :--- | :--- | :--- |']
    for r in lst:
        m, m2 = actual(r.尺寸, r.台面, r.元素)
        a = f"{int(later.loc[m, 'y'].sum())} / {len(m)}" if m else '0 / 0（没人做）'
        b = f"{int(later.loc[m2, 'y'].sum())} / {len(m2)}" if m2 else '0 / 0'
        out.append(f"| {r.尺寸} {r.档}档 {r.台面} + {r.元素} | {in10(r.p)} | {a} | {b} | {pct(share_of(B6, r.尺寸, r.台面, r.元素))} → {pct(share_of(A6, r.尺寸, r.台面, r.元素))} |")
    return out + ['']
L += ['## 1. 1 月推荐、避开的，实际怎样', ''] + block('推荐（有先例）', pick) + block('推荐（空白方案）', blank) + block('避开', avoid)
gp = [u for u in later.index if any(ff[u]['主尺寸段'][0] == r.尺寸 and ff[u]['台面类型'][0] == r.台面 and r.元素 in ff[u]['元素'] for r in pick)]
ga = [u for u in later.index if any(ff[u]['主尺寸段'][0] == r.尺寸 and ff[u]['台面类型'][0] == r.台面 and r.元素 in ff[u]['元素'] for r in avoid)]
L += [f'合计：推荐（有先例）同类 {len(gp)} 个，做到 {int(later.loc[gp, "y"].sum())} 个（每 10 个 {in10(later.loc[gp, "y"].mean()) if gp else "—"}）；'
      f'避开同类 {len(ga)} 个，做到 {int(later.loc[ga, "y"].sum())} 个（每 10 个 {in10(later.loc[ga, "y"].mean()) if ga else "—"}）；全部 {in10(later["y"].mean())}。', '']

# 2. 漏掉的：2026 实际做到的组合，1 月怎么排
rows = []
for (s, tp), grp in later.groupby([later.index.map(lambda u: ff[u]['主尺寸段'][0]), later.index.map(lambda u: ff[u]['台面类型'][0])]):
    els = pd.Series([e for u in grp.index for e in ff[u]['元素'] if e not in ('fluted', 'reeded', '未知')]).value_counts()
    for el in els.index:
        m = [u for u in grp.index if el in ff[u]['元素']]
        if len(m) < 2: continue
        p1, rk = concept_rank(s, tp, el)
        rows.append(dict(尺寸=s, 台面=tp, 元素=el, 家族=len(m), 做到=int(later.loc[m, 'y'].sum()), 比例=later.loc[m, 'y'].mean(), 一月p=p1, 一月名次=rk,
                         家族平均p=later.loc[m, 'p'].mean()))
R = pd.DataFrame(rows).sort_values(['做到', '比例'], ascending=False)
L += ['## 2. 有没有漏掉：2026 年实际做起来的组合（同尺寸 × 台面 × 元素，至少 2 个家族），1 月怎么排的', '',
      '"1 月名次"= 这个组合在 1 月全部候选方案里的位置（前 10% = 推荐区，后 30% = 避开区）；"—" = 1 月候选里没有（尺寸不在 24 / 30 / 36 / 48″，或元素、台面不在候选）。', '',
      '| 组合 | 2026 实际 做到 / 家族 | 1 月给的每 10 个做到（最好的价位颜色） | 1 月名次 | 判断 |', '| :--- | :--- | :--- | :--- | :--- |']
for r in R.itertuples():
    if r.做到 == 0 and r.家族 < 4: continue
    if pd.isna(r.一月名次): j = '1 月没覆盖'
    elif r.比例 >= 0.5 and r.一月名次 > 0.3: j = '**漏掉**：实际好，1 月排得靠后'
    elif r.比例 >= 0.5: j = '抓到了'
    elif r.比例 < 0.3 and r.一月名次 <= 0.3: j = '**看错**：1 月排得靠前，实际不好'
    else: j = '—'
    L.append(f"| {r.尺寸} {r.台面} + {r.元素} | {r.做到} / {r.家族} | {in10(r.一月p) if pd.notna(r.一月p) else '—'} | {('前 %.0f%%' % (r.一月名次 * 100)) if pd.notna(r.一月名次) else '—'} | {j} |")
L += ['']

# 2b. 做起来的每个家族，1 月打分排在哪
later['名次'] = later['p'].rank(ascending=False, pct=True)
W_ = later[later['y'] == 1].sort_values('名次')
cap = lambda q: int((W_['名次'] <= q).sum())
L += ['### 2026 年做起来的新家族，1 月的打分排在哪', '',
      f"做起来的 {len(W_)} 个里：排在 1 月打分前 20% 的 {cap(0.2)} 个，前 50% 的 {cap(0.5)} 个，后 50% 的 {len(W_) - cap(0.5)} 个（如果打分没用，前 20% 里应该只有约 {len(W_) * 0.2:.0f} 个）。", '',
      '排在后 50%、但做起来了的（1 月会被看漏的）：', '',
      '| 单位 | 品牌 | 上架 | 主尺寸 · 价格档 · 台面 · 元素 | 颜色数 / 子体数 | 1 月打分（每 10 个） | 名次 |', '| :--- | :--- | :--- | :--- | :--- | :--- | :--- |']
for u, r in W_[W_['名次'] > 0.5].iterrows():
    f = ff[u]; L.append(f"| {u} | {r['品牌']} | {ms(int(r['L']))} | {f['主尺寸段'][0]} · {f['价格档'][0]} · {f['台面类型'][0]} · {'/'.join(e for e in f['元素'] if e not in ('fluted', 'reeded'))} | {f['_颜色数']} / {f['_变体']} | {in10(r['p'])} | 后 {(1 - r['名次']) * 100:.0f}% |")
L += ['']
# 3. 单个属性：1 月的方向在 2026 成立吗
coef = g('coef')
attrs = [t for t in coef.index if not t.startswith(('装=', '形态='))]
L += ['## 3. 1 月模型里的每个属性，2026 年方向对不对', '', '比的是 2026 年上架的新家族里"有这个属性的"和"没有的"做到的比例（不分格，样本小，只看方向）。', '',
      '| 属性 | 1 月系数（正 = 更容易做到） | 2026 有它 做到 / 家族 | 2026 没有它 | 方向 |', '| :--- | ---: | :--- | :--- | :--- |']
TKL = {u: toks(ff[u]) for u in later.index}
for t in sorted(attrs, key=lambda t: -abs(coef[t])):
    h = [u for u in later.index if t in TKL[u]]; n_ = [u for u in later.index if t not in TKL[u]]
    if len(h) < 5 or len(n_) < 5: continue
    d = later.loc[h, 'y'].mean() - later.loc[n_, 'y'].mean()
    ok = '对' if np.sign(d) == np.sign(coef[t]) else '**反了**'
    L.append(f"| {t.replace('=', '：')} | {coef[t]:+.2f} | {int(later.loc[h, 'y'].sum())} / {len(h)}（{pct(later.loc[h, 'y'].mean())}） | {pct(later.loc[n_, 'y'].mean())}（{len(n_)} 个） | {ok}（差 {d * 100:+.0f}） |")

# 4. 市场：2026 份额涨得最多的类别，1 月有没有提到
def grow(by):
    a = B6.groupby(by)['c'].sum() / B6['c'].sum(); b = A6.groupby(by)['c'].sum() / A6['c'].sum()
    return pd.DataFrame({'前': a, '后': b}).fillna(0).assign(变=lambda d: d['后'] - d['前']).sort_values('变', ascending=False)
G = grow(['尺寸段', '台面类型'])
L += ['', f'## 4. 市场：{ms(T - 6)} 至 {ms(T - 1)} → 2026-04 至 09，销量份额涨得最多 / 跌得最多的"尺寸 × 台面"', '',
      '| 尺寸 × 台面 | 份额 前 → 后 | 变化 | 1 月建议里有没有 |', '| :--- | :--- | ---: | :--- |']
rec = {(r.尺寸, r.台面) for r in list(pick) + list(blank)}; avd = {(r.尺寸, r.台面) for r in avoid}
for (s, tp), r in pd.concat([G.head(6), G.tail(4)]).iterrows():
    if tp in ('未知',) or str(tp).startswith('台面未知'): continue
    L.append(f"| {s} {tp} | {pct(r['前'])} → {pct(r['后'])} | {r['变'] * 100:+.1f} 个百分点 | {'推荐' if (s, tp) in rec else ('避开' if (s, tp) in avd else '—')} |")
L += ['', '## 5. 结论（2026-11-02 读表写，数字以上表为准）', '',
      '1. **推荐的实现了一部分，但多数没人做、验证不了**：有先例的 6 个推荐里，2026 年有人做的只有 2 个——36″ 陶瓷一体 + 农场风 1 / 1，30″ 陶瓷一体 + 竖棱 3 / 7；合计 4 / 8，每 10 个 5 个，高于全部的 3.5。空白方案 2026 年没人做。',
      '2. **"避开"没分出来**：避开同类 6 / 17，每 10 个 3.5，和全部一样；只有"低档"这一项方向对（27% 对 39%）。',
      '3. **排序有一点用，但漏掉一半**：做起来的 25 个里，8 个排在 1 月打分前 20%（瞎猜约 5 个），12 个排在后 50%。',
      '4. **漏掉的主要是"大尺寸、高档、石材台面"**：1 月模型按 2024–2025 年的经验给 48″、高档、石材台面减分，2026 年这三类反而做得好'
      '（48″ 3 / 5，高档 5 / 11，石材台面 5 / 10）；KEIKI 48″ 石材、XWNE 42″ / 60″ 石材高档、Alphabath 36″ 高档都被排在后半。'
      '其实 1 月的市场表已经有信号：48″ 搜索同比 +33%、搜索份额比销量份额高 6 个百分点、近 12 个月只有 3 个新家族——打分模型只看历史成败，没有把这些市场信号加进去。',
      '5. **另外两处市场变化没提到**：24″ 不含盆（只卖柜体）份额 3% → 6%，30″ 树脂一体 1% → 3%（1 月只推荐了 36″ 树脂一体）。',
      '6. **属性方向**：17 个属性里 10 个方向对；颜色 ≥ 2（49% 对 22%）、子体 ≥ 4（45% 对 29%）、原木色、树脂一体、低档、黑色最稳；36″、48″、石材、高档、竖棱、白色、30″ 反了。',
      '', '**改进**：打分要把"市场在往哪走"放进去（尺寸、台面的份额变化、搜索同比和缺口、近期新家族数），不能只靠历史成败；按属性的关键词（台面、元素、颜色）要补，48″ 这类信号才能在台面、元素层面也看到。']
os.makedirs(os.path.dirname(OUTMD), exist_ok=True)
open(OUTMD, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
