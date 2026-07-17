import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SwarmEvent } from "../types/events";

const PASS_THRESHOLD = 8.5;

interface ScorePoint {
  label: string;
  score: number;
}

function TooltipContent({ active, payload }: { active?: boolean; payload?: { payload: ScorePoint }[] }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <div>{point.label}</div>
      <div>score: {point.score.toFixed(1)}</div>
    </div>
  );
}

interface ScoreTimelineProps {
  events: SwarmEvent[];
}

export function ScoreTimeline({ events }: ScoreTimelineProps) {
  const data: ScorePoint[] = useMemo(
    () =>
      events
        .filter((e) => e.agent === "critic" && e.critic_score !== null)
        .map((e) => ({ label: e.step_id, score: e.critic_score as number })),
    [events],
  );

  if (data.length === 0) {
    return (
      <div className="panel-box score-timeline">
        <div className="empty">No critic verdicts yet…</div>
      </div>
    );
  }

  return (
    <div className="panel-box score-timeline">
      <ResponsiveContainer width="100%" height={140}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
          <CartesianGrid stroke="var(--gridline)" vertical={false} />
          <XAxis dataKey="label" stroke="var(--text-muted)" fontSize={11} tickLine={false} />
          <YAxis domain={[0, 10]} stroke="var(--text-muted)" fontSize={11} tickLine={false} width={28} />
          <Tooltip content={<TooltipContent />} />
          <ReferenceLine y={PASS_THRESHOLD} stroke="var(--status-good)" strokeDasharray="4 4" />
          <Line
            dataKey="score"
            stroke="var(--agent-critic)"
            strokeWidth={2}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            dot={(props: any) => {
              const { cx, cy, payload, key } = props;
              const color =
                (payload?.score ?? 0) >= PASS_THRESHOLD ? "var(--status-good)" : "var(--status-critical)";
              return <circle key={key} cx={cx} cy={cy} r={4} fill={color} stroke="none" />;
            }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
