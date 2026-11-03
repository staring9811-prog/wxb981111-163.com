"""工作台（PAGE-F15-02）按角色聚合，以及 RULE-01 全路由越权检查。"""
import re
from datetime import date

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from conftest import login_as, make_user
from pdt import auth, costgate
from pdt.db import Base, session
from pdt.models import Approval, Batch, Budget, Card, CostRecord, Forecast, ModelRun, Product, Secret, Tag, User
from pdt.web.routes_home import _data_month


def _nav(html):
    return html.split('<nav class="nav">')[1].split("</nav>")[0]


def _block(html, name):
    return f'data-block="{name}"' in html


def _seed(dm):
    from pdt.security import encrypt
    with session() as s:
        wid = s.scalar(select(User.id).where(User.username == "wen"))
        s.add(Batch(channel="amazon", month=dm, source="api", status="suspect_month",
                    anomaly_reason="与上月小类排名完全相同的 ASIN 占 99.9%（阈值 10%），未并入"))
        s.add(Batch(channel="homedepot", month=dm, source="tracker", status="merged", rows=210))
        s.add_all([
            Product(channel="amazon", item_id="B0CXK7R2QW", brand="Sweetcrispy", title="30 Inch Bathroom Vanity with Sink, Fluted Doors"),
            Product(channel="amazon", item_id="B0D1M9TZ4P", brand="Kahomvis", title="30 Inch Farmhouse Bathroom Vanity with Barn Door"),
            Product(channel="lowes", item_id="5014452871", brand="allen + roth", title="allen + roth Presley 36-in Gray Bathroom Vanity"),
        ])
        s.add_all([
            Tag(channel="amazon", item_id="B0CXK7R2QW", tag="元素", value="竖棱", source="vision", status="queued", img_group="g1"),
            Tag(channel="amazon", item_id="B0D1M9TZ4P", tag="元素", value="农场风", source="vision", status="queued", img_group="g1"),
            Tag(channel="lowes", item_id="5014452871", tag="台面材质", value="岗石", confidence=0.62, source="rule", status="queued"),
            Tag(channel="amazon", item_id="B0CXK7R2QW", tag="主色", value="白", confidence=0.95, source="rule", status="auto"),
        ])
        s.add(ModelRun(month=dm, valid=False, valid_msg="D 档之后变大 36%（阈值 ≤ 30%），把握分档 C 档低于 D 档。"))
        card = Card(channel="amazon", frame="30″ · 整装 · 落地式", attr="台面材质", value="岩板", status="pending")
        s.add(card)
        s.flush()
        s.add(Approval(obj_type="card", obj_id=card.id, submitted_by=wid))
        s.add(Forecast(code="TZ-2026-004", card_id=card.id, card_version=1, frame="36″ · 整装 · 落地式", attr="盆数", value="双盆",
                       launch_month="2026-05", channels=["amazon", "homedepot"], status="due",
                       result={"homedepot": {"made": True, "basis": "估算月销 268 件 ≥ 250"}}))
        s.add(Forecast(code="TZ-2026-006", card_id=card.id, card_version=1, frame="48″ · 整装 · 落地式", attr="台面材质", value="岩板",
                       launch_month="2026-07", channels=["amazon"], status="unlinked"))
        s.add(Budget(service="brightdata", cap=80, unit="usd"))
        s.add(Secret(slot="brightdata", enc_value=encrypt("b7e94c2a1f0d8e6b3c5a7f9d2e4b6c8a"), last4="6c8a"))
        s.add(CostRecord(month=costgate.month_key(), service="brightdata", task="评论 VP 追踪 · Wayfair 页面", qty=250, amount=65.6))


def test_home_empty_state(wen):
    """DESIGN-02（空状态）：系统刚部署时数据状态区提示先拉第一批，标签、审批、对账区块显示一句话而非空白。"""
    html = wen.get("/").text
    assert "还没有任何月份的数据。先在 Amazon 月度数据页拉取第一批。" in html and 'href="/data/amazon">去拉取' in html
    assert "本月没有待确认标签" in html and "没有等待审批的提交" in html and "本月没有到期对账的台账条目" in html
    assert "还没有市场评分" in html
    assert "未连接" in html  # 四个服务都未填密钥


