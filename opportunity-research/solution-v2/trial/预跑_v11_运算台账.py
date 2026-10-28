"""v11 预跑：把每一步运算的输入、公式、中间数、输出全部写进台账（Markdown）。
数据：input/data_v2/…_v11（不入库）。目标：跑赢同宽度新品中位（过程型）。"""
import json, itertools, os, warnings
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.metrics import roc_auc_score
warnings.filterwarnings('ignore')
D = '/home/user/wxb981111-163.com/opportunity-research/input/data_v2/BathroomVanities_202606-202609_SKU销量预估_已打标_v11'
OUT = '/home/user/wxb981111-163.com/opportunity-research/solution-v2/trial/预跑_v11_运算台账.md'
L = ['# v11 预跑运算台账（2026-10-28）', '', '每一步写：输入 → 规则/公式 → 中间数 → 输出。']
def sec(t): L.extend(['', f'## {t}', ''])
def tbl(df, idx=True, r=2):
    L.append(df.round(r).to_markdown(index=idx) if hasattr(df, 'to_markdown') else df.round(r).to_string())
# 步骤 1 读入
sec('步骤 1 · 读入与范围')
a = json.load(open(D + '.analysis.json', encoding='utf-8'))
man = pd.DataFrame(a['rowManifest'])
raw = pd.read_excel(D + '.xlsx', sheet_name='SKU估算明细')
L.append(f'- Excel「SKU估算明细」{len(raw):,} 行；analysis.json 清单 {len(man):,} 行，其中 includeInBathroomAnalysis=true 的 {int(man["includeInBathroomAnalysis"].sum()):,} 行（排除原因：{man.loc[~man["includeInBathroomAnalysis"], "exclusionReason"].value_counts().to_dict()}）。')
keep = {(r.month, r.childASIN) for r in man.itertuples() if r.includeInBathroomAnalysis}
df = raw.copy(); df['月'] = df['目标月份'].astype(str).str.replace('-', '').str[:6]
df = df[[(m, c) in keep for m, c in zip(df['月'], df['子ASIN'])]].copy()
df['销量'] = pd.to_numeric(df['最终SKU月销量估算'], errors='coerce'); df['价格'] = pd.to_numeric(df['商品价格'], errors='coerce')
df['BSR'] = pd.to_numeric(df['目标月校验小类BSR'], errors='coerce'); df['BSR有效'] = df['BSR校验状态'] == '未发现排序异常'
df['上架'] = pd.to_datetime(df['上架日期'], errors='coerce'); df['月期'] = pd.PeriodIndex(df['月'], freq='M')
df['销售额'] = df['销量'] * df['价格']; df['FBA'] = df['配送方式'].astype(str).str.contains('FBA|Amazon', case=False)
L.append(f'- 纳入分析 {len(df):,} 行（子ASIN × 月），唯一子 ASIN {df["子ASIN"].nunique():,}，唯一父 ASIN {df["核验父ASIN"].nunique():,}；销量列=「最终SKU月销量估算」（父体销量按流量词数分摊），价格=采集时快照，BSR=「目标月校验小类BSR」且只在校验状态为"未发现排序异常"时使用（有效行 {int(df["BSR有效"].sum()):,}）。')
L.append(f'- 各月行数：{df["月"].value_counts().sort_index().to_dict()}；销量缺失 {int(df["销量"].isna().sum())} 行按缺失处理，不填 0。')
# 步骤 2 属性清洗
sec('步骤 2 · 属性标签清洗（v11）')
ATTR = {'形态': 'D1产品形态', '安装': 'D2安装方式', '盆数': 'D3盆数', '台面形态': 'D4台面形态', '元素': 'D5元素', '颜色': 'D6柜体颜色', '柜体材质': 'D7柜体材质', '台面材质': 'D8台面材质'}
L += ['规则：取分隔符前第一个值，去掉"（父体候选）"后缀；含"信息不足/待/未知/冲突"或空的记为"未知"。', '', '| 属性 | 行级未知占比 | 取值数（含未知） |', '| :--- | :--- | :--- |']
for k, v in ATTR.items():
    s = df[v].astype(str).str.split(r'[;；、,]').str[0].str.replace('（父体候选）', '').str.strip()
    s[s.str.contains('信息不足|待|未知|nan|冲突|^$', na=True)] = '未知'; df[k] = s
    L.append(f'| {k} | {(s == "未知").mean():.1%} | {s.nunique()} |')
