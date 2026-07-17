import { useEffect, useState } from "react";
import { getRunStatus } from "../api";
import type { RunStatus } from "../types";

const POLL_INTERVAL_MS = 1500;

function isTerminal(status: RunStatus["status"]): boolean {
  return status === "done" || status === "error" || status === "waiting_for_input" || status === "not_found";
}

/**
 * Polls /api/runs/{runId} while a run is actively in progress -- this is
 * what backs the "Running..." indicator, since the real Planner/Coder/
 * Critic/debate calls take several real seconds each and the dashboard
 * would otherwise look frozen during that wait.
 */
export function useRunStatus(runId: string | null) {
  const [status, setStatus] = useState<RunStatus | null>(null);

  useEffect(() => {
    if (runId === null) {
      setStatus(null);
      return;
    }
    setStatus(null);
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      try {
        const result = await getRunStatus(runId);
        if (cancelled) return;
        setStatus(result);
        if (!isTerminal(result.status)) {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch {
        if (!cancelled) timer = setTimeout(poll, POLL_INTERVAL_MS);
      }
    };
    poll();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [runId]);

  return status;
}
