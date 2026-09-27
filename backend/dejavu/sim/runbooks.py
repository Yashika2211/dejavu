"""Kestrel Pay's runbooks (Day-0 fixtures), as `get_runbook` finds them.

Runbooks are what the team wrote down, not what is true today: some are stale on purpose
(RB-ledger-pool predates the PgBouncer migration; RB-cache-failover still says redis-cache).
"""

import re
from datetime import date
from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from dejavu.config import REPO_ROOT

RUNBOOK_DIR = REPO_ROOT / "data" / "fixtures" / "runbooks"
_WORD = re.compile(r"[a-z0-9_]+")


class Runbook(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)  # keywords such as 401 or 429

    id: str
    title: str
    services: list[str]
    keywords: list[str]
    author: str
    last_edited: date
    body: str

    @property
    def terms(self) -> set[str]:
        words = {w for k in (*self.keywords, *self.services, self.title) for w in _WORD.findall(k.lower())}
        return words | {s.lower() for s in self.services}


def parse(path: Path) -> Runbook:
    _, front, body = path.read_text().split("---", 2)
    return Runbook(**yaml.safe_load(front), body=body.strip())


@cache
def all_runbooks(directory: Path = RUNBOOK_DIR) -> tuple[Runbook, ...]:
    return tuple(sorted((parse(p) for p in directory.glob("*.md")), key=lambda r: r.id))


def find(topic: str, directory: Path = RUNBOOK_DIR) -> Runbook | None:
    """Best keyword match for a free-text topic, or None when nothing overlaps."""
    wanted = set(_WORD.findall(topic.lower())) | {topic.strip().lower()}
    exact = [r for r in all_runbooks(directory) if r.id.lower() == topic.strip().lower()]
    if exact:
        return exact[0]
    scored = [(len(wanted & r.terms), r.id, r) for r in all_runbooks(directory)]
    best = max(scored, key=lambda s: (s[0], [-ord(c) for c in s[1]]), default=None)
    return best[2] if best and best[0] > 0 else None