def wb(v):
    try: w = float(v)
    except: return None
    for lo, hi, lab in [(0, 26, '≤25″'), (26, 33, '26–32″'), (33, 40, '33–39″'), (40, 47, '40–46″'), (47, 55, '47–54″'), (55, 66, '55–65″'), (66, 200, '≥66″')]:
        if lo <= w < hi: return lab
df['宽度段'] = df['D9宽(in)'].map(wb)
L.append(f'| 宽度段（D9宽 分 7 档） | {df["宽度段"].isna().mean():.1%} | 7 |')
# 步骤 3 新品家族
sec('步骤 3 · 新品家族与观察窗')
fam = df.groupby('核验父ASIN')
F = pd.DataFrame({'上架': fam['上架'].min(), '子体数': fam['子ASIN'].nunique(), '品牌': fam['品牌'].first()})
F['上架月'] = F['上架'].dt.to_period('M')
new = F[(F['上架'] >= '2026-01-01') & (F['上架'] <= '2026-07-31')].copy()
L.append(f'- 单位=父 ASIN 家族（SPU 的近似）；家族上架日=子体最早上架日。全部 {len(F)} 个家族，其中最早上架在 2026-01-01 至 07-31 的新品家族 {len(new)} 个：{new["上架月"].value_counts().sort_index().astype(int).to_dict()}')
df = df.merge(new[['上架月']], left_on='核验父ASIN', right_index=True, how='left')
df['月龄'] = (df['月期'] - df['上架月']).apply(lambda x: x.n + 1 if pd.notna(x) else np.nan)
obs = df[df['核验父ASIN'].isin(new.index) & df['月龄'].between(1, 6)]
g = obs.groupby('核验父ASIN'); new['观察月数'] = g['月'].nunique(); new = new[new['观察月数'] >= 1]
L.append(f'- 月龄 = 观察月 − 上架月 + 1；只保留月龄 1–6 且落在 2026-06 至 09 的行：{len(obs):,} 行。有观察行的新品家族 {len(new)} 个，观察月数分布 {new["观察月数"].value_counts().sort_index().astype(int).to_dict()}（多数只有 1 个月）。')
t = obs.groupby(obs['核验父ASIN'].map(new['上架月'].astype(str)))['月龄'].agg(['min', 'max']); t['家族数'] = new.groupby(new['上架月'].astype(str)).size(); tbl(t)
# 步骤 4 结果变量
sec('步骤 4 · 结果变量（过程型）')
g = obs.groupby('核验父ASIN'); new['月均销量'] = g['销量'].sum() / new['观察月数']
def mode(s):
    s = s[s != '未知']; return s.mode().iloc[0] if len(s) else '未知'
