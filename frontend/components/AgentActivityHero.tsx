"use client";
import { useState, useEffect, useRef } from "react";
import { useLang } from "@/context/LanguageContext";
import { useActivity, ActivityEvent } from "@/hooks/useActivity";

const INNER_NODES = [
  { id: 1,  name: "Behavioral",       icon: "👁",  color: "#C9A84C" },
  { id: 2,  name: "NLP",              icon: "💬",  color: "#38A169" },
  { id: 3,  name: "History",          icon: "📚",  color: "#4A90D9" },
  { id: 4,  name: "Academic",         icon: "📐",  color: "#C9A84C" },
  { id: 5,  name: "Projections",      icon: "🔭",  color: "#9F7AEA" },
  { id: 6,  name: "FOMC_Minutes",     icon: "📄",  color: "#E53E3E" },
  { id: 7,  name: "Macro_Data",       icon: "📊",  color: "#38A169" },
  { id: 8,  name: "Political_Economy",icon: "🏛",  color: "#4A6080" },
  { id: 10, name: "Consensus",        icon: "🏦",  color: "#4A90D9" },
];

const OUTER_NODES = [
  { id: 101, label: "BOS" }, { id: 102, label: "NY"  }, { id: 103, label: "PHL" },
  { id: 104, label: "CLE" }, { id: 105, label: "RIC" }, { id: 106, label: "ATL" },
  { id: 107, label: "CHI" }, { id: 108, label: "STL" }, { id: 109, label: "MIN" },
  { id: 110, label: "KC"  }, { id: 111, label: "DAL" }, { id: 112, label: "SF"  },
];

const REGIONAL_COLOR = "#9F7AEA";

function toRad(deg: number) { return (deg * Math.PI) / 180; }

function agentColorFromEvent(e: ActivityEvent): string {
  const inner = INNER_NODES.find(n => n.name === e.agent || e.agent.includes(n.name));
  if (inner) return inner.color;
  if (e.source === "collector") return "#4A90D9";
  if (e.source === "orchestrator") return "#C9A84C";
  if (e.source === "system") return "#4A6080";
  return REGIONAL_COLOR;
}

function activeAgentsFromEvent(e: ActivityEvent): number[] {
  const inner = INNER_NODES.find(n => n.name === e.agent || e.agent.includes(n.name));
  if (inner) return [inner.id];
  // Map regional bank abbreviations
  const bankMap: Record<string, number> = {
    Boston: 101, "New York": 102, NewYork: 102, Philadelphia: 103, Cleveland: 104,
    Richmond: 105, Atlanta: 106, Chicago: 107, "St. Louis": 108, StLouis: 108,
    Minneapolis: 109, "Kansas City": 110, KansasCity: 110, Dallas: 111, "San Francisco": 112, SanFrancisco: 112,
  };
  for (const [key, id] of Object.entries(bankMap)) {
    if (e.agent.includes(key)) return [id];
  }
  return [];
}

