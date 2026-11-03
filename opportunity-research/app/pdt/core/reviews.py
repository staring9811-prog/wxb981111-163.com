"""差评拉取与归类（F22）。

- amazon_reviews：卖家精灵拉卡中 Amazon SKU 的 1–3 星评论（每个最多 30 条，AC-F22-01）；同时把卡片关联的
  Home Depot / Lowe's / Wayfair 商品在评论 VP 追踪明细（ChannelReview）里的 1–3 星评论并入同卡（AC-F22-02）；
  大模型已连接时接着归类（同一次确认）。
- review_classify：只对还没归类的评论调用大模型归类（例如先拉了差评、后来才填大模型密钥）。
- 改判：人工改归类后占比重算，记为人工修改（AC-F22-04）。
"""
import json
import re

from sqlalchemy import func, select

from .. import costgate, services
from ..db import session
from ..models import Card, CardReview, ChannelReview
from .card import REVIEW_CATS, log

MAX_PER_SKU = 30
LLM_BATCH = 20


def card_items(c: Card) -> dict:
    """卡片 SKU 层里的商品：{channel: [item_id, ...]}。"""
    out = {}
    for ch in (c.numbers or {}).get("channels", []):
        ids = [s["item_id"] for s in ch.get("skus") or []]
        if ids:
            out[ch["channel"]] = ids
    return out


def _card_id(target: str) -> int:
    return int(target.split(":")[1])


def _n_unclassified(card_id):
    with session() as s:
        return s.scalar(select(func.count()).select_from(CardReview).where(CardReview.card_id == card_id, CardReview.reason == "")) or 0


