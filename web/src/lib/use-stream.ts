"use client";

// Subscribes to a run or race stream and folds its events into one RunView per lane.
// State is keyed by URL and only changes from EventSource callbacks. Reconnects replay the
// backlog, so events are de-duplicated by (run, seq) for as long as the URL stays the same.

import { useEffect, useRef, useState } from "react";

import { apply, emptyRun, EVENT_TYPES, type RunView } from "./run";
import type { TraceEvent } from "./types";

export type StreamStatus = "idle" | "connecting" | "open" | "ended" | "error";

export type StreamState = { lanes: Record<string, RunView>; status: StreamStatus };

type Keyed = StreamState & { url: string | null };

const IDLE: StreamState = { lanes: {}, status: "idle" };
const CONNECTING: StreamState = { lanes: {}, status: "connecting" };

export function useRunStream(url: string | null): StreamState {
  const [state, setState] = useState<Keyed>({ url: null, ...IDLE });
  const seen = useRef<{ url: string; keys: Set<string> } | null>(null);

  useEffect(() => {
    if (!url) return;
    if (seen.current?.url !== url) seen.current = { url, keys: new Set() };
    const keys = seen.current.keys;
    const source = new EventSource(url);
    const current = (prev: Keyed): Keyed => (prev.url === url ? prev : { url, lanes: {}, status: "connecting" });

    const onEvent = (message: MessageEvent<string>) => {
      // The browser fires its own data-less `error` event on connection drops; only parse ours.
      if (typeof message.data !== "string") return;
      let event: TraceEvent;
      try {
        event = JSON.parse(message.data) as TraceEvent;
      } catch {
        return;
      }
      const key = `${event.run_id}:${event.seq}`;
      if (keys.has(key)) return;
      keys.add(key);
      const lane = event.lane ?? "main";
      setState((prev) => {
        const base = current(prev);
        return { url, status: "open", lanes: { ...base.lanes, [lane]: apply(base.lanes[lane] ?? emptyRun(), event) } };
      });
    };
    for (const type of EVENT_TYPES) source.addEventListener(type, onEvent);
    source.addEventListener("end", () => {
      source.close();
      setState((prev) => ({ ...current(prev), status: "ended" }));
    });
    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) {
        setState((prev) => {
          const base = current(prev);
          return { ...base, status: base.status === "ended" ? "ended" : "error" };
        });
      }
    };
    return () => source.close();
  }, [url]);

  if (!url) return IDLE;
  if (state.url !== url) return CONNECTING;
  return { lanes: state.lanes, status: state.status };
}
