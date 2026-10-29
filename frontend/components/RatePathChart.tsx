"use client";
import { useState, useEffect } from "react";
import {
  ComposedChart, Line, Area, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer,
} from "recharts";
import { AllHorizons, HorizonForecast } from "@/lib/api";
import { useLang } from "@/context/LanguageContext";
import { shortLabel, longLabel } from "@/lib/horizons";

const SIG_COLOR: Record<string, string> = {
  hawkish: "var(--color-signal-red)",
  neutral: "var(--color-gold)",
  dovish: "var(--color-signal-green)",
};

interface Row {
  key: string;
  label: string;
  full: string;
  rate: number | null;
  band: [number, number] | null;
  delta: number;
  signal: string;
  conf: number;
  primary: boolean;
  kind: string;
}

interface Props {
  horizons: AllHorizons | null;
  activeHorizon?: string | null;
  onSelect?: (key: string) => void;
  height?: number;
}

/** Implied policy-rate level after each FOMC meeting in the 3-year window
 *  (today's rate + the committee's cumulative call), with the ±1σ committee
 *  band. The 5Y / 10Y / 30Y points are shown as separate cards, not here. */
export default function RatePathChart({ horizons, activeHorizon, onSelect, height = 230 }: Props) {
  const { lang } = useLang();
  const ko = lang === "ko";
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!horizons) return null;
  const base = horizons.current_rate_pct;
  const pts: HorizonForecast[] = horizons.items.filter(i => i.kind === "today" || i.kind === "fomc");
  if (pts.length < 2) return null;

  const rows: Row[] = pts.map(fc => {
    const d = fc.published_delta_bps ?? 0;
    const rate = fc.implied_rate_pct ?? (base != null ? base + d / 100 : null);
    const lo = fc.band_low_bps, hi = fc.band_high_bps;
    const band: [number, number] | null =
      base != null && lo != null && hi != null ? [base + lo / 100, base + hi / 100] : null;
    return {
      key: fc.horizon, label: shortLabel(fc, lang), full: longLabel(fc, lang),
      rate, band, delta: d, signal: fc.signal, conf: fc.confidence ?? 0,
      primary: fc.horizon === horizons.primary, kind: fc.kind,
    };
  });

  const rates = rows.flatMap(r => [r.rate ?? NaN, ...(r.band ?? [])]).filter(v => Number.isFinite(v));
  const yMin = Math.floor((Math.min(...rates) - 0.15) * 4) / 4;
  const yMax = Math.ceil((Math.max(...rates) + 0.15) * 4) / 4;

  if (!mounted) return <div style={{ width: "100%", height }} />;

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <ComposedChart data={rows} margin={{ top: 10, right: 12, bottom: 0, left: -14 }}
          onClick={(s) => {
            const idx = (s as { activeTooltipIndex?: number | string | null })?.activeTooltipIndex;
            const i = typeof idx === "string" ? parseInt(idx, 10) : idx;
            if (onSelect && i != null && rows[i]) onSelect(rows[i].key);
          }}>
          <XAxis dataKey="label" tick={{ fontSize: 9, fill: "#8BA0BC" }} interval={0}
            angle={-45} textAnchor="end" height={44} tickMargin={4} />
          <YAxis domain={[yMin, yMax]} tick={{ fontSize: 9, fill: "#8BA0BC" }}
            tickFormatter={(v: number) => `${v.toFixed(2)}%`} width={56} />
          <Tooltip
            contentStyle={{ background: "#0D1F3C", border: "1px solid #112952", fontSize: 11 }}
            labelStyle={{ color: "#8BA0BC" }}
            labelFormatter={(_l, payload) => {
              const r = payload?.[0]?.payload as Row | undefined;
              return r ? r.full : "";
            }}
            formatter={(v, name, item) => {
              const r = item?.payload as Row | undefined;
              if (name === "band" && Array.isArray(v)) {
                return [`${v[0].toFixed(2)}% ~ ${v[1].toFixed(2)}%`, ko ? "위원회 ±1σ" : "committee ±1σ"];
              }
              if (!r) return [String(v), name];
              const sig = r.signal === "hawkish" ? (ko ? "매파" : "hawkish") : r.signal === "dovish" ? (ko ? "비둘기" : "dovish") : (ko ? "중립" : "neutral");
              return [
                `${Number(v).toFixed(2)}%  (${r.delta > 0 ? "+" : ""}${r.delta.toFixed(0)} bps · ${sig} · ${ko ? "신뢰도" : "conf"} ${(r.conf * 100).toFixed(0)}%)`,
                ko ? "예상 기준금리" : "implied rate",
              ];
            }}
          />
          {base != null && (
            <ReferenceLine y={base} stroke="#8BA0BC" strokeDasharray="3 3"
              label={{ value: ko ? "현재" : "now", position: "insideTopRight", fontSize: 9, fill: "#8BA0BC" }} />
          )}
          <Area type="stepAfter" dataKey="band" stroke="none" fill="var(--color-gold)" fillOpacity={0.12}
            connectNulls isAnimationActive={false} />
          <Line type="stepAfter" dataKey="rate" stroke="var(--color-gold)" strokeWidth={1.8}
            connectNulls isAnimationActive={false}
            dot={(p: { cx?: number; cy?: number; payload?: Row; index?: number }) => {
              const r = p.payload;
              if (!r || p.cx == null || p.cy == null) return <g key={p.index} />;
              const isActive = activeHorizon === r.key;
              const color = r.kind === "today" ? "#8BA0BC" : SIG_COLOR[r.signal] ?? "var(--color-gold)";
              return (
                <g key={r.key}>
                  {(r.primary || isActive) && (
                    <circle cx={p.cx} cy={p.cy} r={isActive ? 8 : 7} fill="none"
                      stroke={isActive ? color : "var(--color-gold)"} strokeWidth={1.2} opacity={0.7} />
                  )}
                  <circle cx={p.cx} cy={p.cy} r={r.kind === "today" ? 3 : 4} fill={color}
                    stroke="#0D1F3C" strokeWidth={1} />
                </g>
              );
            }}
            activeDot={{ r: 6 }} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
