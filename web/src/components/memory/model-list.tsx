"use client";

import type { MentalModel } from "@/lib/types";
import { cx } from "../ui";

export function ModelList({ models, selected, onSelect }: { models: MentalModel[]; selected: string | null; onSelect: (id: string) => void }) {
  return (
    <ul className="space-y-0.5">
      {models.map((m) => (
        <li key={m.id}>
          <button
            type="button"
            onClick={() => onSelect(m.id)}
            aria-current={m.id === selected ? "true" : undefined}
            className={cx(
              "w-full rounded px-2 py-1.5 text-left text-sm transition-colors",
              m.id === selected ? "bg-memory/15 text-text" : "text-muted hover:bg-border/60 hover:text-text",
            )}
          >
            {m.name || m.id}
          </button>
        </li>
      ))}
    </ul>
  );
}
