"""The API's app state round-trips through SQLite and survives a restart."""

from pathlib import Path

from dejavu.store.db import FeedbackRecord, IncidentRecord, RaceRecord, RunRecord, Store


def _incident(incident_id: str, created_at: str) -> IncidentRecord:
    return IncidentRecord(
        id=incident_id,
        source="archetype",
        requested="cert_expiry",
        archetype="cert_expiry",
        seed=7,
        alert_at="2026-09-27T10:00:00+05:30",
        created_at=created_at,
    )


def test_incidents_runs_and_feedback_round_trip() -> None:
    store = Store("sqlite://")
    store.save(_incident("INC-4501", "2026-09-28T10:00:00+05:30"))
    store.save(_incident("INC-4502", "2026-09-28T11:00:00+05:30"))
    assert [i.id for i in store.incidents()] == ["INC-4502", "INC-4501"]

    store.save(RunRecord(id="r1", incident_id="INC-4501", strategy="dejavu"))
    store.update_run("r1", status="done", score={"correct": True, "mttr_min": 12.5})
    run = store.run("r1")
    assert run is not None
    assert (run.status, run.score) == ("done", {"correct": True, "mttr_min": 12.5})

    store.save(FeedbackRecord(incident_id="INC-4501", correct=False, actual_category="psp_rate_limit"))
    assert [f.actual_category for f in store.feedback("INC-4501")] == ["psp_rate_limit"]


def test_runs_left_running_by_a_crash_are_interrupted(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'app.db'}"
    Store(url).save(RunRecord(id="r1", incident_id="INC-4501", strategy="amnesiac"))
    restarted = Store(url)
    assert restarted.interrupt_running() == 1
    run = restarted.run("r1")
    assert run is not None
    assert run.status == "interrupted"


def test_race_lanes_are_found_by_race() -> None:
    store = Store("sqlite://")
    store.save(RaceRecord(id="race-1", incident_id="INC-4499", left="amnesiac", right="dejavu"))
    for lane, strategy in (("left", "amnesiac"), ("right", "dejavu")):
        store.save(
            RunRecord(id=f"r-{lane}", incident_id="INC-4499", strategy=strategy, race_id="race-1", lane=lane)
        )
    assert {r.lane for r in store.runs(race_id="race-1")} == {"left", "right"}
    race = store.race("race-1")
    assert race is not None
    assert race.left == "amnesiac"
