"use client";
import { useLang } from "@/context/LanguageContext";
import { HorizonForecast } from "@/lib/api";

interface Props {
  signal: "hawkish" | "neutral" | "dovish";
  confidence: number;
  publishedAt?: string;
  horizon?: string;
}

const SIGNAL_VALUE = { hawkish: 85, neutral: 50, dovish: 15 };
const SIGNAL_COLOR = {
  hawkish: "var(--color-signal-red)",
  neutral: "var(--color-gold)",
  dovish: "var(--color-signal-green)",
};

export default function HawkDoveGauge({ signal, confidence, publishedAt, horizon = "12m" }: Props) {
  const { T, lang } = useLang();
  const value = SIGNAL_VALUE[signal];
  const r = 70, cx = 100, cy = 90;
  const angle = Math.PI + (value / 100) * Math.PI;
  const needleX = cx + (r - 10) * Math.cos(angle);
  const needleY = cy + (r - 10) * Math.sin(angle);

  const horizonLabel = T.horizonLabels[horizon as keyof typeof T.horizonLabels] ?? horizon;

  const dateLabel = publishedAt
    ? new Date(publishedAt).toLocaleString("ko-KR", {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
        timeZone: "Asia/Seoul",
      }) + " KST 기준"
    : null;

  return (
    <div className="card flex flex-col items-center">
      <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest mb-1">{T.policyStance}</p>
      <p className="text-[10px] text-[var(--color-gold)] mb-3">{horizonLabel}</p>

      <svg viewBox="0 0 200 100" className="w-48" suppressHydrationWarning>
        <path d={`M${cx - r},${cy} A${r},${r} 0 0,1 ${cx + r},${cy}`}
          fill="none" stroke="var(--color-navy-700)" strokeWidth="10" />
        <path d={`M${cx - r},${cy} A${r},${r} 0 0,1 ${needleX},${needleY}`}
          fill="none" stroke={SIGNAL_COLOR[signal]} strokeWidth="10" strokeLinecap="round" />
        <circle cx={needleX} cy={needleY} r="6" fill={SIGNAL_COLOR[signal]} />
        <text x={cx - r - 4} y={cy + 18} fontSize="8" fill="var(--color-signal-red)" textAnchor="middle">HAWK</text>
        <text x={cx + r + 4} y={cy + 18} fontSize="8" fill="var(--color-signal-green)" textAnchor="middle">DOVE</text>
      </svg>

      <span style={{ color: SIGNAL_COLOR[signal] }} className="text-lg font-semibold mt-1">
        {signal === "hawkish" ? T.hawkish : signal === "dovish" ? T.dovish : T.neutral}
      </span>
      <span className="text-xs text-[var(--color-text-muted)] mt-0.5">
        {(confidence * 100).toFixed(0)}% {T.confidence.toLowerCase()}
      </span>
      {dateLabel && (
        <span className="text-[10px] text-[var(--color-text-muted)] mt-1.5 text-center" suppressHydrationWarning>
          {dateLabel}
        </span>
      )}
    </div>
  );
}
