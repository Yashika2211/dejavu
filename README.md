# DejaVu

**The on-call agent that has seen this before.**

Every postmortem is hindsight, and it usually dies in a Google Doc. DejaVu turns it into memory, then into foresight. The second time production breaks the same way, it's fixed in minutes. The third time, it's prevented.

DejaVu investigates production alerts with tools, diagnoses the root cause, proposes a remediation for a human to approve, and learns from the outcome through [Hindsight](https://hindsight.vectorize.io) memory: which signals separate look-alike causes, which fixes failed or made things worse, and which old fixes stopped working after a migration.

## Why this problem

- Root-cause analysis is one of the hardest open problems for agents. On **OpenRCA** (ICLR 2025: 335 real failures, 68 GB of telemetry) the best model with a purpose-built agent solved **11.34%** of cases. [paper](https://proceedings.iclr.cc/paper_files/paper/2025/hash/d29b8d53678015079e1d245c023e49d2-Abstract-Conference.html)
- A July 2026 follow-up found that injecting domain knowledge raised full-accuracy RCA on one system from **35.29% to 56.86%**: "the bottleneck is not data access but the agent's ability to reason over it correctly." [arXiv](https://arxiv.org/html/2607.13548v1)
- On Artificial Analysis' **ITBench-AA** (Kubernetes incident RCA), the top frontier models score in the low-to-mid 50s. [ITBench-AA](https://artificialanalysis.ai/evaluations/itbench-aa)
- Most AI SRE agents "investigate each incident from a cold start". [2026 AI-SRE market map](https://www.mezmo.com/learn/the-2026-ai-sre-market-map-agents-harnesses-and-the-data-layer)

**Thesis:** domain knowledge is the lever, and memory is how an agent earns it on the job. Hindsight is that memory.

## What makes it different

DejaVu keeps the four kinds of memory a senior on-call engineer has:

| Memory | What it holds | How DejaVu uses it |
|---|---|---|
| Episodic | incidents, its own first-person investigation logs (wrong hypotheses, wasted steps), human feedback | cites precedents, stops repeating its own mistakes |
| Semantic | observations consolidated across incidents: failure modes, discriminators, what fixes work | the triage brief: priors, the cheapest discriminating check, what to avoid |
| Procedural | living runbooks nobody wrote (mental models refreshed after consolidation) | the Memory screen; stale human runbooks get contradicted |
| Prospective | change and incident history | Foresight reviews a pending deploy or flag flip before it ships |

1. **Discriminator memory.** The same checkout p99 spike can be pool exhaustion, a missing index or the payment processor throttling us; memory keeps which signal tells them apart.
2. **Negative memory.** Restarts that relapsed, pool bumps that did nothing, a postgres restart that made it worse.
3. **Temporal validity.** After the PgBouncer migration (3 Sep) raising the HikariCP pool does nothing; the briefing says so.
4. **Proof, not claims.** A reproducible benchmark (the Gauntlet): no memory vs naive RAG vs DejaVu over 24 simulated incidents.

## How DejaVu uses Hindsight

See [`docs/HOW_WE_USE_HINDSIGHT.md`](docs/HOW_WE_USE_HINDSIGHT.md) for every feature with a code pointer, and [`docs/HINDSIGHT_NOTES.md`](docs/HINDSIGHT_NOTES.md) for what we verified against Hindsight Cloud.

| Hindsight feature | Where | Why it matters |
|---|---|---|
| `retain_batch` with timestamps, tags, entities, metadata, `update_mode: append` | `backend/dejavu/memory/writer.py` | alert, timeline, investigation log, outcome, change log, feedback and postmortem, each at its simulated time |
| First-person context → `experience` facts | `writer.py` (`AGENT_CONTEXT`) | DejaVu's own mistakes are remembered as its experience |
| `retain_files` (PDF) | `backend/dejavu/memory/day0.py` | the Day-0 handbook and an RFC arrive as PDFs |
| Recall with `tags_match="any"`, `query_timestamp`, source facts | `backend/dejavu/memory/reader.py` | the triage brief and the `recall_memory` tool |
| Reflect with `response_schema` and `based_on` | `reader.py`, `backend/dejavu/foresight/risk_review.py` | structured briefs and risk reviews with provenance |
| Observations + consolidation, settle before the next incident | `backend/dejavu/memory/settle.py` | the next incident sees what the last one taught |
| Mental models (per service, triage playbook, change risk, conventions) | `backend/dejavu/memory/mental_models.py` | living runbooks and belief timelines |
| Directives, missions, dispositions, entity labels | `backend/dejavu/memory/missions.py`, `bank_setup.py` | how the bank reasons about operations |
| Curation (invalidate / restore) | `backend/dejavu/api/routes/memory.py` | "Wrong / outdated" in the explorer |
| Clone and export | `backend/dejavu/memory/snapshots.py`, `rest.py` | day 1 and day 42 snapshots, demo reset |
| Chunk-mode bank | `backend/dejavu/strategies/rag.py` | the naive-RAG ablation receives the same documents |

## Results

Numbers here come only from the Gauntlet (`make gauntlet`, generated into [`docs/EVAL_RESULTS.md`](docs/EVAL_RESULTS.md) by `eval/report.py`).

| | No memory | Naive RAG | DejaVu |
|---|---|---|---|
| Correct diagnoses | {{placeholder}} | {{placeholder}} | {{placeholder}} |
| Mean MTTR | {{placeholder}} | {{placeholder}} | {{placeholder}} |
| MTTR on recurrences vs no memory | | {{placeholder}} | {{placeholder}} |

The full Gauntlet needs about 1,200 model calls; Groq's free tier allows 1,000 requests and 8,000 tokens a minute, so it runs on the paid Developer tier (`make gauntlet DRY=1` estimates the cost).

## Architecture

```
SRE-Gym simulator (Parquet telemetry, remediation engine, 15 archetypes, 24-incident Gauntlet)
        │ tools (metrics, logs, traces, changes, topology, runbooks, remediation)
        ▼
Investigation loop (Groq, one tool call per turn, rationale on every step, budgeted context)
        ▲ briefing / recall_memory            │ resolution, feedback, postmortem
        │                                     ▼
Memory strategy: amnesiac | naive RAG (chunk bank) | DejaVu (Hindsight bank)
        │
FastAPI + Server-Sent Events  ──►  Next.js war room (War Room, Race, Memory, Learning, Foresight)
```

## Quickstart

```
cp .env.example .env        # add GROQ_API_KEY and HINDSIGHT_API_KEY
make setup                  # uv sync + pnpm install
make health                 # Groq models, Hindsight version and credentials
make bank                   # create kestrel-ops-live and import the Day-0 history
make dev                    # API on :8000, war room on :3000
make run N=5 STRATEGY=dejavu   # one incident from the CLI
make test                   # ruff, web lint, backend tests
```

Other targets: `make spike` (Hindsight contract checks), `make mini-sequence`, `make gauntlet`, `make report`.

Deploying (API on Render, war room on Vercel, or `docker compose up --build`): see [`docs/DEPLOY.md`](docs/DEPLOY.md).

## Repo

- `backend/`: Python 3.12 (uv). Simulator (`sim/`), agent (`agent/`), LLM layer (`llm/`), memory (`memory/`), strategies, eval harness (`eval/`), Foresight, API.
- `web/`: Next.js war-room UI.
- `data/fixtures/`: the human side of the story (postmortems, Slack threads, feedback, runbooks, RFCs).
- `docs/`: [`HOW_WE_USE_HINDSIGHT.md`](docs/HOW_WE_USE_HINDSIGHT.md), [`HINDSIGHT_NOTES.md`](docs/HINDSIGHT_NOTES.md).

## Limitations

- The environment is simulated (SRE-Gym); telemetry, incidents and people are synthetic.
- Small N: 24 incidents, one seed by default.
- Memory Defense was not available to our Hindsight Cloud organisation; secrets and injection text are redacted client-side before retain.

## Disclaimer

Kestrel Pay, its engineers (Priya Raman, Marcus Oyelaran and the rest), and the payment processors acquirerx, paynova and smsbridge are fictional. All telemetry is simulated.
