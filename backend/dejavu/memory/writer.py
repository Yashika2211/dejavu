"""The write path (spec 6.4): what DejaVu retains, when, and how it is tagged.

- Tags are low-cardinality filters (org, service, symptom, kind, team). Never incident IDs: a
  per-incident tag would fragment observations per incident. IDs go in document_id and metadata.
- observation_scopes are explicit, so observations accumulate per service and per symptom class.
- timestamp is always the simulated event time; omitting it disables temporal ranking.
- Content is raw, never pre-summarised, but sanitised first (secrets, injection text). Memory
  Defense redacts secrets again on the server.
- DejaVu's own investigation log is first person, with a context naming the bank's agent as the
  speaker, so Hindsight files it as `experience`.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path

from fpdf import FPDF

from dejavu.agent.schemas import AgentStep
from dejavu.documents import Document
from dejavu.memory.hindsight_adapter import FileItem, RetainItem
from dejavu.money import inr_words
from dejavu.security import sanitize
from dejavu.sim.clock import fmt_hm
from dejavu.sim.generators.events import ChangeEvent
from dejavu.strategies.base import Resolution
from dejavu.taxonomy import SymptomClass

ORG_TAG = "org:kestrel"
KIND_CONTEXT = {
    "postmortem": "postmortem written after resolution",
    "runbook": "runbook",
    "handbook": "on-call handbook",
    "rfc": "design RFC",
    "announcement": "announcement in #eng-announce",
    "feedback": "feedback from the on-call engineer",
    "slack": "incident channel",
}
AGENT_CONTEXT = (
    "DejaVu, the on-call agent that owns this memory bank, is speaking: its own first-person "
    "investigation log for {incident}"
)
OUTCOME_WORDS = {
    "resolves": "fixed it",
    "transient": "brief relief, then relapse",
    "partial": "partial relief only",
    "no_effect": "no effect",
    "harmful": "made it worse",
    "invalid": "target did not exist",
}
_PEOPLE = re.compile(
    r"\b(Priya Raman|Tomás Ortega|Farhan Qureshi|Ananya Iyer|Rohan Mehta|Neha Kulkarni|Sara Kim|Deepak Rao|"
    r"Arjun Nair|Meera Pillai|Vikram Shetty|Ishita Bose|Lena Fischer|Kofi Mensah|Marcus Oyelaran|Kabir Malhotra)\b"
)


def tags_for(
    services: list[str], symptom: SymptomClass | None, kind: str, team: str | None = None
) -> list[str]:
    tags = [ORG_TAG, *(f"service:{s}" for s in dict.fromkeys(services)), f"kind:{kind}"]
    if symptom:
        tags.append(f"symptom:{symptom.value}")
    if team:
        tags.append(f"team:{team}")
    return tags


def scopes_for(services: list[str], symptom: SymptomClass | None) -> list[list[str]]:
    scopes = [[f"service:{s}"] for s in dict.fromkeys(services)]
    return [*scopes, [f"symptom:{symptom.value}"]] if symptom else scopes


def entities_for(services: list[str], text: str) -> list[tuple[str, str]]:
    people = sorted(set(_PEOPLE.findall(text)))
    return [*((s, "SERVICE") for s in dict.fromkeys(services)), *((p, "PERSON") for p in people)]


# Day-0 history and migrations ---------------------------------------------------------------------


def _doc_kind(doc: Document) -> str:
    return "migration" if doc.path.parent.name == "migrations" else doc.kind


def document_item(doc: Document) -> RetainItem:
    """A written document (postmortem, runbook, RFC, announcement) exactly as the team wrote it."""
    body = sanitize(f"{doc.title}\n\n{doc.body}")
    context = KIND_CONTEXT.get(doc.kind, doc.kind)
    if doc.kind == "postmortem" and doc.incident_id is None:
        context = f"historical postmortem by {doc.author}"
    return RetainItem(
        content=body,
        context=context,
        timestamp=doc.date,
        document_id=doc.id,
        tags=tags_for(doc.services, doc.symptom, _doc_kind(doc)),
        metadata={
            "author": doc.author,
            "title": doc.title,
            **({"incident_id": doc.incident_id} if doc.incident_id else {}),
        },
        entities=entities_for(doc.services, doc.body),
        observation_scopes=scopes_for(doc.services, doc.symptom) if doc.services else None,
    )


def _latin1(text: str) -> str:
    return text.replace("₹", "Rs ").encode("latin-1", "replace").decode("latin-1")


def document_file(doc: Document, directory: Path) -> FileItem:
    """Render a document as a PDF, for ingestion through retain_files."""
    path = directory / f"{doc.id}.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.multi_cell(0, 8, _latin1(doc.title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    pdf.multi_cell(0, 6, _latin1(f"{doc.author}, {doc.date:%d %b %Y}"), new_x="LMARGIN", new_y="NEXT")
    for paragraph in sanitize(doc.body).split("\n"):
        pdf.multi_cell(
            0, 5, _latin1(paragraph.replace("**", "").lstrip("# ")) or " ", new_x="LMARGIN", new_y="NEXT"
        )
    pdf.output(str(path))
    return FileItem(
        path=path,
        document_id=doc.id,
        context=KIND_CONTEXT.get(doc.kind, doc.kind),
        timestamp=doc.date,
        tags=tags_for(doc.services, doc.symptom, _doc_kind(doc)),
        metadata={"author": doc.author, "title": doc.title},
    )


def day0_payloads(docs: list[Document], pdf_dir: Path) -> tuple[list[RetainItem], list[FileItem]]:
    """Markdown documents as retain items; the ones marked `format: pdf` as files."""
    items = [document_item(d) for d in docs if d.format == "md"]
    files = [document_file(d, pdf_dir) for d in docs if d.format == "pdf"]
    return items, files


# after an incident ---------------------------------------------------------------------------------------


def _services(resolution: Resolution) -> list[str]:
    confirmed = [s for d in resolution.documents.values() for s in d.services]
    return list(dict.fromkeys([resolution.incident.service, *confirmed]))


def _step_line(step: AgentStep, at: datetime) -> str:
    args = ", ".join(f"{k}={v}" for k, v in step.args.items() if v not in (None, "", {}))
    first = next(
        (line.strip() for line in step.output.splitlines()[1:3] if line.strip()),
        step.output.splitlines()[0] if step.output else "",
    )
    done = f" It {OUTCOME_WORDS[step.outcome]}." if step.outcome in OUTCOME_WORDS else ""
    why = f" I did this because {step.rationale.rstrip('.')}." if step.rationale else ""
    return f"At {fmt_hm(at)} I called {step.tool}({args}).{why} It showed: {first[:220]}{done}"


def investigation_log(resolution: Resolution) -> str:
    """DejaVu's own account of the investigation, in the first person, including its mistakes."""
    inc = resolution.incident
    out = resolution.outcome
    lines = [f"I was paged at {fmt_hm(inc.alert_at)} IST on {inc.alert_at:%a %d %b %Y} for {inc.summary}."]
    for step in resolution.steps:
        lines.append(_step_line(step, inc.alert_at + timedelta(minutes=step.at_min)))
    d = resolution.diagnosis
    if d is not None:
        verdict = (
            "The on-call engineer confirmed it."
            if out.get("correct")
            else "The on-call engineer corrected me (see their feedback)."
        )
        lines.append(
            f"I diagnosed {d.root_cause_category.value} in {d.culprit_service} after {out.get('ttd_min')} minutes "
            f"with confidence {d.confidence:.0%}. {verdict}"
        )
    wasted = out.get("wasted_steps", 0)
    if wasted:
        lines.append(f"In hindsight, {wasted} of my {len(resolution.steps)} steps did not help.")
    for rem in out.get("remediations", []):
        lines.append(
            f"Applying {rem['action']} to {rem['target']} {OUTCOME_WORDS.get(rem['outcome'], rem['outcome'])}."
        )
    return sanitize("\n".join(lines))


