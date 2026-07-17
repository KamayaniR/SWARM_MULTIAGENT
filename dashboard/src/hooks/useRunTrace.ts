import { useEffect, useState } from "react";
import { getTraces } from "../api";
import type { TraceEvent } from "../types";

const POLL_INTERVAL_MS = 3000;

/**
 * Polls the full trace for one specific run -- used by the per-run
 * "Run Pipeline" drill-down, which the user explicitly opened, so it gets
 * full real-time detail rather than the Live Activity panel's 2-3 minute
 * batching (that throttle exists to keep the always-on collective feed calm,
 * not because per-run detail should be stale).
 */
export function useRunTrace(runId: string | null): TraceEvent[] {
  const [entries, setEntries] = useState<TraceEvent[]>([]);

  useEffect(() => {
    if (runId === null) {
      setEntries([]);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      try {
        const res = await getTraces(runId);
        if (!cancelled) setEntries(res.entries);
      } catch {
        // transient fetch failure -- next poll will retry
      }
      if (!cancelled) timer = setTimeout(poll, POLL_INTERVAL_MS);
    };
    poll();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [runId]);

  return entries;
}
