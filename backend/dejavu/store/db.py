"""App state for the war room (spec 3.2), in SQLite through SQLModel.

Telemetry lives in Parquet and run events in JSONL traces; this keeps what the API needs to list,
reopen and reproduce them: the incidents it created (enough to re-instantiate each scenario), the
runs and races made of them, and the on-call human's feedback. Times are stored as ISO strings,
because SQLite drops time zones and every simulated time here is IST.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlalchemy.pool import StaticPool
from sqlmodel import Field, Session, SQLModel, col, create_engine, select

from dejavu.config import REPO_ROOT

DB_PATH = REPO_ROOT / "data" / "app.db"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class IncidentRecord(SQLModel, table=True):
    """An incident the war room created; archetype, seed, alert time and id re-instantiate it."""

    id: str = Field(primary_key=True)
    source: str  # demo | archetype | surprise | webhook
    requested: str  # the demo name or archetype asked for
    archetype: str  # ground truth: never shown before the incident is resolved
    seed: int
    alert_at: str
    created_at: str = Field(default_factory=now_iso)


class RunRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    incident_id: str = Field(index=True)
    strategy: str  # amnesiac | rag | dejavu | day1
    bank: str | None = None
    race_id: str | None = Field(default=None, index=True)
    lane: str | None = None
    status: str = "running"  # running | done | error | interrupted
    started_at: str = Field(default_factory=now_iso)
    ended_at: str | None = None
    trace_path: str | None = None
    score: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))


class RaceRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    incident_id: str
    left: str
    right: str
    created_at: str = Field(default_factory=now_iso)


class FeedbackRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    incident_id: str = Field(index=True)
    run_id: str | None = None
    correct: bool
    actual_category: str | None = None
    actual_service: str | None = None
    notes: str = ""
    retained: bool = False
    created_at: str = Field(default_factory=now_iso)


class Store:
    """Thin persistence for the API. `Store("sqlite://")` is an in-memory store for tests."""

    def __init__(self, url: str | None = None) -> None:
        if url is None:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            url = f"sqlite:///{DB_PATH}"
        memory = url == "sqlite://"
        self.engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            **({"poolclass": StaticPool} if memory else {}),
        )
        SQLModel.metadata.create_all(self.engine)

    def _session(self) -> Session:
        return Session(self.engine, expire_on_commit=False)

    def save[R: SQLModel](self, record: R) -> R:
        """Insert or update; returns the stored record (with its generated id, if any)."""
        with self._session() as session:
            stored = session.merge(record)
            session.commit()
            return stored

    def incident(self, incident_id: str) -> IncidentRecord | None:
        with self._session() as session:
            return session.get(IncidentRecord, incident_id)

    def incidents(self) -> list[IncidentRecord]:
        with self._session() as session:
            return list(session.exec(select(IncidentRecord).order_by(col(IncidentRecord.created_at).desc())))

    def run(self, run_id: str) -> RunRecord | None:
        with self._session() as session:
            return session.get(RunRecord, run_id)

    def runs(self, *, incident_id: str | None = None, race_id: str | None = None) -> list[RunRecord]:
        query = select(RunRecord).order_by(col(RunRecord.started_at))
        if incident_id is not None:
            query = query.where(RunRecord.incident_id == incident_id)
        if race_id is not None:
            query = query.where(RunRecord.race_id == race_id)
        with self._session() as session:
            return list(session.exec(query))

    def update_run(self, run_id: str, **fields: Any) -> None:
        with self._session() as session:
            record = session.get(RunRecord, run_id)
            if record is None:
                return
            for key, value in fields.items():
                setattr(record, key, value)
            session.add(record)
            session.commit()

    def interrupt_running(self) -> int:
        """Runs left `running` by a previous process can't finish: mark them interrupted."""
        with self._session() as session:
            stale = list(session.exec(select(RunRecord).where(RunRecord.status == "running")))
            for record in stale:
                record.status = "interrupted"
                session.add(record)
            session.commit()
            return len(stale)

    def race(self, race_id: str) -> RaceRecord | None:
        with self._session() as session:
            return session.get(RaceRecord, race_id)

    def feedback(self, incident_id: str) -> list[FeedbackRecord]:
        with self._session() as session:
            query = select(FeedbackRecord).where(FeedbackRecord.incident_id == incident_id)
            return list(session.exec(query.order_by(col(FeedbackRecord.created_at))))
