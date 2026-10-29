"use client";
import { useState, useEffect } from "react";
import { AllHorizons, Horizon } from "@/lib/api";
import { useLang } from "@/context/LanguageContext";
import { byKey, longLabel } from "@/lib/horizons";

const SIGNAL_VALUE = { hawkish: 85, neutral: 50, dovish: 15 };
const SIGNAL_COLOR = {
  hawkish: "var(--color-signal-red)",
  neutral: "var(--color-gold)",
  dovish: "var(--color-signal-green)",
};

interface Props {
  horizons: AllHorizons | null;
  activeHorizon: Horizon;
}

export default function MultiHorizonGauges({ horizons, activeHorizon: active }: Props) {
  const { T, lang } = useLang();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!horizons) return null;

  const sel = byKey(horizons, active);
  const fc = sel && sel.kind !== "today" ? sel : null;
  const signal = fc?.signal ?? "neutral";
  const confidence = fc?.confidence ?? 0;
  const delta = fc?.published_delta_bps ?? 0;
  const color = SIGNAL_COLOR[signal];
  const signalLabel = signal === "hawkish" ? T.hawkish : signal === "dovish" ? T.dovish : T.neutral;

  // Gauge math
  const r = 90, cx = 130, cy = 120;
  const angle = Math.PI + (SIGNAL_VALUE[signal] / 100) * Math.PI;
  const needleX = cx + (r - 12) * Math.cos(angle);
  const needleY = cy + (r - 12) * Math.sin(angle);

  const dateLabel = fc?.published_at
    ? new Date(fc.published_at).toLocaleString("ko-KR", {
        month: "short", day: "numeric",
        hour: "2-digit", minute: "2-digit",
        timeZone: "Asia/Seoul",
      }) + " KST"
    : null;

  return (
    <div className="card">
      <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest mb-4">
        {lang === "en" ? "Policy Stance" : "정책 기조"}
      </p>

      {/* Large gauge for selected horizon */}
      <div className="flex flex-col items-center">
        {!mounted ? (
          <div style={{ width: 260, height: 145 }} />
        ) : (
          <svg viewBox="0 0 260 145" className="w-56 md:w-64">
            {/* Track */}
            <path d={`M${cx - r},${cy} A${r},${r} 0 0,1 ${cx + r},${cy}`}
              fill="none" stroke="var(--color-navy-700)" strokeWidth="14" />
            {/* Fill */}
            {fc && (
              <path d={`M${cx - r},${cy} A${r},${r} 0 0,1 ${needleX},${needleY}`}
                fill="none" stroke={color} strokeWidth="14" strokeLinecap="round" />
            )}
            {/* Glow ring */}
            {fc && (
              <path d={`M${cx - r},${cy} A${r},${r} 0 0,1 ${needleX},${needleY}`}
                fill="none" stroke={color} strokeWidth="4" strokeLinecap="round" opacity="0.25" />
            )}
            {/* Needle */}
            {fc && <circle cx={needleX} cy={needleY} r="9" fill={color} />}
            {/* Center labels */}
            <text x={cx - r - 6} y={cy + 22} fontSize="11" fill="var(--color-signal-red)" textAnchor="middle" fontWeight="600">HAWK</text>
            <text x={cx + r + 6} y={cy + 22} fontSize="11" fill="var(--color-signal-green)" textAnchor="middle" fontWeight="600">DOVE</text>
          </svg>
        )}

        {/* Signal label */}
        <p className="text-2xl font-semibold mt-1" style={{ color: fc ? color : "var(--color-text-muted)" }}>
          {fc ? signalLabel : "—"}
        </p>
        {fc && (
          <p className="text-base font-light mt-0.5" style={{ color }}>
            {delta > 0 ? "+" : ""}{delta.toFixed(0)} bps
          </p>
        )}
        <p className="text-xs text-[var(--color-text-muted)] mt-1">
          {fc ? longLabel(fc, lang) : (lang === "ko" ? "FOMC 회의를 선택하세요" : "Select an FOMC meeting")}
        </p>

        {/* Confidence */}
        {fc && (
          <div className="w-full max-w-[12rem] mt-4">
            <div className="flex justify-between text-[10px] text-[var(--color-text-muted)] mb-1">
              <span>{T.confidence}</span>
              <span>{(confidence * 100).toFixed(0)}%</span>
            </div>
            <div className="h-1.5 bg-[var(--color-navy-700)] rounded-full overflow-hidden">
              <div className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${confidence * 100}%`,
                  backgroundColor: confidence >= 0.65
                    ? "var(--color-signal-green)"
                    : confidence >= 0.4 ? "var(--color-gold)" : "var(--color-slate-400)",
                }} />
            </div>
          </div>
        )}

        {/* Timestamp */}
        {dateLabel && (
          <p className="text-[10px] text-[var(--color-text-muted)] mt-2" suppressHydrationWarning>
            {dateLabel} {lang === "en" ? "basis" : "기준"}
          </p>
        )}
      </div>

      {/* Legend */}
      <div className="mt-4 space-y-1">
        <p className="text-[10px] text-[var(--color-text-muted)] text-center">
          {lang === "en"
            ? "bps = cumulative change from current Fed Funds Rate"
            : "bps = 현재 기준금리 대비 누적 변화폭"}
        </p>
      </div>
    </div>
  );
}
