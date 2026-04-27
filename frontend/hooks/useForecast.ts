"use client";
import { useState, useEffect, useCallback } from "react";
import api, { ForecastHistoryItem, AgentStatus, AllHorizons } from "@/lib/api";
import { useLang } from "@/context/LanguageContext";

export function useForecast() {
  const { lang } = useLang();
  const [horizons, setHorizons] = useState<AllHorizons | null>(null);
  const [history, setHistory] = useState<ForecastHistoryItem[]>([]);
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [report, setReport] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const refresh = useCallback(async () => {  // eslint-disable-line react-hooks/exhaustive-deps
    try {
      const [horRes, hRes, aRes, repRes] = await Promise.all([
        api.get<AllHorizons>("/api/forecast/horizons"),
        api.get<ForecastHistoryItem[]>("/api/forecast/history"),
        api.get<AgentStatus[]>("/api/agents/status"),
        api.get<{ report: string }>(`/api/forecast/report?lang=${lang}`),
      ]);
      setHorizons(horRes.data);
      setHistory(hRes.data);
      setAgents(aRes.data);
      setReport(repRes.data.report || "");
      setError(null);
      setLastRefresh(new Date());
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Network error";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [lang]);  // re-fetch report when language changes

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15 * 60 * 1000);
    return () => clearInterval(id);
  }, [refresh]);

  return { horizons, history, agents, report, loading, error, lastRefresh, refresh };
}
