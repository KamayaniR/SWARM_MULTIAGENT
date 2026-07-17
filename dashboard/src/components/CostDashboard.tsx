import { useRunHistory } from "../hooks/useRunHistory";
import type { CollectiveCosts, RunCosts, ViewMode } from "../types";
import { BarBreakdown } from "./BarBreakdown";
import { ModelCards } from "./ModelCards";

const usd = (v: number | null) => (v === null || v === Infinity ? "—" : `$${v.toFixed(3)}`);
const pct = (v: number) => `${(v * 100).toFixed(0)}%`;

// This backend leaves step_class as "" for calls that aren't tied to any
// specific plan step (e.g. the Planner's own call) -- shown as a blank,
// unlabeled bar otherwise. Relabeled here rather than filtered out, since
// it's real cost and often one of the largest bars.
function labelStepClasses(data: Record<string, number>): Record<string, number> {
  if (!("" in data)) return data;
  const { "": unclassified, ...rest } = data;
  return { "(unclassified)": unclassified, ...rest };
}

interface Props {
  view: ViewMode;
  isCollective: boolean;
  collective: CollectiveCosts | null;
  perRun: RunCosts | null;
  selectedRun: string | null;
}

export function CostDashboard({ view, isCollective, collective, perRun, selectedRun }: Props) {
  const data = isCollective ? collective : perRun;
  // Real Critic score (0-10) of the winning solution for whichever run is
  // selected -- sourced from orchestrator/artifacts.py's run_history table,
  // not tied to a live/active-session run, so it's visible for any
  // historical run the user picks from the Scope selector too.
  const history = useRunHistory(selectedRun, !isCollective);

  if (!data) return <p className="empty-note">Loading...</p>;

  const totalUsd = data.total_usd;
  const perConverged = data.cost_per_converged_task;
  const costPerModel = data.cost_per_model;
  const callsPerModel = data.calls_per_model;
  const costPerStepClass = labelStepClasses(data.cost_per_step_class);
  const accuracyPerModel = isCollective ? (collective as CollectiveCosts).accuracy_per_model : null;

  return (
    <div className="cost-dashboard">
      <div className="headline-row">
        <div className="headline-stat">
          <span className="headline-label">Total spend</span>
          <span className="headline-value">{usd(totalUsd)}</span>
        </div>
        <div className="headline-stat">
          <span className="headline-label">Cost / converged task</span>
          <span className="headline-value">{usd(perConverged)}</span>
        </div>
        {!isCollective && history && typeof history.accuracy === "number" && (
          <div className="headline-stat">
            <span className="headline-label">Solution quality (Critic score)</span>
            <span className="headline-value">{history.accuracy.toFixed(1)}/10</span>
          </div>
        )}
      </div>

      <ModelCards costPerModel={costPerModel} callsPerModel={callsPerModel} accuracyPerModel={accuracyPerModel} />

      {view === "overview" && (
        <div className="chart-grid">
          <BarBreakdown title="Cost per model" data={costPerModel} valueLabel="cost" format={usd} sort="desc" />
          <BarBreakdown
            title="Cost per step class"
            data={costPerStepClass}
            valueLabel="cost"
            format={usd}
            sort="desc"
            color="#8b5cf6"
          />
        </div>
      )}

      {view === "cost_effective" && (
        <div className="chart-grid">
          <BarBreakdown
            title="Cheapest models first"
            data={costPerModel}
            valueLabel="cost"
            format={usd}
            sort="asc"
            color="#10b981"
          />
          <BarBreakdown
            title="Cheapest step classes first"
            data={costPerStepClass}
            valueLabel="cost"
            format={usd}
            sort="asc"
            color="#10b981"
          />
        </div>
      )}

      {view === "accuracy" && accuracyPerModel && (
        <div className="chart-grid">
          <BarBreakdown
            title="Pass rate per model"
            data={accuracyPerModel}
            valueLabel="pass rate"
            format={pct}
            sort="desc"
            color="#f59e0b"
          />
          <BarBreakdown title="Cost per model" data={costPerModel} valueLabel="cost" format={usd} sort="desc" />
        </div>
      )}
    </div>
  );
}
