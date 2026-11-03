"""决策组测试数据：按《决策卡_树脂》样板造小而真实的数据（30″ · 拆装 · 落地式 × 台面材质：树脂）。

期望值来源：solution-v2/机会判定卡/决策卡_树脂.md、决策卡_树脂_数据.md（不由被测代码生成）。
- B0D1QHH3QW 2025-07 至 11：月销 115 / 89 / 64 / 96 / 87，价格 $280 / 320 / 320 / 320 / 280，价比 1.12 / 1.30 / 1.39 / 1.33 / 1.17，评分 4.2，小类排名 16 / 24 / 30 / 28 / 22；
- 市场评分把握 57% · B 档，份额 8.4% → 11.5%，预测 13.1%（9.6%–17.4%）；新品做到概率 6.4 / 6.2，模型偏差 1.2（每 10 个）→ 5.2 / 5.0；
- 框内历史：含树脂新家族 6 个做到 5 个，同框其他 79 个做到 37 个，p = 0.11。
"""
from pdt.db import session
from pdt.models import Batch, ChannelReview, ModelRun, Opportunity, Product, Snapshot, Tag, UnitScore

FRAME = "30″ · 拆装 · 落地式"
FRAME24 = "24″ · 拆装 · 悬浮式"
MONTHS = [f"2025-{m:02d}" for m in range(4, 13)] + [f"2026-{m:02d}" for m in range(1, 10)]  # 2025-04 至 2026-09


def _tags(s, ch, item, size="30″", zhuang="拆装", form="落地式", top="树脂", elem="农场风装饰饰条", color="灰", status="confirmed"):
    for t, v in (("尺寸段", size), ("装", zhuang), ("形态", form), ("台面材质", top), ("元素", elem), ("主色", color)):
        s.add(Tag(channel=ch, item_id=item, tag=t, value=v, source="manual" if status == "confirmed" else "rule",
                  status=status, auto_value=v, confidence=0.95))


def _batches(s, ch, months, star=()):
    ids = {}
    for m in months:
        b = Batch(channel=ch, month=m, source="api" if ch == "amazon" else "tracker", status="merged", star=m in star, rows=10)
        s.add(b)
        s.flush()
        ids[m] = b.id
    return ids


# 子 ASIN：品牌、取值、元素、主色、上架、家族、逐月 (月销, 价格, 评分, 排名)
AMZ = {
    "B0D1QHH3QW": ("AMERLIFE", "树脂", "农场风装饰饰条", "灰", "2024-04-14", "AMERLIFE-B0FGV32L8C",
                   {"2025-07": (115, 280, 4.2, 16), "2025-08": (89, 320, 4.2, 24), "2025-09": (64, 320, 4.2, 30),
                    "2025-10": (96, 320, 4.2, 28), "2025-11": (87, 280, 4.2, 22), "2025-12": (51, 300, 4.2, 108),
                    "2026-02": (70, 260, 4.2, 24), "2026-03": (61, 255, 4.3, 58), "2026-05": (56, 240, 4.3, 7),
                    "2026-06": (99, 240, 4.3, 11), "2026-07": (56, 240, 4.4, 19), "2026-08": (38, 240, 4.3, 25), "2026-09": (26, 240, 4.4, 27)}),
    "B0DY7SKD52": ("DELUXE LIVING", "树脂", "夏克式", "深木", "2025-03-02", "DELUXE-B0DY7SKD52",
                   {"2025-12": (88, 260, 4.6, 11), "2026-01": (100, 270, 4.7, 8), "2026-02": (83, 270, 4.6, 12), "2026-03": (69, 265, 4.4, 18),
                    "2026-04": (58, 255, 4.2, 22), "2026-05": (52, 250, 4.1, 30), "2026-06": (47, 250, 4.0, 35), "2026-07": (44, 250, 4.0, 40),
                    "2026-08": (40, 245, 3.9, 44), "2026-09": (38, 245, 3.9, 47)}),
    "B0GSQKH3HV": ("NOVAMAISON", "树脂", "竖棱", "原木", "2026-04-01", "NOVAMAISON-B0GSQKH3HV",
                   {"2026-04": (92, 310, 5.0, 61), "2026-05": (78, 310, 4.6, 17), "2026-06": (64, 310, 4.4, 24), "2026-07": (55, 310, 4.2, 33),
                    "2026-08": (50, 310, 4.2, 36), "2026-09": (48, 310, 4.2, 38)}),
    "B0H452LRTC": ("JUMMICO", "树脂", "农场风装饰饰条", "黑", "2026-06-06", "JUMMICO-B0H452LRTC",
                   {"2026-06": (141, 225, 4.1, 7), "2026-07": (176, 230, 4.1, 9), "2026-08": (214, 230, 4.0, 7), "2026-09": (188, 229, 4.0, 10)}),
}
# 同框陶瓷 / 木板（让同月同框中位价 = 价比的分母）：2025-07 至 11 只有 3 个商品在榜，中位价 250 / 246 / 230 / 241 / 239
CERAMIC_MED = {"2025-07": 250, "2025-08": 246, "2025-09": 230, "2025-10": 241, "2025-11": 239}


