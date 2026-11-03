"""审批（F25）：决策卡立项审批、策略库条目与"改为已验证"申请。

- 提交：草稿 → 待审批，记录提交版本（以提交时锁定的版本为准）；
- 决定：批准 / 驳回 / 退回修改，驳回与退回意见必填；记录审批人、时间、结论、意见并写审计（AC-F25-01）；
- 批准：锁定只读、保存数字快照（AC-F25-02）、自动登记预测台账（AC-F25-03）；
- 策略库：三种状态，修改产生新版本，旧版本保留（AC-F25-04）；改为"已验证"必须经老板批准才生效（AC-F25-05）。
"""
from datetime import datetime

from sqlalchemy import select

from ..auth import audit
from ..db import session
from ..models import Approval, Card, Strategy, StrategyVersion, User, now
from ..models_decision import StrategyRequest, StrategyVersionNote
from . import card as cardcore

DECISIONS = {"approve": "批准", "reject": "驳回", "return": "退回修改"}
STRAT_STATUS = ["未验证经验", "历史观察", "已验证"]
STRAT_KINDS = ["分框信号", "条件表", "经验"]


class ApprovalError(Exception):
    pass


def _uname(s, uid):
    u = s.get(User, uid) if uid else None
    return u.name if u else "—"


# ---------------------------------------------------------------- 决策卡
def submit_card(card_id: int, user_id: int, note: str = "") -> int:
    with session() as s:
        c = s.get(Card, card_id)
        miss = cardcore.missing_items(c)
        if miss:
            raise ApprovalError("还缺：" + "、".join(miss))
        cardcore.transition(c, "submit")
        c.narrative = dict(c.narrative or {}, submit_note=note)
        a = Approval(obj_type="card", obj_id=c.id, obj_version=c.version, submitted_by=user_id, comment="")
        s.add(a)
        s.flush()
        cardcore.log(s, c.id, "submit", f"{_uname(s, user_id)} 提交第 {c.version} 版" + (f"：{note}" if note else ""), user_id)
        return a.id


def decide(approval_id: int, decision: str, comment: str, user_id: int, ip: str = "") -> dict:
    comment = (comment or "").strip()
    if decision not in DECISIONS:
        raise ApprovalError("请选择结论")
    if decision != "approve" and not comment:
        raise ApprovalError("驳回或退回修改时请填写意见")
    with session() as s:
        a = s.get(Approval, approval_id)
        if a is None or a.status != "pending":
            raise ApprovalError("这条已处理")
        a.status, a.decision, a.decided_by, a.decided_at, a.comment = "done", decision, user_id, now(), comment
        who = _uname(s, user_id)
        res = {}
        if a.obj_type == "card":
            c = s.get(Card, a.obj_id)
            if c.version != a.obj_version or c.status != "pending":
                raise ApprovalError("这条已处理")
            cardcore.transition(c, decision)
            name = cardcore.card_name(c)
            if decision == "approve":
                cardcore.take_snapshot(s, c)
                s.flush()
                from . import ledger
                f = ledger.register(s, c)
                res = dict(ledger_code=f.code)
                txt = f"{who} 批准" + (f"：“{comment}”" if comment else "")
            elif decision == "return":
                c.version += 1  # 退回后再提交是下一版
                txt = f"{who} 退回修改：“{comment}”"
            else:
                txt = f"{who} 驳回：“{comment}”"
            cardcore.log(s, c.id, decision, txt, user_id)
            content = f"决策卡立项 · {name} 第 {a.obj_version} 版 · {DECISIONS[decision]}" + (f" · 意见：{comment}" if comment else "")
        else:
            st = s.get(Strategy, a.obj_id)
            req = s.scalar(select(StrategyRequest).where(StrategyRequest.approval_id == a.id))
            if decision == "approve":
                _new_version(s, st, dict(status=req.to_status if req else "已验证"), user_id, f"老板批准改为已验证（审批 #{a.id}）")
            content = f"策略库改为已验证 · {st.code} {st.title} · {DECISIONS[decision]}" + (f" · 意见：{comment}" if comment else "")
    audit("approve", content, user_id, ip)
    return res


