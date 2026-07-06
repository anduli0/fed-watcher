"use client";
import { useState, useEffect, useCallback } from "react";
import api, { TradingDesk, TreasuryPosition, TradeDir } from "@/lib/api";
import { useLang } from "@/context/LanguageContext";

const DIR_COLOR: Record<TradeDir, string> = {
  long: "var(--color-signal-green)",
  short: "var(--color-signal-red)",
  neutral: "var(--color-gold)",
};
const EQUITY_PRESETS = [100_000, 1_000_000, 10_000_000];

function fmtUSD(n: number): string {
  if (n >= 1_000_000) return "$" + (n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1) + "M";
  if (n >= 1_000) return "$" + (n / 1_000).toFixed(0) + "K";
  return "$" + n.toFixed(0);
}

// Forecast-horizon months keyed by the labels used in `horizon_basis` (e.g. "0.55·6m + 0.45·12m")
const HORIZON_MONTHS: Record<string, number> = { "6m": 6, "12m": 12, "3y": 36, "10y": 120 };

// Turn a horizon_basis string into the human time window over which the target is expected
// to be reached, e.g. "0.55·6m + 0.45·12m" → "6~12개월", "0.55·3y + 0.45·10y" → "3~10년".
function horizonPeriod(basis: string, ko: boolean): string | null {
  if (!basis) return null;
  const months = (basis.match(/12m|10y|6m|3y/g) || []).map(h => HORIZON_MONTHS[h]).filter(Boolean);
  if (!months.length) return null;
  const lo = Math.min(...months), hi = Math.max(...months);
  const yr = (mo: number) => { const v = mo / 12; return Number.isInteger(v) ? `${v}` : v.toFixed(1); };
  if (lo === hi) return hi < 12 ? (ko ? `${hi}개월` : `${hi}m`) : (ko ? `${yr(hi)}년` : `${yr(hi)}y`);
  if (hi <= 12) return ko ? `${lo}~${hi}개월` : `${lo}~${hi}m`;
  if (lo >= 12) return ko ? `${yr(lo)}~${yr(hi)}년` : `${yr(lo)}~${yr(hi)}y`;
  return ko ? `${lo}개월~${yr(hi)}년` : `${lo}m~${yr(hi)}y`;
}

