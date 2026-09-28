# DejaVu web

The war-room UI for DejaVu (Next.js App Router, Tailwind, pnpm). It talks to the FastAPI backend (`make api`) over REST and Server-Sent Events; set `NEXT_PUBLIC_API_URL` if the API is not on `http://localhost:8000`.

```
pnpm install
pnpm dev      # http://localhost:3000 (or `make dev` from the repo root for api + web)
pnpm lint
pnpm build
```

| Screen | Route | What it shows |
|---|---|---|
| War Room | `/` | One incident investigated live: alert, recent changes, every step with its rationale, hypotheses, déjà vu cards with provenance, approvals, diagnosis, feedback |
| Race | `/race` | The same incident, two responders side by side (no memory, naive RAG or day 1 vs day 42), then a scoreboard |
| Memory | `/memory` | Living runbooks, belief timelines with diffs, the explorer with Wrong / outdated and Restore, brain growth |
| Learning | `/learning` | KPIs and learning curves from a real Gauntlet run under `data/eval` (an empty state until one exists) |
| Foresight | `/foresight` | Pending changes, risk reviews with and without memory, and what holding or shipping would have done |

Ask DejaVu opens anywhere with ⌘K. Design tokens live in `src/app/globals.css` (spec Section 11.1); violet (`memory`) is reserved for things DejaVu remembered.