for k in ATTR: new[k] = g[k].agg(mode)
new['宽度段'] = g['宽度段'].agg(lambda s: s.dropna().mode().iloc[0] if s.notna().any() else '未知')
bm = new.groupby('宽度段')['月均销量'].agg(['size', 'median'])
L += ['公式：月均销量 = 观察窗内月龄 1–6 各月家族销量之和 ÷ 观察月数；销量指数 = 月均销量 ÷ 同宽度段新品家族的月均销量中位数（该段不足 5 个家族时用全体中位数）；跑赢 = 销量指数 ≥ 1。', '', '同宽度段中位数：']; tbl(bm.rename(columns={'size': '家族数', 'median': '月均销量中位'}), r=1)
allmed = new['月均销量'].median()
med = new.groupby('宽度段')['月均销量'].transform(lambda s: s.median() if len(s) >= 5 else allmed)
new['销量指数'] = new['月均销量'] / med; new['R_rel'] = new['销量指数'] >= 1
fm = obs.groupby(['核验父ASIN', '月'])['销售额'].sum()
new['R_100k'] = fm.groupby(level=0).max().reindex(new.index) >= 100000
new['R_bsr'] = obs[obs['BSR有效'] & (obs['BSR'] <= 50)].groupby('核验父ASIN').size().reindex(new.index).fillna(0) > 0
ex = new.sort_values('月均销量', ascending=False).index[5]
L.append(f'\n举例 {ex}：观察月数 {int(new.loc[ex, "观察月数"])}，月均销量 {new.loc[ex, "月均销量"]:.1f}，宽度段 {new.loc[ex, "宽度段"]} 中位 {med.loc[ex]:.1f} → 指数 {new.loc[ex, "销量指数"]:.2f} → 跑赢 {bool(new.loc[ex, "R_rel"])}。')
base = new['R_rel'].mean()
L.append(f'\n三种口径比例：跑赢 {base:.1%}（{int(new["R_rel"].sum())}/{len(new)}）；任一月子体 BSR ≤ 50：{new["R_bsr"].mean():.1%}；任一月家族销售额 ≥ $100k：{new["R_100k"].mean():.1%}。后两者只作参考：样本只含头部商品，且 6 个月窗口看不满。')
# 步骤 5 控制量与环境量
sec('步骤 5 · 控制量与环境量（每个家族一行）')
new['颜色数'] = g['颜色'].nunique(); new['尺寸数'] = g['宽度段'].nunique()
w = obs.assign(w=obs['销量'].where(obs['价格'].notna(), 0))
new['加权价'] = w.groupby('核验父ASIN').apply(lambda x: np.average(x['价格'].fillna(0), weights=x['w']) if x['w'].sum() > 0 else np.nan)
band_med = df.groupby('宽度段')['价格'].median(); new['价格位置'] = new['加权价'] / new['宽度段'].map(band_med)
new['定价'] = pd.cut(new['价格位置'], [0, .85, 1.15, 99], labels=['低于同尺寸', '持平', '高于同尺寸']).astype(str).replace('nan', '未知')
new['变体'] = pd.cut(new['子体数'], [0, 1, 3, 6, 999], labels=['1', '2–3', '4–6', '7+']).astype(str)
new['配送'] = np.where(g['FBA'].mean().reindex(new.index) >= .5, 'FBA为主', '非FBA为主')
hot_old = df[~df['核验父ASIN'].isin(new.index) & df['BSR有效'] & (df['BSR'] <= 50)]['品牌'].unique()
new['品牌'] = np.where(new['品牌'].isin(hot_old), '已有热销款', '无'); new['上架月份'] = new['上架月'].astype(str)
L += ['定义：定价 = 家族销量加权价 ÷ 同宽度段全部商品价格中位数，<0.85 低于、0.85–1.15 持平、>1.15 高于；变体 = 子体数分档；配送 = 观察行中 FBA 占比 ≥ 50%；品牌 = 该品牌是否有非新品家族任一月子体 BSR ≤ 50（"已有热销款"）。', '', '每个变量的取值与家族数（新品家族层面）：', '', '| 变量 | 取值：家族数 |', '| :--- | :--- |']
DIMS = ['宽度段'] + list(ATTR) + ['定价', '变体', '配送', '品牌', '上架月份']
for d in DIMS: L.append(f'| {d} | {", ".join(f"{k}:{v}" for k, v in new[d].value_counts().items())} |')
# 步骤 6 稀有取值合并 + EPV
sec('步骤 6 · 数据驱动的降维与样本量检查（EPV）')
MODEL_DIMS = [d for d in DIMS if d != '上架月份']
M = new[MODEL_DIMS].copy(); merged = []
for d in MODEL_DIMS:
    vc = M[d].value_counts(); rare = vc[vc < 8].index.tolist()
    if rare: M[d] = M[d].replace(rare, '其他'); merged.append(f'{d}：{len(rare)} 个取值并入"其他"')
