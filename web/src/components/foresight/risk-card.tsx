"use client";

// A risk review: how risky, what could break, which past incidents it resembles, what to do.

import { humanize } from "@/lib/format";
import type { ReviewResponse } from "@/lib/types";
import { Provenance } from "../provenance";
import { Badge, cx, Empty, type Tone } from "../ui";

const RISK: Record<string, Tone> = { low: "ok", medium: "warning", high: "critical" };
const ACTION: Record<string, string> = {
  ship: "Ship",
  ship_with_canary: "Ship with a canary",
  hold: "Hold",
  block: "Block",
};

export function RiskCard({ response, title, memory }: { response: ReviewResponse; title: string; memory: boolean }) {
  const { review, based_on, error } = response.result;
  return (
    <article className={cx("rounded-md border bg-panel p-3", memory ? "border-memory/50" : "border-border")}>
      <p className={cx("mb-2 text-[11px] tracking-wider uppercase", memory ? "text-memory" : "text-muted")}>{title}</p>
      {!review ? (
        <Empty>{error ?? "No review."}</Empty>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={RISK[review.risk]}>{review.risk.toUpperCase()} risk</Badge>
            <Badge tone={review.recommended_action === "ship" ? "neutral" : "warning"}>
              {ACTION[review.recommended_action]}
            </Badge>
            {memory && based_on.length > 0 && (
              <span className="ml-auto">
                <Provenance hits={based_on} />
              </span>
            )}
          </div>
          <p className="text-sm leading-snug">{review.summary}</p>
          {review.failure_modes.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted">
              {review.failure_modes.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          )}
          {review.precedents.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[11px] tracking-wider text-muted uppercase">Precedents</p>
              {review.precedents.map((p) => (
                <p key={p.incident_id} className="flex gap-2 text-xs">
                  <Badge tone="memory">{p.incident_id}</Badge>
                  <span className="text-muted">{p.date}</span>
                  <span>{p.resemblance}</span>
                </p>
              ))}
            </div>
          )}
          {review.safeguards.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {review.safeguards.map((s) => (
                <Badge key={s}>{humanize(s)}</Badge>
              ))}
            </div>
          )}
        </div>
      )}
    </article>
  );
}
