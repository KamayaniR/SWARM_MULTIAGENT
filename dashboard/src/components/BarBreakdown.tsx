import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface Props {
  title: string;
  data: Record<string, number>;
  valueLabel: string;
  format: (v: number) => string;
  sort?: "asc" | "desc" | "none";
  color?: string;
}

export function BarBreakdown({ title, data, valueLabel, format, sort = "desc", color = "#6366f1" }: Props) {
  let entries = Object.entries(data).map(([name, value]) => ({ name, value }));
  if (sort !== "none") {
    entries = entries.sort((a, b) => (sort === "asc" ? a.value - b.value : b.value - a.value));
  }

  return (
    <div className="chart-card">
      <h3>{title}</h3>
      {entries.length === 0 ? (
        <p className="empty-note">No data yet.</p>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={entries} layout="vertical" margin={{ left: 24 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" tickFormatter={format} />
            <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(v) => [format(Number(v)), valueLabel]} />
            <Bar dataKey="value" fill={color} radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
