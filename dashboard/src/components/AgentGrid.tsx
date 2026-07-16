import type { Agent, SwarmEvent } from "../types/events";

const AGENT_LABELS: Record<Agent, string> = {
  planner: "Planner",
  router: "Router",
  coder: "Coder",
  tester: "Tester",
  critic: "Critic",
};

const AGENT_COLOR_VAR: Record<Agent, string> = {
  planner: "--agent-planner",
  router: "--agent-router",
  coder: "--agent-coder",
  tester: "--agent-tester",
  critic: "--agent-critic",
};

function statusText(event: SwarmEvent | undefined): string {
  if (!event) return "idle";
  if (event.agent === "coder") return event.action === "implement" ? "writing…" : event.detail;
  return event.detail || event.action;
}

interface AgentGridProps {
  agents: Agent[];
  latestByAgent: Partial<Record<Agent, SwarmEvent>>;
  activeAgent: Agent | null;
}

export function AgentGrid({ agents, latestByAgent, activeAgent }: AgentGridProps) {
  return (
    <div className="agent-grid">
      {agents.map((agent) => {
        const event = latestByAgent[agent];
        return (
          <div
            key={agent}
            className={`agent-card${agent === activeAgent ? " active" : ""}`}
            style={{ ["--card-color" as string]: `var(${AGENT_COLOR_VAR[agent]})` }}
          >
            <div className="name">{AGENT_LABELS[agent]}</div>
            <div className="status">{statusText(event)}</div>
            {agent === "coder" && event?.model && (
              <div className="model-badge">{event.model}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}
