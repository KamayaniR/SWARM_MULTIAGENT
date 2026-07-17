export type Agent =
  | "planner"
  | "coder"
  | "critic"
  | "tester"
  | "router"
  | "team_planner"
  | "evaluator";
export type Difficulty = "EASY" | "MEDIUM" | "HARD";
export type Outcome = "pass" | "fail" | "error";

// Mirrors docs/EVENT_SCHEMA.md exactly — keep both in sync manually.
export interface SwarmEvent {
  timestamp: string;
  run_id: string;
  agent: Agent;
  action: string;
  step_id: string;
  step_class: string;
  model: string | null;
  provider: string | null;
  routing_reason: string;
  difficulty: Difficulty | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number;
  latency_ms: number;
  iteration: number;
  outcome: Outcome | null;
  critic_score: number | null;
  tests_passed: number | null;
  tests_total: number | null;
  detail: string;
}

export const AGENTS: Agent[] = ["planner", "router", "coder", "tester", "critic"];

// --- Agent mode (team composition + per-role model bake-off) ---

export interface AgentRole {
  id: string;
  name: string;
  responsibility: string;
  step_class: string;
  probe_description: string;
  acceptance: string[];
}

export interface CandidateResult {
  model: string;
  provider: string;
  files: Record<string, string>;
  critic_score: number;
  tests_passed: number;
  tests_total: number;
  cost_usd: number;
  latency_ms: number;
  passed: boolean;
  error: string | null;
}

export interface RoleResult {
  role: AgentRole;
  candidates: CandidateResult[];
  recommended_model: string | null;
}

export interface TeamResult {
  run_id: string;
  status: "running" | "done" | "error";
  spec: string;
  roles: RoleResult[];
  total_cost: number;
  detail: string;
}
