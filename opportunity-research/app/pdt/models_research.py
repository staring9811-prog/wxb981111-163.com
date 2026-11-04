"""渠道调研（F30）追加的表，由 db.init_db 自动加载。不写入其他渠道分析库（Batch / Snapshot，AC-F30-08）。

- DATA-F30-01：ResearchImport（一次上传的核对：文件、哈希、核对摘要、状态 待确认 / 已确认 / 已放弃、操作人、来源 导入 / 系统抓取）
  与 ResearchVersion（按渠道的调研版本：当前 / 已替换）。
- DATA-F30-02：ResearchProduct / ResearchMonthly（按版本存的商品与月销）、ResearchResult（按渠道的计算结果缓存与重算时间、出错原因）、
  ResearchOverride（多尺寸未拆选“不进框”；其余分框确认写 Tag，与机会扫描共用，RA-120）。
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import Cat, now


class ResearchImport(Base):
    __tablename__ = "research_import"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending 待确认 / confirmed 已确认 / abandoned 已放弃
    source: Mapped[str] = mapped_column(String(16), default="导入")  # 导入 / 系统抓取（第二版）
    files: Mapped[dict] = mapped_column(JSON, default=dict)  # {products: 文件名, monthly: 文件名, products_sha, monthly_sha, dir}
    summary: Mapped[dict] = mapped_column(JSON, default=dict)  # 按渠道核对摘要（含冲突逐月）
    imported: Mapped[list] = mapped_column(JSON, default=list)  # 确认导入的渠道
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    category: Mapped[str] = Cat()


class ResearchVersion(Base):
    __tablename__ = "research_version"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(16))
    no: Mapped[int] = mapped_column(Integer, default=1)  # 该渠道第几版
    status: Mapped[str] = mapped_column(String(16), default="current")  # current 当前 / replaced 已替换
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    files: Mapped[dict] = mapped_column(JSON, default=dict)
    n_products: Mapped[int] = mapped_column(Integer, default=0)
    n_families: Mapped[int] = mapped_column(Integer, default=0)
    months: Mapped[list] = mapped_column(JSON, default=list)  # 窗口完整月 [起, 止]
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    category: Mapped[str] = Cat()
    __table_args__ = (Index("ix_rver", "category", "channel", "status"),)


class ResearchProduct(Base):
    __tablename__ = "research_product"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(Integer, index=True)
    channel: Mapped[str] = mapped_column(String(16))
    fam: Mapped[str] = mapped_column(String(64))
    pid: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text, default="")
    brand: Mapped[str] = mapped_column(String(128), default="")
    source: Mapped[str] = mapped_column(String(32), default="")  # 两词 / 类目节点 / 两者 / 同家族变体
    size: Mapped[str] = mapped_column(String(16), default="")
    asm: Mapped[str] = mapped_column(String(16), default="")
    form: Mapped[str] = mapped_column(String(16), default="")
    top: Mapped[str] = mapped_column(String(64), default="")
    color: Mapped[str] = mapped_column(String(32), default="")
    cab: Mapped[str] = mapped_column(String(32), default="")
    elements: Mapped[str] = mapped_column(String(128), default="")
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviews: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_month: Mapped[str] = mapped_column(String(7), default="")
    raw: Mapped[dict] = mapped_column(JSON, default=dict)  # 宽、选项段、多尺寸段、颜色 / 台面 / 柜体原值、月度来源、浴室柜


class ResearchMonthly(Base):
    __tablename__ = "research_monthly"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(Integer, index=True)
    channel: Mapped[str] = mapped_column(String(16))
    fam: Mapped[str] = mapped_column(String(64))
    pid: Mapped[str] = mapped_column(String(64))
    size: Mapped[str] = mapped_column(String(16), default="")
    asm: Mapped[str] = mapped_column(String(16), default="")
    form: Mapped[str] = mapped_column(String(16), default="")
    month: Mapped[str] = mapped_column(String(7))
    vp: Mapped[float] = mapped_column(Float, default=0)
    nonvp: Mapped[float] = mapped_column(Float, default=0)
    units: Mapped[float] = mapped_column(Float, default=0)


class ResearchResult(Base):
    """按渠道的计算结果缓存（最近一次成功的结果 + 最近一次重算的状态）。出错时保留上次结果并记原因（DEC-106）。"""
    __tablename__ = "research_result"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(16))
    version_id: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 当前显示结果的计算时间
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok / running / error
    error: Mapped[str] = mapped_column(Text, default="")
    error_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    category: Mapped[str] = Cat()
    __table_args__ = (Index("ix_rres", "category", "channel"),)


class ResearchOverride(Base):
    """调研专用的分框决定：多尺寸未拆选“不进框”（AC-F30-28）。按渠道 + pid 保留，再导入仍有效（AC-F30-30）。"""
    __tablename__ = "research_override"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(16))
    pid: Mapped[str] = mapped_column(String(64))
    tag: Mapped[str] = mapped_column(String(16), default="尺寸段")
    value: Mapped[str] = mapped_column(String(32), default="不进框")
    by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=now)
    category: Mapped[str] = Cat()
    __table_args__ = (Index("ix_rovr", "category", "channel", "pid"),)
