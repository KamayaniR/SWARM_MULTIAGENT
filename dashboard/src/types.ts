export interface TraceEvent {
  // This backend's real events (verified against live output) carry
  // `timestamp` (an ISO string), not `seq`/`ts` -- kept optional so this
  // type still fits both our own backend's events and this one's.
  timestamp: string;
  seq?: number;
  ts?: number;
  run_id: string;
  agent: string;
  action: string;
  model?: string;
  step_id?: string;
  step_class?: string;
  cost_usd?: number;
  latency_ms?: number;
  input_tokens?: number;
  output_tokens?: number;
  critic_score?: number;
  outcome?: string;
  detail?: string;
  [key: string]: unknown;
}

export interface CollectiveCosts {
  total_usd: number;
  cost_per_model: Record<string, number>;
  calls_per_model: Record<string, number>;
  cost_per_step_class: Record<string, number>;
  // null whenever calls have been recorded but nothing has passed yet (e.g.
  // right after a run starts) -- "not yet computable", not zero.
  cost_per_converged_task: number | null;
  accuracy_per_model: Record<string, number>;
  latency_per_model: Record<string, number>;
}

export interface RunCosts {
  run_id: string;
  total_usd: number;
  cost_per_model: Record<string, number>;
  calls_per_model: Record<string, number>;
  cost_per_step: Record<string, number>;
  cost_per_step_class: Record<string, number>;
  // null whenever calls have been recorded but nothing has passed yet (e.g.
  // right after a run starts) -- "not yet computable", not zero.
  cost_per_converged_task: number | null;
  latency_per_model: Record<string, number>;
}

// Raw shapes the backend (KamayaniR/SWARM_MULTIAGENT's orchestrator/server.py)
// actually returns -- reshaped into CollectiveCosts/RunCosts at the api.ts
// boundary so every component downstream stays unchanged.
export interface RawCostBreakdownEntry {
  model: string;
  provider: string;
  calls: number;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
}

export interface RawCosts {
  run_id?: string;
  total_usd: number;
  breakdown: RawCostBreakdownEntry[];
  accuracy_per_model: Record<string, number>;
  latency_per_model: Record<string, number>;
  cost_per_step_class: Record<string, number>;
  cost_per_converged_task: number | null;
}

export interface RecentPrompt {
  run_id: string;
  spec: string;
  submitted_at: number;
}

export interface ModelInfo {
  label: string;
  emoji: string;
  color: string;
}

export interface PlanStepInfo {
  id: string;
  description: string;
  step_class: string;
  est_loc: number;
  deps: string[];
  acceptance: string[];
  status: string;
}

// step_id -> { file_path: file_content }. Their backend tracks one flat
// workspace_files dict per run (not split per-step) -- getRunStatus() in
// api.ts wraps it under a single synthetic "generated_files" key so
// OutputPanel's existing per-step rendering works unchanged.
export type CompletedFiles = Record<string, Record<string, string>>;

export type RunStatus =
  | { run_id: string; status: "not_found" }
  | { run_id: string; status: "running" }
  | { run_id: string; status: "waiting_for_input"; interrupt: unknown }
  | { run_id: string; status: "error"; detail: string }
  | { run_id: string; status: "done"; steps: PlanStepInfo[]; completed_files: CompletedFiles };

export interface RawRunStatus {
  run_id: string;
  status: string;
  events: TraceEvent[];
  plan?: PlanStepInfo[];
  workspace_files?: Record<string, string>;
  detail?: string | null;
  interrupt?: unknown;
}

export type ViewMode = "overview" | "cost_effective" | "accuracy";

// GET /api/runs/{id}/history -- one persisted row per run (orchestrator/
// artifacts.py's run_history table). `accuracy` here is a genuinely
// different metric from CollectiveCosts.accuracy_per_model (which is a
// pass-RATE across many calls per model): this is the real Critic score
// (0-10) of the one winning solution this specific run produced.
export interface RunHistoryRecord {
  run_id: string;
  status: "not_found" | string;
  prompt?: string;
  plan?: PlanStepInfo[];
  files?: Record<string, string>;
  selected?: string;
  total_cost?: number;
  latency_ms?: number;
  accuracy?: number;
  created_at?: string;
}