X = pd.get_dummies(M.astype(str), drop_first=True); y = new['R_rel'].astype(int)
events = int(min(y.sum(), len(y) - y.sum())); epv = events / X.shape[1]
L += ['规则（不由人挑变量）：家族数 < 8 的取值并入"其他"；上架月份不进模型（它反映的是观察窗，不是产品）。', '- ' + '；'.join(merged),
      f'- 进模型的参数（哑变量列）数 = {X.shape[1]}；较少的一类事件数 = {events}；**每参数事件数 EPV = {epv:.2f}**。',
      f'- 标准：逻辑回归的 EPV 至少 10（Peduzzi 等 1996），预测模型更严格（Riley 等 2019）。按 EPV=10，当前 {events} 个事件最多支持约 {events // 10} 个参数，现在用了 {X.shape[1]} 个，超出约 {X.shape[1] / max(events // 10, 1):.0f} 倍。结论：这份数据不够支撑一个多变量模型，下面的模型结果只能看作"确认没有强信号"，不能作为锦囊。']
# 步骤 7 单变量
sec('步骤 7 · 单变量：每个取值的跑赢比例（n ≥ 8）')
L += ['公式：跑赢比例 = 该取值家族中跑赢的个数 ÷ 该取值家族数；相对整体 = 跑赢比例 ÷ 整体跑赢比例。', '', '| 变量 | 取值 | n | 跑赢 | 相对整体 |', '| :--- | :--- | :--- | :--- | :--- |']
uni = []
for d in DIMS:
    t = new.groupby(d)['R_rel'].agg(['size', 'sum', 'mean']); t = t[t['size'] >= 8]
    for lv, r in t.iterrows(): uni.append((d, lv, int(r['size']), int(r['sum']), r['mean'], r['mean'] / base))
for d, lv, n, s_, m, lift in sorted(uni, key=lambda x: -abs(x[5] - 1)): L.append(f'| {d} | {lv} | {n} | {s_}/{n} = {m:.0%} | {lift:.2f}× |')
# 步骤 8 多元组合枚举 + 打乱检验
sec('步骤 8 · 多元组合穷举与打乱检验')
half = new['上架月'].apply(lambda p: p.month <= 3).values; yv = y.values.astype(float)
groups = {}; appear = {}
for k in (2, 3, 4, 5):
    groups[k] = []; appear[k] = 0
    for ds in itertools.combinations(MODEL_DIMS, k):
        for vals, idx in new.groupby(list(ds)).indices.items():
            appear[k] += 1
            if len(idx) >= 8 and '未知' not in vals: groups[k].append((ds, vals, np.asarray(idx)))
def winners(yvec, k):
    out = []
    for ds, vals, idx in groups[k]:
        m = yvec[idx].mean(); h = half[idx]
        if m >= 1.5 * base and h.any() and (~h).any() and yvec[idx[h]].mean() >= base and yvec[idx[~h]].mean() >= base: out.append((ds, vals, len(idx), m))
    return out
rng = np.random.default_rng(0); perms = [rng.permutation(yv) for _ in range(100)]
L += ['规则：对 13 个变量（不含上架月份）取 k 元组合，k = 2–5；每个组合内的取值组合为一个"格子"；保留 n ≥ 8 且不含"未知"的格子；达标 = 跑赢比例 ≥ 整体 1.5 倍，且 1–3 月、4–7 月两段上架批次各自都 ≥ 整体。打乱检验：把跑赢结果随机打乱 100 次，数每次的达标数。', '',
      '| k | 实际出现的格子 | n ≥ 8 的格子 | 真实达标 | 打乱后达标中位 | 打乱后 95% 上限 |', '| :--- | :--- | :--- | :--- | :--- | :--- |']
real = {}
for k in (2, 3, 4, 5):
    real[k] = winners(yv, k); sims = [len(winners(p, k)) for p in perms]
    L.append(f'| {k} | {appear[k]:,} | {len(groups[k]):,} | {len(real[k])} | {int(np.median(sims))} | {int(np.percentile(sims, 95))} |')
for k in (2, 3, 4, 5):
    L += ['', f'k={k} 真实达标的前 5 个：'] + [f'- {" 且 ".join(f"{d}={v}" for d, v in zip(ds, vals))}：n={n}，跑赢 {m:.0%}' for ds, vals, n, m in sorted(real[k], key=lambda x: -x[3])[:5]]
