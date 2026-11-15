"""设置组追加的表（由 db.init_db 自动加载）。"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import Cat, now


class ConfigNote(Base):
    """品类配置参数版本的修改说明（PAGE-F27-01 保存弹窗里的“修改说明”）。CategoryConfig 只存差异，说明单独存。"""
    __tablename__ = "config_note"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime, default=now)
    category: Mapped[str] = Cat()
    __table_args__ = (UniqueConstraint("category", "version"),)

