"use client";

// The end of a race: both lanes' grades side by side, with the difference.

import { humanize, inr, minutes } from "@/lib/format";
import type { Score } from "@/lib/types";
import { cx } from "@/components/ui";

type Row = { label: string; value: (s: Score) => number | null; show: (v: number | null) => string; better: "lower" | "higher" };

const ROWS: Row[] = [
  { label: "Time to diagnosis", value: (s) => s.ttd_min, show: minutes, better: "lower" },
  { label: "MTTR", value: (s) => s.mttr_min, show: minutes, better: "lower" },
  { label: "Steps", value: (s) => s.steps, show: (v) => String(v ?? "n/a"), better: "lower" },
  { label: "Wasted steps", value: (s) => s.wasted_steps, show: (v) => String(v ?? "n/a"), better: "lower" },
  { label: "Harmful actions", value: (s) => s.harmful_actions, show: (v) => String(v ?? "n/a"), better: "lower" },
  { label: "Payments at risk", value: (s) => s.inr_at_risk, show: (v) => (v === null ? "n/a" : inr(v)), better: "lower" },
];

function delta(row: Row, left: number | null, right: number | null): { text: string; good: boolean | null } {
  if (left === null || right === null) return { text: "", good: null };
  const diff = right - left;
  if (diff === 0) return { text: "same", good: null };
  const unit = row.show === minutes ? " min" : "";
  const text = row.label === "Payments at risk" ? inr(diff) : `${diff > 0 ? "+" : ""}${Number(diff.toFixed(1))}${unit}`;
  return { text, good: row.better === "lower" ? diff < 0 : diff > 0 };
}

export function Scoreboard({ left, right, leftName, rightName }: { left: Score; right: Score; leftName: string; rightName: string }) {
  const lanes = [
    { name: leftName, score: left, memory: false },
    { name: rightName, score: right, memory: true },
  ];
  return (
    <table className="w-full text-sm">
      <caption className="sr-only">Race scoreboard</caption>
      <thead>
        <tr className="text-left text-[11px] tracking-wider text-muted uppercase">
          <th className="py-1.5 font-medium" />
          <th className="py-1.5 font-medium">Correct</th>
          {ROWS.map((row) => (
            <th key={row.label} className="py-1.5 font-medium">
              {row.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="font-mono tabular-nums">
        {lanes.map(({ name, score, memory }) => (
          <tr key={name} className="border-t border-border">
            <th scope="row" className={cx("py-1.5 pr-3 text-left font-sans font-medium", memory && "text-memory")}>
              {name}
            </th>
            <td>{score.correct ? "yes" : `no (${humanize(score.archetype)})`}</td>
            {ROWS.map((row) => (
              <td key={row.label}>{row.show(row.value(score))}</td>
            ))}
          </tr>
        ))}
        <tr className="border-t border-border">
          <th scope="row" className="py-1.5 pr-3 text-left font-sans font-medium text-muted">
            Difference
          </th>
          <td />
          {ROWS.map((row) => {
            const d = delta(row, row.value(left), row.value(right));
            return (
              <td key={row.label} className={cx(d.good === true && "text-ok", d.good === false && "text-critical")}>
                {d.text}
                {d.good !== null && <span className="sr-only">{d.good ? " (better)" : " (worse)"}</span>}
              </td>
            );
          })}
        </tr>
      </tbody>
    </table>
  );
}
