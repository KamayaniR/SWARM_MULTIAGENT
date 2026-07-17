import type { CollectiveCosts, RunCosts, RunStatus, TraceEvent } from "./types";

// Overridable via VITE_API_BASE if the server isn't on localhost:8000 (e.g.
// deployed separately from the dashboard's static host).
export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";
export const WS_URL = API_BASE.replace(/^http/, "ws") + "/ws/events";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    throw new Error(`${path} -> ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function startRun(spec: string): Promise<{ run_id: string }> {
  return json("/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ spec }),
  });
}

export function intervene(run_id: string, correction_text: string): Promise<{ status: string }> {
  return json("/intervene", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id, correction_text }),
  });
}

export function getCollectiveCosts(): Promise<CollectiveCosts> {
  return json("/api/costs");
}

export function getRunCosts(runId: string): Promise<RunCosts> {
  return json(`/api/costs/${runId}`);
}

export function getRunStatus(runId: string): Promise<RunStatus> {
  return json(`/api/runs/${runId}`);
}

export function getTraces(runId: string): Promise<{ run_id: string; entries: TraceEvent[] }> {
  return json(`/api/traces/${runId}`);
}
