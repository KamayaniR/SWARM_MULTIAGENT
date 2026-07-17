import { useEffect, useRef } from "react";
import type { Agent, SwarmEvent } from "../types/events";

const AGENT_COLOR_VAR: Record<Agent, string> = {
  planner: "--agent-planner",
  router: "--agent-router",
  coder: "--agent-coder",
  tester: "--agent-tester",
  critic: "--agent-critic",
};

const DIFFICULTY_COLOR_VAR: Record<string, string> = {
  EASY: "--difficulty-easy",
  MEDIUM: "--difficulty-medium",
  HARD: "--difficulty-hard",
};

function outcomeMark(event: SwarmEvent): string {
  if (event.outcome === "pass") return "✓";
  if (event.outcome === "fail" || event.outcome === "error") return "✗";
  return "";
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString([], { hour12: false });
}

interface DecisionLogProps {
  events: SwarmEvent[];
  onSelectEvent?: (event: SwarmEvent) => void;
}

export function DecisionLog({ events, onSelectEvent }: DecisionLogProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [events.length]);

  return (
    <div className="decision-log" ref={scrollRef}>
      {events.length === 0 && <div className="empty">Waiting for events…</div>}
      {events.map((event, i) => (
        <div
          className="row"
          key={`${event.timestamp}-${i}`}
          onClick={() => onSelectEvent?.(event)}
          role={onSelectEvent ? "button" : undefined}
        >
          <span className="timestamp">{formatTime(event.timestamp)}</span>
          <span
            className="agent-tag"
            style={{ ["--row-color" as string]: `var(${AGENT_COLOR_VAR[event.agent]})` }}
          >
            {event.agent}
          </span>
          <span className="step-id">{event.step_id}</span>
          <span
            className="difficulty"
            style={
              event.difficulty
                ? { ["--diff-color" as string]: `var(${DIFFICULTY_COLOR_VAR[event.difficulty]})` }
                : undefined
            }
          >
            {event.difficulty ?? ""}
          </span>
          <span className="model">{event.model ?? ""}</span>
          <span className={`outcome ${event.outcome ?? ""}`}>{outcomeMark(event)}</span>
          <span className="detail">{event.detail}</span>
          <span className="cost">{event.cost_usd ? `$${event.cost_usd.toFixed(4)}` : ""}</span>
        </div>
      ))}
    </div>
  );
}