def test_home_by_role(app_env, wen):
    """DESIGN-02 / AC-F19-04 / AC-F15-02 / AC-F15-03：操作者看到全部区块；审批者看到“待我审批”与有效性、对账，没有数据 / 标签 / 花费；
    只读只看到有效性、到期对账、常用入口；有效性未通过时三种角色都显示“市场评分本月未通过有效性检验”。"""
    dm = _data_month(date.today())
    _seed(dm)
    html = wen.get("/").text
    assert all(_block(html, b) for b in ("data", "tags", "recon", "approvals", "spend"))
    assert "市场评分本月未通过有效性检验" in html and "D 档之后变大 36%" in html
    assert "疑似月份错误" in html and "99.9%" in html and "已并入" in html and "未拉取" in html
    total = re.search(r"data-tag-total>(\d+)<", html).group(1)
    nav_count = re.search(r'href="/tagging".*?nav__count">(\d+)<', _nav(html)).group(1)
    assert total == nav_count == "3" and "元素 2、低置信度 1" in html and "共 2 组（同主图的合为一组" in html
    assert "等待审批" in html and "30″ · 整装 · 落地式｜台面材质 = 岩板" in html
    assert "TZ-2026-004" in html and "Home Depot 已自动对账：做到（估算月销 268 件 ≥ 250）" in html and "Amazon 等待数据" in html
    assert "满 6 个月：2026-10" in html and "待关联：预计上架 2026-07" in html
    assert "$65.60 / $80.00" in html and "82%" in html and "接近上限" in html

    make_user("zhoujianguo", "周建国", "approver")
    make_user("lixiaomei", "李晓梅", "readonly")
    a = login_as(TestClient(app_env), "zhoujianguo", "密码-123456").get("/").text
    assert "待我审批" in a and "30″ · 整装 · 落地式｜台面材质 = 岩板" in a and "市场评分本月未通过有效性检验" in a
    assert _block(a, "recon") and not any(_block(a, b) for b in ("data", "tags", "spend"))
    assert "设置" not in _nav(a) and "$65.60" not in a and "疑似月份错误" not in a

    r = login_as(TestClient(app_env), "lixiaomei", "密码-123456").get("/").text
    assert "市场评分本月未通过有效性检验" in r and _block(r, "recon") and "TZ-2026-004" in r
    assert not any(_block(r, b) for b in ("data", "tags", "spend", "approvals"))
    assert "设置" not in _nav(r) and 'href="/approvals"' not in _nav(r) and "查看回测" not in r
    for word in ("机会扫描", "决策卡", "预测台账", "策略库"):
        assert word in r


def test_home_batch_status_all_chinese(wen):
    """DESIGN-02：本月数据状态表里所有批次状态都显示中文（其他渠道未完整月 reference = “仅参考（未完整月）”），不出现英文原始值。"""
    from pdt.web.routes_home import BATCH_STATUS
    dm = _data_month(date.today())
    for st in ("suspect_month", "anomaly", "ok", "merged", "reference", "superseded", "rejected"):
        assert st in BATCH_STATUS and re.search(r"[\u4e00-\u9fff]", BATCH_STATUS[st][0])
    with session() as s:
        s.add(Batch(channel="amazon", month=dm, source="api", status="merged", rows=2961))
        s.add(Batch(channel="wayfair", month=dm, source="tracker", status="reference", rows=184))
        s.add(Batch(channel="lowes", month=dm, source="tracker", status="superseded", rows=203))
        s.add(Batch(channel="homedepot", month=dm, source="tracker", status="rejected", rows=0))
    html = wen.get("/").text
    block = html.split('data-block="data"')[1].split("</section>")[0]
    assert "仅参考（未完整月）" in block and "已被新版本替换" in block and "已退回" in block
    for raw in ("reference", "superseded", "rejected", "merged"):
        assert f"</svg>{raw}<" not in block


