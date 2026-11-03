"""Decide whether a listed product belongs to the target category.

Config (cfg["filters"]):
  preset            : optional built-in rule set, e.g. "bathroom_vanity"
  include_keywords  : title must contain at least one (empty = no requirement; products come from a category page)
  exclude_keywords  : title containing any of these is excluded ...
  keep_keywords     : ... unless it also contains one of these (e.g. "vanity with" keeps "vanity with faucet")
"""
import re

PRESETS = {}

# ---- preset: bathroom vanity (validated on HDP / Lowe's / Wayfair, Nov 2026)
_V_WHOLE = re.compile(r"vanity (with|set|cabinet|base|combo)\b|bathroom vanit(y|ies)\b(?! (top|mirror|light|lighting|stool|bench|tray))|\bvanity\b.*\bcombo\b")
_V_ACC = [
    (r"\bvanity tops?\b", "台面"), (r"\bvanity (mirror|mirrors)\b|\bmirror\b(?!.*\bvanity\b)", "镜子"),
    (r"\bvanity (light|lights|lighting|fixture)\b", "灯具"), (r"\bvanity (stool|bench|chair|tray|organizer)\b", "配件"),
    (r"\bmedicine cabinet\b", "镜柜"), (r"\b(linen|side|storage|wall|over[- ]the[- ]toilet) cabinet\b(?!.*\bvanity\b)", "侧柜/储物柜"),
    (r"\bfaucet\b(?!.*\bvanity\b)", "龙头"), (r"\b(vessel|undermount|drop-in) sink\b(?!.*\bvanity\b)", "台盆"),
]


def _vanity(t):
    if _V_WHOLE.search(t) or re.search(r"\bsink base\b|\bbath(room)? cabinet\b.*\b(base|only)\b|\b(single|double) sink\b.*\btop\b", t):
        return "纳入"
    for pat, what in _V_ACC:
        if re.search(pat, t):
            return f"排除-非目标（{what}）"
    return "纳入"


PRESETS["bathroom_vanity"] = _vanity


def _norm(s):
    return (s or "").lower().replace("-", " ")


def include_reason(title, filters):
    t = _norm(title)
    inc = [_norm(k) for k in filters.get("include_keywords") or [] if k.strip()]
    exc = [_norm(k) for k in filters.get("exclude_keywords") or [] if k.strip()]
    keep = [_norm(k) for k in filters.get("keep_keywords") or [] if k.strip()]
    if inc and not any(k in t for k in inc):
        return "排除-非目标（标题不含必含词）"
    if keep and any(k in t for k in keep):
        return "纳入"
    for k in exc:
        if k in t:
            return f"排除-非目标（含排除词 {k}）"
    p = PRESETS.get(filters.get("preset") or "")
    return p(t) if p else "纳入"
