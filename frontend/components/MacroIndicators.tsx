"use client";
import { useEffect, useState } from "react";
import api, { MacroIndicators as MacroData, MacroIndicator } from "@/lib/api";
import { useLang } from "@/context/LanguageContext";

const CAT_ORDER = ["policy", "inflation", "labor", "growth", "expectations"] as const;

function daysUntil(dateStr: string | null): number | null {
  if (!dateStr) return null;
  const now = new Date();
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  const [y, m, d] = dateStr.split("-").map(Number);
  if (!y) return null;
  return Math.round((Date.UTC(y, m - 1, d) - today) / 86400000);
}

export default function MacroIndicators() {
  const { T, lang } = useLang();
  const ko = lang === "ko";
  const [data, setData] = useState<MacroData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<MacroData>("/api/macro/indicators")
      .then(r => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  const byCat = (c: string) => (data?.indicators ?? []).filter(i => i.category === c);

  return (
    <div className="card">
      <div className="flex items-start justify-between gap-3 mb-4 flex-wrap">
        <div>
          <p className="text-[11px] uppercase tracking-[0.25em] text-[var(--color-gold)] mb-1">
            {T.macroCalTitle}
          </p>
          <p className="text-sm text-[var(--color-text-muted)]">{T.macroCalSub}</p>
        </div>
        {data?.as_of && (
          <span className="text-[10px] text-[var(--color-text-muted)]" suppressHydrationWarning>
            {T.macroReleased} {data.as_of}
          </span>
        )}
      </div>

      {loading ? (
        <div className="h-32 flex items-center justify-center">
          <p className="text-sm text-[var(--color-text-muted)] animate-pulse">{T.loadingChart}</p>
        </div>
      ) : !data || data.indicators.length === 0 ? (
        <p className="text-sm text-[var(--color-text-muted)]">{T.noChartData}</p>
      ) : (
        <div className="space-y-5">
          {CAT_ORDER.map(cat => {
            const items = byCat(cat);
            if (!items.length) return null;
            return (
              <div key={cat}>
                <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-2">
                  {T.macroCat[cat]}
                </p>
                <div className="grid sm:grid-cols-2 gap-2.5">
                  {items.map(i => <IndicatorCard key={i.key} i={i} ko={ko} T={T} />)}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <p className="text-[10px] text-[var(--color-text-muted)] leading-relaxed mt-4 pt-3 border-t"
        style={{ borderColor: "var(--color-navy-700)" }}>
        {T.macroNote}
      </p>
    </div>
  );
}

function IndicatorCard({ i, ko, T }: { i: MacroIndicator; ko: boolean; T: ReturnType<typeof useLang>["T"] }) {
  const name = ko ? i.name_ko : i.name_en;
  const d = daysUntil(i.next_release);
  const up = i.change != null && i.change > 0;
  const down = i.change != null && i.change < 0;
  const arrow = up ? "▲" : down ? "▼" : "±";
  // Neutral palette — up=gold, down=slate — so we don't imply "good/bad" (higher
  // inflation and higher unemployment pull opposite ways for the Fed).
  const changeColor = up ? "var(--color-gold)" : down ? "var(--color-slate-300)" : "var(--color-text-muted)";

  return (
    <div className="rounded-lg p-3.5" style={{ background: "var(--color-navy)", border: "1px solid var(--color-navy-700)" }}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <p className="text-sm font-semibold text-[var(--color-text-primary)] truncate">{name}</p>
            {i.impact === "high" && (
              <span className="text-[8px] px-1 py-0.5 rounded shrink-0"
                style={{ background: "rgba(201,168,76,0.15)", color: "var(--color-gold)" }}>
                {ko ? "★" : "★"}
              </span>
            )}
          </div>
          <p className="text-[10px] text-[var(--color-text-muted)] mt-0.5 leading-snug">{i.meaning_ko && ko ? i.meaning_ko : i.series_id}</p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-xl font-light leading-none text-[var(--color-text-primary)]">
            {i.latest_display ?? "—"}
          </p>
          {i.prior_display && (
            <p className="text-[10px] mt-1" style={{ color: changeColor }}>
              {arrow} <span className="text-[var(--color-text-muted)]">{T.macroPrior} {i.prior_display}</span>
            </p>
          )}
        </div>
      </div>
      <div className="flex items-center justify-between mt-2.5 pt-2 border-t" style={{ borderColor: "var(--color-navy-700)" }}>
        <span className="text-[10px] text-[var(--color-text-muted)]">
          {i.latest_date ? `${T.macroReleased} ${i.latest_date}` : ""}
        </span>
        {i.next_release ? (
          <span className="text-[10px] px-1.5 py-0.5 rounded font-medium"
            style={{ background: "rgba(56,161,105,0.10)", color: "var(--color-signal-green)" }}>
            {T.macroNext} {i.next_release}{d != null && d >= 0 ? ` · D-${d}` : ""}
          </span>
        ) : (
          <span className="text-[10px] text-[var(--color-text-muted)]">{T.macroTBD}</span>
        )}
      </div>
    </div>
  );
}
