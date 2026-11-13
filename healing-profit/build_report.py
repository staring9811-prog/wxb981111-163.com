# -*- coding: utf-8 -*-
"""Build the healing-category profit report (index.html) and a v1.14 calculator import file.
Inputs: calc_out.json (v1.14 calcProduct output, via run.js), summary.json (break-even / max cost)."""
import json, os, html
HERE = os.path.dirname(os.path.abspath(__file__))
calc = json.load(open(os.path.join(HERE, "calc_out.json"), encoding="utf-8"))
summ = json.load(open(os.path.join(HERE, "summary.json"), encoding="utf-8"))
scen = json.load(open(os.path.join(HERE, "scen.json"), encoding="utf-8"))
R = {(r["sku"], r["tier"]): r for r in calc["res"]}
HC = {}
for r in json.load(open(os.path.join(HERE, "calc_hc103.json"), encoding="utf-8"))["res"]:
    HC[(r["sku"], r["tier"])] = r

def wx_table():
    head = "".join(f"<th>{t}</th>" for _, t in TIERS)
    def row(name, get):
        cells = []
        for t, _ in TIERS:
            price, profit, m = get(t)
            cells.append(f'<td><div class="cell"><span class="price">{usd(price)}</span><span class="profit {"neg" if profit < 0 else ""}">{usd(profit)}</span>{pill(m)}</div></td>')
        return f'<tr><th scope="row">{name}</th>{"".join(cells)}</tr>'
    amz = lambda k: (lambda t: (HC[(k, t)]["amzPrice"], HC[(k, t)]["fbm"], HC[(k, t)]["fbm"] / HC[(k, t)]["amzPrice"]))
    pl = lambda k, c: (lambda t: (HC[(k, t)]["plat"][c]["retail"], HC[(k, t)]["plat"][c]["profit"], HC[(k, t)]["plat"][c]["margin"]))
    rows = [
        row("对照：SAD6221-1 珠三角 ¥6,270 · Amazon FBM", lambda t: (R[("SAD6221-1", t)]["amzPrice"], R[("SAD6221-1", t)]["fbm"], R[("SAD6221-1", t)]["fbm"] / R[("SAD6221-1", t)]["amzPrice"])),
        row("SMT-HC103 包装 +10% · Amazon FBM", amz("SMT-HC103")),
        row("SMT-HC103 包装 +10% · Home Depot", pl("SMT-HC103", "hd")),
        row("SMT-HC103 包装 +10% · Lowe's SC", pl("SMT-HC103", "lowesSC")),
        row("SMT-HC103 包装 +10% · Wayfair", pl("SMT-HC103", "wf")),
        row("参考：SMT-HC103 原包装 · Amazon FBM", amz("SMT-HC103-orig")),
    ]
    return (f'<div class="tw"><table class="pt"><thead><tr><th>方案（单人房）</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')
S = {(r["sku"], r["tier"]): r for r in summ}
E = html.escape

def usd(v, d=0):
    s = f"{abs(v):,.{d}f}"
    return ("−$" if v < 0 else "$") + s

def pill(m):
    if m is None:
        return '<span class="pill na">无同类</span>'
    cls = "good" if m >= 0.15 else ("warn" if m >= 0 else "bad")
    lab = "达标" if m >= 0.15 else ("微利" if m >= 0 else "亏损")
    return f'<span class="pill {cls}" title="{lab}">{m*100:.0f}%</span>'

CH = [("amzFBA", "Amazon FBA"), ("amzFBM", "Amazon FBM（自发货）"), ("hd", "Home Depot"),
      ("lowesVC", "Lowe's VC"), ("lowesSC", "Lowe's SC"), ("wf", "Wayfair")]
TIERS = [("low", "低价带"), ("mid", "中价带"), ("high", "高价带")]

def profit_table(sku, order):
    head = "".join(f"<th>{t}</th>" for _, t in TIERS)
    body = []
    for k, name in order:
        cells = []
        for t, _ in TIERS:
            v = S[(sku, t)].get(k)
            if not v:
                cells.append('<td class="na-cell"><span class="pill na">无同类</span></td>')
                continue
            cells.append(
                f'<td><div class="cell"><span class="price">{usd(v["price"], 2 if v["price"] < 300 else 0)}</span>'
                f'<span class="profit {"neg" if v["profit"] < 0 else ""}">{usd(v["profit"])}</span>{pill(v["margin"])}</div></td>')
        body.append(f'<tr><th scope="row">{name}</th>{"".join(cells)}</tr>')
    return (f'<div class="tw"><table class="pt"><thead><tr><th>渠道</th>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>'
            '<p class="note">每格：前台售价 · 单件利润 · 利润率。Amazon 利润率 = 利润 ÷ 售价；Home Depot / Lowe\'s / Wayfair = 利润 ÷ 平台结算价（前台价 ÷ 加价倍率）。'
            '颜色：<span class="pill good">≥15% 达标</span> <span class="pill warn">0–15% 微利</span> <span class="pill bad">亏损</span></p>')

def need_table(sku, chans):
    rows = []
    for k, name in chans:
        be = S[(sku, "mid")][k]["breakeven"]
        mx = [S[(sku, t)].get(k) for t, _ in TIERS]
        cells = "".join(
            f'<td>{"—" if not v else ("<span class=neg>无解</span>" if v["maxCostRMB"] <= 0 else "¥" + format(v["maxCostRMB"], ",d"))}</td>' for v in mx)
        rows.append(f'<tr><th scope="row">{name}</th><td>{usd(be)}</td>{cells}</tr>')
    return ('<div class="tw"><table class="nt"><thead><tr><th>渠道</th><th>保本前台价</th>'
            '<th>低价带下最高采购价</th><th>中价带下最高采购价</th><th>高价带下最高采购价</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')

def bar(label, price, parts, profit):
    total = sum(v for _, v, _ in parts)
    scale = max(total, price)
    segs = "".join(
        f'<span class="seg s{i+1}" style="width:{v/scale*100:.2f}%" title="{n} {usd(v)}"></span>' for i, (n, v, _) in enumerate(parts))
    mark = price / scale * 100
    legend = "".join(f'<li><i class="sw s{i+1}"></i>{n}<b>{usd(v)}</b><em>{d}</em></li>' for i, (n, v, d) in enumerate(parts))
    res = f'<b class="{"neg" if profit < 0 else "pos"}">{"利润" if profit >= 0 else "亏损"} {usd(profit)}（{profit/price*100:.0f}%）</b>'
    return (f'<div class="bar"><div class="bar-h"><span>{label}</span><span>售价 {usd(price, 2 if price < 300 else 0)} · 成本合计 {usd(total)} · {res}</span></div>'
            f'<div class="track"><div class="fill">{segs}</div><span class="pricemark" style="left:{mark:.2f}%"><span>售价</span></span></div>'
            f'<ul class="lg">{legend}</ul></div>')

def parts_amz(r, ship_key, ship_name):
    return [("采购成本", r["cost"], "出厂价换美元"), ("头程海运", r["sea"], "按体积分摊整柜"),
            (ship_name, r[ship_key], "尾程 / 配送"),
            ("平台费用", r["fees"], f'佣金 {usd(r["comm"])} + 广告 {usd(r["promo"])} + 退款 {usd(r["refund"])} + 汇损 {usd(r["fx"])}')]

