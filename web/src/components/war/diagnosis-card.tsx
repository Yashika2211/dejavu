"use client";

// The agent's diagnosis and plan, then the grade once the run is scored.

import { CheckCircle2, XCircle } from "lucide-react";

import { humanize, inr, minutes, pct } from "@/lib/format";
import type { Diagnosis, Score } from "@/lib/types";
import { Badge, Empty } from "../ui";

export function DiagnosisCard({ diagnosis, score }: { diagnosis: Diagnosis | null; score: Score | null }) {
  if (!diagnosis) return <Empty>No diagnosis yet.</Empty>;
  return (
    <div className="space-y-3">
      <div>
        <p className="text-base leading-snug font-medium">
          {humanize(diagnosis.root_cause_category)} <span className="text-muted">in</span> {diagnosis.culprit_service}
        </p>
        <p className="mt-1 text-sm leading-snug text-muted">{diagnosis.summary}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <Badge>confidence {pct(diagnosis.confidence)}</Badge>
          {diagnosis.trigger_change_id && <Badge>{diagnosis.trigger_change_id}</Badge>}
          {diagnosis.precedent_incident_ids.map((id) => (
            <Badge key={id} tone="memory">
              {id}
            </Badge>
          ))}
        </div>
      </div>
      {diagnosis.remediation_plan.length > 0 && (
        <ol className="list-decimal space-y-0.5 pl-4 text-xs">
          {diagnosis.remediation_plan.map((a, i) => (
            <li key={i}>
              <span className="font-mono">
                {a.action} {a.target}
              </span>{" "}
              <span className="text-muted">{a.rationale}</span>
            </li>
          ))}
        </ol>
      )}
      {score && (
        <div className="rounded-md border border-border p-2.5">
          <p className="flex items-center gap-1.5 text-sm font-medium">
            {score.correct ? (
              <CheckCircle2 aria-hidden className="size-4 text-ok" />
            ) : (
              <XCircle aria-hidden className="size-4 text-critical" />
            )}
            {score.correct ? "Correct" : `Incorrect: it was ${humanize(score.archetype)}`}
          </p>
          <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            <dt className="text-muted">Time to diagnosis</dt>
            <dd className="text-right font-mono tabular-nums">{minutes(score.ttd_min)}</dd>
            <dt className="text-muted">MTTR ({score.resolved_by})</dt>
            <dd className="text-right font-mono tabular-nums">{minutes(score.mttr_min)}</dd>
            <dt className="text-muted">Steps, wasted</dt>
            <dd className="text-right font-mono tabular-nums">
              {score.steps}, {score.wasted_steps}
            </dd>
            <dt className="text-muted">Harmful actions</dt>
            <dd className="text-right font-mono tabular-nums">{score.harmful_actions}</dd>
            <dt className="text-muted">Payments at risk</dt>
            <dd className="text-right font-mono tabular-nums">{inr(score.inr_at_risk)}</dd>
          </dl>
        </div>
      )}
    </div>
  );
}
