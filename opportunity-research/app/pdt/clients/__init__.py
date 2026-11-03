"""外部服务真实客户端（卖家精灵 / Bright Data / Apify / 大模型）。

入口 `make(slot, key, llm_settings)`，由 services.client() 调用；业务代码不要直接 import 本模块。
统一约定：
- `test()` 做最小只读请求，返回 (status, msg)，status ∈ ok / auth / network / quota / error，不抛异常；
- 其他方法失败时抛 ServiceError(status, msg)，status 同上；
- 异常信息、日志、返回值里都不带密钥（NFR-008）：错误信息只用固定中文文案和 HTTP 状态码，不转述服务端原文。
测试可把 TRANSPORT 设为 httpx2.MockTransport，所有 HTTP 请求（含两个大模型 SDK）都会经过它。
"""
import base64
import time
import urllib.parse

import httpx2 as httpx  # 与 anthropic / openai SDK 同用 httpx2，测试注入的 MockTransport 才能覆盖全部请求

TRANSPORT: httpx.BaseTransport | None = None  # 测试注入

MSG = {
    "ok": "可用",
    "auth": "密钥无效或已被撤销，请更换",
    "network": "连接超时，请确认运行机能访问外网",
    "quota": "账户额度不足，请到服务商后台充值",
}


class ServiceError(Exception):
    def __init__(self, status: str, msg: str = ""):
        self.status = status
        self.msg = msg or MSG.get(status, "调用失败")
        super().__init__(f"{status}: {self.msg}")


def _status_of(code: int) -> str:
    if code in (401, 403):
        return "auth"
    if code in (402, 429):
        return "quota"
    return "error"


def _http_client(timeout=60.0) -> httpx.Client:
    return httpx.Client(transport=TRANSPORT, timeout=timeout) if TRANSPORT else httpx.Client(timeout=timeout)


class _Http:
    """带鉴权头的 HTTP 调用；把网络异常、401/403、402/429 映射成 network / auth / quota。"""

    def __init__(self, base_url: str, headers: dict, timeout=60.0):
        self.base_url = base_url.rstrip("/")
        self.headers = headers
        self.timeout = timeout

    def request(self, method: str, path: str, **kw) -> httpx.Response:
        url = path if path.startswith("http") else self.base_url + path
        try:
            with _http_client(kw.pop("timeout", self.timeout)) as c:
                r = c.request(method, url, headers=self.headers, **kw)
        except httpx.TimeoutException:
            raise ServiceError("network") from None
        except httpx.TransportError:
            raise ServiceError("network") from None
        if r.status_code >= 400 and r.status_code != 202:
            st = _status_of(r.status_code)
            raise ServiceError(st, MSG.get(st) or f"服务返回 HTTP {r.status_code}")
        return r


def _safe_test(fn):
    try:
        fn()
        return "ok", MSG["ok"]
    except ServiceError as e:
        return e.status, e.msg


# ---------------------------------------------------------------- 卖家精灵
# 本会话里卖家精灵是通过 MCP 用的，仓库里没有现成的 HTTP 调用。下面的地址、鉴权头和路径是按卖家精灵开放平台的常见用法
# 预置的默认值，可在 Setting "sellersprite_api" 中改；需要 wen 提供接口文档后核对。
SELLERSPRITE_DEFAULT = {
    "base_url": "https://api.sellersprite.com",
    "header": "secret-key",
    "test_path": "/v1/visits",              # 最小只读请求：查询本账户访问额度
    "product_path": "/v1/product/research",  # 选产品 / 类目月度数据
    "review_path": "/v1/review",             # 商品评论
    "page_size": 100,
}


