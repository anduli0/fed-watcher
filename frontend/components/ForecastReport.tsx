"use client";
import { useState } from "react";
import { useLang } from "@/context/LanguageContext";

export default function ForecastReport({ report }: { report: string }) {
  const { T, lang } = useLang();
  const [open, setOpen] = useState(true);

  if (!report) {
    return (
      <div className="card">
        <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest mb-2">
          📋 {T.derivationReport}
        </p>
        <p className="text-xs text-[var(--color-text-muted)]">{T.reportEmpty}</p>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest">
          📋 {T.derivationReport}
        </p>
        <button
          onClick={() => setOpen(!open)}
          className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
        >
          {open ? T.hideReport : T.showReport}
        </button>
      </div>
      {open && (
        <div className="prose prose-sm max-w-none">
          <pre
            className="text-xs leading-relaxed whitespace-pre-wrap font-sans"
            style={{ color: "var(--color-text-muted)", background: "var(--color-navy-700)", padding: "16px", borderRadius: "8px", border: "1px solid var(--color-slate-400)" }}
          >
            {report}
          </pre>
          <p className="text-[10px] text-[var(--color-text-muted)] mt-2 italic">
            {T.collaborationNote}
          </p>
        </div>
      )}
    </div>
  );
}
