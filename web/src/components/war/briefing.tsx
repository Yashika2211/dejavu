"use client";

// Déjà vu cards: what memory suggested before the first tool call (spec 6.5, 11.2), with provenance.
// A naive-RAG briefing is shown as retrieved passages, not as memory (violet means DejaVu remembered).

import { AlertTriangle, Ban } from "lucide-react";

import { pct } from "@/lib/format";
import type { Briefing } from "@/lib/types";
import { MemoryList, Provenance } from "../provenance";
import { Badge, Empty } from "../ui";

const VALIDITY = {
  yes: { tone: "ok", label: "still valid" },
  no: { tone: "critical", label: "no longer valid" },
  unknown: { tone: "neutral", label: "validity unknown" },
} as const;

export function DejaVuCards({ briefing, hasMemory }: { briefing: Briefing | null; hasMemory: boolean }) {
  if (!hasMemory) return <Empty>This strategy has no memory to brief from.</Empty>;
  if (!briefing) return <Empty>Waiting for the briefing…</Empty>;
  if (briefing.source === "rag") {
    return (
      <div>
        <p className="mb-2 text-xs text-muted">Passages retrieved by similarity to the alert:</p>
        <MemoryList hits={briefing.data.chunks ?? []} limit={4} />
      </div>
    );
  }
  const brief = briefing.data.brief;
  const basedOn = briefing.data.based_on ?? briefing.data.observations ?? [];
  if (!brief) {
    return (
      <div>
        <p className="mb-2 text-xs text-muted">No structured brief; what past incidents suggest:</p>
        <p className="text-xs leading-relaxed whitespace-pre-wrap">{briefing.text}</p>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {brief.likely_causes.length === 0 && <Empty>Memory has nothing specific about this alert.</Empty>}
      {[...brief.likely_causes]
        .sort((a, b) => b.prior - a.prior)
        .slice(0, 3)
        .map((cause, i) => {
          const validity = VALIDITY[cause.still_valid];
          return (
            <article key={i} className="rounded-md border border-memory/40 bg-memory/5 p-2.5">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium leading-snug">
                  {cause.cause} <span className="text-muted">in</span> {cause.service}
                </p>
                <span className="font-mono text-xs text-memory tabular-nums">{pct(cause.prior)}</span>
              </div>
              <p className="mt-1 text-xs leading-snug text-muted">{cause.why}</p>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {cause.precedent_incident_ids.map((id) => (
                  <Badge key={id} tone="memory">
                    {id}
                  </Badge>
                ))}
                {cause.last_seen && <span className="text-[11px] text-muted">last seen {cause.last_seen}</span>}
                <Badge tone={validity.tone}>{validity.label}</Badge>
                <span className="ml-auto">
                  <Provenance hits={basedOn} />
                </span>
              </div>
              {cause.validity_note && <p className="mt-1.5 text-[11px] text-warning">{cause.validity_note}</p>}
            </article>
          );
        })}
      {brief.first_checks.length > 0 && (
        <div>
          <p className="mb-1 text-[11px] tracking-wider text-muted uppercase">Check first</p>
          <ol className="list-decimal space-y-1 pl-4 text-xs">
            {brief.first_checks.slice(0, 3).map((c, i) => (
              <li key={i}>
                <span className="font-mono">{c.check}</span> <span className="text-muted">{c.reason}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
      {brief.avoid.length > 0 && (
        <div>
          <p className="mb-1 text-[11px] tracking-wider text-muted uppercase">Avoid</p>
          <ul className="space-y-1 text-xs">
            {brief.avoid.slice(0, 3).map((a, i) => (
              <li key={i} className="flex gap-1.5">
                <Ban aria-hidden className="mt-0.5 size-3 shrink-0 text-critical" />
                <span>
                  {a.action} <span className="text-muted">{a.reason}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {brief.stale_knowledge_warnings.map((w, i) => (
        <p key={i} className="flex gap-1.5 text-xs text-warning">
          <AlertTriangle aria-hidden className="mt-0.5 size-3 shrink-0" />
          {w}
        </p>
      ))}
    </div>
  );
}