class SellerSprite:
    service = "sellersprite"

    def __init__(self, key: str, cfg: dict | None = None):
        self.cfg = dict(SELLERSPRITE_DEFAULT, **(cfg or {}))
        self.http = _Http(self.cfg["base_url"], {self.cfg["header"]: key, "Content-Type": "application/json"})

    def _call(self, method: str, path: str, body: dict | None = None):
        r = self.http.request(method, path, json=body) if body is not None else self.http.request(method, path)
        try:
            j = r.json()
        except ValueError:
            raise ServiceError("error", "卖家精灵返回的不是 JSON") from None
        code = str(j.get("code", "OK")) if isinstance(j, dict) else "OK"
        if code.upper() not in ("OK", "200", "0", "SUCCESS"):
            u = code.upper()
            if "AUTH" in u or "KEY" in u or "TOKEN" in u or "SIGN" in u:
                raise ServiceError("auth")
            if "VISIT" in u or "QUOTA" in u or "LIMIT" in u or "BALANCE" in u:
                raise ServiceError("quota")
            raise ServiceError("error", f"卖家精灵返回错误码 {code}")
        return j.get("data") if isinstance(j, dict) else j

    def test(self):
        return _safe_test(lambda: self._call("GET", self.cfg["test_path"]))

    def product_month(self, month: str, page: int, **query):
        """按月拉一页类目商品数据。返回 (rows, cost_calls)；一次请求计 1 次调用。"""
        body = dict(query, month=month.replace("-", ""), page=page, size=self.cfg["page_size"])
        data = self._call("POST", self.cfg["product_path"], body)
        rows = (data or {}).get("items", data) if isinstance(data, dict) else (data or [])
        return list(rows or []), 1

    def reviews(self, asin: str, stars=None, limit: int = 100, **query):
        """拉一个 ASIN 的评论。返回 (rows, cost_calls)。"""
        body = dict(query, asin=asin, size=limit)
        if stars:
            body["stars"] = list(stars)
        data = self._call("POST", self.cfg["review_path"], body)
        rows = (data or {}).get("items", data) if isinstance(data, dict) else (data or [])
        return list(rows or []), 1


# ---------------------------------------------------------------- Bright Data（Web Unlocker 异步接口，沿用 reviewkit 的调用方式）
BD_API = "https://api.brightdata.com"
BD_PRICE = 1.5 / 1000  # 每次成功请求美元


class BrightData:
    service = "brightdata"
    price_per_request = BD_PRICE

    def __init__(self, key: str, cfg: dict | None = None):
        cfg = cfg or {}
        self.customer = cfg.get("customer", "")
        self.zone = cfg.get("zone", "mcp_unlocker")
        self.http = _Http(BD_API, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})

    def test(self):
        # 最小只读请求：查询账户余额
        def go():
            r = self.http.request("GET", "/customer/balance")
            try:
                bal = r.json().get("balance")
            except (ValueError, AttributeError):
                bal = None
            if isinstance(bal, (int, float)) and bal <= 0:
                raise ServiceError("quota")
        return _safe_test(go)

    def fetch(self, url: str, poll: float = 15, max_wait: float = 1200):
        """提交一个页面抓取并等待结果。返回 (目标站状态码, 页面字节)。"""
        q = {"zone": self.zone}
        if self.customer:
            q["customer"] = self.customer
        r = self.http.request("POST", "/unblocker/req?" + urllib.parse.urlencode(q), json={"url": url, "country": "us"})
        rid = r.json()["response_id"]
        q["response_id"] = rid
        t0 = time.time()
        while time.time() - t0 < max_wait:
            r = self.http.request("GET", "/unblocker/get_result?" + urllib.parse.urlencode(q))
            if r.status_code == 200:
                return int(r.headers.get("x-brd-status-code", 200) or 200), r.content
            time.sleep(poll)
        return 504, b"timeout"


# ---------------------------------------------------------------- Apify（沿用 reviewkit 的调用方式）
APIFY = "https://api.apify.com/v2"


