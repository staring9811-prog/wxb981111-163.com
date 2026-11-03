"""SQLite（WAL）+ SQLAlchemy。"""
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import data_dir


class Base(DeclarativeBase):
    pass


_engine = None
_Session = None


def engine():
    global _engine, _Session
    if _engine is None:
        _engine = create_engine(f"sqlite:///{data_dir() / 'pdt.sqlite3'}", connect_args={"check_same_thread": False})

        @event.listens_for(_engine, "connect")
        def _pragma(conn, _):
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        _Session = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def reset_engine():
    """测试切换数据目录时调用。"""
    global _engine, _Session
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _Session = None


def init_db():
    import importlib
    from . import models  # noqa: F401  注册全部表
    for ext in ("models_settings", "models_data", "models_decision", "models_channel"):  # 各模块组追加的表
        try:
            importlib.import_module(f"{__package__}.{ext}")
        except ModuleNotFoundError as e:
            if e.name != f"{__package__}.{ext}":
                raise
    Base.metadata.create_all(engine())


@contextmanager
def session():
    engine()
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
