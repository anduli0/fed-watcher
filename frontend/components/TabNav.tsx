"use client";
import { useLang } from "@/context/LanguageContext";

export type Tab =
  | "today" | "live" | "forecast" | "agents" | "analysis" | "data"
  | "briefing" | "track" | "trading";

// Ordered by importance: daily-use tabs first, reference material last.
const TABS: { id: Tab; en: string; ko: string; icon: string }[] = [
  { id: "today",    en: "Today",        ko: "오늘",         icon: "☀️" },
  { id: "forecast", en: "Forecast",     ko: "금리예측",     icon: "📈" },
  { id: "briefing", en: "Daily Brief",  ko: "데일리 브리프", icon: "📰" },
  { id: "track",    en: "Track Record", ko: "적중기록",     icon: "🎯" },
  { id: "trading",  en: "Trading",      ko: "트레이딩",     icon: "💼" },
  { id: "live",     en: "Live",         ko: "실시간",       icon: "⚡" },
  { id: "agents",   en: "Agents",       ko: "에이전트",     icon: "🤖" },
  { id: "data",     en: "Data",         ko: "데이터",       icon: "📊" },
  { id: "analysis", en: "Analysis",     ko: "분석",         icon: "🔬" },
];

interface Props {
  active: Tab;
  onChange: (t: Tab) => void;
}

export default function TabNav({ active, onChange }: Props) {
  const { lang } = useLang();
  return (
    // Sticky on mobile so the tab strip stays pinned while content scrolls;
    // overscroll containment + snap keep horizontal drags on the tabs instead
    // of sliding the strip (or the page) into empty space.
    <nav
      className="tabnav flex gap-1 border-b mb-6 overflow-x-auto scrollbar-none sticky top-0 z-30 select-none"
      style={{
        borderColor: "var(--color-navy-700)",
        background: "var(--color-navy)",
        overscrollBehaviorX: "contain",
        touchAction: "pan-x",
        scrollSnapType: "x proximity",
        WebkitTapHighlightColor: "transparent",
      }}
    >
      {TABS.map(t => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className="flex items-center gap-1.5 px-3 sm:px-4 py-2.5 text-xs font-medium transition-all relative whitespace-nowrap shrink-0"
          style={{
            scrollSnapAlign: "start",
            color: active === t.id ? "var(--color-text-primary)" : "var(--color-text-muted)",
            borderBottom: active === t.id
              ? "2px solid var(--color-gold)"
              : "2px solid transparent",
            marginBottom: "-1px",
          }}
        >
          <span>{t.icon}</span>
          <span>{lang === "ko" ? t.ko : t.en}</span>
        </button>
      ))}
    </nav>
  );
}
