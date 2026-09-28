# DejaVu: working notes for Claude Code

DejaVu is an on-call SRE agent for the fictional fintech Kestrel Pay. It learns from every incident through Hindsight memory and gets measurably faster on recurrences. `DEJAVU_BUILD_SPEC.md` is the source of truth for scope; read the relevant section before starting any phase.

## Where things live

- `backend/`: Python 3.12 package `dejavu` (uv-managed). Simulator (`sim/`), agent loop (`agent/`), memory strategies (`strategies/`), Hindsight integration (`memory/`), eval harness (`eval/`), FastAPI (`api/`).
- `backend/scripts/`: one-off and operational scripts (`spike_hindsight.py`, fixture generation, Gauntlet runner).
- `web/`: Next.js App Router war-room UI (pnpm).
- `data/fixtures/`: committed human artifacts. `data/incidents/`, `data/runs/`: generated, gitignored.
- `docs/`: `HINDSIGHT_NOTES.md` records every observed SDK/server behaviour. Check it before using any Hindsight call.

## Commands

```
make setup     # uv sync + pnpm install
make test      # ruff + pytest (live tests skipped without keys)
make health    # Groq model list + Hindsight version
make spike     # Hindsight memory-contract spike against the real server
make dev       # api + web
```

## Rules

- Phases in spec Section 15 are gates. `PROGRESS.md` is the live checklist; `DECISIONS.md` gets one line per non-blocking choice.
- The installed Hindsight SDK beats the spec's snippets. Verify signatures with `inspect.signature` / OpenAPI and record mismatches in `docs/HINDSIGHT_NOTES.md`.
- Never fabricate numbers. Anything user-facing comes from an eval run or is `{{placeholder}}`.
- Secrets only in `.env`. Fake secret-shaped strings are generated at runtime from the seed, never committed.
- Tags: never `incident:<id>` (fragments observations). Incident IDs go in `document_id` and `metadata`.
- Always pass `timestamp` on retain and `query_timestamp` on recall (simulated time). Reflect has no `query_timestamp`; state the time in the query text.
- Archetype ids/titles never appear in telemetry, tool output or incident IDs.
- Typed Python, Pydantic v2, ruff-clean, small files, docstrings on public modules, tests for everything deterministic.

## Git

- Remote: `https://github.com/Yashika2211/dejavu`, branch `main`.
- Commit and push after every file or edit, one small commit each, short lowercase messages.
- Author is only `Yashika <163101486+Yashika2211@users.noreply.github.com>` (repo-local config). No Co-Authored-By or AI attribution lines, ever.
