import { useEffect, useState } from "react";
import type { RoleResult, TeamResult } from "../types/events";
import { CandidateCard } from "./CandidateCard";
import { CodeViewer } from "./CodeViewer";

interface RoleCardProps {
  roleResult: RoleResult;
  index: number;
}

function RoleCard({ roleResult, index }: RoleCardProps) {
  const { role, candidates, recommended_model } = roleResult;
  // Default the selected model to the recommendation.
  const [selected, setSelected] = useState<string | null>(recommended_model);
  useEffect(() => setSelected(recommended_model), [recommended_model]);

  const selectedCandidate =
    candidates.find((c) => c.model === selected) ?? candidates[0];

  return (
    <div className="role-card">
      <div className="role-head">
        <span className="role-index">Agent {index + 1}</span>
        <span className="role-name">{role.name}</span>
        <span className="role-class">{role.step_class}</span>
      </div>
      <div className="role-responsibility">{role.responsibility}</div>

      <div className="candidate-row">
        {candidates.map((candidate) => (
          <CandidateCard
            key={candidate.model}
            candidate={candidate}
            recommended={candidate.model === recommended_model}
            selected={candidate.model === selectedCandidate?.model}
            onSelect={() => setSelected(candidate.model)}
          />
        ))}
      </div>

      {selectedCandidate && (
        <div className="role-code">
          <div className="role-code-head">
            Code from <strong>{selectedCandidate.model}</strong>
          </div>
          <CodeViewer files={selectedCandidate.files} />
        </div>
      )}
    </div>
  );
}

interface TeamPanelProps {
  result: TeamResult | null;
}

export function TeamPanel({ result }: TeamPanelProps) {
  if (!result || result.roles.length === 0) return null;

  return (
    <div className="team-panel">
      <div className="team-summary">
        <span className="team-count">
          {result.roles.length} agent{result.roles.length === 1 ? "" : "s"} recommended
        </span>
        <span className="team-cost">bake-off cost ${result.total_cost.toFixed(4)}</span>
        {result.status === "running" && <span className="team-status">evaluating…</span>}
      </div>
      {result.roles.map((roleResult, i) => (
        <RoleCard key={roleResult.role.id} roleResult={roleResult} index={i} />
      ))}
    </div>
  );
}
