import axios from "axios";

// ── Static-data mode (GitHub Pages) ──────────────────────────────────────
// When NEXT_PUBLIC_STATIC_DATA=true the site has no backend: the daily CI job
// (scripts/ci_daily.py) snapshots every GET endpoint into /data/*.json, and
// this adapter maps the same API URLs onto those files. POST is unavailable.
const STATIC_MODE = process.env.NEXT_PUBLIC_STATIC_DATA === "true";
const BASE = process.env.NEXT_PUBLIC_BASE_PATH || "";

/* Mirrors the axios surface the app uses — T defaults to `any` like axios. */
/* eslint-disable @typescript-eslint/no-explicit-any */
interface ApiClient {
  get<T = any>(url: string): Promise<{ data: T }>;
  post<T = any>(url: string, body?: unknown): Promise<{ data: T }>;
  patch<T = any>(url: string, body?: unknown): Promise<{ data: T }>;
  delete<T = any>(url: string): Promise<{ data: T }>;
}
/* eslint-enable @typescript-eslint/no-explicit-any */

async function staticGet<T>(url: string): Promise<{ data: T }> {
  const [path, qs] = url.split("?");
  const params = new URLSearchParams(qs || "");
  const lang = params.get("lang");
  let p = path.replace(/^\/api\//, "").replace(/\/+$/, "");
  const isBriefingList = p === "briefings";
  if (isBriefingList) p = "briefings/index"; // /api/briefings → archive index
  const res = await fetch(`${BASE}/data/${p}${lang ? `.${lang}` : ""}.json`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`No static data for ${p} (${res.status})`);
  let data: unknown = await res.json();
  // Query params a live backend would apply server-side:
  const limit = parseInt(params.get("limit") || "0", 10);
  if (isBriefingList && limit > 0 && Array.isArray(data)) data = data.slice(0, limit);
  const afterId = parseInt(params.get("after_id") || "0", 10);
  if (p === "activity" && afterId > 0 && Array.isArray(data)) {
    data = (data as { id: number }[]).filter((e) => e.id > afterId);
  }
  return { data: data as T };
}

const staticUnavailable = () =>
  Promise.reject(new Error("Not available on the static deployment"));

const staticApi: ApiClient = {
  get: staticGet,
  post: staticUnavailable,
  patch: staticUnavailable,
  delete: staticUnavailable,
};

const axiosApi = axios.create({
  baseURL: "",   // Next.js rewrites /api/* → localhost:8000/api/*
  withCredentials: true,
});

axiosApi.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

const api: ApiClient = STATIC_MODE ? staticApi : (axiosApi as unknown as ApiClient);

export default api;

// Horizon keys are FOMC decision dates ("2026-12-09") for every scheduled
// meeting within 3 years, plus "5y" / "10y" / "30y" (the meeting nearest that
// many years ahead) and a synthetic "today" anchor. The set shifts daily, so
// consumers read the ordered `items` list rather than fixed keys.
export type Horizon = string;
export type HorizonKind = "today" | "fomc" | "5y" | "10y" | "30y";

export interface HorizonForecast {
  horizon: Horizon;
  meeting_date: string;                // ISO date of the targeted FOMC decision
  kind: HorizonKind;
  is_primary: boolean;                 // headline call (meeting nearest 12 months)
  months_ahead?: number;
  days_to_meeting?: number;
  projected?: boolean;                 // date projected (Fed has not published it yet)
  label_en?: string;
  label_ko?: string;
  published_at: string | null;
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
  band_source?: "conformal" | "dispersion";
  probs?: MeetingProbs | null;         // P(cut / hold / hike) after this meeting
  synthetic?: boolean;                 // the "today" anchor
}

export interface MeetingProbs {
  states: Record<string, number>;      // cumulative-delta state (bps) → probability
  p_cut: number | null;
  p_hold: number | null;
  p_hike: number | null;
  mean: number | null;
}

export interface LearningStatus {
  as_of: string;
  fitted_at: string | null;
  n_matured_committee: number;
  n_matured_agent_calls: number;
  scores: { n?: number; hit_rate?: number; mae_bps?: number; brier?: number | null; brier_n?: number; brier_climatology?: number };
  agent_skill: Record<string, { agent_id: number; agent_name: string; multiplier: number; n: number | null }[]>;
  conf_map: { conf: number; p_correct: number }[];
  conformal: Record<string, { q68: number; q90: number; n: number }>;
  thresholds: { skill_min_n: number; conf_min_n: number; conformal_min_n: number };
  notes: string[];
  method: string;
}

export interface AllHorizons {
  as_of: string;
  current_rate_pct: number | null;
  primary: Horizon | null;
  items: HorizonForecast[];            // ordered: today → each FOMC → 5y → 10y → 30y
}

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
  horizon_months?: [number, number]; // months-ahead span of the driving meetings
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
