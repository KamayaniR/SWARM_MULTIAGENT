import { useEffect, useRef, useState } from "react";
import { WS_URL } from "../api";
import type { TraceEvent } from "../types";

const MAX_EVENTS = 500;
const RECONNECT_DELAY_MS = 2000;
// The rendered event list updates on this cadence, not per-message -- a
// constantly reflowing list read as "keeps refreshing" in practice. `onEvent`
// still fires immediately per message underneath (cost aggregates stay
// real-time), only the visible feed is batched.
const FLUSH_INTERVAL_MS = 150_000;

/**
 * Owns the single live WebSocket connection to the server. Reconnects on
 * drop (dev server restarts, network blips) rather than leaving the
 * dashboard silently stale. `onEvent` fires per message so callers can react
 * (e.g. refetch cost aggregates) without threading the whole event list
 * through props.
 */
export function useLiveEvents(onEvent?: (event: TraceEvent) => void) {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  const bufferRef = useRef<TraceEvent[]>([]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    const flush = () => {
      if (bufferRef.current.length === 0) return;
      const pending = bufferRef.current;
      bufferRef.current = [];
      setEvents((prev) => {
        const next = [...prev, ...pending];
        return next.length > MAX_EVENTS ? next.slice(next.length - MAX_EVENTS) : next;
      });
    };
    const flushTimer = setInterval(flush, FLUSH_INTERVAL_MS);

    const connect = () => {
      ws = new WebSocket(WS_URL);

      ws.onopen = () => setConnected(true);

      ws.onmessage = (msg) => {
        const event = JSON.parse(msg.data) as TraceEvent;
        bufferRef.current.push(event);
        onEventRef.current?.(event);
      };

      ws.onclose = () => {
        setConnected(false);
        if (!cancelled) {
          reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
        }
      };

      ws.onerror = () => ws?.close();
    };

    connect();

    return () => {
      cancelled = true;
      clearInterval(flushTimer);
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, []);

  return { events, connected };
}
