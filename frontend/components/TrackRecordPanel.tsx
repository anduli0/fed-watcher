"use client";
import { useEffect, useState } from "react";
import {
  ComposedChart, Line, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";
import api from "@/lib/api";
import { useLang } from "@/context/LanguageContext";

interface TrackRecord {
  records: {
    date: string;
    predicted_bps: number;
    signal: string;
    confidence: number;
    market_move_bps: number | null;
    hit: boolean | null;
    pending: boolean;
  }[];
  stats: {
    total_days: number;
    scored: number;
    hits: number;
    misses: number;
    hit_rate: number | null;
    avg_abs_error_bps: number | null;
    proxy_series: string;
  };
  agent_misses: { agent_id: number; miss_count: number }[];
}

const SIG_COLOR: Record<string, string> = {
  hawkish: "var(--color-signal-red)",
  neutral: "var(--color-gold)",
  dovish: "var(--color-signal-green)",
};

interface AccuracySummary {
  as_of: string;
  matured_count: number;
  matured_hits: number;
  dff_now: number | null;
  dff_realized_move_bps: number | null;
  tracking: {
    horizon: string; predicted_delta_bps: number; signal: string; confidence: number;
    dff_realized_so_far_bps: number | null; elapsed_days: number; window_days: number;
    gradeable_vs_dff: boolean;
  }[];
  maturity_ledger: {
    horizon: string; issued: string; matures_on: string; predicted_delta_bps: number;
    status: string; days_remaining: number; dff_realized_bps?: number; hit?: boolean;
  }[];
}

interface Quality {
  n_cycles: number;
  mean_overall: number | null;
  latest: {
    run_id: number; at: string | null; overall: number | null;
    term_coherence: number | null; calibration: number | null;
    signal_consistency: number | null; consensus: number | null;
    prior_coherence: number | null; critique: string | null;
  } | null;
}

interface Backtest {
  data_range?: { start: string | null; end: string | null; n_decision_months: number };
  headline_excl_zlb?: {
    DFF_6m?: { hit_rate: number | null; hit_rate_directional_only: number | null; n: number };
    DFF_12m?: { hit_rate: number | null; hit_rate_directional_only: number | null; n: number };
  };
  error?: string;
}

function scoreColor(v: number | null | undefined): string {
  if (v == null) return "var(--color-text-muted)";
  if (v >= 0.85) return "var(--color-signal-green)";
  if (v >= 0.7) return "var(--color-gold)";
  return "var(--color-signal-red)";
}

export default function TrackRecordPanel() {
  const { lang } = useLang();
  const ko = lang === "ko";
  const [data, setData] = useState<TrackRecord | null>(null);
  const [acc, setAcc] = useState<AccuracySummary | null>(null);
  const [quality, setQuality] = useState<Quality | null>(null);
  const [backtest, setBacktest] = useState<Backtest | null>(null);
  const [dffSeries, setDffSeries] = useState<{ date: string; value: number }[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([
      api.get<TrackRecord>("/api/track-record").then(r => setData(r.data)),
      api.get<AccuracySummary>("/api/accuracy/summary").then(r => setAcc(r.data)),
      api.get<Quality>("/api/accuracy/quality").then(r => setQuality(r.data)),
      api.get<Backtest>("/api/backtest/skill").then(r => setBacktest(r.data)),
      api.get<{ data: { date: string; value: number }[] }>("/api/macro/series/DFF")
        .then(r => setDffSeries(r.data.data)),
    ]).finally(() => setLoading(false));
  }, []);

  // Chart: actual DFF (solid green) + latest forecast path to maturity (dashed
  // gold, unverified) + past prediction targets as hollow dots at maturity.
  const chartData = (() => {
    if (!dffSeries.length) return [];
    const dffNow = dffSeries[dffSeries.length - 1].value;
    const today = dffSeries[dffSeries.length - 1].date;
    const rows: { date: string; actual?: number; forecast?: number; past?: number }[] =
      dffSeries.slice(-240).map(p => ({ date: p.date, actual: p.value }));
    rows[rows.length - 1].forecast = dffNow;
    const addDays = (d: string, n: number) => {
      const t = new Date(d); t.setDate(t.getDate() + n);
      return t.toISOString().slice(0, 10);
    };
    const windows: Record<string, number> = { "6m": 183, "12m": 365, "3y": 1095, "10y": 3650 };
    for (const t of (acc?.tracking ?? [])) {
      if (t.horizon === "3y" || t.horizon === "10y") continue; // keep chart near-term
      rows.push({
        date: addDays(today, windows[t.horizon] ?? 365),
        forecast: Math.round((dffNow + t.predicted_delta_bps / 100) * 100) / 100,
      });
    }
    for (const e of (acc?.maturity_ledger ?? [])) {
      if (!e.matures_on) continue;
      rows.push({
        date: e.matures_on,
        past: Math.round((dffNow + e.predicted_delta_bps / 100) * 100) / 100,
      });
    }
    return rows.sort((a, b) => a.date.localeCompare(b.date));
  })();

  if (loading) {
    return <div className="flex items-center justify-center h-48">
      <p className="text-[var(--color-text-muted)] text-sm animate-pulse">Loading…</p>
    </div>;
  }

  const stats = data?.stats;
  const records = data?.records ?? [];
  const tracking = acc?.tracking ?? [];
  const ledger = acc?.maturity_ledger ?? [];
  const q = quality?.latest;
  const bt = backtest?.headline_excl_zlb;

  return (
    <div className="space-y-4 pb-8">
      {/* 예측 vs 실제 chart */}
      <div className="card">
        <div className="flex items-center justify-between mb-1">
          <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest">
            {ko ? "예측 vs 실제 · 적중 기록" : "Forecast vs Realized"}
          </p>
          <div className="flex gap-3 text-[9px] text-[var(--color-text-muted)]">
            <span><span style={{ color: "var(--color-signal-green)" }}>━</span> {ko ? "실제 기준금리" : "Actual DFF"}</span>
            <span><span style={{ color: "var(--color-gold)" }}>┅</span> {ko ? "예측 경로" : "Forecast path"}</span>
            <span><span style={{ color: "var(--color-gold)" }}>○</span> {ko ? "과거 예측치" : "Past targets"}</span>
          </div>
        </div>
        <p className="text-[10px] text-[var(--color-text-muted)] mb-2">
          {ko
            ? "지금(최신) 예측이 보는 미래 경로 — 현재 금리에서 만기일 목표까지. 아직 검증 전이라 점선입니다."
            : "The latest call's path from today's rate to its maturity target — dashed because unverified."}
        </p>
        {chartData.length > 0 ? (
          <div style={{ width: "100%", height: 220 }}>
            <ResponsiveContainer>
              <ComposedChart data={chartData} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
                <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#8BA0BC" }}
                  tickFormatter={(d: string) => d.slice(0, 7)} minTickGap={40} />
                <YAxis domain={["auto", "auto"]} tick={{ fontSize: 9, fill: "#8BA0BC" }}
                  tickFormatter={(v: number) => `${v.toFixed(1)}%`} />
                <Tooltip
                  contentStyle={{ background: "#0D1F3C", border: "1px solid #112952", fontSize: 11 }}
                  labelStyle={{ color: "#8BA0BC" }}
                  formatter={(v) => [`${Number(v).toFixed(2)}%`]}
                />
                <Line type="stepAfter" dataKey="actual" stroke="var(--color-signal-green)"
                  strokeWidth={1.8} dot={false} connectNulls name={ko ? "실제" : "Actual"} />
                <Line type="linear" dataKey="forecast" stroke="var(--color-gold)"
                  strokeWidth={1.5} strokeDasharray="5 4" dot={{ r: 3 }} connectNulls
                  name={ko ? "예측" : "Forecast"} />
                <Scatter dataKey="past" fill="transparent" stroke="var(--color-gold)"
                  strokeWidth={1.5} name={ko ? "과거 예측" : "Past"} shape="circle" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="text-sm text-[var(--color-text-muted)]">{ko ? "차트 데이터 로딩 중…" : "Loading chart…"}</p>
        )}
      </div>

      {/* Live maturity tracking — each horizon call vs realized DFF */}
      <div className="card overflow-x-auto">
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest">
            {ko ? "만기 추적 — 예측 vs 실제 정책금리(DFF)" : "Maturity Tracking — Calls vs Realized DFF"}
          </p>
          {acc?.dff_now != null && (
            <span className="text-[10px] text-[var(--color-text-muted)]">DFF {acc.dff_now.toFixed(2)}%</span>
          )}
        </div>
        {tracking.length === 0 ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            {ko ? "첫 예측이 발행되면 만기까지 실측 추적이 시작됩니다." : "Tracking starts when the first forecast publishes."}
          </p>
        ) : (
          <table className="w-full text-sm min-w-[520px]">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] border-b"
                style={{ borderColor: "var(--color-navy-700)" }}>
                <th className="text-left py-2 pr-3">{ko ? "호라이즌" : "Horizon"}</th>
                <th className="text-right py-2 px-3">{ko ? "예측" : "Predicted"}</th>
                <th className="text-right py-2 px-3">{ko ? "현재까지 실측" : "Realized so far"}</th>
                <th className="text-right py-2 pl-3">{ko ? "경과" : "Elapsed"}</th>
              </tr>
            </thead>
            <tbody>
              {tracking.map(t => (
                <tr key={t.horizon} className="border-b" style={{ borderColor: "var(--color-navy-700)" }}>
                  <td className="py-2 pr-3 text-xs font-medium uppercase">{t.horizon}</td>
                  <td className="py-2 px-3 text-right" style={{ color: SIG_COLOR[t.signal] ?? "inherit" }}>
                    {t.predicted_delta_bps > 0 ? "+" : ""}{Math.round(t.predicted_delta_bps)} bps
                  </td>
                  <td className="py-2 px-3 text-right text-xs">
                    {t.dff_realized_so_far_bps != null
                      ? `${t.dff_realized_so_far_bps > 0 ? "+" : ""}${t.dff_realized_so_far_bps} bps`
                      : "—"}
                  </td>
                  <td className="py-2 pl-3 text-right text-[10px] text-[var(--color-text-muted)]">
                    {t.elapsed_days}/{t.window_days}{ko ? "일" : "d"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {ledger.length > 0 && (
          <div className="mt-4">
            <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-widest mb-2">
              {ko ? "만기 원장" : "Maturity Ledger"}
            </p>
            <div className="space-y-1">
              {ledger.slice(0, 8).map((e, i) => (
                <div key={i} className="flex items-center justify-between text-xs py-1 border-b"
                  style={{ borderColor: "var(--color-navy-700)" }}>
                  <span className="uppercase font-medium w-10">{e.horizon}</span>
                  <span className="text-[var(--color-text-muted)]">{e.issued} → {e.matures_on}</span>
                  <span>{e.predicted_delta_bps > 0 ? "+" : ""}{Math.round(e.predicted_delta_bps)}bps</span>
                  {e.status === "matured" ? (
                    e.hit != null ? (
                      <span className="text-[10px] px-2 py-0.5 rounded font-semibold" style={{
                        background: e.hit ? "rgba(56,161,105,0.15)" : "rgba(229,62,62,0.15)",
                        color: e.hit ? "var(--color-signal-green)" : "var(--color-signal-red)",
                      }}>{e.hit ? (ko ? "적중" : "HIT") : (ko ? "빗나감" : "MISS")}</span>
                    ) : <span className="text-[10px] text-[var(--color-text-muted)]">{ko ? "판정불가" : "N/A"}</span>
                  ) : (
                    <span className="text-[10px] px-2 py-0.5 rounded"
                      style={{ background: "rgba(139,160,188,0.15)", color: "var(--color-text-muted)" }}>
                      D-{e.days_remaining}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Process self-review + mechanical backtest */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="card">
          <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest mb-3">
            {ko ? "프로세스 자가평가" : "Process Self-Review"}
          </p>
          {q ? (
            <div>
              <div className="flex items-baseline gap-2 mb-2">
                <span className="text-2xl font-light" style={{ color: scoreColor(q.overall) }}>
                  {q.overall != null ? q.overall.toFixed(3) : "—"}
                </span>
                <span className="text-[10px] text-[var(--color-text-muted)]">
                  {ko ? `평균 ${quality?.mean_overall ?? "—"} · ${quality?.n_cycles}사이클` : `mean ${quality?.mean_overall ?? "—"} · ${quality?.n_cycles} cycles`}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                {([
                  ["term_coherence", ko ? "기간구조 일관성" : "Term coherence"],
                  ["calibration", ko ? "신뢰도 캘리브레이션" : "Calibration"],
                  ["signal_consistency", ko ? "시그널 정합성" : "Signal consistency"],
                  ["consensus", ko ? "에이전트 합의" : "Consensus"],
                  ["prior_coherence", ko ? "직전 대비 안정성" : "Prior coherence"],
                ] as const).map(([k, label]) => (
                  <div key={k} className="flex justify-between">
                    <span className="text-[var(--color-text-muted)]">{label}</span>
                    <span style={{ color: scoreColor(q[k]) }}>{q[k] != null ? q[k]!.toFixed(2) : "—"}</span>
                  </div>
                ))}
              </div>
              {q.critique && (
                <p className="text-[10px] text-[var(--color-gold)] leading-relaxed mt-2">{q.critique}</p>
              )}
            </div>
          ) : (
            <p className="text-sm text-[var(--color-text-muted)]">
              {ko ? "첫 사이클 완료 후 자가평가가 시작됩니다." : "Self-review starts after the first completed cycle."}
            </p>
          )}
        </div>
        <div className="card">
          <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest mb-3">
            {ko ? "기계적 백테스트 (참조 하한선)" : "Mechanical Backtest (reference floor)"}
          </p>
          {bt ? (
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">{ko ? "6M 방향 적중률 (DFF)" : "6M direction hit (DFF)"}</span>
                <span className="font-medium" style={{ color: "var(--color-gold)" }}>
                  {bt.DFF_6m?.hit_rate_directional_only != null ? `${Math.round(bt.DFF_6m.hit_rate_directional_only * 100)}%` : "—"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">{ko ? "12M 방향 적중률 (DFF)" : "12M direction hit (DFF)"}</span>
                <span className="font-medium" style={{ color: "var(--color-gold)" }}>
                  {bt.DFF_12m?.hit_rate_directional_only != null ? `${Math.round(bt.DFF_12m.hit_rate_directional_only * 100)}%` : "—"}
                </span>
              </div>
              <p className="text-[10px] text-[var(--color-text-muted)] leading-relaxed mt-2">
                {ko
                  ? `${backtest?.data_range?.start ?? ""}~${backtest?.data_range?.end ?? ""} 시장내재+인플레갭 기계 시그널의 과거 적중률 — 21에이전트 앙상블의 참조 하한선입니다 (ZLB 제외).`
                  : `${backtest?.data_range?.start ?? ""}–${backtest?.data_range?.end ?? ""} market-implied + inflation-gap mechanical signal — a reference floor for the 21-agent ensemble (ZLB months excluded).`}
              </p>
            </div>
          ) : (
            <p className="text-sm text-[var(--color-text-muted)]">
              {ko ? "백테스트 계산 중…" : "Computing backtest…"}
            </p>
          )}
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="card">
          <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-widest">
            {ko ? "방향 적중률" : "Hit Rate"}
          </p>
          <p className="text-2xl font-light mt-1" style={{ color: "var(--color-gold)" }}>
            {stats?.hit_rate != null ? `${Math.round(stats.hit_rate * 100)}%` : "—"}
          </p>
        </div>
        <div className="card">
          <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-widest">
            {ko ? "적중 / 판정" : "Hits / Scored"}
          </p>
          <p className="text-2xl font-light mt-1">
            <span style={{ color: "var(--color-signal-green)" }}>{stats?.hits ?? 0}</span>
            <span className="text-[var(--color-text-muted)] text-base"> / {stats?.scored ?? 0}</span>
          </p>
        </div>
        <div className="card">
          <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-widest">
            {ko ? "평균 오차" : "Avg Error"}
          </p>
          <p className="text-2xl font-light mt-1">
            {stats?.avg_abs_error_bps != null ? `${stats.avg_abs_error_bps}` : "—"}
            <span className="text-xs text-[var(--color-text-muted)] ml-1">bps</span>
          </p>
        </div>
        <div className="card">
          <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-widest">
            {ko ? "기록일수" : "Days Tracked"}
          </p>
          <p className="text-2xl font-light mt-1">{stats?.total_days ?? 0}</p>
        </div>
      </div>

      {/* Records table */}
      <div className="card overflow-x-auto">
        <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest mb-3">
          {ko ? "일별 적중 기록 (12M 콜)" : "Daily Hit Record (12M call)"}
        </p>
        {records.length === 0 ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            {ko
              ? "아직 기록이 없습니다 — 사이클이 돌 때마다 하루 단위로 쌓입니다."
              : "No records yet — one row accrues per forecast day."}
          </p>
        ) : (
          <table className="w-full text-sm min-w-[480px]">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] border-b"
                style={{ borderColor: "var(--color-navy-700)" }}>
                <th className="text-left py-2 pr-3">{ko ? "날짜" : "Date"}</th>
                <th className="text-right py-2 px-3">{ko ? "예측" : "Predicted"}</th>
                <th className="text-right py-2 px-3">{ko ? "시장 변화" : "Market Move"}</th>
                <th className="text-right py-2 pl-3">{ko ? "판정" : "Result"}</th>
              </tr>
            </thead>
            <tbody>
              {records.map(r => (
                <tr key={r.date} className="border-b" style={{ borderColor: "var(--color-navy-700)" }}>
                  <td className="py-2 pr-3 text-xs">{r.date}</td>
                  <td className="py-2 px-3 text-right" style={{ color: SIG_COLOR[r.signal] ?? "inherit" }}>
                    {r.predicted_bps > 0 ? "+" : ""}{Math.round(r.predicted_bps)} bps
                  </td>
                  <td className="py-2 px-3 text-right text-xs">
                    {r.market_move_bps != null
                      ? `${r.market_move_bps > 0 ? "+" : ""}${r.market_move_bps} bps`
                      : "—"}
                  </td>
                  <td className="py-2 pl-3 text-right">
                    {r.pending ? (
                      <span className="text-[10px] px-2 py-0.5 rounded"
                        style={{ background: "rgba(139,160,188,0.15)", color: "var(--color-text-muted)" }}>
                        {ko ? "집계중" : "PENDING"}
                      </span>
                    ) : r.hit === true ? (
                      <span className="text-[10px] px-2 py-0.5 rounded font-semibold"
                        style={{ background: "rgba(56,161,105,0.15)", color: "var(--color-signal-green)" }}>
                        {ko ? "적중" : "HIT"}
                      </span>
                    ) : r.hit === false ? (
                      <span className="text-[10px] px-2 py-0.5 rounded font-semibold"
                        style={{ background: "rgba(229,62,62,0.15)", color: "var(--color-signal-red)" }}>
                        {ko ? "빗나감" : "MISS"}
                      </span>
                    ) : (
                      <span className="text-[10px] px-2 py-0.5 rounded"
                        style={{ background: "rgba(139,160,188,0.15)", color: "var(--color-text-muted)" }}>
                        {ko ? "판정불가" : "FLAT"}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="text-[10px] text-[var(--color-text-muted)] leading-relaxed mt-3">
          {ko
            ? `판정 기준: 각 날짜의 마지막 12M 예측 방향을 다음 예측일까지의 2Y 국채금리(${stats?.proxy_series ?? "GS2"}) 변화 방향과 비교합니다. 시장이 ±1bp 미만 움직인 날은 판정에서 제외됩니다.`
            : `Scoring: each day's final 12M call is compared against the direction of the 2Y Treasury yield (${stats?.proxy_series ?? "GS2"}) move until the next forecast day. Days where the market moved <±1bp are not scored.`}
        </p>
      </div>

      {/* Agent misses */}
      {(data?.agent_misses?.length ?? 0) > 0 && (
        <div className="card">
          <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest mb-3">
            {ko ? "피드백 루프 — 오차 큰 에이전트" : "Feedback Loop — Most-Divergent Agents"}
          </p>
          <div className="flex flex-wrap gap-2">
            {data!.agent_misses.map(a => (
              <span key={a.agent_id} className="text-xs px-2.5 py-1 rounded"
                style={{ background: "var(--color-navy)", color: "var(--color-text-muted)" }}>
                Agent #{a.agent_id} · {a.miss_count}{ko ? "회" : "×"}
              </span>
            ))}
          </div>
          <p className="text-[10px] text-[var(--color-text-muted)] mt-2">
            {ko
              ? "오차가 20bp 이상 벌어진 예측은 부정 예시로 다음 사이클 프롬프트에 주입되어 자가 교정합니다."
              : "Predictions diverging ≥20bp are injected as negative examples into the next cycle's prompts."}
          </p>
        </div>
      )}
    </div>
  );
}
