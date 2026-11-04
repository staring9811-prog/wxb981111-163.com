"""小平台调研：Home Depot / Lowe's / Wayfair 的"单元 × 指标"观察表（不做回测、不下立项结论）。
用法：python3 小平台调研_单元指标.py
  → solution-v2/开发建议/小平台调研_单元×指标_HD_Lowes_Wayfair.md（数字全部来自本次运行）
  → input/data_v2/渠道调研/小平台调研_单元指标_全量.csv、小平台调研_框_全量.csv（不入库）
叫法（wen 2026-11-04）：框 = 尺寸段 × 拆装 × 形态；属性 = 台面材质 / 元素 / 主色 / 柜体材质；取值 = 属性的值；
单元（行）= 框 × 属性取值；指标（列）= 观察的数据维度；模式 = 指标组合成的信号。比较只在同一框、同一渠道内。
数据：
- HD：评论重建（input/data_v2/渠道历史/homedepot/，与 小平台_HD回测小试.py / 跨渠道供给差_HD检验.py 同一读取与 v12.2 规格打标）；
- Lowe's / Wayfair：渠道VP_20261103.xlsx「商品月度明细」，同系列商品共享评论 → 按"10 个月 VP / 非 VP 序列 + 页面累计评论数"相同合成家族，
  家族销量按成员商品页均分（同 Amazon"子体月销（家族均分）"）；标题按 v12.2 规则打标；
- Amazon：input/data_v2/统一打标/统一打标_分析用.pkl（第二轮 / 第九版同一张表），2026-04 至 09。
月销 = VP × 50 + 非 VP × 20；窗口 2026-01 至 10（11 月不完整，不计）。不改 tools/ 与 app/，只 import。"""
import os, sys, re, json, glob, numpy as np, pandas as pd, warnings
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
import 跨渠道供给差_HD检验 as XC   # noqa: E402  （内部 import 小平台_HD回测小试 与 app/pdt/core 的打标规则）
HD, TR = XC.HD, XC.TR
from families import mi, ms   # noqa: E402

MON = [mi(f'2026-{i:02d}') for i in range(1, 11)]
Q = {'1–3': MON[0:3], '4–6': MON[3:6], '7–9': MON[6:9], '10': MON[9:10]}
PRE, REC = MON[0:3], MON[7:10]                 # 前 3 月、近 3 月
AZM = [mi(f'2026-{i:02d}') for i in range(4, 10)]; AZ_PRE, AZ_REC = AZM[:3], AZM[3:]
FR_MIN, U_MIN = 200, 20                        # 框月均 ≥ 200 件、单元月均 ≥ 20 件
ATTRS = ('台面材质', '元素', '主色', '柜体材质')
UNK = set(HD.UNKS) | {'未知'}
PRICE_ABS = XC.PRICE_ABS
RESIN = '树脂一体（Cultured Marble + 树脂）'
AZKEY = lambda att, v: RESIN if att == '台面材质' and str(v) in ('Cultured Marble', '树脂') else str(v)   # 小平台取值 → Amazon 对照键
LN = 0.3                                       # 模式：份额 ln(近 3 ÷ 前 3) ≥ 0.3 算涨、≤ −0.3 算跌（与 机会扫描.py 同）
DIR = 0.2                                      # 三渠道方向：|ln| < 0.2 记 →
LW = "Lowe's"
XLSX = os.path.join(ROOT, 'input/data_v2/渠道VP/浴室柜_2026_渠道VP_20261103.xlsx')
OUTMD = os.path.join(ROOT, 'solution-v2', '开发建议', '小平台调研_单元×指标_HD_Lowes_Wayfair.md')
OUTDIR = os.path.join(ROOT, 'input', 'data_v2', '渠道调研')
L = []; P = lambda *a: L.extend(a)
pc = lambda x, d=0: '—' if x is None or not np.isfinite(x) else f'{x:.{d}%}'
num = lambda x, d=0: '—' if x is None or not np.isfinite(x) else f'{x:,.{d}f}'
ps = lambda x: '—' if x is None or not np.isfinite(x) else (f'{x:.1%}' if abs(x) < 0.1 else f'{x:.0%}')   # 份额：< 10% 保留一位小数
gx = lambda x: '新出现' if x is None or not np.isfinite(x) else f'{x:.2f}'                                  # 近 3 ÷ 前 3，前 3 为 0 时"新出现"
sg = lambda x, d=2: '—' if x is None or not np.isfinite(x) else f'{x:+.{d}f}'


def wq(x, w, q):
    x, w = np.asarray(x, float), np.asarray(w, float); k = ~np.isnan(x) & (w > 0); x, w = x[k], w[k]
    if not len(x): return np.nan
    o = np.argsort(x); c = np.cumsum(w[o]); return x[o][min(np.searchsorted(c, c[-1] * q), len(x) - 1)]


# ====================================================================== 1. 行级表（每行 = 渠道 × 商品页 × 月，c = 估算销量）
def hd_table():
    A, V, M0, END = XC.hd_rows()
    A = A[A['m'].isin(MON)].copy()
    first = {}; rat = []
    for f in glob.glob(os.path.join(HD.CACHE, 'reviews', '*.json')):
        g = HD.load_json(f) or {}; fk = os.path.basename(f)[:-5]; first[fk] = g.get('首条评论')
        for rid, x in (g.get('reviews') or {}).items():
            d = x.get('d') or ''
            if d[:4].isdigit() and mi(d) in MON: rat.append((rid, x['pid'], mi(d), x['r']))
    R = pd.DataFrame(rat, columns=['rid', 'pid', 'm', 'r']).drop_duplicates('rid')
    RS = R.groupby(['pid', 'm'])['r'].agg(rs='sum', rn='count')
    A = A.join(RS, on=['pid', 'm']); A[['rs', 'rn']] = A[['rs', 'rn']].fillna(0)
    A['首评'] = A['fam'].map(first)
    A['新家族'] = A['首评'].map(lambda d: isinstance(d, str) and d[:4] == '2026')
    A['进入月'] = A['首评'].map(lambda d: mi(d) if isinstance(d, str) and d[:4] == '2026' else np.nan)
    A['装来源'] = A['pid'].map(V['装来源']).fillna('家族补'); A.loc[A['装来源'].eq(''), '装来源'] = '家族补'; A.loc[A['装'] == '未知', '装来源'] = '未知'
    A['形态来源'] = A['pid'].map(V['形态来源']).fillna(''); A.loc[A['形态来源'].eq(''), '形态来源'] = '默认落地式/家族补'
    return A, V


