"use client";
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useLang } from "@/context/LanguageContext";

interface TradeRow {
  id: number;
  created_at: string | null;
  instrument: string;
  direction: string;
  entry_rate: number | null;
  exit_rate: number | null;
  pnl_pct: number | null;
  unrealized_pnl_pct?: number;
  current_rate?: number;
  rationale: string | null;
}

interface TradingData {
  open_positions: TradeRow[];
  closed_trades: TradeRow[];
  summary: {
    open_count: number;
    closed_count: number;
    realized_pnl_pct: number;
    wins: number;
    losses: number;
    win_rate: number | null;
    mark_series: string;
    mark: number | null;
  };
}

const INSTRUMENT_LABEL: Record<string, { en: string; ko: string }> = {
  "2Y_TREASURY": { en: "2Y Treasury", ko: "미국채 2년" },
  "10Y_TREASURY": { en: "10Y Treasury", ko: "미국채 10년" },
  TLT: { en: "TLT (20Y+ ETF)", ko: "TLT (장기채 ETF)" },
  USD: { en: "US Dollar", ko: "달러 (USD)" },
};

function pnlColor(v: number | null | undefined): string {
  if (v == null || v === 0) return "var(--color-text-muted)";
  return v > 0 ? "var(--color-signal-green)" : "var(--color-signal-red)";
}

