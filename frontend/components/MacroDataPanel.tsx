"use client";
import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import api from "@/lib/api";
import { useLang } from "@/context/LanguageContext";

const SERIES = [
  { id: "DFF",   label: "Fed Funds", color: "#C9A84C" },
  { id: "GS2",   label: "2Y Yield",  color: "#E53E3E" },
  { id: "GS10",  label: "10Y Yield", color: "#38A169" },
  { id: "T5YIE", label: "Breakeven", color: "#4A6080" },
];

interface Point { date: string; value: number; }

export default function MacroDataPanel() {
  const { T } = useLang();
  const [data, setData] = useState<Point[]>([]);
  const [active, setActive] = useState("DFF");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.get<{ data: Point[] }>(`/api/macro/series/${active}`)
      .then(r => setData(r.data.data))
      .catch(() => setData([]))
      .finally(() => setLoading(false));
  }, [active]);

  const activeColor = SERIES.find(s => s.id === active)?.color;
  const latest = data[data.length - 1];

  return (
    <div className="card">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <div>
          <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest">{T.macroData}</p>
          {latest && (
            <p className="text-lg font-light mt-0.5" style={{ color: activeColor }}>
              {latest.value.toFixed(2)}
              <span className="text-xs text-[var(--color-text-muted)] ml-2">{latest.date}</span>
            </p>
          )}
        </div>
        <div className="flex gap-1 flex-wrap">
          {SERIES.map(s => (
            <button key={s.id} onClick={() => setActive(s.id)}
              className="text-xs px-2 py-1 rounded transition-colors"
              style={{
                background: active === s.id ? "var(--color-navy-700)" : "transparent",
                color: active === s.id ? s.color : "var(--color-text-muted)",
                border: `1px solid ${active === s.id ? s.color : "transparent"}`,
              }}>
              {s.label}
            </button>
          ))}
        </div>
      </div>
      <div className="h-48">
        {loading ? (
          <div className="h-full flex items-center justify-center">
            <p className="text-xs text-[var(--color-text-muted)] animate-pulse">{T.loadingChart}</p>
          </div>
        ) : data.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
                tickFormatter={d => d.slice(2, 7)} interval="preserveStartEnd" minTickGap={40} />
              <YAxis tick={{ fontSize: 10, fill: "var(--color-text-muted)" }} domain={["auto", "auto"]} width={45} />
              <Tooltip contentStyle={{ background: "var(--color-navy-800)", border: "1px solid var(--color-navy-700)", borderRadius: 8, fontSize: 11 }}
                labelStyle={{ color: "var(--color-text-muted)" }} />
              <Line type="monotone" dataKey="value" stroke={activeColor} dot={false} strokeWidth={1.5} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full flex items-center justify-center">
            <p className="text-xs text-[var(--color-text-muted)]">{T.noChartData}</p>
          </div>
        )}
      </div>
    </div>
  );
}
