"""FastAPI application: local-only, Host-checked, token-protected writes (NFR-006, 技术方案 §7.2)."""

from __future__ import annotations

import logging
import secrets
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from oppo import service as SV
from oppo.web import common as C

HERE = Path(__file__).resolve().parent
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
SAFE = {"GET", "HEAD", "OPTIONS"}


async def csrf(request: Request) -> None:
    """Writes need the per-start token and must not come from another site."""
    if request.method in SAFE:
        return
    origin = request.headers.get("origin") or request.headers.get("referer")
    if origin:
        host = urlparse(origin).hostname
        if host not in ALLOWED_HOSTS:
            raise HTTPException(status_code=403, detail="跨来源的写请求已拒绝")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(status_code=403, detail="跨来源的写请求已拒绝")
    token = request.headers.get("x-oppo-token")
    if not token:
        ctype = request.headers.get("content-type", "")
        if "form" in ctype:
            form = await request.form()
            token = form.get("_token")  # type: ignore[assignment]
    if not token or not secrets.compare_digest(str(token), request.app.state.token):
        raise HTTPException(status_code=403, detail="缺少或无效的启动令牌，写请求已拒绝")


def _setup_logging(svc: SV.App) -> None:
    log = logging.getLogger("oppo")
    if any(isinstance(h, TimedRotatingFileHandler) for h in log.handlers):
        return
    svc.settings.logs_dir.mkdir(parents=True, exist_ok=True)
    h = TimedRotatingFileHandler(svc.settings.logs_dir / "oppo.log", when="midnight", backupCount=90,
                                 encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)


def create_app(svc: SV.App | None = None, token: str | None = None) -> FastAPI:
    svc = svc or SV.open_app()
    _setup_logging(svc)
    app = FastAPI(title="品类机会判定台", docs_url=None, redoc_url=None, openapi_url=None,
                  dependencies=[Depends(csrf)])
    app.state.svc = svc
    app.state.token = token or secrets.token_urlsafe(24)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    from oppo.web.views import analysis, data_prep, ledger, products, workbench

    for mod in (workbench, data_prep, products, analysis, ledger):
        app.include_router(mod.router)

    @app.get("/mode/{mode}")
    def set_mode(mode: str, next: str = "/") -> RedirectResponse:  # noqa: A002
        if mode not in ("history", "cross"):
            mode = "history"
        target = next if next.startswith("/") and not next.startswith("//") else "/"
        r = RedirectResponse(target, status_code=303)
        r.set_cookie("oppo_mode", mode, samesite="strict", httponly=True)
        return r

    @app.get("/jobs/current")
    def job_current(request: Request) -> JSONResponse:
        return JSONResponse(C.job_state(request))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):  # type: ignore[no-untyped-def]
        if request.headers.get("hx-request") or request.method not in SAFE:
            return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
        return HTMLResponse(C.error_page(request, exc.status_code, str(exc.detail)), status_code=exc.status_code)

    return app
