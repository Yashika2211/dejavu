"use client";

// Changes waiting to ship, soonest first.

import { Flag, GitCommitHorizontal, Settings2, Sparkles } from "lucide-react";

import { istDate, istTime } from "@/lib/format";
import type { PendingChange } from "@/lib/types";
import { cx } from "../ui";

const ICONS = { deploy: GitCommitHorizontal, flag: Flag, helm: Settings2, model_release: Sparkles } as const;

export function ChangeList({
  changes,
  selected,
  onSelect,
}: {
  changes: PendingChange[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <ul className="space-y-1.5">
      {changes.map((c) => {
        const Icon = ICONS[c.type as keyof typeof ICONS] ?? GitCommitHorizontal;
        return (
          <li key={c.id}>
            <button
              type="button"
              onClick={() => onSelect(c.id)}
              aria-current={c.id === selected ? "true" : undefined}
              className={cx(
                "w-full rounded-md border p-2.5 text-left transition-colors",
                c.id === selected ? "border-memory/60 bg-memory/5" : "border-border hover:bg-border/40",
              )}
            >
              <div className="flex items-center gap-2 text-xs text-muted">
                <Icon aria-hidden className="size-3.5" />
                <span className="font-mono">{c.type}</span>
                <span className="font-mono">{c.service}</span>
                <span className="ml-auto font-mono">
                  {istDate(c.planned_at)} {istTime(c.planned_at)}
                </span>
              </div>
              <p className="mt-1 text-sm">{c.summary}</p>
              <p className="mt-0.5 text-xs text-muted">by {c.author}</p>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
