"use client";

// Learning (spec 11.2): does memory make the agent better? Everything here comes from a real
// Gauntlet run under data/eval; with no run, the page says so instead of showing numbers.

import { ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";

import { LearningCharts } from "@/components/learning/charts";
import { Kpis } from "@/components/learning/kpis";
import { Empty, Select } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { EvalDetail, EvalRun } from "@/lib/types";

const RESULTS_DOC = "https://github.com/Yashika2211/dejavu/blob/main/docs/EVAL_RESULTS.md";

export default function Learning() {
  const [runs, setRuns] = useState<EvalRun[] | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [detail, setDetail] = useState<{ id: string; data: EvalDetail } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selected = picked ?? runs?.find((r) => r.complete)?.run_id ?? runs?.[0]?.run_id ?? null;

  useEffect(() => {
    api
      .get<EvalRun[]>("/eval/runs")
      .then(setRuns)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load Gauntlet runs."));
  }, []);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    api
      .get<EvalDetail>(`/eval/runs/${selected}`)
      .then((data) => !cancelled && setDetail({ id: selected, data }))
      .catch((e) => !cancelled && setError(e instanceof ApiError ? e.message : "Could not load the run."));
    return () => {
      cancelled = true;
    };
  }, [selected]);

  if (error) return <Empty>{error}</Empty>;
  if (!runs) return <Empty>Loading…</Empty>;
  if (runs.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="max-w-lg text-center">
          <p className="text-base">No Gauntlet results yet.</p>
          <p className="mt-2 text-sm text-muted">
            Numbers appear here only from real runs. Run <code className="font-mono">make gauntlet-quick</code> for six
            incidents, or <code className="font-mono">make gauntlet</code> for all 24 with every strategy.
          </p>
        </div>
      </div>
    );
  }
  const data = detail?.id === selected ? detail.data : null;
  const summary = data?.summary;
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
      <div className="flex flex-wrap items-center gap-3">
        <Select
          label="Run"
          value={selected ?? ""}
          onChange={setPicked}
          options={runs.map((r) => ({
            value: r.run_id,
            label: `${r.run_id} · seed ${r.seed} · ${r.complete ? "complete" : "partial"}`,
          }))}
        />
        {summary && !summary.complete && (
          <span className="text-sm text-warning">
            Partial run:{" "}
            {Object.entries(summary.incidents_done)
              .map(([s, n]) => `${s} ${n} of ${summary.incidents_planned}`)
              .join(", ")}
          </span>
        )}
        <a href={RESULTS_DOC} target="_blank" rel="noreferrer" className="ml-auto flex items-center gap-1 text-sm text-memory-highlight hover:underline">
          EVAL_RESULTS.md <ExternalLink aria-hidden className="size-3.5" />
        </a>
      </div>
      {!data ? (
        <Empty>Loading…</Empty>
      ) : (
        <>
          <Kpis summary={data.summary} />
          <LearningCharts data={data.chart_data} />
          <p className="text-xs text-muted">
            Simulated incidents (SRE-Gym), {data.summary.incidents_planned} per strategy, seed {data.summary.run.seed},{" "}
            {data.summary.run.models.join(", ")}. Small N: a difference of one or two incidents is within noise.
          </p>
        </>
      )}
    </div>
  );
}
