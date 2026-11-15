"""账号管理与审计日志（PAGE-F15-03；API-F15-02 / API-F15-03；AC-F15-04、AC-F15-05；DEC-103）。仅操作者可用。"""
import io
from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import Response
from sqlalchemy import func, select

from .. import auth
from ..auth import operator_only
from ..config import ROLES
from ..db import session
from ..models import Audit, User
from ..security import hash_pw
from .ui import redirect, render

router = APIRouter()

AUDIT_KINDS = {"login": "登录", "approve": "审批", "key": "密钥变更", "spend": "花钱任务", "account": "账号", "other": "其他"}
FILTER_KINDS = ["login", "approve", "key", "spend"]  # 页面筛选只列四类（蓝图 §9），“全部”包含账号类记录


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _audit_rows(kind: str, user: str, month: str):
    with session() as s:
        users = {u.id: u for u in s.scalars(select(User))}
        q = select(Audit).order_by(Audit.at.desc(), Audit.id.desc())
        if kind in AUDIT_KINDS:
            q = q.where(Audit.kind == kind)
        if user:
            uid = next((u.id for u in users.values() if u.username == user), -1)
            q = q.where(Audit.user_id == uid)
        if month:
            q = q.where(func.strftime("%Y-%m", Audit.at) == month)
        rows = []
        for a in s.scalars(q):
            u = users.get(a.user_id)
            rows.append(dict(at=a.at, username=u.username if u else "—", kind=a.kind,
                             kind_name=AUDIT_KINDS.get(a.kind, a.kind), content=a.content, ip=a.ip))
        months = sorted({m for (m,) in s.execute(select(func.strftime("%Y-%m", Audit.at)).distinct()) if m}, reverse=True)
        return rows, months


@router.get("/accounts")
def accounts_page(request: Request, tab: str = "accounts", type: str = "all", user: str = "", month: str = "",
                  page: int = 1, me=operator_only):
    with session() as s:
        users = list(s.scalars(select(User).order_by(User.id)))
        for u in users:
            s.expunge(u)
    rows, months = _audit_rows(type, user, month)
    per = 50
    pages = max(1, (len(rows) + per - 1) // per)
    page = min(max(1, page), pages)
    return render(request, "accounts.html", "PAGE-F15-03", "账号管理", users=users, roles=ROLES, me=me,
                  tab="audit" if tab == "audit" else "accounts", ftype=type if type in AUDIT_KINDS else "all",
                  fuser=user, fmonth=month, months=months, audit=rows[(page - 1) * per: page * per],
                  audit_total=len(rows), page=page, pages=pages, kinds=AUDIT_KINDS, filter_kinds=FILTER_KINDS)


@router.post("/accounts")
def create_account(request: Request, name: str = Form(""), username: str = Form(""), role: str = Form(""),
                   password: str = Form(""), password2: str = Form(""), me=operator_only):
    name, username = name.strip(), username.strip()
    for v, label in ((name, "姓名"), (username, "账号"), (role, "角色"), (password, "初始密码")):
        if not v:
            return redirect("/accounts", f"请填写{label}", "error")
    if role not in ROLES:
        return redirect("/accounts", "角色只能是操作者、审批者或只读", "error")
    if password != password2:
        return redirect("/accounts", "两次输入的密码不一致", "error")
    with session() as s:
        if s.scalar(select(User.id).where(User.username == username)):
            return redirect("/accounts", f"账号 {username} 已存在", "error")
        s.add(User(username=username, name=name, role=role, pw_hash=hash_pw(password)))
    auth.audit("account", f"新建账号 {name}（{username}），角色 {ROLES[role]}", me.id, _ip(request))
    return redirect("/accounts", f"已创建账号 {name}（{ROLES[role]}）")


@router.post("/accounts/{uid}/reset")
def reset_password(request: Request, uid: int, password: str = Form(""), password2: str = Form(""), me=operator_only):
    if not password:
        return redirect("/accounts", "请填写新密码", "error")
    if password != password2:
        return redirect("/accounts", "两次输入的密码不一致", "error")
    with session() as s:
        u = s.get(User, uid)
        if not u or not u.active:
            return redirect("/accounts", "账号不存在或已停用", "error")
        u.pw_hash = hash_pw(password)
        who = f"{u.name}（{u.username}）"
    auth.audit("account", f"重置 {who} 的密码", me.id, _ip(request))
    return redirect("/accounts", f"已重置 {who} 的密码")


@router.post("/accounts/{uid}/disable")
def disable_account(request: Request, uid: int, me=operator_only):
    with session() as s:
        u = s.get(User, uid)
        if not u or not u.active:
            return redirect("/accounts", "账号不存在或已停用", "error")
        who = f"{u.name}（{u.username}）"
        if u.role == "operator":
            n = s.scalar(select(func.count()).select_from(User).where(User.role == "operator", User.active.is_(True))) or 0
            if n <= 1:  # DEC-103：至少保留一个正常状态的操作者
                return redirect("/accounts", f"不能停用 {who}：系统至少要保留一个正常状态的操作者，否则没人能管理账号", "error")
        if u.id == me.id:
            return redirect("/accounts", "不能停用当前登录的自己", "error")
        u.active = False
    # 会话不在这里删：auth.user_from_token 在对方下一次请求时检查停用并让会话失效（AC-F15-05）
    auth.audit("account", f"停用账号 {who}", me.id, _ip(request))
    return redirect("/accounts", f"已停用 {who}，其会话将在下一次操作时失效")


@router.get("/audit")
def audit_page(type: str = "all", user: str = "", month: str = "", me=operator_only):
    from urllib.parse import urlencode
    return redirect("/accounts?" + urlencode(dict(tab="audit", type=type, user=user, month=month)))


@router.get("/audit/export")
def audit_export(type: str = "all", user: str = "", month: str = "", me=operator_only):
    from openpyxl import Workbook
    rows, _ = _audit_rows(type, user, month)
    wb = Workbook()
    ws = wb.active
    ws.title = "审计日志"
    ws.append(["时间", "账号", "类型", "内容", "来源地址"])
    for r in rows:
        ws.append([r["at"].strftime("%Y-%m-%d %H:%M:%S"), r["username"], r["kind_name"], r["content"], r["ip"]])
    for col, w in zip("ABCDE", (20, 14, 10, 80, 16)):
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    from urllib.parse import quote
    fn = f"审计日志_{month or datetime.now().strftime('%Y-%m')}.xlsx"
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fn)}"})
