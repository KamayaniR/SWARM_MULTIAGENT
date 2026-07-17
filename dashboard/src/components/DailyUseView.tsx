import { useRunState } from "../hooks/useRunState";
import { AgentGrid } from "./AgentGrid";
import { DecisionLog } from "./DecisionLog";
import { DownloadCodeButton } from "./DownloadCodeButton";

export function DailyUseView() {
  const { events, latestByAgent, activeAgent, totalCostUsd, agents } = useRunState();

  // Task runs surface only as websocket events; the latest one carries the
  // active run_id, which the download endpoint keys off.
  const runId = events.length > 0 ? events[events.length - 1].run_id : null;

  return (
    <>
      <div className="cost-area">
        <span className="label">This run</span>
        <span className="value">${totalCostUsd.toFixed(4)}</span>
      </div>

      <AgentGrid agents={agents} latestByAgent={latestByAgent} activeAgent={activeAgent} />

      {runId && <DownloadCodeButton runId={runId} />}

      <DecisionLog events={events} />
    </>
  );
}
