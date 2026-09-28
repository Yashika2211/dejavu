"use client";

// War Room (spec 11.2): one incident, investigated live. Left: the alert, recent changes and the
// timeline. Center: every step with its rationale. Right: hypotheses, what memory suggested,
// remediations awaiting approval, and the diagnosis.

import { Loader2, Play, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";

import { useAnimatedNumber } from "@/components/war/animated";
import { DejaVuCards } from "@/components/war/briefing";
import { AlertCard, RecentChanges, Timeline } from "@/components/war/context";
import { DiagnosisCard } from "@/components/war/diagnosis-card";
import { FeedbackForm } from "@/components/war/feedback-form";
import { HypothesisBoard } from "@/components/war/hypothesis-board";
import { RemediationPanel } from "@/components/war/remediation-panel";
import { StepCard } from "@/components/war/step-card";
import { Badge, Button, Empty, Panel, Select } from "@/components/ui";
import { api, ApiError, streamUrl } from "@/lib/api";
import { humanize, inr, istTime, stopwatch } from "@/lib/format";
import { finished } from "@/lib/run";
import { STRATEGY_NAMES, type IncidentSummary, type Strategy } from "@/lib/types";
import { useRunStream, type StreamStatus } from "@/lib/use-stream";

type Scenarios = { demos: string[]; archetypes: string[] };

const STATUS: Record<StreamStatus, { tone: "neutral" | "ok" | "warning" | "critical"; label: string }> = {
  idle: { tone: "neutral", label: "idle" },
  connecting: { tone: "warning", label: "connecting" },
  open: { tone: "ok", label: "streaming" },
  ended: { tone: "neutral", label: "finished" },
  error: { tone: "critical", label: "disconnected" },
};

function Clock({ alertAt, minutes }: { alertAt: string; minutes: number }) {
  const smooth = useAnimatedNumber(minutes);
  return (
    <div className="flex items-baseline gap-2 font-mono tabular-nums">
      <span className="text-lg">{istTime(alertAt, smooth)}</span>
      <span className="text-xs text-muted">IST · +{stopwatch(smooth)}</span>
    </div>
  );
}

function Rupees({ amount }: { amount: number }) {
  const smooth = useAnimatedNumber(amount);
  return (
    <div className="text-right">
      <p className="font-mono text-lg text-critical tabular-nums">{inr(smooth)}</p>
      <p className="text-[11px] text-muted">payments at risk</p>
    </div>
  );
}

export default function WarRoom() {
  const [scenarios, setScenarios] = useState<Scenarios | null>(null);
  const [choice, setChoice] = useState("race-pool-after-pgbouncer");
  const [strategy, setStrategy] = useState<Strategy>("dejavu");
  const [incident, setIncident] = useState<IncidentSummary | null>(null);
  const [running, setRunning] = useState<Strategy>("dejavu");
  const [path, setPath] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const stream = useRunStream(path ? streamUrl(path) : null);
  const run = stream.lanes.main ?? null;

  useEffect(() => {
    api
      .get<Scenarios>("/scenarios")
      .then(setScenarios)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load scenarios."));
  }, []);

  const start = async (fresh: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const { incident_id } = await api.post<{ incident_id: string }>("/incidents", { scenario: choice });
      setIncident(await api.get<IncidentSummary>(`/incidents/${incident_id}`));
      const again = fresh ? `&fresh=true&t=${Date.now()}` : "";
      setRunning(strategy);
      setPath(`/incidents/${incident_id}/stream?strategy=${strategy}${again}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start the incident.");
    } finally {
      setBusy(false);
    }
  };

  const options = [
    ...(scenarios?.demos ?? []).map((d) => ({ value: d, label: `demo: ${d}` })),
    { value: "surprise", label: "surprise me" },
    ...(scenarios?.archetypes ?? []).map((a) => ({ value: a, label: humanize(a) })),
  ];
  const status = STATUS[stream.status];
  const done = run ? finished(run) : false;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border px-4 py-2">
        <Select label="Incident" value={choice} onChange={setChoice} options={options} />
        <Select
          label="Strategy"
          value={strategy}
          onChange={(v) => setStrategy(v as Strategy)}
          options={(Object.keys(STRATEGY_NAMES) as Strategy[]).map((s) => ({ value: s, label: STRATEGY_NAMES[s] }))}
        />
        <Button variant="primary" onClick={() => start(false)} disabled={busy || !scenarios}>
          {busy ? <Loader2 aria-hidden className="size-4 animate-spin" /> : <Play aria-hidden className="size-4" />}
          Page DejaVu
        </Button>
        {incident && (
          <Button onClick={() => start(true)} disabled={busy} title="Investigate the same incident again from scratch">
            <RotateCcw aria-hidden className="size-4" />
            Run again
          </Button>
        )}
        {incident && (
          <div className="ml-auto flex items-center gap-6">
            <Badge tone={status.tone}>{status.label}</Badge>
            <Clock alertAt={incident.alert_at} minutes={run?.clock.at ?? 0} />
            <Rupees amount={run?.resolved?.inr ?? run?.clock.inr ?? 0} />
          </div>
        )}
      </div>
      {error && <p className="border-b border-critical/40 bg-critical/10 px-4 py-1.5 text-sm text-critical">{error}</p>}

      {!incident ? (
        <div className="flex flex-1 items-center justify-center p-8">
          <div className="max-w-md text-center">
            <p className="text-base">No incident yet.</p>
            <p className="mt-2 text-sm text-muted">
              Pick a rehearsed demo or any failure mode, choose who is on call, and page them. Every step, its reason
              and what memory contributed appears here as it happens.
            </p>
          </div>
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-[minmax(260px,300px)_minmax(0,1fr)_minmax(320px,380px)] gap-3 p-3">
          <div className="flex min-h-0 flex-col gap-3 overflow-y-auto">
            <Panel title="Alert">
              <AlertCard incident={incident} />
            </Panel>
            <Panel title="Changes before the alert">
              <RecentChanges incidentId={incident.id} />
            </Panel>
            <Panel title="Timeline">{run ? <Timeline run={run} /> : <Empty>Waiting for the run…</Empty>}</Panel>
          </div>

          <div className="flex min-h-0 flex-col gap-2 overflow-y-auto pr-1" aria-live="polite">
            {!run?.started && stream.status !== "ended" && (
              <Empty>{stream.status === "error" ? "The stream dropped." : "Preparing the incident and the model…"}</Empty>
            )}
            {run?.steps.map((step, i) => <StepCard key={step.seq} step={step} index={i + 1} />)}
            {run?.errors.map((e, i) => (
              <p key={i} className="rounded-md border border-critical/40 bg-critical/10 p-3 text-sm text-critical">
                {e}
              </p>
            ))}
          </div>

          <div className="flex min-h-0 flex-col gap-3 overflow-y-auto">
            <Panel title="Hypotheses">
              <HypothesisBoard hypotheses={run?.hypotheses ?? []} briefing={run?.briefing ?? null} />
            </Panel>
            <Panel title="Déjà vu">
              <DejaVuCards briefing={run?.briefing ?? null} hasMemory={running !== "amnesiac"} />
            </Panel>
            <Panel title="Remediation">
              <RemediationPanel runId={run?.runId ?? null} proposals={run?.proposals ?? []} canApprove={!done} />
            </Panel>
            <Panel title="Diagnosis">
              <DiagnosisCard diagnosis={run?.diagnosis ?? null} score={run?.score ?? null} />
            </Panel>
            {run?.score && (
              <Panel title="Feedback">
                <FeedbackForm incidentId={incident.id} strategy={running} />
              </Panel>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
