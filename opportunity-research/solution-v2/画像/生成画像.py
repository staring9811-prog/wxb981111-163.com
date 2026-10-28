"""读 成功率口径_对齐.py 输出的 success_window{N}_{UNIT}_{BSR_RULE}.json，生成成功率判定台画像 HTML。只读结果，不重算判定。"""
import json, os
S = os.environ['TRIAL_DUMP']; N = os.environ.get('WINDOW', '3'); U = os.environ.get('UNIT', 'chain'); B = os.environ.get('BSR_RULE', 'all')
CELL = os.environ.get('CELL', '26–32″|落地式'); GATE = 20
J = json.load(open(S + f'/success_window{N}_{U}_{B}.json', encoding='utf-8'))
F = J['families']; done = [f for f in F if f['状态'] in ('成功', '未成功')]
def pc(k, n): return f'{k / n * 100:.0f}%' if n else '—'
def kn(fs): return sum(f['状态'] == '成功' for f in fs), len(fs)
widths = ['≤25″', '26–32″', '33–39″', '40–46″', '47–54″', '55–65″']; forms = ['落地式', '悬浮式']
def cellhtml(key, fs):
    k, n = kn(fs)
    if not n: return '<td class="empty">—</td>'
    ok = n >= GATE; sel = ' sel' if key == CELL else ''
    return (f'<td class="{"ok" if ok else "thin"}{sel}"><div class="p">{pc(k, n)}</div><div class="n">{k} 成功 / {n} 个</div>'
            + ('' if ok else '<div class="tag">n &lt; 20 · 不下结论</div>') + '</td>')
grid = ''
for w in widths:
    grid += f'<tr><th>{w}</th>' + ''.join(cellhtml(f'{w}|{f}', [x for x in done if x['宽度段'] == w and x['形态'] == f]) for f in forms)
    grid += cellhtml(w + '|all', [x for x in done if x['宽度段'] == w]) + '</tr>'
K, NN = kn(done)
cw, cf = CELL.split('|'); C = [f for f in F if f['宽度段'] == cw and f['形态'] == cf]; Cd = [f for f in C if f in done]
st = {s: [f for f in C if f['状态'] == s] for s in ['成功', '未成功', '观察中', '数据不全']}
stat = ''.join(f'<tr><td>{s}</td><td>{len(v)}</td><td>{"进分母" if s in ("成功", "未成功") else "不进分母"}</td><td class="muted">{d}</td></tr>' for s, v, d in [
    ('成功', st['成功'], f'{N} 个月内达线'), ('未成功', st['未成功'], f'{N} 个月走完，没达线'), ('观察中', st['观察中'], f'第 {N} 个月还没到（数据止于 {J["data"][-7:]}）'),
    ('数据不全', st['数据不全'], f'观察期前段在 {J["data"][:7]} 之前，看不到')])
tops = {}
for f in Cd: tops.setdefault(f['台面'], []).append(f)
split = ''.join(f'<tr><td>{t}</td><td>{kn(v)[1]}</td><td>{kn(v)[0]}</td><td>{pc(*kn(v))}</td></tr>' for t, v in sorted(tops.items(), key=lambda kv: -len(kv[1])))
def basis(f):
    h = f['首次达线']
    if f['状态'] == '成功': return f'<b class="y">✓ 成功</b><span class="why">第 {h["月龄"]} 月（{h["月份"]}）{h["依据"]}</span>'
    if f['状态'] == '未成功':
        b = '—' if f['最好BSR'] is None else int(f['最好BSR'])
        return f'<b class="x">✗ 未成功</b><span class="why">{N} 个月内最好小类 BSR {b}，最高月销售额 ${f["最高月销售额"]:,}，两条线都没到</span>'
    if f['状态'] == '观察中':
        return '<b class="m">观察中</b><span class="why">' + (f'已在第 {h["月龄"]} 月达线：{h["依据"]}；观察期走完后计入' if h else '观察期还没走完，暂不计入') + '</span>'
    return '<b class="m">数据不全</b><span class="why">观察期前段不在数据月份内</span>'