function fmtPnl(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

export default function TradingPanel() {
  const { lang } = useLang();
  const ko = lang === "ko";
  const [data, setData] = useState<TradingData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<TradingData>("/api/trading")
      .then(r => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="flex items-center justify-center h-48">
      <p className="text-[var(--color-text-muted)] text-sm animate-pulse">Loading…</p>
    </div>;
  }

  const s = data?.summary;
  const open = data?.open_positions ?? [];
  const closed = data?.closed_trades ?? [];
  const dirLabel = (d: string) =>
    d === "long" ? (ko ? "롱" : "LONG") : (ko ? "숏" : "SHORT");

  return (
    <div className="space-y-4 pb-8">
      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="card">
          <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-widest">
            {ko ? "누적 실현손익" : "Realized P&L"}
          </p>
          <p className="text-2xl font-light mt-1" style={{ color: pnlColor(s?.realized_pnl_pct) }}>
            {fmtPnl(s?.realized_pnl_pct)}
          </p>
        </div>
        <div className="card">
          <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-widest">
            {ko ? "승률" : "Win Rate"}
          </p>
          <p className="text-2xl font-light mt-1" style={{ color: "var(--color-gold)" }}>
            {s?.win_rate != null ? `${Math.round(s.win_rate * 100)}%` : "—"}
          </p>
          <p className="text-[10px] text-[var(--color-text-muted)] mt-0.5">
            {s ? `${s.wins}W · ${s.losses}L` : ""}
          </p>
        </div>
        <div className="card">
          <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-widest">
            {ko ? "보유 포지션" : "Open Positions"}
          </p>
          <p className="text-2xl font-light mt-1">{s?.open_count ?? 0}</p>
        </div>
        <div className="card">
          <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-widest">
            {ko ? "청산 완료" : "Closed Trades"}
          </p>
          <p className="text-2xl font-light mt-1">{s?.closed_count ?? 0}</p>
        </div>
      </div>

      {/* Open positions */}
      <div className="card overflow-x-auto">
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest">
            {ko ? "보유 포지션" : "Open Positions"}
          </p>
          {s?.mark != null && (
            <span className="text-[10px] text-[var(--color-text-muted)]">
              {ko ? "기준" : "Mark"}: {s.mark_series} {s.mark.toFixed(2)}%
            </span>
          )}
        </div>
        {open.length === 0 ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            {ko
              ? "보유 포지션이 없습니다 — 다음 예측 사이클에서 12M 콜 기준으로 자동 진입합니다."
              : "No open positions — the next forecast cycle opens positions from the 12M call."}
          </p>
        ) : (
          <table className="w-full text-sm min-w-[560px]">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] border-b"
                style={{ borderColor: "var(--color-navy-700)" }}>
                <th className="text-left py-2 pr-3">{ko ? "종목" : "Instrument"}</th>
                <th className="text-center py-2 px-3">{ko ? "방향" : "Side"}</th>
                <th className="text-right py-2 px-3">{ko ? "진입금리" : "Entry"}</th>
                <th className="text-right py-2 px-3">{ko ? "평가손익" : "Unrealized"}</th>
                <th className="text-left py-2 pl-3">{ko ? "논거" : "Rationale"}</th>
              </tr>
            </thead>
            <tbody>
              {open.map(t => (
                <tr key={t.id} className="border-b" style={{ borderColor: "var(--color-navy-700)" }}>
                  <td className="py-2 pr-3 text-xs font-medium">
                    {ko ? INSTRUMENT_LABEL[t.instrument]?.ko ?? t.instrument
                        : INSTRUMENT_LABEL[t.instrument]?.en ?? t.instrument}
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span className="text-[10px] px-2 py-0.5 rounded font-semibold" style={{
                      background: t.direction === "long" ? "rgba(56,161,105,0.15)" : "rgba(229,62,62,0.15)",
                      color: t.direction === "long" ? "var(--color-signal-green)" : "var(--color-signal-red)",
                    }}>
                      {dirLabel(t.direction)}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right text-xs">
                    {t.entry_rate != null ? `${t.entry_rate.toFixed(2)}%` : "—"}
                  </td>
                  <td className="py-2 px-3 text-right" style={{ color: pnlColor(t.unrealized_pnl_pct) }}>
                    {fmtPnl(t.unrealized_pnl_pct)}
                  </td>
                  <td className="py-2 pl-3 text-[10px] text-[var(--color-text-muted)] max-w-[220px]">
                    {t.rationale ?? ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Closed trades */}
      <div className="card overflow-x-auto">
        <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest mb-3">
          {ko ? "청산 내역" : "Closed Trades"}
        </p>
        {closed.length === 0 ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            {ko
              ? "청산 내역이 없습니다 — 포지션은 다음 사이클에서 자동 청산·재진입됩니다."
              : "No closed trades yet — positions roll automatically each cycle."}
          </p>
        ) : (
          <table className="w-full text-sm min-w-[560px]">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] border-b"
                style={{ borderColor: "var(--color-navy-700)" }}>
                <th className="text-left py-2 pr-3">{ko ? "일시" : "Date"}</th>
                <th className="text-left py-2 px-3">{ko ? "종목" : "Instrument"}</th>
                <th className="text-center py-2 px-3">{ko ? "방향" : "Side"}</th>
                <th className="text-right py-2 px-3">{ko ? "진입→청산" : "Entry→Exit"}</th>
                <th className="text-right py-2 pl-3">{ko ? "손익" : "P&L"}</th>
              </tr>
            </thead>
            <tbody>
              {closed.map(t => (
                <tr key={t.id} className="border-b" style={{ borderColor: "var(--color-navy-700)" }}>
                  <td className="py-2 pr-3 text-[10px] text-[var(--color-text-muted)]">
                    {t.created_at?.replace("T", " ").slice(0, 16) ?? "—"}
                  </td>
                  <td className="py-2 px-3 text-xs">
                    {ko ? INSTRUMENT_LABEL[t.instrument]?.ko ?? t.instrument
                        : INSTRUMENT_LABEL[t.instrument]?.en ?? t.instrument}
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span className="text-[10px] px-2 py-0.5 rounded font-semibold" style={{
                      background: t.direction === "long" ? "rgba(56,161,105,0.15)" : "rgba(229,62,62,0.15)",
                      color: t.direction === "long" ? "var(--color-signal-green)" : "var(--color-signal-red)",
                    }}>
                      {dirLabel(t.direction)}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right text-xs">
                    {t.entry_rate != null && t.exit_rate != null
                      ? `${t.entry_rate.toFixed(2)}% → ${t.exit_rate.toFixed(2)}%`
                      : "—"}
                  </td>
                  <td className="py-2 pl-3 text-right font-medium" style={{ color: pnlColor(t.pnl_pct) }}>
                    {fmtPnl(t.pnl_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="text-[10px] text-[var(--color-text-muted)] leading-relaxed mt-3">
          {ko
            ? "⚠ 가상(페이퍼) 트레이딩입니다. 각 사이클의 12M 금리 콜을 채권/달러 포지션으로 변환해 2Y 국채금리 기준으로 손익을 평가하며, 실제 매매가 아닙니다."
            : "⚠ Paper trading. Each cycle's 12M rate call is mapped to bond/USD positions and marked against the 2Y Treasury yield. No real orders are placed."}
        </p>
      </div>
    </div>
  );
}
