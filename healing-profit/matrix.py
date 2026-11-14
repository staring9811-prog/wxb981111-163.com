# -*- coding: utf-8 -*-
"""Market-layout matrices (rows = size / config, column groups = material / feature) from SellerSprite
Amazon child listings (mkt/*.csv). Parent sales are counted once: SellerSprite repeats the parent's monthly
units on every child, so each parent's units are split evenly across its children in the sample."""
import csv, html, os, re, json
from collections import defaultdict

E = html.escape

def load(path):
    rows, seen = [], set()
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            a = r.get("asin")
            if not a or a in seen:
                continue
            seen.add(a)
            def num(k):
                try: return float(r.get(k) or "")
                except ValueError: return None
            r["price"], r["units"], r["rating"] = num("price"), num("units") or 0.0, num("rating")
            r["t"] = html.unescape((r.get("title") or "") + " " + (r.get("sku") or "")).lower()
            rows.append(r)
    return rows

def split_parent_units(rows):
    """Each child carries the parent's units; give every child units / children."""
    by_p = defaultdict(list)
    for r in rows:
        by_p[r.get("parent") or r["asin"]].append(r)
    for kids in by_p.values():
        u = max(k["units"] for k in kids)
        for k in kids:
            k["u"] = u / len(kids); k["pu"] = u; k["sib"] = len(kids)
    return rows

# ---------------- classifiers ----------------
def sauna_keep(t):
    if re.search(r"tent|blanket|\bpod\b|portable|dome|sauna box|\bbag\b|\bmat\b|steam|traditional|barrel|stove", t):
        return False
    if re.search(r"heater", t) and not re.search(r"person|room|cabin", t):
        return False
    return bool(re.search(r"infrared|full spectrum|far ir|far-ir|carbon|ceramic|red light", t)) and bool(re.search(r"person|people|sauna room|indoor sauna|outdoor sauna|home sauna", t))

WORDN = {"one": 1, "single": 1, "two": 2, "double": 2, "three": 3, "four": 4, "five": 5, "six": 6}
def sauna_cap(t):
    t2 = re.sub(r"\b(one|single|two|double|three|four|five|six)\b", lambda m: str(WORDN[m.group(1)]), t)
    m = re.search(r"(\d)\s*(?:-|to|~|–|or)\s*(\d)\s*(?:person|people|persons)", t2)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a == 1 and b == 2: return "1-2 人"
        if a == 2 and b == 3: return "2-3 人"
        if a == 3 and b == 4: return "3-4 人"
        return "4 人+" if a >= 4 else ("3-4 人" if a == 3 else f"{a}-{b} 人")
    m = re.search(r"(\d)\s*(?:person|people|persons|-person)", t2)
    if m:
        n = int(m.group(1))
        return {1: "1 人", 2: "2 人", 3: "3-4 人"}.get(n, "4 人+")
    return "未注明"
SAUNA_ROWS = ["1 人", "1-2 人", "2 人", "2-3 人", "3-4 人", "4 人+", "未注明"]
def sauna_wood(t):
    if "hemlock" in t: return "铁杉"
    if "cedar" in t: return "雪松"
    if re.search(r"spruce|pine|\bfir\b", t): return "云杉 / 松木 / 冷杉"
    return "其他 / 未注明"
SAUNA_COLS = ["铁杉", "雪松", "云杉 / 松木 / 冷杉", "其他 / 未注明"]

def tandem_keep(t):
    if not re.search(r"tandem|two people|2 people|couples|for two|2 person|double shower head", t):
        return False
    return not re.search(r"valve|faucet set|rough-in|trim kit|thermostatic|body jet|shower system faucet", t)
def tandem_cfg(t):
    if re.search(r"triple|3 shower head|three shower|3-way tandem|3 heads", t): return "三头（含手持）"
    if re.search(r"hand ?held|hand-held|handheld", t): return "双头 + 手持"
    return "双头"
