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

export type Horizon = "6m" | "12m" | "3y" | "10y";
export const HORIZONS: Horizon[] = ["6m", "12m", "3y", "10y"];

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
}

export interface AllHorizons {
  "6m":  HorizonForecast | null;
  "12m": HorizonForecast | null;
  "3y":  HorizonForecast | null;
  "10y": HorizonForecast | null;
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
