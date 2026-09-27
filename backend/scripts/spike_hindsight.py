"""Phase 0 spike: prove the Hindsight memory contract DejaVu depends on.

Exercises every Hindsight capability the build relies on against the configured server, on a
throwaway bank, and prints a PASS / FAIL / SKIP table. Observed response shapes and timings are
written to data/spike/<bank>.json and summarised in docs/HINDSIGHT_NOTES.md.

    uv run python scripts/spike_hindsight.py           # delete the spike banks afterwards
    uv run python scripts/spike_hindsight.py --keep    # keep them for inspection in the UI
"""

import argparse
import asyncio
import json
import sys
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import spike_content as doc
from fpdf import FPDF
from hindsight_client import Hindsight
from rich.console import Console
from rich.table import Table

from dejavu.config import REPO_ROOT, get_settings
from dejavu.memory.missions import (
    DIRECTIVES,
    DISPOSITION,
    ENTITY_LABELS,
    MEMORY_DEFENSE,
    OBSERVATIONS_MISSION,
    REFLECT_MISSION,
    RETAIN_MISSION,
)
from dejavu.memory.rest import HindsightRest
from dejavu.sim.fake_secrets import fake_jwt

SERVICE_TAG = "service:ledger-svc"
SYMPTOM_TAG = "symptom:latency_p99"
BASE_TAGS = ["org:kestrel", SERVICE_TAG, SYMPTOM_TAG]
SCOPES = [[SERVICE_TAG], [SYMPTOM_TAG]]
ENTITIES = [{"text": "ledger-svc", "type": "SERVICE"}, {"text": "Marcus Oyelaran", "type": "PERSON"}]
INCIDENT_TIME = "2026-08-24T19:42:00+05:30"
MM_ID = "svc-ledger-svc-failure-modes"

TRIAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "likely_causes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cause": {"type": "string"},
                    "prior": {"type": "number"},
                    "precedent_incident_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["cause", "prior", "precedent_incident_ids"],
            },
        },
        "avoid": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["likely_causes", "avoid"],
}

Status = Literal["PASS", "FAIL", "SKIP"]


class SpikeCheckError(Exception):
    """A spike expectation did not hold."""


def check(condition: object, message: str) -> None:
    if not condition:
        raise SpikeCheckError(message)


def dump(obj: Any) -> Any:
    """Best-effort JSON-able view of SDK models, dicts and lists."""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [dump(o) for o in obj]
    return obj


@dataclass
class StepResult:
    name: str
    status: Status
    seconds: float
    detail: str


@dataclass
class Spike:
    """Runs named checks in order, skipping any whose prerequisites failed."""

    hs: Hindsight
    rest: HindsightRest
    bank: str
    results: list[StepResult] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)

    def passed(self, name: str) -> bool:
        return any(r.name == name and r.status == "PASS" for r in self.results)

    async def run(self, name: str, fn: Callable[[], Awaitable[str]], *, needs: tuple[str, ...] = ()) -> None:
        blocked = [n for n in needs if not self.passed(n)]
        if blocked:
            self.results.append(StepResult(name, "SKIP", 0.0, f"needs: {', '.join(blocked)}"))
            return
        start = time.perf_counter()
        try:
            detail, status = await fn(), "PASS"
        except Exception as exc:
            detail, status = f"{type(exc).__name__}: {exc}"[:500], "FAIL"
        self.results.append(StepResult(name, status, round(time.perf_counter() - start, 2), detail))

    # helpers ----------------------------------------------------------------------------

    async def retain(self, items: list[dict[str, Any]], *, operation_id: str | None = None) -> Any:
        """Retain items; async (with an operation id) when `operation_id` is given."""
        return await self.hs.aretain_batch(
            bank_id=self.bank,
            items=items,
            retain_async=operation_id is not None,
            operation_id=operation_id,
        )

    async def doc_memories(self, document_id: str, **filters: Any) -> list[dict[str, Any]]:
        page = await self.rest.list_memories(self.bank, document_id=document_id, limit=100, **filters)
        return page["items"]

    async def wait_op(self, operation_id: str, *, bank: str | None = None, timeout_s: float = 300) -> float:
        start = time.perf_counter()
        status = await self.rest.wait_for_operation(bank or self.bank, operation_id, timeout_s=timeout_s)
        check(status["status"] == "completed", f"operation {operation_id} ended {status['status']}")
        return round(time.perf_counter() - start, 1)


