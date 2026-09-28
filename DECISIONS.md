# Decisions

One line each: decision, then why.

- Spec reconstructed from two pastes; the few lost words at the end of 7.2 are read as "feedback, postmortems, Slack threads". The surrounding rules make the intent unambiguous.
- Commits authored as `Yashika` with the GitHub no-reply address and no AI trailers. The owner asked for this, and it overrides spec rule 5's "commit at green checkpoints" cadence: every file or edit gets its own commit and push.
- Python 3.12 is installed through uv (the system Python is 3.9). The spec pins 3.12, and uv manages it per project.
- SDK gaps (operation polling, curation, graph, entities, stats, consolidate, scopes) go through a small httpx REST client, not the SDK's private `_*_api` attributes. It is explicit, testable with respx, and survives SDK refactors.
- Symptom classes are `latency_p99`, `error_rate_5xx`, `auth_failures` and `write_failures`, one per alert family. The OTP-delay archetypes (Kafka rebalance, SMS quota) fire the auth alert, which is what makes them look-alikes in group B.
- Added the `config_tuning` remediation family for fixes no other family covers (Kafka `max.poll.interval.ms`, NodeLocal DNSCache, JWKS refresh).
- Entity-label groups keep `tag: false`. Label tags would change every memory's tag set and interfere with observation scoping.
- Tagged mental models set `trigger.tags_match = "any"`. The server's default for tagged models is `all_strict`, which hides untagged Day-0 documents.
- The leaked token in incident 16 is JWT-shaped and generated from the seed at runtime. Memory Defense's `jwt` pattern catches it, and nothing secret-shaped is committed.
- PDFs for `retain_files` are generated with fpdf2 (pure Python, tiny) instead of committing binary fixtures.
- Kept Next.js 16's generated `web/AGENTS.md`. It points agents at the bundled docs for this Next version, and `next dev` re-creates it anyway.
- `.github/workflows/ci.yml` exists locally but isn't pushed: the GitHub token lacks the `workflow` scope. It gets pushed after `gh auth refresh -s workflow`.
- Phase 1 started before the Phase 0 live spike passed. The owner said "go" with no keys configured; the simulator needs no keys, and the spike runs as soon as `.env` has them.
- Human-voice fixtures were written by Claude Code from simulator fact sheets, not generated through Groq (no key was available). `generate_fixtures.py` produces the fact sheets, and a test pins every figure in each postmortem to them.
- Incident ticket numbers come from the calendar, not the run seed, so fixtures can cite them (e.g. "the INC-4127 pattern") across seeds. Details that vary with the seed, such as the skewed node's name, are exact only for seed 42.
- Default token prices: gpt-oss-120b $0.15/$0.60 per 1M tokens (from the spec); gpt-oss-20b $0.075/$0.30 and qwen3.8-27b $0.29/$0.59 are estimates. Reports label costs as estimates, and `LLM_PRICES` overrides them.
- Day-0 PDFs go through `retain_files` as the spec asks. Its `files_metadata` has no documented timestamp and `PATCH /documents` only updates tags, so those two documents may be dated at upload time. Their text carries explicit dates for temporal extraction, and the spike checks whether an undocumented `timestamp` is honoured.
- Triage reflect states the incident time in its query, because reflect has no `query_timestamp` (0.10.1). Banks never hold documents from after the incident, so nothing leaks.
- The change log is retained per incident (`changes-INC-xxxx`, the six hours before the alert) rather than as daily batches. Each incident gets the changes that matter to it as one document.
- NaiveRAG subclasses DejaVu and overrides only the read path. Inheriting the write path guarantees the same documents in the same order (spec 6.8).
- The RAG bank uses Hindsight's chunk mode until the spike's chunk-mode check says otherwise; if it fails, RAG moves to a local embedding store as spec 6.8 allows.
- A 429 whose retry-after exceeds 120 s raises `QuotaExhaustedError` instead of sleeping. Waiting out a daily cap inside one request would stall a run for hours.
- The Gauntlet pins the primary model with no fallbacks; a daily cap stops the run for `--resume`. Switching models mid-run would confound the strategy comparison.
- Gauntlet strategies take turns incident by incident, so a stopped run leaves every strategy at the same point and partial results stay comparable.
- A run that ends in an LLM error is not graded, and memory learns nothing from it; it is retried on resume. It measures the API, not the agent.
- Gauntlet traces go to `data/runs/<run-id>/` (gitignored, reproducible); results, summaries and charts go to `data/eval/<run-id>/` (committed, the record).
- `docs/EVAL_RESULTS.md` is only written by `report --publish` from a chosen run, so quick and partial runs never overwrite published results.
- Snapshot banks are written only with `--snapshots`. Day1 is cloned straight after the Day-0 import, before the bank counts as prepared, so it can never contain an incident.
- Incident kinds (first, recurrence, look-alike, novel) come from the schedule's notes and order, so the per-kind breakdown has a single definition.
