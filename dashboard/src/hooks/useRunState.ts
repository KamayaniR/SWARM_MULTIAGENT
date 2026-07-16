import { useMemo } from "react";
import { AGENTS, type Agent, type SwarmEvent } from "../types/events";
import { useMockEvents } from "./useMockEvents";
import { useWebSocket } from "./useWebSocket";

const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";

export function useRunState() {
  // Both hooks are always called (Rules of Hooks); each no-ops internally
  // when its `enabled` flag is false, so only one ever does real work.
  const mock = useMockEvents(USE_MOCK);
  const live = useWebSocket(!USE_MOCK);
  const { events, connected } = USE_MOCK ? mock : live;

  const latestByAgent = useMemo(() => {
    const map: Partial<Record<Agent, SwarmEvent>> = {};
    for (const event of events) {
      map[event.agent] = event;
    }
    return map;
  }, [events]);

  const activeAgent: Agent | null = events.length > 0 ? events[events.length - 1].agent : null;

  const totalCostUsd = useMemo(
    () => events.reduce((sum, e) => sum + (e.cost_usd ?? 0), 0),
    [events],
  );

  return { events, connected, latestByAgent, activeAgent, totalCostUsd, agents: AGENTS, usingMock: USE_MOCK };
}
