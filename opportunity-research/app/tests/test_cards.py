"""决策卡（PAGE-F21-01 / 02）：FLOW-12、FLOW-13、FLOW-14、FLOW-26（决策卡部分）、RULE-03、AC-F19-04、NFR-010、AC-F15-03。
期望值来自 solution-v2/机会判定卡/决策卡_树脂*.md（见 decision_seed.py 文档），不由被测代码生成。"""
import json
import re

import pytest

from conftest import login_as, make_user
import decision_seed as ds

UNIT = {"channel": "amazon", "frame": ds.FRAME, "attr": "台面材质", "value": "树脂"}
J = {"accept": "application/json"}


def _card(c, **kw):
    r = c.post("/cards", data=dict(UNIT, **kw), headers=J)
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture()
def seeded(wen):
    ds.seed_all()
    return wen


def test_flow12_ten_sections_numbers_sources_readonly(seeded):
    """FLOW-12：十个分节齐全；“我们在赌什么”含市场评分、扣偏差后的新品打分、框内历史做到率与 p 值、拟定价位实测成交；
    每个数字可点开看框、月份、样本数；数字不可改，叙述可编辑并保存；做到概率原值与扣偏差值并列。"""
    cid = _card(seeded)
    html = seeded.get(f"/cards/{cid}").text
    for no, sec in enumerate(["分框决策", "我们在赌什么", "看到什么就停", "被放弃的选项", "大数据层：时间线", "SKU 层", "差评归类", "钱", "上架后跟踪", "数据限制"], 1):
        assert f'<span class="csec__no">{no:02d}</span>{sec}' in html, sec
    s2 = html.split('id="s2"')[1].split('id="s3"')[0]
    assert "把握 57%" in s2 and "B 档" in s2 and "13.1%（80% 区间 9.6%–17.4%）" in s2  # 市场评分（UnitScore）
    assert "6.4 / 6.2" in s2 and "扣偏差 1.2 后" in s2 and "5.2 / 5.0" in s2  # 原值与扣偏差值并列（AC-F21-03）
    assert re.search(r"新家族 <span class=\"num\">6</span> 个做到 <span class=\"num\">5</span> 个；同框其他 <span class=\"num\">79</span> 个做到 <span class=\"num\">37</span> 个 · <span class=\"num\">p = 0.11</span>", s2)
    assert "$200–250：" in s2 and "月销中位" in s2  # 拟定价位实测成交
    assert "4.09" in s2 and "4.27" in s2
    # 每个数字的来源浮层都带框、月份、样本数（AC-F21-02）
    pops = re.findall(r'data-pop="([^"]*)"', html)
    assert len(pops) >= 10
    for p in pops:
        assert "框=" in p and "月份=" in p and "样本数=" in p, p
    # 数字不可编辑：直接改数字的请求被拒绝；叙述可编辑并保存
    r = seeded.post(f"/cards/{cid}/numbers", data={"bet.score.grasp": "0.9"}, headers=J)
    assert r.status_code == 409 and "不能直接修改" in r.json()["detail"]
    r = seeded.post(f"/cards/{cid}/narrative", data={"numbers.share_now": "0.5"}, headers=J)
    assert r.status_code == 409
    r = seeded.post(f"/cards/{cid}/narrative", data={"consumer": "陶瓷一体占七成、款式同质；树脂一体在同价位给出不一样的样子。"}, headers=J)
    assert r.status_code == 200 and r.json()["ok"]
    html = seeded.get(f"/cards/{cid}").text
    assert "陶瓷一体占七成、款式同质" in html and 'name="consumer" form="narr-form"' in html
    assert 'data-numbers="readonly"' in html and "<input" not in html.split('id="s2"')[1].split('narr-consumer')[0]


