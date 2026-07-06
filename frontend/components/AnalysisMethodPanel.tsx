"use client";
import { useLang } from "@/context/LanguageContext";

const AGENT_DESCRIPTIONS = {
  en: [
    {
      id: 1, name: "Behavioral Analysis", icon: "👁",
      how: "Analyzes Fed Chair body language, facial tension, and vocal patterns during press conferences. Confidence intervals, micro-expressions, and speech hesitation patterns signal unspoken policy uncertainty.",
      weight: "0.8×", color: "#C9A84C",
    },
    {
      id: 2, name: "NLP Sentiment", icon: "💬",
      how: "Scores every word in Fed speeches using a hawkish/dovish lexicon. Speaker-weighted: Chair counts 3×, Vice Chair 2×, Governors 1.5×. Tracks language drift across consecutive speeches.",
      weight: "1.2×", color: "#38A169",
    },
    {
      id: 3, name: "Historical Cycles", icon: "📚",
      how: "Matches current macro conditions against 9 historical FOMC cycles (1994, 1999, 2004, 2015, 2022 tightening; 2001, 2007, 2019, 2020 easing). Infers rate path by analogy.",
      weight: "0.9×", color: "#4A90D9",
    },
    {
      id: 4, name: "Taylor Rule", icon: "📐",
      how: "Calculates the neutral rate via r* = 2.5 + π + 0.5(π − 2.0) + 0.5(output gap). Compares the theoretical rate to the actual Fed Funds Rate to quantify policy restrictiveness.",
      weight: "1.1×", color: "#C9A84C",
    },
    {
      id: 5, name: "Dot Plot & Beige Book", icon: "🔭",
      how: "Decodes the FOMC's Summary of Economic Projections — median dot, dispersion, and trajectory. Cross-references Beige Book district conditions for regional divergence signals.",
      weight: "1.1×", color: "#9F7AEA",
    },
    {
      id: 6, name: "FOMC Minutes", icon: "📄",
      how: "Counts hawkish vs. dovish passages in the latest 3 meeting minutes. Tracks vote-indicator language: 'several members', 'a few participants', 'all members agreed'. Measures language drift between meetings.",
      weight: "1.3×", color: "#E53E3E",
    },
    {
      id: 7, name: "FRED Macro Data", icon: "📊",
      how: "Processes 10 hard data series from the Federal Reserve Economic Database: CPI, PCE, NFP, unemployment, 2Y/10Y yields, breakeven inflation, SOFR, and the yield curve spread.",
      weight: "1.4×", color: "#38A169",
    },
    {
      id: 8, name: "Political Economy", icon: "🏛",
      how: "Operates under a 'partial independence' framework. Monitors White House rhetoric, Congressional hearing pressure, Treasury coordination, and election-cycle dynamics that may constrain Fed decision-making.",
      weight: "0.9×", color: "#4A6080",
    },
    {
      id: 9, name: "Regional Fed Presidents", icon: "🗺",
      how: "Maps the current policy stance of all 12 Regional Fed Presidents. Tracks voting rotation, recent speeches, and dissent probability. A >3 hawk/dove imbalance among voters is a leading indicator.",
      weight: "1.0×", color: "#C9A84C",
    },
    {
      id: 10, name: "Market Consensus", icon: "🏦",
      how: "Synthesizes CME FedWatch implied probabilities and Wall Street bank rate targets. When market-implied path diverges from Fed guidance, this signals either a policy error or a credibility gap. Weight: 1.5× premium.",
      weight: "1.5×", color: "#4A90D9",
    },
  ],
  ko: [
    {
      id: 1, name: "행동 분석", icon: "👁",
      how: "기자회견에서 연준 의장의 신체 언어, 표정 긴장도, 발화 패턴을 분석합니다. 망설임, 미세 표정, 음성 패턴의 변화는 명시적 발언보다 앞선 정책 불확실성 신호입니다.",
      weight: "0.8×", color: "#C9A84C",
    },
    {
      id: 2, name: "NLP 감성", icon: "💬",
      how: "연준 연설의 모든 단어를 매파/비둘기 어휘 사전으로 점수화합니다. 화자 가중치: 의장 3×, 부의장 2×, 이사 1.5×. 연속 연설 간 언어 변화 추이를 추적합니다.",
      weight: "1.2×", color: "#38A169",
    },
    {
      id: 3, name: "역사적 사이클", icon: "📚",
      how: "현재 거시경제 조건을 9개 역사적 FOMC 사이클과 매칭합니다 (1994, 1999, 2004, 2015, 2022 긴축; 2001, 2007, 2019, 2020 완화). 유사 사이클 분석으로 금리 경로를 추론합니다.",
      weight: "0.9×", color: "#4A90D9",
    },
    {
      id: 4, name: "테일러 준칙", icon: "📐",
      how: "테일러 준칙으로 중립금리를 계산합니다: r* = 2.5 + π + 0.5(π − 2.0) + 0.5(산출 갭). 이론값 대비 실제 기준금리를 비교해 정책 제약 정도를 수치화합니다.",
      weight: "1.1×", color: "#C9A84C",
    },
    {
      id: 5, name: "점도표 & 베이지북", icon: "🔭",
      how: "FOMC 경제전망보고서(SEP)의 점도표 중앙값, 분산, 경로를 해독합니다. 베이지북 지역별 경기 여건과 교차 분석해 지역 편차 신호를 포착합니다.",
      weight: "1.1×", color: "#9F7AEA",
    },
    {
      id: 6, name: "FOMC 의사록", icon: "📄",
      how: "최근 3회 FOMC 의사록에서 매파/비둘기 문구를 계수화합니다. '여러 위원', '일부 참석자', '모든 위원 동의' 등 투표 신호 언어를 추적하고 회의 간 언어 변화를 측정합니다.",
      weight: "1.3×", color: "#E53E3E",
    },
    {
      id: 7, name: "거시경제 데이터", icon: "📊",
      how: "FRED API에서 10개 시계열을 처리합니다: CPI, PCE, 비농업취업자수, 실업률, 2Y/10Y 금리, 브레이크이븐 인플레이션, SOFR, 수익률 곡선 스프레드.",
      weight: "1.4×", color: "#38A169",
    },
    {
      id: 8, name: "정치경제", icon: "🏛",
      how: "'부분적·제약된 독립성' 프레임워크로 운영됩니다. 백악관 발언, 의회 청문회 압력, 재무부 조율 신호, 선거 주기 역학을 모니터링합니다.",
      weight: "0.9×", color: "#4A6080",
    },
    {
      id: 9, name: "지역 연준", icon: "🗺",
      how: "12개 지역 연준 총재의 현재 정책 기조를 매핑합니다. 투표 로테이션, 최근 연설, 반대 투표 확률을 추적합니다. 현 투표권자 중 매파/비둘기 불균형 3명 이상은 선행 지표입니다.",
      weight: "1.0×", color: "#C9A84C",
    },
    {
      id: 10, name: "시장 컨센서스", icon: "🏦",
      how: "CME FedWatch 내재 확률과 월가 은행 금리 전망을 종합합니다. 시장 내재 경로와 연준 가이던스의 괴리는 정책 오류 또는 신뢰 격차 신호입니다. 가중치 1.5× 프리미엄.",
      weight: "1.5×", color: "#4A90D9",
    },
  ],
};