def lw_table(ch):
    """Lowe's / Wayfair：商品页 → 家族（共享评论）→ 家族月销按成员均分 → 标题打标。"""
    d = pd.read_excel(XLSX, '商品月度明细'); d = d[d['渠道'] == ch].copy()
    vc = [f'{ms(m)} VP' for m in MON]; nc = [f'{ms(m)} 非VP' for m in MON]
    d['fam'] = 'F' + pd.factorize(d[vc + nc + ['2026-11（未完整） 合计']].astype(str).agg('|'.join, axis=1) + '#' + d['页面累计评论数'].astype(str))[0].astype(str)
    d['商品ID'] = d['商品ID'].astype(str); d = d.sort_values('排名').drop_duplicates('商品ID')
    rows = []
    for _, r in d.iterrows():
        t = HD.tag_variant(TR, r['标题'], None, None)
        rows.append(dict(pid=r['商品ID'], fam=r['fam'], 入口=r['入口'], 排名=r['排名'], 品牌=r['品牌'], title=r['标题'], 累计=r['页面累计评论数'],
                         y2026=r['1-10月 合计'] + r['2026-11（未完整） 合计'], **t))
    V = pd.DataFrame(rows).set_index('pid')
    # 同家族补（同系列只换颜色尺寸）：装、形态、柜体材质、台面材质
    for col in ('装', '形态'):
        mode = V[V[col] != '未知'].groupby('fam')[col].agg(lambda s: s.mode().iloc[0])
        k = (V[col] == '未知') & V['fam'].isin(mode.index); V.loc[k, col] = V.loc[k, 'fam'].map(mode); V.loc[k, col + '来源'] = '家族补'
    for col in ('D7', 'D8'):
        mode = V[~V[col].isin(UNK)].groupby('fam')[col].agg(lambda s: s.mode().iloc[0])
        k = V[col].isin(UNK) & V['fam'].isin(mode.index); V.loc[k, col] = V.loc[k, 'fam'].map(mode)
    V['装来源'] = V['装来源'].replace('', '未写')
    if ch == "Lowe's":   # wen 2026Q2 文档：Lowe's 100% 整装 → 判断不了的按业务默认整装
        k = V['装'] == '未知'; V.loc[k, '装'] = '整装'; V.loc[k, '装来源'] = '业务默认（wen 文档 100% 整装）'
    V['形态来源'] = V['形态来源'].replace('', '默认落地式')
    V['形态'] = V['形态'].replace({'两用': '落地式'}); V.loc[V['形态'] == '未知', '形态'] = '落地式'
    V['尺寸段'] = V['宽'].map(XC.band); V['柜体材质'] = V['D7'].map(XC.cab)
    V['台面材质'] = V['D8'].map(lambda v: '未知' if v in UNK else v); V['主色'] = V['D6'].map(XC.color)
    V['元素'] = V['D5'].map(lambda v: sorted({HD.ELEM_MAP[x] for x in str(v).split('；') if x in HD.ELEM_MAP}) or ['未知'])
    n = V.groupby('fam').size()
    fr = d.drop_duplicates('fam').set_index('fam')
    out = []
    for fam, r in fr.iterrows():
        first_m = next((m for m in MON if r[f'{ms(m)} 合计'] > 0), None)
        cum, y26 = r['页面累计评论数'], r['1-10月 合计'] + r['2026-11（未完整） 合计']
        new = bool(pd.notna(cum) and cum <= y26 and y26 > 0)
        for m in MON:
            c = (r[f'{ms(m)} VP'] * 50 + r[f'{ms(m)} 非VP'] * 20) / n[fam]
            for p in V.index[V['fam'] == fam]:
                out.append(dict(fam=fam, pid=p, m=m, c=c, 新家族=new, 进入月=first_m if new else np.nan, 累计不一致=bool(pd.notna(cum) and cum < y26)))
    A = pd.DataFrame(out).join(V[['尺寸段', '装', '装来源', '形态', '形态来源', '台面材质', '主色', '柜体材质', '元素', '品牌', 'title']], on='pid')
    A['价格'] = np.nan; A['rs'] = 0.0; A['rn'] = 0.0
    return A, V


def az_table():
    B = XC.az_rows(); B = B[B['m'].isin(AZM)].copy()
    return B


# ====================================================================== 2. 框与单元的指标
def frame_key(A, view):
    s = A['尺寸段'].astype(object)
    if view == '框':
        ok = s.notna() & (A['装'] != '未知'); k = s.fillna('') + ' · ' + A['装'] + ' · ' + A['形态']
    elif view == '不分拆装':
        ok = s.notna(); k = s.fillna('') + ' · 不分拆装 · ' + A['形态']
    elif view == '不分尺寸段':
        ok = A['装'] != '未知'; k = '不分尺寸段 · ' + A['装'] + ' · ' + A['形态']
    elif view == '全尺寸不分拆装':
        ok = pd.Series(True, index=A.index); k = '全尺寸 · 不分拆装 · ' + A['形态']
    return k.where(ok)


def share_series(C, F):
    return C.reindex(MON, fill_value=0) / F.reindex(MON, fill_value=0).replace(0, np.nan)


def metrics(A, view, ch):
    """返回 框表、单元表。份额分母 = 整框销量（含该属性未知的部分，框表给出各属性已知占比）。"""
    A = A.assign(框=frame_key(A, view)); A = A[A['框'].notna()]
    FR, UN = [], []
    for fr, g in A.groupby('框'):
        Fm = g.groupby('m')['c'].sum().reindex(MON, fill_value=0); tot = Fm.sum()
        fams = g.loc[g['c'] > 0, 'fam'].nunique(); famavg = tot / 10 / max(fams, 1)
        newf = g[g['新家族']]
        fi = dict(渠道=ch, 视图=view, 框=fr, 框月均=tot / 10, 家族=fams, 单款月均=famavg,
                  前3=Fm[PRE].sum() / 3, 近3=Fm[REC].sum() / 3, 框新家族=newf.loc[newf['c'] > 0, 'fam'].nunique(), 框新家族占比=newf['c'].sum() / tot if tot else np.nan,
                  框中位价=wq(g['价格'], g['c'], .5), 框评分=g['rs'].sum() / g['rn'].sum() if g['rn'].sum() else np.nan, 框评论数=g['rn'].sum(),
                  **{f'季{k}': Fm[v].sum() / len(v) for k, v in Q.items()})
        for att in ATTRS:
            x = g.explode('元素') if att == '元素' else g
            kn = x[~x[att].astype(str).isin(UNK | {'其他'})]
            fi[f'{att}已知'] = (kn.drop_duplicates(['pid', 'm'])['c'].sum() / tot) if tot else np.nan
            for v, u in kn.groupby(att):
                Um = u.groupby('m')['c'].sum().reindex(MON, fill_value=0); us = Um.sum()
                if us / 10 < 1: continue
                sh = share_series(Um, Fm); s_pre = Um[PRE].sum() / max(Fm[PRE].sum(), 1e-9); s_rec = Um[REC].sum() / max(Fm[REC].sum(), 1e-9)
                xs = np.arange(10); ok = sh.notna().values
                slope = np.polyfit(xs[ok], sh.values[ok], 1)[0] if ok.sum() >= 3 else np.nan
                uf = u.loc[u['c'] > 0, 'fam'].nunique()
                nu = u[u['新家族'] & (u['c'] > 0)]
                # 新家族进入后是否卖起来：进入月到 10 月，家族在该单元的月均 ≥ 同框单款月均
                up = 0
                for f, h in nu.groupby('fam'):
                    e = int(h['进入月'].iloc[0]) if pd.notna(h['进入月'].iloc[0]) else MON[0]; e = max(e, MON[0])
                    if h.loc[h['m'] >= e, 'c'].sum() / (MON[-1] - e + 1) >= famavg: up += 1
                mu = Um.mean()
                UN.append(dict(渠道=ch, 视图=view, 框=fr, 属性=att, 取值=v, 月均=us / 10, 份额=us / tot,
                               **{f'份额{k}': Um[q].sum() / max(Fm[q].sum(), 1e-9) for k, q in Q.items()},
                               份额前3=s_pre, 份额近3=s_rec, 份额差pp=(s_rec - s_pre) * 100, 份额ln=np.log((s_rec + 0.002) / (s_pre + 0.002)),
                               斜率pp=slope * 100, 单元增长=Um[REC].sum() / Um[PRE].sum() if Um[PRE].sum() > 0 else np.nan, 框增长=Fm[REC].sum() / max(Fm[PRE].sum(), 1e-9),
                               CV=Um.std(ddof=0) / mu if mu else np.nan, 家族=uf, 单款比=(us / max(uf, 1)) / max(famavg * 10, 1e-9),
                               新家族=nu['fam'].nunique(), 新家族卖起来=up, 新家族占比=u.loc[u['新家族'], 'c'].sum() / us, 框新家族占比=fi['框新家族占比'],
                               P25=wq(u['价格'], u['c'], .25), 中位价=wq(u['价格'], u['c'], .5), P75=wq(u['价格'], u['c'], .75),
                               溢价=wq(u['价格'], u['c'], .5) / fi['框中位价'] if fi['框中位价'] == fi['框中位价'] else np.nan,
                               评分=u['rs'].sum() / u['rn'].sum() if u['rn'].sum() else np.nan, 评论数=u['rn'].sum(), 框评分=fi['框评分'],
                               尺寸段=g['尺寸段'].iloc[0], 形态=g['形态'].iloc[0], 框月均=tot / 10,
                               月序列='/'.join(f'{x * 100:.0f}' for x in sh.fillna(0).values)))
        FR.append(fi)
    F = pd.DataFrame(FR); U = pd.DataFrame(UN)
    if len(U):
        U['评分差'] = U['评分'] - U['框评分']
        U['走势'] = [trend_label(r) for r in U.itertuples()]
    return F, U