def test_flow13_sku_drawer_and_bigdata_layer(seeded):
    """FLOW-13：SKU 抽屉显示子 ASIN 链接、主图、逐月价格 / 价比 / 评分 / 月销 / 小类排名、首次进前 50；
    B0D1QHH3QW 2025-07 至 11 的数值与《决策卡_树脂_数据.md》一致；大数据层有份额、新品占比、溢价率、价格带构成的逐季图。"""
    cid = _card(seeded)
    html = seeded.get(f"/cards/{cid}").text
    assert 'id="drawer-sku"' in html and "data-sku-link" in html and "data-sku-img" in html and "首次进前 50" in html
    skus = json.loads(re.search(r'<script type="application/json" id="sku-data">(.*?)</script>', html, re.S).group(1))
    amz = skus[0]
    k = next(x for x in amz if x["item_id"] == "B0D1QHH3QW")
    assert k["link"] == "https://www.amazon.com/dp/B0D1QHH3QW" and k["image_url"].startswith("https://m.media-amazon.com/")
    assert k["first_top50"] == "2025-07" and k["best_rank"] == 7
    got = {r["month"]: r for r in k["series"]}
    expect = {"2025-07": (280, 1.12, 4.2, 115, 16), "2025-08": (320, 1.30, 4.2, 89, 24), "2025-09": (320, 1.39, 4.2, 64, 30),
              "2025-10": (320, 1.33, 4.2, 96, 28), "2025-11": (280, 1.17, 4.2, 87, 22)}
    for m, (price, ratio, rating, units, rank) in expect.items():
        r = got[m]
        assert (r["price"], round(r["price_ratio"], 2), r["rating"], r["units"], r["rank"]) == (price, ratio, rating, units, rank), m
    s5 = html.split('id="s5"')[1].split('id="s6"')[0]
    assert s5.count('class="spark chart"') >= 3 and "框内份额" in s5 and "新品占比" in s5 and "溢价率" in s5
    assert "价格带构成" in s5 and 'class="hbar__bar' in s5 and "2026Q3*" in s5


def test_flow14_ai_draft_after_cost_confirm(seeded):
    """FLOW-14：起草叙述先弹费用确认（估算时不调用大模型）；确认后填入大模型文字并标“AI 草稿”；编辑保存后标记消失。"""
    from pdt import services
    services.save_secret("llm_claude", "sk-ant-测试密钥-0001")
    llm = ds.FakeLLM()
    services.set_fake("llm", llm)
    cid = _card(seeded)
    assert 'data-cost-kind="llm_draft"' in seeded.get(f"/cards/{cid}").text
    j = seeded.post("/jobs/estimate", data={"kind": "llm_draft", "target": f"card:{cid}"}).json()
    assert j["status"] == "estimated" and j["estimate"]["usd_hi"] > 0 and llm.calls == []
    j = seeded.post(f"/jobs/{j['id']}/confirm").json()
    assert j["status"] == "done" and len(llm.calls) == 1
    html = seeded.get(f"/cards/{cid}").text
    assert "data-ai-badge><svg" in html and "AI 草稿" in html and "在同样的 $240 价位给出不一样的样子" in html
    from pdt.db import session
    from pdt.models import CostRecord
    with session() as s:
        assert s.query(CostRecord).filter_by(service="llm").count() == 1
    seeded.post(f"/cards/{cid}/narrative", data={"consumer": "树脂一体在 $240 给出可选颜色的一体盆台。（推测，待问答验证）"}, headers=J)
    html = seeded.get(f"/cards/{cid}").text
    assert "data-ai-badge><svg" not in html and "可选颜色的一体盆台" in html


def test_flow26_card_channels_side_by_side(seeded):
    """FLOW-26（决策卡部分）：四渠道并排显示份额、趋势、分级、样本量和上 / 不上 / 观察；Amazon 与 Home Depot 都涨标“多渠道印证”，
    Wayfair 在跌标“渠道分歧”；只在渠道内比较，不比绝对销量。"""
    cid = _card(seeded)
    j = seeded.get(f"/cards/{cid}/channels").json()
    by = {c["channel"]: c for c in j["channels"]}
    assert set(by) == {"amazon", "homedepot", "lowes", "wayfair"}
    assert (by["amazon"]["direction"], by["amazon"]["grade"], by["amazon"]["verdict"]) == ("涨", "B", "上")
    assert (by["homedepot"]["direction"], by["homedepot"]["verdict"]) == ("涨", "观察")
    assert by["lowes"]["sample_ok"] is False and by["lowes"]["verdict"] == "不上"
    assert (by["wayfair"]["direction"], by["wayfair"]["verdict"]) == ("跌", "不上")
    assert j["marks"]["agree"] == ["Amazon", "Home Depot"] and j["marks"]["diverge"] == ["Wayfair"]
    html = seeded.get(f"/cards/{cid}").text
    s1 = html.split('id="s1"')[1].split('id="s2"')[0]
    assert "多渠道印证：Amazon、Home Depot 都在涨" in s1 and "渠道分歧：Wayfair 在跌" in s1
    assert "8.4% → 11.5%" in s1 and "6.1% → 9.8%" in s1 and "14.2% → 10.6%" in s1 and "样本不足" in s1
    assert "只在本渠道内比较份额，不比较绝对销量" in s1 and "未验证" in s1


