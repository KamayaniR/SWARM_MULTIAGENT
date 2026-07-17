import { useEffect, useState } from "react";
import type { RunStatus } from "../types";

interface Props {
  status: RunStatus | null;
  startedAt: number | null;
}

function label(status: RunStatus): string {
  switch (status.status) {
    case "running":
      return "Running";
    case "waiting_for_input":
      return "Waiting on you";
    case "error":
      return `Error: ${status.detail}`;
    case "done":
      return "Done";
    case "not_found":
      return "Not found";
  }
}

export function RunStatusBanner({ status, startedAt }: Props) {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!status || status.status !== "running") return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [status]);

  if (!status || startedAt === null) return null;

  const elapsedSec = Math.max(0, Math.round((now - startedAt) / 1000));
  const stateClass =
    status.status === "done"
      ? "done"
      : status.status === "error"
        ? "error"
        : status.status === "waiting_for_input"
          ? "waiting"
          : "running";

  return (
    <div className={`run-status-banner run-status-${stateClass}`}>
      <span className="run-status-dot" />
      <span className="run-status-text">{label(status)}</span>
      {status.status === "running" && <span className="run-status-elapsed">{elapsedSec}s</span>}
    </div>
  );
}
