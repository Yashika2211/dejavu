# Decisions

One line each: decision, then why.

- Spec reconstructed from two pastes; the few lost words at the end of 7.2 are read as "feedback, postmortems, Slack threads". The surrounding rules make the intent unambiguous.
- Commits authored as `Yashika` with the GitHub no-reply address and no AI trailers. The owner asked for this, and it overrides spec rule 5's "commit at green checkpoints" cadence: every file or edit gets its own commit and push.
- Python 3.12 is installed through uv (the system Python is 3.9). The spec pins 3.12, and uv manages it per project.
- SDK gaps (operation polling, curation, graph, entities, stats, consolidate, scopes) go through a small httpx REST client, not the SDK's private `_*_api` attributes. It is explicit, testable with respx, and survives SDK refactors.
- Symptom classes are `latency_p99`, `error_rate_5xx`, `auth_failures`, `otp_delays` and `write_failures`. They follow the alert level of the archetype table's look-alike groups and keep `symptom:` tags low-cardinality.
- Entity-label groups keep `tag: false`. Label tags would change every memory's tag set and interfere with observation scoping.
- Tagged mental models set `trigger.tags_match = "any"`. The server's default for tagged models is `all_strict`, which hides untagged Day-0 documents.
- The leaked token in incident 16 is JWT-shaped and generated from the seed at runtime. Memory Defense's `jwt` pattern catches it, and nothing secret-shaped is committed.
- PDFs for `retain_files` are generated with fpdf2 (pure Python, tiny) instead of committing binary fixtures.
- Kept Next.js 16's generated `web/AGENTS.md`. It points agents at the bundled docs for this Next version, and `next dev` re-creates it anyway.
- `.github/workflows/ci.yml` exists locally but isn't pushed: the GitHub token lacks the `workflow` scope. It gets pushed after `gh auth refresh -s workflow`.
- Phase 1 started before the Phase 0 live spike passed. The owner said "go" with no keys configured; the simulator needs no keys, and the spike runs as soon as `.env` has them.
