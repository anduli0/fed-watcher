"use client";
import { useEffect, useState } from "react";
import api, { AllHorizons, Horizon, HORIZONS } from "@/lib/api";
import { useLang } from "@/context/LanguageContext";
import { useLatestBriefing } from "@/hooks/useBriefing";
import { Tab } from "@/components/TabNav";

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
  const { lang } = useLang();
  const ko = lang === "ko";
  const [today, setToday] = useState<TodayData | null>(null);
  const { briefing } = useLatestBriefing(lang);

  useEffect(() => {
    api.get<TodayData>("/api/today").then(r => setToday(r.data)).catch(() => {});
  }, []);

  const fc12 = horizons?.["12m"];
  const weekday = today
    ? (ko ? WEEKDAYS_KO[today.weekday_kst] : WEEKDAYS_EN[today.weekday_kst])
    : "";

  return (
    <div className="space-y-4 pb-8">
      {/* Date + event header */}
      <div className="card flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest">
            {ko ? "연준은 어디로 가는가 — 한눈에" : "Where Is The Fed Headed — At a Glance"}
          </p>
          <p className="text-xl font-light mt-0.5">
            {today ? `${today.date_kst} (${weekday})` : "…"}
            <span className="text-sm text-[var(--color-text-muted)] ml-2">
              {today ? `${today.time_kst} KST` : ""}
            </span>
          </p>
        </div>
        <div className="text-left sm:text-right">
          {today?.event ? (
            <span className="text-xs px-2.5 py-1.5 rounded font-medium"
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

      {/* Horizon summary chips */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest">
            {ko ? "오늘의 금리 경로 콜" : "Today's Rate Path Call"}
          </p>
          <button onClick={() => onNavigate("forecast")}
            className="text-xs text-[var(--color-gold)] hover:underline">
            {ko ? "상세 보기 →" : "Details →"}
          </button>
        </div>
        {fc12 ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {HORIZONS.map((h: Horizon) => {
              const f = horizons?.[h];
              if (!f) return (
                <div key={h} className="rounded p-3" style={{ background: "var(--color-navy)" }}>
                  <p className="text-[10px] text-[var(--color-text-muted)] uppercase">{h}</p>
                  <p className="text-sm text-[var(--color-text-muted)] mt-1">—</p>
                </div>
              );
              return (
                <div key={h} className="rounded p-3" style={{ background: "var(--color-navy)" }}>
                  <p className="text-[10px] text-[var(--color-text-muted)] uppercase">{h}</p>
                  <p className="text-lg font-light mt-0.5" style={{ color: SIG_COLOR[f.signal] }}>
                    {f.published_delta_bps > 0 ? "+" : ""}{Math.round(f.published_delta_bps)} bps
                  </p>
                  <p className="text-[10px] mt-0.5" style={{ color: SIG_COLOR[f.signal] }}>
                    {f.signal.toUpperCase()} · {Math.round((f.confidence ?? 0) * 100)}%
                  </p>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-muted)]">
            {ko ? "오늘의 금리 경로 불러오는 중…" : "Loading today's rate path…"}
          </p>
        )}
      </div>

      {/* Today's briefing (compact) */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest">
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
          <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest mb-3">
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
          <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest mb-3">
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