def pending(s):
    return list(s.scalars(select(Approval).where(Approval.status == "pending").order_by(Approval.submitted_at.desc())))


def done(s):
    return list(s.scalars(select(Approval).where(Approval.status == "done").order_by(Approval.decided_at.desc())))


def describe(s, a: Approval) -> dict:
    d = dict(id=a.id, type=a.obj_type, type_name="决策卡立项" if a.obj_type == "card" else "策略库改为已验证",
             version=a.obj_version, submitter=_uname(s, a.submitted_by), submitted_at=a.submitted_at,
             decision=a.decision, decision_name=DECISIONS.get(a.decision, ""), decider=_uname(s, a.decided_by),
             decided_at=a.decided_at, comment=a.comment, status=a.status)
    if a.obj_type == "card":
        c = s.get(Card, a.obj_id)
        d.update(obj=cardcore.card_name(c), href=f"/cards/{c.id}", channel=c.channel, card=c,
                 note=(c.narrative or {}).get("submit_note", ""))
        if c.status in cardcore.LOCKED:
            from ..models import Forecast
            f = s.scalar(select(Forecast).where(Forecast.card_id == c.id))
            d["result"] = f"已锁定第 {c.version} 版" + (f" · 台账 {f.code}" if f else "")
        else:
            d["result"] = "卡片状态：" + cardcore.STATUS_NAMES.get(c.status, c.status)
    else:
        st = s.get(Strategy, a.obj_id)
        req = s.scalar(select(StrategyRequest).where(StrategyRequest.approval_id == a.id))
        d.update(obj=f"{st.code} {st.title}", href=f"/strategies#{st.code}", strategy=st,
                 from_status=req.from_status if req else "", to_status=req.to_status if req else "已验证",
                 note=req.basis if req else "", result="条目状态：" + st.status)
    return d


# ---------------------------------------------------------------- 策略库
SEED = [
    ("SL-06", "只在同一个“尺寸段 × 拆装 × 形态”框里比较，不跨框比份额、溢价、评分", "条件表", "已验证",
     "wen 硬规则（2026-11-03）；跨框比较会把尺寸、拆装带来的体量差异误当成机会", "全部框"),
    ("SL-01", "分框信号：取值的新品占比高于同框 → 之后份额更可能变大", "分框信号", "历史观察",
     "第九版回测：加入新品占比后市场层 ≥ 300 件单元秩相关 +0.43 至 +0.49（第八版 +0.17 至 +0.38）；竖棱站在 2025-07 即 A 档。严格样本外检验要等 2026-10 起的数据（回归预测_回测_第九版.md）", "全部框"),
    ("SL-02", "分框信号：份额近 6 个月比前 6 个月高（份额斜率为正）", "分框信号", "历史观察",
     "第八、九版市场层回测：把握分档后实际变大比例单调（22% / 43% / 56% / 65%），D 档只有 20% 变大", "全部框"),
    ("SL-03", "新品首月 ≥ 2 色、≥ 4 子体更容易做到", "条件表", "历史观察",
     "第一版新品打分 + 条件表，已用 2026-01 至 04 上架的实际核对过（项目纪要 2026-11-02）", "全部框"),
    ("SL-04", "老板：老品评分差，新品把评分做好就起量", "经验", "未验证经验",
     "老板经验；第九版检验时现有数据验证不了（评分差距、低分高销检验后不进入打分），记为未验证经验（项目纪要 2026-11-03）", "全部框"),
    ("SL-05", "30″ 及以下从拆装切入比整装容易", "经验", "未验证经验", "wen 经验，待预测台账积累后检验", "24″ / 30″"),
]


def seed_strategies():
    with session() as s:
        if s.scalar(select(Strategy.id).limit(1)) is not None:
            return
        for code, title, kind, status, basis, body in SEED:
            st = Strategy(code=code, title=title, kind=kind, status=status, version=1, basis=basis, body=body)
            s.add(st)
            s.flush()
            v = StrategyVersion(strategy_id=st.id, version=1, title=title, status=status, basis=basis, body=body, by=None)
            s.add(v)
            s.flush()
            s.add(StrategyVersionNote(version_id=v.id, note="首次启动预置（第二轮结论）"))


