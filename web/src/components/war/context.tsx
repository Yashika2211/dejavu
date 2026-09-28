"use client";

// The left column: the alert, what changed before it, and the run's timeline so far.

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { istTime, stopwatch } from "@/lib/format";
import type { RunView } from "@/lib/run";
import type { Change, IncidentSummary } from "@/lib/types";
import { Badge, Empty } from "../ui";

export function AlertCard({ incident }: { incident: IncidentSummary }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Badge tone="critical">{incident.alert.severity.toUpperCase()}</Badge>
        <span className="font-mono text-xs text-muted">{incident.id}</span>
        <span className="ml-auto font-mono text-xs text-muted">{istTime(incident.alert_at)} IST</span>
      </div>
      <p className="font-mono text-sm">{incident.alert.name}</p>
      <p className="text-sm text-muted">{incident.alert.summary}</p>
    </div>
  );
}

export function RecentChanges({ incidentId }: { incidentId: string }) {
  const [changes, setChanges] = useState<Change[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    api
      .get<Change[]>(`/incidents/${incidentId}/changes`)
      .then((c) => !cancelled && setChanges(c))
      .catch(() => !cancelled && setChanges([]));
    return () => {
      cancelled = true;
    };
  }, [incidentId]);
  if (changes === null) return <p className="text-xs text-muted">Loading changes…</p>;
  if (changes.length === 0) return <Empty>No changes in the six hours before the alert.</Empty>;
  return (
    <ul className="space-y-2">
      {changes.slice(0, 6).map((c) => (
        <li key={c.id} className="text-xs leading-snug">
          <div className="flex gap-2 font-mono text-muted">
            <span>{istTime(c.at)}</span>
            <span>{c.type}</span>
            <span className="truncate">{c.service}</span>
          </div>
          <p>{c.summary}</p>
        </li>
      ))}
    </ul>
  );
}

type Entry = { at: number; text: string; memory?: boolean };

export function Timeline({ run }: { run: RunView }) {
  const entries: Entry[] = [];
  if (run.started) entries.push({ at: 0, text: "Paged" });
  if (run.briefing) entries.push({ at: 0, text: "Memory briefing", memory: run.briefing.source === "dejavu" });
  run.steps.forEach((s, i) => {
    if (s.memory) entries.push({ at: s.at, text: `Step ${i + 1}: memory moment`, memory: true });
  });
  run.proposals.forEach((p) => {
    if (p.applied) entries.push({ at: p.applied.at, text: `${p.action} ${p.target}: ${p.applied.outcome.replace("_", " ")}` });
  });
  if (run.diagnosis) entries.push({ at: run.score?.ttd_min ?? run.clock.at, text: "Diagnosis submitted" });
  if (run.resolved) entries.push({ at: run.resolved.at, text: "Recovered" });
  if (entries.length === 0) return <Empty>Nothing yet.</Empty>;
  return (
    <ol className="space-y-1.5">
      {entries
        .sort((a, b) => a.at - b.at)
        .map((e, i) => (
          <li key={i} className="flex gap-2 text-xs">
            <span className="w-11 shrink-0 font-mono text-muted tabular-nums">+{stopwatch(e.at)}</span>
            <span className={e.memory ? "text-memory" : undefined}>{e.text}</span>
          </li>
        ))}
    </ol>
  );
}
