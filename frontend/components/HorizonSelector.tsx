"use client";
import { useEffect, useRef } from "react";
import { AllHorizons, Horizon, HorizonForecast } from "@/lib/api";
import { useLang } from "@/context/LanguageContext";
import { shortLabel } from "@/lib/horizons";

const SIG_COLOR: Record<string, string> = {
  hawkish: "var(--color-signal-red)",
  neutral: "var(--color-gold)",
  dovish: "var(--color-signal-green)",
};

interface Props {
  horizons: AllHorizons | null;
  active: Horizon;
  onChange: (h: Horizon) => void;
}

/** Horizontally scrollable strip of every forecast point: today, each FOMC
 *  meeting inside the 3-year window (by decision date), then 5Y / 10Y / 30Y. */
export default function HorizonSelector({ horizons, active, onChange }: Props) {
  const { lang } = useLang();
  const ko = lang === "ko";
  const activeRef = useRef<HTMLButtonElement | null>(null);

  // Keep the selected chip in view when the selection changes.
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" });
  }, [active]);

  if (!horizons || horizons.items.length === 0) return null;

  const chip = (fc: HorizonForecast) => {
    const isActive = active === fc.horizon;
    const isPrimary = fc.horizon === horizons.primary;
    const delta = fc.published_delta_bps ?? 0;
    const color = SIG_COLOR[fc.signal] ?? "var(--color-gold)";
    const year = fc.meeting_date?.slice(0, 4);
    return (
      <button
        key={fc.horizon}
        ref={isActive ? activeRef : undefined}
        onClick={() => onChange(fc.horizon)}
        title={fc.meeting_date}
        className="shrink-0 snap-start flex flex-col items-center gap-0.5 px-2.5 py-1.5 rounded-md transition-all min-w-[56px]"
        style={{
          background: isActive ? "var(--color-navy-700)" : "transparent",
          border: `1px solid ${isActive ? color : isPrimary ? "rgba(201,168,76,0.6)" : "var(--color-navy-700)"}`,
          boxShadow: isPrimary && !isActive ? "0 0 0 1px rgba(201,168,76,0.2)" : "none",
        }}
      >
        <span className="text-[11px] font-medium leading-none"
          style={{ color: isActive ? "var(--color-text-primary)" : "var(--color-text-muted)" }}>
          {shortLabel(fc, lang)}
        </span>
        <span className="text-[10px] leading-none" style={{ color: fc.kind === "today" ? "var(--color-text-muted)" : color }}>
          {fc.kind === "today"
            ? (fc.implied_rate_pct != null ? `${fc.implied_rate_pct.toFixed(2)}%` : "—")
            : `${delta > 0 ? "+" : ""}${delta.toFixed(0)}`}
        </span>
        {isPrimary && (
          <span className="text-[8px] font-bold tracking-wider" style={{ color: "var(--color-gold)" }}>
            {ko ? "핵심" : "KEY"}
          </span>
        )}
        {fc.kind === "fomc" && fc.projected && (
          <span className="sr-only">{year} projected</span>
        )}
      </button>
    );
  };

  const today = horizons.items.filter(i => i.kind === "today");
  const fomc = horizons.items.filter(i => i.kind === "fomc");
  const long = horizons.items.filter(i => i.kind !== "today" && i.kind !== "fomc");

  // Year dividers inside the FOMC run so 20+ chips stay scannable.
  const groups: { year: string; items: HorizonForecast[] }[] = [];
  for (const fc of fomc) {
    const y = fc.meeting_date?.slice(0, 4) ?? "";
    const g = groups[groups.length - 1];
    if (g && g.year === y) g.items.push(fc);
    else groups.push({ year: y, items: [fc] });
  }

  return (
    <div>
      <div className="flex gap-1.5 overflow-x-auto snap-x pb-1 -mx-1 px-1"
        style={{ overscrollBehaviorX: "contain" }}>
        {today.map(chip)}
        {groups.map(g => (
          <div key={g.year} className="flex items-stretch gap-1.5 shrink-0">
            <div className="flex items-center px-1 shrink-0">
              <span className="text-[9px] tracking-widest text-[var(--color-text-muted)]"
                style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}>
                {g.year}
              </span>
            </div>
            {g.items.map(chip)}
          </div>
        ))}
        {long.length > 0 && (
          <div className="flex items-stretch gap-1.5 shrink-0 pl-1.5 ml-0.5 border-l" style={{ borderColor: "var(--color-navy-700)" }}>
            {long.map(chip)}
          </div>
        )}
      </div>
      <p className="text-[10px] text-[var(--color-text-muted)] mt-1">
        {ko
          ? `FOMC ${fomc.length}회(3년 내, 결정일 기준) + 5·10·30년 뒤 회의 · 숫자는 현재 기준금리 대비 누적 bps`
          : `${fomc.length} FOMC meetings within 3 years (by decision date) + the meetings 5 / 10 / 30 years out · numbers are cumulative bps vs today's rate`}
      </p>
    </div>
  );
}