order = {'成功': 0, '未成功': 1, '观察中': 2, '数据不全': 3}
rows = sorted([f for f in C if f['状态'] != '数据不全'], key=lambda f: (order[f['状态']], f['最好BSR'] or 9e9))
fams = ''.join(f'<tr><td class="mono">{f["单位"]}{"<span class=chip>串了 " + str(len(f["父ASIN"])) + " 个父 ASIN</span>" if len(f["父ASIN"]) > 1 else ""}</td><td>{f["品牌"]}</td><td>{f["上架月"][2:].replace("-", "/")}</td><td>{f["台面"]}</td><td>{"、".join(map(str, f["看到的月龄"]))}</td><td>{basis(f)}</td></tr>' for f in rows)
A = [f for f in Cd if f['台面'] == '陶瓷']; A0 = [f for f in Cd if f['台面'] not in ('陶瓷', '未知')]; un = sum(f['台面'] == '未知' for f in Cd)
ka, na = kn(A); kb, nb = kn(A0)
diff = f'{(ka / na - kb / nb) * 100:+.0f} 个百分点' if na and nb else '无法比较'
src = lambda t, ok: f'<span class="src {"u" if ok else "a"}">{t}</span>'
caliber = ''.join(f'<div><i>{a}</i>{b}{c}</div>' for a, b, c in [
    ('成功线', '任一月 小类 BSR ≤ 50 或 SPU 月销售额 ≥ $100,000，满足其一', src('wen 10-26 定', True)),
    ('观察期', f'上架当月算第 1 个月，连续 {N} 个月', src('wen 10-28 定', True)),
    ('分母', '观察期走完的起量新品（进表 = 父体月销 ≥ 60 件）', src('wen 第一轮定', True)),
    ('成功单位', '产品链：同一子 ASIN 换了父 ASIN 的，串成一个产品', src('AI 提议 · 待确认', False)),
    ('BSR 取值', '当月小类 BSR，含全父体共享排名', src('AI 提议 · 待确认', False)),
    ('结论闸门', '格子里观察期走完的产品 ≥ 20 个才下结论', src('AI 提议 · 待确认', False))])
