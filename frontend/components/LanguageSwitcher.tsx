"use client";
import { useLang } from "@/context/LanguageContext";

export default function LanguageSwitcher() {
  const { lang, setLang } = useLang();

  return (
    <div className="flex items-center gap-1">
      {/* Globe icon */}
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
        className="text-[var(--color-text-muted)]">
        <circle cx="12" cy="12" r="10" />
        <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
      </svg>
      <button
        onClick={() => setLang("en")}
        className="text-xs px-1.5 py-0.5 rounded transition-colors"
        style={{
          color: lang === "en" ? "var(--color-gold)" : "var(--color-text-muted)",
          fontWeight: lang === "en" ? 600 : 400,
        }}
      >
        EN
      </button>
      <span className="text-[var(--color-navy-700)] text-xs">|</span>
      <button
        onClick={() => setLang("ko")}
        className="text-xs px-1.5 py-0.5 rounded transition-colors"
        style={{
          color: lang === "ko" ? "var(--color-gold)" : "var(--color-text-muted)",
          fontWeight: lang === "ko" ? 600 : 400,
        }}
      >
        KO
      </button>
    </div>
  );
}
