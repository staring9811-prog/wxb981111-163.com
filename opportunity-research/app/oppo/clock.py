"""Single source of "now" so step timing (F14) can be driven by a controllable clock.

OPPO_CLOCK_FILE: path to a text file holding an ISO local datetime; when set and the
file exists, now() returns that value (tests move time by rewriting the file).
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path


def now() -> datetime:
    path = os.environ.get("OPPO_CLOCK_FILE")
    if path:
        p = Path(path)
        if p.exists():
            text = p.read_text(encoding="utf-8").strip()
            if text:
                return datetime.fromisoformat(text)
    return datetime.now().replace(microsecond=0)


def now_iso() -> str:
    return now().isoformat(sep=" ", timespec="seconds")