TANDEM_COLS = ["双头", "双头 + 手持", "三头（含手持）"]
def load_tandem_detail(path):
    """parent/asin -> (rod-span row, material column) from asin_detail (overviews.Material, feature bullets)."""
    out = {}
    if not os.path.exists(path): return out
    for line in open(path, encoding="utf-8"):
        d = json.loads(line)
        ov = d.get("overviews") or "{}"
        try: ov = json.loads(ov) if isinstance(ov, str) else (ov or {})
        except Exception: ov = {}
        m = (ov.get("Material") or "").lower()
        plastic = bool(re.search(r"acrylonitrile|\babs\b|plastic", m))
        steel = "stainless" in m; metal = bool(re.search(r"metal|brass|alloy|zinc|copper", m))
        if not m: mat = "未注明"
        elif plastic and (steel or metal): mat = "ABS + 不锈钢 / 金属"
        elif plastic: mat = "ABS / 塑料"
        elif steel: mat = "不锈钢"
        else: mat = "金属 / 黄铜"
        f = " ".join(d.get("features") or []) + " " + (d.get("dimensions") or "")
        nums = [float(x) for x in re.findall(r"(\d{2}(?:\.\d)?)\s*(?:-|\s)?(?:inch|inches|in\b|\"|”)", f, re.I) if 30 <= float(x) <= 100]
        span = max(nums) if nums else None
        row = "未注明" if span is None else ("≤60″" if span <= 60 else ("61–80″" if span <= 80 else "81″+"))
        v = (row, mat, span, ov.get("Material") or "")
        out[d["asin"]] = v
        if d.get("parent"): out[d["parent"]] = v
    return out
TANDEM2_ROWS = ["≤60″", "61–80″", "81″+", "未注明"]
TANDEM2_COLS = ["ABS / 塑料", "ABS + 不锈钢 / 金属", "不锈钢", "金属 / 黄铜", "未注明"]

def band(p, edges, labels):
    for e, l in zip(edges, labels):
        if p < e: return l
    return labels[-1]
TANDEM_ROWS = ["< $80", "$80–120", "$120–180", "$180–250", "$250+"]
def tandem_row(p): return band(p, [80, 120, 180, 250], TANDEM_ROWS)

def thermo_keep(t, p):
    if p is None or p > 2500: return False
    if not re.search(r"system|set|combo|kit", t): return False
    if re.search(r"valve only|trim only|replacement|cartridge only|body spray trim", t): return False
    return bool(re.search(r"thermostatic|body jet|body spray|jets", t))
def thermo_jets(t):
    m = re.search(r"(\d+)\s*(?:pcs|pieces|x)?\s*(?:-|\s)?(?:body\s*)?(?:spray\s*)?(?:massage\s*)?jets?\b", t)
    if m and 1 <= int(m.group(1)) <= 12:
        n = int(m.group(1)); return "6 个及以上" if n >= 6 else "2–4 个"
    if re.search(r"(?:six|6)\s*(?:pcs)?\s*body", t): return "6 个及以上"
    if re.search(r"(?:four|4)\s*(?:pcs)?\s*body", t): return "2–4 个"
    if re.search(r"body jet|body spray|jets", t): return "有侧喷（数量未注明）"
    return "无侧喷"
THERMO_COLS = ["无侧喷", "2–4 个", "6 个及以上", "有侧喷（数量未注明）"]
def thermo_top(t):
    if re.search(r"(\d{2})\s*(?:\"|inch|in\.?)?\s*[x×\*]\s*(\d{2})", t): return "方形大顶喷（14×20″ 等）"
    sizes = [int(x) for x in re.findall(r"(\d{1,2})(?:\"|''|”|\s?-?inch|\s?in\b)", t) if 4 <= int(x) <= 30]
    if not sizes: return "未注明"
    s = max(sizes)
    if s <= 10: return "≤10″"
    if s <= 13: return "12″"
    if s <= 18: return "16″"
    return "20″+"
THERMO_ROWS = ["≤10″", "12″", "16″", "20″+", "方形大顶喷（14×20″ 等）", "未注明"]

