"""决策组追加的表（由 db.init_db 自动加载）。决策卡、审批、策略库、台账、利润方案的主表在 models.py。"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import Cat, now


class CardEvent(Base):
    """决策卡的版本与审批记录时间线（PAGE-F21-02 侧栏）：生成、编辑叙述、提交、审批、另存、回写利润等。"""
    __tablename__ = "card_event"
    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("card.id"))
    at: Mapped[datetime] = mapped_column(DateTime, default=now)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(16))  # create / edit / submit / approve / reject / return / save_as / profit / reviews / draft
    text: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = Cat()


class StrategyRequest(Base):
    """策略库"申请改为已验证"的申请内容（审批记录在 Approval，obj_type=strategy）。"""
    __tablename__ = "strategy_request"
    id: Mapped[int] = mapped_column(primary_key=True)
    approval_id: Mapped[int] = mapped_column(ForeignKey("approval.id"))
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategy.id"))
    from_status: Mapped[str] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16), default="已验证")
    basis: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = Cat()


class StrategyVersionNote(Base):
    """策略库每个版本的修改说明与修改人姓名（版本历史里显示）。"""
    __tablename__ = "strategy_version_note"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("strategy_version.id"))
    note: Mapped[str] = mapped_column(Text, default="")


class ProfitQuote(Base):
    """利润测算“报价库”的一个报价版本（工厂 + 版本名 + 日期 + 产品条目），存服务端供局域网共享（AC-F24-02）。"""
    __tablename__ = "profit_quote"
    id: Mapped[int] = mapped_column(primary_key=True)
    factory: Mapped[str] = mapped_column(String(128), default="")
    version: Mapped[str] = mapped_column(String(128), default="")
    date: Mapped[str] = mapped_column(String(10), default="")
    source: Mapped[str] = mapped_column(Text, default="")
    items: Mapped[list] = mapped_column(JSON, default=list)
    saved_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    saved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str] = Cat()
