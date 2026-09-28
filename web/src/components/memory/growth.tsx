"use client";

// Brain growth (spec 6.6): the bank's counts now, and how they grew across the latest Gauntlet run.

import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api, ApiError } from "@/lib/api";
import { Empty, Panel } from "../ui";

type Stats = {
  bank: string;
  stats: Record<string, unknown>;
  growth: { run_id: string | null; points: ({ n: number } & Record<string, number>)[] };
};

const SERIES = [
  { key: "total_nodes", label: "memory units", color: "#8b5cf6" },
  { key: "total_observations", label: "observations", color: "#22d3ee" },
  { key: "total_entities", label: "entities", color: "#8b93a7" },
  { key: "total_documents", label: "documents", color: "#e6e9ef" },
];

export function Growth() {
  const [data, setData] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .get<Stats>("/memory/stats")
      .then(setData)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load bank stats."));
  }, []);
  if (error) return <Empty>{error}</Empty>;
  if (!data) return <Empty>Loading…</Empty>;
  const counts = SERIES.filter((s) => typeof data.stats[s.key] === "number");
  const plotted = SERIES.filter((s) => data.growth.points.some((p) => typeof p[s.key] === "number"));
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="grid grid-cols-4 gap-3">
        {counts.map((s) => (
          <div key={s.key} className="rounded-md border border-border bg-panel p-3">
            <p className="font-mono text-2xl tabular-nums">{Number(data.stats[s.key]).toLocaleString("en-IN")}</p>
            <p className="text-xs text-muted">{s.label} in {data.bank}</p>
          </div>
        ))}
      </div>
      <Panel title={`Growth across Gauntlet run ${data.growth.run_id ?? ""}`} fill>
        {data.growth.points.length === 0 ? (
          <Empty>No Gauntlet run has recorded growth yet. Run `make gauntlet` to see memory grow incident by incident.</Empty>
        ) : (
          <ResponsiveContainer width="100%" height="100%" minHeight={260}>
            <LineChart data={data.growth.points} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="#1d2330" vertical={false} />
              <XAxis dataKey="n" stroke="#8b93a7" fontSize={11} label={{ value: "incident (0 = Day-0 import)", position: "insideBottom", offset: -4, fill: "#8b93a7", fontSize: 11 }} />
              <YAxis stroke="#8b93a7" fontSize={11} />
              <Tooltip contentStyle={{ background: "#10131a", border: "1px solid #1d2330", fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {plotted.map((s) => (
                <Line key={s.key} dataKey={s.key} name={s.label} stroke={s.color} dot={false} strokeWidth={2} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </Panel>
    </div>
  );
}
