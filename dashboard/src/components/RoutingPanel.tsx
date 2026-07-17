import { useMemo } from "react";
import type { SwarmEvent } from "../types/events";

const DIFFICULTY_COLOR_VAR: Record<string, string> = {
  EASY: "--difficulty-easy",
  MEDIUM: "--difficulty-medium",
  HARD: "--difficulty-hard",
};

interface Attempt {
  router: SwarmEvent;
  critic?: SwarmEvent;
}

interface StepGroup {
  stepId: string;
  stepClass: string;
  attempts: Attempt[];
}

function groupByStep(events: SwarmEvent[]): StepGroup[] {
  const order: string[] = [];
  const groups: Record<string, StepGroup> = {};

  for (const e of events) {
    if (!e.step_id) continue;

    if (e.agent === "router") {
      if (!groups[e.step_id]) {
        groups[e.step_id] = { stepId: e.step_id, stepClass: e.step_class, attempts: [] };
        order.push(e.step_id);
      }
      groups[e.step_id].attempts.push({ router: e });
    }

    if (e.agent === "critic" && groups[e.step_id]) {
      const attempts = groups[e.step_id].attempts;
      if (attempts.length > 0) attempts[attempts.length - 1].critic = e;
    }
  }

  return order.map((id) => groups[id]);
}

interface RoutingPanelProps {
  events: SwarmEvent[];
  onIntervene?: (stepId: string) => void;
}

export function RoutingPanel({ events, onIntervene }: RoutingPanelProps) {
  const steps = useMemo(() => groupByStep(events), [events]);

  return (
    <div className="routing-panel">
      {steps.length === 0 && <div className="empty">No routing decisions yet…</div>}
      {steps.map((step) => (
        <div
          key={step.stepId}
          className={`routing-card${onIntervene ? " clickable" : ""}`}
          onClick={() => onIntervene?.(step.stepId)}
          role={onIntervene ? "button" : undefined}
        >
          <div className="routing-card-header">
            <span className="step-id">{step.stepId}</span>
            <span className="step-class">{step.stepClass}</span>
          </div>
          {step.attempts.map((attempt, i) => (
            <div className="routing-attempt" key={i}>
              <span
                className="difficulty"
                style={
                  attempt.router.difficulty
                    ? { ["--diff-color" as string]: `var(${DIFFICULTY_COLOR_VAR[attempt.router.difficulty]})` }
                    : undefined
                }
              >
                {attempt.router.difficulty}
              </span>
              <span className="arrow">→</span>
              <span className="model">{attempt.router.model}</span>
              {attempt.critic && (
                <span className={`outcome ${attempt.critic.outcome ?? ""}`}>
                  {attempt.critic.outcome === "pass" ? "✓" : "✗"}
                </span>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
