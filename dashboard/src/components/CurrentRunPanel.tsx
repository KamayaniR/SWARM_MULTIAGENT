import { useMemo } from "react";
import { deriveCriticScores, deriveRoutingSteps, deriveStages } from "../pipelineDerive";
import type { CompletedFiles, RunStatus, TraceEvent } from "../types";
import { AgentPipelineRow } from "./AgentPipelineRow";
import { CriticScoreChart } from "./CriticScoreChart";
import { OutputPanel } from "./OutputPanel";
import { RoutingDecisionsList } from "./RoutingDecisionsList";
import { RunStatusBanner } from "./RunStatusBanner";

interface Props {
  runId: string | null;
  startedAt: number | null;
  status: RunStatus | null;
  events: TraceEvent[];
}

export function CurrentRunPanel({ runId, startedAt, status, events }: Props) {
  const isRunning = status?.status === "running";
  const stages = useMemo(() => deriveStages(events, isRunning), [events, isRunning]);
  const routingSteps = useMemo(() => deriveRoutingSteps(events, isRunning), [events, isRunning]);
  const criticScores = useMemo(() => deriveCriticScores(events), [events]);
  const completedFiles: CompletedFiles =
    status?.status === "done" ? status.completed_files : {};

  if (runId === null) {
    return (
      <div className="panel current-run-panel current-run-panel-empty">
        <span className="empty-note">Submit a prompt to watch its pipeline run live here.</span>
      </div>
    );
  }

  return (
    <div className="panel current-run-panel">
      <h2>Current run</h2>
      <RunStatusBanner status={status} startedAt={startedAt} />
      <AgentPipelineRow stages={stages} />

      <div className="current-run-grid">
        <div>
          <h3 className="section-label">Routing decisions</h3>
          <RoutingDecisionsList steps={routingSteps} completedFiles={completedFiles} />
        </div>
        <div>
          <h3 className="section-label">Critic scores</h3>
          <CriticScoreChart points={criticScores} />
        </div>
      </div>

      {status?.status === "done" && (
        <OutputPanel completedFiles={completedFiles} runId={runId} />
      )}
    </div>
  );
}
