"""工具：评论 VP 追踪（FLOW-16）与利润测算（FLOW-17、FLOW-18）。
- FLOW-16：Bright Data / Apify 用假服务；导出与原工具（tools/评论月度VP追踪器/reviewkit）对同一批明细的导出逐格比对。
- FLOW-17：利润数字的基准由原工具 tools/利润测算台/index.html（wen 2026-11-03 第二版：变量抽屉、保存回当前版本、渠道费用矩阵、计算说明）
  的 JS 在 node 里算出，与并入版 engine.js 逐项比对；engine.js / profit.css / _profit_sections.html 由 tools_sync_profit.py 从原工具生成。"""
import html
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

import decision_seed as ds
import tools_sync_profit as sync
from conftest import login_as, make_user
from pdt import costgate, services
from pdt.config import PROJECT_DIR
from pdt.db import session
from pdt.models import Budget, Card, CostRecord, Job, ProfitPlan

J = {"accept": "application/json"}
TOOL = PROJECT_DIR / "tools" / "评论月度VP追踪器"
PROFIT_HTML = PROJECT_DIR / "tools" / "利润测算台" / "index.html"
ENGINE = Path(__file__).resolve().parent.parent / "pdt" / "static" / "profit" / "engine.js"


# ================================================================ FLOW-16 评论 VP 追踪
N_PROD = 12
BADGES = ["Verified Purchase", "Verified Purchase", "Incentivized Review", "Wayfair Professional", "Verified Purchase"]


def _reviews(i):
    """第 i 个商品的评论：2026-01 至 2026-10 每月 1 条（徽章轮换）+ 2026-11 未完整月 1 条 + 2025-12 窗口外 1 条。"""
    out = []
    for m in range(1, 11):
        out.append(dict(reviewId=f"wf{i:02d}-{m:02d}", date=f"{m:02d}/15/2026", rating=(m % 5) + 1, text=f"Vanity review {m}", badge=BADGES[(i + m) % 5]))
    out.append(dict(reviewId=f"wf{i:02d}-11", date="11/02/2026", rating=4, text="new", badge="Verified Purchase"))
    out.append(dict(reviewId=f"wf{i:02d}-00", date="12/20/2025", rating=5, text="old", badge="Verified Purchase"))
    return list(reversed(out))  # 原样按最新在前


def _expected_vp():
    """期望值由测试数据直接数出：窗口 2026-01-01 至 2026-10-31 内 Verified Purchase 计 VP，其余徽章计非 VP。"""
    vp = sum(1 for i in range(N_PROD) for m in range(1, 11) if BADGES[(i + m) % 5] == "Verified Purchase")
    return vp, N_PROD * 10 - vp


class FakeBD:
    def __init__(self):
        self.calls = []

    def fetch(self, url, poll=15, max_wait=1200):
        self.calls.append(url)
        cards = []
        for i in range(30):
            meta = json.dumps({"metadata": {"displayListingId": f"W1000{i:03d}", "firstPriceValue": 229 + i, "averageRating": 4.2, "totalReviewCount": 120}})
            cards.append(f'<div data-tracking-metadata="{html.escape(meta)}" data-clio-id="ListingCardContents::{i}">'
                         f'<a href="https://www.wayfair.com/bed-bath/pdp/latitude-run-30-single-bathroom-vanity-w1000{i:03d}.html">x</a></div>')
        return 200, ("<html>" + "".join(cards) + "</html>").encode()


class FakeApify:
    def __init__(self, pause_first=False):
        self.calls = []
        self.pause_first = pause_first

    def run(self, actor, run_input, max_charge_usd=3, timeout_s=3600, poll=20):
        self.calls.append([u.split("-w")[-1].split(".")[0].upper() for u in run_input["urls"]])
        if self.pause_first and len(self.calls) == 1:  # 模拟 wen 在第一批进行中点“暂停”
            with session() as s:
                jid = s.query(Job).filter_by(kind="vp_collect", status="running").one().id
            costgate.pause(jid)
        items = []
        for u in run_input["urls"]:
            sku = "W" + u.split("-w")[-1].split(".")[0]
            items.append(dict(sku=sku, name=f"Latitude Run 30'' Single Bathroom Vanity {sku}", brand="Latitude Run", reviews=_reviews(int(sku[-3:]))))
        return items, 0.05


@pytest.fixture()
def vp(wen, monkeypatch):
    from pdt.core import vp as vpcore
    from pdt.reviewkit import wayfair
    monkeypatch.setattr(wayfair.reviews_batch, "__defaults__", (10, 1))  # 每批 10 个、串行，便于在两批之间暂停
    vpcore.projects()  # 首次打开：复制原工具全部项目设置
    cfg = vpcore.load("浴室柜_2026")
    assert len(cfg["entries"]) == 6 and cfg["window"] == {"start": "2026-01-01", "full_end": "2026-10-31", "include_partial": True}
    cfg["entries"] = [dict(e, top_n=N_PROD) for e in cfg["entries"] if e["name"] == "Wayfair主类目"]
    r = wen.post("/tools/vp/project", data={"cfg": json.dumps(cfg, ensure_ascii=False)}, headers=J)
    assert r.json()["name"] == "浴室柜_2026"
    services.save_secret("brightdata", "bd-测试密钥-7f3a")
    services.save_secret("apify", "apify-测试密钥-k29Q")
    bd = FakeBD()
    services.set_fake("brightdata", bd)
    return wen, bd, vpcore


