"""登录、会话与角色校验（API-F15-01，AC-F15-01～03、05）。"""
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from .config import SESSION_DAYS
from .db import session
from .models import Audit, LoginSession, User, now
from .security import check_pw, new_token

COOKIE = "pdt_session"
OPEN_PREFIXES = ("/login", "/static/")


class NoPermission(HTTPException):
    def __init__(self):
        super().__init__(status_code=403, detail="无权限")


def audit(kind: str, content: str, user_id=None, ip: str = ""):
    with session() as s:
        s.add(Audit(kind=kind, content=content, user_id=user_id, ip=ip))


def login(username: str, password: str, ip: str = ""):
    with session() as s:
        u = s.scalar(select(User).where(User.username == username))
        if not u or not u.active or not check_pw(u.pw_hash, password):
            return None
        tok = new_token()
        s.add(LoginSession(token=tok, user_id=u.id, expires_at=now() + timedelta(days=SESSION_DAYS)))
        u.last_login = now()
        s.add(Audit(kind="login", content=f"{u.name}（{u.username}）登录", user_id=u.id, ip=ip))
        return tok


def logout(token: str):
    with session() as s:
        ls = s.get(LoginSession, token)
        if ls:
            s.delete(ls)


def user_from_token(token: str | None):
    """每次请求都检查会话和账号是否停用（AC-F15-05）。"""
    if not token:
        return None
    with session() as s:
        ls = s.get(LoginSession, token)
        if not ls or ls.expires_at < now():
            return None
        u = s.get(User, ls.user_id)
        if not u or not u.active:
            s.delete(ls)
            return None
        s.expunge(u)
        return u


def current_user(request: Request) -> User:
    u = getattr(request.state, "user", None)
    if u is None:
        raise HTTPException(status_code=401)
    return u


def roles(*allowed):
    def dep(request: Request) -> User:
        u = current_user(request)
        if u.role not in allowed:
            raise NoPermission()
        return u
    return Depends(dep)


operator_only = roles("operator")
approver_only = roles("approver")
any_user = roles("operator", "approver", "readonly")
