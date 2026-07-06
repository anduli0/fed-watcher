import axios from "axios";

const api = axios.create({
  baseURL: "",   // Next.js rewrites /api/* → localhost:8000/api/*
  withCredentials: true,
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default api;

export type Horizon = "today" | "3m" | "6m" | "12m" | "3y" | "10y";
// Term-structure order: spot → near-term → analytical horizons.
export const HORIZONS: Horizon[] = ["today", "3m", "6m", "12m", "3y", "10y"];
// The four horizons the 21-agent committee actually forecasts (today & 3m are
// derived anchor points on the same curve).
export const CORE_HORIZONS: Horizon[] = ["6m", "12m", "3y", "10y"];

export interface HorizonForecast {
  horizon: Horizon;
  published_at: string;
  published_delta_bps: number;
  smoothed_delta_bps: number;
  confidence: number;
  signal: "hawkish" | "neutral" | "dovish";
  trigger_event: string | null;
  unchanged_streak_days: number;
  change_justification: string | null;
  dispersion_bps?: number | null;
  band_low_bps?: number | null;
  band_high_bps?: number | null;
  implied_rate_pct?: number | null;   // current Fed Funds + delta
  synthetic?: boolean;                 // today / 3m derived anchor points
}

export type AllHorizons = { [k in Horizon]: HorizonForecast | null };

// ── Trading desk (positions by maturity) ─────────────────────────────────
export type TradeDir = "long" | "short" | "neutral";

export interface TreasuryPosition {
  label: string;                 // "2Y" | "5Y" | "10Y" | "30Y"
  spot_instrument: string;
  direction: TradeDir;
  raw_direction: TradeDir;
  reason: string | null;
  current_yield: number | null;
  target_yield: number | null;
  expected_dy_bps: number | null;
  confidence: number;
  horizon_basis: string;
  fed_path_beta: number;
  cash_mod_duration: number;
  spot_face_value: number;
  spot_price_move_pct: number | null;
  futures_symbol: string;
  futures_name: string;
  futures_contracts: number;
  futures_dv01: number;
  futures_price_move_pct: number | null;
  stop_yield: number | null;
  take_profit_yield: number | null;
  stop_bps: number;
  risk_dollars: number;
}

export interface TradingDesk {
  as_of: string | null;
  fed_funds: number | null;
  equity: number;
  positions: TreasuryPosition[];
  disclaimer: string;
}

// ── Macro indicators (Today tab) ─────────────────────────────────────────
export interface MacroIndicator {
  key: string;
  series_id: string;
  name_ko: string;
  name_en: string;
  category: "inflation" | "labor" | "growth" | "expectations" | "policy";
  unit: string;
  impact: "high" | "medium" | "low";
  meaning_ko: string;
  latest_value: number | null;
  latest_display: string | null;
  latest_date: string | null;
  prior_value: number | null;
  prior_display: string | null;
  change: number | null;
  next_release: string | null;
}

export interface MacroIndicators {
  as_of: string | null;
  indicators: MacroIndicator[];
}

export interface ForecastHistoryItem {
  date: string;
  published_delta_bps: number;
  confidence: number;
  change_justification: string | null;
  unchanged_streak_days: number;
}

export interface AgentHorizon {
  delta_bps: number;
  confidence: number;
  rationale: string;
}

export interface AgentStatus {
  agent_id: number;
  agent_name: string;
  signal: "hawkish" | "neutral" | "dovish";
  rate_path_delta_bps: number;
  horizons: { [k in Horizon]?: AgentHorizon };
  confidence: number;
  limited_mode: boolean;
  duration_ms: number;
  round: number;
  last_run: string;
}

// Backward-compat
export interface Forecast {
  published_at: string;
  published_delta_bps: number;
  smoothed_delta_bps: number;
  confidence: number;
  signal: "hawkish" | "neutral" | "dovish";
  trigger_event: string | null;
  unchanged_streak_days: number;
  change_justification: string | null;
}

// ── Daily Briefing types ─────────────────────────────────────────────────

export interface BriefingSection {
  heading: string;
  body: string;
  sourceIds: string[];
}

export interface BriefingSource {
  id: string;
  title: string;
  url: string;
  publisher: string;
  published_at: string;
}

export interface DailyBriefing {
  id: number;
  briefing_date: string;          // "2026-04-28"
  language: "en" | "ko";
  timezone: string;
  title: string;
  market_impact_headline: string;
  executive_summary: string[];
  sections: BriefingSection[];
  what_changed_since_yesterday: string[];
  fed_watcher_rate_path_signal: string;
  watch_next: string[];
  disclaimer: string;
  source_count: number;
  article_count: number;
  model_used: string;
  status: "draft" | "published" | "failed";
  generation_finished_at: string | null;
  created_at: string | null;
  sources: BriefingSource[];
  fallback?: boolean;             // true if showing other-language fallback
  requested_lang?: string;
}

export interface BriefingListItem {
  id: number;
  briefing_date: string;
  language: "en" | "ko";
  title: string;
  market_impact_headline: string;
  status: string;
  generation_finished_at: string | null;
  article_count: number;
  source_count: number;
}