d_mid, s1_mid, s2_mid = R[("DUAL", "mid")], R[("SAD6221-1", "mid")], R[("SAD6221-2", "mid")]
bars = (bar("双人淋浴花洒 · Amazon FBA · 中价带", d_mid["amzPrice"], parts_amz(d_mid, "fbaShip", "FBA 配送费"), d_mid["fba"]) +
        bar("SAD6221-1 单人桑拿房 · Amazon FBM · 中价带", s1_mid["amzPrice"], parts_amz(s1_mid, "fbmShip", "LTL 尾程"), s1_mid["fbm"]) +
        bar("SAD6221-2 1-2 人桑拿房 · Amazon FBM · 中价带", s2_mid["amzPrice"], parts_amz(s2_mid, "fbmShip", "LTL 尾程"), s2_mid["fbm"]))

# ---------------- price-tier content (curated from channel pages + SellerSprite, 2026-11) ----------------
DUAL_TIERS = [
 ("低价带", "$60–95", [
   ("Amazon", "Nuodan 6\" 双头滑杆淋浴", "$74.99", "月销约 160"),
   ("Amazon", "Voolan 双头滑杆淋浴", "$79.99", "月销约 140"),
   ("Amazon", "TRIPHIL 16\" 宽杆双头", "$69.99", ""),
   ("Wayfair", "SR SUN RISE 双人横杆淋浴", "$92.99", "")],
  ["花洒头 ABS 电镀，横杆铝或薄不锈钢", "2 个固定头，无手持或塑料手持", "3–8 种出水模式", "免打孔、租房友好，靠低价走量"]),
 ("中价带", "$120–190", [
   ("Amazon", "OURBAOFU 双头 + 手持（采购参考款）", "$139.99–189.99", "月销约 320，4.4★"),
   ("Amazon", "KES 原创可调滑杆 7 模式", "$159.99–169.99", "Home Depot $159.99 / Wayfair $163.99"),
   ("Amazon", "Novast / SOOVOW 双头系统", "$119.99–159.98", ""),
   ("Lowe's", "Justincity 双人滑杆淋浴", "$177.98", "")],
  ["不锈钢滑杆 + 2 个头 + 手持，三出水", "三通分水阀，可单独或同时出水", "7 种左右出水模式，高度/角度可调", "部分带过滤芯；多色饰面（黑/镍/金）"]),
 ("高价带", "$220–400", [
   ("Amazon", "BOONA Tandem Shower（Shark Tank 款）", "$220–319", "月销约 525，4.8★ 1,228 评"),
   ("Lowe's", "ITOPFOX 三头全金属双人系统", "$297–387", ""),
   ("Lowe's", "LAIFUCAM 双人淋浴杆 5 模式", "$397.48", "")],
  ["全金属（黄铜 / 不锈钢）机身与滑杆", "专利滑杆结构，单手调距", "品牌背书 + 大量高分评价", "礼品化包装（情侣 / 家庭场景）"]),
]
SAUNA_TIERS = [
 ("低价带", "$700–1,000", [
   ("Amazon", "Albott 1 人低 EMF 红外桑拿", "$899.99", "月销约 160（父体）"),
   ("Amazon", "Homsido 1 人铁杉 900W", "$749–949", "月销约 100（父体）"),
   ("Home Depot", "Spygo 1 人欧洲白杨木 6 板", "$979", ""),
   ("Wayfair", "Sauna Pro 1 人奥克曼木", "$995.99（原价 $2,049.99）", "4.7★")],
  ["智利松 / 云杉 / 白杨或基础铁杉", "900–1,050W 碳纤维板 4–6 片", "5–6mm 钢化玻璃，矮款 59–67\"", "蓝牙 + LCD 面板，无红光、无 App"]),
 ("中价带", "$1,100–1,500", [
   ("Amazon", "Dynamic Saunas Elite 1 人", "$1,299–1,499", "704 评，4.6★"),
   ("Amazon", "Homsido 1 人红光美容灯款", "$1,149–1,399", ""),
   ("Home Depot", "SaunaSpa S13HD 1 人铁杉触控", "$1,441", "65 评，5★"),
   ("Wayfair", "Holaki 1 人远红外", "$1,399", "")],
  ["加拿大铁杉", "1,200–1,450W 低 EMF 碳板", "7 色光疗 + 红光美容灯 / 负离子", "触控面板 + 蓝牙，高度 67–75\""]),
 ("高价带", "$1,700–2,800", [
   ("Home Depot", "Backyard Discovery Rylan 1 人雪松", "$1,799", "104 评，4.9★"),
   ("Amazon", "Dynamic Saunas Barcelona 1-2 人", "$1,799.99", "781 评，4.6★"),
   ("Home Depot", "Maxxus 全光谱红光 1 人", "$2,055", ""),
   ("Lowe's", "LOVMOR 1 人红雪松", "$2,818.90", "")],
  ["红雪松或品牌铁杉", "全光谱：远红外 + 近红外 660/850nm 红光", "App / WiFi 控制，户外防水款", "美国品牌（Dynamic、Backyard Discovery、Sunray）+ 大量评价"]),
]

def tier_cards(tiers, ours_tier):
    out = []
    for name, rng, prods, feats in tiers:
        ours = '<span class="ours">我方定位</span>' if name == ours_tier else ""
        pr = "".join(f'<li><span class="ch">{E(c)}</span><span class="pn">{E(n)}</span><span class="pp">{E(p)}</span>'
                     f'{f"<span class=pm>{E(m)}</span>" if m else ""}</li>' for c, n, p, m in prods)
        ft = "".join(f"<li>{E(f)}</li>" for f in feats)
        out.append(f'<article class="tier"><header><h4>{name}</h4><span class="rng">{rng}</span>{ours}</header>'
                   f'<div class="tier-b"><div><h5>代表产品</h5><ul class="prods">{pr}</ul></div>'
                   f'<div><h5>功能 / 材质特征</h5><ul class="feats">{ft}</ul></div></div></article>')
    return f'<div class="tiers">{"".join(out)}</div>'