export default function TradingDeskPanel() {
  const { lang } = useLang();
  const ko = lang === "ko";
  const [equity, setEquity] = useState(1_000_000);
  const [desk, setDesk] = useState<TradingDesk | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(false);

  const load = useCallback(async (eq: number) => {
    setLoading(true); setErr(false);
    try {
      const r = await api.get<TradingDesk>(`/api/trading/desk?equity=${eq}`);
      setDesk(r.data);
    } catch { setErr(true); } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(equity); }, [equity, load]);

  const dirLabel = (d: TradeDir) =>
    d === "long" ? (ko ? "롱 (매수)" : "LONG") : d === "short" ? (ko ? "숏 (매도)" : "SHORT") : (ko ? "관망" : "FLAT");

  const counts = desk?.positions.reduce(
    (a, p) => { a[p.direction]++; return a; },
    { long: 0, short: 0, neutral: 0 } as Record<TradeDir, number>
  );

  return (
    <div className="pb-8 space-y-4 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.25em] text-[var(--color-gold)] mb-1">
            {ko ? "트레이딩 데스크" : "Treasury Trading Desk"}
          </p>
          <h2 className="text-xl sm:text-2xl font-semibold text-[var(--color-text-primary)]">
            {ko ? "미국 국채 — 만기별 포지션" : "US Treasuries — positions by maturity"}
          </h2>
          <p className="text-xs text-[var(--color-text-muted)] mt-1">
            {ko
              ? "금리 경로 예측 → 현물·선물 롱/숏 / 목표가 / 포지션 사이징 (AI 자동매매용)"
              : "Rate-path forecast → spot & futures long/short, targets, sizing (for AI auto-trading)"}
          </p>
        </div>
        {desk && (
          <div className="text-left sm:text-right text-xs text-[var(--color-text-muted)]">
            <p suppressHydrationWarning>{ko ? "기준" : "as of"} {desk.as_of}</p>
            {desk.fed_funds != null && <p>{ko ? "기준금리" : "Fed Funds"} {desk.fed_funds.toFixed(2)}%</p>}
          </div>
        )}
      </div>

      {/* Account equity + sizing control */}
      <div className="card flex flex-col sm:flex-row sm:items-center gap-3">
        <span className="text-xs text-[var(--color-text-muted)]">
          {ko ? "계좌 자본 (포지션 크기 기준)" : "Account equity (sizes positions)"}
        </span>
        <div className="flex items-center gap-1.5 flex-wrap">
          {EQUITY_PRESETS.map(v => (
            <button key={v} onClick={() => setEquity(v)}
              className="text-xs px-2.5 py-1 rounded transition-colors"
              style={{
                background: equity === v ? "var(--color-gold)" : "var(--color-navy-700)",
                color: equity === v ? "var(--color-navy)" : "var(--color-text-muted)",
              }}>
              {fmtUSD(v)}
            </button>
          ))}
          <input
            type="number" value={equity} min={10000} step={10000}
            onChange={e => setEquity(Math.max(10000, Number(e.target.value) || 0))}
            className="text-xs w-28 px-2 py-1 rounded bg-[var(--color-navy-700)] border border-[var(--color-navy-700)] text-[var(--color-text-primary)]"
          />
        </div>
        {counts && (
          <div className="sm:ml-auto flex items-center gap-3 text-xs">
            <span style={{ color: DIR_COLOR.long }}>● {ko ? "롱" : "Long"} {counts.long}</span>
            <span style={{ color: DIR_COLOR.short }}>● {ko ? "숏" : "Short"} {counts.short}</span>
            <span style={{ color: DIR_COLOR.neutral }}>● {ko ? "관망" : "Flat"} {counts.neutral}</span>
          </div>
        )}
      </div>

      {loading && !desk && (
        <div className="flex items-center justify-center h-40">
          <p className="text-[var(--color-text-muted)] text-sm animate-pulse">{ko ? "포지션 계산 중…" : "Computing positions…"}</p>
        </div>
      )}
      {err && <div className="card"><p className="text-sm text-[var(--color-signal-red)]">{ko ? "데이터를 불러오지 못했습니다." : "Failed to load."}</p></div>}

      {/* Position cards */}
      {desk && (
        <div className="grid md:grid-cols-2 gap-3">
          {desk.positions.map(p => <PositionCard key={p.label} p={p} dirLabel={dirLabel} ko={ko} />)}
        </div>
      )}

      {/* Disclaimer */}
      {desk && (
        <div className="card" style={{ borderColor: "rgba(201,168,76,0.25)" }}>
          <p className="text-[10px] leading-relaxed text-[var(--color-text-muted)]">
            ⚠ {ko
              ? "투자 조언이 아닙니다. 확률적 금리 예측에서 파생된 모델·연구·모의매매용 산출물입니다. 듀레이션·베타·DV01은 곡선/최저인도채권에 따라 변하는 단순 추정치이며, 실주문 전 브로커 실시간 데이터로 재계산하세요. 선물 레버리지는 증거금 초과 손실을 낼 수 있습니다. 실자본 투입 전 검증·모의매매 하십시오."
              : desk.disclaimer}
          </p>
        </div>
      )}
    </div>
  );
}

