# Progress

Live checklist. Phases are gates (spec Section 15).

## Phase 0: setup + Hindsight spike

- [x] Repo initialised, spec saved, remote `Yashika2211/dejavu`
- [x] CLAUDE.md, PROGRESS.md, DECISIONS.md
- [x] `.env.example`, backend `pyproject.toml` (uv, Python 3.12)
- [x] `dejavu.config` (pydantic-settings)
- [x] Health checks: Groq `GET /models`, Hindsight version (`make health`)
- [x] Hindsight SDK signatures verified (inspect + OpenAPI + docs), mismatches in `docs/HINDSIGHT_NOTES.md`
- [x] `scripts/spike_hindsight.py` with PASS/FAIL table (27 checks, including chunk mode for the RAG ablation; runs, blocked on key)
- [x] Makefile (`setup`, `test`, `lint`, `fmt`, `health`, `spike`, `web`)
- [x] `web/` Next.js 16 scaffold (pnpm), design tokens, builds
- [ ] CI workflow: written locally, push blocked (token lacks `workflow` scope)
- [x] `docs/HINDSIGHT_NOTES.md` (offline verification; live timings pending)
- [x] `make test` runs: 27 passed, 1 live test skipped
- [ ] **Blocked:** `HINDSIGHT_API_KEY` and `GROQ_API_KEY` needed in `.env` to run the live spike
- [ ] **DoD:** spike table all PASS or every FAIL documented with a workaround
- [ ] Paused for review

## Phase 1: SRE-Gym

- [x] Scenario DSL (`sim/scenario.py`): metric_shift, log_inject, trace_delay, event, placeholders with offsets, migration-conditional effects
- [x] 12 + 3 archetypes (`sim/scenarios/*.yaml`), each validated across seeds and migration phases
- [x] Gauntlet schedule (24 incidents), held-out set (6), demo incidents (`schedule.yaml`, `sim/schedule.py`)
- [x] Generators: metrics (baseline + incident layers), logs (12 native formats), traces, change events, alerts
- [x] Parquet telemetry + DuckDB store; deterministic content hash
- [x] Remediation engine (resolves / transient / partial / no effect / harmful) and severity curve
- [x] Impact model (excess failed payments x ₹1,850)
- [x] Agent tools (10), bounded to 700 tokens, visibility capped at now
- [x] Runbooks (8, some stale on purpose)
- [x] `make sim-demo`
- [x] **DoD tests:** determinism per seed, discriminators per archetype, token bounds, remediation outcomes per archetype (296 tests pass)
- [x] Human fixtures: Day-0 history (6 postmortems, handbook, 2 RFCs), M1/M2 RFCs + announcements, 24 x (postmortem, Slack thread, feedback)
- [x] Fact sheets (`scripts/generate_fixtures.py`): human paths replayed in the simulator; tests prove every postmortem number matches
- [x] **Phase 1 complete** (352 tests)

## Phase 2: agent + LLM layer + amnesiac

- [x] Groq client over the OpenAI SDK: own retry policy (429 retry-after, 5xx backoff), 413 / tool_use_failed / unknown-model errors, call accounting and cost
- [x] Per-model rate limiter (RPM / TPM / RPD) that honours retry-after
- [x] Tool calling: one call per turn, salvage of `failed_generation`, re-prompts, model fallback, JSON-mode emulation
- [x] Startup model resolution (`GET /models`, unavailable models disabled)
- [x] Agent schemas, system prompt, budgeted context (running summary + last steps verbatim, <= 6,000 tokens)
- [x] Investigation loop: briefing injection, untrusted wrapping, sanitizer (secrets + injection), invalid-arg retries, final diagnosis, remediation plan, approvals hook, replayable JSONL traces
- [x] Amnesiac strategy; memory strategy contract
- [x] Grader (correct, ttd, MTTR rules, wasted steps, harmful actions, precedent precision, cost, ₹ at risk)
- [x] `scripts/run_incident.py` / `make run`
- [x] **DoD (offline):** loop tests with a scripted model, error-handling tests (tool_use_failed, invalid args, 429 retry-after, 5xx, 413), injection + leaked-token test, grader tests (414 tests pass)
- [ ] **DoD (live, blocked on GROQ_API_KEY):** amnesiac end to end on real incidents; live injection test on incident 16

## Phase 3: DejaVu memory strategy

- [x] Memory adapter over the SDK + REST (`memory/hindsight_adapter.py`), one `MemoryBackend` interface, degraded mode on any failure
- [x] Idempotent bank setup for the `dejavu` and `rag` profiles (`memory/bank_setup.py`, `scripts/bank_setup.py`, `make bank`)
- [x] Missions, dispositions, entity labels, Memory Defense, 5 directives, 11 mental models (8 services + triage playbook, change-risk register, team conventions)
- [x] Day-0 import with original dates; two PDFs through `retain_files` (`memory/day0.py`)
- [x] Write path (`memory/writer.py`): alert timeline (append), first-person investigation log, outcome, change log, feedback, postmortem; low-cardinality tags, explicit observation scopes, entities, sanitised content
- [x] Settle (`memory/settle.py`): retains, consolidation, pending work, manual refresh of paused mental models, timeouts
- [x] Read path (`memory/reader.py`): triage brief (observations + reflect with `TriageBrief` schema and `based_on`, retry, fallback), `recall_memory` lookups
- [x] DejaVu strategy (`strategies/dejavu.py`) and calendar-order sequence runner (`eval/sequence.py`)
- [x] NaiveRAG ablation (`strategies/rag.py`) inheriting DejaVu's write path
- [x] **DoD (offline):** bank setup idempotent, Day-0 import, write path, settle, briefing + provenance, lookups, degraded mode, three-incident mini-sequence plumbing (all with a fake memory; 444 tests pass, 4 live skipped)
- [ ] **DoD (live, blocked on both keys):** `make mini-sequence` (incidents 1 → 5 → 12 on a throwaway bank) shows memory moments and temporal validity; mental models refreshing; live mini-sequence test

## Phase 4: the Gauntlet

- [x] Harness (`eval/gauntlet.py`, `make gauntlet`): strategies take turns per incident, checkpoint per (incident, strategy) pair, `--resume`, `--n`, `--dry-run` estimate, pinned model, ungraded aborts on LLM errors, memory growth per incident
- [x] Metrics (`eval/metrics.py`): accuracy, MTTR, time to diagnosis, wasted and harmful steps, ₹ at risk, tokens, cost, precedent precision; per incident kind; paired comparison with the amnesiac; learning curves
- [x] Report (`eval/report.py`, `make report`): `summary.json`, chart-ready `chart_data.json`, charts (MTTR per incident with M1/M2 markers and look-alike shading, cumulative accuracy, useful vs wasted steps, memory growth, cost); `--publish` writes `docs/EVAL_RESULTS.md` with limitations
- [x] Snapshots (`memory/snapshots.py`): `kestrel-ops-day1` after the Day-0 import, `kestrel-ops-trained` after the full run (`--snapshots`)
- [x] NaiveRAG strategy wired into the Gauntlet
- [x] **Offline tests:** metrics, report, abort and resume with a scripted model and the fake memory (458 tests pass, 4 live skipped)
- [ ] **Blocked on both keys:** `make gauntlet-quick` (6 incidents, amnesiac and dejavu), then `make gauntlet SNAPSHOTS=1` (24 incidents, all three strategies), then `make report PUBLISH=1`
- [ ] Paused to show results (needs the runs above)

## Phase 5: API + UI
- [ ] not started

## Phase 6: advanced
- [ ] not started

## Phase 7: polish and submission
- [ ] not started
