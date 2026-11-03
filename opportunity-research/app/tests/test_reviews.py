"""差评拉取与归类（F22）：FLOW-15。卖家精灵与大模型用假服务；Home Depot 评论来自评论 VP 追踪已采集明细（ChannelReview）。"""
import pytest

import decision_seed as ds
from pdt import services
from pdt.db import session
from pdt.models import CardReview, CostRecord

J = {"accept": "application/json"}
CATS = {"装配 / 做工", "本品类关键部件", "柜体材料", "结构 / 设计", "运输", "服务", "不明"}


@pytest.fixture()
def card(wen):
    ds.seed_all()
    services.save_secret("sellersprite", "ss-测试密钥-0001")
    services.save_secret("llm_claude", "sk-ant-测试密钥-0001")
    ss, llm = ds.FakeSellerSprite(), ds.FakeLLM()
    services.set_fake("sellersprite", ss)
    services.set_fake("llm", llm)
    cid = wen.post("/cards", data={"channel": "amazon", "frame": ds.FRAME, "attr": "台面材质", "value": "树脂"}, headers=J).json()["id"]
    return wen, cid, ss, llm


def test_flow15_pull_merge_classify_and_override(card):
    """FLOW-15：确认费用后只拉卡中 SKU 的 1–3 星（每个最多 30 条）；Home Depot 1–3 星从 F23 明细并入同卡（同系列共享评论只算一次）；
    每条归入七类之一并显示占比；把一条从“运输”改判为“装配 / 做工”后占比重算、标“人工修改”。"""
    wen, cid, ss, llm = card
    html = wen.get(f"/cards/{cid}").text
    assert 'data-cost-kind="amazon_reviews"' in html
    j = wen.post("/jobs/estimate", data={"kind": "amazon_reviews", "target": f"card:{cid}"}).json()
    assert j["status"] == "estimated" and ss.calls == [] and llm.calls == []  # 先弹费用确认，未确认不调用
    assert set(j["estimate"]["services"]) == {"sellersprite", "llm"} and j["estimate"]["services"]["sellersprite"]["calls"] == 4
    j = wen.post(f"/jobs/{j['id']}/confirm").json()
    assert j["status"] == "done", j
    asins = {"B0D1QHH3QW", "B0DY7SKD52", "B0GSQKH3HV", "B0H452LRTC"}  # 卡片 SKU 层里的 Amazon 子 ASIN
    assert {c[0] for c in ss.calls} == asins and all(c[1] == (1, 2, 3) and c[2] == 30 for c in ss.calls)
    with session() as s:
        rows = s.query(CardReview).filter_by(card_id=cid).all()
        amz = [r for r in rows if r.channel == "amazon"]
        hd = [r for r in rows if r.channel == "homedepot"]
        assert all(r.stars <= 3 for r in rows)
        for a in asins:
            n = sum(1 for r in amz if r.item_id == a)
            assert 0 < n <= 30
        assert len(amz) == 4 * 24  # 每个 ASIN 返回 40 条（1–5 星各 8 条），1–3 星 24 条
        assert sorted(r.review_id for r in hd) == ["hd-r1", "hd-r2", "hd-r4"]  # 5 星的 hd-r3 不并入；hd-r2 同系列共享只算一次
        assert all(r.reason in CATS for r in rows)
        assert s.query(CostRecord).filter_by(service="sellersprite").count() == 4
        assert s.query(CostRecord).filter_by(service="llm").count() >= 1
        target = next(r for r in hd if r.review_id == "hd-r2")
        assert target.reason == "运输"
        tid = target.id
        n_transport = sum(1 for r in rows if r.reason == "运输")
        n_assembly = sum(1 for r in rows if r.reason == "装配 / 做工")
        total = len(rows)
    html = wen.get(f"/cards/{cid}").text
    s7 = html.split('id="s7"')[1].split('id="s8"')[0]
    for c in ["装配 / 做工", "本品类关键部件（树脂本身）", "柜体材料", "结构 / 设计", "运输", "服务", "不明"]:
        assert c in s7
    assert f"{n_transport} 条 · {round(n_transport / total * 100)}%" in s7
    r = wen.post(f"/reviews/{tid}/category", data={"reason": "装配 / 做工"}, headers=J).json()
    got = {c["cat"]: c for c in r["cats"]}
    assert got["运输"]["n"] == n_transport - 1 and got["装配 / 做工"]["n"] == n_assembly + 1
    assert abs(got["装配 / 做工"]["pct"] - (n_assembly + 1) / total) < 1e-9 and r["manual"] == 1
    with session() as s:
        t = s.get(CardReview, tid)
        assert t.reason == "装配 / 做工" and t.reason_source == "manual"
    html = wen.get(f"/cards/{cid}").text
    assert "人工修改" in html and f"{n_assembly + 1} 条 · {round((n_assembly + 1) / total * 100)}%" in html
    assert wen.post(f"/reviews/{tid}/category", data={"reason": "质量"}, headers=J).status_code == 400


def test_reviews_without_llm_only_show_text(wen):
    """大模型未连接：差评只显示原文、不归类（requirements 依赖兜底）。"""
    ds.seed_all()
    services.save_secret("sellersprite", "ss-测试密钥-0001")
    services.set_fake("sellersprite", ds.FakeSellerSprite())
    cid = wen.post("/cards", data={"channel": "amazon", "frame": ds.FRAME, "attr": "台面材质", "value": "树脂"}, headers=J).json()["id"]
    j = wen.post("/jobs/estimate", data={"kind": "amazon_reviews", "target": f"card:{cid}"}).json()
    assert "大模型未连接" in j["estimate"]["note"]
    assert wen.post(f"/jobs/{j['id']}/confirm").json()["status"] == "done"
    with session() as s:
        rows = s.query(CardReview).filter_by(card_id=cid).all()
        assert rows and all(r.reason == "" for r in rows)
    assert "大模型未连接：只显示原文、不归类" in wen.get(f"/cards/{cid}").text