TAGS = {
 "sauna": [("红光", r"red light|660|850 ?nm|near.infrared"), ("全光谱", r"full spectrum"), ("低 EMF", r"low.emf|ultra.low"), ("彩光疗法", r"chromo|7.colou?r|color light|colou?rful"),
           ("蓝牙", r"bluetooth|speaker"), ("App / WiFi", r"\bapp\b|wifi|wi-fi|smart"), ("碳晶 / 碳纤维板", r"carbon"), ("陶瓷加热", r"ceramic"), ("云母板", r"mica"),
           ("户外款", r"outdoor"), ("负离子 / 氧吧", r"ioniz|oxygen|negative ion"), ("盐砖", r"salt"), ("钢化玻璃", r"glass"), ("角落款", r"corner"), ("240V", r"240v|220v")],
 "tandem": [("带手持", r"hand ?held|hand-held"), ("过滤", r"filter"), ("不锈钢", r"stainless"), ("全金属", r"all.metal|brass"), ("免打孔 / 租房友好", r"no.drill|renter|drill.free|tool.free"),
            ("可调滑杆", r"slider|slide bar|adjustable"), ("高压", r"high pressure"), ("磁吸", r"magnet"), ("黑色", r"black"), ("金色", r"gold"), ("拉丝镍", r"nickel|brushed")],
 "thermo": [("恒温", r"thermostatic"), ("压力平衡", r"pressure.balanc"), ("LED", r"\bled\b"), ("数显温度", r"digital|display"), ("蓝牙音乐", r"bluetooth|music"),
            ("瀑布", r"waterfall"), ("吸顶", r"ceiling"), ("壁挂", r"wall.mount"), ("含预埋阀", r"rough.in|valve (?:and trim|included)|with valve"),
            ("可同时出水", r"simultaneous|run (?:all )?together|at (?:the same|one) time|use at once"), ("浴缸龙头", r"tub spout|bathtub"), ("全铜", r"brass"), ("双顶喷", r"dual (?:rain|shower) head|double shower head|dual head")],
}
SPRITE_PX = 88
SPRITE_COLS = 24
def load_meta(path):
    m = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                m[r["asin"]] = html.unescape(r.get("brand") or "")
    return m

