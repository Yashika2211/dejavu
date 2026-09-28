"use client";

// Remediations the agent proposed: what they touch, who approved them, and what they did.

import { useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { ProposalView } from "@/lib/run";
import { Badge, Button, Empty, type Tone } from "../ui";

const OUTCOMES: Record<string, { tone: Tone; label: string }> = {
  resolves: { tone: "ok", label: "fixed it" },
  transient: { tone: "warning", label: "brief relief, then relapse" },
  partial: { tone: "warning", label: "partial relief only" },
  no_effect: { tone: "neutral", label: "no effect" },
  harmful: { tone: "critical", label: "made it worse" },
  invalid: { tone: "neutral", label: "target did not exist" },
};

export function RemediationPanel({
  runId,
  proposals,
  canApprove,
}: {
  runId: string | null;
  proposals: ProposalView[];
  canApprove: boolean;
}) {
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<Record<string, boolean>>({});
  if (proposals.length === 0) return <Empty>No remediation proposed yet.</Empty>;

  const decide = async (actionId: string, approved: boolean) => {
    if (!runId) return;
    setSent((s) => ({ ...s, [actionId]: approved }));
    try {
      await api.post(`/runs/${runId}/approve`, { action_id: actionId, approved });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not send the decision.");
    }
  };

  return (
    <ul className="space-y-2">
      {proposals.map((p) => {
        const outcome = p.applied ? OUTCOMES[p.applied.outcome] : null;
        const waiting = p.needs_approval && !p.approval && !p.applied;
        return (
          <li key={p.action_id} className="rounded-md border border-border p-2.5">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-mono text-sm">
                {p.action} {p.target}
              </span>
              <Badge tone={p.needs_approval ? "warning" : "neutral"}>
                {p.needs_approval ? "stateful: needs approval" : "stateless"}
              </Badge>
            </div>
            {Object.keys(p.params).length > 0 && (
              <p className="mt-1 font-mono text-[11px] text-muted">{JSON.stringify(p.params)}</p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {waiting && canApprove && sent[p.action_id] === undefined && (
                <>
                  <Button variant="primary" onClick={() => decide(p.action_id, true)}>
                    Approve
                  </Button>
                  <Button variant="danger" onClick={() => decide(p.action_id, false)}>
                    Deny
                  </Button>
                </>
              )}
              {waiting && sent[p.action_id] !== undefined && <span className="text-xs text-muted">Sending…</span>}
              {p.approval && (
                <Badge tone={p.approval.approved ? "ok" : "critical"}>
                  {p.approval.approved ? "approved" : "declined"} by {p.approval.by}
                </Badge>
              )}
              {outcome && <Badge tone={outcome.tone}>{outcome.label}</Badge>}
            </div>
          </li>
        );
      })}
      {error && <p className="text-xs text-critical">{error}</p>}
    </ul>
  );
}
