import type { RecentPrompt, TraceEvent } from "../types";

const EVENT_LIMIT = 5;
const PROMPT_LIMIT = 5;

interface Props {
  events: TraceEvent[];
  recentPrompts: RecentPrompt[];
  connected: boolean;
  activeRunId: string | null;
}

function describe(event: TraceEvent): string {
  const parts = [event.agent, event.action];
  if (event.model) parts.push(event.model);
  if (event.step_class) parts.push(`(${event.step_class})`);
  if (typeof event.cost_usd === "number") parts.push(`$${event.cost_usd.toFixed(3)}`);
  return parts.join(" · ");
}

function truncate(text: string, max: number): string {
  const oneLine = text.replace(/\s+/g, " ").trim();
  return oneLine.length > max ? `${oneLine.slice(0, max)}...` : oneLine;
}

export function EventFeed({ events, recentPrompts, connected, activeRunId }: Props) {
  const visibleEvents = (activeRunId ? events.filter((e) => e.run_id === activeRunId) : events)
    .slice()
    .reverse()
    .slice(0, EVENT_LIMIT);
  const visiblePrompts = recentPrompts.slice(0, PROMPT_LIMIT);

  return (
    <div className="panel event-feed">
      <div className="event-feed-header">
        <h2>Live activity</h2>
        <span className={`ws-status ${connected ? "connected" : "disconnected"}`}>
          {connected ? "live" : "reconnecting..."}
        </span>
      </div>

      <h3 className="event-feed-subheader">Recent prompts</h3>
      <ul className="prompt-list">
        {visiblePrompts.length === 0 && <li className="empty-note">No prompts submitted yet.</li>}
        {visiblePrompts.map((p) => (
          <li key={p.run_id}>
            <span className="event-run">{p.run_id.slice(0, 8)}</span>
            <span className="event-desc">{truncate(p.spec, 80)}</span>
          </li>
        ))}
      </ul>

      <h3 className="event-feed-subheader">Latest events</h3>
      <ul>
        {visibleEvents.length === 0 && <li className="empty-note">No events yet.</li>}
        {visibleEvents.map((e) => (
          <li key={`${e.run_id}-${e.seq}`}>
            <span className="event-run">{e.run_id.slice(0, 8)}</span>
            <span className="event-desc">{describe(e)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