def item(
    content: str,
    *,
    context: str,
    timestamp: str,
    document_id: str,
    kind: str,
    tagged: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    """A retain item following the DejaVu write-path conventions (spec 6.3 / 6.4)."""
    out: dict[str, Any] = {
        "content": content,
        "context": context,
        "timestamp": timestamp,
        "document_id": document_id,
        **extra,
    }
    if tagged:
        out["tags"] = [*BASE_TAGS, f"kind:{kind}"]
        out["observation_scopes"] = SCOPES
    return out


def write_pdf(path: Path, lines: tuple[str, ...]) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in lines:
        pdf.multi_cell(0, 7, line, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))


async def run_spike(spike: Spike, clone_bank: str) -> None:
    hs, rest, bank, notes = spike.hs, spike.rest, spike.bank, spike.notes
    token = fake_jwt(seed=16)

    async def create_bank() -> str:
        profile = await hs.acreate_bank(bank, name="DejaVu spike")
        notes["bank_profile"] = dump(profile)
        return f"created {bank}"

    async def update_config() -> str:
        await hs.aupdate_bank_config(
            bank,
            retain_mission=RETAIN_MISSION,
            observations_mission=OBSERVATIONS_MISSION,
            reflect_mission=REFLECT_MISSION,
            enable_observations=True,
            entity_labels=ENTITY_LABELS,
            memory_defense=MEMORY_DEFENSE,
            **DISPOSITION,
        )
        cfg = await hs.aget_bank_config(bank)
        notes["bank_config"] = cfg
        blob = json.dumps(cfg)
        missing = [
            label
            for label, needle in [
                ("retain_mission", RETAIN_MISSION[:60]),
                ("observations_mission", OBSERVATIONS_MISSION[:60]),
                ("reflect_mission", REFLECT_MISSION[:60]),
                ("entity_labels", "failure_mode"),
                ("memory_defense", "sensitive_data"),
            ]
            if needle not in blob
        ]
        check(not missing, f"config did not persist: {missing}")
        return "missions, dispositions, observations, entity labels, memory defense persisted"

    async def injection_rule() -> str:
        rules = [*MEMORY_DEFENSE["rules"], {"on": "prompt_injection", "action": "block"}]
        try:
            await hs.aupdate_bank_config(bank, memory_defense={"enabled": True, "rules": rules})
            cfg = await hs.aget_bank_config(bank)
            notes["injection_rule_config"] = cfg
            check("prompt_injection" in json.dumps(cfg), "rule accepted but not persisted")
        finally:
            await hs.aupdate_bank_config(bank, memory_defense=MEMORY_DEFENSE)
        return "prompt_injection/block rule accepted"

    async def directives() -> str:
        for d in DIRECTIVES:
            await hs.acreate_directive(bank_id=bank, name=d.name, content=d.content)
        listed = dump(await hs.alist_directives(bank))
        notes["directives_list"] = listed
        items = listed.get("items", listed) if isinstance(listed, dict) else listed
        check(len(items) >= len(DIRECTIVES), f"expected {len(DIRECTIVES)} directives, got {len(items)}")
        return f"{len(items)} directives"

    async def retain_sync() -> str:
        resp = await spike.retain(
            [
                item(
                    doc.HIST_POSTMORTEM,
                    context="historical postmortem by Marcus Oyelaran",
                    timestamp="2026-07-14T11:20:00+05:30",
                    document_id="pm-hist-3902",
                    kind="postmortem",
                    metadata={"incident_id": "INC-3902", "author": "Marcus Oyelaran", "severity": "SEV-2"},
                    entities=ENTITIES,
                )
            ]
        )
        notes["retain_sync_response"] = dump(resp)
        mems = await spike.doc_memories("pm-hist-3902")
        notes["memory_unit_sample"] = mems[:2]
        check(mems, "no memory units for pm-hist-3902")
        check(any(SERVICE_TAG in (m.get("tags") or []) for m in mems), "tags missing on units")
        check(
            any((m.get("metadata") or {}).get("incident_id") == "INC-3902" for m in mems), "metadata missing"
        )
        types = sorted({m.get("fact_type") for m in mems})
        return f"{len(mems)} units, types {types}, tags + metadata present"

    async def retain_async() -> str:
        op_id = str(uuid.uuid4())
        items = [
            item(
                doc.STALE_RUNBOOK,
                context="runbook",
                timestamp="2026-03-02T10:00:00+05:30",
                document_id="rb-ledger-pool",
                kind="runbook",
            ),
            item(
                doc.OUTCOME,
                context="incident outcome",
                timestamp="2026-08-17T03:41:00+05:30",
                document_id="inc-4127-outcome",
                kind="outcome",
                metadata={"incident_id": "INC-4127"},
                entities=ENTITIES[:1],
            ),
            item(
                doc.INVESTIGATION_LOG,
                context=doc.INVESTIGATION_CONTEXT,
                timestamp="2026-08-17T03:36:00+05:30",
                document_id="inc-4127-investigation",
                kind="investigation",
                metadata={"incident_id": "INC-4127"},
            ),
            item(
                doc.HANDBOOK,
                context="on-call handbook",
                timestamp="2026-05-01T09:00:00+05:30",
                document_id="handbook",
                kind="handbook",
                tagged=False,
            ),
        ]
        submitted = time.perf_counter()
        resp = await spike.retain(items, operation_id=op_id)
        notes["retain_async_response"] = dump(resp)
        check(resp.operation_id == op_id, f"operation id not echoed: {resp.operation_id}")
        waited = await spike.wait_op(op_id)
        notes["async_retain_seconds"] = round(time.perf_counter() - submitted, 1)
        again = await spike.retain(items, operation_id=op_id)
        notes["resubmit_same_operation_id"] = dump(again)
        return f"4 items completed in {waited}s; resubmit returned op {again.operation_id}"

    async def recallable() -> str:
        start = time.perf_counter()
        while True:
            r = await hs.arecall(bank_id=bank, query="RB-ledger-pool maximum-pool-size Helm", budget="low")
            if any(x.document_id == "rb-ledger-pool" for x in r.results):
                break
            check(time.perf_counter() - start < 60, "runbook fact not recallable within 60s")
            await asyncio.sleep(2)
        notes["recallable_after_completed_s"] = round(time.perf_counter() - start, 1)
        return f"recallable {notes['recallable_after_completed_s']}s after operation completed"

    async def experience() -> str:
        mems = await spike.doc_memories("inc-4127-investigation")
        types = [m.get("fact_type") for m in mems]
        notes["investigation_fact_types"] = types
        check("experience" in types, f"first-person log landed as {types}")
        return f"fact types {types}"

    async def upsert() -> str:
        for text in (doc.UPSERT_V1, doc.UPSERT_V2):
            await spike.retain(
                [
                    item(
                        text,
                        context="postmortem written after resolution",
                        timestamp="2026-08-19T18:00:00+05:30",
                        document_id="pm-4188",
                        kind="postmortem",
                    )
                ]
            )
        texts = [m["text"] for m in await spike.doc_memories("pm-4188")]
        notes["upsert_texts"] = texts
        check(texts, "no units after upsert")
        check(not any("CoreDNS" in t for t in texts), "v1 facts survived the upsert")
        check(any("acquirerx" in t for t in texts), "v2 facts missing")
        return f"{len(texts)} units, only v2 content"

    async def append() -> str:
        common = {"context": "incident timeline", "document_id": "inc-4127-timeline", "kind": "timeline"}
        await spike.retain([item(doc.ALERT_FIRING, timestamp="2026-08-17T03:07:00+05:30", **common)])
        await spike.retain(
            [item(doc.ALERT_RESOLVED, timestamp="2026-08-17T03:41:00+05:30", update_mode="append", **common)]
        )
        stored = await rest.get_document(bank, "inc-4127-timeline")
        body = stored.get("original_text") or ""
        notes["append_document"] = {k: stored.get(k) for k in ("original_text", "memory_unit_count")}
        check("CheckoutLatencyP99High" in body and "03:41" in body, "document body lacks both parts")
        return f"document holds alert + resolution; {stored.get('memory_unit_count')} units"

    async def redaction() -> str:
        await spike.retain(
            [
                item(
                    doc.secret_debug_line(token),
                    context="debug log excerpt",
                    timestamp="2026-09-13T21:05:44+05:30",
                    document_id="inc-debug-log",
                    kind="timeline",
                )
            ]
        )
        stored = await rest.get_document(bank, "inc-debug-log")
        body = stored.get("original_text") or ""
        texts = [m["text"] for m in await spike.doc_memories("inc-debug-log")]
        notes["redacted_document_text"] = body
        check(token not in body, "token stored verbatim in document")
        check(not any(token in t for t in texts), "token stored verbatim in a memory unit")
        check("[REDACTED" in body, "no redaction marker in document")
        return "token replaced by a [REDACTED:...] marker"

    async def retain_pdf() -> str:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rfc-014-pgbouncer.pdf"
            write_pdf(path, doc.RFC_PGBOUNCER_LINES)
            resp = await hs.aretain_files(
                bank,
                [path],
                context="migration RFC",
                files_metadata=[
                    {
                        "document_id": "rfc-014",
                        "tags": ["org:kestrel", SERVICE_TAG, "kind:migration"],
                        "context": "migration RFC",
                    }
                ],
            )
        notes["retain_files_response"] = dump(resp)
        for op in resp.operation_ids:
            await spike.wait_op(op)
        mems = await spike.doc_memories("rfc-014")
        check(mems, "no units extracted from the PDF")
        return f"PDF ingested: {len(mems)} units"

    async def recall_full() -> str:
        r = await hs.arecall(
            bank_id=bank,
            query="checkout p99 latency, ledger-svc connection pool waiting",
            types=["world", "experience"],
            tags=[SERVICE_TAG, SYMPTOM_TAG],
            tags_match="any",
            budget="mid",
            max_tokens=1500,
            query_timestamp=INCIDENT_TIME,
            include_source_facts=True,
            trace=True,
        )
        notes["recall_result_sample"] = dump(r.results[:2])
        notes["recall_trace_keys"] = sorted((r.trace or {}).keys())
        check(r.results, "no results")
        check(r.trace, "no trace returned")
        return f"{len(r.results)} results, trace keys {notes['recall_trace_keys'][:5]}"

    async def untagged_visible() -> str:
        query = "who approves actions on postgres-ledger"
        seen: dict[str, bool] = {}
        for mode in ("any", "any_strict"):
            r = await hs.arecall(bank_id=bank, query=query, tags=[SERVICE_TAG], tags_match=mode, budget="low")
            seen[mode] = any(x.document_id == "handbook" for x in r.results)
        notes["untagged_handbook_visible"] = seen
        check(seen["any"] and not seen["any_strict"], f"unexpected visibility {seen}")
        return "untagged handbook visible with 'any', hidden with 'any_strict'"

    async def consolidation() -> str:
        start = time.perf_counter()
        resp = await rest.consolidate(bank)
        notes["consolidate_response"] = resp
        await spike.wait_op(resp["operation_id"])
        while (stats := await rest.stats(bank))["total_observations"] == 0 or stats.get(
            "pending_consolidation"
        ):
            check(time.perf_counter() - start < 300, f"consolidation not done: {stats}")
            await asyncio.sleep(3)
        notes["consolidation_seconds"] = round(time.perf_counter() - start, 1)
        return f"{stats['total_observations']} observations after {notes['consolidation_seconds']}s"

    async def scopes() -> str:
        listed = await rest.observation_scopes(bank)
        notes["observation_scopes"] = listed
        tag_sets = [sorted(s["tags"]) for s in listed["scopes"]]
        check([SERVICE_TAG] in tag_sets, f"no service scope in {tag_sets}")
        check([SYMPTOM_TAG] in tag_sets, f"no symptom scope in {tag_sets}")
        return f"scopes {tag_sets}"

    async def recall_observations() -> str:
        r = await hs.arecall(
            bank_id=bank,
            query="checkout p99 latency on ledger-svc",
            types=["observation"],
            tags=[SERVICE_TAG, SYMPTOM_TAG],
            tags_match="any",
            budget="mid",
            query_timestamp=INCIDENT_TIME,
            include_source_facts=True,
        )
        notes["observation_sample"] = dump(r.results[:2])
        check(r.results, "no observations recalled")
        check(r.source_facts, "no source facts")
        return f"{len(r.results)} observations, {len(r.source_facts or {})} source facts"

    async def reflect() -> str:
        r = await hs.areflect(
            bank_id=bank,
            query=(
                f"It is {INCIDENT_TIME}. Alert: checkout-api p99 above 2s. Affected service: ledger-svc. "
                "Which root causes are most likely and with what prior, and which fixes should be avoided? "
                "Cite incident IDs."
            ),
            budget="mid",
            response_schema=TRIAGE_SCHEMA,
            tags=[SERVICE_TAG, SYMPTOM_TAG],
            tags_match="any",
            include_facts=True,
        )
        notes["reflect_structured_output"] = r.structured_output
        notes["reflect_structured_output_error"] = r.structured_output_error
        notes["reflect_based_on"] = dump(r.based_on)
        notes["reflect_usage"] = dump(r.usage)
        check(r.structured_output, f"no structured output: {r.structured_output_error}")
        check(r.based_on and r.based_on.memories, "no based_on memories")
        return f"structured output ok; based_on {len(r.based_on.memories)} memories"

    async def mental_model() -> str:
        created = await hs.acreate_mental_model(
            bank_id=bank,
            id=MM_ID,
            name="ledger-svc: failure modes and what works now",
            source_query=(
                "What are the known failure modes of ledger-svc, which signals distinguish them, which "
                "fixes work today, and which fixes failed or made things worse? Cite incident IDs and dates."
            ),
            tags=[SERVICE_TAG],
            trigger={
                "refresh_after_consolidation": True,
                "mode": "delta",
                "min_refresh_interval_seconds": 60,
                "tags_match": "any",
            },
        )
        notes["mental_model_create"] = dump(created)
        await spike.wait_op(created.operation_id)
        model = dump(await hs.aget_mental_model(bank, MM_ID, detail="full"))
        notes["mental_model"] = {k: model.get(k) for k in ("content", "trigger", "last_refreshed_at")}
        check(model.get("content"), "mental model has no content")
        return f"content {len(model['content'])} chars"

    async def mental_model_refresh() -> str:
        resp = dump(await hs.arefresh_mental_model(bank, MM_ID))
        await spike.wait_op(resp["operation_id"])
        history = dump(await hs.aget_mental_model_history(bank, MM_ID))
        notes["mental_model_history"] = history
        check(history, "empty history")
        return f"refreshed; history has {len(history) if isinstance(history, list) else '?'} entries"

    async def knowledge_page() -> str:
        folder = dump(await hs.acreate_knowledge_folder(bank, "Runbooks"))
        page = dump(
            await hs.acreate_knowledge_page(
                bank,
                name="Living runbook: ledger-svc",
                source_query=(
                    "Write the current runbook for ledger-svc incidents: symptoms, first checks, fixes that "
                    "work now, fixes to avoid, with incident citations and dates."
                ),
                parent_id=folder["id"],
                tags=[SERVICE_TAG],
            )
        )
        notes["knowledge_page_create"] = page
        if page.get("operation_id"):
            await spike.wait_op(page["operation_id"])
        got = dump(await hs.aget_knowledge_page(bank, page["page_id"]))
        notes["knowledge_page"] = got
        notes["knowledge_tree"] = dump(await hs.aget_knowledge_base_tree(bank))
        check(got.get("markdown"), "page has no markdown")
        return f"page markdown {len(got['markdown'])} chars"

    async def curation() -> str:
        mems = await spike.doc_memories("pm-hist-3902", type="world")
        check(mems, "no world facts to curate")
        target = mems[0]
        await rest.set_memory_state(bank, target["id"], "invalidated", reason="spike: wrong root cause")
        invalid = await rest.get_memory(bank, target["id"])
        r = await hs.arecall(bank_id=bank, query=target["text"], types=["world"], budget="low")
        excluded = all(x.id != target["id"] for x in r.results)
        await rest.set_memory_state(bank, target["id"], "valid")
        restored = await rest.get_memory(bank, target["id"])
        notes["curation"] = {"invalidated": invalid.get("state"), "restored": restored.get("state")}
        check(invalid.get("state") == "invalidated", f"state after invalidate: {invalid.get('state')}")
        check(excluded, "invalidated fact still recalled")
        check(restored.get("state") == "valid", f"state after restore: {restored.get('state')}")
        return "invalidated (excluded from recall), then restored"

    async def graph() -> str:
        g = await rest.graph(bank, limit=200)
        ents = await rest.entities(bank)
        names = [e["canonical_name"] for e in ents["items"]]
        notes["graph_counts"] = {"nodes": len(g["nodes"]), "edges": len(g["edges"])}
        notes["graph_node_sample"] = g["nodes"][:2]
        notes["entity_names"] = names[:40]
        check(g["nodes"], "empty graph")
        check(any("ledger" in n.lower() for n in names), f"ledger-svc not an entity: {names[:10]}")
        return f"{len(g['nodes'])} nodes, {len(g['edges'])} edges, {ents['total']} entities"

    async def stats() -> str:
        s = await rest.stats(bank)
        notes["bank_stats"] = s
        return f"nodes {s['total_nodes']}, docs {s['total_documents']}, obs {s.get('total_observations')}"

    async def clone() -> str:
        op_id = await hs.aclone_bank(bank, clone_bank)
        try:
            await spike.wait_op(op_id)
        except Exception:
            await spike.wait_op(op_id, bank=clone_bank)
        src, dst = await rest.stats(bank), await rest.stats(clone_bank)
        notes["clone_stats"] = {"source_nodes": src["total_nodes"], "clone_nodes": dst["total_nodes"]}
        check(dst["total_nodes"] == src["total_nodes"], f"clone node count differs: {notes['clone_stats']}")
        return f"clone has {dst['total_nodes']} nodes"

    async def export() -> str:
        archive = await hs.aexport_bank(bank)
        notes["export_bytes"] = len(archive)
        check(archive, "empty archive")
        return f"archive {len(archive):,} bytes"

    run = spike.run
    sync_step = "retain (sync, tags/ts/doc/meta/entities/scopes)"
    async_step = "retain_batch async + operation poll"
    await run("create bank", create_bank)
    await run("update config", update_config, needs=("create bank",))
    await run("memory defense: injection rule", injection_rule, needs=("update config",))
    await run("create directives", directives, needs=("create bank",))
    await run(sync_step, retain_sync, needs=("create bank",))
    await run(async_step, retain_async, needs=("create bank",))
    await run("recallable after retain", recallable, needs=(async_step,))
    await run("first-person log lands as experience", experience, needs=(async_step,))
    await run("upsert via same document_id", upsert, needs=("create bank",))
    await run("update_mode append", append, needs=("create bank",))
    await run("memory defense redacts runtime token", redaction, needs=("update config",))
    await run("retain_files (PDF)", retain_pdf, needs=("create bank",))
    await run("recall: types/tags/budget/qts/source facts/trace", recall_full, needs=("create bank",))
    await run("tags_match any keeps untagged visible", untagged_visible, needs=("create bank",))
    await run("consolidation", consolidation, needs=(sync_step,))
    await run("observation scopes per service / symptom", scopes, needs=("consolidation",))
    await run("recall observations + source facts", recall_observations, needs=("consolidation",))
    await run("reflect: response_schema + based_on", reflect, needs=("consolidation",))
    await run("mental model create", mental_model, needs=("consolidation",))
    await run("mental model refresh + history", mental_model_refresh, needs=("mental model create",))
    await run("knowledge page create / get", knowledge_page, needs=("consolidation",))
    await run("invalidate / restore", curation, needs=(sync_step,))
    await run("graph + entities", graph, needs=("create bank",))
    await run("bank stats", stats, needs=("create bank",))
    await run("clone bank", clone, needs=("create bank",))
    await run("export bank", export, needs=("create bank",))