def test_queued_count_same_everywhere(wen):
    """DESIGN-08 / DESIGN-02：侧栏“打标确认”角标、工作台待确认数、打标确认页待确认数同一口径——已标“不是本品类”的商品不计入。"""
    from pdt.core import tagging
    with session() as s:
        s.add_all([
            Product(channel="amazon", item_id="B0CXK7R2QW", brand="Sweetcrispy", title="30 Inch Bathroom Vanity with Sink, Fluted Doors"),
            Product(channel="amazon", item_id="B0D1M9TZ4P", brand="Kahomvis", title="30 Inch Farmhouse Bathroom Vanity with Barn Door"),
            Product(channel="amazon", item_id="B0BWX3KQ7L", brand="VASAGLE", title="Bathroom Floor Storage Cabinet with Doors", excluded=True),
        ])
        s.add_all([
            Tag(channel="amazon", item_id="B0CXK7R2QW", tag="元素", value="竖棱", source="vision", status="queued", img_group="g1"),
            Tag(channel="amazon", item_id="B0D1M9TZ4P", tag="元素", value="农场风", source="vision", status="queued", img_group="g1"),
            Tag(channel="amazon", item_id="B0BWX3KQ7L", tag="元素", value="", source="rule", status="queued", img_group="g2"),
            Tag(channel="amazon", item_id="B0BWX3KQ7L", tag="尺寸段", value="24″", confidence=0.5, source="rule", status="queued", img_group="g2"),
        ])
    assert tagging.queued_count() == tagging.counts()["total"] == 2
    home = wen.get("/").text
    assert re.search(r"data-tag-total>(\d+)<", home).group(1) == "2"
    assert re.search(r'href="/tagging".*?nav__count">(\d+)<', _nav(home)).group(1) == "2"
    assert "共 1 组（同主图的合为一组" in home
    tag_page = wen.get("/tagging").text
    assert re.search(r'href="/tagging".*?nav__count">(\d+)<', _nav(tag_page)).group(1) == "2"
    assert '待确认 <span class="count">2</span>' in tag_page


def test_home_validity_pass_and_stale(wen):
    """AC-F19-04 / DESIGN-02：本月重算且通过时显示“市场评分本月通过有效性检验”；最新重算发生在之前的月份时显示“本月尚未重算”，
    两种都按最新 ModelRun 的数据截至月与重算时间写同一句依据。"""
    from datetime import datetime
    dm = _data_month(date.today())
    with session() as s:
        s.add(ModelRun(month=dm, valid=True, valid_msg="D 档之后变大 24%，阈值 ≤ 30%；把握分档逐档上升。"))
    html = wen.get("/").text
    assert "市场评分本月通过有效性检验" in html and f"第九版，数据截至 {dm}，{date.today():%Y-%m-%d} 重算" in html and "尚未纳入重算" not in html
    with session() as s:
        s.add(ModelRun(month="2026-01", valid=True, created_at=datetime(2026, 2, 6, 10, 30)))
    html = wen.get("/").text
    assert "本月尚未重算，以下沿用数据截至 2026-01 的结论" in html and "第九版，数据截至 2026-01，2026-02-06 重算" in html


def test_home_validity_no_contradiction_when_recomputed_on_older_data(wen):
    """DESIGN-02：本月已重算但用的是上上月数据（数据月尚未并入）时，不说“本月尚未重算”，说明数据截至月与待纳入的数据月。"""
    from pdt.core.card import validity_statement
    dm = _data_month(date.today())
    y, m = map(int, dm.split("-"))
    older = f"{y - (m == 1):04d}-{(m - 2) % 12 + 1:02d}"
    with session() as s:
        s.add(ModelRun(month=older, valid=True))
    html = wen.get("/").text
    assert "本月尚未重算" not in html and "市场评分本月通过有效性检验" in html
    assert f"第九版，数据截至 {older}，{date.today():%Y-%m-%d} 重算。{dm} 数据尚未纳入重算。" in html
    with session() as s:
        run = s.scalar(select(ModelRun))
        v = validity_statement(run, dm)
    assert (v["kind"], v["pending"]) == ("pass", f"{dm} 数据尚未纳入重算")


