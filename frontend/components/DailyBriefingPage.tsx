"use client";
import { useState } from "react";
import { useLang } from "@/context/LanguageContext";
import { useLatestBriefing, useBriefingList, useBriefingByDate } from "@/hooks/useBriefing";
import { DailyBriefing, BriefingListItem } from "@/lib/api";

// ── Small utilities ─────────────────────────────────────────────────────────

function fmt(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-GB", {
      timeZone: "Asia/Seoul",
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    }) + " KST";
  } catch { return iso; }
}

function fmtDate(d: string): string {
  try {
    return new Date(d + "T00:00:00").toLocaleDateString("en-GB", { month: "short", day: "numeric", year: "numeric" });
  } catch { return d; }
}

// ── Section card ─────────────────────────────────────────────────────────────

function SectionCard({ heading, body }: { heading: string; body: string }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="card mb-3">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between mb-2"
      >
        <span className="text-sm font-semibold text-[var(--color-gold)] uppercase tracking-wide">
          {heading}
        </span>
        <span className="text-[var(--color-text-muted)] text-xs">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="text-sm text-[var(--color-text-muted)] leading-relaxed whitespace-pre-line">
          {body}
        </div>
      )}
    </div>
  );
}

// ── Bullet list card ─────────────────────────────────────────────────────────