def print_table(results: list[StepResult]) -> None:
    table = Table(title="Hindsight spike")
    for col in ("#", "check", "status", "s", "detail"):
        table.add_column(col, overflow="fold")
    colors = {"PASS": "green", "FAIL": "red", "SKIP": "yellow"}
    for i, r in enumerate(results, 1):
        table.add_row(str(i), r.name, f"[{colors[r.status]}]{r.status}[/]", f"{r.seconds:.1f}", r.detail)
    Console().print(table)


async def main(keep: bool) -> int:
    settings = get_settings()
    api_key = settings.hindsight_api_key.get_secret_value() if settings.hindsight_api_key else None
    bank = f"spike-{datetime.now():%Y%m%d-%H%M%S}"
    clone_bank = f"{bank}-clone"
    hs = Hindsight(base_url=settings.hindsight_base_url, api_key=api_key, timeout=300)
    async with HindsightRest(settings.hindsight_base_url, api_key, timeout=120) as rest:
        spike = Spike(hs=hs, rest=rest, bank=bank)
        try:
            await run_spike(spike, clone_bank)
        finally:
            if not keep:
                for b in (clone_bank, bank):
                    try:
                        await hs.adelete_bank(b)
                    except Exception as exc:
                        spike.notes.setdefault("cleanup_errors", []).append(f"{b}: {exc}"[:200])
            await hs.aclose()

    out_dir = REPO_ROOT / "data" / "spike"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{bank}.json"
    out.write_text(
        json.dumps(
            {
                "bank": bank,
                "base_url": settings.hindsight_base_url,
                "results": [asdict(r) for r in spike.results],
                "notes": spike.notes,
            },
            indent=2,
            default=str,
        )
    )
    print_table(spike.results)
    print(f"observations written to {out.relative_to(REPO_ROOT)}")
    return 0 if all(r.status == "PASS" for r in spike.results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep", action="store_true", help="keep the spike banks for inspection")
    sys.exit(asyncio.run(main(parser.parse_args().keep)))
