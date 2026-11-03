"""利润测算 · AI 识别任意格式报价单（服务端）。

浏览器不直连大模型、不存 API Key（NFR-008、AC-F16-05）：页面把报价单文字（原工具 sheetText 的产物）或截图交给服务端，
服务端用设置页所选大模型（services.client("llm")），经费用闸门 profit_ai_quote 先估算、确认后才识别，费用记入同一费用记录。
提示词 PROMPT 与原工具 tools/利润测算台/index.html 的 aiPrompt 逐字相同（测试核对）。
PDF：组 A 的大模型客户端 complete(prompt, images) 只接收文字和图片，PDF 请截图或另存为 Excel。
"""
import base64
import json
import secrets

from .. import costgate, services
from ..config import data_dir

PROMPT = ('你是外贸采购助理。下面是一份工厂报价单，格式不固定（可能有多个工作表、合并单元格、中英文混排、一个产品占多行、多包裹）。请提取每个产品的报价信息。\n'
    '\n'
    '只输出一个 JSON 对象，不要任何解释文字。格式：\n'
    '{{"factory":"工厂名，找不到就空字符串","quote_date":"YYYY-MM-DD，找不到就空字符串","items":[{{"name":"型号或品名","desc":"材质/颜色/配置，简短","match_key":"规格键","price":数字或null,"price_currency":"USD 或 RMB","price_tax":"FOB 或 含税 或 未税","price_rmb_tax":数字或null,"moq":数字或null,"packages":[{{"l":数字,"w":数字,"h":数字,"dim_unit":"cm 或 mm 或 in","weight":数字或null,"weight_unit":"kg 或 lb"}}],"notes":"拿不准的地方，没有就空字符串"}}]}}\n'
    '\n'
    '规则：\n'
    '1. packages 用外箱/纸箱/包装尺寸和毛重，不要用产品本身尺寸或净重；一个产品分几个箱子就列几个 package。\n'
    '2. price 填 FOB 美元价；price_rmb_tax 填人民币含税价（国内交货/出厂含税价），两者都有就都填。只有人民币未税价时，填在 price 并标 price_currency 为 RMB、price_tax 为未税。看不出含税与否时按含税处理并在 notes 说明。\n'
    '3. 同一型号只是颜色不同、价格和包装都相同，合并成一条，颜色写进 desc。\n'
    '4. match_key 用于跨工厂对比同一规格，格式如“30寸 落地式”“24寸 单盆”：尺寸写成“数字+寸”，再加最能区分款式的一两个词。{keys}\n'
    '5. 不要编造：表里没有的数填 null，并在 notes 说明。\n'
    '\n'
    '报价单内容：\n')


def ai_prompt(body: str, keys: list) -> str:
    """与原工具 aiPrompt(body) 相同：keys = 报价库里已有的对比键（最多 80 个）。"""
    keys = [k for k in dict.fromkeys(keys or []) if k][:80]
    return PROMPT.format(keys=("已有这些规格键，同规格请原样复用：" + "、".join(keys)) if keys else "") + body


def _dir():
    d = data_dir() / "profit_ai"
    d.mkdir(parents=True, exist_ok=True)
    return d


def prepare(payload: dict) -> str:
    kind = payload.get("kind")
    if kind not in ("text", "image"):
        raise ValueError("只支持报价单文字（Excel / CSV）或截图；PDF 请截图或另存为 Excel")
    if kind == "text" and not (payload.get("text") or "").strip():
        raise ValueError("报价单是空的")
    if kind == "image":
        base64.b64decode(payload.get("data") or "", validate=True)
    tok = secrets.token_hex(8)
    rec = dict(kind=kind, name=payload.get("name", ""), keys=list(payload.get("keys") or [])[:80], text=payload.get("text", ""),
               data=payload.get("data", ""), media_type=payload.get("media_type") or "image/png", status="prepared")
    (_dir() / f"{tok}.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    return tok


def load(tok: str) -> dict:
    if not tok.isalnum():
        raise FileNotFoundError(tok)
    return json.loads((_dir() / f"{tok}.json").read_text(encoding="utf-8"))


def _save(tok, rec):
    (_dir() / f"{tok}.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")


def parse_loose(t: str):
    """与原工具 parseLoose 相同：先整体解析，不行取第一个 { 到最后一个 }。"""
    try:
        return json.loads(t)
    except ValueError:
        pass
    a, b = t.find("{"), t.rfind("}")
    if a >= 0 and b > a:
        try:
            return json.loads(t[a:b + 1])
        except ValueError:
            pass
    raise ValueError("AI 返回的不是有效 JSON")


def _estimate(p):
    rec = load(p["target"].split(":", 1)[1])
    chars = len(ai_prompt(rec["text"] if rec["kind"] == "text" else "（见附带的报价单图片）", rec["keys"]))
    tin = chars / 1.5 + (1600 if rec["kind"] == "image" else 0)  # 中文约 1.5 字 / token；图片约 1,600 tokens
    lo = (tin * 4 + 2000 * 20) / 1e6
    hi = (tin * 5 + 16000 * 25) / 1e6
    return dict(service="llm", calls=1, usd_lo=round(lo, 3), usd_hi=round(hi, 3), minutes=round(0.5 + tin / 20000, 1),
                note=f"识别报价单“{rec['name']}”：约 {int(tin):,} tokens 输入，最多 16,000 tokens 输出（按所选模型实际计费）")


def _run(ctx):
    tok = ctx.target.split(":", 1)[1]
    rec = load(tok)
    llm = services.client("llm")
    ctx.allow("llm", amount=0.0)
    if rec["kind"] == "image":
        prompt = ai_prompt("（见附带的报价单图片）", rec["keys"])
        text, usd = llm.complete(prompt, images=[(base64.b64decode(rec["data"]), rec["media_type"])], max_tokens=16000)
    else:
        text, usd = llm.complete(ai_prompt(rec["text"], rec["keys"]), max_tokens=16000)
    ctx.charge("llm", qty=1, amount=usd, task=f"AI 识别报价单 {rec['name']}")
    try:
        rec.update(status="done", out=parse_loose(text or ""))
    except ValueError as e:
        rec.update(status="failed", code="invalid_json", error=str(e))
    rec.pop("data", None)
    _save(tok, rec)


costgate.register("profit_ai_quote", "AI 识别报价单", _estimate, _run)
