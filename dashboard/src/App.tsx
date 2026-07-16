import { AgentGrid } from "./components/AgentGrid";
import { DecisionLog } from "./components/DecisionLog";
import { useRunState } from "./hooks/useRunState";

function App() {
  const { events, latestByAgent, activeAgent, totalCostUsd, agents, usingMock } = useRunState();

  return (
    <>
      <header className="app-header">
        <h1>Swarm Control</h1>
        <span className="mode-badge">{usingMock ? "mock data" : "live"}</span>
      </header>

      <div className="cost-area">
        <span className="label">This run</span>
        <span className="value">${totalCostUsd.toFixed(4)}</span>
      </div>

      <AgentGrid agents={agents} latestByAgent={latestByAgent} activeAgent={activeAgent} />

      <DecisionLog events={events} />
    </>
  );
}

export default App;
