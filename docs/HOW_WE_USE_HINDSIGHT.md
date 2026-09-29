# How DejaVu uses Hindsight

DejaVu is an on-call agent whose only advantage over a cold-start agent is memory. Everything it knows about Kestrel Pay's past, it knows through one Hindsight bank per profile. This page lists every Hindsight feature we use, where the code is, and why it is there. What we verified against Hindsight Cloud (and what surprised us) is in [`HINDSIGHT_NOTES.md`](HINDSIGHT_NOTES.md).

## Banks

| Bank | Purpose |
|---|---|
| `kestrel-ops-live` | what the war room reads and learns into |
| `kestrel-ops-day1` | snapshot after the Day-0 import only ("DejaVu on day 1") |
| `kestrel-ops-trained` | snapshot after the full Gauntlet ("day 42"); "Reset demo" re-clones live from it |
| `kestrel-ops-rag` | the naive-RAG ablation: same documents, chunk mode, no observations |
| `gx-<run>-dejavu`, `gx-<run>-rag` | one pair per Gauntlet run |

Setup is idempotent: `make bank` (`backend/scripts/bank_setup.py`, `backend/dejavu/memory/bank_setup.py`).

## Retain: what gets written, and when

| Hindsight feature | Code | Why |
|---|---|---|
| `retain_batch(retain_async=True, operation_id=…)` | `memory/hindsight_adapter.py` (`retain`), `strategies/dejavu.py` (`on_resolution`) | end-of-incident writes in one batch; a deterministic operation id makes retries safe |
| `timestamp` on every item | `memory/writer.py` | the simulated event time, so old runbooks stay old and temporal ranking works |
| `document_id` upserts | `writer.py` (`pm-INC-…`, `fb-INC-…`) | an edited postmortem replaces the old one |
| `update_mode: "append"` | `writer.py` (`inc-…-timeline`) | the alert and the resolution land in one timeline document |
| `context` naming the speaker | `writer.py` (`AGENT_CONTEXT`) | DejaVu's first-person investigation log is stored as **experience**, so it remembers its own wrong turns |
| `entities` (services, people) | `writer.py` (`entities_for`) | services and people are always recognised entities for the graph |
| `metadata` | `writer.py` | incident id, kind, team, author, title: shown in provenance, never used as filters |
| `tags` (org, service, symptom) | `writer.py` (`tags_for`) | the only filters reads use; kept small because observations inherit their source's full tag set |
| `observation_scopes` | `writer.py` (`scopes_for`) | per service and per symptom class |
| `retain_files` (PDF, with a timestamp) | `memory/day0.py` | two Day-0 documents arrive as PDFs; the timestamp becomes the document's event date |

## Settle before the next incident

`memory/settle.py` waits for the retain operations, triggers consolidation, waits until nothing is pending, and refreshes any mental model whose last refresh failed (a failed refresh pauses automatic ones). The next incident must see what the last one taught.

## Recall and reflect: what gets read

| Hindsight feature | Code | Why |
|---|---|---|
| `recall(types=["observation"], tags=[service, symptom], tags_match="any", query_timestamp, include_source_facts)` | `memory/reader.py` (`triage_brief`) | observations relevant to the alert, anchored at the incident time; untagged Day-0 material stays visible |
| `reflect(response_schema=TriageBrief, include_facts=True)` | `reader.py` | the briefing: likely causes with priors and precedents, cheapest discriminating checks, what to avoid, stale knowledge; `based_on` is the provenance shown on every déjà vu card |
| `recall(types=[observation, world, experience], budget="low")` | `reader.py` (`lookup`) | the agent's own `recall_memory` tool mid-investigation |
| `reflect(response_schema=RiskReview)` | `foresight/risk_review.py` | Foresight: a pending change reviewed against incident history, citing precedents |
| `reflect(budget="high")` | `api/routes/memory.py` (`/ask`) | Ask DejaVu (⌘K) with citations |

## Consolidation, observations, mental models, knowledge

| Hindsight feature | Code | Why |
|---|---|---|
| Missions (retain, observations, reflect), dispositions, entity labels | `memory/missions.py` | tell the bank what matters in operations: discriminators, negative results, before/after migrations |
| Directives | `missions.py` (`DIRECTIVES`) | evidence over memory, cite precedents, respect negative history, approval for stateful systems, temporal validity |
| Mental models, refreshed after consolidation (`mode: delta`, `tags_match: any`) | `memory/mental_models.py` | one per core service plus triage playbook, change-risk register and team conventions: the living runbooks nobody wrote |
| Mental model history | `api/routes/memory.py` (`belief_versions`) | the belief timeline, with diffs |
| Memory curation (`state: invalidated / valid`) | `memory/rest.py`, `api/routes/memory.py` | "Wrong / outdated" and "Restore" in the explorer, with the audit trail kept |
| Bank stats | `eval/gauntlet.py` | memory growth per Gauntlet incident |

## Snapshots and the ablation

| Hindsight feature | Code | Why |
|---|---|---|
| Clone | `memory/snapshots.py` | day 1 and day 42 snapshots; the demo reset |
| Export (transfer ZIP) | `memory/rest.py` (`export_bank`) | the "brain" archive |
| `retain_extraction_mode="chunks"`, observations off | `bank_setup.py` (`rag` profile), `strategies/rag.py` | the naive-RAG baseline: every document, no learning |

## Safety

Every retained text goes through `dejavu/security.py` first: secret-shaped strings (JWTs, bearer tokens, API keys, database URLs) are redacted and prompt-injection text is neutralised. Hindsight's Memory Defense is requested for every bank as a second layer; our Cloud organisation isn't entitled to it (`detectors_not_entitled`), so the client-side layer is the one that holds today.
