"use client";
import { useState } from "react";
import { AgentStatus } from "@/lib/api";
import { useLang } from "@/context/LanguageContext";

const SPEC_ICONS: Record<string, string> = {
  Behavioral: "👁", NLP: "💬", History: "📚", Academic: "📐",
  Projections: "🔭", FOMC_Minutes: "📄", Macro_Data: "📊",
  Political_Economy: "🏛", Consensus: "🏦",
};

const SPEC_DESC: Record<string, { en: string; ko: string }> = {
  Behavioral:        { en: "Body language & vocal tone analysis",       ko: "신체 언어 및 발화 패턴 분석" },
  NLP:               { en: "Speech sentiment scoring (speaker-weighted)", ko: "연설 감성 점수화 (화자 가중)" },
  History:           { en: "Historical cycle pattern matching",          ko: "역사적 사이클 패턴 매칭" },
  Academic:          { en: "Taylor Rule neutral rate calculation",        ko: "테일러 준칙 중립금리 계산" },
  Projections:       { en: "Dot Plot & Beige Book decoding",             ko: "점도표 & 베이지북 해독" },
  FOMC_Minutes:      { en: "Hawkish/dovish balance extraction",          ko: "매파/비둘기 균형 추출" },
  Macro_Data:        { en: "FRED hard data processing (10 series)",      ko: "FRED 경제지표 처리 (10개 시계열)" },
  Political_Economy: { en: "Institutional pressure & election dynamics",  ko: "제도적 압력 및 선거 역학" },
  Consensus:         { en: "CME FedWatch + Wall St. synthesis (1.5×)",   ko: "CME FedWatch + 월가 종합 (1.5×)" },
};

function bankFromName(name: string): string {
  // Boston_Fed → Boston, NewYork_Fed → New York
  return name.replace("_Fed", "").replace(/([A-Z])/g, " $1").trim();
}

