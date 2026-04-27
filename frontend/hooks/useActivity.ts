"use client";
import { useState, useEffect, useRef } from "react";
import api from "@/lib/api";

export interface ActivityEvent {
  id: number;
  ts: number;
  source: string;
  agent: string;
  message: string;
  color: string;
  status: string;
}

const POLL_INTERVAL = 3000;  // 3s

export function useActivity(active: boolean = true) {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const lastIdRef = useRef(0);

  useEffect(() => {
    if (!active) return;

    async function poll() {
      try {
        const res = await api.get<ActivityEvent[]>(`/api/activity?after_id=${lastIdRef.current}`);
        const newEvents = res.data;
        if (newEvents.length > 0) {
          lastIdRef.current = newEvents[newEvents.length - 1].id;
          setEvents(prev => [...newEvents, ...prev].slice(0, 50));
        }
      } catch {
        // silent fail
      }
    }

    poll();  // immediate first fetch
    const id = setInterval(poll, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [active]);

  return events;
}