class Apify:
    service = "apify"

    def __init__(self, key: str, cfg: dict | None = None):
        self.http = _Http(APIFY, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=120)

    def test(self):
        return _safe_test(lambda: self.http.request("GET", "/users/me"))

    def run(self, actor: str, run_input: dict, max_charge_usd: float = 3, timeout_s: int = 3600, poll: float = 20):
        """运行一个 Actor 并取回全部结果。返回 (items, usd)。"""
        act = actor.replace("/", "~")
        r = self.http.request("POST", f"/acts/{act}/runs?timeout={timeout_s}&maxTotalChargeUsd={max_charge_usd:.2f}", json=run_input)
        run = r.json()["data"]
        while run.get("status") in ("READY", "RUNNING", "TIMING-OUT", "ABORTING"):
            time.sleep(poll)
            run = self.http.request("GET", f"/actor-runs/{run['id']}").json()["data"]
        items, off = [], 0
        while True:
            page = self.http.request("GET", f"/datasets/{run['defaultDatasetId']}/items?format=json&offset={off}&limit=1000").json()
            if not isinstance(page, list) or not page:
                break
            items += page
            off += len(page)
            if len(page) < 1000:
                break
        if run.get("status") != "SUCCEEDED" and not items:
            raise ServiceError("error", f"Apify 任务结束状态 {run.get('status')}")
        return items, float(run.get("usageTotalUsd") or 0)


# ---------------------------------------------------------------- 大模型
# 每百万 token 美元（输入, 输出）。用于按 usage 估算费用；未列出的模型按默认模型价格估算。
CLAUDE_DEFAULT_MODEL = "claude-opus-5-5"
CLAUDE_PRICES = {
    "claude-fable-5-1": (10.0, 50.0), "claude-fable-5": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0), "claude-opus-5": (5.0, 25.0), "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0), "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0), "claude-sonnet-5": (2.0, 10.0), "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-5-5": (0.10, 0.50), "claude-haiku-4-5": (1.0, 5.0),
}
OPENAI_DEFAULT_MODEL = "gpt-4o"
OPENAI_DEFAULT_PRICE = (2.5, 10.0)


def _usd(tokens_in, tokens_out, price) -> float:
    return round((tokens_in or 0) / 1e6 * price[0] + (tokens_out or 0) / 1e6 * price[1], 6)


def _image_parts(images):
    """images：URL 字符串，或图片字节，或 (字节, media_type)。返回 [(kind, url_or_b64, media_type)]。"""
    out = []
    for im in images or []:
        if isinstance(im, str):
            out.append(("url", im, ""))
            continue
        data, mt = (im if isinstance(im, tuple) else (im, ""))
        if not mt:
            mt = "image/png" if data[:4] == b"\x89PNG" else "image/webp" if data[8:12] == b"WEBP" else "image/jpeg"
        out.append(("base64", base64.standard_b64encode(data).decode(), mt))
    return out


def _map_sdk_error(sdk, e) -> ServiceError:
    if isinstance(e, (sdk.AuthenticationError, sdk.PermissionDeniedError)):
        return ServiceError("auth")
    if isinstance(e, sdk.RateLimitError):
        return ServiceError("quota")
    if isinstance(e, sdk.APIConnectionError):  # 含超时
        return ServiceError("network")
    if isinstance(e, sdk.APIStatusError):
        st = _status_of(e.status_code)
        return ServiceError(st, MSG.get(st) or f"服务返回 HTTP {e.status_code}")
    return ServiceError("error", f"调用失败（{type(e).__name__}）")


