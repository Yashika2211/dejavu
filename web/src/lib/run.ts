// Folds a run's trace events (spec 10) into what the war room shows.

import type { Briefing, Diagnosis, Hypothesis, Score, TraceEvent } from "./types";

export type StepView = {
  seq: number;
  tool: string;
  args: Record<string, unknown>;
  rationale: string;
  at: number;
  result?: { ok: boolean; summary: string; output: string; sim_minutes: number };
  memory?: { cited: string[] };
};

export type ProposalView = {
  action_id: string;
  action: string;
  target: string;
  params: Record<string, string>;
  needs_approval: boolean;
  at: number;
  approval?: { approved: boolean; by: string };
  applied?: { outcome: string; at: number };
};

export type RunView = {
  runId: string | null;
  started: boolean;
  alert: string | null;
  briefing: Briefing | null;
  steps: StepView[];
  hypotheses: Hypothesis[];
  proposals: ProposalView[];
  diagnosis: Diagnosis | null;
  resolved: { at: number; inr: number } | null;
  score: Score | null;
  clock: { at: number; inr: number };
  degraded: string[];
  errors: string[];
};

export const EVENT_TYPES = [
  "run_started",
  "briefing",
  "tool_call",
  "tool_result",
  "memory_moment",
  "hypotheses",
  "remediation_proposed",
  "approval",
  "remediation_applied",
  "diagnosis",
  "resolved",
  "clock",
  "degraded",
  "error",
  "scored",
] as const;

export const emptyRun = (): RunView => ({
  runId: null,
  started: false,
  alert: null,
  briefing: null,
  steps: [],
  hypotheses: [],
  proposals: [],
  diagnosis: null,
  resolved: null,
  score: null,
  clock: { at: 0, inr: 0 },
  degraded: [],
  errors: [],
});

const str = (value: unknown) => (typeof value === "string" ? value : "");

function updateLastStep(run: RunView, patch: (step: StepView) => StepView): RunView {
  if (run.steps.length === 0) return run;
  const steps = run.steps.slice();
  steps[steps.length - 1] = patch(steps[steps.length - 1]);
  return { ...run, steps };
}

export function apply(run: RunView, event: TraceEvent): RunView {
  const d = event.data;
  switch (event.type) {
    case "run_started":
      return { ...run, runId: event.run_id, started: true, alert: str(d.alert) };
    case "briefing":
      return { ...run, briefing: d as unknown as Briefing };
    case "tool_call":
      return {
        ...run,
        steps: [
          ...run.steps,
          {
            seq: event.seq,
            tool: str(d.tool),
            args: (d.args as Record<string, unknown>) ?? {},
            rationale: str(d.rationale),
            at: event.at_min,
          },
        ],
      };
    case "tool_result":
      return updateLastStep(run, (step) => ({
        ...step,
        result: {
          ok: Boolean(d.ok),
          summary: str(d.summary),
          output: str(d.output),
          sim_minutes: Number(d.sim_minutes ?? 0),
        },
      }));
    case "memory_moment":
      return updateLastStep(run, (step) => ({ ...step, memory: { cited: (d.cited as string[]) ?? [] } }));
    case "hypotheses":
      return { ...run, hypotheses: (d.hypotheses as Hypothesis[]) ?? [] };
    case "remediation_proposed":
      return {
        ...run,
        proposals: [
          ...run.proposals,
          {
            action_id: str(d.action_id),
            action: str(d.action),
            target: str(d.target),
            params: (d.params as Record<string, string>) ?? {},
            needs_approval: Boolean(d.needs_approval),
            at: event.at_min,
          },
        ],
      };
    case "approval":
      return {
        ...run,
        proposals: run.proposals.map((p) =>
          p.action_id === d.action_id ? { ...p, approval: { approved: Boolean(d.approved), by: str(d.by) } } : p,
        ),
      };
    case "remediation_applied": {
      const clock = { ...run.clock, at: Math.max(run.clock.at, event.at_min) };
      const index = run.proposals.findLastIndex((p) => p.action === d.action && p.target === d.target && !p.applied);
      if (index < 0) return { ...run, clock };
      const proposals = run.proposals.slice();
      proposals[index] = { ...proposals[index], applied: { outcome: str(d.outcome), at: event.at_min } };
      return { ...run, proposals, clock };
    }
    case "diagnosis":
      return { ...run, diagnosis: d as unknown as Diagnosis };
    case "resolved": {
      const inr = Number(d.inr_at_risk ?? 0);
      return { ...run, resolved: { at: event.at_min, inr }, clock: { at: Math.max(run.clock.at, event.at_min), inr } };
    }
    case "clock":
      return { ...run, clock: { at: event.at_min, inr: Number(d.inr_at_risk ?? run.clock.inr) } };
    case "scored":
      return { ...run, score: d as unknown as Score };
    case "degraded":
      return { ...run, degraded: [...run.degraded, `${str(d.component)}: ${str(d.error)}`] };
    case "error":
      return { ...run, errors: [...run.errors, str(d.error)] };
    default:
      return run;
  }
}

/** A run is over once it has been scored or has failed. */
export const finished = (run: RunView) => run.score !== null || run.errors.length > 0;

/** What each remediation step did, by step seq: the n-th proposal answers the n-th run_remediation call. */
export function remediationOutcomes(run: RunView): Record<number, string> {
  const steps = run.steps.filter((s) => s.tool === "run_remediation" && s.result?.ok);
  const out: Record<number, string> = {};
  steps.forEach((step, i) => {
    const outcome = run.proposals[i]?.applied?.outcome;
    if (outcome) out[step.seq] = outcome;
  });
  return out;
}
