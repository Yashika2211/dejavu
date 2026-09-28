.PHONY: setup test lint fmt health spike sim-demo run bank mini-sequence gauntlet gauntlet-quick report api dev web

BACKEND := cd backend &&
ALL_STRATEGIES := amnesiac,rag,dejavu
WEB := cd web &&

setup:            ## install backend (uv) and web (pnpm) dependencies
	$(BACKEND) uv sync
	$(WEB) pnpm install

test: lint        ## ruff + pytest (live tests skip without keys)
	$(BACKEND) uv run pytest -q

lint:
	$(BACKEND) uv run ruff check . && uv run ruff format --check .
	$(WEB) pnpm lint

fmt:
	$(BACKEND) uv run ruff format . && uv run ruff check --fix .

health:           ## Groq model list + Hindsight version
	$(BACKEND) uv run python -m dejavu.health

spike:            ## Hindsight memory-contract spike (KEEP=1 keeps the banks)
	$(BACKEND) uv run python scripts/spike_hindsight.py $(if $(KEEP),--keep,)

sim-demo:         ## readable oracle investigation of one incident (N=1..24, default 12)
	$(BACKEND) uv run python scripts/sim_demo.py $(if $(N),--n $(N),)

run:              ## investigate one incident with the real model (N=1..24, STRATEGY=amnesiac|dejavu, BANK=)
	$(BACKEND) uv run python scripts/run_incident.py --n $(or $(N),1) --strategy $(or $(STRATEGY),amnesiac) $(if $(BANK),--bank $(BANK),)

bank:             ## set up a memory bank and import Day-0 (BANK=kestrel-ops-live, PROFILE=dejavu|rag)
	$(BACKEND) uv run python scripts/bank_setup.py --bank $(or $(BANK),kestrel-ops-live) --profile $(or $(PROFILE),dejavu) --day0

mini-sequence:    ## live Phase 3 check: incidents 1, 5, 12 with DejaVu on a throwaway bank
	$(BACKEND) uv run python scripts/mini_sequence.py

gauntlet:         ## the full Gauntlet (STRATEGIES=amnesiac,rag,dejavu N=24 SEED=42; RESUME=1, DRY=1, SNAPSHOTS=1)
	$(BACKEND) uv run python -m dejavu.eval.gauntlet $(if $(RESUME),--resume,--strategies $(or $(STRATEGIES),$(ALL_STRATEGIES)) --seed $(or $(SEED),42)) $(if $(N),--n $(N),) $(if $(SNAPSHOTS),--snapshots,) $(if $(DRY),--dry-run,)

gauntlet-quick:   ## quick mode: the first 6 incidents, amnesiac and dejavu
	$(BACKEND) uv run python -m dejavu.eval.gauntlet --strategies amnesiac,dejavu --n 6 $(if $(DRY),--dry-run,)

report:           ## charts and summary for a run (RUN=<run id>, default the latest; PUBLISH=1 rewrites docs/EVAL_RESULTS.md)
	$(BACKEND) uv run python -m dejavu.eval.report $(if $(RUN),--run-id $(RUN),) $(if $(PUBLISH),--publish,)

api:              ## FastAPI with reload on API_PORT (default 8000)
	$(BACKEND) uv run uvicorn dejavu.api.main:app --reload --port $(or $(API_PORT),8000)

dev:              ## api and web together
	$(MAKE) -j2 api web

web:              ## Next.js dev server
	$(WEB) pnpm dev
