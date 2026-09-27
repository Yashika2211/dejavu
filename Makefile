.PHONY: setup test lint fmt health spike sim-demo web

BACKEND := cd backend &&
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

web:              ## Next.js dev server
	$(WEB) pnpm dev
