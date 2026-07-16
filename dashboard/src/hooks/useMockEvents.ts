import { useEffect, useState } from "react";
import type { SwarmEvent } from "../types/events";

const STEP_DELAY_MS = 700;

// Cached at module scope so React StrictMode's dev-only double-invoke of
// this effect (mount -> cleanup -> remount) reuses one fetch instead of
// racing two.
let cachedEventsPromise: Promise<SwarmEvent[]> | null = null;
function loadMockEvents(): Promise<SwarmEvent[]> {
  if (!cachedEventsPromise) {
    cachedEventsPromise = fetch("/mock/mock_events.json").then((res) => res.json());
  }
  return cachedEventsPromise;
}

export function useMockEvents(enabled: boolean) {
  const [events, setEvents] = useState<SwarmEvent[]>([]);

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | undefined;

    loadMockEvents().then((allEvents) => {
      if (cancelled) return;
      const startedAt = Date.now();
      // Derives how many events should be visible from elapsed wall-clock
      // time rather than an incrementally-mutated counter, so an extra or
      // duplicate tick (e.g. from StrictMode's dev-only double effect
      // invocation) just recomputes the same slice instead of drifting.
      timer = setInterval(() => {
        const elapsed = Date.now() - startedAt;
        const count = Math.min(allEvents.length, Math.floor(elapsed / STEP_DELAY_MS) + 1);
        setEvents(allEvents.slice(0, count));
        if (count >= allEvents.length) clearInterval(timer);
      }, STEP_DELAY_MS);
    });

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [enabled]);

  return { events, connected: true };
}
