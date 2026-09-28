"use client";

// Where a remembered claim comes from: the memories it rests on, with dates and documents.

import * as Popover from "@radix-ui/react-popover";
import { History } from "lucide-react";

import { istDate } from "@/lib/format";
import type { MemoryHit } from "@/lib/types";
import { Badge } from "./ui";

export function MemoryList({ hits, limit = 8 }: { hits: MemoryHit[]; limit?: number }) {
  if (hits.length === 0) return <p className="text-xs text-muted">No source memories were returned.</p>;
  return (
    <ul className="space-y-2">
      {hits.slice(0, limit).map((hit, i) => (
        <li key={hit.id ?? i} className="text-xs leading-snug">
          <div className="mb-0.5 flex flex-wrap items-center gap-1.5 text-muted">
            {hit.type && <Badge tone={hit.type === "observation" ? "memory" : "neutral"}>{hit.type}</Badge>}
            {hit.when && <span>{istDate(hit.when)}</span>}
            {hit.document_id && <span className="font-mono">{hit.document_id}</span>}
          </div>
          <p className="text-text">{hit.text}</p>
        </li>
      ))}
    </ul>
  );
}

export function Provenance({ hits, label = "Why" }: { hits: MemoryHit[]; label?: string }) {
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded px-1 text-[11px] text-memory-highlight hover:underline"
        >
          <History aria-hidden className="size-3" />
          {label} ({hits.length})
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="left"
          align="start"
          sideOffset={8}
          className="z-50 max-h-96 w-96 overflow-y-auto rounded-md border border-border bg-panel p-3 shadow-xl"
        >
          <p className="mb-2 text-[11px] tracking-wider text-muted uppercase">Based on these memories</p>
          <MemoryList hits={hits} />
          <Popover.Arrow className="fill-border" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
