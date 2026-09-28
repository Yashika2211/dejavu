"""The written record is consistent with the simulation: numbers, dates, identities, hygiene."""

import json
import re
from datetime import timedelta

import pytest

from dejavu.config import REPO_ROOT
from dejavu.documents import FIXTURES, day0_documents, incident_documents, migration_documents
from dejavu.money import inr_words
from dejavu.sim.clock import ist
from dejavu.sim.generators.humans import fact_sheet
from dejavu.sim.migrations import M1, M2
from dejavu.sim.scenario import archetype_ids
from dejavu.sim.schedule import entry_for, gauntlet

GAUNTLET = {entry_for(s).n: s for s in gauntlet()}
SECRET = re.compile(r"eyJ[\w-]{8,}\.eyJ[\w-]{8,}\.[\w-]+|\bgsk_\w{10,}|\bsk-[A-Za-z0-9]{20,}|\bghp_\w{30,}")


def _facts(n: int) -> dict:
    return json.loads((FIXTURES / "facts" / f"incident-{n:02d}.json").read_text())


def _all_documents():
    docs = [*day0_documents(), *migration_documents()]
    for n in range(1, 25):
        docs += incident_documents(n).values()
    return docs


def test_document_ids_are_unique() -> None:
    ids = [d.id for d in _all_documents()]
    assert len(ids) == len(set(ids))


def test_day0_history_predates_the_gauntlet_and_includes_two_pdfs() -> None:
    start = min(s.alert_at for s in GAUNTLET.values())
    docs = day0_documents()
    assert all(d.date < start for d in docs)
    assert sum(d.format == "pdf" for d in docs) == 2
    assert sum(d.kind == "postmortem" for d in docs) == 6
    assert sum(d.kind == "runbook" for d in docs) == 8


def test_migration_rfcs_precede_and_announcements_follow_the_migration() -> None:
    by_id = {d.id: d for d in migration_documents()}
    assert by_id["rfc-014"].date < M1.at <= by_id["slack-m1"].date
    assert by_id["rfc-015"].date < M2.at <= by_id["slack-m2"].date


@pytest.mark.parametrize("n", range(1, 25))
def test_each_incident_has_a_consistent_written_record(n: int) -> None:
    scenario, facts = GAUNTLET[n], _facts(n)
    docs = incident_documents(n)
    assert set(docs) == {"postmortem", "slack", "feedback"}
    resolved = ist(f"{scenario.alert_at:%Y-%m-%d}T{facts['resolved_at']}")
    if resolved < scenario.alert_at:
        resolved += timedelta(days=1)
    later = [s.alert_at for s in GAUNTLET.values() if s.alert_at > scenario.alert_at]
    next_alert = min(later) if later else scenario.alert_at + timedelta(days=7)
    for doc in docs.values():
        assert doc.incident_id == scenario.incident_id
        assert doc.symptom == scenario.spec.symptom_class
    assert scenario.alert_at <= docs["slack"].date <= resolved
    assert resolved < docs["feedback"].date < next_alert
    assert resolved < docs["postmortem"].date < next_alert
    assert docs["postmortem"].author == facts["author"]


@pytest.mark.parametrize("n", range(1, 25))
def test_postmortem_numbers_come_from_the_simulation(n: int) -> None:
    facts, body = _facts(n), incident_documents(n)["postmortem"].body
    assert f"{facts['failed_payments']:,} failed payments" in body
    assert inr_words(facts["inr_at_risk"]) in body
    assert f"{facts['impact_minutes']:g} minutes" in body
    assert facts["resolved_at"] in body


@pytest.mark.parametrize("n", [1, 7, 12, 19])
def test_committed_fact_sheets_reproduce(n: int, tmp_path) -> None:
    assert fact_sheet(n, GAUNTLET[n], root=tmp_path).model_dump(mode="json") == _facts(n)


def test_fixtures_hold_no_secrets_and_no_ground_truth_labels() -> None:
    text = "\n".join(p.read_text() for p in (REPO_ROOT / "data" / "fixtures").rglob("*.md"))
    assert not SECRET.search(text)
    for archetype in archetype_ids():
        assert archetype not in text
