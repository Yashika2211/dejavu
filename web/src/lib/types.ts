// Shapes of the API's JSON and of the trace events it streams (backend: dejavu/agent/schemas.py,
// dejavu/eval/grading.py, dejavu/foresight/risk_review.py).

export type Strategy = "dejavu" | "amnesiac" | "rag" | "day1";

export const STRATEGY_NAMES: Record<Strategy, string> = {
  dejavu: "DejaVu",
  amnesiac: "No memory",
  rag: "Naive RAG",
  day1: "DejaVu, day 1",
};

export type TraceEvent = {
  run_id: string;
  lane: string | null;
  seq: number;
  type: string;
  at_min: number;
  wall_ms: number;
  data: Record<string, unknown>;
};

export type Hypothesis = {
  id: string;
  statement: string;
  category: string;
  service: string;
  probability: number;
  evidence_for: string[];
  evidence_against: string[];
  origin: "memory" | "evidence" | "both";
};

export type LikelyCause = {
  cause: string;
  service: string;
  prior: number;
  why: string;
  precedent_incident_ids: string[];
  last_seen: string | null;
  still_valid: "yes" | "no" | "unknown";
  validity_note: string;
};

export type TriageBrief = {
  likely_causes: LikelyCause[];
  first_checks: { check: string; reason: string }[];
  avoid: { action: string; reason: string; precedent_incident_ids: string[] }[];
  stale_knowledge_warnings: string[];
  novel_signals: string[];
};

export type MemoryHit = {
  id: string | null;
  text: string;
  type: string | null;
  when: string | null;
  document_id: string | null;
  context: string | null;
  tags: string[];
  state?: string;
  invalidation_reason?: string | null;
};

export type Briefing = {
  source: string;
  text: string;
  data: {
    brief?: TriageBrief | null;
    based_on?: MemoryHit[];
    observations?: MemoryHit[];
    chunks?: MemoryHit[];
    structured_error?: string | null;
  };
};

export type PlannedAction = { action: string; target: string; params: Record<string, string>; rationale: string };

export type Diagnosis = {
  root_cause_category: string;
  culprit_service: string;
  trigger_change_id: string | null;
  summary: string;
  confidence: number;
  remediation_plan: PlannedAction[];
  precedent_incident_ids: string[];
  memory_used: boolean;
};

export type Score = {
  incident_id: string;
  archetype: string;
  strategy: string;
  correct: boolean;
  category_correct: boolean;
  culprit_correct: boolean;
  ended: string;
  ttd_min: number | null;
  mttr_min: number;
  resolved_by: string;
  steps: number;
  wasted_steps: number;
  harmful_actions: number;
  remediations: { action: string; target: string; outcome: string }[];
  tokens_in: number;
  tokens_out: number;
  usd_cost: number;
  wall_clock_s: number;
  llm_calls: number;
  cited: string[];
  precedent_precision: number | null;
  inr_at_risk: number;
  prevented: boolean;
};

export type RunRecord = {
  id: string;
  incident_id: string;
  strategy: Strategy;
  race_id: string | null;
  lane: string | null;
  status: "running" | "done" | "error" | "interrupted";
  started_at: string;
  ended_at: string | null;
  score: Score | null;
};

export type IncidentSummary = {
  id: string;
  source: string;
  demo: string | null;
  alert_at: string;
  created_at: string;
  alert: { name: string; service: string; severity: string; summary: string };
  runs: RunRecord[];
};

export type Change = {
  id: string;
  at: string;
  type: string;
  service: string;
  author: string;
  summary: string;
  details: Record<string, unknown>;
};

export type Health = {
  mode: "live" | "replay";
  checks: { name: string; ok: boolean; detail: string }[];
  degraded: { llm: boolean; memory: boolean };
};

export type MentalModel = {
  id: string;
  name: string;
  tags: string[];
  last_refreshed_at: string | null;
  last_refresh_failed_at: string | null;
  source_query?: string | null;
  content?: string | null;
};

export type BeliefVersion = { content: string; since: string | null; until: string | null };

export type Safeguard =
  | "canary_rollout"
  | "flag_guard"
  | "load_test"
  | "query_plan_review"
  | "pool_config_review"
  | "owner_review"
  | "revert";

export type RiskReview = {
  risk: "low" | "medium" | "high";
  summary: string;
  failure_modes: string[];
  precedents: { incident_id: string; date: string | null; resemblance: string }[];
  recommended_action: "ship" | "ship_with_canary" | "hold" | "block";
  safeguards: Safeguard[];
};

export type PendingChange = {
  id: string;
  type: string;
  service: string;
  author: string;
  planned_at: string;
  summary: string;
  details: Record<string, unknown>;
};

export type ReviewResponse = {
  change: PendingChange;
  result: { source: "dejavu" | "amnesiac"; review: RiskReview | null; based_on: MemoryHit[]; error: string | null };
  prevented: boolean | null;
  inr_avoided: number | null;
  window_min: number;
};

export type StrategySummary = {
  strategy: string;
  incidents: number;
  correct: number;
  accuracy: number;
  mttr_mean: number;
  mttr_median: number;
  ttd_mean: number | null;
  steps_mean: number;
  wasted_steps: number;
  harmful_actions: number;
  inr_at_risk: number;
  tokens: number;
  usd_cost: number;
  precedent_precision: number | null;
  prevented: number;
  by_kind: Record<string, { incidents: number; accuracy: number; mttr_mean: number }>;
};

export type Comparison = {
  strategy: string;
  baseline: string;
  incidents: number;
  mttr_reduction_pct: number | null;
  recurrence_mttr_reduction_pct: number | null;
  accuracy_delta_pp: number;
  wasted_steps_saved: number;
  inr_saved: number;
};

export type CurvePoint = {
  n: number;
  incident_id: string;
  kind: string;
  correct: boolean;
  mttr_min: number;
  cumulative_accuracy: number;
  steps: number;
  wasted_steps: number;
  usd_cost: number;
};

export type EvalRun = {
  run_id: string;
  seed: number;
  n: number;
  strategies: string[];
  models: string[];
  started_at: string;
  complete: boolean;
  incidents_done: Record<string, number>;
};

export type EvalDetail = {
  summary: {
    run: EvalRun & { git_sha?: string | null };
    complete: boolean;
    incidents_planned: number;
    incidents_done: Record<string, number>;
    strategies: Record<string, StrategySummary>;
    comparisons: Record<string, Comparison>;
  };
  chart_data: {
    strategies: string[];
    colors: Record<string, string>;
    incidents: { n: number; incident_id: string; archetype: string; kind: string; after_migration: boolean; alert_at: string }[];
    migrations: { id: string; at: string; x: number; summary: string }[];
    curves: Record<string, CurvePoint[]>;
    growth: Record<string, ({ n: number; strategy: string } & Record<string, number>)[]>;
  };
};