# ---------------------------------------------------------------- 拉取
def est_pull(p):
    cid = _card_id(p["target"])
    with session() as s:
        c = s.get(Card, cid)
        asins = card_items(c).get("amazon", [])
        others = sum(len(v) for k, v in card_items(c).items() if k != "amazon")
    n = len(asins)
    svcs = {"sellersprite": dict(calls=n, usd_lo=0, usd_hi=0)}
    note = f"本卡 {n} 个 Amazon SKU · 1–3 星 · 每个最多 {MAX_PER_SKU} 条；其他渠道 {others} 个商品从评论 VP 追踪明细并入（不花钱）"
    if services.connected("llm"):
        k = n * MAX_PER_SKU
        svcs["llm"] = dict(calls=max(1, -(-k // LLM_BATCH)), usd_lo=round(k * 0.0005, 2), usd_hi=round(k * 0.003, 2))
        note += f"；大模型归类最多 {k} 条"
    else:
        note += "；大模型未连接：只显示原文、不归类"
    return dict(service="sellersprite", services=svcs, calls=sum(v["calls"] for v in svcs.values()),
                usd_lo=sum(v["usd_lo"] for v in svcs.values()), usd_hi=sum(v["usd_hi"] for v in svcs.values()),
                minutes=round(1 + n * 0.2, 1), note=note)


def _norm(r: dict) -> dict:
    """卖家精灵评论字段归一（不同接口版本字段名不同）。"""
    g = lambda *ks: next((r[k] for k in ks if r.get(k) not in (None, "")), None)
    star = g("star", "stars", "rating", "score")
    return dict(review_id=str(g("reviewId", "review_id", "id") or ""), stars=float(star) if star is not None else None,
                text=str(g("content", "text", "body", "reviewText") or ""), date=str(g("date", "reviewDate", "reviewTime") or "")[:10])


def run_pull(ctx):
    cid = _card_id(ctx.target)
    with session() as s:
        c = s.get(Card, cid)
        items = card_items(c)
    ss = services.client("sellersprite")
    got = 0
    for asin in items.get("amazon", []):
        key = f"card{cid}:{asin}"
        if ctx.shard_done(key):
            continue
        ctx.allow("sellersprite", qty=1)
        rows, calls = ss.reviews(asin, stars=[1, 2, 3], limit=MAX_PER_SKU)
        ctx.charge("sellersprite", qty=calls, amount=0.0, task=f"拉差评 {asin}")
        rows = [_norm(r) for r in rows]
        rows = [r for r in rows if r["stars"] is not None and r["stars"] <= 3 and r["review_id"]][:MAX_PER_SKU]
        with session() as s:
            have = {x for (x,) in s.execute(select(CardReview.review_id).where(CardReview.card_id == cid, CardReview.channel == "amazon"))}
            for r in rows:
                if r["review_id"] not in have:
                    s.add(CardReview(card_id=cid, channel="amazon", item_id=asin, review_id=r["review_id"], stars=r["stars"], text=r["text"], date=r["date"]))
                    have.add(r["review_id"])
                    got += 1
        ctx.mark_shard(key)
        ctx.progress(done=got)
    merged = merge_other_channels(cid)
    with session() as s:
        log(s, cid, "reviews", f"拉差评：Amazon 新增 {got} 条；其他渠道从评论 VP 追踪明细并入 {merged} 条")
    if services.connected("llm"):
        classify(ctx, cid)


def merge_other_channels(cid: int) -> int:
    """卡片关联的 HD / Lowe's / Wayfair 商品：从 F23 已采集明细取 1–3 星并入同卡（AC-F22-02）。"""
    with session() as s:
        c = s.get(Card, cid)
        items = {k: v for k, v in card_items(c).items() if k != "amazon"}
        n = 0
        for ch, ids in items.items():
            have = {x for (x,) in s.execute(select(CardReview.review_id).where(CardReview.card_id == cid, CardReview.channel == ch))}
            for r in s.scalars(select(ChannelReview).where(ChannelReview.channel == ch, ChannelReview.item_id.in_(ids),
                                                           ChannelReview.stars <= 3).order_by(ChannelReview.date.desc())):
                if r.review_id in have:  # 同系列共享评论按评论 ID 去重
                    continue
                s.add(CardReview(card_id=cid, channel=ch, item_id=r.item_id, review_id=r.review_id, stars=r.stars or 0, text=r.text, date=r.date or r.month))
                have.add(r.review_id)
                n += 1
        return n


# ---------------------------------------------------------------- 归类
def _prompt(value: str, rows: list) -> str:
    cats = "、".join(REVIEW_CATS)
    lines = "\n".join(f'{r["id"]}\t{r["stars"]:.0f} 星\t{r["text"][:600]}' for r in rows)
    return (f"下面是浴室柜商品的 1–3 星差评（本品类关键部件指 {value} 这类台面 / 盆本身的问题）。"
            f"请把每条评论归入一个主要原因，只能从这七类里选：{cats}。看不出原因的归“不明”。\n"
            f"只输出 JSON 数组，每个元素形如 {{\"id\": 编号, \"reason\": \"类别\"}}，不要其他文字。\n\n编号\t星级\t评论\n{lines}")


def parse_reasons(text: str) -> dict:
    m = re.search(r"\[.*\]", text or "", re.S)
    if not m:
        return {}
    try:
        arr = json.loads(m.group(0))
    except ValueError:
        return {}
    out = {}
    for x in arr:
        if isinstance(x, dict) and "id" in x:
            r = str(x.get("reason", "")).replace("/", " / ").replace("  ", " ").strip()
            r = next((c for c in REVIEW_CATS if c.replace(" ", "") == r.replace(" ", "")), "不明")
            out[int(x["id"])] = r
    return out


def classify(ctx, cid: int):
    llm = services.client("llm")
    with session() as s:
        value = s.get(Card, cid).value
        rows = [dict(id=r.id, stars=r.stars or 0, text=r.text) for r in s.scalars(
            select(CardReview).where(CardReview.card_id == cid, CardReview.reason == "").order_by(CardReview.id))]
    done = 0
    for i in range(0, len(rows), LLM_BATCH):
        chunk = rows[i:i + LLM_BATCH]
        key = f"card{cid}:cls:{chunk[0]['id']}-{chunk[-1]['id']}"
        if ctx.shard_done(key):
            continue
        ctx.allow("llm", amount=0.0)
        text, usd = llm.complete(_prompt(value, chunk))
        ctx.charge("llm", qty=1, amount=usd, task="差评归类")
        got = parse_reasons(text)
        with session() as s:
            for r in chunk:
                cr = s.get(CardReview, r["id"])
                if cr.reason_source != "manual":
                    cr.reason = got.get(r["id"], "不明")
                    cr.reason_source = "auto"
        ctx.mark_shard(key)
        done += len(chunk)
        ctx.progress(classified=done)


def est_classify(p):
    cid = _card_id(p["target"])
    n = _n_unclassified(cid)
    return dict(service="llm", calls=max(1, -(-n // LLM_BATCH)), usd_lo=round(n * 0.0005, 2), usd_hi=round(n * 0.003, 2),
                minutes=round(0.5 + n / 60, 1), note=f"{n} 条还没归类的评论，每条归入七类之一")


def run_classify(ctx):
    cid = _card_id(ctx.target)
    merge_other_channels(cid)
    classify(ctx, cid)


costgate.register("amazon_reviews", "拉差评并归类", est_pull, run_pull)
costgate.register("review_classify", "差评归类", est_classify, run_classify)


# ---------------------------------------------------------------- 改判与统计
def set_reason(review_id: int, reason: str, user_id=None) -> int:
    if reason not in REVIEW_CATS:
        raise ValueError("归类只能是七类之一")
    with session() as s:
        r = s.get(CardReview, review_id)
        c = s.get(Card, r.card_id)
        if c.status != "draft":
            raise PermissionError("只有草稿可以改判")
        if r.reason != reason:
            old = r.reason or "未归类"
            r.reason, r.reason_source = reason, "manual"
            log(s, c.id, "edit", f"差评改判：{old} → {reason}", user_id)
        return c.id


def cat_label(cat: str, value: str) -> str:
    return f"本品类关键部件（{value}本身）" if cat == "本品类关键部件" else cat


def summary(s, card_id: int, value: str) -> dict:
    rows = list(s.scalars(select(CardReview).where(CardReview.card_id == card_id).order_by(CardReview.channel, CardReview.date.desc())))
    total = len(rows)
    classified = [r for r in rows if r.reason]
    counts = {c: sum(1 for r in classified if r.reason == c) for c in REVIEW_CATS}
    n_cls = len(classified)
    by_ch = {}
    for r in rows:
        by_ch.setdefault(r.channel, set()).add(r.item_id)
    by_sku = {}
    for r in rows:
        d = by_sku.setdefault((r.channel, r.item_id), {c: 0 for c in REVIEW_CATS} | {"n": 0})
        d["n"] += 1
        if r.reason:
            d[r.reason] += 1
    return dict(total=total, classified=n_cls, manual=sum(1 for r in rows if r.reason_source == "manual"),
                cats=[dict(cat=c, label=cat_label(c, value), n=counts[c], pct=(counts[c] / n_cls) if n_cls else None) for c in REVIEW_CATS],
                channels={k: len(v) for k, v in by_ch.items()}, by_channel_n={k: sum(1 for r in rows if r.channel == k) for k in by_ch},
                by_sku=[dict(channel=k[0], item_id=k[1], **v) for k, v in by_sku.items()],
                items=[dict(id=r.id, channel=r.channel, item_id=r.item_id, stars=r.stars, text=r.text, date=r.date, reason=r.reason,
                            manual=r.reason_source == "manual") for r in rows])