def _job(wen, kind):
    j = wen.post("/jobs/estimate", data={"kind": kind, "target": "vp:浴室柜_2026"}).json()
    assert j["status"] == "estimated", j
    return j


def test_flow16_four_steps_pause_resume_and_same_export_as_original(vp, tmp_path):
    """FLOW-16：① 采集列表 → ② 评估费用 → ③ 采集评论（中途暂停后继续，不重复采集）→ ④ 导出 Excel；调用使用设置页密钥，费用进同一费用记录；
    导出的 VP / 非 VP 与原工具对同一批明细的导出一致（Wayfair 只有 Verified Purchase 计 VP）。"""
    wen, bd, vpcore = vp
    ap = FakeApify(pause_first=True)
    services.set_fake("apify", ap)
    page = wen.get("/tools/vp?name=浴室柜_2026").text
    for step in ("① 采集列表", "② 评估费用", "③ 采集评论", "④ 导出 Excel"):
        assert step in page
    assert "Bright Data 已连接" in page and "···· 7f3a" in page and "1. 项目与时间窗" in page and "5. 本项目预算（美元）" in page
    j = _job(wen, "vp_lists")
    assert bd.calls == []  # 先确认费用
    assert wen.post(f"/jobs/{j['id']}/confirm").json()["status"] == "done"
    assert len(bd.calls) == 1
    est = wen.post("/tools/vp/estimate?name=浴室柜_2026", headers=J).json()
    assert est["平台"]["Wayfair"]["商品数"] == N_PROD and est["合计"]["Apify费用"] > 0
    j = _job(wen, "vp_collect")
    assert ap.calls == []
    j = wen.post(f"/jobs/{j['id']}/confirm").json()
    assert j["status"] == "paused" and len(ap.calls) == 1 and len(ap.calls[0]) == 10  # 第一批 10 个已采并保存
    j = wen.post(f"/jobs/{j['id']}/confirm").json()  # 继续
    assert j["status"] == "done" and len(ap.calls) == 2 and len(ap.calls[1]) == 2  # 只采剩下 2 个，不重复
    with session() as s:
        recs = {(r.service, r.amount) for r in s.query(CostRecord)}
        assert ("brightdata", 0.0015) in recs and ("apify", 0.05) in recs
        assert s.query(CostRecord).filter_by(service="apify").count() == 2
    st = vpcore.state("浴室柜_2026")
    assert st["progress"]["Wayfair"] == [N_PROD, N_PROD] and st["ledger"]["apify_wayfair_usd"] == 0.1
    files = wen.post("/tools/vp/export?name=浴室柜_2026", headers=J).json()["files"]
    mine = vpcore.rk_ctx("浴室柜_2026").path("exports", next(f for f in files if f.startswith("Wayfair")))
    # 原工具对同一批明细导出
    sys.path.insert(0, str(TOOL))
    try:
        from reviewkit import common as o_common, export as o_export
        octx = o_common.Ctx(vpcore.load("浴室柜_2026"), data_dir=vpcore.rk_ctx("浴室柜_2026").data)
        theirs = str(tmp_path / "原工具_Wayfair.xlsx")
        o_export.export(octx, "Wayfair", theirs)
    finally:
        sys.path.remove(str(TOOL))
    a, b = load_workbook(mine), load_workbook(theirs)
    assert a.sheetnames == b.sheetnames == ["月度趋势", "入口月度汇总", "商品", "评论明细"]
    for name in a.sheetnames:
        assert [list(r) for r in a[name].iter_rows(values_only=True)] == [list(r) for r in b[name].iter_rows(values_only=True)], name
    ws = a["入口月度汇总"]
    head = [c.value for c in ws[1]]
    row = [c.value for c in ws[2]]
    vp_n, non = _expected_vp()
    assert row[head.index("完整月 VP合计")] == vp_n and row[head.index("完整月 非VP合计")] == non
    assert row[head.index("2026-11（未完整） 合计")] == N_PROD  # 未完整月单列


def test_flow16_monthly_cap_stops_and_keeps_data(vp):
    """FLOW-16：系统设置页 Apify 月度上限低于本次费用 → 达到上限即停止，已采数据保留；调高上限后续跑不重复。"""
    wen, bd, vpcore = vp
    ap = FakeApify()
    services.set_fake("apify", ap)
    with session() as s:
        s.add(Budget(service="apify", cap=0.055, unit="usd"))
    j = _job(wen, "vp_lists")
    wen.post(f"/jobs/{j['id']}/confirm")
    wen.post("/tools/vp/estimate?name=浴室柜_2026", headers=J)
    j = _job(wen, "vp_collect")
    assert j["estimate"]["warnings"]  # 预计超过本月上限
    j = wen.post(f"/jobs/{j['id']}/confirm").json()
    assert j["status"] == "stopped_cap" and len(ap.calls) == 1
    raw = Path(vpcore.rk_ctx("浴室柜_2026").path("wayfair", "apify"))
    assert len(list(raw.glob("*.json"))) == 10  # 第一批 10 个商品的评论已保存（原工具的采集缓存），续跑不再调用
    assert "已达上限，已采数据已保存" in wen.get("/tools/vp?name=浴室柜_2026").text
    with session() as s:
        s.get(Budget, "apify").cap = 60
    assert wen.post(f"/jobs/{j['id']}/confirm").json()["status"] == "done" and len(ap.calls) == 2 and len(ap.calls[1]) == 2