def test_home_spend_shows_used_and_cap(wen):
    """DESIGN-02：工作台“本月花费 / 上限”按预算页口径显示“已用 / 上限”；没设上限写“未设上限”；未连接另行标注。"""
    from pdt.security import encrypt
    html = wen.get("/").text
    block = html.split('data-block="spend"')[1].split("</section>")[0]
    assert "0 次 / 未设上限" in block and block.count("$0.00 / 未设上限") == 3 and block.count("未连接") == 4
    with session() as s:
        s.add(Budget(service="sellersprite", cap=5000, unit="calls"))
        s.add(Budget(service="brightdata", cap=80, unit="usd"))
        s.add(Secret(slot="brightdata", enc_value=encrypt("b7e94c2a1f0d8e6b3c5a7f9d2e4b6c8a"), last4="6c8a"))
        s.add(CostRecord(month=costgate.month_key(), service="sellersprite", task="拉取 Amazon 2026-10 第 1 页", qty=3120, amount=31.2))
        s.add(CostRecord(month=costgate.month_key(), service="brightdata", task="评论 VP 追踪 · Wayfair 页面", qty=250, amount=65.6))
    block = wen.get("/").text.split('data-block="spend"')[1].split("</section>")[0]
    assert "3,120 / 5,000 次" in block and "$65.60 / $80.00" in block and "82%" in block
    ss = block.split('data-svc="sellersprite"')[1].split('data-svc="brightdata"')[0]
    assert "未连接" in ss  # 有上限但未填密钥：上限照常显示，未连接另行标注
    bd = block.split('data-svc="brightdata"')[1].split('data-svc="apify"')[0]
    assert "未连接" not in bd and "接近上限" in bd


def test_home_data_note_column_collapses_long_text(wen):
    """DESIGN-02：本月数据状态表“核对说明”长文本截断为一行摘要并可展开，不再把行撑成十几行。"""
    dm = _data_month(date.today())
    reason = "上月购买标日期为 2026-09-01 至 2026-09-30，不在所标月份；与 2026-09 小类排名完全相同的 ASIN 占 96.9%（n=3,222）；品类总月销较上月 +43.7%"
    with session() as s:
        s.add(Batch(channel="amazon", month=dm, source="upload", status="suspect_month", anomaly_reason=reason))
    block = wen.get("/").text.split('data-block="data"')[1].split("</section>")[0]
    assert '<th class="col-note">核对说明</th>' in block
    assert f'<details class="note-more" data-no-row><summary>{reason[:32]}…<span class="tlink">展开</span></summary><div>{reason}</div></details>' in block


# ---------------------------------------------------------------- RULE-01
APPROVER_ALLOWED = re.compile(r"^/approvals|comment|decide|^/logout$")  # 审批者只允许审批与留意见（AC-F15-03）


def _walk(routes):
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        elif hasattr(r, "original_router"):  # include_router 包装（各模块路由，无前缀）
            yield from _walk(r.original_router.routes)


def _routes(app):
    out = []
    for r in _walk(app.routes):
        path = re.sub(r"\{[^}]+\}", "1", r.path)
        approver = any(d.call is auth.approver_only.dependency for d in r.dependant.dependencies)
        for m in r.methods:
            out.append((m, path, approver))
    return sorted(set(out))


def _counts():
    with session() as s:
        return {t.name: s.scalar(select(func.count()).select_from(t)) for t in Base.metadata.sorted_tables}


def test_rule01_all_routes(app_env, client):
    """RULE-01：遍历全部已注册路由——未登录一律 303 到 /login 且不含业务数据；只读对所有修改请求、审批者对除审批 / 意见外的修改请求
    都得到 403“无权限”，数据库各表行数不变；两者访问操作者专属设置页也得到 403。"""
    routes = _routes(app_env)
    assert len(routes) > 10
    for m, p, _ in routes:
        if p.startswith("/login"):
            continue
        r = client.request(m, p, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login", (m, p, r.status_code)
        assert len(r.content) < 200, (m, p)

    make_user("lixiaomei", "李晓梅", "readonly")
    make_user("zhoujianguo", "周建国", "approver")
    ro = login_as(TestClient(app_env), "lixiaomei", "密码-123456")
    ap = login_as(TestClient(app_env), "zhoujianguo", "密码-123456")
    before = _counts()
    for m, p, approver in routes:
        if m in ("GET", "HEAD") or p.startswith("/login") or p == "/logout":
            continue
        r = ro.request(m, p, headers={"accept": "application/json"}, follow_redirects=False)
        assert r.status_code == 403 and r.json()["detail"] == "无权限", ("只读", m, p, r.status_code)
        if approver and APPROVER_ALLOWED.search(p):
            continue
        r = ap.request(m, p, headers={"accept": "application/json"}, follow_redirects=False)
        assert r.status_code == 403 and r.json()["detail"] == "无权限", ("审批者", m, p, r.status_code)
    after = _counts()
    after.pop("login_session", None), before.pop("login_session", None)
    assert after == before
    for c in (ro, ap):
        for p in ("/settings/keys", "/settings/budget", "/settings/category", "/accounts", "/settings/ledger"):
            assert c.get(p).status_code == 403, p
