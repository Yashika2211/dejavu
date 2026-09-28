"use client";

// Living runbooks (spec 6.6): pages nobody wrote. Each is a mental model that rewrites itself
// after consolidation, so it always reflects what DejaVu has learned so far.

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useState } from "react";

import { istDate } from "@/lib/format";
import { Empty, Panel } from "../ui";
import { ModelList } from "./model-list";
import { useModel, useModels } from "./use-models";

export function Runbooks() {
  const models = useModels();
  const [picked, setPicked] = useState<string | null>(null);
  const selected = picked ?? models.data?.[0]?.id ?? null;
  const detail = useModel(selected);

  if (models.error) return <Empty>{models.error}</Empty>;
  if (!models.data) return <Empty>Loading…</Empty>;
  if (models.data.length === 0) return <Empty>This bank has no mental models yet. Set it up with `make bank`.</Empty>;
  const model = detail.data?.model;
  return (
    <div className="grid min-h-0 flex-1 grid-cols-[260px_minmax(0,1fr)] gap-3">
      <Panel title="Runbooks" fill bodyClassName="overflow-y-auto">
        <ModelList models={models.data} selected={selected} onSelect={setPicked} />
      </Panel>
      <Panel
        title={model?.name ?? "Runbook"}
        fill
        bodyClassName="overflow-y-auto"
        actions={
          model?.last_refreshed_at ? (
            <span className="text-[11px] text-muted">refreshed {istDate(model.last_refreshed_at)}</span>
          ) : undefined
        }
      >
        <p className="mb-4 text-xs text-memory">Nobody wrote this page. It rewrites itself as DejaVu learns.</p>
        {detail.error && <Empty>{detail.error}</Empty>}
        {model && (
          <article className="prose-runbook max-w-3xl text-sm leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{model.content || "_Nothing learned yet._"}</ReactMarkdown>
          </article>
        )}
      </Panel>
    </div>
  );
}
