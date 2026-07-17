import type { CandidateResult } from "../types/events";

interface CandidateCardProps {
  candidate: CandidateResult;
  recommended: boolean;
  selected: boolean;
  onSelect: () => void;
}

export function CandidateCard({ candidate, recommended, selected, onSelect }: CandidateCardProps) {
  const { model, critic_score, tests_passed, tests_total, cost_usd, latency_ms, passed, error } =
    candidate;

  return (
    <button
      type="button"
      className={`candidate-card${selected ? " selected" : ""}${passed ? " pass" : " fail"}`}
      onClick={onSelect}
    >
      <div className="candidate-head">
        <span className="candidate-model">{model}</span>
        {recommended && <span className="rec-badge">recommended</span>}
      </div>

      {error ? (
        <div className="candidate-error">error: {error}</div>
      ) : (
        <div className="candidate-metrics">
          <div className="metric">
            <span className="metric-label">cost</span>
            <span className="metric-value">${cost_usd.toFixed(4)}</span>
          </div>
          <div className="metric">
            <span className="metric-label">quality</span>
            <span className="metric-value">{critic_score.toFixed(1)}</span>
          </div>
          <div className="metric">
            <span className="metric-label">tests</span>
            <span className="metric-value">
              {tests_passed}/{tests_total}
            </span>
          </div>
          <div className="metric">
            <span className="metric-label">time</span>
            <span className="metric-value">{(latency_ms / 1000).toFixed(1)}s</span>
          </div>
        </div>
      )}

      <div className={`candidate-verdict ${passed ? "pass" : "fail"}`}>
        {passed ? "PASS" : "FAIL"}
      </div>
    </button>
  );
}
