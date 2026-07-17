import { useCallback, useEffect, useMemo, useState } from "react";
import "./App.css";
import { listRunHistory } from "./api";
import { CostDashboard } from "./components/CostDashboard";
import { CurrentRunPanel } from "./components/CurrentRunPanel";
import { EventFeed } from "./components/EventFeed";
import { PromptPanel } from "./components/PromptPanel";
import { RunSelector } from "./components/RunSelector";
import { ViewToggle } from "./components/ViewToggle";
import { useCosts } from "./hooks/useCosts";
import { useLiveEvents } from "./hooks/useLiveEvents";
import { useRunStatus } from "./hooks/useRunStatus";
import { useRunTrace } from "./hooks/useRunTrace";
import type { RecentPrompt, TraceEvent, ViewMode } from "./types";

const MAX_RECENT_PROMPTS = 5;

export default function App() {
  const [view, setView] = useState<ViewMode>("overview");
  // null = collective (default). Set when the user picks a specific prompt
  // from the RunSelector to drill into just that run's breakdown.
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [activeRunStartedAt, setActiveRunStartedAt] = useState<number | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [seenRunIds, setSeenRunIds] = useState<string[]>([]);
  const [recentPrompts, setRecentPrompts] = useState<RecentPrompt[]>([]);

  const bumpRefresh = useCallback((event: TraceEvent) => {
    setSeenRunIds((prev) => (prev.includes(event.run_id) ? prev : [event.run_id, ...prev]));
    // Cost-affecting actions only -- no need to refetch on every trace event.
    if (event.action === "llm_call" || event.action === "verdict") {
      setRefreshToken((t) => t + 1);
    }
  }, []);

  const { events, connected } = useLiveEvents(bumpRefresh);

  // Seed the run selector with real persisted history (orchestrator/
  // artifacts.py's run_history table) on mount -- otherwise only runs
  // submitted live in this exact browser session are selectable, and
  // historical accuracy/cost data becomes unreachable after a page reload.
  useEffect(() => {
    listRunHistory()
      .then(({ runs }) => {
        setSeenRunIds((prev) => {
          const ids = runs.map((r) => r.run_id);
          const merged = [...prev];
          for (const id of ids) if (!merged.includes(id)) merged.push(id);
          return merged;
        });
        setRecentPrompts((prev) => {
          const known = new Set(prev.map((p) => p.run_id));
          const historical: RecentPrompt[] = runs
            .filter((r) => !known.has(r.run_id))
            .map((r) => ({
              run_id: r.run_id,
              spec: r.prompt ?? "",
              submitted_at: r.created_at ? new Date(r.created_at).getTime() : 0,
            }));
          return [...prev, ...historical]
            .sort((a, b) => b.submitted_at - a.submitted_at)
            .slice(0, MAX_RECENT_PROMPTS);
        });
      })
      .catch(() => {
        // Non-fatal -- the dashboard still works from live session data alone.
      });
  }, []);

  const isCollective = selectedRun === null;
  const effectiveView = useMemo<ViewMode>(
    () => (view === "accuracy" && !isCollective ? "overview" : view),
    [view, isCollective],
  );
  const { collective, perRun } = useCosts(selectedRun, refreshToken);
  const runStatus = useRunStatus(activeRunId);
  const activeRunTrace = useRunTrace(activeRunId);

  const onRunStarted = (runId: string, spec: string) => {
    const submittedAt = Date.now();
    setActiveRunId(runId);
    setActiveRunStartedAt(submittedAt);
    // Deliberately NOT switching `selectedRun` here -- the cost dashboard's
    // scope stays on whatever the user had selected (Collective by
    // default), so it keeps showing real prior data uninterrupted instead
    // of jumping to a brand-new run_id that has no data yet while it's
    // still in progress. RunStatusBanner (via activeRunId) is what tracks
    // this specific prompt's progress instead.
    setSeenRunIds((prev) => (prev.includes(runId) ? prev : [runId, ...prev]));
    setRecentPrompts((prev) =>
      [{ run_id: runId, spec, submitted_at: submittedAt }, ...prev].slice(0, MAX_RECENT_PROMPTS),
    );
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>The Yield</h1>
        <p className="app-subtitle">Cost-aware multi-agent build system — live dashboard</p>
      </header>

      <CurrentRunPanel
        runId={activeRunId}
        startedAt={activeRunStartedAt}
        status={runStatus}
        events={activeRunTrace}
      />

      <main className="app-grid">
        <div className="left-column">
          <PromptPanel onRunStarted={onRunStarted} />
          <EventFeed
            events={events}
            recentPrompts={recentPrompts}
            connected={connected}
            activeRunId={activeRunId}
          />
        </div>

        <div className="right-column">
          <div className="dashboard-controls">
            <RunSelector runIds={seenRunIds} selected={selectedRun} onChange={setSelectedRun} />
            <ViewToggle view={effectiveView} onChange={setView} isCollective={isCollective} />
          </div>
          <CostDashboard
            view={effectiveView}
            isCollective={isCollective}
            collective={collective}
            perRun={perRun}
            selectedRun={selectedRun}
          />
        </div>
      </main>
    </div>
  );
}
