import { useState } from "react";

const API = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

interface InterveneModalProps {
  runId: string;
  stepId: string;
  onClose: () => void;
}

export function InterveneModal({ runId, stepId, onClose }: InterveneModalProps) {
  const [correction, setCorrection] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  async function submit() {
    if (!correction.trim()) return;
    setSubmitting(true);
    try {
      await fetch(`${API}/intervene`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: runId, step_id: stepId, correction_text: correction }),
      });
      setSubmitted(true);
    } catch (err) {
      console.error("Failed to submit intervention", err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal intervene-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Intervene · {stepId}</h2>
          <button className="btn" onClick={onClose}>
            Close
          </button>
        </div>

        {submitted ? (
          <div className="empty">Correction submitted — watch the decision log for the re-plan.</div>
        ) : (
          <>
            <textarea
              className="intervene-textarea"
              placeholder="Describe the correction for this step…"
              value={correction}
              onChange={(e) => setCorrection(e.target.value)}
              rows={4}
            />
            <button className="btn btn-primary" onClick={submit} disabled={submitting || !correction.trim()}>
              {submitting ? "Submitting…" : "Submit correction"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