export default function AgentStatusGrid({ agents }: { agents: AgentStatus[] }) {
  const { lang, T } = useLang();
  const [expanded, setExpanded] = useState<number | null>(null);

  const specialists = agents.filter(a => a.agent_id < 100);
  const regionals   = agents.filter(a => a.agent_id >= 100);

  return (
    <div className="space-y-4">
      {/* Specialists */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest">
            {T.agentStatus} — {lang === "en" ? "Specialists" : "전문 분석"}
          </p>
          <span className="text-[10px] text-[var(--color-text-muted)]">
            {specialists.length}/9
          </span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-5 gap-2">
          {specialists.map(a => (
            <SpecialistCard key={a.agent_id} a={a} expanded={expanded} onClick={setExpanded} lang={lang} T={T} />
          ))}
          {specialists.length === 0 && (
            <p className="col-span-5 text-sm text-[var(--color-text-muted)]">{T.awaitingCycle}</p>
          )}
        </div>
      </div>

      {/* Regional Feds */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest">
            {lang === "en" ? "12 Regional Fed Agents" : "12개 지역 연준 에이전트"}
          </p>
          <span className="text-[10px] text-[var(--color-text-muted)]">
            {regionals.length}/12
          </span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          {regionals.map(a => (
            <RegionalCard key={a.agent_id} a={a} expanded={expanded} onClick={setExpanded} lang={lang} T={T} />
          ))}
        </div>
        {agents.length > 0 && (
          <p className="text-[10px] text-[var(--color-text-muted)] mt-3">
            {lang === "en" ? "Click any card for details and 4-horizon view" : "카드를 클릭하면 4시계열 상세 정보가 표시됩니다"}
          </p>
        )}
      </div>
    </div>
  );
}


function HorizonGrid({ a, lang }: { a: AgentStatus; lang: "en" | "ko" }) {
  const HORIZONS: Array<["6m" | "12m" | "3y" | "10y", string]> = [
    ["6m", lang === "en" ? "6M" : "6개월"],
    ["12m", "1Y"],
    ["3y", lang === "en" ? "3Y" : "3년"],
    ["10y", lang === "en" ? "10Y" : "10년"],
  ];
  return (
    <div className="grid grid-cols-2 gap-1.5 mt-2">
      {HORIZONS.map(([h, lbl]) => {
        const hor = a.horizons?.[h];
        const d = hor?.delta_bps ?? 0;
        const c = hor?.confidence ?? 0;
        return (
          <div key={h} className="flex items-center gap-1.5 text-[10px]">
            <span className="text-[var(--color-text-muted)] w-7">{lbl}</span>
            <span style={{ color: d < 0 ? "var(--color-signal-green)" : d > 0 ? "var(--color-signal-red)" : "var(--color-gold)" }}>
              {d > 0 ? "+" : ""}{d.toFixed(0)}
            </span>
            <span className="text-[var(--color-text-muted)] ml-auto">{(c * 100).toFixed(0)}%</span>
          </div>
        );
      })}
    </div>
  );
}


function SpecialistCard({ a, expanded, onClick, lang, T }: { a: AgentStatus; expanded: number | null; onClick: (id: number | null) => void; lang: "en" | "ko"; T: any }) {
  const isExp = expanded === a.agent_id;
  const desc = SPEC_DESC[a.agent_name];
  return (
    <div
      className="rounded-lg p-3 cursor-pointer transition-all"
      style={{
        background: isExp ? "var(--color-slate)" : "var(--color-navy-700)",
        border: `1px solid ${isExp ? "var(--color-slate-400)" : "transparent"}`,
      }}
      onClick={() => onClick(isExp ? null : a.agent_id)}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-base">{SPEC_ICONS[a.agent_name] ?? "🤖"}</span>
        <div className="flex items-center gap-1">
          {a.limited_mode && <span className="badge-limited">LIMITED</span>}
          {a.round === 2 && <span className="text-[9px] text-[var(--color-gold)] font-bold">R2</span>}
          <span className="text-[9px] text-[var(--color-text-muted)]">#{a.agent_id}</span>
        </div>
      </div>
      <p className="text-xs font-medium text-[var(--color-text-primary)] leading-tight mb-1">
        {T.agents[a.agent_name as keyof typeof T.agents] ?? a.agent_name.replace("_", " ")}
      </p>
      <p className={`text-xs font-semibold mb-2 ${
        a.signal === "hawkish" ? "badge-hawkish" : a.signal === "dovish" ? "badge-dovish" : "badge-neutral"
      }`}>
        {a.signal === "hawkish" ? T.hawkish : a.signal === "dovish" ? T.dovish : T.neutral}
      </p>
      <div className="flex items-center gap-1">
        <div className="flex-1 h-1 bg-[var(--color-navy-800)] rounded-full overflow-hidden">
          <div
            className="h-full rounded-full"
            style={{
              width: `${a.confidence * 100}%`,
              backgroundColor: a.confidence >= 0.65 ? "var(--color-signal-green)" :
                a.confidence >= 0.4 ? "var(--color-gold)" : "var(--color-slate-400)",
            }}
          />
        </div>
        <span className="text-[10px] text-[var(--color-text-muted)]">
          {(a.confidence * 100).toFixed(0)}%
        </span>
      </div>
      {isExp && (
        <>
          <HorizonGrid a={a} lang={lang} />
          {desc && (
            <p className="text-[10px] text-[var(--color-text-muted)] leading-relaxed mt-2 pt-2 border-t border-[var(--color-navy-800)]">
              {desc[lang]}
            </p>
          )}
          <p className="text-[9px] text-[var(--color-text-muted)] mt-1">
            {lang === "en" ? `Duration: ${a.duration_ms}ms` : `처리 시간: ${a.duration_ms}ms`}
          </p>
        </>
      )}
    </div>
  );
}


function RegionalCard({ a, expanded, onClick, lang, T }: { a: AgentStatus; expanded: number | null; onClick: (id: number | null) => void; lang: "en" | "ko"; T: any }) {
  const isExp = expanded === a.agent_id;
  const bank = bankFromName(a.agent_name);
  return (
    <div
      className="rounded-lg p-2.5 cursor-pointer transition-all"
      style={{
        background: isExp ? "var(--color-slate)" : "var(--color-navy-700)",
        border: `1px solid ${isExp ? "var(--color-slate-400)" : "transparent"}`,
      }}
      onClick={() => onClick(isExp ? null : a.agent_id)}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-[var(--color-text-muted)]">🗺 {bank}</span>
        <div className="flex items-center gap-1">
          {a.round === 2 && <span className="text-[9px] text-[var(--color-gold)] font-bold">R2</span>}
        </div>
      </div>
      <p className={`text-xs font-semibold mb-1 ${
        a.signal === "hawkish" ? "badge-hawkish" : a.signal === "dovish" ? "badge-dovish" : "badge-neutral"
      }`}>
        {a.signal === "hawkish" ? T.hawkish : a.signal === "dovish" ? T.dovish : T.neutral}
      </p>
      <div className="flex items-center gap-1">
        <div className="flex-1 h-0.5 bg-[var(--color-navy-800)] rounded-full overflow-hidden">
          <div className="h-full rounded-full" style={{
            width: `${a.confidence * 100}%`,
            backgroundColor: a.confidence >= 0.65 ? "var(--color-signal-green)" :
              a.confidence >= 0.4 ? "var(--color-gold)" : "var(--color-slate-400)",
          }} />
        </div>
        <span className="text-[9px] text-[var(--color-text-muted)]">
          {(a.confidence * 100).toFixed(0)}%
        </span>
      </div>
      {isExp && <HorizonGrid a={a} lang={lang} />}
    </div>
  );
}