def seed_amazon(s, star=("2026-06", "2026-07", "2026-08", "2026-09")):
    bid = _batches(s, "amazon", MONTHS, star)
    for item, (brand, top, elem, color, listed, fam, series) in AMZ.items():
        s.add(Product(channel="amazon", item_id=item, parent=fam.split("-")[1], family_key=fam, brand=brand,
                      title=f"{brand} 30 Inch Bathroom Vanity with {top} Sink, {elem}", link=f"https://www.amazon.com/dp/{item}",
                      image_url=f"https://m.media-amazon.com/images/I/{item}._AC_SL500_.jpg", listed_at=listed))
        _tags(s, "amazon", item, top=top, elem=elem, color=color)
        for m, (u, p, r, rk) in series.items():
            s.add(Snapshot(batch_id=bid[m], channel="amazon", month=m, item_id=item, price=p, units=u, revenue=u * p, rank=rk, rating=r))
    # 陶瓷两款：一款价格等于目标中位价，一款低价
    for item, brand, listed in (("B0CK8TQ2ZD", "VEVOR", "2024-02-10"), ("B0C5W1N8RL", "Eclife", "2023-11-05")):
        s.add(Product(channel="amazon", item_id=item, family_key=f"{brand}-{item}", brand=brand, title=f"{brand} 30 inch vanity ceramic sink",
                      link=f"https://www.amazon.com/dp/{item}", listed_at=listed))
        _tags(s, "amazon", item, top="陶瓷", elem="夏克式", color="白")
        for m in MONTHS:
            if item == "B0CK8TQ2ZD":
                p = CERAMIC_MED.get(m, 249)
                u = 320
            else:
                p, u = 189.99, 280
            s.add(Snapshot(batch_id=bid[m], channel="amazon", month=m, item_id=item, price=p, units=u, revenue=u * p, rank=40, rating=4.3))
    # 木板一款（2025-12 起）
    s.add(Product(channel="amazon", item_id="B0F2LQ7M3X", family_key="HOMLUX-B0F2LQ7M3X", brand="HOMLUX", title="HOMLUX 30 inch solid wood top vanity", listed_at="2025-11-20"))
    _tags(s, "amazon", "B0F2LQ7M3X", top="木板", elem="夏克式", color="原木")
    for m in MONTHS[8:]:
        s.add(Snapshot(batch_id=bid[m], channel="amazon", month=m, item_id="B0F2LQ7M3X", price=290, units=120, revenue=120 * 290, rank=55, rating=4.3))
    return bid


