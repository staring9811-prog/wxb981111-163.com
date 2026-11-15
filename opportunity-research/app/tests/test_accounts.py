"""账号管理与审计（PAGE-F15-03）：FLOW-01、DEC-103、审计日志筛选与导出。"""
import io

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import select

from conftest import login_as
from pdt.db import session
from pdt.models import Audit, User


def _new_client(app):
    return TestClient(app)


def _create(wen, name, username, role, pw="梅花-2026-ok"):
    return wen.post("/accounts", data=dict(name=name, username=username, role=role, password=pw, password2=pw), follow_redirects=False)


def _nav(html):
    return html.split('<nav class="nav">')[1].split("</nav>")[0]


def test_flow01_create_login_disable_last_operator(app_env, wen):
    """FLOW-01：新建只读与审批者账号并登录；停用李晓梅后其会话下一次请求回登录页且不能再登录；停用唯一操作者被拒绝并提示原因（DEC-103）。"""
    r = _create(wen, "李晓梅", "lixiaomei", "readonly")
    assert r.status_code == 303 and "msg=" in r.headers["location"]
    r = _create(wen, "周建国", "zhoujianguo", "approver")
    assert r.status_code == 303
    page = wen.get("/accounts").text
    assert "李晓梅" in page and "lixiaomei" in page and "周建国" in page and "审批者" in page

    li = login_as(_new_client(app_env), "lixiaomei", "梅花-2026-ok")
    nav = _nav(li.get("/").text)
    assert "设置" not in nav and "打标确认" not in nav and "href=\"/approvals\"" not in nav and "决策卡" in nav
    assert li.get("/accounts").status_code == 403
    assert li.post("/accounts", data=dict(name="王磊", username="wanglei", role="readonly", password="a", password2="a"),
                   headers={"accept": "application/json"}).json()["detail"] == "无权限"

    zhou = login_as(_new_client(app_env), "zhoujianguo", "梅花-2026-ok")
    home = zhou.get("/").text
    assert "待我审批" in home and "设置" not in _nav(home)
    assert zhou.get("/settings/keys").status_code == 403

    with session() as s:
        lid = s.scalar(select(User.id).where(User.username == "lixiaomei"))
        wid = s.scalar(select(User.id).where(User.username == "wen"))
    r = wen.post(f"/accounts/{lid}/disable", follow_redirects=False)
    assert r.status_code == 303
    r = li.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    r = _new_client(app_env).post("/login", data={"account": "lixiaomei", "password": "梅花-2026-ok"}, follow_redirects=False)
    assert r.status_code == 401
    assert "已停用" in wen.get("/accounts").text

    r = wen.post(f"/accounts/{wid}/disable", follow_redirects=True)
    assert "系统至少要保留一个正常状态的操作者" in r.text
    with session() as s:
        assert s.get(User, wid).active is True
        contents = [a.content for a in s.scalars(select(Audit).where(Audit.kind == "account"))]
    assert any("新建账号 李晓梅（lixiaomei）" in c for c in contents)
    assert any("停用账号 李晓梅（lixiaomei）" in c for c in contents)


def test_create_validation_and_reset(app_env, wen):
    """FLOW-01 补充：账号重复、两次密码不一致被拦截；重置密码后用新密码登录并写审计。"""
    _create(wen, "陈志强", "chenzhiqiang", "readonly")
    r = _create(wen, "陈志强", "chenzhiqiang", "readonly")
    assert "账号 chenzhiqiang 已存在" in wen.get(r.headers["location"]).text
    r = wen.post("/accounts", data=dict(name="王磊", username="wanglei", role="readonly", password="甲-1", password2="乙-2"),
                 follow_redirects=True)
    assert "两次输入的密码不一致" in r.text
    with session() as s:
        assert s.scalar(select(User).where(User.username == "wanglei")) is None
        cid = s.scalar(select(User.id).where(User.username == "chenzhiqiang"))
    wen.post(f"/accounts/{cid}/reset", data=dict(password="新密码-采购-9", password2="新密码-采购-9"))
    login_as(_new_client(app_env), "chenzhiqiang", "新密码-采购-9")
    with session() as s:
        assert s.scalar(select(Audit).where(Audit.content.like("%重置 陈志强（chenzhiqiang） 的密码%"))) is not None


def test_audit_filter_and_export(app_env, wen):
    """审计日志：按类型筛选（登录 / 密钥变更），导出 Excel 与筛选结果一致。"""
    from pdt import services

    class 假Apify:
        def test(self):
            return "ok", "可用"
    services.set_fake("apify", 假Apify())
    wen.post("/settings/keys/apify", data={"value": "apify_api_Q7mLx2pR9sT4vW8yZ1cD3fG5hJ6k"})
    r = wen.get("/accounts?tab=audit&type=login")
    assert "wen（wen）登录" in r.text and "Apify 密钥" not in r.text
    r = wen.get("/accounts?tab=audit&type=key")
    assert "保存 Apify 密钥 ••••hJ6k" in r.text and "wen（wen）登录" not in r.text
    x = wen.get("/audit/export?type=key")
    ws = load_workbook(io.BytesIO(x.content)).active
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0] == ("时间", "账号", "类型", "内容", "来源地址")
    assert len(rows) == 2 and rows[1][2] == "密钥变更" and rows[1][3].startswith("保存 Apify 密钥 ••••")