def test_flow16_project_budget_either_first(vp):
    """AC-F23-02：原工具项目自身预算也保留，与月度上限“任一先到即停”。"""
    wen, bd, vpcore = vp
    ap = FakeApify()
    services.set_fake("apify", ap)
    cfg = vpcore.load("浴室柜_2026")
    cfg["budget"]["apify_wayfair_usd"] = 0.05
    wen.post("/tools/vp/project", data={"cfg": json.dumps(cfg, ensure_ascii=False)}, headers=J)
    wen.post(f"/jobs/{_job(wen, 'vp_lists')['id']}/confirm")
    wen.post("/tools/vp/estimate?name=浴室柜_2026", headers=J)
    wen.post(f"/jobs/{_job(wen, 'vp_collect')['id']}/confirm")
    st = vpcore.state("浴室柜_2026")
    assert len(ap.calls) == 1 and len(list(Path(vpcore.rk_ctx("浴室柜_2026").path("wayfair", "apify")).glob("*.json"))) == 10
    assert any("达到预算上限，已停止" in line for line in st["log"]) and st["ledger"]["apify_wayfair_usd"] == 0.05


def test_flow16_vp_rules_unchanged_from_original():
    """AC-F23-01：口径不变——采集与导出代码（VP 判定、去重、导出、估算、品类筛选）与原工具逐字相同，只改了密钥与记账（services.py）和停止传递（pipeline.py）。"""
    mine = Path(__file__).resolve().parent.parent / "pdt" / "reviewkit"
    for f in ("hdp.py", "lowes.py", "wayfair.py", "export.py", "estimate.py", "classify.py", "common.py"):
        assert (mine / f).read_bytes() == (TOOL / "reviewkit" / f).read_bytes(), f
    assert 'VP" if badge == "Verified Purchase" else "non_VP"' in (mine / "wayfair.py").read_text(encoding="utf-8")


def test_vp_page_operator_only(client):
    make_user("lixiaomei", "李晓梅", "readonly")
    ro = login_as(client, "lixiaomei", "密码-123456")
    assert ro.get("/tools/vp").status_code == 403


# ================================================================ FLOW-17 / 18 利润测算
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="需要 node 计算原工具基准")


def _calc_blocks(src: str) -> list:
    """原工具脚本里的默认参数段与计算段（中间的状态初始化两行是并入时唯一改动的地方）。"""
    a = src.index("/* ---------------- defaults ---------------- */")
    b = src.index("/* ---------------- state ---------------- */")
    c = src.index("/* ---------------- calculation (mirrors the original workbook) ---------------- */")
    d = src.index("/* ---------------- bulk: set platform list prices from the Amazon price ---------------- */")
    return [src[a:b], src[c:d]]


