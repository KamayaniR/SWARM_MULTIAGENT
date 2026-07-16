import { useState } from "react";

const API = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

const DEMO_SPEC = `Build a CSV deduplication CLI that:
- Takes --input, --output, and --key flags
- Reads CSV handling quoted fields
- Deduplicates rows by configurable key columns
- Writes deduplicated output`;

interface RunControlsProps {
  onRunStarted?: (runId: string) => void;
}

export function RunControls({ onRunStarted }: RunControlsProps) {
  const [running, setRunning] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);

  async function startRun(baseline: boolean) {
    setRunning(true);
    try {
      const res = await fetch(`${API}/${baseline ? "run/baseline" : "run"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ spec: DEMO_SPEC }),
      });
      const data = await res.json();
      setRunId(data.run_id);
      onRunStarted?.(data.run_id);
    } catch (err) {
      console.error("Failed to start run — is the backend running on", API, "?", err);
    } finally {
      setRunning(false);
    }
  }

  async function resetScheduler() {
    await fetch(`${API}/scheduler/reset`, { method: "POST" });
  }

  return (
    <div className="run-controls">
      <button onClick={() => startRun(false)} disabled={running} className="btn btn-primary">
        {running ? "Running…" : "Run"}
      </button>
      <button onClick={() => startRun(true)} disabled={running} className="btn">
        Baseline
      </button>
      <button onClick={resetScheduler} className="btn">
        Reset Router
      </button>
      {runId && <span className="run-id">{runId.slice(0, 8)}</span>}
    </div>
  );
}
