"""分析组（数据 / 打标 / 模型 / 扫描）追加的数据表。只追加，不改 models.py 已有表的字段含义。"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, Text
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
