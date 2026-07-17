import { useEffect, useState } from "react";
import type { SwarmEvent } from "../types/events";

const API = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

interface TraceEntry {
  agent: string;
  step_id: string;
  step_class: string;
  model: string;
  provider: string;
  iteration: number;
  system: string;
  messages: unknown;
  response: unknown;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  latency_ms: number;
}

interface TraceViewerProps {
  runId: string;
  event: SwarmEvent;
  onClose: () => void;
}

export function TraceViewer({ runId, event, onClose }: TraceViewerProps) {
  const [entry, setEntry] = useState<TraceEntry | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`${API}/api/traces/${runId}`)
      .then((res) => res.json())
      .then((data: { entries: TraceEntry[] }) => {
        const match = data.entries.find(
          (e) => e.agent === event.agent && e.step_id === event.step_id && e.iteration === event.iteration,
        );
        setEntry(match ?? null);
      })
      .catch((err) => console.error("Failed to fetch trace", err))
      .finally(() => setLoading(false));
  }, [runId, event]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal trace-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>
            {event.agent} · {event.step_id || "run"}
          </h2>
          <button className="btn" onClick={onClose}>
            Close
          </button>
        </div>

        {loading && <div className="empty">Loading trace…</div>}
        {!loading && !entry && <div className="empty">No trace data found for this event.</div>}

        {entry && (
          <div className="trace-body">
            <div className="trace-meta">
              <span>{entry.model}</span>
              <span>{entry.input_tokens} in / {entry.output_tokens} out tokens</span>
              <span>${entry.cost_usd.toFixed(4)}</span>
              <span>{entry.latency_ms.toFixed(0)}ms</span>
            </div>
            <h3>System prompt</h3>
            <pre className="trace-block">{entry.system}</pre>
            <h3>Messages</h3>
            <pre className="trace-block">{JSON.stringify(entry.messages, null, 2)}</pre>
            <h3>Response</h3>
            <pre className="trace-block">{JSON.stringify(entry.response, null, 2)}</pre>
          </div>
        )}
      </div>
    </div>
  );
}
