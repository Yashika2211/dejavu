"use client";

// One tool call: what the agent did, why (its <=25-word rationale), and a compact view of the result.

import {
  Activity,
  Bell,
  BookOpen,
  Flag,
  GitCommitHorizontal,
  History,
  ListChecks,
  Network,
  PhoneCall,
  ScrollText,
  Waypoints,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { motion } from "motion/react";

import { stopwatch } from "@/lib/format";
import type { StepView } from "@/lib/run";
import { Badge, cx } from "../ui";

const ICONS: Record<string, LucideIcon> = {
  get_alert: Bell,
  get_topology: Network,
  list_changes: GitCommitHorizontal,
  query_metrics: Activity,
  search_logs: ScrollText,
  get_traces: Waypoints,
  get_runbook: BookOpen,
  run_remediation: Wrench,
  recall_memory: History,
  update_hypotheses: ListChecks,
  page_human: PhoneCall,
  submit_diagnosis: Flag,
};

function argText(args: Record<string, unknown>): string {
  return Object.entries(args)
    .filter(([, v]) => v !== null && v !== "" && !(typeof v === "object" && v && Object.keys(v).length === 0))
    .map(([k, v]) => (k === "hypotheses" ? `${(v as unknown[]).length} hypotheses` : typeof v === "object" ? `${k}=${JSON.stringify(v)}` : String(v)))
    .join(" · ");
}

const LEVELS = "▁▂▃▄▅▆▇█";

/** The tool's block-character sparkline, drawn as bars (one per 2.5-minute bucket). */
function Bars({ blocks }: { blocks: string }) {
  const heights = [...blocks].map((c) => LEVELS.indexOf(c)).filter((level) => level >= 0);
  const width = 4;
  return (
    <svg
      role="img"
      aria-label="metric over the last hour"
      width={heights.length * (width + 1)}
      height={24}
      className="text-muted"
    >
      {heights.map((level, i) => (
        <rect
          key={i}
          x={i * (width + 1)}
          y={24 - 3 * (level + 1)}
          width={width}
          height={3 * (level + 1)}
          rx={1}
          className={level >= 5 ? "fill-warning" : "fill-current"}
        />
      ))}
    </svg>
  );
}

function Sparkline({ output }: { output: string }) {
  const lines = output.split("\n");
  const spark = lines.find((l) => /[▁▂▃▄▅▆▇█]{4,}/.test(l));
  const now = lines.find((l) => l.startsWith("now "));
  const change = lines.find((l) => l.startsWith("change point"));
  return (
    <div className="space-y-1">
      <p className="font-mono text-[11px] text-muted">{lines[0]}</p>
      {spark && <Bars blocks={spark.split("  ")[0]} />}
      {now && <p className="font-mono text-[11px] text-muted">{now}</p>}
      {change && <p className="font-mono text-[11px] text-warning">{change}</p>}
    </div>
  );
}

function LogTemplates({ output }: { output: string }) {
  const lines = output.split("\n");
  const templates: { count: string; level: string; text: string }[] = [];
  lines.forEach((line, i) => {
    const m = line.match(/^\[\d+\]\s+(\d+)x\s+(\w+)/);
    if (m) templates.push({ count: m[1], level: m[2], text: (lines[i + 1] ?? "").trim() });
  });
  return (
    <div className="space-y-1">
      <p className="font-mono text-[11px] text-muted">{lines[0]}</p>
      {templates.slice(0, 3).map((t, i) => (
        <p key={i} className="font-mono text-[11px] leading-snug">
          <span className={cx("mr-1.5", t.level === "ERROR" || t.level === "FATAL" ? "text-critical" : t.level === "WARN" ? "text-warning" : "text-muted")}>
            {t.count}x {t.level}
          </span>
          {t.text}
        </p>
      ))}
    </div>
  );
}

function CriticalPath({ output }: { output: string }) {
  const shares = [...output.matchAll(/^\s+(\d+)%\s+(\S+)\s{2}(.+?)\s{2}\(avg ([\d,]+) ms\)/gm)]
    .map((m) => ({ pct: Number(m[1]), service: m[2], op: m[3], avg: m[4] }))
    .filter((s) => s.pct > 0);
  const colors = ["bg-warning", "bg-muted/70", "bg-border", "bg-border"];
  return (
    <div className="space-y-1.5">
      <p className="font-mono text-[11px] text-muted">{output.split("\n")[1]}</p>
      <div className="flex h-2 overflow-hidden rounded-sm" aria-hidden>
        {shares.map((s, i) => (
          <div key={i} className={colors[Math.min(i, colors.length - 1)]} style={{ width: `${s.pct}%` }} />
        ))}
      </div>
      {shares.slice(0, 2).map((s, i) => (
        <p key={i} className="font-mono text-[11px]">
          {s.pct}% {s.service} {s.op} <span className="text-muted">(avg {s.avg} ms)</span>
        </p>
      ))}
    </div>
  );
}

function Result({ step }: { step: StepView }) {
  const result = step.result;
  if (!result) return <p className="text-[11px] text-muted">running…</p>;
  if (!result.ok) return <p className="font-mono text-[11px] text-critical">{result.summary}</p>;
  if (step.tool === "query_metrics") return <Sparkline output={result.output} />;
  if (step.tool === "search_logs") return <LogTemplates output={result.output} />;
  if (step.tool === "get_traces") return <CriticalPath output={result.output} />;
  return (
    <p className="font-mono text-[11px] leading-snug whitespace-pre-wrap text-muted">
      {result.output.split("\n").slice(0, 4).join("\n")}
    </p>
  );
}

export function StepCard({ step, index, compact = false }: { step: StepView; index: number; compact?: boolean }) {
  const Icon = ICONS[step.tool] ?? Activity;
  const memory = step.memory;
  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={cx(
        "rounded-md border bg-panel p-3",
        memory ? "border-memory/60 shadow-[0_0_0_1px_rgba(139,92,246,0.25)]" : "border-border",
      )}
    >
      <header className="flex items-start gap-2">
        <Icon aria-hidden className={cx("mt-0.5 size-4 shrink-0", memory ? "text-memory" : "text-muted")} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-xs text-muted tabular-nums">#{index}</span>
            <span className="font-mono text-xs font-medium">{step.tool}</span>
            <span className="truncate font-mono text-xs text-muted">{argText(step.args)}</span>
            <span className="ml-auto font-mono text-[11px] text-muted tabular-nums">+{stopwatch(step.at)}</span>
          </div>
          {step.rationale && <p className="mt-1 text-sm leading-snug">{step.rationale}</p>}
        </div>
      </header>
      {memory && (
        <div className="mt-2 flex flex-wrap gap-1.5 pl-6">
          {memory.cited.length > 0 ? (
            memory.cited.map((id) => (
              <Badge key={id} tone="memory">
                ↺ from {id}
              </Badge>
            ))
          ) : (
            <Badge tone="memory">↺ {step.tool === "recall_memory" ? "memory lookup" : "briefing's first check"}</Badge>
          )}
        </div>
      )}
      {!compact && (
        <div className="mt-2 pl-6">
          <Result step={step} />
        </div>
      )}
    </motion.article>
  );
}
