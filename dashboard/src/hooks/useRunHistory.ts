import { useEffect, useState } from "react";
import { getRunHistory } from "../api";
import type { RunHistoryRecord } from "../types";

/**
 * Fetches the persisted run_history row (orchestrator/artifacts.py) once a
 * run reaches a terminal state. This is what backs the real Critic-score
 * "accuracy" for one specific run -- separate from CollectiveCosts'
 * accuracy_per_model, which is a pass-rate across many calls per model.
 */
export function useRunHistory(runId: string | null, isDone: boolean): RunHistoryRecord | null {
  const [history, setHistory] = useState<RunHistoryRecord | null>(null);

  useEffect(() => {
    if (runId === null || !isDone) {
      setHistory(null);
      return;
    }
    let cancelled = false;
    getRunHistory(runId)
      .then((h) => {
        if (!cancelled) setHistory(h);
      })
      .catch(() => {
        // Non-fatal -- the run history endpoint is a supplementary metric,
        // not required for the rest of the dashboard to function.
      });
    return () => {
      cancelled = true;
    };
  }, [runId, isDone]);

  return history;
}
