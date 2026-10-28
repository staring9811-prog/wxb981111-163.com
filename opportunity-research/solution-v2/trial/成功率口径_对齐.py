"""成功率口径对齐：逐个新品家族给出成功 / 未成功 / 观察中 / 数据不全，以及判定依据（哪个月、哪条线、多少值）。
口径（待 wen 逐项确认）：
- 成功单位（UNIT）：replace（默认）= 以当月核验父 ASIN 为基础，旧父体下个月消失、且一半以上子体整体搬到同一个新父体时视为同一产品（wen 2026-10-28：父体只是 MCP 抓取时的统一入口，换父体不代表新产品）；parent = 只按当月核验父 ASIN（对照）；chain = 凡共享过子 ASIN 的父体都串成一个（过粗，会把挂过老家族的新款并进老品，仅对照）。
- 新品：单位内最早子体上架日期在 2026-01 至 09。
- 观察期：上架当月为第 1 个月，连续 N 个月（WINDOW，默认 3）。
- 成功线：观察期内任一月，父体内最好的子体小类 BSR ≤ 50（BSR_RULE：all = 家族排名，共享排名照算，默认，wen 2026-10-28 确认；own = 不含共享排名；strict = 只用"未发现排序异常"的行）或 SPU 月销售额 ≥ $100,000。SPU 月销售额 = 父体月销量 × 导出子体的销量加权均价（wen 2026-10-28：没导出的子体按销量太低处理，父体销量全部归导出子体）；REV_RULE=child 时改回子体分摊销售额相加，仅作对照。
- 分母：观察期完整落在数据月份内、且观察期内至少一个月出现在表里（父体月销 ≥ 60 件）的家族。
输出：WINDOW 对应的 json（TRIAL_DUMP 目录）和终端摘要。"""
import os, re, html, json, pandas as pd
S = os.environ['TRIAL_DUMP']; N = int(os.environ.get('WINDOW', 3)); BSR_LINE, REV_LINE = 50, 100000
UNIT = os.environ.get('UNIT', 'replace'); BSR_RULE = os.environ.get('BSR_RULE', 'all'); REV_RULE = os.environ.get('REV_RULE', 'parent')
df = pd.read_pickle(S + '/df.pkl').dropna(subset=['核验父ASIN'])
OKS = {'strict': ['未发现排序异常'], 'own': ['未发现排序异常', '发现排序异常'], 'all': ['未发现排序异常', '发现排序异常', '共享排名不适用']}[BSR_RULE]
df['BSR可用'] = df['BSR'].notna() & df['BSR校验状态'].isin(OKS)
TAG = {'未发现排序异常': '', '发现排序异常': '，该月销量估算与排名顺序不一致', '共享排名不适用': '，全父体共享排名'}
# 产品链：同一子 ASIN 在不同月挂到不同核验父 ASIN 时，把这些父 ASIN 并成一个单位（并查集）
up = {p: p for p in df['核验父ASIN'].unique()}
def root(x):
    while up[x] != x: up[x] = up[up[x]]; x = up[x]
    return x
if UNIT == 'chain':
    for ps in df.groupby('子ASIN')['核验父ASIN'].unique():
        for q in ps[1:]: up[root(q)] = root(ps[0])
elif UNIT == 'replace':
    kids = {(m, p): set(g['子ASIN']) for (m, p), g in df.groupby(['月', '核验父ASIN'])}
    ms = sorted(df['月'].unique())
    for a, b in zip(ms, ms[1:]):
        pa = {p for (m, p) in kids if m == a}; pb = sorted(p for (m, p) in kids if m == b)
        for A in sorted(pa - set(pb)):  # 旧父体下个月消失
            share = {B: len(kids[(a, A)] & kids[(b, B)]) / len(kids[(a, A)]) for B in pb}
            top = max(share.values(), default=0); winners = [B for B, v in share.items() if v == top]
            # 只有一个新父体接收了至少一半子体才算整体搬家；子体平分到几个新父体是拆分，不合并
            if top >= 0.5 and len(winners) == 1: up[root(A)] = root(winners[0])
