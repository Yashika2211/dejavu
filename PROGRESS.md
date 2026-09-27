# Progress

Live checklist. Phases are gates (spec Section 15).

## Phase 0: setup + Hindsight spike

- [x] Repo initialised, spec saved, remote `Yashika2211/dejavu`
- [x] CLAUDE.md, PROGRESS.md, DECISIONS.md
- [x] `.env.example`, backend `pyproject.toml` (uv, Python 3.12)
- [x] `dejavu.config` (pydantic-settings)
- [x] Health checks: Groq `GET /models`, Hindsight version (`make health`)
- [x] Hindsight SDK signatures verified (inspect + OpenAPI + docs), mismatches in `docs/HINDSIGHT_NOTES.md`
- [x] `scripts/spike_hindsight.py` with PASS/FAIL table (26 checks; runs, blocked on key)
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
- [ ] Human fixtures: Day-0 history, migration artifacts, per-incident postmortem / Slack thread / feedback

## Phase 2: agent + LLM layer + amnesiac
- [ ] not started

## Phase 3: DejaVu memory strategy
- [ ] not started

## Phase 4: the Gauntlet
- [ ] not started

## Phase 5: API + UI
- [ ] not started

## Phase 6: advanced
- [ ] not started

## Phase 7: polish and submission
- [ ] not started
