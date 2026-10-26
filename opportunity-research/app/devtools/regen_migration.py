"""Development helper: regenerate the single initial migration from oppo.db.metadata.

Only valid before the first release (no deployed databases). Appends the append-only
triggers to the generated upgrade()."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

import oppo.migrations as mig

versions = mig.HERE / "versions"
for f in versions.glob("*.py"):
    f.unlink()
with tempfile.TemporaryDirectory() as tmp:
    eng = create_engine(f"sqlite:///{Path(tmp) / 'x.db'}")
    cfg = Config()
    cfg.set_main_option("script_location", str(mig.HERE))
    with eng.begin() as conn:
        cfg.attributes["connection"] = conn
        command.revision(cfg, message="initial schema", autogenerate=True, rev_id="0001")
path = next(versions.glob("0001*.py"))
src = path.read_text(encoding="utf-8")
src = src.replace("from alembic import op\n", "from alembic import op\n\nfrom oppo.db import drop_trigger_sql, trigger_sql\n", 1)
src = re.sub(r"(def upgrade\(\) -> None:\n(?:.*\n)*?    # ### end Alembic commands ###\n)",
             r"\1    for stmt in trigger_sql():\n        op.execute(stmt)\n", src, count=1)
src = re.sub(r"(def downgrade\(\) -> None:\n)", r"\1    for stmt in drop_trigger_sql():\n        op.execute(stmt)\n", src, count=1)
path.write_text(src, encoding="utf-8")
print("wrote", path)
