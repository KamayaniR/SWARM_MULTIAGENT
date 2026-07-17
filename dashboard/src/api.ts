import type {
  CollectiveCosts,
  CompletedFiles,
  RawCosts,
  RawRunStatus,
  RunCosts,
  RunHistoryRecord,
  RunStatus,
  TraceEvent,
} from "./types";

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
    body: JSON.stringify({ spec, mode: "task" }),
  });
}

export function intervene(run_id: string, correction_text: string): Promise<{ status: string }> {
  return json("/intervene", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id, step_id: "", correction_text }),
  });
}

// Models hidden from the dashboard's *display* only -- the real cost/call
// data for these still exists in the backend's DB and still counts toward
// total_usd (a true total), it's just excluded from the per-model
// breakdown/cards/accuracy/latency views shown here. Per explicit request:
// claude-haiku-4-5 was genuinely used (Task mode's MEDIUM-difficulty
// routing) and has real recorded cost, but is deliberately not surfaced in
// this dashboard's per-model views.
const HIDDEN_MODELS = new Set(["claude-haiku-4-5"]);

// This backend's /api/costs* endpoints return a per-model `breakdown` array
// (verified: [{model, provider, calls, cost_usd, input_tokens, output_tokens}])
// rather than the dict-keyed-by-model shape our components expect --
// reshaped here, once, so CostDashboard/ModelCards/BarBreakdown stay
// unchanged.
function reshapeCosts(raw: RawCosts): {
  cost_per_model: Record<string, number>;
  calls_per_model: Record<string, number>;
} {
  const cost_per_model: Record<string, number> = {};
  const calls_per_model: Record<string, number> = {};
  for (const entry of raw.breakdown) {
    if (HIDDEN_MODELS.has(entry.model)) continue;
    cost_per_model[entry.model] = entry.cost_usd;
    calls_per_model[entry.model] = entry.calls;
  }
  return { cost_per_model, calls_per_model };
}

function omitHidden(byModel: Record<string, number>): Record<string, number> {
  return Object.fromEntries(Object.entries(byModel).filter(([model]) => !HIDDEN_MODELS.has(model)));
}

export async function getCollectiveCosts(): Promise<CollectiveCosts> {
  const raw = await json<RawCosts>("/api/costs");
  const { cost_per_model, calls_per_model } = reshapeCosts(raw);
  return {
    total_usd: raw.total_usd,
    cost_per_model,
    calls_per_model,
    cost_per_step_class: raw.cost_per_step_class,
    cost_per_converged_task: raw.cost_per_converged_task,
    accuracy_per_model: omitHidden(raw.accuracy_per_model),
    latency_per_model: omitHidden(raw.latency_per_model),
  };
}

export async function getRunCosts(runId: string): Promise<RunCosts> {
  const raw = await json<RawCosts>(`/api/costs/${runId}`);
  const { cost_per_model, calls_per_model } = reshapeCosts(raw);
  return {
    run_id: runId,
    total_usd: raw.total_usd,
    cost_per_model,
    calls_per_model,
    // This backend doesn't track per-step (only per-model) cost -- no
    // per-step breakdown is retrievable, so this stays empty rather than
    // fabricating one.
    cost_per_step: {},
    cost_per_step_class: raw.cost_per_step_class,
    cost_per_converged_task: raw.cost_per_converged_task,
    latency_per_model: omitHidden(raw.latency_per_model),
  };
}

export async function getRunStatus(runId: string): Promise<RunStatus> {
  const raw = await json<RawRunStatus>(`/api/runs/${runId}`);
  if (raw.status === "not_found") return { run_id: runId, status: "not_found" };
  if (raw.status === "running") return { run_id: runId, status: "running" };
  // "awaiting_preference" is Agent mode's dual-candidate comparison pause
  // (orchestrator/loop.py's comparison_gate) -- the only real pause state
  // this backend has for Task mode is none at all: a step that exhausts
  // max_iterations just terminates with status "escalated" rather than
  // pausing (unlike our own backend's interrupt()-based escalation).
  if (raw.status === "awaiting_preference") {
    return { run_id: runId, status: "waiting_for_input", interrupt: raw.interrupt ?? null };
  }
  if (raw.status === "error") {
    return { run_id: runId, status: "error", detail: raw.detail ?? "unknown error" };
  }
  // "done" or "escalated" (a real terminal status here, not a pause) --
  // this backend tracks one flat workspace_files dict per run rather than
  // splitting generated code per step, so it's wrapped under a single
  // synthetic key; OutputPanel just renders whatever step keys it's given.
  const completed_files: CompletedFiles =
    raw.workspace_files && Object.keys(raw.workspace_files).length > 0
      ? { generated_files: raw.workspace_files }
      : {};
  return {
    run_id: runId,
    status: "done",
    steps: raw.plan ?? [],
    completed_files,
  };
}

export function getTraces(runId: string): Promise<{ run_id: string; entries: TraceEvent[] }> {
  return json(`/api/traces/${runId}`);
}

export function getRunHistory(runId: string): Promise<RunHistoryRecord> {
  return json(`/api/runs/${runId}/history`);
}
