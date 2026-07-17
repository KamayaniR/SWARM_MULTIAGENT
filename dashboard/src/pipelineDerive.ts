import type { TraceEvent } from "./types";

// Matches config.py's CRITIC_PASS_THRESHOLD -- duplicated here only for
// drawing the pass-line on the chart, never used for any actual pass/fail
// decision (that's entirely the server's Critic agent's call).
export const CRITIC_PASS_THRESHOLD = 8.5;

export type StageId = "planner" | "scheduler" | "coder" | "tester" | "critic";
const STAGE_AGENTS: Record<StageId, string[]> = {
  planner: ["planner"],
  scheduler: ["scheduler", "scheduler_classifier", "scheduler_debate"],
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

function humanizeAction(event: TraceEvent): string {
  switch (event.action) {
    case "llm_call":
      return "calling model...";
    case "plan_created":
      return `planned ${event.step_count} step(s)`;
    case "route":
      return `routed to ${event.model}`;
    case "debate_transcript":
      return "debating tier...";
    case "implement":
      return "wrote files";
    case "run_tests":
      return `${event.tests_passed}/${event.tests_total} tests passed`;
    case "verdict":
      return `scored ${event.score}`;
    case "replan":
      return "flagged for replan";
    case "escalate":
      return "escalated to human";
    case "history_reset":
      return "reset suspicious history";
    default:
      return event.action;
  }
}

export function deriveStages(events: TraceEvent[], isRunning: boolean): StageInfo[] {
  const lastSeq = events.length > 0 ? events[events.length - 1].seq : -1;

  return STAGE_ORDER.map((id) => {
    const label = id[0].toUpperCase() + id.slice(1);
    const stageEvents = events.filter((e) => STAGE_AGENTS[id].includes(e.agent));
    if (stageEvents.length === 0) {
      return { id, label, status: "pending", detail: "—" };
    }
    const last = stageEvents[stageEvents.length - 1];
    const isActive = isRunning && last.seq === lastSeq;
    const model = [...stageEvents].reverse().find((e) => typeof e.model === "string")?.model as
      | string
      | undefined;
    return {
      id,
      label,
      status: isActive ? "active" : "idle",
      detail: humanizeAction(last),
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
    if (e.action === "route" && typeof e.model === "string") {
      if (!entry.tiers.includes(e.model)) entry.tiers.push(e.model);
      entry.escalated = entry.tiers.length > 1;
      entry.status = "active";
    }
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
    .filter((e) => e.action === "verdict" && typeof e.score === "number")
    .map((e) => ({
      step_id: e.step_id as string,
      score: e.score as number,
      passed: e.outcome === "pass",
    }));
}

export function describeLogLine(event: TraceEvent): string {
  const parts = [event.agent, humanizeAction(event)];
  if (typeof event.cost_usd === "number") parts.push(`$${event.cost_usd.toFixed(3)}`);
  return parts.join(" · ");
}