export default function AnalysisMethodPanel() {
  const { lang, T } = useLang();
  const descs = AGENT_DESCRIPTIONS[lang];

  return (
    <div className="card">
      <p className="text-xs text-[var(--color-text-muted)] uppercase tracking-widest mb-5">
        {lang === "en" ? "How The Forecast Is Built — 21-Agent Architecture" : "예측 생성 방법 — 21에이전트 아키텍처"}
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {descs.map(d => (
          <div key={d.id} className="rounded-lg p-3.5" style={{ background: "var(--color-navy-700)", border: `1px solid ${d.color}22` }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-base">{d.icon}</span>
              <span className="text-xs font-semibold" style={{ color: d.color }}>
                {d.id}. {d.name}
              </span>
              <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded"
                style={{ background: `${d.color}22`, color: d.color }}>
                {d.weight}
              </span>
            </div>
            <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">{d.how}</p>
          </div>
        ))}
      </div>

      {/* Aggregation explanation */}
      <div className="mt-4 p-4 rounded-lg" style={{ background: "var(--color-navy-700)", border: "1px solid #C9A84C33" }}>
        <p className="text-xs font-semibold text-[var(--color-gold)] mb-2">
          {lang === "en" ? "⚡ Aggregation & Stabilization Logic" : "⚡ 집계 및 안정화 로직"}
        </p>
        <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">
          {lang === "en"
            ? "Each agent outputs a rate path delta (bps) and confidence score. The Chief Orchestrator applies a weighted average, shrunk toward the market-implied prior in proportion to committee dispersion (the backtest shows the market signal is hardest to beat when the committee disagrees). The result passes through a 6-stage stabilizer: (1) EMA smoothing — α=0.25 normal, α=0.60 on FOMC/CPI/NFP days; (2) Half-quantum gate — changes under 12.5 bps are discarded as noise; (3) Conviction gate — low-confidence signals blocked unless it's an event day; (4) 25 bps quantization; (5) 1σ conviction band — if the committee's ±1σ band straddles zero the call publishes as NEUTRAL (on-hold regimes are the engine's historical weak spot); (6) confidence calibration — published confidence never exceeds the weighted share of agents agreeing with the call."
            : "각 에이전트는 금리 경로 변화(bps)와 신뢰도를 출력합니다. 수석 오케스트레이터가 가중 평균을 계산하되, 위원회 분산에 비례해 시장내재 프라이어 쪽으로 수축합니다(백테스트상 위원회가 분열될수록 시장 시그널이 우세). 결과는 6단계 안정화 파이프라인을 거칩니다: (1) EMA 스무딩 — 평시 α=0.25, FOMC/CPI/NFP 당일 α=0.60; (2) 하프-퀀텀 게이트 — 12.5 bps 미만 변화는 노이즈로 폐기; (3) 컨빅션 게이트 — 저신뢰 신호는 이벤트일 외 차단; (4) 25 bps 양자화; (5) 1σ 컨빅션 밴드 — 위원회 ±1σ 밴드가 0을 걸치면 중립 발행 (동결기가 엔진의 역사적 약점); (6) 신뢰도 캘리브레이션 — 발행 신뢰도는 콜에 동의하는 가중 비율을 초과할 수 없음."
          }
        </p>
      </div>
    </div>
  );
}
