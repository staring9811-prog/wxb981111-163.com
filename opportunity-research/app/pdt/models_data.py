"""分析组（数据 / 打标 / 模型 / 扫描）追加的数据表。只追加，不改 models.py 已有表的字段含义。"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import Cat, now


class SearchVolume(Base):
    """搜索量（第九版特征 x3 搜索同比的来源）：关键词 × 月；维度 / 取值 = 该词对应的大属性取值。"""
    __tablename__ = "search_volume"
    id: Mapped[int] = mapped_column(primary_key=True)
    dim: Mapped[str] = mapped_column(String(16))  # 尺寸 / 台面 / 元素 / 主色 / 形态
    value: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(16))  # amazon / google
    keyword: Mapped[str] = mapped_column(String(256))
    month: Mapped[str] = mapped_column(String(7))
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    category: Mapped[str] = Cat()
    __table_args__ = (Index("ix_sv", "category", "dim", "value"),)


class ScanMeta(Base):
    """一次扫描的元信息（渠道 × 数据截至月）：近期 / 前期月份、框数、计算耗时。Opportunity 行按同一 (channel, month) 关联。"""
    __tablename__ = "scan_meta"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(16))
    month: Mapped[str] = mapped_column(String(7))  # 数据截至月（含）
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    category: Mapped[str] = Cat()
    __table_args__ = (Index("ix_scanmeta", "category", "channel", "month"),)


class DataNote(Base):
    """数据页上的操作留痕（并入、放弃、异常确认说明），供历史月份列表显示。"""
    __tablename__ = "data_note"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(DateTime, default=now)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(16))  # merge / reject / anomaly_confirm / pull
    text: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = Cat()


# ---------- DATA-F28-02 渠道历史回补与重建（REQ-F28-03、REQ-F23-02、REQ-F18-04） ----------

class ChannelHistReview(Base):
    """渠道历史评论明细：回补采到的全部历史评论，按评论 ID 唯一（一条评论只计一次）。item_id = 写评论时的商品页。"""
    __tablename__ = "channel_hist_review"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(16))
    review_id: Mapped[str] = mapped_column(String(128))
    item_id: Mapped[str] = mapped_column(String(64))
    family_key: Mapped[str] = mapped_column(String(128))
    date: Mapped[str] = mapped_column(String(10))
    month: Mapped[str] = mapped_column(String(7))
    stars: Mapped[float | None] = mapped_column(Float, nullable=True)
    vp: Mapped[bool] = mapped_column(Boolean, default=False)
    syndicated: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str] = Cat()
    __table_args__ = (UniqueConstraint("category", "channel", "review_id"), Index("ix_chr_fam", "category", "channel", "family_key"))


class ChannelPageSpec(Base):
    """商品页规格：回补（或月度追踪）抓到的商品页规格字段，供规格优先打标（AC-F18-08）。listed = 在类目榜单前 N 内。"""
    __tablename__ = "channel_page_spec"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(16))
    item_id: Mapped[str] = mapped_column(String(64))
    family_key: Mapped[str] = mapped_column(String(128), default="")
    listed: Mapped[bool] = mapped_column(Boolean, default=False)
    entry: Mapped[str] = mapped_column(String(64), default="")  # 类目入口（带台面 / 无台面 …）
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 采集日的类目榜单排名（排除广告位）
    title: Mapped[str] = mapped_column(Text, default="")
    brand: Mapped[str] = mapped_column(String(128), default="")
    price: Mapped[float | None] = mapped_column(Float, nullable=True)  # 采集日当天价
    specs: Mapped[dict] = mapped_column(JSON, default=dict)
    highlights: Mapped[list] = mapped_column(JSON, default=list)
    page_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discontinued: Mapped[bool] = mapped_column(Boolean, default=False)
    collected_on: Mapped[str] = mapped_column(String(10), default="")
    category: Mapped[str] = Cat()
    __table_args__ = (UniqueConstraint("category", "channel", "item_id"),)


class ChannelFamily(Base):
    """评论家族（AC-F28-07）：共享同一批评论的商品页合并成一个家族，家族是该渠道份额计算单位。members = 榜单前 N 内的成员商品页。"""
    __tablename__ = "channel_family"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(16))
    family_key: Mapped[str] = mapped_column(String(128))
    members: Mapped[list] = mapped_column(JSON, default=list)
    variants: Mapped[list] = mapped_column(JSON, default=list)  # 起始月以来有评论的全部商品页（含不在前 N 的）
    best_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    brand: Mapped[str] = mapped_column(String(128), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    first_review: Mapped[str] = mapped_column(String(10), default="")  # 家族首条评论（≈ 上架）
    status: Mapped[str] = mapped_column(String(16), default="")  # 完整 / 截断 / 失败 / 无评论
    complete_to: Mapped[str] = mapped_column(String(10), default="")  # 截断时只完整到该日
    sharded: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否做过星级 / VP 分片补采
    note: Mapped[str] = mapped_column(Text, default="")
    reviews_window: Mapped[int] = mapped_column(Integer, default=0)  # 起始月至最后完整月的评论数
    vp_window: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = Cat()
    __table_args__ = (UniqueConstraint("category", "channel", "family_key"),)


class ChannelRebuild(Base):
    """一次历史重建的结果摘要（API-F28-02）：月份范围、商品页 / 家族 / 评论数、截断、覆盖估计、换手、季度历史。"""
    __tablename__ = "channel_rebuild"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(16))
    at: Mapped[datetime] = mapped_column(DateTime, default=now)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    category: Mapped[str] = Cat()
