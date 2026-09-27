from dejavu.memory.missions import DIRECTIVES, ENTITY_LABELS, MEMORY_DEFENSE
from dejavu.taxonomy import Outcome, Remediation, RootCause, SymptomClass


def _values(key: str) -> set[str]:
    group = next(g for g in ENTITY_LABELS if g["key"] == key)
    return {v["value"] for v in group["values"]}


def test_entity_labels_cover_the_taxonomy() -> None:
    assert _values("failure_mode") == {c.value for c in RootCause}
    assert _values("symptom") == {s.value for s in SymptomClass}
    assert _values("remediation") == {r.value for r in Remediation}
    assert _values("outcome") == {o.value for o in Outcome}


def test_taxonomy_has_twelve_archetypes_plus_novel() -> None:
    assert len(RootCause) == 13
    assert RootCause.NOVEL in RootCause


def test_labels_do_not_become_tags() -> None:
    # Label tags would change each memory's tag set; observation scoping must stay per service/symptom.
    assert not any(g.get("tag") for g in ENTITY_LABELS)


def test_five_unique_directives() -> None:
    assert len({d.name for d in DIRECTIVES}) == 5


def test_memory_defense_redacts_sensitive_data() -> None:
    assert MEMORY_DEFENSE["enabled"] is True
    assert {"on": "sensitive_data", "action": "redact"} in MEMORY_DEFENSE["rules"]
