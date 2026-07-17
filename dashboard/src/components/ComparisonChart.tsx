import { useEffect, useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const API = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

interface Comparison {
  baseline_usd: number;
  scheduler_usd: number;
  savings_pct: number;
}

interface ComparisonChartProps {
  baselineRunId: string | null;
  schedulerRunId: string | null;
}

export function ComparisonChart({ baselineRunId, schedulerRunId }: ComparisonChartProps) {
  const [comparison, setComparison] = useState<Comparison | null>(null);

  useEffect(() => {
    if (!baselineRunId || !schedulerRunId) {
      setComparison(null);
      return;
    }
    fetch(`${API}/api/costs/compare/${baselineRunId}/${schedulerRunId}`)
      .then((res) => res.json())
      .then(setComparison)
      .catch((err) => console.error("Failed to fetch cost comparison", err));
  }, [baselineRunId, schedulerRunId]);

  if (!baselineRunId || !schedulerRunId) {
    return (
      <div className="panel-box comparison-chart">
        <div className="empty">Run both Baseline and Run to see the cost comparison.</div>
      </div>
    );
  }

  if (!comparison) {
    return (
      <div className="panel-box comparison-chart">
        <div className="empty">Loading comparison…</div>
      </div>
    );
  }

  const data = [
    { name: "Baseline", cost: comparison.baseline_usd },
    { name: "Scheduler", cost: comparison.scheduler_usd },
  ];

  return (
    <div className="panel-box comparison-chart">
      <div className="comparison-savings">
        {comparison.savings_pct > 0
          ? `${comparison.savings_pct.toFixed(0)}% cheaper with the scheduler`
          : "No savings on this run"}
      </div>
      <ResponsiveContainer width="100%" height={100}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 8 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="name" stroke="var(--text-secondary)" fontSize={12} width={70} />
          <Tooltip
            formatter={(value) => `$${Number(value).toFixed(4)}`}
            contentStyle={{
              background: "var(--surface-1)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              fontSize: 12,
            }}
          />
          <Bar dataKey="cost" radius={4} barSize={22}>
            <Cell fill="var(--agent-tester)" />
            <Cell fill="var(--agent-router)" />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
