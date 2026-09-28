"use client";

// The Gauntlet's learning curves (spec 7.4), drawn from chart_data.json: one line per strategy,
// dashed markers at the migrations, look-alike incidents shaded.

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { STRATEGY_NAMES, type CurvePoint, type EvalDetail, type Strategy } from "@/lib/types";
import { Panel } from "../ui";

type Data = EvalDetail["chart_data"];
type Field = keyof Pick<CurvePoint, "mttr_min" | "cumulative_accuracy" | "usd_cost">;

function rows(data: Data, field: Field, scale = 1): Record<string, number>[] {
  return data.incidents.map((incident) => {
    const row: Record<string, number> = { n: incident.n };
    for (const s of data.strategies) {
      const point = data.curves[s]?.find((p) => p.n === incident.n);
      if (point) row[s] = Number((point[field] * scale).toFixed(3));
    }
    return row;
  });
}

function Curve({ data, field, title, unit, scale = 1 }: { data: Data; field: Field; title: string; unit: string; scale?: number }) {
  const last = data.incidents.at(-1)?.n ?? 1;
  return (
    <Panel title={title} fill>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows(data, field, scale)} margin={{ top: 12, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="#1d2330" vertical={false} />
          {data.incidents
            .filter((i) => i.kind === "look-alike")
            .map((i) => (
              <ReferenceArea key={i.n} x1={i.n - 0.5} x2={i.n + 0.5} fill="#22d3ee" fillOpacity={0.08} />
            ))}
          {data.migrations.map((m) => (
            <ReferenceLine key={m.id} x={m.x} stroke="#8b93a7" strokeDasharray="4 4" label={{ value: m.id, position: "top", fill: "#8b93a7", fontSize: 11 }} />
          ))}
          <XAxis dataKey="n" type="number" domain={[0.5, last + 0.5]} ticks={data.incidents.map((i) => i.n)} stroke="#8b93a7" fontSize={11} />
          <YAxis stroke="#8b93a7" fontSize={11} unit={unit} width={52} />
          <Tooltip
            contentStyle={{ background: "#10131a", border: "1px solid #1d2330", fontSize: 12 }}
            labelFormatter={(n) => `incident ${n}`}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {data.strategies.map((s) => (
            <Line
              key={s}
              dataKey={s}
              name={STRATEGY_NAMES[s as Strategy] ?? s}
              stroke={data.colors[s]}
              strokeWidth={s === "dejavu" ? 2.5 : 1.5}
              dot={{ r: 2 }}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </Panel>
  );
}

export function LearningCharts({ data }: { data: Data }) {
  return (
    <div className="grid shrink-0 grid-cols-2 gap-3">
      <div className="col-span-2 flex h-[320px] flex-col">
        <Curve data={data} field="mttr_min" title="MTTR per incident (simulated minutes)" unit="" />
      </div>
      <div className="flex h-[280px] flex-col">
        <Curve data={data} field="cumulative_accuracy" title="Cumulative diagnosis accuracy" unit="%" scale={100} />
      </div>
      <div className="flex h-[280px] flex-col">
        <Curve data={data} field="usd_cost" title="LLM cost per incident (USD)" unit="" />
      </div>
    </div>
  );
}
