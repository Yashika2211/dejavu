"""Drain-style log template mining, simplified: mask the variable tokens, then group and count.

Lines generated from one template collapse to one pattern, the way a log pipeline's template
view shows them, so a burst of `Connection is not available ... waiting=143` lines reads as one
row with a count rather than hundreds of near-duplicates.
"""

import re
from dataclasses import dataclass

_MASKS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"), "<ts>"),
    (re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+"), "<jwt>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), "<uuid>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"), "<ip>"),
    (re.compile(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+)*-[a-z0-9]{9,10}-[a-z0-9]{5}\b"), "<pod>"),
    (re.compile(r"\b[a-z]+_[0-9a-f]{6,}\b"), "<id>"),
    (re.compile(r"\b0x[0-9a-f]+\b"), "<hex>"),
    (re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-f]{7,}\b"), "<hex>"),
    (re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w])"), "<n>"),
)


def template_of(message: str) -> str:
    out = message
    for pattern, token in _MASKS:
        out = pattern.sub(token, out)
    return out


@dataclass
class Template:
    level: str
    pattern: str
    count: int
    first_s: float
    last_s: float
    example: str


def mine(rows: list[tuple[float, str, str, str]]) -> list[Template]:
    """Group (offset_s, level, message, line) rows into templates, most frequent first."""
    groups: dict[tuple[str, str], Template] = {}
    for offset_s, level, message, line in rows:
        key = (level, template_of(message))
        found = groups.get(key)
        if found is None:
            groups[key] = Template(level, key[1], 1, offset_s, offset_s, line)
        else:
            found.count += 1
            found.last_s = offset_s
            found.example = line
    return sorted(groups.values(), key=lambda t: (-t.count, t.first_s))
