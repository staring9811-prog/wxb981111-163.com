"""密钥与大模型、预算与费用记录（PAGE-F16-01 / F16-02）：FLOW-02、FLOW-03、RULE-02、DEC-104，以及真实客户端的错误映射。"""
import io
import logging
import re

import httpx2 as httpx
import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from pdt import clients, costgate, services
from pdt.config import data_dir
from pdt.db import session
from pdt.models import Budget, CostRecord, Job, Secret

# 真实格式的密钥（随机生成的样例，不是任何真实账户的密钥）
KEYS = {
    "sellersprite": "ss8f3a1c9e27b54d0fa6c2e8b1d4f7a903",
    "brightdata": "b7e94c2a1f0d8e6b3c5a7f9d2e4b6c8a0f1e3d5c7b9a2e4f6d8c0b1a3e5f7d9c",
    "apify": "apify_api_Q7mLx2pR9sT4vW8yZ1cD3fG5hJ6kN0bV",
    "llm_claude": "sk-ant-api03-Zp4Kq8Rw2Tx6Vy0Bc3Df7Gh1Jk5Lm9Np2Qr6St0Uv4Wx8Yz-AbCdEfGh",
    "llm_openai": "sk-proj-Hn5Jk9Lm3Np7Qr1St5Uv9Wx3Yz7Ab1Cd5Ef9Gh3Ij7Kl1Mn5Op9Qr3",
}


class 假服务:
    """可替换的假外部服务：记录调用次数，测试结果按 status 返回。"""

    def __init__(self, status="ok"):
        self.status = status
        self.calls = []

    def test(self):
        self.calls.append("test")
        return self.status, {"ok": "可用", "auth": "密钥无效或已被撤销，请更换", "network": "连接超时，请确认运行机能访问外网",
                             "quota": "账户额度不足，请到服务商后台充值"}.get(self.status, "调用失败")

    def complete(self, prompt, images=None):
        self.calls.append(("complete", prompt))
        return "落地式", 0.01


@pytest.fixture()
def fakes():
    f = {n: 假服务() for n in ("sellersprite", "brightdata", "apify", "llm")}
    for n, o in f.items():
        services.set_fake(n, o)
    return f


@pytest.fixture()
def mock_http():
    """拦截真实客户端的所有 HTTP 请求（含两个大模型 SDK），记录请求，按路由返回。"""
    seen, routes = [], {}

    def handler(req: httpx.Request):
        seen.append(req)
        for pat, resp in routes.items():
            if re.search(pat, str(req.url)):
                if isinstance(resp, Exception):
                    raise resp
                return resp(req) if callable(resp) else resp
        return httpx.Response(200, json={})

    clients.TRANSPORT = httpx.MockTransport(handler)
    yield seen, routes
    clients.TRANSPORT = None


def _save(wen, slot, value=None):
    return wen.post(f"/settings/keys/{slot}", data={"value": value or KEYS[slot]}, follow_redirects=True)


def test_flow02_keys_mask_test_replace_delete(wen, fakes, mock_http):
    """FLOW-02：保存四类密钥只显示后 4 位；测试结果显示 可用 / 认证失败 / 网络 / 额度；更换后下一次调用用新密钥；删除 Apify 后显示未连接且不发起调用。"""
    for slot in ("sellersprite", "brightdata", "apify", "llm_claude"):
        page = _save(wen, slot).text
        assert "••••" + KEYS[slot][-4:] in page and KEYS[slot] not in page
    page = wen.get("/settings/keys").text
    assert page.count("可用") >= 4

    fakes["brightdata"].status, fakes["apify"].status, fakes["sellersprite"].status = "auth", "network", "quota"
    for slot, word in (("brightdata", "认证失败"), ("apify", "网络"), ("sellersprite", "额度"), ("llm_claude", "可用")):
        r = wen.post(f"/settings/keys/{slot}/test", follow_redirects=True)
        assert word in r.text
    with session() as s:
        assert {r.slot: r.test_status for r in s.scalars(select(Secret))} == {
            "sellersprite": "quota", "brightdata": "auth", "apify": "network", "llm_claude": "ok"}
    page = wen.get("/settings/keys").text
    for word in ("认证失败", "网络", "额度"):
        assert f'<div class="banner__title">{word}</div>' in page

    # 更换 Bright Data：用真实客户端（HTTP 被拦截）确认之后的调用带新密钥
    new_bd = "c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2"
    page = _save(wen, "brightdata", new_bd).text
    assert "••••c1d2" in page and "••••" + KEYS["brightdata"][-4:] not in page
    services.clear_fakes()
    seen, routes = mock_http
    routes[r"/customer/balance"] = httpx.Response(200, json={"balance": 12.5})
    assert services.client("brightdata").test() == ("ok", "可用")
    assert seen[-1].headers["authorization"] == f"Bearer {new_bd}"

    # 删除 Apify：依赖功能“未连接”，假服务收不到调用
    apify = 假服务()
    services.set_fake("apify", apify)
    wen.post("/settings/keys/apify/delete")
    with pytest.raises(services.NotConnected):
        services.client("apify")
    assert apify.calls == []
    assert "未连接" in wen.get("/settings/keys").text


