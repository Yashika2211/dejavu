"use client";

// Polls GET /health; the banner says plainly what is degraded (spec 11.1, 13).

import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { Health } from "@/lib/types";

export type HealthState = { health: Health | null; unreachable: boolean };

export function useHealth(intervalMs = 30_000): HealthState {
  const [state, setState] = useState<HealthState>({ health: null, unreachable: false });
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const health = await api.get<Health>("/health");
        if (!cancelled) setState({ health, unreachable: false });
      } catch (error) {
        if (!cancelled) setState({ health: null, unreachable: error instanceof ApiError && error.status === 0 });
      }
    };
    void load();
    const timer = setInterval(load, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [intervalMs]);
  return state;
}

export function HealthBanner({ state }: { state: HealthState }) {
  const messages: string[] = [];
  if (state.unreachable) messages.push("The DejaVu API is not reachable. Start it with `make api`.");
  if (state.health?.degraded.memory) messages.push("Memory offline: running without memory.");
  if (state.health?.degraded.llm) messages.push("The model is unreachable: investigations cannot start.");
  if (messages.length === 0) return null;
  return (
    <div role="status" className="border-b border-warning/40 bg-warning/10 px-4 py-1.5 text-sm text-warning">
      {messages.join(" ")}
    </div>
  );
}