def _node(code: str, tmp_path, name):
    p = tmp_path / name
    p.write_text(code, encoding="utf-8")
    r = subprocess.run([NODE, str(p)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


HARNESS = """
var window = {}; var PDT = undefined; var localStorage = {getItem: function(){ return null; }, setItem: function(){}};
var document = {getElementById: function(){ return {addEventListener: function(){}}; }, querySelectorAll: function(){ return []; }, addEventListener: function(){}};
%s
/* 同一组输入：原工具示例产品，每个补一个人民币含税国内出货价（出厂价 × 7.25），并加一个“国内”海运方案，覆盖国内出货与对比 */
products.forEach(function(p, i){ p.costRmb = Math.round(p.cost * 7.25 * 100) / 100; });
P.sea.push({name: "国内整柜·近三个月", rmb: 98000, cbm: 68});
P.sea.push({name: "国内整柜·近六个月", rmb: 61000, cbm: 68});
function one(r){ return {cost: r.cost, price: r.price, sc: r.sc, fbmShip: r.fbmShip, cgShip: r.cgShip, fbaShip: r.fbaShip, warn: r.warn,
  plat: Object.fromEntries(Object.entries(r.plat).map(function(kv){ var x = kv[1]; return [kv[0], {list: x.list, promo: x.promo, sc: x.sc}]; })),
  rows: chanList().map(function(ch){ var v = chanVal(r, ch, 0); return {channel: ch.name, profit: v.ok ? v.profit : null}; })}; }
var R = products.map(function(p){ return {p: p, r: calcProduct(p)}; });
var out = {params: P, products: products,
  R: R.map(function(x){ return Object.assign({name: x.p.name}, one(x.r)); }),
  dom: domData(R).map(function(x){ return {name: x.p.name, fob: one(x.f), dom: one(x.d)}; }),
  scen: scenData(R).map(function(x){ return {name: x.p.name, off: one(x.n), on: one(x.k)}; }),
  plans: cmpPlans(), seaFob: seaList("fob"), seaDom: seaList("dom")};
console.log(JSON.stringify(out));
"""


def _script(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    if path.suffix == ".html":
        s = s[s.index('"use strict";'):s.rindex("</script>")]
    return s


def _head(src: str) -> str:
    """默认参数 + 状态 + 计算 + 结果段（chanList / chanVal、旺季对比 scenData、FOB vs 国内 domData / cmpPlans），足够在 node 里算利润表。"""
    a = src.index("/* All visible channels in one list")
    b = src.index("function renderDetail(R)")
    return src[:src.index("/* ---------------- bulk")] + src[a:b]


@needs_node
def test_flow17_profit_numbers_match_original_tool(tmp_path, wen, client):
    """FLOW-17：每个利润数字与原工具基准一致（原 index.html 的 JS 在 node 里算同一组输入）；原工具导出的方案 .json 可导入；
    方案存服务端，另一台电脑（只读账号）能看到同一份。"""
    orig, eng = _script(PROFIT_HTML), _script(ENGINE)
    for blk in _calc_blocks(orig):
        assert blk in eng  # 默认参数与计算逻辑逐字保留
    base = _node(HARNESS % _head(orig), tmp_path, "orig.js")
    got = _node(HARNESS % _head(eng), tmp_path, "mine.js")
    for k in ("R", "dom", "scen", "plans", "seaFob", "seaDom"):
        assert got[k] == base[k], k  # 利润表、国内出货、旺季 / 海运方案对比逐项相同
    assert len(base["R"]) == 5 and base["R"][0]["name"] == "24寸 单包" and isinstance(base["R"][0]["sc"][0]["fbm"], float)
    d0 = base["dom"][0]
    assert d0["dom"]["cost"] != d0["fob"]["cost"] and base["seaDom"] and base["scen"][0]["on"]["sc"] != base["scen"][0]["off"]["sc"]
    # 原工具导出的方案 .json（格式 {version, params, products}）导入为服务端方案
    js = json.dumps({"version": 1, "params": base["params"], "products": base["products"]}, ensure_ascii=False)
    r = wen.post("/tools/profit/import", files={"file": ("利润测算方案_20261101.json", js.encode("utf-8"), "application/json")})
    assert r.status_code == 200 and r.json()["count"] == 5 and r.json()["name"] == "利润测算方案_20261101"
    pid = r.json()["id"]
    assert wen.post("/tools/profit/import", files={"file": ("坏.json", b"{bad", "application/json")}).status_code == 400
    # 另一台电脑、只读账号：看到同一份方案，页面只读
    make_user("lixiaomei", "李晓梅", "readonly")
    ro = login_as(TestClient(client.app), "lixiaomei", "密码-123456")
    items = ro.get("/tools/profit/plans").json()["items"]
    assert [x["id"] for x in items] == [pid] and items[0]["products"] == base["products"] and items[0]["by"] == "wen"
    page = ro.get(f"/tools/profit?plan={pid}").text
    assert '"readonly": true' in page and "/static/profit/engine.js" in page and "导入报价表" in page and "利润测算表" in page and "历史库" in page
    assert ro.post("/tools/profit/plans", json={"name": "x", "products": [{}]}).status_code == 403
    # 历史库：保存新版本、改名、删除
    n2 = wen.post("/tools/profit/plans", json={"name": "树脂一体30寸_v1", "params": base["params"], "products": base["products"][:2]}).json()
    assert n2["count"] == 2
    assert wen.post(f"/tools/profit/plans/{n2['id']}", json={"name": "树脂一体30寸_v2"}).json()["name"] == "树脂一体30寸_v2"
    wen.post(f"/tools/profit/plans/{n2['id']}/delete")
    assert [x["id"] for x in wen.get("/tools/profit/plans").json()["items"]] == [pid]
    assert Path(__file__).resolve().parent.parent.joinpath("pdt/static/vendor/xlsx.full.min.js").exists()  # 导出 Excel 不依赖外网


@needs_node
def test_flow18_card_prefill_and_writeback(tmp_path, wen):
    """FLOW-18：从决策卡“测算利润”打开时预填尺寸与拟定售价；保存并回写后卡片“钱”一节显示各渠道单件利润、利润率、保本价；方案改售价再保存，卡片随之更新。"""
    ds.seed_all()
    cid = wen.post("/cards", data={"channel": "amazon", "frame": ds.FRAME, "attr": "台面材质", "value": "树脂"}, headers=J).json()["id"]
    with session() as s:
        price = s.get(Card, cid).narrative["price"]
    assert f'href="/tools/profit?card={cid}"' in wen.get(f"/cards/{cid}").text
    page = wen.get(f"/tools/profit?card={cid}").text
    pdt = json.loads(page.split("window.PDT = ")[1].split(";</script>")[0])
    assert pdt["card"]["price"] == price and pdt["card"]["size"] == "30″" and pdt["card"]["id"] == cid
    assert "已从卡片带入：尺寸 30″、拟定售价 $" + str(price) in page
    assert "保存并回写决策卡" in page
    head = _head(_script(ENGINE))

    def prod_of(p):
        return {"id": "c1", "name": "30″ 树脂（决策卡）", "desc": "", "supplier": "", "category": "家具", "peak": "非旺季", "price": p, "cost": 130,
                "costCur": "USD", "adj": 0, "prices": {}, "pkgs": [{"l": 93, "w": 57, "h": 40, "kg": 47}]}  # 原工具示例“30寸 单包”的包装

    def result(p):
        prod = prod_of(p)
        code = "var document = {getElementById: function(){ return {addEventListener: function(){}}; }, querySelectorAll: function(){ return []; }, addEventListener: function(){}}; var window = {PDT: {init: {products: [%s]}}}; var PDT = window.PDT; var localStorage = {getItem: function(){ return null; }, setItem: function(){}};\n%s\n" % (json.dumps(prod), head)
        code += """var r = calcProduct(products[0]);
console.log(JSON.stringify({product: products[0].name, rows: chanList().map(function(ch){ var v = chanVal(r, ch, 0);
  if (ch.amz) return {channel: ch.name, price: r.price, profit: v.profit, margin: v.profit / r.price, breakeven: null};
  var x = r.plat[ch.plat]; return {channel: ch.name, price: x.promo, profit: x.sc[0].promo.profit, margin: x.sc[0].promo.margin, breakeven: x.sc[0].breakeven}; })}));"""
        return _node(code, tmp_path, f"r{p}.js")

    r1 = result(price)
    plan = wen.post("/tools/profit/plans", json={"name": "树脂一体30寸_v1", "params": {}, "products": [prod_of(price)], "card_id": cid, "result": r1}).json()
    sec8 = html.unescape(wen.get(f"/cards/{cid}").text.split('id="s8"')[1].split('id="s9"')[0])
    for row in r1["rows"]:
        assert row["channel"] in sec8
        p = row["profit"]
        assert f"{'−' if p < 0 else ''}${abs(p):.2f}" in sec8 and f"{row['margin'] * 100:.1f}%" in sec8
    assert "方案“树脂一体30寸_v1”" in sec8 and "随方案更新" in sec8
    fbm1 = next(r for r in r1["rows"] if r["channel"] == "Amazon FBM")["profit"]
    r2 = result(price + 30)
    wen.post(f"/tools/profit/plans/{plan['id']}", json={"products": [prod_of(price + 30)], "result": r2})
    sec8 = html.unescape(wen.get(f"/cards/{cid}").text.split('id="s8"')[1].split('id="s9"')[0])
    fbm2 = next(r for r in r2["rows"] if r["channel"] == "Amazon FBM")["profit"]
    money = lambda v: f"{'−' if v < 0 else ''}${abs(v):.2f}"
    assert fbm2 > fbm1 and money(fbm2) in sec8 and money(fbm1) not in sec8
    with session() as s:
        assert s.get(Card, cid).profit_plan_id == plan["id"] and s.get(ProfitPlan, plan["id"]).card_id == cid


@needs_node
def test_sync_script_regenerates_committed_files():
    """同步脚本：对现在的原工具运行成功，生成的 engine.js / profit.css / _profit_sections.html 与提交的版本逐字相同；
    补丁清单每条都有说明和【判定台改动】编号；同步记录里的哈希就是原工具文件的哈希（启动时据此判断原工具有没有更新）。"""
    out = sync.build(PROFIT_HTML.read_text(encoding="utf-8"))
    for path, text in out.items():
        assert path.read_text(encoding="utf-8") == text, path.name
    assert all(p["why"] and p["mark"] in sync.MARKS for p in sync.PATCHES)
    assert {p["mark"] for p in sync.PATCHES} >= {"1/4", "2/4", "3/4", "4/4"}
    assert json.loads(sync.STAMP.read_text(encoding="utf-8"))["source_sha256"] == sync.file_sha(PROFIT_HTML)
    eng = out[sync.OUT_ENGINE]
    # 新版界面在系统里：变量抽屉、计算说明、渠道费用矩阵、保存回当前版本；“当前版本”不再记在本浏览器
    for key in ("function openVars()", "function openHelp(id)", 'class="cm"', "function histSaveCur()", "function getCur(){ return (window.PDT&&PDT.cur)||null; }"):
        assert key in eng, key
    assert "pc_cur" not in eng and "window.claude" not in eng and "x-api-key" not in eng
    body = out[sync.OUT_HTML]
    for key in ('id="varDrawer"', 'id="helpModal"', 'id="saveBar4"', 'id="saveBar5"', 'id="vChan"'):
        assert key in body, key
    assert "#pc-root #varDrawer{" in out[sync.OUT_CSS] and "\nbody{" not in out[sync.OUT_CSS]


def test_sync_script_stops_when_anchor_missing(tmp_path, monkeypatch, capsys):
    """原工具里某条补丁的锚点没了（这里删掉“初始方案”那两行）：脚本报出是第几条、原工具哪一段变了，不生成半成品、不覆盖现有文件。"""
    outs = {}
    for name in ("OUT_ENGINE", "OUT_CSS", "OUT_HTML", "STAMP", "DEFAULT_SRC"):
        src = getattr(sync, name)
        dst = tmp_path / src.name
        dst.write_text(src.read_text(encoding="utf-8") if name != "DEFAULT_SRC" else "", encoding="utf-8")
        monkeypatch.setattr(sync, name, dst)
        outs[dst] = dst.read_text(encoding="utf-8")
    html = PROFIT_HTML.read_text(encoding="utf-8")
    cut = 'let products = load("pc_products") || sampleProducts();\n'
    assert html.count(cut) == 1
    bad = tmp_path / "利润测算台_改过.html"
    bad.write_text(html.replace(cut, ""), encoding="utf-8")
    assert sync.main(["--from", str(bad)]) == 1
    err = capsys.readouterr().err
    assert "同步停下，没有改动任何文件" in err and "补丁 #1" in err and "【判定台改动 1/4】" in err and "需要找 AI" in err
    assert '-let products = load("pc_products") || sampleProducts();' in err  # 差异里指出原工具哪一行没了
    for p, text in outs.items():
        assert p.read_text(encoding="utf-8") == text, p.name  # 现有文件原样保留
    # 锚点出现两次同样停下
    a1 = sync.PATCHES[0]["anchor"]
    bad.write_text(html.replace(a1, a1 + a1), encoding="utf-8")
    assert sync.main(["--from", str(bad)]) == 1 and "出现 2 次" in capsys.readouterr().err
    # 页面结构变了（少了一条要去掉的整页样式）也停下
    bad.write_text(html.replace("header.bar .wrap{", "header.top .wrap{"), encoding="utf-8")
    assert sync.main(["--from", str(bad)]) == 1 and "header.bar .wrap" in capsys.readouterr().err
    for p, text in outs.items():
        assert p.read_text(encoding="utf-8") == text, p.name


def test_profit_page_hints_when_original_tool_changed(wen, tmp_path, monkeypatch):
    """启动时检测：原工具 index.html 与上次同步的哈希不同，利润测算页顶部提示“原工具有更新，运行同步脚本”；相同则不提示。只提示，不改代码。"""
    from pdt.web import routes_tools
    stamp = tmp_path / "profit_sync.json"
    monkeypatch.setattr(routes_tools, "PROFIT_SYNC", stamp)
    stamp.write_text(json.dumps({"source_sha256": sync.file_sha(PROFIT_HTML)}), encoding="utf-8")
    routes_tools.profit_tool_outdated.cache_clear()
    assert "原工具有更新" not in wen.get("/tools/profit").text
    stamp.write_text(json.dumps({"source_sha256": "0" * 64}), encoding="utf-8")
    routes_tools.profit_tool_outdated.cache_clear()
    page = wen.get("/tools/profit").text
    assert "原工具有更新，运行同步脚本" in page and "python tools_sync_profit.py" in page
    routes_tools.profit_tool_outdated.cache_clear()


def test_flow18_writeback_rejects_missing_inputs(wen):
    """DESIGN-14 / FLOW-18：产品缺出厂价（或采购成本）、尺寸或售价时，回写接口拒绝并说明“请补全：…”；保本价 ≤ 0 的结果不得写回；
    被拒后决策卡不关联方案、“钱”一节不出现错误数字。"""
    ds.seed_all()
    cid = wen.post("/cards", data={"channel": "amazon", "frame": ds.FRAME, "attr": "台面材质", "value": "树脂"}, headers=J).json()["id"]
    full = {"id": "c1", "name": "30″ 树脂（决策卡）", "category": "家具", "price": 399, "cost": 130, "costCur": "USD", "adj": 0, "prices": {},
            "pkgs": [{"l": 93, "w": 57, "h": 40, "kg": 47}]}
    rows = [{"channel": "Amazon FBM", "price": 399, "profit": 160.4, "margin": 0.402, "breakeven": 0.0},
            {"channel": "Home Depot", "price": 379, "profit": 120.5, "margin": 0.318, "breakeven": 251.3}]
    res = {"product": full["name"], "sea": "当前海运", "rows": rows}
    no_cost = dict(full, cost="")
    r = wen.post("/tools/profit/plans", json={"name": "树脂一体30寸_缺出厂价", "params": {}, "products": [no_cost], "card_id": cid, "result": res})
    assert r.status_code == 400 and r.json()["detail"] == "不能回写：请补全：出厂价 / 采购成本"
    no_all = dict(full, cost="", price="", pkgs=[{"l": "", "w": "", "h": "", "kg": ""}])
    r = wen.post("/tools/profit/plans", json={"name": "树脂一体30寸_缺三项", "params": {}, "products": [no_all], "card_id": cid, "result": res})
    assert r.json()["detail"] == "不能回写：请补全：出厂价 / 采购成本、尺寸（包裹长宽高）、售价"
    r = wen.post("/tools/profit/plans", json={"name": "树脂一体30寸_保本价0", "params": {}, "products": [full], "card_id": cid, "result": res})
    assert r.status_code == 400 and "Amazon FBM 的保本价无效（≤ $0）" in r.json()["detail"]
    with session() as s:
        assert s.get(Card, cid).profit_plan_id is None and s.query(ProfitPlan).count() == 0
    # 已保存的方案再走回写接口同样拒绝
    plan = wen.post("/tools/profit/plans", json={"name": "树脂一体30寸_v1", "params": {}, "products": [no_cost]}).json()
    r = wen.post(f"/tools/profit/{plan['id']}/link/{cid}", json={"result": dict(res, rows=rows[1:])})
    assert r.status_code == 400 and "请补全：出厂价 / 采购成本" in r.json()["detail"]
    r = wen.post(f"/tools/profit/plans/{plan['id']}", json={"card_id": cid, "result": dict(res, rows=rows[1:])})
    assert r.status_code == 400
    with session() as s:
        assert s.get(Card, cid).profit_plan_id is None
    assert "$160.40" not in html.unescape(wen.get(f"/cards/{cid}").text.split('id="s8"')[1].split('id="s9"')[0])
    # 补全出厂价、去掉无效保本价后可以回写
    plan2 = wen.post("/tools/profit/plans", json={"name": "树脂一体30寸_v2", "params": {}, "products": [full], "card_id": cid,
                                                   "result": dict(res, rows=rows[1:])})
    assert plan2.status_code == 200
    with session() as s:
        assert s.get(Card, cid).profit_plan_id == plan2.json()["id"]


@needs_node
def test_writeback_modal_missing_fields_js(tmp_path):
    """DESIGN-14：弹窗与服务端同一必填口径——pdt-profit.js 的 missingFields 对缺出厂价 / 尺寸 / 售价逐项给出“请补全”内容；国内出货价可代替出厂价。"""
    src = (ENGINE.parent / "pdt-profit.js").read_text(encoding="utf-8")
    code = "var window = {PDT: {}}; var localStorage = {getItem: function(){ return null; }};\n" + src + """
var f = window.PDT.missingFields;
var full = {name: "30″ 树脂（决策卡）", price: 399, cost: 130, pkgs: [{l: 93, w: 57, h: 40, kg: 47}]};
console.log(JSON.stringify([f(full), f(Object.assign({}, full, {cost: ""})), f(Object.assign({}, full, {cost: "", costRmb: 905})),
  f({name: "36″ 岗石", price: "", cost: "", pkgs: [{l: 93, w: "", h: 40, kg: 47}]})]));"""
    out = _node(code, tmp_path, "missing.js")
    assert out == [[], ["出厂价 / 采购成本"], [], ["出厂价 / 采购成本", "尺寸（包裹长宽高）", "售价"]]


class FakeQuoteLLM:
    """假大模型：记录提示词，返回原工具要求格式的 JSON（夹在说明文字里，验证与 parseLoose 相同的宽松解析）。"""
    def __init__(self):
        self.calls = []

    def complete(self, prompt, images=None, max_tokens=4096):
        self.calls.append((prompt, images, max_tokens))
        out = {"factory": "嘉宏卫浴", "quote_date": "2026-11-01", "items": [
            {"name": "RV30-ON", "desc": "树脂一体 · 原木", "match_key": "30寸 落地式", "price": 118, "price_currency": "USD", "price_tax": "FOB",
             "price_rmb_tax": 905, "moq": 100, "packages": [{"l": 880, "w": 520, "h": 380, "dim_unit": "mm", "weight": 36, "weight_unit": "kg"}], "notes": ""}]}
        return "识别结果如下：\n" + json.dumps(out, ensure_ascii=False), 0.042


@needs_node
def test_flow17_ai_quote_via_server_and_costgate(tmp_path, wen):
    """AI 识别报价单：浏览器不直连大模型、不存 Key（NFR-008、AC-F16-05）；服务端用设置页所选大模型，先估算、确认后才识别，费用记入同一费用记录；
    提示词与原工具 aiPrompt 逐字相同；大模型未连接时提示去设置页。"""
    eng = _script(ENGINE)
    for bad in ("pc_ai_cfg", "x-api-key", "anthropic-dangerous-direct-browser-access", "api.anthropic.com", "aiKey()", "localStorage.setItem(\"pc_ai"):
        assert bad not in eng, bad
    payload = {"kind": "text", "name": "嘉宏报价_20261101.xlsx", "keys": ["30寸 落地式", "24寸 单盆"], "text": "\n### 工作表：报价\n型号,外箱尺寸,毛重,FOB\nRV30-ON,880*520*380mm,36,118\n"}
    r = wen.post("/tools/profit/ai/prepare", json=payload)
    assert r.status_code == 400 and "设置页" in r.json()["detail"]
    page = wen.get("/tools/profit").text
    assert '"llm": null' in page and "AI 接口设置" not in page and 'id="aiKey"' not in page
    services.save_secret("llm_claude", "sk-ant-测试密钥-0001")
    llm = FakeQuoteLLM()
    services.set_fake("llm", llm)
    assert '"llm": "Claude"' in wen.get("/tools/profit").text
    tok = wen.post("/tools/profit/ai/prepare", json=payload).json()["token"]
    j = wen.post("/jobs/estimate", data={"kind": "profit_ai_quote", "target": f"quote:{tok}"}).json()
    assert j["status"] == "estimated" and j["estimate"]["usd_hi"] > 0 and llm.calls == []  # 先确认费用
    assert wen.post(f"/jobs/{j['id']}/confirm").json()["status"] == "done"
    res = wen.get(f"/tools/profit/ai/{tok}").json()
    assert res["status"] == "done" and res["out"]["factory"] == "嘉宏卫浴" and res["out"]["items"][0]["price_rmb_tax"] == 905
    with session() as s:
        rec = s.query(CostRecord).filter_by(service="llm").one()
        assert rec.amount == 0.042 and "AI 识别报价单" in rec.task
    # 提示词：用原工具的 aiPrompt 在 node 里拼出同一份，与服务端发给大模型的逐字相同
    orig = _script(PROFIT_HTML)
    fn = orig[orig.index("function aiPrompt(body){"):orig.index("function parseLoose(t)")]
    code = ("var qlib = {items: [{items: [{key: '30寸 落地式'}, {key: '24寸 单盆'}]}]};\n" + fn +
            "\nconsole.log(JSON.stringify(aiPrompt(%s)));" % json.dumps(payload["text"]))
    assert _node(code, tmp_path, "prompt.js") == llm.calls[0][0] and llm.calls[0][2] == 16000
    # 截图走图片附件；PDF 不支持
    tok = wen.post("/tools/profit/ai/prepare", json={"kind": "image", "name": "报价单.png", "keys": [], "data": "iVBORw0KGgo=", "media_type": "image/png"}).json()["token"]
    j = wen.post("/jobs/estimate", data={"kind": "profit_ai_quote", "target": f"quote:{tok}"}).json()
    wen.post(f"/jobs/{j['id']}/confirm")
    assert llm.calls[1][1] == [(b"\x89PNG\r\n\x1a\n", "image/png")] and "（见附带的报价单图片）" in llm.calls[1][0]
    assert wen.post("/tools/profit/ai/prepare", json={"kind": "pdf", "name": "报价.pdf"}).status_code == 400


def test_quote_library_on_server(wen, client):
    """报价库与历史库一样存服务端（AC-F24-02 局域网同一份）；原工具的报价库数据（.json）可导入。"""
    q = {"factory": "嘉宏卫浴", "version": "2026-11 报价", "date": "2026-11-01", "source": "嘉宏报价_20261101.xlsx",
         "items": [{"key": "30寸 落地式", "name": "RV30-ON", "desc": "树脂一体 · 原木", "cost": 118, "costRmb": 905, "costCur": "USD", "moq": 100,
                    "pkgs": [{"l": 88, "w": 52, "h": 38, "kg": 36}]}]}
    a = wen.post("/tools/profit/quotes", json=q).json()
    assert a["count"] == 1 and a["by"] == "wen" and isinstance(a["id"], str)
    assert wen.post(f"/tools/profit/quotes/{a['id']}", json={"version": "2026-11 报价（改）"}).json()["version"] == "2026-11 报价（改）"
    old = [dict(q, id="k3x9", factory="恒发家具", version="2026-10 报价", savedAtMs=1761900000000, count=1)]
    r = wen.post("/tools/profit/quotes/import", files={"file": ("报价库.json", json.dumps(old, ensure_ascii=False).encode(), "application/json")})
    assert [x["factory"] for x in r.json()["items"]] == ["恒发家具"]
    make_user("lixiaomei", "李晓梅", "readonly")
    ro = login_as(TestClient(client.app), "lixiaomei", "密码-123456")
    assert {x["factory"] for x in ro.get("/tools/profit/quotes").json()["items"]} == {"嘉宏卫浴", "恒发家具"}
    assert ro.post("/tools/profit/quotes", json=q).status_code == 403
    page = ro.get("/tools/profit").text
    assert 'id="quoteCount"' in page and "报价库" in page and 'id="s6"' in page
    wen.post(f"/tools/profit/quotes/{a['id']}/delete")
    assert len(wen.get("/tools/profit/quotes").json()["items"]) == 1


def test_quote_metric_options_filled_before_quotes_load():
    """DESIGN-14：报价对比“对比指标”下拉框在报价库读取中或没有版本时也有选项（采购成本 / 落地成本 / 各渠道利润，即 qMetricVal 支持的取值），
    不再因为 renderS6 提前返回而留空。"""
    src = ENGINE.read_text(encoding="utf-8")
    body = src[src.index("function renderS6(){"):]
    fill = body.index('document.getElementById("qMetric").innerHTML=ms.map(')
    assert fill < body.index('if(qlib.mode==="pending"||qlib.loading)') and fill < body.index("if(!qlib.items.length)")
    assert src.count('document.getElementById("qMetric").innerHTML=') == 1
    assert 'const METRICS=()=>[["cost","采购成本 $（换算美元，越低越好）"],["landed",' in src


def test_design13_steps_single_number_and_nothing_to_collect(wen):
    """DESIGN-13（v8 复核）：四步进度条每步只有圆圈编号一个序号（名称不再带“①”）；
    费用弹窗在估算为“没有要采的内容”（nothing）时禁用“确认并开始”（Home Depot 回补没有要采的商品页时估算带 nothing、说明“没有需要采集的商品页”，见 test_backfill FLOW-27 用例）。"""
    html = wen.get('/tools/vp').text
    steps = html.split('aria-label="四步流程"')[1].split('</ol>')[0]
    names = [x.split('</span>')[0] for x in steps.split('<span class="step__name">')[1:]]
    assert names == ['采集列表', '评估费用', '采集评论', '导出 Excel']
    assert '①完成后可评估' not in steps
    js = wen.get('/static/costgate.js').text
    assert "ok.disabled = !!e.nothing" in js
