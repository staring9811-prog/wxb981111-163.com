"""全部数据表（技术方案附录 A.2）。所有业务表带品类与渠道字段。"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from .config import CATEGORY
from .db import Base


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def Cat():
    return mapped_column(String(32), default=CATEGORY)


# ---------- DATA-F15-01 / 02 账号、会话、审计 ----------
class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(16))  # operator / approver / readonly
    pw_hash: Mapped[str] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LoginSession(Base):
    __tablename__ = "login_session"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=now)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(16))  # login / approve / key / spend / account / other
    content: Mapped[str] = mapped_column(Text)
    ip: Mapped[str] = mapped_column(String(64), default="")


# ---------- DATA-F16-01 / 02 / 03 密钥、预算、费用、任务 ----------
class Secret(Base):
    __tablename__ = "secret"
    slot: Mapped[str] = mapped_column(String(32), primary_key=True)
    enc_value: Mapped[bytes] = mapped_column()
    last4: Mapped[str] = mapped_column(String(8))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    test_status: Mapped[str] = mapped_column(String(16), default="")  # ok / auth / network / quota / error
    test_msg: Mapped[str] = mapped_column(Text, default="")
    tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Setting(Base):
    __tablename__ = "setting"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class Budget(Base):
    __tablename__ = "budget"
    service: Mapped[str] = mapped_column(String(32), primary_key=True)
    cap: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(8))  # usd / calls


class CostRecord(Base):
    __tablename__ = "cost_record"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=now)
    month: Mapped[str] = mapped_column(String(7))  # 计费所属自然月 YYYY-MM
    service: Mapped[str] = mapped_column(String(32))
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    task: Mapped[str] = mapped_column(String(128))
    qty: Mapped[float] = mapped_column(Float)  # 调用次数 / 请求数 / token 等
    amount: Mapped[float] = mapped_column(Float)  # 美元
    source: Mapped[str] = mapped_column(String(64), default="")


class Job(Base):
    __tablename__ = "job"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))  # amazon_pull / tagging / vision / reviews / llm_draft / classify / vp_collect ...
    month: Mapped[str] = mapped_column(String(7), default="")
    target: Mapped[str] = mapped_column(String(128), default="")  # 关联对象，如 card:12
    status: Mapped[str] = mapped_column(String(16), default="estimated")
    # estimated → running → done / failed / stopped_cap / paused / cancelled
    estimate: Mapped[dict] = mapped_column(JSON, default=dict)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    category: Mapped[str] = Cat()


class Shard(Base):
    """分片完成记录。唯一键：任务类型 + 月份 + 分片键。重跑时跳过已完成分片（NFR-011）。"""
    __tablename__ = "shard"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    month: Mapped[str] = mapped_column(String(7))
    key: Mapped[str] = mapped_column(String(256))
    job_id: Mapped[int] = mapped_column(Integer)
    done_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    payload_path: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = Cat()
    __table_args__ = (UniqueConstraint("category", "kind", "month", "key"),)


# ---------- DATA-F17-01 / 02 月度批次、商品、快照 ----------
class Batch(Base):
    __tablename__ = "batch"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(16))
    month: Mapped[str] = mapped_column(String(7))
    source: Mapped[str] = mapped_column(String(16))  # api / upload / tracker
    file_path: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16))  # suspect_month / anomaly / ok / merged / rejected
    checks: Mapped[dict] = mapped_column(JSON, default=dict)
    anomaly_reason: Mapped[str] = mapped_column(Text, default="")
    star: Mapped[bool] = mapped_column(Boolean, default=False)
    rows: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    merged_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str] = Cat()


class Product(Base):
    __tablename__ = "product"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(16))
    item_id: Mapped[str] = mapped_column(String(64))  # ASIN / 商品 ID
    parent: Mapped[str] = mapped_column(String(64), default="")
    family_key: Mapped[str] = mapped_column(String(128), default="")
    series: Mapped[str] = mapped_column(String(128), default="")
    brand: Mapped[str] = mapped_column(String(128), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(Text, default="")
    listed_at: Mapped[str] = mapped_column(String(10), default="")
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)  # 看不出 / 不是本品类（AC-F18-06）
    excluded_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    excluded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    category: Mapped[str] = Cat()
    __table_args__ = (UniqueConstraint("category", "channel", "item_id"),)


class Snapshot(Base):
    __tablename__ = "snapshot"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batch.id"))
    channel: Mapped[str] = mapped_column(String(16))
    month: Mapped[str] = mapped_column(String(7))
    item_id: Mapped[str] = mapped_column(String(64))
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    units: Mapped[float | None] = mapped_column(Float, nullable=True)  # 月销（其他渠道为估算）
    revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    rank: Mapped[float | None] = mapped_column(Float, nullable=True)  # 小类排名 / 榜单名次
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    ratings_count: Mapped[float | None] = mapped_column(Float, nullable=True)
    vp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nonvp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    category: Mapped[str] = Cat()
    __table_args__ = (Index("ix_snap_cm", "category", "channel", "month", "item_id"),)


class ChannelReview(Base):
    """其他渠道评论明细（按评论 ID 去重，AC-F28-05）。"""
    __tablename__ = "channel_review"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(16))
    review_id: Mapped[str] = mapped_column(String(128))
    item_id: Mapped[str] = mapped_column(String(64))
    series: Mapped[str] = mapped_column(String(128), default="")
    month: Mapped[str] = mapped_column(String(7))
    vp: Mapped[bool] = mapped_column(Boolean, default=False)
    stars: Mapped[float | None] = mapped_column(Float, nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")
    date: Mapped[str] = mapped_column(String(10), default="")
    category: Mapped[str] = Cat()
    __table_args__ = (UniqueConstraint("category", "channel", "review_id", "item_id"),)


# ---------- DATA-F18-01 标签 ----------
class Tag(Base):
    __tablename__ = "tag"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(16))
    item_id: Mapped[str] = mapped_column(String(64))
    tag: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(128), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(16))  # rule / vision / manual
    status: Mapped[str] = mapped_column(String(16))  # auto / queued / confirmed
    auto_value: Mapped[str] = mapped_column(String(128), default="")
    candidates: Mapped[list] = mapped_column(JSON, default=list)
    img_group: Mapped[str] = mapped_column(String(64), default="")
    confirm_mode: Mapped[str] = mapped_column(String(16), default="")  # group / single
    confirmed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    month: Mapped[str] = mapped_column(String(7), default="")
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    category: Mapped[str] = Cat()
    __table_args__ = (UniqueConstraint("category", "channel", "item_id", "tag"),)


# ---------- DATA-F19-01 / F20-01 模型、评分、机会 ----------
class ModelRun(Base):
    __tablename__ = "model_run"
    id: Mapped[int] = mapped_column(primary_key=True)
    month: Mapped[str] = mapped_column(String(7))  # 最新数据月
    version: Mapped[str] = mapped_column(String(16), default="第九版")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    market: Mapped[dict] = mapped_column(JSON, default=dict)  # 系数、校准
    newlayer: Mapped[dict] = mapped_column(JSON, default=dict)  # 模型偏差等
    backtest: Mapped[dict] = mapped_column(JSON, default=dict)
    valid: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_msg: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = Cat()


class UnitScore(Base):
    __tablename__ = "unit_score"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("model_run.id"))
    channel: Mapped[str] = mapped_column(String(16), default="amazon")
    frame: Mapped[str] = mapped_column(String(128))
    attr: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(128))
    data: Mapped[dict] = mapped_column(JSON, default=dict)  # 把握、分级、份额预测与区间、做到概率等
    category: Mapped[str] = Cat()


class Opportunity(Base):
    __tablename__ = "opportunity"
    id: Mapped[int] = mapped_column(primary_key=True)
    month: Mapped[str] = mapped_column(String(7))
    channel: Mapped[str] = mapped_column(String(16))
    frame: Mapped[str] = mapped_column(String(128))
    attr: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16), default="")  # 增长型 / 评分缺口型 / 价格缺口型 / 坑 / ""
    evidence: Mapped[str] = mapped_column(String(16), default="未验证")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    category: Mapped[str] = Cat()
    __table_args__ = (Index("ix_opp", "category", "channel", "month"),)


# ---------- DATA-F21-01 决策卡 ----------
class Card(Base):
    __tablename__ = "card"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(16))  # 主渠道
    frame: Mapped[str] = mapped_column(String(128))
    attr: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # draft → pending → approved / rejected；pending → draft（退回）；approved → tracking → reconciled
    version: Mapped[int] = mapped_column(Integer, default=1)
    numbers: Mapped[dict] = mapped_column(JSON, default=dict)  # 生成时计算的数字（含来源）
    snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 批准时的数字快照（AC-F25-02）
    narrative: Mapped[dict] = mapped_column(JSON, default=dict)  # 叙述字段；ai_draft 标记
    data_month: Mapped[str] = mapped_column(String(7), default="")
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 另存为新草稿的来源
    profit_plan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    category: Mapped[str] = Cat()


class CardReview(Base):
    """决策卡上的差评与归类（DATA-F22-01）。"""
    __tablename__ = "card_review"
    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("card.id"))
    channel: Mapped[str] = mapped_column(String(16))
    item_id: Mapped[str] = mapped_column(String(64))
    review_id: Mapped[str] = mapped_column(String(128))
    stars: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text, default="")
    date: Mapped[str] = mapped_column(String(10), default="")
    reason: Mapped[str] = mapped_column(String(32), default="")
    reason_source: Mapped[str] = mapped_column(String(16), default="")  # auto / manual
    __table_args__ = (UniqueConstraint("card_id", "channel", "review_id"),)


# ---------- DATA-F24-01 利润方案 ----------
class ProfitPlan(Base):
    __tablename__ = "profit_plan"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    data: Mapped[dict] = mapped_column(JSON, default=dict)  # 原利润测算台方案 JSON
    result: Mapped[dict] = mapped_column(JSON, default=dict)  # 各渠道单件利润、利润率、保本价
    card_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str] = Cat()


# ---------- DATA-F25-01 / 02 审批、策略库 ----------
class Approval(Base):
    __tablename__ = "approval"
    id: Mapped[int] = mapped_column(primary_key=True)
    obj_type: Mapped[str] = mapped_column(String(16))  # card / strategy
    obj_id: Mapped[int] = mapped_column(Integer)
    obj_version: Mapped[int] = mapped_column(Integer, default=1)
    submitted_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending / done
    decision: Mapped[str] = mapped_column(String(16), default="")  # approve / reject / return
    decided_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = Cat()


class Strategy(Base):
    __tablename__ = "strategy"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16))  # 分框信号 / 条件表 / 经验
    status: Mapped[str] = mapped_column(String(16))  # 未验证经验 / 历史观察 / 已验证
    version: Mapped[int] = mapped_column(Integer, default=1)
    basis: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    category: Mapped[str] = Cat()


class StrategyVersion(Base):
    __tablename__ = "strategy_version"
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategy.id"))
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    basis: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime, default=now)
    by: Mapped[int | None] = mapped_column(Integer, nullable=True)


# ---------- DATA-F26-01 预测台账 ----------
class Forecast(Base):
    __tablename__ = "forecast"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16))  # TZ-2026-08
    card_id: Mapped[int] = mapped_column(ForeignKey("card.id"))
    card_version: Mapped[int] = mapped_column(Integer)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    frame: Mapped[str] = mapped_column(String(128))
    attr: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(128))
    grade: Mapped[str] = mapped_column(String(4), default="")
    grasp: Mapped[float | None] = mapped_column(Float, nullable=True)
    share_lo: Mapped[float | None] = mapped_column(Float, nullable=True)
    share_hi: Mapped[float | None] = mapped_column(Float, nullable=True)
    prob_raw: Mapped[float | None] = mapped_column(Float, nullable=True)
    prob_adj: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_conditions: Mapped[list] = mapped_column(JSON, default=list)
    launch_month: Mapped[str] = mapped_column(String(7))
    channels: Mapped[list] = mapped_column(JSON, default=list)
    own_items: Mapped[dict] = mapped_column(JSON, default=dict)  # {channel: [item_id,...]}
    result: Mapped[dict] = mapped_column(JSON, default=dict)  # {channel: {made, basis, stop_triggered, month}}
    status: Mapped[str] = mapped_column(String(16), default="tracking")  # tracking / due / reconciled / unlinked
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    params_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str] = Cat()


# ---------- DATA-F27-01 品类配置 ----------
class CategoryConfig(Base):
    __tablename__ = "category_config"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    diff: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str] = Cat()
    __table_args__ = (UniqueConstraint("category", "version"),)
