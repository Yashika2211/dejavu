"""Kestrel Pay's written record: runbooks, Marcus's Day-0 history, migration artifacts and the
postmortems, Slack threads and feedback notes written after each Gauntlet incident.

Every document carries front matter (id, kind, author, date, services, symptom, format), which
is what the memory layer uses for `document_id`, `timestamp`, tags and PDF ingestion.
"""

from datetime import datetime, time
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from dejavu.config import REPO_ROOT
from dejavu.sim.clock import IST
from dejavu.sim.runbooks import all_runbooks
from dejavu.taxonomy import SymptomClass

FIXTURES = REPO_ROOT / "data" / "fixtures"

Kind = Literal["postmortem", "slack", "feedback", "runbook", "handbook", "rfc", "announcement"]


class Document(BaseModel):
    id: str
    kind: Kind
    title: str
    author: str
    date: datetime
    services: list[str]
    symptom: SymptomClass | None = None
    format: Literal["md", "pdf"] = "md"
    incident_id: str | None = None
    body: str
    path: Path | None = None  # None for documents written in the war room rather than loaded from fixtures


def parse(path: Path) -> Document:
    _, front, body = path.read_text().split("---", 2)
    meta = yaml.safe_load(front)
    return Document(**meta, body=body.strip(), path=path)


def _runbook_documents() -> list[Document]:
    return [
        Document(
            id=rb.id,
            kind="runbook",
            title=rb.title,
            author=rb.author,
            date=datetime.combine(rb.last_edited, time(10, 0), IST),
            services=rb.services,
            body=rb.body,
            path=FIXTURES / "runbooks" / f"{rb.id}.md",
        )
        for rb in all_runbooks()
    ]


@cache
def day0_documents() -> tuple[Document, ...]:
    """Everything imported before the Gauntlet: Marcus's history plus the runbooks, oldest first."""
    docs = [parse(p) for p in sorted((FIXTURES / "day0").glob("*.md"))] + _runbook_documents()
    return tuple(sorted(docs, key=lambda d: (d.date, d.id)))


@cache
def migration_documents() -> tuple[Document, ...]:
    """RFCs and announcements for M1 and M2, oldest first."""
    return tuple(sorted((parse(p) for p in (FIXTURES / "migrations").glob("*.md")), key=lambda d: d.date))


@cache
def incident_documents(n: int) -> dict[str, Document]:
    """The postmortem, Slack thread and feedback note for Gauntlet incident `n`, keyed by kind."""
    folder = FIXTURES / "incidents" / f"{n:02d}"
    return {d.kind: d for d in (parse(p) for p in sorted(folder.glob("*.md")))}
