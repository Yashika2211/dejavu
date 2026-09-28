"""Structured outputs shared by the agent loop, the memory layer, the grader and the UI (spec 5.3)."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from dejavu.taxonomy import Remediation, RootCause


class Hypothesis(BaseModel):
    id: str = Field(description="Short stable id, e.g. h1")
    statement: str
    category: RootCause
    service: str
    probability: float = Field(ge=0, le=1)
    evidence_for: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)
    origin: Literal["memory", "evidence", "both"] = "evidence"


class HypothesisBoard(BaseModel):
    """Arguments of `update_hypotheses`: the full current board, most likely first."""

    hypotheses: list[Hypothesis] = Field(min_length=1, max_length=6)


class RecallArgs(BaseModel):
    """Arguments of `recall_memory`."""

    query: str = Field(
        description="What to look up, e.g. 'have we seen x509 certificate has expired before?'"
    )


class EvidenceRef(BaseModel):
    step_id: int
    excerpt: str


class PlannedAction(BaseModel):
    action: Remediation
    target: str
    params: dict[str, str] = Field(default_factory=dict)
    rationale: str = ""

    @field_validator("params", mode="before")
    @classmethod
    def _stringify(cls, value: object) -> object:
        return {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else value


class Diagnosis(BaseModel):
    """Arguments of `submit_diagnosis`; ends the investigation."""

    root_cause_category: RootCause
    culprit_service: str = Field(
        description="Component name from get_topology, or 'nodes' for a node-level cause"
    )
    trigger_change_id: str | None = Field(
        None, description="chg-... id from list_changes, if a change caused it"
    )
    summary: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    remediation_plan: list[PlannedAction] = Field(default_factory=list)
    precedent_incident_ids: list[str] = Field(default_factory=list)
    memory_used: bool = False


class AgentStep(BaseModel):
    """One tool call as it happened (the unit of the run trace and the UI's step cards)."""

    index: int
    tool: str
    args: dict
    rationale: str
    ok: bool
    output: str
    sim_minutes: float
    at_min: float = Field(description="Simulated minutes after the alert when the step started")
    memory_moment: bool = False
    cited_incidents: list[str] = Field(default_factory=list)
    model: str | None = None
    repaired: bool = False