df['单位'] = df['核验父ASIN'].map(root)
members = df.groupby('单位')['核验父ASIN'].unique().map(sorted)
fam = df.groupby('单位')['上架'].min().rename('上架F')
df = df.drop(columns=[c for c in ['上架月', '月龄'] if c in df]).join(fam, on='单位')
df['上架月'] = df['上架F'].dt.to_period('M')
df = df[(df['上架F'] >= '2026-01-01') & (df['上架F'] <= '2026-09-30')].copy()
df['月龄'] = (df['月期'] - df['上架月']).apply(lambda x: x.n + 1)
first, last = df['月期'].min(), df['月期'].max()
win = df[df['月龄'].between(1, N)]

def mode(s):
    s = s[s != '未知']; return s.mode().iloc[0] if len(s) else '未知'
# 与打标技能 v12 的 PEDESTAL_FORM 一致（标题/SKU 写明即优先，FORM-PEDESTAL-PRIORITY）；6–9 月 v11 原标签按旧规则，这里在分析层统一
PEDESTAL = re.compile(r'\bpedestal\s+(?:sink|basin|under[ -]?sink)\b|\bfor\s+(?:a\s+)?pedestal\s+sinks?\b', re.I)
ped_units = set(df[(df['商品标题'].fillna('').astype(str) + ' ' + df['SKU属性'].fillna('').astype(str)).map(lambda t: bool(PEDESTAL.search(re.sub(r'\s+', ' ', html.unescape(t))))) | (df['形态'] == '柱状盆')]['单位'])
attr = df.groupby('单位').agg(宽度段=('宽度段', lambda s: s.dropna().mode().iloc[0] if s.notna().any() else '未知'),
                                  形态=('形态', mode), 台面材质=('台面材质', mode), 品牌=('品牌', 'first'), 上架月=('上架月', 'first'))

attr.loc[attr.index.isin(ped_units), '形态'] = '柱状盆'
rows = []
for f, a in attr.iterrows():
    lm = a['上架月']; end = lm + (N - 1)
    g = win[win['单位'] == f]
    ev = []  # 每个月龄的判定依据
    for m, gm in g.groupby('月龄'):
        v = gm[gm['BSR可用']]
        b = v.loc[v['BSR'].idxmin()] if len(v) else None
        if REV_RULE == 'child': rev = gm['销售额'].sum()
        else:  # 父体月销量（同月多个父体时相加）× 导出子体按分摊销量加权的价格
            pq = gm.groupby('核验父ASIN')['父体月销量预测'].first().astype(float).sum()
            pr = gm.dropna(subset=['价格']); wsum = pr['销量'].fillna(0).sum()
            price = (pr['销量'].fillna(0) * pr['价格']).sum() / wsum if wsum > 0 else pr['价格'].median()
            rev = pq * price if pd.notna(price) else 0.0
        bad = gm[~gm['BSR可用'] & gm['BSR'].notna() & (gm['BSR'] <= BSR_LINE)]
        ev.append(dict(月龄=int(m), 月份=str(gm['月期'].iloc[0]), 最好BSR=None if b is None else int(b['BSR']), BSR子体=None if b is None else b['子ASIN'], BSR状态=None if b is None else b['BSR校验状态'],
                       销售额=round(float(rev)), 无效BSR达线=int(len(bad)), 子体数=int(gm['子ASIN'].nunique())))
    hit = None
    for e in ev:
        why = []
        if e['最好BSR'] is not None and e['最好BSR'] <= BSR_LINE: why.append(f"小类 BSR {e['最好BSR']} ≤ {BSR_LINE}（子体 {e['BSR子体']}{TAG[e['BSR状态']]}）")
        if e['销售额'] >= REV_LINE: why.append(f"家族销售额 ${e['销售额']:,} ≥ $100,000")
        if why: hit = dict(月龄=e['月龄'], 月份=e['月份'], 依据='；'.join(why), 线=('BSR' if 'BSR' in why[0] else '') + ('+销售额' if len(why) == 2 else ('销售额' if 'BSR' not in why[0] else ''))); break
    if lm < first: status = '数据不全'          # 观察期前段在数据开始之前，看不到
    elif end > last: status = '观察中'          # 观察期还没走完
    elif not ev: status = '未起量'              # 观察期内一个月都没进表（不进分母）
    else: status = '成功' if hit else '未成功'
    best = min([e['最好BSR'] for e in ev if e['最好BSR'] is not None], default=None)
    rows.append(dict(单位=f, 父ASIN=list(members[f]), 品牌=a['品牌'], 上架月=str(lm), 宽度段=a['宽度段'], 形态=a['形态'], 台面=a['台面材质'], 状态=status,
                     已达线=bool(hit), 首次达线=hit, 看到的月龄=[e['月龄'] for e in ev], 最好BSR=best,
                     最高月销售额=max([e['销售额'] for e in ev], default=0), 逐月=ev))
