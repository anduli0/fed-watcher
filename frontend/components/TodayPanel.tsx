"use client";
import { useEffect, useState } from "react";
import api, { AllHorizons, Horizon, HORIZONS } from "@/lib/api";
import { useLang } from "@/context/LanguageContext";
import { useLatestBriefing } from "@/hooks/useBriefing";
import { Tab } from "@/components/TabNav";
import MacroIndicators from "@/components/MacroIndicators";

interface TodayData {
  date_kst: string;
  time_kst: string;
  weekday_kst: number;
  event: { label: string } | null;
  schedule_kst: { forecast_cycles: string[]; daily_briefing: string; data_collection: string };
  latest_run: {
    id: number; status: string; cycle_type: string;
    started_at: string | null; completed_at: string | null;
  } | null;
}

const SIG_COLOR: Record<string, string> = {
  hawkish: "var(--color-signal-red)",
  neutral: "var(--color-gold)",
  dovish: "var(--color-signal-green)",
};

const WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"];
const WEEKDAYS_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function nextCycleTime(cycles: string[], nowHHMM: string): string {
  const upcoming = cycles.filter(c => c > nowHHMM).sort();
  return upcoming[0] ?? cycles.slice().sort()[0];
}

export default function TodayPanel({
  horizons, onNavigate,
}: { horizons: AllHorizons | null; onNavigate: (t: Tab) => void }) {
  const { lang, T } = useLang();
  const ko = lang === "ko";
  const [today, setToday] = useState<TodayData | null>(null);
  const { briefing } = useLatestBriefing(lang);

  useEffect(() => {
    api.get<TodayData>("/api/today").then(r => setToday(r.data)).catch(() => {});
  }, []);

  const anchor = horizons?.["12m"] ?? horizons?.["6m"];
  const weekday = today
    ? (ko ? WEEKDAYS_KO[today.weekday_kst] : WEEKDAYS_EN[today.weekday_kst])
    : "";

  return (
    <div className="space-y-4 pb-8 animate-fade-in">
      {/* Date + event header */}
      <div className="card flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <p className="text-[11px] text-[var(--color-gold)] uppercase tracking-[0.25em]">
            {ko ? "연준은 어디로 가는가 — 한눈에" : "Where Is The Fed Headed — At a Glance"}
          </p>
          <p className="text-2xl font-light mt-1">
            {today ? `${today.date_kst} (${weekday})` : "…"}
            <span className="text-sm text-[var(--color-text-muted)] ml-2">
              {today ? `${today.time_kst} KST` : ""}
            </span>
          </p>
        </div>
        <div className="text-left sm:text-right">
          {today?.event ? (
            <span className="text-sm px-3 py-2 rounded-lg font-medium inline-block"
              style={{ background: "rgba(201,168,76,0.15)", color: "var(--color-gold)" }}>
              ⚠ {today.event.label}
            </span>
          ) : (
            <span className="text-xs text-[var(--color-text-muted)]">
              {ko ? "오늘 주요 지표 발표 없음" : "No material releases today"}
            </span>
          )}
        </div>
      </div>

      {/* Rate-path curve — 6 horizons, big */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-[11px] text-[var(--color-gold)] uppercase tracking-[0.25em]">
              {ko ? "오늘의 금리 경로" : "Today's Rate Path"}
            </p>
            <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
              {ko ? "현재 기준금리 대비 전망 — 오늘·3개월·6개월·1년·3년·10년"
                  : "Forecast vs current Fed Funds — today · 3M · 6M · 1Y · 3Y · 10Y"}
            </p>
          </div>
          <button onClick={() => onNavigate("forecast")}
            className="text-xs text-[var(--color-gold)] hover:underline shrink-0">
            {ko ? "상세 보기 →" : "Details →"}
          </button>
        </div>
        {anchor ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
            {HORIZONS.map((h: Horizon) => (
              <HorizonCard key={h} h={h} fc={horizons?.[h] ?? null} label={T.horizonTabs[h]} ko={ko} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-muted)]">
            {ko ? "오늘의 금리 경로 불러오는 중…" : "Loading today's rate path…"}
          </p>
        )}
        <p className="text-[10px] text-[var(--color-text-muted)] mt-3">
          {ko ? "큰 숫자 = 예상 기준금리 수준(현재 기준금리 + 전망 변화). ‘오늘’은 현행 금리 기준점입니다."
              : "Large figure = implied policy-rate level (current Fed Funds + forecast Δ). ‘Today’ is the current-rate anchor."}
        </p>
      </div>

      {/* Macro indicators — schedule + values */}
      <MacroIndicators />

      {/* Today's briefing (compact) */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <p className="text-[11px] text-[var(--color-text-muted)] uppercase tracking-widest">
            {ko ? "오늘의 브리핑" : "Today's Briefing"}
          </p>
          <button onClick={() => onNavigate("briefing")}
            className="text-xs text-[var(--color-gold)] hover:underline">
            {ko ? "전체 읽기 →" : "Read full →"}
          </button>
        </div>
        {briefing ? (
          <div>
            <p className="text-sm font-medium mb-1">{briefing.title}</p>
            {briefing.market_impact_headline && (
              <p className="text-xs text-[var(--color-gold)] mb-2">{briefing.market_impact_headline}</p>
            )}
            <ul className="space-y-1.5">
              {(briefing.executive_summary ?? []).slice(0, 3).map((s, i) => (
                <li key={i} className="text-xs text-[var(--color-text-muted)] leading-relaxed flex gap-2">
                  <span className="text-[var(--color-gold)] shrink-0">•</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-muted)]">
            {ko ? "오늘 브리핑이 아직 생성되지 않았습니다 (매일 07:30 KST 발행)." : "Today's briefing is not out yet (published daily at 07:30 KST)."}
          </p>
        )}
      </div>

      {/* Schedule + latest run */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="card">
          <p className="text-[11px] text-[var(--color-text-muted)] uppercase tracking-widest mb-3">
            {ko ? "자동 실행 일정 (KST)" : "Automation Schedule (KST)"}
          </p>
          {today && (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">{ko ? "다음 예측 사이클" : "Next forecast cycle"}</span>
                <span className="font-medium" style={{ color: "var(--color-gold)" }}>
                  {nextCycleTime(today.schedule_kst.forecast_cycles, today.time_kst)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">{ko ? "예측 사이클" : "Forecast cycles"}</span>
                <span className="text-xs">{today.schedule_kst.forecast_cycles.join(" · ")}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">{ko ? "데일리 브리핑" : "Daily briefing"}</span>
                <span>{today.schedule_kst.daily_briefing}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">{ko ? "데이터 수집" : "Data collection"}</span>
                <span className="text-xs">{ko ? "30분마다" : today.schedule_kst.data_collection}</span>
              </div>
            </div>
          )}
        </div>
        <div className="card">
          <p className="text-[11px] text-[var(--color-text-muted)] uppercase tracking-widest mb-3">
            {ko ? "최근 사이클" : "Latest Cycle"}
          </p>
          {today?.latest_run ? (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">{ko ? "상태" : "Status"}</span>
                <span className="font-medium" style={{
                  color: today.latest_run.status === "completed"
                    ? "var(--color-signal-green)"
                    : today.latest_run.status === "running" ? "var(--color-gold)" : "var(--color-signal-red)",
                }}>
                  {today.latest_run.status === "completed" ? (ko ? "완료" : "Completed")
                    : today.latest_run.status === "running" ? (ko ? "실행 중" : "Running")
                    : (ko ? "실패" : "Failed")}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">{ko ? "유형" : "Type"}</span>
                <span className="text-xs">{today.latest_run.cycle_type}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">{ko ? "시작" : "Started"}</span>
                <span className="text-xs">{today.latest_run.started_at?.replace("T", " ").slice(0, 16) ?? "—"}</span>
              </div>
              <button onClick={() => onNavigate("live")}
                className="text-xs text-[var(--color-gold)] hover:underline mt-1">
                {ko ? "실시간 활동 보기 →" : "Watch live →"}
              </button>
            </div>
          ) : (
            <p className="text-sm text-[var(--color-text-muted)]">
              {ko ? "아직 실행 기록이 없습니다." : "No runs yet."}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function HorizonCard({ h, fc, label, ko }: {
  h: Horizon;
  fc: AllHorizons[Horizon];
  label: string;
  ko: boolean;
}) {
  const isToday = h === "today";
  const signal = fc?.signal ?? "neutral";
  const color = SIG_COLOR[signal];
  const delta = fc?.published_delta_bps ?? 0;
  const level = fc?.implied_rate_pct;
  const conf = fc?.confidence ?? 0;
  const primary = h === "12m";

  return (
    <div className="rounded-lg p-3.5 flex flex-col"
      style={{
        background: "var(--color-navy)",
        border: `1px solid ${primary ? "var(--color-gold)" : "var(--color-navy-700)"}`,
        boxShadow: primary ? "0 0 0 1px rgba(201,168,76,0.25)" : "none",
        opacity: fc ? 1 : 0.5,
      }}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">{label}</span>
        {primary && (
          <span className="text-[8px] px-1 py-0.5 rounded font-bold"
            style={{ background: "rgba(201,168,76,0.15)", color: "var(--color-gold)" }}>
            {ko ? "핵심" : "KEY"}
          </span>
        )}
      </div>

      {/* implied rate level — the big, tangible number */}
      <p className="text-2xl font-light leading-none" style={{ color: isToday ? "var(--color-text-primary)" : color }}>
        {level != null ? `${level.toFixed(2)}%` : (delta > 0 ? "+" : "") + delta.toFixed(0)}
      </p>

      {/* delta + signal */}
      <p className="text-[11px] font-medium mt-1" style={{ color: isToday ? "var(--color-text-muted)" : color }}>
        {isToday
          ? (ko ? "현행 유지" : "current")
          : `${delta > 0 ? "+" : ""}${delta.toFixed(0)} bps · ${
              signal === "hawkish" ? (ko ? "매파" : "HAWK")
              : signal === "dovish" ? (ko ? "비둘기" : "DOVE")
              : (ko ? "중립" : "NEUT")}`}
      </p>

      {/* confidence */}
      <div className="mt-auto pt-2.5">
        <div className="h-1 bg-[var(--color-navy-700)] rounded-full overflow-hidden">
          <div className="h-full rounded-full" style={{
            width: `${conf * 100}%`,
            background: conf >= 0.65 ? "var(--color-signal-green)" : conf >= 0.4 ? "var(--color-gold)" : "var(--color-slate-400)",
          }} />
        </div>
        <p className="text-[9px] text-[var(--color-text-muted)] mt-1">
          {ko ? "신뢰도" : "conf"} {(conf * 100).toFixed(0)}%
        </p>
      </div>
    </div>
  );
}
