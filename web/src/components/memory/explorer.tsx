"use client";

// Explorer (spec 6.7, 11.2): search what DejaVu remembers, see each memory's kind, date and tags,
// and mark a wrong or outdated one; invalidation is reversible and keeps the audit trail.

import { Search } from "lucide-react";
import { useState } from "react";

import { api, ApiError } from "@/lib/api";
import { istDate } from "@/lib/format";
import type { MemoryHit } from "@/lib/types";
import { Badge, Button, Empty, Panel, Select } from "../ui";

const TYPES = [
  { value: "", label: "all kinds" },
  { value: "world", label: "facts" },
  { value: "experience", label: "experiences" },
  { value: "observation", label: "observations" },
];

export function Explorer() {
  const [query, setQuery] = useState("");
  const [type, setType] = useState("");
  const [retired, setRetired] = useState(false);
  const [rows, setRows] = useState<MemoryHit[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const search = async () => {
    setBusy(true);
    setError(null);
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (type) params.set("type", type);
    if (retired) params.set("state", "invalidated");
    try {
      setRows(await api.get<MemoryHit[]>(`/memory/search?${params}`));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Search failed.");
    } finally {
      setBusy(false);
    }
  };

  const curate = async (row: MemoryHit, action: "invalidate" | "restore") => {
    if (!row.id) return;
    const body = action === "invalidate" ? { reason: "marked wrong or outdated in the war room" } : undefined;
    try {
      await api.post(`/memory/${encodeURIComponent(row.id)}/${action}`, body);
      setRows((current) => (current ?? []).filter((r) => r.id !== row.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not update the memory.");
    }
  };

  return (
    <Panel title="Explorer" fill bodyClassName="flex min-h-0 flex-col gap-3">
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void search();
        }}
      >
        <label className="flex h-8 flex-1 items-center gap-2 rounded border border-border bg-bg px-2">
          <Search aria-hidden className="size-4 text-muted" />
          <span className="sr-only">Search memory</span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="dns checkout latency"
            className="h-full flex-1 bg-transparent text-sm outline-none"
          />
        </label>
        <Select label="Kind" value={type} onChange={setType} options={TYPES} />
        <label className="flex items-center gap-1.5 text-xs text-muted">
          <input type="checkbox" checked={retired} onChange={(e) => setRetired(e.target.checked)} />
          only invalidated
        </label>
        <Button type="submit" variant="primary" disabled={busy}>
          Search
        </Button>
      </form>
      {error && <p className="text-sm text-critical">{error}</p>}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {rows === null && <Empty>Search the live bank, or list what has been invalidated.</Empty>}
        {rows?.length === 0 && <Empty>Nothing found.</Empty>}
        <ul className="divide-y divide-border">
          {rows?.map((row, i) => (
            <li key={row.id ?? i} className="flex gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
                  {row.type && <Badge tone={row.type === "observation" ? "memory" : "neutral"}>{row.type}</Badge>}
                  {row.state === "invalidated" && <Badge tone="critical">invalidated</Badge>}
                  {row.when && <span>{istDate(row.when)}</span>}
                  {row.document_id && <span className="font-mono">{row.document_id}</span>}
                  {row.tags.slice(0, 4).map((t) => (
                    <span key={t} className="font-mono">
                      {t}
                    </span>
                  ))}
                </div>
                <p className="text-sm leading-snug">{row.text}</p>
                {row.invalidation_reason && <p className="mt-1 text-xs text-muted">Reason: {row.invalidation_reason}</p>}
              </div>
              {row.id &&
                row.type !== "observation" &&
                (row.state === "invalidated" ? (
                  <Button onClick={() => curate(row, "restore")}>Restore</Button>
                ) : (
                  <Button variant="danger" onClick={() => curate(row, "invalidate")}>
                    Wrong / outdated
                  </Button>
                ))}
            </li>
          ))}
        </ul>
      </div>
    </Panel>
  );
}