R = pd.DataFrame(rows)
done = R[R['状态'].isin(['成功', '未成功'])]
out = {'window': N, 'unit': UNIT, 'bsr_rule': BSR_RULE, 'data': f'{first}—{last}', 'status': R['状态'].value_counts().to_dict(),
       'by_launch': R.groupby(['上架月', '状态']).size().unstack(fill_value=0).to_dict('index'),
       'rate': dict(n=int(len(done)), k=int((done['状态'] == '成功').sum())),
       'early_hit_unfinished': int(R[R['状态'].isin(['观察中', '数据不全']) & R['已达线']].shape[0]),
       'by_line': done[done['状态'] == '成功']['首次达线'].map(lambda h: h['线']).value_counts().to_dict(),
       'invalid_bsr_only': int(done[(done['状态'] == '未成功') & done['逐月'].map(lambda ev: any(e['无效BSR达线'] for e in ev))].shape[0]),
       'grid': {}, 'families': R.to_dict('records')}
for (w, f), g in done.groupby(['宽度段', '形态']): out['grid'][f'{w}|{f}'] = dict(n=int(len(g)), k=int((g['状态'] == '成功').sum()))
for w, g in done.groupby('宽度段'): out['grid'][f'{w}|all'] = dict(n=int(len(g)), k=int((g['状态'] == '成功').sum()))
# 阈值敏感性：同一批观察完整的家族，换线后成功几个
def k_with(bl, rl, both=False):
    c = 0
    for ev in done['逐月']:
        ok = [((e['最好BSR'] is not None and e['最好BSR'] <= bl), e['销售额'] >= rl) for e in ev]
        c += any((x and y) if both else (x or y) for x, y in ok)
    return c
out['sens'] = {'BSR≤50 或 ≥$10万（现行）': k_with(50, REV_LINE), '只看 BSR≤50': k_with(50, 9e18), '只看 ≥$10万': k_with(0, REV_LINE),
               'BSR≤50 且 ≥$10万': k_with(50, REV_LINE, True), 'BSR≤30 或 ≥$10万': k_with(30, REV_LINE), 'BSR≤100 或 ≥$10万': k_with(100, REV_LINE),
               'BSR≤50 或 ≥$5万': k_with(50, 50000)}
json.dump(out, open(S + f'/success_window{N}_{UNIT}_{BSR_RULE}_{REV_RULE}.json', 'w', encoding='utf-8'), ensure_ascii=False, default=str, indent=1)
print('数据', out['data'], '观察期', N, '个月', '单位', UNIT, 'BSR', BSR_RULE, '单位数', len(R), '多父体单位', int((R['父ASIN'].map(len) > 1).sum())); print('状态', out['status']); print('按上架月', out['by_launch'])
print('成功率（观察完整）', out['rate'], f"{out['rate']['k'] / max(out['rate']['n'], 1):.1%}")
print('观察期没走完但已达线', out['early_hit_unfinished']); print('成功由哪条线触发', out['by_line'])
print('未成功但有被排除的异常 BSR 达线', out['invalid_bsr_only']); print('阈值敏感性', out['sens'])
print('格子', {k: v for k, v in out['grid'].items() if v['n'] >= 3})
for r in R[R['状态'] == '成功'].itertuples(): print(' ✓', r.单位, len(r.父ASIN), r.品牌, r.上架月, r.宽度段, r.形态, '第', r.首次达线['月龄'], '月', r.首次达线['依据'])
for r in done[(done['状态'] == '未成功') & done['逐月'].map(lambda ev: any(e['无效BSR达线'] for e in ev))].itertuples():
    x = df[(df['单位'] == r.单位) & df['月龄'].between(1, N) & ~df['BSR可用'] & (df['BSR'] <= BSR_LINE)]
    print(' ? 被排除的BSR', r.单位, r.品牌, r.上架月, x[['月', '子ASIN', 'BSR', 'BSR校验状态', '销量']].to_dict('records'))
