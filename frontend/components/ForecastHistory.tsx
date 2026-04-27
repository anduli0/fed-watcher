"use client";
import { useState } from "react";
import { ForecastHistoryItem } from "@/lib/api";
import { useLang } from "@/context/LanguageContext";

export default function ForecastHistory({ history }: { history: ForecastHistoryItem[] }) {
  const [open, setOpen] = useState(false);
  const { T } = useLang();

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
      >
        {open ? T.hideHistory : T.viewHistory}
      </button>
      {open && (
        <div className="mt-3 space-y-1.5 max-h-52 overflow-y-auto pr-1">
          {history.map((item, i) => (
            <div key={i} className="flex items-start gap-3 text-xs py-1.5 border-b border-[var(--color-navy-700)]">
              <span className="text-[var(--color-text-muted)] w-20 shrink-0">{item.date}</span>
              <span className={item.published_delta_bps < 0 ? "text-[var(--color-signal-green)]" : item.published_delta_bps > 0 ? "text-[var(--color-signal-red)]" : "text-[var(--color-gold)]"}>
                {item.published_delta_bps > 0 ? "+" : ""}{item.published_delta_bps.toFixed(0)} bps
              </span>
              <span className="text-[var(--color-text-muted)] flex-1">{item.change_justification ?? "—"}</span>
            </div>
          ))}
          {history.length === 0 && (
            <p className="text-[var(--color-text-muted)]">No history yet.</p>
          )}
        </div>
      )}
    </div>
  );
}
