"""Alembic migration chain, run programmatically so the offline package needs no alembic.ini."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

HERE = Path(__file__).resolve().parent


def _ini(value: str) -> str:
    """Alembic keeps options in a ConfigParser: a literal % must be doubled (Windows URLs carry %5C for \\)."""
    return value.replace("%", "%%")


def _config(engine: Engine) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", _ini(str(HERE)))
    cfg.set_main_option("sqlalchemy.url", _ini(engine.url.render_as_string(hide_password=False)))
    return cfg


def upgrade(engine: Engine) -> None:
    cfg = _config(engine)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
