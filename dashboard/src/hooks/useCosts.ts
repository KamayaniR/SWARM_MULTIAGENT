import { useCallback, useEffect, useState } from "react";
import { getCollectiveCosts, getRunCosts } from "../api";
import type { CollectiveCosts, RunCosts } from "../types";

/**
 * `runId === null` means the collective (all-prompts) view -- the
 * dashboard's default. Passing a run_id switches to that one prompt's
 * breakdown. `refreshToken` bumping re-fetches; callers bump it from the
 * live WebSocket stream so the numbers update in near-real-time without
 * polling on a fixed interval.
 */
export function useCosts(runId: string | null, refreshToken: number) {
  const [collective, setCollective] = useState<CollectiveCosts | null>(null);
  const [perRun, setPerRun] = useState<RunCosts | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      if (runId === null) {
        setCollective(await getCollectiveCosts());
      } else {
        setPerRun(await getRunCosts(runId));
      }
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    setLoading(true);
    refresh();
  }, [refresh, refreshToken]);

  return { collective, perRun, loading, error, refresh };
}
