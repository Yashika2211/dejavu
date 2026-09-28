"use client";

// Headline tiles, computed by the backend from a real Gauntlet run's results (never typed in).

import { inr, minutes, pct } from "@/lib/format";
import { STRATEGY_NAMES, type EvalDetail, type Strategy } from "@/lib/types";
import { cx } from "../ui";

const name = (s: string) => STRATEGY_NAMES[s as Strategy] ?? s;

function Tile({ value, label, memory = false }: { value: string; label: string; memory?: boolean }) {
  return (
    <div className={cx("rounded-md border bg-panel p-3", memory ? "border-memory/50" : "border-border")}>
      <p className={cx("font-mono text-2xl tabular-nums", memory && "text-memory")}>{value}</p>
      <p className="mt-1 text-xs leading-snug text-muted">{label}</p>
    </div>
  );
}

const signed = (value: number | null, unit: string) =>
  value === null ? "n/a" : `${value > 0 ? "−" : "+"}${Math.abs(value)}${unit}`;

export function Kpis({ summary }: { summary: EvalDetail["summary"] }) {
  const dejavu = summary.comparisons.dejavu;
  const strategies = Object.values(summary.strategies);
  return (
    <div className="space-y-3">
      {dejavu && (
        <div className="grid grid-cols-4 gap-3">
          <Tile memory value={signed(dejavu.recurrence_mttr_reduction_pct, "%")} label="MTTR on recurrences, DejaVu vs no memory" />
          <Tile memory value={signed(dejavu.mttr_reduction_pct, "%")} label={`MTTR over ${dejavu.incidents} incidents, DejaVu vs no memory`} />
          <Tile memory value={`${dejavu.accuracy_delta_pp >= 0 ? "+" : ""}${dejavu.accuracy_delta_pp} pp`} label="diagnosis accuracy, DejaVu vs no memory" />
          <Tile memory value={inr(dejavu.inr_saved)} label="payments at risk avoided, DejaVu vs no memory" />
        </div>
      )}
      <table className="w-full rounded-md border border-border bg-panel text-sm">
        <thead>
          <tr className="text-left text-[11px] tracking-wider text-muted uppercase">
            {["Strategy", "Correct", "Look-alikes", "Mean MTTR", "Harmful actions", "Payments at risk", "Cost"].map((h) => (
              <th key={h} className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="font-mono tabular-nums">
          {strategies.map((s) => (
            <tr key={s.strategy} className="border-t border-border">
              <th scope="row" className={cx("px-3 py-2 text-left font-sans font-medium", s.strategy === "dejavu" && "text-memory")}>
                {name(s.strategy)}
              </th>
              <td className="px-3 py-2">
                {s.correct}/{s.incidents} ({pct(s.accuracy)})
              </td>
              <td className="px-3 py-2">{s.by_kind["look-alike"] ? pct(s.by_kind["look-alike"].accuracy) : "n/a"}</td>
              <td className="px-3 py-2">{minutes(s.mttr_mean)}</td>
              <td className="px-3 py-2">{s.harmful_actions}</td>
              <td className="px-3 py-2">{inr(s.inr_at_risk)}</td>
              <td className="px-3 py-2">${s.usd_cost.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