def incident_items(resolution: Resolution, changes: list[ChangeEvent]) -> list[RetainItem]:
    """Everything retained once an incident is resolved (spec 6.4), in event order."""
    inc = resolution.incident
    out = resolution.outcome
    services = _services(resolution)
    team = inc.alert.get("labels", {}).get("team")
    meta = {"incident_id": inc.incident_id}
    scopes = scopes_for(services, inc.symptom)
    ents = entities_for(services, " ".join(d.body for d in resolution.documents.values()))

    def item(
        content: str, context: str, when: datetime, doc_id: str, kind: str, **extra: object
    ) -> RetainItem:
        return RetainItem(
            content=sanitize(content),
            context=context,
            timestamp=when,
            document_id=doc_id,
            tags=tags_for(services, inc.symptom, kind, team),
            metadata=meta,
            entities=ents,
            observation_scopes=scopes,
            **extra,
        )

    alert = inc.alert
    alert_text = (
        f"Alert {alert['labels']['alertname']} fired for {alert['labels']['service']} at {fmt_hm(inc.alert_at)} IST "
        f"({alert['labels'].get('severity', 'sev2')}): {alert['annotations']['description']}."
    )
    remediations = "; ".join(
        f"{r['action']} {r['target']}: {OUTCOME_WORDS.get(r['outcome'], r['outcome'])}"
        for r in out.get("remediations", [])
    )
    diagnosis = resolution.diagnosis
    summary = (
        f"{inc.incident_id} resolved at {fmt_hm(resolution.resolved_at)} IST after {out.get('mttr_min')} minutes "
        f"(recovered by {out.get('resolved_by')})."
    )
    outcome_text = (
        f"Outcome of {inc.incident_id} ({inc.alert_at:%a %d %b %Y}, {alert['labels']['alertname']}): "
        + (
            f"DejaVu diagnosed {diagnosis.root_cause_category.value} in {diagnosis.culprit_service}"
            f" ({'confirmed' if out.get('correct') else 'corrected by the on-call engineer'}). "
            if diagnosis
            else "No diagnosis. "
        )
        + (f"Remediations: {remediations}. " if remediations else "")
        + f"Time to diagnosis {out.get('ttd_min')} min, MTTR {out.get('mttr_min')} min, "
        f"about {inr_words(out.get('inr_at_risk', 0))} of payments at risk."
    )
    items = [
        item(
            alert_text,
            "production alert",
            inc.alert_at,
            f"inc-{inc.incident_id}-timeline",
            "timeline",
            update_mode="append",
        ),
        item(
            summary,
            "incident timeline",
            resolution.resolved_at,
            f"inc-{inc.incident_id}-timeline",
            "timeline",
            update_mode="append",
        ),
        item(
            investigation_log(resolution),
            AGENT_CONTEXT.format(incident=inc.incident_id),
            inc.alert_at + timedelta(minutes=out.get("ttd_min") or 0),
            f"inc-{inc.incident_id}-investigation",
            "investigation",
        ),
        item(
            outcome_text,
            "incident outcome",
            resolution.resolved_at,
            f"inc-{inc.incident_id}-outcome",
            "outcome",
        ),
    ]
    if changes:
        log = "\n".join(
            f"{c.at:%d %b %H:%M} {c.id} {c.type.value} {c.service}: {c.summary} (by {c.author})"
            + (f". {c.details['diff']}" if c.details.get("diff") else "")
            for c in changes
        )
        items.append(
            item(
                f"Changes in the six hours before {inc.incident_id}:\n{log}",
                "deploy and config change log",
                inc.alert_at,
                f"changes-{inc.incident_id}",
                "change",
            )
        )
    for kind in ("feedback", "postmortem"):
        doc = resolution.documents.get(kind)
        if doc is not None:
            items.append(
                RetainItem(
                    **{
                        **document_item(doc).model_dump(),
                        "tags": tags_for(services, inc.symptom, kind, team),
                        "observation_scopes": scopes,
                    }
                )
            )
    return sorted(items, key=lambda i: i.timestamp)
