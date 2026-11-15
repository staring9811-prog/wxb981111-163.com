"""模型组追加的表（DATA-F19-02，由 db.init_db 自动加载）：分渠道模型运行与回测。不改 ModelRun 已有字段含义。"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import Cat, now


class ChannelModelRun(Base):
    """一次分渠道重算与滚动回测（REQ-F19-03）：数据截至月、参数版本、原值与打折后指标、证据等级“经回测（打折）/ 未验证”、有效性判定、
    本次各单元把握与分级（键“框|属性|取值”）、Amazon 侧丰富度信号的交叉验证结果。"""
    __tablename__ = "channel_model_run"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(16))
    month: Mapped[str] = mapped_column(String(7))  # 数据截至月
    start: Mapped[str] = mapped_column(String(7), default="")  # 重建起始月
    n_months: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config_version: Mapped[int] = mapped_column(Integer, default=1)  # 品类配置（打折参数）版本
    discount_params: Mapped[dict] = mapped_column(JSON, default=dict)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)  # 原值：把握四档、D 档、秩相关、方向对、逐时点
    discounted: Mapped[dict] = mapped_column(JSON, default=dict)  # 打折后读法
    validity: Mapped[dict] = mapped_column(JSON, default=dict)  # {mono, d_ok, valid, ups}
    valid: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence: Mapped[str] = mapped_column(String(16), default="未验证")
    reason: Mapped[str] = mapped_column(Text, default="")
    signals: Mapped[dict] = mapped_column(JSON, default=dict)
    units: Mapped[dict] = mapped_column(JSON, default=dict)
    now_info: Mapped[dict] = mapped_column(JSON, default=dict)  # 本次评分：立项时点、是否拟合、系数
    category: Mapped[str] = Cat()
    __table_args__ = (Index("ix_chrun", "category", "channel"),)


class ChannelRichness(Base):
    """跨渠道供给丰富度对照的预计算快照（AC-F29-05、NFR-009）：每次该渠道机会扫描后存一份，扫描页直接读，不必每次加载 Amazon 全表。
    data = richness.table() 的可 JSON 化结果（单元键“属性||尺寸段 · 形态||取值”）。"""
    __tablename__ = "channel_richness"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(16))
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    category: Mapped[str] = Cat()
