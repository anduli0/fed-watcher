"use client";
import { useState, useEffect, useRef } from "react";
import TabNav, { Tab } from "@/components/TabNav";
import ForecastBanner from "@/components/ForecastBanner";
import AgentStatusGrid from "@/components/AgentStatusGrid";
import AgentActivityHero from "@/components/AgentActivityHero";
import AnalysisMethodPanel from "@/components/AnalysisMethodPanel";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import ForecastReport from "@/components/ForecastReport";
import MacroDataPanel from "@/components/MacroDataPanel";
import MultiHorizonGauges from "@/components/MultiHorizonGauges";
import DailyBriefingPage from "@/components/DailyBriefingPage";
import TodayPanel from "@/components/TodayPanel";
import TrackRecordPanel from "@/components/TrackRecordPanel";
import TradingPanel from "@/components/TradingPanel";
import { useForecast } from "@/hooks/useForecast";
import { useLang } from "@/context/LanguageContext";
import { Horizon } from "@/lib/api";
import api from "@/lib/api";

export default function DashboardPage() {
  const { horizons, history, agents, report, loading, lastRefresh, refresh } = useForecast();
  const { T, lang } = useLang();
  const [tab, setTab] = useState<Tab>("today");
  const [activeHorizon, setActiveHorizon] = useState<Horizon>("12m");
  const [timeStr, setTimeStr] = useState("");
  const [yr, setYr] = useState(2026);
  const [triggering, setTriggering] = useState(false);
  const [triggerMsg, setTriggerMsg] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setTimeStr(lastRefresh.toLocaleTimeString("ko-KR", { timeZone: "Asia/Seoul" }) + " KST");
  }, [lastRefresh]);

  useEffect(() => { setYr(new Date().getFullYear()); }, []);

  async function runCycle() {
    setTriggering(true);
    setTriggerMsg("");
    try {
      await api.post("/api/trigger-cycle");
      setTriggerMsg(T.cycleRunning);
      let attempts = 0;
      const prevDelta = horizons?.["12m"]?.published_delta_bps;
      pollRef.current = setInterval(async () => {
        attempts++;
        await refresh();
        const newDelta = horizons?.["12m"]?.published_delta_bps;
        if (newDelta !== prevDelta || attempts >= 18) {
          clearInterval(pollRef.current!);
          pollRef.current = null;
          setTriggerMsg("");
        }
      }, 10000);
    } catch {
      setTriggerMsg(T.triggerFailed);
    } finally {
      setTriggering(false);
    }
  }

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const has12m = horizons?.["12m"] != null;
  const noForecast = !loading && !has12m;
  const noAgents = !loading && agents.length === 0;
  const fc12m = horizons?.["12m"];

  return (
    <main className="min-h-screen flex flex-col">
      <div className="flex-1 max-w-6xl mx-auto w-full px-4 md:px-8">

        {/* ── Header ── */}
        <div className="flex items-center justify-between py-3 sm:py-5 flex-wrap gap-2 sm:gap-3">
          <button
            onClick={() => { setTab("live"); setActiveHorizon("12m"); }}
            className="text-left group"
          >
            <h1 className="text-lg sm:text-xl font-semibold tracking-tight text-[var(--color-text-primary)] group-hover:text-[var(--color-gold)] transition-colors">
              {T.title}
            </h1>
            <p className="text-xs text-[var(--color-text-muted)] mt-0.5 hidden sm:block">{T.subtitle}</p>
          </button>
          <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap justify-end">
            <span className="hidden sm:inline text-xs text-[var(--color-text-muted)]">{timeStr}</span>
            <button onClick={runCycle} disabled={triggering}
              className="text-xs px-2.5 sm:px-3 py-1.5 rounded font-medium transition-colors disabled:opacity-50"
              style={{ background: "var(--color-gold)", color: "var(--color-navy)" }}>
              {triggering ? T.running : T.runCycle}
            </button>
            <button onClick={refresh}
              className="text-xs px-2.5 sm:px-3 py-1.5 rounded border border-[var(--color-navy-700)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors">
              {T.refresh}
            </button>
            <a href="/login"
              className="hidden sm:inline-flex text-xs px-3 py-1.5 rounded border border-[var(--color-navy-700)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors">
              {T.admin}
            </a>
            <LanguageSwitcher />
          </div>
        </div>

        {/* ── Tab Navigation ── */}
        <TabNav active={tab} onChange={setTab} />

        {/* ── First cycle banner ── */}
        {(noForecast || noAgents) && (
          <div className="card mb-4" style={{ borderColor: "rgba(201,168,76,0.3)" }}>
            <p className="text-sm text-[var(--color-gold)] font-medium mb-1">{T.firstCycleTitle}</p>
            <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">{T.firstCycleDesc}</p>
            {triggerMsg && <p className="text-xs text-[var(--color-signal-green)] mt-2">{triggerMsg}</p>}
          </div>
        )}

        {/* ── Tab: Today ── */}
        {tab === "today" && (
          <TodayPanel horizons={horizons} onNavigate={setTab} />
        )}

        {/* ── Tab: Live ── */}
        {tab === "live" && (
          <div className="space-y-4 pb-8">
            <AgentActivityHero liveTab />
          </div>
        )}

        {/* ── Tab: Forecast ── */}
        {tab === "forecast" && (
          <div className="pb-8">
            {loading ? (
              <div className="flex items-center justify-center h-48">
                <p className="text-[var(--color-text-muted)] text-sm animate-pulse">Connecting…</p>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Forecast banner + policy stance gauge — share the same active horizon */}
                <ForecastBanner
                  horizons={horizons}
                  history={history}
                  activeHorizon={activeHorizon}
                  onHorizonChange={setActiveHorizon}
                />
                <MultiHorizonGauges
                  horizons={horizons}
                  activeHorizon={activeHorizon}
                  onHorizonChange={setActiveHorizon}
                />

                {/* Derivation report */}
                <ForecastReport report={report} />
              </div>
            )}
          </div>
        )}

        {/* ── Tab: Agents ── */}
        {tab === "agents" && (
          <div className="pb-8">
            {loading ? (
              <div className="flex items-center justify-center h-48">
                <p className="text-[var(--color-text-muted)] text-sm animate-pulse">Loading…</p>
              </div>
            ) : (
              <AgentStatusGrid agents={agents} />
            )}
          </div>
        )}

        {/* ── Tab: Analysis ── */}
        {tab === "analysis" && (
          <div className="pb-8">
            <AnalysisMethodPanel />
          </div>
        )}

        {/* ── Tab: Data ── */}
        {tab === "data" && (
          <div className="pb-8">
            <MacroDataPanel />
          </div>
        )}

        {/* ── Tab: Daily Brief ── */}
        {tab === "briefing" && (
          <DailyBriefingPage />
        )}

        {/* ── Tab: Track Record ── */}
        {tab === "track" && (
          <TrackRecordPanel />
        )}

        {/* ── Tab: Trading ── */}
        {tab === "trading" && (
          <TradingPanel />
        )}
      </div>

      {/* ── Footer ── */}
      <footer className="mt-auto border-t" style={{ borderColor: "var(--color-navy-700)", background: "linear-gradient(180deg, transparent 0%, rgba(13,31,60,0.5) 100%)" }}>
        <div className="max-w-6xl mx-auto px-4 md:px-8 py-6">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div>
              <p className="text-xs font-bold tracking-[0.25em] text-[var(--color-gold)] mb-1">FED-WATCHER</p>
              <p className="text-xs text-[var(--color-text-muted)]">
                {lang === "en"
                  ? "Macroeconomic Rate Path Intelligence · 21-Agent Architecture"
                  : "거시경제 금리 경로 분석 · 21에이전트 아키텍처"}
              </p>
            </div>
            <div className="text-left md:text-right">
              <p className="text-[10px] uppercase tracking-[0.25em] text-[var(--color-text-muted)] mb-1">
                {lang === "en" ? "Designed, owned and operated by" : "설계 · 소유 · 운영"}
              </p>
              <p className="text-base font-semibold tracking-wide text-[var(--color-text-primary)]">
                Minkyu An <span className="text-[var(--color-text-muted)] font-normal">· 안민규</span>
              </p>
              <p className="text-[10px] text-[var(--color-text-muted)] mt-0.5" suppressHydrationWarning>
                © {yr} Minkyu An. {lang === "en" ? "All rights reserved." : "모든 권리 보유."}
              </p>
              <p className="text-[10px] text-[var(--color-text-muted)]">
                {lang === "en"
                  ? "Proprietary & Confidential · Unauthorized reproduction prohibited"
                  : "대외비 · 무단 복제 및 재배포 금지"}
              </p>
            </div>
          </div>
          {/* Disclaimer */}
          <div className="mt-4 pt-4 border-t" style={{ borderColor: "var(--color-navy-700)" }}>
            <p className="text-[10px] text-[var(--color-text-muted)] leading-relaxed mb-3">
              {lang === "en"
                ? "⚠ Disclaimer: All forecasts are AI-generated predictions based on publicly available data and are for informational purposes only. Predictions may be inaccurate and should not be construed as financial advice. The owner assumes no liability for any losses or decisions made based on this information."
                : "⚠ 면책 고지: 본 서비스의 모든 예측은 공개 데이터를 기반으로 AI가 생성한 참고용 정보이며, 투자 조언이 아닙니다. 예측의 정확성을 보장하지 않으며, 본 정보를 이용하여 발생한 손실 또는 결과에 대해 운영자는 어떠한 법적 책임도 지지 않습니다."}
            </p>
            <div className="flex items-center justify-between text-[9px] tracking-[0.3em] uppercase">
              <span className="text-[var(--color-text-muted)]" suppressHydrationWarning>
                ID-{yr}-MA-FW-21A
              </span>
              <span className="text-[var(--color-text-muted)]">
                Hardware-locked · IP-restricted · MAC-bound
              </span>
            </div>
          </div>
        </div>
      </footer>
    </main>
  );
}
