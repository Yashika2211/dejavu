"use client";

// Race (spec 11.2): the same incident, two responders, side by side. Left: no memory, naive RAG
// or DejaVu on day 1. Right: DejaVu with everything the Gauntlet taught it (day 42).

import { Flag, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Lane } from "@/components/race/lane";
import { Scoreboard } from "@/components/race/scoreboard";
import { Button, Panel, Select } from "@/components/ui";
import { api, ApiError, streamUrl, unreachable } from "@/lib/api";
import { STRATEGY_NAMES } from "@/lib/types";
import { useRunStream } from "@/lib/use-stream";

type Left = "amnesiac" | "rag" | "day1";
const RIGHT_NAME = "DejaVu, day 42";

export default function Race() {
  const [demos, setDemos] = useState<string[]>([]);
  const [scenario, setScenario] = useState("race-pool-after-pgbouncer");
  const [left, setLeft] = useState<Left>("amnesiac");
  const [leftName, setLeftName] = useState(STRATEGY_NAMES.amnesiac);
  const [raceId, setRaceId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const stream = useRunStream(raceId ? streamUrl(`/races/${raceId}/stream`) : null);
  const l = stream.lanes.left;
  const r = stream.lanes.right;

  useEffect(() => {
    api
      .get<{ demos: string[] }>("/scenarios")
      .then((s) => setDemos(s.demos))
      .catch((e) => !unreachable(e) && setError(e instanceof ApiError ? e.message : "Could not load scenarios."));
  }, []);

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const race = await api.post<{ race_id: string }>("/race", { scenario, left, right: "dejavu" });
      setLeftName(STRATEGY_NAMES[left]);
      setRaceId(race.race_id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start the race.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border px-4 py-2">
        <Select label="Incident" value={scenario} onChange={setScenario} options={demos.map((d) => ({ value: d, label: d }))} />
        <Select
          label="Left"
          value={left}
          onChange={(v) => setLeft(v as Left)}
          options={(["amnesiac", "rag", "day1"] as Left[]).map((s) => ({ value: s, label: STRATEGY_NAMES[s] }))}
        />
        <span className="text-sm text-muted">
          vs <span className="text-memory">{RIGHT_NAME}</span>
        </span>
        <Button variant="primary" onClick={start} disabled={busy || demos.length === 0}>
          {busy ? <Loader2 aria-hidden className="size-4 animate-spin" /> : <Flag aria-hidden className="size-4" />}
          Start race
        </Button>
      </div>
      {error && <p className="border-b border-critical/40 bg-critical/10 px-4 py-1.5 text-sm text-critical">{error}</p>}
      {!raceId ? (
        <div className="flex flex-1 items-center justify-center p-8">
          <p className="max-w-md text-center text-sm text-muted">
            Two responders get the same page at the same moment. The left one has no memory, or only what Marcus
            left behind; the right one has lived through the whole Gauntlet. Same model, same tools, same budget.
          </p>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
          <div className="grid min-h-0 flex-1 grid-cols-2 gap-3">
            <Lane title={leftName} run={l} memory={false} />
            <Lane title={RIGHT_NAME} run={r} memory />
          </div>
          {l?.score && r?.score && (
            <Panel title="Scoreboard">
              <Scoreboard left={l.score} right={r.score} leftName={leftName} rightName={RIGHT_NAME} />
            </Panel>
          )}
        </div>
      )}
    </div>
  );
}
