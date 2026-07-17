import { useRunState } from "../hooks/useRunState";
import { AgentGrid } from "./AgentGrid";
import { DecisionLog } from "./DecisionLog";

export function DailyUseView() {
  const { events, latestByAgent, activeAgent, totalCostUsd, agents } = useRunState();

  return (
    <>
      <div className="cost-area">
        <span className="label">This run</span>
        <span className="value">${totalCostUsd.toFixed(4)}</span>
      </div>

      <AgentGrid agents={agents} latestByAgent={latestByAgent} activeAgent={activeAgent} />

      <DecisionLog events={events} />
    </>
  );
}