class ClaudeLLM:
    service = "llm"
    provider = "claude"

    def __init__(self, key: str, cfg: dict | None = None):
        import anthropic
        cfg = cfg or {}
        self.sdk = anthropic
        self.model = cfg.get("model") or CLAUDE_DEFAULT_MODEL
        self.base_url = cfg.get("base_url") or None
        kw = dict(api_key=key, max_retries=1)
        if TRANSPORT:
            kw["http_client"] = _http_client(600)
        if self.base_url:
            kw["base_url"] = self.base_url
        self.client = anthropic.Anthropic(**kw)

    def test(self):
        def go():
            try:
                self.client.models.list(limit=1)
            except self.sdk.APIError as e:
                raise _map_sdk_error(self.sdk, e) from None
        return _safe_test(go)

    def complete(self, prompt: str, images=None, max_tokens: int = 4096):
        content = []
        for kind, v, mt in _image_parts(images):
            src = {"type": "url", "url": v} if kind == "url" else {"type": "base64", "media_type": mt, "data": v}
            content.append({"type": "image", "source": src})
        content.append({"type": "text", "text": prompt})
        try:
            msg = self.client.messages.create(model=self.model, max_tokens=max_tokens,
                                              messages=[{"role": "user", "content": content}])
        except self.sdk.APIError as e:
            raise _map_sdk_error(self.sdk, e) from None
        u = msg.usage
        usd = _usd(u.input_tokens + (getattr(u, "cache_read_input_tokens", 0) or 0), u.output_tokens,
                   CLAUDE_PRICES.get(self.model, CLAUDE_PRICES[CLAUDE_DEFAULT_MODEL]))
        if msg.stop_reason == "refusal":
            raise ServiceError("error", "大模型拒绝了这次请求")
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return text, usd


class OpenAILLM:
    """OpenAI 及兼容接口（可填 base_url）。"""
    service = "llm"
    provider = "openai"

    def __init__(self, key: str, cfg: dict | None = None):
        import openai
        cfg = cfg or {}
        self.sdk = openai
        self.model = cfg.get("model") or OPENAI_DEFAULT_MODEL
        try:
            self.price = (float(cfg["price_in"]), float(cfg["price_out"]))
        except (KeyError, TypeError, ValueError):
            self.price = OPENAI_DEFAULT_PRICE
        kw = dict(api_key=key, max_retries=1)
        if TRANSPORT:
            kw["http_client"] = _http_client(600)
        if cfg.get("base_url"):
            kw["base_url"] = cfg["base_url"]
        self.client = openai.OpenAI(**kw)

    def test(self):
        def go():
            try:
                self.client.models.list()
            except self.sdk.APIError as e:
                raise _map_sdk_error(self.sdk, e) from None
        return _safe_test(go)

    def complete(self, prompt: str, images=None, max_tokens: int = 4096):
        content = [{"type": "text", "text": prompt}]
        for kind, v, mt in _image_parts(images):
            url = v if kind == "url" else f"data:{mt};base64,{v}"
            content.append({"type": "image_url", "image_url": {"url": url}})
        try:
            r = self.client.chat.completions.create(model=self.model, max_tokens=max_tokens,
                                                    messages=[{"role": "user", "content": content}])
        except self.sdk.APIError as e:
            raise _map_sdk_error(self.sdk, e) from None
        u = r.usage
        usd = _usd(getattr(u, "prompt_tokens", 0), getattr(u, "completion_tokens", 0), self.price) if u else 0.0
        return r.choices[0].message.content or "", usd


def make(slot: str, key: str, llm_settings: dict | None = None):
    """slot ∈ sellersprite / brightdata / apify / llm_claude / llm_openai。"""
    from ..services import get_setting
    llm_settings = llm_settings or {}
    if slot == "sellersprite":
        return SellerSprite(key, get_setting("sellersprite_api", {}) or {})
    if slot == "brightdata":
        return BrightData(key, get_setting("brightdata_api", {}) or {})
    if slot == "apify":
        return Apify(key)
    if slot == "llm_claude":
        return ClaudeLLM(key, llm_settings.get("claude") or {})
    if slot == "llm_openai":
        return OpenAILLM(key, llm_settings.get("openai") or {})
    raise ValueError(f"未知服务 {slot}")


__all__ = ["make", "ServiceError", "TRANSPORT"]