function PositionCard({ p, dirLabel, ko }: { p: TreasuryPosition; dirLabel: (d: TradeDir) => string; ko: boolean }) {
  const color = DIR_COLOR[p.direction];
  const active = p.direction !== "neutral";
  const moveSign = (n: number | null) => (n == null ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(2)}%`);
  const horizonP = horizonPeriod(p.horizon_basis, ko);

  return (
    <div className="card" style={{ borderColor: active ? color : "var(--color-navy-700)", boxShadow: active ? `0 0 0 1px ${color}40` : "none" }}>
      {/* header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-baseline gap-2">
          <span className="text-lg font-semibold text-[var(--color-text-primary)]">{p.label}</span>
          <span className="text-[10px] text-[var(--color-text-muted)]">{p.spot_instrument}</span>
        </div>
        <span className="text-xs font-bold px-2.5 py-1 rounded" style={{ background: `${color}1f`, color }}>
          {dirLabel(p.direction)}
        </span>
      </div>

      {/* yield current -> target */}
      <div className="flex items-end gap-2 mb-1">
        <div>
          <p className="text-[10px] text-[var(--color-text-muted)]">{ko ? "현재 수익률" : "Current yield"}</p>
          <p className="text-xl font-light text-[var(--color-text-primary)]">{p.current_yield != null ? p.current_yield.toFixed(2) + "%" : "—"}</p>
        </div>
        <span className="text-[var(--color-text-muted)] mb-1.5">→</span>
        <div>
          <p className="text-[10px] text-[var(--color-text-muted)]">{ko ? "예상(목표) 수익률" : "Expected (target)"}</p>
          <p className="text-xl font-light" style={{ color }}>{p.target_yield != null ? p.target_yield.toFixed(2) + "%" : "—"}</p>
        </div>
        {p.expected_dy_bps != null && (
          <span className="ml-auto text-xs mb-1" style={{ color }}>
            {p.expected_dy_bps > 0 ? "+" : ""}{p.expected_dy_bps.toFixed(0)}bps
          </span>
        )}
      </div>

      {/* expected time window over which the target yield is forecast to be reached */}
      {horizonP && (
        <p className="text-[11px] text-[var(--color-text-muted)] mb-2">
          {ko ? "예상 도달 기간" : "Expected horizon"}:{" "}
          <span className="font-medium" style={{ color }}>{ko ? `${horizonP} 내` : `within ${horizonP}`}</span>
        </p>
      )}

      {/* confidence */}
      <div className="mt-2 mb-3">
        <div className="flex justify-between text-[10px] text-[var(--color-text-muted)] mb-1">
          <span>{ko ? "신뢰도" : "Confidence"}</span><span>{(p.confidence * 100).toFixed(0)}%</span>
        </div>
        <div className="h-1 bg-[var(--color-navy-700)] rounded-full overflow-hidden">
          <div className="h-full rounded-full" style={{ width: `${p.confidence * 100}%`, background: color }} />
        </div>
      </div>

      {active ? (
        <>
          {/* spot + futures legs */}
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="rounded p-2" style={{ background: "var(--color-navy-700)" }}>
              <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">{ko ? "현물" : "Spot"}</p>
              <p className="font-medium" style={{ color }}>{moveSign(p.spot_price_move_pct)}</p>
              <p className="text-[10px] text-[var(--color-text-muted)] mt-0.5">{ko ? "수량" : "Size"}: {p.spot_face_value > 0 ? "$" + p.spot_face_value.toLocaleString() + (ko ? " 액면" : " face") : "—"}</p>
              <p className="text-[10px] text-[var(--color-text-muted)]">Dur {p.cash_mod_duration}</p>
            </div>
            <div className="rounded p-2" style={{ background: "var(--color-navy-700)" }}>
              <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">{ko ? "선물" : "Futures"} · {p.futures_symbol}</p>
              <p className="font-medium" style={{ color }}>{moveSign(p.futures_price_move_pct)}</p>
              <p className="text-[10px] text-[var(--color-text-muted)] mt-0.5">{ko ? "계약" : "Contracts"}: <b style={{ color: p.futures_contracts > 0 ? color : "var(--color-text-muted)" }}>{p.direction === "short" ? "-" : ""}{p.futures_contracts}</b></p>
              <p className="text-[10px] text-[var(--color-text-muted)]">DV01 ${p.futures_dv01}/bp</p>
            </div>
          </div>

          {/* stop / take-profit / risk */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-[11px]">
            <span className="text-[var(--color-text-muted)]">{ko ? "손절" : "Stop"}: <span className="text-[var(--color-signal-red)]">{p.stop_yield != null ? p.stop_yield.toFixed(2) + "%" : "—"}</span> ({p.stop_bps}bps)</span>
            <span className="text-[var(--color-text-muted)]">{ko ? "목표" : "Target"}: <span style={{ color }}>{p.take_profit_yield != null ? p.take_profit_yield.toFixed(2) + "%" : "—"}</span></span>
            <span className="text-[var(--color-text-muted)]">{ko ? "리스크" : "Risk"}: {fmtUSD(p.risk_dollars)}</span>
          </div>
        </>
      ) : (
        <p className="text-xs text-[var(--color-text-muted)] italic">
          {ko ? "관망 — " : "Flat — "}
          {p.reason === "within neutral band (±8bps)" ? (ko ? "예상 변동이 중립 밴드(±8bps) 이내" : p.reason)
            : p.reason?.startsWith("forecast confidence") ? (ko ? "예측 신뢰도 부족" : p.reason)
            : p.reason?.startsWith("signal confidence") ? (ko ? "신호 신뢰도 부족" : p.reason)
            : p.reason || (ko ? "신호 없음" : "no signal")}
          {p.raw_direction !== "neutral" && (
            <span className="not-italic"> · {ko ? "방향 신호" : "bias"}: <b style={{ color: DIR_COLOR[p.raw_direction] }}>{dirLabel(p.raw_direction)}</b></span>
          )}
        </p>
      )}

      {/* basis */}
      <p className="text-[10px] text-[var(--color-text-muted)] mt-2 pt-2 border-t" style={{ borderColor: "var(--color-navy-700)" }}>
        {ko ? "근거" : "Driven by"}: {p.horizon_basis} · β {p.fed_path_beta} · {p.futures_name}
      </p>
    </div>
  );
}
