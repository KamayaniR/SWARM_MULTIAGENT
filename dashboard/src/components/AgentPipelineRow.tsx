import { Fragment } from "react";
import type { StageInfo } from "../pipelineDerive";

interface Props {
  stages: StageInfo[];
}

function icon(status: StageInfo["status"]): string {
  if (status === "active") return "●";
  if (status === "idle") return "✓";
  return "○";
}

function connectorClass(from: StageInfo, to: StageInfo): string {
  if (from.status === "active") return "flowing";
  if (from.status === "idle" && (to.status === "idle" || to.status === "active")) return "done";
  return "pending";
}

export function AgentPipelineRow({ stages }: Props) {
  return (
    <div className="flow-diagram">
      {stages.map((stage, i) => (
        <Fragment key={stage.id}>
          <div className={`flow-node flow-node-${stage.status}`}>
            <span className="flow-node-icon">{icon(stage.status)}</span>
            <span className="flow-node-label">{stage.label}</span>
            {stage.model && <span className="flow-node-model">{stage.model}</span>}
            <span className="flow-node-detail">{stage.detail}</span>
          </div>
          {i < stages.length - 1 && (
            <div className={`flow-connector flow-connector-${connectorClass(stage, stages[i + 1])}`} />
          )}
        </Fragment>
      ))}
    </div>
  );
}