def test_flow02_llm_provider_switch(wen, mock_http):
    """FLOW-02：大模型先 Claude 再切换 OpenAI；切换后看图打标、差评归类、叙述草稿三类调用都发往 OpenAI（OpenAI 兼容地址与模型名生效）。"""
    seen, routes = mock_http
    routes[r"/v1/models"] = httpx.Response(200, json={"data": [], "object": "list", "has_more": False, "first_id": None, "last_id": None})
    routes[r"/chat/completions"] = httpx.Response(200, json={
        "id": "c1", "object": "chat.completion", "created": 0, "model": "qwen-vl-max",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "竖棱"}}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200}})
    _save(wen, "llm_claude")
    assert isinstance(services.client("llm"), clients.ClaudeLLM)
    _save(wen, "llm_openai")
    r = wen.post("/settings/llm", data=dict(provider="openai", openai_base_url="https://dashscope.example.cn/compatible-mode/v1",
                                            openai_model="qwen-vl-max", openai_price_in="2", openai_price_out="6"), follow_redirects=True)
    assert "大模型提供方已改为 OpenAI" in r.text
    seen.clear()
    for prompt in ("看图打元素：这张浴室柜主图属于哪种元素？", "差评归类：Top cracked after two weeks", "叙述草稿：30″ · 拆装 · 落地式｜台面材质 = 岗石"):
        text, usd = services.client("llm").complete(prompt, images=[b"\x89PNG\r\n\x1a\n" + b"0" * 16] if "看图" in prompt else None)
        assert text == "竖棱" and usd == pytest.approx(1000 / 1e6 * 2 + 200 / 1e6 * 6)
    assert len(seen) == 3
    assert all(str(q.url).startswith("https://dashscope.example.cn/compatible-mode/v1/chat/completions") for q in seen)
    assert all(q.headers["authorization"] == f"Bearer {KEYS['llm_openai']}" for q in seen)
    assert b'"model":"qwen-vl-max"' in seen[0].content.replace(b" ", b"")


@pytest.mark.parametrize("resp,status", [
    (httpx.Response(401, json={"error": "invalid key"}), "auth"),
    (httpx.Response(403, json={"error": "forbidden"}), "auth"),
    (httpx.Response(429, json={"error": "rate"}), "quota"),
    (httpx.Response(402, json={"error": "billing"}), "quota"),
    (httpx.ConnectError("connection refused"), "network"),
    (httpx.ReadTimeout("timeout"), "network"),
])
def test_real_clients_error_mapping(resp, status, app_env, mock_http):
    """FLOW-02 / AC-F16-02：真实客户端把 401/403、402/429、网络异常分别映射为 认证失败 / 额度 / 网络，信息中不含密钥。"""
    seen, routes = mock_http
    routes["."] = resp
    for slot in ("sellersprite", "brightdata", "apify", "llm_claude", "llm_openai"):
        c = clients.make(slot, KEYS[slot], {})
        st, msg = c.test()
        assert st == status, (slot, st, msg)
        assert KEYS[slot] not in msg


# ---------------------------------------------------------------- FLOW-03
FLOW03 = {}


def _register_fake_kinds():
    """四类花钱任务（拉数据、采评论、打标、归类）的假任务：只通过 services.client 调用假服务，并逐笔记账。"""
    spec = {"测试_拉数据": ("sellersprite", 3, 0.01), "测试_采评论": ("apify", 2, 0.35),
            "测试_打标": ("llm", 4, 0.03), "测试_归类": ("llm", 2, 0.02)}
    for kind, (svc, n, price) in spec.items():
        def est(p, svc=svc, n=n, price=price):
            return dict(service=svc, calls=n, usd_lo=round(n * price * 0.9, 4), usd_hi=round(n * price * 1.1, 4), minutes=n * 0.5,
                        note=f"{n} 个分片")

        def run(ctx, svc=svc, n=n, price=price, kind=kind):
            for i in range(n):
                ctx.allow(svc, amount=price, qty=1)
                FLOW03.setdefault(kind, []).append(services.client(svc).test())
                ctx.charge(svc, qty=1, amount=price, task=f"{kind} · 分片{i + 1}")
        costgate.register(kind, kind, est, run)
    return spec


