import { useMemo, useState } from "react";
import { useAgentRun } from "../hooks/useAgentRun";
import { useWebSocket } from "../hooks/useWebSocket";
import { DecisionLog } from "./DecisionLog";
import { TeamPanel } from "./TeamPanel";

export function AgentModeView() {
  const [spec, setSpec] = useState("");
  const { runId, status, result, error, start } = useAgentRun();

  // Live events stream over the shared WebSocket; filter to this run.
  const { events } = useWebSocket(true);
  const runEvents = useMemo(
    () => (runId ? events.filter((e) => e.run_id === runId) : []),
    [events, runId],
  );

  const busy = status === "running";

  return (
    <div className="agent-mode">
      <p className="agent-mode-intro">
        Describe a task. A planner decides how many agents it needs, then two candidate
        models are baked off per agent in isolated sandboxes — real code, tests, and cost —
        so you can pick the best fit and take its code.
      </p>

      <div className="agent-input">
        <textarea
          value={spec}
          onChange={(e) => setSpec(e.target.value)}
          placeholder="e.g. Build a string-utils library with slugify and titlecase, fully tested."
          rows={4}
          disabled={busy}
        />
        <button
          className="btn btn-primary"
          onClick={() => start(spec)}
          disabled={busy || spec.trim().length === 0}
        >
          {busy ? "Composing…" : "Compose team"}
        </button>
      </div>

      {error && <div className="agent-error">Error: {error}</div>}

      {runId && (
        <>
          <h2 className="section-title">Live decisions</h2>
          <DecisionLog events={runEvents} />
        </>
      )}

      <TeamPanel result={result} />
    </div>
  );
}