HD = {"330582417": ("Glacier Bay", "GB-Rhodes-30", {"2026-04": (90, 249, 4.3, 45), "2026-05": (100, 249, 4.3, 41), "2026-08": (110, 249, 4.3, 38)}),
      "330582418": ("Glacier Bay", "GB-Rhodes-30", {"2026-04": (80, 249, 4.3, 52), "2026-05": (85, 249, 4.3, 49)}),
      "329847105": ("Home Decorators Collection", "HDC-Lark-30", {"2026-05": (60, 279, 4.4, 70), "2026-07": (70, 279, 4.4, 61)})}


def seed_other(s):
    bid = _batches(s, "homedepot", MONTHS[-6:])
    for item, (brand, series, rows) in HD.items():
        s.add(Product(channel="homedepot", item_id=item, series=series, family_key=series, brand=brand, title=f"{brand} 30 in. Vanity with Resin Top",
                      link=f"https://www.homedepot.com/p/{item}"))
        _tags(s, "homedepot", item, top="树脂", elem="农场风装饰饰条", color="白")
        for m, (u, p, r, rk) in rows.items():
            s.add(Snapshot(batch_id=bid[m], channel="homedepot", month=m, item_id=item, price=p, units=u, rank=rk, rating=r))
    # 陶瓷对照（框销量）
    s.add(Product(channel="homedepot", item_id="315207884", series="GB-Bannister", brand="Glacier Bay", title="Glacier Bay 30 in. Bannister vanity"))
    _tags(s, "homedepot", "315207884", top="陶瓷", elem="夏克式", color="白")
    for m in MONTHS[-6:]:
        s.add(Snapshot(batch_id=bid[m], channel="homedepot", month=m, item_id="315207884", price=269, units=900, rank=12, rating=4.3))
    # 评论 VP 追踪明细（F23 已采集）：同系列两商品共享一条评论
    for rid, item, stars, text, month, vp in (
            ("hd-r1", "330582417", 2, "The resin top cracked near the drain after two weeks", "2026-08", True),
            ("hd-r2", "330582417", 1, "Box arrived crushed and a door was split", "2026-07", True),
            ("hd-r2", "330582418", 1, "Box arrived crushed and a door was split", "2026-07", True),
            ("hd-r3", "330582418", 5, "Looks great, easy install", "2026-07", False),
            ("hd-r4", "329847105", 3, "Drawers hard to align, instructions unclear", "2026-06", False)):
        s.add(ChannelReview(channel="homedepot", review_id=rid, item_id=item, series=HD[item][1] if item in HD else "", month=month, vp=vp,
                            stars=stars, text=text, date=f"{month}-15"))


def seed_scores(s, valid=True):
    run = ModelRun(month="2026-09", version="第九版", newlayer={"bias": {"pred": 0.48, "actual": 0.36, "bias": 0.12, "n": 204}}, valid=valid,
                   valid_msg="D 档之后变大 19%，把握分档逐档上升" if valid else "D 档之后变大 41%，超过 30%")
    s.add(run)
    s.flush()
    s.add(UnitScore(run_id=run.id, channel="amazon", frame=FRAME, attr="台面材质", value="树脂",
                    data=dict(grasp=0.57, grade="B", share_now=0.115, pred_share=0.131, pred_lo=0.096, pred_hi=0.174, extra_units=60,
                              k_months=6, prob_raw=[0.64, 0.62], prob_adj=None, n_families=37, made_rate=5 / 6, made_p=0.11,
                              sources=dict(frame=FRAME, months="2026-04 至 2026-09", n="近 6 个月 37 个家族"))))
    s.add(UnitScore(run_id=run.id, channel="homedepot", frame=FRAME, attr="台面材质", value="树脂", data=dict(grade="C", grasp=0.44)))
    s.add(UnitScore(run_id=run.id, channel="wayfair", frame=FRAME, attr="台面材质", value="树脂", data=dict(grade="D", grasp=0.21)))
    return run


