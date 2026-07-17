import { useState } from "react";
import { startRun } from "../api";

interface Props {
  onRunStarted: (runId: string, spec: string) => void;
}

export function PromptPanel({ onRunStarted }: Props) {
  const [spec, setSpec] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!spec.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const { run_id } = await startRun(spec);
      onRunStarted(run_id, spec);
      setSpec("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="panel prompt-panel">
      <h2>New prompt</h2>
      <textarea
        value={spec}
        onChange={(e) => setSpec(e.target.value)}
        placeholder="Describe the software to build..."
        rows={6}
        disabled={submitting}
      />
      <div className="prompt-panel-footer">
        <button onClick={submit} disabled={submitting || !spec.trim()}>
          {submitting ? "Starting..." : "Run"}
        </button>
        {error && <span className="error-text">{error}</span>}
      </div>
    </div>
  );
}
