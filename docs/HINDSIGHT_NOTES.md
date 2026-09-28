# Hindsight notes

What we verified about Hindsight before building on it, and what surprised us. Versions: `hindsight-client` 0.10.1, Hindsight Cloud API 0.10.1 (`GET /version`, 28 Sep 2026). Sources: `inspect.signature` on the installed SDK, the SDK source, `openapi.json` and `llms-full.txt`.

## 1. SDK surface vs the build spec

| Spec assumption | Reality in 0.10.1 | What we do |
|---|---|---|
| `create_bank(..., entity_labels, memory_defense)` | `create_bank` takes missions, dispositions and retrieval toggles only | Create the bank, then set everything with `update_bank_config` |
| `retain(..., observation_scopes=...)` | Single-item `aretain` has no `observation_scopes` or `strategy` | Always write through `aretain_batch(items=[...])`; items accept `observation_scopes`, `update_mode`, `entities`, `metadata`, `tags`, `timestamp` |
| Poll operations from the SDK | No SDK method | `GET /v1/default/banks/{bank}/operations/{id}` via `dejavu.memory.rest.HindsightRest.wait_for_operation` |
| Invalidate / restore through a memories API | No SDK method | `PATCH /memories/{id}` with `{"state": "invalidated" \| "valid", "reason"}`. Only world/experience facts can be curated; observations are derived |
| Graph, entities, bank stats, consolidate | No SDK methods | REST: `/graph`, `/entities`, `/stats`, `POST /consolidate` |
| Reflect `based_on` kwarg name unknown | `areflect(include_facts=True)` → `based_on = {memories, mental_models, directives}` | Always pass `include_facts=True` for provenance |
| Reflect default budget | SDK default is `low` (recall defaults to `mid`) | Pass `budget` explicitly everywhere |
| `query_timestamp` on recall and reflect | Recall has it; reflect has none (SDK and `ReflectRequest`) | Triage and Ask queries state the simulated time in their text ("It is 19:42 IST on Mon 24 Aug 2026"). Banks never hold documents from after the incident, so reflect anchoring to real time can't leak the future |
| Knowledge pages "if available" | Available: folders + pages, each page backed by a mental model | Use them for living runbooks |
| Clone returns a bank | `aclone_bank(src, target, include_data, include_bank_config, include_history)` returns an **operation id** (HTTP 202). The target must not exist | Poll the operation before using the clone |
| Export | `aexport_bank` polls internally and returns the archive `bytes` | Direct |

The SDK retries transient failures itself (`max_attempts=3`) and defaults to a 300 s timeout.

## 2. Semantics that matter for DejaVu

- **Tags and `tags_match`.** Modes are `any` (OR, untagged included), `all` (AND, untagged included), `any_strict` / `all_strict` (untagged excluded) and `exact`. Triage uses `any` so untagged handbook material stays visible.
- **Observation scopes.** Per retain item: `combined` (the default: one pass over the item's whole tag set), `per_tag`, `all_combinations`, `shared`, or an explicit list of tag lists (one consolidation pass per inner list). We send `[["service:<svc>"], ["symptom:<class>"]]`. `GET /observations/scopes` lists the resulting scopes with counts.
- **Tagged mental models are strict by default.** When a model has tags and no `trigger.tags_match`, refresh uses `all_strict`, so a `service:ledger-svc` model never sees untagged Day-0 documents. Our service models set `trigger.tags_match = "any"`.
- **Refresh triggers.** `refresh_after_consolidation` and `refresh_cron` are mutually exclusive. A failed refresh pauses automatic refreshes until a manual refresh succeeds, so the settle step must check `last_refresh_failed_at`.
- **Knowledge page default trigger:** `{"mode": "delta", "fact_types": ["observation"], "exclude_mental_models": true, "refresh_after_consolidation": true}`. A trigger sent at creation is a patch over that default.
- **World vs experience** is decided by who is speaking, not by grammar. First-person text becomes `experience` only when the item's `context` says the bank's own agent is the speaker. Our investigation logs use: *"DejaVu, the on-call agent that owns this memory bank, is speaking: its own first-person investigation log for INC-xxxx"*.
- **`update_mode: "append"`** concatenates to the stored document and re-extracts. It routes on the metadata sent with the append call, so resend the same metadata.
- **`operation_id`** gives idempotent retries for *async* retains only; sync retain ignores it with a warning.
- **Entity labels** are label groups `{key, description, type: value|multi-values|text|multi-text|map, optional, tag, values: [{value, description}]}`. With `tag: true` a label is also written as a tag. We leave it `false`, because extra tags would change each memory's tag set and interfere with scoping.
- **Memory Defense** (per-bank `memory_defense` config) implements one rule in the open-source server: `sensitive_data`, with `redact` or `block`. It has 45 regex patterns (JWTs, `gsk_` Groq keys, GitHub tokens, DB URLs, PEM keys and more). Redaction writes `[REDACTED:<label>]` into both memory units and the stored document body. It only applies to future retains. Our runtime leaked token is therefore JWT-shaped (`dejavu.sim.fake_secrets.fake_jwt`) so the `jwt` pattern catches it. No prompt-injection rule is documented; the spike checks whether Cloud accepts one.
- **Consolidation** runs automatically after retains (`enable_auto_consolidation`, default on). `POST /consolidate` forces a run and deduplicates against a pending task. `GET /stats` exposes `pending_consolidation`, `total_observations` and `last_consolidated_at`, which the settle step polls.
- **`/version` is public** on Cloud. `features.worker` and `features.bank_llm_health` are reported off on the API node.

## 3. Live spike results

`make spike` runs `backend/scripts/spike_hindsight.py` against the configured server on a throwaway bank. The run has not happened yet because `HINDSIGHT_API_KEY` isn't configured. Timings and pass/fail results go here after the first run:

| Measure | Value |
|---|---|
| Spike table | {{placeholder}} |
| Sync retain of one postmortem | {{placeholder}} |
| Async retain of 4 items (submit → completed) | {{placeholder}} |
| Operation completed → fact recallable | {{placeholder}} |
| Consolidation trigger → observations present | {{placeholder}} |
| Observation scopes created | {{placeholder}} |
| Investigation log fact type | {{placeholder}} |
| Prompt-injection rule on Cloud | {{placeholder}} |
