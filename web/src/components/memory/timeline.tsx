"use client";

// Belief timeline (spec 6.6): how a mental model changed, version by version, with the words
// that were added or dropped highlighted.

import { diffWords } from "diff";
import { useState } from "react";

import { istDate } from "@/lib/format";
import type { BeliefVersion } from "@/lib/types";
import { Empty, Panel } from "../ui";
import { ModelList } from "./model-list";
import { useModel, useModels } from "./use-models";

function Diff({ before, after }: { before: string; after: string }) {
  return (
    <p className="text-sm leading-relaxed whitespace-pre-wrap">
      {diffWords(before, after).map((part, i) =>
        part.added ? (
          <ins key={i} className="rounded-sm bg-ok/15 text-ok no-underline">
            {part.value}
          </ins>
        ) : part.removed ? (
          <del key={i} className="text-critical/80">
            {part.value}
          </del>
        ) : (
          <span key={i}>{part.value}</span>
        ),
      )}
    </p>
  );
}

function span(v: BeliefVersion): string {
  const from = v.since ? istDate(v.since) : "the beginning";
  return v.until ? `${from} to ${istDate(v.until)}` : `since ${from} (current)`;
}

export function BeliefTimeline() {
  const models = useModels();
  const [picked, setPicked] = useState<string | null>(null);
  const selected = picked ?? models.data?.find((m) => m.id.startsWith("svc-"))?.id ?? models.data?.[0]?.id ?? null;
  const detail = useModel(selected);

  if (models.error) return <Empty>{models.error}</Empty>;
  if (!models.data) return <Empty>Loading…</Empty>;
  const versions = detail.data?.versions ?? [];
  return (
    <div className="grid min-h-0 flex-1 grid-cols-[260px_minmax(0,1fr)] gap-3">
      <Panel title="Beliefs" fill bodyClassName="overflow-y-auto">
        <ModelList models={models.data} selected={selected} onSelect={setPicked} />
      </Panel>
      <Panel title={detail.data?.model.name ?? "Timeline"} fill bodyClassName="overflow-y-auto">
        {versions.length <= 1 && <Empty>This belief has not changed yet.</Empty>}
        {versions.length > 1 && (
          <ol className="space-y-4">
            {versions.map((v, i) => {
              const older = versions[i + 1];
              return (
                <li key={i} className="rounded-md border border-border p-3">
                  <p className="mb-2 text-[11px] tracking-wider text-muted uppercase">{span(v)}</p>
                  {older ? <Diff before={older.content} after={v.content} /> : <p className="text-sm whitespace-pre-wrap">{v.content}</p>}
                </li>
              );
            })}
          </ol>
        )}
      </Panel>
    </div>
  );
}
