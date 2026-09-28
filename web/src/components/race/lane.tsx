"use client";

// One side of a race: a big simulated stopwatch, the step count, payments at risk, the steps.

import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useEffect, useRef } from "react";

import { useAnimatedNumber } from "@/components/war/animated";
import { HypothesisBoard } from "@/components/war/hypothesis-board";
import { StepCard } from "@/components/war/step-card";
import { Badge, cx, Empty } from "@/components/ui";
import { humanize, inr, stopwatch } from "@/lib/format";
import { remediationOutcomes, type RunView } from "@/lib/run";

function status(run: RunView | undefined): { label: string; tone: "neutral" | "ok" | "warning" | "critical" } {
  if (!run?.started) return { label: "waiting", tone: "neutral" };
  if (run.errors.length) return { label: "failed", tone: "critical" };
  if (run.resolved) return { label: "recovered", tone: "ok" };
  if (run.diagnosis) return { label: "diagnosed", tone: "ok" };
  return { label: "investigating", tone: "warning" };
}

export function Lane({ title, run, memory }: { title: string; run: RunView | undefined; memory: boolean }) {
  const minutes = useAnimatedNumber(run?.clock.at ?? 0);
  const rupees = useAnimatedNumber(run?.clock.inr ?? 0);
  const state = status(run);
  const end = useRef<HTMLDivElement>(null);
  const count = run?.steps.length ?? 0;
  const outcomes = run ? remediationOutcomes(run) : {};
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [count]);

  return (
    <section
      aria-label={title}
      className={cx(
        "flex min-h-0 flex-col rounded-md border bg-panel",
        memory ? "border-memory/50" : "border-border",
      )}
    >
      <header className="flex items-end justify-between gap-4 border-b border-border px-4 py-3">
        <div>
          <p className={cx("text-sm font-medium", memory && "text-memory")}>{title}</p>
          <div className="mt-1 flex items-center gap-2">
            <Badge tone={state.tone}>
              {state.label === "investigating" && <Loader2 aria-hidden className="size-3 animate-spin" />}
              {state.label}
            </Badge>
            <span className="text-xs text-muted tabular-nums">{count} steps</span>
          </div>
        </div>
        <div className="text-right">
          <p className="font-mono text-4xl leading-none tabular-nums">{stopwatch(minutes)}</p>
          <p className="mt-1 font-mono text-sm text-critical tabular-nums">{inr(rupees)} at risk</p>
        </div>
      </header>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
        {!run?.started && <Empty>Preparing…</Empty>}
        {run?.steps.map((step, i) => (
          <StepCard key={step.seq} step={step} index={i + 1} compact outcome={outcomes[step.seq]} />
        ))}
        {run?.diagnosis && (
          <div className="rounded-md border border-border p-3 text-sm">
            <p className="flex items-center gap-1.5 font-medium">
              {run.score &&
                (run.score.correct ? (
                  <CheckCircle2 aria-hidden className="size-4 text-ok" />
                ) : (
                  <XCircle aria-hidden className="size-4 text-critical" />
                ))}
              {humanize(run.diagnosis.root_cause_category)} in {run.diagnosis.culprit_service}
            </p>
            <p className="mt-1 text-xs text-muted">{run.diagnosis.summary}</p>
          </div>
        )}
        {run?.errors.map((e, i) => (
          <p key={i} className="text-sm text-critical">
            {e}
          </p>
        ))}
        <div ref={end} />
      </div>
      {run && run.hypotheses.length > 0 && (
        <footer className="max-h-40 shrink-0 overflow-y-auto border-t border-border p-3">
          <HypothesisBoard hypotheses={run.hypotheses} briefing={run.briefing} limit={2} />
        </footer>
      )}
    </section>
  );
}
