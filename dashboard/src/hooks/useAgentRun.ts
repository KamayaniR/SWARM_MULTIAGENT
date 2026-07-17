import { useCallback, useEffect, useRef, useState } from "react";
import type { TeamResult } from "../types/events";

const API_BASE =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

const POLL_MS = 1500;

export type AgentRunStatus = "idle" | "running" | "done" | "error";

export function useAgentRun() {
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<AgentRunStatus>("idle");
  const [result, setResult] = useState<TeamResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = undefined;
    }
  }, []);

  const start = useCallback(
    async (spec: string) => {
      stopPolling();
      setStatus("running");
      setResult(null);
      setError(null);
      setRunId(null);
      try {
        const res = await fetch(`${API_BASE}/agent/run`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ spec }),
        });
        const { run_id } = (await res.json()) as { run_id: string };
        setRunId(run_id);
      } catch (e) {
        setStatus("error");
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [stopPolling],
  );

  // Poll the run's result until it finishes.
  useEffect(() => {
    if (!runId) return;
    stopPolling();

    async function poll() {
      try {
        const res = await fetch(`${API_BASE}/api/agent/${runId}`);
        const data = (await res.json()) as {
          status: string;
          result: TeamResult | null;
        };
        if (data.result) setResult(data.result);
        if (data.status === "done") {
          setStatus("done");
          stopPolling();
        } else if (data.status === "error") {
          setStatus("error");
          setError(data.result?.detail ?? "run failed");
          stopPolling();
        }
      } catch {
        // transient — keep polling
      }
    }

    poll();
    pollRef.current = setInterval(poll, POLL_MS);
    return stopPolling;
  }, [runId, stopPolling]);

  return { runId, status, result, error, start };
}