def seed_opps(s, month="2026-10"):
    """机会扫描结果（扫描组写 Opportunity.metrics）。Amazon、Home Depot 在涨，Wayfair 在跌，Lowe's 框太小。"""
    rows = [
        ("amazon", "树脂", "增长型", "经回测", dict(units=549, share=0.115, share_prev=0.084, families=37, rating=4.09, frame_rating=4.27, premium=0.86,
                                                median_price=250, newshare=0.43, frame_newshare=0.33, newfam=6, newmade=5, frame_newfam=85, frame_newmade=42, frame_units=4751)),
        ("amazon", "陶瓷", "", "经回测", dict(units=3409, share=0.717, share_prev=0.74, families=152, rating=4.29, premium=0.83, frame_units=4751)),
        ("amazon", "木板", "", "经回测", dict(units=703, share=0.148, share_prev=0.15, families=54, rating=4.29, premium=1.01, frame_units=4751)),
        ("homedepot", "树脂", "增长型", "未验证", dict(units=180, share=0.098, share_prev=0.061, families=6, frame_units=1840)),
        ("lowes", "树脂", "", "未验证", dict(units=40, share=0.041, share_prev=0.030, families=2, frame_units=140)),
        ("wayfair", "树脂", "坑", "未验证", dict(units=161, share=0.106, share_prev=0.142, families=9, frame_units=1520)),
    ]
    for ch, v, kind, ev, m in rows:
        s.add(Opportunity(month=month, channel=ch, frame=FRAME, attr="台面材质", value=v, kind=kind, evidence=ev, metrics=m))
    s.add(Opportunity(month=month, channel="amazon", frame="24″ · 拆装 · 落地式", attr="台面材质", value="树脂", kind="增长型", evidence="经回测",
                      metrics=dict(units=233, share=0.133, share_prev=0.02, families=8)))


def seed_all(valid=True):
    with session() as s:
        seed_amazon(s)
        seed_other(s)
        seed_scores(s, valid)
        seed_opps(s)


class FakeLLM:
    """假大模型：记录调用；起草返回固定文字；归类按关键词归入七类。"""
    def __init__(self):
        self.calls = []

    def complete(self, prompt, images=None, max_tokens=4096):
        self.calls.append(prompt)
        if "主要原因" in prompt:
            import json
            import re
            out = []
            for line in prompt.split("编号\t星级\t评论\n")[1].splitlines():
                rid, _, text = line.split("\t", 2)
                t = text.lower()
                reason = ("运输" if "crushed" in t or "box" in t else "本品类关键部件" if "drain" in t or "resin" in t or "sink" in t
                          else "装配 / 做工" if "align" in t or "instructions" in t or "pieces" in t else "不明")
                out.append({"id": int(rid), "reason": reason})
            return "```json\n" + json.dumps(out, ensure_ascii=False) + "\n```", 0.004
        return ("30″ 拆装落地里陶瓷一体占七成，款式同质。树脂一体把台面和盆做成一体、颜色可选，在同样的 $240 价位给出不一样的样子。"
                "（推测，待问答验证）"), 0.03


class FakeSellerSprite:
    """假卖家精灵：每个 ASIN 返回 1–5 星混合评论 40 条（验证只取 1–3 星、最多 30 条）。"""
    def __init__(self):
        self.calls = []

    def reviews(self, asin, stars=None, limit=100, **q):
        self.calls.append((asin, tuple(stars or ()), limit))
        rows = []
        texts = ["The drain hole is 1-3/4 inches, not standard", "Too many pieces, about 35 pieces", "Box arrived crushed",
                 "Particle board is soft, screws pull out", "water splashes out of basin"]
        for i in range(40):
            rows.append({"reviewId": f"{asin}-R{i:02d}", "star": (i % 5) + 1, "content": texts[i % 5], "date": f"2026-0{(i % 9) + 1}-12"})
        return rows, 1
