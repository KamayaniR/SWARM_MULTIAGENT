import { useState } from "react";
import type { CompletedFiles } from "../types";
import type { RoutingStep } from "../pipelineDerive";

interface Props {
  steps: RoutingStep[];
  completedFiles: CompletedFiles;
}

const STATUS_LABEL: Record<RoutingStep["status"], string> = {
  active: "active",
  passed: "✓ done",
  failed: "✕ failed",
  queued: "queued",
};

export function RoutingDecisionsList({ steps, completedFiles }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (steps.length === 0) {
    return <p className="empty-note">No steps yet -- waiting on the Planner.</p>;
  }

  return (
    <div className="routing-list">
      {steps.map((step) => {
        const files = completedFiles[step.step_id];
        const canExpand = !!files;
        const isOpen = expanded === step.step_id;
        return (
          <div key={step.step_id} className={`routing-item routing-item-${step.status}`}>
            <div
              className={`routing-item-row ${canExpand ? "clickable" : ""}`}
              onClick={() => canExpand && setExpanded(isOpen ? null : step.step_id)}
            >
              <div className="routing-item-main">
                <span className="routing-step-id">{step.step_id}</span>
                <span className="routing-step-class">{step.step_class}</span>
                <span className="routing-tiers">
                  {step.tiers.map((t, i) => (
                    <span key={t}>
                      {i > 0 && " → "}
                      {t}
                    </span>
                  ))}
                  {step.escalated && <span className="routing-escalated"> ↑ escalated</span>}
                </span>
              </div>
              <div className="routing-item-side">
                <span className={`routing-status routing-status-${step.status}`}>
                  {STATUS_LABEL[step.status]}
                </span>
                <span className="routing-cost">${step.cost_usd.toFixed(3)}</span>
                {canExpand && <span className="routing-expand-hint">{isOpen ? "▲" : "▼ view code"}</span>}
              </div>
            </div>
            {isOpen && files && (
              <div className="routing-code">
                {Object.entries(files).map(([path, content]) => (
                  <div key={path} className="routing-code-file">
                    <div className="routing-code-path">{path}</div>
                    <pre>{content}</pre>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
