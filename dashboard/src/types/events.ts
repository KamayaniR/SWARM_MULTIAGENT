export type Agent = "planner" | "coder" | "critic" | "tester" | "router";
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
