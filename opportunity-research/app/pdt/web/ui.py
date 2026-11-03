"""页面渲染公共部分：侧栏（按角色隐藏，蓝图 §3）、顶栏、模板环境。"""
from datetime import datetime

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from ..config import APP_DIR, CHANNEL_NAMES, ROLES
from ..db import session
from ..models import Approval

templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

# (PAGE ID, 路径, 图标, 名称, 分组, 可见角色)
NAV = [
    ("PAGE-F15-02", "/", "ph-house", "工作台", "", "operator approver readonly"),
    ("PAGE-F17-01", "/data/amazon", "ph-package", "Amazon 月度数据", "数据", "operator"),
    ("PAGE-F28-01", "/data/channels", "ph-tray", "其他渠道数据", "数据", "operator"),
    ("PAGE-F18-01", "/tagging", "ph-list-checks", "打标确认", "数据", "operator"),
    ("PAGE-F20-01", "/scan", "ph-target", "机会扫描", "分析", "operator approver readonly"),
    ("PAGE-F19-01", "/models", "ph-flask", "模型与回测", "分析", "operator approver"),
    ("PAGE-F21-01", "/cards", "ph-cards", "决策卡", "决策", "operator approver readonly"),
    ("PAGE-F25-01", "/approvals", "ph-seal-check", "审批", "审批与台账", "operator approver"),
    ("PAGE-F25-02", "/strategies", "ph-stack", "策略库", "审批与台账", "operator approver readonly"),
    ("PAGE-F26-01", "/ledger", "ph-book-open-text", "预测台账", "审批与台账", "operator approver readonly"),
    ("PAGE-F23-01", "/tools/vp", "ph-chart-bar", "评论 VP 追踪", "工具", "operator"),
    ("PAGE-F24-01", "/tools/profit", "ph-scales", "利润测算", "工具", "operator approver readonly"),
    ("PAGE-F16-01", "/settings/keys", "ph-fingerprint", "密钥与大模型", "设置", "operator"),
    ("PAGE-F16-02", "/settings/budget", "ph-timer", "预算与费用", "设置", "operator"),
    ("PAGE-F15-03", "/accounts", "ph-user-circle", "账号", "设置", "operator"),
    ("PAGE-F27-01", "/settings/category", "ph-sliders-horizontal", "品类配置", "设置", "operator"),
]


def nav_for(user, page_id: str):
    with session() as s:
        pend = s.scalar(select(func.count()).select_from(Approval).where(Approval.status == "pending")) or 0
    from ..core.tagging import queued_count
    counts = {"PAGE-F18-01": queued_count(), "PAGE-F25-01": pend if user.role == "approver" else 0}
    items, last_group = [], None
    for pid, href, icon, name, group, rs in NAV:
        if user.role not in rs.split():
            continue
        if group and group != last_group:
            items.append({"group": group})
            last_group = group
        items.append(dict(pid=pid, href=href, icon=icon, name=name, current=pid == page_id, count=counts.get(pid, 0)))
    return items


def render(request: Request, template: str, page_id: str, title: str, **ctx) -> HTMLResponse:
    user = request.state.user
    return templates.TemplateResponse(request, template, dict(
        ctx, user=user, role_name=ROLES[user.role], page_id=page_id, title=title,
        nav=nav_for(user, page_id), channel_names=CHANNEL_NAMES, today=datetime.now().strftime("%Y-%m-%d"),
        flash=request.query_params.get("msg", ""), flash_kind=request.query_params.get("kind", "ok")))


def redirect(url: str, msg: str = "", kind: str = "ok") -> RedirectResponse:
    if msg:
        from urllib.parse import quote
        url += ("&" if "?" in url else "?") + f"msg={quote(msg)}&kind={kind}"
    return RedirectResponse(url, status_code=303)


def fmt_num(v, nd=0):
    if v is None:
        return "—"
    try:
        return f"{v:,.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


def fmt_pct(v, nd=1):
    return "—" if v is None else f"{v * 100:.{nd}f}%"


def fmt_dt(v):
    return "—" if v is None else v.strftime("%Y-%m-%d %H:%M")


templates.env.filters["num"] = fmt_num
templates.env.filters["pct"] = fmt_pct
templates.env.filters["dt"] = fmt_dt