def test_ac_f19_04_validity_banner(wen):
    """AC-F19-04：最新模型评分未通过有效性检验时，每张卡顶部显示“市场评分本月未通过有效性检验”。"""
    ds.seed_all(valid=False)
    cid = _card(wen)
    assert "市场评分本月未通过有效性检验" in wen.get(f"/cards/{cid}").text


def test_nfr010_generate_within_30s(seeded):
    """NFR-010 / AC-F20-05：从扫描单元生成草稿（不含外部调用）30 秒内完成。"""
    import time
    t0 = time.time()
    cid = _card(seeded)
    assert time.time() - t0 < 30
    from pdt.db import session
    from pdt.models import Card
    with session() as s:
        c = s.get(Card, cid)
        assert c.status == "draft" and c.numbers["gen_seconds"] < 30 and "用时" in seeded.get(f"/cards/{cid}").text


def test_rule03_snapshot_after_approval(seeded, client):
    """RULE-03：批准后并入新月份、修改关联利润方案、直接改数字 → 数字与快照逐项相同、显示“有新数据”、改数字被拒；
    另存为新草稿用最新数据，原批准版本不变。"""
    from pdt.db import session
    from pdt.models import Batch, Card, ModelRun, Opportunity, ProfitPlan, UnitScore, now
    cid = _card(seeded)
    seeded.post(f"/cards/{cid}/narrative", data={"consumer": "树脂一体给出不一样的样子。"}, headers=J)
    plan = seeded.post("/tools/profit/plans", json={"name": "树脂一体30寸_v1", "products": [{"name": "30″ 树脂", "price": 240, "pkgs": []}], "params": {},
                                                    "card_id": cid, "result": {"product": "30″ 树脂", "rows": [{"channel": "Amazon FBM", "price": 240, "profit": 31.4, "margin": 0.131, "breakeven": 201.5}]}}).json()
    assert seeded.post(f"/cards/{cid}/submit", data={"note": "请审"}, headers=J).status_code == 200
    make_user("laoban", "老板", "approver")
    boss = login_as(client.__class__(client.app), "laoban", "密码-123456")
    assert boss.post(f"/cards/{cid}/decide", data={"decision": "approve", "comment": "先做 30″"}, headers=J).status_code == 200
    with session() as s:
        before = json.dumps(s.get(Card, cid).numbers, sort_keys=True)
        snap = s.get(Card, cid).snapshot
    page0 = seeded.get(f"/cards/{cid}").text
    # 数据更新：并入 2026-10、模型重算、利润方案改价后再保存
    with session() as s:
        s.add(Batch(channel="amazon", month="2026-10", source="api", status="merged", merged_at=now(), rows=100))
        run = ModelRun(month="2026-10", version="第九版", newlayer={"bias": {"pred": 0.41, "actual": 0.36, "bias": 0.05, "n": 230}}, valid=True)
        s.add(run)
        s.flush()
        old = s.query(UnitScore).filter_by(channel="amazon", value="树脂").first()
        s.add(UnitScore(run_id=run.id, channel="amazon", frame=ds.FRAME, attr="台面材质", value="树脂", data=dict(old.data, grasp=0.61)))
        for o in s.query(Opportunity).filter_by(channel="amazon", value="树脂"):
            o.metrics = dict(o.metrics, share=0.125)
    seeded.post(f"/tools/profit/plans/{plan['id']}", json={"products": [{"name": "30″ 树脂", "price": 260, "pkgs": []}],
                                                          "result": {"product": "30″ 树脂", "rows": [{"channel": "Amazon FBM", "price": 260, "profit": 45.0, "margin": 0.17, "breakeven": 201.5}]}})
    page = seeded.get(f"/cards/{cid}").text
    assert "有新数据" in page and "2026-10 Amazon 月度数据已并入" in page and "已更新" in page
    for a, b in (("8.4% → 11.5%", True), ("12.5%", False), ("$31.40", True), ("$45.00", False), ("5.2 / 5.0", True), ("快照", True)):
        assert (a in page) is b, a
    with session() as s:
        c = s.get(Card, cid)
        assert json.dumps(c.numbers, sort_keys=True) == before and c.snapshot == snap
        assert s.get(ProfitPlan, plan["id"]).result["rows"][0]["profit"] == 45.0
    assert page.split('id="s2"')[1].split('id="s3"')[0] == page0.split('id="s2"')[1].split('id="s3"')[0]
    r = seeded.post(f"/cards/{cid}/numbers", data={"bet.score.grasp": "0.9"}, headers=J)
    assert r.status_code == 409 and r.json()["detail"] == "已批准的卡不能改数字，只能另存为新草稿"
    r = seeded.post(f"/cards/{cid}/narrative", data={"consumer": "改"}, headers=J)
    assert r.status_code == 409
    nid = seeded.post(f"/cards/{cid}/save-as-new", headers=J).json()["id"]
    with session() as s:
        n, o = s.get(Card, nid), s.get(Card, cid)
        assert n.status == "draft" and n.parent_id == cid and n.version == o.version + 1
        assert n.numbers["bet"]["share_now"] == 0.125 and o.snapshot["numbers"]["bet"]["share_now"] == 0.115
        assert abs(n.numbers["bet"]["prob"]["adj"][0] - 0.59) < 1e-9  # 新草稿用最新模型偏差 0.05（每 10 个 0.5）
        assert o.status == "approved" and json.dumps(o.numbers, sort_keys=True) == before