def trend_label(r):
    fr = '框涨' if r.框增长 >= 1.15 else ('框跌' if r.框增长 <= 0.87 else '框平')
    if r.份额ln >= LN: return f'抢份额（{fr}）'
    if r.份额ln <= -LN: return f'丢份额（{fr}）'
    return f'随框（{fr}）'


# ====================================================================== 3. Amazon 对照（尺寸段 × 形态 × 取值，不分拆装）
def az_cells(B, level):
    B = B.assign(框=(B['尺寸段'].astype(object).fillna('') + ' · ' + B['形态']).where(B['尺寸段'].notna()) if level == '尺寸段' else '全尺寸 · ' + B['形态'])
    B = B[B['框'].notna()]
    Fm = B.groupby(['框', 'm'])['c'].sum()
    out = {}
    for att in ATTRS:
        x = B.explode('元素') if att == '元素' else B
        x = x[~x[att].astype(str).isin(UNK | {'其他'}) & ~x[att].astype(str).str.startswith('其他（')]
        if att == '台面材质':   # Amazon 很少标 Cultured Marble，树脂一体多标"树脂"：另给合并键，供 Cultured Marble / 树脂 对照
            x = pd.concat([x, x[x[att].isin(['Cultured Marble', '树脂'])].assign(**{att: RESIN})])
        for (fr, v), u in x.groupby(['框', att]):
            Um = u.groupby('m')['c'].sum(); F = Fm.loc[fr]
            pre = Um.reindex(AZ_PRE, fill_value=0).sum() / max(F.reindex(AZ_PRE, fill_value=0).sum(), 1e-9)
            rec = Um.reindex(AZ_REC, fill_value=0).sum() / max(F.reindex(AZ_REC, fill_value=0).sum(), 1e-9)
            w = u[u['c'] > 0]
            out[(fr, att, str(v))] = dict(AZ月均=Um.sum() / 6, AZ份额=Um.sum() / F.sum(), AZ家族=w['fam'].nunique(),
                                          AZ价位段=pd.cut(w['价格'], PRICE_ABS, labels=False, right=False).nunique(),
                                          AZ份额前=pre, AZ份额近=rec, AZln=np.log((rec + 0.002) / (pre + 0.002)))
    return out


def arrow(x):
    return '—' if x is None or not np.isfinite(x) else ('↑' if x >= DIR else ('↓' if x <= -DIR else '→'))


def attach_az(U, AZ, level):
    if not len(U): return U
    keys = []
    for r in U.itertuples():
        fr = f'{r.尺寸段} · {r.形态}' if level == '尺寸段' else f'全尺寸 · {r.形态}'
        keys.append(AZ.get((fr, r.属性, AZKEY(r.属性, r.取值)), {}))
    Z = pd.DataFrame(keys, index=U.index)
    for c in ('AZ月均', 'AZ份额', 'AZ家族', 'AZ价位段', 'AZ份额前', 'AZ份额近', 'AZln'):
        U[c] = Z[c] if c in Z else np.nan
    return U


# ====================================================================== 4. 报告片段
def cov_table(A, ch):
    """每个标签的覆盖率：按商品页、按 1–10 月估算销量。"""
    V = A.drop_duplicates('pid'); S = A.groupby('pid')['c'].sum(); tot = S.sum()
    rows = []
    def add(name, known, note=''):
        kp = known.reindex(V['pid']).fillna(False).values if isinstance(known, pd.Series) else known
        ids = V['pid'][kp]; rows.append(f'| {name} | {kp.mean():.0%} | {S.reindex(ids).sum() / tot:.0%} | {note} |')
    vi = V.set_index('pid')
    add('尺寸段', vi['尺寸段'].notna())
    src = A.groupby('装来源')['c'].sum() / tot
    add('装（含业务默认 / 家族补）', vi['装'] != '未知', '来源（按销量）：' + '、'.join(f'{k} {v:.0%}' for k, v in src.sort_values(ascending=False).items()))
    src = A.groupby('形态来源')['c'].sum() / tot
    add('形态', pd.Series(True, index=vi.index), '来源（按销量）：' + '、'.join(f'{k} {v:.0%}' for k, v in src.sort_values(ascending=False).items()))
    for att in ('台面材质', '主色', '柜体材质'):
        add(att, ~vi[att].astype(str).isin(UNK))
    add('元素（文字规则）', vi['元素'].map(lambda e: e != ['未知']))
    add('框（尺寸段 × 装 × 形态）可定', vi['尺寸段'].notna() & (vi['装'] != '未知'))
    return ['| 标签 | 商品页覆盖 | 1–10 月销量覆盖 | 说明 |', '| :--- | ---: | ---: | :--- |'] + rows


def frame_table(F):
    F = F.sort_values('框月均', ascending=False)
    out = ['| 框 | 月均 | 渠道内份额 | 季均 1–3 / 4–6 / 7–9 / 10 月 | 近 3 ÷ 前 3 | 家族 | 单款月均 | 新家族（销量占比） | 中位价 | 评分 | 台面 / 主色 / 柜体 / 元素 已知 |',
           '| :--- | ---: | ---: | :--- | ---: | ---: | ---: | :--- | ---: | ---: | :--- |']
    tot = F['框月均'].sum()
    for _, r in F.iterrows():
        out.append(f"| {r['框']} | {num(r['框月均'])} | {pc(r['框月均'] / tot)} | {num(r['季1–3'])} / {num(r['季4–6'])} / {num(r['季7–9'])} / {num(r['季10'])} | {r['近3'] / max(r['前3'], 1e-9):.2f} | {r['家族']} | {num(r['单款月均'])} | "
                   f"{r['框新家族']}（{pc(r['框新家族占比'])}） | {('$' + num(r['框中位价'])) if np.isfinite(r['框中位价']) else '无'} | {num(r['框评分'], 2) if np.isfinite(r['框评分']) else '无'} | "
                   f"{pc(r['台面材质已知'])} / {pc(r['主色已知'])} / {pc(r['柜体材质已知'])} / {pc(r['元素已知'])} |")
    return out


