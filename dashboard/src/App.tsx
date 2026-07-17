import { useState } from "react";
import { AgentGrid } from "./components/AgentGrid";
import { ComparisonChart } from "./components/ComparisonChart";
import { CostMeter } from "./components/CostMeter";
import { DecisionLog } from "./components/DecisionLog";
import { InterveneModal } from "./components/InterveneModal";
import { RoutingPanel } from "./components/RoutingPanel";
import { RunControls } from "./components/RunControls";
import { ScoreTimeline } from "./components/ScoreTimeline";
import { TraceViewer } from "./components/TraceViewer";
import { useRunState } from "./hooks/useRunState";
import type { SwarmEvent } from "./types/events";

function App() {
  const { events, latestByAgent, activeAgent, agents, usingMock } = useRunState();

  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [baselineRunId, setBaselineRunId] = useState<string | null>(null);
  const [schedulerRunId, setSchedulerRunId] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<SwarmEvent | null>(null);
  const [interveneStepId, setInterveneStepId] = useState<string | null>(null);

  function handleRunStarted(runId: string, baseline: boolean) {
    setCurrentRunId(runId);
    if (baseline) setBaselineRunId(runId);
    else setSchedulerRunId(runId);
  }

  return (
    <>
      <header className="app-header">
        <h1>Swarm Control</h1>
        <div className="header-right">
          <RunControls onRunStarted={handleRunStarted} />
          <span className="mode-badge">{usingMock ? "mock data" : "live"}</span>
        </div>
      </header>

      <CostMeter events={events} />

      <AgentGrid agents={agents} latestByAgent={latestByAgent} activeAgent={activeAgent} />

      <div className="panel-row">
        <RoutingPanel
          events={events}
          onIntervene={currentRunId ? (stepId) => setInterveneStepId(stepId) : undefined}
        />
        <ComparisonChart baselineRunId={baselineRunId} schedulerRunId={schedulerRunId} />
      </div>

      <ScoreTimeline events={events} />

      <DecisionLog events={events} onSelectEvent={(event) => setSelectedEvent(event)} />

      {selectedEvent && (
        <TraceViewer
          runId={selectedEvent.run_id}
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      )}

      {interveneStepId && currentRunId && (
        <InterveneModal
          runId={currentRunId}
          stepId={interveneStepId}
          onClose={() => setInterveneStepId(null)}
        />
      )}
    </>
  );
}

export default App;
