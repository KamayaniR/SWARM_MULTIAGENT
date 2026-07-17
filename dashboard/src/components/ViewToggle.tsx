import type { ViewMode } from "../types";

const VIEWS: { id: ViewMode; label: string; description: string; collectiveOnly?: boolean }[] = [
  { id: "overview", label: "Overview", description: "Cost split evenly across model and step class" },
  { id: "cost_effective", label: "Cost Effective", description: "Cheapest tiers and step classes first" },
  { id: "accuracy", label: "Accuracy", description: "Pass rate per model", collectiveOnly: true },
];

interface Props {
  view: ViewMode;
  onChange: (view: ViewMode) => void;
  isCollective: boolean;
}

export function ViewToggle({ view, onChange, isCollective }: Props) {
  return (
    <div className="view-toggle">
      {VIEWS.map((v) => {
        const disabled = v.collectiveOnly && !isCollective;
        return (
          <button
            key={v.id}
            className={`view-toggle-btn ${view === v.id ? "active" : ""}`}
            title={disabled ? "Only available in the collective (all-prompts) view" : v.description}
            disabled={disabled}
            onClick={() => onChange(v.id)}
          >
            {v.label}
          </button>
        );
      })}
    </div>
  );
}
