import type { TraceEvent } from "./types";

// Matches config.py's CRITIC_PASS_THRESHOLD -- duplicated here only for
// drawing the pass-line on the chart, never used for any actual pass/fail
// decision (that's entirely the server's Critic agent's call).
export const CRITIC_PASS_THRESHOLD = 8.5;

export type StageId = "planner" | "scheduler" | "coder" | "tester" | "critic";
// Real agent names from this backend's orchestrator/loop.py + agent_mode.py
// (verified against actual live trace events, not assumed): "router" is
// Task mode's single/debate routing; "debate" and "evaluator" only appear
// in Agent mode's deliberation/comparison path.
const STAGE_AGENTS: Record<StageId, string[]> = {
  planner: ["planner", "team_planner"],
  scheduler: ["router", "debate", "evaluator"],
  coder: ["coder"],
  tester: ["tester"],
  critic: ["critic"],
};
const STAGE_ORDER: StageId[] = ["planner", "scheduler", "coder", "tester", "critic"];

export interface StageInfo {
  id: StageId;
  label: string;
  status: "pending" | "active" | "idle";
  detail: string;
  model?: string;
}

// This backend's _event() helper always fills in a human-readable `detail`
// string server-side (e.g. "nano classified as EASY", "wrote 1 file(s)",
// "score 9.5 -> PASS") -- using it directly is more robust than
// reconstructing a message from individual fields, and stays correct even
// as they add new action types this dashboard doesn't know about yet.
function describeEvent(event: TraceEvent): string {
  return (event.detail as string) || (event.action as string);
}

export function deriveStages(events: TraceEvent[], isRunning: boolean): StageInfo[] {
  // Object-identity comparison against the last element of the same array
  // (stageEvents is filtered from `events`, so the references are shared)
  // -- works regardless of whether events carry `seq` (ours) or only
  // `timestamp` (this backend's), since it doesn't need either field.
  const lastEvent = events.length > 0 ? events[events.length - 1] : null;

  return STAGE_ORDER.map((id) => {
    const label = id[0].toUpperCase() + id.slice(1);
    const stageEvents = events.filter((e) => STAGE_AGENTS[id].includes(e.agent));
    if (stageEvents.length === 0) {
      return { id, label, status: "pending", detail: "—" };
    }
    const last = stageEvents[stageEvents.length - 1];
    const isActive = isRunning && last === lastEvent;
    const model = [...stageEvents].reverse().find((e) => typeof e.model === "string")?.model as
      | string
      | undefined;
    return {
      id,
      label,
      status: isActive ? "active" : "idle",
      detail: describeEvent(last),
      model,
    };
  });
}

export interface RoutingStep {
  step_id: string;
  step_class: string;
  tiers: string[]; // every tier this step was routed to, in order
  escalated: boolean;
  status: "active" | "passed" | "failed" | "queued";
  cost_usd: number;
}

export function deriveRoutingSteps(events: TraceEvent[], isRunning: boolean): RoutingStep[] {
  const order: string[] = [];
  const byStep = new Map<string, RoutingStep>();

  for (const e of events) {
    const stepId = e.step_id as string | undefined;
    if (!stepId) continue;
    if (!byStep.has(stepId)) {
      byStep.set(stepId, {
        step_id: stepId,
        step_class: (e.step_class as string) ?? "unknown",
        tiers: [],
        escalated: false,
        status: "queued",
        cost_usd: 0,
      });
      order.push(stepId);
    }
    const entry = byStep.get(stepId)!;
    if (e.step_class) entry.step_class = e.step_class as string;
    // "classify" is this backend's routing-decision event (their name for
    // what we'd call "route") -- fired once per attempt, whether the model
    // came from a single nano classification, a converged debate, a
    // similarity-skip, or an agent-mode deliberation.
    if (e.action === "classify" && typeof e.model === "string") {
      if (!entry.tiers.includes(e.model)) entry.tiers.push(e.model);
      entry.escalated = entry.tiers.length > 1;
      entry.status = "active";
    }
    // Real per-call cost/latency live only in the cost tracker DB on this
    // backend -- every trace event's cost_usd is a hardcoded 0.0, so this
    // accumulator is deliberately left as-is rather than pretending
    // otherwise; per-step cost isn't retrievable from the event stream here.
    if (typeof e.cost_usd === "number") entry.cost_usd += e.cost_usd;
    if (e.action === "verdict") {
      entry.status = e.outcome === "pass" ? "passed" : "failed";
    }
  }

  const lastStepId = [...events].reverse().find((e) => e.step_id)?.step_id as string | undefined;
  return order.map((id) => {
    const step = byStep.get(id)!;
    if (isRunning && id === lastStepId && step.status !== "passed" && step.status !== "failed") {
      step.status = "active";
    }
    return step;
  });
}

export interface CriticScorePoint {
  step_id: string;
  score: number;
  passed: boolean;
}

export function deriveCriticScores(events: TraceEvent[]): CriticScorePoint[] {
  return events
    .filter((e) => e.action === "verdict" && typeof e.critic_score === "number")
    .map((e) => ({
      step_id: e.step_id as string,
      score: e.critic_score as number,
      passed: e.outcome === "pass",
    }));
}

export function describeLogLine(event: TraceEvent): string {
  const parts = [event.agent, describeEvent(event)];
  if (typeof event.model === "string") parts.push(event.model);
  return parts.join(" · ");
}