def _new_version(s, st: Strategy, patch: dict, user_id, note: str):
    for k in ("title", "kind", "status", "basis", "body"):
        if k in patch and patch[k] is not None:
            setattr(st, k, patch[k])
    st.version += 1
    st.updated_at = now()
    v = StrategyVersion(strategy_id=st.id, version=st.version, title=st.title, status=st.status, basis=st.basis, body=st.body, by=user_id)
    s.add(v)
    s.flush()
    s.add(StrategyVersionNote(version_id=v.id, note=note))


def create_strategy(title, kind, status, basis, body, user_id) -> int:
    if status not in ("未验证经验", "历史观察"):
        raise ApprovalError("新增结论只能是“未验证经验”或“历史观察”；改为已验证需老板批准")
    if not (title or "").strip() or kind not in STRAT_KINDS or not (basis or "").strip():
        raise ApprovalError("结论、类型、依据都要填写")
    with session() as s:
        n = len(list(s.scalars(select(Strategy.id)))) + 1
        codes = {c for (c,) in s.execute(select(Strategy.code))}
        while f"SL-{n:02d}" in codes:
            n += 1
        st = Strategy(code=f"SL-{n:02d}", title=title.strip(), kind=kind, status=status, version=1, basis=basis.strip(), body=(body or "").strip())
        s.add(st)
        s.flush()
        v = StrategyVersion(strategy_id=st.id, version=1, title=st.title, status=status, basis=st.basis, body=st.body, by=user_id)
        s.add(v)
        s.flush()
        s.add(StrategyVersionNote(version_id=v.id, note="新增"))
        return st.id


def update_strategy(sid, title, status, basis, body, note, user_id) -> int:
    with session() as s:
        st = s.get(Strategy, sid)
        if status == "已验证" and st.status != "已验证":
            raise ApprovalError("改为“已验证”要走申请，经老板批准才生效")
        if status not in STRAT_STATUS:
            raise ApprovalError("状态只能是三种之一")
        patch = dict(title=(title or st.title).strip(), status=status, basis=(basis or st.basis).strip(), body=(body if body is not None else st.body))
        if all(getattr(st, k) == v for k, v in patch.items()):
            return st.version
        _new_version(s, st, patch, user_id, (note or "").strip() or "修改")
        return st.version


def pending_request(s, sid):
    return s.scalar(select(Approval).where(Approval.obj_type == "strategy", Approval.obj_id == sid, Approval.status == "pending"))


def apply_verified(sid, basis, user_id) -> int:
    if not (basis or "").strip():
        raise ApprovalError("请填写申请依据")
    with session() as s:
        st = s.get(Strategy, sid)
        if st.status == "已验证":
            raise ApprovalError("这条已经是已验证")
        if pending_request(s, sid):
            raise ApprovalError("已有待审批申请")
        a = Approval(obj_type="strategy", obj_id=sid, obj_version=st.version, submitted_by=user_id)
        s.add(a)
        s.flush()
        s.add(StrategyRequest(approval_id=a.id, strategy_id=sid, from_status=st.status, to_status="已验证", basis=basis.strip()))
        return a.id


def versions(s, sid):
    out = []
    for v in s.scalars(select(StrategyVersion).where(StrategyVersion.strategy_id == sid).order_by(StrategyVersion.version.desc())):
        n = s.scalar(select(StrategyVersionNote).where(StrategyVersionNote.version_id == v.id))
        out.append(dict(version=v.version, title=v.title, status=v.status, basis=v.basis, body=v.body, at=v.at,
                        by=_uname(s, v.by) if v.by else "系统", note=n.note if n else ""))
    return out


def fmt_dt(v: datetime | None):
    return v.strftime("%Y-%m-%d %H:%M") if v else "—"