def test_flow03_estimate_cancel_confirm_ledger(wen, fakes):
    """FLOW-03：四类花钱任务都先估算弹窗（调用量 / 费用区间 / 耗时）；取消后假服务调用 0；确认后逐笔记账，按月汇总 = 明细之和。"""
    for slot in ("sellersprite", "apify", "llm_claude"):
        _save(wen, slot)
    for f in fakes.values():
        f.calls.clear()
    FLOW03.clear()
    spec = _register_fake_kinds()
    page = wen.get("/settings/budget").text
    assert 'id="cmp-f16-01"' in page and "确认费用后开始" in page and "确认并开始" in page

    for kind, (svc, n, price) in spec.items():
        j = wen.post("/jobs/estimate", data={"kind": kind, "month": "2026-10"}).json()
        assert j["status"] == "estimated" and j["estimate"]["calls"] == n and j["estimate"]["usd_hi"] > 0 and j["estimate"]["minutes"] > 0
        wen.post(f"/jobs/{j['id']}/cancel")
    assert all(f.calls == [] for f in fakes.values()) and FLOW03 == {}
    with session() as s:
        assert s.query(CostRecord).count() == 0

    for kind, (svc, n, price) in spec.items():
        j = wen.post("/jobs/estimate", data={"kind": kind, "month": "2026-10"}).json()
        j = wen.post(f"/jobs/{j['id']}/confirm").json()
        assert j["status"] == "done"
        assert len(FLOW03[kind]) == n
    led = wen.get("/settings/ledger").json()
    assert len(led["detail"]) == sum(n for _, n, _ in spec.values())
    assert {r["task"].split(" · ")[0] for r in led["detail"]} == set(spec)
    assert all(r["at"] and r["service"] and r["qty"] == 1 for r in led["detail"])
    expected = sum(n * price for _, n, price in spec.values())
    month = costgate.month_key()
    m = next(r for r in led["monthly"] if r["month"] == month)
    assert m["total"] == pytest.approx(expected) == pytest.approx(sum(r["amount"] for r in led["detail"]))
    assert m["services"]["llm"] == pytest.approx(4 * 0.03 + 2 * 0.02)

    page = wen.get("/settings/budget?tab=month").text
    assert f"${expected:,.2f}" in page
    ws = load_workbook(io.BytesIO(wen.get("/settings/ledger/export?view=month").content)).active
    rows = list(ws.iter_rows(values_only=True))
    assert rows[1][0] == month and rows[1][-1] == pytest.approx(expected)
    ws = load_workbook(io.BytesIO(wen.get(f"/settings/ledger/export?view=detail&month={month}").content)).active
    assert ws.max_row - 1 == len(led["detail"])


def test_demo_preview_makes_no_calls(wen, fakes):
    """预算页“预览费用评估弹窗”演示任务：确认后不调用任何服务、不记账。"""
    j = wen.post("/jobs/estimate", data={"kind": "cost_demo", "month": costgate.month_key()}).json()
    assert j["estimate"]["usd_hi"] == 0
    assert wen.post(f"/jobs/{j['id']}/confirm").json()["status"] == "done"
    assert all(f.calls == [] for f in fakes.values())
    with session() as s:
        assert s.query(CostRecord).count() == 0


def test_budget_caps_and_status_dec104(wen, fakes):
    """DEC-104 / AC-F16-06：保存上限（卖家精灵按次数、其余按美元）；≥ 80% 接近上限，≥ 100% 已达上限；非法上限被拦截。"""
    for slot in ("sellersprite", "brightdata", "apify", "llm_claude"):
        _save(wen, slot)
    r = wen.post("/settings/budget", data=dict(cap_sellersprite="5000", unit_sellersprite="calls", cap_brightdata="80", unit_brightdata="usd",
                                               cap_apify="10", unit_apify="usd", cap_llm="50", unit_llm="usd"), follow_redirects=True)
    assert "已保存上限" in r.text
    with session() as s:
        assert (s.get(Budget, "sellersprite").cap, s.get(Budget, "sellersprite").unit) == (5000, "calls")
        m = costgate.month_key()
        s.add_all([CostRecord(month=m, service="sellersprite", task="拉取 Amazon 2026-10", qty=3120, amount=31.2),
                   CostRecord(month=m, service="brightdata", task="评论 VP 追踪 · Wayfair 页面 2026-10", qty=250, amount=65.6),
                   CostRecord(month=m, service="apify", task="评论 VP 追踪 · Lowe's 评论 2026-10", qty=6480, amount=10.0),
                   CostRecord(month=m, service="llm", task="看图打元素 · 2026-10 其他渠道新商品", qty=412, amount=18.75)])
    page = wen.get("/settings/budget").text
    row = {svc: page.split(f'data-svc="{svc}"')[1].split("</tr>")[0] for svc in ("sellersprite", "brightdata", "apify", "llm")}
    assert "62%" in row["sellersprite"] and "正常" in row["sellersprite"] and "3,120 次" in row["sellersprite"]
    assert "82%" in row["brightdata"] and "接近上限" in row["brightdata"] and "meter--warn" in row["brightdata"]
    assert "100%" in row["apify"] and "已达上限，已停止新调用" in row["apify"]
    assert "38%" in row["llm"] and "正常" in row["llm"]
    home = wen.get("/").text
    assert "$65.60 / $80.00" in home and "接近上限" in home and "已达上限，已停止新调用" in home

    assert "请填写大于 0 的上限" in wen.post("/settings/budget", data=dict(cap_apify="0", unit_apify="usd"), follow_redirects=True).text
    assert "调用次数需为整数" in wen.post("/settings/budget", data=dict(cap_sellersprite="12.5", unit_sellersprite="calls"),
                                         follow_redirects=True).text
    r = wen.post("/settings/budget", data=dict(cap_brightdata="60", unit_brightdata="usd"), follow_redirects=True)
    assert "已立即停止其新调用" in r.text
    with pytest.raises(costgate.CapReached):
        costgate.check("brightdata", amount=0.01)