def unit_table(U, has_price, has_rating):
    h = '| 属性：取值 | 月均 | 份额 | 季度份额 1–3 / 4–6 / 7–9 / 10 | 近3−前3 | 斜率 pp/月 | 走势（单元 ÷ 框） | CV | 家族 | 单款 ÷ 同框 | 新家族 个（卖起来）· 占比（同框） |'
    s = '| :--- | ---: | ---: | :--- | ---: | ---: | :--- | ---: | ---: | ---: | :--- |'
    if has_price: h += ' 价格带 P25–P75 · 溢价 |'; s += ' :--- |'
    if has_rating: h += ' 评分（同框差） |'; s += ' :--- |'
    h += ' Amazon 家族 · 价位段 · 份额前→近 |'; s += ' :--- |'
    out = [h, s]
    for r in U.itertuples():
        q = [U.at[r.Index, f'份额{k}'] for k in Q]
        line = (f"| {r.属性}：{r.取值} | {num(r.月均)} | {ps(r.份额)} | {ps(q[0])} / {ps(q[1])} / {ps(q[2])} / {ps(q[3])} | {sg(r.份额差pp, 1)} pp | {sg(r.斜率pp, 2)} | "
                f"{r.走势} {gx(r.单元增长)} ÷ {r.框增长:.2f} | {r.CV:.2f} | {r.家族} | {r.单款比:.2f} | {r.新家族}（{r.新家族卖起来}）· {pc(r.新家族占比)}（{pc(r.框新家族占比)}） |")
        if has_price: line += f" ${num(r.P25)}–{num(r.P75)} · {r.溢价:.2f} |" if np.isfinite(r.中位价) else ' 无 |'
        if has_rating: line += f" {r.评分:.2f}（{sg(r.评分差)}） |" if np.isfinite(r.评分) else ' — |'
        line += (f" {int(r.AZ家族)} · {int(r.AZ价位段)} · {ps(r.AZ份额前)}→{ps(r.AZ份额近)} {arrow(r.AZln)}{'（树脂一体合并）' if AZKEY(r.属性, r.取值) == RESIN else ''} |" if np.isfinite(r.AZ家族) else ' 无 |')
        out.append(line)
    return out


def patterns(U, ch, has_price, has_rating):
    out = []
    pat = [('份额在涨 + 新家族进入', (U['份额ln'] >= LN) & (U['新家族'] > 0) & (U['新家族占比'] > U['框新家族占比']),
            lambda r: f"份额 {ps(r.份额前3)}→{ps(r.份额近3)}，单元销量 ×{gx(r.单元增长)}、框 ×{r.框增长:.2f}；新家族 {r.新家族} 个（{r.新家族卖起来} 个达到同框单款月均），销量占比 {pc(r.新家族占比)}（同框 {pc(r.框新家族占比)}）"),
           ('份额在涨（无新家族带动）', (U['份额ln'] >= LN) & ~((U['新家族'] > 0) & (U['新家族占比'] > U['框新家族占比'])),
            lambda r: f"份额 {ps(r.份额前3)}→{ps(r.份额近3)}，单元 ×{gx(r.单元增长)}、框 ×{r.框增长:.2f}；家族 {r.家族}、新家族 {r.新家族}"),
           ('份额在跌', U['份额ln'] <= -LN,
            lambda r: f"份额 {ps(r.份额前3)}→{ps(r.份额近3)}，单元 ×{gx(r.单元增长)}、框 ×{r.框增长:.2f}；家族 {r.家族}")]
    if has_rating:
        pat.append(('评分低于同框但单款卖得多', (U['评分差'] <= -0.15) & (U['单款比'] >= 1.0) & (U['评论数'] >= 20),
                    lambda r: f"评分 {r.评分:.2f}（同框 {r.框评分:.2f}，{int(r.评论数)} 条评论）、单款 ÷ 同框 {r.单款比:.2f}、份额 {ps(r.份额)}"))
    if has_price:
        pat.append(('高溢价且有成交', U['溢价'] >= 1.3,
                    lambda r: f"中位价 ${num(r.中位价)}（溢价 {r.溢价:.2f}），月均 {num(r.月均)}、份额 {ps(r.份额前3)}→{ps(r.份额近3)}"))
    for name, k, fmt in pat:
        d = U[k].copy(); d['_s'] = d['月均'] * d['份额ln'].abs(); d = d.sort_values('_s', ascending=False)
        out += [f'**{name}**（{len(d)} 个单元{"，列前 10" if len(d) > 10 else ""}）', '']
        if not len(d): out += ['- 无', '']; continue
        for r in d.head(10).itertuples():
            out.append(f'- {r.框} ｜ {r.属性}：{r.取值}（月均 {num(r.月均)}）：{fmt(r)}')
        out.append('')
    return out


