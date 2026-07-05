"use client";
import { useEffect, useState } from "react";
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

export default function TrackRecordPanel() {
  const { lang } = useLang();
  const ko = lang === "ko";
  const [data, setData] = useState<TrackRecord | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<TrackRecord>("/api/track-record")
      .then(r => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="flex items-center justify-center h-48">
      <p className="text-[var(--color-text-muted)] text-sm animate-pulse">Loading…</p>
    </div>;
  }

  const stats = data?.stats;
  const records = data?.records ?? [];

  return (
    <div className="space-y-4 pb-8">
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
