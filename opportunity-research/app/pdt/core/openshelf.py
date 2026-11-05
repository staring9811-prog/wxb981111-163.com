"""开放式（不带门的开放层板）判定（AC-F18-10，wen 2026-11-05：开放式从落地式分出、单独成框）。

正则与排除项逐字移植自 `solution-v2/数据准备/卖家精灵导出_打标.py` 第 5 点（柜体结构 = 开放式），与数据侧整理脚本同口径：
open shelf / open storage / open cubes / side shelves / two-tier shelf / console vanity 等算；前面带 no / not / without 的、
镜柜或药柜上的层板、放水管的柜内层板、门背置物架不算。
系统里只有标题、SKU 属性与商品页规格类型（没有五点描述），所以只看这些文字。
只靠泛指词（open storage、open space）判出的，可能说的是柜内空间（数据侧已知误判：Lowe's 5017604281 带门柜），置信度给低档、进确认队列。
"""
import html
import re

OPEN_RE = re.compile(r'\bopen(?:[ -]+(?:storage|display|side|bottom|lower|middle|upper|top|left|right|tier))*[ -]+(?:shel(?:f|ves|ving)|storage|cubb(?:y|ies)|cubes?|compartments?|spaces)\b'
                     r'|\bopening\s+(?:bottom\s+|lower\s+|side\s+)?shel(?:f|ves)\b'
                     r'|\bside\s+(?:open\s+)?(?:storage\s+)?shel(?:f|ves)\b'
                     r'|\b(?:2|3|two|three)[ -]tier(?:ed)?\s+(?:open\s+)?(?:side\s+)?(?:storage\s+)?shel(?:f|ves)\b'
                     r'|\bconsole\s+(?:vanity|sink|table)\b', re.I)
NEG_RE = re.compile(r'\b(?:no|not|without)\s+(?:an?\s+|any\s+)?$', re.I)
MIRROR_BEFORE = re.compile(r'\b(?:mirror|medicine)\s+cabinet\b[^.|]{0,40}$', re.I)
PIPES_AFTER = re.compile(r'^[^.|]{0,20}\b(?:accommodat\w*|fits?|for|around|hid(?:es?|ing))\s+(?:the\s+)?(?:pipes?|plumbing)\b', re.I)
DOOR_RACK_BEFORE = re.compile(r'\bdoors?\s+(?:features?|has|have|with|includes?)\s+(?:an?\s+)?$', re.I)
DOOR_RACK_AFTER = re.compile(r'^\s*(?:on|inside|behind|in)\b', re.I)
# 泛指词：只说"open storage / open space(s)"，没说层板、格子、隔间、console
GENERIC_RE = re.compile(r'^open(?:[ -]+(?:storage|display|side|bottom|lower|middle|upper|top|left|right|tier))*[ -]+(?:storage|spaces)$', re.I)

STRONG, WEAK = 'strong', 'weak'


def cue(text) -> str | None:
    """返回 'strong'（写明开放层板 / console）、'weak'（只有泛指词）或 None。"""
    t = html.unescape(str(text or ''))
    best = None
    for mm in OPEN_RE.finditer(t):
        before, after = t[max(0, mm.start() - 60):mm.start()], t[mm.end():mm.end() + 40]
        if NEG_RE.search(before[-20:]):
            continue
        if MIRROR_BEFORE.search(before) or PIPES_AFTER.search(after):
            continue
        g = mm.group(0)
        if re.match(r'(?:2|3|two|three)[ -]tier', g, re.I) and 'open' not in g.lower() \
                and (DOOR_RACK_BEFORE.search(before) or DOOR_RACK_AFTER.search(after)):
            continue
        if GENERIC_RE.match(g.strip()):
            best = best or WEAK
            continue
        return STRONG
    return best


def form_of(base: str, *texts) -> tuple[str, str | None]:
    """按基础形态与文字判形态：只有落地式（含原规则的 console 开放式）会分出开放式。返回 (形态, 依据强弱)。"""
    if base not in ('落地式', '开放式'):
        return base, None
    if base == '开放式':  # 原规则已从 console 判出
        return '开放式', STRONG
    k = None
    for t in texts:
        c = cue(t)
        if c == STRONG:
            return '开放式', STRONG
        k = k or c
    return ('开放式', WEAK) if k else ('落地式', None)
