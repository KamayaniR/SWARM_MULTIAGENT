import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

// Matches the dashboard's own font stack (App.css's `body` rule) -- recharts
// renders <text> nodes with its own default font otherwise, which reads as
// visually "off" against the rest of the page.
const FONT_FAMILY = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, sans-serif";
const AXIS_TICK_STYLE = { fontSize: 11, fontFamily: FONT_FAMILY, fill: "var(--muted)" };

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
  // Longest model name in this dataset sets the label column width instead
  // of a fixed guess -- avoids both wasted whitespace and clipped labels.
  const labelWidth = Math.min(140, Math.max(64, ...entries.map((e) => e.name.length * 6.5)));
  const rowHeight = 34;
  const chartHeight = Math.max(120, entries.length * rowHeight + 40);

  return (
    <div className="chart-card">
      <h3>{title}</h3>
      {entries.length === 0 ? (
        <p className="empty-note">No data yet.</p>
      ) : (
        <ResponsiveContainer width="100%" height={chartHeight}>
          <BarChart
            data={entries}
            layout="vertical"
            margin={{ top: 4, right: 20, bottom: 4, left: 4 }}
            barCategoryGap="30%"
          >
            <XAxis
              type="number"
              tickFormatter={format}
              tick={AXIS_TICK_STYLE}
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              tickCount={4}
            />
            <YAxis
              type="category"
              dataKey="name"
              width={labelWidth}
              tick={AXIS_TICK_STYLE}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              formatter={(v) => [format(Number(v)), valueLabel]}
              contentStyle={{ fontFamily: FONT_FAMILY, fontSize: 12 }}
              cursor={{ fill: "rgba(99, 102, 241, 0.06)" }}
            />
            <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={22}>
              {entries.map((entry) => (
                <Cell key={entry.name} fill={color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
