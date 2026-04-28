"use client";
import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { DailyBriefing, BriefingListItem } from "@/lib/api";

export function useLatestBriefing(lang: "en" | "ko") {
  const [briefing, setBriefing] = useState<DailyBriefing | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<DailyBriefing | null>(`/api/briefings/latest?lang=${lang}`);
      setBriefing(res.data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load briefing");
    } finally {
      setLoading(false);
    }
  }, [lang]);

  useEffect(() => { fetch(); }, [fetch]);
  return { briefing, loading, error, refetch: fetch };
}

export function useBriefingList(lang: "en" | "ko", limit = 14) {
  const [list, setList] = useState<BriefingListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api.get<BriefingListItem[]>(`/api/briefings?lang=${lang}&limit=${limit}`)
      .then(r => { if (!cancelled) setList(r.data); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [lang, limit]);

  return { list, loading };
}

export function useBriefingByDate(date: string, lang: "en" | "ko") {
  const [briefing, setBriefing] = useState<DailyBriefing | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.get<DailyBriefing>(`/api/briefings/${date}?lang=${lang}`)
      .then(r => { if (!cancelled) setBriefing(r.data); })
      .catch(e => { if (!cancelled) setError(e?.response?.status === 404 ? "not_found" : "error"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [date, lang]);

  return { briefing, loading, error };
}
