"use client";
import { useEffect, useState } from "react";
import api, { AllHorizons, HorizonForecast } from "@/lib/api";
import { useLang } from "@/context/LanguageContext";
import RatePathChart from "@/components/RatePathChart";
import { primaryOf, nextMeeting, fomcItems, highlightItems, shortLabel, longLabel, roleTag } from "@/lib/horizons";
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
  const { lang } = useLang();
  const ko = lang === "ko";
  const [today, setToday] = useState<TodayData | null>(null);
  const { briefing } = useLatestBriefing(lang);

  useEffect(() => {
    api.get<TodayData>("/api/today").then(r => setToday(r.data)).catch(() => {});
  }, []);

  const anchor = primaryOf(horizons) ?? nextMeeting(horizons);
  const fomc = fomcItems(horizons);
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

      {/* Rate path — every FOMC meeting in the 3-year window, then 5Y / 10Y / 30Y */}
      <div className="card">
        <div className="flex items-center justify-between mb-2">
          <div>
            <p className="text-[11px] text-[var(--color-gold)] uppercase tracking-[0.25em]">
              {ko ? "오늘의 금리 경로" : "Today's Rate Path"}
            </p>
            <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
              {ko ? `3년 내 모든 FOMC(${fomc.length}회) 회의별 예상 기준금리 — 그다음 5년·10년·30년 뒤 회의`
                  : `Implied policy rate after each of the ${fomc.length} FOMC meetings within 3 years — then 5Y · 10Y · 30Y`}
            </p>
          </div>
          <button onClick={() => onNavigate("forecast")}
            className="text-xs text-[var(--color-gold)] hover:underline shrink-0">
            {ko ? "상세 보기 →" : "Details →"}
          </button>
        </div>
        {anchor ? (
          <>
            <RatePathChart horizons={horizons} />
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5 mt-3">
              {highlightItems(horizons).map(fc => (
                <HorizonCard key={fc.horizon} fc={fc} ko={ko}
                  label={shortLabel(fc, lang)} sub={longLabel(fc, lang)}
                  tag={roleTag(fc, horizons, lang)} primary={fc.horizon === horizons?.primary} />
              ))}
            </div>
          </>
        ) : (
          <p className="text-sm text-[var(--color-text-muted)]">
            {ko ? "오늘의 금리 경로 불러오는 중…" : "Loading today's rate path…"}
          </p>
        )}
        <p className="text-[10px] text-[var(--color-text-muted)] mt-3">
          {ko ? "금색 계단 = 위원회 예상 기준금리(해당 FOMC 직후), 회색 점선 = 시장이 가격에 반영한 경로(국채 선도금리), 음영 = 위원회 밴드. 카드의 확률은 최빈 시나리오(인하/동결/인상)가 맞을 확률입니다."
              : "Gold steps = committee implied policy rate after each FOMC; grey dashed = the path the market prices (Treasury forwards); shading = committee band. Card probability = chance the modal scenario (cut/hold/hike) is right."}
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

function HorizonCard({ fc, label, sub, tag, primary, ko }: {
  fc: HorizonForecast;
  label: string;
  sub: string;
  tag: string | null;
  primary: boolean;
  ko: boolean;
}) {
  const signal = fc.signal ?? "neutral";
  const color = SIG_COLOR[signal];
  const delta = fc.published_delta_bps ?? 0;
  const level = fc.implied_rate_pct;
  const conf = fc.confidence ?? 0;

  return (
    <div className="rounded-lg p-3.5 flex flex-col"
      style={{
        background: "var(--color-navy)",
        border: `1px solid ${primary ? "var(--color-gold)" : "var(--color-navy-700)"}`,
        boxShadow: primary ? "0 0 0 1px rgba(201,168,76,0.25)" : "none",
      }}>
      <div className="flex items-center justify-between mb-1.5 gap-1">
        <span className="text-[11px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wide">{label}</span>
        {tag && (
          <span className="text-[8px] px-1 py-0.5 rounded font-bold truncate"
            style={{ background: "rgba(201,168,76,0.15)", color: "var(--color-gold)" }}>
            {tag}
          </span>
        )}
      </div>

      {/* implied rate level — the big, tangible number */}
      <p className="text-2xl font-light leading-none" style={{ color }}>
        {level != null ? `${level.toFixed(2)}%` : (delta > 0 ? "+" : "") + delta.toFixed(0)}
      </p>

      {/* delta + signal */}
      <p className="text-[11px] font-medium mt-1" style={{ color }}>
        {`${delta > 0 ? "+" : ""}${delta.toFixed(0)} bps · ${
            signal === "hawkish" ? (ko ? "매파" : "HAWK")
            : signal === "dovish" ? (ko ? "비둘기" : "DOVE")
            : (ko ? "중립" : "NEUT")}`}
      </p>
      <p className="text-[9px] text-[var(--color-text-muted)] mt-0.5 truncate" title={sub}>{sub}</p>

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
