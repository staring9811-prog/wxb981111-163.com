from __future__ import annotations

from alembic import context

from oppo.db import metadata

config = context.config
connection = config.attributes.get("connection")
if connection is None:  # pragma: no cover - only used when alembic CLI is pointed here
    from sqlalchemy import create_engine

    connection = create_engine(config.get_main_option("sqlalchemy.url")).connect()

context.configure(connection=connection, target_metadata=metadata, render_as_batch=True)
with context.begin_transaction():
    context.run_migrations()
