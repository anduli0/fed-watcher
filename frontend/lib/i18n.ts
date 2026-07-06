export type Lang = "en" | "ko";

export const t = {
  en: {
    // Header
    title: "FED-WATCHER",
    subtitle: "Macroeconomic Rate Path Intelligence",
    runCycle: "Run Cycle",
    running: "Running…",
    refresh: "Refresh",
    admin: "🔑 Admin",

    // Hero
    heroLabel: "LIVE AGENT NETWORK",
    heroSub: "10 specialized AI agents continuously analyzing Fed communications, macro data, and market signals",
    systemActive: "System Active",
    agentsOnline: "agents online",
    nextCycle: "Next cycle",
    activityFeed: "LIVE ACTIVITY",

    // Forecast
    forecastLabel: "Rate Path Forecast",
    horizon: "12-month horizon",
    confidence: "Confidence",

    // Horizons
    horizonTabs: { "6m": "6 Months", "12m": "1 Year", "3y": "3 Years", "10y": "10 Years" },
    horizonLabels: { "6m": "6-month horizon", "12m": "12-month horizon", "3y": "3-year horizon", "10y": "10-year horizon" },
    horizonNote: "Click any horizon tab above to view that forecast",
    derivationReport: "Derivation Report",
    showReport: "View derivation report",
    hideReport: "Hide report",
    reportEmpty: "Report will appear after the next cycle completes",
    collaborationNote: "Agents collaborated across 2 rounds — outliers reviewed and may have revised",
    forecastUnchanged: "Forecast unchanged for",
    days: "days",
    day: "day",
    nextUpdate: "Next update",
    noForecast: "First forecast publishes at 08:00 KST",
    viewHistory: "View change history",
    hideHistory: "Hide history",

    // Signals
    hawkish: "HAWKISH",
    dovish: "DOVISH",
    neutral: "NEUTRAL",

    // Gauge
    policyStance: "Policy Stance",

    // Agents
    agentStatus: "Agent Status",
    awaitingCycle: "Awaiting first cycle…",

    // Macro
    macroData: "Macro Data",
    noChartData: "No data available",
    loadingChart: "Loading…",

    // First cycle banner
    firstCycleTitle: "⚡ First cycle has not run yet",
    firstCycleDesc: "Click Run Cycle to fetch FRED data, scrape Fed communications, and run all 10 agents. Takes 1–3 minutes.",
    cycleRunning: "Cycle running… results in 1–3 min",
    triggerFailed: "Trigger failed",

    // Agent names
    agents: {
      Behavioral: "Behavioral",
      NLP: "NLP Sentiment",
      History: "Historical Cycles",
      Academic: "Taylor Rule",
      Projections: "Dot Plot",
      FOMC_Minutes: "FOMC Minutes",
      Macro_Data: "Macro Data",
      Political_Economy: "Political Economy",
      Regional: "Regional Feds",
      Consensus: "Market Consensus",
    },

    // Activity feed messages
    activityMessages: [
      { agent: "Macro_Data",      msg: "Fetching FRED DFF, CPI, NFP series…" },
      { agent: "NLP",             msg: "Parsing Fed Chair speech sentiment…" },
      { agent: "FOMC_Minutes",    msg: "Extracting hawkish/dovish balance from minutes…" },
      { agent: "Academic",        msg: "Calculating Taylor Rule neutral rate…" },
      { agent: "Behavioral",      msg: "Analyzing press conference tone patterns…" },
      { agent: "History",         msg: "Matching current cycle to 2004–2006 analog…" },
      { agent: "Regional",        msg: "Scraping 12 Regional Fed President speeches…" },
      { agent: "Consensus",       msg: "Parsing CME FedWatch probabilities…" },
      { agent: "Projections",     msg: "Decoding Dot Plot median and dispersion…" },
      { agent: "Political_Economy", msg: "Assessing institutional pressure signals…" },
      { agent: "Macro_Data",      msg: "FRED returned 365 observations for GS10…" },
      { agent: "NLP",             msg: "Detected 3 hawkish phrases in latest speech…" },
      { agent: "Academic",        msg: "Taylor Rule implies r* = 2.8% vs current 4.33%…" },
      { agent: "FOMC_Minutes",    msg: "Hawkish/dovish ratio: 1.4:1 in latest minutes…" },
      { agent: "Consensus",       msg: "CME FedWatch: 72% probability of hold in June…" },
      { agent: "History",         msg: "Best analog: 2019 mid-cycle adjustment pattern…" },
      { agent: "Orchestrator",    msg: "Aggregating 10 agent signals…" },
      { agent: "Orchestrator",    msg: "Applying EMA stabilization filter…" },
      { agent: "Orchestrator",    msg: "Forecast updated. Next publish: 08:00 KST" },
    ],

    // Daily Briefing
    dailyBrief: "Daily Brief",
    briefingTitle: "Daily Macro Briefing",
    briefingLatest: "Today's Briefing",
    briefingArchive: "Previous Briefings",
    briefingGenerating: "Generating briefing…",
    briefingEmpty: "No briefing yet. Generates automatically each morning at 07:30 KST.",
    briefingFailed: "Last generation failed",
    briefingGeneratedAt: "Generated",
    briefingArticles: "articles from",
    briefingSources: "sources",
    briefingDisclaimer: "AI-generated from public information. Not financial advice.",
    briefingWhatChanged: "What changed since yesterday?",
    briefingRateSignal: "Signal for rate-path analysis",
    briefingWatchNext: "Watch next",
    briefingExecSummary: "Executive Summary",
    briefingMarketImpact: "Market Impact",
    briefingSourceList: "Sources",
    briefingGenerate: "Generate now",
    briefingDate: "Briefing date",
    briefingNotAvail: "No briefing for this date",
    briefingFallback: "Showing available language version",
    briefingSelect: "Select date",
  },

  ko: {
    title: "FED-WATCHER",
    subtitle: "거시경제 금리 경로 분석 시스템",
    runCycle: "사이클 실행",
    running: "실행 중…",
    refresh: "새로고침",
    admin: "🔑 관리자",

    heroLabel: "실시간 에이전트 네트워크",
    heroSub: "10개의 전문 AI 에이전트가 연준 커뮤니케이션, 거시경제 데이터, 시장 신호를 실시간으로 분석합니다",
    systemActive: "시스템 활성",
    agentsOnline: "에이전트 온라인",
    nextCycle: "다음 사이클",
    activityFeed: "실시간 활동",

    forecastLabel: "금리 경로 예측",
    horizon: "12개월 전망",
    confidence: "신뢰도",

    horizonTabs: { "6m": "6개월", "12m": "1년", "3y": "3년", "10y": "10년" },
    horizonLabels: { "6m": "6개월 전망", "12m": "12개월 전망", "3y": "3년 전망", "10y": "10년 전망" },
    horizonNote: "위 탭을 클릭해 다른 시계열을 볼 수 있습니다",
    derivationReport: "도출 보고서",
    showReport: "도출 보고서 보기",
    hideReport: "보고서 숨기기",
    reportEmpty: "다음 사이클이 완료되면 보고서가 표시됩니다",
    collaborationNote: "에이전트들이 2라운드로 협업했습니다 — 이탈 에이전트는 검토 및 수정 가능",
    forecastUnchanged: "예측 유지 중",
    days: "일",
    day: "일",
    nextUpdate: "다음 업데이트",
    noForecast: "첫 예측은 오전 8시 KST에 게시됩니다",
    viewHistory: "변경 이력 보기",
    hideHistory: "이력 숨기기",

    hawkish: "매파",
    dovish: "비둘기파",
    neutral: "중립",

    policyStance: "정책 기조",

    agentStatus: "에이전트 현황",
    awaitingCycle: "첫 번째 사이클 대기 중…",

    macroData: "거시경제 데이터",
    noChartData: "데이터 없음",
    loadingChart: "로딩 중…",

    firstCycleTitle: "⚡ 첫 사이클이 아직 실행되지 않았습니다",
    firstCycleDesc: "사이클 실행 버튼을 클릭하면 FRED 데이터 수집, 연준 커뮤니케이션 분석, 10개 에이전트 추론이 시작됩니다. 1~3분 소요.",
    cycleRunning: "사이클 실행 중… 1~3분 후 결과 확인",
    triggerFailed: "실행 실패",

    agents: {
      Behavioral: "행동 분석",
      NLP: "NLP 감성",
      History: "역사적 사이클",
      Academic: "테일러 준칙",
      Projections: "점도표",
      FOMC_Minutes: "FOMC 의사록",
      Macro_Data: "거시 데이터",
      Political_Economy: "정치경제",
      Regional: "지역 연준",
      Consensus: "시장 컨센서스",
    },

    activityMessages: [
      { agent: "거시 데이터",     msg: "FRED DFF, CPI, NFP 시계열 수집 중…" },
      { agent: "NLP 감성",        msg: "연준 의장 연설 감성 분석 중…" },
      { agent: "FOMC 의사록",     msg: "의사록 매파/비둘기 균형 추출 중…" },
      { agent: "테일러 준칙",     msg: "테일러 준칙 중립금리 계산 중…" },
      { agent: "행동 분석",       msg: "기자회견 발화 패턴 분석 중…" },
      { agent: "역사적 사이클",   msg: "현재 사이클과 2004~2006 사이클 매칭 중…" },
      { agent: "지역 연준",       msg: "12개 지역 연준 총재 발언 수집 중…" },
      { agent: "시장 컨센서스",   msg: "CME FedWatch 확률 파싱 중…" },
      { agent: "점도표",          msg: "점도표 중앙값 및 분산 해석 중…" },
      { agent: "정치경제",        msg: "제도적 압력 신호 평가 중…" },
      { agent: "거시 데이터",     msg: "FRED GS10 365개 데이터 포인트 수신 완료…" },
      { agent: "NLP 감성",        msg: "최근 연설에서 매파 문구 3개 감지…" },
      { agent: "테일러 준칙",     msg: "테일러 준칙: r* = 2.8% vs 현재 4.33%…" },
      { agent: "FOMC 의사록",     msg: "최신 의사록 매파/비둘기 비율: 1.4:1…" },
      { agent: "시장 컨센서스",   msg: "CME FedWatch: 6월 동결 확률 72%…" },
      { agent: "역사적 사이클",   msg: "최적 유사 사이클: 2019 중간 조정 패턴…" },
      { agent: "오케스트레이터",  msg: "10개 에이전트 신호 가중 집계 중…" },
      { agent: "오케스트레이터",  msg: "EMA 안정화 필터 적용 중…" },
      { agent: "오케스트레이터",  msg: "예측 업데이트 완료. 다음 게시: 오전 8시 KST" },
    ],

    // Daily Briefing
    dailyBrief: "데일리 브리프",
    briefingTitle: "일일 매크로 브리핑",
    briefingLatest: "오늘의 브리핑",
    briefingArchive: "이전 브리핑",
    briefingGenerating: "브리핑 생성 중…",
    briefingEmpty: "아직 브리핑이 없습니다. 매일 오전 7시 30분 KST에 자동 생성됩니다.",
    briefingFailed: "생성 실패",
    briefingGeneratedAt: "생성 시각",
    briefingArticles: "개 기사 /",
    briefingSources: "개 소스",
    briefingDisclaimer: "공개 정보를 기반으로 AI가 생성한 참고 자료이며, 투자 조언이 아닙니다.",
    briefingWhatChanged: "어제와 달라진 점",
    briefingRateSignal: "금리 경로 시그널",
    briefingWatchNext: "주목할 이벤트",
    briefingExecSummary: "핵심 요약",
    briefingMarketImpact: "시장 영향",
    briefingSourceList: "출처",
    briefingGenerate: "즉시 생성",
    briefingDate: "브리핑 날짜",
    briefingNotAvail: "해당 날짜 브리핑 없음",
    briefingFallback: "다른 언어 버전을 표시합니다",
    briefingSelect: "날짜 선택",
  },
} as const;

export type Translations = typeof t.en;