def test_roles_on_card_page(seeded, client):
    """AC-F15-03：审批者在详情页只能批准 / 驳回 / 退回与留意见，不能编辑；只读只看。"""
    cid = _card(seeded)
    seeded.post(f"/cards/{cid}/narrative", data={"consumer": "树脂一体给出不一样的样子。"}, headers=J)
    seeded.post(f"/cards/{cid}/submit", data={"note": ""}, headers=J)
    make_user("laoban", "老板", "approver")
    make_user("lixiaomei", "李晓梅", "readonly")
    boss = login_as(client.__class__(client.app), "laoban", "密码-123456")
    ro = login_as(client.__class__(client.app), "lixiaomei", "密码-123456")
    h = boss.get(f"/cards/{cid}").text
    assert 'data-decide="approve"' in h and 'data-decide="reject"' in h and 'data-decide="return"' in h
    assert 'form="narr-form"' not in h and 'data-cost-kind="' not in h and "提交审批</span>" not in h
    assert boss.post(f"/cards/{cid}/narrative", data={"consumer": "改"}, headers=J).status_code == 403
    h = ro.get(f"/cards/{cid}").text
    assert 'data-decide="' not in h and 'form="narr-form"' not in h and "另存为新草稿" not in h and 'data-cost-kind="' not in h
    assert ro.post(f"/cards/{cid}/decide", data={"decision": "approve"}, headers=J).status_code == 403


def test_cards_list_filters(seeded):
    """PAGE-F21-01：列表按主渠道显示，六种状态带计数；其他渠道无卡时显示空状态。"""
    _card(seeded)
    h = seeded.get("/cards?channel=amazon").text
    assert "台面材质：树脂" in h and 'data-filter="status:draft"' in h and "草稿 <span class=\"count\">1</span>" in h
    assert "30″ · 拆装 · 落地式" in h
    assert "还没有以 Wayfair 为主渠道的决策卡" in seeded.get("/cards?channel=wayfair").text