function BulletCard({ title, items, accentColor }: { title: string; items: string[]; accentColor?: string }) {
  if (!items?.length) return null;
  const color = accentColor || "var(--color-gold)";
  return (
    <div className="card mb-3">
      <p className="text-xs font-bold uppercase tracking-widest mb-2" style={{ color }}>
        {title}
      </p>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-2 text-sm text-[var(--color-text-muted)]">
            <span className="shrink-0 mt-0.5 w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── Source list ─────────────────────────────────────────────────────────────

function SourceList({ sources, label }: { sources: DailyBriefing["sources"]; label: string }) {
  const [open, setOpen] = useState(false);
  if (!sources?.length) return null;
  return (
    <div className="card mb-3">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between"
      >
        <span className="text-xs font-bold uppercase tracking-widest text-[var(--color-text-muted)]">
          {label} ({sources.length})
        </span>
        <span className="text-[var(--color-text-muted)] text-xs">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <ul className="mt-3 space-y-2">
          {sources.map((s, i) => (
            <li key={i} className="text-xs">
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[var(--color-gold)] hover:underline leading-snug"
              >
                {s.title}
              </a>
              <span className="text-[var(--color-text-muted)] ml-1.5">
                · {s.publisher}
                {s.published_at ? ` · ${new Date(s.published_at).toLocaleDateString()}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Briefing full view ────────────────────────────────────────────────────────

function BriefingView({ b, T }: { b: DailyBriefing; T: ReturnType<typeof useLang>["T"] }) {
  return (
    <div className="space-y-0">
      {/* Header */}
      <div className="card mb-3">
        {b.fallback && (
          <div className="mb-2 text-xs px-2 py-1 rounded bg-[var(--color-navy-700)] text-[var(--color-gold)] inline-block">
            {T.briefingFallback}
          </div>
        )}
        <h2 className="text-base font-semibold text-[var(--color-text-primary)] leading-snug mb-1">
          {b.title}
        </h2>
        <p
          className="text-sm font-medium mb-3 leading-snug"
          style={{ color: "var(--color-signal-green)" }}
        >
          {b.market_impact_headline}
        </p>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-[var(--color-text-muted)] border-t pt-2"
          style={{ borderColor: "var(--color-navy-700)" }}>
          <span>{T.briefingGeneratedAt}: {fmt(b.generation_finished_at)}</span>
          <span>{b.article_count} {T.briefingArticles} {b.source_count} {T.briefingSources}</span>
          <span>{fmtDate(b.briefing_date)}</span>
        </div>
      </div>

      {/* Executive Summary */}
      <BulletCard
        title={T.briefingExecSummary}
        items={b.executive_summary}
        accentColor="var(--color-gold)"
      />

      {/* Main sections */}
      {b.sections?.map((s, i) => (
        <SectionCard key={i} heading={s.heading} body={s.body} />
      ))}

      {/* What changed */}
      <BulletCard
        title={T.briefingWhatChanged}
        items={b.what_changed_since_yesterday}
        accentColor="var(--color-signal-green)"
      />

      {/* Rate path signal */}
      {b.fed_watcher_rate_path_signal && (
        <div className="card mb-3">
          <p className="text-xs font-bold uppercase tracking-widest text-[var(--color-signal-red)] mb-2">
            {T.briefingRateSignal}
          </p>
          <p className="text-sm text-[var(--color-text-muted)] leading-relaxed">
            {b.fed_watcher_rate_path_signal}
          </p>
        </div>
      )}

      {/* Watch next */}
      <BulletCard
        title={T.briefingWatchNext}
        items={b.watch_next}
        accentColor="var(--color-slate-300)"
      />

      {/* Sources */}
      <SourceList sources={b.sources} label={T.briefingSourceList} />

      {/* Disclaimer */}
      <p className="text-[10px] text-[var(--color-text-muted)] leading-relaxed mt-1 px-1">
        ⚠ {b.disclaimer || T.briefingDisclaimer}
      </p>
    </div>
  );
}

// ── Archive sidebar ───────────────────────────────────────────────────────────

function ArchiveSidebar({
  list,
  selectedDate,
  onSelect,
  T,
}: {
  list: BriefingListItem[];
  selectedDate: string | null;
  onSelect: (d: string | null) => void;
  T: ReturnType<typeof useLang>["T"];
}) {
  if (!list.length) return null;
  return (
    <div className="card">
      <p className="text-xs font-bold uppercase tracking-widest text-[var(--color-text-muted)] mb-3">
        {T.briefingArchive}
      </p>
      <ul className="space-y-1">
        <li>
          <button
            onClick={() => onSelect(null)}
            className="w-full text-left text-xs px-2 py-1.5 rounded transition-colors"
            style={{
              background: selectedDate === null ? "var(--color-navy-700)" : "transparent",
              color: selectedDate === null ? "var(--color-gold)" : "var(--color-text-muted)",
            }}
          >
            {T.briefingLatest}
          </button>
        </li>
        {list.map(item => (
          <li key={item.id}>
            <button
              onClick={() => onSelect(item.briefing_date)}
              className="w-full text-left text-xs px-2 py-1.5 rounded transition-colors leading-snug"
              style={{
                background: selectedDate === item.briefing_date ? "var(--color-navy-700)" : "transparent",
                color: selectedDate === item.briefing_date ? "var(--color-gold)" : "var(--color-text-muted)",
              }}
            >
              {fmtDate(item.briefing_date)}
              {item.title && (
                <span className="block text-[10px] truncate opacity-70 mt-0.5">{item.title}</span>
              )}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── Historical briefing view ──────────────────────────────────────────────────

function HistoricalBriefing({ date, lang, T }: { date: string; lang: "en" | "ko"; T: ReturnType<typeof useLang>["T"] }) {
  const { briefing, loading, error } = useBriefingByDate(date, lang);
  if (loading) return <div className="card animate-pulse text-sm text-[var(--color-text-muted)]">{T.briefingGenerating}</div>;
  if (error === "not_found") return <div className="card text-sm text-[var(--color-text-muted)]">{T.briefingNotAvail}</div>;
  if (!briefing) return <div className="card text-sm text-[var(--color-text-muted)]">{T.briefingNotAvail}</div>;
  return <BriefingView b={briefing} T={T} />;
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function DailyBriefingPage() {
  const { T, lang } = useLang();
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const { briefing, loading, error } = useLatestBriefing(lang as "en" | "ko");
  const { list } = useBriefingList(lang as "en" | "ko", 30);

  return (
    <div className="pb-8">
      {/* Page header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest">
            {T.briefingTitle}
          </p>
        </div>
      </div>

      <div className="flex flex-col lg:flex-row gap-4 items-start">
        {/* Main content */}
        <div className="flex-1 min-w-0">
          {selectedDate ? (
            <HistoricalBriefing date={selectedDate} lang={lang as "en" | "ko"} T={T} />
          ) : loading ? (
            <div className="card">
              <div className="animate-pulse space-y-3">
                <div className="h-4 bg-[var(--color-navy-700)] rounded w-3/4" />
                <div className="h-3 bg-[var(--color-navy-700)] rounded w-1/2" />
                <div className="h-3 bg-[var(--color-navy-700)] rounded w-full" />
                <div className="h-3 bg-[var(--color-navy-700)] rounded w-5/6" />
              </div>
              <p className="text-xs text-[var(--color-text-muted)] mt-3 animate-pulse">{T.briefingGenerating}</p>
            </div>
          ) : error ? (
            <div className="card">
              <p className="text-sm text-[var(--color-text-muted)]">{T.briefingFailed}</p>
            </div>
          ) : !briefing ? (
            <div className="card">
              <p className="text-sm text-[var(--color-text-muted)]">{T.briefingEmpty}</p>
            </div>
          ) : (
            <BriefingView b={briefing} T={T} />
          )}
        </div>

        {/* Archive sidebar */}
        <div className="w-full lg:w-52 shrink-0">
          <ArchiveSidebar
            list={list}
            selectedDate={selectedDate}
            onSelect={setSelectedDate}
            T={T}
          />
        </div>
      </div>
    </div>
  );
}