n_ob = sum(f['状态'] == '观察中' for f in F); n_in = sum(f['状态'] == '数据不全' for f in F)
html = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>
:root{{--bg:#F4F5F7;--s:#fff;--fg:#14181D;--mu:#5A6370;--bd:#D9DEE4;--ac:#1C5A8A;--warn:#8F5300;--wbg:#FFF6E5;--ok:#1B7343;--no:#9B2C2C}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 "WenQuanYi Zen Hei",sans-serif;width:1440px}}
.top{{background:var(--s);border-bottom:1px solid var(--bd);padding:14px 28px;display:flex;gap:24px;align-items:center}}
.top h1{{font-size:18px;margin:0;white-space:nowrap}} .ctl{{border:1px solid var(--bd);border-radius:6px;padding:6px 12px;background:#fff}} .ctl b{{color:var(--ac)}}
.muted{{color:var(--mu)}} .wrap{{padding:20px 28px;display:grid;grid-template-columns:1.05fr 1fr;gap:20px}}
.card{{background:var(--s);border:1px solid var(--bd);border-radius:8px;padding:18px}} .card h2{{font-size:16px;margin:0 0 4px}} .sub{{color:var(--mu);font-size:12px;margin-bottom:12px}}
.full{{grid-column:1/3}} .warn{{grid-column:1/3;background:var(--wbg);border:1px solid #F0D9A8;border-radius:8px;padding:12px 16px;color:#5C3A00}} .warn b{{color:var(--warn)}}
.cal{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}} .cal div{{background:#F7F8FA;border:1px solid var(--bd);border-radius:6px;padding:10px;font-size:13px}} .cal i{{font-style:normal;color:var(--mu);font-size:12px;display:block}}
.src{{display:inline-block;margin-top:6px;font-size:11px;border-radius:10px;padding:0 8px}} .src.u{{background:#E6F4EC;color:var(--ok);border:1px solid #BFE0CC}} .src.a{{background:#FFF0D6;color:var(--warn);border:1px solid #F0D9A8}}
table{{border-collapse:collapse;width:100%}} th,td{{border-bottom:1px solid #EEF1F4;padding:8px 10px;text-align:left;font-size:13px;vertical-align:top}} thead th{{color:var(--mu);font-weight:normal;font-size:12px}}
.hm td{{border:3px solid #fff;border-radius:6px;vertical-align:top;height:74px;width:30%}} .hm th{{width:10%;color:var(--mu);vertical-align:middle}}
.hm td.ok{{background:#2A78D6;color:#fff}} .hm td.thin{{background:repeating-linear-gradient(45deg,#EEF1F4,#EEF1F4 6px,#E3E7EC 6px,#E3E7EC 12px);color:#3A424D}} .hm td.empty{{color:#C4CAD1;text-align:center;vertical-align:middle}}
.hm td.sel{{outline:3px solid var(--ac);outline-offset:-3px}} .p{{font-size:20px;font-weight:bold}} .n{{font-size:12px}} .tag{{display:inline-block;margin-top:4px;font-size:11px;background:#fff;border:1px solid #C4CAD1;border-radius:3px;padding:0 5px;color:#5A6370}}
.mono{{font-family:monospace;font-size:12px}} .chip{{display:inline-block;margin-left:6px;font-family:sans-serif;font-size:11px;background:#EAF2FB;color:var(--ac);border-radius:3px;padding:0 5px}}
.y{{color:var(--ok)}} .x{{color:var(--no)}} .m{{color:var(--mu)}} .why{{display:block;color:var(--fg);font-size:12px;margin-top:2px}}
.steps{{display:flex;gap:10px;align-items:stretch}} .st{{flex:1;background:#F7F8FA;border:1px solid var(--bd);border-radius:6px;padding:10px;font-size:13px}} .st b{{display:block;margin-bottom:4px;color:var(--ac)}} .arrow{{align-self:center;color:var(--mu)}}
.kn{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}} .kn div{{background:#F7F8FA;border:1px solid var(--bd);border-radius:6px;padding:10px;font-size:13px}} .kn i{{font-style:normal;color:var(--mu);font-size:12px;display:block}}
.badge{{display:inline-block;border-radius:10px;padding:1px 8px;font-size:12px;background:#FFF0D6;color:#8F5300;border:1px solid #F0D9A8}}
</style></head><body>
<div class="top"><h1>品类机会判定台 · 成功率判定</h1>
<span class="ctl">观察期 <b>{N} 个月 ▾</b> <span class="muted">（可选 3 / 6 / 自定义）</span></span>
<span class="muted">数据 {J["data"]} · 打标 v11 · 新品产品链 {len(F)} 个</span></div>
<div class="wrap">
<div class="card full"><h2>成功率口径</h2><div class="sub">成功率 = 成功个数 ÷ 观察期走完的个数。绿色标签 = wen 已定；橙色标签 = AI 提议，等 wen 确认</div><div class="cal">{caliber}</div></div>
<div class="warn"><b>数据体检：</b>① 表里只收录父体月销 ≥ 60 件的商品，这里是"起量新品"的成功率，不是"上架就算"的成功率；② 数据只有 {J["data"]}，观察期走完的只有 2026-06、07 上架的 {NN} 个产品，另有 {n_ob} 个观察中、{n_in} 个数据不全，不进分母；③ 所有格子 n &lt; 20，只显示数字，不下结论、不出锦囊。</div>
<div class="card"><h2>格子成功率（宽度段 × 形态）</h2><div class="sub">每格 = 成功个数 ÷ 观察期走完的个数。n ≥ 20 着色；斜纹 = 不下结论</div>
<table class="hm"><thead><tr><th></th><th>落地式</th><th>悬浮式</th><th>该尺寸全部</th></tr></thead><tbody>{grid}</tbody></table>
<div class="sub" style="margin-top:8px">全部：{K} 成功 / {NN} 个 = {pc(K, NN)}。其余形态（柱状盆、转角式等）只计入"该尺寸全部"</div></div>
<div class="card"><h2>点开：{cw} · {cf}</h2><div class="sub">这个格子的 {len(C)} 个新品，按状态分</div>
<table><thead><tr><th>状态</th><th>个数</th><th>分母</th><th>含义</th></tr></thead><tbody>{stat}</tbody></table>
<h2 style="margin-top:16px;font-size:14px">观察期走完的 {len(Cd)} 个，按台面材质拆</h2>
<table><thead><tr><th>台面材质</th><th>个数</th><th>成功</th><th>成功率</th></tr></thead><tbody>{split}</tbody></table></div>
<div class="card full"><h2>这个格子里的新品：每个勾叉都写明依据</h2><div class="sub">数据不全的 {len(st["数据不全"])} 个不列出。销售额 = 子体估算销量 × 当前快照价，按产品链求和</div>
<table><thead><tr><th>产品链（代表父 ASIN）</th><th>品牌</th><th>上架</th><th>台面</th><th>看到的月龄</th><th>结果与依据</th></tr></thead><tbody>{fams}</tbody></table></div>
<div class="card full"><h2>锦囊卡（示例：被闸门拦下）</h2><div class="sub">锦囊 = 同一语境下，做这个动作的成功率 − 默认动作的成功率。两边各 ≥ 20 个且三道反证通过，才进入排序</div>
<div class="kn"><div><i>语境</i>{cw} · {cf}</div><div><i>动作</i>台面用陶瓷<br><span class="muted">默认：其余已标台面</span></div><div><i>预期</i>{pc(ka, na)} vs {pc(kb, nb)}<br>差 {diff}</div><div><i>依据</i>陶瓷 {ka}/{na}<br>默认 {kb}/{nb}<br><span class="muted">台面未知 {un} 个，待打标复核</span></div><div><i>反证</i>数据核对 待办<br>稳健性 待办<br>留批次 未达样本</div><div><i>状态</i><span class="badge">不出 · 样本不足</span></div></div></div>
<div class="card full"><h2>运算链（每一步可点开）</h2><div class="steps">
<div class="st"><b>① 原始行</b>子 ASIN × 月：估算销量、快照价、当月小类 BSR、v11 标签</div><div class="arrow">→</div>
<div class="st"><b>② 产品链</b>同一子 ASIN 挂过的父 ASIN 串成一个；上架 = 链内最早子体</div><div class="arrow">→</div>
<div class="st"><b>③ 逐月判定</b>该月任一子体 BSR ≤ 50 或链内销售额 ≥ $10 万，记下首次达线的月和数值</div><div class="arrow">→</div>
<div class="st"><b>④ 状态</b>成功 / 未成功 / 观察中 / 数据不全；后两种不进分母</div><div class="arrow">→</div>
<div class="st"><b>⑤ 成功率</b>成功 ÷（成功 + 未成功）；格子 n ≥ 20 才着色、才出锦囊</div></div></div>
</div></body></html>'''
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '成功率判定_画像.html'), 'w', encoding='utf-8').write(html)