# ---------------------------------------------------------------- RULE-02
def test_rule02_keys_never_leak(app_env, wen, mock_http, caplog, capsys):
    """RULE-02：保存四类（五个槽位）真实格式密钥，执行测试、更换、制造外部报错、导出 Excel 后，
    数据库明文、data 目录文件、日志输出、页面 HTML、接口响应与源码中完整密钥出现 0 次；数据库只有加密值。"""
    caplog.set_level(logging.DEBUG)
    seen, routes = mock_http
    routes["."] = httpx.Response(401, json={"error": {"message": "invalid x-api-key"}})  # 每个测试都制造一次外部认证报错
    bodies = []
    for slot in KEYS:
        r = _save(wen, slot)
        bodies.append(r.text)
        r = wen.post(f"/settings/keys/{slot}/test", headers={"accept": "application/json"})
        bodies.append(r.text)
        assert r.json()["test_status"] == "auth" and r.json()["last4"] == KEYS[slot][-4:]
    wen.post("/settings/llm", data={"provider": "openai"})
    try:
        services.client("llm").complete("差评归类：Top cracked after two weeks")
    except clients.ServiceError as e:
        bodies.append(str(e))
    for p in ("/", "/settings/keys", "/settings/budget", "/settings/budget?tab=month", "/accounts", "/accounts?tab=audit",
              "/settings/category", "/settings/ledger"):
        bodies.append(wen.get(p).text)
    for p in ("/audit/export", "/settings/ledger/export", "/settings/ledger/export?view=month"):
        wb = load_workbook(io.BytesIO(wen.get(p).content))
        bodies.append("\n".join(str(c) for ws in wb for row in ws.iter_rows(values_only=True) for c in row))
    out = capsys.readouterr()
    bodies += [out.out, out.err, caplog.text]

    blobs = [p.read_bytes() for p in data_dir().rglob("*") if p.is_file()]
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "pdt"
    blobs += [p.read_bytes() for p in src.rglob("*") if p.is_file() and p.suffix in (".py", ".html", ".js", ".css")]
    for slot, key in KEYS.items():
        assert sum(b.count(key) for b in bodies) == 0, slot
        assert sum(b.count(key.encode()) for b in blobs) == 0, slot
    with session() as s:
        for r in s.scalars(select(Secret)):
            assert r.enc_value.startswith(b"gAAAA")  # Fernet 密文
    assert len(seen) >= len(KEYS)  # 测试确实发出了请求（被拦截）


def test_ledger_detail_pagination(wen):
    """DESIGN-05 / FLOW-03：费用明细超过 50 条时可翻页，第 2 页显示第 51 条起，合计不变。"""
    from pdt import costgate
    from pdt.db import session
    from pdt.models import CostRecord
    m = costgate.month_key()
    with session() as s:
        for i in range(79):
            s.add(CostRecord(month=m, service="sellersprite", task=f"拉取 Amazon 2026-10 第 {i + 1} 页", qty=1, amount=0.01))
    p1 = wen.get("/settings/budget").text
    assert "共 79 条" in p1 and "第 1 / 2 页" in p1 and "拉取 Amazon 2026-10 第 79 页" in p1
    p2 = wen.get(f"/settings/budget?tab=detail&month={m}&svc=all&page=2").text
    assert "第 2 / 2 页" in p2 and "拉取 Amazon 2026-10 第 1 页<" in p2 and "拉取 Amazon 2026-10 第 79 页" not in p2