export default function AgentActivityHero({ liveTab = false }: { liveTab?: boolean }) {
  const { T } = useLang();
  const [mounted, setMounted] = useState(false);
  const [activeIds, setActiveIds] = useState<Set<number>>(new Set([7, 2, 102]));
  const [pulseCenter, setPulseCenter] = useState(false);
  const events = useActivity(true);  // always poll real events

  useEffect(() => { setMounted(true); }, []);

  // Update active nodes from real events
  useEffect(() => {
    if (events.length === 0) return;
    const latest = events[0];
    const ids = activeAgentsFromEvent(latest);
    if (ids.length > 0) {
      setActiveIds(prev => {
        const next = new Set(prev);
        ids.forEach(id => next.add(id));
        if (next.size > 5) next.delete(next.values().next().value!);
        return next;
      });
    }
    if (latest.source === "orchestrator" && latest.message.includes("synth")) {
      setPulseCenter(true);
      setTimeout(() => setPulseCenter(false), 1200);
    }
  }, [events]);

  const W = 460, H = 420, cx = W / 2, cy = H / 2, R_INNER = 110, R_OUTER = 175;

  return (
    <div
      className="w-full rounded-xl overflow-hidden"
      style={{ background: "linear-gradient(135deg, #060E1C 0%, #0A1628 60%, #0D1F3C 100%)", border: "1px solid #112952" }}
    >
      {/* Header */}
      <div className="px-4 sm:px-6 pt-4 sm:pt-5 pb-3">
        <div className="flex items-center gap-2 mb-1">
          <span className="w-2 h-2 rounded-full bg-[var(--color-signal-green)] animate-pulse" />
          <span className="text-xs font-bold tracking-[0.2em] text-[var(--color-text-muted)]">
            {T.heroLabel}
          </span>
          <span className="ml-auto text-[10px] text-[var(--color-signal-green)]">
            ● {events.length > 0 ? "LIVE" : "STANDBY"}
          </span>
        </div>
        <p className="hidden sm:block text-xs text-[var(--color-text-muted)] max-w-xl leading-relaxed">{T.heroSub}</p>
      </div>

      <div className="flex flex-col lg:flex-row items-stretch">

        {/* Network SVG — client-only to prevent hydration mismatch */}
        <div className="flex-1 flex items-center justify-center px-4 pb-4" style={{ minHeight: "clamp(220px, 45vw, 360px)" }}>
          {!mounted ? (
            <div style={{ width: W, height: H, maxHeight: 420 }} />
          ) : (
            <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-lg" style={{ maxHeight: 420 }}>
              <defs>
                <filter id="glow2">
                  <feGaussianBlur stdDeviation="3" result="blur" />
                  <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
                </filter>
                <radialGradient id="cg2" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="#1E3A5F" />
                  <stop offset="100%" stopColor="#0A1628" />
                </radialGradient>
              </defs>

              {OUTER_NODES.map((node, i) => {
                const angle = (i / OUTER_NODES.length) * 360 - 90;
                const nx = cx + R_OUTER * Math.cos(toRad(angle));
                const ny = cy + R_OUTER * Math.sin(toRad(angle));
                const isActive = activeIds.has(node.id);
                const d = `M ${nx} ${ny} L ${cx} ${cy}`;
                return (
                  <g key={node.id}>
                    <path d={d} stroke={isActive ? REGIONAL_COLOR : "#1A2640"}
                      strokeWidth={isActive ? 1.2 : 0.5} strokeDasharray={isActive ? "3 4" : "1 5"}
                      fill="none" opacity={isActive ? 0.8 : 0.2}
                      style={{ transition: "stroke 0.4s, opacity 0.4s" }} />
                    {isActive && (
                      <circle r="2.5" fill={REGIONAL_COLOR} filter="url(#glow2)" opacity="0.9">
                        <animateMotion dur="1.4s" repeatCount="indefinite" path={d} />
                      </circle>
                    )}
                  </g>
                );
              })}

              {INNER_NODES.map((node, i) => {
                const angle = (i / INNER_NODES.length) * 360 - 90 + 20;
                const nx = cx + R_INNER * Math.cos(toRad(angle));
                const ny = cy + R_INNER * Math.sin(toRad(angle));
                const isActive = activeIds.has(node.id);
                const d = `M ${nx} ${ny} L ${cx} ${cy}`;
                return (
                  <g key={node.id}>
                    <path d={d} stroke={isActive ? node.color : "#1E2D42"}
                      strokeWidth={isActive ? 1.5 : 0.8} strokeDasharray={isActive ? "4 4" : "2 6"}
                      fill="none" opacity={isActive ? 0.9 : 0.35}
                      style={{ transition: "stroke 0.4s, opacity 0.4s" }} />
                    {isActive && (
                      <circle r="3" fill={node.color} filter="url(#glow2)" opacity="0.9">
                        <animateMotion dur="1.0s" repeatCount="indefinite" path={d} />
                      </circle>
                    )}
                  </g>
                );
              })}

              {/* Chief */}
              <circle cx={cx} cy={cy} r={pulseCenter ? 32 : 28} fill="url(#cg2)" stroke="#C9A84C"
                strokeWidth={pulseCenter ? 2 : 1.5} filter={pulseCenter ? "url(#glow2)" : undefined}
                style={{ transition: "r 0.3s" }} />
              {pulseCenter && (
                <circle cx={cx} cy={cy} r="38" fill="none" stroke="#C9A84C" strokeWidth="1" opacity="0.3">
                  <animate attributeName="r" values="30;48" dur="0.8s" repeatCount="1" />
                  <animate attributeName="opacity" values="0.5;0" dur="0.8s" repeatCount="1" />
                </circle>
              )}
              <text x={cx} y={cy - 6} textAnchor="middle" fontSize="8" fill="#C9A84C" fontWeight="700" letterSpacing="1">CHIEF</text>
              <text x={cx} y={cy + 6} textAnchor="middle" fontSize="6.5" fill="#8BA0BC" letterSpacing="0.5">ORCHESTRATOR</text>

              {INNER_NODES.map((node, i) => {
                const angle = (i / INNER_NODES.length) * 360 - 90 + 20;
                const nx = cx + R_INNER * Math.cos(toRad(angle));
                const ny = cy + R_INNER * Math.sin(toRad(angle));
                const isActive = activeIds.has(node.id);
                return (
                  <g key={node.id}>
                    {isActive && (
                      <circle cx={nx} cy={ny} r="16" fill="none" stroke={node.color} strokeWidth="1" opacity="0.4">
                        <animate attributeName="r" values="13;20" dur="1.5s" repeatCount="indefinite" />
                        <animate attributeName="opacity" values="0.5;0" dur="1.5s" repeatCount="indefinite" />
                      </circle>
                    )}
                    <circle cx={nx} cy={ny} r="13" fill="#0D1F3C"
                      stroke={isActive ? node.color : "#1E2D42"} strokeWidth={isActive ? 1.5 : 1}
                      filter={isActive ? "url(#glow2)" : undefined} style={{ transition: "stroke 0.4s" }} />
                    <text x={nx} y={ny + 1} textAnchor="middle" fontSize="11" dominantBaseline="middle">{node.icon}</text>
                  </g>
                );
              })}

              {OUTER_NODES.map((node, i) => {
                const angle = (i / OUTER_NODES.length) * 360 - 90;
                const nx = cx + R_OUTER * Math.cos(toRad(angle));
                const ny = cy + R_OUTER * Math.sin(toRad(angle));
                const isActive = activeIds.has(node.id);
                return (
                  <g key={node.id}>
                    {isActive && (
                      <circle cx={nx} cy={ny} r="11" fill="none" stroke={REGIONAL_COLOR} strokeWidth="0.8" opacity="0.4">
                        <animate attributeName="r" values="9;14" dur="1.5s" repeatCount="indefinite" />
                        <animate attributeName="opacity" values="0.5;0" dur="1.5s" repeatCount="indefinite" />
                      </circle>
                    )}
                    <circle cx={nx} cy={ny} r="9" fill="#0D1F3C"
                      stroke={isActive ? REGIONAL_COLOR : "#1E2D42"} strokeWidth={isActive ? 1.2 : 0.8}
                      filter={isActive ? "url(#glow2)" : undefined} style={{ transition: "stroke 0.4s" }} />
                    <text x={nx} y={ny + 1} textAnchor="middle" fontSize="6.5" dominantBaseline="middle"
                      fill={isActive ? REGIONAL_COLOR : "#6B839E"} fontWeight="600" letterSpacing="0.3">
                      {node.label}
                    </text>
                  </g>
                );
              })}
            </svg>
          )}
        </div>

        {/* Real Activity Feed */}
        <div className="w-full lg:w-80 border-t lg:border-t-0 lg:border-l flex flex-col" style={{ borderColor: "#112952" }}>
          <div className="px-4 py-3 border-b flex items-center justify-between" style={{ borderColor: "#112952" }}>
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-signal-green)] animate-pulse" />
              <span className="text-xs font-bold tracking-[0.15em] text-[var(--color-text-muted)]">
                {T.activityFeed}
              </span>
            </div>
            <span className="text-[9px] text-[var(--color-text-muted)]">↻ 3s</span>
          </div>
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2" style={{ maxHeight: liveTab ? "min(600px, 60vh)" : "min(360px, 50vh)" }}>
            {events.length === 0 ? (
              <p className="text-xs text-[var(--color-text-muted)] animate-pulse">
                Waiting for activity…
              </p>
            ) : (
              events.slice(0, liveTab ? 30 : 15).map((e, i) => (
                <div key={`${e.id}-${i}`} className="flex items-start gap-2 animate-fade-in">
                  <span className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0"
                    style={{ backgroundColor: agentColorFromEvent(e) }} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] font-semibold shrink-0"
                        style={{ color: agentColorFromEvent(e) }}>
                        {e.agent}
                      </span>
                      {e.status === "ok" && <span className="text-[9px] text-[var(--color-signal-green)]">✓</span>}
                      {e.status === "warn" && <span className="text-[9px] text-[var(--color-gold)]">⚠</span>}
                    </div>
                    <p className="text-xs text-[var(--color-text-muted)] leading-snug break-words">{e.message}</p>
                  </div>
                  <span className="text-[9px] text-[#2A3E57] shrink-0 pt-0.5">
                    {new Date(e.ts * 1000).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Status bar */}
      <div className="flex items-center gap-3 px-4 sm:px-6 py-2.5 border-t text-[10px]" style={{ borderColor: "#112952" }}>
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-signal-green)] animate-pulse" />
          <span className="text-[var(--color-signal-green)] font-semibold">{T.systemActive}</span>
        </div>
        <span className="text-[var(--color-text-muted)] hidden sm:inline">21 {T.agentsOnline} · 9 specialists + 12 regional</span>
        <span className="text-[var(--color-text-muted)] sm:hidden">21 {T.agentsOnline}</span>
        <span className="text-[var(--color-text-muted)] ml-auto">{T.nextCycle}: 16:30 KST</span>
      </div>
    </div>
  );
}
