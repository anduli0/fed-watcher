"use client";
import { AllHorizons, ForecastHistoryItem, Horizon, HorizonForecast } from "@/lib/api";
import { useLang } from "@/context/LanguageContext";
import ForecastHistory from "./ForecastHistory";
import HorizonSelector from "./HorizonSelector";
import { byKey, longLabel, roleTag, countdown } from "@/lib/horizons";

interface Props {
  horizons: AllHorizons | null;
  history: ForecastHistoryItem[];
  activeHorizon: Horizon;
  onHorizonChange: (h: Horizon) => void;
}

export default function ForecastBanner({ horizons, history, activeHorizon: active, onHorizonChange: setActive }: Props) {
  const { T, lang } = useLang();

  const fc: HorizonForecast | null = byKey(horizons, active);

  if (!fc || fc.kind === "today") {
    return (
      <div className="card">
        <HorizonSelector horizons={horizons} active={active} onChange={setActive} />
        <p className="text-[var(--color-text-muted)] text-sm mt-4">
          {fc?.kind === "today"
            ? (lang === "ko"
                ? `현행 기준금리 ${fc.implied_rate_pct != null ? fc.implied_rate_pct.toFixed(2) + "%" : ""} — 예측 곡선의 기준점입니다. 위에서 FOMC 회의를 선택하세요.`
                : `Current policy rate ${fc.implied_rate_pct != null ? fc.implied_rate_pct.toFixed(2) + "%" : ""} — the anchor of the curve. Pick an FOMC meeting above.`)
            : T.noForecast}
        </p>
      </div>
    );
  }
  const tag = roleTag(fc, horizons, lang);
  const dday = countdown(fc, lang);

  const { published_delta_bps: delta, confidence, signal, unchanged_streak_days, change_justification, trigger_event } = fc;
  const published_at = fc.published_at ?? new Date().toISOString();
  const signalClass = signal === "hawkish" ? "badge-hawkish" : signal === "dovish" ? "badge-dovish" : "badge-neutral";
  const signalLabel = signal === "hawkish" ? T.hawkish : signal === "dovish" ? T.dovish : T.neutral;
  const direction = delta < 0 ? "▼" : delta > 0 ? "▲" : "—";
  const absLabel = `${direction} ${Math.abs(delta).toFixed(0)} bps`;

  const nextUpdate = (() => {
    const d = new Date(published_at);
    d.setDate(d.getDate() + 1);
    d.setHours(8, 0, 0, 0);
    return d.toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Seoul" });
  })();

  const streakLabel = `${unchanged_streak_days} ${unchanged_streak_days === 1 ? T.day : T.days}`;

  return (
    <div className="card space-y-4">
      <HorizonSelector horizons={horizons} active={active} onChange={setActive} />

      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
        <div>
          <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest mb-1">
            {T.forecastLabel}
          </p>
          <div className="flex items-baseline gap-3">
            <span className="text-3xl sm:text-4xl font-light">{absLabel}</span>
            <span className={`text-lg ${signalClass}`}>{signalLabel}</span>
          </div>
          <p className="text-[var(--color-text-muted)] text-sm mt-1">
            {longLabel(fc, lang)}
            {tag && <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(201,168,76,0.15)", color: "var(--color-gold)" }}>{tag}</span>}
            {dday && <span className="ml-2 text-[10px] text-[var(--color-text-muted)]">{dday}</span>}
            {fc.implied_rate_pct != null && (
              <span className="ml-2 text-[11px]">
                {lang === "ko" ? "예상 기준금리" : "implied rate"} <b className="text-[var(--color-text-primary)]">{fc.implied_rate_pct.toFixed(2)}%</b>
              </span>
            )}
          </p>
        </div>
        <div className="text-left sm:text-right">
          <p className="text-xs text-[var(--color-text-muted)]" suppressHydrationWarning>
            {new Date(published_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })} KST
          </p>
          <p className="text-xs text-[var(--color-text-muted)]">{T.nextUpdate}: {nextUpdate} KST</p>
        </div>
      </div>

      <div>
        <div className="flex justify-between text-xs text-[var(--color-text-muted)] mb-1">
          <span>{T.confidence}</span>
          <span>{(confidence * 100).toFixed(0)}%</span>
        </div>
        <div className="h-1.5 bg-[var(--color-navy-700)] rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${confidence * 100}%`,
              backgroundColor: confidence >= 0.7 ? "var(--color-signal-green)" : confidence >= 0.5 ? "var(--color-gold)" : "var(--color-slate-400)",
            }}
          />
        </div>
      </div>

      <div className="flex items-center gap-4 pt-1 border-t border-[var(--color-navy-700)]">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[var(--color-gold)]" />
          <span className="text-xs text-[var(--color-text-muted)]">
            {T.forecastUnchanged}{" "}
            <span className="text-[var(--color-text-primary)] font-medium">{streakLabel}</span>
          </span>
        </div>
        {trigger_event && (
          <span className="text-xs px-2 py-0.5 rounded bg-[var(--color-navy-700)] text-[var(--color-gold)]">
            {trigger_event}
          </span>
        )}
      </div>

      {change_justification && (
        <p className="text-xs text-[var(--color-text-muted)] italic">{change_justification}</p>
      )}

      <ForecastHistory history={history} />
    </div>
  );
}

