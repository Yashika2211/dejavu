"use client";

// Current hypotheses, most likely first. Each bar splits into what memory suggested (violet, the
// briefing's prior for that service) and what the evidence has added since (neutral).

import { motion } from "motion/react";

import { humanize, pct } from "@/lib/format";
import type { Briefing, Hypothesis } from "@/lib/types";
import { Empty } from "../ui";

function priorFor(hypothesis: Hypothesis, briefing: Briefing | null): number {
  const causes = briefing?.data.brief?.likely_causes ?? [];
  return Math.max(0, ...causes.filter((c) => c.service === hypothesis.service).map((c) => c.prior));
}

export function HypothesisBoard({
  hypotheses,
  briefing,
  limit = 5,
}: {
  hypotheses: Hypothesis[];
  briefing: Briefing | null;
  limit?: number;
}) {
  if (hypotheses.length === 0) return <Empty>No hypotheses yet.</Empty>;
  const sorted = [...hypotheses].sort((a, b) => b.probability - a.probability).slice(0, limit);
  return (
    <ul className="space-y-3">
      {sorted.map((h) => {
        const prior = priorFor(h, briefing);
        const fromMemory = Math.min(prior, h.probability);
        return (
          <li key={h.id}>
            <div className="mb-1 flex items-baseline justify-between gap-2">
              <p className="text-sm leading-snug">{h.statement}</p>
              <span className="font-mono text-xs tabular-nums">{pct(h.probability)}</span>
            </div>
            <div className="relative h-2 overflow-hidden rounded-sm bg-border" aria-hidden>
              <motion.div
                className="absolute inset-y-0 left-0 bg-memory"
                animate={{ width: `${fromMemory * 100}%` }}
                transition={{ type: "spring", stiffness: 120, damping: 20 }}
              />
              <motion.div
                className="absolute inset-y-0 bg-muted"
                animate={{ left: `${fromMemory * 100}%`, width: `${(h.probability - fromMemory) * 100}%` }}
                transition={{ type: "spring", stiffness: 120, damping: 20 }}
              />
              {prior > h.probability && (
                <div className="absolute inset-y-0 w-px bg-memory-highlight" style={{ left: `${prior * 100}%` }} />
              )}
            </div>
            <p className="mt-1 text-[11px] text-muted">
              {humanize(h.category)} · {h.service}
              {prior > 0 && ` · memory prior ${pct(prior)}`}
            </p>
          </li>
        );
      })}
    </ul>
  );
}
