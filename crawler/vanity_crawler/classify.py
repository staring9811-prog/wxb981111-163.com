import re

NON_VANITY = [
    (r"\bvanity top\b(?!.*\bvanity with\b)", "排除-非整柜（台面）"),
    (r"\bvanity tops?\b only", "排除-非整柜（台面）"),
    (r"\bmirror\b(?!.*vanity)", "排除-非整柜（镜子）"),
    (r"\bmedicine cabinet\b", "排除-非整柜（镜柜）"),
    (r"\b(linen|side|storage|wall|over[- ]the[- ]toilet) cabinet\b", "排除-非整柜（侧柜/储物柜）"),
    (r"\bfaucet\b(?!.*vanity)", "排除-非整柜（龙头）"),
    (r"\b(vessel|undermount|drop-in) sink\b(?!.*vanity)", "排除-非整柜（台盆）"),
    (r"\b(hardware|knob|pull|backsplash|leg kit)\b(?!.*vanity)", "排除-非整柜（配件）"),
]


def include_reason(title, category_hint=""):
    """Return '纳入' or an exclusion reason based on the product title."""
    t = (title or "").lower()
    if "vanit" not in t and "vanit" not in category_hint.lower():
        return "排除-非整柜（标题无 vanity）"
    for pat, reason in NON_VANITY:
        if re.search(pat, t):
            # 'Vanity with ... Top' is a full vanity
            if "top" in reason and re.search(r"vanity (cabinet )?with .*top", t):
                continue
            return reason
    return "纳入"
