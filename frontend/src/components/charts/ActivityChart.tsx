import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Overview } from "../../types/api";

const chartDateFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
});

export function ActivityChart({ data }: { data: Overview["chart"] }) {
  if (!data.length) {
    return (
      <div className="chart-empty">
        Collection activity will appear after the first run.
      </div>
    );
  }
  return (
    <div className="chart-wrap" role="img" aria-label="Collection activity over time">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 9, left: -18, bottom: 3 }}>
          <CartesianGrid stroke="#354052" vertical={false} strokeDasharray="3 5" />
          <XAxis
            dataKey="date"
            tickFormatter={(value: string) =>
              chartDateFormatter.format(new Date(value))
            }
            stroke="#BFCBDD"
            tick={{ fill: "#D4DEEA", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            minTickGap={20}
          />
          <YAxis
            allowDecimals={false}
            stroke="#BFCBDD"
            tick={{ fill: "#D4DEEA", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={{
              background: "#171F2A",
              border: "1px solid #526176",
              borderRadius: 8,
              color: "#FFFFFF",
              fontSize: 12,
            }}
            labelFormatter={(value) => new Date(String(value)).toLocaleDateString()}
          />
          <Legend wrapperStyle={{ color: "#D4DEEA", fontSize: 11, paddingTop: 4 }} />
          <Line
            type="monotone"
            dataKey="new_records"
            name="New records"
            stroke="#FFAD73"
            strokeWidth={2}
            dot={{ r: 2, fill: "#FFAD73" }}
            activeDot={{ r: 4 }}
          />
          <Line
            type="monotone"
            dataKey="changed_records"
            name="Updated records"
            stroke="#69BAFF"
            strokeWidth={2}
            dot={{ r: 2, fill: "#69BAFF" }}
            activeDot={{ r: 4 }}
          />
          <Line
            type="monotone"
            dataKey="failed_runs"
            name="Failed runs"
            stroke="#FF7185"
            strokeWidth={1.7}
            dot={{ r: 2, fill: "#FF7185" }}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
