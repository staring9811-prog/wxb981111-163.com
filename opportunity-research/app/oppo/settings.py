"""Runtime settings: data directory, operator, port. Read from environment so the
CLI, the web app and tests can point at separate databases."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _default_data_dir() -> Path:
    env = os.environ.get("OPPO_DATA_DIR")
    if env:
        return Path(env)
    # Offline package layout: <install>/app/oppo -> <install>/data
    here = Path(__file__).resolve()
    install_root = here.parents[2]
    if (install_root / "启动.bat").exists() or (install_root / "data").exists():
        return install_root / "data"
    return Path.home() / ".oppo-data"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    operator: str
    port: int

    @property
    def db_path(self) -> Path:
        return self.data_dir / "oppo.sqlite3"

    @property
    def packages_dir(self) -> Path:
        return self.data_dir / "packages"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"


def load() -> Settings:
    data_dir = _default_data_dir()
    return Settings(
        data_dir=data_dir,
        operator=os.environ.get("OPPO_OPERATOR", "wen"),
        port=int(os.environ.get("OPPO_PORT", "8765")),
    )