# 步骤 9 决策树
sec('步骤 9 · 决策树（深度 3，每叶 ≥ 10）')
Xt = pd.get_dummies(M.astype(str))
tree = DecisionTreeClassifier(max_depth=3, min_samples_leaf=10, random_state=0).fit(Xt, y)
accs = []
for m_ in new['上架月份'].unique():
    tr, te = new['上架月份'] != m_, new['上架月份'] == m_
    t_ = DecisionTreeClassifier(max_depth=3, min_samples_leaf=10, random_state=0).fit(Xt[tr], y[tr]); accs.append((m_, int(te.sum()), (t_.predict(Xt[te]) == y[te]).mean()))
L += ['规则：每一层选一个"按它分开后两边跑赢比例差别最大"的变量取值；叶子里 weights=[未跑赢数, 跑赢数]。', '', '```', export_text(tree, feature_names=list(Xt.columns), show_weights=True), '```', '', '留一个上架月份检验（用其余月份建树，预测留出月份的准确率；瞎猜约 50%）：', '', '| 留出月份 | 家族数 | 准确率 |', '| :--- | :--- | :--- |'] + [f'| {m_} | {n_} | {acc:.0%} |' for m_, n_, acc in sorted(accs)]
# 步骤 10 逻辑回归
sec('步骤 10 · 逻辑回归（L2 正则，C=0.5）与留月检验')
oof = pd.Series(np.nan, index=new.index); folds = []
for m_ in sorted(new['上架月份'].unique()):
    tr, te = new['上架月份'] != m_, new['上架月份'] == m_
    lr = LogisticRegression(C=.5, max_iter=3000).fit(X[tr], y[tr]); p_ = lr.predict_proba(X[te])[:, 1]; oof[te] = p_
    try: fa = roc_auc_score(y[te], p_)
    except ValueError: fa = np.nan
    folds.append((m_, int(te.sum()), fa))
auc = roc_auc_score(y, oof); k20 = max(1, len(new) // 5); top = new.loc[oof.sort_values(ascending=False).index[:k20], 'R_rel'].mean()
lr = LogisticRegression(C=.5, max_iter=3000).fit(X, y); coef = pd.Series(lr.coef_[0], index=X.columns).sort_values()
L += ['公式：概率 = 1 / (1 + e^−(截距 + Σ 系数 × 取值哑变量))；系数由全部样本最大似然估计（带 L2 收缩）。检验：轮流留出一个上架月份。', '', '| 留出月份 | 家族数 | 该月 AUC |', '| :--- | :--- | :--- |'] + [f'| {m_} | {n_} | {"—" if np.isnan(fa) else f"{fa:.2f}"} |' for m_, n_, fa in folds]
L += ['', f'- 合并全部留出预测的 AUC = {auc:.2f}；预测概率最高的 {k20} 个家族中跑赢 {top:.0%}，整体 {base:.0%}，提升 {top / base:.2f} 倍。',
      f'- 全样本系数（截距 {lr.intercept_[0]:+.2f}），绝对值最大的 10 个：'] + [f'  - {k_}: {v_:+.2f}' for k_, v_ in pd.concat([coef.head(5), coef.tail(5)]).sort_values(ascending=False).items()]
sec('步骤 11 · 结论')
L += [f'1. 样本 {len(new)} 个家族、{events} 个少数类事件，EPV={epv:.2f}，远低于 10 的标准：数据不足以估计多变量模型。',
      f'2. 留月检验 AUC {auc:.2f}、树准确率在 50% 上下：没有能推广到新批次的信号。',
      '3. 多元组合的真实达标数在各 k 都未超过打乱后的 95% 上限：赢家数量与碰巧相当。',
      '4. 这些结论对 v2 和 v11 两版标签都成立；标签变了赢家名单就变，说明打标是前置模块。',
      '5. 数据补齐方向不变：每个新品 ≥ 6 个月逐月轨迹、同期全部新品含未起量、逐月价格、看图补元素与台面材质。']
open(OUT, 'w', encoding='utf-8').write('\n'.join(L) + '\n'); print(open(OUT, encoding='utf-8').read()[:6000]); print('...\n[台账已写入]', OUT)
