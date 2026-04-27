"use client";
import { AllHorizons, ForecastHistoryItem, Horizon, HORIZONS, HorizonForecast } from "@/lib/api";
import { useLang } from "@/context/LanguageContext";
import ForecastHistory from "./ForecastHistory";

interface Props {
  horizons: AllHorizons | null;
  history: ForecastHistoryItem[];
  activeHorizon: Horizon;
  onHorizonChange: (h: Horizon) => void;
}

export default function ForecastBanner({ horizons, history, activeHorizon: active, onHorizonChange: setActive }: Props) {
  const { T, lang } = useLang();

  const fc: HorizonForecast | null = horizons?.[active] ?? null;

  if (!fc) {
    return (
      <div className="card">
        <HorizonTabs active={active} onChange={setActive} availability={horizons} />
        <p className="text-[var(--color-text-muted)] text-sm mt-4">{T.noForecast}</p>
      </div>
    );
  }

  const { published_delta_bps: delta, confidence, signal, unchanged_streak_days, change_justification, trigger_event, published_at } = fc;
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
      <HorizonTabs active={active} onChange={setActive} availability={horizons} />

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
            {T.horizonLabels[active]}
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


function HorizonTabs({
  active, onChange, availability,
}: {
  active: Horizon;
  onChange: (h: Horizon) => void;
  availability: AllHorizons | null;
}) {
  const { T } = useLang();
  return (
    <div className="flex gap-1 flex-wrap">
      {HORIZONS.map(h => {
        const isActive = active === h;
        const has = availability?.[h] != null;
        const fc = availability?.[h];
        const delta = fc?.published_delta_bps ?? 0;
        return (
          <button
            key={h}
            onClick={() => onChange(h)}
            className="text-xs px-3 py-1.5 rounded-md transition-all flex items-center gap-2"
            style={{
              background: isActive ? "var(--color-navy-700)" : "transparent",
              color: isActive ? "var(--color-text-primary)" : "var(--color-text-muted)",
              border: `1px solid ${isActive ? "var(--color-gold)" : "var(--color-navy-700)"}`,
              opacity: has ? 1 : 0.55,
            }}
          >
            <span className="font-medium">{T.horizonTabs[h]}</span>
            {has && (
              <span className="text-[10px]"
                style={{
                  color: delta < 0 ? "var(--color-signal-green)" : delta > 0 ? "var(--color-signal-red)" : "var(--color-gold)",
                }}>
                {delta > 0 ? "+" : ""}{delta.toFixed(0)}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
