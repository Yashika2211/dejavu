"use client";

// Memory (spec 11.2): living runbooks, belief timelines, the explorer with curation, brain growth.

import * as Tabs from "@radix-ui/react-tabs";

import { BeliefTimeline } from "@/components/memory/timeline";
import { Explorer } from "@/components/memory/explorer";
import { Growth } from "@/components/memory/growth";
import { Runbooks } from "@/components/memory/runbooks";

const TABS = [
  { value: "runbooks", label: "Living runbooks", view: <Runbooks /> },
  { value: "timeline", label: "Belief timeline", view: <BeliefTimeline /> },
  { value: "explorer", label: "Explorer", view: <Explorer /> },
  { value: "growth", label: "Brain growth", view: <Growth /> },
];

export default function Memory() {
  return (
    <Tabs.Root defaultValue="runbooks" className="flex min-h-0 flex-1 flex-col">
      <Tabs.List aria-label="Memory views" className="flex shrink-0 gap-1 border-b border-border px-4 py-2">
        {TABS.map((t) => (
          <Tabs.Trigger
            key={t.value}
            value={t.value}
            className="rounded px-2.5 py-1.5 text-sm text-muted transition-colors hover:text-text data-[state=active]:bg-memory/15 data-[state=active]:text-text"
          >
            {t.label}
          </Tabs.Trigger>
        ))}
      </Tabs.List>
      {TABS.map((t) => (
        <Tabs.Content key={t.value} value={t.value} className="flex min-h-0 flex-1 flex-col p-3 data-[state=inactive]:hidden">
          {t.view}
        </Tabs.Content>
      ))}
    </Tabs.Root>
  );
}