# ====================================================================== 5. 主流程
def main():
    print('读 HD …'); AH, VH = hd_table()
    print("读 Lowe's / Wayfair …"); AL, VL = lw_table("Lowe's"); AW, VW = lw_table('Wayfair')
    print('读 Amazon …'); B = az_table()
    AZs, AZa = az_cells(B, '尺寸段'), az_cells(B, '全尺寸')
    CH = {'Home Depot': (AH, True, True), "Lowe's": (AL, False, False), 'Wayfair': (AW, False, False)}
    VIEWS = {'Home Depot': ['框', '不分拆装', '全尺寸不分拆装'], "Lowe's": ['框', '不分尺寸段', '全尺寸不分拆装'], 'Wayfair': ['框', '不分拆装', '全尺寸不分拆装']}
    RES = {}
    for ch, (A, hp, hr) in CH.items():
        for v in VIEWS[ch]:
            F, U = metrics(A, v, ch)
            U = attach_az(U, AZa if v in ('不分尺寸段', '全尺寸不分拆装') else AZs, '全尺寸' if v in ('不分尺寸段', '全尺寸不分拆装') else '尺寸段')
            RES[(ch, v)] = (F, U)
    os.makedirs(OUTDIR, exist_ok=True)
    pd.concat([r[1] for r in RES.values()]).to_csv(os.path.join(OUTDIR, '小平台调研_单元指标_全量.csv'), index=False, encoding='utf-8-sig')
    pd.concat([r[0] for r in RES.values()]).to_csv(os.path.join(OUTDIR, '小平台调研_框_全量.csv'), index=False, encoding='utf-8-sig')

    # ---------------- 一、口径
    tot = {ch: A.groupby('m')['c'].sum().mean() for ch, (A, _, _) in CH.items()}
    lw_fam = {ch: (A['fam'].nunique(), A['pid'].nunique()) for ch, (A, _, _) in CH.items()}
    incons = {ch: A.drop_duplicates('fam')['累计不一致'].mean() for ch, (A, _, _) in CH.items() if ch != 'Home Depot'}
    P('# 小平台调研：单元 × 指标（Home Depot / Lowe\'s / Wayfair）', '',
      '> 由 `solution-v2/trial/小平台调研_单元指标.py` 生成，数字都是脚本实际运行结果。本页是**观察分析**，不是回测，不下立项结论；"模式"一节只列符合条件的事实。'
      '全量单元表在 `input/data_v2/渠道调研/小平台调研_单元指标_全量.csv`（框表 `小平台调研_框_全量.csv`，不入库）。', '')
    P('## 一、口径', '',
      '**叫法**（wen 2026-11-04）：框 = 尺寸段 × 拆装 × 形态；属性 = 台面材质 / 元素 / 主色 / 柜体材质；取值 = 属性的值；单元（表的一行）= 框 × 属性取值；指标（表的一列）= 观察的数据维度；模式 = 指标组合成的信号。'
      '**一切比较只在同一框、同一渠道内**；三渠道对照只比方向和结构，不比绝对销量。', '',
      '**数据与窗口**', '',
      f'- Home Depot：评论重建（两个类目 Top Sellers 各前 300 个商品页 → 评论家族，采集 2026-11-03），变体级销量 = 该变体当月 VP 评论 × 50 + 非 VP × 20；主窗口 2026-01 至 10，月均 {num(tot["Home Depot"])} 件（重建口径，覆盖类目头部约 6–7 成，见 `小平台_HD回测小试.md` §3）。'
      '价格 = 采集日（2026-11-03）列表 / 商品页当天价，套到整个窗口；评分 = 窗口内评论星级的平均（按评论条数），不是页面总评分。',
      f'- Lowe\'s / Wayfair：`渠道VP_20261103.xlsx`「商品月度明细」（Lowe\'s 两个 Best Sellers 榜各前 100；Wayfair 主类目 Recommended 前 200 + 无台面前 50；采集 2026-11-02 至 03）。'
      f'同系列不同颜色 / 尺寸的商品页共享评论，按"1–10 月 VP / 非 VP 序列 + 11 月 + 页面累计评论数"完全相同合成家族：Lowe\'s {lw_fam[LW][1]} 个商品页 → {lw_fam[LW][0]} 个家族，Wayfair {lw_fam["Wayfair"][1]} → {lw_fam["Wayfair"][0]}；'
      '家族月销按成员商品页均分（同 Amazon"子体月销（家族均分）"）。核对：Lowe\'s 家族去重后 1–10 月评论 3,852 条（表内去重口径 3,850），Wayfair 7,550 条（表内 7,373，多 2%：少数商品页累计数不同但共享部分评论，没有逐条去重）。'
      f'月均 Lowe\'s {num(tot[LW])}、Wayfair {num(tot["Wayfair"])} 件。**没有价格、评分字段**，表里写"无"。',
      '- Amazon：第二轮统一打标表（`统一打标_分析用.pkl`，与第九版、跨渠道检验同一张），窗口 2026-04 至 09（数据到 9 月）；按"尺寸段 × 形态 × 属性取值"（不分拆装，跨渠道检验报告的"忽略装"口径）给家族数、绝对价位段数（$0–200 / 200–300 / 300–450 / 450–650 / 650–900 / 900–1,300 / 1,300+）、框内份额 4–6 月 → 7–9 月。',
      '- 11 月不完整，不计入；10 月是评论采集前最后一个完整月，评论有滞后（买后才评），三个渠道 10 月都可能略低，影响"近 3 月"的销量水平，对同框份额影响较小。', '',
      '**指标**（每个单元一行）', '',
      '- 体量：月均 = 1–10 月估算销量 ÷ 10；份额 = 单元销量 ÷ **整框**销量（分母含该属性未知的部分，所以同一框同一属性的份额加起来 = 该属性已知占比，框表里给出）。',
      f'- 趋势：季度份额（1–3 / 4–6 / 7–9 / 10 月，CSV 里有逐月）；近 3−前 3 = 8–10 月份额 − 1–3 月份额（百分点）；斜率 = 10 个月月度份额的线性斜率（百分点 / 月）；'
      f'走势 = 份额 ln(近 3 ÷ 前 3) ≥ {LN} 记"抢份额"、≤ −{LN} 记"丢份额"、其余"随框"，括号里是框本身近 3 ÷ 前 3（≥ 1.15 框涨、≤ 0.87 框跌），后面两个数 = 单元销量近 3 ÷ 前 3、框销量近 3 ÷ 前 3（区分"整框在涨"和"取值在抢份额"）；CV = 10 个月月销的变异系数。',
      '- 新家族：家族首条评论在 2026 年（HD 用按最早排序抓到的首评日期；Lowe\'s / Wayfair 用"页面累计评论数 ≤ 2026 年 1–11 月评论数"，即所有评论都在 2026 年）；"卖起来" = 进入月到 10 月在该单元的月均 ≥ 同框单款月均；占比 = 新家族在单元 1–10 月销量里的占比，括号是同框。'
      f'Lowe\'s {pc(incons[LW])}、Wayfair {pc(incons["Wayfair"])} 的家族页面累计数小于 2026 年评论数（口径不一致），这些按"非新"处理。',
      '- 供给：家族 = 窗口内单元里有销量的家族数；单款 ÷ 同框 = 单元每个家族的月均 ÷ 同框每个家族的月均。',
      '- 价格（仅 HD）：价格带 = 按销量加权的 P25–P75；溢价 = 单元加权中位价 ÷ 同框加权中位价。评分（仅 HD）：单元评分与同框评分的差。',
      '- Amazon 对照：同尺寸段 × 形态 × 取值（不分拆装）的家族数 · 价位段数 · 框内份额 4–6 月 → 7–9 月，箭头 ↑ / → / ↓ 按 ln 变化 ±0.2。', '',
      f'**门槛**：框月均 ≥ {FR_MIN} 件、单元月均 ≥ {U_MIN} 件才列（三个渠道体量相近，月均 1.7–2.9 万件，用同一门槛；{FR_MIN} 件约为渠道月销的 0.7–1.2%，与 HD 回测"大单元"同量级）。'
      '1 条 VP 评论 = 50 件，月均 20 件的单元 10 个月只有约 4 条 VP 评论，**小单元的趋势和 CV 噪声很大**，只看方向，家族数 1–2 的单元基本是单个产品的走势。', '')
    P('**幸存者偏差**：三个渠道都是"今天在榜（前 100–300）"的商品往回看。过去卖得好、今天掉出榜单的商品看不到，所以：① 早月份的框销量偏低，"框在涨""份额在涨"会偏乐观（尤其新家族多的单元，进入早期本来就是 0）；'
      '② "份额在跌"只看到还在榜的商品在跌，真实下跌更多；③ HD 2024–2025 年的重建只作背景，2026 年 1–10 月离采集日近、偏差较小，但仍有。这也是本页只做观察、不做回测的原因（`幸存者偏差模拟_小平台回测可行性.md`）。', '')

    P('### 打标覆盖', '',
      '规则：v12.2 打标（`app/pdt/core/tagging_rules.py` 的 Tagger，关掉默认值）。HD 用标题 + 商品页规格（"Assembled""Vanity Type"规格优先），Lowe\'s / Wayfair 只有标题；同家族已知值补装、形态、柜体材质、台面材质；'
      '形态没写的按落地式（与 Amazon、HD 小试同口径）；元素只用文字规则（夏克式 / 竖棱 / 农场风 / 玻璃门 / 木条格栅 / rattan），不看图。'
      '**装**：HD 判断不了记未知、不进框；Lowe\'s 判断不了按 wen《2026-Q2 浴室柜品类规划》"Lowe\'s 100% 整装"作业务默认整装（来源：wen 文档，非数据）；Wayfair 拆装约 23%（wen 文档），不能默认，判断不了的不进带"装"的框，另给"尺寸段 × 形态（不分拆装）"降级视图。', '')
    for ch, (A, _, _) in CH.items():
        P(f'**{ch}**', '', *cov_table(A, ch), '')

    # ---------------- 二、每个渠道
    P('## 二、各渠道', '')
    SEC = {'Home Depot': [('框', '主视图：框 = 尺寸段 × 装 × 形态')],
           "Lowe's": [('框', '主视图：框 = 尺寸段 × 装 × 形态（尺寸段几乎认不出，见覆盖表）'), ('不分尺寸段', '**降级视图**：不分尺寸段 × 装（业务默认整装）× 形态 —— 不满足"同尺寸段"硬规则，只能看属性结构和走势，不能当框内比较')],
           'Wayfair': [('框', '主视图：框 = 尺寸段 × 装 × 形态（只含装能从标题判断的商品）'), ('不分拆装', '**降级视图**：尺寸段 × 形态（不分拆装）—— 整装、拆装混在一个框里，价格、单款比较会偏')]}
    KEYN = {'Home Depot': 5, "Lowe's": 3, 'Wayfair': 4}
    for ch, (A, hp, hr) in CH.items():
        P(f'### {ch}', '')
        for v, title in SEC[ch]:
            F, U = RES[(ch, v)]
            F2 = F[F['框月均'] >= FR_MIN]
            P(f'#### {title}', '', f'框月均 ≥ {FR_MIN} 的框 {len(F2)} 个（全部框 {len(F)} 个，合计月均 {num(F["框月均"].sum())}；达标框占 {pc(F2["框月均"].sum() / max(F["框月均"].sum(), 1e-9))}）。', '')
            if not len(F2): P('（没有达标的框。）', ''); continue
            P(*frame_table(F2), '')
            U2 = U[U['框'].isin(F2['框']) & (U['月均'] >= U_MIN)]
            P(f'达标单元 {len(U2)} 个（单元月均 ≥ {U_MIN}）。', '')
            for fr in F2.sort_values('框月均', ascending=False)['框'].head(KEYN[ch]):
                d = U2[U2['框'] == fr].sort_values(['属性', '月均'], ascending=[True, False])
                P(f'**{fr}**（框月均 {num(F2.set_index("框").at[fr, "框月均"])}）', '', *unit_table(d, hp, hr), '')
            P(f'**模式观察（{ch} · {v}，所有达标框）**：条件 —— 份额在涨 / 跌：ln(近 3 ÷ 前 3 份额) ≥ {LN} / ≤ −{LN}；新家族进入：有新家族且新家族销量占比高于同框；'
              '评分低于同框：差 ≤ −0.15、单款 ÷ 同框 ≥ 1、窗口评论 ≥ 20 条；高溢价：溢价 ≥ 1.3。只陈述事实，排序按 月均 × |份额 ln 变化|。', '', *patterns(U2, ch, hp, hr))

    # ---------------- 三、三渠道对照
    P('## 三、三渠道与 Amazon 对照（只比方向和结构）', '',
      f'方向：小平台 = 份额 ln(8–10 月 ÷ 1–3 月)，Amazon = ln(7–9 月 ÷ 4–6 月)，|ln| < {DIR} 记 →。窗口不同（Amazon 数据到 9 月），只看是否同向。份额 = 同（尺寸段 ×）形态框内的份额（不分拆装）。', '')
    def struct(A, att, w='c'):
        x = A.explode('元素') if att == '元素' else A
        x = x[~x[att].astype(str).isin(UNK | {'其他'}) & ~x[att].astype(str).str.startswith('其他（')]
        return x.groupby(att)[w].sum() / A[w].sum()
    COV = {ch: {att: struct(A, att).sum() for att in ATTRS} for ch, (A, _, _) in CH.items()}
    COVMIN = 0.3
    P(f'属性覆盖不足的渠道不参与该属性的方向比较：某渠道某属性已知销量 < {COVMIN:.0%} 时记"覆盖不足"（' +
      '；'.join(f'{ch} ' + '、'.join(f'{a} {COV[ch][a]:.0%}' for a in ATTRS) for ch in CH) + '）。台面材质 Cultured Marble 与 树脂 在 Amazon 侧按"树脂一体"合并对照（Amazon 很少单标 Cultured Marble）。', '')
    # 3.1 全尺寸 × 形态 × 取值（含 Lowe's）
    GA = {ch: RES[(ch, '全尺寸不分拆装')][1] for ch in CH}
    keys = set()
    for ch, U in GA.items(): keys |= set(map(tuple, U.loc[U['月均'] >= U_MIN, ['框', '属性', '取值']].values))
    rows = []
    for k in sorted(keys):
        rec = {'框': k[0], '属性': k[1], '取值': k[2]}
        for ch, U in GA.items():
            r = U[(U['框'] == k[0]) & (U['属性'] == k[1]) & (U['取值'] == k[2])]
            rec[ch] = r.iloc[0] if len(r) else None
        az = AZa.get((k[0].replace('全尺寸 · 不分拆装 · ', '全尺寸 · '), k[1], AZKEY(k[1], k[2])))
        rec['AZ'] = az; rows.append(rec)
    def cell(r, ch, att):
        if COV[ch][att] < COVMIN: return '覆盖不足'
        return '—' if r is None else f'{ps(r["份额"])} {arrow(r["份额ln"])}'
    def azc(a):
        return '—' if not a else f'{ps(a["AZ份额"])} {arrow(a["AZln"])}（{a["AZ家族"]} 家族）'
    P('### 3.1 全尺寸 × 形态 × 取值（四个渠道，Lowe\'s 只能在这一层比）', '',
      '格式：框内份额 方向。只列至少一个小平台月均 ≥ 20 件（且该渠道该属性覆盖够）、在落地式框里的取值（悬浮式在 HD / Lowe\'s 几乎没有）；"一致"只数月均 ≥ 20 且覆盖够的渠道。', '',
      '| 属性：取值 | HD | Lowe\'s | Wayfair | Amazon（家族） | 三个小平台方向一致？ |', '| :--- | :--- | :--- | :--- | :--- | :--- |')
    agree = []
    for rec in rows:
        if '落地式' not in rec['框']: continue
        dirs = [arrow(rec[ch]['份额ln']) for ch in CH if rec[ch] is not None and rec[ch]['月均'] >= U_MIN and COV[ch][rec['属性']] >= COVMIN]
        if not any(rec[ch] is not None and rec[ch]['月均'] >= U_MIN and COV[ch][rec['属性']] >= COVMIN for ch in CH): continue
        same = '—' if len(dirs) < 2 else ('一致' if len(set(dirs)) == 1 else '不一致')
        azd = arrow(rec['AZ']['AZln']) if rec['AZ'] else None
        agree.append((same, dirs, azd))
        P(f"| {rec['属性']}：{rec['取值']} | {cell(rec['Home Depot'], 'Home Depot', rec['属性'])} | {cell(rec[LW], LW, rec['属性'])} | {cell(rec['Wayfair'], 'Wayfair', rec['属性'])} | {azc(rec['AZ'])} | {same} |")
    n2 = [a for a in agree if a[0] != '—']
    P('', f'落地式里能在 ≥ 2 个小平台比较的取值 {len(n2)} 个，方向一致 {sum(a[0] == "一致" for a in n2)} 个。', '')
    # 3.2 尺寸段 × 形态 × 取值（HD / Wayfair / Amazon）
    UH = RES[('Home Depot', '不分拆装')][1]; UW = RES[('Wayfair', '不分拆装')][1]
    FH = RES[('Home Depot', '不分拆装')][0]; FW = RES[('Wayfair', '不分拆装')][0]
    okH = UH[UH['框'].isin(FH.loc[FH['框月均'] >= FR_MIN, '框']) & (UH['月均'] >= U_MIN)]
    okW = UW[UW['框'].isin(FW.loc[FW['框月均'] >= FR_MIN, '框']) & (UW['月均'] >= U_MIN)]
    M = okH.merge(okW, on=['框', '属性', '取值'], suffixes=('_H', '_W'))
    M = M[M['属性'].map(lambda a: COV['Home Depot'][a] >= COVMIN and COV['Wayfair'][a] >= COVMIN)]
    P('### 3.2 尺寸段 × 形态 × 取值（HD、Wayfair 都达标的单元 + Amazon）', '',
      f'两边框月均 ≥ {FR_MIN}、单元月均 ≥ {U_MIN}、属性覆盖两边都 ≥ {COVMIN:.0%}（实际只剩台面材质）的交集 {len(M)} 个单元。格式：框内份额 方向（不分拆装）。', '')
    if len(M):
        P('| 框 | 属性：取值 | HD | Wayfair | Amazon（家族 · 价位段） | HD 与 Wayfair | 与 Amazon 同向的小平台 |', '| :--- | :--- | :--- | :--- | :--- | :--- | :--- |')
        same_hw = 0; az_same = []
        for r in M.sort_values(['框', '属性']).itertuples():
            a = AZs.get((r.框.replace(' · 不分拆装 · ', ' · '), r.属性, AZKEY(r.属性, r.取值)))
            dh, dw = arrow(r.份额ln_H), arrow(r.份额ln_W); same_hw += dh == dw
            da = arrow(a['AZln']) if a else None
            hit = [n for n, dd in (('HD', dh), ('Wayfair', dw)) if da and dd == da]; az_same.append(len(hit))
            P(f"| {r.框} | {r.属性}：{r.取值} | {ps(r.份额_H)} {dh} | {ps(r.份额_W)} {dw} | " + (f"{ps(a['AZ份额'])} {da}（{a['AZ家族']} · {a['AZ价位段']}）" if a else '无') + f" | {'同向' if dh == dw else '不同'} | {'、'.join(hit) or '—'} |")
        P('', f'HD 与 Wayfair 同向 {same_hw}/{len(M)}；与 Amazon 同向的小平台个数分布：' + '、'.join(f'{k} 个 {v} 次' for k, v in sorted(pd.Series(az_same).value_counts().items())) + '。', '')
    # 3.3 结构：各渠道属性取值的份额（全尺寸、全形态、不分拆装）
    P('### 3.3 结构：各渠道取值占渠道销量的比例（全尺寸、全形态，只看结构）', '')
    for att in ATTRS:
        S = {ch: struct(A, att) for ch, (A, _, _) in CH.items()}; S['Amazon（4–9 月）'] = struct(B, att)
        vals = pd.concat(S, axis=1).fillna(0); vals = vals[vals.max(axis=1) >= 0.02].sort_values('Home Depot', ascending=False)
        if att == '台面材质': vals.loc[RESIN] = vals.reindex(['Cultured Marble', '树脂']).fillna(0).sum()
        P(f'**{att}**（已知部分占渠道销量：' + '、'.join(f'{k} {v.sum():.0%}' for k, v in S.items()) + '）', '',
          '| 取值 | ' + ' | '.join(vals.columns) + ' |', '| :--- |' + ' ---: |' * len(vals.columns))
        for v, r in vals.iterrows(): P(f'| {v} | ' + ' | '.join(pc(x) for x in r.values) + ' |')
        P('')

    # ---------------- 四、wen 老文档判断核对
    P('## 四、对 wen 老文档判断的核对（只给事实）', '', '老文档：小平台 2026 年 4–5 月截面、Lowe\'s / HDP 前两页手动收集（约 80–130 SKU）；这里用 1–10 月和更大的样本，口径不同，差异不一定说明老判断错。', '')
    # 4.1 HDP 36–48 实木 + 岗石/石英石 $649–799
    H = AH.copy(); H['实木类'] = H['柜体材质'].isin(['实木', '实木框架']); H['石材'] = H['台面材质'].isin(['岗石', '石英石'])
    for sz, band_ in ((['36″', '42″', '48″'], (649, 799)), (['48″', '60″'], (900, 1200))):
        g = H[H['尺寸段'].isin(sz)]; s = g[g['实木类'] & g['石材']]
        inb = s[(s['价格'] >= band_[0]) & (s['价格'] <= band_[1])]
        sp = lambda q: s.loc[s['m'].isin(q), 'c'].sum() / max(g.loc[g['m'].isin(q), 'c'].sum(), 1)
        bands = pd.cut(s['价格'], [0, 450, 649, 800, 900, 1200, 1e9], right=False, labels=['<$450', '$450–648', '$649–799', '$800–899', '$900–1,199', '≥$1,200'])
        bd = (s.groupby(bands)['c'].sum() / s['c'].sum())
        P(f'- **HD {"/".join(sz)}（全部装与形态）实木 / 实木框架 × 岗石 / 石英石**：月均 {num(s["c"].sum() / 10)} 件，占这几个尺寸段 {pc(s["c"].sum() / g["c"].sum())}；'
          f'份额 1–3 月 {pc(sp(PRE))} → 8–10 月 {pc(sp(REC))}；家族 {s.loc[s["c"] > 0, "fam"].nunique()} 个（2026 首评的新家族 {s.loc[s["新家族"] & (s["c"] > 0), "fam"].nunique()} 个）；'
          f'加权中位价 ${num(wq(s["价格"], s["c"], .5))}（P25–P75 ${num(wq(s["价格"], s["c"], .25))}–{num(wq(s["价格"], s["c"], .75))}），'
          f'落在 ${band_[0]}–{band_[1]} 的销量占 {pc(inb["c"].sum() / s["c"].sum())}；价格段分布：' + '、'.join(f'{k} {v:.0%}' for k, v in bd.items() if v > 0) + '。')
        ab = g[(g['价格'] >= band_[0]) & (g['价格'] <= band_[1])]
        combo = (ab.groupby([ab['柜体材质'], ab['台面材质']])['c'].sum() / ab['c'].sum()).sort_values(ascending=False).head(4)
        P(f'  同尺寸段全部商品里 ${band_[0]}–{band_[1]} 的销量占 {pc(ab["c"].sum() / g["c"].sum())}（家族 {ab.loc[ab["c"] > 0, "fam"].nunique()} 个），主要是：' +
          '、'.join(f'{a} × {b} {v:.0%}' for (a, b), v in combo.items()) + '（价格为 2026-11-03 当天价）。')
    sint = AH[AH['台面材质'] == '岩板']
    P(f'- **HD 岩板**：台面材质 = 岩板的销量 {num(sint["c"].sum() / 10)} 件 / 月（商品页 {sint["pid"].nunique()} 个），' + ('老文档"岩板一体热弯盆空白"在本样本里仍成立（以标题 / 规格文字为准）。' if sint['c'].sum() == 0 else '有少量。'))
    # 4.2 Lowe's
    lv = AL; tt = lv['c'].sum()
    top = lv[~lv['台面材质'].astype(str).isin(UNK | {'不适用（不含台面）'})]
    resin = top['台面材质'].isin(['Cultured Marble', '树脂'])
    Vd = VL[~VL['台面材质'].astype(str).isin(UNK | {'不适用（不含台面）'})]
    P(f'- **Lowe\'s 树脂盆 81%**：带台面且台面材质已知的销量占渠道 {pc(top["c"].sum() / tt)}；其中 Cultured Marble / 树脂（树脂一体）占 {pc(top.loc[resin, "c"].sum() / top["c"].sum())}'
      f'（按商品页数 {pc(Vd["台面材质"].isin(["Cultured Marble", "树脂"]).mean())}，{int(Vd["台面材质"].isin(["Cultured Marble", "树脂"]).sum())}/{len(Vd)} 个，少数 Cultured Marble 系列销量很大）；'
      '其余：' + '、'.join(f'{k} {v:.0%}' for k, v in (top.groupby('台面材质')['c'].sum() / top['c'].sum()).sort_values(ascending=False).items() if k not in ('Cultured Marble', '树脂') and v >= 0.01) +
      '。岗石 / 石英石台面常配陶瓷台下盆，标题不写盆材，所以"树脂盆"比例只能按台面推，按销量约在这个数上下。')
    src = lv.groupby('装来源')['c'].sum() / tt
    P(f'- **Lowe\'s 100% 整装**：标题写明装的销量占 {pc(src.drop(index=[i for i in src.index if "默认" in i], errors="ignore").sum())}，其中整装 {pc(lv.loc[~lv["装来源"].str.contains("默认") & (lv["装"] == "整装"), "c"].sum() / max(lv.loc[~lv["装来源"].str.contains("默认"), "c"].sum(), 1))}；'
      f'其余 {pc(src[[i for i in src.index if "默认" in i]].sum())} 按业务默认记整装（没有反证，也没有直接证据）。')
    # 4.3 Wayfair
    wv = AW; wt = wv['c'].sum(); kn = wv[wv['装'] != '未知']
    P(f'- **Wayfair 拆装 23%**：标题能判断装的销量只占 {pc(kn["c"].sum() / wt)}，其中拆装 {pc(kn.loc[kn["装"] == "拆装", "c"].sum() / max(kn["c"].sum(), 1))}；覆盖太低，验证不了 23%。')
    cb = wv[~wv['柜体材质'].astype(str).isin(UNK)]
    P(f'- **Wayfair 实木类 83%**：柜体材质已知销量占 {pc(cb["c"].sum() / wt)}，其中实木 + 实木框架 {pc(cb.loc[cb["柜体材质"].isin(["实木", "实木框架"]), "c"].sum() / cb["c"].sum())}'
      f'（标题里写 "solid wood" 的常是"实木 + 人造板"混合，规则归到实木框架或含胶合板等，口径与老文档可能不同）；分布：' + '、'.join(f'{k} {v:.0%}' for k, v in (cb.groupby('柜体材质')['c'].sum() / cb['c'].sum()).sort_values(ascending=False).items() if v >= 0.02) + '。')
    fam = wv.groupby(['fam', '形态'])['c'].sum().reset_index(); fam['月均'] = fam['c'] / 10
    fs = fam.groupby('形态')['月均'].agg(['count', 'mean', 'median'])
    P('- **Wayfair 悬浮式单链接贡献高（老文档 556 vs 落地 199）**：按家族（≈ 链接）1–10 月月均：' + '；'.join(f'{k} {int(r["count"])} 个家族，平均 {num(r["mean"])}、中位 {num(r["median"])}' for k, r in fs.iterrows()) + '。'
      + ('悬浮式平均高于落地式。' if fs.loc['悬浮式', 'mean'] > fs.loc['落地式', 'mean'] else '本样本里悬浮式的单家族月均不高于落地式。') if '悬浮式' in fs.index else '')
    fl = RES[('Wayfair', '全尺寸不分拆装')][0].set_index('框')['框月均']
    P(f'  Wayfair 全尺寸悬浮式月均 {num(fl.get("全尺寸 · 不分拆装 · 悬浮式", np.nan))}、落地式 {num(fl.get("全尺寸 · 不分拆装 · 落地式", np.nan))}；形态"悬浮式"来自标题（floating / wall-mounted），没写的按落地式，悬浮式可能被低估。')
    # 4.4 42″
    def size_share(A):
        s = A[A['尺寸段'].notna()]; return s.groupby('尺寸段')['c'].sum() / s['c'].sum(), s['c'].sum() / A['c'].sum()
    parts = []
    for nm, A_ in (('HD', AH), ("Lowe's", AL), ('Wayfair', AW), ('Amazon（4–9 月）', B)):
        sh, cv = size_share(A_)
        parts.append(f'{nm}：尺寸段已知 {pc(cv)}，不可读' if cv < 0.3 else f'{nm}：42″ {pc(sh.get("42″", 0))}（36″ {pc(sh.get("36″", 0))}、48″ {pc(sh.get("48″", 0))}；尺寸段已知 {pc(cv)}）')
    P('- **42″ 体量**（占尺寸段已知销量）：' + '；'.join(parts) + '。')
    h42 = RES[('Home Depot', '框')][0].set_index('框')
    if '42″ · 整装 · 落地式' in h42.index:
        r = h42.loc['42″ · 整装 · 落地式']
        P(f'  HD 42″ · 整装 · 落地式 框月均 {num(r["框月均"])}，季均 {num(r["季1–3"])} / {num(r["季4–6"])} / {num(r["季7–9"])} / {num(r["季10"])}，家族 {r["家族"]}、单款月均 {num(r["单款月均"])}、中位价 ${num(r["框中位价"])}。')
    P('')

    # ---------------- 五、局限
    P('## 五、局限', '',
      '1. **幸存者偏差**（见口径）：只看今天在榜的商品，涨的偏乐观、跌的偏少；新家族"进入后卖起来"的比例偏高（没卖起来的多半已不在榜）。',
      '2. **销量是评论换算**（VP × 50 + 非 VP × 20），没有按各渠道校准；Wayfair 非 VP 占 43%（Incentivized 等），换算系数对它的偏差可能更大。小单元颗粒粗。',
      '3. **Lowe\'s 标题几乎不写尺寸**（同一商品页含多个尺寸），尺寸段覆盖极低，Lowe\'s 无法按"同尺寸段"框比较，只有降级视图；"装"有一部分是业务默认值。',
      '4. **Wayfair 标题多不写装**，带"装"的框只覆盖少数商品；降级视图混了整装和拆装。Wayfair 家族多数只有一个商品页，变体尺寸以标题那个为准。',
      '5. **Lowe\'s / Wayfair 家族销量按成员商品页均分**，同一家族内不同尺寸 / 颜色的真实分布未知；HD 评论带变体 ID，没有这个问题。',
      '6. **价格只有 HD、且是采集日当天价**；评分只有 HD（窗口评论平均）。Lowe\'s / Wayfair 价格、评分写"无"。',
      '7. **元素只用文字规则**，三个渠道元素覆盖都很低（HD 约 6% 销量），元素单元基本不可读；主色 HD 约 7 成、Lowe\'s / Wayfair 见覆盖表。',
      '8. Amazon 窗口（4–9 月）与小平台（1–10 月）不同，三渠道对照只看同向与否；Amazon 拆装为主、HD / Lowe\'s 整装为主，忽略装对齐会把不同市场混在一起（跨渠道检验 §1）。',
      '9. 这是一次观察：没有回测，模式不代表之后会延续；要用作立项证据需等月度快照积累后按同法回测。', '')
    open(OUTMD, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('写出', OUTMD, len(L), '行')
    return RES


if __name__ == '__main__':
    main()
