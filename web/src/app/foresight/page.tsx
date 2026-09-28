"use client";

// Foresight (spec 8, 11.2): review a change before it ships. DejaVu cites the incidents it
// resembles; the baseline judges it from the description alone. Deciding shows what would happen.

import { History, Loader2, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ChangeList } from "@/components/foresight/change-list";
import { RiskCard } from "@/components/foresight/risk-card";
import { Button, Empty, Panel } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { inr } from "@/lib/format";
import type { PendingChange, ReviewResponse } from "@/lib/types";

type Choice = "ship" | "ship_with_canary" | "hold";
const CHOICES: { value: Choice; label: string }[] = [
  { value: "hold", label: "Hold" },
  { value: "ship_with_canary", label: "Ship with a canary" },
  { value: "ship", label: "Ship" },
];

function outcome(choice: Choice, review: ReviewResponse): { text: string; good: boolean } {
  const recommended = review.result.review?.recommended_action;
  if (choice === "ship") {
    return review.prevented === null
      ? { text: "Shipped. It was harmless.", good: true }
      : { text: "Shipped. This change causes an incident.", good: false };
  }
  if (review.prevented === null) return { text: "Held a change that would have been harmless.", good: true };
  if (review.prevented) {
    const avoided = review.inr_avoided === null ? "" : ` Estimated ${inr(review.inr_avoided)} at risk avoided (first ${review.window_min} simulated minutes).`;
    return { text: `Incident prevented.${avoided}`, good: true };
  }
  return recommended === "ship"
    ? { text: "Held on your own call; the review saw no risk, so there is no safeguard plan to judge.", good: true }
    : { text: "Held, but none of the recommended safeguards would have caught this failure.", good: false };
}

export default function Foresight() {
  const [changes, setChanges] = useState<PendingChange[] | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [reviews, setReviews] = useState<Record<string, ReviewResponse>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [choice, setChoice] = useState<Record<string, Choice>>({});
  const [error, setError] = useState<string | null>(null);
  const resultRef = useRef<HTMLParagraphElement>(null);
  const selected = picked ?? changes?.[0]?.id ?? null;
  const change = changes?.find((c) => c.id === selected) ?? null;

  const decidedNow = selected ? choice[selected] : undefined;
  useEffect(() => {
    if (decidedNow) resultRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [decidedNow]);

  useEffect(() => {
    api
      .get<PendingChange[]>("/changes/pending")
      .then(setChanges)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load pending changes."));
  }, []);

  const review = async (strategy: "dejavu" | "amnesiac") => {
    if (!selected) return;
    setBusy(strategy);
    setError(null);
    try {
      const response = await api.post<ReviewResponse>("/foresight/review", { change_id: selected, strategy });
      setReviews((r) => ({ ...r, [`${selected}:${strategy}`]: response }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The review failed.");
    } finally {
      setBusy(null);
    }
  };

  if (!changes) return <Empty>{error ?? "Loading…"}</Empty>;
  const withMemory = selected ? reviews[`${selected}:dejavu`] : undefined;
  const baseline = selected ? reviews[`${selected}:amnesiac`] : undefined;
  const decided = selected ? choice[selected] : undefined;
  const result = decided && withMemory ? outcome(decided, withMemory) : null;

  return (
    <div className="grid min-h-0 flex-1 grid-cols-[minmax(300px,380px)_minmax(0,1fr)] gap-3 p-3">
      <Panel title="Pending changes" fill bodyClassName="overflow-y-auto">
        <ChangeList changes={changes} selected={selected} onSelect={setPicked} />
      </Panel>
      <div className="flex min-h-0 flex-col gap-3 overflow-y-auto">
        {change && (
          <Panel title={`${change.type} · ${change.service}`}>
            <p className="text-base">{change.summary}</p>
            <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
              {Object.entries(change.details).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-muted">{k}</dt>
                  <dd className="font-mono break-words">{Array.isArray(v) ? v.join(", ") : String(v)}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-3 flex gap-2">
              <Button variant="memory" onClick={() => review("dejavu")} disabled={busy !== null}>
                {busy === "dejavu" ? <Loader2 aria-hidden className="size-4 animate-spin" /> : <History aria-hidden className="size-4" />}
                Review with DejaVu
              </Button>
              <Button onClick={() => review("amnesiac")} disabled={busy !== null}>
                {busy === "amnesiac" && <Loader2 aria-hidden className="size-4 animate-spin" />}
                Review without memory
              </Button>
            </div>
            {error && <p className="mt-2 text-sm text-critical">{error}</p>}
          </Panel>
        )}
        {(withMemory || baseline) && (
          <div className="grid grid-cols-2 gap-3">
            {withMemory ? <RiskCard response={withMemory} title="DejaVu" memory /> : <div />}
            {baseline ? <RiskCard response={baseline} title="Without memory" memory={false} /> : <div />}
          </div>
        )}
        {withMemory?.result.review && selected && (
          <Panel title="Decision">
            <div className="flex flex-wrap items-center gap-2">
              {CHOICES.map((c) => (
                <Button
                  key={c.value}
                  variant={withMemory.result.review?.recommended_action === c.value ? "primary" : "ghost"}
                  onClick={() => setChoice((prev) => ({ ...prev, [selected]: c.value }))}
                >
                  {c.label}
                </Button>
              ))}
              <span className="text-xs text-muted">The highlighted action is DejaVu&apos;s recommendation.</span>
            </div>
            {result && (
              <p ref={resultRef} className={`mt-3 flex items-center gap-2 text-sm ${result.good ? "text-ok" : "text-critical"}`}>
                <ShieldCheck aria-hidden className="size-4" />
                {result.text}
              </p>
            )}
          </Panel>
        )}
      </div>
    </div>
  );
}
