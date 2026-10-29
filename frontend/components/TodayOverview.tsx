"use client";
import { useMemo } from "react";
import {
  AllHorizons, ForecastHistoryItem, AgentStatus,
} from "@/lib/api";
import { primaryOf, highlightItems, shortLabel } from "@/lib/horizons";
import { useLang } from "@/context/LanguageContext";
import { useLatestBriefing } from "@/hooks/useBriefing";
import type { Tab } from "./TabNav";

interface Props {
  horizons: AllHorizons | null;
  history: ForecastHistoryItem[];
  agents: AgentStatus[];
  report: string;
  loading: boolean;
  error: string | null;
  lastRefresh: Date;
  onRunCycle: () => void;
  triggering: boolean;
  triggerMsg: string;
  onOpenTab: (t: Tab) => void;
}

const SIGNAL_COLOR: Record<string, string> = {
  hawkish: "var(--color-signal-red)",
  dovish: "var(--color-signal-green)",
  neutral: "var(--color-gold)",
};

function todayKST(): string {
  // YYYY-MM-DD in Asia/Seoul — matches backend target_date labelling.
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());
}

export default function TodayOverview({
  horizons, history, agents, report, loading, error,
  onRunCycle, triggering, triggerMsg, onOpenTab,
}: Props) {
  const { T, lang } = useLang();
  const { briefing } = useLatestBriefing(lang);

  const fc12 = primaryOf(horizons);
  const hasData = fc12 != null;

  // ── derived: change vs yesterday (12m) ──
  const vsYesterday = useMemo(() => {
    if (history.length < 2) return null;
    const [latest, prev] = history;
    return latest.published_delta_bps - prev.published_delta_bps;
  }, [history]);

  // ── derived: agent consensus split ──
  const consensus = useMemo(() => {
    const c = { hawkish: 0, neutral: 0, dovish: 0 };
    for (const a of agents) {
      if (a.signal === "hawkish") c.hawkish++;
      else if (a.signal === "dovish") c.dovish++;
      else c.neutral++;
    }
    return { ...c, total: agents.length };
  }, [agents]);

  // ── freshness ──
  const asOf = fc12?.published_at ?? null;
  const asOfDateKST = asOf
    ? new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(asOf))
    : null;
  const isFresh = asOfDateKST != null && asOfDateKST === todayKST();

  const sig = (s: string) =>
    s === "hawkish" ? T.hawkish : s === "dovish" ? T.dovish : T.neutral;
  const fmtBps = (d: number) => `${d > 0 ? "+" : d < 0 ? "" : "±"}${d.toFixed(0)}`;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-[var(--color-text-muted)] text-sm animate-pulse">
          {lang === "en" ? "Loading today's rate path…" : "오늘의 금리 경로 불러오는 중…"}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4 pb-8 animate-fade-in">

      {/* ── As-of bar ───────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.25em] text-[var(--color-gold)] mb-1">
            {lang === "en" ? "Today's Rate Path Call" : "오늘의 금리 경로 콜"}
          </p>
          <h2 className="text-xl sm:text-2xl font-semibold text-[var(--color-text-primary)]">
            {lang === "en"
              ? "Where the Fed is headed — at a glance"
              : "연준은 어디로 가는가 — 한눈에"}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          {error ? (
            <span className="inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-full"
              style={{ background: "rgba(229,62,62,0.10)", color: "var(--color-signal-red)", border: "1px solid rgba(229,62,62,0.30)" }}>
              <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: "var(--color-signal-red)" }} />
              {lang === "en" ? "Reconnecting…" : "연결 재시도 중…"}
            </span>
          ) : (
            <span
              className="inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-full"
              style={{
                background: isFresh ? "rgba(56,161,105,0.12)" : "rgba(201,168,76,0.12)",
                color: isFresh ? "var(--color-signal-green)" : "var(--color-gold)",
                border: `1px solid ${isFresh ? "rgba(56,161,105,0.35)" : "rgba(201,168,76,0.35)"}`,
              }}
              suppressHydrationWarning
            >
              <span className="w-1.5 h-1.5 rounded-full"
                style={{ background: isFresh ? "var(--color-signal-green)" : "var(--color-gold)" }} />
              {hasData
                ? (isFresh
                    ? (lang === "en" ? "Updated today" : "오늘 최신")
                    : (lang === "en" ? `As of ${asOfDateKST}` : `${asOfDateKST} 기준`))
                : (lang === "en" ? "Needs first run" : "최초 실행 필요")}
            </span>
          )}
          <button
            onClick={onRunCycle}
            disabled={triggering}
            className="text-[11px] px-3 py-1.5 rounded font-medium transition-colors disabled:opacity-50"
            style={{ background: "var(--color-gold)", color: "var(--color-navy)" }}
          >
            {triggering ? T.running : (lang === "en" ? "Refresh now" : "지금 갱신")}
          </button>
        </div>
      </div>

      {triggerMsg && (
        <p className="text-xs text-[var(--color-signal-green)]">{triggerMsg}</p>
      )}

      {/* ── No-data / stale prompt ──────────────────────────────── */}
      {!hasData && (
        <div className="card" style={{ borderColor: "rgba(201,168,76,0.3)" }}>
          <div className="flex items-center gap-2 mb-1">
            <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: "var(--color-gold)" }} />
            <p className="text-sm text-[var(--color-gold)] font-medium">
              {lang === "en" ? "Preparing today's forecast…" : "오늘의 예측을 준비 중입니다…"}
            </p>
          </div>
          <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">
            {lang === "en"
              ? "On the first launch of the day the server auto-runs all 21 agents (about 1–4 min). This page refreshes by itself — or use Refresh now to trigger it."
              : "그날 처음 켜면 서버가 21개 에이전트를 자동으로 돌립니다 (약 1~4분). 이 화면은 자동으로 갱신되며, 「지금 갱신」으로 즉시 실행할 수도 있습니다."}
          </p>
        </div>
      )}

      {/* ── 4 horizon call cards ────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {highlightItems(horizons).map((fc) => {
          const h = fc.horizon;
          const primary = fc.horizon === horizons?.primary;
          const signal = fc?.signal ?? "neutral";
          const color = SIGNAL_COLOR[signal];
          const delta = fc?.published_delta_bps ?? 0;
          const conf = fc?.confidence ?? 0;
          return (
            <button
              key={h}
              onClick={() => onOpenTab("forecast")}
              className="card text-left transition-all hover:-translate-y-0.5"
              style={{
                padding: "1rem",
                borderColor: primary ? "var(--color-gold)" : "var(--color-navy-700)",
                boxShadow: primary ? "0 0 0 1px rgba(201,168,76,0.25)" : "none",
                opacity: fc ? 1 : 0.5,
              }}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-[var(--color-text-muted)]">
                  {shortLabel(fc, lang)}
                </span>
                {primary && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded font-bold tracking-wider"
                    style={{ background: "rgba(201,168,76,0.15)", color: "var(--color-gold)" }}>
                    {lang === "en" ? "KEY" : "핵심"}
                  </span>
                )}
              </div>

              {fc ? (
                <>
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-2xl sm:text-3xl font-light" style={{ color }}>
                      {fmtBps(delta)}
                    </span>
                    <span className="text-xs text-[var(--color-text-muted)]">bps</span>
                  </div>
                  <p className="text-xs font-semibold mt-0.5" style={{ color }}>
                    {sig(signal)}
                  </p>
                  {/* confidence */}
                  <div className="mt-3">
                    <div className="flex justify-between text-[9px] text-[var(--color-text-muted)] mb-1">
                      <span>{T.confidence}</span>
                      <span>{(conf * 100).toFixed(0)}%</span>
                    </div>
                    <div className="h-1 bg-[var(--color-navy-700)] rounded-full overflow-hidden">
                      <div className="h-full rounded-full"
                        style={{
                          width: `${conf * 100}%`,
                          backgroundColor: conf >= 0.65 ? "var(--color-signal-green)" : conf >= 0.4 ? "var(--color-gold)" : "var(--color-slate-400)",
                        }} />
                    </div>
                  </div>
                  <p className="text-[10px] text-[var(--color-text-muted)] mt-2">
                    {lang === "en"
                      ? `held ${fc.unchanged_streak_days}d`
                      : `${fc.unchanged_streak_days}일 유지`}
                  </p>
                </>
              ) : (
                <p className="text-[var(--color-text-muted)] text-2xl font-light">—</p>
              )}
            </button>
          );
        })}
      </div>

      {/* ── 12m headline strip: vs yesterday + meaning ──────────── */}
      {hasData && (
        <div className="card flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-6">
          <div className="flex-1">
            <p className="text-[11px] uppercase tracking-widest text-[var(--color-text-muted)] mb-1">
              {lang === "en" ? "1-Year View — bottom line" : "1년 전망 — 결론"}
            </p>
            <p className="text-sm text-[var(--color-text-primary)] leading-relaxed">
              {lang === "en"
                ? <>The 1-year rate path is <b style={{ color: SIGNAL_COLOR[fc12!.signal] }}>{sig(fc12!.signal)}</b> at <b>{fmtBps(fc12!.published_delta_bps)} bps</b> versus today&apos;s Fed Funds Rate.</>
                : <>1년 금리 경로는 현재 기준금리 대비 <b>{fmtBps(fc12!.published_delta_bps)} bps</b>, <b style={{ color: SIGNAL_COLOR[fc12!.signal] }}>{sig(fc12!.signal)}</b> 기조입니다.</>}
            </p>
            {fc12!.change_justification && (
              <p className="text-xs text-[var(--color-text-muted)] italic mt-1.5">{fc12!.change_justification}</p>
            )}
          </div>
          <div className="sm:text-right sm:border-l sm:pl-6" style={{ borderColor: "var(--color-navy-700)" }}>
            <p className="text-[11px] uppercase tracking-widest text-[var(--color-text-muted)] mb-1">
              {lang === "en" ? "vs yesterday" : "어제 대비"}
            </p>
            {vsYesterday == null ? (
              <p className="text-lg font-light text-[var(--color-text-muted)]">—</p>
            ) : vsYesterday === 0 ? (
              <p className="text-lg font-light text-[var(--color-gold)]">
                {lang === "en" ? "Unchanged" : "변동 없음"}
              </p>
            ) : (
              <p className="text-2xl font-light"
                style={{ color: vsYesterday > 0 ? "var(--color-signal-red)" : "var(--color-signal-green)" }}>
                {vsYesterday > 0 ? "▲" : "▼"} {Math.abs(vsYesterday).toFixed(0)} bps
              </p>
            )}
          </div>
        </div>
      )}

      {/* ── Agent consensus + Briefing headline (two-up) ────────── */}
      <div className="grid md:grid-cols-2 gap-3">

        {/* Agent consensus */}
        <button
          onClick={() => onOpenTab("agents")}
          className="card text-left transition-all hover:-translate-y-0.5"
        >
          <div className="flex items-center justify-between mb-3">
            <p className="text-[11px] uppercase tracking-widest text-[var(--color-text-muted)]">
              {lang === "en" ? "Agent Consensus" : "에이전트 컨센서스"}
            </p>
            <span className="text-[10px] text-[var(--color-text-muted)]">
              {consensus.total} {lang === "en" ? "agents" : "에이전트"} ›
            </span>
          </div>
          {consensus.total > 0 ? (
            <>
              <div className="flex h-3 rounded-full overflow-hidden bg-[var(--color-navy-700)]">
                {(["hawkish", "neutral", "dovish"] as const).map(k => (
                  consensus[k] > 0 && (
                    <div key={k} style={{
                      width: `${(consensus[k] / consensus.total) * 100}%`,
                      background: SIGNAL_COLOR[k],
                    }} />
                  )
                ))}
              </div>
              <div className="flex justify-between mt-2.5 text-xs">
                <span style={{ color: SIGNAL_COLOR.hawkish }}>● {T.hawkish} {consensus.hawkish}</span>
                <span style={{ color: SIGNAL_COLOR.neutral }}>● {T.neutral} {consensus.neutral}</span>
                <span style={{ color: SIGNAL_COLOR.dovish }}>● {T.dovish} {consensus.dovish}</span>
              </div>
            </>
          ) : (
            <p className="text-sm text-[var(--color-text-muted)]">{T.awaitingCycle}</p>
          )}
        </button>

        {/* Briefing headline */}
        <button
          onClick={() => onOpenTab("briefing")}
          className="card text-left transition-all hover:-translate-y-0.5"
        >
          <div className="flex items-center justify-between mb-2">
            <p className="text-[11px] uppercase tracking-widest text-[var(--color-text-muted)]">
              {lang === "en" ? "Daily Brief" : "오늘의 브리핑"}
            </p>
            <span className="text-[10px] text-[var(--color-text-muted)]">
              {lang === "en" ? "Read full" : "전체 보기"} ›
            </span>
          </div>
          {briefing ? (
            <>
              <p className="text-sm font-semibold text-[var(--color-text-primary)] leading-snug line-clamp-2">
                {briefing.title}
              </p>
              {briefing.market_impact_headline && (
                <p className="text-xs text-[var(--color-text-muted)] mt-1.5 leading-relaxed line-clamp-3">
                  {briefing.market_impact_headline}
                </p>
              )}
              <p className="text-[10px] text-[var(--color-text-muted)] mt-2">{briefing.briefing_date}</p>
            </>
          ) : (
            <p className="text-sm text-[var(--color-text-muted)]">{T.briefingEmpty}</p>
          )}
        </button>
      </div>

      {/* ── Derivation teaser ───────────────────────────────────── */}
      {report && (
        <button
          onClick={() => onOpenTab("forecast")}
          className="card text-left w-full transition-all hover:-translate-y-0.5"
        >
          <p className="text-[11px] uppercase tracking-widest text-[var(--color-text-muted)] mb-1.5">
            {lang === "en" ? "How this was derived" : "도출 근거"}
            <span className="float-right text-[10px] normal-case tracking-normal">
              {lang === "en" ? "Full report" : "전체 리포트"} ›
            </span>
          </p>
          <p className="text-xs text-[var(--color-text-muted)] leading-relaxed line-clamp-3">
            {report.replace(/[#*`>_]/g, "").slice(0, 320)}…
          </p>
        </button>
      )}
    </div>
  );
}
