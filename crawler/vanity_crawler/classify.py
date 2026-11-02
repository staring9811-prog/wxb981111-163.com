import re

# A product is a whole vanity if the title (or URL slug) names a vanity, unless the vanity word is only
# describing an accessory (vanity top / mirror / light / stool ...) or the item is a different cabinet type.
WHOLE = re.compile(r"vanity (with|set|cabinet|base|combo)\b|bathroom vanit(y|ies)\b(?! (top|mirror|light|lighting|stool|bench|tray))|\bvanity\b.*\bcombo\b")
ACCESSORY = [
    (r"\bvanity tops?\b", "排除-非整柜（台面）"),
    (r"\bvanity (mirror|mirrors)\b|\bmirror\b(?!.*\bvanity\b)", "排除-非整柜（镜子）"),
    (r"\bvanity (light|lights|lighting|fixture)\b", "排除-非整柜（灯具）"),
    (r"\bvanity (stool|bench|chair|tray|organizer)\b", "排除-非整柜（配件）"),
    (r"\bmedicine cabinet\b", "排除-非整柜（镜柜）"),
    (r"\b(linen|side|storage|wall|over[- ]the[- ]toilet) cabinet\b(?!.*\bvanity\b)", "排除-非整柜（侧柜/储物柜）"),
    (r"\bfaucet\b(?!.*\bvanity\b)", "排除-非整柜（龙头）"),
    (r"\b(vessel|undermount|drop-in) sink\b(?!.*\bvanity\b)", "排除-非整柜（台盆）"),
]


def include_reason(title, category_hint=""):
    """Return '纳入' or an exclusion reason based on the product title / URL slug."""
    t = (title or "").lower().replace("-", " ").replace("vantiy", "vanity")
    in_category = "vanit" in (category_hint or "").lower()
    if "vanit" not in t and not in_category:
        return "排除-非整柜（标题无 vanity）"
    if WHOLE.search(t) or re.search(r"\bsink base\b|\bbath(room)? cabinet\b.*\b(base|only)\b|\b(single|double) sink\b.*\btop\b", t):
        return "纳入"
    for pat, reason in ACCESSORY:
        if re.search(pat, t):
            return reason
    return "纳入"
