"""The on-call human's feedback on a war-room incident, in their own words, for the write path.

A confirmation or a correction becomes a `feedback` document dated a few minutes after recovery,
the same kind of document the Gauntlet's fixtures give every strategy (spec 9).
"""

from datetime import timedelta

from pydantic import BaseModel

from dejavu.api.live import LiveRun
from dejavu.documents import Document
from dejavu.eval.grading import DETECTION_MIN
from dejavu.strategies.base import IncidentContext
from dejavu.taxonomy import RootCause

FEEDBACK_DELAY_MIN = 5


class Feedback(BaseModel):
    correct: bool
    actual_category: RootCause | None = None
    actual_service: str | None = None
    notes: str = ""
    author: str = "Priya Raman"


def feedback_document(run: LiveRun, feedback: Feedback) -> Document:
    """The feedback as the on-call engineer would write it; needs a finished, graded run."""
    if run.result is None or run.score is None or run.world is None:
        raise ValueError(f"run {run.id} has not finished")
    scenario = run.world.scenario
    ctx = IncidentContext.from_alert(scenario.incident_id, run.world.store.alert, scenario.alert_at)
    d = run.result.diagnosis
    predicted = f"{d.root_cause_category.value} in {d.culprit_service}" if d else "no diagnosis"
    if feedback.correct:
        text = f"{feedback.author} (on-call) confirmed DejaVu's diagnosis for {ctx.incident_id}: {predicted}."
    else:
        actual = " in ".join(
            x
            for x in (feedback.actual_category and feedback.actual_category.value, feedback.actual_service)
            if x
        )
        text = (
            f"{feedback.author} (on-call) corrected DejaVu on {ctx.incident_id}: the root cause was "
            f"{actual or 'something else'}, not {predicted}."
        )
    if feedback.notes.strip():
        text += f" {feedback.notes.strip()}"
    recovered = scenario.alert_at + timedelta(minutes=run.score.mttr_min - DETECTION_MIN)
    services = [
        s for s in dict.fromkeys([ctx.service, feedback.actual_service, d and d.culprit_service]) if s
    ]
    return Document(
        id=f"fb-{ctx.incident_id}",
        kind="feedback",
        title=f"Feedback on {ctx.incident_id}",
        author=feedback.author,
        date=recovered + timedelta(minutes=FEEDBACK_DELAY_MIN),
        services=services,
        symptom=ctx.symptom,
        incident_id=ctx.incident_id,
        body=text,
    )
