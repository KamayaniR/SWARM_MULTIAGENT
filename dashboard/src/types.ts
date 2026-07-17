export interface TraceEvent {
  seq: number;
  ts: number;
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

// step_id -> { file_path: file_content } for the diff that actually passed.
export type CompletedFiles = Record<string, Record<string, string>>;

export type RunStatus =
  | { run_id: string; status: "not_found" }
  | { run_id: string; status: "running" }
  | { run_id: string; status: "waiting_for_input"; interrupt: unknown }
  | { run_id: string; status: "error"; detail: string }
  | { run_id: string; status: "done"; steps: PlanStepInfo[]; completed_files: CompletedFiles };

export type ViewMode = "overview" | "cost_effective" | "accuracy";
