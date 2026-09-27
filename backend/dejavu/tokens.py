"""Token counting with the o200k encoding (the family gpt-oss uses), for budgets and bounds."""

from functools import lru_cache

import tiktoken


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("o200k_base")


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text, disallowed_special=()))


def fit_blocks(header: str, blocks: list[str], *, max_tokens: int, more: str = "more") -> str:
    """Header plus as many whole blocks as fit, then a note saying how many were left out."""
    out = [header]
    used = count_tokens(header)
    for i, block in enumerate(blocks):
        cost = count_tokens(block) + 1
        remaining = len(blocks) - i
        if used + cost > max_tokens - 12:
            out.append(f"(+{remaining} {more} not shown; narrow the query)")
            break
        out.append(block)
        used += cost
    return "\n".join(out)


def clip(text: str, max_tokens: int) -> str:
    """Hard cap: cut at a line boundary and say so."""
    if count_tokens(text) <= max_tokens:
        return text
    lines = text.splitlines()
    while lines and count_tokens("\n".join(lines)) > max_tokens - 8:
        lines.pop()
    return "\n".join([*lines, "(output truncated)"])