def make_sprite(asins, img_dir, out_path):
    """Pack thumbnails into one JPEG; returns {asin: index}. Missing images get no index."""
    from PIL import Image
    have = [a for a in asins if os.path.exists(os.path.join(img_dir, a + ".jpg"))]
    n = len(have); cols = SPRITE_COLS; rows = (n + cols - 1) // cols or 1
    sheet = Image.new("RGB", (cols * SPRITE_PX, rows * SPRITE_PX), (255, 255, 255))
    idx = {}
    for i, a in enumerate(have):
        try:
            im = Image.open(os.path.join(img_dir, a + ".jpg")).convert("RGB")
            im.thumbnail((SPRITE_PX - 4, SPRITE_PX - 4))
            x = (i % cols) * SPRITE_PX + (SPRITE_PX - im.width) // 2
            y = (i // cols) * SPRITE_PX + (SPRITE_PX - im.height) // 2
            sheet.paste(im, (x, y)); idx[a] = i
        except Exception:
            pass
    sheet.save(out_path, "JPEG", quality=78, optimize=True)
    return idx, rows

def cell_items(rows, rowf, colf, mid, brands=None, sprite=None):
    tags = [(n, re.compile(p)) for n, p in TAGS.get(mid, [])]
    brands = brands or {}; sprite = sprite or {}
    out = defaultdict(list)
    for r in rows:
        k = f"{mid}|{rowf(r)}|{colf(r)}"
        out[k].append({"a": r["asin"], "b": brands.get(r["asin"], ""), "i": sprite.get(r["asin"], -1), "p": r["price"], "u": round(r["u"], 1), "pu": round(r.get("pu", 0)),
                       "rt": r["rating"], "rn": r.get("ratings") or "", "t": html.unescape(r.get("title") or "")[:220],
                       "sku": html.unescape(r.get("sku") or "")[:80], "tg": (r.get("ex") or []) + [n for n, rx in tags if rx.search(r["t"])]})
    for v in out.values():
        v.sort(key=lambda x: -x["u"])
    return dict(out)

def build(rows, rowf, colf, row_names, col_names):
    cell = defaultdict(lambda: {"u": 0.0, "n": 0, "pu": 0.0, "ru": 0.0, "rw": 0.0, "pn": 0.0})
    for r in rows:
        k = (rowf(r), colf(r)); c = cell[k]
        c["u"] += r["u"]; c["n"] += 1
        w = max(r["u"], 0.01)
        if r["price"]: c["pu"] += r["price"] * w; c["pn"] += w
        if r["rating"]: c["ru"] += r["rating"] * w; c["rw"] += w
    out = {}
    for k, c in cell.items():
        out[k] = dict(u=c["u"], n=c["n"], per=c["u"] / c["n"] if c["n"] else 0,
                      price=c["pu"] / c["pn"] if c["pn"] else None, rating=c["ru"] / c["rw"] if c["rw"] else None)
    rows_used = [r for r in row_names if any((r, c) in out for c in col_names)]
    cols_used = [c for c in col_names if any((r, c) in out for r in row_names)]
    return out, rows_used, cols_used

def render(title, sub, data, rows, cols, ours, row_label="尺寸", footnote="", mid="m"):
    """ours: {row: {"cells": [col,...], "price": str, "margin": str, "cls": "good|warn|bad"}}"""
    out = data
    maxper = max((v["per"] for v in out.values()), default=1) or 1
    tot = sum(v["u"] for v in out.values()) or 1
    h1 = f'<th rowspan="2" class="rh">{row_label}</th>' + "".join(f'<th colspan="5" class="g g{i%2}">{E(c)}</th>' for i, c in enumerate(cols)) + \
         '<th rowspan="2" class="tot">合计<br>月销</th><th rowspan="2" class="our">我们<br>售价</th><th rowspan="2" class="our">我们<br>利润率</th>'
    h2 = "".join(f'<th class="s g{i%2}">月销</th><th class="s g{i%2}">ASIN数</th><th class="s g{i%2}">单ASIN<br>月销</th><th class="s g{i%2}">加权<br>均价</th><th class="s g{i%2}">加权<br>评分</th>' for i, _ in enumerate(cols))
    body = []
    for r in rows:
        o = ours.get(r)
        cls = ' class="mine"' if o else ""
        tag = ' <span class="chip">我们</span>' if o else ""
        tds = []
        for i, c in enumerate(cols):
            v = out.get((r, c)); box = o and c in o["cells"]
            b = " box" if box else ""
            if not v:
                tds.append(f'<td class="dash first{b}">—</td><td class="{b.strip()}"></td><td class="{b.strip()}"></td><td class="{b.strip()}"></td><td class="last{b}"></td>')
                continue
            a = 0.08 + 0.62 * (v["per"] / maxper)
            rt = v["rating"]
            rcls = "low" if rt is not None and rt < 4.0 else ""
            k = E(f"{mid}|{r}|{c}", quote=True)
            d = f' data-k="{k}"'
            tds.append(f'<td class="clk first{b}"{d}>{v["u"]:,.0f}</td><td class="clk {b.strip()}"{d}>{v["n"]}</td>'
                       f'<td class="clk heat{b}" style="--a:{a:.2f}"{d} tabindex="0" role="button" aria-label="查看 {E(r)} × {E(c)} 的产品">{v["per"]:,.1f}</td>'
                       f'<td class="clk {b.strip()}"{d}>{"$" + format(v["price"], ",.0f") if v["price"] else "—"}</td>'
                       f'<td class="clk last{b} {rcls}"{d}>{f"{rt:.2f}" if rt else "—"}</td>')
        rt = sum(out[(r, c)]["u"] for c in cols if (r, c) in out)
        mp = f'<td class="our">{o["price"]}</td><td class="our"><span class="pill {o["cls"]}">{o["margin"]}</span></td>' if o else '<td class="our"></td><td class="our"></td>'
        body.append(f'<tr{cls}><th scope="row" class="rh">{E(r)}{tag}</th>{"".join(tds)}<td class="tot">{rt:,.0f}</td>{mp}</tr>')
    foot = []
    for i, c in enumerate(cols):
        cu = sum(out[(r, c)]["u"] for r in rows if (r, c) in out)
        foot.append(f'<td class="first">{cu:,.0f}</td><td colspan="4" class="last share">占 {cu/tot*100:.0f}%</td>')
    body.append(f'<tr class="sum"><th scope="row" class="rh">合计</th>{"".join(foot)}<td class="tot">{tot:,.0f}</td><td class="our"></td><td class="our"></td></tr>')
    return (f'<figure class="mx-fig"><figcaption><b>{E(title)}</b><span>{E(sub)}</span></figcaption>'
            f'<div class="tw mxw"><table class="mx"><thead><tr>{h1}</tr><tr>{h2}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
            f'<p class="note">点任意有数据的格子可查看该格的具体产品。单ASIN月销 = 月销 ÷ ASIN数，越高底色越深；评分低于 4.0 标红；黄色行 / 橙框为我们的产品落点。{footnote}</p></figure>')

MX_CSS = """
.mx-fig{margin:0;display:grid;gap:8px;width:min(1480px,calc(100vw - 32px));position:relative;left:50%;transform:translateX(-50%)}
.mx-fig figcaption{display:grid;gap:2px} .mx-fig figcaption b{font-size:16px} .mx-fig figcaption span{font-size:12.5px;color:var(--muted)}
table.mx{font-size:12.5px;border-collapse:separate;border-spacing:0}
table.mx th,table.mx td{padding:6px 7px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
table.mx thead th{text-align:center;font-weight:500;color:var(--fg);font-size:12px}
table.mx th.g0{background:var(--g0)} table.mx th.g1{background:var(--g1)}
table.mx th.rh{text-align:center;background:var(--bg);font-weight:500;position:sticky;left:0;z-index:1}
table.mx td.first{border-left:2px solid var(--line)}
table.mx td.dash{color:var(--muted);text-align:center}
table.mx td.heat{background:color-mix(in srgb,var(--heat) calc(var(--a)*100%),transparent)}
table.mx td.low{color:var(--bad);font-weight:600}
table.mx td.tot,table.mx th.tot{border-left:2px solid var(--line);font-weight:600}
table.mx td.our,table.mx th.our{background:var(--mine-bg)}
table.mx tr.mine>th.rh,table.mx tr.mine>td{background-color:var(--mine-bg)}
table.mx tr.mine>td.heat{background:color-mix(in srgb,var(--heat) calc(var(--a)*100%),var(--mine-bg))}
table.mx td.box{outline:2px solid var(--box);outline-offset:-2px}
table.mx tr.sum td,table.mx tr.sum th{background:var(--bg);font-weight:600} table.mx td.share{text-align:left;color:var(--muted);font-weight:400}
.chip{display:inline-block;font-size:10.5px;background:var(--box);color:#fff;border-radius:4px;padding:0 5px;margin-left:4px;vertical-align:1px}
"""

MX_CSS += """
table.mx td.clk{cursor:pointer}
table.mx tr:hover td.clk{filter:brightness(0.97)}
table.mx td.clk:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.mxp-bg[hidden]{display:none!important}
.mxp-bg{position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:50;display:flex;justify-content:flex-end}
.mxp{background:var(--panel);color:var(--fg);width:min(860px,100%);height:100%;overflow:auto;padding:calc(18px + env(safe-area-inset-top,0px)) max(18px,env(safe-area-inset-right,0px)) 24px 18px;display:grid;gap:12px;align-content:start;box-shadow:-8px 0 24px rgba(0,0,0,.2)}
.mxp-h{display:flex;justify-content:space-between;gap:12px;align-items:start}
.mxp-h h3{font-size:17px} .mxp-h p{font-size:12.5px;color:var(--muted);margin-top:4px}
.mxp-x{border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:8px;padding:4px 12px;font:inherit;cursor:pointer}
.mxp-k{display:flex;flex-wrap:wrap;gap:8px}
.mxp-k span{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:12.5px;color:var(--muted)} .mxp-k b{color:var(--fg);font-family:var(--f-num);margin-left:4px}
.mxp-l{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.mxp-l li{border:1px solid var(--line);border-radius:10px;padding:10px 12px;display:grid;grid-template-columns:88px minmax(0,1fr);gap:12px;align-items:start}
.mxp-c{display:grid;gap:6px;min-width:0}
.mxp-img{width:88px;height:88px;border-radius:8px;background-color:#fff;background-repeat:no-repeat;border:1px solid var(--line)}
.mxp-img.none{display:grid;place-items:center;font-size:11px;color:#888}
.mxp-b{display:inline-block;font-size:12px;font-weight:600;margin-right:6px;padding:0 6px;border-radius:4px;background:var(--bg);border:1px solid var(--line)}
@media (max-width:520px){.mxp-l li{grid-template-columns:64px minmax(0,1fr)} .mxp-img{width:88px;height:88px;transform:scale(.727);transform-origin:0 0;margin-bottom:-24px}}
.mxp-t{font-size:13.5px;line-height:1.5} .mxp-t a{color:var(--accent);text-decoration:none;font-family:var(--f-num);font-size:12.5px;margin-right:6px}
.mxp-m{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12.5px;color:var(--muted)} .mxp-m b{color:var(--fg);font-family:var(--f-num);font-weight:600}
.mxp-m .low{color:var(--bad)}
.mxp-g{display:flex;flex-wrap:wrap;gap:4px} .mxp-g span{font-size:11.5px;border-radius:20px;padding:1px 8px;background:var(--accent-soft);color:var(--accent)}
.mxp-s{font-size:12px;color:var(--muted)}
"""
MX_JS_T = r"""
<div class="mxp-bg" id="mxp" hidden><aside class="mxp" role="dialog" aria-modal="true" aria-labelledby="mxp-title">
  <div class="mxp-h"><div><h3 id="mxp-title"></h3><p id="mxp-sub"></p></div><button type="button" class="mxp-x" id="mxp-x">关闭</button></div>
  <div class="mxp-k" id="mxp-k"></div><ul class="mxp-l" id="mxp-l"></ul></aside></div>
<script>
(function(){
  var D={}; try{D=JSON.parse(document.getElementById('mxdata').textContent);}catch(e){}
  var PX=%d, COLS=%d;
  var bg=document.getElementById('mxp'), L=document.getElementById('mxp-l'), last=null;
  function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  function money(v){return v==null?'—':'$'+Number(v).toLocaleString('en-US',{maximumFractionDigits:2});}
  function open(k,src){
    var it=D[k]||[]; var p=k.split('|'); last=src;
    var names={sauna:'红外桑拿房',tandem:'双人淋浴花洒',thermo:'恒温 / 侧喷系统'};
    document.getElementById('mxp-title').textContent=(names[p[0]]||'')+' · '+p[1]+' × '+p[2];
    var u=0,pw=0,pp=0,rw=0,rr=0; it.forEach(function(x){u+=x.u; var w=Math.max(x.u,0.01); if(x.p){pp+=x.p*w;pw+=w;} if(x.rt){rr+=x.rt*w;rw+=w;}});
    document.getElementById('mxp-sub').textContent='Amazon 2026-10 · 按分摊月销从高到低 · 父体月销按子体平均分摊';
    document.getElementById('mxp-k').innerHTML='<span>月销<b>'+Math.round(u).toLocaleString()+'</b></span><span>ASIN 数<b>'+it.length+'</b></span><span>加权均价<b>'+(pw?money(Math.round(pp/pw)):'—')+'</b></span><span>加权评分<b>'+(rw?(rr/rw).toFixed(2):'—')+'</b></span>';
    L.innerHTML=it.map(function(x){
      var rc=x.rt!=null&&x.rt<4?' class="low"':'';
      var img=x.i>=0?'<div class="mxp-img" style="background-image:url('+((window.MX_SPRITES||{})[p[0]]||('sprite_'+p[0]+'.jpg'))+');background-position:-'+((x.i%COLS)*PX)+'px -'+(Math.floor(x.i/COLS)*PX)+'px"></div>':'<div class="mxp-img none">无图</div>';
      return '<li>'+img+'<div class="mxp-c"><div class="mxp-t">'+(x.b?'<b class="mxp-b">'+esc(x.b)+'</b>':'')+'<a href="https://www.amazon.com/dp/'+esc(x.a)+'" target="_blank" rel="noopener">'+esc(x.a)+' ↗</a>'+esc(x.t)+'</div>'+
        '<div class="mxp-m"><span>售价 <b>'+money(x.p)+'</b></span><span>月销（分摊）<b>'+x.u+'</b></span><span>父体月销 <b>'+x.pu+'</b></span><span>评分 <b'+rc+'>'+(x.rt==null?'—':x.rt)+'</b>（'+esc(x.rn||0)+' 评）</span></div>'+
        (x.sku?'<div class="mxp-s">变体：'+esc(x.sku)+'</div>':'')+
        (x.tg&&x.tg.length?'<div class="mxp-g">'+x.tg.map(function(t){return '<span>'+esc(t)+'</span>';}).join('')+'</div>':'')+'</div></li>';
    }).join('');
    bg.hidden=false; document.getElementById('mxp-x').focus();
  }
  function close(){bg.hidden=true; if(last&&last.focus) last.focus();}
  document.addEventListener('click',function(e){var td=e.target.closest&&e.target.closest('td[data-k]'); if(td) open(td.getAttribute('data-k'),td);});
  document.addEventListener('keydown',function(e){ if(e.key==='Escape'&&!bg.hidden) close(); var td=e.target.closest&&e.target.closest('td[data-k]'); if(td&&(e.key==='Enter'||e.key===' ')){e.preventDefault(); open(td.getAttribute('data-k'),td);} });
  bg.addEventListener('click',function(e){ if(e.target===bg) close(); });
  document.getElementById('mxp-x').addEventListener('click',close);
})();
</script>
"""

MX_JS = MX_JS_T.replace("var PX=%d, COLS=%d;", f"var PX={SPRITE_PX}, COLS={SPRITE_COLS};")
