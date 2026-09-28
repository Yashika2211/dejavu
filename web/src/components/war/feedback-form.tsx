"use client";

// The on-call human confirms or corrects the diagnosis; with DejaVu, the live bank learns from it.

import { useState } from "react";

import { api, ApiError } from "@/lib/api";
import { humanize } from "@/lib/format";
import { Button } from "../ui";

const CATEGORIES = [
  "db_pool_exhaustion",
  "psp_rate_limit",
  "cert_expiry",
  "memory_leak_oom",
  "retry_storm",
  "missing_index_slow_query",
  "kafka_rebalance_storm",
  "clock_skew_jwt",
  "cache_stampede",
  "dns_resolution_failure",
  "cpu_throttling",
  "disk_full_wal",
  "novel",
];

export function FeedbackForm({ incidentId, strategy }: { incidentId: string; strategy: string }) {
  const [correct, setCorrect] = useState<boolean | null>(null);
  const [category, setCategory] = useState(CATEGORIES[0]);
  const [service, setService] = useState("");
  const [notes, setNotes] = useState("");
  const [result, setResult] = useState<string | null>(null);

  const send = async () => {
    if (correct === null) return;
    try {
      const body = correct
        ? { correct, notes }
        : { correct, actual_category: category, actual_service: service || null, notes };
      const { learning } = await api.post<{ learning: boolean }>(`/incidents/${incidentId}/feedback`, body);
      setResult(learning ? "Saved. DejaVu is learning from this incident." : "Saved.");
    } catch (e) {
      setResult(e instanceof ApiError ? e.message : "Could not save the feedback.");
    }
  };

  if (result) return <p className="text-sm text-muted">{result}</p>;
  return (
    <div className="space-y-2 text-sm">
      <div className="flex gap-2">
        <Button variant={correct === true ? "primary" : "ghost"} onClick={() => setCorrect(true)}>
          Diagnosis was right
        </Button>
        <Button variant={correct === false ? "primary" : "ghost"} onClick={() => setCorrect(false)}>
          Correct it
        </Button>
      </div>
      {correct === false && (
        <div className="flex flex-wrap gap-2">
          <select
            aria-label="Actual root cause"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="h-8 rounded border border-border bg-bg px-2 text-sm"
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {humanize(c)}
              </option>
            ))}
          </select>
          <input
            aria-label="Actual service"
            placeholder="service"
            value={service}
            onChange={(e) => setService(e.target.value)}
            className="h-8 w-36 rounded border border-border bg-bg px-2 font-mono text-sm"
          />
        </div>
      )}
      {correct !== null && (
        <>
          <textarea
            aria-label="Notes"
            placeholder="What should DejaVu remember?"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="w-full rounded border border-border bg-bg p-2 text-sm"
          />
          <Button variant={strategy === "dejavu" ? "memory" : "primary"} onClick={send}>
            Save feedback
          </Button>
        </>
      )}
    </div>
  );
}
