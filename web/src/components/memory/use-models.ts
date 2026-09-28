"use client";

// Mental models of the live bank, service models first.

import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { BeliefVersion, MentalModel } from "@/lib/types";

export type Loaded<T> = { data: T | null; error: string | null };

const order = (m: MentalModel) => (m.id.startsWith("svc-") ? 0 : 1);

export function useModels(): Loaded<MentalModel[]> {
  const [state, setState] = useState<Loaded<MentalModel[]>>({ data: null, error: null });
  useEffect(() => {
    api
      .get<MentalModel[]>("/memory/models")
      .then((models) => setState({ data: [...models].sort((a, b) => order(a) - order(b) || a.name.localeCompare(b.name)), error: null }))
      .catch((e) => setState({ data: null, error: e instanceof ApiError ? e.message : "Could not load memory." }));
  }, []);
  return state;
}

export type ModelDetail = { model: MentalModel; versions: BeliefVersion[] };

export function useModel(id: string | null): Loaded<ModelDetail> {
  const [state, setState] = useState<Loaded<ModelDetail> & { id: string | null }>({ id: null, data: null, error: null });
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    api
      .get<ModelDetail>(`/memory/models/${encodeURIComponent(id)}`)
      .then((data) => !cancelled && setState({ id, data, error: null }))
      .catch((e) => !cancelled && setState({ id, data: null, error: e instanceof ApiError ? e.message : "Could not load the model." }));
    return () => {
      cancelled = true;
    };
  }, [id]);
  return state.id === id ? state : { data: null, error: null };
}