def price_grid(sku):
    t = next(s for s in scen["skus"] if s["id"] == sku)["tiers"]
    rows = []
    for k, name in [("amz", "Amazon"), ("hd", "Home Depot"), ("wf", "Wayfair"), ("lw", "Lowe's")]:
        cells = "".join(f'<td>{usd(t[x][k], 2 if t[x][k] < 300 else 0) if t[x][k] else "—"}</td>' for x, _ in TIERS)
        rows.append(f"<tr><th scope=row>{name}</th>{cells}</tr>")
    return ('<div class="tw"><table class="pg"><thead><tr><th>测算用前台价</th><th>低</th><th>中</th><th>高</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


# ---------------- thermostatic shower systems (procurement quotes, estimated packaging) ----------------
TH = json.load(open(os.path.join(HERE, "calc_thermo.json"), encoding="utf-8"))["res"]
TS = json.load(open(os.path.join(HERE, "scen_thermo.json"), encoding="utf-8"))["skus"]
_pct = (calc["params"]["promo"] + calc["params"]["fx"] + calc["params"]["refund"] + calc["params"]["comm"]) / 100
def th_rows(sku):
    return {r["tier"]: r for r in TH if r["sku"] == sku}
def th_summary():
    head = ('<tr><th>型号</th><th>报价</th><th>包装（估）</th><th>Amazon FBA 低</th><th>Amazon FBA 中</th><th>Amazon FBA 高</th>'
            '<th>HD 中</th><th>Lowe\'s SC 中</th><th>Wayfair 中</th><th>Amazon 保本价</th></tr>')
    body = []
    for s in TS:
        r = th_rows(s["id"]); g = s["pkgs"][0]
        def amz(t):
            x = r[t]; return f'<td><div class="cell"><span class="price">{usd(x["amzPrice"])}</span><span class="profit {"neg" if x["fba"]<0 else ""}">{usd(x["fba"])}</span>{pill(x["fba"]/x["amzPrice"])}</div></td>'
        def plat(k):
            v = r["mid"]["plat"][k]
            if not v["priced"]: return '<td class="na-cell"><span class="pill na">无同类</span></td>'
            return f'<td><div class="cell"><span class="price">{usd(v["retail"])}</span><span class="profit {"neg" if v["profit"]<0 else ""}">{usd(v["profit"])}</span>{pill(v["margin"])}</div></td>'
        be = (r["mid"]["cost"] + r["mid"]["sea"] + r["mid"]["fbaShip"]) / (1 - _pct)
        body.append(f'<tr><th scope="row">{s["id"]}</th><td>¥{s["cost"]:,}</td><td>{g[0]:.0f}×{g[1]:.0f}×{g[2]:.0f}cm · {g[3]}kg</td>'
                    f'{amz("low")}{amz("mid")}{amz("high")}{plat("hd")}{plat("lowesSC")}{plat("wf")}<td>{usd(be)}</td></tr>')
    return f'<div class="tw"><table class="pt"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>'
def th_detail(sku):
    r = th_rows(sku)
    head = "".join(f"<th>{t}</th>" for _, t in TIERS)
    rows = []
    def cell(price, profit, m):
        return f'<td><div class="cell"><span class="price">{usd(price)}</span><span class="profit {"neg" if profit<0 else ""}">{usd(profit)}</span>{pill(m)}</div></td>'
    rows.append('<tr><th scope="row">Amazon FBA</th>' + "".join(cell(r[t]["amzPrice"], r[t]["fba"], r[t]["fba"]/r[t]["amzPrice"]) for t,_ in TIERS) + '</tr>')
    rows.append('<tr><th scope="row">Amazon FBM</th>' + "".join(cell(r[t]["amzPrice"], r[t]["fbm"], r[t]["fbm"]/r[t]["amzPrice"]) for t,_ in TIERS) + '</tr>')
    for k, name in [("hd","Home Depot"),("lowesVC","Lowe's VC"),("lowesSC","Lowe's SC"),("wf","Wayfair")]:
        cs = []
        for t,_ in TIERS:
            v = r[t]["plat"][k]
            cs.append(cell(v["retail"], v["profit"], v["margin"]) if v["priced"] else '<td class="na-cell"><span class="pill na">无同类</span></td>')
        rows.append(f'<tr><th scope="row">{name}</th>{"".join(cs)}</tr>')
    return f'<div class="tw"><table class="pt"><thead><tr><th>渠道</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
TH_TIERS = [
 ("低价带", "$250–420", [
   ("Amazon", "Oupukle 恒温 12\" 顶喷 + 6 侧喷", "$360.99", ""),
   ("Wayfair", "CASAINC 12\" 吸顶恒温 + 6 侧喷", "$362.50", "4.9★ 41 评"),
   ("Home Depot", "Boyel Living 恒温 12\" + 6 侧喷", "$291.29", ""),
   ("Lowe's", "Yichuhaoxi 12\" LED 顶喷 + 4 侧喷", "$421.98", "5★ 16 评")],
  ["12\" 方 / 圆顶喷 + 4–6 个侧喷 + 手持", "基础恒温阀或压力平衡阀，按键 / 旋钮分水", "侧喷多为塑料或锌壳，顶喷 ABS 或薄不锈钢", "以中国卖家白牌为主"]),
 ("中价带", "$450–870", [
   ("Amazon", "JetsBath 16\" 恒温 + 6 侧喷", "$489.99", ""),
   ("Amazon", "Dasan 恒温双头（16\" + 6\"）+ 6 侧喷", "$599–670", "月销约 80"),
   ("Wayfair", "EVERSTEIN 12\" 双雨淋 + 6 侧喷", "$477", "5★"),
   ("Home Depot", "Modland 16\" 恒温 + 6 侧喷", "$867.64", "")],
  ["16\" 顶喷或双顶喷（雨淋 + 6\" 壁喷）", "6 个可调侧喷，各出水可同时开", "黄铜恒温阀体，3–4 路分水", "多色饰面（黑 / 镍 / 金）"]),
 ("高价带", "$740–1,500", [
   ("Amazon", "NPYSVSSS 14×20\" 吸顶 LED 恒温 + 侧喷", "$739.99", ""),
   ("Amazon", "RomceBath 16×24\" 三合一（雨淋 / 瀑布 / 喷雾）", "$899.99", ""),
   ("Wayfair", "EVERSTEIN 16\" 双雨淋 + 6 侧喷", "$1,118.55", "4.7★ 187 评"),
   ("Home Depot", "GRANDJOY 16\" RGB LED + 6 侧喷", "$1,439.10", "")],
  ["大尺寸嵌顶顶喷，多功能（雨淋 + 瀑布 + 喷雾）", "LED 灯 / 数显温度 / 蓝牙音乐", "全铜阀体，5–6 路分水", "品牌店铺（EVERSTEIN、GRANDJOY）+ 较多评价"]),
]
TH2_TIERS = [
 ("低价带", "$160–180", [("Amazon", "Gabrylly 10\" 恒温花洒 + 浴缸龙头", "$179.99", "月销约 560"), ("Amazon", "VEVOR 恒温吸顶 + 6\" 壁喷 + 手持", "$158.99", "")],
  ["10–12\" 顶喷 + 手持，两功能", "基础恒温阀", "顶喷 ABS，手持塑料"]),
 ("中价带", "$340–550", [("Amazon", "SHOYELA 恒温 12\" + 6\" 双头", "$339.99", "4.3★ 196 评"), ("Amazon", "VANFOXLE 恒温花洒套装", "$349.99", ""), ("Home Depot", "EVERSTEIN 恒温壁挂 12\" + 6\"", "$548", ""), ("Lowe's", "GRANDJOY 恒温 12\" 双头 + 3 侧喷", "$479", "")],
  ["12\" 顶喷 + 6\" 壁喷 + 手持", "按键分水，可同时出水", "黄铜阀体"]),
 ("高价带", "$460–830", [("Amazon", "JetsBath 16\" 恒温双雨淋", "$459.99", ""), ("Home Depot", "YAWWALK 恒温 12\" + 6\" 7 种出水", "$669", "4.9★"), ("Wayfair", "EVERSTEIN 恒温 12\"（含预埋阀）", "$825.75", "4.8★ 106 评")],
  ["16\" 大顶喷或品牌款", "含预埋阀，安装配套齐", "品牌 + 较多评价"]),
]

# ---------------- market-layout matrices (Amazon, SellerSprite 2026-10) ----------------
import matrix as MX
MX_ITEMS = {}
def _mx(name, keep, rf, cf, R, C):
    rows = [r for r in MX.load(os.path.join(HERE, "mkt", name + ".csv")) if keep(r)]
    MX.split_parent_units(rows)
    order = [r["asin"] for r in sorted(rows, key=lambda r: -r["u"])]
    sp, _ = MX.make_sprite(order, os.path.join(HERE, "img"), os.path.join(HERE, f"sprite_{name}.jpg"))
    MX_ITEMS.update(MX.cell_items(rows, rf, cf, name, MX.load_meta(os.path.join(HERE, "mkt", name + "_meta.csv")), sp))
    return MX.build(rows, rf, cf, R, C), len(rows)
(_sd, _sn) = _mx("sauna", lambda r: MX.sauna_keep(r["t"]), lambda r: MX.sauna_cap(r["t"]), lambda r: MX.sauna_wood(r["t"]), MX.SAUNA_ROWS, MX.SAUNA_COLS)
_TD = MX.load_tandem_detail(os.path.join(HERE, "mkt", "tandem_detail.jsonl"))
def _tdg(r):
    v = _TD.get(r.get("parent")) or _TD.get(r["asin"]) or ("未注明", "未注明", None, "")
    if "ex" not in r:
        r["ex"] = ([f"材质：{v[3][:60]}"] if v[3] else []) + ([f"可调宽度至 {v[2]:g}″"] if v[2] else []) + [MX.tandem_cfg(r["t"])]
    return v
(_td, _tn) = _mx("tandem", lambda r: MX.tandem_keep(r["t"]) and r["price"] and _tdg(r), lambda r: _tdg(r)[0], lambda r: _tdg(r)[1], MX.TANDEM2_ROWS, MX.TANDEM2_COLS)
(_hd, _hn) = _mx("thermo", lambda r: MX.thermo_keep(r["t"], r["price"]), lambda r: MX.thermo_top(r["t"]), lambda r: MX.thermo_jets(r["t"]), MX.THERMO_ROWS, MX.THERMO_COLS)
def _m(x): return f"{x*100:.0f}%"
def _c(x): return "good" if x >= 0.15 else ("warn" if x >= 0 else "bad")
_t = lambda sku, t, ch: (lambda r: r[ch] / r["amzPrice"])(next(x for x in TH if x["sku"] == sku and x["tier"] == t))
s1m = R[("SAD6221-1", "mid")]["fbm"] / R[("SAD6221-1", "mid")]["amzPrice"]
hcm = HC[("SMT-HC103", "mid")]["fbm"] / HC[("SMT-HC103", "mid")]["amzPrice"]
s2m = R[("SAD6221-2", "mid")]["fbm"] / R[("SAD6221-2", "mid")]["amzPrice"]
dmm = R[("DUAL", "mid")]["fba"] / R[("DUAL", "mid")]["amzPrice"]
MX_HTML = (
  MX.render("Amazon 红外桑拿房（木质房体）：容量 × 木材", f"2026-10 · 卖家精灵 {_sn} 个子体 · 父体月销按子体平均分摊",
            _sd[0], _sd[1], _sd[2],
            {"1 人": {"cells": ["铁杉"], "price": "$1,299", "margin": f"SAD6221-1 {_m(s1m)}<br>SMT-HC103 {_m(hcm)}", "cls": "bad"},
             "1-2 人": {"cells": ["铁杉"], "price": "$1,799", "margin": f"SAD6221-2 {_m(s2m)}", "cls": _c(s2m)}},
            mid="sauna", row_label="容量", footnote="容量、木材按标题识别，标题没写木材的归“其他 / 未注明”；已剔除帐篷 / 便携 / 蒸汽 / 桶形款。利润率为 Amazon FBM，SMT-HC103 按包装 +10%。") +
  MX.render("Amazon 双人淋浴花洒：可调宽度 × 材质", f"2026-10 · 卖家精灵 {_tn} 个子体（tandem / two people / couples 词组匹配）· 已剔除带阀门的淋浴系统",
            _td[0], _td[1], _td[2],
            {"61–80″": {"cells": ["ABS + 不锈钢 / 金属"], "price": "$149.99", "margin": _m(dmm), "cls": _c(dmm)}},
            mid="tandem", row_label="可调宽度", footnote="材质取商品详情页的 Material 字段，可调宽度取卖点里写的最大适配宽度（如 fits 48–78 inch），按父体取一个代表 ASIN 的详情（49 个父体）。我方按 OURBAOFU 同款规格（ABS 花洒头 + 304 不锈钢杆，48–78″）落点。利润率为 Amazon FBA，成本 ¥190（1688 参考价）。") +
  MX.render("Amazon 恒温 / 侧喷淋浴系统：顶喷尺寸 × 侧喷数量", f"2026-10 · 卖家精灵 {_hn} 个子体（thermostatic / body jets 词组匹配）",
            _hd[0], _hd[1], _hd[2],
            {"≤10″": {"cells": ["无侧喷"], "price": "$340", "margin": f"FFS223 {_m(_t('FFS223','mid','fba'))}", "cls": _c(_t('FFS223','mid','fba'))},
             "12″": {"cells": ["2–4 个"], "price": "$490", "margin": f"F00F40 {_m(_t('F00F40','mid','fba'))}", "cls": _c(_t('F00F40','mid','fba'))},
             "16″": {"cells": ["6 个及以上"], "price": "$650", "margin": f"F00F42 {_m(_t('F00F42','mid','fba'))}<br>F00F41 {_m(_t('F00F41','mid','fba'))}", "cls": "warn"}},
            mid="thermo", row_label="顶喷尺寸", footnote="顶喷尺寸、侧喷数按标题识别。我方落点：F00F41 / F42 的 400mm 顶喷约 16″；FFS223、F00F40 报价未写顶喷尺寸，暂按 ≤10″、12″ 放置，待采购确认。利润率为 Amazon FBA。")
)

MX_DATA = json.dumps(MX_ITEMS, ensure_ascii=False).replace('</', '<\\/')
P = calc["params"]
s1 = S[("SAD6221-1", "mid")]; s1h = S[("SAD6221-1", "high")]
dm = S[("DUAL", "mid")]; dl = S[("DUAL", "low")]

page = f"""<title>疗愈品类利润摸底</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&family=IBM+Plex+Mono:wght@400;600&display=swap">
<style>
/* Layout: single reading column, summary first, then one section per category (market → price tiers → profit) */
:root{{
  --bg:#f6f7f5; --panel:#ffffff; --fg:#1b2420; --muted:#5d6a64; --line:#dde3df; --accent:#1f5f55; --accent-soft:#e3efec;
  --good:#1d7a3e; --good-bg:#e2f3e7; --warn:#8a5a00; --warn-bg:#fbf0d6; --bad:#b3261e; --bad-bg:#fbe5e3; --na:#7b8580; --na-bg:#eef1ef;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100;
  --g0:#e1f3ee; --g1:#fbe4ee; --heat:#3aa57f; --mine-bg:#fff4c7; --box:#e8a10a;
  --f-body:"Noto Sans SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif; --f-num:"IBM Plex Mono",ui-monospace,Menlo,monospace;
}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{
  --bg:#121614; --panel:#1a201d; --fg:#e7ece9; --muted:#9aa7a1; --line:#2c3531; --accent:#6cc2b1; --accent-soft:#1f2f2b;
  --good:#6fd38f; --good-bg:#16301f; --warn:#f0c15a; --warn-bg:#352a10; --bad:#ff8a80; --bad-bg:#3a1a18; --na:#93a09a; --na-bg:#232a27;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --g0:#1d3a33; --g1:#3e2330; --heat:#2f9a73; --mine-bg:#3a3214; --box:#e0a020; color-scheme:dark}}}}
:root[data-theme="dark"]{{
  --bg:#121614; --panel:#1a201d; --fg:#e7ece9; --muted:#9aa7a1; --line:#2c3531; --accent:#6cc2b1; --accent-soft:#1f2f2b;
  --good:#6fd38f; --good-bg:#16301f; --warn:#f0c15a; --warn-bg:#352a10; --bad:#ff8a80; --bad-bg:#3a1a18; --na:#93a09a; --na-bg:#232a27;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --g0:#1d3a33; --g1:#3e2330; --heat:#2f9a73; --mine-bg:#3a3214; --box:#e0a020; color-scheme:dark}}
body{{background:var(--bg);color:var(--fg);font-family:var(--f-body);font-size:15px;line-height:1.65}}
.wrap{{max-width:1080px;margin:0 auto;padding-block:28px 64px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:grid;grid-template-columns:minmax(0,1fr);gap:36px}}
h1,h2,h3,h4,h5{{text-wrap:balance;margin:0;line-height:1.3}}
h1{{font-size:28px}} h2{{font-size:21px;padding-bottom:8px;border-bottom:2px solid var(--accent)}} h3{{font-size:17px}} h4{{font-size:16px}} h5{{font-size:12px;letter-spacing:.06em;color:var(--muted);font-weight:500;margin-bottom:6px}}
p{{margin:0}} .sub{{color:var(--muted);font-size:13.5px}}
section{{display:grid;grid-template-columns:minmax(0,1fr);gap:18px;min-width:0}}
.num,.price,.profit,td,.pp,.rng,.bar-h,.lg b{{font-variant-numeric:tabular-nums}}
.verdict{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}}
.vc{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px;display:grid;gap:8px;align-content:start;border-top:4px solid var(--c)}}
.vc.ok{{--c:var(--good)}} .vc.no{{--c:var(--bad)}}
.vc .big{{font-family:var(--f-num);font-size:26px;font-weight:600}}
.vc ul{{margin:0;padding-left:18px;display:grid;gap:4px}}
.mkt{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}}
.mkt article{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px;display:grid;gap:10px;align-content:start;min-width:0}}
.kv{{display:grid;grid-template-columns:auto 1fr;gap:6px 12px;font-size:14px}}
.kv dt{{color:var(--muted)}} .kv dd{{margin:0}}
.decision{{background:var(--accent-soft);border-radius:8px;padding:10px 14px;font-size:14px}}
.tiers{{display:grid;gap:12px}}
.tier{{background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}}
.tier header{{display:flex;flex-wrap:wrap;gap:10px;align-items:baseline;padding:10px 16px;border-bottom:1px solid var(--line)}}
.rng{{font-family:var(--f-num);font-weight:600;color:var(--accent)}}
.ours{{font-size:12px;background:var(--accent);color:var(--bg);border-radius:20px;padding:1px 10px}}
.tier-b{{display:grid;grid-template-columns:1.5fr 1fr;gap:16px;padding:12px 16px}}
.tier-b>div{{min-width:0}}
@media (max-width:700px){{.tier-b{{grid-template-columns:1fr}}}}
.prods,.feats{{list-style:none;margin:0;padding:0;display:grid;gap:6px;font-size:14px}}
.prods li{{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline}}
.ch{{font-size:11.5px;color:var(--muted);border:1px solid var(--line);border-radius:4px;padding:0 6px}}
.pn{{flex:1 1 180px}} .pp{{font-family:var(--f-num);font-weight:600}} .pm{{font-size:12px;color:var(--muted);flex-basis:100%;padding-left:2px}}
.feats li{{padding-left:14px;position:relative}} .feats li::before{{content:"";position:absolute;left:2px;top:.7em;width:6px;height:6px;border-radius:50%;background:var(--accent)}}
.tw{{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--panel)}}
table{{border-collapse:collapse;width:100%;font-size:14px}}
th,td{{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}}
thead th{{font-size:12.5px;color:var(--muted);font-weight:500;background:var(--bg)}}
tbody tr:last-child>*{{border-bottom:0}}
tbody th{{font-weight:500}}
.cell{{display:flex;gap:10px;align-items:center}}
.price{{color:var(--muted);font-size:13px;min-width:62px}} .profit{{font-family:var(--f-num);font-weight:600;min-width:60px;text-align:right}}
.neg{{color:var(--bad)}} .pos{{color:var(--good)}}
.pill{{display:inline-block;font-size:12px;font-family:var(--f-num);font-weight:600;border-radius:20px;padding:1px 9px}}
.pill.good{{color:var(--good);background:var(--good-bg)}} .pill.warn{{color:var(--warn);background:var(--warn-bg)}} .pill.bad{{color:var(--bad);background:var(--bad-bg)}} .pill.na{{color:var(--na);background:var(--na-bg);font-family:var(--f-body);font-weight:400}}
.note{{font-size:12.5px;color:var(--muted)}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} @media (max-width:760px){{.two{{grid-template-columns:1fr}}}}
.two>*{{min-width:0}}
.bars{{display:grid;gap:18px;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px}}
.bar{{display:grid;gap:6px}}
.bar-h{{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 12px;font-size:13.5px}}
.bar-h span:first-child{{font-weight:500}}
.track{{position:relative;height:22px}}
.fill{{display:flex;gap:2px;height:100%}}
.seg{{height:100%}} .seg:first-child{{border-radius:4px 0 0 4px}} .seg:last-child{{border-radius:0 4px 4px 0}}
.s1{{background:var(--s1)}} .s2{{background:var(--s2)}} .s3{{background:var(--s3)}} .s4{{background:var(--s4)}}
.pricemark{{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--fg)}}
.pricemark span{{position:absolute;top:-17px;left:50%;transform:translateX(-50%);font-size:11px;color:var(--muted);white-space:nowrap}}
.lg{{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:4px 16px;font-size:12.5px;color:var(--muted)}}
.lg li{{display:flex;gap:5px;align-items:center}} .lg b{{color:var(--fg);font-weight:600;font-family:var(--f-num)}} .lg em{{font-style:normal;display:none}}
.sw{{width:10px;height:10px;border-radius:2px;display:inline-block}}
.callout{{border-left:4px solid var(--bad);background:var(--bad-bg);border-radius:0 8px 8px 0;padding:12px 16px;display:grid;gap:6px;font-size:14px}}
.callout.g{{border-color:var(--good);background:var(--good-bg)}}
.rules{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;font-size:13.5px}}
.rules div{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 16px}}
.rules ul{{margin:6px 0 0;padding-left:18px;display:grid;gap:3px}}
details{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 14px}} details>summary{{cursor:pointer;font-weight:500}} details .tw{{margin-top:10px}}
{MX.MX_CSS}
.todo{{margin:0;padding-left:20px;display:grid;gap:6px}}
table.mtg td,table.mtg th{{white-space:normal;vertical-align:top;min-width:160px}}
table.mtg tbody th{{white-space:nowrap}}
</style>

<div class="wrap">
<header style="display:grid;gap:8px">
  <p class="sub">疗愈项目 · 拓展品类利润摸底 · 2026-11-13 · 测算规则：利润测算台 v1.14 默认参数</p>
  <h1>双人淋浴花洒 & 红外单人桑拿房：市场与利润摸底</h1>
  <p class="sub">售价取自 Amazon（卖家精灵 2026-10）及 Home Depot、Lowe's、Wayfair 2026-11-13 搜索页的同类在售产品；成本为采购报价（桑拿，人民币）与 1688 参考价（花洒）。</p>
</header>

<section aria-label="结论">
  <div class="verdict">
    <div class="vc ok"><h3>双人淋浴花洒：可以做，定中价带</h3>
      <div class="big">{dm['amzFBA']['margin']*100:.0f}% <span class="sub">Amazon FBA 中价带 {usd(dm['amzFBA']['price'],2)}，单件 {usd(dm['amzFBA']['profit'])}</span></div>
      <ul><li>落地成本约 $32（采购 ¥190 + 海运），四个渠道中价带利润率 33–40%</li>
      <li>低价带 $80 只剩 {dl['amzFBA']['margin']*100:.0f}%，Wayfair $93 基本保本，不打低价</li>
      <li>高价带 $249 需要品牌力（BOONA 一家独大）</li></ul></div>
    <div class="vc ok"><h3>恒温顶喷 / 侧喷系统：两款能做，两款要谈价</h3>
      <div class="big">35% <span class="sub">FFS223 Amazon 中价带 $340；F00F40 中价带 $490 为 25%</span></div>
      <ul><li>F00F41 / F00F42 报价 ¥2,600–2,800，中价带 $650 只有 4–8%，含税要谈到约 ¥2,200</li>
      <li>包装尺寸、毛重为估算；cUPC 认证约 ¥10 万+ 未计入</li></ul></div>
    <div class="vc no"><h3>红外单人桑拿房：按现报价全渠道亏损</h3>
      <div class="big">{usd(s1['amzFBM']['breakeven'])} <span class="sub">SAD6221-1 在 Amazon 的保本价，高于市场高价带 $1,799</span></div>
      <ul><li>报价 ¥6,270 → 采购 $816，海运 $165，LTL 尾程 $342，三项已超过中价带售价 $1,299</li>
      <li>高价带 $1,799 要达 15% 利润，含税采购价需 ≤ ¥{s1h['amzFBM']['maxCostRMB']:,}（约现报价的一半）</li>
      <li>报价重量 220kg 是同类（60–110kg）的 2 倍，直接推高尾程</li>
      <li>合肥便宜款 SMT-HC103（¥3,842 含税，包装 +10%）高价带也只有约 9%；要过 15% 还得同时升配置、降高度</li></ul></div>
  </div>
</section>

<section aria-labelledby="m">
  <h2 id="m">一、市场情况</h2>
  <div class="mkt">
    <article><h3>五金花洒 / 双人淋浴</h3>
      <dl class="kv">
        <dt>市场规模</dt><dd>美国花洒市场 $20 亿（2024），CAGR 7.1%；手持款增速最快 7.8%，线上渠道 CAGR 8.0%</dd>
        <dt>大盘</dt><dd>Showerheads & Systems CAGR 6.54%，高于卫浴五金整体 5.17%</dd>
        <dt>搜索</dt><dd>rain shower head 9.3 万/月；双人细分 tandem 1.47 万 + dual for two 0.6 万 + couples 0.22 万，2022 年几乎为零，2026 比 2025 +11%</dd>
        <dt>竞争</dt><dd>首页无大牌垄断，以中国卖家为主；双人款只有 BOONA（Shark Tank）形成品牌</dd>
        <dt>认证</dt><dd>CEC、无铅</dd>
      </dl>
      <p class="decision">选品结论：第一优先级。体量大、利润可观，用来打开五金市场。</p></article>
    <article><h3>红外桑拿房</h3>
      <dl class="kv">
        <dt>市场规模</dt><dd>美国桑拿市场 $2.06 亿（2025），CAGR 5.4%；红外增速最快约 7.5%；家用约 $1.22 亿（估算）</dd>
        <dt>搜索</dt><dd>home sauna 5.6 万/月、indoor sauna 1.9 万；Google Trends 近 12 个月 infrared sauna +140%、indoor sauna +110%</dd>
        <dt>热度</dt><dd>Reddit 讨论热度 16,621，是五金（1,853）的 9 倍；DTC 销量约 4.9 万件，大概率大于渠道</dd>
        <dt>渠道</dt><dd>Amazon 82% SKU 是织物便携款（中位价 $150）；Wayfair / HD / Lowe's 以木质房体为主，中位价 $3,300 / $2,570 / $1,999</dd>
        <dt>Amazon 销售</dt><dd>年销售额 $175 万–933 万，2025 年比 2024 年 +33%；木质款月销 Amazon 约 1,200 台、HD 370、Lowe's 340、Wayfair 135；1–2 人款卖得最好，九成为红外（8/6 会议）</dd>
        <dt>认证</dt><dd>整机 ETL，须以我方电商主体申请</dd>
      </dl>
      <p class="decision">选品结论：第二优先级，增长期先发、绝对利润额高；便携式桑拿不做。</p></article>
  </div>
  <p class="note">来源：Grand View Research、Mordor Intelligence、卖家精灵关键词与类目数据、Google Trends（2026-08-04 采集）、桑拿四渠道属性分布报告、Reddit 讨论分析。</p>
</section>

<section aria-labelledby="mx">
  <h2 id="mx">市场布局：我们落在哪一格</h2>
  <p class="sub">一行一个尺寸 / 价格带，一组列一个材质 / 配置。看哪里卖得多（月销）、哪里挤（ASIN 数）、哪里单链接效率高（单 ASIN 月销，底色越深越好）、哪里口碑差（评分 &lt; 4.0 标红），以及我们的产品落在哪一格、按这个价能不能赚钱。</p>
  {MX_HTML}
  <script type="application/json" id="mxdata">{MX_DATA}</script>
  {MX.MX_JS}
  <div class="rules">
    <div><b>桑拿房</b><ul>
      <li>1 人 × 铁杉：月销 380、41 个 ASIN，单链接 9.3 台，均价 $1,203。我们两款按 $1,299 都亏（−36% / −12%）。</li>
      <li>单链接效率最高的是 1-2 人“其他 / 未注明”格（26.5 台），其次 4 人+（18.8 台）但评分只有 3.76。</li>
      <li>铁杉占木质房月销 30%，雪松只有 2%，雪松款在 Amazon 卖不动。</li></ul></div>
    <div><b>双人淋浴花洒</b><ul>
      <li>量最大的一格是 81″+ × 不锈钢：月销 1,359、23 个 ASIN，但加权均价只有 $84，是低价走量带。</li>
      <li>我们落在 61–80″ × ABS + 不锈钢：月销 527、12 个 ASIN、均价 $141、评分 4.45；旁边 61–80″ × 纯不锈钢月销 763、均价 $222、评分 4.63，是往上走的方向。</li>
      <li>纯 ABS 款很少（合计月销约 130），评分偏低（3.95）；“金属 / 黄铜”61–80″ 一格评分 3.96，有口碑缺口。</li></ul></div>
    <div><b>恒温 / 侧喷系统</b><ul>
      <li>最大的一格是 ≤10″ × 无侧喷：月销 2,727，单链接 105，均价 $233。FFS223 定 $340 比这格均价高 46%，要么配置拉开，要么价格贴近 $250。</li>
      <li>16″ × 6 侧喷：月销 228、30 个 ASIN、均价 $540，F00F41 / F42 定 $650 高于均价且只有 4–8%。</li>
      <li>有侧喷的系统合计只占月销约 34%，大头仍是不带侧喷的恒温款。</li></ul></div>
  </div>
</section>

<section aria-labelledby="mt">
  <h2 id="mt">项目脉络：四次会议的结论</h2>
  <div class="tw"><table class="mtg"><thead><tr><th>会议</th><th>结论</th><th>对本报告的影响</th></tr></thead><tbody>
    <tr><th scope="row">6/25 Wellness 开品方向</th><td>核心人群三类：仪式疗愈型（占比最大）、变美型（约 35%）、压力管理 / 健康投资型（约 10%）；Home Spa 最重要的场景是淋浴和泡澡，水和光是载体；思路是从人群找痛点再开品，把高端品平民化</td><td>两个品类都落在“水 + 光”：花洒走水，红外桑拿走光（近红外抗炎修护）</td></tr>
    <tr><th scope="row">7/17 品类筛选规则</th><td>弃用漏斗穷举，改为积分卡加权（市场体量、进入难度、竞争、场景延展性）；范围从“浴室”扩到全 Home Wellness；不做单价低于 $30 的小件；收敛到 1–3 个方向</td><td>两个品类都远高于 $30，符合规则</td></tr>
    <tr><th scope="row">8/6 桑拿 vs 五金二选一</th><td>马桶（头部垄断）、浴缸（搜索仅 5–6 千且增长慢）、非木质便携桑拿排除；用体量、头部垄断、评分、粗略利润、品牌锚点价值 5 个维度二选一；桑拿试水款定为 1–2 人 / 2–3 人预组装红外房，Amazon 定价 $1,000–1,500，同价差异化可做波纹灯效、冥想 / 海浪音疗、香氛模块</td><td>本报告补上“粗略利润”这一维：花洒能赚；桑拿在 $1,000–1,500 这个试水价带按任何现有报价都亏</td></tr>
    <tr><th scope="row">10/10 光波房与花洒调研</th><td>桑拿：珠三角单人房含税 ¥6,000–7,000、无起订量、质保 5–6 年；皖徐不含税 ¥3,400–4,000、整柜起订、质保短；Amazon 主流款高约 1.35 米以省尾程，我方报价都是 1.9–2.1 米；木箱 + 托盘包装；整机 ETL 须以我方电商主体申请。花洒：北美需 cUPC 等认证，单品类首次约 ¥10 万+；铜价高涨，行业转向不锈钢（比铜主体低约 ¥40）；前期选工厂现有带认证款，用竞品链接反查供应商</td><td>桑拿报价 ¥6,270 就是珠三角价位；合肥便宜款 SMT-HC103 实报价测算见下文。220kg 重量来自木箱托盘包装，高度和包装是物流费的关键。花洒中价带主流就是不锈钢滑杆</td></tr>
  </tbody></table></div>
  <p class="note">来源：飞书智能纪要 2026-06-25、07-17、08-06、10-10（AI 生成纪要，个别数字以原始录音为准）。</p>
</section>

<section aria-labelledby="d">
  <h2 id="d">二、双人淋浴花洒</h2>
  <h3>各价带典型产品与功能差异</h3>
  {tier_cards(DUAL_TIERS, "中价带")}
  <p class="note">Home Depot、Wayfair 搜 “dual shower head” 主要是固定头 + 手持二合一款（Moen、Delta、Kohler，$40–140），不是双人款；真正的双人款在这两个渠道只有 KES、SR SUN RISE 等少数几款。</p>
  <div class="callout" style="border-color:var(--accent);background:var(--accent-soft)"><b>供应端（10/10 会议）</b>
    <span>产业带：广东开平水口供应链最全、成本中等；厦门偏高端、成本最高；浙江以 ABS 塑料为主、成本最低。材质：铜价上涨，行业转向不锈钢主体（比铜主体每件低约 ¥40）；锌包塑水路寿命风险高，不用。</span>
    <span>认证：北美需 cUPC 等认证，单品类首次约 ¥10 万+；Amazon 要求认证主体与店铺主体一致。会上定的“先用工厂现有带认证款”要先确认认证能否转到我方主体，否则这 ¥10 万+ 要摊进首批成本。</span>
    <span>会上的选型方向是带顶喷、腰喷、雨淋、恒温的疗愈类花洒，对应采购已报价的 4 款，测算见第三部分。</span></div>
  <h3>利润测算（成本 ¥190，按中价带规格）</h3>
  <div class="two">{price_grid("DUAL")}<div class="callout g"><b>成本构成</b><span>采购 ¥190（1688 参考价，按未税价）= $27.94；海运 $4.03；FBA 配送 $12.04（小号大件，旺季费率）；平台费用占售价 34%（佣金 15% + 广告 10% + 退款 8% + 汇损 1%）。</span><span>包装按 70×22×12cm、4kg 估算，待采购给实测尺寸。</span></div></div>
  {profit_table("DUAL", CH)}
</section>

<section aria-labelledby="t">
  <h2 id="t">三、恒温顶喷 / 侧喷花洒系统（采购已报价 4 款）</h2>
  <p class="sub">10/10 会议定的疗愈花洒选型方向：带顶喷、腰喷（侧喷）、雨淋、恒温。采购报价：F00F40 ¥1,289、F00F41 ¥2,800、F00F42 ¥2,600、FFS223 ¥640（按含税价处理）。包装尺寸和毛重为估算（参照 Amazon 同类 13–47 lb），待采购给实测值。</p>
  <h3>带侧喷的恒温系统：各价带典型产品（对标 F00F40 / F41 / F42）</h3>
  {tier_cards(TH_TIERS, "")}
  <h3>恒温两功能（无侧喷）：各价带典型产品（对标 FFS223）</h3>
  {tier_cards(TH2_TIERS, "中价带")}
  <h3>利润测算总览</h3>
  {th_summary()}
  <p class="note">F00F40 测算价用“带侧喷”低 / 中 / 高价带；F00F41、F00F42 配置更高（400 两功能顶喷 + 6 侧喷 + 支架），从中价带起算：低 $490、中 $650、高 $900（Amazon），其他渠道同理上移一档。FFS223 用“恒温两功能”价带。利润率口径同上。</p>
  <div class="two">
    <div class="callout g"><b>能做：FFS223、F00F40</b><span>FFS223 报价 ¥640（约 $83），中价带 $340 在 Amazon 有 35%，HD / Lowe's 36–47%。F00F40 报价 ¥1,289（约 $168），中价带 $490 有 25%，高价带 $740 接近 40%；但它只有单功能顶喷 + 4 侧喷 + 塑料手持，配置在低价带，卖到中价带需要补外观或功能。</span></div>
    <div class="callout"><b>要谈价：F00F41、F00F42</b><span>¥2,600–2,800（约 $338–364）在中价带 $650 只有 4–8%，要到高价带 $900 才有 21–24%，而高价带对手是 14×20" LED、三合一顶喷、数显恒温。F00F42 比 F00F41 便宜 ¥200 且多一路功能，二选一应选 F00F42。按 Amazon 中价带 $650 做到 15% 反推，含税报价需降到约 ¥2,200。</span></div>
  </div>
  <div class="callout" style="border-color:var(--accent);background:var(--accent-soft)"><b>10/10 会议提醒</b><span>恒温、复杂水流款在北美售后风险高、普及度还不高；美国主流是带防烫的压力平衡阀。认证需 cUPC 等，单品类首次约 ¥10 万+，Amazon 要求认证主体与店铺一致。这些费用和退货率（测算按 8%）是这条线的主要风险。</span></div>
  {"".join(f"<details><summary>{s['id']} 分渠道明细</summary>{th_detail(s['id'])}</details>" for s in TS)}
</section>

<section aria-labelledby="s">
  <h2 id="s">四、红外单人桑拿房</h2>
  <h3>各价带典型产品与功能差异（1 人款）</h3>
  {tier_cards(SAUNA_TIERS, "")}
  <div class="callout" style="border-color:var(--accent);background:var(--accent-soft)"><b>我方两款对标</b>
    <span>SAD6221-1（800×900×2100，1 人）/ SAD6221-2（900×1200×2100，1-2 人）：加拿大铁杉、远红外云母加热板、8mm 透明钢化玻璃、高密度负离子、LED 阅读灯、机械控制面板。</span>
    <span>材质和玻璃是中高配，但控制面板、灯光、娱乐配置只到低价带（无蓝牙、无 7 色光、无红光、无 App），2.1 米高、220kg 重于同类。</span></div>
  <h3>SAD6221-1 单人款（铁杉 ¥6,270）</h3>
  <div class="two">{price_grid("SAD6221-1")}<div class="callout"><b>为什么亏</b><span>采购 $816 = ¥6,270 ÷ 1.13 ÷ 6.8；海运 $165（0.757m³）；最大一箱 145kg 超出快递上限，只能走 LTL，按 220kg 估算 $342。三项合计 $1,323，平台费用再占售价 34%。</span></div></div>
  {profit_table("SAD6221-1", [CH[1], CH[0]] + CH[2:])}
  <h3>SAD6221-2 1-2 人款（铁杉 ¥8,618）</h3>
  <div class="two">{price_grid("SAD6221-2")}<div class="callout"><b>为什么亏</b><span>采购 $1,122；海运 $195（0.891m³）；LTL $378（250kg）。Amazon 保本价 {usd(S[('SAD6221-2','mid')]['amzFBM']['breakeven'])}，高于 1-2 人款高价带 $2,299。</span></div></div>
  {profit_table("SAD6221-2", [CH[1], CH[0]] + CH[2:])}
  <h3>便宜款实报价：SMT-HC103（合肥）</h3>
  <div class="two">
    <div class="callout" style="border-color:var(--accent);background:var(--accent-soft)"><b>产品与报价</b>
      <span>900×900×1900mm 单人房，铁杉，陶瓷加热器；USB + 蓝牙控制面板、双音箱、氧吧、LED 阅读灯。EXW 含税 ¥3,842（约 $500），20 尺柜起订，一柜 28 台。</span>
      <span>配置对标低价带（陶瓷而非碳晶加热、无 7 色光 / 红光）。</span></div>
    <div class="callout" style="border-color:var(--accent);background:var(--accent-soft)"><b>包装（按要求各边 +10%）</b>
      <span>工厂纸箱 4 件：183×96×17、183×92×17、98×110×20、86×50×13cm，毛重 110kg。</span>
      <span>测算用 201×106×19、201×101×19、108×121×22、95×55×14cm，毛重 121kg（便宜款可能过不了跌落测试，加厚包装预留）。体积 1.14m³，海运 $249；最大一箱围长超 165 英寸，只能走 LTL，估 $269。</span></div>
  </div>
  {wx_table()}
  <div class="two">
    <div class="callout"><b>结论</b><span>采购降到 $500，但包装加大后海运 $249 + LTL $269 = $518，比 SAD6221-1 的 $507 还高。结果是 Amazon 高价带 $1,799 约 9%，中价带 $1,299 亏 12%；Lowe's SC 高价带 13%。按原包装算，高价带也只到 13%，都没到 15%。</span></div>
    <div class="callout" style="border-color:var(--accent);background:var(--accent-soft)"><b>还能动的地方</b><span>这款低配只能卖低价带（$700–1,000），而低价带全渠道亏损。要么在这个成本上补碳晶板、7 色光把它推到 $1,500–1,800，要么压包装体积：Amazon 主流单人款高约 1.35 米，1.9 米高的板件是箱子长 1.8–2 米的原因。</span></div>
  </div>
  <div class="callout g"><b>差异化机会（10/10 会议）</b><span>Amazon 桑拿差评的核心是加热板配置不足、加热体感差。优质碳晶板套件成本 ¥1,000+，低价款 ¥300 出头；用好加热板 + 5–6 年质保，是在 $1,500–1,800 价带讲得通的卖点。8/6 会议提出的波纹灯效、冥想 / 海浪音疗、香氛模块可作为同价差异化。</span></div>
  <h3>要赚钱需要什么条件</h3>
  <p class="sub">保本前台价 = 现报价下利润为 0 的售价；最高采购价 = 在该价带售价下达到 15% 目标利润率时，工厂含税报价最多能给到多少（物流按现重量和体积不变）。</p>
  <h4>SAD6221-1</h4>
  {need_table("SAD6221-1", [CH[1], CH[2], CH[3], CH[4], CH[5]])}
  <p class="note">“无解”= 即使采购价为 0 也达不到 15%，这个价带下光物流和平台费用就超了。</p>
</section>

<section aria-labelledby="c">
  <h2 id="c">五、钱花在哪里（Amazon 中价带）</h2>
  <div class="bars">{bars}</div>
  <p class="note">每条按成本合计与售价中较大者铺满；竖线是售价，竖线以右的部分就是亏损。</p>
</section>

<section aria-labelledby="r">
  <h2 id="r">六、测算口径与待确认</h2>
  <div class="rules">
    <div><b>通用（利润测算台 v1.14 默认）</b><ul>
      <li>汇率 {P['rate']}；Amazon 佣金 {P['comm']}%、广告 {P['promo']}%、退款 {P['refund']}%、汇损 {P['fx']}%</li>
      <li>桑拿报价按含税处理：÷ (1+{P['tax']}%) ÷ 汇率；1688 价格按未税处理：÷ 汇率</li>
      <li>海运：FOB 整柜 ¥100,891 / 68m³（近三个月方案），按体积分摊</li>
      <li>LTL 估算：$92.5 + $0.43/lb + $54/m³；FBM 快递燃油 29.5%</li>
      <li>FBA 按当前日期取旺季费率（10/15–1/14）</li></ul></div>
    <div><b>平台（默认值）</b><ul>
      <li>Home Depot：结算价 = 前台价 ÷ 1.6，佣金 3.22%，平台发货只付处理费</li>
      <li>Lowe's VC：÷ 1.7，佣金 5.2%（按原批发价）；Lowe's SC：÷ 1，佣金 15%，自发货</li>
      <li>Wayfair：÷ 2.1，佣金 4%，入 CG 仓，仓储 2% + 出仓 4%</li>
      <li>各平台广告 10%、汇损 1%、退款 10%（Wayfair 5%）、仓储 2%</li></ul></div>
    <div><b>待确认</b><ol class="todo">
      <li>桑拿重量：报价 220kg / 250kg 是同类 2 倍，用 10/10 会上整理的单人、双人箱规和重量替换后重算</li>
      <li>ETL 认证（我方主体申请）的费用和周期，摊入单件成本</li>
      <li>桑拿报价是否含税（13%）</li>
      <li>双人淋浴：1688 具体链接与报价、包装尺寸和毛重</li>
      <li>桑拿谈价目标：高价带定位下含税 ≤ ¥3,100，并补蓝牙、7 色光、红光配置以撑起高价</li>
      <li>SMT-HC103：跌落测试结果、加厚后的实际箱规和毛重；同厂 1.35 米矮款和碳晶板配置的报价</li>
      <li>花洒：工厂现有 cUPC 认证能否用于我方 Amazon 主体；不能的话认证费 ¥10 万+ 计入首批</li>
      <li>恒温系统 4 款的实测包装尺寸、毛重，以及报价是否含税</li></ol></div>
  </div>
</section>
</div>
"""
open(os.path.join(HERE, "index.html"), "w", encoding="utf-8").write(page)

# ---------------- import file for 利润测算台 v1.14（打开方案 .json） ----------------
import random, string
uid = lambda: "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(7))
prods = []
for s in scen["skus"]:
    for t, tn in TIERS:
        tp = s["tiers"][t]
        prices = {k: {"promo": tp[m]} for k, m in [("lowesVC", "lw"), ("lowesSC", "lw"), ("hd", "hd"), ("wf", "wf")] if tp[m]}
        prods.append({"id": uid(), "name": f'{s["id"]} {tn}', "desc": s["name"], "supplier": "", "category": "其他", "peak": "非旺季",
                      "price": tp["amz"], "cost": s["cost"], "costCur": s["costCur"], "adj": 0, "pack": s["pack"], "prices": prices,
                      "pkgs": [{"l": g[0], "w": g[1], "h": g[2], "kg": g[3]} for g in s["pkgs"]]})
json.dump({"products": prods}, open(os.path.join(HERE, "疗愈品类_利润测算台导入.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ok", len(page))
