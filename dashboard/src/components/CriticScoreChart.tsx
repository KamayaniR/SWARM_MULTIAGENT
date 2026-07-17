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
import { CRITIC_PASS_THRESHOLD, type CriticScorePoint } from "../pipelineDerive";

interface Props {
  points: CriticScorePoint[];
}

export function CriticScoreChart({ points }: Props) {
  if (points.length === 0) {
    return <p className="empty-note">No Critic verdicts yet.</p>;
  }

  const data = points.map((p) => ({ ...p, name: p.step_id }));

  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data} margin={{ left: 4, right: 16, top: 8 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name" tick={{ fontSize: 11 }} />
        <YAxis domain={[0, 10]} tick={{ fontSize: 11 }} />
        <Tooltip formatter={(v) => Number(v).toFixed(1)} />
        <ReferenceLine
          y={CRITIC_PASS_THRESHOLD}
          stroke="#8b90a3"
          strokeDasharray="4 4"
          label={{ value: `pass (${CRITIC_PASS_THRESHOLD})`, position: "insideTopRight", fontSize: 10, fill: "#8b90a3" }}
        />
        <Line
          type="monotone"
          dataKey="score"
          stroke="#a78bfa"
          strokeWidth={2}
          dot={(props: { cx?: number; cy?: number; payload?: CriticScorePoint & { name: string } }) => {
            const { cx, cy, payload } = props;
            if (cx === undefined || cy === undefined || !payload) return <g />;
            return (
              <circle
                key={`dot-${payload.name}`}
                cx={cx}
                cy={cy}
                r={5}
                fill={payload.passed ? "#10b981" : "#f87171"}
                stroke="none"
              />
            );
          }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
