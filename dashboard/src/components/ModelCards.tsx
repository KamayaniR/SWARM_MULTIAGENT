import type { CSSProperties } from "react";
import { modelInfo } from "../modelInfo";

type AccentStyle = CSSProperties & { "--accent": string };

interface Props {
  costPerModel: Record<string, number>;
  callsPerModel: Record<string, number>;
  accuracyPerModel: Record<string, number> | null;
}

export function ModelCards({ costPerModel, callsPerModel, accuracyPerModel }: Props) {
  const models = Array.from(
    new Set([
      ...Object.keys(costPerModel),
      ...Object.keys(callsPerModel),
      ...Object.keys(accuracyPerModel ?? {}),
    ]),
  ).sort((a, b) => (costPerModel[b] ?? 0) - (costPerModel[a] ?? 0));

  if (models.length === 0) {
    return <p className="empty-note">No model activity yet -- run a prompt to see it here.</p>;
  }

  return (
    <div className="model-cards">
      {models.map((model) => {
        const info = modelInfo(model);
        const cost = costPerModel[model] ?? 0;
        const calls = callsPerModel[model] ?? 0;
        const accuracy = accuracyPerModel?.[model];
        const avgCost = calls > 0 ? cost / calls : 0;
        return (
          <div key={model} className="model-card" style={{ "--accent": info.color } as AccentStyle}>
            <div className="model-card-top">
              <span className="model-emoji">{info.emoji}</span>
              <span className="model-name">{info.label}</span>
            </div>
            <div className="model-card-stat">
              <span className="model-stat-value">${cost.toFixed(3)}</span>
              <span className="model-stat-label">total cost</span>
            </div>
            <div className="model-card-row">
              <div className="model-card-substat">
                <span className="model-substat-value">{calls}</span>
                <span className="model-substat-label">calls</span>
              </div>
              <div className="model-card-substat">
                <span className="model-substat-value">${avgCost.toFixed(3)}</span>
                <span className="model-substat-label">avg/call</span>
              </div>
              {/* Always render this third column, even when accuracy is
                  missing for this model -- otherwise cards with 2 vs 3
                  columns don't line up with each other across the grid. */}
              <div className="model-card-substat">
                <span className="model-substat-value">
                  {accuracy !== undefined ? `${(accuracy * 100).toFixed(0)}%` : "—"}
                </span>
                <span className="model-substat-label">pass rate</span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
