# DejaVu

**The on-call agent that has seen this before.**

Every postmortem is hindsight, and it usually dies in a Google Doc. DejaVu turns it into memory, then into foresight. The second time production breaks the same way, it's fixed in minutes. The third time, it's prevented.

DejaVu investigates production alerts with tools, diagnoses the root cause, proposes a remediation for a human to approve, and drafts the postmortem. It learns from the outcome through [Hindsight](https://hindsight.vectorize.io) memory: which signals separate look-alike causes, which fixes failed or made things worse, and which old fixes stopped working after a migration.

> Status: early build. See [`PROGRESS.md`](PROGRESS.md). Results and screenshots will be added once the eval harness has produced them.

## Quickstart

```
cp .env.example .env      # add GROQ_API_KEY and HINDSIGHT_API_KEY
make setup
make health               # Groq models + Hindsight version
make spike                # Hindsight memory-contract spike
make test
```

## Repo

- `backend/`: Python 3.12 (uv). Simulator, agent, memory strategies, eval harness, API.
- `web/`: Next.js war-room UI.
- `docs/`: design notes, including [`HINDSIGHT_NOTES.md`](docs/HINDSIGHT_NOTES.md).

## Disclaimer

Kestrel Pay, its engineers (Priya Raman, Marcus Oyelaran and the rest), and the payment processors acquirerx, paynova and smsbridge are fictional. All telemetry is simulated.
