"""应用入口。各模块在 pdt/web/ 下各自一个 routes_*.py，模块内 `router = APIRouter()`，在 MODULES 里登记。"""
import importlib

from fastapi import FastAPI, Form, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from . import auth
from .config import APP_DIR
from .db import init_db, session
from .models import User
from .security import hash_pw
from .web.ui import templates

MODULES = [
    "routes_home",      # 工作台 F15-02
    "routes_accounts",  # F15-03
    "routes_jobs",      # 费用闸门任务接口（API-F16-03）
    "routes_settings",  # F16-01 / F16-02
    "routes_data",      # F17-01 / F28-01
    "routes_tagging",   # F18-01
    "routes_models",    # F19-01
    "routes_scan",      # F20-01
    "routes_cards",     # F21 / F22 / F29
    "routes_tools",     # F23-01 / F24-01
    "routes_approval",  # F25-01 / F25-02
    "routes_ledger",    # F26-01
    "routes_category",  # F27-01
    "routes_research",  # F30-01 / F30-02 / F30-03
]


def ensure_operator():
    """首次启动没有账号时建初始操作者 wen。初始密码随机生成，写入本机 data/初始密码.txt（不入库），
    也可用环境变量 PDT_INIT_PASSWORD 指定。登录后请在账号页重置。"""
    import os
    import secrets
    from .config import data_dir
    with session() as s:
        if (s.scalar(select(func.count()).select_from(User)) or 0) == 0:
            pw = os.environ.get("PDT_INIT_PASSWORD") or secrets.token_urlsafe(9)
            s.add(User(username="wen", name="wen", role="operator", pw_hash=hash_pw(pw)))
            if not os.environ.get("PDT_INIT_PASSWORD"):
                (data_dir() / "初始密码.txt").write_text(f"账号：wen\n初始密码：{pw}\n登录后请到“账号”页重置密码，然后删除本文件。\n", encoding="utf-8")
            return pw
    return None


def create_app() -> FastAPI:
    init_db()
    ensure_operator()
    from .core import ingest, tagging
    tagging.fill_groups()  # 无主图商品按同系列 / 同品牌同标题补分组键（之前一商品一组）
    ingest.recheck_stuck()  # 上次进程在核对中途退出的批次补做核对（否则一直显示“核对中”）
    tagging.ensure_frame_rules()  # 分框规则升级到 revision 10 时重打尺寸段 / 形态并重扫描（AC-F18-11）；已是则不动
    app = FastAPI(title="品类机会判定台", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

    @app.middleware("http")
    async def login_required(request: Request, call_next):
        path = request.url.path
        request.state.user = None
        if not path.startswith(auth.OPEN_PREFIXES):
            u = auth.user_from_token(request.cookies.get(auth.COOKIE))
            if u is None:  # AC-F15-01：未登录重定向，不返回业务数据
                if path.startswith("/api/") or request.headers.get("accept", "").startswith("application/json"):
                    return JSONResponse({"detail": "未登录"}, status_code=401)
                return RedirectResponse("/login", status_code=303)
            request.state.user = u
            # 只读角色：任何修改请求都拒绝（AC-F15-02），退出登录除外
            if u.role == "readonly" and request.method not in ("GET", "HEAD") and path != "/logout":
                return _forbidden(request)
        return await call_next(request)

    @app.exception_handler(HTTPException)
    async def http_err(request: Request, exc: HTTPException):
        if exc.status_code == 403:
            return _forbidden(request)
        if exc.status_code == 401:
            return RedirectResponse("/login", status_code=303)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, expired: int = 0):
        return templates.TemplateResponse(request, "login.html", dict(error=False, expired=bool(expired), account=""))

    @app.post("/login")
    def login_post(request: Request, account: str = Form(""), password: str = Form("")):
        tok = auth.login(account.strip(), password, ip=request.client.host if request.client else "")
        if not tok:
            return templates.TemplateResponse(request, "login.html", dict(error=True, expired=False, account=account), status_code=401)
        r = RedirectResponse("/", status_code=303)
        r.set_cookie(auth.COOKIE, tok, httponly=True, samesite="lax", max_age=7 * 86400)
        return r

    @app.post("/logout")
    def logout(request: Request):
        auth.logout(request.cookies.get(auth.COOKIE, ""))
        r = RedirectResponse("/login", status_code=303)
        r.delete_cookie(auth.COOKIE)
        return r

    for m in MODULES:
        try:
            mod = importlib.import_module(f".web.{m}", __package__)
        except ModuleNotFoundError as e:
            if e.name == f"{__package__}.web.{m}":
                continue  # 模块尚未开发
            raise
        app.include_router(mod.router)
    return app


def _forbidden(request: Request):
    if request.method == "GET" and not request.headers.get("accept", "").startswith("application/json"):
        return HTMLResponse('<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/static/tokens.css"><link rel="stylesheet" href="/static/app.css">'
                            '<main class="content"><div class="banner banner--block" role="alert"><div class="banner__body">无权限：当前账号的角色不能访问或执行此操作。<a href="/">回到工作台</a></div></div></main>',
                            status_code=403)
    return JSONResponse({"detail": "无权限"}, status_code=403)
